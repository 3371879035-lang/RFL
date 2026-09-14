"""Stage 5: does correct responsibility routing EVER convert to task utility?

Every earlier stage found the effect in credit/knowledge but never in policy
utility -- Pilot Beta's Oracle correction reached exactly zero collateral damage
while all arms ended at identical final success.  The research plan's decision
tree anticipates this ("knowledge protection improves but return does not") and
directs a check of whether the benchmark is too easy, i.e. whether ordinary RL
repairs the damage faster than it can matter.

This sweeps the two things that control repair speed and task slack:
  * horizon  -- how much slack the task allows (5 is exactly enough for the
    longer lane, i.e. zero slack)
  * alpha    -- how fast ordinary RL re-learns a damaged value

At each setting the contrast is traditional vs Oracle selective correction, and
the question is whether the paired task-AUC difference ever separates from zero.
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

from rflnext.beta import train_beta
from rflnext.metrics import final_success, success_auc
from rflnext.stats import cohens_dz, paired_bootstrap_ci, paired_sign_flip_test

ARMS = ("traditional", "traditional_oracle")

SETTINGS = (
    {"name": "base_h8_a10", "horizon": 8, "alpha": 0.10},
    {"name": "tight_h6_a10", "horizon": 6, "alpha": 0.10},
    {"name": "tight_h5_a10", "horizon": 5, "alpha": 0.10},
    {"name": "base_h8_a03", "horizon": 8, "alpha": 0.03},
    {"name": "tight_h5_a03", "horizon": 5, "alpha": 0.03},
    {"name": "base_h8_a01", "horizon": 8, "alpha": 0.01},
)


def git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return ""


def build_cfg(base: dict, setting: dict) -> dict:
    cfg = json.loads(json.dumps(base))
    cfg["environment"]["horizon"] = int(setting["horizon"])
    cfg["learning"]["alpha_low"] = float(setting["alpha"])
    cfg["learning"]["alpha_high"] = float(setting["alpha"])
    return cfg


def kd_stats(records: list) -> dict:
    events = [d for r in records for d in r.diagnostics]
    innocent = [d.kd_innocent for d in events if d.kd_innocent is not None]
    return {
        "collateral_events": int(sum(1 for d in events if d.corrected_h or d.corrected_l)),
        "kd_innocent_mean": float(np.mean(innocent)) if innocent else None,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--seeds", type=int, default=None)
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args(argv)

    base = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    exp = base["experiment"]
    if args.seeds is not None:
        exp["seeds"] = args.seeds

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "config.yaml").write_text(
        yaml.safe_dump(base, allow_unicode=True, sort_keys=True), encoding="utf-8"
    )

    rng = np.random.RandomState(0)
    rows = []
    per_setting: dict = {}

    for setting in SETTINGS:
        cfg = build_cfg(base, setting)
        store: dict = {a: {} for a in ARMS}
        for index in range(int(exp["seeds"])):
            seed = int(exp["seed_base"]) + index
            for arm in ARMS:
                res = train_beta(cfg, seed=seed, condition=arm)
                kd = kd_stats([res])
                store[arm][seed] = {
                    "success_auc": success_auc(res.success_curve, res.checkpoints),
                    "final_success": final_success(res.success_curve),
                    "n_diagnostic": len(res.diagnostics),
                    "kd_innocent_mean": kd["kd_innocent_mean"],
                    "q_hash": res.q_hash,
                }
        x = np.array([store["traditional_oracle"][s]["success_auc"] for s in sorted(store["traditional"])])
        y = np.array([store["traditional"][s]["success_auc"] for s in sorted(store["traditional"])])
        lo, hi = paired_bootstrap_ci(x, y, n_resample=10000, rng=rng)
        contrast = {
            "d_auc_mean": float((x - y).mean()),
            "d_auc_ci": [float(lo), float(hi)],
            "cohens_dz": cohens_dz(x - y),
            "p_sign_flip": float(paired_sign_flip_test(x, y, n_perm=10000, rng=rng)),
            "separates_from_zero": bool(lo > 0.0 or hi < 0.0),
            "traditional_auc": float(y.mean()),
            "oracle_auc": float(x.mean()),
            "traditional_final": float(np.mean([store["traditional"][s]["final_success"] for s in store["traditional"]])),
            "oracle_final": float(np.mean([store["traditional_oracle"][s]["final_success"] for s in store["traditional_oracle"]])),
            "oracle_kd": _mean_or_none([store["traditional_oracle"][s]["kd_innocent_mean"] for s in store["traditional_oracle"]]),
            "oracle_diagnoses": float(np.mean([store["traditional_oracle"][s]["n_diagnostic"] for s in store["traditional_oracle"]])),
            "traditional_diagnoses": float(np.mean([store["traditional"][s]["n_diagnostic"] for s in store["traditional"]])),
        }
        per_setting[setting["name"]] = {"setting": setting, "contrast": contrast}
        for index, seed in enumerate(sorted(store["traditional"])):
            rows.append({
                "setting": setting["name"], "seed": seed,
                "traditional_auc": store["traditional"][seed]["success_auc"],
                "oracle_auc": store["traditional_oracle"][seed]["success_auc"],
                "traditional_final": store["traditional"][seed]["final_success"],
                "oracle_final": store["traditional_oracle"][seed]["final_success"],
            })
        print(f"[{setting['name']:<14}] trad={contrast['traditional_auc']:.4f} "
              f"oracle={contrast['oracle_auc']:.4f} dAUC={contrast['d_auc_mean']:+.5f} "
              f"CI=[{lo:+.5f},{hi:+.5f}] separates={contrast['separates_from_zero']}", flush=True)

    any_separation = any(
        v["contrast"]["separates_from_zero"] for v in per_setting.values()
    )
    summary = {
        "schema_version": base["schema_version"],
        "experiment": exp["name"],
        "git_commit": git_commit(),
        "config": base,
        "settings": per_setting,
        "rows": rows,
        "any_setting_separates": bool(any_separation),
    }
    (outdir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n=== difficulty sweep: Oracle minus Traditional on task AUC ===")
    print(f"{'setting':<16}{'horizon':>8}{'alpha':>8}{'trad_auc':>10}{'oracle_auc':>12}"
          f"{'dAUC':>10}{'95% CI':>26}{'sep':>6}{'oracle_KD':>11}")
    for name, v in per_setting.items():
        s, c = v["setting"], v["contrast"]
        kd = f"{c['oracle_kd']:.5f}" if c["oracle_kd"] is not None else "-"
        lo, hi = c["d_auc_ci"]
        ci = f"[{lo:+.5f},{hi:+.5f}]"
        print(f"{name:<16}{s['horizon']:>8}{s['alpha']:>8.2f}{c['traditional_auc']:>10.4f}"
              f"{c['oracle_auc']:>12.4f}{c['d_auc_mean']:>+10.5f}"
              f"{ci:>26}{str(c['separates_from_zero']):>6}{kd:>11}")
    print(f"\nany difficulty setting separates Oracle from Traditional on AUC = {any_separation}")

    if args.report_only:
        return 0
    return 0 if any_separation else 2


def _mean_or_none(vals: list):
    clean = [float(v) for v in vals if v is not None]
    return float(np.mean(clean)) if clean else None


if __name__ == "__main__":
    raise SystemExit(main())
