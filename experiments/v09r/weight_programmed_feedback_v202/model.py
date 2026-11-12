"""Analytically written transition-memory network; parameters never trained.

Python stores real transition records. The tensor program retrieves transitions,
propagates factual moments through observed successors, proposes actions, and
decides adoption from fresh paired real trials. No task simulator is imported.
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
    planning_depth: int = 6


class FeedbackNet(nn.Module):
    def __init__(self, config=Config()):
        super().__init__()
        self.config = config
        d, f = config.context_dim + config.action_dim, config.fact_dim
        self.d, self.f, self.k = d, f, d + 3
        self.query = nn.Linear(d + 2, self.k, bias=False)
        self.key = nn.Linear(d + 3, self.k, bias=False)
        # The value map carries means AND joint second moments, not confidence
        # inferred merely from the presence of a retrieved memory record.
        self.value = nn.Linear(f + f * f, f + f * f, bias=False)
        self.goal_readout = nn.Bilinear(f, f, 1, bias=False)
        self.exploration_readout = nn.Linear(2, 1, bias=False)
        self.trial_margin = nn.Linear(3, 1, bias=False)
        self.trial_extent = nn.Linear(2, 1, bias=False)
        for name, shape, dtype in [
            ('contexts', (config.capacity, config.context_dim), torch.float32),
            ('actions', (config.capacity, config.action_dim), torch.float32),
            ('next_contexts', (config.capacity, config.context_dim), torch.float32),
            ('facts', (config.capacity, f), torch.float32),
            ('known', (config.capacity, f), torch.bool),
            ('terminal', (config.capacity,), torch.bool),
            ('timestamps', (config.capacity,), torch.float32),
        ]:
            self.register_buffer(name, torch.zeros(shape, dtype=dtype), persistent=False)
        self.count = 0

    @torch.no_grad()
    def observe_transition(self, context, action, successor, terminal, facts, known):
        c, a, s = [torch.as_tensor(x, dtype=torch.float32) for x in (context, action, successor)]
        y, mask = torch.as_tensor(facts, dtype=torch.float32), torch.as_tensor(known, dtype=torch.bool)
        if c.shape != (self.config.context_dim,) or s.shape != c.shape or a.shape != (self.config.action_dim,):
            raise ValueError('Transition descriptor shape mismatch')
        if y.shape != (self.f,) or mask.shape != y.shape:
            raise ValueError('Outcome shape mismatch')
        if not (torch.isfinite(c).all() and torch.isfinite(a).all() and torch.isfinite(s).all() and torch.isfinite(y[mask]).all()):
            raise ValueError('Observed transition must be finite; unknown outcome uses a mask')
        if torch.any((y[mask] < 0) | (y[mask] > 1)):
            raise ValueError('This interface declares factual outcomes in [0,1]')
        i = self.count % self.config.capacity
        self.contexts[i].copy_(c)
        self.actions[i].copy_(a)
        self.next_contexts[i].copy_(s)
        self.facts[i].copy_(torch.where(mask, y, torch.zeros_like(y)))
        self.known[i].copy_(mask)
        self.terminal[i] = bool(terminal)
        self.timestamps[i] = self.count
        self.count += 1

    def _weights(self, queries, memory, minimum, scale, ages):
        q = (queries - minimum) / scale
        k = (memory - minimum) / scale
        qin = torch.cat((q, q.square().sum(-1, keepdim=True), torch.ones(len(q), 1)), -1)
        kin = torch.cat((k, k.square().sum(-1, keepdim=True), torch.ones(len(k), 1), ages[:, None]), -1)
        logits = self.query(qin) @ self.key(kin).T / math.sqrt(self.k)
        return logits.clamp(min=-80., max=0.).exp()

    def _belief(self, weights, moments, grounded, goal):
        f = self.f
        effective = weights * grounded[None, :]
        mass = effective.sum(-1)
        prior_mean = torch.full((f,), .5)
        prior_second = torch.outer(prior_mean, prior_mean) + torch.eye(f) / 12.
        prior = torch.cat((prior_mean, prior_second.reshape(-1)))
        decoded = self.value(moments)
        combined = (effective @ decoded + prior) / (1. + mass[:, None])
        mean = combined[:, :f]
        second = combined[:, f:].reshape(-1, f, f)
        objective = self.goal_readout(mean, goal.expand_as(mean)).squeeze(-1)
        variance = (torch.einsum('i,nij,j->n', goal, second, goal) - objective.square()).clamp_min(0.)
        # Local sample-mass proxy, NOT a calibrated confidence interval. Noise
        # variance remains visible even when many observations support the mean.
        epistemic = (variance / (1. + mass) + .25 / (1. + mass).square()).sqrt()
        missing = 1. / (1. + mass)
        bonus = self.exploration_readout(torch.stack((epistemic, missing), -1)).squeeze(-1)
        return dict(moments=combined, mean=mean, objective=objective,
                    outcome_variance=variance, epistemic_proxy=epistemic,
                    grounded_mass=mass, support=1. - missing, bonus=bonus)

    def prepare(self, action_catalog, goal, link_successors=True):
        """Freeze a model-generated proposal from the current observed memory.

        The public action catalog is fixed for this finite interface. Planning
        uses only actually recorded successors; it is not an environment call.
        """
        actions = torch.as_tensor(action_catalog, dtype=torch.float32)
        goal = torch.as_tensor(goal, dtype=torch.float32)
        if actions.ndim != 2 or actions.shape[1] != self.config.action_dim or goal.shape != (self.f,):
            raise ValueError('Query interface mismatch')
        if not torch.isfinite(goal).all() or goal.abs().sum() > 1.00001:
            raise ValueError('Goal must be finite and L1-normalized to at most one')
        n, a, f = min(self.count, self.config.capacity), len(actions), self.f
        memory = torch.cat((self.contexts[:n], self.actions[:n]), -1).clone()
        minimum = memory.min(0).values if n else torch.zeros(self.d)
        span = memory.max(0).values - minimum if n else torch.ones(self.d)
        scale = torch.where(span > 0, span, torch.ones_like(span))
        ages = (self.count - 1 - self.timestamps[:n]).clone()
        terminal = self.terminal[:n].clone()
        known = self.known[:n]
        values = torch.where(known, self.facts[:n], torch.full((n, f), .5))
        second = values[:, :, None] * values[:, None, :] + torch.diag_embed((~known).float() / 12.)
        direct = torch.cat((values, second.reshape(n, f * f)), -1)
        active = goal.abs() > 0
        valid_terminal = terminal & torch.all(known | ~active[None, :], dim=-1)
        # No outcome is copied retrospectively onto every earlier action.
        # Nonterminal rows initially have no grounded outcome evidence at all.
        moments = direct.clone()
        grounded = valid_terminal.float()
        if n and link_successors:
            queries = torch.cat((self.next_contexts[:n, None, :].expand(-1, a, -1),
                                 actions[None, :, :].expand(n, -1, -1)), -1).reshape(n * a, -1)
            next_weights = self._weights(queries, memory, minimum, scale, ages)
            for _ in range(self.config.planning_depth):
                belief = self._belief(next_weights, moments, grounded, goal)
                objective = belief['objective'].reshape(n, a)
                maximum = objective.max(-1, keepdim=True).values
                # A tie is an equal mixture, not a preference for action label 0.
                choice = (objective >= maximum - 1e-6).float()
                choice = choice / choice.sum(-1, keepdim=True)
                following = torch.einsum('na,nav->nv', choice, belief['moments'].reshape(n, a, -1))
                following_ground = (choice * belief['support'].reshape(n, a)).sum(-1)
                moments = torch.where(terminal[:, None], direct, following)
                grounded = torch.where(terminal, valid_terminal.float(), following_ground)
        return dict(memory=memory, minimum=minimum, scale=scale, ages=ages,
                    moments=moments, grounded=grounded, actions=actions.clone(),
                    goal=goal.clone(), count=self.count, link_successors=bool(link_successors))

    def forward(self, context, prepared, explore=False):
        c = torch.as_tensor(context, dtype=torch.float32)
        actions = prepared['actions']
        query = torch.cat((c.expand(len(actions), -1), actions), -1)
        weights = self._weights(query, prepared['memory'], prepared['minimum'], prepared['scale'], prepared['ages'])
        result = self._belief(weights, prepared['moments'], prepared['grounded'], prepared['goal'])
        result['scores'] = result['objective'] + (result['bonus'] if explore else 0.)
        return result

    def assess_trials(self, candidate_outcomes, incumbent_outcomes, goal):
        """Gate sees ONLY fresh realized factual outcomes, never predictions.

        Both policies must have been frozen before these paired trials. The
        margin is a conservative engineering heuristic, not a claimed 95% CI.
        """
        new = torch.as_tensor(candidate_outcomes, dtype=torch.float32)
        old = torch.as_tensor(incumbent_outcomes, dtype=torch.float32)
        goal = torch.as_tensor(goal, dtype=torch.float32)
        if new.shape != old.shape or new.ndim != 2 or new.shape[1] != self.f or len(new) < 2:
            raise ValueError('Paired actual trial outcomes are required')
        difference = self.goal_readout(new - old, goal.expand_as(new)).squeeze(-1)
        n = len(difference)
        average = difference.mean()
        stderr = (difference.var(unbiased=True) / n).sqrt()
        margin = self.trial_margin(torch.stack((average, stderr, torch.ones_like(average)))).squeeze()
        extent = self.trial_extent(torch.tensor([float(n), 1.])).squeeze()
        accept = (margin > 0.) & (extent > 0.)
        return dict(accept=bool(accept), mean_difference=float(average),
                    standard_error=float(stderr), margin=float(margin), pairs=n,
                    paired_differences=difference.tolist())


@torch.no_grad()
def write_initial_weights(net):
    """Compile distance matching, moment transport and actual-trial gating."""
    for parameter in net.parameters():
        parameter.zero_()
    beta, rho, d = 20., .002, net.d
    q, k = net.query.weight, net.key.weight
    for j in range(d):
        q[j, j], k[j, j] = 1., 2. * beta
    q[d, d], k[d, d + 1] = 1., -beta
    q[d + 1, d + 1], k[d + 1, d] = 1., -beta
    q[d + 2, d + 1], k[d + 2, d + 2] = 1., -rho
    k.mul_(math.sqrt(net.k))
    net.value.weight.copy_(torch.eye(net.f + net.f * net.f))
    net.goal_readout.weight[0].copy_(torch.eye(net.f))
    net.exploration_readout.weight[0].copy_(torch.tensor([.5, .1]))
    net.trial_margin.weight[0].copy_(torch.tensor([1., -2., 0.]))
    net.trial_extent.weight[0].copy_(torch.tensor([1., -7.]))
    return net


def save_initial_model(path, config=Config()):
    model = write_initial_weights(FeedbackNet(config))
    with open(path, 'xb') as stream:
        torch.save(dict(config=asdict(config), state_dict=model.state_dict(),
                        origin='analytic_weight_programming_v202', optimizer_steps=0,
                        environment_data_read_by_writer=0), stream)
    return model


def load_model(path):
    payload = torch.load(path, map_location='cpu', weights_only=True)
    model = FeedbackNet(Config(**payload['config']))
    model.load_state_dict(payload['state_dict'], strict=True)
    return model
