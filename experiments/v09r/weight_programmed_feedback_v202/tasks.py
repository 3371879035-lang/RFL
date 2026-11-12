"""New small abstract decision processes, not games or reused V200 fixtures.

Hidden transition/outcome rules live only here. Learners receive numeric public
observations and the facts that have actually occurred; no table or best action.
"""
import numpy as np


class Task:
    def __init__(self, seed, family):
        self.family = family
        rng = np.random.default_rng(seed)
        self.labels = rng.permutation(64)
        self.columns = rng.permutation(6)
        self.action_order = rng.permutation(2)
        self.actions = np.eye(6, dtype=np.float32)[self.action_order]
        self.good = rng.integers(0, 2, 4)
        self.secrets = rng.integers(0, 2, (4, 3))

    def observation(self, state):
        code = int(self.labels[state])
        vector = np.array([(code >> j) & 1 for j in range(6)], np.float32)
        return vector[self.columns]

    def begin(self, case, cycle, uniforms):
        return Episode(self, case, cycle, uniforms)


class Episode:
    def __init__(self, task, case, cycle, uniforms):
        self.task, self.case, self.cycle = task, int(case), int(cycle)
        self.uniforms = uniforms
        self.t, self.prefix, self.done = 0, [], False
        self.depth = (2 if case % 2 == 0 else 5) if task.family == 'delayed_choice' else (3 if task.family == 'joint_sequence' else 2)

    def observe(self):
        if self.task.family == 'joint_sequence':
            # Public distinct prefix states make the process Markov. No secret
            # action sequence or goodness flag is in these opaque descriptors.
            node = (2 ** self.t - 1) + sum(bit * 2 ** (self.t - j - 1) for j, bit in enumerate(self.prefix))
            state = self.case * 7 + node if not self.done else 60 + self.case
        else:
            # Root + two branches, each with up to four distinct successors.
            state = self.case * 11 if self.t == 0 else self.case * 11 + 1 + self.prefix[0] * 5 + self.t - 1
        return self.task.observation(state)

    def step(self, chosen):
        assert not self.done and chosen in (0, 1)
        # Candidate descriptors and action identity stay consistent within task.
        self.prefix.append(int(chosen))
        self.t += 1
        self.done = self.t == self.depth
        facts, known = np.zeros(3, np.float32), np.zeros(3, bool)
        if self.done:
            if self.task.family == 'joint_sequence':
                good = bool(np.array_equal(self.prefix, self.task.secrets[self.case]))
                success = float(good)
            else:
                desired = int(self.task.good[self.case])
                if self.task.family == 'stochastic_reversal' and self.cycle >= 8:
                    desired = 1 - desired
                good = self.prefix[0] == desired
                success = float(self.uniforms[-1] < (.8 if good else .2)) if self.task.family == 'stochastic_reversal' else float(good)
            facts = np.array([success, 1. - success, 1. / self.depth], np.float32)
            known[:] = True
        return self.observe(), facts, known, self.done
