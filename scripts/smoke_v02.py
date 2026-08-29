"""v0.2 layered smoke gate; writes only under outputs/v02_smoke."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import yaml


def _run(cmd: list[str], cwd: Path) -> None:
    print("[smoke]", " ".join(cmd))
    env = os.environ.copy()
    env["PYTHONPATH"] = str(cwd / "src") + os.pathsep + env.get("PYTHONPATH", "")
    subprocess.run(cmd, cwd=str(cwd), check=True, env=env)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--stage", choices=("all", "router", "metrics", "scenarios", "experiments"), default="all")
    args = ap.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    outdir = root / "outputs" / "v02_smoke"
    outdir.mkdir(parents=True, exist_ok=True)
    stage = args.stage
    started = time.time()
    if stage in ("all", "router"):
        _run([sys.executable, "-m", "pytest", "tests/test_router.py", "-q"], root)
    if stage in ("all", "metrics"):
        _run([sys.executable, "-m", "pytest", "tests/test_metrics.py", "-q"], root)
    if stage in ("all", "scenarios"):
        _run([sys.executable, "-c", "from rflcc.update_scenarios import make_high_protection,make_low_protection,make_environment_mixed,make_hl_mixed; [f(1, seed=7, max_attempts=300) for f in (make_high_protection,make_low_protection,make_environment_mixed,make_hl_mixed)]"], root)
    if stage in ("all", "experiments"):
        _run([sys.executable, "scripts/experiment_a_v02.py", "--config", args.config, "--stage", "update", "--outdir", str(outdir / "a")], root)
        _run([sys.executable, "scripts/experiment_b_v02.py", "--config", args.config, "--stage", "transfer", "--outdir", str(outdir / "b")], root)
    meta = {"schema_version": "0.2.0", "stage": stage, "config": str(args.config), "elapsed_s": round(time.time() - started, 3), "status": "passed"}
    (outdir / "run_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
