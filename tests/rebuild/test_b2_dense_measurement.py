"""Prospective dense measurement laws; seedless fixtures, no old data or training."""
from fractions import Fraction
import copy
from pathlib import Path
import pytest
from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b2 import measurement_revision as m, protocol_profile as profile
from rfl_rebuild.b2 import design_selection as ds
from rfl_rebuild.b2.numerics import sd
from rfl_rebuild.b2.rmst_policy import benchmark_rmst_policy


@pytest.mark.parametrize("q", range(2, 481))
def test_fixed_witness_and_grid_for_every_legal_horizon(q):
    horizon = max((6 * q + 4) // 5, q + 2)
    grid = m.fixed_dense_grid(q, horizon)
    assert horizon <= 576 and grid == tuple(range(horizon + 1))
    assert set(m.late_anchors(q, horizon)) <= set(grid)
    for form in m.FORMS:
        witness = m.construct_witness(form, grid=grid, quantile=q, horizon=horizon)
        assert witness["valid"] and witness["exact_trapezoid_area_equal"]
        assert witness["same_restricted_time"] and witness["different_retention"]
    assert Fraction(1, 2 * (horizon - q + 1)) >= Fraction(1, 194)


@pytest.mark.parametrize("kind", ("flat", "never_recovered", "late_recovery", "collapse", "oscillatory"))
def test_dense_identity_is_outcome_independent_and_never_searches(kind, monkeypatch):
    def forbidden(*a, **kw):
        raise AssertionError("sparse template search reached fixed dense measurement")
    monkeypatch.setattr(ds, "grid_templates", forbidden)
    horizon, q = 12, 10
    if kind == "flat": curve = [1.] * 13
    elif kind == "never_recovered": curve = [0.] * 13
    elif kind == "late_recovery": curve = [0.] * 10 + [1.] * 3
    elif kind == "collapse": curve = [1.] * 10 + [0.] * 3
    else: curve = [float(i % 2) for i in range(13)]
    curves = [curve[:] for _ in range(32)]
    before = copy.deepcopy(curves)
    result = m.select_grid(curves, quantile=q, horizon=horizon, pre_level=1.)
    assert result["grid"] == list(range(13)) and result["status"] == "ADMISSIBLE"
    assert result["candidates"] == [{"template":"DENSE_FIXED_0_TO_T", "grid":list(range(13)),
                                      "metric":0., "admissible":True}]
    assert result["grid_error_role"] == "STRUCTURAL_DENSE_IDENTITY_NOT_TREATMENT_EFFICACY"
    assert curves == before and m.GRID_ERROR_LIMIT == .05


def test_sparse_grid_with_all_anchors_still_refused():
    with pytest.raises(ProtocolError, match="full integer"):
        m.construct_witness("RetentionAtH", grid=(0, 1, 10, 11, 12), quantile=10, horizon=12)
    with pytest.raises(ProtocolError, match="full integer"):
        m.select_retention([[1.] * 13] * 32, grid=(0, 1, 10, 11, 12),
                           quantile=10, horizon=12, pre_level=1.)


def test_retention_late_window_reads_every_absolute_episode_and_original_mean():
    q, horizon = 100, 120
    # Nonlinear, seedless fixture distinguishes every checkpoint from the three
    # anchors. Retention's frozen formula uses Python sum, not numerics.mean.
    curves = [[.8 + i / 10000 + e * e / 10000000 for e in range(horizon + 1)] for i in range(32)]
    result = m.select_retention(curves, grid=tuple(range(121)), quantile=q, horizon=horizon, pre_level=.8)
    late = result["candidates"][1]
    expected = tuple(sum(float(v) for v in c[q:horizon + 1]) / (horizon - q + 1) for c in curves)
    assert late["values"] == expected and late["margin"] == .25 * sd(expected)
    assert late["parameters"] == {"H1":100, "H2":120}
    anchors = m.late_anchors(q, horizon)
    assert expected[0] != sum(float(curves[0][e]) for e in anchors) / len(anchors)


def test_full_grid_preserves_three_adjacent_episode_recovery():
    utility = m.FutureUtility.from_curve([0.,0.,1.,1.,1.,0.,0.], tuple(range(7)), pre_level=1., t_max=6)
    assert utility.tau == 2 and utility.restricted_time == 2


def test_old_profile_and_manifest_identity_are_not_reused():
    assert m.MEASUREMENT_PROFILE == profile.MEASUREMENT_PROFILE == "v03r-a96-dense-measurement-v1"
    assert profile.STAGE_ROOT == "experiments/v03r/a96_dense"
    assert "a96" in profile.MANIFEST_SCHEMA and "a96" in profile.LOCK_SCHEMA
    assert set(profile.SPENT_SCIENTIFIC_SEEDS) >= set(range(2026100910, 2026100942))
    assert not set(profile.STAGE_SEEDS["dev_baseline"]) & set(profile.SPENT_SCIENTIFIC_SEEDS)


def test_atomic_composition_refuses_a_sparse_grid_under_current_profile():
    from tests.rebuild.test_b2_design_selection import admissible_design_fixture
    design = admissible_design_fixture()
    design["f_G"]["grid"] = [0, 1, 6, 7, 8]
    with pytest.raises(ProtocolError, match="full integer"):
        ds.combine_design_and_thresholds(design, rmst_policy=benchmark_rmst_policy(ratified=True))


def test_registration_and_parent_snapshot_are_in_instrument():
    from rfl_rebuild.b2.f0_stages import source_inventory, read_json
    root = Path(__file__).resolve().parents[2]
    inventory = source_inventory(root)
    for name in ("pipeline/preregistration.json", "pipeline/parent_snapshot.json"):
        assert profile.STAGE_ROOT + "/" + name in inventory
    contract = read_json(root / "docs/rebuild/a96_dense_measurement_contract.json")
    assert contract["approval"]["human_reply"] == "继续完成" and contract["approval"]["ratified"]
    assert contract["unchanged"]["grid_error_limit"] == .05
    assert contract["unchanged"]["acquisition_cap"] == 576
    assert contract["unchanged"]["retention_stability_limit"] == .1
    assert not contract["scientific_execution_authorized"]
