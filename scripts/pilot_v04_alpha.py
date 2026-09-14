"""Pilot Alpha (v0.4): how coarse should a failure credit unit be?

Fixed: Oracle failure truth, reward +1/-1, negative-only update, balanced
distribution.  Varied: Module vs Decision vs Repair credit granularity.

The pre-registered screen is the plan's:
  non-inferiority   CI_low(delta SuccessAUC) > -0.01
  practical effect  WMD down by at least 20% relative to ModuleOracle
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np
import yaml

from rflnext.metrics import success_auc
from rflnext.stats_ext import summary_contrast
from rflv04.train import ARMS, train

EXIT_OK = 0
EXIT_GATE_FAILED = 2
EXIT_CEILING_RISK = 3


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:
        return ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--seeds", type=int, default=None)
    ap.add_argument("--episodes", type=int, default=None)
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args(argv)

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    exp = cfg["experiment"]
    if args.seeds is not None:
        exp["seeds"] = args.seeds
    if args.episodes is not None:
        exp["episodes"] = args.episodes

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "config.yaml").write_text(
        yaml.safe_dump(cfg, allow_unicode=True, sort_keys=True), encoding="utf-8")

    arms = list(exp["arms"])
    rows, by_arm = [], {a: {} for a in arms}
    for i in range(int(exp["seeds"])):
        seed = int(exp["seed_base"]) + i
        for arm in arms:
            res = train(cfg, seed=seed, arm=arm)
            auc = success_auc(res.success_curve, res.checkpoints)
            row = {"seed": seed, "arm": arm, "success_auc": auc,
                   "final_success": res.success_curve[-1], "wmd": res.wmd,
                   "kd_innocent": res.kd_innocent, "collateral": res.collateral,
                   "corrections": res.corrections, "sites": res.sites_touched,
                   "clippings": res.clippings, "family_counts": res.family_counts,
                   "wall_s": res.wall_s, "q_hash": res.q_hash}
            rows.append(row)
            by_arm[arm][seed] = row
        print(f"[seed {seed}] " + "  ".join(
            f"{a}:auc={by_arm[a][seed]['success_auc']:.3f}"
            f"/wmd={by_arm[a][seed]['wmd']:.4f}" for a in arms), flush=True)

    pooled = {}
    for a in arms:
        v = list(by_arm[a].values())
        pooled[a] = {k: float(np.mean([r[k] for r in v]))
                     for k in ("success_auc", "final_success", "wmd",
                               "kd_innocent", "collateral", "sites")}

    rng = np.random.RandomState(0)
    contrasts = {}
    for cand in ("DecisionOracle", "RepairOracle"):
        for metric in ("success_auc", "wmd", "kd_innocent", "collateral"):
            xs = [by_arm[cand][s][metric] for s in sorted(by_arm[cand])]
            ys = [by_arm["ModuleOracle"][s][metric] for s in sorted(by_arm[cand])]
            contrasts.setdefault(cand, {})[metric] = summary_contrast(
                np.array(xs), np.array(ys), n_perm=10000, n_boot=10000, rng=rng)

    # ---- ceiling preflight, NoCorrection only (plan's rule) -------------
    nc = pooled["NoCorrection"]
    gate = cfg["gate"]
    ceiling_risk = bool(nc["final_success"] >= gate["ceiling_success"] and
                        nc["success_auc"] >= gate["ceiling_success"])
    learning_failure = bool(nc["final_success"] < gate["learning_failure_success"])

    screens = {}
    for cand in ("DecisionOracle", "RepairOracle"):
        ni = contrasts[cand]["success_auc"]
        wmd_rel = (pooled["ModuleOracle"]["wmd"] - pooled[cand]["wmd"]) / \
            max(1e-9, abs(pooled["ModuleOracle"]["wmd"]))
        inconclusive = (ni["ci"][1] - ni["ci"][0]) > gate["inconclusive_ci_width"]
        screens[cand] = {
            "noninferior": bool(ni["ci"][0] > -gate["noninferiority_margin"]),
            "wmd_relative_decrease": float(wmd_rel),
            "wmd_screen_passed": bool(wmd_rel >= gate["wmd_relative_decrease"]),
            "inconclusive_precision": bool(inconclusive),
            "verdict": ("INCONCLUSIVE_PRECISION" if inconclusive else
                        ("SCREEN_PASS" if (ni["ci"][0] > -gate["noninferiority_margin"]
                                           and wmd_rel >= gate["wmd_relative_decrease"])
                         else "SCREEN_FAIL")),
        }

    summary = {"schema_version": cfg["schema_version"], "experiment": exp["name"],
               "git_commit": git_commit(), "config": cfg, "seeds": rows,
               "pooled": pooled, "contrasts": contrasts, "screens": screens,
               "preflight": {"ceiling_risk": ceiling_risk,
                             "learning_failure": learning_failure,
                             "nocorrection_final_success": nc["final_success"]}}
    (outdir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== Pilot Alpha: pooled by arm ===")
    print(f"{'arm':<16}{'SuccessAUC':>12}{'final':>8}{'WMD':>10}{'KD_innoc':>10}"
          f"{'collateral':>12}{'sites':>8}")
    for a in arms:
        p = pooled[a]
        print(f"{a:<16}{p['success_auc']:>12.4f}{p['final_success']:>8.4f}"
              f"{p['wmd']:>10.5f}{p['kd_innocent']:>10.5f}{p['collateral']:>12.4f}"
              f"{p['sites']:>8.1f}")
    print(f"\npreflight: ceiling_risk={ceiling_risk} "
          f"learning_failure={learning_failure} "
          f"(NoCorrection final={nc['final_success']:.3f})")
    for cand, s in screens.items():
        print(f"  {cand:<16} {s['verdict']:<22} "
              f"dAUC_CI=[{contrasts[cand]['success_auc']['ci'][0]:+.4f},"
              f"{contrasts[cand]['success_auc']['ci'][1]:+.4f}] "
              f"WMD_rel={s['wmd_relative_decrease']:+.3f}")

    if args.report_only:
        return EXIT_OK
    if ceiling_risk or learning_failure:
        return EXIT_CEILING_RISK
    return EXIT_OK if any(s["verdict"] == "SCREEN_PASS" for s in screens.values()) \
        else EXIT_GATE_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
