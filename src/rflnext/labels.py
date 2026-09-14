"""Exact ground-truth causal labels for the two-level causal grid.

Stage 1 deliberately has no attributor: the generator knows the SCM, so the
learning responsibility ``U`` is computed by definition from two booleans about
the realized rollout plus the generator's own hazard flag.  Nothing is
searched, sampled, or estimated.

``p`` is multi-label causal evidence and is *not* normalized and *not* softmaxed:
``p_h + p_l + p_e`` may exceed 1.  ``p`` and ``U`` are separate variables and
must never be collapsed into one.
"""

from __future__ import annotations

from dataclasses import dataclass

from .env import SUCCESS, W

FAMILIES = ("H_error", "L_error", "HL_error", "E_failure")


@dataclass(frozen=True)
class CausalLabels:
    family: str
    u_h: int
    u_l: int
    p_h: float
    p_l: float
    p_e: float
    h_correct: bool
    l_correct: bool
    hazard: int

    @property
    def u(self) -> tuple[int, int]:
        return (self.u_h, self.u_l)


def causal_labels(
    *,
    option: int,
    goal_lane: int,
    final_x: int,
    final_y: int,
    hazard: int,
    terminal: str,
) -> CausalLabels | None:
    """Ground-truth labels for one finished episode, or ``None`` on success.

    ``l_correct`` asks whether the low level completed *its own* corridor --
    the one selected by ``option`` -- rather than whether it reached the goal
    lane.  Judging it by the goal lane would score "chose the right option but
    drove to the wrong lane" as a high-level error, and would make the pair
    ``(h_correct, l_correct) == (True, True)`` reachable on a failure.
    """
    if terminal == SUCCESS:
        return None

    h_correct = option == goal_lane
    l_correct = final_x == W - 1 and final_y == option

    if hazard == 1:
        # The gate is jammed: no plan and no execution could have helped.
        return CausalLabels(
            family="E_failure", u_h=0, u_l=0, p_h=0.0, p_l=0.0, p_e=1.0,
            h_correct=h_correct, l_correct=l_correct, hazard=hazard,
        )

    u_h = 0 if h_correct else 1
    u_l = 0 if l_correct else 1
    family = {
        (1, 0): "H_error",
        (0, 1): "L_error",
        (1, 1): "HL_error",
    }.get((u_h, u_l))
    if family is None:
        raise AssertionError(
            "hazard-free failure with both modules correct is unreachable: "
            f"option={option} goal_lane={goal_lane} final=({final_x},{final_y}) "
            f"terminal={terminal}"
        )
    return CausalLabels(
        family=family, u_h=u_h, u_l=u_l,
        p_h=float(u_h), p_l=float(u_l), p_e=0.0,
        h_correct=h_correct, l_correct=l_correct, hazard=hazard,
    )


def family_of(u_h: int, u_l: int, hazard: int) -> str:
    """Inverse map, used by tests and by the realized-count report."""
    if hazard == 1:
        return "E_failure"
    return {(1, 0): "H_error", (0, 1): "L_error", (1, 1): "HL_error"}[(u_h, u_l)]
