"""The formal evaluator/metric pipeline — the ONLY one. Oracle and every real arm
go through this identical code; only the source of the prediction differs (A60).

Frozen conventions, because each was a place where a different choice would have
silently changed the ceiling:

* ``p`` is FIVE INDEPENDENT MARGINALS (A59), not a mutually-exclusive
  distribution. So ECE does per-cause **binary** calibration and then a macro
  average. Computing ECE as a 5-class softmax would be measuring a different
  object.
* macro = unweighted mean over the five causes, pre-registered here.
* AUROC uses midranks for ties, so exact 0/1 predictions still give exactly 1.
* AUPRC is average precision over the ranked positives of that cause.

No third-party dependency: the ceiling must not depend on a library's tie
convention.
"""

from __future__ import annotations

from dataclasses import dataclass

N_CAUSES = 5
CAUSES = ("P", "D", "X", "E", "U")
THRESHOLD = 0.5
ECE_BINS = 10


@dataclass(frozen=True, slots=True)
class Metrics:
    macro_auprc: float
    macro_auroc: float
    exact_set_accuracy: float
    hamming: float
    brier: float
    ece: float
    auprc: tuple
    auroc: tuple
    ece_per_cause: tuple
    n_scenes: int
    # A63: a per-cause metric can be UNDEFINED because the batch contains no
    # scene of that class. That is a property of the batch, not of the method, so
    # it is reported as NOT_EVALUABLE rather than as nan -- and the macro is taken
    # over the EVALUABLE causes only, with the two sets named in the artifact.
    evaluable_causes: tuple = ()
    not_evaluable_causes: tuple = ()
    macro_over: str = "all causes"

    def __post_init__(self) -> None:
        if self.macro_over == "all causes" and self.not_evaluable_causes:
            raise ValueError(
                "macro_over must name the evaluable set when some cause is "
                "NOT_EVALUABLE; silently averaging over all five would treat an "
                "undefined per-cause metric as zero")


NOT_EVALUABLE = "NOT_EVALUABLE"


def _definition(x) -> bool:
    """A per-cause metric is defined iff the batch has both classes."""
    return isinstance(x, float) and not (x != x)      # not NaN


def _check(P, Y):
    if len(P) != len(Y):
        raise ValueError(f"prediction/label length mismatch: {len(P)} vs {len(Y)}")
    if not P:
        raise ValueError("empty evaluation set")
    for row in P:
        if len(row) != N_CAUSES:
            raise ValueError("prediction rows must have 5 entries")
    for row in Y:
        if len(row) != N_CAUSES:
            raise ValueError("label rows must have 5 entries")


def auprc_binary(scores, labels) -> float:
    """Average precision. Perfect separation gives exactly 1.0."""
    pos = sum(labels)
    if pos == 0:
        return float("nan")          # undefined; the fixture must prevent this
    order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
    hits = 0
    total = 0.0
    for rank, i in enumerate(order, start=1):
        if labels[i] == 1:
            hits += 1
            total += hits / rank
    return total / pos


def auroc_binary(scores, labels) -> float:
    """Mann-Whitney with midranks, so ties cannot bias the ceiling."""
    pos = sum(labels)
    neg = len(labels) - pos
    if pos == 0 or neg == 0:
        return float("nan")
    order = sorted(range(len(scores)), key=lambda i: scores[i])
    ranks = [0.0] * len(scores)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        midrank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = midrank
        i = j + 1
    rank_sum = sum(ranks[k] for k in range(len(scores)) if labels[k] == 1)
    return (rank_sum - pos * (pos + 1) / 2.0) / (pos * neg)


def brier(P, Y) -> float:
    tot = 0.0
    n = 0
    for p, y in zip(P, Y):
        for i in range(N_CAUSES):
            tot += (p[i] - y[i]) ** 2
            n += 1
    return tot / n


def ece_per_cause(scores, labels, bins: int = ECE_BINS) -> float:
    """Per-cause BINARY calibration error, then averaged by the caller.

    Empty bins are skipped rather than counted as zero, which would flatter a
    degenerate predictor.
    """
    n = len(scores)
    if n == 0:
        return float("nan")
    total = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [i for i, s in enumerate(scores)
               if (lo < s <= hi) or (b == 0 and s <= 0.0)]
        if not idx:
            continue
        conf = sum(scores[i] for i in idx) / len(idx)
        acc = sum(labels[i] for i in idx) / len(idx)
        total += (len(idx) / n) * abs(acc - conf)
    return total


def evaluate(P, Y) -> Metrics:
    _check(P, Y)
    auprcs, aurocs, eces = [], [], []
    for i in range(N_CAUSES):
        s = [row[i] for row in P]
        y = [row[i] for row in Y]
        auprcs.append(auprc_binary(s, y))
        aurocs.append(auroc_binary(s, y))
        eces.append(ece_per_cause(s, y))

    exact = sum(1 for p, y in zip(P, Y)
                if all((p[i] > THRESHOLD) == (y[i] == 1)
                       for i in range(N_CAUSES))) / len(P)
    ham = sum(sum((p[i] > THRESHOLD) != (y[i] == 1)
                  for i in range(N_CAUSES))
              for p, y in zip(P, Y)) / (len(P) * N_CAUSES)
    ev = tuple(CAUSES[i] for i in range(N_CAUSES) if _definition(auprcs[i]))
    nev = tuple(CAUSES[i] for i in range(N_CAUSES) if not _definition(auprcs[i]))
    if not ev:
        raise ValueError(
            "no cause is evaluable on this batch; the primary endpoint is "
            "undefined and must be reported as such")
    idx = [i for i in range(N_CAUSES) if CAUSES[i] in ev]
    return Metrics(
        macro_auprc=sum(auprcs[i] for i in idx) / len(idx),
        macro_auroc=sum(aurocs[i] for i in idx) / len(idx),
        exact_set_accuracy=exact, hamming=ham, brier=brier(P, Y),
        ece=sum(eces[i] for i in idx) / len(idx),
        auprc=tuple(auprcs), auroc=tuple(aurocs), ece_per_cause=tuple(eces),
        n_scenes=len(P),
        evaluable_causes=ev, not_evaluable_causes=nev,
        macro_over=("all causes" if not nev else
                    "evaluable causes only: " + ",".join(ev)),
    )


# --------------------------------------------------------------------------- #
# mutation negative controls (A60) — each must be KILLED by the gate
# --------------------------------------------------------------------------- #

def mutate_swap_PD(P):
    return [(r[1], r[0], r[2], r[3], r[4]) for r in P]


def mutate_softmax(P):
    out = []
    for r in P:
        s = sum(r) or 1.0
        out.append(tuple(v / s for v in r))
    return out


def mutate_shift_rows(P):
    return P[1:] + P[:1]


def mutate_flip_one(P, k=0):
    out = list(P)
    row = list(out[k])
    row[CAUSES.index("U")] = 1.0 - row[CAUSES.index("U")]
    out[k] = tuple(row)
    return out
