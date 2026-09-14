"""Two-level causal grid: geometry only, no randomness, no learning."""

from __future__ import annotations

UP, DOWN, RIGHT, WAIT = 0, 1, 2, 3
N_ACTIONS = 4
W = 5
LANES = 2
HORIZON = 8

SUCCESS = "SUCCESS"
BLOCKED = "BLOCKED"
TIMEOUT = "TIMEOUT"
FAILURES = (BLOCKED, TIMEOUT)


def step_cell(x: int, y: int, action: int) -> tuple[int, int]:
    """Deterministic primitive transition."""
    if action == UP:
        return x, 0
    if action == DOWN:
        return x, 1
    if action == RIGHT:
        return min(x + 1, W - 1), y
    if action == WAIT:
        return x, y
    raise ValueError(f"unknown action {action!r}")


def terminal_kind(x: int, y: int, goal_lane: int, hazard: int) -> str | None:
    """Terminal on the exit cell, or ``None`` to continue.

    Entering the exit cell while the hazard is active is a failure: the gate
    is jammed.  This is the only exogenous cause of failure in the env, and it
    is what makes the ``E_failure`` family unwinnable by construction.
    """
    if x == W - 1 and y == goal_lane:
        return BLOCKED if hazard == 1 else SUCCESS
    return None
