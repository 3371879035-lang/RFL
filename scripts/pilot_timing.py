"""Pilot: attribution timing x historical revision (Stage 3).

Cells: {immediate, deferred} x {fixed, revisable}.  Every cell sees the same
seeds and the same episode schedule, so the contrast is paired.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np
import yaml

from rflnext.stats_ext import summary_contrast
from rflnext.timing import CELLS, run_cell

EXIT_OK = 0
EXIT_NO_REVISION_BENEFIT = 2

PAIRS = (
    ("immediate_revisable", "immediate_fixed"),
    ("deferred_revisable", "deferred_fixed"),
    ("deferred_fixed", "immediate_fixed"),
    ("deferred_revisable", "immediate_revisable"),
    # The plan warns that patching Q by -dQ_old is only an approximation; this
    # contrast measures how far the approximation drifts from a real replay.
    ("immediate_revisable", "immediate_revisable_naive"),
    ("deferred_revisable", "deferred_revisable_naive"),
)
METRICS = (
    "overcredit_after_lucky",
    "overcredit_after_contradiction",
    "correct_credit_after_contradiction",
    "recovery_episodes",
    "revision_precision",
    "false_reversal_rate",
)


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

    cells = list(exp["cells"])
    rows = []
    ledger_rows = []
    for index in range(int(exp["seeds"])):
        seed = int(exp["seed_base"]) + index
        for cell in cells:
            res = run_cell(cfg, seed=seed, cell=cell)
            for rec in res.revision_records:
                ledger_rows.append({"seed": seed, "cell": cell, **asdict(rec)})
            rows.append({
                "seed_index": index, "seed": seed, "cell": cell,
                "overcredit_after_lucky": res.overcredit_after_lucky,
                "overcredit_after_contradiction": res.overcredit_after_contradiction,
                "correct_credit_after_contradiction": res.correct_credit_after_contradiction,
                "recovery_episodes": res.recovery_episodes,
                "revisions": res.revisions,
                "true_revisions": res.true_revisions,
                "false_reversals": res.false_reversals,
                "revision_precision": res.revision_precision,
                "false_reversal_rate": res.false_reversal_rate,
                "n_diagnosis": res.n_diagnosis,
                "n_cf": res.n_cf,
                "wall_s": res.wall_s,
            })
        print(f"[seed {seed}] " + "  ".join(
            f"{c}:oc={next(r for r in rows if r['seed'] == seed and r['cell'] == c)['overcredit_after_contradiction']:+.3f}"
            f"/rec={next(r for r in rows if r['seed'] == seed and r['cell'] == c)['recovery_episodes']}"
            for c in cells), flush=True)

    by_cell: dict = {}
    for r in rows:
        by_cell.setdefault(r["cell"], {})[r["seed"]] = r

    pooled = {}
    for c in cells:
        pooled[c] = {
            m: (
                float(np.mean([v[m] for v in by_cell[c].values() if v[m] is not None]))
                if any(v[m] is not None for v in by_cell[c].values()) else None
            )
            for m in METRICS
        }
        pooled[c]["n_diagnosis"] = float(np.mean([v["n_diagnosis"] for v in by_cell[c].values()]))
        pooled[c]["revisions"] = float(np.mean([v["revisions"] for v in by_cell[c].values()]))
        pooled[c]["false_reversals"] = float(np.mean([v["false_reversals"] for v in by_cell[c].values()]))

    rng = np.random.RandomState(0)
    contrasts: dict = {}
    for a, b in PAIRS:
        for metric in METRICS:
            xs, ys = [], []
            for s in sorted(set(by_cell[a]) & set(by_cell[b])):
                va, vb = by_cell[a][s][metric], by_cell[b][s][metric]
                if va is None or vb is None:
                    continue
                xs.append(float(va))
                ys.append(float(vb))
            if len(xs) < 2:
                continue
            x, y = np.array(xs), np.array(ys)
            contrasts.setdefault(f"{a}_minus_{b}", {})[metric] = summary_contrast(
                x, y, n_perm=10000, n_boot=10000, rng=rng
            )

    summary = {
        "schema_version": cfg["schema_version"],
        "experiment": exp["name"],
        "git_commit": git_commit(),
        "config": cfg,
        "seeds": rows,
        "pooled": pooled,
        "contrasts": contrasts,
    }
    (outdir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (outdir / "revision_ledger.jsonl").open("w", encoding="utf-8") as fh:
        for row in ledger_rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"\nwrote {len(ledger_rows)} revision-ledger rows to revision_ledger.jsonl")

    print("\n=== pooled by cell ===")
    print(f"{'cell':<22}{'overcredit$':>12}{'overcredit#':>12}{'correct#':>10}"
          f"{'recovery':>10}{'rev_prec':>10}{'false_rev':>11}{'revisions':>11}{'diag':>8}")
    for c in cells:
        p = pooled[c]
        fmt = lambda v, w=10, nd=4: (f"{v:>{w}.{nd}f}" if v is not None else f"{'-':>{w}}")
        print(f"{c:<22}{fmt(p['overcredit_after_lucky'],12)}{fmt(p['overcredit_after_contradiction'],12)}"
              f"{fmt(p['correct_credit_after_contradiction'],10)}"
              f"{fmt(p['recovery_episodes'],10,2)}{fmt(p['revision_precision'],10)}"
              f"{fmt(p['false_reversal_rate'],11)}{fmt(p['revisions'],11,2)}{fmt(p['n_diagnosis'],8,2)}")
    print("  overcredit$ = after lucky phase; # = after contradiction phase")
    print("  overcredit = Q(wrong plan), lower is better; correct# = Q(right plan), higher is better")

    print("\n=== key contrast: does revisable credit beat fixed? ===")
    key = contrasts.get("immediate_revisable_minus_immediate_fixed", {})
    for metric, info in key.items():
        print(f"  {metric:<32} mean={info['mean']:+.5f} "
              f"CI=[{info['ci'][0]:+.5f},{info['ci'][1]:+.5f}] p={info['p_sign_flip']:.4f}")
    print("\n=== key contrast: does deferral add anything? ===")
    key2 = contrasts.get("deferred_revisable_minus_immediate_revisable", {})
    for metric, info in key2.items():
        print(f"  {metric:<32} mean={info['mean']:+.5f} "
              f"CI=[{info['ci'][0]:+.5f},{info['ci'][1]:+.5f}] p={info['p_sign_flip']:.4f}")

    oc = key.get("overcredit_after_contradiction")
    benefit = bool(oc and oc["mean"] < 0.0 and oc["ci"][1] < 0.0)
    print(f"\nrevisable credit reduces residual overcredit = {benefit}")

    if args.report_only:
        return EXIT_OK
    return EXIT_OK if benefit else EXIT_NO_REVISION_BENEFIT


if __name__ == "__main__":
    raise SystemExit(main())
