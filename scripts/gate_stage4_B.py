"""Gate L under the decided criterion (A51): identify ``B``, not ``Z``.

``13-GATE-L-FAILURE.md`` §4, amendment A51.

``Z`` is fault *presence*; a fault can be present and yet have no effect on any
trajectory, feedback or outcome, and such a fault is indistinguishable from its
own absence at every budget. Demanding that ``Z`` be recovered therefore failed
Gate L for 2,695 of 2,749 multi-``Z`` classes -- proved, not measured.

``B`` is but-for *relevance*: it already answers the question RFL actually asks
(what is worth repairing), and ``R_causal`` is defined on it. So the gate's
target becomes ``B`` while ``Z`` stays as the world's mechanism flag.

Two implementation points that decide whether this is honest:

* ``B`` is computed by ``kernel.but_for_relevance`` with ``omega`` HELD FIXED,
  which is the frozen definition (A26). Resampling the tape would be a different
  operation and would silently inflate separability.
* Representatives are deduplicated on ``(dynamical_key, B)``, NOT on
  ``dynamical_key`` alone. Worlds that agree on all dynamics but disagree on
  ``B`` must stay distinct, or the compression would hide exactly the
  non-identifiability the gate exists to detect.

The label vector is ordered by ``CAUSE_KEYS``, so component ``i`` of the label is
``B`` for ``Z_i``.
"""

from __future__ import annotations

import json
import pathlib
import sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gate_stage2 import LatentCase, reference_provider, sigma0  # noqa: E402
from gate_stage3 import build_partition, class_local_queries, dynamical_key  # noqa: E402
from gate_stage4 import B_CF, precompute, solve_class  # noqa: E402
from identifiability_gate import CAUSE_KEYS  # noqa: E402
from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

_BKEYS = ("Z_P", "Z_D", "Z_X", "Z_E", "Z_U")
_cache: dict = {}


def b_of(sol, case: LatentCase):
    """``B(ell)`` with omega held fixed, memoised on the full world."""
    key = (case.kappa, case.phi, case.error_flag, case.cause_rank,
           case.base_option, case.Z, case.option_fault, case.decision,
           case.controller, case.plant, case.trap)
    hit = _cache.get(key)
    if hit is None:
        d = K.but_for_relevance(
            kappa=case.kappa, tape=case.tape(),
            command_provider=reference_provider(sol),
            base_option=case.base_option, mask=case.mask(),
            option_fault=case.option_fault)
        hit = tuple(d[k] for k in _BKEYS)
        _cache[key] = hit
    return hit


def one_label(mask, lab):
    first = None
    mm = mask
    while mm:
        b = mm & -mm
        v = lab[b.bit_length() - 1]
        if first is None:
            first = v
        elif v != first:
            return False
        mm ^= b
    return True


def closure(sol, reps, queries, full, lab):
    """Proved depth, or None if no finite depth separates. No depth cap."""
    seen, stack = {full}, [full]
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
    known = {H for H in seen if one_label(H, lab)}
    rounds = 0
    while True:
        if full in known:
            return rounds
        rounds += 1
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


def main() -> int:
    sol = solve_reference()
    classes, _a, n_feasible, _c = build_partition(sol)
    print(f"partition: {len(classes):,} classes from {n_feasible:,} feasible cases")

    depth_hist = Counter()
    b_diff = Counter()
    proved_unbounded = 0
    nondeterministic_B = 0
    z_was_unbounded_but_B_is_not = 0
    examples = []

    for i, (sig, members) in enumerate(classes.items()):
        by_key: dict = {}
        for m in members:
            k = (dynamical_key(m), b_of(sol, m))
            if k not in by_key:
                by_key[k] = m
        reps = list(by_key.values())
        lab = [b_of(sol, m) for m in reps]

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
                                 "n_distinct_B": len(set(lab)),
                                 "n_distinct_Z": len({m.Z for m in members}),
                                 "reason": "no query legal on the class"})
            continue

        d = closure(sol, reps, queries, full, lab)
        if d is None:
            proved_unbounded += 1
            depth_hist["unbounded"] += 1
            # attribute the residual: find two reps with different B that no
            # query legal on both can tell apart. A tree can only split along
            # query responses, so such a pair is unidentifiable at any budget.
            tables = []
            from gate_stage3 import response as _resp
            for q, _l, _p in queries:
                t = {}
                for j, mm in enumerate(reps):
                    r = _resp(sol, mm, q)
                    if r is not None:
                        t[j] = r
                tables.append(t)
            found = None
            n = len(reps)
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
                b_diff[keys] += 1
            else:
                b_diff[("<no pair; needs 3+ worlds>",)] += 1
            if len(examples) < 20:
                examples.append({"class_index": i, "class_size": len(members),
                                 "n_reps": len(reps),
                                 "n_distinct_B": len(set(lab)),
                                 "n_distinct_Z": len({m.Z for m in members}),
                                 "witness_B_differs_on":
                                     list(b_diff and (keys if found else [])),
                                 "reason": "fixed point, root unseparated"})
        else:
            depth_hist[d] += 1

    print("\ndepth histogram under the B criterion:")
    for k in sorted(depth_hist, key=lambda x: (isinstance(x, str), str(x))):
        print(f"  D = {str(k):<9} {depth_hist[k]}")

    ints = [k for k in depth_hist if isinstance(k, int)]
    worst = max(ints, default=0)
    fails = proved_unbounded + sum(v for k, v in depth_hist.items()
                                   if isinstance(k, int) and k > B_CF)
    verdict = (f"Gate L PASS at B_CF = {B_CF}" if fails == 0 else
               f"Gate L FAIL at B_CF = {B_CF}: {fails} classes")
    print(f"\nB_min_adaptive = max_C D(C) = {worst}   (B_CF = {B_CF})")
    print(f"proved unidentifiable at any depth: {proved_unbounded}")
    print(verdict)

    print("\nresidual: which B components the unseparable witness differs on")
    print("  (per-class FIRST witness; coordinates shown are the ones that pair "
          "happens\nto differ on, so this is a pointer to the obstruction, not an "
          "additive\naxis count — the same class can be attributed to a different "
          "coordinate\nwhen the query family changes)")
    for k in sorted(b_diff, key=lambda x: -b_diff[x]):
        print(f"  {'+'.join(k):<28} {b_diff[k]}")

    if examples:
        print("\nresidual failures (first few):")
        for e in examples[:6]:
            print("  ", json.dumps(e))

    out = ROOT / "outputs" / "rebuild" / "gate_stage4_B.json"
    out.write_text(json.dumps({
        "criterion": "separate B (but-for relevance), omega held fixed (A26, A51)",
        "B_CF": B_CF,
        "depth_histogram": {str(k): v for k, v in depth_hist.items()},
        "max_adaptive_depth": worst,
        "proved_unbounded": proved_unbounded,
        "residual_witness_B_components": {"+".join(k): v for k, v in b_diff.items()},
        "verdict": verdict,
        "examples": examples,
    }, indent=1, default=str), encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
