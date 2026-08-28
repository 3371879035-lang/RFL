"""结果分析与预注册统计（S11/S13）。

用法：
    python scripts/analyze.py --pilot --dir outputs/pilot_a
    python scripts/analyze.py --confirmatory --dir outputs/confirmatory_a
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np

from rflcc.plots import plot_cf_pareto, plot_metric_by_algorithm
from rflcc.stats import (
    cohens_dz,
    holm_correct,
    paired_bootstrap_ci,
    paired_sign_flip_test,
)


def load_seed_rows(csv_path: str) -> list[dict]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def paired_comparison(rows, condition: str, algo_a: str, algo_b: str, metric: str):
    """按 seed 配对比较 algo_a - algo_b 的 metric。"""
    by_seed_a = {int(r["seed_idx"]): float(r[metric]) for r in rows
                 if r["condition"] == condition and r["algorithm"] == algo_a and r[metric] not in (None, "")}
    by_seed_b = {int(r["seed_idx"]): float(r[metric]) for r in rows
                 if r["condition"] == condition and r["algorithm"] == algo_b and r[metric] not in (None, "")}
    common = sorted(set(by_seed_a) & set(by_seed_b))
    if len(common) < 2:
        return None
    va = np.array([by_seed_a[s] for s in common])
    vb = np.array([by_seed_b[s] for s in common])
    diff = va - vb
    p = paired_sign_flip_test(va, vb)
    lo, hi = paired_bootstrap_ci(va, vb)
    return {
        "n_seeds": len(common),
        "mean_diff": float(diff.mean()),
        "cohens_dz": cohens_dz(diff),
        "p_sign_flip": p,
        "ci95_lo": lo,
        "ci95_hi": hi,
    }


def run_analyze(args) -> None:
    outdir = args.dir or "outputs"
    csv_path = os.path.join(outdir, "seed_metrics.csv")
    if not os.path.exists(csv_path):
        print(f"[analyze] no seed_metrics.csv in {outdir}")
        return
    rows = load_seed_rows(csv_path)

    # 1. 汇总表
    summary = []
    for r in rows:
        summary.append({
            "condition": r["condition"], "algorithm": r["algorithm"],
            "ae": float(r["ae_mean"]) if r["ae_mean"] not in ("", "None") else np.nan,
            "wur": float(r["wur_mean"]) if r["wur_mean"] not in ("", "None") else np.nan,
            "coverage": float(r["coverage"]) if r["coverage"] not in ("", "None") else np.nan,
            "cf_transitions": float(r["cf_transitions_mean"]) if r["cf_transitions_mean"] not in ("", "None") else np.nan,
        })
    summary_path = os.path.join(outdir, "summary.csv")
    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
        w.writeheader()
        w.writerows(summary)
    print(f"[analyze] summary -> {summary_path}")

    # 2. 预注册主比较：Full-RFL vs Immediate（AE / WUR）
    comparisons = []
    for cond in sorted({r["condition"] for r in rows}):
        for metric in ("ae_mean", "wur_mean"):
            res = paired_comparison(rows, cond, "full_rfl", "immediate", metric)
            if res:
                res.update({"condition": cond, "metric": metric,
                            "algo_a": "full_rfl", "algo_b": "immediate"})
                comparisons.append(res)
    stats_path = os.path.join(outdir, "statistics.csv")
    if comparisons:
        with open(stats_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(comparisons[0].keys()))
            w.writeheader()
            w.writerows(comparisons)
        print(f"[analyze] statistics -> {stats_path}")
        for c in comparisons:
            print(f"  {c['condition']}/{c['metric']}: diff={c['mean_diff']:+.3f} "
                  f"dz={c['cohens_dz']:+.2f} p={c['p_sign_flip']:.3f} "
                  f"CI=[{c['ci95_lo']:.3f},{c['ci95_hi']:.3f}]")

    # 3. 图
    figdir = os.path.join(outdir, "figures")
    for metric in ("ae_mean", "wur_mean"):
        rows_plot = [{"condition": r["condition"], "algorithm": r["algorithm"],
                      "value": float(r[metric]) if r[metric] not in ("", "None") else np.nan}
                     for r in rows]
        plot_metric_by_algorithm(
            rows_plot, metric,
            os.path.join(figdir, f"{metric}.png"),
            f"{metric} by algorithm", metric,
        )
    plot_cf_pareto(
        [{"algorithm": r["algorithm"], "cf_transitions": float(r["cf_transitions_mean"]),
          "ae": float(r["ae_mean"]) if r["ae_mean"] not in ("", "None") else np.nan}
         for r in rows if r["condition"] == "symmetric"],
        os.path.join(figdir, "cf_pareto.png"),
    )
    print(f"[analyze] figures -> {figdir}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", action="store_true")
    ap.add_argument("--confirmatory", action="store_true")
    ap.add_argument("--rebuild-all", action="store_true")
    ap.add_argument("--dir", default=None)
    args = ap.parse_args()
    run_analyze(args)


if __name__ == "__main__":
    main()
