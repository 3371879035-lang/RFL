"""Baseline-only damage-persistence calibration.

Pilot Alpha was not interpretable because ordinary Q-learning repaired the
injected corruption inside the 250-episode evaluation interval, so no credit
representation had anything to add.  The plan's rule is that difficulty is
calibrated on the **NoCorrection baseline alone**, never by looking at whether a
treatment arm wins.  This script does exactly that.

The lever is the corruption *magnitude*, not the number of corrupted states: the
TD target is a fixed failure value, so a value starting at ``Q_correct + delta``
needs roughly ``log(delta) / log(1 - alpha)`` visits to fall back below the
correct action.  With few reachable states, magnitude is what controls how long
the damage persists.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np
import yaml

from rflv04.knowledge import build_knowledge_set
from rflv04.train import evaluate, train


def recovery_profile(curve: list, checkpoints: list) -> dict:
    """How far the baseline fell, and how long it took to come back."""
    if not curve:
        return {}
    clean = curve[-1]
    low = min(curve)
    low_ep = checkpoints[curve.index(low)]
    target = 0.9 * clean if clean > 0 else 0.0
    recovered = next((e for e, v in zip(checkpoints, curve) if v >= target), None)
    return {
        "clean_final": float(clean),
        "min_success": float(low),
        "min_at_episode": int(low_ep),
        "damage_depth": float(clean - low),
        "recovered_at_episode": recovered,
        "dynamic_range": bool((clean - low) > 0.05),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--seeds", type=int, default=2)
    ap.add_argument("--episodes", type=int, default=400)
    ap.add_argument("--eval-every", type=int, default=10)
    args = ap.parse_args(argv)

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    deltas = [1.0, 10.0, 100.0, 1000.0]
    results = {}
    for delta in deltas:
        cfg["experiment"]["corrupt_delta"] = delta
        cfg["experiment"]["episodes"] = args.episodes
        cfg["experiment"]["eval_every"] = args.eval_every
        cfg["experiment"]["eval_episodes"] = 40
        curves = []
        for s in range(args.seeds):
            res = train(cfg, seed=4700000 + s, arm="NoCorrection")
            curves.append(res)
        mean_curve = [float(np.mean([r.success_curve[i] for r in curves]))
                      for i in range(len(curves[0].success_curve))]
        prof = recovery_profile(mean_curve, curves[0].checkpoints)
        prof["curve"] = mean_curve
        prof["checkpoints"] = curves[0].checkpoints
        prof["corrupt_delta"] = delta
        results[str(delta)] = prof
        print(f"[delta={delta:>7.1f}] min={prof['min_success']:.3f} "
              f"@ep{prof['min_at_episode']:<4} recovered@{prof['recovered_at_episode']} "
              f"range={prof['dynamic_range']}", flush=True)

    # Also profile the clean reference so the ceiling is explicit.
    cfg["experiment"]["corrupt_delta"] = 0.0
    clean = [train(cfg, seed=4700000 + s, arm="NoCorruption") for s in range(args.seeds)]
    clean_curve = [float(np.mean([r.success_curve[i] for r in clean]))
                   for i in range(len(clean[0].success_curve))]

    viable = [d for d, p in results.items() if p["dynamic_range"]]
    summary = {
        "experiment": "v04_damage_calibration",
        "baseline_only": True,
        "seeds": args.seeds,
        "episodes": args.episodes,
        "eval_every": args.eval_every,
        "clean_reference_curve": clean_curve,
        "clean_reference_checkpoints": clean[0].checkpoints,
        "by_delta": results,
        "viable_deltas": viable,
    }
    (outdir / "calibration.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nclean reference final = {clean_curve[-1]:.3f}")
    print(f"viable corrupt_delta values (dynamic range > 0.05): {viable}")
    print("Pick the smallest viable delta; it is a baseline-only choice.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
