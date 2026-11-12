"""Explicitly authorized one-shot parallel design analysis, never new acquisition."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
PARENT=ROOT / "experiments/v03r/f1_parallel_verify_20261008"
sys.path.insert(0,str(PARENT))
import control_f1_parallel as previous
import parallel_f1 as old_adapter
p=previous.p
p.HERE=HERE
PWSH=previous.PWSH
INDEX,MANIFEST=previous.INDEX,previous.MANIFEST
CONTROL_FILES=("design_backend.py","control_parallel_design.py","test_parallel_design.py",
               "preregistration.json","equivalence_contract.json","handover.ps1","launch_detached.ps1")


def require_committed(path):
    previous.require_committed(path)


def context():
    original=previous.context()
    registration=p.read_json(HERE / "preregistration.json")
    p.require(registration["analysis_execution_backend_changes"] is True and registration["max_workers"] == 16
        and registration["start_method"] == "spawn" and all(registration[k] is False for k in
        ("frozen_source_file_changes","scientific_parameter_changes","acquisition_restart","scientific_seed_change",
         "automatic_retry","validation_cache")),"parallel analysis authority/boundary changed")
    p.require(registration["parent_folder"] == PARENT.relative_to(ROOT).as_posix()
        and original["sources_digest"] == registration["original_scientific_sources_digest"]
        and original["manifest_sha256"] == registration["original_f0_identity"]
        and original["index_sha256"] == registration["original_acquisition_index_identity"],"original acquisition binding changed")
    prior=PARENT / "source_bound_parallel_f1_review.json"
    require_committed(prior)
    p.require(p.digest(prior.read_bytes()) == registration["prior_analysis_review_sha256"]
        and p.read_json(prior)["decision"] == "VALID","prior analysis review drift")
    controls={name:p.digest((HERE / name).read_bytes()) for name in CONTROL_FILES}
    for name in CONTROL_FILES:require_committed(HERE / name)
    return {"original_acquisition_binding":original,"analysis_execution_files":controls,
        "prior_review_sha256":registration["prior_analysis_review_sha256"],
        "analysis_backend_identity":p.digest(p.canonical_bytes(controls)),
        "analysis_backend_changes":True,"new_acquisition":False}


def require_parent_exited():
    receipt=p.read_json(PARENT / "design_lock.receipt.json")
    exit_receipt=p.read_json(PARENT / "pipeline_exit.json")
    p.require(receipt["native_exit_code"] != 0 and exit_receipt["native_exit_code"] == 2 and
        str(exit_receipt["start_utc_ticks"]) == "639270601849822357","old analysis/controller native exit not authenticated")
    p.require(not (PARENT / "pipeline_result.json").exists() and
        not (ROOT / "experiments/v03r/dev_lock.json").exists(),"old F1 has already produced a result")


def preserve_parent():
    index=p.read_index(INDEX)
    files={path.relative_to(ROOT).as_posix():old_adapter.pv.file_digest(path)
           for path in PARENT.rglob("*") if path.is_file()}
    files.update({(INDEX.parent / s["path"]).relative_to(ROOT).as_posix():old_adapter.pv.file_digest(INDEX.parent / s["path"])
        for s in index["shards"]})
    files[INDEX.relative_to(ROOT).as_posix()]=old_adapter.pv.file_digest(INDEX)
    p.publish_new(HERE / "parent_preservation.json",{"role":"POST_NATIVE_USER_AUTHORIZED_ANALYSIS_HANDOVER_PRESERVATION",
        "files":files,"old_source_commit_and_raw_metadata_retained":True,
        "compressed_hashes_are_not_uncompressed_descriptor_hashes":True,"observed_at":p.now()})


def check_tests(path):
    suites=ET.parse(path).getroot().findall("testsuite")
    counts={key:sum(int(s.get(key,"0")) for s in suites) for key in ("tests","failures","errors","skipped")}
    p.require(counts["tests"] >= 80 and counts["errors"] == counts["failures"] == counts["skipped"] == 0,
        "fresh original-law/parallel-analysis/dispatch tests not all PASS")
    return counts


def main():
    claimed=False
    try:
        p.require(not (HERE / "control_claim.json").exists(),"one-shot parallel design already reserved")
        identity=context()
        p.run_success("parent_preflight",[PWSH,"-NoProfile","-NonInteractive","-File",HERE / "handover.ps1","-CheckOnly"])
        p.publish_new(HERE / "control_claim.json",{"pid":os.getpid(),"started_at":p.now(),"binding":identity})
        claimed=True
        p.run_success("wrapper_checks",[sys.executable,"-B","-X","utf8","-m","pytest","-q",
            ROOT / "tests/rebuild/test_b2_design_selection.py",
            ROOT / "experiments/v03r/parallel_verify_20261008/test_parallel_verify.py",
            PARENT / "test_parallel_f1.py",HERE / "test_parallel_design.py","--junitxml",HERE / "wrapper_checks.xml"])
        counts=check_tests(HERE / "wrapper_checks.xml")
        p.require(context() == identity,"analysis review input/source/control drift")
        review_path=HERE / "source_bound_parallel_design_review.json"
        review={"decision":"VALID","role":"INTERNAL_SOURCE_BOUND_EXPLICIT_PARALLEL_ANALYSIS_REVIEW",
            "binding":identity,"fresh_checks":counts,"analysis_backend_changes":True,
            "original_per_record_arithmetic_functions_used":True,"join_fixed_seed_order":True,
            "only_max_undefined_and_exact_integer_histogram_join":True,
            "acquisition_restarted":False,"old_full_regression_smoke_timing_not_claimed_fresh":True,
            "scientific_outcomes_used_to_choose_execution_or_design_parameters":False,
            "independent_agent_review_performed":False,"external_expert_review_performed":False,
            "scientific_completion_claims_authorized":[],"reviewed_at":p.now()}
        p.publish_new(review_path,review)
        p.commit_exact([review_path,HERE / "wrapper_checks.xml",HERE / "wrapper_checks.receipt.json"],
                       "Review exact seed-parallel F1 computation and unchanged scientific laws")
        p.require(context() == identity,"post-review byte drift")
        p.run_success("parent_handover",[PWSH,"-NoProfile","-NonInteractive","-File",HERE / "handover.ps1"])
        require_parent_exited()
        preserve_parent()
        p.publish_new(HERE / "pipeline_claim.json",{"pid":os.getpid(),"started_at":p.now(),"binding":identity,
            "review_sha256":p.digest(review_path.read_bytes()),"acquisition_restart":False})
        argv=[sys.executable,"-u","-B","-X","utf8",HERE / "design_backend.py"]
        p.run_success("design_lock_plan",[*argv,"--plan"])
        plan=previous.parse_result(HERE / "design_lock_plan.stdout.log")
        p.require(plan["status"] == "PLAN_VALID" and plan["metrics_computed"] is False and plan["written"] is False,
            "invalid fresh F1 analysis plan")
        code=p.command("design_lock",argv)
        result=previous.parse_result(HERE / "design_lock.stdout.log")
        status=p.classify_lock(code,result)
        p.require(context() == identity,"post-analysis byte drift")
        execution=HERE / "f1_execution.json"
        payload={"status":status,"f1_result":result,"binding":identity,
            "review_sha256":p.digest(review_path.read_bytes()),"execution_sha256":p.digest(execution.read_bytes()),
            "research_complete":False,"next_stage_automatically_authorized":False,
            "original_acquisition_and_timing_not_relabelled":True,"finished_at":p.now()}
        attestation=HERE / "f1_execution_attestation.json"
        paths=[attestation,execution,HERE / "design_lock.receipt.json",HERE / "parallel_design/completed.json"]
        if code == 0:
            lock=ROOT / "experiments/v03r/dev_lock.json"
            payload["lock_sha256"]=p.digest(lock.read_bytes())
            paths.append(lock)
        p.publish_new(attestation,payload)
        commit=p.commit_exact(paths,"Record complete F1 parallel analysis with exact ordered scientific reduction")
        p.publish_new(HERE / "pipeline_result.json",{**payload,"evidence_commit":commit,"native_f1_exit_code":code})
        return code
    except Exception as exc:
        failure={"status":"STOPPED_PARALLEL_F1_DESIGN_OPERATION","error_type":type(exc).__name__,"error":str(exc),
            "observed_at":p.now(),"automatic_retry":False,"research_complete":False}
        if claimed and not (HERE / "pipeline_failure.json").exists():p.publish_new(HERE / "pipeline_failure.json",failure)
        print(json.dumps(failure,ensure_ascii=False),flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
