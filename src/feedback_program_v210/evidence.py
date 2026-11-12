"""Fresh paired-outcome evidence; no predicted/replayed outcome is generated here.

The caller must provide genuine paired observations in an actual experiment.
This module checks identities and chronology, not the physical truth of a call.
"""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class PairObservation:
    pair_id: str
    reference_observation_id: int
    candidate_observation_id: int
    reference_policy_id: str
    candidate_policy_id: str
    reference_outcome: int
    candidate_outcome: int


def _log_mean_exp(values):
    maximum = max(values)
    if maximum == -math.inf:
        return maximum
    return maximum+math.log(sum(math.exp(v-maximum) for v in values)/len(values))


class EvidenceBook:
    def __init__(self, alpha):
        if not 0 < alpha < 1:
            raise ValueError('Declare the lifetime false-adoption tolerance')
        self.alpha = float(alpha)
        self.issued = 0
        self.used_observations = set()
        self.used_pairs = set()
        self.last_observation_id = -1
        self.trials = []

    def start(self, reference, candidate, known_through_id, horizon, switch_cost,
              max_pairs, pair_cost=0., epsilon=.2):
        reference.assert_frozen()
        candidate.assert_frozen()
        if reference.goal != candidate.goal:
            raise ValueError('A comparison cannot change the objective')
        if (type(horizon) is not int or horizon < 1 or switch_cost < 0
                or type(max_pairs) is not int or max_pairs < 1 or pair_cost < 0
                or not math.isfinite(switch_cost+pair_cost) or not 0 <= epsilon <= 1):
            raise ValueError('Finite, predeclared comparison costs and budgets required')
        self.issued += 1
        alpha = self.alpha/(self.issued*(self.issued+1))
        trial = PairedTrial(self, self.issued, alpha, reference, candidate,
                            max(known_through_id, reference.last_fact_id, candidate.last_fact_id,
                                self.last_observation_id),
                            horizon, switch_cost, max_pairs, pair_cost, epsilon)
        self.trials.append(trial)
        return trial


class PairedTrial:
    def __init__(self, book, index, alpha, reference, candidate, cutoff,
                 horizon, switch_cost, max_pairs, pair_cost, epsilon):
        self.book, self.index, self.alpha = book, index, alpha
        self.reference, self.candidate, self.cutoff = reference, candidate, cutoff
        self.horizon, self.switch_cost = horizon, float(switch_cost)
        self.max_pairs, self.pair_cost = max_pairs, float(pair_cost)
        self.epsilon = epsilon
        self.delta = self.switch_cost/self.horizon
        self.log_plus, self.log_minus = [0.]*4, [0.]*4
        self.n = 0
        self.differences = []
        self.status = ('same_snapshot' if reference.identity == candidate.identity else
                       'cost_dominates' if self.delta >= 1 else 'continue')

    @property
    def log_e_plus(self):
        return _log_mean_exp(self.log_plus)

    @property
    def log_e_minus(self):
        return _log_mean_exp(self.log_minus)

    def add_pair(self, observation):
        if self.status != 'continue':
            raise ValueError('This comparison is closed; do not append or silently retry it')
        if type(observation) is not PairObservation:
            raise ValueError('A paired observation record is required')
        self.reference.assert_frozen()
        self.candidate.assert_frozen()
        r = observation
        if (r.reference_policy_id != self.reference.identity
                or r.candidate_policy_id != self.candidate.identity):
            raise ValueError('Observed policies differ from the frozen comparison')
        ids = (r.reference_observation_id, r.candidate_observation_id)
        if (any(type(i) is not int or i <= max(self.cutoff, self.book.last_observation_id)
                for i in ids) or ids[0] == ids[1]
                or any(i in self.book.used_observations for i in ids)
                or r.pair_id in self.book.used_pairs):
            raise ValueError('Each pair must contain new, distinct post-freeze observations')
        goal = self.reference.goal
        if (type(r.reference_outcome) is not int or type(r.candidate_outcome) is not int
                or not 0 <= r.reference_outcome < len(goal)
                or not 0 <= r.candidate_outcome < len(goal)):
            raise ValueError('Outcome outside the declared public schema')
        self.book.used_observations.update(ids)
        self.book.used_pairs.add(r.pair_id)
        self.book.last_observation_id = max(ids)
        difference = goal[r.candidate_outcome]-goal[r.reference_outcome]
        # Convex form avoids cancellation at D=-1 or D=+1 with q=1.
        for j, q in enumerate((.25, .5, .75, 1.)):
            plus = (1.-q)+q*(1.+difference)/(1.+self.delta)
            minus = (1.-q)+q*(1.-difference)/(1.-self.delta)
            self.log_plus[j] += math.log(plus) if plus else -math.inf
            self.log_minus[j] += math.log(minus) if minus else -math.inf
        self.differences.append(difference)
        self.n += 1
        threshold = -math.log(self.alpha)
        if self.log_e_plus >= threshold:
            self.status = 'adopt'
        elif self.log_e_minus >= threshold:
            self.status = 'not_worth_cost'
        elif self.n >= self.max_pairs:
            self.status = 'unresolved_keep'
        return self.status

    def summary(self):
        plus, minus = self.log_e_plus, self.log_e_minus
        return {'trial_index': self.index, 'alpha_spent': self.alpha, 'status': self.status,
                'reference': self.reference.identity, 'candidate': self.candidate.identity,
                'pairs': self.n, 'max_pairs': self.max_pairs, 'effect_cost_threshold': self.delta,
                'horizon': self.horizon, 'switch_cost': self.switch_cost,
                'epsilon': self.epsilon,
                'pair_cost_spent': self.n*self.pair_cost,
                'mean_difference': sum(self.differences)/self.n if self.n else None,
                'log_e_plus': '-inf' if plus == -math.inf else plus,
                'log_e_minus': '-inf' if minus == -math.inf else minus}
