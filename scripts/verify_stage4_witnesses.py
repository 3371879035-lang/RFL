"""Every positive Stage 4 depth claim, replayed. There are only 54 of them.

Stage 4's negative claim (2,695 classes are not identifiable at B_CF = 4) is
corroborated by V1 (all-classes necessary condition) and by the DP-free capacity
bound. Its positive claim is narrower and should therefore be checked in full,
not sampled: exactly the classes reported at finite depth. For each one we
rebuild the tree and walk it, asserting every leaf carries a single Z.

A depth claim with no replayable witness is not a result.
"""

from __future__ import annotations

import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gate_stage2 import LatentCase  # noqa: E402,F401
from gate_stage3 import (  # noqa: E402
    build_partition, class_local_queries, dynamical_key,
)
from gate_stage4 import precompute, solve_class  # noqa: E402
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402


def bits(mask):
    out = []
    while mask:
        b = mask & -mask
        out.append(b.bit_length() - 1)
        mask ^= b
    return out


def build_tree(reps, queries, H, d):
    """Reconstruct a depth-<=d tree for H, or None."""
    zlab = [m.Z for m in reps]
    if len({zlab[i] for i in bits(H)}) <= 1:
        return {"leaf": sorted({zlab[i] for i in bits(H)})}
    if d == 0:
        return None
    for q, legal, parts in queries:
        if H & ~legal:
            continue
        branches = [H & p for p in parts if H & p]
        if len(branches) < 2:
            continue
        kids = []
        ok = True
        deepest = 0
        for b in branches:
            t = build_tree(reps, queries, b, d - 1)
            if t is None:
                ok = False
                break
            deepest = max(deepest, t.get("d", 0))
            kids.append(t)
        if ok and deepest + 1 <= d:
            return {"q": repr(q), "d": deepest + 1, "kids": kids}
    return None


def walk(reps, t) -> bool:
    if "leaf" in t:
        return len(t["leaf"]) <= 1
    if not t.get("kids"):
        return False
    return all(walk(reps, k) for k in t["kids"])


def main() -> int:
    sol = solve_reference()
    classes, *_ = build_partition(sol)

    checked = bad = 0
    for i, (sig, members) in enumerate(classes.items()):
        if len({m.Z for m in members}) < 2:
            continue
        by_key: dict = {}
        for m in members:
            by_key.setdefault(dynamical_key(m), m)
        reps = list(by_key.values())
        qfam = class_local_queries(sol, members[0].kappa, members[0].phi, sig[0])
        queries, full, _n = precompute(sol, reps, qfam)
        if not queries:
            continue
        d, _m, _r = solve_class(reps, queries, full)
        if d is None:
            continue
        checked += 1
        tree = build_tree(reps, queries, full, d)
        if tree is None or not walk(reps, tree):
            bad += 1
            print(f"  BAD class {i} depth={d} reps={len(reps)} q={len(queries)}")
        else:
            leaves = []

            def collect(t):
                if "leaf" in t:
                    leaves.append(t["leaf"])
                else:
                    for k in t["kids"]:
                        collect(k)
            collect(tree)
            print(f"  ok  class {i:>5} depth={d} leaves={len(leaves)} "
                  f"distinct_Z={len({m.Z for m in members})} q={len(queries)}")

    print(f"\nall finite-depth classes: {checked} checked, {bad} failed to replay")
    print("VERIFIED" if bad == 0 and checked > 0 else "VERIFICATION FAILED")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
