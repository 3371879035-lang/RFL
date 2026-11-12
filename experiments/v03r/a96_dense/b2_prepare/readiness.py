"""Source-isolated B2 preparation. This module has NO acquisition entry point.

The frozen 313-file parent remains unchanged. Parent F0/F1 authorize no B2
collection. Reference construction is seedless on Q*, not a treatment curve.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b1.contract import fingerprint
from rfl_rebuild.b2.baseline_artifact import canonical_bytes, digest
from rfl_rebuild.b2.environment import learned_rollout
from rfl_rebuild.b2.evalorder import prefix, prefix_digest
from rfl_rebuild.b2.f0_stages import load_manifest, source_inventory
from rfl_rebuild.b2.numerics import mean
from rfl_rebuild.learner.reference import reference_view_from
from rfl_rebuild.learner.store import LearnerPersistentState
from rfl_rebuild.solve.dp import solve_reference

FOLDER = Path("experiments/v03r/a96_dense")
PROFILE = "v03r-a96-dense-measurement-v1"
REFERENCE_SCHEMA = "a96-b2-seedless-locked-bank-reference-v1"
REFERENCE_KEYS = {"schema", "role", "status", "measurement_profile", "lock_sha256",
                  "parent_sources_digest", "q_reference_sha256", "N_eval",
                  "evaluation_sample_sha256", "ordered_healthy_scene_levels", "v_pre",
                  "f1_master_design_v_pre", "master_design_reference_is_not_B2_reference_authorization",
                  "seed_draws", "training_episodes", "treatment_collected",
                  "confirmatory_collected", "collection_authorized"}
ENDPOINTS = {("P", "RMST"), ("P", "DeficitAUC"),
             ("P", "BehavioralCollateral"), ("P", "Retention"),
             ("T", "RMST"), ("T", "DeficitAUC")}


def require(ok, message):
    if not ok:
        raise ProtocolError(message)


def read_json(path):
    return json.loads(Path(path).read_bytes())


def file_hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_design(lock):
    require(type(lock) is dict and lock.get("status") == "LOCKED" and
            lock.get("schema") == "f1-a96-dense-design-threshold-v1", "not an A96 full lock")
    d = lock["design"]
    t, q, n = d["T"], d["healthy_settling_quantile"], d["N_eval"]
    require(type(t) is int and type(q) is int and 2 <= q < t <= 576,
            "invalid locked integer horizon")
    require(t == max((6 * q + 4) // 5, q + 2), "A95 horizon law differs")
    require(d["measurement_profile"] == PROFILE and type(n) is int and
            n in (100, 256, 512, 1024), "locked profile or evaluation bank differs")
    require(type(d["grid"]) is list and all(type(x) is int for x in d["grid"]) and
            d["grid"] == list(range(t + 1)), "not the fixed complete integer grid")
    require(d["late_anchors"] == [q, q + (t - q) // 2, t] and
            all(type(x) is int for x in d["late_anchors"]), "late anchors differ")
    require(d["refinement"] in ("eligible_all", "eligible_phase_even", "eligible_phase_odd",
            "eligible_cause_rank_lower", "eligible_error_absent", "eligible_base_option_nonzero"),
            "unknown locked collateral refinement")
    r = d["retention"]
    require(r in ({"form": "RetentionAtH", "parameters": {"H": t}},
                  {"form": "LateWindowRetention", "parameters": {"H1": q, "H2": t}})
            and all(type(x) is int for x in r["parameters"].values()),
            "Retention parameters are not F1-derived")
    rows = d["thresholds"]
    require(len(rows) == 6 and {(x["regime"], x["statistic"]) for x in rows} == ENDPOINTS,
            "missing, duplicate or pooled endpoint identity")
    registry = {(x["regime"], x["statistic"]): x for x in rows}
    for x in rows:
        require(type(x["value"]) in (int, float) and math.isfinite(x["value"]) and
                x["value"] > 0, "invalid positive endpoint margin")
    for regime in ("P", "T"):
        require(registry[regime, "RMST"]["value"] == 1.5 and
                registry[regime, "DeficitAUC"]["value"] == .01,
                "fixed quantitative margins differ")
    p, h = registry["P", "RMST"], registry["T", "RMST"]
    require(p["claim"] == "benchmark-quantitative-improvement" and
            p["practical_meaning_claimed"] is False and p["equivalence_claimed"] is False,
            "unsupported RMST practical claim")
    require(h["criterion"] == "lower-ci-bound>=-margin" and h["bound_inclusive"] is True
            and h["zero_harm_claimed"] is False and h["practical_meaning_claimed"] is False,
            "T constraint cannot be inferred from the margin label")
    return d


def load_parent(root=ROOT):
    """Read proofs/bytes only; never rerun validation, selectors or scientific seeds."""
    root = Path(root).resolve()
    audit = read_json(root / FOLDER / "pipeline/full_f1_complete_external_audit.json")
    manifest, mh = load_manifest(root, root / FOLDER / "f0_manifest.json", "design_lock")
    sources = source_inventory(root)
    require(len(sources) == 313 and sources == manifest["sources"] and
            digest(canonical_bytes(sources)) == audit["audit"]["sources_digest"],
            "frozen parent source inventory changed")
    # Fixed proofs and the closed native tail must still match the audited bytes.
    hashes = dict(audit["audit"]["fixed_native_file_hashes"])
    hashes.update(audit["audit"]["post_controller_commit_native_tail_hashes"])
    for name, expected in hashes.items():
        path = (root / name).resolve()
        require(path.is_relative_to(root) and file_hash(path) == expected,
                f"parent native binding changed: {name}")
    lock_path = root / FOLDER / "dev_lock.json"
    lock = read_json(lock_path)
    require(digest(lock_path.read_bytes()) == audit["audit"]["atomic_lock_sha256"] and
            lock["f0_manifest_sha256"] == mh, "lock/manifest binding differs")
    committed = subprocess.check_output(["git", "show", f"HEAD:{FOLDER.as_posix()}/dev_lock.json"],
                                        cwd=root)
    require(committed == lock_path.read_bytes(), "F1 must match committed bytes")
    d = validate_design(lock)
    require(audit["native_F1_receipt"]["native_exit_code"] == 0 and
            audit["native_controller_exit"]["native_exit_code"] == 0 and
            audit["outcome"]["scientific_treatment_or_confirmation_collected"] is False,
            "native completed F1 evidence is missing")
    return {"root": root, "lock": lock, "design": d, "sources": sources,
            "manifest_sha256": mh, "lock_sha256": file_hash(lock_path),
            "sources_digest": digest(canonical_bytes(sources))}


def build_reference(parent):
    """One seedless healthy reference for the LOCKED bank, not the master bank.

    Production will inject its committed result once for both arms. Construction
    retains ordered scene values for the original left-to-right mean cross-check.
    No C3 corruption, future training, diagnostic method or scientific seed runs.
    """
    d = validate_design(parent["lock"])
    require(source_inventory(parent["root"]) == parent["sources"], "parent source drift")
    sample = prefix(d["N_eval"])
    reference = reference_view_from(solve_reference())
    healthy = LearnerPersistentState()
    before = fingerprint(healthy)
    values = [learned_rollout(healthy, kappa=u.kappa, tape=u.tape,
                             base_option=u.base_option, q_reference=reference).return_value
              for u in sample]
    require(fingerprint(healthy) == before, "reference evaluation mutated healthy state")
    require(source_inventory(parent["root"]) == parent["sources"], "parent source drift")
    return {"schema": REFERENCE_SCHEMA, "role": "SEEDLESS_Q_STAR_REFERENCE_NOT_TREATMENT_DATA",
            "status": "PREPARED_NOT_COLLECTION_AUTHORIZATION", "measurement_profile": PROFILE,
            "lock_sha256": parent["lock_sha256"], "parent_sources_digest": parent["sources_digest"],
            "q_reference_sha256": reference.digest(), "N_eval": len(sample),
            "evaluation_sample_sha256": prefix_digest(len(sample)),
            "ordered_healthy_scene_levels": values, "v_pre": mean(values),
            "f1_master_design_v_pre": parent["lock"]["v_pre"],
            "master_design_reference_is_not_B2_reference_authorization": True,
            "seed_draws": 0, "training_episodes": 0, "treatment_collected": False,
            "confirmatory_collected": False, "collection_authorized": False}


def validate_reference(payload, parent):
    d = validate_design(parent["lock"])
    require(type(payload) is dict and set(payload) == REFERENCE_KEYS, "reference field set differs")
    require(payload["schema"] == REFERENCE_SCHEMA and payload["measurement_profile"] == PROFILE
            and payload["lock_sha256"] == parent["lock_sha256"] and
            payload["parent_sources_digest"] == parent["sources_digest"], "reference parent differs")
    require(payload["role"] == "SEEDLESS_Q_STAR_REFERENCE_NOT_TREATMENT_DATA" and
            payload["status"] == "PREPARED_NOT_COLLECTION_AUTHORIZATION" and
            type(payload["q_reference_sha256"]) is str and len(payload["q_reference_sha256"]) == 64
            and all(c in "0123456789abcdef" for c in payload["q_reference_sha256"]),
            "invalid nominal-reference identity")
    require(type(payload["N_eval"]) is int and payload["N_eval"] == d["N_eval"] and
            payload["evaluation_sample_sha256"] == prefix_digest(d["N_eval"]),
            "reference scenes do not match locked future measurement bank")
    values = payload["ordered_healthy_scene_levels"]
    require(type(values) is list and len(values) == d["N_eval"] and
            all(type(x) is float and math.isfinite(x) for x in values), "invalid scene values")
    require(type(payload["v_pre"]) is float and payload["v_pre"] == mean(values),
            "reference mean arithmetic differs")
    require(type(payload["seed_draws"]) is type(payload["training_episodes"]) is int and
            payload["seed_draws"] == payload["training_episodes"] == 0 and
            payload["treatment_collected"] is False and payload["confirmatory_collected"] is False
            and payload["collection_authorized"] is False and
            payload["master_design_reference_is_not_B2_reference_authorization"] is True,
            "preparation claimed acquisition authority")
    return payload["v_pre"]


def readiness(parent):
    """A preparation checklist, never a collection-gate implementation or PASS."""
    return {"status": "F1_AUDITED_B2_PREPARATION_ONLY", "collection_authorized": False,
            "research_complete": False, "parent_sources_digest": parent["sources_digest"],
            "lock_sha256": parent["lock_sha256"],
            "required_before_collection": ["frozen_contrast_population_and_seed_registry",
                "frozen_B2_addon_code_test_analysis_inventory", "complete_B2_integration_gates",
                "source_bound_internal_review", "full_dense_B2_workload_resource_certification",
                "committed_B2_manifest_and_single_use_collection_gate"],
            "baseline_engineering_timing_is_B2_workload_certification": False}


if __name__ == "__main__":
    # Only two read/construction modes. There is intentionally no --collect flag.
    require(sys.argv[1:] in ([], ["--build-reference"]), "unknown preparation mode")
    parent = load_parent()
    result = build_reference(parent) if sys.argv[1:] else readiness(parent)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
