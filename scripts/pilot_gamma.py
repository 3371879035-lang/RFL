"""Pilot Gamma: does a cheap sequence prior make counterfactual verification
cheaper at equal attribution quality?

Compares, at matched verification budgets:
  sequence_only    -- 0 counterfactual queries
  cf_only(K)       -- K queries in a fixed canonical order
  seq_then_cf(K)   -- K queries chosen by the sequence model's ranking
  oracle           -- evaluator SCM truth
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

from rflnext.gamma import (
    SequenceModel,
    generate_balanced,
    run_method,
    score_method,
)

EXIT_OK = 0
EXIT_GATE_FAILED = 3
EXIT_NO_COMPOSITION_EFFECT = 2


def load_config(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return ""


def method_plan(budgets: list) -> list:
    plan = ["oracle", "sequence_only"]
    for k in budgets:
        plan.append(("cf_only", k))
        plan.append(("seq_then_cf", k))
    return plan


def label_for(entry) -> str:
    if isinstance(entry, tuple):
        return f"{entry[0]}_k{entry[1]}"
    return entry


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--seeds", type=int, default=None)
    ap.add_argument("--n-traces", type=int, default=None)
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    exp = cfg["experiment"]
    gen = cfg["generation"]
    if args.seeds is not None:
        exp["seeds"] = args.seeds
    if args.n_traces is not None:
        gen["n_total"] = args.n_traces

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "config.yaml").write_text(
        yaml.safe_dump(cfg, allow_unicode=True, sort_keys=True), encoding="utf-8"
    )

    n_total = int(gen["n_total"])
    n_train = int(gen["n_train"])
    horizon = int(cfg["environment"]["horizon"])
    p_hazard = float(gen["p_hazard"])
    alpha_diag = float(cfg["learning"]["alpha_diag"])
    budgets = [int(b) for b in cfg["budgets"]]
    plan = method_plan(budgets)

    per_seed = []
    for index in range(int(exp["seeds"])):
        seed = int(exp["seed_base"]) + index
        traces = generate_balanced(
            n_total, seed=seed, horizon=horizon, p_hazard=p_hazard
        )
        train, test = traces[:n_train], traces[n_train:]
        model = SequenceModel().fit(train)

        rows = {}
        for entry in plan:
            name = entry[0] if isinstance(entry, tuple) else entry
            k = entry[1] if isinstance(entry, tuple) else 0
            atts = run_method(name, test, model, k=k)
            rows[label_for(entry)] = score_method(
                label_for(entry), atts, test, alpha_diag=alpha_diag
            )
        per_seed.append({"seed": seed, "n_train": len(train), "n_test": len(test),
                         "methods": rows})
        summary_bits = " ".join(
            f"{label_for(e)}:brier={rows[label_for(e)]['brier']:.4f}"
            f"/cf={rows[label_for(e)]['mean_cf_queries']:.2f}"
            for e in plan
        )
        print(f"[seed {seed}] {summary_bits}", flush=True)

    # Pool across seeds by averaging the per-seed metric.
    labels = [label_for(e) for e in plan]
    pooled = {}
    for lab in labels:
        keys = per_seed[0]["methods"][lab].keys()
        pooled[lab] = {
            key: (
                sum(s["methods"][lab][key] for s in per_seed) / len(per_seed)
                if all(isinstance(s["methods"][lab][key], (int, float))
                       and s["methods"][lab][key] is not None for s in per_seed)
                else None
            )
            for key in keys
        }

    pareto = sorted(
        (
            {
                "method": lab,
                "mean_cf_queries": pooled[lab]["mean_cf_queries"],
                "brier": pooled[lab]["brier"],
                "update_precision": pooled[lab]["update_precision"],
                "collateral_rate": pooled[lab]["collateral_rate"],
                "expected_knowledge_damage": pooled[lab]["expected_knowledge_damage"],
                "auprc_H": pooled[lab]["auprc_H"],
                "auprc_L": pooled[lab]["auprc_L"],
                "auprc_E": pooled[lab]["auprc_E"],
            }
            for lab in labels
        ),
        key=lambda r: (r["mean_cf_queries"], r["brier"]),
    )

    # Pre-registered composition test: at ONE query, does the sequence prior
    # beat the fixed order, and does it match the two-query fixed order?
    summary = {
        "schema_version": cfg["schema_version"],
        "experiment": exp["name"],
        "git_commit": git_commit(),
        "config": cfg,
        "per_seed": per_seed,
        "pooled": pooled,
        "pareto": pareto,
    }
    (outdir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n=== Pareto: verification cost vs attribution quality ===")
    print(f"{'method':<18}{'cf_queries':>11}{'brier':>9}{'upd_prec':>10}"
          f"{'collat':>9}{'exp_KD':>9}{'auprc_H':>9}{'auprc_L':>9}{'auprc_E':>9}")
    for r in pareto:
        print(f"{r['method']:<18}{r['mean_cf_queries']:>11.2f}{r['brier']:>9.4f}"
              f"{(r['update_precision'] or 0):>10.4f}{(r['collateral_rate'] or 0):>9.4f}"
              f"{r['expected_knowledge_damage']:>9.5f}"
              f"{(r['auprc_H'] or 0):>9.4f}{(r['auprc_L'] or 0):>9.4f}"
              f"{(r['auprc_E'] or 0):>9.4f}")

    comp = {
        "seq_then_cf_k1_vs_cf_only_k1": _relative(
            pooled, "seq_then_cf_k1", "cf_only_k1", "brier"
        ),
        "seq_then_cf_k1_vs_cf_only_k2": _relative(
            pooled, "seq_then_cf_k1", "cf_only_k2", "brier"
        ),
    }
    summary["composition"] = comp
    (outdir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\n=== composition (lower Brier is better) ===")
    for name, info in comp.items():
        if info:
            print(f"  {name}: {info}")

    advantage = bool(
        comp.get("seq_then_cf_k1_vs_cf_only_k1")
        and comp["seq_then_cf_k1_vs_cf_only_k1"]["brier_delta"] < 0.0
    )
    print(f"\nsequence-prior advantage at equal budget = {advantage}")

    if args.report_only:
        return EXIT_OK
    return EXIT_OK if advantage else EXIT_NO_COMPOSITION_EFFECT


def _relative(pooled: dict, a: str, b: str, key: str) -> dict | None:
    if a not in pooled or b not in pooled:
        return None
    va, vb = pooled[a].get(key), pooled[b].get(key)
    if va is None or vb is None:
        return None
    return {
        f"{key}_{a}": float(va),
        f"{key}_{b}": float(vb),
        f"{key}_delta": float(va) - float(vb),
        "cf_queries_a": float(pooled[a]["mean_cf_queries"]),
        "cf_queries_b": float(pooled[b]["mean_cf_queries"]),
    }


if __name__ == "__main__":
    raise SystemExit(main())
