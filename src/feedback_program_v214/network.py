"""Conditional applicability of real history; no residual transplantation or truth input."""
from itertools import combinations, product
import copy
import hashlib
import math

import torch
from torch import nn
from torch.nn import functional as F

from feedback_program_v210.network import Fact, RelationLift, TemporalRelation


def subsets(d, include_empty=False):
    return tuple(s for k in range(0 if include_empty else 1, d+1) for s in combinations(range(d), k))


def log_prior(structures, dimensions):
    values = torch.tensor([-len(s)*math.log(2)-math.log(math.comb(dimensions, len(s)))
                           for s in structures], dtype=torch.float64)
    return values-torch.logsumexp(values, 0)


def state_digest(model):
    digest = hashlib.sha256()
    for key, value in model.state_dict().items():
        digest.update(key.encode()); digest.update(value.detach().numpy().tobytes())
    return digest.hexdigest()


class RelationPredictor(nn.Module):
    """Common relational capacity for all controls; original temporal operators unchanged."""
    def __init__(self, cardinalities, actions=2, outcomes=2, hazard=.05, block_size=32):
        super().__init__()
        self.cardinalities = tuple(cardinalities)
        self.actions, self.outcomes = actions, outcomes
        self.hazard, self.block_size = hazard, block_size
        self.structures = subsets(len(cardinalities))
        self.heads = nn.ModuleList([TemporalRelation(cardinalities, s, actions, outcomes, block_size, hazard)
                                    for s in self.structures])
        self.register_buffer('log_structure', log_prior(self.structures, len(cardinalities)))
        self.n = 0
        self.last_id = -1
        self.eval().requires_grad_(False)

    def predict(self, rows):
        parts = torch.stack([h(rows)[0] for h in self.heads], dim=1)
        prediction = torch.einsum('s,bsao->bao', torch.softmax(self.log_structure, 0), parts)
        return prediction, parts

    def forward(self, rows):
        return self.predict(rows)[0]

    @torch.no_grad()
    def observe(self, fact, parts=None):
        if type(fact) is not Fact or type(fact.id) is not int or fact.id <= self.last_id:
            raise ValueError('New ordered actual facts required')
        if not 0 <= fact.action < self.actions or not 0 <= fact.outcome < self.outcomes:
            raise ValueError('Fact outside public action/outcome schema')
        if parts is None:
            _, parts = self.predict([fact.context])
        likelihood = parts[0, :, fact.action, fact.outcome]
        self.log_structure += likelihood.log()
        self.log_structure -= torch.logsumexp(self.log_structure, 0)
        for head in self.heads:
            head.observe(fact)
        self.n += 1
        self.last_id = fact.id


class ContextLift(nn.Module):
    """All public candidate partitions, including the empty/global partition."""
    def __init__(self, cardinalities, conditional=True):
        super().__init__()
        self.cardinalities = tuple(cardinalities)
        self.partitions = subsets(len(cardinalities), True) if conditional else ((),)
        self.offsets, self.sizes = [], []
        weights, biases = [], []
        cursor = 0
        for s in self.partitions:
            if s:
                lift = RelationLift(cardinalities, s)
                weights.append(lift.weight.detach().clone()); biases.append(lift.bias.detach().clone())
            else:
                weights.append(torch.zeros((1, sum(cardinalities)), dtype=torch.float64))
                biases.append(torch.ones(1, dtype=torch.float64))
            self.offsets.append(cursor); self.sizes.append(len(biases[-1])); cursor += len(biases[-1])
        self.weight = nn.Parameter(torch.cat(weights), requires_grad=False)
        self.bias = nn.Parameter(torch.cat(biases), requires_grad=False)
        self.cells = cursor

    def forward(self, rows):
        encoded = torch.zeros((len(rows), sum(self.cardinalities)), dtype=torch.float64)
        for i, row in enumerate(rows):
            if len(row) != len(self.cardinalities): raise ValueError('Context schema mismatch')
            offset = 0
            for value, size in zip(row, self.cardinalities):
                if type(value) is not int or not 0 <= value < size: raise ValueError('Invalid public category')
                encoded[i, offset+value] = 1.; offset += size
        phi = torch.relu(F.linear(encoded, self.weight, self.bias))
        return torch.stack([phi[:, start:start+size].argmax(-1)+start
                            for start,size in zip(self.offsets,self.sizes)], dim=1)


class ApplicabilityGate(nn.Module):
    def __init__(self, cardinalities, conditional=True, gamma=.02):
        super().__init__()
        if not 0 <= gamma < 1: raise ValueError('Declare a source reopening rate')
        self.lift = ContextLift(cardinalities, conditional)
        self.gamma = gamma
        self.register_buffer('log_sources', torch.full((self.lift.cells,2), -math.log(2), dtype=torch.float64))
        self.register_buffer('log_partitions', log_prior(self.lift.partitions, len(cardinalities)))
        self.register_buffer('visits', torch.zeros(self.lift.cells, dtype=torch.int64))
        self.updates = 0
        self.eval().requires_grad_(False)

    def predict(self, rows, historical, current):
        indices = self.lift(rows)
        weights = (1.-self.gamma)*torch.softmax(self.log_sources[indices], -1)+self.gamma/2
        grouping = torch.softmax(self.log_partitions, 0)
        sources = torch.stack((historical,current), dim=1)
        local = torch.einsum('bge,beao->bgao', weights, sources)
        prediction = torch.einsum('g,bgao->bao', grouping, local)
        history_share = torch.einsum('g,bg->b', grouping, weights[:,:,0])
        return prediction, history_share, {'indices':indices, 'weights':weights, 'local':local,
                                          'sources':sources, 'partition_weights':grouping}

    @torch.no_grad()
    def observe(self, cache, action, outcome):
        if cache['indices'].shape[0] != 1: raise ValueError('One actual observation at a time')
        cells = cache['indices'][0]
        likelihood = cache['sources'][0,:,action,outcome]
        joint = cache['weights'][0].log()+likelihood.log()[None,:]
        self.log_sources[cells] = joint-torch.logsumexp(joint, -1, keepdim=True)
        self.log_partitions += cache['local'][0,:,action,outcome].log()
        self.log_partitions -= torch.logsumexp(self.log_partitions, 0)
        self.visits[cells] += 1
        self.updates += 1


class HistoricalFeedbackNet(nn.Module):
    MODES = ('pooled_history','fresh_only','temporal_v210','global_gate','conditional_gate')

    def __init__(self, mode, history_model, temporal_model, history, epsilon=.2, goal=(0.,1.)):
        super().__init__()
        if mode not in self.MODES or not 0 < epsilon < 1: raise ValueError('Invalid mode or support')
        self.mode, self.epsilon = mode, epsilon
        self.goal = tuple(goal)
        self.register_buffer('utility', torch.tensor(goal,dtype=torch.float64))
        cards = history_model.cardinalities
        self.actions, self.outcomes = history_model.actions, history_model.outcomes
        if len(goal)!=self.outcomes or any(not 0<=v<=1 for v in goal): raise ValueError('Bounded public goal required')
        if history_model.n != len(history) or temporal_model.n != len(history):
            raise ValueError('Both history interpretations must use the complete declared archive')
        if mode == 'pooled_history': self.current = copy.deepcopy(history_model)
        elif mode == 'temporal_v210': self.current = copy.deepcopy(temporal_model)
        else: self.current = RelationPredictor(cards, self.actions, self.outcomes, hazard=.05)
        self.historical = copy.deepcopy(history_model) if mode.endswith('gate') else None
        self.gate = ApplicabilityGate(cards, conditional=(mode=='conditional_gate')) if self.historical is not None else None
        self.archive = list(history)
        self.full_context_counts = {}
        for fact in history:
            self.full_context_counts[fact.context] = self.full_context_counts.get(fact.context,0)+1
        self.last_id = history[-1].id if history else -1
        self.pending = None
        self.initial_history_digest = state_digest(self.historical) if self.historical is not None else None
        self.eval().requires_grad_(False)

    def _policy(self, prediction):
        actions = (prediction@self.utility).argmax(-1)
        return (1.-self.epsilon)*F.one_hot(actions,self.actions).to(torch.float64)+self.epsilon/self.actions

    def predict(self, rows):
        fresh, parts = self.current.predict(rows)
        if self.gate is None:
            return fresh, self._policy(fresh), None, {'parts':parts,'gate':None,'history':None,'fresh':fresh}
        historical = self.historical(rows)
        prediction, share, cache = self.gate.predict(rows,historical,fresh)
        behavior = share[:,None]*self._policy(historical)+(1.-share[:,None])*self._policy(fresh)
        return prediction, behavior, share, {'parts':parts,'gate':cache,'history':historical,'fresh':fresh}

    def forward(self, rows):
        return self.predict(rows)[0]

    @torch.no_grad()
    def offer(self, context, observation_id):
        if self.pending is not None or type(observation_id) is not int or observation_id <= self.last_id:
            raise ValueError('One new actual event per outstanding offer')
        prediction, behavior, share, cache = self.predict([context])
        wire = {'id':observation_id,'context':tuple(context),'prediction':prediction[0].tolist(),
                'behavior':behavior[0].tolist(),'history_share':float(share[0]) if share is not None else None,
                'history_prediction':cache['history'][0].tolist() if cache['history'] is not None else None,
                'fresh_prediction':cache['fresh'][0].tolist(),
                'previous_full_context_observations':self.full_context_counts.get(tuple(context),0)}
        self.pending = (wire,cache)
        return wire

    @torch.no_grad()
    def observe(self, offer, fact):
        if self.pending is None or offer is not self.pending[0] or type(fact) is not Fact:
            raise ValueError('Use the outstanding offer exactly once')
        if (fact.id != offer['id'] or fact.context != offer['context'] or fact.policy_id != self.mode
                or type(fact.action) is not int or not 0<=fact.action<self.actions
                or type(fact.outcome) is not int or not 0<=fact.outcome<self.outcomes
                or not math.isfinite(fact.propensity) or not 0<fact.propensity<=1
                or abs(fact.propensity-offer['behavior'][fact.action])>1e-12):
            raise ValueError('Fact must match the actual public action protocol')
        cache = self.pending[1]
        if self.gate is not None:
            self.gate.observe(cache['gate'],fact.action,fact.outcome)
        self.current.observe(fact,cache['parts'])
        self.archive.append(fact)
        self.full_context_counts[fact.context] = self.full_context_counts.get(fact.context,0)+1
        self.last_id = fact.id
        self.pending = None

    def assert_history_unchanged(self):
        if self.historical is not None and state_digest(self.historical)!=self.initial_history_digest:
            raise AssertionError('Frozen historical interpretation was mutated')
