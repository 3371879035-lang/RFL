"""Pure knowledge-state diagnostics for the v0.2 update-learning chain."""

from __future__ import annotations

from collections.abc import Sequence


def correct_margin(values: dict, correct_key) -> float:
    """Margin of the correct item over the strongest competing item."""
    correct = float(values.get(correct_key, 0.0))
    competitors = [float(v) for k, v in values.items() if k != correct_key]
    return correct - (max(competitors) if competitors else 0.0)


def wrong_margin(values: dict, correct_key, wrong_key) -> float:
    """Wrong-item advantage over the correct item."""
    return float(values.get(wrong_key, 0.0)) - float(values.get(correct_key, 0.0))


def ckd(margin_before: float, margin_after: float, eps: float = 1e-9) -> float:
    """Correct-knowledge degradation, clipped to degradation only."""
    return max(0.0, float(margin_before) - float(margin_after)) / (abs(float(margin_before)) + eps)


def wkr(margin_before: float, margin_after: float, eps: float = 1e-9) -> float:
    """Wrong-knowledge reinforcement, clipped to reinforcement only."""
    return max(0.0, float(margin_after) - float(margin_before)) / (abs(float(margin_before)) + eps)


def correct_knowledge_damage(before: dict, after: dict, correct_key, eps: float = 1e-9) -> float:
    """CKD computed directly from before/after Q-value dictionaries."""
    return ckd(correct_margin(before, correct_key), correct_margin(after, correct_key), eps)


def wrong_knowledge_reinforcement(
    before: dict, after: dict, correct_key, wrong_key, eps: float = 1e-9
) -> float:
    """WKR computed directly from before/after Q-value dictionaries."""
    return wkr(wrong_margin(before, correct_key, wrong_key), wrong_margin(after, correct_key, wrong_key), eps)


def recovery_episode(
    margins: Sequence[float],
    initial_margin: float | None = None,
    *,
    fraction: float = 0.95,
    threshold: float | None = None,
    consecutive: int = 3,
    episode_interval: int = 1,
    checkpoint_interval: int | None = None,
    horizon: int | None = None,
) -> int | None:
    """First checkpoint at which the margin stays above threshold.

    ``margins`` is ordered by evaluation checkpoint.  Returning ``None`` (or
    ``horizon + 1`` when a horizon is supplied) explicitly represents
    failure to recover rather than silently treating the last checkpoint as a
    success.
    """
    interval = episode_interval if checkpoint_interval is None else checkpoint_interval
    if not margins:
        return (horizon + 1) if horizon is not None else None
    base = float(margins[0] if initial_margin is None else initial_margin)
    target = (fraction if threshold is None else threshold) * base
    run = 0
    for idx, value in enumerate(margins):
        run = run + 1 if float(value) >= target else 0
        if run >= max(1, consecutive):
            start = idx - run + 1
            return start * interval
    return (horizon + 1) if horizon is not None else None
