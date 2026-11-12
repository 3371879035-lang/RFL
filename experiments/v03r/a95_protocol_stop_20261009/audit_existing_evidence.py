"""Read-only closure audit. Never runs gates, acquisition, selectors or publication."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from rfl_rebuild.b2.baseline_artifact import canonical_bytes, digest, read_index
from rfl_rebuild.b2.f0_stages import (
    source_inventory, _committed_sources, read_json, load_manifest, require_smoke,
    MANIFEST_PATH, SMOKE_PATH, STAGE_SEEDS, ENGINEERING_KEYS,
)

STAGE = ROOT / "experiments/v03r/a95_measurement"
OP = STAGE / "pipeline"
EXPECTED_SOURCE_DIGEST = "4d8a4bc3a0afc2c0335decafa559af44e2cd9028ccd3c4776189fc8c11dffd79"
NATIVE_COMMIT = "2dd3afc5b10a8ffa30a9c122ca40502abbf2477a"
CHECKS = []
HASHES = {}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)
    CHECKS.append(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    path = Path(path)
    HASHES[path.relative_to(ROOT).as_posix()] = sha(path)
    return read_json(path)


def git_bytes(revision, path):
    return subprocess.check_output(["git", "show", f"{revision}:{path}"], cwd=ROOT)


def regression(folder):
    path = folder / "regression.xml"
    HASHES[path.relative_to(ROOT).as_posix()] = sha(path)
    doc = ET.parse(path)
    suites = list(doc.iter("testsuite"))
    counts = {k: sum(int(s.get(k, "0")) for s in suites)
              for k in ("tests", "failures", "errors", "skipped")}
    skips = [{"classname": c.get("classname"), "name": c.get("name")}
             for c in doc.iter("testcase") if c.find("skipped") is not None]
    require(counts == {"tests": 1120, "failures": 0, "errors": 0, "skipped": 1},
            f"{folder.relative_to(ROOT)}: complete regression counts")
    require(skips == [{"classname": "tests.rebuild.test_b2_acquisition",
                       "name": "test_12_a_site_no_episode_consults_shares_the_generic_value[P]"}],
            f"{folder.relative_to(ROOT)}: only the existing explicit skip")
    receipts = [read(folder / f"gate-{n:02d}.receipt.json") for n in range(1, 7)]
    require(all(r["native_exit_code"] == 0 and r["receipt_origin"] == "native_subprocess_wait"
                for r in receipts), f"{folder.relative_to(ROOT)}: six native-zero gates")
    require(all(a["finished_unix"] <= b["started_unix"] for a, b in zip(receipts, receipts[1:])),
            f"{folder.relative_to(ROOT)}: gates did not overlap")
    return {**counts, "passed": 1119, "skipped_cases": skips,
            "six_native_gate_exit_codes": [r["native_exit_code"] for r in receipts]}


def validation(path, index_path, expected_pairs):
    completion = read(path)
    index = read_index(index_path)
    compressed = {s["path"]: sha(index_path.parent / s["path"]) for s in index["shards"]}
    require(completion["status"] == "ALL_SHARDS_VERIFIED" and
            completion["index_sha256"] == sha(index_path) and
            completion["compressed_sha256"] == compressed,
            f"{path.relative_to(ROOT)}: completion binds current index and all compressed bytes")
    require(completion["max_workers"] == 16 and completion["start_method"] == "spawn" and
            completion["validation_reduced"] is False and
            completion["scientific_metrics_computed"] is False,
            f"{path.relative_to(ROOT)}: full validation dispatch contract")
    require(len(completion["shards"]) == 32 and
            [s["seed"] for s in completion["shards"]] == index["seeds"] and
            completion["records"] == index["records"] == 18464 and
            completion["pairs"] == index["pairs"] == expected_pairs,
            f"{path.relative_to(ROOT)}: all 32 seeds, records and incidence pairs")
    worker_folder = path.parent / "workers"
    if path.name == "runtime_verified.json":
        worker_folder = path.parent / "runtime_verified"
    require(len(list(worker_folder.glob("seed-*.verified.json"))) == 32,
            f"{path.relative_to(ROOT)}: exactly 32 native completion files")
    for receipt, descriptor in zip(completion["shards"], index["shards"]):
        require(receipt == read(worker_folder / f"seed-{descriptor['seed']}.verified.json") and
                receipt["seed"] == descriptor["seed"] and receipt["records"] == descriptor["records"] == 577 and
                receipt["pairs"] == descriptor["pairs"] and receipt["sha256"] == descriptor["sha256"] and
                receipt["validator"] == "frozen-_shard_records",
                f"{path.relative_to(ROOT)}: seed {descriptor['seed']} original-parser completion")
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": sha(path),
            "workers_completed": 32, "records": 18464, "pairs": expected_pairs,
            "index_and_all_compressed_bytes_match": True,
            "canonical_uncompressed_hashes_match_index": True}


def main():
    sources = source_inventory(ROOT)
    frozen = read(OP / "frozen_inputs.json")
    require(len(sources) == 309 and sources == frozen["sources"] and
            digest(canonical_bytes(sources)) == frozen["sources_digest"] == EXPECTED_SOURCE_DIGEST,
            "309 current instrument files match the frozen source inventory")
    for revision in (frozen["instrument_commit"], NATIVE_COMMIT, "HEAD"):
        require(_committed_sources(ROOT, revision, tuple(sources)) == sources,
                f"instrument matches committed bytes at {revision}")
    prereg = read(OP / "preregistration.json")
    require(prereg["automatic_retry"] is False and prereg["maximum_spawn_workers"] == 16 and
            prereg["treatment_or_confirmatory_authorized"] is False,
            "one-shot preregistration excludes treatment, confirmation and automatic retry")
    launch, claim, launcher = (read(OP / n) for n in
                               ("pipeline_launch.json", "pipeline_claim.json", "launcher_claim.json"))
    observation = read(OP / "launch_live_observation.json")
    require(launch["pid"] == claim["pid"] == 26732 and
            str(launch["start_utc_ticks"]) == "639270752638521679" and
            launch["controller_sha256"] == sha(ROOT / "scripts/run_a95_pipeline.py") and
            launch["launcher_sha256"] == sha(ROOT / "scripts/launch_a95_pipeline.ps1") and
            launcher["launcher_pid"] == 23516 and
            str(launcher["start_utc_ticks"]) == "639270752627165537",
            "launch identity and current controller/launcher source hashes agree")
    identities = {p["pid"]: p for p in observation["processes"]}
    require(str(identities[26732]["start_utc_ticks"]) == str(launch["start_utc_ticks"]) and
            "scripts\\run_a95_pipeline.py" in identities[26732]["full_command"] and
            str(identities[23516]["start_utc_ticks"]) == str(launcher["start_utc_ticks"]) and
            "scripts\\launch_a95_pipeline.ps1" in identities[23516]["full_command"],
            "original full commands and actual start ticks are historically authenticated")
    review = read(OP / "source_bound_review.json")
    require(review["decision"] == "VALID" and review["sources_digest"] == EXPECTED_SOURCE_DIGEST and
            review["independent_agent_or_external_expert_review"] is False and
            review["old_reviews_runtime_or_data_migrated"] is False,
            "review is current-source internal acceptance, not independent or migrated")
    regressions = {name: regression(folder) for name, folder in (
        ("acceptance", OP / "acceptance_gates"),
        ("engineering_runtime", STAGE / "f0_runtime/gates"),
        ("formal_smoke", STAGE / "smoke_gates"))}
    manifest, manifest_sha = load_manifest(ROOT, ROOT / MANIFEST_PATH, "design_lock")
    require(manifest["sources"] == sources and require_smoke(ROOT, manifest, manifest_sha) == sha(ROOT / SMOKE_PATH),
            "committed F0, gates, sources, seeds, runtime and separate passing smoke bind the design stage")
    for n in (MANIFEST_PATH, SMOKE_PATH, "experiments/v03r/a95_measurement/f0_runtime/runtime.json"):
        read(ROOT / n)
    evaluator = read_json(OP / "independent_smoke_evaluator.stdout.log")
    require(evaluator == {"reason": None, "verdict": "PASS"}, "separate native smoke evaluator PASS")
    index_path = STAGE / "dev_baseline.json"
    index = read(index_path)
    require(index["seeds"] == list(STAGE_SEEDS["dev_baseline"]) == list(range(2026100910, 2026100942)) and
            index["episodes"] == list(range(577)) and index["bank_size"] == 1024 and
            index["execution"]["sources"] == sources and index["execution"]["manifest_sha256"] == manifest_sha,
            "development population, full dense axis and source/manifest bindings match")
    native_stages = {}
    for stage_name, expected_code in (("full_runtime", 0), ("runtime_full_verification", 0),
                                    ("formal_smoke", 0), ("independent_smoke_evaluator", 0),
                                    ("development32", 0), ("f1_plan", 0), ("full_f1", 3)):
        receipt = read(OP / f"{stage_name}.receipt.json")
        require(receipt["native_exit_code"] == expected_code and
                receipt["receipt_origin"] == "native_subprocess_wait",
                f"{stage_name}: genuine native exit {expected_code}")
        read(OP / f"{stage_name}.launch.json")
        native_stages[stage_name] = receipt
    passes = [validation(STAGE / part / "completed.json", index_path, 240959684) for part in
              ("f1_plan/validation-pass-001", "f1_execution/validation-pass-001",
               "f1_execution/validation-pass-002")]
    require(len(list((STAGE / "f1_plan").glob("validation-pass-*"))) == 1 and
            len(list((STAGE / "f1_execution").glob("validation-pass-*"))) == 2,
            "negative F1 has two fresh complete validation passes; plan has one separately")
    runtime_verified = validation(OP / "runtime_verified.json", STAGE / "f0_runtime/baseline.json", 241257920)
    engineering_index = read(STAGE / "f0_runtime/baseline.json")
    require(engineering_index["seeds"] == list(ENGINEERING_KEYS["dev_baseline"]) and
            not set(engineering_index["seeds"]).intersection(index["seeds"]),
            "engineering keys and incidence totals remain distinct from scientific development")
    f1_result = read(STAGE / "f1_result.json")
    diagnostics = f1_result["diagnostics"]
    completion = read(STAGE / "f1_execution/parallel_design/completed.json")
    require(completion["status"] == "ALL_SEEDS_CALCULATED_ORDERED_JOIN_COMPLETE" and
            completion["seeds"] == index["seeds"] and completion["records"] == 18464 and
            completion["pairs"] == 240959684 and len(completion["workers"]) == 32 and
            completion["index_sha256"] == sha(index_path) and
            completion["compressed_sha256"] == {s["path"]: sha(index_path.parent / s["path"]) for s in index["shards"]} and
            completion["design_result_sha256"] == digest(canonical_bytes(diagnostics)) and
            completion["join_order"] == "frozen-seed-order" and completion["max_workers"] == 16 and
            completion["start_method"] == "spawn" and completion["floating_moment_reduction"] is False and
            completion["partial_lock_published"] is False,
            "all design workers and deterministic ordered result bind unchanged input bytes")
    require(len(list((STAGE / "f1_execution/parallel_design").glob("seed-*.completed.json"))) == 32,
            "exactly 32 complete design receipts, not a partial worker prefix")
    for worker, descriptor in zip(completion["workers"], index["shards"]):
        require(worker == read(STAGE / f"f1_execution/parallel_design/seed-{descriptor['seed']}.completed.json") and
                worker["seed"] == descriptor["seed"] and worker["records"] == 577 and
                worker["pairs"] == descriptor["pairs"] and
                worker["uncompressed_shard_sha256"] == descriptor["sha256"] and
                len(worker["summary_sha256"]) == 64 and worker["parser"] == "original-_shard_records" and
                worker["arithmetic"] == "original-per-record-selector-updates",
                f"design seed {descriptor['seed']}: native full-axis completion and canonical hash binding")
    require(f1_result["status"] == diagnostics["status"] == "NO_ADMISSIBLE_GRID" and
            f1_result["written"] is False and diagnostics["f_R"] is None and
            not (STAGE / "dev_lock.json").exists(), "valid grid stop publishes no lock; Retention is not evaluated")
    require([r["metric"] for r in diagnostics["f_G"]["candidates"]] ==
            [0.3978494623655914, 0.210752688172043, 0.1032258064516129] and
            all(r["admissible"] is False and r["metric"] > .05 for r in diagnostics["f_G"]["candidates"]),
            "all three registered grids fail the unchanged 0.05 criterion")
    pipeline_result, controller_exit = (read(OP / n) for n in ("pipeline_result.json", "pipeline_exit.json"))
    require(pipeline_result["classification"] == "VALID_PROTOCOL_STOP_NO_ADMISSIBLE_DESIGN" and
            pipeline_result["result"] == f1_result and pipeline_result["native_f1_exit_code"] == 3 and
            controller_exit["native_exit_code"] == 3 and controller_exit["pid"] == 26732 and
            str(controller_exit["start_utc_ticks"]) == "639270752638521679" and
            controller_exit["role"] == "NATIVE_CONTROLLER_EXIT_ONLY" and
            pipeline_result["research_complete"] is False and
            pipeline_result["treatment_and_confirmatory_collected"] is False and
            not (OP / "pipeline_failure.json").exists(),
            "native F1 and controller agree on valid protocol stop, not operational invalidity")
    for name in ("f1_result.json", "dev_baseline.json", "pipeline/pipeline_result.json"):
        relative = (STAGE / name).relative_to(ROOT).as_posix()
        require(git_bytes(NATIVE_COMMIT, relative) == (ROOT / relative).read_bytes(),
                f"{name}: native evidence already committed without byte rewrite")
    preserved = read(OP / "parent_preservation.json")
    parent = Path(preserved["parent_root"])
    parent_manifest = read_json(parent / "experiments/v03r/parallel_verify_restart_20261008/f0_manifest_after_shutdown.json")
    require(len(parent_manifest["sources"]) == 295 and
            digest(canonical_bytes(parent_manifest["sources"])) == preserved["parent_sources_digest"] and
            all(sha(parent / p) == h for p, h in parent_manifest["sources"].items()),
            "all 295 archived rev5 instrument files remain unchanged")
    require(all(sha(parent / p) == h for p, h in preserved["native_evidence_sha256"].items()),
            "all four preserved rev5 native evidence files remain unchanged")
    parent_index_path = parent / "experiments/v03r/dev_baseline.json"
    require(preserved["compressed_sha256"] ==
            {s["path"]: sha(parent_index_path.parent / s["path"]) for s in read_json(parent_index_path)["shards"]},
            "all 32 archived rev5 compressed development shards remain unchanged")
    logs = list(OP.rglob("*.log")) + list((STAGE / "f1_execution").rglob("*.log"))
    for path in logs:
        HASHES[path.relative_to(ROOT).as_posix()] = sha(path)
    require(source_inventory(ROOT) == sources, "instrument unchanged at closure-audit end")
    print(json.dumps({
        "schema": "rfl-a95-read-only-closure-audit-v1",
        "role": "EXTERNAL_CLOSURE_AUDIT_NOT_NATIVE_EXECUTION_RECEIPT",
        "audit_verdict": "PASS", "observed_at": datetime.now(timezone.utc).isoformat(),
        "root": str(ROOT), "instrument_commit": frozen["instrument_commit"],
        "native_F1_evidence_commit": NATIVE_COMMIT, "source_count": 309,
        "sources_digest": EXPECTED_SOURCE_DIGEST, "native_stages": native_stages,
        "regressions": regressions, "development_validation_passes": passes,
        "engineering_full_verification": runtime_verified,
        "design": {"status": completion["status"], "workers_completed": 32, "records": 18464,
                   "incidence_pairs": 240959684, "join_order": completion["join_order"],
                   "design_result_sha256": completion["design_result_sha256"],
                   "complete_evidence_sha256": sha(STAGE / "f1_execution/parallel_design/completed.json"),
                   "worker_summary_hashes": "native worker/parent binding retained; summaries were in memory and are not independently rehashed here"},
        "native_F1_status": f1_result["status"], "native_F1_exit": 3,
        "native_controller_exit": 3, "lock_published": False,
        "retention_evaluated": False, "treatment_effect_measured": False,
        "research_complete": False, "old_rev5_preservation_passed": True,
        "new_experiment_or_full_parser_rerun": False,
        "gates_or_scientific_parameters_modified": False,
        "independent_agent_or_external_expert_review": False,
        "checks_passed": len(CHECKS), "checklist_sha256": digest(canonical_bytes(CHECKS)),
        "all_read_evidence_files": len(HASHES),
        "all_read_evidence_inventory_sha256": digest(canonical_bytes(HASHES)),
        "evidence_sha256": {p: h for p, h in HASHES.items()
                            if "/workers/" not in p and not Path(p).name.startswith("seed-")},
        "native_diagnostic_excerpt": {"f_T": diagnostics["f_T"], "f_N": diagnostics["f_N"],
            "f_C": {k: diagnostics["f_C"][k] for k in ("status", "refinement", "collateral_bound", "spread_population", "metrics")},
            "f_G": diagnostics["f_G"], "f_R": None},
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
