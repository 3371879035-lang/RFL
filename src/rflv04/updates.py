"""Update-target semantics.

v0.3's rule was ``Q <- Q - alpha_diag``: a fixed subtraction with no target.
Pilot Beta's arms replace it with proper TD-style targets, so the question
"should the bad action go down, should a verified alternative go up, or both"
is asked separately from "which entry".

All updates go through :func:`apply_update`, which enforces the plan's safe
constraints in code rather than by convention:

* no site, no update;
* ``|delta Q| <= DELTA_MAX`` on every single write;
* the full before/after Q-row is returned, never only a scalar.
"""

from __future__ import annotations

from dataclasses import dataclass, field

DELTA_MAX = 0.25


@dataclass
class AppliedUpdate:
    unit: str
    state: tuple
    action: int
    q_before: float
    q_after: float
    target_value: float
    clipped: bool = False
    role: str = "bad"       # "bad" | "alternative"

    @property
    def delta_q(self) -> float:
        return self.q_after - self.q_before


@dataclass
class UpdateRecord:
    mode: str
    applied: list = field(default_factory=list)
    no_site: bool = False

    @property
    def total_mass(self) -> float:
        return sum(abs(u.delta_q) for u in self.applied)


def _row(q, unit: str, state: tuple) -> dict:
    if unit == "PLAN":
        options = tuple(getattr(q, "options", (0, 1)))
        return {o: q.high_get(state, o) for o in options}
    row = q.low.get(state)
    if row is None:
        return {}
    return {a: row[a] for a in range(len(row))}


def _write(q, unit: str, state: tuple, action: int, value: float) -> None:
    if unit == "PLAN":
        q.high_update(state, action, value, 1.0)
    else:
        q.low_update(state, action, value, 1.0)


def apply_update(
    q,
    *,
    unit: str,
    state: tuple,
    action: int,
    target_value: float,
    alpha: float,
    mode: str,
    role: str = "bad",
    delta_max: float = DELTA_MAX,
) -> AppliedUpdate | None:
    """One capped TD-style write, returning a full receipt."""
    row = _row(q, unit, state)
    if not row:
        return None
    before = float(row.get(action, 0.0))
    desired = alpha * (float(target_value) - before)
    clipped = abs(desired) > delta_max
    delta = max(-delta_max, min(delta_max, desired))
    after = before + delta
    _write(q, unit, state, action, after)
    return AppliedUpdate(unit=unit, state=state, action=action, q_before=before,
                         q_after=after, target_value=float(target_value),
                         clipped=clipped, role=role)


def negative_only(q, sites, targets, *, alpha: float) -> UpdateRecord:
    """Push the factual bad action toward its failure target.  Nothing else."""
    rec = UpdateRecord("negative_only")
    if not sites:
        rec.no_site = True
        return rec
    for site in sites:
        y = targets.get(site.key)
        if y is None:
            continue
        upd = apply_update(q, unit=site.unit, state=site.state, action=site.action,
                           target_value=y, alpha=alpha, mode="negative_only")
        if upd is not None:
            rec.applied.append(upd)
    return rec


def positive_alternative_only(q, alternatives, targets, *, alpha: float) -> UpdateRecord:
    """Raise only the verified alternative.  The bad action is left alone."""
    rec = UpdateRecord("positive_alternative_only")
    if not alternatives:
        rec.no_site = True
        return rec
    for site in alternatives:
        y = targets.get(site.key)
        if y is None:
            continue
        upd = apply_update(q, unit=site.unit, state=site.state, action=site.action,
                           target_value=y, alpha=alpha, mode="positive_alternative_only",
                           role="alternative")
        if upd is not None:
            rec.applied.append(upd)
    return rec


def contrastive(q, sites, alternatives, targets, *, alpha: float) -> UpdateRecord:
    """Both directions, as the plan's H_B hypothesis specifies."""
    rec = UpdateRecord("contrastive")
    if not sites and not alternatives:
        rec.no_site = True
        return rec
    for site in sites:
        y = targets.get(site.key)
        if y is None:
            continue
        upd = apply_update(q, unit=site.unit, state=site.state, action=site.action,
                           target_value=y, alpha=alpha, mode="contrastive")
        if upd is not None:
            rec.applied.append(upd)
    for site in alternatives:
        y = targets.get(site.key)
        if y is None:
            continue
        upd = apply_update(q, unit=site.unit, state=site.state, action=site.action,
                           target_value=y, alpha=alpha, mode="contrastive",
                           role="alternative")
        if upd is not None:
            rec.applied.append(upd)
    return rec


MODES = {
    "negative_only": negative_only,
    "positive_alternative_only": positive_alternative_only,
    "contrastive": contrastive,
}
