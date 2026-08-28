"""Pilot runner（S11）：12 pilot seeds，永久禁止进入 confirmatory。

用法：
    python scripts/run_pilot.py --experiment A
    python scripts/run_pilot.py --experiment B --stage B3
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--experiment", choices=["A", "B"], required=True)
    ap.add_argument("--stage", default=None)
    ap.add_argument("--seeds", type=int, default=12)
    ap.add_argument("--episodes", type=int, default=5000)
    args = ap.parse_args()

    py = sys.executable
    if args.experiment == "A":
        cmd = [
            py, os.path.join(ROOT, "scripts", "experiment_a.py"),
            "--seeds", str(args.seeds),
            "--per-cause", "30",
            "--outdir", os.path.join(ROOT, "outputs", "pilot_a"),
        ]
        print("[pilot] " + " ".join(cmd))
        subprocess.run(cmd, cwd=ROOT, check=True)
        subprocess.run(
            [py, os.path.join(ROOT, "scripts", "analyze.py"), "--pilot",
             "--dir", os.path.join(ROOT, "outputs", "pilot_a")],
            cwd=ROOT, check=True,
        )
    else:
        stage = args.stage or "B3"
        cmd = [
            py, os.path.join(ROOT, "scripts", "experiment_b.py"),
            "--stage", stage, "--pilot",
            "--seeds", str(args.seeds), "--episodes", str(args.episodes),
            "--outdir", os.path.join(ROOT, "outputs", "pilot_b"),
        ]
        print("[pilot] " + " ".join(cmd))
        subprocess.run(cmd, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
