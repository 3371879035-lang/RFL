"""Conditional sequence likelihood from the identical online observation recursion."""
import torch
from feedback_program_v222.memory import actual_sequence
from .filtering import from_view, observe


def sequence_nll(model, bank, event_ids):
    if bank.layout != model.layout:
        raise ValueError('Measurement semantics changed')
    _, events = actual_sequence(bank, event_ids)
    first = events[0]; stop = bank.index[first.id]
    memory = bank.forecast_view(first.previous_id, stop)
    p = next(model.parameters()); tensor = lambda x: torch.as_tensor(x, dtype=p.dtype, device=p.device)
    state = from_view(model, tensor([first.observation]), tensor([first.goal]), memory)
    initial_log_weights = state.log_weights; terms = []; states = []
    for event in events:
        states.append(state)
        state, detail = observe(model, state, event); terms.append(detail)
    loss = -torch.stack([t['log_predictive'] for t in terms]).sum()
    component = torch.stack([t['component_log_likelihood'] for t in terms]).sum(0)
    direct = -torch.logsumexp(initial_log_weights+component, 0)
    return loss, dict(terms=terms, pre_states=states, final_state=state,
        direct_joint_nll=direct, target_ids=tuple(event_ids), input_prefix_ids=tuple(memory['ids']),
        anchor_ids=states[0].anchor_ids, pre_consumed_ids=states[0].used_ids)
