"""Fresh abstract task instances. No game adaptation or task-specific learner."""
import numpy as np


class Task:
    def __init__(self, seed, family):
        self.family = family
        rng = np.random.default_rng(seed)
        self.labels = rng.permutation(64)
        self.columns = rng.permutation(6)
        self.actions = np.eye(6, dtype=np.float32)[rng.permutation(2)]
        self.good = rng.integers(0, 2, 4)
        self.secrets = rng.integers(0, 2, (4, 3))

    def observation(self, state):
        code = int(self.labels[state])
        return np.array([(code >> j) & 1 for j in range(6)], np.float32)[self.columns]

    def begin(self, case, cycle, uniforms):
        return Episode(self, case, cycle, uniforms)


class Episode:
    def __init__(self, task, case, cycle, uniforms):
        self.task, self.case, self.cycle, self.uniforms = task, int(case), int(cycle), uniforms
        self.t, self.prefix, self.done = 0, [], False
        self.depth = (2 if case % 2 == 0 else 5) if task.family == 'delayed_choice' else (3 if task.family == 'joint_sequence' else 2)

    def observe(self):
        if self.task.family == 'joint_sequence':
            node = (2 ** self.t - 1) + sum(bit * 2 ** (self.t - j - 1) for j, bit in enumerate(self.prefix))
            state = self.case * 7 + node if not self.done else 60 + self.case
        else:
            state = self.case * 11 if self.t == 0 else self.case * 11 + 1 + self.prefix[0] * 5 + self.t - 1
        return self.task.observation(state)

    def step(self, chosen):
        assert not self.done and chosen in (0, 1)
        self.prefix.append(int(chosen))
        self.t += 1
        self.done = self.t == self.depth
        facts, known = np.zeros(3, np.float32), np.zeros(3, bool)
        if self.done:
            if self.task.family == 'joint_sequence':
                success = float(np.array_equal(self.prefix, self.task.secrets[self.case]))
            else:
                desired = int(self.task.good[self.case])
                if self.task.family == 'stochastic_reversal' and self.cycle >= 8:
                    desired = 1 - desired
                good = self.prefix[0] == desired
                success = float(self.uniforms[-1] < (.8 if good else .2)) if self.task.family.startswith('stochastic_') else float(good)
            facts = np.array([success, 1. - success, 1. / self.depth], np.float32)
            known[:] = True
        return self.observe(), facts, known, self.done
