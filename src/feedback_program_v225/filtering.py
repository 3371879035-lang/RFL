"""One observed-data recursion for online prediction and offline sequence likelihood."""
from dataclasses import dataclass, replace
import hashlib
import torch
from torch.nn import functional as F
from feedback_program_v223.losses import observed_gaussian_log_prob
from .identity import world_identity


@dataclass(frozen=True)
class BeliefState:
    encoded: torch.Tensor
    valid: torch.Tensor
    context: torch.Tensor
    h: torch.Tensor
    log_weights: torch.Tensor
    log_evidence: torch.Tensor
    expected_observation: torch.Tensor
    goal: torch.Tensor
    anchor_ids: tuple
    used_ids: tuple
    world_id: str
    episode: str | None = None
    last_step: int | None = None
    terminal: bool = False


def posterior_update(log_weights, component_log_likelihood):
    joint = log_weights.double() + component_log_likelihood.double()
    log_z = torch.logsumexp(joint, -1)
    return joint-log_z, log_z


def start(model, observation, goal, memory):
    if observation.shape[0] != 1:
        raise ValueError('This temporal interface handles one actual episode per state')
    encoded, valid = model.encode_memory(memory)
    query = model.query_encoder(torch.cat((observation, goal), -1))
    read, _, _ = model.reader(query[:, None, :], encoded, valid)
    context = model.context_fusion(torch.cat((query, read[:, 0]), -1))
    log_weights = model.mixture_head(context)[0].double().log_softmax(-1)
    h = model.belief_init(context[:, None, :]+model.hypothesis_embeddings[None])[0]
    return BeliefState(encoded, valid, context, h, log_weights, log_weights.new_zeros(()),
                       observation[0], goal[0], tuple(memory['ids']), (), world_identity(model))


def require_query(model, state, observation, goal, full_ids):
    if state.world_id != world_identity(model):
        raise ValueError('Cached belief belongs to a different world version')
    if state.terminal:
        raise ValueError('Cannot continue a terminated belief state')
    if tuple(full_ids) != state.anchor_ids+state.used_ids:
        raise ValueError('Reference memory and current evidence must partition the exact input prefix')
    if not torch.equal(observation[0], state.expected_observation) or not torch.equal(goal[0], state.goal):
        raise ValueError('Current public observation/goal differs from the actual predecessor')


def component_likelihood(model, state, event):
    p = next(model.parameters()); k = model.config.hypotheses
    tensor = lambda x: torch.as_tensor(x, dtype=p.dtype, device=p.device)
    obs = tensor([event.observation]).expand(k, -1); goal = tensor([event.goal]).expand(k, -1)
    actions = tensor([event.actions]).expand(k, -1, -1)
    raw, _, _ = model.state_kernel(obs, goal, actions, state.encoded.expand(k, -1, -1), state.valid.expand(k, -1),
                                    state.h, torch.arange(k, device=p.device))
    raw = raw[:, event.action_index]
    innovation, mask = model.layout.innovations(event)
    u = tensor(innovation).expand(k, -1); m = tensor(mask).expand(k, -1)
    dt = tensor(float(event.terminal)).expand(k); gg = tensor(float(event.goal_met)).expand(k)
    mask_ll = -F.binary_cross_entropy_with_logits(model.visibility_head(raw), m, reduction='none').sum(-1)
    tl, gl = model.discrete(raw, m, dt)
    discrete_ll = -F.binary_cross_entropy_with_logits(tl, dt, reduction='none')-F.binary_cross_entropy_with_logits(gl, gg, reduction='none')
    mean, lower = model.continuous(raw, m, dt, gg)
    nxt = tensor(event.next_observation).expand(k, -1); value = torch.cat((nxt, u), -1)
    observed = torch.cat((torch.ones(model.schema.observation, dtype=torch.bool, device=p.device), m[0].bool()))
    continuous_ll = observed_gaussian_log_prob(mean, lower, value, observed)
    ll = (mask_ll+discrete_ll+continuous_ll).double()
    h = model.update_observed_belief(state.h, obs, actions[:, event.action_index], nxt, u, m, goal, gg, dt)
    return ll, h, {'mask': mask_ll, 'discrete': discrete_ll, 'continuous': continuous_ll,
                  'observed_continuous_coordinates': int(observed.sum())}


def observe(model, state, event):
    if event.id in state.anchor_ids or event.id in state.used_ids:
        raise ValueError('This factual identity has already been consumed')
    p = next(model.parameters()); tensor = lambda x: torch.as_tensor(x, dtype=p.dtype, device=p.device)
    require_query(model, state, tensor([event.observation]), tensor([event.goal]), state.anchor_ids+state.used_ids)
    previous = state.used_ids[-1] if state.used_ids else None
    if event.previous_id != previous or (state.episode is not None and event.episode != state.episode):
        raise ValueError('Event is not the next member of this actual chain')
    if state.last_step is not None and event.step != state.last_step+1:
        raise ValueError('A temporal gap cannot be treated as an observed transition')
    model.layout.validate_event(event)
    ll, h, detail = component_likelihood(model, state, event)
    log_weights, log_z = posterior_update(state.log_weights, ll)
    updated = replace(state, h=h, log_weights=log_weights, log_evidence=state.log_evidence+log_z,
        expected_observation=tensor(event.next_observation), used_ids=state.used_ids+(event.id,),
        episode=event.episode, last_step=event.step, terminal=event.terminal)
    return updated, dict(detail, component_log_likelihood=ll, log_predictive=log_z)


def from_view(model, observation, goal, memory):
    plan = memory.get('filter_plan')
    if plan is None:
        return start(model, observation, goal, memory)
    p = next(model.parameters()); first = plan['events'][0]
    tensor = lambda x: torch.as_tensor(x, dtype=p.dtype, device=p.device)
    state = start(model, tensor([first.observation]), tensor([first.goal]), plan['anchor'])
    for event in plan['events']:
        state, _ = observe(model, state, event)
    require_query(model, state, observation, goal, memory['ids'])
    return state


def root_dict(state):
    return dict(encoded=state.encoded, valid=state.valid, context=state.context,
                h=state.h[None], weights=state.log_weights.exp().to(state.h.dtype)[None])


def state_record(state):
    return dict(anchor_ids=list(state.anchor_ids), used_ids=list(state.used_ids),
        log_weights=state.log_weights.detach().cpu().tolist(), log_evidence=float(state.log_evidence.detach()),
        h_sha256=hashlib.sha256(state.h.detach().cpu().contiguous().numpy().tobytes()).hexdigest(),
        world_id=state.world_id, episode=state.episode, terminal=state.terminal)
