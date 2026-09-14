"""Seed-paired analysis for Pilot Alpha.

The statistical unit is the seed.  Episodes are nested inside seeds and are
never treated as independent samples.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rflnext.stats import cohens_dz, paired_bootstrap_ci, paired_sign_flip_test

ARM_A = "traditional"
ARM_B = "positive_only"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--n-perm", type=int, default=10000)
    ap.add_argument("--n-boot", type=int, default=10000)
    args = ap.parse_args(argv)

    outdir = Path(args.dir)
    summary = json.loads((outdir / "summary.json").read_text(encoding="utf-8"))
    by_arm: dict = {}
    for row in summary["seeds"]:
        by_arm.setdefault(row["arm"], {})[row["seed"]] = row

    if ARM_A not in by_arm or ARM_B not in by_arm:
        print(f"missing an arm: have {sorted(by_arm)}", file=sys.stderr)
        return 3

    seeds = sorted(set(by_arm[ARM_A]) & set(by_arm[ARM_B]))
    if len(seeds) != len(by_arm[ARM_A]) or len(seeds) != len(by_arm[ARM_B]):
        print("unpaired seeds between arms", file=sys.stderr)
        return 3

    rng = np.random.RandomState(0)

    def deltas(metric: str) -> np.ndarray:
        x = np.array([by_arm[ARM_A][s][metric] for s in seeds], dtype=float)
        y = np.array([by_arm[ARM_B][s][metric] for s in seeds], dtype=float)
        return x - y

    auc_delta = deltas("success_auc")
    final_delta = deltas("final_success")

    x_auc = np.array([by_arm[ARM_A][s]["success_auc"] for s in seeds], dtype=float)
    y_auc = np.array([by_arm[ARM_B][s]["success_auc"] for s in seeds], dtype=float)

    ci_lo, ci_hi = paired_bootstrap_ci(x_auc, y_auc, n_resample=args.n_boot, rng=rng)
    p_value = paired_sign_flip_test(x_auc, y_auc, n_perm=args.n_perm, rng=rng)

    n_neg = {
        arm: int(sum(by_arm[arm][s]["n_negative_td"] for s in seeds)) for arm in (ARM_A, ARM_B)
    }

    table = {
        "unit": "seed",
        "n_seeds": len(seeds),
        "contrast": f"{ARM_A} - {ARM_B}",
        "auc_delta_mean": float(auc_delta.mean()),
        "auc_delta_median": float(np.median(auc_delta)),
        "auc_delta_ci": [float(ci_lo), float(ci_hi)],
        "auc_delta_cohens_dz": cohens_dz(auc_delta),
        "auc_sign_flip_p": float(p_value),
        "final_success_delta_mean": float(final_delta.mean()),
        "auc_by_arm": {
            arm: float(np.mean([by_arm[arm][s]["success_auc"] for s in seeds]))
            for arm in (ARM_A, ARM_B)
        },
        "n_negative_td_by_arm": n_neg,
        "seeds": seeds,
    }
    (outdir / "analysis.json").write_text(
        json.dumps(table, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"unit = seed, n = {table['n_seeds']}")
    print(f"AUC  {ARM_A} - {ARM_B}: mean={table['auc_delta_mean']:+.5f} "
          f"median={table['auc_delta_median']:+.5f} "
          f"dz={table['auc_delta_cohens_dz']:+.3f} p={p_value:.4f}")
    print(f"     95% paired CI = [{ci_lo:+.5f}, {ci_hi:+.5f}]")
    print(f"FinalSuccess delta mean = {table['final_success_delta_mean']:+.5f}")
    print(f"negative TD errors by arm = {n_neg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
