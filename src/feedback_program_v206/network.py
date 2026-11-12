"""V2 module probe: frozen arithmetic, selectable event context, real trial counts.

No environment imports or task identifiers. Binary factual outcomes only in this
prototype; this is not a replacement for the V205 additive-successor operator.
"""
from functools import lru_cache
import hashlib
import math
import torch
from torch import nn


def digest_parameters(module):
    h = hashlib.sha256()
    for name, p in module.named_parameters():
        h.update(name.encode())
        h.update(p.detach().cpu().numpy().tobytes())
    return h.hexdigest()


class Arithmetic(nn.Module):
    def __init__(self, eta=4., share=.02):
        super().__init__()
        self.loss_scale = nn.Linear(1, 1, bias=False, dtype=torch.float64)
        self.share_scale = nn.Linear(1, 1, bias=False, dtype=torch.float64)
        self.pair_readout = nn.Linear(4, 3, bias=False, dtype=torch.float64)
        self.share = share
        with torch.no_grad():
            self.loss_scale.weight.fill_(-eta)
            self.share_scale.weight.fill_(1. - share)
            self.pair_readout.weight.copy_(torch.tensor([[0., 0., 1., 1.], [0., 1., 0., 1.], [0., 1., -1., 0.]]))
        self.eval().requires_grad_(False)

    def mix_after(self, weight, loss):
        logits = weight.log() + self.loss_scale(loss[..., None]).squeeze(-1)
        updated = logits.flatten().softmax(0).reshape_as(weight)
        return self.share_scale(updated[..., None]).squeeze(-1) + self.share / weight.numel()

    def pair_means(self, counts):
        alpha = torch.tensor(counts, dtype=torch.float64) + 1.
        return self.pair_readout(alpha / alpha.sum()).tolist()


def selectors(fields, slots, recent):
    result = [('constant', -1, -1)]
    result += [('current', -1, f) for f in range(fields)]
    result += [('recent' if recent else 'past', i, f) for i in range(2 if recent else slots) for f in range(fields)]
    return tuple(result)


def features(observations, definitions):
    current, previous = observations[-1], observations[:-1]
    values = []
    for kind, pos, field in definitions:
        if kind == 'constant':
            value = 0
        elif kind == 'current':
            value = current[field + 1]
        elif kind == 'past':
            value = previous[pos][field + 1] if pos < len(previous) else 2
        else:
            value = previous[-1-pos][field + 1] if pos < len(previous) else 2
        if value not in (0, 1, 2):
            raise ValueError('This probe requires declared binary fields and missing-category 2')
        values.append(int(value))
    return torch.tensor(values, dtype=torch.long)


class Snapshot:
    def __init__(self, counts, weights, definitions):
        self.counts, self.weights = counts.clone(), weights.clone()
        self.definitions = definitions
        self.k, self.r = self.weights.shape

    def probabilities(self, observations):
        f = features(observations, self.definitions)
        selected = self.counts[torch.arange(self.k)[:, None], torch.arange(self.r)[None, :], :, f[None, :], :]
        # [timescale, selector, action, outcome]; Beta(1,1) is an explicit prediction prior.
        p = (selected[..., 1] + 1.) / (selected.sum(-1) + 2.)
        return (self.weights[..., None] * p).sum((0, 1))

    def act(self, observations):
        return int(self.probabilities(observations).argmax())


class BinaryFactLearner:
    def __init__(self, fields=2, slots=12, recent=False, static_time=False, uniform=False):
        self.net = Arithmetic()
        self.definitions = selectors(fields, slots, recent)
        self.half_lives = (math.inf,) if static_time else (8., 32., math.inf)
        self.k, self.r = len(self.half_lives), len(self.definitions)
        self.decay = torch.tensor([1. if math.isinf(h) else 2. ** (-1. / h) for h in self.half_lives], dtype=torch.float64)
        self.counts = torch.zeros(self.k, self.r, 2, 3, 2, dtype=torch.float64)
        self.weights = torch.full((self.k, self.r), 1. / (self.k * self.r), dtype=torch.float64)
        self.uniform, self.seen = uniform, 0

    def observe(self, public_episode):
        # Only this sanitized interface is accepted: no family, seed, regime, or hidden target.
        assert set(public_episode) == {'id', 'observations', 'action', 'outcome'}
        self.counts *= self.decay[:, None, None, None, None]
        f = features(public_episode['observations'], self.definitions)
        action, y = public_episode['action'], public_episode['outcome']
        k, r = torch.arange(self.k)[:, None], torch.arange(self.r)[None, :]
        selected = self.counts[k, r, action, f[None, :], :]
        pred = (selected[..., 1] + 1.) / (selected.sum(-1) + 2.)
        mixture = float((self.weights * pred).sum())
        loss = (pred - y).square()
        if not self.uniform:
            self.weights = self.net.mix_after(self.weights, loss)
        self.counts[k, r, action, f[None, :], y] += 1.
        top = int(self.weights.flatten().argmax())
        receipt = dict(id=public_episode['id'], before=self.seen, prediction=mixture, outcome=y,
                       loss=(mixture-y)**2, top_selector=top % self.r, top_scale=top // self.r,
                       top_weight=float(self.weights.flatten()[top]))
        self.seen += 1
        return receipt

    def snapshot(self):
        return Snapshot(self.counts, self.weights, self.definitions)


class BudgetController:
    def __init__(self, per_pair_cost=.02, maximum_pairs=16):
        self.net = Arithmetic()
        self.cost, self.maximum_pairs = per_pair_cost, maximum_pairs
        self.table = {}

    @lru_cache(maxsize=None)
    def value(self, budget, pair_cap, counts):
        if budget == 0:
            self.table[(budget, pair_cap, counts)] = (0., 'keep')
            return (0., 'keep')
        old, new, _ = self.net.pair_means(counts)
        options = [(budget * old, 'keep')]
        if sum(counts) > 0:
            options.append((budget * new, 'adopt'))
        if budget >= 2 and pair_cap > 0:
            total = sum(counts) + 4.
            continuation = 0.
            for cell in range(4):
                nxt = list(counts)
                nxt[cell] += 1
                continuation += (counts[cell] + 1.) / total * self.value(budget-2, pair_cap-1, tuple(nxt))[0]
            options.append((old + new - self.cost + continuation, 'trial'))
        # Equal numerical values use keep, then adopt, then trial, in that order.
        result = max(options, key=lambda item: item[0])
        self.table[(budget, pair_cap, counts)] = result
        return result

    def decide(self, original_budget, counts):
        used = sum(counts)
        return self.value(original_budget - 2 * used, min(self.maximum_pairs, original_budget // 2) - used, tuple(counts))[1]


class FixedEightController:
    def decide(self, original_budget, counts):
        if sum(counts) < 8:
            return 'trial'
        return 'adopt' if counts[1] > counts[2] else 'keep'
