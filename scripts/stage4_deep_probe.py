"""How deep WOULD the adaptive tree have to be, if the budget were not the issue?

Gate L failed at the frozen B_CF = 4. Reporting only "FAIL" leaves the resolution
undetermined, because two very different worlds produce the same verdict:

  * BUDGET-BOUND -- most classes clear at depth 5-6. The cause space is
    |2^5| = 32 patterns while the factual query family is only ~7-8 queries long,
    so B_CF = 4 is simply tight. The fix is a design decision about the budget,
    argued and frozen BEFORE any seed.
  * LABEL-BOUND -- many classes need depth >= 10, or are unbounded. No plausible
    budget fixes that; the labels themselves are not separable by this query
    family and §4's resolution 1 (merge) is the honest route.

It also extracts the airtight part of the failure: classes where two cases with
DIFFERENT Z agree on EVERY query. Those are observationally equivalent, so they
are unidentifiable at ANY depth and ANY budget -- no arithmetic about tree
capacity can rescue them, and no future amendment to B_CF can either. That is a
proof, not a measurement, and it must be reported separately from the depth
counts.
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
from gate_stage4 import precompute, solve_class  # noqa: E402
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

DEEP = 8


def main() -> int:
    sol = solve_reference()
    classes, *_ = build_partition(sol)
    print(f"partition: {len(classes):,} classes")

    hist = Counter()
    by_nz = Counter()
    unidentifiable_any_depth = []
    equiv_witness = []

    for i, (sig, members) in enumerate(classes.items()):
        zs = {m.Z for m in members}
        if len(zs) < 2:
            hist["single_Z"] += 1
            continue

        by_key: dict = {}
        for m in members:
            by_key.setdefault(dynamical_key(m), m)
        reps = list(by_key.values())
        qfam = class_local_queries(sol, members[0].kappa, members[0].phi, sig[0])
        queries, full, _n = precompute(sol, reps, qfam)

        # ---- observational equivalence, independent of any depth ---------- #
        if not queries:
            # every query is constant across reps: all reps are indistinguishable
            by_z: dict = {}
            for m in reps:
                by_z.setdefault(m.Z, m)
            if len(by_z) > 1:
                zlist = sorted(by_z)
                unidentifiable_any_depth.append({
                    "class_index": i, "class_size": len(members),
                    "n_reps": len(reps), "n_distinct_Z": len(by_z),
                    "n_query_candidates": len(qfam),
                    "Z_pair": [list(zlist[0]), list(zlist[1])],
                })
                equiv_witness.append({
                    "class_index": i,
                    "Z_a": list(zlist[0]), "Z_b": list(zlist[1]),
                    "kappa": reps[0].kappa, "phi": reps[0].phi,
                    "base_option": reps[0].base_option,
                    "sigma0_a": str(sigma0_of(sol, by_z[zlist[0]])),
                    "sigma0_b": str(sigma0_of(sol, by_z[zlist[1]])),
                })
            hist["observationally_equivalent"] += 1
            by_nz[(len(by_z), "EQUIV")] += 1
            continue

        d, _m, _r = solve_class(reps, queries, full, max_depth=DEEP)
        hist["unbounded" if d is None else d] += 1
        by_nz[(len(zs), "unbounded" if d is None else d)] += 1

    print("\ndecidability vs number of distinct Z in the class:")
    print(f"{'nZ':>4} | " + "  ".join(f"D={k:>9}" for k in
          ["1", "2", "3", "4", "5", "6", "7", "8", "unbounded", "EQUIV"]))
    for nz in sorted({k[0] for k in by_nz}):
        cells = [f"{by_nz.get((nz, k), 0):>11}" for k in
                 ["1", "2", "3", "4", "5", "6", "7", "8", "unbounded", "EQUIV"]]
        print(f"{nz:>4} | " + "  ".join(cells))

    print(f"\ndepth with the budget opened to {DEEP}:")
    for k in sorted(hist, key=lambda x: (isinstance(x, str), str(x))):
        print(f"  D = {str(k):<28} {hist[k]}")

    fixed_by_raising = sum(v for k, v in hist.items()
                          if isinstance(k, int) and k > 4)
    print(f"\nclasses that B_CF = 4 loses but a larger budget would win: {fixed_by_raising}")
    print(f"observationally EQUIVALENT pairs (unidentifiable at ANY budget): "
          f"{hist['observationally_equivalent']}")
    print(f"still unbounded up to depth {DEEP}: {hist['unbounded']}")

    if equiv_witness:
        print("\n=== airtight non-identifiability witnesses ===")
        for w in equiv_witness[:3]:
            print(f"\n class {w['class_index']}  Z_a={w['Z_a']}  Z_b={w['Z_b']}")
            print(f"   kappa={w['kappa']} phi={w['phi']} base_option={w['base_option']}")
            print(f"   sigma0_a = {w['sigma0_a']}")
            print(f"   sigma0_b = {w['sigma0_b']}")
            print("   -> same factual observation, same response to every legal query")

    out = ROOT / "outputs" / "rebuild" / "stage4_deep_probe.json"
    out.write_text(json.dumps({
        "deep_limit": DEEP,
        "histogram": {str(k): v for k, v in hist.items()},
        "by_n_distinct_Z": {f"{k[0]}|{k[1]}": v for k, v in by_nz.items()},
        "n_unidentifiable_any_depth": len(unidentifiable_any_depth),
        "n_fixed_by_raising_budget": fixed_by_raising,
        "unidentifiable_examples": unidentifiable_any_depth[:50],
        "equivalence_witnesses": equiv_witness[:20],
    }, indent=1, default=str), encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


def sigma0_of(sol, case):
    from gate_stage2 import sigma0
    sig, err = sigma0(sol, case)
    return "ERR:" + str(err) if sig is None else sig[0]


if __name__ == "__main__":
    raise SystemExit(main())
