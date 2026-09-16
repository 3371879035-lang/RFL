"""A60 — Oracle ceiling gate: does the whole label -> prediction -> metric chain
have the right ceiling?

`S1_ORACLE` only checked that `OracleAdapter` was pointed at the right target on
one all-zero sample. That says nothing about the AUPRC/AUROC/Brier/ECE plumbing,
and `06`'s go/no-go requires the ceiling on the **primary endpoint**.

Structure of the gate:

1. a DETERMINISTIC fixture, selected once and fingerprinted into the artifact, so
   the gate cannot quietly re-find "a set that passes";
2. `p^Oracle = Z^fire` fed through the FORMAL pipeline (the same
   `rfl_rebuild.eval` code every real arm will use) — never oracle-only metrics;
3. exact expected values, not soft thresholds. The Oracle input IS the truth, so
   the ceiling is exact; a pure floating-point tolerance is allowed but the
   semantics are 1/0;
4. four MUTATION NEGATIVE CONTROLS. A correct implementation scoring 1 proves
   little on its own; the gate must be shown to KILL a broken pipeline.

Fixture constraints, each of which exists to make a control detectable:

* every cause has both a positive and a negative scene, or AUROC is undefined;
* at least one scene with ``y_P != y_D``, or the P/D swap control cannot be seen;
* at least one scene with ``Z^fire != Z^pres``, or mis-targeting on presence
  cannot be seen.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import pathlib
import sys
from collections import Counter
from dataclasses import asdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gate_stage2 import (  # noqa: E402
    LatentCase, _domains, fire_of, reference_provider, sigma0,
)
from identifiability_gate import CAUSE_KEYS, KAPPAS, TAPES, canonicalise  # noqa: E402
from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.eval import (  # noqa: E402
    CAUSES, N_CAUSES, evaluate, mutate_flip_one, mutate_shift_rows,
    mutate_softmax, mutate_swap_PD,
)
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

TOL = 1e-12
POOL_CAP = 60_000
FIXTURE_SIZE = 64
EXACT = {"macro_auprc": 1.0, "macro_auroc": 1.0, "exact_set_accuracy": 1.0,
         "hamming": 0.0, "brier": 0.0, "ece": 0.0}


def fingerprint(case) -> str:
    key = (case.kappa, case.phi, case.error_flag, case.cause_rank,
           case.base_option, case.Z, case.option_fault, case.decision,
           case.controller, case.plant, case.trap)
    return hashlib.sha256(repr(key).encode("utf-8")).hexdigest()[:24]


def main() -> int:
    sol = solve_reference()
    provider = reference_provider(sol)

    # ---- build a deterministic pool, then select the fixture ------------- #
    pool = []
    scanned = 0
    for kappa in KAPPAS:
        if len(pool) >= POOL_CAP:
            break
        for tape in TAPES:
            if len(pool) >= POOL_CAP:
                break
            for z in K.option_ids():
                if len(pool) >= POOL_CAP:
                    break
                tr0 = K.rollout(kappa=kappa, tape=tape, command_provider=provider,
                                base_option=z)
                dom = _domains(sol, kappa, tape, z, tr0)
                canon = {k: canonicalise(dom[k]) for k in CAUSE_KEYS}
                for bits in itertools.product((0, 1), repeat=5):
                    if len(pool) >= POOL_CAP:
                        break
                    active = [k for k, b in zip(CAUSE_KEYS, bits) if b]
                    if any(not canon[k] for k in active):
                        continue
                    for combo in itertools.product(*[canon[k] for k in active]):
                        if len(pool) >= POOL_CAP:
                            break
                        blocks = dict(zip(active, combo))
                        case = LatentCase(
                            case_id=0, kappa=kappa, phi=tape.phase,
                            error_flag=tape.error_flag, cause_rank=tape.cause_rank,
                            base_option=z, Z=bits,
                            option_fault=blocks.get("P"),
                            decision=blocks.get("D"),
                            controller=blocks.get("X"),
                            plant=blocks.get("E"), trap=blocks.get("U"))
                        if sigma0(sol, case)[0] is None:
                            continue
                        scanned += 1
                        fire = tuple(fire_of(sol, case))
                        pool.append((case, fire, fingerprint(case)))

    # deterministic selection: satisfy the constraints earliest-first
    need_pos = {i: False for i in range(N_CAUSES)}
    need_neg = {i: False for i in range(N_CAUSES)}
    chosen, idx = [], []
    still_need = lambda: (not all(need_pos.values()) or not all(need_neg.values()))
    for k, (case, fire, fp) in enumerate(pool):
        helpful = any(fire[i] == 1 and not need_pos[i] for i in range(N_CAUSES)) \
            or any(fire[i] == 0 and not need_neg[i] for i in range(N_CAUSES))
        if helpful or len(chosen) < FIXTURE_SIZE:
            chosen.append((case, fire, fp))
            idx.append(k)
            for i in range(N_CAUSES):
                need_pos[i] |= (fire[i] == 1)
                need_neg[i] |= (fire[i] == 0)
            if len(chosen) >= FIXTURE_SIZE and not still_need():
                break
    have_pd = any(f[0] != f[1] for _c, f, _p in chosen)
    have_fire_pres = any(tuple(c.Z) != f for c, f, _p in chosen)
    if not (all(need_pos.values()) and all(need_neg.values())):
        print("fixture could not satisfy per-cause both-classes; aborting")
        return 1
    while not have_pd or not have_fire_pres:
        added = False
        for k, (case, fire, fp) in enumerate(pool):
            if k in idx:
                continue
            if not have_pd and fire[0] != fire[1]:
                chosen.append((case, fire, fp)); idx.append(k); added = True
                have_pd = True
                continue
            if not have_fire_pres and tuple(case.Z) != fire:
                chosen.append((case, fire, fp)); idx.append(k); added = True
                have_fire_pres = True
        if not added:
            print("fixture lacks a P!=D or fire!=pres scene; aborting")
            return 1

    Y = [list(f) for _c, f, _p in chosen]
    P_oracle = [[float(v) for v in f] for _c, f, _p in chosen]
    P_pres = [[float(v) for v in c.Z] for c, _f, _p in chosen]

    m = evaluate(P_oracle, Y)

    # ---- mutations: the gate must KILL each ------------------------------ #
    controls = {}
    controls["swap_PD_columns"] = evaluate(mutate_swap_PD(P_oracle), Y)
    controls["target_Z_pres_instead_of_Z_fire"] = evaluate(P_pres, Y)
    controls["force_softmax_sum_to_1"] = evaluate(mutate_softmax(P_oracle), Y)
    controls["shift_predictions_by_one_row"] = evaluate(mutate_shift_rows(P_oracle), Y)
    controls["flip_one_prediction"] = evaluate(mutate_flip_one(P_oracle, 0), Y)

    def ceiling_ok(x) -> bool:
        return all(abs(getattr(x, k) - v) < TOL for k, v in EXACT.items())

    gate_ok = ceiling_ok(m)
    killed = {name: not ceiling_ok(v) for name, v in controls.items()}
    must_kill = ("swap_PD_columns", "target_Z_pres_instead_of_Z_fire")

    verdict = (gate_ok and all(killed[n] for n in must_kill))

    out = {
        "gate": "A60 — Oracle ceiling / metric plumbing gate",
        "fixture": {
            "n_scenes": len(chosen),
            "size": FIXTURE_SIZE,
            "case_fingerprints": [p for _c, _f, p in chosen],
            "per_cause_positive": [sum(row[i] for row in Y)
                                   for i in range(N_CAUSES)],
            "per_cause_negative": [len(Y) - sum(row[i] for row in Y)
                                   for i in range(N_CAUSES)],
            "has_scene_with_yP_ne_yD": have_pd,
            "has_scene_with_fire_ne_pres": have_fire_pres,
            "selection": "deterministic: earliest-first over the canonical "
                         "enumeration, constraints satisfied then FIXTURE_SIZE",
        },
        "oracle": {"metrics": asdict(m),
                   "expected": EXACT, "tolerance": TOL,
                   "exact_ceiling_met": gate_ok},
        "mutations": {name: {"metrics": asdict(v), "killed": killed[name]}
                      for name, v in controls.items()},
        "must_kill": list(must_kill),
        "verdict": "PASS" if verdict else "FAIL",
        "pipeline_note": (
            "Oracle is fed through rfl_rebuild.eval, the same code every real arm "
            "will use. There is no oracle-only metric path. p is five independent "
            "marginals (A59), so ECE does per-cause binary calibration and then a "
            "macro average -- NOT a 5-class softmax."),
    }
    (ROOT / "experiments" / "v01r").mkdir(parents=True, exist_ok=True)
    path = ROOT / "experiments" / "v01r" / "oracle_ceiling.json"
    path.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")

    print(f"pool scanned: {scanned:,}; fixture: {len(chosen)} scenes")
    print(f"per-cause positives: {out['fixture']['per_cause_positive']}")
    print(f"per-cause negatives: {out['fixture']['per_cause_negative']}")
    print(f"has y_P != y_D scene: {have_pd}; has fire != pres scene: {have_fire_pres}")
    print(f"\nOracle: macro AUPRC={m.macro_auprc!r} macro AUROC={m.macro_auroc!r}")
    print(f"        exact-set={m.exact_set_accuracy!r} Hamming={m.hamming!r} "
          f"Brier={m.brier!r} ECE={m.ece!r}")
    print(f"        AUPRC_U={m.auprc[CAUSES.index('U')]!r}")
    print(f"        exact ceiling met: {gate_ok}")
    print("\nmutations (must be killed):")
    for name, v in controls.items():
        print(f"  {name:<38} killed={killed[name]}")
    print(f"\nA60 verdict: {out['verdict']}")
    print(f"wrote {path}")
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
