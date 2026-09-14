"""Pilot Beta: Penalty x Oracle selective correction.

Compares, on identical scenes and identical seeds:
  * the 2x2 {failure = -1, failure = 0} x {no correction, Oracle correction}
  * the update-rule calibration arms h_only / l_only / hl, i.e. blunt rules that
    correct a module whatever the truth

The headline output is not who wins on success; it is the matrix of
KnowledgeDamage on the correct-but-not-responsible module, per scene family per
rule.
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

from rflnext.beta import CONDITIONS, INNOCENT, train_beta
from rflnext.gates import ceiling_gate, family_gate
from rflnext.metrics import episodes_to_90, final_success, success_auc

EXIT_OK = 0
EXIT_ORACLE_NO_ADVANTAGE = 2
EXIT_GATE_FAILED = 3

MAIN_2X2 = ("traditional", "positive_only", "traditional_oracle", "positive_only_oracle")
BLUNT = ("h_only", "l_only", "hl")


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
    def __init__(self, name: str, records: list):
        self.arm = name
        self.checkpoints = list(records[0].checkpoints)
        n = len(self.checkpoints)
        self.success_curve = [
            sum(r.success_curve[i] for r in records) / len(records) for i in range(n)
        ]
        self.family_counts = {
            f: sum(r.family_counts.get(f, 0) for r in records) for f in INNOCENT
        }
        self.winnable_fraction = (
            sum(r.eval_winnable_fraction for r in records) / len(records)
        )


def _kd_stats(records: list) -> dict:
    """family -> aggregated damage stats for one (seed, condition) cell."""
    events = [d for r in records for d in r.diagnostics]
    out: dict = {}
    for family in INNOCENT:
        sel = [d for d in events if d.family == family]
        innocent_vals = [d.kd_innocent for d in sel if d.kd_innocent is not None]
        out[family] = {
            "n": len(sel),
            "kd_innocent_mean": (
                sum(innocent_vals) / len(innocent_vals) if innocent_vals else None
            ),
            "kd_h_mean": (sum(d.kd_h for d in sel) / len(sel)) if sel else None,
            "kd_l_mean": (sum(d.kd_l for d in sel) / len(sel)) if sel else None,
            "wr_h_mean": (sum(d.wr_h for d in sel) / len(sel)) if sel else None,
            "wr_l_mean": (sum(d.wr_l for d in sel) / len(sel)) if sel else None,
            "margin_h_before_mean": (
                sum(d.margin_h_before for d in sel) / len(sel)
            ) if sel else None,
            "margin_l_before_mean": (
                sum(d.margin_l_before for d in sel) / len(sel)
            ) if sel else None,
            "corrected_h_frac": (sum(d.corrected_h for d in sel) / len(sel)) if sel else None,
            "corrected_l_frac": (sum(d.corrected_l for d in sel) / len(sel)) if sel else None,
        }
    return out


def _kd_matrix(records_by_condition: dict) -> dict:
    """family -> condition -> aggregated damage statistics."""
    out: dict = {f: {} for f in INNOCENT}
    for condition, records in records_by_condition.items():
        events = [d for r in records for d in r.diagnostics]
        for family in INNOCENT:
            sel = [d for d in events if d.family == family]
            if not sel:
                out[family][condition] = {"n": 0}
                continue
            innocent_vals = [d.kd_innocent for d in sel if d.kd_innocent is not None]
            out[family][condition] = {
                "n": len(sel),
                "kd_innocent_mean": (
                    sum(innocent_vals) / len(innocent_vals) if innocent_vals else None
                ),
                "kd_h_mean": sum(d.kd_h for d in sel) / len(sel),
                "kd_l_mean": sum(d.kd_l for d in sel) / len(sel),
                "wr_h_mean": sum(d.wr_h for d in sel) / len(sel),
                "wr_l_mean": sum(d.wr_l for d in sel) / len(sel),
                "margin_h_before_mean": sum(d.margin_h_before for d in sel) / len(sel),
                "margin_l_before_mean": sum(d.margin_l_before for d in sel) / len(sel),
                "corrected_h_frac": sum(d.corrected_h for d in sel) / len(sel),
                "corrected_l_frac": sum(d.corrected_l for d in sel) / len(sel),
            }
    return out


def _oracle_advantage(matrix: dict, *, margin: float) -> dict:
    """Does Oracle beat *every* blunt rule on innocent-module damage, in at
    least one family?  That is the pre-registered precondition for Pilot Gamma."""
    per_family: dict = {}
    any_advantage = False
    for family, by_cond in matrix.items():
        if INNOCENT[family] is None:
            per_family[family] = {"applicable": False, "reason": "no innocent module"}
            continue
        oracle = by_cond.get("traditional_oracle", {}).get("kd_innocent_mean")
        blunt = {
            rule: by_cond.get(rule, {}).get("kd_innocent_mean") for rule in BLUNT
        }
        if oracle is None or any(v is None for v in blunt.values()):
            per_family[family] = {"applicable": False, "reason": "missing arm"}
            continue
        gaps = {rule: float(v) - float(oracle) for rule, v in blunt.items()}
        best_rule = min(gaps, key=gaps.get)
        advantage = gaps[best_rule] >= float(margin)
        any_advantage = any_advantage or advantage
        per_family[family] = {
            "applicable": True,
            "oracle_kd_innocent": float(oracle),
            "blunt_kd_innocent": {k: float(v) for k, v in blunt.items()},
            "gap_vs_closest_blunt": float(gaps[best_rule]),
            "closest_blunt": best_rule,
            "advantage": bool(advantage),
        }
    return {"any_advantage": bool(any_advantage), "per_family": per_family}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--seeds", type=int, default=None)
    ap.add_argument("--episodes", type=int, default=None)
    ap.add_argument("--eval-every", type=int, default=None)
    ap.add_argument("--eval-episodes", type=int, default=None)
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    exp = cfg["experiment"]
    for attr, key in (("seeds", "seeds"), ("episodes", "episodes"),
                      ("eval_every", "eval_every"), ("eval_episodes", "eval_episodes")):
        val = getattr(args, attr)
        if val is not None:
            exp[key] = val

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "config.yaml").write_text(
        yaml.safe_dump(cfg, allow_unicode=True, sort_keys=True), encoding="utf-8"
    )

    conditions = list(exp["conditions"])
    seed_base = int(exp["seed_base"])
    rows = []
    by_condition: dict = {c: [] for c in conditions}

    for index in range(int(exp["seeds"])):
        seed = seed_base + index
        for condition in conditions:
            res = train_beta(cfg, seed=seed, condition=condition)
            by_condition[condition].append(res)
            auc = success_auc(res.success_curve, res.checkpoints)
            rows.append({
                "seed_index": index,
                "seed": seed,
                "condition": condition,
                "reward_mode": res.reward_mode,
                "rule": res.rule,
                "checkpoints": res.checkpoints,
                "success_curve": res.success_curve,
                "success_auc": auc,
                "episodes_to_90": episodes_to_90(res.success_curve, res.checkpoints),
                "final_success": final_success(res.success_curve),
                "family_counts": res.family_counts,
                "n_diagnostic_events": len(res.diagnostics),
                "kd_by_family": _kd_stats([res]),
                "q_hash": res.q_hash,
            })
            print(f"[seed {seed} {condition:20s}] auc={auc:.4f} "
                  f"final={final_success(res.success_curve):.3f} "
                  f"diag={len(res.diagnostics):5d} "
                  f"families={res.family_counts}", flush=True)

    pooled = {c: _Pooled(c, recs) for c, recs in by_condition.items()}
    matrix = _kd_matrix(by_condition)

    gate_cfg = cfg["gate"]
    ceiling = ceiling_gate(
        pooled,
        structural_ceiling=(
            sum(p.winnable_fraction for p in pooled.values()) / len(pooled)
        ),
        min_auc_gap=float(gate_cfg["min_auc_gap"]),
    )
    family = family_gate(pooled, min_family_events=int(gate_cfg["min_family_events"]))
    advantage = _oracle_advantage(matrix, margin=float(gate_cfg["oracle_advantage_kd"]))

    summary = {
        "schema_version": cfg["schema_version"],
        "experiment": exp["name"],
        "git_commit": git_commit(),
        "config": cfg,
        "seeds": rows,
        "pooled": {
            c: {
                "checkpoints": p.checkpoints,
                "success_curve": p.success_curve,
                "success_auc": success_auc(p.success_curve, p.checkpoints),
                "final_success": final_success(p.success_curve),
                "family_counts": p.family_counts,
            }
            for c, p in pooled.items()
        },
        "kd_matrix": matrix,
        "oracle_advantage": advantage,
        # Pilot Beta's primary endpoint is KnowledgeDamage, not success AUC.
        # The AUC spread is recorded as a secondary descriptor of policy
        # utility and is deliberately NOT fatal here (unlike in Pilot Alpha).
        # The fatal gates for Beta are family power and the pre-registered
        # Oracle structural advantage.
        "auc_check": {
            "fatal": False,
            "status": ceiling.status, "reasons": ceiling.reasons,
            "finals": ceiling.finals, "aucs": ceiling.aucs,
            "auc_spread": ceiling.auc_spread,
            "saturated_at_ceiling": ceiling.saturated_at_ceiling,
        },
        "family_gate": {
            "fatal": True, "status": family.status, "short_families": family.reasons,
        },
        "oracle_advantage_gate": {"fatal": True, "passed": bool(advantage["any_advantage"])},
    }
    (outdir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n=== KnowledgeDamage on the correct-but-not-responsible module ===")
    header = f"{'family':<11}" + "".join(f"{c:>22}" for c in conditions)
    print(header)
    for fam in INNOCENT:
        cells = []
        for c in conditions:
            v = matrix[fam][c].get("kd_innocent_mean")
            cells.append(f"{v:>22.5f}" if v is not None else f"{'-':>22}")
        print(f"{fam:<11}" + "".join(cells))
    print("\n(HL_error has no innocent module; E_failure averages both.)")

    print(f"\nauc_check (secondary for Beta, NOT fatal) = {ceiling.status} {ceiling.reasons}")
    print(f"   aucs = { {k: round(v, 4) for k, v in ceiling.aucs.items()} }"
          f"  spread={ceiling.auc_spread:.5f}")
    print(f"family_gate (fatal)  = {family.status} {family.reasons}")
    print(f"oracle_advantage (fatal) = {advantage['any_advantage']}")
    for fam, info in advantage["per_family"].items():
        print(f"   {fam:<11} {info}")

    if args.report_only:
        return EXIT_OK
    if family.status != "ok":
        return EXIT_GATE_FAILED
    if not advantage["any_advantage"]:
        return EXIT_ORACLE_NO_ADVANTAGE
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
