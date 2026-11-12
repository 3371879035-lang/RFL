"""Prospective seed-level statistics candidate; no collection or final verdict.

Inputs must already be one aggregate per independent seed. The population,
contrast, orientation, multiplicity family and complete sample size still need
their own committed preregistration. These functions cannot approve a claim.
No legacy rflnext statistical code is reused.
"""
from __future__ import annotations

from collections import Counter
import math
import random

BOOTSTRAP_RESAMPLES = 10000
BOOTSTRAP_ALGORITHM_SEED = 960031  # analysis RNG, NEVER an environment/training key


def require(ok, message):
    if not ok:
        raise ValueError(message)


def left_sum(xs):
    total = 0.0
    for x in xs:
        total += x
    return total


def average(xs):
    return left_sum(xs) / len(xs)


def median(xs):
    x = sorted(xs)
    n = len(x)
    return x[n // 2] if n % 2 else (x[n // 2 - 1] + x[n // 2]) / 2


def percentile_linear(xs, p):
    x = sorted(xs)
    index = (len(x) - 1) * p
    lo = int(index)
    return x[lo] if lo == len(x) - 1 else x[lo] + (x[lo + 1] - x[lo]) * (index - lo)


def exact_sign_p(d):
    nonzero = [x for x in d if x != 0.0]
    n = len(nonzero)
    if n == 0:
        return None
    k = min(sum(x > 0 for x in nonzero), sum(x < 0 for x in nonzero))
    return min(1.0, 2 * sum(math.comb(n, j) for j in range(k + 1)) / (2 ** n))


def exact_wilcoxon(d):
    """Conditional exact signed-rank distribution, including average tied ranks.

    Ranks are doubled integers. Exact zeros are discarded (wilcox convention).
    Tail probabilities count sign assignments, not a normal approximation.
    All zeros are undefined, not an invented p value.
    """
    values = sorted((abs(x), x > 0) for x in d if x != 0.0)
    if not values:
        return {"statistic": None, "p": None, "reason": "ALL_EXACT_TIES"}
    weights, positive, i = [], 0, 0
    while i < len(values):
        j = i + 1
        while j < len(values) and values[j][0] == values[i][0]:
            j += 1
        weight = (i + 1) + j  # twice the average of ranks i+1..j
        weights.extend([weight] * (j - i))
        positive += weight * sum(sign for _, sign in values[i:j])
        i = j
    total = sum(weights)
    low = min(positive, total - positive)
    distribution = Counter({0: 1})
    for weight in weights:
        shifted = {rank + weight: count for rank, count in distribution.items()}
        distribution.update(shifted)
    count = sum(v for rank, v in distribution.items() if rank <= low or rank >= total - low)
    return {"statistic": low / 2, "p": count / (2 ** len(values)), "reason": None,
            "method": "conditional-exact-average-ties-zero-wilcox"}


def holm(p_values):
    require(bool(p_values) and all(type(p) in (int, float) and math.isfinite(p) and
                                  0 <= p <= 1 for p in p_values), "invalid Holm family")
    order = sorted(range(len(p_values)), key=lambda i: (p_values[i], i))
    result, previous = [0.0] * len(order), 0.0
    for rank, i in enumerate(order):
        previous = min(1.0, max(previous, (len(order) - rank) * p_values[i]))
        result[i] = previous
    return result


def paired_differences(rows, expected_seeds, orientation):
    require(orientation in ("reference-minus-treatment", "treatment-minus-reference"),
            "explicit endpoint orientation required")
    seeds = tuple(expected_seeds)
    require(seeds and all(type(s) is int and s >= 0 for s in seeds) and
            len(set(seeds)) == len(seeds), "invalid expected seed population")
    require(len(rows) == len(seeds), "partial sample or pseudo replication")
    require(all(type(r) is dict and set(r) == {"seed", "reference", "treatment"} for r in rows),
            "one closed aggregate row per seed required")
    require(all(type(r["seed"]) is int for r in rows) and
            tuple(r["seed"] for r in rows) == seeds, "duplicate, missing or reordered seed")
    require(all(type(r[k]) in (int, float) and math.isfinite(r[k]) for r in rows
                for k in ("reference", "treatment")), "missing/nonfinite paired endpoint")
    sign = 1 if orientation == "reference-minus-treatment" else -1
    differences = [sign * (r["reference"] - r["treatment"]) for r in rows]
    require(all(math.isfinite(x) for x in differences), "difference overflow")
    return differences


def summarize(rows, expected_seeds, *, orientation):
    d = paired_differences(rows, expected_seeds, orientation)
    n, center = len(d), average(d)
    ordered, trim = sorted(d), int(.05 * n)
    trimmed = ordered[trim:n - trim] if trim else ordered
    rng = random.Random(BOOTSTRAP_ALGORITHM_SEED)
    boot = [average([d[rng.randrange(n)] for _ in range(n)])
            for _ in range(BOOTSTRAP_RESAMPLES)]
    variance = left_sum([(x - center) ** 2 for x in d]) / (n - 1) if n > 1 else 0.0
    require(math.isfinite(center) and math.isfinite(variance), "statistics arithmetic overflow")
    sign = 1 if center > 0 else -1 if center < 0 else 0
    # Prospective convention: five largest contributions aligned to net direction;
    # tied contributions use frozen input seed order. Not five post-hoc outliers.
    top = sorted(range(n), key=lambda i: (-sign * d[i], i))[:5] if sign else []
    net = left_sum(d)
    top_share = left_sum([d[i] for i in top]) / net if net != 0 else None
    remainder = [x for i, x in enumerate(d) if i not in top]
    return {"role": "SEED_LEVEL_STATISTICS_CANDIDATE_NOT_CONFIRMATORY_VERDICT",
            "n_seeds": n, "orientation": orientation, "mean": center,
            "median": median(d), "trimmed_mean_5pct_each_tail": average(trimmed),
            "tie_fraction": sum(x == 0 for x in d) / n,
            "non_tied_seeds": sum(x != 0 for x in d), "p_exact_sign": exact_sign_p(d),
            "wilcoxon": exact_wilcoxon(d),
            "probability_of_improvement": sum(x > 0 for x in d) / n,
            "paired_bootstrap_95_ci": [percentile_linear(boot, .025), percentile_linear(boot, .975)],
            "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
            "bootstrap_method": "paired-seed-percentile-linear-Python-Random",
            "cohens_dz": center / math.sqrt(variance) if variance > 0 else None,
            "cohens_dz_undefined_reason": None if variance > 0 else "ZERO_SAMPLE_SPREAD",
            "top5_contribution_seed_ids": [rows[i]["seed"] for i in top],
            "top5_share_of_net_sum": top_share,
            "mean_without_top5": average(remainder) if remainder else None,
            "holm_applied": False, "confirmatory_claim_authorized": False,
            "research_complete": False}
