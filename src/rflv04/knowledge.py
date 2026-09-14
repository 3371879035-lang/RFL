"""Knowledge sets and the two damage endpoints.

v0.3 measured only ``KD_innocent`` -- harm to the module that was *not* blamed.
Oracle's value on that metric was exactly zero, so the metric reported Oracle as
perfect while Oracle was still damaging correct sub-knowledge *inside* the
module it correctly blamed.  A metric that cannot see the failure cannot
diagnose it.

Both endpoints here are the same function over different knowledge sets:

    KD_innocent   margin loss over K of the unit that was NOT blamed
    WMD           margin loss over K of the unit that WAS blamed

The knowledge set is established on the **clean reference path**, before any
shock, and only items with a checkpoint margin of at least ``theta`` enter it.
That avoids the v0.2 failure mode of hunting for "correct knowledge" at a
failing trace's terminal transition, which is the one place a collision has
just taught Q to dislike.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rflnext.knowledge import correct_margin

from .env import ACT, X_MAX, reference_action

DEFAULT_THETA = 0.60


@dataclass(frozen=True)
class KnowledgeItem:
    """One established correct knowledge item of a module."""

    unit: str          # "PLAN" | "DECISION" | "EXECUTION"
    state: tuple
    correct: int
    margin_at_checkpoint: float

    @property
    def key(self) -> tuple:
        return (self.unit, self.state, self.correct)


@dataclass
class KnowledgeSet:
    items: list = field(default_factory=list)
    theta: float = DEFAULT_THETA

    def by_unit(self, unit: str) -> list:
        return [k for k in self.items if k.unit == unit]

    def units(self) -> list:
        return sorted({k.unit for k in self.items})


def build_knowledge_set(q, *, theta: float = DEFAULT_THETA, horizon: int = 8,
                        x_max: int = X_MAX) -> KnowledgeSet:
    """Read established knowledge off a trained checkpoint, evaluator-side.

    Only items the checkpoint already holds with margin >= theta are admitted,
    so a damage measurement is never normalised by knowledge that was never
    there.
    """
    ks = KnowledgeSet(theta=theta)
    options = tuple(getattr(q, "options", (0, 1)))

    # PLAN-phase items: at t=0 the correct plan is the context lane.
    for g in (0, 1):
        state = (g, 0, 0, -1, 0)
        vals = {o: q.high_get((g, 0, 0), o) for o in options}
        if vals:
            best = max(vals, key=vals.get)
            m = correct_margin(vals, best)
            if m >= theta:
                ks.items.append(KnowledgeItem("PLAN", (g, 0, 0), best, m))

    # DECISION-phase items: on the clean path, the correct action at each state.
    # The competing set must be the ACT actions only.  Including PLAN_A/PLAN_B
    # (which are never legal here and sit at exactly 0.0) manufactured a
    # competitor out of nothing and pushed every real margin below theta, which
    # silently emptied the Knowledge Set and made the whole damage measurement
    # structurally zero.
    from .env import ACT_ACTIONS
    for o in options:
        x, y = 0, 0
        for t in range(1, horizon + 1):
            state = (x, y, o, t)
            correct = reference_action(x, y, o)
            row = q.low.get(state)
            if row is None:
                break
            vals = {a: row[a] for a in ACT_ACTIONS}
            m = correct_margin(vals, correct)
            if m >= theta:
                ks.items.append(KnowledgeItem("DECISION", state, correct, m))
            from .env import apply_action
            x, y = apply_action(x, y, o, correct)
            if x == x_max:
                break
    return ks


def unit_margin(q, item: KnowledgeItem) -> float:
    if item.unit == "PLAN":
        options = tuple(getattr(q, "options", (0, 1)))
        vals = {o: q.high_get(item.state, o) for o in options}
    else:
        from .env import ACT_ACTIONS
        row = q.low.get(item.state)
        if row is None:
            return 0.0
        vals = {a: row[a] for a in ACT_ACTIONS}
    return correct_margin(vals, item.correct)


def damage(q_before, q_after, items: list, *, eps: float = 1e-9) -> float:
    """Mean normalised margin loss over the given knowledge items.

    Reuses the v0.3 CKD formula, so the two are directly comparable.
    """
    if not items:
        return 0.0
    total = 0.0
    for item in items:
        mb = unit_margin(q_before, item)
        ma = unit_margin(q_after, item)
        total += max(0.0, mb - ma) / (abs(mb) + eps)
    return total / len(items)


def wmd(q_before, q_after, ks: KnowledgeSet, blamed_units: set) -> float:
    """WithinModuleDamage: damage inside the unit that was blamed."""
    items = [k for k in ks.items if k.unit in blamed_units]
    return damage(q_before, q_after, items)


def kd_innocent(q_before, q_after, ks: KnowledgeSet, blamed_units: set) -> float:
    """Damage to units that were NOT blamed."""
    items = [k for k in ks.items if k.unit not in blamed_units]
    return damage(q_before, q_after, items)


def clean_reference_path(o: int, *, horizon: int = 8, x_max: int = X_MAX) -> list:
    """The states a correct execution of plan ``o`` visits."""
    from .env import apply_action

    x, y = 0, 0
    out = []
    for t in range(1, horizon + 1):
        out.append((x, y, o, t))
        x, y = apply_action(x, y, o, reference_action(x, y, o))
        if x == x_max:
            break
    return out
