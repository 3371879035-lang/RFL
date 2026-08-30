"""Capture the reproducibility envelope required for a v0.2 run.

This utility does not run an experiment.  It records the exact interpreter,
dependencies, git revision, frozen configuration hashes, and *planned* seed
manifest alongside a separately generated run.  Keeping it separate prevents
environment capture from silently altering an experiment's runtime path.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterable

import yaml

try:  # Direct script execution and package-style test imports.
    from .v02_integrity import canonical_config_hash
except ImportError:  # pragma: no cover - direct invocation branch
    from v02_integrity import canonical_config_hash


DEPENDENCIES = ("numpy", "pandas", "scipy", "matplotlib", "PyYAML", "pytest", "rflcc")


class ReproducibilityError(RuntimeError):
    """Raised when a required reproducibility artifact cannot be captured."""


def _git_commit(project_root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(project_root), check=False,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    commit = completed.stdout.strip()
    if completed.returncode != 0 or not commit:
        raise ReproducibilityError(
            f"cannot capture git commit from {project_root}: {completed.stderr.strip()}"
        )
    return commit


def _working_tree_clean(project_root: Path) -> bool:
    completed = subprocess.run(
        ["git", "status", "--porcelain"], cwd=str(project_root), check=False,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    if completed.returncode != 0:
        raise ReproducibilityError(
            f"cannot inspect worktree state from {project_root}: {completed.stderr.strip()}"
        )
    return not completed.stdout.strip()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _dependency_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for package in DEPENDENCIES:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "not-installed"
    return versions


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _normalise_config_paths(config_paths: Iterable[str | Path], project_root: Path) -> list[Path]:
    paths: list[Path] = []
    for raw in config_paths:
        path = Path(raw)
        if not path.is_absolute():
            path = (project_root / path).resolve()
        if not path.is_file():
            raise ReproducibilityError(f"configuration file does not exist: {path}")
        paths.append(path)
    if not paths:
        raise ReproducibilityError("at least one frozen configuration is required")
    return paths


def capture_reproducibility(
    outdir: str | Path,
    *,
    project_root: str | Path,
    config_paths: Iterable[str | Path],
    stages: Iterable[str] = ("A-attribution", "A-update", "B-transfer", "B-online"),
    benchmark: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write the complete metadata envelope into a new or empty directory.

    Seed entries are marked ``planned`` because the experiment entry point is
    the authority for actual completed rows.  This avoids inventing completion
    status if a gate stops a pilot or confirmatory run early.
    """
    project_root = Path(project_root).resolve()
    outdir = Path(outdir)
    if not outdir.is_absolute():
        outdir = (project_root / outdir).resolve()
    if outdir.exists() and any(outdir.iterdir()):
        raise ReproducibilityError(f"refusing to overwrite reproducibility artifacts: {outdir}")
    outdir.mkdir(parents=True, exist_ok=True)

    configs = _normalise_config_paths(config_paths, project_root)
    parsed: list[tuple[Path, dict[str, Any]]] = []
    for path in configs:
        cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(cfg, dict) or cfg.get("schema_version") != "0.2.0":
            raise ReproducibilityError(f"not a v0.2 configuration: {path}")
        if not isinstance(cfg.get("experiment"), dict):
            raise ReproducibilityError(f"missing experiment block: {path}")
        parsed.append((path, cfg))

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    commit = _git_commit(project_root)
    environment = {
        "captured_at_utc": now,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python_executable": sys.executable,
        "project_root": str(project_root),
        "source_commit": commit,
        "analysis_commit": commit,
        "working_tree_clean": str(_working_tree_clean(project_root)).lower(),
    }
    _write_text(outdir / "environment.txt", "\n".join(f"{key}={value}" for key, value in environment.items()) + "\n")
    _write_text(outdir / "python_version.txt", sys.version + "\n")
    _write_text(
        outdir / "dependency_versions.txt",
        "\n".join(f"{name}=={version}" for name, version in _dependency_versions().items()) + "\n",
    )
    _write_text(outdir / "git_commit.txt", commit + "\n")

    config_lines = []
    manifest_rows: list[dict[str, Any]] = []
    stage_names = tuple(stages)
    for config_path, cfg in parsed:
        rel_path = str(config_path.relative_to(project_root)) if config_path.is_relative_to(project_root) else str(config_path)
        file_hash = _file_sha256(config_path)
        canonical_hash = canonical_config_hash(cfg)
        config_lines.append(
            f"path={rel_path}\tfile_sha256={file_hash}\tcanonical_json_sha256={canonical_hash}"
        )
        exp = cfg["experiment"]
        n_seeds = int(exp["seeds"])
        seed_base = int(exp["seed_base"])
        for stage in stage_names:
            for seed_index in range(n_seeds):
                manifest_rows.append({
                    "status": "planned",
                    "config_path": rel_path,
                    "canonical_config_hash": canonical_hash,
                    "stage": stage,
                    "seed_index": seed_index,
                    "configured_seed_base": seed_base,
                    "planned_seed": seed_base + seed_index,
                })
    _write_text(outdir / "config_hashes.txt", "\n".join(config_lines) + "\n")
    with (outdir / "seed_manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(manifest_rows[0]))
        writer.writeheader()
        writer.writerows(manifest_rows)

    benchmark_payload = {
        "schema_version": "0.2.1",
        "captured_at_utc": now,
        "source_commit": commit,
        "analysis_commit": commit,
        "kind": "metadata-capture",
        "metadata": benchmark or {},
    }
    (outdir / "benchmark.json").write_text(
        json.dumps(benchmark_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "outdir": str(outdir),
        "git_commit": commit,
        "configs": len(parsed),
        "planned_seed_rows": len(manifest_rows),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="capture the v0.2 reproducibility envelope")
    parser.add_argument("--config", action="append", required=True, help="frozen v0.2 YAML (repeatable)")
    parser.add_argument("--outdir", default="outputs/v02_reproducibility")
    parser.add_argument(
        "--stage", action="append", dest="stages",
        help="planned stage name (repeatable; defaults to all A/B v0.2 stages)",
    )
    parser.add_argument("--project-root", default=None)
    args = parser.parse_args(argv)
    project_root = Path(args.project_root).resolve() if args.project_root else Path(__file__).resolve().parents[1]
    result = capture_reproducibility(
        args.outdir,
        project_root=project_root,
        config_paths=args.config,
        stages=tuple(args.stages) if args.stages else ("A-attribution", "A-update", "B-transfer", "B-online"),
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
