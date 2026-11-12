"""Deterministic construction tests. No random seed or training run is used."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import measurement_prototype as p


def curves(level=.8, cap=12):
    return [tuple(level + i / 10000 for _ in range(cap + 1)) for i in range(32)]


def test_imports_are_bound_to_new_worktree():
    assert Path(p.FutureUtility.__module__.replace(".", "/")).name == "utility"
    import rfl_rebuild.b2.utility as u
    assert Path(u.__file__).resolve().is_relative_to(p.ROOT / "src")


def test_late_healthy_plateau_replaces_early_low_flat_window():
    values = (.4,) * 4 + (.6,) + (.8,) * 8
    assert p.healthy_settling_time(values, range(13), pre_level=.8) == 7
    result = p.select_horizon([values] * 32, pre_level=.8, acquisition_cap=12)
    assert result["quantile"] == 7 and result["T"] == 9
    assert result["late_anchors"] == [7, 8, 9]
    assert result["scientific_execution_authorized"] is False


def test_forever_low_is_not_healthy_settling():
    assert p.healthy_settling_time((.5,) * 13, range(13), pre_level=1) is None


def test_health_then_late_collapse_is_not_settled():
    values = (.8,) * 8 + (.3,) * 5
    assert p.healthy_settling_time(values, range(13), pre_level=.8) is None


def test_late_change_is_observed_not_ignored_after_first_plateau():
    values = (.8,) * 8 + (.9,) * 8
    assert p.healthy_settling_time(values, range(16), pre_level=.8) == 10


def test_last_window_without_followup_is_censored():
    values = (.4,) * 10 + (.8,) * 3
    assert p.healthy_settling_time(values, range(13), pre_level=.8) is None


def test_healthy_threshold_is_inclusive_but_not_relaxed():
    assert p.healthy_settling_time((.95,) * 7, range(7), pre_level=1) == 2
    assert p.healthy_settling_time((.95 - 1e-6,) * 7, range(7), pre_level=1) is None


def test_nonconstant_flat_window_with_undefined_flip_is_not_imputed():
    assert p._flat((.8, .8, .80000001)) is False


def test_reversing_zero_net_slope_is_not_flat():
    assert p._flat((.8, .81, .8)) is False


def test_k_minus_one_followup_requirement_is_exact():
    values = (.4,) * 3 + (.8,) * 5
    assert p.healthy_settling_time(values, range(8), pre_level=.8) == 5


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf"), True, "0.8"])
def test_bad_curve_value_is_invalid_not_censored(bad):
    values = [.8] * 7
    values[1] = bad
    with pytest.raises(p.ProtocolError):
        p.healthy_settling_time(values, range(7), pre_level=.8)


@pytest.mark.parametrize("bad", [0, -1, True, float("nan"), float("inf"), "1"])
def test_bad_reference_is_rejected(bad):
    with pytest.raises(p.ProtocolError):
        p.healthy_settling_time((.8,) * 7, range(7), pre_level=bad)


@pytest.mark.parametrize("axis", [(0, 1, 2, 3, 4, 5), (1, 2, 3, 4, 5, 6, 7),
                                  (0, 1, 2, 3, 4, 4, 6), (0, 1, 2, 3, 4, 6, 5),
                                  (0, True, 2, 3, 4, 5, 6)])
def test_missing_or_malformed_axis_is_invalid(axis):
    with pytest.raises(p.ProtocolError):
        p.healthy_settling_time((.8,) * 7, axis, pre_level=.8)


@pytest.mark.parametrize("cap", [0, 3, True, 4.5])
def test_invalid_cap_is_not_auto_extended(cap):
    with pytest.raises(p.ProtocolError):
        p.select_horizon(curves(), pre_level=.8, acquisition_cap=cap)


def test_all_32_seeds_are_required():
    with pytest.raises(p.ProtocolError):
        p.select_horizon(curves()[:-1], pre_level=.8, acquisition_cap=12)


def test_extra_seed_is_refused():
    with pytest.raises(p.ProtocolError):
        p.select_horizon(curves() + [(.8,) * 13], pre_level=.8, acquisition_cap=12)


def test_missing_late_record_is_invalid_not_a_seed_to_drop():
    material = curves()
    material[-1] = material[-1][:-1]
    with pytest.raises(p.ProtocolError):
        p.select_horizon(material, pre_level=.8, acquisition_cap=12)


@pytest.mark.parametrize("censored,admissible", [(0, True), (3, True), (4, False), (32, False)])
def test_original_nearest_rank_denominator_preserves_censoring(censored, admissible):
    material = curves()
    for i in range(censored):
        material[i] = (.4,) * 13
    result = p.select_horizon(material, pre_level=.8, acquisition_cap=12)
    assert result["n"] == 32 and result["rank"] == 29 and result["censored"] == censored
    assert (result["T"] is not None) == admissible


def test_t_above_original_cap_stops_instead_of_increasing_cap():
    values = (.4,) * 6 + (.8,) * 5  # end=8, but proposed T=10; cap=10, so legal.
    allowed = p.select_horizon([values] * 32, pre_level=.8, acquisition_cap=10)
    assert allowed["T"] == 10
    values = (.4,) * 7 + (.8,) * 5  # end=9 gives T=11; cap=11.
    assert p.select_horizon([values] * 32, pre_level=.8, acquisition_cap=11)["T"] == 11
    values = (.4,) * 10 + (.8,) * 5  # end=12 gives T=15; cap=14.
    result = p.select_horizon([values] * 32, pre_level=.8, acquisition_cap=14)
    assert result["T"] is None and result["reason"] == "HORIZON_EXCEEDS_UNCHANGED_CAP"


@pytest.mark.parametrize("q", [2, 3, 4, 5, 7, 9, 25, 100, 400])
def test_anchor_template_and_construct_witness_for_each_form(q):
    horizon = max((6 * q + 4) // 5, q + 2)
    anchors = p.late_anchors(q, horizon)
    assert len(set(anchors)) == 3 and anchors[0] == q and anchors[-1] == horizon
    for template in p.grid_templates(horizon):
        grid = tuple(sorted(set(template) | set(anchors)))
        for form in p.FORMS:
            result = p.construct_witness(form, grid=grid, quantile=q, horizon=horizon)
            assert result["valid"] and result["exact_trapezoid_area_equal"]
            assert result["same_grid_deficit_auc_within_roundoff"]


@pytest.mark.parametrize("q,horizon", [(1, 3), (2, 3), (3, 6), (True, 4), (2, 4.0)])
def test_noncontract_horizon_cannot_be_injected(q, horizon):
    with pytest.raises(p.ProtocolError):
        p.late_anchors(q, horizon)


def test_grid_union_is_shared_and_keeps_error_limit_and_tie_order():
    material = curves(cap=12)
    before = copy.deepcopy(material)
    result = p.select_grid(material, quantile=2, horizon=4, pre_level=.8)
    assert len(result["candidates"]) == 3
    for candidate in result["candidates"]:
        assert {2, 3, 4}.issubset(candidate["grid"])
        assert candidate["metric"] == 0
    assert result["grid"] == [0, 1, 2, 3, 4]
    assert material == before


def test_late_corruption_is_refused_even_outside_selected_horizon():
    material = curves(cap=12)
    material[-1] = tuple(material[-1][:-1]) + (float("nan"),)
    with pytest.raises(p.ProtocolError):
        p.select_grid(material, quantile=2, horizon=4, pre_level=.8)


def test_undefined_correlation_stays_null_and_is_not_a_gate_pass_migration():
    result = p.select_retention(curves(), grid=(0, 1, 2, 3, 4), quantile=2, horizon=4, pre_level=.8)
    assert result["endpoint"] is not None
    # A checkpoint mean can differ from the last value by an ulp even on a
    # constant curve. Exact original left-to-right arithmetic is authoritative;
    # do not impose an approximate tie or force the desired candidate.
    expected = min(enumerate(result["candidates"]), key=lambda pair: (pair[1]["stability"], pair[0]))[1]
    assert result["endpoint"] == expected
    for candidate in result["candidates"]:
        assert candidate["diagnostic_spearman_restricted_time"] is None
        assert candidate["diagnostic_spearman_deficit_auc"] is None
        assert candidate["construct_witness"]["valid"]
        assert candidate["margin"] > 0
    assert result["scientific_execution_authorized"] is False


def test_constant_healthy_retention_still_has_no_positive_threshold():
    result = p.select_retention([(.8,) * 13] * 32, grid=(0, 1, 2, 3, 4),
                                quantile=2, horizon=4, pre_level=.8)
    assert result["endpoint"] is None
    for candidate in result["candidates"]:
        assert candidate["margin"] == 0
        assert candidate["stability"] == 0
        assert "ZERO_RETENTION_SPREAD_NO_THRESHOLD" in candidate["reasons"]


def test_instability_gate_not_relaxed():
    material = [(1.,) * 13] * 31 + [(.2,) * 13]
    result = p.select_retention(material, grid=(0, 1, 2, 3, 4), quantile=2, horizon=4, pre_level=.8)
    assert result["endpoint"] is None
    assert all("STABILITY_EXCEEDS_UNCHANGED_0.10" in c["reasons"] for c in result["candidates"])


def test_margin_is_original_population_sd_in_endpoint_units():
    result = p.select_retention(curves(), grid=(0, 1, 2, 3, 4), quantile=2, horizon=4, pre_level=.8)
    for candidate in result["candidates"]:
        assert candidate["margin"] == .25 * p.sd(candidate["values"])


def test_missing_anchor_is_refused():
    with pytest.raises(p.ProtocolError):
        p.select_retention(curves(), grid=(0, 1, 2, 4), quantile=2, horizon=4, pre_level=.8)


def test_duplicate_or_wrong_grid_is_refused():
    with pytest.raises(p.ProtocolError):
        p.select_retention(curves(), grid=(0, 1, 2, 3, 3, 4), quantile=2, horizon=4, pre_level=.8)


def test_late_window_is_absolute_and_not_per_seed_recovery_conditioned():
    result = p.select_retention(curves(), grid=(0, 1, 2, 3, 4), quantile=2, horizon=4, pre_level=.8)
    assert result["candidates"][1]["parameters"] == {"H1": 2, "H2": 4}


def test_unknown_or_conditional_form_is_refused():
    with pytest.raises(p.ProtocolError):
        p.construct_witness("RetentionFraction", grid=(0, 1, 2, 3, 4), quantile=2, horizon=4)


def test_no_new_locks_training_or_authorization_exist():
    with pytest.raises(p.ProtocolError, match="DRAFT_PROTOTYPE"):
        p.require_scientific_execution_authorization()
    contract = json.loads((HERE / "contract.json").read_text(encoding="utf-8"))
    assert contract["ratified"] is False and contract["scientific_execution_authorized"] is False
    assert contract["production_dispatch_changed"] is False and contract["scientific_seed_sets"] is None
    assert not (p.ROOT / "experiments/v03r/dev_lock.json").exists()
    assert contract["unchanged"]["acquisition_cap"] == 576


def test_original_production_selectors_are_not_monkeypatched():
    import rfl_rebuild.b2.design_selection as original
    import rfl_rebuild.b2.convergence as convergence
    assert original.select_retention is not p.select_retention
    assert original.select_grid is not p.select_grid
    assert original.convergence_time is convergence.convergence_time
    assert original.select_horizon is convergence.select_horizon
