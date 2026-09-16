"""A53 outcome: the surviving plant (E) collisions, saved as replayable witnesses.

The plant-input audit removed part of the E obstruction but not all of it. Per the
frozen instruction, the response is to **save the witness, not to escalate the
query** until it can "see E" directly. So this script does not search for a
stronger query. It extracts, for the classes where an E-differing pair survives,
everything needed to adjudicate the obstruction by hand:

* the two ``B`` vectors and both worlds' full latent parameters;
* each world's factual ``(a_cmd, u, a_realized)`` chain, i.e. exactly what the
  audit exposes, so it is visible whether the audit is being *withheld* by
  legality or is simply *uninformative* here;
* whether the plant fault fires at all on the factual rollout.

That last column is the diagnostic one. ``B_E`` is computed by removing the plant
fault and re-running the same tape, so a plant fault that never fires factually
must give ``B_E = 0``. If a witness shows a firing plant fault in one world and
not the other while ``sigma_0`` agrees, the obstruction is in how ``a_realized``
fails to record the firing; if both are non-firing, the two worlds differ in
``B_E`` for a reason that must be found in the removal step itself.
"""

from __future__ import annotations

import json
import pathlib
import sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gate_stage2 import LatentCase, reference_provider, sigma0  # noqa: E402,F401
from gate_stage3 import (  # noqa: E402
    build_partition, class_local_queries, dynamical_key, response,
)
from gate_stage4 import precompute  # noqa: E402
from gate_stage4_B import b_of  # noqa: E402
from identifiability_gate import CAUSE_KEYS  # noqa: E402
from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402


def factual_chain(sol, case):
    tr = K.rollout(kappa=case.kappa, tape=case.tape(),
                   command_provider=reference_provider(sol),
                   base_option=case.base_option, mask=case.mask(),
                   option_fault=case.option_fault)
    return [(s.state.t - 1, s.a_cmd, s.u, s.a_realized) for s in tr.steps]


def world(case):
    return {"Z": list(case.Z), "kappa": case.kappa, "phi": case.phi,
            "base_option": case.base_option, "option_fault": case.option_fault,
            "decision": repr(case.decision), "controller": repr(case.controller),
            "plant": repr(case.plant), "trap": repr(case.trap)}


def main() -> int:
    sol = solve_reference()
    classes, _a, _b, _c = build_partition(sol)
    print(f"partition: {len(classes):,} classes")

    e_witnesses = []
    other_witnesses = []
    kind = Counter()

    for i, (sig, members) in enumerate(classes.items()):
        by_key: dict = {}
        for m in members:
            by_key.setdefault((dynamical_key(m), b_of(sol, m)), m)
        reps = list(by_key.values())
        lab = [b_of(sol, m) for m in reps]
        if len(set(lab)) < 2:
            continue
        qfam = class_local_queries(sol, members[0].kappa, members[0].phi, sig[0])
        queries, _f, _n = precompute(sol, reps, qfam)
        if not queries:
            continue

        tables = []
        for q, _l, _p in queries:
            t = {}
            for j, m in enumerate(reps):
                r = response(sol, m, q)
                if r is not None:
                    t[j] = r
            tables.append(t)

        n = len(reps)
        for a in range(n):
            for b in range(a + 1, n):
                if lab[a] == lab[b]:
                    continue
                if any(a in t and b in t and t[a] != t[b] for t in tables):
                    continue
                keys = tuple(CAUSE_KEYS[p] for p in range(5)
                             if lab[a][p] != lab[b][p])
                chain_a = factual_chain(sol, reps[a])
                chain_b = factual_chain(sol, reps[b])
                # a_cmd != u  => controller/internal problem (X)
                # a_realized != u => external plant problem (E)
                ctrl_a = any(c != u for (_t, c, u, _r) in chain_a)
                ctrl_b = any(c != u for (_t, c, u, _r) in chain_b)
                plant_a = any(r != u for (_t, _c, u, r) in chain_a)
                plant_b = any(r != u for (_t, _c, u, r) in chain_b)
                rec = {
                    "class_index": i, "class_size": len(members),
                    "n_distinct_B": len(set(lab)),
                    "B_a": list(lab[a]), "B_b": list(lab[b]),
                    "differ_on": list(keys),
                    "world_a": world(reps[a]), "world_b": world(reps[b]),
                    "controller_fault_fires_a": ctrl_a,
                    "controller_fault_fires_b": ctrl_b,
                    "plant_fault_fires_a": plant_a,
                    "plant_fault_fires_b": plant_b,
                    "chain_a": chain_a, "chain_b": chain_b,
                    "audit_responses_equal": all(
                        (a not in t) or (b not in t) or t[a] == t[b]
                        for t in tables),
                }
                if keys == ("E",):
                    e_witnesses.append(rec)
                else:
                    other_witnesses.append(rec)
                kind[keys] += 1
                break          # one witness per class is enough to adjudicate
            else:
                continue
            break

    print(f"\nresidual witnesses saved: E-only {len(e_witnesses)}, "
          f"other {len(other_witnesses)}")
    print(f"attribution: {dict(kind)}")

    fires = Counter((w["plant_fault_fires_a"], w["plant_fault_fires_b"])
                    for w in e_witnesses)
    ctrl = Counter((w["controller_fault_fires_a"], w["controller_fault_fires_b"])
                   for w in e_witnesses)
    print("\nE witnesses -- does the PLANT fault (a_realized != u) fire factually?")
    for k, v in sorted(fires.items()):
        print(f"  (a={k[0]}, b={k[1]}): {v}")
    print("   ... and does the CONTROLLER fault (a_cmd != u) fire factually?")
    for k, v in sorted(ctrl.items()):
        print(f"  (a={k[0]}, b={k[1]}): {v}")
    print("   ... do both worlds look identical through the audit (all u_t equal)?")
    same = sum(1 for w in e_witnesses if w["audit_responses_equal"])
    print(f"  audit-identical: {same} / {len(e_witnesses)}")

    if e_witnesses:
        print("\n=== first E witness ===")
        w = e_witnesses[0]
        print(f" class {w['class_index']}  B_a={w['B_a']}  B_b={w['B_b']}")
        print(f" world_a: {json.dumps(w['world_a'], default=str)}")
        print(f" world_b: {json.dumps(w['world_b'], default=str)}")
        print(f" plant fires: a={w['plant_fault_fires_a']} b={w['plant_fault_fires_b']}")
        print(f" chain_a (t,a_cmd,u,a_realized): {w['chain_a']}")
        print(f" chain_b (t,a_cmd,u,a_realized): {w['chain_b']}")

    out = ROOT / "outputs" / "rebuild" / "a53_e_witnesses.json"
    out.write_text(json.dumps({
        "n_e_only": len(e_witnesses), "n_other": len(other_witnesses),
        "attribution": {"+".join(k): v for k, v in kind.items()},
        "plant_fires_histogram": {f"a={k[0]},b={k[1]}": v
                                  for k, v in fires.items()},
        "controller_fires_histogram": {f"a={k[0]},b={k[1]}": v
                                       for k, v in ctrl.items()},
        "audit_identical": same,
        "e_witnesses": e_witnesses[:60],
        "other_witnesses": other_witnesses[:20],
    }, indent=1, default=str), encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
