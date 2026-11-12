"""Unratified, seedless V0.3R measurement amendment prototype.

These pure functions are NOT installed into the production F0/F1 dispatch. No
acquisition, filesystem writes, lock publication or stage authorization exists
here. The intended scientific behavior changes are explicit in contract.json.
"""
from __future__ import annotations

import math
from fractions import Fraction
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b2.design_selection import grid_templates, spearman
from rfl_rebuild.b2.numerics import mean, sd
from rfl_rebuild.b2.retention import RetentionAtH, LateWindowRetention
from rfl_rebuild.b2.utility import FutureUtility

PROTOTYPE_ID = "v03r-healthy-settling-retention-construct-draft-v1"
K = 3
EPSILON_S = .001
EPSILON_F = .1
HEALTHY_FRACTION = .95
STABILITY_LIMIT = .10
GRID_ERROR_LIMIT = .05
RETENTION_MARGIN_MULTIPLIER = .25
FORMS = ("RetentionAtH", "LateWindowRetention")


def _finite(values):
    values = tuple(values)
    if not values or any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
        raise ProtocolError("nonempty finite real curve required; bool is not a level")
    return values


def _pre_level(value):
    _finite((value,))
    if value <= 0:
        raise ProtocolError("positive healthy reference required for this proposed recovery rule")
    return value


def _cap(value):
    if type(value) is not int or value < 4:
        raise ProtocolError("cap must allow K=3 plus two observed follow-up episodes")
    return value


def _full_curves(curves, cap):
    cap = _cap(cap)
    curves = tuple(_finite(curve) for curve in curves)
    if len(curves) != 32 or any(len(curve) != cap + 1 for curve in curves):
        raise ProtocolError("all original 32 complete baseline axes 0..cap are required")
    return curves


def _flat(window):
    # Exactly the former K=3 slope/flip arithmetic, now applied to each window.
    slope = (window[-1] - window[0]) / (K - 1)
    increments = tuple(b - a for a, b in zip(window, window[1:]))
    if all(delta == 0 for delta in increments):
        flip_rate = 0.0
    else:
        pairs = [(a, b) for a, b in zip(increments, increments[1:]) if a != 0 and b != 0]
        if not pairs:
            return False  # Undefined flip denominator is not filled with zero.
        flip_rate = sum((a < 0) != (b < 0) for a, b in pairs) / len(pairs)
    return abs(slope) < EPSILON_S and flip_rate < EPSILON_F


def healthy_settling_time(values, episodes, *, pre_level):
    """First healthy flat window whose entire observed suffix remains healthy/flat.

Dense baseline axis only. At least two subsequent observed episodes must exist.
None is censoring/non-identification, never missing-data imputation. The suffix
checks all the way to the fixed cap; no old or treatment curve enters this code.
"""
    values, episodes = _finite(values), tuple(episodes)
    cap = _cap(len(values) - 1)
    if (len(episodes) != len(values) or any(type(e) is not int for e in episodes)
            or episodes != tuple(range(cap + 1))):
        raise ProtocolError("complete dense baseline episode axis 0..cap required")
    threshold = HEALTHY_FRACTION * _pre_level(pre_level)
    suffix_valid = [False] * len(values)
    suffix = True
    for end in range(cap, K - 2, -1):
        window = values[end - K + 1:end + 1]
        suffix = suffix and all(v >= threshold for v in window) and _flat(window)
        suffix_valid[end] = suffix
    return next((end for end in range(K - 1, cap - 1) if suffix_valid[end]), None)


def select_horizon(curves, *, pre_level, acquisition_cap):
    curves = _full_curves(curves, acquisition_cap)
    times = [healthy_settling_time(c, range(acquisition_cap + 1), pre_level=pre_level) for c in curves]
    observed = sorted(t for t in times if t is not None)
    rank = (9 * len(times) + 9) // 10
    result = {"prototype": PROTOTYPE_ID, "status": "NO_ADMISSIBLE_T", "T": None,
              "reason": "HEALTHY_SETTLING_QUANTILE_UNIDENTIFIED", "n": len(times),
              "rank": rank, "uncensored": len(observed), "censored": len(times) - len(observed),
              "healthy_settling_times": times, "scientific_execution_authorized": False}
    if len(observed) < rank:
        return result
    q = observed[rank - 1]
    # Original exact 6/5 ceiling retained; q+2 supplies three distinct shared
    # late anchors. It is NOT an expanded cap or a fitted persistence duration.
    horizon = max((6 * q + 4) // 5, q + 2)
    if horizon > acquisition_cap:
        return {**result, "quantile": q, "reason": "HORIZON_EXCEEDS_UNCHANGED_CAP"}
    return {**result, "status": "HORIZON_MEASURABLE_PROTOTYPE_ONLY", "reason": None,
            "quantile": q, "T": horizon, "late_anchors": list(late_anchors(q, horizon))}


def late_anchors(q, horizon):
    if (type(q) is not int or q < K - 1 or type(horizon) is not int
            or horizon != max((6 * q + 4) // 5, q + 2)):
        raise ProtocolError("shared late window must be exactly the proposed q-to-T rule")
    anchors = (q, q + (horizon - q) // 2, horizon)
    if len(set(anchors)) != K:
        raise ProtocolError("late anchors must contain three distinct checkpoints")
    return anchors


def select_grid(curves, *, quantile, horizon, pre_level):
    curves = tuple(_finite(c) for c in curves)
    _pre_level(pre_level)
    anchors = late_anchors(quantile, horizon)
    if len(curves) != 32 or any(len(c) <= horizon for c in curves):
        raise ProtocolError("all 32 complete horizon prefixes required")
    full_grid = tuple(range(horizon + 1))
    full = [FutureUtility.from_curve(c[:horizon + 1], full_grid, pre_level=pre_level, t_max=horizon)
            for c in curves]
    candidates = []
    for number, template in enumerate(grid_templates(horizon), 1):
        grid = tuple(sorted(set(template) | set(anchors)))
        metrics = []
        for curve, original in zip(curves, full):
            reduced = FutureUtility.from_curve(tuple(curve[e] for e in grid), grid,
                                               pre_level=pre_level, t_max=horizon)
            metrics.append(max(abs(reduced.restricted_time - original.restricted_time) / horizon,
                               abs(reduced.deficit_auc - original.deficit_auc)))
        metric = max(metrics)
        candidates.append({"template": number, "grid": list(grid), "metric": metric,
                           "admissible": metric <= GRID_ERROR_LIMIT})
    eligible = [c for c in candidates if c["admissible"]]
    chosen = min(eligible, key=lambda c: (len(c["grid"]), c["template"])) if eligible else None
    return {"prototype": PROTOTYPE_ID, "status": "GRID_MEASURABLE_PROTOTYPE_ONLY" if chosen else "NO_ADMISSIBLE_GRID",
            "grid": chosen["grid"] if chosen else None, "candidates": candidates,
            "scientific_execution_authorized": False}


def _grid(grid, quantile, horizon):
    anchors = late_anchors(quantile, horizon)
    grid = tuple(grid)
    if (any(type(e) is not int for e in grid) or tuple(sorted(set(grid))) != grid
            or not grid or grid[0] != 0 or grid[-1] != horizon or not set(anchors) <= set(grid)):
        raise ProtocolError("shared complete grid and all late anchors required")
    return grid


def _retention_value(form, curve, grid, q, horizon):
    values = tuple(curve[e] for e in grid)
    if form == "RetentionAtH":
        return RetentionAtH.value(values, grid, H=horizon)
    if form == "LateWindowRetention":
        return LateWindowRetention.value(values, grid, H1=q, H2=horizon)
    raise ProtocolError("form outside the unchanged two-element universe")


def construct_witness(form, *, grid, quantile, horizon):
    """Fixed algebraic challenge, never fitted to development or treatment data.

    Both curves recover at 0 and have identical grid DeficitAUC analytically. Their final/late
performance differs. This is a witness of functional non-equivalence, NOT a
proof of treatment efficacy, low sampling correlation or practical importance.
"""
    grid = _grid(grid, quantile, horizon)
    first, second = [1.] * (horizon + 1), [1.] * (horizon + 1)
    earlier, penultimate = grid[-3], grid[-2]
    last_gap = horizon - penultimate
    span = horizon - earlier
    first[penultimate], first[horizon] = 0., 1.
    second[penultimate], second[horizon] = float(Fraction(last_gap, span)), 0.
    utilities = [FutureUtility.from_curve(tuple(c[e] for e in grid), grid,
                                         pre_level=1., t_max=horizon) for c in (first, second)]
    a, b = utilities
    retained = [_retention_value(form, c, grid, quantile, horizon) for c in (first, second)]
    exact_a = Fraction(span, 2)
    exact_b = Fraction(1, 2) * (1 - Fraction(last_gap, span)) * span + Fraction(last_gap, 2)
    roundoff_equal = math.isclose(a.deficit_auc, b.deficit_auc, rel_tol=0., abs_tol=1e-12)
    valid = (a.restricted_time == b.restricted_time and exact_a == exact_b
             and roundoff_equal and retained[0] != retained[1])
    return {"valid": valid, "role": "FIXED_ALGEBRAIC_CONSTRUCT_WITNESS_NOT_SCIENCE",
            "same_restricted_time": a.restricted_time == b.restricted_time,
            "exact_trapezoid_area_equal": exact_a == exact_b,
            "same_grid_deficit_auc_within_roundoff": roundoff_equal,
            "construction_roundoff_absolute_tolerance": 1e-12,
            "different_retention": retained[0] != retained[1]}


def select_retention(curves, *, grid, quantile, horizon, pre_level):
    """DRAFT replacement of correlation eligibility, never a rev5 PASS migration.

Stability limit .10, epsilon 1e-9 and .25*population-SD margin retained. Constant
Retention remains inadmissible. Spearman is reported including None; it is not
filled, thresholded or used to rank. The new construct gate must be ratified.
"""
    grid = _grid(grid, quantile, horizon)
    curves = tuple(_finite(c) for c in curves)
    if len(curves) != 32 or any(len(c) <= horizon for c in curves):
        raise ProtocolError("all 32 complete horizon prefixes required")
    _pre_level(pre_level)
    utilities = [FutureUtility.from_curve(tuple(c[e] for e in grid), grid,
                                         pre_level=pre_level, t_max=horizon) for c in curves]
    candidates = []
    for form in FORMS:
        values = _finite(_retention_value(form, c, grid, quantile, horizon) for c in curves)
        stability = (max(values) - min(values)) / (max(abs(v) for v in values) + 1e-9)
        margin = RETENTION_MARGIN_MULTIPLIER * sd(values)
        witness = construct_witness(form, grid=grid, quantile=quantile, horizon=horizon)
        reasons = []
        if not witness["valid"]:
            reasons.append("CONSTRUCT_WITNESS_FAIL")
        if stability > STABILITY_LIMIT:
            reasons.append("STABILITY_EXCEEDS_UNCHANGED_0.10")
        if margin == 0:
            reasons.append("ZERO_RETENTION_SPREAD_NO_THRESHOLD")
        candidates.append({"form": form, "parameters": {"H": horizon} if form == "RetentionAtH" else {"H1": quantile, "H2": horizon},
                           "values": values, "stability": stability, "margin": margin,
                           "construct_witness": witness, "admissible": not reasons, "reasons": reasons,
                           "diagnostic_spearman_restricted_time": spearman(values, [u.restricted_time for u in utilities]),
                           "diagnostic_spearman_deficit_auc": spearman(values, [u.deficit_auc for u in utilities])})
    eligible = [(i, c) for i, c in enumerate(candidates) if c["admissible"]]
    chosen = min(eligible, key=lambda pair: (pair[1]["stability"], pair[0]))[1] if eligible else None
    return {"prototype": PROTOTYPE_ID, "status": "RETENTION_MEASURABLE_PROTOTYPE_ONLY" if chosen else "NO_ADMISSIBLE_RETENTION",
            "endpoint": chosen, "candidates": candidates, "scientific_execution_authorized": False}


def require_scientific_execution_authorization(*_args, **_kwargs):
    """Fail closed until a separate ratified production instrument is implemented."""
    raise ProtocolError("DRAFT_PROTOTYPE: no F0/F1 lock, training or scientific seed authorization")
