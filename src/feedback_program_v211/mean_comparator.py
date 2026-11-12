"""Declared ablation: eight paired observations, positive mean, no error guarantee.

The V210 identity/chronology checks and observation accounting are reused.
Intermediate e-values are diagnostics ONLY and do not determine this arm's stop.
No old class or instance is monkeypatched.
"""
import math
from feedback_program_v210.evidence import EvidenceBook, PairedTrial


class MeanEightTrial(PairedTrial):
    def add_pair(self, observation):
        super().add_pair(observation)
        self.status = ('continue' if self.n < 8 else
                       'adopt' if sum(self.differences) > 0 else 'unresolved_keep')
        return self.status

    def summary(self):
        result = super().summary()
        result['alpha_spent'] = None
        result['validation_rule'] = 'eight_pair_positive_mean_no_error_guarantee'
        return result


class MeanEightBook(EvidenceBook):
    def start(self, reference, candidate, known_through_id, horizon, switch_cost,
              max_pairs, pair_cost=0., epsilon=.2):
        if max_pairs != 8 or switch_cost != 0 or pair_cost != 0:
            raise ValueError('This explicit ablation is exactly eight pairs and a zero cost threshold')
        reference.assert_frozen()
        candidate.assert_frozen()
        if reference.goal != candidate.goal or horizon < 1 or not 0 <= epsilon <= 1:
            raise ValueError('Common objective and valid fixed budget required')
        self.issued += 1
        trial = MeanEightTrial(self, self.issued, self.alpha/(self.issued*(self.issued+1)),
                              reference, candidate,
                              max(known_through_id, reference.last_fact_id, candidate.last_fact_id,
                                  self.last_observation_id),
                              horizon, switch_cost, max_pairs, pair_cost, epsilon)
        self.trials.append(trial)
        return trial
