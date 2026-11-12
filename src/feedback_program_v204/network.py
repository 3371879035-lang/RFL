"""A portable feedback tensor program with frozen neural parameters.

Actual transitions change episodic memory. Pre-observation factual prediction
errors select memory timescales; fresh actual trials support local adoption.
Neither task labels, a task simulator, nor an evaluator is imported here.
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
    def __init__(self, config=Config(), adaptive=True):
        super().__init__()
        self.config, self.adaptive = config, bool(adaptive)
        d, f = config.context_dim + config.action_dim, config.fact_dim
        self.d, self.f, self.k = d, f, d + 3
        self.query = nn.Linear(d + 2, self.k, bias=False)
        self.key = nn.Linear(d + 3, self.k, bias=False)
        self.value = nn.Linear(f + f * f, f + f * f, bias=False)
        self.goal_readout = nn.Bilinear(f, f, 1, bias=False)
        self.exploration_readout = nn.Linear(2, 1, bias=False)
        self.expert_decay = nn.Linear(1, 2, bias=False)
        self.fixed_decay = nn.Linear(1, 1, bias=False)
        self.evidence_decay = nn.Linear(1, 1, bias=False)
        self.loss_readout = nn.Linear(1, 1, bias=False)
        self.trial_margin = nn.Linear(1, 1, bias=False)
        self.trial_extent = nn.Linear(2, 1, bias=False)
        for name, shape, dtype in [
            ('contexts', (config.capacity, config.context_dim), torch.float32),
            ('actions', (config.capacity, config.action_dim), torch.float32),
            ('next_contexts', (config.capacity, config.context_dim), torch.float32),
            ('facts', (config.capacity, f), torch.float32),
            ('known', (config.capacity, f), torch.bool),
            ('terminal', (config.capacity,), torch.bool),
            ('timestamps', (config.capacity,), torch.float32),
            ('prequential_losses', (config.capacity, 2, f), torch.float32),
            ('loss_known', (config.capacity, f), torch.bool),
        ]:
            self.register_buffer(name, torch.zeros(shape, dtype=dtype), persistent=False)
        self.count = 0

    def _similarity(self, queries, memory, minimum, scale):
        q, k = (queries - minimum) / scale, (memory - minimum) / scale
        qin = torch.cat((q, q.square().sum(-1, keepdim=True), torch.ones(len(q), 1)), -1)
        kin = torch.cat((k, k.square().sum(-1, keepdim=True),
                         torch.ones(len(k), 1), torch.zeros(len(k), 1)), -1)
        logits = self.query(qin) @ self.key(kin).T / math.sqrt(self.k)
        return logits.clamp(min=-80., max=0.).exp()

    def _weights(self, queries, state, adaptive=None):
        similarity = self._similarity(queries, state['memory'], state['minimum'], state['scale'])
        order = torch.argsort(state['ages'], descending=True)
        ordered = similarity[:, order]
        newer = ordered.flip(-1).cumsum(-1).flip(-1) - ordered
        age = torch.empty_like(similarity)
        age[:, order] = newer
        use_adaptive = self.adaptive if adaptive is None else adaptive
        if not use_adaptive:
            weights = similarity[:, None, :] * self.fixed_decay(age[..., None]).squeeze(-1).exp()[:, None, :]
            return weights, torch.ones(len(queries), 1)
        weights = similarity[:, None, :] * self.expert_decay(age[..., None]).permute(0, 2, 1).exp()
        evidence = similarity * self.evidence_decay(age[..., None]).squeeze(-1).exp()
        channels = state['goal'].abs()
        channel_mass = (state['loss_known'] * channels[None, :]).sum(-1)
        relevant_losses = (state['losses'] * state['loss_known'][:, None, :] * channels[None, None, :]).sum(-1)
        relevant_losses = relevant_losses / channel_mass[:, None].clamp_min(1e-12)
        evidence = evidence * (channel_mass > 0)[None, :]
        # Losses were measured before their outcomes entered memory. No
        # posterior fit to the very observation it purports to predict.
        scores = self.loss_readout((evidence @ relevant_losses).unsqueeze(-1)).squeeze(-1)
        return weights, scores.softmax(-1)

    def _state(self, goal=None):
        n = min(self.count, self.config.capacity)
        memory = torch.cat((self.contexts[:n], self.actions[:n]), -1).clone()
        minimum = memory.min(0).values if n else torch.zeros(self.d)
        span = memory.max(0).values - minimum if n else torch.ones(self.d)
        return dict(memory=memory, minimum=minimum, scale=torch.where(span > 0, span, torch.ones_like(span)),
                    ages=(self.count - 1 - self.timestamps[:n]).clone(),
                    losses=self.prequential_losses[:n].clone(), loss_known=self.loss_known[:n].clone(),
                    goal=(torch.ones(self.f) / self.f if goal is None else goal.clone()))

    @torch.no_grad()
    def observe_transition(self, context, action, successor, terminal, facts, known):
        c, a, s = [torch.as_tensor(x, dtype=torch.float32) for x in (context, action, successor)]
        y, mask = torch.as_tensor(facts, dtype=torch.float32), torch.as_tensor(known, dtype=torch.bool)
        if c.shape != (self.config.context_dim,) or s.shape != c.shape or a.shape != (self.config.action_dim,):
            raise ValueError('Transition descriptor shape mismatch')
        if y.shape != (self.f,) or mask.shape != y.shape:
            raise ValueError('Factual channel shape mismatch')
        state = self._state()
        n = len(state['memory'])
        # Each timescale predicts the observable factual channels, WITHOUT the
        # current result and without consulting the current goal or evaluator.
        preloss = torch.zeros(2, self.f)
        valid_loss = bool(terminal) and bool(mask.any())
        if valid_loss:
            w, _ = self._weights(torch.cat((c, a))[None, :], state, adaptive=True)
            valid = self.known[:n].float() * self.terminal[:n, None].float()
            mass = w[0] @ valid
            predictions = (w[0] @ (valid * self.facts[:n]) + .5) / (1. + mass)
            preloss[:, mask] = (predictions[:, mask] - y[mask]).square()
        i = self.count % self.config.capacity
        self.contexts[i].copy_(c)
        self.actions[i].copy_(a)
        self.next_contexts[i].copy_(s)
        self.facts[i].copy_(torch.where(mask, y, torch.zeros_like(y)))
        self.known[i].copy_(mask)
        self.terminal[i] = bool(terminal)
        self.timestamps[i] = self.count
        self.prequential_losses[i].copy_(preloss)
        self.loss_known[i].copy_(mask & bool(terminal))
        self.count += 1
        return dict(pre_observation_losses=preloss.tolist(), observed_factual_channels=int(mask.sum()),
                    loss_known=valid_loss, source_records_before=self.count - 1)

    def _belief(self, weights, mixture, moments, grounded, goal):
        f = self.f
        effective = weights * grounded[None, None, :]
        mass = effective.sum(-1)
        prior_mean = torch.full((f,), .5)
        prior_second = torch.outer(prior_mean, prior_mean) + torch.eye(f) / 12.
        prior = torch.cat((prior_mean, prior_second.reshape(-1)))
        # Normalize each timescale BEFORE mixing. Otherwise a slow expert's
        # large memory mass overwhelms its selected probability.
        per_expert = (effective @ self.value(moments) + prior) / (1. + mass[..., None])
        combined = (mixture[..., None] * per_expert).sum(1)
        mean = combined[:, :f]
        second = combined[:, f:].reshape(-1, f, f)
        objective = self.goal_readout(mean, goal.expand_as(mean)).squeeze(-1)
        variance = (torch.einsum('i,nij,j->n', goal, second, goal) - objective.square()).clamp_min(0.)
        per_mean = per_expert[:, :, :f]
        per_objective = torch.einsum('nhf,f->nh', per_mean, goal)
        disagreement = (mixture * (per_objective - objective[:, None]).square()).sum(-1)
        effective_mass = (mixture * mass).sum(-1)
        epistemic = (variance / (1. + effective_mass) + disagreement + .25 / (1. + effective_mass).square()).sqrt()
        missing = (mixture / (1. + mass)).sum(-1)
        bonus = self.exploration_readout(torch.stack((epistemic, missing), -1)).squeeze(-1)
        return dict(moments=combined, mean=mean, objective=objective, outcome_variance=variance,
                    epistemic_proxy=epistemic, grounded_mass=effective_mass, support=1. - missing,
                    expert_probabilities=mixture, expert_means=per_mean, bonus=bonus)

    def prepare(self, action_catalog, goal, link_successors=True):
        actions, goal = torch.as_tensor(action_catalog, dtype=torch.float32), torch.as_tensor(goal, dtype=torch.float32)
        if actions.ndim != 2 or actions.shape[1] != self.config.action_dim or goal.shape != (self.f,):
            raise ValueError('Public action catalog or goal shape mismatch')
        state = self._state(goal)
        n, a, f = len(state['memory']), len(actions), self.f
        terminal, known = self.terminal[:n].clone(), self.known[:n].clone()
        values = torch.where(known, self.facts[:n], torch.full((n, f), .5))
        second = values[:, :, None] * values[:, None, :] + torch.diag_embed((~known).float() / 12.)
        direct = torch.cat((values, second.reshape(n, f * f)), -1)
        valid_terminal = terminal & torch.all(known | ~(goal.abs() > 0)[None, :], dim=-1)
        moments, grounded = direct.clone(), valid_terminal.float()
        if n and link_successors:
            queries = torch.cat((self.next_contexts[:n, None, :].expand(-1, a, -1),
                                 actions[None, :, :].expand(n, -1, -1)), -1).reshape(n * a, -1)
            weights, mixture = self._weights(queries, state)
            for _ in range(self.config.planning_depth):
                belief = self._belief(weights, mixture, moments, grounded, goal)
                objectives = belief['objective'].reshape(n, a)
                choice = (objectives >= objectives.max(-1, keepdim=True).values - 1e-6).float()
                choice /= choice.sum(-1, keepdim=True)
                following = torch.einsum('na,nav->nv', choice, belief['moments'].reshape(n, a, -1))
                following_ground = (choice * belief['support'].reshape(n, a)).sum(-1)
                moments = torch.where(terminal[:, None], direct, following)
                grounded = torch.where(terminal, valid_terminal.float(), following_ground)
        return dict(**state, moments=moments, grounded=grounded, actions=actions.clone(),
                    count=self.count, link_successors=bool(link_successors))

    def forward(self, context, prepared, explore=False):
        c = torch.as_tensor(context, dtype=torch.float32)
        actions = prepared['actions']
        queries = torch.cat((c.expand(len(actions), -1), actions), -1)
        weights, mixture = self._weights(queries, prepared)
        result = self._belief(weights, mixture, prepared['moments'], prepared['grounded'], prepared['goal'])
        result['scores'] = result['objective'] + (result['bonus'] if explore else 0.)
        return result

    def assess_local_trials(self, contexts, candidate_outcomes, incumbent_outcomes, goal, prepared):
        contexts = torch.as_tensor(contexts, dtype=torch.float32)
        new, old = torch.as_tensor(candidate_outcomes, dtype=torch.float32), torch.as_tensor(incumbent_outcomes, dtype=torch.float32)
        goal = torch.as_tensor(goal, dtype=torch.float32)
        difference = self.goal_readout(new - old, goal.expand_as(new)).squeeze(-1)
        return dict(contexts=contexts.clone(), differences=difference.clone(),
                    minimum=prepared['minimum'][:self.config.context_dim].clone(),
                    scale=prepared['scale'][:self.config.context_dim].clone())

    def trial_decision(self, context, trial_evidence):
        c = torch.as_tensor(context, dtype=torch.float32)
        dim = self.config.action_dim
        queries = torch.cat((c, torch.zeros(dim)))[None, :]
        contexts = trial_evidence['contexts']
        memory = torch.cat((contexts, torch.zeros(len(contexts), dim)), -1)
        minimum = torch.cat((trial_evidence['minimum'], torch.zeros(dim)))
        scale = torch.cat((trial_evidence['scale'], torch.ones(dim)))
        weights = self._similarity(queries, memory, minimum, scale)[0]
        mass = weights.sum()
        estimate = (weights @ trial_evidence['differences']) / (1. + mass)
        margin = self.trial_margin(estimate[None]).squeeze()
        extent = self.trial_extent(torch.stack((mass, torch.ones_like(mass)))).squeeze()
        return dict(adopt=bool((margin > 0.) & (extent >= 0.)), estimate=float(estimate), mass=float(mass),
                    actual_trial_weights=weights.tolist())

    def memory_state(self):
        return dict(count=self.count, buffers={k: v.clone() for k, v in self.named_buffers()})

    @torch.no_grad()
    def restore_memory(self, state):
        for k, value in self.named_buffers():
            value.copy_(state['buffers'][k])
        self.count = state['count']


@torch.no_grad()
def write_initial_weights(net):
    for p in net.parameters():
        p.zero_()
    beta, d = 20., net.d
    q, k = net.query.weight, net.key.weight
    for j in range(d):
        q[j, j], k[j, j] = 1., 2. * beta
    q[d, d], k[d, d + 1] = 1., -beta
    q[d + 1, d + 1], k[d + 1, d] = 1., -beta
    k.mul_(math.sqrt(net.k))
    net.value.weight.copy_(torch.eye(net.f + net.f * net.f))
    net.goal_readout.weight[0].copy_(torch.eye(net.f))
    net.exploration_readout.weight[0].copy_(torch.tensor([.5, .1]))
    net.expert_decay.weight[:, 0].copy_(torch.tensor([-math.log(2.), -math.log(2.) / 32.]))
    net.fixed_decay.weight.fill_(-math.log(2.) / 8.)
    net.evidence_decay.weight.fill_(-math.log(2.) / 4.)
    net.loss_readout.weight.fill_(-2.)
    net.trial_margin.weight.fill_(1.)
    net.trial_extent.weight[0].copy_(torch.tensor([1., -2.]))
    return net


def save_initial_model(path, config=Config()):
    model = write_initial_weights(FeedbackNet(config))
    with open(path, 'xb') as stream:
        torch.save(dict(config=asdict(config), state_dict=model.state_dict(),
                        origin='analytic_weight_programming_v204', optimizer_steps=0,
                        environment_data_read_by_writer=0), stream)
    return model


def load_model(path, adaptive=True):
    payload = torch.load(path, map_location='cpu', weights_only=True)
    model = FeedbackNet(Config(**payload['config']), adaptive=adaptive)
    model.load_state_dict(payload['state_dict'], strict=True)
    return model
