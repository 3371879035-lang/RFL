r"""$F_0$ §3's balanced evaluation ordering, gated.

$$\boxed{\text{every admissible } N:\ \text{prefix}(N) \text{ covers } \kappa, \phi, \texttt{error\_flag},
z_{\text{base}} \text{ and all } 60 \text{ cause ranks}}$$

The point of these tests is that the balance claim is **verified, not asserted**: `coverage` recomputes it
from the order itself, so a change to either stride fails here rather than at $F_1$.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from collections import Counter  # noqa: E402

from rfl_rebuild.b1.errors import ProtocolError  # noqa: E402
from rfl_rebuild.b2.evalorder import (  # noqa: E402
    CAUSE_STRIDE,
    CELL_STRIDE,
    balanced_units,
    coverage,
    prefix,
    prefix_digest,
)
from rfl_rebuild.b2.unaffected import TAPE_CAUSE_SUPPORT, scene_domain  # noqa: E402

CANDIDATES = (100, 256, 512, 1024, 2048, 4096, 5760)
FROZEN_DIGEST_1024 = "f9ac07213237dbdb"   # the value F0's pre-data verification recorded


def test_1_the_balanced_order_is_a_bijection_onto_u2():
    units = balanced_units()
    assert len(units) == 5760
    assert len(set(units)) == 5760
    assert set(units) == set(scene_domain())
    assert (CAUSE_STRIDE, CELL_STRIDE) == (7, 37)   # both as frozen, both coprime with 60


def test_2_the_two_strides_are_the_arithmetic_the_spec_writes_down():
    units = balanced_units()
    for n in (0, 1, 37, 95, 96, 97, 959, 5760 - 1):
        q, r = divmod(n, 96)
        assert units[n].cause_rank == (CAUSE_STRIDE * q + CELL_STRIDE * r) % len(TAPE_CAUSE_SUPPORT)
        assert units[n].cause_rank == (7 * q + 37 * r) % 60
    # coprime with the 60-cause support: that is what makes the rotation a permutation
    for stride in (CAUSE_STRIDE, CELL_STRIDE):
        assert all(stride % p for p in (2, 3, 5))


def test_3_every_cell_carries_each_cause_exactly_once_over_its_visits():
    """The order factorises: 96 cells round-robin, the cause rotating inside each of them."""
    units = balanced_units()
    per_cell = {}
    for unit in units:
        cell = (unit.kappa, unit.phase, unit.error_flag, unit.base_option)
        per_cell.setdefault(cell, []).append(unit.cause_rank)
    assert len(per_cell) == 96
    for cell, causes in per_cell.items():
        assert len(causes) == 60, cell
        assert sorted(causes) == sorted(TAPE_CAUSE_SUPPORT), cell
    assert Counter(u.cause_rank for u in units) == Counter({c: 96 for c in TAPE_CAUSE_SUPPORT})


def test_4_every_admissible_prefix_covers_the_strata():
    for n in CANDIDATES:
        counts = coverage(n)
        assert counts["kappa"] == 2 and counts["phase"] == 6, counts
        assert counts["error_flag"] == 2 and counts["base_option"] == 4, counts
        assert counts["cause_rank"] == 60, counts
        assert counts["distinct"] == n, counts


def test_5_canonical_lexicographic_enumeration_would_not_be_balanced():
    """The reason §3 orders the bank at all: a measured deficiency of the naive prefix.

    `scene_domain()` stays A88 §76.2's canonical order (the two enumerations are deliberately different
    objects); the counts below are the frozen record of *why* the evaluation bank is not its prefix.
    """
    canonical = scene_domain()
    naive = coverage(1024, units=canonical)
    assert (naive["kappa"], naive["phase"]) == (1, 3), naive   # kappa 1 and phase 3 only
    assert (naive["error_flag"], naive["cause_rank"], naive["base_option"]) == (2, 60, 4), naive
    balanced = coverage(1024)
    assert (balanced["kappa"], balanced["phase"]) == (2, 6), balanced
    assert [balanced[k] for k in ("error_flag", "cause_rank", "base_option")] == [2, 60, 4]
    assert repr(tuple(u.key for u in prefix(1024))) != repr(
        tuple(u.key for u in prefix(1024, units=canonical)))
    # and the canonical order does cover everything once it is complete: the gap is the prefix, not the set
    assert coverage(5760, units=canonical) == coverage(5760)


def test_6_a_prefix_is_nested_bounded_and_taken_from_the_given_order():
    assert prefix(100) == prefix(256)[:100]
    assert len(prefix(5760)) == 5760
    for bad in (0, 5761, -1):
        with pytest.raises(ProtocolError, match="outside"):
            prefix(bad)
    supplied = tuple(reversed(balanced_units()))
    assert prefix(3, units=supplied) == supplied[:3]
    with pytest.raises(ProtocolError, match="outside"):
        prefix(5761, units=supplied)


def test_7_the_digest_pins_the_order_it_was_frozen_with():
    assert prefix_digest(1024)[:16] == FROZEN_DIGEST_1024
    assert prefix_digest(1024) == prefix_digest(1024)
    assert prefix_digest(1024) != prefix_digest(512)
    # two orders holding the same *set* still digest differently, so a re-ordering is visible
    assert prefix_digest(1024) != prefix_digest(1024, units=tuple(reversed(balanced_units())))
    assert prefix_digest(2048, units=scene_domain()) == prefix_digest(2048, units=scene_domain())
