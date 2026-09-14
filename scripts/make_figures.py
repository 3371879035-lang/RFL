"""Fixed figures for the v0.3 results, in the plan's "固定版图" sense.

Reads the artifacts already on disk and writes PNGs.  Deliberately has no
analytical logic: it only renders numbers that the analysis scripts produced.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def _load(root: Path, name: str) -> dict | None:
    path = root / name / "summary.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def fig_alpha(root: Path, out: Path) -> bool:
    s = _load(root, "v03_alpha")
    if not s:
        return False
    fig, ax = plt.subplots(figsize=(7, 4))
    for arm, p in s["pooled"].items():
        ax.plot(p["checkpoints"], p["success_curve"], marker="o", ms=3, label=arm)
    ceiling = 1.0 - s["config"]["environment"]["p_hazard"]
    ax.axhline(ceiling, ls="--", c="grey", lw=1, label=f"structural ceiling {ceiling:.2f}")
    ax.set_xlabel("episode")
    ax.set_ylabel("greedy success rate")
    ax.set_title("Pilot Alpha: Traditional vs Positive-only")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out / "alpha_success_curves.png", dpi=140)
    plt.close(fig)
    return True


def fig_gamma_pareto(root: Path, out: Path) -> bool:
    s = _load(root, "v03_gamma_formal") or _load(root, "v03_gamma")
    if not s:
        return False
    rows = [r for r in s["pareto"] if r["brier"] is not None]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.scatter([r["mean_cf_queries"] for r in rows], [r["brier"] for r in rows],
               s=45, c="tab:blue", zorder=3)
    for r in rows:
        ax.annotate(r["method"], (r["mean_cf_queries"], r["brier"]),
                    fontsize=8, xytext=(4, 4), textcoords="offset points")
    ax.set_xlabel("mean counterfactual queries per failure")
    ax.set_ylabel("Brier score (lower is better)")
    ax.set_title("Pilot Gamma: verification cost vs attribution quality")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out / "gamma_pareto.png", dpi=140)
    plt.close(fig)
    return True


def fig_beta_kd(root: Path, out: Path) -> bool:
    s = _load(root, "v03_beta_formal") or _load(root, "v03_beta")
    if not s:
        return False
    matrix = s["kd_matrix"]
    conds = list(s["pooled"].keys())
    fams = [f for f in matrix if any(matrix[f][c].get("kd_innocent_mean") is not None
                                     for c in conds)]
    fig, ax = plt.subplots(figsize=(9, 3.6))
    width = 0.8 / max(1, len(fams))
    for i, fam in enumerate(fams):
        xs, ys = [], []
        for j, c in enumerate(conds):
            v = matrix[fam][c].get("kd_innocent_mean")
            xs.append(j + i * width - 0.4 + width / 2)
            ys.append(v if v is not None else 0.0)
        ax.bar(xs, ys, width=width, label=fam)
    ax.set_xticks(range(len(conds)))
    ax.set_xticklabels(conds, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("KnowledgeDamage (innocent module)")
    ax.set_title("Pilot Beta: collateral knowledge damage by arm")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(out / "beta_knowledge_damage.png", dpi=140)
    plt.close(fig)
    return True


def fig_stage5(root: Path, out: Path) -> bool:
    s = _load(root, "v03_stage5")
    if not s:
        return False
    names = list(s["settings"])
    means = [s["settings"][n]["contrast"]["d_auc_mean"] for n in names]
    los = [s["settings"][n]["contrast"]["d_auc_ci"][0] for n in names]
    his = [s["settings"][n]["contrast"]["d_auc_ci"][1] for n in names]
    fig, ax = plt.subplots(figsize=(8, 4))
    yerr = [[m - l for m, l in zip(means, los)], [h - m for m, h in zip(means, his)]]
    ax.errorbar(range(len(names)), means, yerr=yerr, fmt="o", capsize=4, c="tab:red")
    ax.axhline(0.0, c="k", lw=1)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("Oracle - Traditional, task AUC")
    ax.set_title("Stage 5: does correct routing ever help? (95% paired CI)")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out / "stage5_difficulty_sweep.png", dpi=140)
    plt.close(fig)
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="outputs")
    ap.add_argument("--outdir", default="outputs/v03_figures")
    args = ap.parse_args(argv)
    root, out = Path(args.root), Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    made = []
    for fn in (fig_alpha, fig_gamma_pareto, fig_beta_kd, fig_stage5):
        if fn(root, out):
            made.append(fn.__name__)
    print(f"wrote {len(made)} figures to {out}: {made}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
