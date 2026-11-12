"""A91 window boundaries, zero cases, real axis and censoring without run data."""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b2.convergence import convergence_time, select_horizon


def test_constant_window_is_qualified_once_at_its_last_checkpoint():
    assert convergence_time([.7, .7, .7], [0, 1, 2]) == 2
    assert convergence_time([.7, .7], [0, 1]) is None
    assert convergence_time([.7, .7, .7, .9], [0, 1, 2, 3]) == 2  # no future-stability rewrite


def test_nonconstant_zero_denominator_is_undefined_not_zero():
    assert convergence_time([0., 0., .0001], [0, 1, 2]) is None
    assert convergence_time([0., .0001, .0001], [0, 1, 2]) is None
    assert convergence_time([0., .0001, .0001, .0001], [0, 1, 2, 3]) == 3


def test_reversal_is_not_diluted_by_flat_increments():
    values = [0., .0001, 0., 0., 0., 0.]
    assert convergence_time(values, range(6), k=6) is None
    assert convergence_time([0., 1e-300, 0.], range(3)) is None  # product would underflow


def test_endpoint_slope_uses_real_episode_distance_and_strict_threshold():
    assert convergence_time([0., .1, .2], [0, 100, 200]) is None  # slope exactly .001
    assert convergence_time([0., .1, .2], [0, 100, 201]) == 201
    assert convergence_time([0., .1, .2], [0, 1, 2]) is None
    assert convergence_time([0., .0001, .0002], [0, 1, 2]) == 2
    assert convergence_time([0., .0001, 0.], [0, 1, 2], epsilon_f=1) is None


def test_censoring_keeps_original_n_and_rank_and_never_substitutes_cap():
    times = [10] * 29 + [None] * 3
    selected = select_horizon(times, acquisition_cap=576)
    assert selected == {"n": 32, "rank": 29, "uncensored": 29, "censored": 3,
                        "T": 12, "quantile": 10, "status": "ADMISSIBLE", "reason": None}
    assert select_horizon([10] * 28 + [None] * 4, acquisition_cap=576)["reason"] == "QUANTILE_UNIDENTIFIED"
    # Dropping censored runs first would move the rank to 27 and incorrectly choose 10.
    assert select_horizon([10] * 28 + [20] + [None] * 3, acquisition_cap=576)["T"] == 24


def test_horizon_ceiling_and_cap_failure_are_not_grid_failures():
    assert select_horizon([2] * 32, acquisition_cap=576)["T"] == 3
    result = select_horizon([481] * 32, acquisition_cap=576)
    assert result["status"] == "NO_ADMISSIBLE_T" and result["T"] is None
    assert result["reason"] == "HORIZON_EXCEEDS_CAP"
    assert select_horizon([480] * 32, acquisition_cap=576)["T"] == 576


@pytest.mark.parametrize("values,episodes,kwargs", [
    ([0., 0., 0.], [0, 0, 2], {}), ([0., 0.], [0, 1, 2], {}),
    ([0., float("nan"), 0.], [0, 1, 2], {}), ([0., 0., 0.], [0, 1, True], {}),
    ([0., 0., 0.], [0, 1, 2], {"epsilon_s": 0}),
    ([0., 0., 0.], [0, 1, 2], {"epsilon_f": 1.1}),
])
def test_invalid_curves_are_errors_not_censored_measurements(values, episodes, kwargs):
    with pytest.raises(ProtocolError):
        convergence_time(values, episodes, **kwargs)


@pytest.mark.parametrize("times", [[], [True], [1], [577]])
def test_invalid_convergence_samples_are_refused(times):
    with pytest.raises(ProtocolError):
        select_horizon(times, acquisition_cap=576)
