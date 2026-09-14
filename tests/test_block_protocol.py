"""Tests for the frozen seed-block protocol.

Covers ``scripts/robustness_audit.py`` and ``scripts/block_analysis.py``, which
implement ``docs/SEED_BLOCK_PROTOCOL.md``. The protocol exists because the
project's earlier practice — re-running with more seeds whenever the conclusion
moved — is optional stopping, and because per-seed paired deltas here are
zero-inflated and heavy-tailed, which makes a bare mean uninterpretable.

The tests below fix the two things that are easy to get silently wrong:

1. the **four-way decision rule** boundaries (``SUPPORT_A`` / ``EQUIVALENT`` /
   ``SUPPORT_B`` / ``INCONCLUSIVE``), including the closed-interval edges; and
2. the **block decomposition identity** — the claim printed next to each
   cumulative look, that a fresh block's own mean is recoverable as
   ``mean_prev + k * (mean_N - mean_prev)``. If that formula drifts, the
   headline diagnostic of the whole protocol silently lies.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import block_analysis as ba  # noqa: E402
import robustness_audit as ra  # noqa: E402


# --------------------------------------------------------------------------- #
# four-way decision rule
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "lo, hi, expected",
    [
        # Strictly above the threshold: a real positive effect.
        (+0.0101, +0.0300, "SUPPORT_A"),
        # Strictly below: a real negative effect.
        (-0.0300, -0.0101, "SUPPORT_B"),
        # Entirely inside the equivalence band.
        (-0.0090, +0.0090, "EQUIVALENT"),
        (-0.0100, +0.0100, "EQUIVALENT"),      # closed interval edge
        (+0.0000, +0.0100, "EQUIVALENT"),      # touching the edge from inside
        (-0.0100, +0.0000, "EQUIVALENT"),
        # Spans a boundary: not a finding.
        (-0.0020, +0.0220, "INCONCLUSIVE"),
        (-0.0220, +0.0020, "INCONCLUSIVE"),
        (-0.0300, +0.0300, "INCONCLUSIVE"),
        (-0.0050, +0.0101, "INCONCLUSIVE"),    # crosses out of the band, upward
        (-0.0101, +0.0050, "INCONCLUSIVE"),    # crosses out of the band, downward
    ],
)
def test_decide_four_way(lo, hi, expected):
    assert ba.decide(lo, hi) == expected


def test_decide_uses_preregistered_delta_min():
    """Delta_min is frozen at 0.01; it must not be silently larger."""
    assert ba.DELTA_MIN == 0.01
    # An effect that is significant but negligible must read EQUIVALENT, not
    # SUPPORT_A -- this is the exact misreading the protocol was written to stop.
    assert ba.decide(+0.0020, +0.0040) == "EQUIVALENT"


def test_a_p_value_crossing_is_not_a_decision_change():
    """The motivating case: a CI tightening must not flip the verdict."""
    wide = ba.decide(-0.0040, +0.0220)     # "p = 0.04"
    tight = ba.decide(-0.0020, +0.0140)    # "p = 0.07"
    assert wide == tight == "INCONCLUSIVE"


# --------------------------------------------------------------------------- #
# block decomposition identity
# --------------------------------------------------------------------------- #

def test_block_decomposition_identity_is_exact():
    """mean_N = ((k-1)*mean_prev + new) / k, solved for `new`.

    This is the identity the report prints as "B{k} alone"; verify it against a
    brute-force recomputation on synthetic blocks with distinct means.
    """
    blocks = {
        1: [0.10, -0.02, 0.00, 0.04],
        2: [-0.06, -0.10, 0.02, -0.02],
        3: [0.30, 0.10, 0.20, 0.00],
    }
    for k in (2, 3):
        prev = [x for b in range(1, k) for x in blocks[b]]
        cur = prev + blocks[k]
        mean_prev = sum(prev) / len(prev)
        mean_cur = sum(cur) / len(cur)
        implied = mean_prev + k * (mean_cur - mean_prev)
        assert implied == pytest.approx(sum(blocks[k]) / len(blocks[k]))


def test_block_decomposition_detects_reversal_not_shrinkage():
    """The two cases the protocol must tell apart.

    A cumulative drop from +0.04 to +0.01 is a *reversal* if the second block
    came in on the opposite side of zero, and mere *variance shrinkage* if it
    came in near zero but on the same side.
    """
    def new_block_mean(prev: list[float], cur: list[float]) -> float:
        mean_prev = sum(prev) / len(prev)
        mean_cur = sum(cur) / len(cur)
        k = len(cur) // len(prev)
        return mean_prev + k * (mean_cur - mean_prev)

    b1 = [+0.04] * 50

    # Reversal: B2 lands negative, opposite side of zero from B1.
    reversal = new_block_mean(b1, b1 + [-0.02] * 50)
    assert reversal == pytest.approx(-0.02)
    assert (reversal > 0) != (b1[0] > 0)

    # Shrinkage: B2 lands on zero -- the pooled mean still falls, but nothing
    # reversed, so this must NOT be reported as a reversal.
    shrinkage = new_block_mean(b1, b1 + [0.0] * 50)
    assert shrinkage == pytest.approx(0.0)
    assert not (shrinkage < 0 < b1[0])

    # And a B2 that stays positive but smaller is also not a reversal.
    damped = new_block_mean(b1, b1 + [+0.01] * 50)
    assert damped == pytest.approx(+0.01)
    assert not (damped < 0 < b1[0])


def test_analyse_contrast_blocks_are_disjoint_and_ordered():
    deltas = [(i, float(i % 7) - 3.0) for i in range(400)]
    import numpy as np

    res = ba.analyse_contrast("synthetic", deltas, np.random.default_rng(0))
    assert [b["block"] for b in res["blocks"]] == [1, 2, 3, 4]
    assert [b["n"] for b in res["blocks"]] == [100, 100, 100, 100]
    assert [lk["n"] for lk in res["looks"]] == [100, 200, 300, 400]
    # Cumulative pooling must equal the pooled mean of the first k blocks.
    pooled_2 = [d for _, d in deltas[:200]]
    assert res["looks"][1]["mean"] == pytest.approx(sum(pooled_2) / 200)


# --------------------------------------------------------------------------- #
# robustness statistics
# --------------------------------------------------------------------------- #

def test_contrast_stats_flags_zero_inflated_tail_driven_mean():
    """v0.3 Alpha's real shape: 70% ties, and the movers cancel in sign.

    The mean is positive only because a few movers are large, so this must be
    flagged as tail-driven rather than reported as an effect.
    """
    deltas = [0.0] * 70
    deltas += [0.070, 0.058, 0.043, 0.041, 0.040]      # five big positives
    deltas += [-0.001] * 25                             # many tiny negatives
    s = ra.contrast_stats(deltas)
    assert s["ties"] == 70
    assert s["median"] == 0.0
    assert s["mean"] > 0
    assert "TAIL-DRIVEN" in ra.verdict(s)


def test_contrast_stats_calls_a_genuine_effect_robust():
    deltas = [-0.09 + 0.001 * (i % 5) for i in range(200)]
    s = ra.contrast_stats(deltas)
    assert s["ties"] == 0
    assert "ROBUST" in ra.verdict(s)


def test_contrast_stats_handles_all_ties():
    s = ra.contrast_stats([0.0] * 50)
    assert s["ties"] == 50
    assert "IDENTICAL" in ra.verdict(s)


def test_holm_is_monotone_and_bounded():
    raw = [0.001, 0.02, 0.04, 0.30]
    adj = ra.holm(raw)
    assert all(0.0 <= a <= 1.0 for a in adj)
    # Ordering of the adjusted values must follow the ordering of the raw ones.
    by_raw = [a for _, a in sorted(zip(raw, adj))]
    assert by_raw == sorted(by_raw)
    assert adj[3] == pytest.approx(min(1.0, raw[3]))
