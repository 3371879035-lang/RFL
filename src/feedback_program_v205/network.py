"""Frozen arithmetic network for additive facts and empirical successors.

No task imports, reward TD, optimizer, learned encoder, or environment access.
This implements the first-order operator, not all of NETWORK_SPEC_V1.
"""
import hashlib
import torch
from torch import nn


def encode(observation, previous, window):
    out = list(observation)
    for j in range(window):
        out.extend(list(previous[-1-j]) + [1.] if j < len(previous) else [0., 0., 0.])
    return tuple(float(x) for x in out)


def parameter_digest(net):
    h = hashlib.sha256()
    for name, p in net.named_parameters():
        h.update(name.encode())
        h.update(p.detach().cpu().numpy().tobytes())
    return h.hexdigest()


class FactNet(nn.Module):
    def __init__(self, dim, facts=2, beta=16., gamma=1.):
        super().__init__()
        self.dim, self.facts, self.gamma = dim, facts, gamma
        self.difference = nn.Linear(2 * dim, dim, bias=False, dtype=torch.float64)
        self.distance_readout = nn.Linear(dim, 1, bias=False, dtype=torch.float64)
        self.backup = nn.Linear(2 * facts, facts, bias=False, dtype=torch.float64)
        self.goal_readout = nn.Bilinear(facts, facts, 1, bias=False, dtype=torch.float64)
        with torch.no_grad():
            self.difference.weight.copy_(torch.cat((torch.eye(dim), -torch.eye(dim)), 1))
            self.distance_readout.weight.fill_(-beta)
            self.backup.weight.copy_(torch.cat((torch.eye(facts), gamma * torch.eye(facts)), 1))
            self.goal_readout.weight[0].copy_(torch.eye(facts))
        self.requires_grad_(False).eval()

    def kernel(self, q, keys):
        # The first public field is a discrete phase/type, not a numeric distance.
        query = torch.as_tensor(q, dtype=torch.float64).expand(len(keys), -1)
        delta = self.difference(torch.cat((query, keys), 1))
        return self.distance_readout(delta.square()).squeeze(-1).exp() * (query[:, 0] == keys[:, 0])

    def utility(self, values, goal):
        return self.goal_readout(values, goal.expand_as(values)).squeeze(-1)


class FactMemory:
    def __init__(self, net, window, terminal_only=False):
        self.net, self.window, self.terminal_only = net, window, terminal_only
        self.rows = []
        self.prediction_records = []

    def ingest(self, episode):
        previous = []
        for step in episode['steps']:
            q = encode(step['observation'], previous, self.window)
            nxt = encode(step['successor'], previous + [step['observation']], self.window)
            x = [(0. if self.terminal_only else c) + step['terminal'] * y
                 for c, y in zip(step['contribution'], step['terminal_fact'])]
            known = list(step['known'])
            pred = [None] * self.net.facts
            if self.rows:
                keys = torch.tensor([r['context'] for r in self.rows], dtype=torch.float64)
                weights = self.net.kernel(q, keys) * torch.tensor([r['action'] == step['action'] for r in self.rows])
                for k in range(self.net.facts):
                    wk = weights * torch.tensor([r['known'][k] for r in self.rows])
                    if float(wk.sum()) > 0.:
                        pred[k] = float(wk @ torch.tensor([r['x'][k] for r in self.rows], dtype=torch.float64) / wk.sum())
            losses = [(p - v) ** 2 if p is not None and m else None for p, v, m in zip(pred, x, known)]
            self.prediction_records.append(dict(episode=episode['id'], step=step['t'], rows_before=len(self.rows),
                                                prediction=pred, target=x, known=known, loss=losses,
                                                terminal=step['terminal']))
            self.rows.append(dict(context=q, action=step['action'], x=x, known=known,
                                  successor=nxt, terminal=step['terminal'], legal_next=step['legal_next'],
                                  episode=episode['id'], step=step['t']))
            previous.append(step['observation'])

    def snapshot(self, goal, depth=6, mean_successor=False):
        return Policy(self.net, self.rows, self.window, goal, depth, mean_successor)


class Policy:
    def __init__(self, net, rows, window, goal, depth=6, mean_successor=False):
        self.net, self.window, self.depth, self.mean_successor = net, window, depth, mean_successor
        # Frozen copies, not a view of the live memory list or its tensors.
        self.rows = tuple(dict(r, context=tuple(r['context']), successor=tuple(r['successor']),
                               x=tuple(r['x']), known=tuple(r['known']), legal_next=tuple(r['legal_next'])) for r in rows)
        self.goal = torch.tensor(goal, dtype=torch.float64)
        self.keys = torch.tensor([r['context'] for r in rows], dtype=torch.float64).reshape(-1, net.dim)
        self.x = torch.tensor([r['x'] for r in rows], dtype=torch.float64).reshape(-1, net.facts)
        self.known = torch.tensor([r['known'] for r in rows], dtype=torch.bool).reshape(-1, net.facts)
        self.actions = torch.tensor([r['action'] for r in rows], dtype=torch.long)
        self.cache = {}
        self.unknown_action_fallbacks = 0

    def values(self, context, legal, depth=None):
        depth = self.depth if depth is None else depth
        key = (tuple(context), tuple(legal), depth)
        if key in self.cache:
            return self.cache[key]
        values, available = [], []
        similarity = self.net.kernel(context, self.keys) if self.rows else torch.zeros(0, dtype=torch.float64)
        for action in legal:
            weights = similarity * (self.actions == action)
            mass = float(weights.sum())
            value = torch.zeros(self.net.facts, dtype=torch.float64)
            valid = torch.ones(self.net.facts, dtype=torch.bool)
            if mass == 0.:
                valid[:] = False
            else:
                p = weights / mass
                for k in range(self.net.facts):
                    pk = p * self.known[:, k]
                    if float(pk.sum()) == 0.:
                        valid[k] = False
                    else:
                        value[k] = pk @ self.x[:, k] / pk.sum()
                following = torch.zeros(self.net.facts, dtype=torch.float64)
                grouped = {}
                for i, row in enumerate(self.rows):
                    if row['terminal'] or float(p[i]) == 0. or depth <= 1:
                        continue
                    skey = (row['successor'], row['legal_next'])
                    grouped[skey] = grouped.get(skey, 0.) + float(p[i])
                if self.mean_successor and grouped:
                    mass_next = sum(grouped.values())
                    nxt = tuple(sum(prob * z[k] for (z, _), prob in grouped.items()) / mass_next for k in range(self.net.dim))
                    # Deliberately flawed ablation. Tasks have identical legal sets within a phase.
                    masks = {acts for _, acts in grouped}
                    phases = {z[0] for z, _ in grouped}
                    if len(masks) != 1:
                        raise ValueError('mean-successor ablation requires a common legal-action set')
                    if len(phases) != 1:
                        raise ValueError('mean-successor ablation cannot average categorical phases')
                    nxt = (phases.pop(),) + nxt[1:]
                    grouped = {(nxt, masks.pop()): mass_next}
                for (nxt, legal_next), prob in grouped.items():
                    future, good, _ = self.choose(nxt, legal_next, depth - 1)
                    following += prob * future
                    valid &= good
                value = self.net.backup(torch.cat((value, following)))
            values.append(value)
            available.append(valid)
        result = (torch.stack(values), torch.stack(available))
        self.cache[key] = result
        return result

    def choose(self, context, legal, depth=None):
        values, available = self.values(context, legal, depth)
        relevant = self.goal != 0.
        valid_actions = torch.all(available[:, relevant], dim=1)
        scores = self.net.utility(values, self.goal)
        options = [i for i, valid in enumerate(valid_actions.tolist()) if valid]
        if options:
            # Stable public identity order on exact score ties.
            selected = max(options, key=lambda i: (float(scores[i]), -i))
        else:
            selected = 0
        return values[selected], available[selected], legal[selected]

    def act(self, observation, previous, legal):
        context = encode(observation, previous, self.window)
        _, available, action = self.choose(context, tuple(legal))
        if not bool(available[self.goal != 0.].all()):
            self.unknown_action_fallbacks += 1
        return int(action)
