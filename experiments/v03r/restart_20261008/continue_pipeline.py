"""One-shot prospective interruption restart R1; no treatment selection.

This operational controller is outside the instrument inventory. It only calls
the existing, source-bound instrument. Every output reservation is exclusive.
It stops at a legitimate F1 refusal or a committed F1 lock, never starts B2/V04R.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[3]
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b2.baseline_artifact import canonical_bytes, digest, read_index, verify_acquisition
from rfl_rebuild.b2.design_lock import publish_new
from rfl_rebuild.b2.f0_stages import (
    CONSTANTS, GATE_PATHS, _committed_sources, load_manifest, read_json,
    require, require_smoke, source_inventory, validate_rmst_policy,
)

BENCHMARK = ROOT / "experiments/v03r/f0_runtime_restart_20261008"
REVIEW = HERE / "source_bound_restart_review.json"
MANIFEST = HERE / "f0_manifest_restart.json"
EXPECTED_KEYS = {"smoke": list(range(970001, 970006)),
                 "dev_baseline": list(range(970006, 970038))}
FORMAL_OUTPUTS = ("smoke_attempt.json", "smoke_report.json", "dev_baseline",
                  "dev_baseline.json", "dev_lock.json")


def now():
    return datetime.now(timezone.utc).isoformat()


def validate_restart_population(registration):
    from rfl_rebuild.b2.f0_stages import SPENT_SMOKE_SEEDS, STAGE_SEEDS
    fresh = registration.get("fresh_smoke_seeds")
    require(type(fresh) is list and all(type(seed) is int for seed in fresh)
            and fresh == list(STAGE_SEEDS["smoke"]), "restart smoke population mismatch")
    require(registration.get("spent_smoke_seeds") == list(SPENT_SMOKE_SEEDS),
            "spent population mismatch")
    require(registration.get("development_seeds") == list(STAGE_SEEDS["dev_baseline"]),
            "development population changed")
    require(not set(fresh).intersection((*SPENT_SMOKE_SEEDS, *STAGE_SEEDS["dev_baseline"],
                                      *EXPECTED_KEYS["smoke"], *EXPECTED_KEYS["dev_baseline"])),
            "restart population overlaps prior or operational keys")
    for name, value in CONSTANTS.items():
        require(registration["unchanged_scientific_parameters"].get(name) == value,
                f"restart scientific constant changed: {name}")


def verify_parent_preserved():
    registration = read_json(HERE / "preregistration.json")
    validate_restart_population(registration)
    require(pathlib.Path(registration["restart_root"]).resolve() == ROOT.resolve(),
            "restart checkout differs from registration")
    parent = pathlib.Path(registration["preserved_root"])
    previous = parent / "experiments/v03r/takeover_20261007"
    interrupted = read_json(HERE / "parent_interruption.json")
    require(digest((previous / "pipeline_interruption.json").read_bytes())
            == digest((HERE / "parent_interruption.json").read_bytes()), "parent observation changed")
    require(digest((previous / "restart_preregistration_20261008.json").read_bytes())
            == digest((HERE / "preregistration.json").read_bytes()), "restart registration changed")
    old_sources = read_json(previous / "pipeline_claim.json")["sources"]
    require(source_inventory(parent) == old_sources, "original worktree source changed")
    attempt = parent / "experiments/v03r/smoke_attempt.json"
    require(digest(attempt.read_bytes()) == interrupted["formal_smoke"]["reservation_sha256"],
            "original spent reservation changed")
    for name, expected in interrupted["preserved_log_sha256"].items():
        require(digest((previous / name).read_bytes()) == expected, "original log changed: " + name)
    require(digest((previous / "f0_manifest_rev5.json").read_bytes())
            == interrupted["completed_preconditions"]["f0_manifest_sha256"], "original F0 changed")
    for name in ("smoke_report.json", "dev_baseline", "dev_baseline.json", "dev_lock.json"):
        require(not (parent / "experiments/v03r" / name).exists(), "parent formal state changed: " + name)
    return {"observed_at": now(), "original_source_preserved": True,
            "old_smoke_reservation_preserved": True, "old_logs_preserved": True,
            "new_population_preregistered": True, "scientific_parameters_unchanged": True}


def classify_lock(exit_code, payload):
    status = payload.get("status") if isinstance(payload, dict) else None
    if exit_code == 0 and status == "LOCKED" and payload.get("written") is True:
        return "F1_LOCKED_REQUIRES_NEXT_STAGE_REVIEW"
    if exit_code == 3 and isinstance(status, str) and status.startswith("NO_ADMISSIBLE_"):
        require(payload.get("written") is False, "refusal claims a published F1")
        return "VALID_PROTOCOL_STOP_NO_ADMISSIBLE_DESIGN"
    raise ProtocolError(f"invalid F1 completion: exit={exit_code}, status={status}")


def validate_launch(root, benchmark, manifest, review):
    root = pathlib.Path(root)
    require(not pathlib.Path(benchmark).exists(), "fresh benchmark reservation required")
    require(not pathlib.Path(manifest).exists(), "new manifest path required")
    for name in FORMAL_OUTPUTS:
        require(not (root / "experiments/v03r" / name).exists(), f"spent formal output: {name}")
    sources = source_inventory(root)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    require(_committed_sources(root, head, tuple(sources)) == sources,
            "source/spec/test bytes differ from their committed instrument")
    identity = digest(canonical_bytes(sources))
    require(review.get("decision") == "VALID" and review.get("sources_digest") == identity,
            "existing source-bound review does not match current instrument")
    validate_rmst_policy(review.get("rmst_policy"))
    return {"head": head, "sources": sources, "sources_digest": identity,
            "source_count": len(sources), "review_sha256": digest(REVIEW.read_bytes()),
            "orchestrator_sha256": digest(pathlib.Path(__file__).read_bytes()),
            "python": sys.executable, "constants": CONSTANTS, "keys": EXPECTED_KEYS,
            "scientific_seed_draws_at_launch": 0}


def command(stage, argv):
    """Separate native stdout/stderr and receipt; preserve all exits verbatim."""
    started = now()
    print(f"START {stage} {started}", flush=True)
    with (HERE / f"{stage}.stdout.log").open("xb") as out, \
            (HERE / f"{stage}.stderr.log").open("xb") as err:
        result = subprocess.run([str(x) for x in argv], cwd=ROOT, stdout=out, stderr=err,
                                env={**os.environ, "PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1",
                                     "PYTHONDONTWRITEBYTECODE": "1"})
    receipt = {"stage": stage, "argv": [str(x) for x in argv], "started_at": started,
               "finished_at": now(), "native_exit_code": result.returncode}
    publish_new(HERE / f"{stage}.receipt.json", receipt)
    print(f"END {stage} exit={result.returncode} {receipt['finished_at']}", flush=True)
    return result.returncode


def run_success(stage, argv):
    code = command(stage, argv)
    require(code == 0, f"{stage} failed with native exit {code}; see its preserved logs")


def verify_benchmark(directory, expected_sources):
    """Reuse the frozen inspector's metadata checker and native full-shard QA."""
    directory = pathlib.Path(directory)
    frozen = read_json(directory / "frozen_inputs.json")
    require(frozen.get("keys") == EXPECTED_KEYS and frozen.get("constants") == CONSTANTS,
            "benchmark operational population/constants differ")
    require(frozen.get("role") == "OPERATIONAL_BENCHMARK", "wrong frozen-input role")
    require(frozen.get("sources") == expected_sources == source_inventory(ROOT),
            "instrument changed before full benchmark verification")
    require(_committed_sources(ROOT, frozen["instrument_commit"], tuple(expected_sources))
            == expected_sources, "benchmark source bytes are not committed")
    runtime_path, index_path = directory / "runtime.json", directory / "baseline.json"
    before = (digest(runtime_path.read_bytes()), digest(index_path.read_bytes()))
    runtime, index = read_json(runtime_path), read_index(index_path)
    gates = {p: digest((ROOT / p).read_bytes()) for p in GATE_PATHS}
    inspector_path = ROOT / "experiments/v03r/amendment_20260927/inspect_runtime_rev5.py"
    spec = importlib.util.spec_from_file_location("frozen_rev5_inspector", inspector_path)
    inspector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(inspector)
    inspector.verify_metadata(frozen, runtime, index, gates)
    verify_acquisition(index_path)
    require(source_inventory(ROOT) == expected_sources, "source drift during verification")
    require((digest(runtime_path.read_bytes()), digest(index_path.read_bytes())) == before,
            "benchmark metadata changed during verification")
    require({p: digest((ROOT / p).read_bytes()) for p in GATE_PATHS} == gates,
            "gate evidence changed during verification")
    return {"status": "MEASURED_AND_VERIFIED", "observed_at": now(),
            "all_shards_verified": True, "verified_dev_runs": 32,
            "dev_records": index["records"], "smoke_records": runtime["smoke"]["records"],
            "runtime_sha256": before[0], "index_sha256": before[1],
            "instrument_commit": frozen["instrument_commit"],
            "sources_digest": frozen["sources_digest"], "metrics_computed": False,
            "formal_stage_authorized": False, "f0_valid": False}


def commit_exact(paths, message):
    """Never commit unrelated staged/dirty work; no reset, push or hook bypass."""
    relatives = [pathlib.Path(p).relative_to(ROOT).as_posix() for p in paths]
    staged_before = subprocess.check_output(["git", "diff", "--cached", "--name-only", "-z"], cwd=ROOT)
    run_success("git_add_" + paths[0].stem, ["git", "add", "--", *relatives])
    run_success("git_commit_" + paths[0].stem, ["git", "commit", "--only", "-m", message, "--", *relatives])
    staged_after = subprocess.check_output(["git", "diff", "--cached", "--name-only", "-z"], cwd=ROOT)
    require(staged_after == staged_before, "unrelated staged inventory changed")
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def preserve_prelaunch():
    folder = HERE / "prelaunch_gate_artifacts"
    folder.mkdir(exist_ok=False)
    receipt = {}
    for name in GATE_PATHS:
        original, copied = ROOT / name, folder / pathlib.Path(name).name
        shutil.copyfile(original, copied)
        require(digest(original.read_bytes()) == digest(copied.read_bytes()), "gate backup differs")
        receipt[name] = {"sha256": digest(copied.read_bytes()), "backup": copied.relative_to(ROOT).as_posix()}
    return receipt


def pipeline():
    review = read_json(REVIEW)
    preflight = validate_launch(ROOT, BENCHMARK, MANIFEST, review)
    parent_preservation = verify_parent_preserved()
    # Exclusive claim: two controllers cannot spend the same stage reservation.
    publish_new(HERE / "pipeline_claim.json", {"pid": os.getpid(), "started_at": now(), **preflight})
    publish_new(HERE / "parent_preservation_verified.json", parent_preservation)
    publish_new(HERE / "prelaunch_preservation.json", preserve_prelaunch())
    run_success("full_regression", [sys.executable, "-B", "-X", "utf8", "-m", "pytest",
                                    "--junitxml", HERE / "full_regression.xml"])
    require(source_inventory(ROOT) == preflight["sources"], "tests did not restore frozen instrument")
    run_success("benchmark", [sys.executable, "-u", "-B", "-X", "utf8",
                              "scripts/benchmark_f0_runtime.py", "--output-dir", BENCHMARK])
    print("START full_runtime_integrity " + now(), flush=True)
    verification = verify_benchmark(BENCHMARK, preflight["sources"])
    publish_new(HERE / "runtime_completion_verified.json", verification)
    print("END full_runtime_integrity " + now(), flush=True)
    run_success("finalize_manifest", [sys.executable, "-B", "-X", "utf8", "scripts/f0_manifest.py",
                                      "--finalize", "--runtime", BENCHMARK / "runtime.json",
                                      "--review", REVIEW, "--output", MANIFEST])
    manifest_commit = commit_exact([MANIFEST, HERE / "runtime_completion_verified.json",
                                   BENCHMARK / "runtime.json", BENCHMARK / "frozen_inputs.json",
                                   BENCHMARK / "baseline.json"],
                                  "Bind completed R1 runtime and prospective restart F0 authorization")
    verify_parent_preserved()
    load_manifest(ROOT, MANIFEST, "smoke")
    run_success("smoke", [sys.executable, "-u", "-B", "-X", "utf8", "scripts/run_smoke.py",
                          "--seeds-file", ROOT / "experiments/v03r/smoke_seeds.txt", "--manifest", MANIFEST])
    run_success("evaluate_smoke", [sys.executable, "-B", "-X", "utf8",
                                  "experiments/v03r/evaluate_smoke_gate.py", "--manifest", MANIFEST])
    manifest, identity = load_manifest(ROOT, MANIFEST, "dev_baseline")
    require_smoke(ROOT, manifest, identity)
    run_success("development", [sys.executable, "-u", "-B", "-X", "utf8", "scripts/run_dev_baseline.py",
                                "--seeds-file", ROOT / "experiments/v03r/dev_seeds.txt", "--manifest", MANIFEST])
    run_success("design_lock_plan", [sys.executable, "-B", "-X", "utf8", "scripts/run_dev_lock.py",
                                     "--design", ROOT / "experiments/v03r/dev_baseline.json",
                                     "--manifest", MANIFEST, "--plan"])
    code = command("design_lock", [sys.executable, "-u", "-B", "-X", "utf8", "scripts/run_dev_lock.py",
                                   "--design", ROOT / "experiments/v03r/dev_baseline.json", "--manifest", MANIFEST])
    payload = json.loads((HERE / "design_lock.stdout.log").read_text(encoding="utf-8"))
    status = classify_lock(code, payload)
    lock_path = ROOT / "experiments/v03r/dev_lock.json"
    if status == "VALID_PROTOCOL_STOP_NO_ADMISSIBLE_DESIGN":
        require(not lock_path.exists(), "NO_ADMISSIBLE may not publish a partial F1")
        lock_commit = None
    else:
        require(lock_path.is_file() and read_json(lock_path).get("status") == "LOCKED", "F1 file missing")
        lock_commit = commit_exact([lock_path], "Freeze indivisible F1 design and threshold lock")
    result = {"status": status, "completed_at": now(), "manifest_commit": manifest_commit,
              "f1_commit": lock_commit, "native_design_lock_exit": code,
              "design_lock_status": payload["status"], "formal_smoke_passed": True,
              "development_seeds": 32, "development_records": 32 * 577,
              "treatment_curves_run": False, "confirmatory_run": False,
              "v04r_started": False, "scientific_superiority_claimed": False}
    publish_new(HERE / "pipeline_result.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return 3 if status == "VALID_PROTOCOL_STOP_NO_ADMISSIBLE_DESIGN" else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()
    if args.plan:
        result = validate_launch(ROOT, BENCHMARK, MANIFEST, read_json(REVIEW))
        parent = verify_parent_preserved()
        print(json.dumps({"status": "READY", "written": False,
                          "sources_digest": result["sources_digest"], "source_count": result["source_count"],
                          "parent_preservation": parent}, ensure_ascii=False, indent=2))
        return 0
    try:
        return pipeline()
    except Exception as exc:
        failure = {"status": "STOPPED_INVALID_OR_RUNTIME_ERROR", "observed_at": now(),
                   "error_type": type(exc).__name__, "error": str(exc),
                   "scientific_superiority_claimed": False, "no_automatic_retry": True}
        # Do not replace a completed or earlier failure receipt.
        path = HERE / "pipeline_failure.json"
        if not path.exists():
            publish_new(path, failure)
        print(json.dumps(failure, ensure_ascii=False, indent=2), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
