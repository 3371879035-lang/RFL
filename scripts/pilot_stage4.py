"""Stage 4 pilot: end-to-end Q-learning with attribution in the loop."""

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

from rflnext.gamma import SequenceModel, generate_balanced
from rflnext.metrics import final_success, success_auc
from rflnext.stage4 import ARMS, train_arm
from rflnext.stats import cohens_dz, paired_bootstrap_ci, paired_sign_flip_test

EXIT_OK = 0
EXIT_RFL_NOT_NONINFERIOR = 2
EXIT_NO_KNOWLEDGE_BENEFIT = 3

METRICS = ("success_auc", "final_success", "collateral_rate",
           "expected_knowledge_damage", "update_precision")


def load_config(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--seeds", type=int, default=None)
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    exp = cfg["experiment"]
    if args.seeds is not None:
        exp["seeds"] = args.seeds

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "config.yaml").write_text(
        yaml.safe_dump(cfg, allow_unicode=True, sort_keys=True), encoding="utf-8"
    )

    att = cfg.get("attribution", {})
    n_traces = int(att.get("n_traces", 2000))
    n_train = int(att.get("n_train", 1000))
    offset = int(att.get("seed_offset", 5_000_000))

    arms = list(exp["arms"])
    rows = []
    by_arm: dict = {a: {} for a in arms}

    for index in range(int(exp["seeds"])):
        seed = int(exp["seed_base"]) + index
        model = SequenceModel().fit(
            generate_balanced(n_traces, seed=seed + offset, horizon=int(cfg["environment"]["horizon"]))[:n_train]
        )
        for arm in arms:
            res = train_arm(cfg, seed=seed, arm=arm, model=model)
            auc = success_auc(res.success_curve, res.checkpoints)
            row = {
                "seed_index": index, "seed": seed, "arm": arm,
                "checkpoints": res.checkpoints, "success_curve": res.success_curve,
                "success_auc": auc,
                "final_success": final_success(res.success_curve),
                "corrections": res.corrections,
                "collateral": res.collateral,
                "collateral_rate": res.collateral_rate,
                "update_precision": res.update_precision,
                "expected_knowledge_damage": res.expected_knowledge_damage,
                "n_cf": res.n_cf,
                "q_hash": res.q_hash,
                "wall_s": res.wall_s,
            }
            rows.append(row)
            by_arm[arm][seed] = row
        print(f"[seed {seed}] " + "  ".join(
            f"{a}:auc={by_arm[a][seed]['success_auc']:.3f}"
            f"/coll={by_arm[a][seed]['collateral_rate'] if by_arm[a][seed]['collateral_rate'] is not None else float('nan'):.3f}"
            for a in arms), flush=True)

    pooled = {}
    for arm in arms:
        vals = list(by_arm[arm].values())
        pooled[arm] = {
            "success_auc": float(np.mean([v["success_auc"] for v in vals])),
            "final_success": float(np.mean([v["final_success"] for v in vals])),
            "collateral_rate": _mean_or_none([v["collateral_rate"] for v in vals]),
            "update_precision": _mean_or_none([v["update_precision"] for v in vals]),
            "expected_knowledge_damage": float(np.mean([v["expected_knowledge_damage"] for v in vals])),
            "corrections": float(np.mean([v["corrections"] for v in vals])),
            "n_cf": float(np.mean([v["n_cf"] for v in vals])),
            "wall_s": float(np.mean([v["wall_s"] for v in vals])),
        }

    rng = np.random.RandomState(0)

    def _pair(ref: str, arm: str, metric: str):
        xs, ys = [], []
        for s in sorted(by_arm[arm]):
            va, vb = by_arm[arm][s][metric], by_arm[ref][s][metric]
            if va is None or vb is None:
                continue
            xs.append(float(va)); ys.append(float(vb))
        if len(xs) < 2:
            return None
        x, y = np.array(xs), np.array(ys)
        lo, hi = paired_bootstrap_ci(x, y, n_resample=10000, rng=rng)
        return {
            "n_seeds": len(xs), "mean": float((x - y).mean()),
            "ci": [float(lo), float(hi)], "cohens_dz": cohens_dz(x - y),
            "p_sign_flip": float(paired_sign_flip_test(x, y, n_perm=10000, rng=rng)),
        }

    # Utility is judged against Traditional; knowledge damage can only be
    # judged against an arm that also corrects something, i.e. direct_feedback.
    # Traditional makes no corrections at all, so it has no collateral to
    # compare against and that contrast cannot exist.
    contrasts, feedback_contrasts = {}, {}
    for arm in arms:
        if arm != "traditional":
            for metric in METRICS:
                res = _pair("traditional", arm, metric)
                if res:
                    contrasts.setdefault(arm, {})[metric] = res
        if arm != "direct_feedback":
            for metric in METRICS:
                res = _pair("direct_feedback", arm, metric)
                if res:
                    feedback_contrasts.setdefault(arm, {})[metric] = res

    margin = float(cfg["gate"]["noninferiority_margin"])
    core = contrasts.get("learned_rfl", {})
    ni = core.get("success_auc")
    noninferior = bool(ni and ni["ci"][0] > -margin)
    coll = feedback_contrasts.get("learned_rfl", {}).get("collateral_rate")
    know_better = bool(coll and coll["mean"] < 0.0 and coll["ci"][1] < 0.0)

    summary = {
        "schema_version": cfg["schema_version"], "experiment": exp["name"],
        "git_commit": git_commit(), "config": cfg, "seeds": rows,
        "pooled": pooled, "contrasts": contrasts,
        "feedback_contrasts": feedback_contrasts,
        "gate": {
            "noninferiority_margin": margin,
            "reference_for_utility": "traditional",
            "reference_for_knowledge_damage": "direct_feedback",
            "learned_rfl_noninferior_on_auc": noninferior,
            "learned_rfl_less_knowledge_damage": know_better,
        },
    }
    (outdir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n=== pooled by arm ===")
    print(f"{'arm':<18}{'success_auc':>13}{'final':>9}{'collateral':>12}{'upd_prec':>10}{'exp_KD':>10}{'corr':>8}{'cf':>8}")
    for a in arms:
        p = pooled[a]
        cr = f"{p['collateral_rate']:.4f}" if p["collateral_rate"] is not None else "-"
        up = f"{p['update_precision']:.4f}" if p["update_precision"] is not None else "-"
        print(f"{a:<18}{p['success_auc']:>13.4f}{p['final_success']:>9.4f}{cr:>12}{up:>10}"
              f"{p['expected_knowledge_damage']:>10.5f}{p['corrections']:>8.0f}{p['n_cf']:>8.0f}")

    print("\n=== vs Traditional (paired, utility) ===")
    for arm in arms:
        if arm == "traditional" or arm not in contrasts:
            continue
        ni_a = contrasts[arm].get("success_auc")
        if ni_a:
            print(f"  {arm:<18} dAUC={ni_a['mean']:+.5f} "
                  f"CI=[{ni_a['ci'][0]:+.5f},{ni_a['ci'][1]:+.5f}] p={ni_a['p_sign_flip']:.4f}")

    print("\n=== vs direct_feedback (paired, knowledge damage) ===")
    for arm in arms:
        if arm == "direct_feedback" or arm not in feedback_contrasts:
            continue
        cl = feedback_contrasts[arm].get("collateral_rate")
        up = feedback_contrasts[arm].get("update_precision")
        if cl:
            print(f"  {arm:<18} dCollateral={cl['mean']:+.5f} "
                  f"CI=[{cl['ci'][0]:+.5f},{cl['ci'][1]:+.5f}] p={cl['p_sign_flip']:.4f}"
                  + (f"   dPrecision={up['mean']:+.5f}" if up else ""))

    print(f"\nlearned_rfl non-inferior on AUC (margin {margin}) = {noninferior}")
    print(f"learned_rfl reduces knowledge damage vs direct_feedback = {know_better}")

    if args.report_only:
        return EXIT_OK
    if not noninferior:
        return EXIT_RFL_NOT_NONINFERIOR
    if not know_better:
        return EXIT_NO_KNOWLEDGE_BENEFIT
    return EXIT_OK


def _mean_or_none(vals: list):
    clean = [float(v) for v in vals if v is not None]
    return float(np.mean(clean)) if clean else None


if __name__ == "__main__":
    raise SystemExit(main())
