"""Joint factual memory -> policy candidates -> held-out evidence selection.

The learner has no environment import, task family, target indices, or rule bit.
Neural parameters are analytic and frozen. Facts and policy snapshots are state.
"""
from collections import deque
from dataclasses import dataclass
from itertools import combinations, product
from pathlib import Path
import hashlib
import importlib.util
import time
import torch
from torch import nn

_path = Path(__file__).resolve().parents[2] / 'docs/feedback_math/relational_feedback_v208/network_operator.py'
_spec = importlib.util.spec_from_file_location('v208_relational_operator', _path)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
RelationalFacts = _module.RelationalFacts


def flatten_history(observations):
    return tuple(value for event in observations for value in event)


def context_index(bits):
    index = 0
    for bit in bits:
        index = 2*index + bit
    return index


def policy_digest(table):
    return hashlib.sha256(bytes(table)).hexdigest()


@dataclass(frozen=True)
class Policy:
    table: tuple
    structure: tuple

    @property
    def identity(self):
        return policy_digest(self.table)

    def act(self, observations):
        return self.table[context_index(flatten_history(observations))]

    def wire(self):
        return {'table': ''.join(map(str, self.table)), 'structure': list(self.structure), 'id': self.identity}


class RelationalFeedbackNet(nn.Module):
    def __init__(self, fields=8, max_order=2, memory_size=192):
        super().__init__()
        self.fields = fields
        structures = tuple(s for order in range(1, max_order+1)
                           for s in combinations(range(fields), order))
        self.relations = RelationalFacts((2,)*fields, structures)
        self.goal_readout = nn.Parameter(torch.tensor([0., 1.], dtype=torch.float64), requires_grad=False)
        self.history = deque(maxlen=memory_size)
        self.seen = 0
        self.rows = tuple(product((0, 1), repeat=fields))
        self.encoded_rows = self.relations.encode(self.rows)
        self.feature_table = self.relations(self.encoded_rows).detach()
        self.build_seconds = 0.
        self.eval().requires_grad_(False)

    def observe(self, public_record):
        expected = {'id', 'observations', 'actions', 'outcome', 'propensity', 'policy_id'}
        if set(public_record) != expected:
            raise ValueError('Only the public factual interface is accepted')
        bits = flatten_history(public_record['observations'])
        if len(bits) != self.fields or any(v not in (0, 1) for v in bits):
            raise ValueError('Declared binary categorical schema required')
        numerator, denominator = public_record['propensity']
        scaled_weight = 9*denominator // numerator
        if 9*denominator != scaled_weight*numerator:
            raise ValueError('Probe propensities must have exact integer scale-nine weights')
        self.history.append((public_record['id'], context_index(bits), public_record['actions'][-1],
                             public_record['outcome'], scaled_weight))
        self.seen += 1

    def candidates(self):
        started = time.perf_counter()
        items = tuple(self.history)
        if not items:
            raise ValueError('Build candidates only after factual observations')
        indices = torch.tensor([x[1] for x in items], dtype=torch.long)
        outputs = torch.zeros((len(items), 4), dtype=torch.float64)
        for i, (_, _, action, outcome, weight) in enumerate(items):
            outputs[i, 2*action+outcome] = weight
        counts = (self.feature_table[indices].T @ outputs).reshape(-1, 2, 2)
        # Counts are scaled IPS state, not counts of independent real trials.
        # Nine in each outcome cell is a declared Beta(1,1) predictive prior at this scale.
        distributions, _, _ = self.relations.factual_distribution(self.encoded_rows, counts+9.)
        goals = distributions @ self.goal_readout
        actions = goals.argmax(-1)  # [all public contexts, structure], ties -> action 0.
        _, raw_support, _ = self.relations.factual_distribution(self.encoded_rows, counts)
        policies, used = [], set()
        for j, structure in enumerate(self.relations.structures):
            table = tuple(actions[:, j].tolist())
            if table not in used:
                used.add(table)
                policies.append(Policy(table, structure))
        elapsed = time.perf_counter()-started
        self.build_seconds += elapsed
        diagnostics = {'memory_ids': [x[0] for x in items], 'seen': self.seen,
                       'counts': counts.to(torch.int64).tolist(),
                       'raw_support_fraction': float(raw_support.to(torch.float64).mean()),
                       'structures': [list(s) for s in self.relations.structures],
                       'build_seconds': elapsed}
        return policies, diagnostics

    def parameter_digest(self):
        h = hashlib.sha256()
        for name, p in self.named_parameters():
            h.update(name.encode())
            h.update(p.detach().cpu().numpy().tobytes())
        return h.hexdigest()


def ips_score(policy, public_records):
    # The candidate was frozen BEFORE these records; a common 9*n denominator is omitted.
    total = 0
    for record in public_records:
        num, den = record['propensity']
        weight = 9*den // num
        action = record['actions'][-1]
        total += int(action == policy.act(record['observations'])) * record['outcome'] * weight
    return total


def select_candidate(bank, incumbent, ranking_records, uniform_rng=None):
    alternatives = [i for i, p in enumerate(bank) if p.table != incumbent.table]
    scores = [ips_score(p, ranking_records) for p in bank]
    baseline = ips_score(incumbent, ranking_records)
    if not alternatives:
        return incumbent, None, scores, baseline
    chosen = (uniform_rng.choice(alternatives) if uniform_rng is not None else
              max(alternatives, key=lambda i: scores[i]))
    return bank[chosen], chosen, scores, baseline
