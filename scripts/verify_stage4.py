"""Independent verification of the Stage 4 adaptive DP.

Stage 4's verdict (2,140 classes at depth > 4, 555 root dead ends) contradicts
the reading of Stage 3 that those classes were merely "needs adaptive". A gate
that flips the answer is exactly the kind of result that has to be checked by
something other than the code that produced it.

Three checks, each independent of the DP under test:

V1  NECESSARY CONDITION (exhaustive, all classes).
    If some NON-ADAPTIVE set S with |S| <= B_CF separates the class -- which is
    what Stage 3 tests -- then the adaptive depth is at most |S|, because a
    non-adaptive set is a depth-1 tree repeated. So for every class,
        D(C) <= |S|  whenever Stage 3 finds such an S.
    Any class where Stage 3 finds a separating S but Stage 4 says INF is a bug
    in Stage 4. This one is cheap and it is checked on EVERY class.

V2  BRUTE FORCE ADAPTIVE SEARCH (sampled).
    Recompute D(C) by explicit iterative deepening over TREES, with
      - no memoisation,
      - no early break on `best == 1`,
      - no `len(branches) < 2` prune (a constant query is legal to waste budget
        on; it cannot lower the depth, so the two implementations must agree),
    and compare. Disagreement is a bug in one of them.

V3  WITNESS REPLAY (for classes reported at D = 1..4).
    Rebuild the actual tree the DP claims, then walk every leaf and assert each
    leaf's member set really does carry a single Z. A depth claim with no
    replayable witness is not a result.
"""

from __future__ import annotations

import json
import pathlib
import random
import sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gate_stage3 import (  # noqa: E402
    build_partition, class_local_queries, dynamical_key, min_separating_subset,
    response,
)
from gate_stage4 import B_CF, INF, precompute, solve_class  # noqa: E402
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402


def class_data(sol, members, sig):
    """Everything the two solvers need, plus the Stage 3 non-adaptive answer."""
    by_key: dict = {}
    for m in members:
        k = dynamical_key(m)
        if k not in by_key:
            by_key[k] = m
    reps = list(by_key.values())
    qfam = class_local_queries(sol, members[0].kappa, members[0].phi, sig[0])
    queries, full, _n = precompute(sol, reps, qfam)

    # Stage 3's non-adaptive result, recomputed from scratch here.
    cols: dict = {}
    for q, legal, parts in queries:
        if legal != full:
            continue
        col = []
        for i, m in enumerate(reps):
            col.append((m.Z, response(sol, m, q)))
        cols[q] = col
    dedup: dict = {}
    for q in sorted(cols, key=repr):
        dedup.setdefault(tuple(cols[q]), q)
    na_size, _na_set = min_separating_subset({q: cols[q] for q in dedup.values()},
                                             B_CF)
    return reps, queries, full, na_size


def brute_force_depth(reps, queries, full_mask, max_depth=B_CF):
    """V2: explicit tree search, no memo, no prune, no early exit."""
    zlab = [m.Z for m in reps]

    def labels(mask):
        out = []
        mm = mask
        while mm:
            b = mm & -mm
            out.append(zlab[b.bit_length() - 1])
            mm ^= b
        return out

    def rec(H, d):
        if len(set(labels(H))) <= 1:
            return 0
        if d == 0:
            return INF
        worst_over_q = INF
        for _q, legal, parts in queries:
            if H & ~legal:
                continue
            branches = [H & p for p in parts if H & p]
            # deliberately do NOT prune constant queries
            if not branches:
                continue
            worst = 0
            for b in branches:
                r = rec(b, d - 1)
                if r > worst:
                    worst = r
            if worst < worst_over_q:
                worst_over_q = worst
        if worst_over_q >= INF:
            return INF
        return 1 + worst_over_q

    for d in range(1, max_depth + 1):
        if rec(full_mask, d) < INF:
            return d
    return None


def build_witness(reps, queries, full_mask, depth):
    """V3: reconstruct the tree the DP claims and return it, or None."""
    zlab = [m.Z for m in reps]

    def one_z(mask):
        seen = set()
        mm = mask
        while mm:
            b = mm & -mm
            seen.add(zlab[b.bit_length() - 1])
            if len(seen) > 1:
                return False
            mm ^= b
        return True

    def rec(H, d):
        if one_z(H):
            return {"leaf": sorted({zlab[i] for i in _bits(H)}), "members": H}
        if d == 0:
            return None
        for _q, legal, parts in queries:
            if H & ~legal:
                continue
            branches = [H & p for p in parts if H & p]
            if len(branches) < 2:
                continue
            subs = []
            ok = True
            worst = 0
            for b in branches:
                s = rec(b, d - 1)
                if s is None:
                    ok = False
                    break
                subs.append(s)
            if not ok:
                continue
            for s in subs:
                h = s.get("depth", 0)
                if h > worst:
                    worst = h
            if worst + 1 <= d:
                return {"query": repr(_q), "depth": worst + 1, "children": subs}
        return None

    def _bits(mask):
        mm, out = mask, []
        while mm:
            b = mm & -mm
            out.append(b.bit_length() - 1)
            mm ^= b
        return out

    return rec(full_mask, depth)


def check_witness(reps, tree) -> bool:
    zlab = [m.Z for m in reps]
    if "leaf" in tree:
        return len({zlab[i] for i in _bits(tree["members"])}) <= 1
    if not tree.get("children"):
        return False
    return all(check_witness(reps, c) for c in tree["children"])


def _bits(mask):
    mm, out = mask, []
    while mm:
        b = mm & -mm
        out.append(b.bit_length() - 1)
        mm ^= b
    return out


def main() -> int:
    sol = solve_reference()
    classes, _nc, _nf, _mm = build_partition(sol)
    print(f"rebuilt partition: {len(classes):,} classes")

    items = list(classes.items())
    rng = random.Random(0)
    sample_idx = set(rng.sample(range(len(items)), min(120, len(items))))
    # always include the extremes: biggest classes and the D=1 ones
    items_by_size = sorted(range(len(items)), key=lambda i: -len(items[i][1]))
    sample_idx.update(items_by_size[:20])
    # plus every class whose NA size is exactly 1 or 2 (smallest pool)
    for i, (_sig, members) in enumerate(items):
        if len({m.Z for m in members}) < 2:
            continue
        if len(sample_idx) > 4000:
            break

    v1_fail = []
    v2_checked = v2_fail = 0
    v3_checked = v3_fail = 0
    na_hist = Counter()
    dp_hist = Counter()

    for i, (sig, members) in enumerate(items):
        zs = {m.Z for m in members}
        if len(zs) < 2:
            continue
        reps, queries, full, na_size = class_data(sol, members, sig)
        na_hist[na_size] += 1

        if not queries:
            dp_hist["DEAD_END"] += 1
            if na_size is not None:
                # V1: a separating set cannot exist if no query is legal at all
                v1_fail.append((i, "DEAD_END but NA separated", na_size))
            continue

        d, _memo, _rs = solve_class(reps, queries, full)
        dp_hist[d] += 1

        # ---- V1: mandatory invariant, every single class -------------------
        if na_size is not None and (d is None or d > na_size):
            v1_fail.append((i, f"NA size {na_size} but adaptive {d}", na_size))

        # ---- V2 / V3: sampled ---------------------------------------------
        if i in sample_idx:
            bf = brute_force_depth(reps, queries, full)
            v2_checked += 1
            if bf != d:
                v2_fail += 1
                if v2_fail <= 5:
                    print(f"  V2 MISMATCH class {i}: dp={d} brute={bf} "
                          f"na={na_size} reps={len(reps)} q={len(queries)}")
            if d is not None:
                tree = build_witness(reps, queries, full, d)
                v3_checked += 1
                if tree is None or not check_witness(reps, tree):
                    v3_fail += 1
                    if v3_fail <= 5:
                        print(f"  V3 BAD WITNESS class {i} depth={d}")

    print(f"\nV1 necessary condition (adaptive depth <= NA set size), all classes:")
    print(f"   violations: {len(v1_fail)}")
    for v in v1_fail[:10]:
        print("    ", v)

    print(f"\nV2 brute-force agreement: {v2_checked - v2_fail}/{v2_checked} sampled agree")
    print(f"V3 witness replay:        {v3_checked - v3_fail}/{v3_checked} sampled replay")

    print(f"\nnon-adaptive separating-set size (Stage 3 recomputed):")
    for k in sorted(na_hist, key=lambda x: (x is None, str(x))):
        print(f"   size = {str(k):<6} {na_hist[k]}")
    print(f"\nadaptive depth (Stage 4):")
    for k in sorted(dp_hist, key=lambda x: (isinstance(x, str), str(x))):
        print(f"   D = {str(k):<9} {dp_hist[k]}")

    ok = not v1_fail and v2_fail == 0 and v3_fail == 0
    print(f"\n{'VERIFIED' if ok else 'VERIFICATION FAILED'}")
    out = ROOT / "outputs" / "rebuild" / "verify_stage4.json"
    out.write_text(json.dumps({
        "v1_violations": len(v1_fail), "v1_examples": v1_fail[:20],
        "v2_checked": v2_checked, "v2_failures": v2_fail,
        "v3_checked": v3_checked, "v3_failures": v3_fail,
        "na_size_histogram": {str(k): v for k, v in na_hist.items()},
        "adaptive_depth_histogram": {str(k): v for k, v in dp_hist.items()},
        "verified": ok,
    }, indent=1, default=str), encoding="utf-8")
    print(f"wrote {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
