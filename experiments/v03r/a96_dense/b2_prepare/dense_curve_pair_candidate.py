"""Complete nominal dense curve pair -> original metric preparation.

This is NOT a trainer, collection gate, or acquisition-origin authenticator.
Both supplied Curve objects may be constructed by engineering fixtures. Their
shape, exact reference, complete raw values and recalculated metrics are useful
for a later owner-executed collector, but do not certify that it ever ran.
No seed, scene/cell identity, protocol, scalar-only result or receipt is accepted.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import math
from pathlib import Path

import readiness as ready
import native_record_candidate as bridge
from rfl_rebuild.b2 import training, utility, retention

_PARENT = ready.load_parent()
_REFERENCE_PATH = ready.ROOT / ready.FOLDER / "b2_prepare/healthy_reference_candidate.json"
_LOCK_PATH = ready.ROOT / ready.FOLDER / "dev_lock.json"
_REFERENCE = ready.read_json(_REFERENCE_PATH)
_REFERENCE_SHA = bridge.sha(_REFERENCE)
_PARENT_BINDING = (_PARENT["sources_digest"], _PARENT["lock_sha256"])
_CODE_PATHS = tuple(Path(m.__file__) for m in (ready, bridge, training, utility, retention)) + (
    Path(__file__), _REFERENCE_PATH, _LOCK_PATH)
_CODE_BINDING = tuple(sha256(p.read_bytes()).hexdigest() for p in _CODE_PATHS)
_ROLES = ("reference", "treatment")


def _guard():
    ready.require((_PARENT["sources_digest"], _PARENT["lock_sha256"]) == _PARENT_BINDING,
                  "loaded parent identity changed")
    ready.require(tuple(sha256(p.read_bytes()).hexdigest() for p in _CODE_PATHS) == _CODE_BINDING,
                  "dense-curve/dependency/reference/lock bytes changed after loading")
    ready.require(sha256(_LOCK_PATH.read_bytes()).hexdigest() == _PARENT["lock_sha256"],
                  "current committed lock byte binding differs")
    ready.require(bridge.sha(ready.read_json(_LOCK_PATH)) == bridge.sha(_PARENT["lock"]),
                  "loaded lock payload changed")
    ready.require(bridge.sha(_REFERENCE) == _REFERENCE_SHA,
                  "once-shared healthy reference payload changed")
    d = ready.validate_design(_PARENT["lock"])
    v_pre = ready.validate_reference(_REFERENCE, _PARENT)
    return d, v_pre


def _curve_payload(curve, d, v_pre):
    ready.require(type(curve) is training.Curve,
                  "nominal native Curve required, never scalar-only/recorder/receipt input")
    ready.require(type(curve.t_max) is int and curve.t_max == d["T"] and
                  type(curve.episodes) is tuple and
                  all(type(e) is int for e in curve.episodes) and
                  curve.episodes == tuple(d["grid"]) == tuple(range(d["T"] + 1)),
                  "complete fixed integer episode axis required, not prefix/sparse/cap/aliases")
    ready.require(type(curve.values) is tuple and len(curve.values) == d["T"] + 1 and
                  all(type(v) is float and math.isfinite(v) for v in curve.values),
                  "every native ordered mean level must be a finite float")
    ready.require(type(curve.pre_level) is float and math.isfinite(curve.pre_level) and
                  curve.pre_level.hex() == v_pre.hex(),
                  "exact once-shared B2 healthy reference required, not own episode0/F1 master")
    return {"episodes": list(curve.episodes),
            "levels_hex": [v.hex() for v in curve.values],
            "T": curve.t_max, "pre_level_hex": curve.pre_level.hex()}


def _metrics(curve, d, v_pre):
    # Delegate to the unchanged original formulas. No streaming moment,
    # re-sorted values, floating tolerance, interpolation, conditional Retention,
    # or independently remeasured per-arm reference replaces these calls.
    future = utility.FutureUtility.from_curve(curve.values, curve.episodes,
                                              pre_level=v_pre, t_max=d["T"])
    retained = retention.select_form(d["retention"]["form"])(
        curve.values, curve.episodes, **d["retention"]["parameters"])
    ready.require(type(future) is utility.FutureUtility and type(future.recovered) is bool and
                  type(future.t_max) is int and future.t_max == d["T"] and
                  type(future.restricted_time) is int and
                  type(future.deficit_auc) is float and math.isfinite(future.deficit_auc) and
                  future.deficit_auc >= 0 and
                  (future.tau is None or
                   (type(future.tau) is int and 0 <= future.tau <= d["T"] - utility.K_RECOVERY + 1)) and
                  future.recovered == (future.tau is not None) and
                  future.restricted_time == (d["T"] if future.tau is None else future.tau),
                  "invalid native Utility result or lost censoring semantics")
    ready.require(type(retained) is float and math.isfinite(retained),
                  "non-finite native Retention result refused, never imputed")
    return {"restricted_time": future.restricted_time,
            "restricted_time_role": "PER_CURVE_NOT_CROSS_SEED_RMST",
            "tau": future.tau, "recovered": future.recovered,
            "DeficitAUC": future.deficit_auc, "DeficitAUC_hex": future.deficit_auc.hex(),
            "Retention": retained, "Retention_hex": retained.hex()}


def inspect_dense_pair(reference_curve, treatment_curve):
    """Inspect full nominal curves; output is not an owned execution receipt.

    Explicit argument roles, not sorting by measured benefit or completion order.
    Each curve retains all466 level hex values and the full locked axis. Original
    Utility and all-seed Retention are recalculated from exactly those arguments.
    No acquired-seed count, statistical sample, diagnosis, collateral, native
    record or collection authorization can be inferred from this result.
    """
    d, v_pre = _guard()
    ready.require(reference_curve is not treatment_curve,
                  "two distinct nominal role curves required, even if contents tie")
    curves = (reference_curve, treatment_curve)
    before = tuple(_curve_payload(c, d, v_pre) for c in curves)
    raw = {"ordered_roles": list(_ROLES), "ordered_curves": list(before),
           "lock_sha256": _PARENT["lock_sha256"],
           "parent_sources_digest": _PARENT["sources_digest"],
           "healthy_reference_file_sha256": sha256(_REFERENCE_PATH.read_bytes()).hexdigest(),
           "healthy_reference_payload_sha256": _REFERENCE_SHA,
           "evaluation_sample_sha256": _REFERENCE["evaluation_sample_sha256"],
           "N_eval": d["N_eval"]}
    results = [_metrics(c, d, v_pre) for c in curves]
    d_after, v_after = _guard()
    ready.require(d_after == d and v_after.hex() == v_pre.hex() and
                  tuple(_curve_payload(c, d_after, v_after) for c in curves) == before,
                  "nominal input changed during original metric calculation")
    payload = {"complete_raw_pair": raw,
               "raw_pair_payload_sha256": bridge.sha(raw),
               "ordered_metrics": [{"role": role, **result}
                                   for role, result in zip(_ROLES, results)],
               "retention_design": deepcopy(d["retention"]),
               "recovery_window_training_episodes": utility.K_RECOVERY,
               "recovery_fraction": utility.RECOVERY_FRACTION}
    return deepcopy({"schema": "a96-complete-dense-curve-pair-candidate-v13",
        "role": "NOMINAL_RAW_CURVE_METRIC_PREPARATION_NOT_AUTHENTICATED_EXECUTION",
        "input_payload": payload, "input_payload_sha256": bridge.sha(payload),
        "complete_raw_level_count": sum(len(c.values) for c in curves),
        "original_utility_retention_recomputed": True,
        "actual_keyed_curve_origin_authenticated": False,
        "collateral_or_native_record_authenticated": False,
        "new_training_or_rollout_executed": False,
        "population_seed_registry_and_collection_gate_authenticated": False,
        "full_dense_B2_workload_resources_certified": False,
        "collection_authorized": False, "scientific_claim_authorized": False,
        "research_complete": False})


def dense_pair_workload_shape():
    """Prospective operation counts only, NOT measured time/cost/resource proof.

    Original train_curve evaluates W_e at e=0..T, and performs ordinary
    training only for e=0..T-1. Each bank traversal keeps the original ordered
    N_eval scenes. These counts cover one reflected pair's future paths only;
    pre/factual/CF/U2/B1/maps/diagnosis/reporting overhead is not included.
    """
    d, _ = _guard()
    return {"role": "PROSPECTIVE_COUNTS_NOT_RUNTIME_OR_RESOURCE_CERTIFICATION",
            "paired_roles": list(_ROLES), "training_episode_indices": list(range(d["T"])),
            "evaluation_episode_indices": list(d["grid"]),
            "ordinary_training_episodes_per_arm": d["T"],
            "ordinary_training_episodes_per_pair": 2 * d["T"],
            "evaluation_checkpoints_per_arm": len(d["grid"]),
            "ordered_scene_rollouts_per_checkpoint": d["N_eval"],
            "evaluation_scene_rollouts_per_arm": len(d["grid"]) * d["N_eval"],
            "evaluation_scene_rollouts_per_pair": 2 * len(d["grid"]) * d["N_eval"],
            "excluded_overhead": ["pre-state", "factual", "counterfactual", "U2_incidence",
                                 "diagnosis", "B1", "collateral_maps", "reporting"],
            "environment_seed_allocated": False, "actual_training_executed": False,
            "wall_time_or_memory_measured": False, "workload_resources_certified": False,
            "collection_authorized": False, "research_complete": False}

