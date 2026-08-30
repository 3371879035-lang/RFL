"""Strict, bounded v0.2 smoke gate.

The smoke runner intentionally creates a fresh ``outputs/v02_smoke_*``
directory on every invocation. It never appends to a prior result directory,
and it validates the artifacts from the A and B entry points before declaring
the gate passed. B-online is excluded by design: its 5,000-episode learning
comparison belongs to pilot after this bounded gate has passed.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

try:  # Support direct script execution and package-style tests.
    from .capture_v02_reproducibility import capture_reproducibility
    from .v02_integrity import (
        OutputIntegrityError,
        canonical_config_hash,
        prepare_fresh_v02_output_dir,
        validate_smoke_output,
    )
except ImportError:  # pragma: no cover - direct invocation branch
    from capture_v02_reproducibility import capture_reproducibility
    from v02_integrity import (
        OutputIntegrityError,
        canonical_config_hash,
        prepare_fresh_v02_output_dir,
        validate_smoke_output,
    )


SMOKE_BUDGETS = {
    "seeds": 2,
    "attribution_per_cause": 5,
    "update_scenarios_per_type": 3,
    "pretrain_episodes": 200,
    "shocks": 4,
    "recovery_episodes": 50,
    "online_episodes": 300,
}
SMOKE_ALGORITHMS = {
    "standard", "immediate", "er5", "pe_seq", "cf_only", "full_rfl",
    "rfl_observe", "oracle_update", "full_rfl_cfcritical",
}


def _load_config(path: Path) -> dict[str, Any]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise OutputIntegrityError(f"configuration is not a YAML object: {path}")
    if config.get("schema_version") != "0.2.0":
        raise OutputIntegrityError("smoke requires a v0.2 configuration")
    semantics = config.get("diagnostic_update_semantics", config.get("learning", {}).get("diagnostic_update_semantics"))
    if semantics != "scaled_additive":
        raise OutputIntegrityError("smoke requires scaled_additive diagnostic updates")
    experiment = config.get("experiment")
    if not isinstance(experiment, dict):
        raise OutputIntegrityError("smoke configuration has no experiment block")
    for name, expected in SMOKE_BUDGETS.items():
        if experiment.get(name) != expected:
            raise OutputIntegrityError(
                f"bounded smoke requires experiment.{name}={expected}, got {experiment.get(name)!r}"
            )
    if set(experiment.get("algorithms", [])) != SMOKE_ALGORITHMS:
        raise OutputIntegrityError("smoke must exercise the complete v0.2 algorithm set")
    if experiment.get("feedback", {}).get("p_false_symmetric") != 0.40:
        raise OutputIntegrityError("smoke requires p_false_symmetric=0.40")
    return config


def _run(command: list[str], *, root: Path, commands: list[dict[str, Any]]) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src") + os.pathsep + env.get("PYTHONPATH", "")
    started = time.perf_counter()
    print("[v0.2 smoke]", " ".join(command), flush=True)
    completed = subprocess.run(command, cwd=str(root), env=env, check=False)
    record = {
        "command": command,
        "returncode": completed.returncode,
        "elapsed_s": round(time.perf_counter() - started, 3),
    }
    commands.append(record)
    if completed.returncode != 0:
        raise OutputIntegrityError(
            f"gate command failed with exit {completed.returncode}: {' '.join(command)}"
        )


def _write_meta(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _default_outdir(root: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return root / "outputs" / f"v02_smoke_{stamp}_{os.getpid()}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="run the bounded, strict RFL-CausalChase v0.2 smoke gate")
    parser.add_argument("--config", required=True)
    parser.add_argument(
        "--stage", choices=("all", "router", "metrics", "scenarios", "experiments"), default="all",
    )
    parser.add_argument(
        "--outdir",
        help="new, empty outputs/v02_* directory; default is a timestamped v02_smoke_* directory",
    )
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = (root / config_path).resolve()
    if not config_path.is_file():
        print(json.dumps({"status": "failed", "error": f"configuration not found: {config_path}"}, ensure_ascii=False))
        return 2

    try:
        config = _load_config(config_path)
        outdir = prepare_fresh_v02_output_dir(args.outdir or _default_outdir(root), project_root=root)
    except (OSError, OutputIntegrityError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 2

    started_wall = time.time()
    commands: list[dict[str, Any]] = []
    meta: dict[str, Any] = {
        "schema_version": "0.2.0",
        "runner": "smoke_v02",
        "requested_stage": args.stage,
        "status": "running",
        "outdir": str(outdir),
        "config_source": str(config_path),
        "config_hash": canonical_config_hash(config),
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "commands": commands,
        "online_executed": False,
    }
    try:
        # Store the frozen source rather than relying on a mutable path outside
        # the run directory; the reproducibility envelope records both hashes.
        shutil.copy2(config_path, outdir / "config.yaml")
        reproducibility = capture_reproducibility(
            outdir / "reproducibility",
            project_root=root,
            config_paths=[config_path],
            stages=("A-attribution", "A-update", "B-transfer"),
            benchmark={"runner": "smoke_v02", "requested_stage": args.stage},
        )
        meta["git_commit"] = reproducibility["git_commit"]
        meta["reproducibility"] = reproducibility

        if args.stage in ("all", "router"):
            _run(
                [sys.executable, "-m", "pytest", "tests/test_router.py", "tests/test_router_scaling.py", "-q"],
                root=root, commands=commands,
            )
        if args.stage in ("all", "metrics"):
            _run(
                [
                    sys.executable, "-m", "pytest", "tests/test_metrics.py", "tests/test_update_metrics.py",
                    "tests/test_knowledge_metrics.py", "-q",
                ],
                root=root, commands=commands,
            )
        if args.stage in ("all", "scenarios"):
            _run(
                [sys.executable, "-m", "pytest", "tests/test_update_scenarios.py", "-q"],
                root=root, commands=commands,
            )
        if args.stage in ("all", "experiments"):
            _run(
                [
                    sys.executable, "-m", "pytest", "tests/test_experiment_a_v02.py",
                    "tests/test_common_checkpoint.py", "tests/test_recovery.py",
                    "tests/test_no_oracle_leakage.py", "tests/test_eval_immutability.py",
                    "tests/test_v02_outputs.py", "-q",
                ],
                root=root, commands=commands,
            )
            _run(
                [
                    sys.executable, "scripts/experiment_a_v02.py", "--config", str(config_path),
                    "--stage", "all", "--outdir", str(outdir / "a"),
                ],
                root=root, commands=commands,
            )
            _run(
                [
                    sys.executable, "scripts/experiment_b_v02.py", "--config", str(config_path),
                    "--stage", "transfer", "--outdir", str(outdir / "b"),
                ],
                root=root, commands=commands,
            )
            meta["artifact_counts"] = validate_smoke_output(outdir, config)

        meta.update({
            "status": "passed",
            "elapsed_s": round(time.time() - started_wall, 3),
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        })
        _write_meta(outdir / "smoke_run_meta.json", meta)
        print(json.dumps({"status": "passed", "outdir": str(outdir), "elapsed_s": meta["elapsed_s"]}, ensure_ascii=False))
        return 0
    except (OSError, OutputIntegrityError, subprocess.SubprocessError, ValueError) as exc:
        meta.update({
            "status": "failed",
            "error": str(exc),
            "elapsed_s": round(time.time() - started_wall, 3),
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        })
        _write_meta(outdir / "smoke_run_meta.json", meta)
        print(json.dumps({"status": "failed", "outdir": str(outdir), "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
