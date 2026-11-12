"""Learn which visible factual address to clear, or keep the task learning.

Candidates are chronological unique visited entries, not hidden fault labels.
The value table is trained on real continuation returns, then frozen. Exact
return ties prefer fewer attempted address edits, then earlier trace position;
this is not a fitted weighted reward/cost objective or a causal posterior.
"""
from dataclasses import dataclass

from candidate_loop import Proposal
from rfl_rebuild.env.kernel import State
from rfl_rebuild.learner.store import Q, DECISION, QAddress, DecisionAddress, Edit


def feature(mode, terminal, evidence):
    return (mode, terminal, any(s.a_cmd != s.a_realized for s in evidence.steps))


def factual_edits(mode, evidence):
    edits = []; seen = set()
    for s in evidence.steps:
        st = State(s.x, s.y, s.t, s.kappa, s.phi)
        a = QAddress(st, s.z, s.m, s.a_cmd) if mode == 'dq' else DecisionAddress(st, s.z, s.m)
        if a not in seen:
            edits.append(Edit(Q if mode == 'dq' else DECISION, a, None))
            seen.add(a)
    return tuple(edits)


def available_actions(mode, evidence):
    return ('keep',) + tuple('single:' + str(i) for i in range(len(factual_edits(mode, evidence)))) + ('clear_factual',)


def candidate(mode, evidence, action):
    if action == 'keep':
        return Proposal()
    edits = factual_edits(mode, evidence)
    if action == 'clear_factual':
        return Proposal('apply', edits)
    if action.startswith('single:'):
        return Proposal('apply', (edits[int(action.split(':')[1])],))
    raise ValueError('unknown candidate')


class ValueTrainer:
    def __init__(self):
        self.samples = {}; self.costs = {}

    def observe(self, key, action, returns, address_edits):
        token = (key, action)
        if token in self.costs and self.costs[token] != address_edits:
            raise ValueError('candidate extent changed within this finite training feature')
        self.costs[token] = address_edits
        self.samples.setdefault(token, []).extend(float(x) for x in returns)

    def freeze(self):
        return FrozenAddressSelector(tuple((key, action, len(v), sum(v) / len(v), self.costs[key, action])
                                           for (key, action), v in sorted(self.samples.items())))


@dataclass(frozen=True, slots=True)
class FrozenAddressSelector:
    table: tuple

    def choose(self, mode, terminal, evidence):
        key = feature(mode, terminal, evidence)
        actions = available_actions(mode, evidence)
        scores = {a: mean for k, a, n, mean, cost in self.table if k == key and n > 0 and a in actions}
        if set(scores) != set(actions):
            return 'keep', {'feature': key, 'scores': scores, 'unknown': True}
        costs = {a: len(candidate(mode, evidence, a).edits) for a in actions}
        selected = min(actions, key=lambda a: (-scores[a], costs[a], actions.index(a)))
        return selected, {'feature': key, 'scores': scores, 'address_costs': costs, 'unknown': False}
