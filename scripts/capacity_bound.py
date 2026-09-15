"""V4 — a counting lower bound on adaptive depth that never runs the DP.

If a class has ``nZ`` distinct cause patterns, any decision tree that identifies
``Z`` must have at least ``nZ`` leaves that are each single-``Z``. A depth-``d``
tree has at most ``beta^d`` leaves, where ``beta`` is the largest number of
distinct responses any single query can produce anywhere in the class (using the
max over ALL queries, not just root-legal ones, so the bound stays valid as
``Q_safe`` grows deeper). Hence

    beta^d < nZ   =>   D(C) > d,  provably.

This is deliberately independent of the Stage 4 DP: it is the "could this
possibly work" question asked with arithmetic instead of search. It also
separates two very different failure stories, which the DP alone cannot:

  * CAPACITY failure -- too few queries / too few responses to ever label nZ
    causes. Widening the budget B_CF cannot fix this; only a richer query family
    or a merged label set can.
  * STRUCTURE failure -- enough raw capacity, but no tree that actually realises
    it. That is a statement about the response patterns.
"""

from __future__ import annotations

import json
import pathlib
import sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gate_stage2 import LatentCase  # noqa: E402,F401
from gate_stage3 import (  # noqa: E402
    build_partition, class_local_queries, dynamical_key, response,
)
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

B_CF = 4


def main() -> int:
    sol = solve_reference()
    classes, _a, _b, _c = build_partition(sol)
    print(f"partition: {len(classes):,} classes")

    verdict = Counter()
    rows = []
    for i, (sig, members) in enumerate(classes.items()):
        zs = {m.Z for m in members}
        if len(zs) < 2:
            verdict["single_Z"] += 1
            continue
        by_key: dict = {}
        for m in members:
            by_key.setdefault(dynamical_key(m), m)
        reps = list(by_key.values())
        qfam = class_local_queries(sol, members[0].kappa, members[0].phi, sig[0])

        beta = 0
        for q in qfam:
            parts = set()
            for m in reps:
                r = response(sol, m, q)
                if r is not None:
                    parts.add(r)
            if len(parts) > beta:
                beta = len(parts)

        nZ = len(zs)
        # smallest d in 1..B_CF with beta^d >= nZ
        d_min = None
        cap = 1
        for d in range(1, B_CF + 1):
            cap = beta ** d
            if cap >= nZ:
                d_min = d
                break

        if beta <= 1:
            verdict["no_query_has_responses"] += 1
        elif d_min is None:
            verdict["CAPACITY_IMPOSSIBLE_at_B_CF"] += 1
            rows.append({"class_index": i, "nZ": nZ, "beta": beta,
                         "n_query_candidates": len(qfam),
                         "capacity_at_4": beta ** B_CF})
        else:
            verdict["capacity_allows"] += 1

    print("\ncapacity classification of the multi-Z classes:")
    for k, v in sorted(verdict.items()):
        print(f"  {k:<34} {v}")

    print(f"\nprovably D > {B_CF} by counting alone (and never a B_CF problem): "
          f"{verdict['CAPACITY_IMPOSSIBLE_at_B_CF'] + verdict['no_query_has_responses']}")

    if rows:
        rows.sort(key=lambda r: -r["nZ"])
        print("\nworst capacity deficits (largest nZ first):")
        for r in rows[:8]:
            print(f"  class {r['class_index']:>5}  nZ={r['nZ']:>3} "
                  f"beta={r['beta']:>3}  capacity(4)={r['capacity_at_4']:>6} "
                  f"q_candidates={r['n_query_candidates']}")

    out = ROOT / "outputs" / "rebuild" / "capacity_bound.json"
    out.write_text(json.dumps({"verdicts": dict(verdict),
                               "worst": rows[:100]}, indent=1, default=str),
                   encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
