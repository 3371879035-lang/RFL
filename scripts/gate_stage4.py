"""Gate stage 4 — exact depth-limited adaptive DP.

``03-IDENTIFIABILITY.md`` §1.8, amendment A50.

At a node with hypothesis set ``H`` (a bitset over the class's representatives):

    D(H) = 0                                      if all ell in H share one Z
    D(H) = 1 + min_{q in Q_safe(H)} max_o D(H_o)   otherwise
    D(H) = INF                                    if Q_safe(H) is empty

with ``Q_safe(H) = {q : H subset of L_q}``, ``L_q`` the legality bitmask of ``q``.

TWO RULES THAT ARE EASY TO GET WRONG, and both are the whole content of A50:

1. A query that is MALFORMED on part of the class must NOT be deleted from the
   candidate pool. It is malformed *at the root*, and may become well-formed on a
   child ``H`` once the offending cases are eliminated. So we keep every query
   together with its legality bitmask and let the DP apply ``H subset of L_q``
   per node. Deleting early silently caps the adaptive power at non-adaptive.
   Availability of a query is itself partially observable; observing it would
   leak hidden ``M``.

2. A query may be pruned at a node only when its response is CONSTANT on ``H``
   (``len(branches) < 2``, no information at all). A query that leaves the number
   of distinct ``Z`` unchanged must be KEPT -- it can still shrink ``H``, and
   therefore GROW ``Q_safe`` one level down.

Gate L: PASS iff ``max_C D(C) <= B_CF``. A failure is reported, never repaired by
raising the budget: enlarging B_CF is a new amendment, not a rerun.
"""

from __future__ import annotations

import json
import pathlib
import sys
import time
from collections import Counter, defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gate_stage2 import LatentCase  # noqa: E402,F401  (import side effects)
from gate_stage3 import (  # noqa: E402
    build_partition, class_local_queries, dynamical_key, response, sigma0,
)
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

from gate_stage3 import B_Q  # noqa: E402

B_CF = B_Q   # A53: the budget counts ALL queries, not only counterfactual ones
INF = 999


def precompute(sol, reps, qfam):
    """Per query: legality bitmask + response partition over representative idx.

    Illegal cases simply carry no bit in ``legal`` and land in no partition
    block; the DP's ``H & ~legal`` test is what makes such a query unselectable,
    and that test is re-evaluated at every node rather than once at the root.
    """
    n = len(reps)
    queries = []
    n_query_candidates = 0
    for q in sorted(qfam, key=repr):
        n_query_candidates += 1
        legal = 0
        parts: dict = defaultdict(int)
        for i, m in enumerate(reps):
            r = response(sol, m, q)
            if r is None:
                continue
            legal |= 1 << i
            parts[r] |= 1 << i
        if legal == 0 or len(parts) < 2:
            # constant (or undefined) on every single representative: it can
            # never separate anything, on any subset. This is the ONLY prune
            # that is safe at the root.
            continue
        queries.append((q, legal, tuple(parts.values())))
    return queries, (1 << n) - 1, n_query_candidates


def solve_class(reps, queries, full_mask, max_depth=B_CF):
    """Smallest adaptive depth needed, or None if it exceeds ``max_depth``."""
    zlab = [m.Z for m in reps]

    def one_z(mask):
        mm = mask
        first = None
        while mm:
            b = mm & -mm
            i = b.bit_length() - 1
            z = zlab[i]
            if first is None:
                first = z
            elif z != first:
                return False
            mm ^= b
        return True

    memo: dict = {}
    root_safe = sum(1 for _q, legal, _p in queries if legal == full_mask)

    def D(H, d):
        if one_z(H):
            return 0
        if d == 0:
            return INF
        key = (H, d)
        hit = memo.get(key)
        if hit is not None:
            return hit
        best = INF
        for _q, legal, parts in queries:
            if H & ~legal:
                continue
            branches = [H & p for p in parts]
            branches = [b for b in branches if b]
            if len(branches) < 2:
                continue
            worst = 0
            for b in branches:
                r = D(b, d - 1)
                if r > worst:
                    worst = r
                if worst >= best:
                    break
            if worst < best:
                best = worst + 1
                if best == 1:
                    break
        memo[key] = best
        return best

    for d in range(1, max_depth + 1):
        v = D(full_mask, d)
        if v < INF:
            return d, memo, root_safe
    return None, memo, root_safe


def main() -> int:
    t0 = time.time()
    sol = solve_reference()
    classes, n_candidate, n_feasible, malformed = build_partition(sol)
    print(f"partition: {len(classes):,} classes from {n_feasible:,} feasible cases "
          f"({n_candidate:,} candidates, {malformed:,} malformed)")

    depths: Counter = Counter()
    failures = []
    root_dead_ends = 0

    for idx, (sig, members) in enumerate(classes.items()):
        zs = {m.Z for m in members}
        if len(zs) < 2:
            depths[0] += 1
            continue

        by_key: dict = {}
        for m in members:
            k = dynamical_key(m)
            if k not in by_key:
                by_key[k] = m
        reps = list(by_key.values())

        qfam = class_local_queries(sol, members[0].kappa, members[0].phi, sig[0])
        queries, full, n_cand = precompute(sol, reps, qfam)

        if not queries:
            root_dead_ends += 1
            depths["DEAD_END"] += 1
            failures.append({"class_index": idx, "class_size": len(members),
                             "n_reps": len(reps), "n_distinct_Z": len(zs),
                             "n_query_candidates": n_cand,
                             "reason": "no query legal on the whole class"})
            continue

        d, _memo, root_safe = solve_class(reps, queries, full)
        if d is None:
            depths[">4"] += 1
            failures.append({"class_index": idx, "class_size": len(members),
                             "n_reps": len(reps), "n_distinct_Z": len(zs),
                             "n_query_candidates": n_cand,
                             "n_queries_safe_at_root": root_safe,
                             "reason": "depth > B_CF"})
        else:
            depths[d] += 1

    if time.time() - t0 > 60:
        print(f"[{time.time() - t0:.0f}s]")

    print("\nadaptive depth histogram (0 = single Z, no query needed):")
    for k in sorted(depths, key=lambda x: (isinstance(x, str), str(x))):
        print(f"  D = {str(k):<9} {depths[k]}")

    ints = [k for k in depths if isinstance(k, int)]
    worst = max(ints, default=0)
    n_fail = depths.get(">4", 0) + depths.get("DEAD_END", 0)
    verdict = (f"Gate L PASS at frozen B_CF = {B_CF}"
               if n_fail == 0 else
               f"Gate L FAIL at frozen B_CF = {B_CF}")

    report = {
        "n_classes": len(classes),
        "n_feasible_cases": n_feasible,
        "B_CF": B_CF,
        "depth_histogram": {str(k): depths[k]
                            for k in sorted(depths, key=lambda x: (isinstance(x, str), str(x)))},
        "max_adaptive_depth": worst,
        "root_dead_ends": root_dead_ends,
        "depth_exceeds_budget": depths.get(">4", 0),
        "verdict": verdict,
        "failures": failures[:50],
        "scope_note": (
            "Depth is computed per class on dynamical-key representatives. Cases "
            "sharing a dynamical key have identical response behaviour and identical "
            "Z, so separation over representatives is separation over all members."),
    }

    print(f"\nB_min_adaptive = max_C D(C) = {worst}    (B_CF = {B_CF})")
    print(verdict)
    print(f"root dead-ends (no class-level legal query): {root_dead_ends}")
    if failures:
        print(f"\nfirst failures (of {len(failures)}):")
        for f in failures[:5]:
            print("  ", json.dumps(f))

    out = ROOT / "outputs" / "rebuild" / "gate_stage4.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
