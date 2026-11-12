"""Post-exit artifact audit and bounded descriptive query, NOT a native F1 receipt.

No acquisition, training, design search, gate mutation, or retry. Read only the
already-collected episodes 0..6 for the mechanism check. Full-stream validity
comes from the authenticated original pass receipts, not this bounded query.
The only writes are exclusive new closure artifacts in this separate folder.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OP = ROOT / "experiments/v03r/f1_parallel_design_20261008"
sys.path.insert(0, str(OP))
import control_parallel_design as control
from rfl_rebuild.b2 import design_lock as dl
from rfl_rebuild.b2.design_selection import spearman
from rfl_rebuild.b2.retention import RetentionAtH, LateWindowRetention
from rfl_rebuild.b2.utility import FutureUtility


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha(value):
    return dl.digest(dl.canonical_bytes(value))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def publish(name, value):
    with (HERE / name).open("x", encoding="utf-8", newline="\n") as out:
        out.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n")


def main():
    require(not (HERE / "closure_audit.json").exists(), "closure audit already exists; no overwrite")
    identity = control.context()
    require(identity == read(OP / "pipeline_claim.json")["binding"], "source/control binding drift")
    review = read(OP / "source_bound_parallel_design_review.json")
    require(review["binding"] == identity and review["decision"] == "VALID", "review drift")
    counts = control.check_tests(OP / "wrapper_checks.xml")
    require(counts == {"tests": 109, "errors": 0, "failures": 0, "skipped": 0}, "fresh wrapper counts")
    result = read(OP / "pipeline_result.json")
    execution = read(OP / "f1_execution.json")
    attestation = read(OP / "f1_execution_attestation.json")
    native = read(OP / "design_lock.receipt.json")
    exit_receipt = read(OP / "pipeline_exit.json")
    require(result["status"] == "VALID_PROTOCOL_STOP_NO_ADMISSIBLE_DESIGN", "not valid protocol stop")
    require(native["native_exit_code"] == exit_receipt["native_exit_code"] == execution["native_result_code"] == 3,
            "native scientific-stop code mismatch")
    require(exit_receipt["start_utc_ticks"] == "639270661004126546", "controller native identity mismatch")
    require(result["execution_sha256"] == attestation["execution_sha256"] == sha(OP / "f1_execution.json"),
            "execution SHA mismatch")
    require(execution["result"] == result["f1_result"] == attestation["f1_result"], "result mismatch")
    require(execution["binding"] == attestation["binding"] == result["binding"] == identity, "final binding mismatch")
    require(result["f1_result"]["status"] == "NO_ADMISSIBLE_RETENTION" and result["f1_result"]["written"] is False,
            "stop subtype or no-write mismatch")
    require(not (ROOT / "experiments/v03r/dev_lock.json").exists(), "a partial/final lock exists")
    require(not (OP / "pipeline_failure.json").exists(), "operation failure coexists")
    for name in ("source_bound_parallel_design_review.json", "wrapper_checks.xml", "wrapper_checks.receipt.json",
                 "f1_execution_attestation.json", "f1_execution.json", "design_lock.receipt.json", "parallel_design/completed.json"):
        control.require_committed(OP / name)

    index = read(control.INDEX)
    index_sha = sha(control.INDEX)
    require(index["seeds"] == list(range(1000, 1032)) and index["episodes"] == list(range(577))
            and index["bank_size"] == 1024 and index["records"] == 18464 and index["pairs"] == 241339812,
            "development population mismatch")
    compressed = {s["path"]: sha(control.INDEX.parent / s["path"]) for s in index["shards"]}
    descriptor_by_seed = {s["seed"]: s for s in index["shards"]}
    pass_audits = []
    require(read(OP / "plan_execution.json")["full_validation_passes"] == 1 and execution["full_validation_passes"] == 2,
            "negative F1 must have one separate plan pass and two F1 full passes")
    for folder, expected in (("plan_validation", 1), ("f1_validation", 2)):
        dirs = sorted((OP / folder).iterdir())
        require(len(dirs) == expected, "full-pass folder count mismatch")
        for d in dirs:
            done, reservation = read(d / "completed.json"), read(d / "reservation.json")
            require(done["status"] == "ALL_SHARDS_VERIFIED" and done["records"] == 18464
                    and done["pairs"] == 241339812 and done["index_sha256"] == index_sha
                    and done["compressed_sha256"] == compressed and done["validation_reduced"] is False
                    and done["scientific_metrics_computed"] is False and done["max_workers"] == 16
                    and done["start_method"] == "spawn" and reservation["validation_cache"] is False,
                    "invalid full-pass completion")
            leaves = sorted((d / "workers").glob("*.verified.json"))
            require(len(leaves) == len(done["shards"]) == 32, "missing worker completion")
            by_seed = {x["seed"]: x for x in done["shards"]}
            require(set(by_seed) == set(index["seeds"]), "full-pass seed set mismatch")
            for path in leaves:
                leaf = read(path)
                desc = descriptor_by_seed[leaf["seed"]]
                require(leaf == by_seed[leaf["seed"]] and leaf["records"] == desc["records"] == 577
                        and leaf["pairs"] == desc["pairs"] and leaf["sha256"] == desc["sha256"]
                        and leaf["validator"] == "frozen-_shard_records", "leaf full-pass binding mismatch")
            pass_audits.append({"path": d.relative_to(ROOT).as_posix(), "completed_sha256": sha(d / "completed.json"),
                                "workers": 32, "records": 18464, "pairs": 241339812, "elapsed_s": done["elapsed_s"]})

    design = read(OP / "parallel_design/completed.json")
    diagnostics = result["f1_result"]["diagnostics"]
    require(design["status"] == "ALL_SEEDS_CALCULATED_ORDERED_JOIN_COMPLETE" and design["seeds"] == index["seeds"]
            and design["records"] == 18464 and design["pairs"] == 241339812
            and design["index_sha256"] == index_sha and design["compressed_sha256"] == compressed
            and design["design_result_sha256"] == canonical_sha(diagnostics)
            and design["join_order"] == "frozen-seed-order" and design["floating_moment_reduction"] is False
            and design["partial_lock_published"] is False and design["max_workers"] == 16
            and design["start_method"] == "spawn", "design completion binding mismatch")
    require(len(design["workers"]) == len(list((OP / "parallel_design").glob("seed-*.completed.json"))) == 32,
            "missing design leaf")
    require([w["seed"] for w in design["workers"]] == index["seeds"], "ordered worker join mismatch")
    for leaf in design["workers"]:
        desc = descriptor_by_seed[leaf["seed"]]
        require(read(OP / f"parallel_design/seed-{leaf['seed']}.completed.json") == leaf
                and leaf["records"] == desc["records"] == 577 and leaf["pairs"] == desc["pairs"]
                and leaf["uncompressed_shard_sha256"] == desc["sha256"], "design leaf mismatch")
    preserved = read(OP / "parent_preservation.json")["files"]
    require(all(sha(ROOT / path) == expected for path, expected in preserved.items()), "parent preservation drift")

    # Bounded descriptive re-read, not a new full validation or design search.
    require(diagnostics["f_T"]["T"] == 6 and diagnostics["f_G"]["grid"] == [0, 1, 5, 6], "frozen diagnostic coordinates")
    curves = []
    for desc in index["shards"]:
        curve = []
        with gzip.open(control.INDEX.parent / desc["path"], "rt", encoding="utf-8") as stream:
            for episode in range(7):
                row = json.loads(next(stream))
                require(row["seed"] == desc["seed"] and row["episode"] == episode and len(row["levels"]) == 1024,
                        "descriptive prefix coordinate mismatch")
                curve.append(dl.mean(row["levels"]))
        curves.append(curve)
    reference = dl.reference_view_from(dl.solve_reference())
    sample, healthy = dl.prefix(1024), dl.LearnerPersistentState()
    pre_level = dl.mean(tuple(dl.learned_rollout(healthy, kappa=u.kappa, tape=u.tape, base_option=u.base_option,
                                               q_reference=reference).return_value for u in sample))
    grid = diagnostics["f_G"]["grid"]
    utilities = [FutureUtility.from_curve([c[e] for e in grid], grid, pre_level=pre_level, t_max=6) for c in curves]
    rt, auc = [u.restricted_time for u in utilities], [u.deficit_auc for u in utilities]
    endpoint_checks = []
    for candidate in diagnostics["f_R"]["candidates"]:
        form = RetentionAtH if candidate["form"] == "RetentionAtH" else LateWindowRetention
        values = [form.value([c[e] for e in grid], grid, **candidate["parameters"]) for c in curves]
        require(values == candidate["values"], "descriptive endpoint differs from native result")
        stability = (max(values) - min(values)) / (max(abs(v) for v in values) + 1e-9)
        correlations = {"restricted_time": spearman(values, rt), "deficit_auc": spearman(values, auc)}
        redundancy = None if None in correlations.values() else max(abs(v) for v in correlations.values())
        require(stability == candidate["stability"] and redundancy == candidate["redundancy"], "diagnostic mismatch")
        endpoint_checks.append({"form": candidate["form"], "parameters": candidate["parameters"],
                                "stability": stability, "correlations": correlations, "redundancy": redundancy,
                                "admissible": candidate["admissible"]})
    mechanism = {"role": "POST_EXIT_DESCRIPTIVE_MECHANISM_QUERY_NOT_NEW_ACQUISITION_OR_FULL_VALIDATION",
                 "index_sha256": index_sha, "seeds": index["seeds"], "episodes_read_per_seed": list(range(7)),
                 "records_read": 224, "frozen_selected_grid_diagnostic_not_published_lock": grid,
                 "healthy_reference_pre_level": pre_level, "recovery_threshold": 0.95 * pre_level,
                 "curves_0_to_6": curves, "restricted_time": rt, "deficit_auc": auc,
                 "recovered_count_within_grid": sum(u.recovered for u in utilities),
                 "restricted_time_unique_values": sorted(set(rt)), "deficit_auc_unique_count": len(set(auc)),
                 "retention_checks": endpoint_checks,
                 "source_functions": ["design_lock.run_lock healthy reference calculation", "numerics.mean",
                                      "FutureUtility.from_curve", "RetentionAtH.value", "LateWindowRetention.value", "spearman"]}

    power_folder = ROOT / "experiments/v03r/power_mode_20261008"
    lease, restored = read(power_folder / "lease.json"), read(power_folder / "restored.json")
    require(sha(power_folder / "manage_power_mode.ps1") == lease["script_sha256"], "power helper drift")
    power_query = subprocess.run([control.PWSH, "-NoProfile", "-NonInteractive", "-File",
                                 str(power_folder / "manage_power_mode.ps1"), "-Mode", "Status"],
                                capture_output=True, check=True, encoding="utf-8")
    current_power = json.loads(power_query.stdout)
    require(all(restored["after"][key] == current_power[key] == lease["original"][key] for key in ("ac", "dc")),
            "temporary power configuration not restored")
    require(control.context() == identity and sha(control.INDEX) == index_sha and compressed ==
            {s["path"]: sha(control.INDEX.parent / s["path"]) for s in index["shards"]}, "post-audit input/source drift")
    evidence_files = [p for p in OP.rglob("*") if p.is_file()]
    for name in ("lease.json", "applied.json", "restored.json", "manage_power_mode.ps1"):
        evidence_files.append(power_folder / name)
    audit = {"schema": "rfl-f1-valid-stop-closure-audit-v1", "role": "POST_EXIT_AUDIT_NOT_NATIVE_CONTROLLER_RECEIPT",
             "status": "PASS", "observed_at": datetime.now(timezone.utc).isoformat(),
             "original_and_analysis_binding": identity, "f1_status": "NO_ADMISSIBLE_RETENTION",
             "native_f1_exit_code": 3, "native_controller_exit_code": 3,
             "full_validation_passes": pass_audits, "design_records": 18464, "design_pairs": 241339812,
             "design_workers_complete": 32, "design_elapsed_s": design["elapsed_s"],
             "native_f1_receipt": native, "native_controller_exit_receipt": exit_receipt,
             "internal_review_only": True, "fresh_wrapper_tests": counts,
             "native_evidence_commit": result["evidence_commit"], "parent_preserved_files": len(preserved),
             "parent_preservation_current_sha_verified": True, "dev_lock_exists": False,
             "treatment_or_confirmatory_authorized": False, "research_efficacy_test_completed": False,
             "descriptive_prefix_query_records": 224, "power_current_readback": current_power,
             "power_restoration_native_receipt": restored,
             "evidence_files_sha256": {p.relative_to(ROOT).as_posix(): sha(p) for p in evidence_files}}
    publish("mechanism_diagnostics.json", mechanism)
    publish("closure_audit.json", audit)
    print(json.dumps({"audit": "PASS", "native_status": audit["f1_status"], "full_passes": len(pass_audits),
                      "design_workers": 32, "records": 18464, "pairs": 241339812,
                      "pre_level": pre_level, "restricted_time_unique": sorted(set(rt)),
                      "recovered": mechanism["recovered_count_within_grid"], "retention": endpoint_checks,
                      "power_restored": True}, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
