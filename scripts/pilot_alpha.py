"""Pilot Alpha: Traditional (+1/-1) vs Positive-only (+1/0).

Only the failure reward differs between arms.  No attribution, no
counterfactual, no human feedback, no diagnostic update.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import yaml

from rflnext.gates import ceiling_gate, family_gate
from rflnext.metrics import episodes_to_90, final_success, success_auc
from rflnext.runner import train

EXIT_OK = 0
EXIT_NO_DISCRIMINATING_POWER = 2
EXIT_GATE_FAILED = 3


def load_config(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return ""


class _Pooled:
    """Per-arm mean curve over seeds, for the pre-registered gates."""

    def __init__(self, arm: str, records: list):
        self.arm = arm
        self.checkpoints = list(records[0].checkpoints)
        n = len(self.checkpoints)
        self.success_curve = [
            sum(r.success_curve[i] for r in records) / len(records) for i in range(n)
        ]
        self.family_counts = {
            f: sum(r.family_counts.get(f, 0) for r in records)
            for f in records[0].family_counts
        }
        self.winnable_fraction = (
            sum(r.eval_winnable_fraction for r in records) / len(records)
        )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--seeds", type=int, default=None)
    ap.add_argument("--episodes", type=int, default=None)
    ap.add_argument("--eval-every", type=int, default=None)
    ap.add_argument("--eval-episodes", type=int, default=None)
    ap.add_argument("--report-only", action="store_true",
                    help="return 0 even when a scientific gate fails")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    exp = cfg["experiment"]
    if args.seeds is not None:
        exp["seeds"] = args.seeds
    if args.episodes is not None:
        exp["episodes"] = args.episodes
    if args.eval_every is not None:
        exp["eval_every"] = args.eval_every
    if args.eval_episodes is not None:
        exp["eval_episodes"] = args.eval_episodes

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "config.yaml").write_text(
        yaml.safe_dump(cfg, allow_unicode=True, sort_keys=True), encoding="utf-8"
    )

    arms = list(exp["arms"])
    seed_base = int(exp["seed_base"])
    rows = []
    per_arm_records = {arm: [] for arm in arms}

    for index in range(int(exp["seeds"])):
        seed = seed_base + index
        for arm in arms:
            result = train(cfg, seed=seed, arm=arm)
            per_arm_records[arm].append(result)
            row = {
                "seed_index": index,
                "seed": seed,
                "arm": arm,
                "checkpoints": result.checkpoints,
                "success_curve": result.success_curve,
                "success_auc": success_auc(result.success_curve, result.checkpoints),
                "episodes_to_90": episodes_to_90(result.success_curve, result.checkpoints),
                "final_success": final_success(result.success_curve),
                "family_counts": result.family_counts,
                "n_negative_td": result.n_negative_td_total,
                "eval_winnable_fraction": result.eval_winnable_fraction,
                "q_hash": result.q_hash,
            }
            rows.append(row)
            print(f"[seed {seed} {arm:14s}] auc={row['success_auc']:.4f} "
                  f"final={row['final_success']:.3f} "
                  f"neg_td={result.n_negative_td_total:6d} "
                  f"families={result.family_counts}", flush=True)

    pooled = {arm: _Pooled(arm, recs) for arm, recs in per_arm_records.items()}
    gate_cfg = cfg["gate"]
    # The theoretical ceiling assumes the eval tape's hazard share is exactly
    # p_hazard; a finite tape's realized share is what actually caps success,
    # so use that.  Falling back on 1 - p_hazard would flag a policy sitting at
    # its true ceiling as "not saturated" (or vice versa) purely from sampling.
    theoretical_ceiling = 1.0 - float(cfg["environment"]["p_hazard"])
    realized_winnable = sum(p.winnable_fraction for p in pooled.values()) / len(pooled)
    structural_ceiling = realized_winnable
    ceiling = ceiling_gate(
        pooled,
        structural_ceiling=structural_ceiling,
        min_auc_gap=float(gate_cfg["min_auc_gap"]),
    )
    family = family_gate(pooled, min_family_events=int(gate_cfg["min_family_events"]))

    summary = {
        "schema_version": cfg["schema_version"],
        "experiment": exp["name"],
        "git_commit": git_commit(),
        "config": cfg,
        "seeds": rows,
        "pooled": {
            arm: {
                "checkpoints": p.checkpoints,
                "success_curve": p.success_curve,
                "success_auc": success_auc(p.success_curve, p.checkpoints),
                "final_success": final_success(p.success_curve),
                "family_counts": p.family_counts,
            }
            for arm, p in pooled.items()
        },
        "ceiling_gate": {
            "status": ceiling.status, "reasons": ceiling.reasons,
            "finals": ceiling.finals, "aucs": ceiling.aucs,
            "auc_spread": ceiling.auc_spread,
            "saturated_at_ceiling": ceiling.saturated_at_ceiling,
            "structural_ceiling_realized": structural_ceiling,
            "structural_ceiling_theoretical": theoretical_ceiling,
            "realized_winnable_fraction": realized_winnable,
        },
        "family_gate": {"status": family.status, "short_families": family.reasons},
    }
    (outdir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\nstructural ceiling: theoretical(1-p_hazard)={theoretical_ceiling:.3f} "
          f"realized={structural_ceiling:.3f}")
    print(f"ceiling_gate = {ceiling.status} {ceiling.reasons}")
    print(f"   finals = { {k: round(v, 4) for k, v in ceiling.finals.items()} }"
          f"  saturated_at_ceiling={ceiling.saturated_at_ceiling}")
    print(f"   aucs   = { {k: round(v, 4) for k, v in ceiling.aucs.items()} }"
          f"  spread={ceiling.auc_spread:.5f}")
    print(f"family_gate  = {family.status} {family.reasons}")
    for arm, p in pooled.items():
        print(f"   {arm:14s} families={p.family_counts}")

    if args.report_only:
        return EXIT_OK
    if ceiling.status != "ok":
        return EXIT_NO_DISCRIMINATING_POWER
    if family.status != "ok":
        return EXIT_GATE_FAILED
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
