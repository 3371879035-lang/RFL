"""Preflight checks for an isolated, auditable v0.2 execution worktree."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml


class PreflightError(RuntimeError):
    """The selected interpreter, source tree, or frozen config is unsafe."""


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, check=False, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if result.returncode:
        raise PreflightError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def run_preflight(project_root: str | Path, config_path: str | Path) -> dict:
    root = Path(project_root).resolve()
    config_path = Path(config_path).resolve()
    if not config_path.is_file():
        raise PreflightError(f"frozen config does not exist: {config_path}")
    try:
        import rflcc
    except ImportError as exc:  # pragma: no cover - depends on local interpreter setup
        raise PreflightError("rflcc cannot be imported by the selected interpreter") from exc
    module_path = Path(rflcc.__file__).resolve()
    expected_source = (root / "src").resolve()
    if not module_path.is_relative_to(expected_source):
        raise PreflightError(
            f"rflcc resolves outside release worktree: {module_path}; expected below {expected_source}"
        )
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(cfg, dict) or cfg.get("schema_version") != "0.2.0":
        raise PreflightError("config is not the frozen v0.2.0 study configuration")
    if int(cfg.get("scenarios", {}).get("search_attempts_per_trace", 0)) != 300:
        raise PreflightError("protected-probe search_attempts_per_trace must equal 300")
    if float(cfg.get("knowledge", {}).get("initial_correct_margin", 0.0)) != 0.60:
        raise PreflightError("knowledge.initial_correct_margin must equal 0.60")
    status = _git(root, "status", "--porcelain")
    if status:
        raise PreflightError("release worktree is not clean; commit or isolate changes before execution")
    tracked_caches = _git(root, "ls-files", "-z", "*.pyc", "__pycache__")
    if tracked_caches:
        raise PreflightError("Git still tracks Python bytecode caches")
    return {
        "status": "passed",
        "project_root": str(root),
        "python_executable": sys.executable,
        "rflcc_file": str(module_path),
        "git_commit": _git(root, "rev-parse", "HEAD"),
        "config": str(config_path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="preflight an isolated v0.2 worktree")
    parser.add_argument("--config", required=True)
    parser.add_argument("--project-root", default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    try:
        print(json.dumps(run_preflight(args.project_root, args.config), ensure_ascii=False))
    except PreflightError as exc:
        print(json.dumps({"status": "invalid", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
