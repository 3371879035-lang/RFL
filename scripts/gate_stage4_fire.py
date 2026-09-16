"""Gate_fire — V0.1R's actual target, under the A54 three-way split.

    Z^pres   fault configured/injected into the latent world
    Z^fire   the mechanism actually EXECUTED on the factual trajectory
    B        removing the fault changes the outcome (counterfactual)

V0.1R's question is "can the system work out *what happened*?". A trap placed at
a cell the episode never enters did not happen; it exists only in the
evaluator's private configuration. So V0.1R's primary target is ``Z^fire``, and
this gate is the one that licenses it.

The other two are retained as diagnostics and are NOT blocking:
  Gate_Z (presence)  -- reported, and expected to fail on dormant faults;
  Gate_B (but-for)   -- reported as a counterfactual secondary endpoint, which
                        `11` §6.2 already says must be reported 'not evaluable'
                        rather than treated as an algorithm negative result.

The three-regime census is printed because it is the concrete payoff of the
split: it separates "never happened" from "happened but was redundant" from
"happened and made a difference", which a single Z vector cannot express.
"""

from __future__ import annotations

import json
import pathlib
import sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gate_stage2 import LatentCase, fire_of  # noqa: E402,F401
from gate_stage3 import (  # noqa: E402
    build_partition, class_local_queries, dynamical_key, response,
)
from gate_stage4 import B_CF, precompute  # noqa: E402
from gate_stage4_B import b_of, closure  # noqa: E402
from identifiability_gate import CAUSE_KEYS  # noqa: E402
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402


def main() -> int:
    sol = solve_reference()
    classes, _a, n_feasible, _c = build_partition(sol)
    print(f"partition: {len(classes):,} classes from {n_feasible:,} feasible cases")

    depth_hist = Counter()
    diff_hist = Counter()
    proved_unbounded = 0
    examples = []

    # ---- A54 three-regime census, over every feasible case ---------------- #
    census = Counter()
    n_pres_fire_gap = 0

    for i, (sig, members) in enumerate(classes.items()):
        for m in members:
            f = fire_of(sol, m)
            b = b_of(sol, m)
            for j, k in enumerate(CAUSE_KEYS):
                if m.Z[j] == 0:
                    continue
                if f[j] == 0:
                    census[(k, "dormant (fired=0, B=%d)" % b[j])] += 1
                else:
                    census[(k, "fired (B=%d)" % b[j])] += 1
                if m.Z[j] != f[j]:
                    n_pres_fire_gap += 1

        by_key: dict = {}
        for m in members:
            by_key.setdefault((dynamical_key(m), fire_of(sol, m)), m)
        reps = list(by_key.values())
        lab = [fire_of(sol, m) for m in reps]

        if len(set(lab)) < 2:
            depth_hist[0] += 1
            continue

        qfam = class_local_queries(sol, members[0].kappa, members[0].phi, sig[0])
        queries, full, _n = precompute(sol, reps, qfam)

        if not queries:
            proved_unbounded += 1
            depth_hist["unbounded"] += 1
            if len(examples) < 20:
                examples.append({"class_index": i, "class_size": len(members),
                                 "n_reps": len(reps),
                                 "n_distinct_fire": len(set(lab)),
                                 "reason": "no query legal on the class"})
            continue

        d = closure(sol, reps, queries, full, lab)
        if d is None:
            proved_unbounded += 1
            depth_hist["unbounded"] += 1
            tables = []
            for q, _l, _p in queries:
                t = {}
                for j, mm in enumerate(reps):
                    r = response(sol, mm, q)
                    if r is not None:
                        t[j] = r
                tables.append(t)
            n = len(reps)
            found = None
            for a in range(n):
                for b in range(a + 1, n):
                    if lab[a] == lab[b]:
                        continue
                    if all(not (a in t and b in t and t[a] != t[b])
                           for t in tables):
                        found = (lab[a], lab[b])
                        break
                if found:
                    break
            if found:
                keys = tuple(CAUSE_KEYS[p] for p in range(5)
                             if found[0][p] != found[1][p])
                diff_hist[keys] += 1
            else:
                diff_hist[("<needs 3+ worlds>",)] += 1
            if len(examples) < 20:
                examples.append({"class_index": i, "class_size": len(members),
                                 "n_reps": len(reps),
                                 "n_distinct_fire": len(set(lab)),
                                 "witness_fire_differs_on":
                                     list(keys) if found else [],
                                 "reason": "fixed point, root unseparated"})
        else:
            depth_hist[d] += 1

    print("\nA54 three-regime census over causes present in some world:")
    for k in CAUSE_KEYS:
        for regime in ("dormant (fired=0, B=0)", "dormant (fired=0, B=1)",
                       "fired (B=0)", "fired (B=1)"):
            v = census.get((k, regime), 0)
            if v:
                print(f"  {k}  {regime:<24} {v}")
    print(f"\n  (pres != fire) cause-world pairs: {n_pres_fire_gap}")

    print("\ndepth histogram under the Z^fire target:")
    for k in sorted(depth_hist, key=lambda x: (isinstance(x, str), str(x))):
        print(f"  D = {str(k):<9} {depth_hist[k]}")

    ints = [k for k in depth_hist if isinstance(k, int)]
    worst = max(ints, default=0)
    fails = proved_unbounded + sum(v for k, v in depth_hist.items()
                                   if isinstance(k, int) and k > B_CF)
    verdict = (f"Gate_fire PASS at B_Q = {B_CF}" if fails == 0 else
               f"Gate_fire FAIL at B_Q = {B_CF}: {fails} classes")
    print(f"\nB_min_adaptive = max_C D(C) = {worst}   (B_Q = {B_CF})")
    print(f"proved unidentifiable at any depth: {proved_unbounded}")
    print(verdict)

    if diff_hist:
        print("\nresidual witnesses -- which Z^fire components differ:")
        for k in sorted(diff_hist, key=lambda x: -diff_hist[x]):
            print(f"  {'+'.join(k):<28} {diff_hist[k]}")

    out = ROOT / "outputs" / "rebuild" / "gate_stage4_fire.json"
    out.write_text(json.dumps({
        "target": "Z^fire (A54)",
        "B_Q": B_CF,
        "depth_histogram": {str(k): v for k, v in depth_hist.items()},
        "max_adaptive_depth": worst,
        "proved_unbounded": proved_unbounded,
        "verdict": verdict,
        "three_regime_census": {f"{k[0]}|{k[1]}": v for k, v in census.items()},
        "pres_ne_fire_pairs": n_pres_fire_gap,
        "residual_witness_components": {"+".join(k): v
                                        for k, v in diff_hist.items()},
        "examples": examples,
    }, indent=1, default=str), encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
