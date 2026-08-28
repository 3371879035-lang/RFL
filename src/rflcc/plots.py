"""结果图（S11）。matplotlib Agg 后端，无 GUI。"""

from __future__ import annotations

import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def plot_metric_by_algorithm(
    rows,
    metric: str,
    outpath: str,
    title: str,
    ylabel: str,
) -> None:
    """rows: list of dict(condition, algorithm, value)。"""
    conditions = sorted({r["condition"] for r in rows})
    algos = sorted({r["algorithm"] for r in rows})
    fig, ax = plt.subplots(figsize=(9, 5))
    x = np.arange(len(algos))
    width = 0.8 / max(len(conditions), 1)
    for i, cond in enumerate(conditions):
        vals = [next((r["value"] for r in rows if r["condition"] == cond and r["algorithm"] == a), np.nan)
                for a in algos]
        ax.bar(x + i * width, vals, width, label=cond)
    ax.set_xticks(x + width * (len(conditions) - 1) / 2)
    ax.set_xticklabels(algos)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend()
    fig.tight_layout()
    os.makedirs(os.path.dirname(outpath) or ".", exist_ok=True)
    fig.savefig(outpath, dpi=150)
    plt.close(fig)


def plot_learning_curves(records_by_algo, outpath: str, metric: str = "success") -> None:
    """records_by_algo: {algo: [(episode, value), ...]}。"""
    fig, ax = plt.subplots(figsize=(8, 5))
    for algo, pts in records_by_algo.items():
        pts = sorted(pts)
        ax.plot([p[0] for p in pts], [p[1] for p in pts], marker="o", label=algo)
    ax.set_xlabel("training episodes")
    ax.set_ylabel(metric)
    ax.set_title(f"Learning curve: {metric}")
    ax.legend()
    fig.tight_layout()
    os.makedirs(os.path.dirname(outpath) or ".", exist_ok=True)
    fig.savefig(outpath, dpi=150)
    plt.close(fig)


def plot_cf_pareto(rows, outpath: str) -> None:
    """compute-accuracy Pareto：x=CF transitions，y=AE。"""
    fig, ax = plt.subplots(figsize=(7, 5))
    for r in rows:
        ax.scatter(r["cf_transitions"], r["ae"], label=r["algorithm"])
    ax.set_xlabel("CF simulated transitions (mean)")
    ax.set_ylabel("Attribution Error (AE)")
    ax.set_title("Compute–accuracy trade-off")
    ax.legend()
    fig.tight_layout()
    os.makedirs(os.path.dirname(outpath) or ".", exist_ok=True)
    fig.savefig(outpath, dpi=150)
    plt.close(fig)
