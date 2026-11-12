from dataclasses import dataclass
from feedback_program_v221.memory import Event,MemoryBank,Schema


@dataclass(frozen=True)
class ThoughtNode:
    arm: int
    hypothesis: int
    depth: int
    parent: int | None
    observation: tuple
    action_index: int
    next_observation: tuple
    feedback: tuple
    next_variance: tuple
    feedback_variance: tuple
    predicted_terminal: bool
    original_weight: float


def actual_sequence(bank,event_ids):
    if not event_ids:raise ValueError('A sequence needs actual observed events')
    positions=[bank.index[i] for i in event_ids]
    if len(set(event_ids))!=len(event_ids) or positions!=sorted(positions):raise ValueError('A sequence lists unique actual events in order')
    events=[bank.events[i] for i in positions]
    for a,b in zip(events,events[1:]):
        if b.previous_id!=a.id or a.terminal or a.episode!=b.episode or a.next_observation!=b.observation:
            raise ValueError('Not a contiguous observed episode segment')
    return bank.view(positions[0]),tuple(events)
