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


def terminal_kind(x: int, y: int, goal_lane: int, hazard: int, lucky: int = 0) -> str | None:
    """Terminal on the exit cell, or ``None`` to continue.

    ``hazard=1`` jams the gate on the goal lane: the only exogenous cause of
    *failure*.  ``lucky=1`` opens a shortcut on the other lane: the only
    exogenous cause of *unearned success*, which Stage 3 needs so that a wrong
    plan can succeed by luck and later be re-interpreted.

    ``lucky`` defaults to 0, so every earlier caller keeps its old behaviour.
    """
    if x == W - 1:
        if y == goal_lane:
            return BLOCKED if hazard == 1 else SUCCESS
        if lucky == 1:
            return SUCCESS
    return None
