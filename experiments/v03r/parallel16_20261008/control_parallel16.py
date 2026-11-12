"""Once-only validation -> authenticated switch -> new-source P16 pipeline.

Preparation failures leave the serial R1 running. No scientific data is copied,
no worker is retried, no old source is edited and no external Git write occurs.
"""
import ctypes
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
spec = importlib.util.spec_from_file_location("p16_pipeline_adapter", HERE / "continue_pipeline.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
p = runner.base
from rfl_rebuild.b2.parallel_acquisition import EXECUTION_PROFILE

ALLOWED_DELTA = {
    "docs/rebuild/12-AMENDMENTS.md", "docs/rebuild/20-B2-DEV-PROTOCOL-FREEZE.md",
    "docs/rebuild/30-F0-STAGE-RUNNERS.md", "docs/rebuild/32-PARALLEL-SEED-EXECUTION.md",
    "scripts/benchmark_f0_runtime.py", "scripts/f0_manifest_selfcheck.py",
    "src/rfl_rebuild/b2/baseline_artifact.py", "src/rfl_rebuild/b2/f0_stages.py",
    "src/rfl_rebuild/b2/parallel_acquisition.py", "tests/rebuild/test_b2_f0_stages.py",
    "tests/rebuild/test_b2_parallel_acquisition.py",
}
PWSH = pathlib.Path("C:/Users/huani/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/powershell/pwsh.exe")


def xml_counts(path):
    counts = {key: sum(int(s.get(key, "0")) for s in ET.parse(path).getroot().findall("testsuite"))
              for key in ("tests", "errors", "failures", "skipped")}
    p.require(counts["tests"] > 0 and counts["errors"] == counts["failures"] == 0, "failing regression XML")
    return counts


def parent_snapshot():
    registration = p.read_json(HERE / "preregistration.json")
    parent = pathlib.Path(registration["preserved_root"])
    claim = p.read_json(parent / "experiments/v03r/restart_20261008/pipeline_claim.json")
    launch = p.read_json(parent / "experiments/v03r/restart_20261008/pipeline_launch.json")
    p.require(p.source_inventory(parent) == claim["sources"], "parent frozen source changed")
    for name in p.FORMAL_OUTPUTS:
        p.require(not (parent / "experiments/v03r" / name).exists(), "parent scientific reservation exists; new seed decision required")
    source = ROOT / "experiments/v03r/smoke_seeds.txt"
    p.require(p.digest(source.read_bytes()) == p.digest((parent / "experiments/v03r/smoke_seeds.txt").read_bytes()),
              "scientific smoke seed file changed")
    return parent, claim, launch


def memory_available():
    class Memory(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
            (name, ctypes.c_ulonglong) for name in ("total", "available", "total_page", "available_page",
                                                  "total_virtual", "available_virtual", "extended")]
    info = Memory()
    info.length = ctypes.sizeof(info)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(info)):
        raise ctypes.WinError()
    p.require(info.available >= 6 * 1024**3, "insufficient available RAM for fixed sixteen workers; no automatic worker-count fallback")
    return {"total_bytes": info.total, "available_bytes": info.available, "required_available_bytes": 6 * 1024**3}


def validate_preparation():
    p.require(not (HERE / "control_claim.json").exists(), "preparation already reserved; no retry")
    parent_snapshot()
    sources = p.source_inventory(ROOT)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    p.require(p._committed_sources(ROOT, head, tuple(sources)) == sources, "P16 sources are not committed")
    registration = p.read_json(HERE / "preregistration.json")
    p.require(p.canonical_bytes(registration["execution_profile"]) == p.canonical_bytes(EXECUTION_PROFILE),
              "registered profile changed")
    old_paths = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", registration["parent_commit"]], cwd=ROOT, text=True).splitlines()
    existing = tuple(name for name in sources if name in old_paths)
    old = p._committed_sources(ROOT, registration["parent_commit"], existing)
    changed = {name for name in sources if name not in old or old[name] != sources[name]}
    p.require(changed == ALLOWED_DELTA, "unexpected P16 instrument delta: " + repr(sorted(changed)))
    return sources, head, old, changed


def prepare_review(sources, head, old, changed):
    p.run_success("review_full_regression", [sys.executable, "-B", "-X", "utf8", "-m", "pytest",
                                             "--junitxml", HERE / "review_full_regression.xml"])
    p.run_success("review_controller_checks", [sys.executable, "-B", "-X", "utf8", "-m", "pytest",
        ROOT / "experiments/v03r/restart_20261008/test_continue_pipeline.py", HERE / "test_control_parallel16.py",
        "--junitxml", HERE / "review_controller_checks.xml"])
    codes = []
    for i, gate in enumerate(__import__("rfl_rebuild.b2.f0_stages", fromlist=["GATES"]).GATES, 1):
        code = p.command(f"review_gate_{i}", [sys.executable, "-B", "-X", "utf8", *gate["argv"][1:]])
        p.require(code == 0, f"P16 review gate {i} failed")
        p.require(p.source_inventory(ROOT) == sources, "review gate did not restore P16 sources")
        codes.append(code)
    selfcheck = p.read_json(ROOT / "experiments/v03r/f0_manifest_selfcheck.json")
    p.require(selfcheck.get("verdict") == "PASS" and selfcheck.get("n_rejected") == 35, "P16 contract selfcheck failed")
    prior = p.read_json(ROOT / "experiments/v03r/restart_20261008/source_bound_restart_review.json")
    p.validate_rmst_policy(prior["rmst_policy"])
    report = {"role": "INTERNAL_SOURCE_BOUND_PARALLEL_EXECUTION_REVIEW", "decision": "VALID",
        "reviewed_at": p.now(), "instrument_commit": head, "source_count": len(sources),
        "sources_digest": p.digest(p.canonical_bytes(sources)), "execution_profile": EXECUTION_PROFILE,
        "preregistration_sha256": p.digest((HERE / "preregistration.json").read_bytes()),
        "checks": {"regression": xml_counts(HERE / "review_full_regression.xml"),
                   "controller": xml_counts(HERE / "review_controller_checks.xml"), "native_gate_exit_codes": codes},
        "delta": {name: {"parent_sha256": old.get(name), "parallel_sha256": sources[name]} for name in sorted(changed)},
        "gate_artifact_sha256": {name: p.digest((ROOT / name).read_bytes()) for name in p.GATE_PATHS},
        "rmst_policy": prior["rmst_policy"], "independent_agent_review_performed": False,
        "external_review_performed": False, "review_method": "Single-agent implementation and internal source-bound audit with real spawn and exact-byte parent-equivalence tests; not independent external methodological review.",
        "formal_stages_authorized": [], "scientific_claims_authorized": [],
        "limitations": ["Fixtures cannot replace complete new-source 37-key timing.",
                        "Prior source review and serial raw authorize neither this source nor scientific efficacy.",
                        "Sixteen workers is a fixed user-authorized engineering choice, not an outcome-selected design.",
                        "Quantitative 1.5 RMST benchmark only; no practical value, equivalence or zero-harm claim."]}
    p.publish_new(runner.base.REVIEW, report)
    p.commit_exact([runner.base.REVIEW, HERE / "review_full_regression.xml", HERE / "review_controller_checks.xml",
                   HERE / "review_full_regression.receipt.json", HERE / "review_controller_checks.receipt.json",
                   *[HERE / f"review_gate_{i}.receipt.json" for i in range(1, 7)]],
                  "Bind internally reviewed sixteen-process source and serial native gates")
    return report


def controlled_switch():
    parent, claim, launch = parent_snapshot()
    p.publish_new(HERE / "switch_claim.json", {"observed_at": p.now(), "parent_controller_pid": launch["pid"],
        "parent_start_utc_ticks": launch["start_utc_ticks"], "role": "USER_AUTHORIZED_P16_SWITCH_NO_RETRY"})
    # Authenticate the controller and its unique benchmark child again in the same
    # native shell immediately before terminating ONLY that child. R1 then receives
    # the genuine native child exit, records its own failure and exits naturally.
    script = """$ErrorActionPreference='Stop'
$parentMeta='{meta}'
$launch=Get-Content -LiteralPath (Join-Path $parentMeta 'pipeline_launch.json') -Raw -Encoding UTF8 | ConvertFrom-Json -AsHashtable
$controller=Get-Process -Id $launch.pid -ErrorAction Stop
if ($controller.StartTime.ToUniversalTime().Ticks -ne $launch.start_utc_ticks) {{ throw 'Parent start mismatch' }}
$native=Get-CimInstance Win32_Process -Filter ('ProcessId='+$launch.pid)
if ($native.CommandLine -notlike '*restart_20261008*continue_pipeline.py*') {{ throw 'Parent command mismatch' }}
$children=@(Get-CimInstance Win32_Process | Where-Object {{ $_.ParentProcessId -eq $launch.pid -and $_.Name -eq 'python.exe' }})
if ($children.Count -ne 1 -or $children[0].CommandLine -notlike '*benchmark_f0_runtime.py*f0_runtime_restart_20261008*') {{ throw 'Not the expected R1 benchmark stage' }}
$child=Get-Process -Id $children[0].ProcessId -ErrorAction Stop
$observed=@{{child_pid=$child.Id; child_started_at=$child.StartTime.ToUniversalTime().ToString('o'); controller_pid=$launch.pid; command=$children[0].CommandLine}}
Stop-Process -Id $child.Id -ErrorAction Stop
Wait-Process -Id $launch.pid -Timeout 60 -ErrorAction Stop
$observed | ConvertTo-Json -Compress
""".format(meta=str(parent / "experiments/v03r/restart_20261008").replace("'", "''"))
    native = subprocess.run([str(PWSH), "-NoProfile", "-NonInteractive", "-Command", script],
                            capture_output=True, text=True, timeout=70)
    p.require(native.returncode == 0, "controlled switch could not confirm native parent exit: " + native.stderr)
    identity = json.loads(native.stdout)
    meta = parent / "experiments/v03r/restart_20261008"
    deadline = time.monotonic() + 15
    while not (meta / "pipeline_exit.json").exists() and time.monotonic() < deadline:
        time.sleep(.2)
    p.require((meta / "pipeline_exit.json").is_file(), "parent launcher native exit receipt missing")
    paths = [path for path in meta.rglob("*") if path.is_file()]
    benchmark = parent / "experiments/v03r/f0_runtime_restart_20261008"
    paths += [path for path in benchmark.rglob("*") if path.is_file()]
    observation = {"role": "EXTERNAL_AUTHORIZED_SWITCH_OBSERVATION", "observed_at": p.now(),
        "reason": "User-authorized sixteen-process cutover after valid P16 construction and serial gates",
        "authenticated_native_stop": identity, "parent_native_exit": p.read_json(meta / "pipeline_exit.json"),
        "preserved_files": {path.relative_to(parent).as_posix(): p.digest(path.read_bytes()) for path in sorted(paths)},
        "partial_old_shards_not_imported": True, "scientific_completion_claimed": False,
        "outcome_metrics_read": False, "automatic_retry": False}
    p.publish_new(HERE / "parent_switch_observation.json", observation)
    runner.verify_parent_preserved()
    return observation


def main():
    try:
        sources, head, old, changed = validate_preparation()
        p.publish_new(HERE / "control_claim.json", {"pid": os.getpid(), "started_at": p.now(),
            "head": head, "sources_digest": p.digest(p.canonical_bytes(sources)), "sources": sources,
            "orchestrator_sha256": p.digest(pathlib.Path(__file__).read_bytes()),
            "runner_sha256": p.digest((HERE / "continue_pipeline.py").read_bytes()),
            "stage_template_sha256": p.digest(runner.TEMPLATE.read_bytes()), "execution_profile": EXECUTION_PROFILE})
        prepare_review(sources, head, old, changed)
        memory = memory_available()
        controlled_switch()
        p.publish_new(HERE / "resource_preflight.json", {"observed_at": p.now(), **memory})
        return p.pipeline()
    except Exception as exc:
        failure = {"status": "STOPPED_P16_PREPARATION_OR_PIPELINE_ERROR", "observed_at": p.now(),
                   "error_type": type(exc).__name__, "error": str(exc), "no_automatic_retry": True,
                   "parent_switch_recorded": (HERE / "parent_switch_observation.json").exists(),
                   "scientific_superiority_claimed": False}
        if not (HERE / "pipeline_failure.json").exists():
            p.publish_new(HERE / "pipeline_failure.json", failure)
        print(json.dumps(failure, ensure_ascii=False), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
