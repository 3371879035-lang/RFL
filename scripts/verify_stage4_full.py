"""Full independent re-derivation of Stage 4's depth for EVERY multi-Z class.

Stage 4's load-bearing claim is negative: 2,140 classes cannot be identified
within B_CF = 4. The capacity bound cannot corroborate those (their raw branching
is sufficient -- beta^4 >= nZ -- so the obstruction is structural), so the DP is
the only witness. One implementation checking itself is not verification.

This recomputes the same quantity by a deliberately different route:

  * bottom-up closure instead of top-down recursion;
  * an explicit downward-closed set of masks reached from the root, then a
    depth-by-depth fixed point over that set, instead of memoised recursion;
  * NO early exit on `best == 1`, NO `worst >= best` cutoff, NO reliance on the
    recursion order.

    S_0 = {H : |Z(H)| = 1}
    S_d = S_{d-1} U {H : some q legal on H splits H into >= 2 blocks all in S_{d-1}}
    D(C) <= d  iff  C in S_d

Agreement on all 2,921 classes is the claim; disagreement is a bug in one of the
two, and is reported with the class index rather than swallowed.
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
    build_partition, class_local_queries, dynamical_key,
)
from gate_stage4 import B_CF, precompute, solve_class  # noqa: E402
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402


def bits(m):
    out = []
    while m:
        b = m & -m
        out.append(b.bit_length() - 1)
        m ^= b
    return out


def closure_and_depth(reps, queries, full, max_depth=B_CF):
    """Bottom-up fixed point. Returns the smallest d with full in S_d, or None."""
    zlab = [m.Z for m in reps]

    # downward-closed set of masks reachable from the root by repeated branching
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

    known = {H for H in seen if one_z(H)}       # S_0
    for d in range(0, max_depth + 1):
        if full in known:                        # D(C) <= d, and d is minimal
            return d
        if d == max_depth:
            break
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
            return None
        known |= new
    return None


def main() -> int:
    sol = solve_reference()
    classes, *_ = build_partition(sol)
    print(f"partition: {len(classes):,} classes")

    agree = disagree = skipped = 0
    mismatches = []
    hist = Counter()

    for i, (sig, members) in enumerate(classes.items()):
        if len({m.Z for m in members}) < 2:
            continue
        by_key: dict = {}
        for m in members:
            by_key.setdefault(dynamical_key(m), m)
        reps = list(by_key.values())
        qfam = class_local_queries(sol, members[0].kappa, members[0].phi, sig[0])
        queries, full, _n = precompute(sol, reps, qfam)

        dp_d, _m, _r = solve_class(reps, queries, full) if queries else (None, None, 0)
        bu_d = closure_and_depth(reps, queries, full) if queries else None

        hist[str(bu_d)] += 1
        if dp_d == bu_d:
            agree += 1
        else:
            disagree += 1
            if len(mismatches) < 20:
                mismatches.append({"class_index": i, "dp": dp_d, "bottom_up": bu_d,
                                   "n_reps": len(reps), "n_queries": len(queries),
                                   "n_distinct_Z": len({m.Z for m in members})})

    print(f"\nbottom-up vs memoised DP over every multi-Z class:")
    print(f"  agree    {agree}")
    print(f"  disagree {disagree}")
    print(f"\nbottom-up depth histogram:")
    for k in sorted(hist, key=lambda x: (x in ("None",), str(x))):
        print(f"  D = {k:<9} {hist[k]}")

    ok = disagree == 0
    print(f"\n{'VERIFIED — two independent algorithms agree on every class' if ok else 'VERIFICATION FAILED'}")
    out = ROOT / "outputs" / "rebuild" / "verify_stage4_full.json"
    out.write_text(json.dumps({
        "agree": agree, "disagree": disagree, "mismatches": mismatches,
        "bottom_up_histogram": dict(hist), "verified": ok,
    }, indent=1, default=str), encoding="utf-8")
    print(f"wrote {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
