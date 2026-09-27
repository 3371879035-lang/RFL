"""Seedless counterexamples for claim scope; never select a real F1 design."""
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from rfl_rebuild.b2.baseline_artifact import canonical_bytes, digest
from rfl_rebuild.b2.convergence import convergence_time, select_horizon
from rfl_rebuild.b2.design_selection import select_grid, select_retention
from rfl_rebuild.b2.f0_stages import source_inventory
from rfl_rebuild.b2.utility import FutureUtility


def utility(curve, grid):
    return FutureUtility.from_curve([curve[e] for e in grid], grid, pre_level=1., t_max=grid[-1])


def audit():
    frozen = json.loads((ROOT / "experiments/v03r/f0_runtime/frozen_inputs.json").read_bytes())
    before = source_inventory(ROOT)
    assert before == frozen["sources"], "running benchmark instrument changed"
    checks = []
    def check(name, condition):
        assert condition, name
        checks.append(name)

    # A short plateau satisfies the specified first-window definition even if
    # recovery happens later. Copies are a synthetic fixture, not sampled seeds.
    plateau = [.5] * 10 + [1.] * 111
    conv = convergence_time(plateau, range(121))
    horizon = select_horizon([conv] * 32, acquisition_cap=120)
    recovery = utility(plateau, tuple(range(121)))
    early_grid = select_grid([plateau] * 32, horizon=horizon["T"], pre_level=1.)
    retention = select_retention([plateau] * 32, grid=early_grid["grid"], pre_level=1.)
    check("first_flat_window_ends_at_2", conv == 2)
    check("synthetic_horizon_is_3", horizon["T"] == 3)
    check("recovery_occurs_later_at_10", recovery.tau == 10)
    check("constant_early_retention_is_refused", retention["status"] == "NO_ADMISSIBLE_RETENTION")

    # A grid legitimately admitted under theta_G=0.05 can move the measured
    # restricted time by more than the proposed 1.5-episode practical threshold.
    step = [.5] * 15 + [1.] * 106
    selected = select_grid([step] * 32, horizon=120, pre_level=1.)
    full, reduced = utility(step, tuple(range(121))), utility(step, selected["grid"])
    error = abs(reduced.restricted_time - full.restricted_time)
    check("grid_is_admissible_by_current_rule", selected["status"] == "ADMISSIBLE")
    check("full_step_recovery_at_15", full.tau == 15)
    check("selected_grid_recovery_at_20", reduced.tau == 20)
    check("five_episode_error_exceeds_proposed_margin", error == 5 and error > 1.5)
    check("error_within_frozen_relative_tolerance", error / 120 <= .05)

    # The preceding tolerance is certified only on its input curves. A healthy
    # synthetic baseline does not certify a different trajectory's projection.
    healthy = [1.] * 121
    healthy_grid = select_grid([healthy] * 32, horizon=120, pre_level=1.)
    changed = [.5] * 21 + [1.] * 100
    other_full = utility(changed, tuple(range(121)))
    other_grid = utility(changed, healthy_grid["grid"])
    check("other_curve_recovers_on_full_axis", other_full.tau == 21)
    check("other_curve_censored_on_baseline_selected_grid", other_grid.tau is None)
    check("no_universal_curve_error_guarantee", other_grid.restricted_time - other_full.restricted_time == 99)

    check("instrument_unchanged", source_inventory(ROOT) == before)
    return {
        "status": "PASS_COUNTEREXAMPLES_REPRODUCED", "checks": checks,
        "data_role": "HAND_CONSTRUCTED_CURVES_ONLY", "formal_seed_draws": 0,
        "operational_or_development_curves_read": False, "f0_authorized": False,
        "scientific_design_selected": False,
        "instrument_commit": frozen["instrument_commit"],
        "sources_digest": digest(canonical_bytes(before)),
        "audit_script_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
        "early_plateau": {"convergence_time": conv, "synthetic_T": horizon["T"],
                          "full_recovery_time": recovery.tau, "retention_status": retention["status"]},
        "admitted_grid_distortion": {"grid": selected["grid"], "full_time": full.restricted_time,
                                     "grid_time": reduced.restricted_time, "absolute_error": error,
                                     "normalized_error": error / 120, "proposed_margin": 1.5},
        "input_population_boundary": {"baseline_selected_grid": healthy_grid["grid"],
                                      "other_full_time": other_full.restricted_time,
                                      "other_grid_time": other_grid.restricted_time,
                                      "other_grid_recovered": other_grid.recovered},
        "tolerance_scales": [{"T": t, "allowed_baseline_time_error": .05 * t,
                              "exceeds_1_5": .05 * t > 1.5} for t in (12, 20, 30, 40, 120, 500, 576)],
        "interpretation": "These are specification/claim-scope examples, not failures of implementation or estimates of C3 performance. No rule or threshold is changed."
    }


if __name__ == "__main__":
    result = audit()
    output = pathlib.Path(__file__).with_suffix(".json")
    with output.open("xb") as out:
        out.write(canonical_bytes(result))
    print(json.dumps(result, indent=2))
