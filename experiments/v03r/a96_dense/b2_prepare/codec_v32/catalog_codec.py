"""Pure subset/conditional-target syntax codec. No RNG, learner or file access."""
from bisect import bisect_right
from collections import defaultdict
from fractions import Fraction
from math import comb, prod


def integer(value):
    if type(value) is not int:
        raise ValueError('exact integer required; bool/float rejected')
    return value


def choose(n, k):
    return comb(n, k) if 0 <= k <= n else 0


class SubsetCodec:
    def __init__(self, groups, targets):
        self.groups = tuple(tuple(g) for g in groups)
        self.targets = tuple(tuple(t) for t in targets)
        self.n = len(self.groups)
        if not self.n or len(self.targets) != self.n:
            raise ValueError('nonempty aligned eligible catalog required')
        for values in self.targets:
            if not values or any(type(v) is not int for v in values) or tuple(sorted(set(values))) != values:
                raise ValueError('distinct sorted legal integer targets required')
        index = defaultdict(list)
        for i, g in enumerate(self.groups):
            index[g].append(i)
        self.group_indices = {g: tuple(v) for g, v in index.items()}

    def _cell(self, k, shape):
        integer(k)
        if not 1 <= k <= 8 or shape not in ('singleton', 'no-shape', 'clustered', 'distributed'):
            raise ValueError('unsupported syntax cell')
        if (shape == 'singleton' and k != 1) or (shape in ('clustered', 'distributed') and k == 1):
            raise ValueError('shape/k mismatch')

    def _prefix(self, prefix):
        q = tuple(prefix)
        if any(type(i) is not int or not 0 <= i < self.n for i in q) or tuple(sorted(set(q))) != q:
            raise ValueError('sorted unique in-range contexts required')
        return q

    def completions(self, prefix, k, shape):
        self._cell(k, shape)
        q = self._prefix(prefix)
        remaining = k-len(q)
        if remaining < 0:
            raise ValueError('prefix longer than cell')
        start = q[-1]+1 if q else 0
        total = choose(self.n-start, remaining)
        if shape in ('singleton', 'no-shape'):
            return total
        if not q:
            monochrome = sum(choose(len(v), k) for v in self.group_indices.values())
            return monochrome if shape == 'clustered' else total-monochrome
        seen = {self.groups[i] for i in q}
        if len(seen) >= 2:
            return 0 if shape == 'clustered' else total
        indices = self.group_indices[self.groups[q[0]]]
        same = choose(len(indices)-bisect_right(indices, q[-1]), remaining)
        return same if shape == 'clustered' else total-same

    def size(self, k, shape):
        return self.completions((), k, shape)

    def unrank(self, rank, k, shape):
        integer(rank)
        if not 0 <= rank < self.size(k, shape):
            raise ValueError('context rank outside nonempty cell')
        prefix = ()
        for depth in range(k):
            for i in range(prefix[-1]+1 if prefix else 0, self.n):
                count = self.completions(prefix+(i,), k, shape)
                if rank < count:
                    prefix += (i,)
                    break
                rank -= count
            else:
                raise AssertionError('completion partition inconsistent')
        if rank != 0:
            raise AssertionError('nonzero residual')
        return prefix

    def rank(self, subset, k, shape):
        q = self._prefix(subset)
        if len(q) != k or self.completions(q, k, shape) != 1:
            raise ValueError('subset not in requested cell')
        rank, prefix = 0, ()
        for actual in q:
            for i in range(prefix[-1]+1 if prefix else 0, actual):
                rank += self.completions(prefix+(i,), k, shape)
            prefix += (actual,)
        return rank

    def target_size(self, subset):
        q = self._prefix(subset)
        if not q:
            raise ValueError('nonempty subset required')
        return prod(len(self.targets[i]) for i in q)

    def target_unrank(self, subset, code):
        integer(code)
        q = self._prefix(subset)
        if not 0 <= code < self.target_size(q):
            raise ValueError('conditional target code outside support')
        digits = []
        for i in reversed(q):
            code, digit = divmod(code, len(self.targets[i]))
            digits.append(self.targets[i][digit])
        return tuple(reversed(digits))

    def target_rank(self, subset, actions):
        q = self._prefix(subset)
        a = tuple(actions)
        if not q or len(a) != len(q) or any(type(v) is not int for v in a):
            raise ValueError('aligned integer target actions required')
        code = 0
        for i, action in zip(q, a):
            if action not in self.targets[i]:
                raise ValueError('target outside this context support')
            code = code*len(self.targets[i])+self.targets[i].index(action)
        return code

    def probability(self, subset, k, shape):
        self.rank(subset, k, shape)
        return Fraction(1, self.size(k, shape)*self.target_size(subset))
