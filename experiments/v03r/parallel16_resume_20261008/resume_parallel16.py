"""Explicitly authorized operational resume, no duplicate stop or automatic retry."""
import ctypes
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import xml.etree.ElementTree as ET

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
spec = importlib.util.spec_from_file_location("p16_resume_adapter", HERE / "continue_pipeline.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
p = runner.base
PWSH = pathlib.Path("C:/Users/huani/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/powershell/pwsh.exe")
UTF8_PREFIX = "$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); $OutputEncoding=[Console]::OutputEncoding;\n"


def native_observation(stage, body):
    """Keep raw bytes and a real receipt BEFORE strict decoding; no reader threads."""
    argv = [str(PWSH), "-NoProfile", "-NonInteractive", "-Command", UTF8_PREFIX + body]
    started = p.now()
    with (HERE / (stage + ".stdout.bin")).open("xb") as out, (HERE / (stage + ".stderr.bin")).open("xb") as err:
        try:
            result = subprocess.run(argv, cwd=ROOT, stdout=out, stderr=err, timeout=30)
        except subprocess.TimeoutExpired:
            p.publish_new(HERE / (stage + ".receipt.json"), {"role": "NATIVE_READ_ONLY_SHELL_EXIT",
                "stage": stage, "started_at": started, "finished_at": p.now(),
                "native_exit_code": None, "timeout": True, "no_automatic_retry": True})
            raise p.ProtocolError("native observation timed out; raw output preserved")
    receipt = {"role": "NATIVE_READ_ONLY_SHELL_EXIT", "stage": stage, "started_at": started,
        "finished_at": p.now(), "native_exit_code": result.returncode,
        "argv": argv, "stdout_sha256": p.digest((HERE / (stage + ".stdout.bin")).read_bytes()),
        "stderr_sha256": p.digest((HERE / (stage + ".stderr.bin")).read_bytes()), "no_automatic_retry": True}
    p.publish_new(HERE / (stage + ".receipt.json"), receipt)
    p.require(result.returncode == 0, "native observation failed; see preserved raw stderr")
    try:
        payload = json.loads((HERE / (stage + ".stdout.bin")).read_bytes().decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise p.ProtocolError("native UTF-8/JSON output invalid; raw output preserved") from error
    p.require(type(payload) is dict, "native observation must be an object")
    p.publish_new(HERE / (stage + ".observation.json"), payload)
    return payload


def require_no_competing_process():
    registration = p.read_json(HERE / "preregistration.json")
    roots = [str(ROOT), registration["preserved_r1_root"]]
    quoted = ",".join("'" + root.replace("/", "\\").replace("'", "''") + "'" for root in roots)
    body = "$roots=@(" + quoted + "); $self=" + str(os.getpid()) + "; " + """
$processes=@(Get-CimInstance Win32_Process | Where-Object {
    if ($_.Name -ne 'python.exe' -or $_.ProcessId -eq $self) { return $false }
    foreach ($root in $roots) { if ($_.CommandLine -like ('*'+$root+'*')) { return $true } }
    return $false
} | Select-Object ProcessId,ParentProcessId,CreationDate,CommandLine)
@{role='NATIVE_READ_ONLY_PROCESS_SNAPSHOT';observed_at=[DateTime]::UtcNow.ToString('o');processes=$processes;no_stop_performed=$true} | ConvertTo-Json -Depth 5 -Compress
"""
    payload = native_observation("parent_process_check", body)
    p.require(payload.get("role") == "NATIVE_READ_ONLY_PROCESS_SNAPSHOT"
              and payload.get("no_stop_performed") is True
              and payload.get("processes") == [], "competing R1/P16 process; no duplicate job")
    return payload


def memory_available():
    class Memory(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
            (name, ctypes.c_ulonglong) for name in ("total", "available", "total_page", "available_page",
                                                  "total_virtual", "available_virtual", "extended")]
    info = Memory()
    info.length = ctypes.sizeof(info)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(info)):
        raise ctypes.WinError()
    p.require(info.available >= 6 * 1024**3, "insufficient RAM for sixteen workers; no automatic fallback")
    return {"total_bytes": info.total, "available_bytes": info.available, "required_available_bytes": 6 * 1024**3}


def xml_counts(path):
    return {key: sum(int(s.get(key, "0")) for s in ET.parse(path).getroot().findall("testsuite"))
            for key in ("tests", "errors", "failures", "skipped")}


def validate_preparation():
    p.require(not (HERE / "control_claim.json").exists(), "resume already reserved; no retry")
    registration = p.read_json(HERE / "preregistration.json")
    preservation = runner.verify_parent_preserved()
    for name in p.FORMAL_OUTPUTS:
        p.require(not (ROOT / "experiments/v03r" / name).exists(), "formal reservation exists: " + name)
    p.require(not p.BENCHMARK.exists() and not p.MANIFEST.exists(), "new output reservation is not fresh")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    sources = p.source_inventory(ROOT)
    p.require(p._committed_sources(ROOT, head, tuple(sources)) == sources, "instrument not committed")
    controls = runner.control_inventory()
    paths = tuple((HERE / name).relative_to(ROOT).as_posix() for name in controls)
    p.require(p._committed_sources(ROOT, head, paths)
              == {path: controls[pathlib.Path(path).name] for path in paths}, "controller not committed")
    prior = p.read_json(ROOT / registration["exact_prior_instrument_review"])
    p.require(prior.get("decision") == "VALID" and prior["sources_digest"] == p.digest(p.canonical_bytes(sources)),
              "prior semantic review does not match identical instrument")
    p.validate_rmst_policy(prior["rmst_policy"])
    p.require(prior["checks"]["native_gate_exit_codes"] == [0]*6, "prior serial gates failed")
    for i in range(1, 7):
        receipt = p.read_json(ROOT / registration["prior_operation_folder"] / ("review_gate_"+str(i)+".receipt.json"))
        p.require(receipt["native_exit_code"] == 0, "native gate receipt is not passing")
    return sources, controls, head, prior, preservation


def main():
    try:
        sources, controls, head, prior, preservation = validate_preparation()
        p.publish_new(HERE / "control_claim.json", {"pid": os.getpid(), "started_at": p.now(), "head": head,
            "sources": sources, "sources_digest": p.digest(p.canonical_bytes(sources)),
            "source_count": len(sources), "operational_control_files": controls,
            "orchestrator_sha256": controls["resume_parallel16.py"], "runner_sha256": controls["continue_pipeline.py"],
            "stage_template_sha256": p.digest(runner.TEMPLATE.read_bytes()), "execution_profile": runner.EXECUTION_PROFILE})
        require_no_competing_process()
        p.publish_new(HERE / "parent_preservation_before_start.json", preservation)
        p.publish_new(HERE / "resource_preflight.json", {"observed_at": p.now(), **memory_available()})
        p.run_success("controller_checks", [sys.executable, "-B", "-X", "utf8", "-m", "pytest", "-q",
            ROOT / "experiments/v03r/restart_20261008/test_continue_pipeline.py",
            ROOT / "experiments/v03r/parallel16_20261008/test_control_parallel16.py",
            HERE / "test_resume_parallel16.py", "--junitxml", HERE / "controller_checks.xml"])
        checks = xml_counts(HERE / "controller_checks.xml")
        p.require(checks["tests"] >= 40 and checks["errors"] == checks["failures"] == checks["skipped"] == 0,
                  "resume controller/encoding checks not complete")
        p.require(runner.control_inventory() == controls and p.source_inventory(ROOT) == sources, "source drift during repair tests")
        report = {"role": "INTERNAL_SAME_INSTRUMENT_OPERATIONAL_REPAIR_REVIEW", "decision": "VALID",
            "reviewed_at": p.now(), "sources_digest": p.digest(p.canonical_bytes(sources)), "source_count": len(sources),
            "instrument_commit": head, "rmst_policy": prior["rmst_policy"], "execution_profile": runner.EXECUTION_PROFILE,
            "operational_control_files": controls, "stage_template_sha256": p.digest(runner.TEMPLATE.read_bytes()),
            "same_instrument_semantic_review": {"path": "experiments/v03r/parallel16_20261008/source_bound_parallel_review.json",
                                               "sha256": p.digest((ROOT / "experiments/v03r/parallel16_20261008/source_bound_parallel_review.json").read_bytes())},
            "fresh_native_controller_checks": checks, "prior_instrument_checks_not_claimed_fresh": prior["checks"],
            "fresh_regression_and_six_gates_required_in_pipeline": True,
            "external_review_performed": False, "independent_agent_review_performed": False,
            "formal_stages_authorized": [], "scientific_claims_authorized": [],
            "limitations": ["This is an internal exact-same-instrument operational repair review, not independent external review.",
                            "No old raw/runtime/F0/PASS is migrated. Fresh full37-key timing and committed F0 remain mandatory.",
                            "No historical stop identity is reconstructed. Both parents are already exited; this controller stops no process."]}
        p.publish_new(p.REVIEW, report)
        p.commit_exact([p.REVIEW, HERE / "controller_checks.xml", HERE / "controller_checks.receipt.json",
                        HERE / "parent_process_check.receipt.json", HERE / "parent_process_check.observation.json",
                        HERE / "parent_preservation_before_start.json", HERE / "resource_preflight.json"],
                       "Bind explicit P16 operational resume, native transport tests and preserved parent evidence")
        return p.pipeline()
    except Exception as exc:
        failure = {"status": "STOPPED_EXPLICIT_P16_RESUME_ERROR", "observed_at": p.now(),
            "error_type": type(exc).__name__, "error": str(exc), "no_automatic_retry": True,
            "scientific_superiority_claimed": False, "historical_stop_reconstructed": False}
        if not (HERE / "pipeline_failure.json").exists():
            p.publish_new(HERE / "pipeline_failure.json", failure)
        print(json.dumps(failure, ensure_ascii=False), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
