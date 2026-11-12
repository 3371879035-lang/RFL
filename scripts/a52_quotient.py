"""A52 pre-analysis: the minimal identifiable quotient the current interface supports.

**This changes nothing.** No environment edit, no new target, no query added. It
only reads out the ontology the current observation-and-intervention interface
actually supports, by computing

    B-tilde = B / ~ ,

where ``b ~ b'`` iff some latent world carrying target ``b`` cannot be told apart
from some world carrying ``b'`` by ANY history-dependent safe query policy.

Why the relation is exactly "no single query separates the pair": a tree splits
worlds only along query responses. If ``r1, r3`` were split by ``q`` while
neither ``r1, r2`` nor ``r2, r3`` is, then ``r2`` is legal on ``q`` and must
return one of the two responses, differing from the other -- so one of those
pairs WAS split. Contradiction. Hence the relation is transitive, and "no single
query separates" coincides with "no adaptive tree of any depth separates". So the
quotient is components of the complement-of-separability graph, and it is exact,
not an approximation.

Legality follows A50: a query illegal on either world of a pair cannot separate
that pair, because it is not selectable at any node still containing both. And
``B`` uses the frozen but-for test with omega held fixed (A26).

Reported, as required:

1. the B-vectors actually occurring inside each unresolved terminal hypothesis set;
2. every inseparable ``B <-> B'`` pair;
3. the resulting equivalence components of ``B``;
4. whether collapsing only the ``P`` and ``E`` coordinates makes all 432 vanish;
5. if not, the minimal set of coordinates that must be collapsed.
"""

from __future__ import annotations

import itertools
import json
import pathlib
import sys
from collections import Counter, defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gate_stage2 import LatentCase, reference_provider  # noqa: E402,F401
from gate_stage3 import build_partition, class_local_queries, dynamical_key  # noqa: E402
from gate_stage4 import precompute  # noqa: E402
from gate_stage4_B import b_of  # noqa: E402
from identifiability_gate import CAUSE_KEYS  # noqa: E402
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

IDX = {k: i for i, k in enumerate(CAUSE_KEYS)}       # P D X E U -> 0..4


def components(sol, reps, queries):
    """Emax components: maximal sets no query can split. See module docstring."""
    from gate_stage3 import response as _resp
    n = len(reps)
    tables = []
    for q, _l, _p in queries:
        t = {}
        for i, m in enumerate(reps):
            r = _resp(sol, m, q)
            if r is not None:
                t[i] = r
        tables.append(t)

    sep = [set() for _ in range(n)]
    for a in range(n):
        for b in range(a + 1, n):
            for t in tables:
                if a in t and b in t and t[a] != t[b]:
                    sep[a].add(b)
                    sep[b].add(a)
                    break

    seen = [False] * n
    comps = []
    for s in range(n):
        if seen[s]:
            continue
        seen[s] = True
        stack, group = [s], []
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
    classes, _a, _b, _c = build_partition(sol)
    print(f"partition: {len(classes):,} classes")

    # global graph over B-vectors
    edges = set()
    unresolved = []                 # item 1
    n_split_classes = 0
    n_ambig_classes = 0

    for i, (sig, members) in enumerate(classes.items()):
        by_key: dict = {}
        for m in members:
            by_key.setdefault((dynamical_key(m), b_of(sol, m)), m)
        reps = list(by_key.values())
        lab = [b_of(sol, m) for m in reps]
        if len(set(lab)) < 2:
            continue
        n_split_classes += 1

        qfam = class_local_queries(sol, members[0].kappa, members[0].phi, sig[0])
        queries, _full, _n = precompute(sol, reps, qfam)
        comps = components(sol, reps, queries)

        ambiguous = []
        for comp in comps:
            bs = sorted({lab[j] for j in comp})
            if len(bs) < 2:
                continue
            for x, y in itertools.combinations(bs, 2):
                edges.add((x, y))
            ambiguous.append([list(b) for b in bs])
        if ambiguous:
            n_ambig_classes += 1
            unresolved.append({"class_index": i, "class_size": len(members),
                               "n_distinct_B": len(set(lab)),
                               "terminal_B_sets": ambiguous})

    # item 3: equivalence components of B
    parent = {}

    def find(a):
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for x, y in edges:
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[ry] = rx

    comp_of = defaultdict(list)
    for b in parent:
        comp_of[find(b)].append(b)
    btilde = sorted([sorted(c) for c in comp_of.values()], key=lambda c: (len(c), c))

    print(f"\nclasses spanning >1 B: {n_split_classes}")
    print(f"classes with an inseparable B-pair (residual of Gate_B): {n_ambig_classes}")
    print(f"\ninseparable B<->B' pairs: {len(edges)}")
    print(f"equivalence components of B (B-tilde): {len(btilde)}")
    for c in btilde:
        if len(c) > 1:
            print(f"  [{len(c)}] " + "  ".join("".join(map(str, b)) for b in c))

    # item 4/5: which coordinates must be collapsed
    def ok_under(collapse: frozenset) -> bool:
        keep = [j for j in range(5) if CAUSE_KEYS[j] not in collapse]
        for u in unresolved:
            for bs in u["terminal_B_sets"]:
                if len({tuple(b[j] for j in keep) for b in bs}) > 1:
                    return False
        return True

    trials = []
    best = None
    for size in range(0, 6):
        for combo in itertools.combinations(CAUSE_KEYS, size):
            if ok_under(frozenset(combo)):
                trials.append({"collapse": list(combo), "works": True})
                if best is None:
                    best = combo
        if best is not None:
            break

    print("\nitem 4 -- collapse {P,E} only?")
    pe_ok = ok_under(frozenset({"P", "E"}))
    print(f"  {'YES' if pe_ok else 'NO'}")

    print("\nitem 5 -- minimal coordinate set that must be collapsed:")
    if best is None:
        print("  none up to size 5 (would require collapsing every coordinate)")
    else:
        print(f"  collapse {{{', '.join(best)}}}  (size {len(best)})")
        print(f"  surviving label = "
              f"({', '.join(k for k in CAUSE_KEYS if k not in best)})")

    out = ROOT / "outputs" / "rebuild" / "a52_quotient.json"
    out.write_text(json.dumps({
        "n_classes": len(classes),
        "n_classes_spanning_multiple_B": n_split_classes,
        "n_classes_with_inseparable_B_pair": n_ambig_classes,
        "n_inseparable_pairs": len(edges),
        "B_tilde_components": [[list(b) for b in c] for c in btilde],
        "collapse_PE_suffices": pe_ok,
        "minimal_collapse": list(best) if best else None,
        "unresolved_examples": unresolved[:60],
    }, indent=1, default=str), encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
