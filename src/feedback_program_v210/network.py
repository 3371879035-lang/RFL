"""V4 formulas: expandable relations and prequential temporal applicability.

No environment import, hidden rule, optimizer, random initialization, or Q*.
Parameters are analytic constants. Counts and hypothesis weights are buffers.
"""
from dataclasses import dataclass
from itertools import combinations, product
import copy
import hashlib
import json
import math
import time

import torch
from torch import nn
from torch.nn import functional as F


@dataclass(frozen=True)
class Fact:
    id: int
    context: tuple
    action: int
    outcome: int
    propensity: float
    policy_id: str


@dataclass(frozen=True)
class Nomination:
    candidate: object
    reference_identity: str
    known_through_id: int


class RelationLift(nn.Module):
    def __init__(self, cardinalities, structure):
        super().__init__()
        self.cardinalities = tuple(cardinalities)
        self.structure = tuple(structure)
        if not self.cardinalities or any(type(c) is not int or c < 1 for c in self.cardinalities):
            raise ValueError('Positive finite categorical cardinalities required')
        if (not self.structure or tuple(sorted(set(self.structure))) != self.structure
                or any(j < 0 or j >= len(self.cardinalities) for j in self.structure)):
            raise ValueError('A nonempty sorted subset of public field indices is required')
        self.offsets = tuple(sum(self.cardinalities[:j]) for j in range(len(self.cardinalities)))
        self.values = tuple(product(*(range(self.cardinalities[j]) for j in self.structure)))
        weight = torch.zeros((len(self.values), sum(self.cardinalities)), dtype=torch.float64)
        for r, values in enumerate(self.values):
            for j, value in zip(self.structure, values):
                weight[r, self.offsets[j]+value] = 1.
        self.weight = nn.Parameter(weight, requires_grad=False)
        self.bias = nn.Parameter(torch.full((len(self.values),), 1.-len(self.structure),
                                            dtype=torch.float64), requires_grad=False)

    def encode(self, rows):
        encoded = torch.zeros((len(rows), sum(self.cardinalities)), dtype=torch.float64)
        for i, row in enumerate(rows):
            if len(row) != len(self.cardinalities):
                raise ValueError('Context must match the declared categorical schema')
            for j, value in enumerate(row):
                if type(value) is not int or not 0 <= value < self.cardinalities[j]:
                    raise ValueError('Context category outside the declared schema')
                encoded[i, self.offsets[j]+value] = 1.
        return encoded

    def forward(self, encoded):
        return torch.relu(F.linear(encoded, self.weight, self.bias))


class TemporalRelation(nn.Module):
    def __init__(self, cardinalities, structure, actions, outcomes, block_size, hazard):
        super().__init__()
        if actions < 1 or outcomes < 2 or block_size < 1 or not 0 <= hazard < 1:
            raise ValueError('Invalid action/outcome schema or block-change prior')
        self.lift = RelationLift(cardinalities, structure)
        self.actions, self.outcomes = actions, outcomes
        self.block_size, self.hazard = block_size, float(hazard)
        self.register_buffer('counts', torch.zeros((1, len(self.lift.values), actions, outcomes),
                                                   dtype=torch.float64))
        self.register_buffer('log_weights', torch.zeros(1, dtype=torch.float64))
        self.starts = (0,)
        self.n = 0

    def _before_next_observation(self):
        # Birth BEFORE the new outcome, and only at predeclared block boundaries.
        if self.n and self.n % self.block_size == 0 and self.hazard:
            counts = torch.cat((self.counts, torch.zeros_like(self.counts[:1])))
            weights = torch.cat((self.log_weights+math.log1p(-self.hazard),
                                 self.log_weights.new_tensor([math.log(self.hazard)])))
            return counts, weights, self.starts+(self.n,)
        return self.counts, self.log_weights, self.starts

    def forward(self, rows):
        phi = self.lift(self.lift.encode(rows))
        counts, log_weights, _ = self._before_next_observation()
        selected = torch.einsum('bc,rcao->brao', phi, counts)
        conditional = (selected+1.)/(selected.sum(-1, keepdim=True)+self.outcomes)
        probabilities = torch.einsum('r,brao->bao', torch.softmax(log_weights, 0), conditional)
        # The first hypothesis contains each archived fact exactly once.
        actual_support = selected[:, 0].sum(-1)
        return probabilities, actual_support

    @torch.no_grad()
    def observe(self, fact):
        phi = self.lift(self.lift.encode([fact.context]))[0]
        cell = int(phi.argmax())
        counts, log_weights, starts = self._before_next_observation()
        selected = counts[:, cell, fact.action]
        likelihood = (selected[:, fact.outcome]+1.)/(selected.sum(-1)+self.outcomes)
        log_joint = log_weights+likelihood.log()
        log_prediction = torch.logsumexp(log_joint, 0)
        self.log_weights = log_joint-log_prediction
        self.counts = counts.clone()
        self.counts[:, cell, fact.action, fact.outcome] += 1.
        self.starts, self.n = starts, self.n+1
        return float(log_prediction)


def parameter_digest(module):
    digest = hashlib.sha256()
    for name, parameter in module.named_parameters():
        digest.update(name.encode())
        digest.update(parameter.detach().cpu().numpy().tobytes())
    return digest.hexdigest()


class FrozenCandidate(nn.Module):
    """Independent neural execution snapshot; no observe or training method."""
    def __init__(self, head, goal, last_fact_id, owner):
        super().__init__()
        self._head = copy.deepcopy(head)
        self.goal = tuple(float(x) for x in goal)
        if len(self.goal) != head.outcomes or any(not 0 <= x <= 1 for x in self.goal):
            raise ValueError('One bounded utility in [0,1] per outcome is required')
        self.register_buffer('_goal', torch.tensor(self.goal, dtype=torch.float64))
        self.last_fact_id, self._owner = last_fact_id, owner
        self.eval().requires_grad_(False)
        self.identity = self._digest()

    def _digest(self):
        head = self._head
        meta = (head.lift.cardinalities, head.lift.structure, head.actions, head.outcomes,
                head.block_size, head.hazard, head.starts, head.n, self.goal)
        digest = hashlib.sha256(json.dumps(meta).encode())
        for name, value in self.state_dict().items():
            digest.update(name.encode())
            digest.update(value.detach().cpu().numpy().tobytes())
        return digest.hexdigest()

    def assert_frozen(self):
        if self._digest() != self.identity:
            raise ValueError('A frozen candidate was modified during comparison')

    def forward(self, rows):
        probabilities, _ = self._head(rows)
        return probabilities @ self._goal

    def act(self, context):
        with torch.no_grad():
            return int(self([context])[0].argmax())

    def action_probability(self, context, action, epsilon):
        return (1.-epsilon)*int(self.act(context) == action)+epsilon/self._head.actions


class AdaptiveFeedbackNet(nn.Module):
    def __init__(self, cardinalities, actions=2, outcomes=2, block_size=32, hazard=.05):
        super().__init__()
        if not cardinalities or any(type(c) is not int or c < 1 for c in cardinalities):
            raise ValueError('A finite categorical observation schema is required')
        if actions < 1 or outcomes < 2 or block_size < 1 or not 0 <= hazard < 1:
            raise ValueError('Invalid action/outcome schema or block-change prior')
        self.cardinalities = tuple(cardinalities)
        self.actions, self.outcomes = actions, outcomes
        self.block_size, self.hazard = block_size, hazard
        self.heads = nn.ModuleList()
        self.history = []
        self._owner = object()
        d = len(self.cardinalities)
        self._frontier = (s for k in range(1, d+1) for s in combinations(range(d), k))
        self._pending = next(self._frontier, None)
        self.replay_reads = 0
        self.growth_seconds = 0.
        self.active = None
        self._trial = None
        self.decisions = []

    @property
    def last_fact_id(self):
        return self.history[-1].id if self.history else -1

    def grow(self, cell_budget):
        if type(cell_budget) is not int or cell_budget < 0:
            raise ValueError('A nonnegative relation-cell budget is required')
        started = time.perf_counter()
        spent, added = 0, []
        while self._pending is not None:
            cells = math.prod(self.cardinalities[j] for j in self._pending)
            if spent+cells > cell_budget:
                break
            head = TemporalRelation(self.cardinalities, self._pending, self.actions,
                                    self.outcomes, self.block_size, self.hazard)
            for fact in self.history:
                head.observe(fact)
                self.replay_reads += 1
            self.heads.append(head)
            added.append(self._pending)
            spent += cells
            self._pending = next(self._frontier, None)
        elapsed = time.perf_counter()-started
        self.growth_seconds += elapsed
        return {'added': added, 'cells_spent': spent, 'next_structure': self._pending,
                'next_cells_needed': (math.prod(self.cardinalities[j] for j in self._pending)
                                      if self._pending is not None else 0),
                'seconds': elapsed}

    def _validate_fact(self, fact):
        if type(fact) is not Fact or type(fact.id) is not int or fact.id <= self.last_fact_id:
            raise ValueError('New ordered factual observations are required')
        if (type(fact.context) is not tuple or len(fact.context) != len(self.cardinalities)
                or any(type(v) is not int or not 0 <= v < c
                       for v, c in zip(fact.context, self.cardinalities))):
            raise ValueError('Invalid public categorical context')
        if (type(fact.action) is not int or type(fact.outcome) is not int
                or not 0 <= fact.action < self.actions or not 0 <= fact.outcome < self.outcomes
                or not 0 < fact.propensity <= 1 or not isinstance(fact.policy_id, str)):
            raise ValueError('Invalid factual action, outcome, propensity, or policy identity')

    def observe(self, fact):
        self._validate_fact(fact)
        scores = [head.observe(fact) for head in self.heads]
        self.history.append(fact)
        return scores

    def forward(self, rows, goal):
        if not self.heads:
            raise ValueError('Expand at least one public relation before predicting')
        target = torch.tensor(goal, dtype=torch.float64)
        if target.shape != (self.outcomes,) or bool(((target < 0) | (target > 1)).any()):
            raise ValueError('One bounded target per outcome is required')
        return torch.stack([head(rows)[0] @ target for head in self.heads], dim=1)

    def snapshot(self, goal):
        return [FrozenCandidate(head, goal, self.last_fact_id, self._owner) for head in self.heads]

    def set_initial_policy(self, candidate):
        if self.active is not None or candidate._owner is not self._owner:
            raise ValueError('Initial policy must be a local snapshot and can be set once')
        candidate.assert_frozen()
        self.active = candidate

    def nominate(self, candidate):
        if self.active is None or candidate._owner is not self._owner:
            raise ValueError('Nominate a local snapshot against the active policy')
        return Nomination(candidate, self.active.identity, self.last_fact_id)

    def start_trial(self, nomination, book, **budget):
        if type(nomination) is not Nomination:
            raise ValueError('A nomination with its selection-data cutoff is required')
        candidate = nomination.candidate
        if self.active is None or self._trial is not None or candidate._owner is not self._owner:
            raise ValueError('A local candidate and one serial active comparison are required')
        if nomination.reference_identity != self.active.identity:
            raise ValueError('The nomination refers to a different incumbent')
        trial = book.start(self.active, candidate,
                           known_through_id=max(self.last_fact_id, nomination.known_through_id), **budget)
        self._trial = trial
        return trial

    def record_trial_pair(self, trial, reference_fact, candidate_fact, pair_id):
        from .evidence import PairObservation
        if trial is not self._trial:
            raise ValueError('Use the outstanding frozen comparison')
        for fact, policy in ((reference_fact, trial.reference), (candidate_fact, trial.candidate)):
            self._validate_fact(fact)
            expected = policy.action_probability(fact.context, fact.action, trial.epsilon)
            if fact.policy_id != policy.identity or abs(fact.propensity-expected) > 1e-12:
                raise ValueError('The logged behavior is not the frozen trial policy')
        if reference_fact.context != candidate_fact.context:
            raise ValueError('This paired protocol requires a shared observed initial history')
        packet = PairObservation(pair_id, reference_fact.id, candidate_fact.id,
                                  reference_fact.policy_id, candidate_fact.policy_id,
                                  reference_fact.outcome, candidate_fact.outcome)
        status = trial.add_pair(packet)
        for fact in sorted((reference_fact, candidate_fact), key=lambda x: x.id):
            self.observe(fact)
        return status

    def respond_to_trial(self, trial, expansion_cell_budget=0):
        if trial is not self._trial or trial.status == 'continue':
            raise ValueError('Only the completed, outstanding comparison can change policy')
        self.active.assert_frozen()
        trial.candidate.assert_frozen()
        if self.active.identity != trial.reference.identity:
            raise ValueError('Reference policy changed during the comparison')
        if trial.status == 'adopt':
            self.active = trial.candidate
            growth = None
        else:
            growth = self.grow(expansion_cell_budget)
        record = {**trial.summary(), 'growth': growth, 'active_identity': self.active.identity}
        self.decisions.append(record)
        self._trial = None
        return record


def rank_candidates(candidates, reference, records, epsilon=.2):
    if not candidates or not records or not 0 <= epsilon <= 1:
        raise ValueError('Frozen candidates, new ranking observations and epsilon are required')
    policies = [reference, *candidates]
    cutoff = max(p.last_fact_id for p in policies)
    ids = [r.id for r in records]
    if len(ids) != len(set(ids)) or min(ids) <= cutoff:
        raise ValueError('Ranking observations must be distinct and post-freeze')
    for p in policies:
        p.assert_frozen()
        if p.goal != reference.goal or p._head.actions != reference._head.actions:
            raise ValueError('Candidates must share the actual objective and action space')
    scores = []
    for policy in policies:
        score = 0.
        for record in records:
            if not 0 < record.propensity <= 1:
                raise ValueError('Known, supported behavior propensity required')
            probability = policy.action_probability(record.context, record.action, epsilon)
            score += probability*policy.goal[record.outcome]/record.propensity
        scores.append(score/len(records))
    eligible = [i for i, p in enumerate(candidates) if p.identity != reference.identity]
    best = max(eligible, key=lambda i: scores[i+1]) if eligible else None
    chosen = reference if best is None else candidates[best]
    return Nomination(chosen, reference.identity, max(ids)), {
        'reference_score': scores[0], 'candidate_scores': scores[1:], 'chosen': best,
        'ranking_ids': ids, 'ranking_only_not_adoption': True}
