"""Prospective within-seed paired aggregation; never samples or acquires data.

Cell membership/order/weights must be independently preregistered. This module
does not choose the study's cells, population, failure conditioning or weights.
No episode/cell is silently promoted to an independent statistical seed.
"""
from __future__ import annotations

from fractions import Fraction
import math

ENDPOINTS = {("P", "RMST"), ("P", "DeficitAUC"), ("P", "BehavioralCollateral"),
             ("P", "Retention"), ("T", "RMST"), ("T", "DeficitAUC")}
CELL_KEYS = {"cell_id", "weight_numerator", "weight_denominator"}
ROW_KEYS = {"seed", "cell_id", "regime", "statistic", "reference", "treatment"}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def validate_cells(cells):
    require(type(cells) is list and cells, "complete prospectively declared cells required")
    require(all(type(c) is dict and set(c) == CELL_KEYS for c in cells), "closed cell declaration required")
    ids, weights = [], []
    for c in cells:
        require(type(c["cell_id"]) is str and c["cell_id"], "named cell required")
        a, b = c["weight_numerator"], c["weight_denominator"]
        require(type(a) is int and type(b) is int and a > 0 and b > 0,
                "strictly positive exact rational cell weight required")
        ids.append(c["cell_id"]); weights.append(Fraction(a, b))
    require(len(ids) == len(set(ids)) and sum(weights, Fraction()) == 1,
            "unique full cell registry with weights summing exactly to one required")
    require(all(math.isfinite(float(w)) and float(w) > 0 for w in weights),
            "registered weights must remain positive in declared float arithmetic")
    return ids, weights


def ordered_aggregate(values, weights):
    # Preserve the original left-to-right mean when weights are uniform, rather
    # than multiplying each term by 1/n and changing the accumulation arithmetic.
    require(len(values) == len(weights) and values, "complete cell scalar vector required")
    total = 0.0
    uniform = len(set(weights)) == 1
    for value, weight in zip(values, weights):
        total += value if uniform else value * float(weight)
    return total / len(values) if uniform else total


def aggregate_paired_cells(records, expected_seeds, cells, *, regime, statistic):
    require((regime, statistic) in ENDPOINTS, "unknown or pooled regime/endpoint")
    require(type(expected_seeds) in (list, tuple) and expected_seeds and
            all(type(s) is int and s >= 0 for s in expected_seeds) and
            len(set(expected_seeds)) == len(expected_seeds), "full unique frozen seed order required")
    ids, weights = validate_cells(cells)
    require(type(records) is list and len(records) == len(expected_seeds) * len(ids),
            "partial or pseudo replicated seed-cell rectangle")
    require(all(type(r) is dict and set(r) == ROW_KEYS for r in records), "closed seed-cell scalar rows required")
    for r in records:
        require(type(r["seed"]) is int and type(r["cell_id"]) is str and
                r["regime"] == regime and r["statistic"] == statistic,
                "wrong seed type, regime or endpoint identity")
        require(all(type(r[k]) in (int, float) and math.isfinite(r[k])
                    for k in ("reference", "treatment")), "nonfinite/nested/boolean cell scalar")
    expected = [(s, c) for s in expected_seeds for c in ids]
    require([(r["seed"], r["cell_id"]) for r in records] == expected,
            "missing, duplicate or future-completion-order seed/cell join")
    output, width = [], len(ids)
    for i, seed in enumerate(expected_seeds):
        block = records[i*width:(i+1)*width]
        pair = {"seed": seed}
        for arm in ("reference", "treatment"):
            pair[arm] = ordered_aggregate([r[arm] for r in block], weights)
            require(math.isfinite(pair[arm]), "seed aggregation overflow")
        output.append(pair)
    require(len(output) == len(expected_seeds), "independent observations must equal seeds, not cells")
    return output
