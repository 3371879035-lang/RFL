"""Fixed benchmark margin with explicitly limited scientific claims.

The retained 1.5 is a declared quantitative comparison target, not a validated
smallest effect of practical importance. Interval classification is not the
V0.3R joint verdict and cannot authorize a scientific stage.
"""
from __future__ import annotations

import math

from rfl_rebuild.b1.errors import ProtocolError


def benchmark_rmst_policy(*, ratified=False):
    """Return an independent copy of the declared policy; drafts authorize nothing."""
    if type(ratified) is not bool:
        raise ProtocolError("benchmark RMST policy ratification must be a boolean")
    return {
        "kind": "benchmark-quantitative-margin-v1",
        "statistic": "RMST",
        "estimand": "restricted-mean-recovery-time-on-locked-grid",
        "units": "training-episodes",
        "difference": "reference-minus-treatment",
        "value": 1.5,
        "claim": "benchmark-quantitative-improvement",
        "practical_meaning_claimed": False,
        "equivalence_claimed": False,
        "zero_harm_claimed": False,
        "rationale": (
            "Retain the previously proposed 1.5 episode comparison margin before any "
            "scientific acquisition, without making the criterion easier after engineering "
            "runs. This is a declared benchmark target, not an independently validated "
            "minimum useful effect, cost-benefit threshold, or equivalence bound. "
            "Crossing it supports only the stated quantitative restricted-mean difference "
            "on the locked checkpoint grid; staying inside it is not practical equivalence. "
            "Its T-regime alias is a separate quantitative harm tolerance, not zero harm."
        ),
        "ratified": ratified,
    }


def validate_rmst_policy(policy):
    """Reject changed values, claim laundering and unratified proposals exactly."""
    expected = benchmark_rmst_policy(ratified=True)
    if (type(policy) is not dict or set(policy) != set(expected)
            or any(type(policy[k]) is not type(v) or policy[k] != v
                   for k, v in expected.items())):
        raise ProtocolError("benchmark RMST policy not ratified or inconsistent with its frozen scope")
    return dict(policy)


def _validate_interval(lower, upper):
    if (type(lower) not in (int, float) or type(upper) not in (int, float)
            or not math.isfinite(lower) or not math.isfinite(upper) or lower > upper):
        raise ProtocolError("RMST interval needs ordered finite numeric bounds")


def rmst_margin_decision(lower, upper, *, policy):
    """Classify a CI for reference minus treatment, without a practical-value claim.

This preserves the previous strict superiority and inclusive containment
boundaries. Companion endpoints, distribution diagnostics and joint gates are
not evaluated here and remain mandatory for a version-level finding.
    """
    margin = validate_rmst_policy(policy)["value"]
    _validate_interval(lower, upper)
    if lower > margin:
        return "MARGIN_A"
    if upper < -margin:
        return "MARGIN_B"
    if lower >= -margin and upper <= margin:
        return "WITHIN_BENCHMARK_MARGIN"
    return "INCONCLUSIVE"


def rmst_harm_bound_met(lower, upper, *, policy):
    """T's separate quantitative loss bound, not zero harm or practical safety.

    For reference minus treatment, L >= -margin bounds the possible worsening
    by the declared numerical tolerance. This condition is independent of the
    four-way P margin label and does not by itself satisfy any joint gate.
    """
    margin = validate_rmst_policy(policy)["value"]
    _validate_interval(lower, upper)
    return lower >= -margin
