"""Statistics the research plan asks for that the vendored ``stats`` module lacks.

Kept separate so the vendored ``stats.py`` stays byte-identical to the frozen
copy it was taken from.

Plan requirements covered here:

* paired permutation test and bootstrap CI -- already in ``stats.py``
* **Wilcoxon signed-rank as a robustness supplement**
* **probability of improvement**
* **Holm correction across the primary comparisons**
"""

from __future__ import annotations

import numpy as np

from .stats import holm_correct  # re-export so callers need one import

__all__ = ["holm_correct", "wilcoxon_signed_rank", "probability_of_improvement",
           "summary_contrast"]


def wilcoxon_signed_rank(x, y) -> float | None:
    """Two-sided Wilcoxon signed-rank p-value, or ``None`` if undefined.

    Undefined when every paired difference is zero (no ranks to speak of) or
    when scipy is unavailable; returns ``None`` rather than a fabricated number.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    d = x - y
    if len(d) == 0 or np.all(d == 0.0):
        return None
    try:
        from scipy.stats import wilcoxon

        if np.all(d > 0) or np.all(d < 0):
            # All differences share a sign: the exact two-sided p is 2^-n, and
            # scipy's normal approximation declines to produce one.
            return float(2.0 ** -len(d))
        return float(wilcoxon(d, zero_method="wilcox").pvalue)
    except Exception:
        return None


def probability_of_improvement(
    x, y, *, n_boot: int = 10000, rng: np.random.RandomState | None = None
) -> float:
    """P(mean of arm A > mean of arm B) under a paired bootstrap.

    Reported instead of leaning on a single p < 0.05, per the plan.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(x) != len(y):
        raise ValueError("paired samples must have equal length")
    n = len(x)
    if n == 0:
        return float("nan")
    rng = rng or np.random.RandomState(0)
    diff = x - y
    idx = rng.randint(0, n, size=(n_boot, n))
    means = diff[idx].mean(axis=1)
    return float((means > 0.0).mean())


def summary_contrast(
    x, y, *, n_perm: int = 10000, n_boot: int = 10000,
    rng: np.random.RandomState | None = None,
) -> dict:
    """The full set of paired statistics the plan asks to be reported."""
    from .stats import cohens_dz, paired_bootstrap_ci, paired_sign_flip_test

    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    rng = rng or np.random.RandomState(0)
    diff = x - y
    lo, hi = paired_bootstrap_ci(x, y, n_resample=n_boot, rng=rng)
    w = wilcoxon_signed_rank(x, y)
    return {
        "n_seeds": int(len(x)),
        "mean": float(diff.mean()),
        "median": float(np.median(diff)),
        "ci": [float(lo), float(hi)],
        "cohens_dz": cohens_dz(diff),
        "p_sign_flip": float(paired_sign_flip_test(x, y, n_perm=n_perm, rng=rng)),
        "p_wilcoxon": w,
        "probability_of_improvement": probability_of_improvement(
            x, y, n_boot=n_boot, rng=rng
        ),
    }
