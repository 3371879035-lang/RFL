"""Pilot Alpha endpoints.  All are pure functions over run history."""

from __future__ import annotations

from collections.abc import Sequence


def success_auc(success_at_checkpoint: Sequence[float], episodes: Sequence[int]) -> float:
    """Trapezoidal area under the success curve, normalised to [0, 1]."""
    if len(success_at_checkpoint) != len(episodes):
        raise ValueError("success and episode lists must align")
    if not episodes:
        return 0.0
    if len(episodes) < 2:
        return float(success_at_checkpoint[0])
    span = float(episodes[-1] - episodes[0])
    if span <= 0.0:
        raise ValueError("checkpoint episodes must be strictly increasing")
    area = 0.0
    for i in range(1, len(episodes)):
        dt = float(episodes[i] - episodes[i - 1])
        area += 0.5 * (float(success_at_checkpoint[i]) + float(success_at_checkpoint[i - 1])) * dt
    return area / span


def episodes_to_90(
    success_at_checkpoint: Sequence[float],
    episodes: Sequence[int],
    *,
    threshold: float = 0.90,
) -> int | None:
    """First checkpoint episode reaching ``threshold``, else ``None``."""
    for value, episode in zip(success_at_checkpoint, episodes):
        if float(value) >= float(threshold):
            return int(episode)
    return None


def final_success(success_at_checkpoint: Sequence[float]) -> float:
    if not success_at_checkpoint:
        raise ValueError("no checkpoints recorded")
    return float(success_at_checkpoint[-1])


def visited_state_coverage(states: Sequence) -> int:
    return len(set(states))


def n_negative_td(records: Sequence) -> int:
    """Count negative TD errors -- records that reward mode B is *not*
    'no negative learning'."""
    return int(sum(int(getattr(r, "n_negative_td", 0)) for r in records))
