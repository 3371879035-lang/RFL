"""The decisive artifact: what exactly is unidentifiable, and why.

Stage 4 established that Gate L fails at B_CF = 4. That alone does not choose
between the two resolutions §4 allows, so this script settles three things and
nothing else.

1. UNBOUNDEDNESS IS PROVED, NOT MEASURED.
   The bottom-up closure of `verify_stage4_full` reaches a fixed point. If the
   fixed point closes with the root still unseparated, then no tree of ANY finite
   depth separates the class -- because `known` is the monotone closure of the
   "separable" predicate over a finite lattice, so its fixed point is exactly the
   set of masks separable at some finite depth. Running it to convergence, with
   no depth cap, turns "not found within 8" into "cannot be done". The DP's
   `max_depth` argument can never make that claim.

2. AIRTIGHT PAIRWISE WITNESSES.
   r1 ~ r2 iff they give the same response to every query legal on both. A tree
   can only ever split worlds along query responses, so a ~-class containing two
   different Z is two worlds no adaptive policy can EVER tell apart. This is
   budget-independent and needs no search at all.

3. WHICH CAUSE IS RESPONSIBLE.
   For each surviving witness we record which of (P, D, X, E, U) the two worlds
   disagree on. That is the input to the resolution decision: a single invisible
   cause argues for either making it observable or merging it into the label set,
   whereas a diffuse pattern argues for a richer query family.

No environment tuning happens here. This script only decides what to report.
"""

from __future__ import annotations

import json
import pathlib
import sys
from collections import Counter, defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gate_stage2 import LatentCase  # noqa: E402,F401
from gate_stage3 import (  # noqa: E402
    build_partition, class_local_queries, dynamical_key, response,
)
from gate_stage4 import precompute  # noqa: E402
from identifiability_gate import CAUSE_KEYS  # noqa: E402
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

NO_CAP = 10_000


def bits(m):
    out = []
    while m:
        b = m & -m
        out.append(b.bit_length() - 1)
        m ^= b
    return out


def closure_to_convergence(reps, queries, full):
    """Returns (depth, proved_unbounded). depth is None iff proved unbounded."""
    zlab = [m.Z for m in reps]

    seen = {full}
    stack = [full]
    while stack:
        H = stack.pop()
        for _q, legal, parts in queries:
            if H & ~legal:
                continue
            for p in parts:
                b = H & p
                if b and b not in seen:
                    seen.add(b)
                    stack.append(b)

    def one_z(H):
        z = None
        for i in bits(H):
            if z is None:
                z = zlab[i]
            elif zlab[i] != z:
                return False
        return True

    known = {H for H in seen if one_z(H)}
    rounds = 0
    while True:
        if full in known:
            return rounds, False
        rounds += 1
        if rounds > NO_CAP:
            raise RuntimeError("closure did not converge")
        new = set()
        for H in seen:
            if H in known:
                continue
            for _q, legal, parts in queries:
                if H & ~legal:
                    continue
                br = [H & p for p in parts if H & p]
                if len(br) < 2:
                    continue
                if all(b in known for b in br):
                    new.add(H)
                    break
        if not new:
            # fixed point reached, root still unseparated => no finite depth works
            return None, True
        known |= new


def never_separable_components(sol, reps, queries):
    """Groups of reps that no adaptive tree can ever split apart.

    A tree can only ever split worlds along a query response, so ``{r1, r2}`` is
    separable iff some query ``q`` is legal on BOTH and returns different
    responses. Two traps here, and getting either wrong manufactures witnesses
    that are not real:

    * A query that is ILLEGAL on one of the two CANNOT separate the pair: under
      A50 it is not selectable at any node that still contains both. So
      "illegal vs legal" must count as NOT separating. Recording it as a
      different response would invent spurious non-identifiability.
    * Do not run union-find over the queries' "cannot tell apart" blocks. Those
      blocks are equivalence relations, and their union's transitive closure is
      strictly COARSER than the intersection we want, so it would merge reps
      that some query does separate -- witness claims that are simply false.

    The complement-of-separability relation is transitive (if r1,r3 were split by
    q while neither r1,r2 nor r2,r3 is, then r2 is legal on q and must match one
    of them and differ from the other, contradiction), so connected components of
    the complement graph are the right grouping. We build the separating pairs
    directly and take components of the complement.
    """
    n = len(reps)
    tables = []
    for q, _legal, _parts in queries:
        t = {}
        for i, m in enumerate(reps):
            r = response(sol, m, q)
            if r is not None:
                t[i] = r
        tables.append(t)

    sep = [set() for _ in range(n)]
    for r1 in range(n):
        for r2 in range(r1 + 1, n):
            for t in tables:
                if r1 in t and r2 in t and t[r1] != t[r2]:
                    sep[r1].add(r2)
                    sep[r2].add(r1)
                    break

    seen = [False] * n
    comps = []
    for s in range(n):
        if seen[s]:
            continue
        seen[s] = True
        stack = [s]
        group = []
        while stack:
            a = stack.pop()
            group.append(a)
            for b in range(n):
                if not seen[b] and b not in sep[a]:
                    seen[b] = True
                    stack.append(b)
        comps.append(group)
    return comps


def main() -> int:
    sol = solve_reference()
    classes, *_ = build_partition(sol)
    print(f"partition: {len(classes):,} classes")

    verdict = Counter()
    diff_hist = Counter()
    witnesses = []
    depth_hist = Counter()

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
        queries, full, _n = precompute(sol, reps, qfam)

        # ---- (2) airtight pairwise witnesses, no search involved ----------- #
        pair_witness = None
        if queries:
            for comp in never_separable_components(sol, reps, queries):
                zset = {}
                for j in comp:
                    zset.setdefault(reps[j].Z, j)
                if len(zset) > 1:
                    zl = sorted(zset)
                    a, b = zl[0], zl[1]
                    keys = tuple(CAUSE_KEYS[p] for p in range(5) if a[p] != b[p])
                    diff_hist[keys] += 1
                    pair_witness = {"Z_a": list(a), "Z_b": list(b),
                                    "differ_on": list(keys)}
                    break
        else:
            zset = {}
            for j, m in enumerate(reps):
                zset.setdefault(m.Z, j)
            if len(zset) > 1:
                zl = sorted(zset)
                a, b = zl[0], zl[1]
                keys = tuple(CAUSE_KEYS[p] for p in range(5) if a[p] != b[p])
                diff_hist[keys] += 1
                pair_witness = {"Z_a": list(a), "Z_b": list(b),
                                "differ_on": list(keys)}

        if pair_witness is None:
            verdict["no_pairwise_witness"] += 1

        # ---- (1) proved unboundedness, no depth cap ------------------------ #
        if not queries:
            d, proved = None, True
        else:
            d, proved = closure_to_convergence(reps, queries, full)

        if proved:
            verdict["PROVED_unbounded_any_depth"] += 1
            if pair_witness is None:
                verdict["unbounded_but_no_pair_witness"] += 1
        else:
            verdict["decidable"] += 1
            depth_hist[d] += 1

        if proved and pair_witness and len(witnesses) < 40:
            witnesses.append({"class_index": i, "class_size": len(members),
                              "n_reps": len(reps), "n_distinct_Z": len(zs),
                              **pair_witness})

    print("\nverdicts:")
    for k in sorted(verdict):
        print(f"  {k:<34} {verdict[k]}")

    print(f"\nfinite depths (these are the only decidable classes):")
    for k in sorted(depth_hist):
        print(f"  D = {k:<4} {depth_hist[k]}")

    print("\nwhich cause keys the never-separable pair disagrees on:")
    for k in sorted(diff_hist, key=lambda x: -diff_hist[x]):
        print(f"  {'+'.join(k):<12} {diff_hist[k]}")

    print("\n=== minimal unidentifiability witnesses (airtight) ===")
    for w in witnesses[:6]:
        print(f"  class {w['class_index']:>5}  nZ={w['n_distinct_Z']:>2}  "
              f"Z_a={w['Z_a']}  Z_b={w['Z_b']}  differ_on={w['differ_on']}")

    out = ROOT / "outputs" / "rebuild" / "stage4_unidentifiable.json"
    out.write_text(json.dumps({
        "verdicts": dict(verdict),
        "finite_depth_histogram": {str(k): v for k, v in depth_hist.items()},
        "differing_cause_keys": {"+".join(k): v for k, v in diff_hist.items()},
        "witnesses": witnesses,
    }, indent=1, default=str), encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
