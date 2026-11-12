"""One authorized verification-only handover; frozen instrument bytes unchanged."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PARENT = ROOT / "experiments/v03r/parallel16_resume_20261008"
spec = importlib.util.spec_from_file_location("unchanged_p16_adapter", PARENT / "continue_pipeline.py")
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)
p = adapter.base
p.HERE = HERE
p.REVIEW = HERE / "source_bound_verification_review.json"
p.MANIFEST = HERE / "f0_manifest_parallel_verify.json"
PWSH = "C:/Users/huani/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/powershell/pwsh.exe"
CONTROL_FILES = ("continue_verified.py", "parallel_verify.py", "test_parallel_verify.py",
                 "launch_detached.ps1", "preregistration.json")


def controls():
    return {name: p.digest((HERE / name).read_bytes()) for name in CONTROL_FILES}


def no_formal():
    for name in p.FORMAL_OUTPUTS:
        p.require(not (ROOT / "experiments/v03r" / name).exists(), "formal reservation exists: " + name)


def context():
    reg = p.read_json(HERE / "preregistration.json")
    p.require(Path(reg["root"]).resolve() == ROOT and ROOT / reg["parent_folder"] == PARENT
              and ROOT / reg["benchmark_folder"] == p.BENCHMARK, "registered paths changed")
    claim = p.read_json(PARENT / "pipeline_claim.json")
    sources = p.source_inventory(ROOT)
    p.require(len(sources) == reg["source_count"] and sources == claim["sources"]
              and p.digest(p.canonical_bytes(sources)) == reg["expected_sources_digest"], "instrument drift")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    p.require(p._committed_sources(ROOT, head, tuple(sources)) == sources, "uncommitted instrument")
    op = controls()
    names = tuple((HERE / name).relative_to(ROOT).as_posix() for name in op)
    p.require(p._committed_sources(ROOT, head, names) == {name: op[Path(name).name] for name in names},
              "uncommitted operational wrapper")
    p.require(reg["instrument_changes"] is False and reg["validation_reduction"] is False
              and reg["scientific_parameter_changes"] is False and reg["max_workers"] == 16
              and reg["automatic_retry"] is False, "operational boundary changed")
    for name, expected in claim["operational_control_files"].items():
        p.require(p.digest((PARENT / name).read_bytes()) == expected, "parent controller drift")
    p.require(p.digest(adapter.TEMPLATE.read_bytes()) == claim["stage_template_sha256"], "template drift")
    review = p.read_json(PARENT / "source_bound_resume_review.json")
    p.require(p.digest((PARENT / "source_bound_resume_review.json").read_bytes()) == claim["review_sha256"]
              and review["decision"] == "VALID" and review["sources_digest"] == reg["expected_sources_digest"],
              "exact-source review mismatch")
    p.validate_rmst_policy(review["rmst_policy"])
    for stage in ("full_regression", "benchmark"):
        p.require(p.read_json(PARENT / (stage + ".receipt.json"))["native_exit_code"] == 0,
                  "same-instrument native prerequisite failed")
    frozen = p.read_json(p.BENCHMARK / "frozen_inputs.json")
    runtime = p.read_json(p.BENCHMARK / "runtime.json")
    index = p.read_index(p.BENCHMARK / "baseline.json")
    p.require(frozen["sources"] == sources and frozen["sources_digest"] == reg["expected_sources_digest"],
              "benchmark instrument differs; no migration allowed")
    p.require(p._committed_sources(ROOT, frozen["instrument_commit"], tuple(sources)) == sources,
              "benchmark original committed source differs")
    gates = {name: p.digest((ROOT / name).read_bytes()) for name in p.GATE_PATHS}
    check = importlib.util.spec_from_file_location("frozen_runtime_metadata_checker",
        ROOT / "experiments/v03r/amendment_20260927/inspect_runtime_rev5.py")
    inspector = importlib.util.module_from_spec(check)
    check.loader.exec_module(inspector)
    inspector.verify_metadata(frozen, runtime, index, gates)
    p.require(frozen["execution_profile"] == adapter.EXECUTION_PROFILE
              == index["execution"]["execution_profile"], "execution profile differs")
    adapter.verify_parent_preserved()
    return {"sources": sources, "sources_digest": frozen["sources_digest"], "source_count": len(sources),
            "head": head, "operational_control_files": op, "rmst_policy": review["rmst_policy"],
            "prior_review_sha256": claim["review_sha256"], "original_instrument_commit": frozen["instrument_commit"],
            "runtime_sha256": p.digest((p.BENCHMARK / "runtime.json").read_bytes()),
            "index_sha256": p.digest((p.BENCHMARK / "baseline.json").read_bytes()), "gates": gates}


def parent_handover():
    """Native process identity and last-moment no-draw guards; no source edits."""
    reg = p.read_json(HERE / "preregistration.json")
    launch = p.read_json(PARENT / "pipeline_launch.json")
    p.require(launch["start_utc_ticks"] == reg["expected_parent_start_utc_ticks"], "parent start changed")
    p.require(p.digest(Path(launch["controller"]).read_bytes()) == reg["expected_parent_controller_sha256"],
              "parent controller identity changed")
    quoted = lambda value: "'" + str(value).replace("'", "''") + "'"
    body = "\n".join([
        "$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); $OutputEncoding=[Console]::OutputEncoding;",
        "$rflParent=" + quoted(PARENT) + "; $rflRoot=" + quoted(ROOT) + "; $rflId=" + str(launch["pid"]) + ";",
        "$rflCim=Get-CimInstance Win32_Process -Filter ('ProcessId = '+$rflId);",
        "$rflProcess=Get-Process -Id $rflId -ErrorAction Stop;",
        "if ($rflProcess.StartTime.ToUniversalTime().Ticks -ne " + str(launch["start_utc_ticks"]) + ") { throw 'Parent PID identity changed' };",
        "$rflExpected='\"D:\\python\\python.exe\" -u -B -X utf8 \"'+" + quoted(launch["controller"]) + "+'\"';",
        "if ($rflCim.CommandLine -cne $rflExpected) { throw 'Parent full command differs' };",
        "$rflFormal=@('smoke_attempt.json','smoke_report.json','dev_baseline','dev_baseline.json','dev_lock.json');",
        "foreach($rflName in $rflFormal){if(Test-Path -LiteralPath (Join-Path $rflRoot ('experiments\\v03r\\'+$rflName))){throw 'Formal reservation appeared; do not switch'}};",
        "if(Test-Path -LiteralPath (Join-Path $rflParent 'runtime_completion_verified.json')){throw 'Parent advanced; do not switch'};",
        "$rflTail=Get-Content -LiteralPath (Join-Path $rflParent 'pipeline.stdout.log') -Tail 1 -Encoding utf8;",
        "if($rflTail -notlike 'START full_runtime_integrity *'){throw 'Parent is not at read-only verification'};",
        "$rflChildren=@(Get-CimInstance Win32_Process | Where-Object {$_.ParentProcessId -eq $rflId -and $_.Name -eq 'python.exe'});",
        "if($rflChildren.Count -ne 0){throw 'Parent has a Python child; no switch'};",
        "$rflIdentity=@{pid=$rflId;start_utc_ticks=$rflProcess.StartTime.ToUniversalTime().Ticks;command=$rflCim.CommandLine};",
        "Stop-Process -InputObject $rflProcess -Force -ErrorAction Stop;",
        "$rflProcess.WaitForExit(10000) | Out-Null;",
        "@{role='EXTERNAL_AUTHENTICATED_READ_ONLY_VERIFICATION_INTERRUPTION';identity=$rflIdentity;observed_at=[DateTime]::UtcNow.ToString('o');stopped=$true;parent_native_completion_claimed=$false} | ConvertTo-Json -Depth 5 -Compress",
    ])
    p.run_success("parent_handover", [PWSH, "-NoProfile", "-NonInteractive", "-Command", body])
    observation = p.read_json(HERE / "parent_handover.stdout.log")
    p.require(observation["stopped"] is True, "parent stop unconfirmed")
    p.publish_new(HERE / "parent_interruption.json", observation)
    deadline = time.monotonic() + 30
    while not (PARENT / "pipeline_exit.json").exists() and time.monotonic() < deadline:
        time.sleep(.2)
    exit_receipt = p.read_json(PARENT / "pipeline_exit.json")
    p.require(exit_receipt["pid"] == launch["pid"] and exit_receipt["start_utc_ticks"] == launch["start_utc_ticks"]
              and exit_receipt["native_exit_code"] is not None, "true parent launcher exit missing")
    no_formal()
    # Preserve all old operation and completed benchmark bytes, never edit them.
    preserved = {}
    for directory in (PARENT, p.BENCHMARK):
        for path in directory.rglob("*"):
            if path.is_file():
                from parallel_verify import file_digest
                preserved[path.relative_to(ROOT).as_posix()] = file_digest(path)
    p.publish_new(HERE / "parent_preservation.json", {"files": preserved,
        "native_parent_exit": exit_receipt, "role": "EXTERNAL_PRESERVATION_NOT_PARENT_COMPLETION"})


def continue_science(identity):
    p.run_success("finalize_manifest", [sys.executable, "-B", "-X", "utf8", "scripts/f0_manifest.py",
        "--finalize", "--runtime", p.BENCHMARK / "runtime.json", "--review", p.REVIEW, "--output", p.MANIFEST])
    manifest_commit = p.commit_exact([p.MANIFEST, HERE / "runtime_completion_verified.json",
        HERE / "parallel_verification.json", p.BENCHMARK / "runtime.json", p.BENCHMARK / "baseline.json",
        p.BENCHMARK / "frozen_inputs.json", HERE / "parent_interruption.json", HERE / "parent_preservation.json"],
        "Bind exact-instrument completed timing and full parallel verification before F0")
    no_formal()
    p.load_manifest(ROOT, p.MANIFEST, "smoke")
    p.run_success("smoke", [sys.executable, "-u", "-B", "-X", "utf8", "scripts/run_smoke.py",
        "--seeds-file", ROOT / "experiments/v03r/smoke_seeds.txt", "--manifest", p.MANIFEST])
    p.run_success("evaluate_smoke", [sys.executable, "-B", "-X", "utf8",
        "experiments/v03r/evaluate_smoke_gate.py", "--manifest", p.MANIFEST])
    manifest, manifest_hash = p.load_manifest(ROOT, p.MANIFEST, "dev_baseline")
    p.require_smoke(ROOT, manifest, manifest_hash)
    p.run_success("development", [sys.executable, "-u", "-B", "-X", "utf8", "scripts/run_dev_baseline.py",
        "--seeds-file", ROOT / "experiments/v03r/dev_seeds.txt", "--manifest", p.MANIFEST])
    p.run_success("design_lock_plan", [sys.executable, "-B", "-X", "utf8", "scripts/run_dev_lock.py",
        "--design", ROOT / "experiments/v03r/dev_baseline.json", "--manifest", p.MANIFEST, "--plan"])
    code = p.command("design_lock", [sys.executable, "-u", "-B", "-X", "utf8", "scripts/run_dev_lock.py",
        "--design", ROOT / "experiments/v03r/dev_baseline.json", "--manifest", p.MANIFEST])
    payload = p.read_json(HERE / "design_lock.stdout.log")
    status = p.classify_lock(code, payload)
    lock = ROOT / "experiments/v03r/dev_lock.json"
    if status == "VALID_PROTOCOL_STOP_NO_ADMISSIBLE_DESIGN":
        p.require(not lock.exists(), "NO_ADMISSIBLE published a partial lock")
        lock_commit = None
    else:
        p.require(lock.is_file() and p.read_json(lock)["status"] == "LOCKED", "F1 missing")
        lock_commit = p.commit_exact([lock], "Freeze complete indivisible F1 lock")
    p.publish_new(HERE / "pipeline_result.json", {"status": status, "completed_at": p.now(),
        "manifest_commit": manifest_commit, "f1_commit": lock_commit, "native_design_lock_exit": code,
        "formal_smoke_passed": True, "development_seeds": 32, "development_records": 18464,
        "treatment_curves_run": False, "confirmatory_run": False, "scientific_superiority_claimed": False})
    return 3 if lock_commit is None else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()
    claimed = False
    try:
        no_formal()
        p.require(not (HERE / "control_claim.json").exists(), "exclusive handover already reserved; no retry")
        identity = context()
        if args.plan:
            print(json.dumps({"status": "READY", "written": False, "sources_digest": identity["sources_digest"]}))
            return 0
        p.publish_new(HERE / "control_claim.json", {"pid": __import__("os").getpid(), "started_at": p.now(), **identity})
        claimed = True
        p.run_success("wrapper_checks", [sys.executable, "-B", "-X", "utf8", "-m", "pytest", "-q",
            HERE / "test_parallel_verify.py", "--junitxml", HERE / "wrapper_checks.xml"])
        suites = ET.parse(HERE / "wrapper_checks.xml").getroot().findall("testsuite")
        counts = {name: sum(int(s.get(name, "0")) for s in suites) for name in ("tests", "errors", "failures", "skipped")}
        p.require(counts["tests"] >= 12 and counts["errors"] == counts["failures"] == counts["skipped"] == 0,
                  "parallel validation tests failed")
        p.require(context() == identity, "wrapper checks changed input identity")
        review = {"decision": "VALID", "role": "INTERNAL_SAME_INSTRUMENT_PARALLEL_VERIFICATION_REVIEW",
            "sources_digest": identity["sources_digest"], "source_count": 295, "rmst_policy": identity["rmst_policy"],
            "original_instrument_commit": identity["original_instrument_commit"],
            "prior_semantic_review": {"path": str(PARENT / "source_bound_resume_review.json"),
                                      "sha256": identity["prior_review_sha256"]},
            "operational_control_files": controls(), "fresh_wrapper_checks": counts,
            "same_instrument_native_prerequisites_not_claimed_fresh": ["full_regression", "benchmark"],
            "independent_agent_review_performed": False, "external_review_performed": False,
            "scientific_claims_authorized": [], "validation_reduced": False,
            "runtime_original_bytes_preserved": True, "reviewed_at": p.now()}
        p.publish_new(p.REVIEW, review)
        p.commit_exact([p.REVIEW, HERE / "wrapper_checks.xml", HERE / "wrapper_checks.receipt.json"],
            "Review read-only parallel validation on identical frozen instrument")
        # A metadata-only Git commit may advance HEAD; the instrument and all inputs must stay equal.
        after = context()
        p.require({k:v for k,v in after.items() if k != "head"} == {k:v for k,v in identity.items() if k != "head"},
                  "source or evidence changed before handover")
        parent_handover()
        p.publish_new(HERE / "pipeline_claim.json", {"pid": __import__("os").getpid(),
            "started_at": p.now(), "role": "POST_ACQUISITION_READ_ONLY_VERIFICATION_HANDOVER", **after})
        p.run_success("parallel_verification", [sys.executable, "-u", "-B", "-X", "utf8",
            HERE / "parallel_verify.py", "--index", p.BENCHMARK / "baseline.json",
            "--output", HERE / "parallel_verification.json"])
        verified = p.read_json(HERE / "parallel_verification.json")
        p.require(verified["status"] == "ALL_SHARDS_VERIFIED" and len(verified["shards"]) == 32
                  and verified["records"] == 18464 and verified["index_sha256"] == identity["index_sha256"],
                  "full verification incomplete")
        final = context()
        p.require({k:v for k,v in final.items() if k != "head"} == {k:v for k,v in identity.items() if k != "head"},
                  "instrument/runtime/gates changed during verification")
        from parallel_verify import file_digest
        preserved = p.read_json(HERE / "parent_preservation.json")["files"]
        p.require(all(file_digest(ROOT / name) == value for name, value in preserved.items()), "preserved evidence drift")
        p.publish_new(HERE / "runtime_completion_verified.json", {"status": "MEASURED_AND_VERIFIED",
            "observed_at": p.now(), "all_shards_verified": True, "verified_dev_runs": 32,
            "dev_records": 18464, "smoke_records": 2885, "runtime_sha256": identity["runtime_sha256"],
            "index_sha256": identity["index_sha256"], "instrument_commit": identity["original_instrument_commit"],
            "sources_digest": identity["sources_digest"], "metrics_computed": False, "f0_valid": False,
            "verification_receipt_sha256": p.digest((HERE / "parallel_verification.json").read_bytes()),
            "verification_max_workers": 16, "validator": "unchanged-frozen-_shard_records"})
        return continue_science(identity)
    except Exception as exc:
        failure = {"status": "STOPPED_PARALLEL_VERIFICATION_OR_HANDOVER", "observed_at": p.now(),
            "error_type": type(exc).__name__, "error": str(exc), "automatic_retry": False,
            "scientific_completion_claimed": False}
        if claimed and not (HERE / "pipeline_failure.json").exists():
            p.publish_new(HERE / "pipeline_failure.json", failure)
        print(json.dumps(failure, ensure_ascii=False), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
