"""Synthetic selector fixtures only: never select a design from construction keys."""
import copy
import json
import pathlib
import sys
from collections import Counter
from types import MappingProxyType

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b2.acquisition import MasterBaseline, RunMaterial
from rfl_rebuild.b2.design_selection import (
    PrefixSelector, CollateralSelector, grid_templates, select_grid, select_retention,
    spearman, weighted_quantile, combine_design_and_thresholds, derive_design, require_calibration,
)
from rfl_rebuild.b2.design_lock import publish_new, prepare_inputs, run_lock, CONSTANTS
from rfl_rebuild.b2.evalorder import prefix
from rfl_rebuild.b2.numerics import mean, sd
from rfl_rebuild.b2.unaffected import CHANNELS, REFINEMENTS, credited_domain, CreditedSite
from rfl_rebuild.env.kernel import State, ControllerSite

CALIBRATION = json.loads((ROOT / "experiments/v03r/calibration_report.json").read_bytes())


def test_prefix_ranking_uses_smallest_admissible_and_worst_record():
    selector = PrefixSelector()
    selector.update([.5] * 1024)
    assert selector.result()["N"] == 100
    levels = [1.] * 300 + [0.] * 724
    selector.update(levels)  # one late checkpoint cannot be averaged away
    result = selector.result()
    expected = {n: abs(mean(levels[:n]) - mean(levels)) / sd(levels) for n in (100, 256, 512, 1024)}
    assert {row["N"]: row["metric"] for row in result["metrics"]} == expected
    assert result["N"] == min(n for n, metric in expected.items() if metric <= .25)


def test_prefix_constant_nonbinary_values_keep_the_frozen_zero_spread_rule():
    selector = PrefixSelector()
    selector.update([.7] * 1024)
    result = selector.result()
    for row in result["metrics"]:
        numerator = abs(mean([.7] * row["N"]) - mean([.7] * 1024))
        assert row["metric"] == (0.0 if numerator == 0 else None)
    assert result["N"] in (100, 256, 512, 1024)


def test_grid_tail_rounding_coarse_indices_and_small_horizon():
    coarse, medium, fine = grid_templates(1200)
    assert medium == (0, 1, 2, 5, 10, 20, 50, 100, 150, 200, 300, 500, 1000, 1200)
    assert coarse == (0,) + medium[1:-1:2] + (1200,)
    assert 3 in fine and 750 in fine and 1100 in fine
    assert all(g == (0, 1, 2) for g in grid_templates(2))


def test_grid_counts_censoring_and_does_not_average_a_bad_seed():
    constant = [1.] * 11
    good = select_grid([constant], horizon=10, pre_level=1.)
    assert good["grid"] == list(grid_templates(10)[0])
    delayed = [0.] * 8 + [1.] * 3  # full-grid tau=8; all three templates lose recovery
    result = select_grid([constant] * 31 + [delayed], horizon=10, pre_level=1.)
    assert result["status"] == "NO_ADMISSIBLE_GRID"
    assert all(c["metric"] >= .2 for c in result["candidates"])
    assert select_grid([[0.] * 11], horizon=10, pre_level=1.)["status"] == "ADMISSIBLE"


def synthetic_material(n=96, *, constant=False):
    # Deliberately small credited populations for a dense-vs-grouped numerical
    # proof, not a production artifact and not an acquired seed record.
    domains = {"D_Q": credited_domain("D_Q", None)[:5], "P": credited_domain("P", None),
               "X": (CreditedSite("X", ControllerSite(State(0, 2, 0, 0, 0), 3)),)}
    incidence = {a: {domain[0]: tuple(range(0, n, 4))} for a, domain in domains.items()}
    return RunMaterial(123, 0, tuple(.5 if constant else .4 + (i % 7) / 20 for i in range(n)),
                       tuple(i % 11 != 0 for i in range(n)), incidence, domains,
                       {a: len(incidence[a]) < len(domains[a]) for a in CHANNELS},
                       {a: 0 for a in CHANNELS})


def test_grouped_collateral_is_the_dense_site_population_including_coverage_and_quantile():
    run, sample = synthetic_material(), prefix(96)
    master = MasterBaseline((123,), (0,), sample, {(123, 0): run})
    selector = CollateralSelector(sample, calibration=CALIBRATION)
    selector.update(run)
    for r in REFINEMENTS:
        ratios, spreads = [], Counter()
        for arch in CHANNELS:
            histogram = Counter()
            for site in run.domains[arch]:
                indices = master.slice_indices(arch, 123, 0, site, r)
                base = master.slice_indices(arch, 123, 0, site, "eligible_all")
                numerator, denominator = master.error(arch, 123, 0, site, r), master.error(arch, 123, 0, site, "eligible_all")
                assert numerator is not None and denominator > 0
                ratios.append(numerator / denominator)
                spreads[sd(run.levels[i] for i in indices)] += 1
                histogram[len(base), len(indices)] += 1
            assert selector.coverage[arch, r] == histogram
        assert selector.metrics[r] == max(ratios)
        assert selector.spreads[r] == spreads
    result = selector.result()
    chosen = result["refinement"]
    expanded = sorted(v for v, count in selector.spreads[chosen].items() for _ in range(count))
    assert result["collateral_bound"] == expanded[(95 * len(expanded) + 99) // 100 - 1]
    assert result["spread_population"] == sum(len(d) for d in run.domains.values())


def test_collateral_zero_zero_is_one_but_all_zero_spread_has_no_threshold():
    selector = CollateralSelector(prefix(96), calibration=CALIBRATION)
    selector.update(synthetic_material(constant=True))
    result = selector.result()
    assert all(row["metric"] == 1 for row in result["metrics"])
    assert result["refinement"] == "eligible_all"  # frozen tie order
    assert result["collateral_bound"] is None


def test_empty_refinement_is_not_zero_error_or_a_coverage_floor():
    run = synthetic_material()
    # Only phase-even scenes can succeed. The odd refinement is undefined even
    # though the full pool is usable; there is no arbitrary minimum-size rule.
    sample = prefix(96)
    from dataclasses import replace
    run = replace(run, success=tuple(u.phase % 2 == 0 for u in sample))
    selector = CollateralSelector(sample, calibration=CALIBRATION)
    selector.update(run)
    assert selector.metrics["eligible_phase_odd"] is None
    assert selector.result()["refinement"] == "eligible_all"


def test_weighted_quantile_does_not_quantile_unique_groups():
    assert weighted_quantile({0.: 95, 1.: 5}) == 0.
    assert weighted_quantile({0.: 94, 1.: 6}) == 1.
    with pytest.raises(ProtocolError):
        weighted_quantile({0.: 0})


def test_calibration_requires_every_named_cell_and_actual_agreement():
    bad = copy.deepcopy(CALIBRATION)
    bad["cells"][0]["measured"] += .1
    with pytest.raises(ProtocolError):
        require_calibration(bad)
    bad = copy.deepcopy(CALIBRATION)
    bad["cells"][-1] = bad["cells"][0]
    with pytest.raises(ProtocolError):
        require_calibration(bad)


def test_spearman_uses_average_tied_ranks_and_rejects_constant_series():
    assert spearman([1, 1, 2, 3], [1, 2, 2, 3]) == pytest.approx(5 / 6)
    assert spearman([3, 2, 1], [1, 2, 3]) == pytest.approx(-1)
    assert spearman([1, 1, 1], [1, 2, 3]) is None


def retention_fixture():
    final = [1., .98, 1.01, .99, .99, 1.01, .98, 1.]
    return [[.4] * tau + [.97] * (8 - tau) + [end]
            for tau, end in zip([1, 2, 3, 4] * 2, final)]


def test_retention_uses_per_seed_endpoints_configured_horizons_and_tie_order():
    result = select_retention(retention_fixture(), grid=tuple(range(9)), pre_level=1.)
    assert result["status"] == "ADMISSIBLE"
    assert result["endpoint"]["form"] == "RetentionAtH"
    assert result["endpoint"]["parameters"] == {"H": 8}
    assert result["candidates"][1]["parameters"] == {"H1": 6, "H2": 8}


def test_retention_rejects_constant_restricted_time_even_with_variable_form_values():
    curves = [[1.] * 8 + [end] for end in (.99, 1., 1.01)]
    result = select_retention(curves, grid=tuple(range(9)), pre_level=1.)
    assert result["status"] == "NO_ADMISSIBLE_RETENTION"
    assert all(c["redundancy"] is None for c in result["candidates"])


def admissible_design_fixture():
    return {"status": "ADMISSIBLE", "f_T": {"T": 8}, "f_N": {"N": 100},
            "f_G": {"grid": list(range(9))},
            "f_C": {"refinement": "eligible_all", "collateral_bound": .02},
            "f_R": select_retention(retention_fixture(), grid=tuple(range(9)), pre_level=1.)}


def test_design_and_thresholds_are_indivisible_and_do_not_ratify_a_policy():
    design = admissible_design_fixture()
    assert combine_design_and_thresholds(design, rmst_policy={"value": 1.5})["lock"] is None
    policy = {"ratified": True, "value": 1.5, "rationale": "Synthetic unit-test policy only"}
    result = combine_design_and_thresholds(design, rmst_policy=policy)
    assert result["status"] == "LOCKABLE"
    registry = {(r["regime"], r["statistic"]): r for r in result["lock"]["thresholds"]}
    assert len(registry) == 6
    assert registry["T", "RMST"]["value"] == registry["P", "RMST"]["value"]
    assert registry["T", "RMST"]["provenance"] == "alias:P:RMST"
    assert registry["P", "Retention"]["value"] == .25 * sd(design["f_R"]["endpoint"]["values"])
    design["f_C"]["collateral_bound"] = None
    assert combine_design_and_thresholds(design, rmst_policy=policy)["lock"] is None


def test_composition_checks_the_entire_axis_before_computing_a_horizon(monkeypatch):
    import rfl_rebuild.b2.design_selection as module
    def forbidden(*args, **kwargs):
        raise AssertionError("incomplete input reached a horizon selector")
    monkeypatch.setattr(module, "convergence_time", forbidden)
    with pytest.raises(ProtocolError, match="missing master record"):
        derive_design([], seeds=(123,), cap=2, sample=prefix(1024), pre_level=1., calibration=CALIBRATION)


def test_atomic_publication_never_replaces_a_lock_or_leaves_partial_temp_files(tmp_path):
    path = tmp_path / "lock.json"
    publish_new(path, {"fixture_only": True, "both": ["design", "thresholds"]})
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        publish_new(path, {"changed": True})
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


def test_missing_or_invalid_f0_refuses_before_acquisition_or_output(tmp_path):
    output = tmp_path / "lock.json"
    with pytest.raises(ProtocolError, match="manifest absent"):
        run_lock(tmp_path, design_path=tmp_path / "absent.json", manifest_path=tmp_path / "f0.json",
                 output_path=output, plan_only=True)
    manifest = tmp_path / "f0.json"
    manifest.write_text(json.dumps({"schema": "f0-c3-design-v1", "status": "NOT_VALID",
                                    "currently_authorises": []}))
    with pytest.raises(ProtocolError, match="not authorized"):
        prepare_inputs(tmp_path, design_path=tmp_path / "absent.json", manifest_path=manifest)
    assert not output.exists()


def test_claiming_valid_without_a_ratified_threshold_cannot_reach_data(tmp_path):
    path = tmp_path / "f0.json"
    path.write_text(json.dumps({"schema": "f0-c3-design-v1", "status": "VALID",
        "currently_authorises": ["design_lock"], "constants": CONSTANTS,
        "rmst_policy": {"value": 1.5, "ratified": False}}))
    with pytest.raises(ProtocolError, match="not ratified"):
        prepare_inputs(tmp_path, design_path=tmp_path / "absent.json", manifest_path=path)


def matrix_fixture(cap=4):
    from dataclasses import replace
    base = synthetic_material(1024)
    return [replace(base, seed=seed, episode=e) for seed in (123, 124) for e in range(cap + 1)]


def test_complete_composition_keeps_undefined_retention_as_a_real_failure():
    result = derive_design(matrix_fixture(), seeds=(123, 124), cap=4, sample=prefix(1024),
                           pre_level=1., calibration=CALIBRATION)
    assert result["f_T"]["T"] == 3
    assert result["f_N"]["N"] == 100
    assert result["f_C"]["status"] == result["f_G"]["status"] == "ADMISSIBLE"
    assert result["status"] == "NO_ADMISSIBLE_RETENTION"


def test_grid_and_retention_read_master_means_even_when_n_selects_100(monkeypatch):
    import rfl_rebuild.b2.design_selection as module
    received = []
    def grid(curves, **kwargs):
        received.append(curves)
        return {"status": "ADMISSIBLE", "grid": [0, 1, 3]}
    def retention(curves, **kwargs):
        received.append(curves)
        return {"status": "NO_ADMISSIBLE_RETENTION"}
    monkeypatch.setattr(module, "select_grid", grid)
    monkeypatch.setattr(module, "select_retention", retention)
    records = matrix_fixture()
    result = derive_design(records, seeds=(123, 124), cap=4, sample=prefix(1024),
                           pre_level=1., calibration=CALIBRATION)
    assert result["f_N"]["N"] == 100
    assert mean(records[0].levels) != mean(records[0].levels[:100])
    assert received[0] == received[1] == [[mean(records[0].levels)] * 5] * 2


def test_f_n_still_reads_records_after_the_selected_horizon():
    from dataclasses import replace
    records = matrix_fixture()
    records[-1] = replace(records[-1], levels=tuple([1.] * 300 + [0.] * 724))
    result = derive_design(records, seeds=(123, 124), cap=4, sample=prefix(1024),
                           pre_level=1., calibration=CALIBRATION)
    assert result["f_T"]["T"] == 3
    assert result["f_N"]["N"] == 1024


def test_plan_mode_does_not_compute_a_design_or_solve_reference(monkeypatch, tmp_path):
    import rfl_rebuild.b2.design_lock as module
    monkeypatch.setattr(module, "prepare_inputs", lambda *a, **k: {
        "index_sha256": "test-fixture", "index": {"records": 18464}})
    def forbidden(*args, **kwargs):
        raise AssertionError("plan mode computed a design or reference")
    monkeypatch.setattr(module, "derive_design", forbidden)
    monkeypatch.setattr(module, "solve_reference", forbidden)
    result = module.run_lock(tmp_path, design_path=tmp_path / "data", manifest_path=tmp_path / "manifest",
                             output_path=tmp_path / "lock", plan_only=True)
    assert result["metrics_computed"] is False and result["written"] is False
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("drift", [False, True])
def test_combined_publication_rechecks_provenance_before_commit(monkeypatch, tmp_path, drift):
    import rfl_rebuild.b2.design_lock as module
    calls = []
    def inputs(*args, **kwargs):
        calls.append(True)
        return {"manifest": {"rmst_policy": {"ratified": True, "value": 1.5,
                  "rationale": "Synthetic test fixture; no experiment ratification"}},
                "index": {"seeds": [123], "ordered_shard_digest": "fixture-shards"},
                "index_sha256": "changed" if drift and len(calls) == 2 else "fixture-index",
                "manifest_sha256": "fixture-f0", "calibration": CALIBRATION}
    monkeypatch.setattr(module, "prepare_inputs", inputs)
    monkeypatch.setattr(module, "iter_verified_material", lambda *a: iter(()))
    monkeypatch.setattr(module, "derive_design", lambda *a, **k: admissible_design_fixture())
    path = tmp_path / "lock.json"
    kwargs = dict(design_path=tmp_path / "data", manifest_path=tmp_path / "manifest", output_path=path)
    if drift:
        with pytest.raises(ProtocolError, match="changed during"):
            module.run_lock(tmp_path, **kwargs)
        assert not path.exists()
    else:
        assert module.run_lock(tmp_path, **kwargs)["status"] == "LOCKED"
        payload = json.loads(path.read_bytes())
        assert len(payload["design"]["thresholds"]) == 6
        assert payload["baseline_index_sha256"] == "fixture-index"
    assert len(calls) == 2


def test_uncommitted_valid_claim_is_refused_before_opening_data(tmp_path):
    path = tmp_path / "f0.json"
    path.write_text(json.dumps({"schema": "f0-c3-design-v1", "status": "VALID",
        "currently_authorises": ["design_lock"], "constants": CONSTANTS,
        "rmst_policy": {"value": 1.5, "ratified": True, "rationale": "test fixture"}}))
    with pytest.raises(ProtocolError, match="must be committed"):
        prepare_inputs(tmp_path, design_path=tmp_path / "missing-data", manifest_path=path)


def test_committed_manifest_with_incomplete_source_inventory_is_refused(monkeypatch, tmp_path):
    import rfl_rebuild.b2.design_lock as module
    path = tmp_path / "f0.json"
    path.write_text(json.dumps({"schema": "f0-c3-design-v1", "status": "VALID",
        "currently_authorises": ["design_lock"], "constants": CONSTANTS,
        "rmst_policy": {"value": 1.5, "ratified": True, "rationale": "test fixture"}, "sources": {}}))
    monkeypatch.setattr(module.subprocess, "check_output", lambda *a, **k: path.read_bytes())
    with pytest.raises(ProtocolError, match="does not cover"):
        prepare_inputs(tmp_path, design_path=tmp_path / "missing-data", manifest_path=path)


def test_no_admissible_result_publishes_no_partial_lock(monkeypatch, tmp_path):
    import rfl_rebuild.b2.design_lock as module
    monkeypatch.setattr(module, "prepare_inputs", lambda *a, **k: {
        "manifest": {"rmst_policy": {}}, "index": {"seeds": [123]}, "calibration": CALIBRATION})
    monkeypatch.setattr(module, "iter_verified_material", lambda *a: iter(()))
    monkeypatch.setattr(module, "derive_design", lambda *a, **k: {"status": "NO_ADMISSIBLE_RETENTION"})
    path = tmp_path / "lock.json"
    result = module.run_lock(tmp_path, design_path=tmp_path / "data", manifest_path=tmp_path / "manifest",
                             output_path=path)
    assert result["status"] == "NO_ADMISSIBLE_RETENTION" and result["written"] is False
    assert not path.exists()
