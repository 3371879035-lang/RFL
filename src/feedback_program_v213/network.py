"""V5: finite behavior classes, leased expert mixing and prequential structure probes.

Analytic neural Parameters stay fixed. Only explicit factual/algorithmic buffers
change. No environment, hidden target, optimizer, or simulated outcome is used.
"""
from dataclasses import dataclass
from itertools import product
import copy
import hashlib
import json
import math
import time

import torch
from torch import nn
from torch.nn import functional as F

from feedback_program_v210.network import Fact, FrozenCandidate, Nomination, TemporalRelation


class BehaviorBank:
    """Exhaustive certificate on a declared finite Cartesian input domain."""
    def __init__(self, reference, candidates, epsilon=.2, context_budget=4096):
        started = time.perf_counter()
        if not 0 <= epsilon <= 1:
            raise ValueError('epsilon must be a probability')
        self.reference, self.epsilon = reference, float(epsilon)
        head = reference._head
        self.cardinalities = tuple(head.lift.cardinalities)
        self.actions, self.goal = head.actions, reference.goal
        size = math.prod(self.cardinalities)
        if size > context_budget:
            raise ValueError('Complete domain exceeds certificate budget; equivalence unknown')
        self.contexts = tuple(product(*(range(c) for c in self.cardinalities)))
        groups = {}
        self.signature_by_identity = {}
        self.forward_calls = 0
        for policy in [reference, *candidates]:
            policy.assert_frozen()
            if (policy._owner is not reference._owner or policy.goal != self.goal
                    or policy._head.actions != self.actions
                    or tuple(policy._head.lift.cardinalities) != self.cardinalities):
                raise ValueError('Local candidates must share goal and complete public schema')
            # Same scalar neural execution as actual actions; no approximate cache.
            signature = tuple(policy.act(row) for row in self.contexts)
            self.forward_calls += len(self.contexts)
            if epsilon == 1:
                signature = (-1,)*len(self.contexts)
            self.signature_by_identity[policy.identity] = signature
            groups.setdefault(signature, {})[policy.identity] = policy
        self.signatures = tuple(sorted(groups))
        self.members = tuple(tuple(sorted(groups[s])) for s in self.signatures)
        self.policies = tuple(min(groups[s].values(), key=lambda p:
            (len(p._head.lift.values), p._head.lift.structure, p.identity)) for s in self.signatures)
        self.reference_class = self.signatures.index(self.signature_by_identity[reference.identity])
        self.seconds = time.perf_counter()-started

    @property
    def has_new_behavior(self):
        return len(self.policies) > 1

    def summary(self):
        return {'domain_size': len(self.contexts), 'behavior_classes': len(self.policies),
                'members': self.members, 'signatures': self.signatures,
                'representatives': [p.identity for p in self.policies],
                'reference_class': self.reference_class, 'epsilon': self.epsilon,
                'certificate_neural_calls': self.forward_calls, 'seconds': self.seconds}


@dataclass(frozen=True)
class ActionReceipt:
    lease_id: str
    ordinal: int
    observation_id: int
    context: tuple
    probabilities: tuple
    expert_probabilities: tuple
    reference_probabilities: tuple
    total_variation: float


class TrialLedger:
    """Cumulative expected one-step utility-risk budget, not a safety certificate."""
    def __init__(self, risk_limit):
        if not math.isfinite(risk_limit) or risk_limit < 0:
            raise ValueError('Declare a finite nonnegative cumulative trial risk limit')
        self.risk_limit = float(risk_limit)
        self.reserved_risk = 0.
        self.leases = []
        self.last_observation_id = -1

    def start(self, bank, horizon, risk_budget, known_through_id):
        if (type(horizon) is not int or horizon < 1 or not math.isfinite(risk_budget)
                or risk_budget < 0 or not 0 < bank.epsilon < 1):
            raise ValueError('Finite horizon, risk budget, and supported nonuniform exploration required')
        if self.leases and not self.leases[-1].closed:
            raise ValueError('Finish the current lease before opening another')
        if not bank.has_new_behavior or risk_budget == 0:
            return None
        rho = min(1., risk_budget/(horizon*(1.-bank.epsilon)))
        reserved = horizon*rho*(1.-bank.epsilon)
        if self.reserved_risk+reserved > self.risk_limit+1e-12:
            raise ValueError('Cumulative trial risk budget exhausted')
        cutoff = max(known_through_id, self.last_observation_id,
                     bank.reference.last_fact_id, *(p.last_fact_id for p in bank.policies))
        lease = TrialMixture(self, len(self.leases)+1, bank, horizon, rho, cutoff)
        self.leases.append(lease)
        self.reserved_risk += reserved
        return lease


class TrialMixture(nn.Module):
    def __init__(self, ledger, index, bank, horizon, rho, cutoff):
        super().__init__()
        self.ledger, self.bank = ledger, bank
        self.reference = bank.reference
        self.candidates = nn.ModuleList(bank.policies)
        self.goal, self.actions, self.epsilon = bank.goal, bank.actions, bank.epsilon
        self.horizon, self.rho, self.cutoff = horizon, rho, cutoff
        m = len(self.candidates)
        self.eta = math.sqrt(2*rho*math.log(m)/(horizon*self.actions)) if m > 1 else 0.
        self.register_buffer('log_weights', torch.full((m,), -math.log(m), dtype=torch.float64))
        metadata = [index, self.reference.identity, [p.identity for p in self.candidates],
                    horizon, rho, cutoff, self.epsilon, self.goal]
        self.identity = hashlib.sha256(json.dumps(metadata).encode()).hexdigest()
        self.n = 0
        self.last_observation_id = cutoff
        self.pending = None
        self.closed = False
        self.total_variation_spent = 0.
        self.neural_calls = 0
        self.observations = []
        self.eval().requires_grad_(False)

    def _policy_probabilities(self, policy, rows):
        values = torch.stack([policy([row])[0] for row in rows])
        self.neural_calls += len(rows)
        choices = values.argmax(-1)
        return ((1.-self.epsilon)*F.one_hot(choices, self.actions).to(torch.float64)
                +self.epsilon/self.actions)

    def _parts(self, rows):
        experts = torch.stack([self._policy_probabilities(p, rows) for p in self.candidates], dim=1)
        reference = self._policy_probabilities(self.reference, rows)
        q = torch.einsum('m,bma->ba', torch.softmax(self.log_weights, 0), experts)
        actual = (1.-self.rho)*reference+self.rho*q
        return actual, experts, reference

    def forward(self, rows):
        return self._parts(rows)[0]

    @torch.no_grad()
    def offer(self, context, observation_id):
        if self.closed or self.n >= self.horizon or self.pending is not None:
            raise ValueError('A live lease requires exactly one result per offered action')
        if type(observation_id) is not int or observation_id <= self.last_observation_id:
            raise ValueError('A new post-freeze observation ID is required')
        probabilities, experts, reference = self._parts([context])
        tv = float((probabilities[0]-reference[0]).abs().sum()/2)
        receipt = ActionReceipt(self.identity, self.n, observation_id, tuple(context),
                                tuple(probabilities[0].tolist()),
                                tuple(tuple(row) for row in experts[0].tolist()),
                                tuple(reference[0].tolist()), tv)
        self.pending = receipt
        return receipt

    @torch.no_grad()
    def observe(self, receipt, fact):
        if receipt is not self.pending or receipt is None or self.closed:
            raise ValueError('Use the outstanding action receipt exactly once')
        if (type(fact) is not Fact or fact.id != receipt.observation_id
                or fact.context != receipt.context or fact.policy_id != self.identity
                or type(fact.action) is not int or not 0 <= fact.action < self.actions
                or type(fact.outcome) is not int or not 0 <= fact.outcome < len(self.goal)):
            raise ValueError('Actual fact must match the offered policy, context and schema')
        if (not math.isfinite(fact.propensity) or not 0 < fact.propensity <= 1
                or abs(fact.propensity-receipt.probabilities[fact.action]) > 1e-12):
            raise ValueError('Log the actual mixture propensity, not a component propensity')
        experts = torch.tensor(receipt.expert_probabilities, dtype=torch.float64)
        loss = 1.-self.goal[fact.outcome]
        estimate = experts[:, fact.action]*loss/fact.propensity
        before = torch.softmax(self.log_weights, 0).tolist()
        self.log_weights -= self.eta*estimate
        self.log_weights -= torch.logsumexp(self.log_weights, 0)
        self.n += 1
        self.last_observation_id = fact.id
        self.ledger.last_observation_id = fact.id
        self.total_variation_spent += receipt.total_variation
        self.observations.append(fact)
        self.pending = None
        return {'before_weights': before, 'estimated_losses': estimate.tolist(),
                'after_weights': torch.softmax(self.log_weights, 0).tolist(),
                'total_variation': receipt.total_variation}

    def finish(self):
        if self.closed or self.pending is not None or self.n != self.horizon:
            raise ValueError('Only a completed lease can produce a nomination')
        for p in [self.reference, *self.candidates]:
            p.assert_frozen()
        # Classes have a stable lexical order; exact numerical ties take the first.
        index = int(self.log_weights.argmax())
        self.closed = True
        return Nomination(self.candidates[index], self.reference.identity, self.last_observation_id)

    def summary(self):
        return {'lease_id': self.identity, 'episodes': self.n, 'horizon': self.horizon,
                'rho': self.rho, 'eta': self.eta, 'behavior_classes': len(self.candidates),
                'log_weights': self.log_weights.tolist(),
                'weights': torch.softmax(self.log_weights, 0).tolist(),
                'tv_spent': self.total_variation_spent,
                'reserved_expected_loss_bound': self.horizon*self.rho*(1.-self.epsilon),
                'neural_calls': self.neural_calls, 'closed': self.closed,
                'permanent_adoption': False}


def certified_trial(nomination, reference, book, *, epsilon=.2, context_budget=4096, **budget):
    """A post-lease nomination is not adoption. The old evidence rule is unchanged."""
    if (type(nomination) is not Nomination or nomination.reference_identity != reference.identity):
        raise ValueError('Nomination must refer to this incumbent')
    bank = BehaviorBank(reference, [nomination.candidate], epsilon, context_budget)
    if not bank.has_new_behavior:
        return None
    return book.start(reference, nomination.candidate,
                      known_through_id=nomination.known_through_id, epsilon=epsilon, **budget)


class ShadowRelationProbe(nn.Module):
    """Predict-before-update model comparison; never changes the incumbent itself."""
    def __init__(self, baseline, structure, history, observations):
        super().__init__()
        if type(observations) is not int or observations < 1:
            raise ValueError('Declare a finite fresh-observation probe budget')
        baseline.assert_frozen()
        if (baseline.last_fact_id != (history[-1].id if history else -1)
                or baseline._head.n != len(history)):
            raise ValueError('Baseline and factual archive must have the same cutoff')
        h = baseline._head
        self.baseline = copy.deepcopy(h)
        self.shadow = TemporalRelation(h.lift.cardinalities, tuple(structure), h.actions,
                                       h.outcomes, h.block_size, h.hazard)
        started = time.perf_counter()
        for fact in history:
            self.shadow.observe(fact)
        self.replay_reads = len(history)
        self.replay_seconds = time.perf_counter()-started
        self.goal, self.owner = baseline.goal, baseline._owner
        self.last_fact_id = baseline.last_fact_id
        self.horizon = observations
        self.n = 0
        self.log_gain = 0.
        self.complexity_cost = max(0, len(self.shadow.lift.values)-len(h.lift.values))*math.log(2.)
        self.eval().requires_grad_(False)

    @torch.no_grad()
    def observe(self, fact):
        if self.n >= self.horizon or type(fact) is not Fact or fact.id <= self.last_fact_id:
            raise ValueError('A probe needs new facts within its declared horizon')
        if not 0 <= fact.action < self.shadow.actions or not 0 <= fact.outcome < self.shadow.outcomes:
            raise ValueError('Fact outside the public action/outcome schema')
        # Both probability vectors exist before either model learns this outcome.
        p0 = self.baseline([fact.context])[0][0, fact.action].tolist()
        p1 = self.shadow([fact.context])[0][0, fact.action].tolist()
        gain = math.log(p1[fact.outcome])-math.log(p0[fact.outcome])
        self.baseline.observe(fact)
        self.shadow.observe(fact)
        self.log_gain += gain
        self.last_fact_id = fact.id
        self.n += 1
        return {'baseline_prediction': p0, 'shadow_prediction': p1, 'log_gain': gain}

    def finish(self):
        if self.n != self.horizon:
            raise ValueError('Complete the declared fresh probe before deciding eligibility')
        eligible = self.log_gain > self.complexity_cost
        candidate = FrozenCandidate(self.shadow, self.goal, self.last_fact_id, self.owner) if eligible else None
        return candidate, {'fresh_observations': self.n, 'replay_reads': self.replay_reads,
                           'replay_seconds': self.replay_seconds, 'log_gain': self.log_gain,
                           'complexity_cost': self.complexity_cost,
                           'candidate_eligible': eligible, 'permanent_adoption': False}
