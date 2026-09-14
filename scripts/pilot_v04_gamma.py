"""Pilot Gamma (v0.4): robustness of the surviving mechanism.

The plan's question here is whether whatever survived Alpha and Beta holds up
across reward semantics and across how the damage is distributed, rather than
being an artifact of one setting.

    reward     in {A: +1/-1, B: +1/0}
    severity   in {mild: delta 1, severe: delta 100}
    mechanism  in {NoCorrection, NegativeOnly, DecisionOracle}

The analysis of interest is the **interaction**, not "which cell is highest".
`N_delta_neg` is reported throughout, because `r_failure = 0` removes the
explicit penalty, not the downward value updates.
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

from rflnext.metrics import success_auc
from rflnext.stats_ext import summary_contrast
from rflv04.train import train

REWARDS = ("A", "B")
SEVERITIES = (("mild", 1.0), ("severe", 100.0))
MECHANISMS = ("NoCorrection", "NegativeOnly", "DecisionOracle")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--seeds", type=int, default=12)
    ap.add_argument("--episodes", type=int, default=2000)
    args = ap.parse_args(argv)

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    cfg["experiment"]["episodes"] = args.episodes
    (outdir / "config.yaml").write_text(
        yaml.safe_dump(cfg, allow_unicode=True, sort_keys=True), encoding="utf-8")

    cells: dict = {}
    rows = []
    for reward in REWARDS:
        for sev_name, sev in SEVERITIES:
            for mech in MECHANISMS:
                key = f"{reward}|{sev_name}|{mech}"
                cfg["experiment"]["reward_mode"] = reward
                cfg["experiment"]["corrupt_delta"] = sev
                vals = []
                for i in range(args.seeds):
                    res = train(cfg, seed=4600000 + i, arm=mech)
                    v = {"seed": 4600000 + i,
                         "success_auc": success_auc(res.success_curve, res.checkpoints),
                         "final_success": res.success_curve[-1], "wmd": res.wmd,
                         "collateral": res.collateral,
                         "n_negative_td": res.n_negative_td}
                    vals.append(v)
                    rows.append({"cell": key, **v})
                cells[key] = {
                    "reward": reward, "severity": sev_name, "mechanism": mech,
                    "success_auc": float(np.mean([v["success_auc"] for v in vals])),
                    "wmd": float(np.mean([v["wmd"] for v in vals])),
                    "collateral": float(np.mean([v["collateral"] for v in vals])),
                    "n_negative_td": float(np.mean([v["n_negative_td"] for v in vals])),
                    "per_seed": vals,
                }
                print(f"[{key:<28}] auc={cells[key]['success_auc']:.4f} "
                      f"wmd={cells[key]['wmd']:.5f} "
                      f"negTD={cells[key]['n_negative_td']:.0f}", flush=True)

    # --- interactions, computed per seed so they stay paired ---------------
    rng = np.random.RandomState(0)
    interactions = {}
    for mech in MECHANISMS:
        for label, pick in (
            ("reward_B_minus_A", lambda r, s: (("B", s), ("A", s))),
            ("severe_minus_mild", lambda r, s: ((r, "severe"), (r, "mild"))),
        ):
            xs, ys = [], []
            for i in range(args.seeds):
                seed = 4600000 + i
                def get(spec):
                    return next(r["success_auc"] for r in rows
                                if r["cell"] == f"{spec[0]}|{spec[1]}|{mech}"
                                and r["seed"] == seed)
                for r in REWARDS:
                    for s, _ in SEVERITIES:
                        (hi_spec, lo_spec) = pick(r, s)
                        xs.append(get(hi_spec))
                        ys.append(get(lo_spec))
            if len(xs) >= 2:
                interactions[f"{mech}:{label}"] = summary_contrast(
                    np.array(xs), np.array(ys), n_perm=5000, n_boot=5000, rng=rng)

    neg_b = {m: cells[f"B|mild|{m}"]["n_negative_td"] for m in MECHANISMS}
    summary = {
        "experiment": "v04_gamma", "seeds": args.seeds, "episodes": args.episodes,
        "cells": cells, "rows": rows, "interactions": interactions,
        "n_negative_td_reward_B": neg_b,
    }
    (outdir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== Gamma: reward x severity x mechanism (SuccessAUC) ===")
    print(f"{'mechanism':<18}" + "".join(f"{r}/{s:>6}" for r in REWARDS
                                         for s, _ in SEVERITIES))
    for mech in MECHANISMS:
        line = f"{mech:<18}"
        for r in REWARDS:
            for s, _ in SEVERITIES:
                line += f"{cells[f'{r}|{s}|{mech}']['success_auc']:>13.4f}"
        print(line)
    print("\n=== interactions (paired) ===")
    for k, v in interactions.items():
        print(f"  {k:<40} mean={v['mean']:+.5f} "
              f"CI=[{v['ci'][0]:+.5f},{v['ci'][1]:+.5f}] p={v['p_sign_flip']:.4f}")
    print(f"\nN_delta_neg under reward B (per 2000 episodes): {neg_b}")
    print("  r_failure = 0 removes the explicit penalty, NOT the downward updates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
