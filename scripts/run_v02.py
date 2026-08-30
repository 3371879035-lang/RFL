"""One strict entry point for the RFL-CausalChase v0.2 study tiers.

Exit codes are part of the study protocol:
0 = engineering and scientific gates pass; 2 = valid scientific FAIL;
3 = invalid configuration/probe/runtime/artifact; 4 = confirmatory refused.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

try:  # pragma: no cover - direct and package invocation paths
    from .capture_v02_reproducibility import capture_reproducibility
    from .v02_integrity import (
        OutputIntegrityError,
        canonical_config_hash,
        prepare_fresh_v02_output_dir,
        validate_a_output,
        validate_b_online_output,
        validate_b_transfer_output,
    )
    from .v02_preflight import PreflightError, run_preflight
except ImportError:  # pragma: no cover
    from capture_v02_reproducibility import capture_reproducibility
    from v02_integrity import (
        OutputIntegrityError,
        canonical_config_hash,
        prepare_fresh_v02_output_dir,
        validate_a_output,
        validate_b_online_output,
        validate_b_transfer_output,
    )
    from v02_preflight import PreflightError, run_preflight


EXIT_PASS = 0
EXIT_SCIENTIFIC_FAIL = 2
EXIT_INVALID = 3
EXIT_CONFIRMATORY_REFUSED = 4


def _read_config(path: Path) -> dict[str, Any]:
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(cfg, dict):
        raise OutputIntegrityError(f"config is not a YAML mapping: {path}")
    return cfg


def _run(command: list[str], root: Path, commands: list[dict[str, Any]]) -> int:
    started = time.perf_counter()
    completed = subprocess.run(command, cwd=root, check=False)
    commands.append({
        "command": command,
        "returncode": completed.returncode,
        "elapsed_s": round(time.perf_counter() - started, 3),
    })
    return completed.returncode


def _actual_benchmark(root: Path, outdir: Path, commands: list[dict[str, Any]]) -> dict[str, Any]:
    """Run the existing benchmark; do not substitute a metadata placeholder."""
    bench_dir = outdir / "benchmark_raw"
    code = _run(
        [sys.executable, "scripts/benchmark.py", "--steps", "10000", "--outdir", str(bench_dir)],
        root, commands,
    )
    if code != 0:
        raise OutputIntegrityError(f"benchmark failed with exit {code}")
    values: dict[str, float] = {}
    for line in (bench_dir / "benchmark.txt").read_text(encoding="utf-8").splitlines():
        key, value = line.split(maxsplit=1)
        values[key] = float(value)
    return {"kind": "real_benchmark", "steps": 10000, **values}


def _write_execution_manifest(outdir: Path, cfg: dict, statuses: dict[str, dict[int, str]]) -> None:
    exp = cfg["experiment"]
    rows = []
    for stage in ("A-attribution", "A-update", "B-transfer", "B-online"):
        for seed_index in range(int(exp["seeds"])):
            experiment_seed = int(exp["seed_base"]) + seed_index
            rows.append({
                "stage": stage,
                "seed_index": seed_index,
                "experiment_seed": experiment_seed,
                "scenario_seed": "",
                "status": statuses.get(stage, {}).get(seed_index, "missing"),
            })
    with (outdir / "execution_manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _transfer_statuses(outdir: Path, cfg: dict) -> dict[int, str]:
    statuses: dict[int, str] = {}
    for seed_index in range(int(cfg["experiment"]["seeds"])):
        seed = int(cfg["experiment"]["seed_base"]) + seed_index
        path = outdir / "b_transfer" / f"transfer_seed{seed}.json"
        if path.exists():
            statuses[seed_index] = str(json.loads(path.read_text(encoding="utf-8")).get("status", "missing"))
    return statuses


def _compare_confirmatory_config(pilot: dict, confirmatory: dict) -> None:
    """Only the preregistered sample-size/seed/A-count fields may differ."""
    import copy

    left, right = copy.deepcopy(pilot), copy.deepcopy(confirmatory)
    for cfg in (left, right):
        experiment = cfg["experiment"]
        for field in ("name", "seeds", "seed_base", "update_scenarios_per_type"):
            experiment.pop(field, None)
        cfg.get("experiment_a", {}).pop("update_scenarios_per_type", None)
    if left != right:
        raise OutputIntegrityError("confirmatory config differs from pilot outside preregistered sample-size fields")
    pilot_seeds = set(range(int(pilot["experiment"]["seed_base"]), int(pilot["experiment"]["seed_base"]) + int(pilot["experiment"]["seeds"])))
    confirm_seeds = set(range(int(confirmatory["experiment"]["seed_base"]), int(confirmatory["experiment"]["seed_base"]) + int(confirmatory["experiment"]["seeds"])))
    if pilot_seeds & confirm_seeds:
        raise OutputIntegrityError("pilot and confirmatory seed sets overlap")


def _pilot_gate_passed(path: Path) -> bool:
    report = json.loads((path / "gate_report.json").read_text(encoding="utf-8"))
    return report.get("primary_gate", {}).get("all_pass") is True and report.get("exit_code") == EXIT_PASS


def run_tier(*, tier: str, config_path: Path, outdir: Path, pilot_dir: Path | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    cfg = _read_config(config_path)
    exp = cfg.get("experiment", {})
    expected_name = f"v02_{tier}"
    if exp.get("name") != expected_name:
        raise OutputIntegrityError(f"{tier} requires experiment.name={expected_name!r}")
    if tier == "confirmatory":
        if pilot_dir is None or not (pilot_dir / "gate_report.json").is_file():
            return EXIT_CONFIRMATORY_REFUSED
        if not _pilot_gate_passed(pilot_dir):
            return EXIT_CONFIRMATORY_REFUSED
        pilot_cfg = _read_config(root / "configs" / "v02_pilot.yaml")
        _compare_confirmatory_config(pilot_cfg, cfg)

    prepared = prepare_fresh_v02_output_dir(outdir, project_root=root)
    commands: list[dict[str, Any]] = []
    statuses: dict[str, dict[int, str]] = {}
    report: dict[str, Any] = {
        "schema_version": "0.2.1",
        "tier": tier,
        "status": "running",
        "config_hash": canonical_config_hash(cfg),
        "config_file": str(config_path),
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "commands": commands,
    }
    try:
        report["preflight"] = run_preflight(root, config_path)
        shutil.copy2(config_path, prepared / "config.yaml")
        benchmark = _actual_benchmark(root, prepared, commands)
        report["reproducibility"] = capture_reproducibility(
            prepared / "reproducibility", project_root=root, config_paths=[config_path], benchmark=benchmark,
        )
        a_code = _run(
            [sys.executable, "scripts/experiment_a_v02.py", "--config", str(config_path), "--stage", "all", "--outdir", str(prepared / "a")],
            root, commands,
        )
        if a_code != 0:
            raise OutputIntegrityError(f"A stage exited {a_code}")
        statuses["A-attribution"] = {i: "completed" for i in range(int(exp["seeds"]))}
        statuses["A-update"] = dict(statuses["A-attribution"])
        validate_a_output(prepared / "a", cfg)

        transfer_code = _run(
            [sys.executable, "scripts/experiment_b_v02.py", "--config", str(config_path), "--stage", "transfer", "--outdir", str(prepared / "b_transfer")],
            root, commands,
        )
        statuses["B-transfer"] = _transfer_statuses(prepared, cfg)
        if transfer_code != 0:
            statuses["B-online"] = {}
            _write_execution_manifest(prepared, cfg, statuses)
            report.update({"status": "blocked_invalid_knowledge_probe", "exit_code": EXIT_INVALID})
            return EXIT_INVALID
        validate_b_transfer_output(prepared / "b_transfer", cfg)

        online_code = _run(
            [sys.executable, "scripts/experiment_b_v02.py", "--config", str(config_path), "--stage", "online", "--outdir", str(prepared / "b_online")],
            root, commands,
        )
        if online_code != 0:
            raise OutputIntegrityError(f"B-online stage exited {online_code}")
        statuses["B-online"] = {i: "completed" for i in range(int(exp["seeds"]))}
        validate_b_online_output(prepared / "b_online", cfg)
        analysis_code = _run(
            [sys.executable, "scripts/analyze_v02.py", "--dir", str(prepared), "--output", str(prepared / "analysis_v02.json")],
            root, commands,
        )
        if analysis_code not in (EXIT_PASS, EXIT_SCIENTIFIC_FAIL):
            raise OutputIntegrityError(f"strict analysis exited {analysis_code}")
        report["primary_gate"] = json.loads((prepared / "analysis_v02.json").read_text(encoding="utf-8"))["primary_gate"]
        report["exit_code"] = analysis_code
        report["status"] = "passed" if analysis_code == EXIT_PASS else "scientific_fail"
        _write_execution_manifest(prepared, cfg, statuses)
        return analysis_code
    except (OSError, ValueError, OutputIntegrityError, PreflightError) as exc:
        report.update({"status": "invalid", "error": str(exc), "exit_code": EXIT_INVALID})
        _write_execution_manifest(prepared, cfg, statuses)
        return EXIT_INVALID
    finally:
        report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        (prepared / "gate_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="strict v0.2 tier runner")
    parser.add_argument("--tier", choices=("smoke", "pilot", "confirmatory"), required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--outdir", required=True)
    parser.add_argument("--pilot-dir", help="completed pilot directory; required by confirmatory")
    args = parser.parse_args(argv)
    try:
        code = run_tier(
            tier=args.tier, config_path=Path(args.config).resolve(), outdir=Path(args.outdir).resolve(),
            pilot_dir=Path(args.pilot_dir).resolve() if args.pilot_dir else None,
        )
    except (OSError, OutputIntegrityError, PreflightError, ValueError) as exc:
        print(json.dumps({"status": "invalid", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return EXIT_INVALID
    print(json.dumps({"tier": args.tier, "exit_code": code}, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
