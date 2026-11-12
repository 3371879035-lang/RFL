"""Explicit user-authorized verification restart after power interruption, no redraw."""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PREVIOUS = ROOT / "experiments/v03r/parallel_verify_20261008"
sys.path.insert(0, str(PREVIOUS))
spec = importlib.util.spec_from_file_location("preserved_verification_controller", PREVIOUS / "continue_verified.py")
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
p = v.p
v.HERE = HERE
v.CONTROL_FILES = ("resume_after_shutdown.py", "launch_detached.ps1", "test_resume_after_shutdown.py",
                   "preregistration.json", "interruption_observation.json", "preservation_before_restart.json")
p.HERE = HERE
p.REVIEW = HERE / "source_bound_verification_review.json"
p.MANIFEST = HERE / "f0_manifest_after_shutdown.json"

def verify_saved(files, root=ROOT):
    from parallel_verify import file_digest
    for name, expected in files.items():
        path = (root / name).resolve()
        p.require(path.is_relative_to(root.resolve()), "preservation path escape")
        p.require(file_digest(path) == expected, "preserved evidence drift: " + name)

def reject_native_completion(folder):
    for name in ("pipeline_exit.json", "parallel_verification.receipt.json",
                 "parallel_verification.json", "runtime_completion_verified.json",
                 "pipeline_result.json", "pipeline_failure.json"):
        p.require(not (folder / name).exists(), "interrupted parent advanced: " + name)

def reject_live_tree(rows):
    p.require(not rows, "existing RFL Python task; no duplicate restart")

def no_existing_task():
    body = ("$ErrorActionPreference='Stop'; "
        "$rflRows=@(Get-CimInstance Win32_Process | Where-Object { "
        "$_.Name -eq 'python.exe' -and $_.ProcessId -ne " + str(os.getpid()) +
        " -and $_.CommandLine -like '*RFL-CausalChase*' } | "
        "Select-Object ProcessId,ParentProcessId,CreationDate,CommandLine); "
        "ConvertTo-Json -InputObject $rflRows -Depth 4 -Compress")
    result = subprocess.run([v.PWSH, "-NoProfile", "-NonInteractive", "-Command", body],
                            capture_output=True, encoding="utf-8")
    p.require(result.returncode == 0, "process preflight failed")
    reject_live_tree(json.loads(result.stdout.lstrip("\ufeff")))
    return {"role": "READ_ONLY_PROCESS_PREFLIGHT", "observed_at": p.now(),
            "existing_rfl_python_tasks": [], "excluded_self_pid": os.getpid(),
            "no_stop_performed": True}

def context():
    reg = p.read_json(HERE / "preregistration.json")
    p.require(reg["user_authorization"] == "2026-10-08: 继续我电脑刚才关机了"
              and reg["acquisition_restart"] is False and reg["scientific_seed_change"] is False,
              "restart authority or no-redraw boundary changed")
    p.require(ROOT / reg["interrupted_verification_folder"] == PREVIOUS, "previous folder differs")
    observation = p.read_json(HERE / "interruption_observation.json")
    p.require(observation["role"] == "EXTERNAL_OBSERVATION_NOT_NATIVE_CONTROLLER_RECEIPT"
              and observation["parent_native_completion_claimed"] is False
              and observation["scientific_completion_claimed"] is False
              and not any(row["exists"] for row in observation["formal_reservations"]),
              "invalid interruption observation")
    reject_native_completion(PREVIOUS)
    old_claim = p.read_json(PREVIOUS / "pipeline_claim.json")
    p.require(old_claim["operational_control_files"] == reg["original_operational_control_files"],
              "old controller binding differs")
    for name, expected in reg["original_operational_control_files"].items():
        p.require(p.digest((PREVIOUS / name).read_bytes()) == expected, "old wrapper changed")
    old_review = p.read_json(PREVIOUS / "source_bound_verification_review.json")
    p.require(p.digest((PREVIOUS / "source_bound_verification_review.json").read_bytes()) == reg["review_sha256"]
              and old_review["decision"] == "VALID"
              and old_review["sources_digest"] == reg["expected_sources_digest"], "old review mismatch")
    saved = p.read_json(HERE / "preservation_before_restart.json")
    p.require(saved["prior_preservation_mismatches"] == [], "prior benchmark preservation failed")
    verify_saved(saved["files"])
    result = v.context()
    p.require(result["runtime_sha256"] == reg["original_runtime_sha256"]
              and result["index_sha256"] == reg["original_index_sha256"], "completed timing differs")
    return result

def same_inputs(left, right):
    return {k:x for k,x in left.items() if k != "head"} == {k:x for k,x in right.items() if k != "head"}

def check_counts(path):
    suites = ET.parse(path).getroot().findall("testsuite")
    counts = {name: sum(int(s.get(name, "0")) for s in suites)
              for name in ("tests", "errors", "failures", "skipped")}
    p.require(counts["tests"] >= 36 and counts["errors"] == counts["failures"] == counts["skipped"] == 0,
              "restart wrapper validation failed")
    return counts

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()
    claimed = False
    try:
        v.no_formal()
        p.require(not (HERE / "control_claim.json").exists(), "restart already reserved; no automatic retry")
        identity = context()
        processes = no_existing_task()
        if args.plan:
            print(json.dumps({"status":"READY", "written":False, "sources_digest":identity["sources_digest"]}))
            return 0
        p.publish_new(HERE / "control_claim.json", {"pid":os.getpid(), "started_at":p.now(), **identity})
        claimed = True
        p.publish_new(HERE / "process_preflight.json", processes)
        p.run_success("wrapper_checks", [sys.executable, "-B", "-X", "utf8", "-m", "pytest", "-q",
            PREVIOUS / "test_parallel_verify.py", HERE / "test_resume_after_shutdown.py",
            "--junitxml", HERE / "wrapper_checks.xml"])
        counts = check_counts(HERE / "wrapper_checks.xml")
        p.require(context() == identity, "wrapper checks changed inputs")
        v.no_formal()
        no_existing_task()
        review = {"decision":"VALID", "role":"INTERNAL_EXPLICIT_POWER_INTERRUPTION_VERIFICATION_REVIEW",
            "sources_digest":identity["sources_digest"], "source_count":295, "rmst_policy":identity["rmst_policy"],
            "original_instrument_commit":identity["original_instrument_commit"],
            "prior_semantic_review":{"path":str(v.PARENT / "source_bound_resume_review.json"),
                                     "sha256":identity["prior_review_sha256"]},
            "prior_verification_review_sha256":p.read_json(HERE / "preregistration.json")["review_sha256"],
            "operational_control_files":v.controls(), "fresh_wrapper_checks":counts,
            "same_instrument_native_prerequisites_not_claimed_fresh":["full_regression", "benchmark"],
            "independent_agent_review_performed":False, "external_review_performed":False,
            "scientific_claims_authorized":[], "validation_reduced":False, "acquisition_restarted":False,
            "runtime_original_bytes_preserved":True, "reviewed_at":p.now()}
        p.publish_new(p.REVIEW, review)
        p.commit_exact([p.REVIEW, HERE / "wrapper_checks.xml", HERE / "wrapper_checks.receipt.json"],
                       "Review explicit post-power-interruption read-only verification restart")
        after = context()
        p.require(same_inputs(after, identity), "inputs changed after review")
        no_existing_task()
        observation = p.read_json(HERE / "interruption_observation.json")
        p.publish_new(HERE / "parent_interruption.json", observation)
        saved = p.read_json(HERE / "preservation_before_restart.json")
        p.publish_new(HERE / "parent_preservation.json", {"files":saved["files"],
            "role":"EXTERNAL_POWER_INTERRUPTION_PRESERVATION_NOT_NATIVE_COMPLETION",
            "old_native_controller_exit_available":False})
        p.publish_new(HERE / "pipeline_claim.json", {"pid":os.getpid(), "started_at":p.now(),
            "role":"EXPLICIT_POST_POWER_INTERRUPTION_READ_ONLY_VERIFICATION", **after})
        p.run_success("parallel_verification", [sys.executable, "-u", "-B", "-X", "utf8",
            PREVIOUS / "parallel_verify.py", "--index", p.BENCHMARK / "baseline.json",
            "--output", HERE / "parallel_verification.json"])
        result = p.read_json(HERE / "parallel_verification.json")
        p.require(result["status"] == "ALL_SHARDS_VERIFIED" and len(result["shards"]) == 32
                  and result["records"] == 18464 and result["index_sha256"] == identity["index_sha256"],
                  "full shard verification incomplete")
        p.require(same_inputs(context(), identity), "source/runtime/gate/postcheck drift")
        v.no_formal()
        p.publish_new(HERE / "runtime_completion_verified.json", {"status":"MEASURED_AND_VERIFIED",
            "observed_at":p.now(), "all_shards_verified":True, "verified_dev_runs":32,
            "dev_records":18464, "smoke_records":2885, "runtime_sha256":identity["runtime_sha256"],
            "index_sha256":identity["index_sha256"], "instrument_commit":identity["original_instrument_commit"],
            "sources_digest":identity["sources_digest"], "metrics_computed":False, "f0_valid":False,
            "verification_receipt_sha256":p.digest((HERE / "parallel_verification.json").read_bytes()),
            "verification_max_workers":16, "validator":"unchanged-frozen-_shard_records"})
        return v.continue_science(identity)
    except Exception as exc:
        failure = {"status":"STOPPED_EXPLICIT_SHUTDOWN_RESTART", "observed_at":p.now(),
            "error_type":type(exc).__name__, "error":str(exc), "automatic_retry":False,
            "scientific_completion_claimed":False}
        if claimed and not (HERE / "pipeline_failure.json").exists():
            p.publish_new(HERE / "pipeline_failure.json", failure)
        print(json.dumps(failure, ensure_ascii=False), flush=True)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
