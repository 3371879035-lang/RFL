"""Seed-paired analysis for Pilot Beta.

Contrasts are paired by seed.  The statistical unit is the seed; the diagnostic
events inside a seed are never treated as independent samples.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rflnext.beta import INNOCENT
from rflnext.stats import cohens_dz, paired_bootstrap_ci, paired_sign_flip_test

PAIRS = (
    ("traditional_oracle", "traditional"),
    ("positive_only_oracle", "positive_only"),
    ("h_only", "traditional"),
    ("l_only", "traditional"),
    ("hl", "traditional"),
)


def _index(rows: list) -> dict:
    out: dict = {}
    for row in rows:
        out.setdefault(row["condition"], {})[row["seed"]] = row
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--n-perm", type=int, default=10000)
    ap.add_argument("--n-boot", type=int, default=10000)
    args = ap.parse_args(argv)

    outdir = Path(args.dir)
    summary = json.loads((outdir / "summary.json").read_text(encoding="utf-8"))
    by_cond = _index(summary["seeds"])
    rng = np.random.RandomState(0)

    def paired(a: str, b: str, key) -> dict | None:
        if a not in by_cond or b not in by_cond:
            return None
        seeds = sorted(set(by_cond[a]) & set(by_cond[b]))
        xs, ys = [], []
        for s in seeds:
            va, vb = key(by_cond[a][s]), key(by_cond[b][s])
            if va is None or vb is None:
                return None
            xs.append(float(va))
            ys.append(float(vb))
        x, y = np.array(xs), np.array(ys)
        lo, hi = paired_bootstrap_ci(x, y, n_resample=args.n_boot, rng=rng)
        return {
            "contrast": f"{a} - {b}",
            "n_seeds": len(seeds),
            "mean": float((x - y).mean()),
            "median": float(np.median(x - y)),
            "ci": [float(lo), float(hi)],
            "cohens_dz": cohens_dz(x - y),
            "p_sign_flip": float(paired_sign_flip_test(x, y, n_perm=args.n_perm, rng=rng)),
        }

    table: dict = {"unit": "seed", "auc": {}, "kd_innocent": {}, "interaction": {}}

    for a, b in PAIRS:
        res = paired(a, b, lambda r: r["success_auc"])
        if res:
            table["auc"][f"{a}_minus_{b}"] = res

    for family in INNOCENT:
        if INNOCENT[family] is None:
            continue
        for a, b in PAIRS:
            res = paired(
                a, b,
                lambda r, f=family: r["kd_by_family"][f]["kd_innocent_mean"],
            )
            if res:
                table["kd_innocent"].setdefault(family, {})[f"{a}_minus_{b}"] = res

    # Penalty x Oracle interaction on AUC: (PO+O - PO) - (T+O - T).
    def auc_row(cond, seed):
        return by_cond[cond][seed]["success_auc"]

    seeds = sorted(set(by_cond["traditional"]) & set(by_cond["positive_only"])
                   & set(by_cond["traditional_oracle"])
                   & set(by_cond["positive_only_oracle"]))
    if seeds:
        inter = np.array([
            (auc_row("positive_only_oracle", s) - auc_row("positive_only", s))
            - (auc_row("traditional_oracle", s) - auc_row("traditional", s))
            for s in seeds
        ])
        lo, hi = paired_bootstrap_ci(
            inter, np.zeros_like(inter), n_resample=args.n_boot, rng=rng
        )
        table["interaction"] = {
            "definition": "(PO+Oracle - PO) - (T+Oracle - T)",
            "n_seeds": len(seeds),
            "mean": float(inter.mean()),
            "ci": [float(lo), float(hi)],
            "cohens_dz": cohens_dz(inter),
        }

    (outdir / "analysis.json").write_text(
        json.dumps(table, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"unit = seed")
    for name, res in table["auc"].items():
        print(f"  AUC  {name:44s} mean={res['mean']:+.5f} "
              f"CI=[{res['ci'][0]:+.5f},{res['ci'][1]:+.5f}] p={res['p_sign_flip']:.4f}")
    for family, rows in table["kd_innocent"].items():
        print(f"  KD_innocent[{family}]")
        for name, res in rows.items():
            print(f"      {name:44s} mean={res['mean']:+.5f} "
                  f"CI=[{res['ci'][0]:+.5f},{res['ci'][1]:+.5f}] p={res['p_sign_flip']:.4f}")
    if table["interaction"]:
        it = table["interaction"]
        print(f"  interaction {it['definition']}: mean={it['mean']:+.5f} "
              f"CI=[{it['ci'][0]:+.5f},{it['ci'][1]:+.5f}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
