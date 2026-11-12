r"""B2-3 — the Retention **candidate forms**, and the diagnostic that is not a candidate.

A79 §67.5 froze Retention as a **dimension** and named candidate forms without choosing one, on one
hard requirement:

$$\boxed{\text{the confirmatory Retention primary must be defined for EVERY seed}}$$

An effect that exists for one or two episodes and then decays is a different finding from one that
holds, and pooling them would hide it — so the eligible forms are the ones that are *always*
defined, including for a seed that never recovers:

* `RetentionAtH` — the level at a **fixed absolute horizon** $H$ measured from the update/trigger,
  not "$H$ episodes after recovery";
* `LateWindowRetention[H1, H2]` — the maintained level over a pre-registered late window.

Both take their horizon as a **parameter**. There is no defaulted $H$, $H_1$ or $H_2$: they are
development-stage quantities (A83 §71.4), and a "reasonable" default in code would be the design
decision made by whoever typed it.

**The $\tau$-conditioned form is kept, and labelled.** `RetentionFraction` divides by
$\#\{t \ge \tau\}$, so it is undefined for a seed that never recovers — it is a **conditional
descriptive diagnostic**, not a confirmatory candidate, and it carries that in its type rather than
in a comment, so a generic registry cannot pick it up by accident.

**No form is selected.** `select_form` raises unless asked for a named candidate, for the same
reason the unaffected-set construction refuses to have a default.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Mapping

from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b2.utility import _require_horizon, _require_real

__all__ = [
    "CANDIDATE_FORMS",
    "DIAGNOSTIC_FORMS",
    "LateWindowRetention",
    "RetentionAtH",
    "RetentionRole",
    "retention_fraction",
    "select_form",
]


class RetentionRole(Enum):
    """Whether a form may serve as the confirmatory primary, or is descriptive only."""

    CANDIDATE = "candidate"
    CONDITIONAL_DIAGNOSTIC = "conditional_diagnostic"


def _require_grid(values, episodes) -> tuple:
    values, episodes = tuple(values), tuple(episodes)
    if len(values) != len(episodes) or not values:
        raise ProtocolError("the curve and its episode indices must be non-empty and equal length")
    for i, (v, t) in enumerate(zip(values, episodes)):
        _require_real(v, f"the curve value at position {i}")
        if isinstance(t, bool) or not isinstance(t, int):
            raise ProtocolError(f"the episode index at position {i} is {t!r}, not an integer")
    for a, b in zip(episodes, episodes[1:]):
        if not a < b:
            raise ProtocolError(
                f"the episode indices must be strictly increasing, got {a} then {b}")
    return values, episodes


def _at(values, episodes, episode: int) -> float:
    if episode not in episodes:
        raise ProtocolError(
            f"episode {episode} is not a checkpoint; a Retention horizon must be one of the "
            f"pre-registered checkpoints {episodes[:4]}..., never interpolated silently")
    return float(values[episodes.index(episode)])


@dataclass(frozen=True, slots=True)
class RetentionAtH:
    r"""$\text{Retention}@H$: the level at a **fixed absolute** horizon from the update.

    The absolute form is the one defined for every seed — with one exception that is checked rather
    than assumed: the horizon must be a pre-registered checkpoint, because interpolating to reach
    $H$ would be a second estimator inside this one.
    """

    role = RetentionRole.CANDIDATE

    @staticmethod
    def value(values, episodes, *, H: int) -> float:
        values, episodes = _require_grid(values, episodes)
        if isinstance(H, bool) or not isinstance(H, int):
            raise ProtocolError(f"the retention horizon H={H!r} is not an integer episode index")
        return _at(values, episodes, H)


@dataclass(frozen=True, slots=True)
class LateWindowRetention:
    r"""$\text{LateWindowRetention}[H_1, H_2]$: the **checkpoint mean** over a late window.

    $H_1$ and $H_2$ are pre-registered **episode bounds**, not required to be checkpoints
    themselves: the value is the arithmetic mean of the checkpoints inside the closed window, and
    at least two must lie inside or the window is refused. That makes the form defined for a seed
    that decays, one that never recovers, and one that recovers late.

    It is a *checkpoint mean* and says so: a time-weighted late-window form is a **different
    candidate** the development stage may compare it against on measurement properties, and naming
    this one precisely is what keeps that comparison available instead of implying the formula was
    frozen by A79.
    """

    role = RetentionRole.CANDIDATE

    @staticmethod
    def value(values, episodes, *, H1: int, H2: int) -> float:
        values, episodes = _require_grid(values, episodes)
        for name, h in (("H1", H1), ("H2", H2)):
            if isinstance(h, bool) or not isinstance(h, int):
                raise ProtocolError(f"the window bound {name}={h!r} is not an integer episode index")
        if not H1 < H2:
            raise ProtocolError(f"the window [{H1}, {H2}] is empty or inverted")
        inside = [(t, v) for t, v in zip(episodes, values) if H1 <= t <= H2]
        if len(inside) < 2:
            raise ProtocolError(
                f"the window [{H1}, {H2}] contains {len(inside)} checkpoint(s); a maintained level "
                "over a window needs at least two")
        return sum(float(v) for _t, v in inside) / len(inside)


def retention_fraction(values, episodes, *, tau, pre_level: float,
                       fraction: float = 0.95) -> float:
    r"""$\text{RetentionFraction} = \frac{\#\{t \ge \tau : V(t) \ge f V_{\text{pre}}\}}
    {\#\{t \ge \tau\}}$ — **conditional and descriptive**.

    Defined only for a seed that recovered, which is exactly why it cannot be the confirmatory
    primary: A79 §67.5 requires a form defined for **every** seed. The `role` marker is on the
    function so a registry can exclude it by inspection.
    """
    if tau is None:
        raise ProtocolError(
            "RetentionFraction is conditioned on recovery and is undefined for a seed that never "
            "recovered; it is a conditional descriptive diagnostic, not a confirmatory form "
            "(A79 67.5)")
    values, episodes = _require_grid(values, episodes)
    after = [(t, v) for t, v in zip(episodes, values) if t >= tau]
    if not after:
        raise ProtocolError(f"no checkpoint lies at or after tau={tau}")
    threshold = fraction * _require_real(pre_level, "the pre-update level")
    return sum(1 for _t, v in after if v >= threshold) / len(after)


retention_fraction.role = RetentionRole.CONDITIONAL_DIAGNOSTIC
retention_fraction.always_defined = False
RetentionAtH.always_defined = True
LateWindowRetention.always_defined = True

#: The forms eligible as the confirmatory primary: always defined, horizon pre-registered.
CANDIDATE_FORMS: Mapping[str, Callable] = {
    "RetentionAtH": RetentionAtH.value,
    "LateWindowRetention": LateWindowRetention.value,
}

#: Kept apart **by registry**, so a generic "give me the candidates" query cannot pick it up.
DIAGNOSTIC_FORMS: Mapping[str, Callable] = {
    "RetentionFraction": retention_fraction,
}


def select_form(name: str) -> Callable:
    r"""$$\boxed{\text{the Retention form is chosen at the development stage, not here}}$$

    §67.5's rule for the choice is frozen (defined for every seed; chosen on measurement
    properties); which of the eligible forms is primary is a dev-stage decision and stays open.
    """
    if name in DIAGNOSTIC_FORMS:
        raise ProtocolError(
            f"{name!r} is a conditional descriptive diagnostic, not an eligible confirmatory form: "
            "it is undefined for a seed that never recovers, and A79 67.5 requires the primary to "
            "be defined for every seed")
    if name not in CANDIDATE_FORMS:
        raise ProtocolError(
            f"{name!r} is not a Retention form; eligible {sorted(CANDIDATE_FORMS)}, diagnostic "
            f"{sorted(DIAGNOSTIC_FORMS)}")
    return CANDIDATE_FORMS[name]
