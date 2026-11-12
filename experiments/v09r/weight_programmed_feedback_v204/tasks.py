"""New abstract numerical worlds. Learners never import this module."""
import numpy as np


class Task:
    def __init__(self, seed, family):
        self.family = family
        rng = np.random.default_rng(seed)
        self.labels = rng.permutation(64)
        self.small_labels = rng.permutation(16)
        self.columns = rng.permutation(6)
        self.actions = np.eye(6, dtype=np.float32)[rng.permutation(2)]
        self.good = rng.integers(0, 2, 4)
        self.thresholds = rng.uniform(-.35, .35, 3)
        self.signs = rng.integers(0, 2, 3)

    def begin(self, case, cycle, uniforms, initial_uniforms):
        return Episode(self, case, cycle, uniforms, initial_uniforms)


class Episode:
    def __init__(self, task, case, cycle, uniforms, initial_uniforms):
        self.task, self.case, self.cycle = task, int(case), int(cycle)
        self.uniforms = uniforms
        self.x = float(2. * initial_uniforms[0] - 1.)
        self.t, self.prefix, self.done = 0, [], False
        self.depth = 5 if task.family == 'continuous_delayed' else (3 if task.family.startswith('continuous_') else 2)

    def observe(self):
        continuous = self.task.family.startswith('continuous_')
        if self.task.family == 'continuous_joint':
            node = 2 ** self.t - 1 + sum(bit * 2 ** (self.t - j - 1) for j, bit in enumerate(self.prefix))
        else:
            node = 0 if self.t == 0 else 1 + self.prefix[0] * 5 + self.t - 1
        if continuous:
            code = int(self.task.small_labels[node])
            out = np.array([*[(code >> j) & 1 for j in range(4)], (self.x + 1.) / 2., self.x ** 2], np.float32)
        else:
            code = int(self.task.labels[self.case * 11 + node])
            out = np.array([(code >> j) & 1 for j in range(6)], np.float32)
        return out[self.task.columns]

    def step(self, chosen):
        assert not self.done and chosen in (0, 1)
        self.prefix.append(int(chosen))
        self.t += 1
        self.done = self.t == self.depth
        facts, known = np.zeros(3, np.float32), np.zeros(3, bool)
        if self.done:
            if self.task.family == 'continuous_joint':
                desired = (self.x > self.task.thresholds).astype(int) ^ self.task.signs
                success = float(np.array_equal(self.prefix, desired))
            else:
                desired = (int(self.x > self.task.thresholds[0]) ^ int(self.task.signs[0])
                           if self.task.family.startswith('continuous_') else int(self.task.good[self.case]))
                if self.task.family in ('abrupt_change', 'continuous_abrupt') and self.cycle >= 8:
                    desired = 1 - desired
                good = self.prefix[0] == desired
                success = (float(good) if self.task.family == 'continuous_delayed'
                           else float(self.uniforms[-1] < (.8 if good else .2)))
            facts = np.array([success, 1. - success, 1. / self.depth], np.float32)
            known[:] = True
        return self.observe(), facts, known, self.done
