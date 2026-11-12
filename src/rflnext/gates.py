"""Pre-registered gates for Pilot Alpha.

The ceiling gate exists because v0.1 Experiment B saturated at 0.96-0.98 and
produced an uninterpretable null.  Here it is checked before the benchmark is
trusted, not after a null result is explained away.

Note on what "saturated" can mean here.  ``hazard=1`` episodes are unwinnable
by construction, so final success has a *structural* ceiling of
``1 - p_hazard`` that no policy can exceed.  Every arm reaching that ceiling is
therefore expected rather than alarming -- on its own it says nothing about
discriminating power.  What makes a benchmark useless is that the arms cannot
be told apart, so the fatal condition is a flat learning curve (AUC spread
below the floor).  Saturation is reported alongside it as a diagnostic.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .metrics import final_success, success_auc


@dataclass
class GateReport:
    status: str
    reasons: list = field(default_factory=list)
    finals: dict = field(default_factory=dict)
    aucs: dict = field(default_factory=dict)
    auc_spread: float = 0.0
    saturated_at_ceiling: bool = False


def ceiling_gate(
    results: dict, *, structural_ceiling: float, min_auc_gap: float
) -> GateReport:
    """Fail only when the arms are indistinguishable.

    ``structural_ceiling`` is ``1 - p_hazard``: the highest final success any
    policy could reach, since hazard episodes cannot be won.
    """
    finals = {arm: final_success(r.success_curve) for arm, r in results.items()}
    aucs = {arm: success_auc(r.success_curve, r.checkpoints) for arm, r in results.items()}

    spread = 0.0
    if len(aucs) >= 2:
        spread = max(aucs.values()) - min(aucs.values())

    saturated = bool(finals) and all(
        v >= float(structural_ceiling) - 1e-9 for v in finals.values()
    )

    reasons: list = []
    if len(aucs) >= 2 and spread < float(min_auc_gap):
        reasons.append("auc_gap_below_floor")

    status = "benchmark_no_discriminating_power" if reasons else "ok"
    return GateReport(
        status=status,
        reasons=reasons,
        finals=finals,
        aucs=aucs,
        auc_spread=float(spread),
        saturated_at_ceiling=saturated,
    )


def family_gate(results: dict, *, min_family_events: int) -> GateReport:
    """Every family must be realized at least ``min_family_events`` times in
    every arm.  Under-representation is reported, never silently patched."""
    short: list = []
    for _arm, r in results.items():
        for family, count in r.family_counts.items():
            if int(count) < int(min_family_events):
                short.append(family)
    short = sorted(set(short))
    status = "insufficient_family_events" if short else "ok"
    return GateReport(status=status, reasons=short)
