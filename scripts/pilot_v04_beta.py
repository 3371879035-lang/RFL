"""Pilot Beta (v0.4): what should the update target be?

Granularity is held fixed at the representation that won Pilot Alpha.  Only the
target semantics vary:

    NegativeOnly         push the factual bad action down
    PositiveAlternative  raise the counterfactually verified alternative
    Contrastive          both
    CFRevalue            target comes from an actual counterfactual re-execution

Pre-registered primary contrast, per the plan: **Contrastive - NegativeOnly**.
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
from rflv04.train import train

EXIT_OK = 0
EXIT_GATE_FAILED = 2


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--seeds", type=int, default=None)
    ap.add_argument("--episodes", type=int, default=None)
    ap.add_argument("--reference-arm", default="NegativeOnly",
                    help="the arm the primary contrast is measured against")
    ap.add_argument("--candidate-arm", default="Contrastive")
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
            row = {"seed": seed, "arm": arm,
                   "success_auc": success_auc(res.success_curve, res.checkpoints),
                   "final_success": res.success_curve[-1], "wmd": res.wmd,
                   "kd_innocent": res.kd_innocent, "collateral": res.collateral,
                   "corrections": res.corrections, "sites": res.sites_touched,
                   "clippings": res.clippings, "checkpoints": res.checkpoints,
                   "curve": res.success_curve, "q_hash": res.q_hash}
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
    for cand in arms:
        if cand == args.reference_arm:
            continue
        for metric in ("success_auc", "wmd", "collateral"):
            xs = [by_arm[cand][s][metric] for s in sorted(by_arm[cand])]
            ys = [by_arm[args.reference_arm][s][metric] for s in sorted(by_arm[cand])]
            contrasts.setdefault(cand, {})[metric] = summary_contrast(
                np.array(xs), np.array(ys), n_perm=10000, n_boot=10000, rng=rng)

    gate = cfg["gate"]
    primary = contrasts.get(args.candidate_arm, {}).get("success_auc")
    width = (primary["ci"][1] - primary["ci"][0]) if primary else None
    inconclusive = bool(width is not None and width > gate["inconclusive_ci_width"])
    noninferior = bool(primary and primary["ci"][0] > -gate["noninferiority_margin"])
    verdict = ("INCONCLUSIVE_PRECISION" if inconclusive else
               "PRIMARY_SUPPORTED" if noninferior else "PRIMARY_NOT_SUPPORTED")

    summary = {"schema_version": cfg["schema_version"], "experiment": exp["name"],
               "config": cfg, "seeds": rows, "pooled": pooled,
               "contrasts_vs_" + args.reference_arm: contrasts,
               "primary_contrast": f"{args.candidate_arm} - {args.reference_arm}",
               "verdict": verdict,
               "ci_width": width}
    (outdir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== Pilot Beta: pooled by arm ===")
    print(f"{'arm':<22}{'SuccessAUC':>12}{'final':>8}{'WMD':>10}{'collat':>10}{'sites':>9}")
    for a in arms:
        p = pooled[a]
        print(f"{a:<22}{p['success_auc']:>12.4f}{p['final_success']:>8.4f}"
              f"{p['wmd']:>10.5f}{p['collateral']:>10.4f}{p['sites']:>9.1f}")
    print(f"\nprimary: {summary['primary_contrast']}")
    if primary:
        print(f"  dAUC mean={primary['mean']:+.5f} CI=[{primary['ci'][0]:+.5f},"
              f"{primary['ci'][1]:+.5f}] width={width:.4f} "
              f"p_signflip={primary['p_sign_flip']:.4f} p_wilcoxon={primary['p_wilcoxon']} "
              f"PoI={primary['probability_of_improvement']:.3f}")
    print(f"  verdict = {verdict}")

    if args.report_only:
        return EXIT_OK
    return EXIT_OK if verdict == "PRIMARY_SUPPORTED" else EXIT_GATE_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
