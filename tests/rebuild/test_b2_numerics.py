r"""$F_0$ §4.0's authoritative spread, gated --- including the case that made it necessary."""

from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.b1.errors import ProtocolError  # noqa: E402
from rfl_rebuild.b2.acquisition import sufficient_error  # noqa: E402
from rfl_rebuild.b2.acquisition import Sufficient  # noqa: E402
from rfl_rebuild.b2.numerics import (  # noqa: E402
    is_constant,
    left_to_right_sum,
    mean,
    sd,
    standard_error,
    sufficient_statistics,
)

#: The same eight values the acquisition's bank produces, where CPython's compensated `sum()` and the
#: frozen left-to-right accumulation differ by an ulp.
VALUES = (0.9199999999999999, 0.88, 0.9, 0.84, 0.9199999999999999, 0.88, 0.9, 0.84)


def test_1_the_accumulation_is_left_to_right_and_differs_from_pythons_sum():
    total = 0.0
    for value in VALUES:
        total += value
    assert left_to_right_sum(VALUES) == total
    assert left_to_right_sum(VALUES) != sum(VALUES), (
        "CPython's sum() is Neumaier-compensated; §4.0 freezes the plain accumulation, so this "
        "difference is the rule and not a defect")
    assert left_to_right_sum(VALUES) / len(VALUES) != sum(VALUES) / len(VALUES)
    assert mean(VALUES) == total / len(VALUES)


def test_2_an_empty_set_has_no_mean_and_no_spread():
    for call in (lambda: mean(()), lambda: sd(()), lambda: is_constant(())):
        with pytest.raises(ProtocolError, match="no mean|no spread"):
            call()
    assert standard_error(()) is None, "empty is inadmissible, never zero"


def test_3_the_constant_case_is_closed_exactly_on_the_values():
    assert is_constant((0.7, 0.7)) is True
    assert is_constant((0.7, 0.7000000000000001)) is False
    assert sd((0.7, 0.7)) == 0.0
    assert sd((0.0, 0.0, 0.0)) == 0.0
    assert standard_error((0.7,)) == 0.0


def test_4_the_two_population_forms_disagree_exactly_where_it_matters():
    r"""The finding, kept as a gate: the value form returns $0$; the triple-expansion returns a residue.

    A set of **one** value has population spread exactly zero. §4.4's zero cases are exact comparisons on
    this quantity, so the residue would decide a branch --- which is why §4.0 makes the values authoritative
    and demotes the triple to a cache.
    """
    assert sd((0.7,)) == 0.0
    residue = sufficient_error(Sufficient(1, 0.7, 0.49))
    assert residue == pytest.approx(7.450580596923828e-09, rel=1e-3)
    assert residue != 0.0
    # the triple and the values agree everywhere the cancellation is not total
    levels = (0.1, 0.3)
    assert sufficient_statistics(levels) == (2, 0.4, pytest.approx(0.1))
    assert standard_error(levels) == pytest.approx((0.01 / 2) ** 0.5)


def test_5_sd_is_the_population_form():
    values = (0.0, 1.0, 2.0)
    centre = 1.0
    expected = (sum((v - centre) ** 2 for v in values) / 3) ** 0.5
    assert sd(values) == pytest.approx(expected)
    assert sd(values) != pytest.approx((sum((v - centre) ** 2 for v in values) / 2) ** 0.5)
    assert standard_error(values) == pytest.approx(expected / 3 ** 0.5)


def test_6_the_statistics_are_a_cache_and_use_the_frozen_accumulation():
    n, total, total_sq = sufficient_statistics(VALUES)
    assert n == len(VALUES)
    assert total == left_to_right_sum(VALUES) != sum(VALUES)
    assert total_sq == left_to_right_sum(v * v for v in VALUES)
