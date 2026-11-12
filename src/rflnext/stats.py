"""Seed-level paired statistics（S11）。

- 统计单位固定为 seed（episode 嵌套在 seed 内，不做 episode-level 伪重复）
- paired sign-flip permutation test（10,000 permutations）
- paired bootstrap 95% CI（10,000 resamples）
- Cohen d_z = mean(diff) / sd(diff)（不含 sqrt(n)，与 paired-t 统计量分开）
- 多重主比较 Holm correction
"""

from __future__ import annotations

import numpy as np


def cohens_dz(diff: np.ndarray) -> float:
    """d_z = mean(diff) / sd(diff, ddof=1)。"""
    d = np.asarray(diff, dtype=float)
    sd = d.std(ddof=1)
    if sd == 0.0:
        return 0.0
    return float(d.mean() / sd)


def paired_t_statistic(diff: np.ndarray) -> float:
    """如需报告 paired t 统计量，单独计算（不混入 d_z）。"""
    return cohens_dz(diff) * np.sqrt(len(diff))


def paired_sign_flip_test(
    x: np.ndarray,
    y: np.ndarray,
    n_perm: int = 10000,
    rng: np.random.RandomState | None = None,
) -> float:
    """paired sign-flip permutation test of mean difference（双尾）。

    返回 p 值：|mean(diff)| 超过观察值 |mean(diff)| 的符号翻转比例。
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(x) != len(y):
        raise ValueError("paired samples must have equal length")
    if rng is None:
        rng = np.random.RandomState(0)
    diff = x - y
    obs = np.abs(diff.mean())
    flips = rng.choice([-1.0, 1.0], size=(n_perm, len(diff)))
    means = np.abs((flips * diff).mean(axis=1))
    return float((means >= obs).mean())


def paired_bootstrap_ci(
    x: np.ndarray,
    y: np.ndarray,
    n_resample: int = 10000,
    ci: float = 0.95,
    rng: np.random.RandomState | None = None,
) -> tuple[float, float]:
    """paired bootstrap 的 mean(diff) 置信区间。"""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    n = len(x)
    if rng is None:
        rng = np.random.RandomState(0)
    diff = x - y
    idx = rng.randint(0, n, size=(n_resample, n))
    means = diff[idx].mean(axis=1)
    lo = (1.0 - ci) / 2
    return float(np.quantile(means, lo)), float(np.quantile(means, 1.0 - lo))


def holm_correct(p_values: list[float], alpha: float = 0.05) -> list[float]:
    """Holm-Bonferroni 校正，返回 adjusted p-values（保序）。"""
    m = len(p_values)
    order = sorted(range(m), key=lambda i: p_values[i])
    adjusted = [0.0] * m
    prev = 0.0
    for rank, i in enumerate(order):
        adj = max((m - rank) * p_values[i], prev)
        adjusted[i] = min(adj, 1.0)
        prev = adjusted[i]
    return adjusted


def seed_level_auc(returns: np.ndarray) -> float:
    """seed-level learning curve 的 AUC（归一化到 [0,1]）。"""
    r = np.asarray(returns, dtype=float)
    if len(r) < 2:
        return float(r.mean()) if len(r) else 0.0
    # 梯形积分除以满面积（max*len），再 clip
    auc = np.trapezoid(r) if hasattr(np, "trapezoid") else np.trapz(r)
    auc = auc / len(r)
    return float(np.clip(auc, 0.0, 1.0))
