"""One-use A96 acceptance -> fresh F0 -> smoke -> development -> full F1.
Native receipts are written only after subprocess.wait. No retry or parameter search.
"""
from __future__ import annotations
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rfl_rebuild.b2.baseline_artifact import canonical_bytes, digest, read_index
from rfl_rebuild.b2.design_lock import CONSTANTS, publish_new
from rfl_rebuild.b2.f0_stages import (
    GATES, GATE_PATHS, MANIFEST_PATH, SMOKE_PATH, SEED_PATHS, ARTIFACT_SCHEMA,
    source_inventory, _committed_sources, require, read_json, run_gate_suite,
    build_manifest, validate_runtime, evaluate_smoke, load_manifest,
)
from rfl_rebuild.b2.protocol_profile import STAGE_ROOT, STAGE_SEEDS, ENGINEERING_KEYS, MEASUREMENT_PROFILE
from rfl_rebuild.b2.parallel_validation import verify_parallel
from rfl_rebuild.b2.rmst_policy import benchmark_rmst_policy

FOLDER = ROOT / STAGE_ROOT
OP = FOLDER / "pipeline"
PARENT = Path("D:/强化反馈学习/RFL-CausalChase-v0.3-measurement-20261008")


def now():
    return datetime.now(timezone.utc).isoformat()


def update_result_ledger(state, *, result=None, native_f1=None):
    # This mutable local overview is not a native receipt or an instrument input.
    path=ROOT / "experiments/rebuild_status_current.json"
    ledger=read_json(path)
    require(Path(ledger["root"]).resolve() == ROOT.resolve()
            and ledger["measurement_profile"] == MEASUREMENT_PROFILE,
            "refuse to overwrite another study's result ledger")
    ledger.update(observed_at_utc=now(), engineering_state=state,
                  research_complete=False, native_f1_exit_code=native_f1)
    if result is not None:
        ledger.update(scientific_result=result["status"],
                      current_frozen_protocol_complete=False,
                      frozen_protocol_state="VALID_NO_ADMISSIBLE_CLOSURE_AUDIT_PENDING" if native_f1 == 3 else "F1_LOCKED_NOT_SCIENTIFIC_COMPLETE",
                      native_result=STAGE_ROOT + "/pipeline/pipeline_result.json",
                      monitor_should_stop=False,
                      execution_level="FRESH_SMOKE_PASS_DEVELOPMENT32_COMPLETE_FULL_F1_NATIVE_"+str(native_f1),
                      scientific_claim="No treatment or confirmation was collected. Full F1 is a design gate, not an efficacy result.")
        ledger["gate_states"].update(full_acceptance="SIX_SERIAL_NATIVE_ZERO_GATES",
            full37_key_engineering_timing="NATIVE_0_COMPLETE_NOT_SCIENTIFIC_DATA",
            full_engineering_shard_validation="NATIVE_0_FULL_32_SHARDS",committed_F0="VALID_SOURCE_BOUND_NEW_MANIFEST",
            formal_smoke="NATIVE_0_AND_SEPARATE_EVALUATOR_PASS",development32="NATIVE_0_COMPLETE",
            f1_plan="NATIVE_0_PLAN_VALID_NO_DESIGN_LOCK",
            indivisible_F1_lock="LOCKED" if native_f1==0 else "NOT_PUBLISHED_VALID_NO_ADMISSIBLE")
    temporary=path.with_name(path.name+f".{os.getpid()}.tmp")
    with temporary.open("xb") as stream:
        stream.write(canonical_bytes(ledger))
    os.replace(temporary,path)


def command(stage, argv, allowed=(0,)):
    started = now()
    print(f"START {stage} {started}", flush=True)
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1",
               OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
    with (OP / (stage + ".stdout.log")).open("xb") as out, (OP / (stage + ".stderr.log")).open("xb") as err:
        process = subprocess.Popen(argv, cwd=ROOT, stdout=out, stderr=err, env=env)
        publish_new(OP / (stage + ".launch.json"), {"argv":argv,"pid":process.pid,"started_at":started,
                    "role":"START_RECORD_NOT_COMPLETION","automatic_retry":False})
        code = process.wait()
    publish_new(OP / (stage + ".receipt.json"), {"argv":argv,"pid":process.pid,"started_at":started,
        "finished_at":now(),"native_exit_code":code,"receipt_origin":"native_subprocess_wait"})
    print(f"END {stage} native={code} {now()}", flush=True)
    require(code in allowed, f"{stage} native exit {code}; no automatic retry")
    return code


def commit_files(label, paths):
    # No broad add, push, reset or unrelated changes. Every evidence path is explicit.
    command("add_" + label, ["git","add","--",*paths])
    command("commit_" + label, ["git","commit","-m",label])


def regression_counts(path):
    doc=ET.parse(path).getroot()
    suites=list(doc.iter("testsuite"))
    result={k:sum(int(s.get(k,"0")) for s in suites) for k in ("tests","failures","errors","skipped")}
    skips=[{"classname":c.get("classname"),"name":c.get("name")} for c in doc.iter("testcase") if c.find("skipped") is not None]
    expected=[{"classname":"tests.rebuild.test_b2_acquisition",
               "name":"test_12_a_site_no_episode_consults_shares_the_generic_value[P]"}]
    require(result["tests"] >= 1001 and result["failures"] == result["errors"] == 0 and skips == expected,
            "full regression failed or gained an unreviewed skip")
    return {**result,"passed":result["tests"]-result["skipped"],"skipped_cases":skips}


def assert_identity(sources):
    require(source_inventory(ROOT) == sources, "instrument source inventory drift")
    require(_committed_sources(ROOT, "HEAD", tuple(sources)) == sources, "current source differs from committed instrument")


def parent_evidence():
    snapshot=read_json(OP / "parent_snapshot.json")
    require(Path(snapshot["parent_root"]).resolve() == PARENT.resolve()
            and snapshot["parent_state"] == "CLOSED_VALID_STOP"
            and snapshot["parent_result"] == "NO_ADMISSIBLE_GRID", "wrong closed parent")
    evidence=snapshot["native_evidence_sha256"]
    for name,expected in evidence.items():
        require(digest((PARENT/name).read_bytes()) == expected,"parent evidence drift: "+name)
    require(len(snapshot["sources"]) == 309 and
            digest(canonical_bytes(snapshot["sources"])) == snapshot["sources_digest"], "parent source inventory mismatch")
    for name,expected in snapshot["sources"].items():
        require(digest((PARENT/name).read_bytes()) == expected,"parent source drift: "+name)
    index_path=PARENT / snapshot["shard_base"] / "dev_baseline.json"
    index=read_json(index_path)
    result=read_json(PARENT / snapshot["shard_base"] / "f1_result.json")
    native_f1=read_json(PARENT / snapshot["shard_base"] / "pipeline/full_f1.receipt.json")
    native_controller=read_json(PARENT / snapshot["shard_base"] / "pipeline/pipeline_exit.json")
    require(result["status"] == "NO_ADMISSIBLE_GRID" and result["written"] is False
            and not (PARENT / snapshot["shard_base"] / "dev_lock.json").exists(), "closed parent was relabelled")
    require(native_f1["native_exit_code"] == native_controller["native_exit_code"] == 3
            and native_f1["receipt_origin"] == "native_subprocess_wait"
            and native_controller["role"] == "NATIVE_CONTROLLER_EXIT_ONLY", "parent stop lacks native exits")
    compressed={s["path"]:digest((index_path.parent/s["path"]).read_bytes()) for s in index["shards"]}
    require(len(compressed) == 32 and compressed == snapshot["compressed_sha256"], "parent raw compressed bytes changed")
    return {"role":"READ_ONLY_PARENT_PRESERVATION_NOT_NEW_SCIENTIFIC_RECEIPT",
            "parent_root":str(PARENT),"native_evidence_sha256":evidence,
            "parent_sources_digest":snapshot["sources_digest"],"compressed_sha256":compressed}


def validate_registration():
    registration=read_json(OP / "preregistration.json")
    contract=read_json(ROOT / "docs/rebuild/a96_dense_measurement_contract.json")
    registry=read_json(ROOT / "docs/rebuild/a96_seed_registry.json")
    require(Path(registration["root"]).resolve() == ROOT.resolve()
            and registration["measurement_profile"] == MEASUREMENT_PROFILE
            and registration["automatic_retry"] is False, "wrong preregistered execution root/profile")
    require(contract["ratified"] is True and contract["approval"]["ratified"] is True
            and contract["scientific_execution_authorized"] is False, "ratified rules do not bypass F0")
    require(contract["measurement_profile"] == MEASUREMENT_PROFILE and
            registry["profile"] == MEASUREMENT_PROFILE, "contract identity mismatch")
    for stage in STAGE_SEEDS:
        require(registry["scientific"][stage] == list(STAGE_SEEDS[stage])
                and registry["engineering"][stage] == list(ENGINEERING_KEYS[stage])
                and contract["scientific_seed_sets"][stage] == list(STAGE_SEEDS[stage])
                and contract["scientific_seeds"][stage] == list(STAGE_SEEDS[stage]), "key registry differs")
    keys=[key for stage in STAGE_SEEDS for key in (*STAGE_SEEDS[stage], *ENGINEERING_KEYS[stage])]
    exclusions=registry["permanent_exclusions"]
    require(len(keys) == len(set(keys)) == 74
            and not set(keys).intersection(exclusions["old_scientific"]), "keys collide with spent science")
    for low,high in exclusions["old_engineering_ranges"]+exclusions["operational_fixture_ranges"]:
        require(not any(low <= key <= high for key in keys), "keys collide with engineering/fixtures")
    require(registry["scientific"]["treatment"] is registry["scientific"]["confirmatory"] is None,
            "later collection must remain separately gated")
    branch=subprocess.check_output(["git","branch","--show-current"],cwd=ROOT,text=True).strip()
    require(branch == registration["branch"], "unexpected execution branch")


def main():
    code=2
    try:
        OP.mkdir(parents=True, exist_ok=True)
        publish_new(OP / "pipeline_claim.json",{"pid":os.getpid(),"claimed_at":now(),
            "root":str(ROOT),"automatic_retry":False,"measurement_profile":MEASUREMENT_PROFILE})
        sources=source_inventory(ROOT)
        assert_identity(sources)
        validate_registration()
        revision=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
        update_result_ledger("FROZEN_ONE_SHOT_FRESH_ACCEPTANCE_RUNNING")
        publish_new(OP / "frozen_inputs.json",{"sources":sources,"sources_digest":digest(canonical_bytes(sources)),
            "instrument_commit":revision,"constants":CONSTANTS,"stage_seeds":STAGE_SEEDS,
            "engineering_keys":ENGINEERING_KEYS,"scientific_execution_started":False})
        parent_before=parent_evidence()
        publish_new(OP / "parent_preservation.json",parent_before)
        gate_codes=run_gate_suite(ROOT, OP / "acceptance_gates")
        require(gate_codes == [0]*len(GATES),"A96 full acceptance gates failed")
        assert_identity(sources)
        counts=regression_counts(OP / "acceptance_gates/regression.xml")
        policy=benchmark_rmst_policy(ratified=True)
        review={"schema":"a96-source-bound-internal-review-v1","decision":"VALID",
            "sources_digest":digest(canonical_bytes(sources)),"instrument_commit":revision,
            "rmst_policy":policy,"reviewed_at":now(),"regression":counts,
            "gate_exit_codes":gate_codes,"measurement_profile":MEASUREMENT_PROFILE,
            "independent_agent_or_external_expert_review":False,
            "role":"INTERNAL_BOUND_ACCEPTANCE_NOT_F0_OR_SCIENTIFIC_RESULT",
            "semantic_changes":"Ratified A96 fixed full integer grid; consecutive-episode recovery and all q..T checkpoint-mean Retention. A95 horizon/other thresholds unchanged; exact parallel arithmetic and fresh full validation.",
            "old_reviews_runtime_or_data_migrated":False,"treatment_or_confirmation_authorized":False}
        publish_new(OP / "source_bound_review.json",review)
        paths=[str((OP / "source_bound_review.json").relative_to(ROOT))]
        paths += [p.relative_to(ROOT).as_posix() for p in (OP/"acceptance_gates").rglob("*") if p.is_file()]
        commit_files("A96-source-bound-internal-acceptance",paths)
        assert_identity(sources)
        py=[sys.executable,"-u","-B","-X","utf8"]
        runtime_dir=FOLDER / "f0_runtime"
        command("full_runtime",py+["scripts/benchmark_f0_runtime.py","--output-dir",str(runtime_dir)])
        runtime=read_json(runtime_dir/"runtime.json")
        validate_runtime(runtime,review["sources_digest"])
        regression_counts(runtime_dir/"gates/regression.xml")
        # Separate complete verification; full actual 32 shards, no curve-based design selection.
        command("runtime_full_verification",py+["scripts/verify_a96_baseline.py",
            "--index",str(runtime_dir/"baseline.json"),"--output",str(OP/"runtime_verified.json")])
        verified=read_json(OP/"runtime_verified.json")
        require(verified["status"] == "ALL_SHARDS_VERIFIED" and len(verified["shards"]) == 32
                and verified["records"] == 32*577,"incomplete engineering verification")
        assert_identity(sources)
        require(parent_evidence() == parent_before,"parent evidence changed during acceptance")
        manifest=build_manifest(ROOT,runtime=runtime,review=review,finalize=True)
        publish_new(ROOT / MANIFEST_PATH,manifest)
        f0_files=[MANIFEST_PATH,str((runtime_dir/"runtime.json").relative_to(ROOT)),
                  str((runtime_dir/"frozen_inputs.json").relative_to(ROOT)),
                  str((runtime_dir/"baseline.json").relative_to(ROOT)),
                  str((OP/"runtime_verified.json").relative_to(ROOT))]
        f0_files += [p.relative_to(ROOT).as_posix() for p in (OP/"runtime_verified").rglob("*") if p.is_file()]
        f0_files += list(GATE_PATHS)
        f0_files += [p.relative_to(ROOT).as_posix() for p in (runtime_dir/"gates").rglob("*") if p.is_file()]
        commit_files("A96-fresh-fully-verified-F0",f0_files)
        assert_identity(sources)
        command("formal_smoke",py+["scripts/run_smoke.py","--seeds-file",str(ROOT/SEED_PATHS["smoke"])])
        command("independent_smoke_evaluator",py+["experiments/v03r/evaluate_smoke_gate.py"])
        loaded,identity=load_manifest(ROOT,ROOT/MANIFEST_PATH,"dev_baseline")
        require(evaluate_smoke(read_json(ROOT/SMOKE_PATH),loaded,identity)["verdict"] == "PASS","smoke did not pass")
        command("development32",py+["scripts/run_dev_baseline.py","--seeds-file",str(ROOT/SEED_PATHS["dev_baseline"])])
        index=read_index(ROOT/ARTIFACT_SCHEMA["index"])
        require(index["seeds"] == list(STAGE_SEEDS["dev_baseline"]) and index["records"] == 32*577,"development incomplete")
        command("f1_plan",py+["scripts/run_dev_lock.py","--design",str(ROOT/ARTIFACT_SCHEMA["index"]),"--plan"])
        code=command("full_f1",py+["scripts/run_dev_lock.py","--design",str(ROOT/ARTIFACT_SCHEMA["index"])],allowed=(0,3))
        result=read_json(FOLDER/"f1_result.json")
        assert_identity(sources)
        require(parent_evidence() == parent_before,"parent evidence changed during scientific stages")
        classification=("F1_LOCKED_REQUIRES_SEPARATE_B2_GATE" if code == 0 else "VALID_PROTOCOL_STOP_NO_ADMISSIBLE_DESIGN")
        require((code == 0 and result["status"] == "LOCKED" and result["written"] is True)
                or (code == 3 and result["status"].startswith("NO_ADMISSIBLE") and result["written"] is False),
                "native exit/result classification mismatch")
        if code == 3:
            require(not (FOLDER/"dev_lock.json").exists(),"partial lock on inadmissible result")
        publish_new(OP/"pipeline_result.json",{"classification":classification,"native_f1_exit_code":code,
            "result":result,"completed_at":now(),"research_complete":False,
            "treatment_and_confirmatory_collected":False,"automatic_retry":False})
        update_result_ledger(classification,result=result,native_f1=code)
        if code == 3:
            report=("A96 VALID PROTOCOL STOP\n"+result["status"]+"\n"
                "Fresh smoke and complete development32 executed; full atomic F1 found no admissible design. "
                "No treatment or confirmation effect was measured. No cap/threshold/initializer change or retry is allowed under this freeze.\n"
                "Mechanism diagnostics are in pipeline_result.json; original A95/rev6 grid stop and rev5 stop are unchanged.\n")
            (OP/"PROTOCOL_STOP_REPORT.txt").write_text(report,encoding="utf-8")
        paths=[p.relative_to(ROOT).as_posix() for p in OP.rglob("*") if p.is_file()]
        paths.append("experiments/rebuild_status_current.json")
        paths += [SMOKE_PATH,STAGE_ROOT+"/smoke_attempt.json",ARTIFACT_SCHEMA["index"],
                  STAGE_ROOT+"/f1_plan_result.json",STAGE_ROOT+"/f1_result.json"]
        if (FOLDER/"dev_lock.json").exists(): paths.append(STAGE_ROOT+"/dev_lock.json")
        for name in ("smoke_gates","f1_plan","f1_execution"):
            paths += [p.relative_to(ROOT).as_posix() for p in (FOLDER/name).rglob("*") if p.is_file()]
        commit_files("A96-native-F1-evidence",paths)
    except BaseException as exc:
        if not (OP/"pipeline_failure.json").exists():
            publish_new(OP/"pipeline_failure.json",{"classification":"OPERATIONAL_OR_PROTOCOL_INVALID",
                "error_type":type(exc).__name__,"message":str(exc),"observed_at":now(),
                "native_controller_exit_expected":2,"scientific_fail_claimed":False,"automatic_retry":False})
        print(f"PIPELINE_INVALID {type(exc).__name__}: {exc}",flush=True)
        code=2
    return code


if __name__ == "__main__":
    raise SystemExit(main())
