"""Candidate values pooled by local visible trajectory evidence, not ordinal ID.

This is a small hand-designed feature representation with learned consequences,
not a causal posterior or an automatically discovered representation.
"""
from dataclasses import dataclass
from selector import available_actions, candidate


@dataclass(frozen=True, slots=True)
class HistoricalVisibleStep:
    x: int
    y: int
    a_cmd: int
    a_realized: int


@dataclass(frozen=True, slots=True)
class HistoricalVisibleSequence:
    steps: tuple


def historical_visible(receipt):
    # Explicit data projection, not reconstruction of a native trace/handle.
    x, y = 0, 2
    rows = []
    for row in receipt['trace']['steps']:
        rows.append(HistoricalVisibleStep(x, y, row['a_cmd'], row['a_realized']))
        x, y = row['state']['x'], row['state']['y']
    return HistoricalVisibleSequence(tuple(rows))


def evidence_key(mode, terminal, evidence, action):
    base = (mode, terminal, any(s.a_cmd != s.a_realized for s in evidence.steps))
    if action in ('keep', 'clear_factual'):
        return base + (action,)
    i = int(action.split(':')[1]); s = evidence.steps[i]
    previous_repeat = i > 0 and (evidence.steps[i-1].x, evidence.steps[i-1].y,
                                evidence.steps[i-1].a_cmd) == (s.x, s.y, s.a_cmd)
    next_relation = ('end' if i+1 == len(evidence.steps) else
                     'stay' if (evidence.steps[i+1].x, evidence.steps[i+1].y) == (s.x, s.y) else 'move')
    return base + ('single', s.a_cmd, previous_repeat, next_relation)


class EvidenceValueTrainer:
    def __init__(self):
        self.samples = {}

    def observe(self, key, returns):
        self.samples.setdefault(key, []).extend(float(v) for v in returns)

    def freeze(self):
        return FrozenEvidenceSelector(tuple((k, len(v), sum(v)/len(v)) for k, v in sorted(self.samples.items())))


@dataclass(frozen=True, slots=True)
class FrozenEvidenceSelector:
    table: tuple

    def choose(self, mode, terminal, evidence):
        actions = available_actions(mode, evidence)
        lookup = {k: mean for k, n, mean in self.table if n > 0}
        keys = {a: evidence_key(mode, terminal, evidence, a) for a in actions}
        scores = {a: lookup[k] for a, k in keys.items() if k in lookup}
        unknown = tuple(a for a in actions if a not in scores)
        costs = {a: len(candidate(mode, evidence, a).edits) for a in actions}
        # No invented value for unseen candidates; keep must itself have support.
        # Unseen candidates are recorded, not selected by adaptive exploration.
        chosen = ('keep' if 'keep' not in scores else
                  min(scores, key=lambda a: (-scores[a], costs[a], actions.index(a))))
        return chosen, {'keys': keys, 'scores': scores, 'address_costs': costs,
                        'unknown_candidates': unknown, 'keep_unknown': 'keep' not in scores}
