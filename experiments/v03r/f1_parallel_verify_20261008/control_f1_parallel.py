"""One-shot internally reviewed F1 validation handover. No scientific redraw."""
from __future__ import annotations
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PARENT = ROOT / "experiments/v03r/parallel_verify_restart_20261008"
TEMPLATE = ROOT / "experiments/v03r/restart_20261008/continue_pipeline.py"
spec = importlib.util.spec_from_file_location("f1_parallel_stage_helpers", TEMPLATE)
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
p.HERE = HERE
PWSH = r"C:\Users\huani\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe"
INDEX = ROOT / "experiments/v03r/dev_baseline.json"
MANIFEST = PARENT / "f0_manifest_after_shutdown.json"
CONTROL_FILES = ("parallel_f1.py", "control_f1_parallel.py", "handover.ps1", "launch_detached.ps1",
                 "test_parallel_f1.py", "preregistration.json")


def require_committed(path):
    relative = Path(path).relative_to(ROOT).as_posix()
    data = subprocess.check_output(["git", "show", "HEAD:" + relative], cwd=ROOT, stderr=subprocess.DEVNULL)
    p.require(data == Path(path).read_bytes(), "operational file differs from committed bytes: " + relative)


def context():
    reg = p.read_json(HERE / "preregistration.json")
    p.require(reg["max_workers"] == 16 and reg["start_method"] == "spawn" and
              reg["validation_dispatch_changes"] is True and
              all(reg[key] is False for key in ("frozen_instrument_file_changes", "validation_reduction",
                  "validation_cache", "scientific_parameter_changes", "acquisition_restart",
                  "scientific_seed_change", "automatic_retry")), "registration boundary changed")
    p.require(reg["parent_folder"] == PARENT.relative_to(ROOT).as_posix() and
              ROOT / reg["index_path"] == INDEX and ROOT / reg["manifest_path"] == MANIFEST,
              "registered paths differ")
    sources = p.source_inventory(ROOT)
    p.require(len(sources) == 295 and p.digest(p.canonical_bytes(sources)) == reg["sources_digest"],
              "frozen source/spec/test changed")
    manifest, manifest_sha = p.load_manifest(ROOT, MANIFEST, "design_lock")
    p.require(manifest_sha == reg["manifest_sha256"] and
              p.require_smoke(ROOT, manifest, manifest_sha) == reg["smoke_sha256"], "F0/smoke binding drift")
    p.require(p.digest(INDEX.read_bytes()) == reg["index_sha256"], "dev index drift")
    index = p.read_index(INDEX)
    p.require(index["role"] == "DEVELOPMENT_BASELINE" and index["seeds"] == list(range(1000,1032)) and
              index["episodes"] == list(range(577)) and index["records"] == 18464 and index["bank_size"] == 1024
              and index["constants"] == p.CONSTANTS and index["execution"]["sources"] == sources and
              index["execution"]["manifest_sha256"] == manifest_sha and
              index["execution"]["smoke_report_sha256"] == reg["smoke_sha256"], "development binding changed")
    receipt = PARENT / "development.receipt.json"
    p.require(p.digest(receipt.read_bytes()) == reg["development_receipt_sha256"] and
              p.read_json(receipt)["native_exit_code"] == 0, "native development incomplete/changed")
    prior = PARENT / "source_bound_verification_review.json"
    p.require(p.digest(prior.read_bytes()) == reg["prior_review_sha256"] and
              p.read_json(prior)["decision"] == "VALID", "prior exact-instrument review changed")
    # Guard old operational bindings too; do not migrate evidence to modified controls.
    for folder in (PARENT, ROOT / "experiments/v03r/parallel_verify_20261008",
                   ROOT / "experiments/v03r/parallel16_resume_20261008"):
        claim = p.read_json(folder / "control_claim.json")
        for name, expected in claim["operational_control_files"].items():
            p.require(p.digest((folder / name).read_bytes()) == expected, "prior operational control drift: " + name)
    pv = ROOT / "experiments/v03r/parallel_verify_20261008/parallel_verify.py"
    p.require(p.digest(pv.read_bytes()) == reg["parallel_verifier_sha256"] and
              p.digest(TEMPLATE.read_bytes()) == reg["template_sha256"], "reused verifier/template drift")
    p.require(p.digest((ROOT / reg["runtime_path"]).read_bytes()) == reg["runtime_sha256"], "original timing changed")
    controls = {name: p.digest((HERE / name).read_bytes()) for name in CONTROL_FILES}
    for name in CONTROL_FILES:
        require_committed(HERE / name)
    return {"sources_digest": reg["sources_digest"], "source_count": 295,
            "operational_control_files": controls, "index_sha256": reg["index_sha256"],
            "manifest_sha256": manifest_sha, "smoke_sha256": reg["smoke_sha256"],
            "reused_verifier_sha256": reg["parallel_verifier_sha256"],
            "original_runtime_sha256_not_fresh": reg["runtime_sha256"]}


def require_parent_exited():
    receipt = p.read_json(PARENT / "design_lock_plan.receipt.json")
    exit_receipt = p.read_json(PARENT / "pipeline_exit.json")
    p.require(receipt["native_exit_code"] != 0 and exit_receipt["native_exit_code"] == 2 and
              str(exit_receipt["start_utc_ticks"]) == "639270461250300818",
              "old native read-only plan/controller exit not confirmed")
    p.require(not (PARENT / "design_lock.receipt.json").exists() and
              not (ROOT / "experiments/v03r/dev_lock.json").exists(), "original full F1 has advanced")


def preserve_parent():
    from parallel_f1 import pv
    index = p.read_index(INDEX)
    files = {path.relative_to(ROOT).as_posix(): pv.file_digest(path)
             for path in PARENT.rglob("*") if path.is_file()}
    files.update({(INDEX.parent / s["path"]).relative_to(ROOT).as_posix(): pv.file_digest(INDEX.parent / s["path"])
                  for s in index["shards"]})
    files[INDEX.relative_to(ROOT).as_posix()] = pv.file_digest(INDEX)
    for name in ("smoke_attempt.json", "smoke_report.json"):
        path = ROOT / "experiments/v03r" / name
        files[path.relative_to(ROOT).as_posix()] = pv.file_digest(path)
    p.publish_new(HERE / "parent_preservation.json", {"role":"POST_NATIVE_HANDOVER_EVIDENCE_PRESERVATION",
        "files":files, "compressed_bytes_hashes_not_descriptor_hashes":True,
        "old_raw_paths_and_instrument_identity_preserved":True, "observed_at":p.now()})


def parse_result(path):
    markers = [line.removeprefix("F1_RESULT_JSON=") for line in Path(path).read_text(encoding="utf-8").splitlines()
               if line.startswith("F1_RESULT_JSON=")]
    p.require(len(markers) == 1, "missing or duplicate terminal F1 result")
    return json.loads(markers[0])


def review_counts(path):
    suites = ET.parse(path).getroot().findall("testsuite")
    counts = {key:sum(int(s.get(key,"0")) for s in suites) for key in ("tests","errors","failures","skipped")}
    p.require(counts["tests"] >= 40 and counts["errors"] == counts["failures"] == counts["skipped"] == 0,
              "fresh operational equivalence tests not all PASS")
    return counts


def main():
    claimed = False
    try:
        p.require(not (HERE / "control_claim.json").exists(), "one-shot claim already exists")
        identity = context()
        p.run_success("parent_preflight", [PWSH,"-NoProfile","-NonInteractive","-File",HERE / "handover.ps1","-CheckOnly"])
        p.publish_new(HERE / "control_claim.json", {"pid":os.getpid(), "started_at":p.now(), **identity})
        claimed = True
        p.run_success("wrapper_checks", [sys.executable,"-B","-X","utf8","-m","pytest","-q",
            ROOT / "experiments/v03r/parallel_verify_20261008/test_parallel_verify.py",
            HERE / "test_parallel_f1.py", "--junitxml", HERE / "wrapper_checks.xml"])
        counts = review_counts(HERE / "wrapper_checks.xml")
        p.require(context() == identity, "pre-review byte drift")
        review = {"decision":"VALID", "role":"INTERNAL_SOURCE_BOUND_F1_VALIDATION_DISPATCH_REVIEW",
            **identity, "fresh_operational_tests":counts, "validation_dispatch_changes":True,
            "original_parser_and_selector_functions_unchanged":True, "selection_order_changed":False,
            "full_original_validation_every_pass":True, "validation_cache":False,
            "prior_semantic_review_sha256":p.read_json(HERE / "preregistration.json")["prior_review_sha256"],
            "prior_full_regression_smoke_and_runtime_not_claimed_fresh":True,
            "independent_agent_review_performed":False, "external_expert_review_performed":False,
            "scientific_claims_authorized":[], "reviewed_at":p.now()}
        review_path = HERE / "source_bound_parallel_f1_review.json"
        p.publish_new(review_path, review)
        p.commit_exact([review_path,HERE / "wrapper_checks.xml",HERE / "wrapper_checks.receipt.json"],
                       "Review validation-only parallel F1 dispatch with full original checks")
        p.require(context() == identity, "pre-handover byte drift")
        p.run_success("parent_handover", [PWSH,"-NoProfile","-NonInteractive","-File",HERE / "handover.ps1"])
        require_parent_exited()
        preserve_parent()
        p.publish_new(HERE / "pipeline_claim.json", {"pid":os.getpid(), "started_at":p.now(), **identity,
            "review_sha256":p.digest(review_path.read_bytes()), "no_new_acquisition":True})
        argv = [sys.executable,"-u","-B","-X","utf8",HERE / "parallel_f1.py"]
        p.run_success("design_lock_plan", [*argv,"--plan"])
        plan = parse_result(HERE / "design_lock_plan.stdout.log")
        p.require(plan["status"] == "PLAN_VALID" and plan["written"] is False and
                  plan["metrics_computed"] is False, "invalid F1 input plan")
        code = p.command("design_lock", argv)
        result = parse_result(HERE / "design_lock.stdout.log")
        status = p.classify_lock(code,result)
        p.require(context() == identity, "post-F1 byte drift")
        attestation = HERE / "f1_execution_attestation.json"
        payload = {"status":status, "f1_result":result, **identity,
            "review_sha256":p.digest(review_path.read_bytes()),
            "execution_receipt_sha256":p.digest((HERE / "f1_execution.json").read_bytes()),
            "research_complete":False, "next_stage_automatically_authorized":False,
            "old_timing_not_claimed_fresh":True, "finished_at":p.now()}
        paths = [attestation,HERE / "f1_execution.json",HERE / "design_lock.receipt.json"]
        if code == 0:
            lock = ROOT / "experiments/v03r/dev_lock.json"
            payload["lock_sha256"] = p.digest(lock.read_bytes())
            paths.append(lock)
        p.publish_new(attestation,payload)
        commit = p.commit_exact(paths,"Record complete original F1 under reviewed parallel input validation")
        p.publish_new(HERE / "pipeline_result.json", {**payload,"evidence_commit":commit,
            "native_f1_exit_code":code})
        return code
    except Exception as exc:
        failure = {"status":"STOPPED_F1_PARALLEL_OPERATION", "error_type":type(exc).__name__,
            "error":str(exc),"observed_at":p.now(),"automatic_retry":False,"research_complete":False}
        if claimed and not (HERE / "pipeline_failure.json").exists():
            p.publish_new(HERE / "pipeline_failure.json",failure)
        print(json.dumps(failure,ensure_ascii=False),flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
