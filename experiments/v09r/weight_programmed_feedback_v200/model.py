"""A weight-programmed, goal-conditioned factual-memory network.

No environment, task identity, reward, optimizer, or pretrained model is imported.
The memory writer copies observations; all retrieval, drift mixing, and action
scoring go through the parameterized forward network. Memory is not a weight.
"""
from dataclasses import asdict, dataclass
import math
import torch
from torch import nn


@dataclass(frozen=True)
class Config:
    context_dim: int = 6
    action_dim: int = 6
    fact_dim: int = 3
    capacity: int = 384


class FeedbackNet(nn.Module):
    def __init__(self, config=Config()):
        super().__init__()
        self.config = config
        d, f = config.context_dim + config.action_dim, config.fact_dim
        self.d, self.f, self.k = d, f, d + 3
        # Key input: x, squared norm, real-record bit, age, factual values, prior bit.
        self.key_size = d + 4 + f
        self.query = nn.ModuleList([nn.Linear(d + 2, self.k, bias=False) for _ in range(2)])
        self.key = nn.ModuleList([nn.Linear(self.key_size, self.k, bias=False) for _ in range(2)])
        self.value = nn.ModuleList([nn.Linear(self.key_size, f + 1, bias=False) for _ in range(2)])
        self.mix = nn.Linear(f, 1)
        self.goal_readout = nn.Bilinear(f, f, 1, bias=False)
        self.uncertainty_readout = nn.Linear(f, 1, bias=False)
        self.register_buffer('memory_x', torch.zeros(config.capacity, d), persistent=False)
        self.register_buffer('memory_facts', torch.zeros(config.capacity, f), persistent=False)
        self.register_buffer('memory_known', torch.zeros(config.capacity, f, dtype=torch.bool), persistent=False)
        self.register_buffer('memory_time', torch.zeros(config.capacity), persistent=False)
        self.count = self.clock = 0

    def clear_memory(self):
        self.count = self.clock = 0
        self.memory_x.zero_()
        self.memory_facts.zero_()
        self.memory_known.zero_()
        self.memory_time.zero_()

    @torch.no_grad()
    def observe(self, context, action, facts, known=None):
        """Copy a real observed record. Missing facts are masked, not zero labels."""
        x = torch.cat((torch.as_tensor(context), torch.as_tensor(action))).float()
        y = torch.as_tensor(facts).float()
        mask = torch.ones(self.f, dtype=torch.bool) if known is None else torch.as_tensor(known).bool()
        if x.shape != (self.d,) or y.shape != (self.f,) or mask.shape != (self.f,):
            raise ValueError('Feedback dimensions do not match the declared interface')
        if not torch.isfinite(x).all() or not torch.isfinite(y[mask]).all():
            raise ValueError('Observed inputs must be finite; unknown facts use a mask')
        slot = self.count % self.config.capacity
        self.memory_x[slot].copy_(x)
        self.memory_facts[slot].copy_(torch.where(mask, y, torch.zeros_like(y)))
        self.memory_known[slot].copy_(mask)
        self.memory_time[slot] = self.clock
        self.count += 1
        self.clock += 1

    def forward(self, context, actions, goal):
        """Score arbitrary candidate descriptors; no game-specific action rules."""
        context = torch.as_tensor(context, dtype=torch.float32)
        actions = torch.as_tensor(actions, dtype=torch.float32)
        goal = torch.as_tensor(goal, dtype=torch.float32)
        if context.shape != (self.config.context_dim,) or actions.ndim != 2 or actions.shape[1] != self.config.action_dim or goal.shape != (self.f,):
            raise ValueError('Query dimensions do not match the declared interface')
        x = torch.cat((context.expand(actions.shape[0], -1), actions), -1)
        qin = torch.cat((x, x.square().sum(-1, keepdim=True), torch.ones(len(x), 1)), -1)
        n = min(self.count, self.config.capacity)
        # A data-independent prior token is part of the architecture, not evidence.
        tokens = torch.zeros(n + 1, self.key_size)
        if n:
            tokens[:n, :self.d] = self.memory_x[:n]
            tokens[:n, self.d] = self.memory_x[:n].square().sum(-1)
            tokens[:n, self.d + 1] = 1.
            tokens[:n, self.d + 2] = self.clock - 1 - self.memory_time[:n]
            tokens[:n, self.d + 3:self.d + 3 + self.f] = self.memory_facts[:n]
        tokens[-1, -1] = 1.
        known = torch.cat((self.memory_known[:n], torch.ones(1, self.f, dtype=torch.bool)), 0)
        predictions, confidence = [], []
        for query, key, value in zip(self.query, self.key, self.value):
            logits = query(qin) @ key(tokens).T / math.sqrt(self.k)
            logits = logits[:, None, :].expand(-1, self.f, -1).masked_fill(~known.T[None, :, :], -torch.inf)
            attention = logits.softmax(-1)
            values = value(tokens)
            predictions.append(torch.einsum('afm,mf->af', attention, values[:, :self.f]))
            confidence.append(torch.einsum('afm,m->af', attention, values[:, -1]))
        slow, fast = predictions
        gate = self.mix((fast - slow).abs()).sigmoid()
        prediction = slow * (1 - gate) + fast * gate
        support = confidence[0] * (1 - gate) + confidence[1] * gate
        score = self.goal_readout(prediction, goal.expand_as(prediction)).squeeze(-1)
        score = score + self.uncertainty_readout(1 - support).squeeze(-1)
        return dict(scores=score, prediction=prediction, support=support, fast_weight=gate.squeeze(-1))


@torch.no_grad()
def write_initial_weights(net):
    """Direct tensor construction. No fitting, backward pass, or task data.

    Compile a task-independent program into Q/K/V, a change-sensitive mixing
    gate, a goal-conditioned bilinear readout and an unsupported-action bonus.
    This is a designed learning prior, not independently discovered causality.
    """
    for parameter in net.parameters():
        parameter.zero_()
    d, f = net.d, net.f
    beta, prior_logit = 20., -8.
    for i, rho in enumerate((0.002, 0.04)):
        q, k, v = net.query[i].weight, net.key[i].weight, net.value[i].weight
        for j in range(d):
            q[j, j] = 1.
            k[j, j] = 2 * beta
        q[d, d] = 1.
        q[d + 1, d + 1] = 1.
        q[d + 2, d + 1] = 1.
        k[d, d + 1] = -beta
        k[d + 1, d] = -beta
        k[d + 1, -1] = prior_logit
        k[d + 2, d + 2] = -rho
        k.mul_(math.sqrt(net.k))
        for j in range(f):
            v[j, d + 3 + j] = 1.
            v[j, -1] = 0.5
        v[f, d + 1] = 1.
    net.mix.weight.fill_(12. / f)
    net.mix.bias.fill_(-1.44)
    net.goal_readout.weight[0].copy_(torch.eye(f))
    net.uncertainty_readout.weight.fill_(0.35 / f)
    net.clear_memory()
    return net


def save_initial_model(path, config=Config()):
    model = write_initial_weights(FeedbackNet(config))
    with open(path, 'xb') as stream:
        torch.save({'config': asdict(config), 'state_dict': model.state_dict(),
                    'origin': 'direct_weight_programming_no_training', 'optimizer_steps': 0,
                    'memory_records': 0}, stream)
    return model


def load_model(path):
    payload = torch.load(path, map_location='cpu', weights_only=True)
    model = FeedbackNet(Config(**payload['config']))
    model.load_state_dict(payload['state_dict'], strict=True)
    return model
