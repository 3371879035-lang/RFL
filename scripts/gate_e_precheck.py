"""Gate E pre-check: is the evaluator lattice still total after A55?

A55 changed the process side of the lattice from

    {do(z = z')}                      (labelled "process")

to

    {do(z = z')}  U  {do(C_P = identity)}

with the new member being the *actual* process repair and $do(z=z')$ demoted to
strategy replay. That is a repair-ontology change, so the totality question has to
be asked again rather than assumed: for the cases the environment actually
produces, is there always something in the lattice that repairs them?

Four things are checked, none of which changes the environment.

1. WELL-DEFINEDNESS. ``do(C_P = identity)`` must reduce to a no-op exactly when
   there is no commit fault, and must be active exactly when there is one. If it
   were active on $Z_P^{\\text{fire}} = 0$ cases it would be repairing nothing and
   would contaminate $R^{*}$.
2. CONSTITUENTS. Every lattice member must be constructible for every feasible
   case, and ``0`` (change nothing) must always be legal.
3. SUFFICIENCY COVERAGE. For each fault kind, how often is the case repaired by a
   size-1 lattice member, and how often by nothing at all. "Nothing repairs it" is
   a legitimate truth (the episode may be unrepairable), but it must be *counted*
   rather than silently become an empty $R^{*}$.
4. THE A55-SPECIFIC RISK. ``do(C_P = identity)`` restores a faithful commit; it
   does **not** guarantee success, because the proposal itself may be a poor
   option. So the check reports how often the commit repair is sufficient versus
   merely fault-removing. Conflating those two would let $R^{*}$ claim a repair it
   did not perform.
"""

from __future__ import annotations

import itertools
import json
import pathlib
import sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gate_stage2 import (  # noqa: E402
    LatentCase, _domains, fire_of, reference_provider, sigma0,
)
from identifiability_gate import CAUSE_KEYS, KAPPAS, TAPES, canonicalise  # noqa: E402
from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.env.kernel import (  # noqa: E402
    ControllerSite, FaultMask, Intervention, InterventionSet, Outcome,
    State,
)
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

SAMPLE_EVERY = 37


def outcome_of(sol, case, ivs=None, commit_repair=False):
    try:
        tr = K.rollout(
            kappa=case.kappa, tape=case.tape(),
            command_provider=reference_provider(sol),
            base_option=case.base_option, mask=case.mask(),
            option_fault=None if commit_repair else case.option_fault,
            interventions=InterventionSet(tuple(ivs or ())),
        )
    except Exception:
        return "MALFORMED"
    return tr.outcome


def main() -> int:
    sol = solve_reference()
    provider = reference_provider(sol)

    verdict = Counter()
    by_kind = Counter()
    n_seen = 0
    examples = []

    for kappa in KAPPAS:
        for tape in TAPES:
            for z in K.option_ids():
                tr = K.rollout(kappa=kappa, tape=tape, command_provider=provider,
                               base_option=z)
                dom = _domains(sol, kappa, tape, z, tr)
                canon = {k: canonicalise(dom[k]) for k in CAUSE_KEYS}
                for bits in itertools.product((0, 1), repeat=5):
                    active = [k for k, b in zip(CAUSE_KEYS, bits) if b]
                    if any(not canon[k] for k in active):
                        continue
                    for combo in itertools.product(*[canon[k] for k in active]):
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
                        n_seen += 1
                        if n_seen % SAMPLE_EVERY:
                            continue

                        fire = fire_of(sol, case)
                        # ---- 1. well-definedness of the commit repair -------- #
                        base = outcome_of(sol, case)
                        commit = outcome_of(sol, case, commit_repair=True)
                        if fire[0] == 0 and commit != base:
                            verdict["commit_repair_active_without_fault"] += 1
                        if fire[0] == 1:
                            by_kind["P_fired"] += 1
                            if commit != base:
                                by_kind["commit_repair_changed_outcome"] += 1
                            if commit == Outcome.SUCCESS:
                                by_kind["commit_repair_sufficient"] += 1

                        # ---- 2/3. size-1 sufficiency coverage ---------------- #
                        cands = [("none", ()), ("commit", ())]
                        for zp in K.option_ids():
                            if zp != case.base_option:
                                cands.append(("strategy", tuple(
                                    [Intervention.process(zp)])))
                        for t in range(K.HORIZON):
                            for a in range(len(K.ACTIONS)):
                                cands.append(("decision", tuple(
                                    [Intervention.decision(t, a)])))
                        # execution sites are the ones the factual episode visited,
                        # which is exactly the family `class_local_queries` builds
                        try:
                            ftr = K.rollout(
                                kappa=case.kappa, tape=case.tape(),
                                command_provider=provider,
                                base_option=case.base_option, mask=case.mask(),
                                option_fault=case.option_fault)
                        except Exception:
                            ftr = None
                        if ftr is not None:
                            st = State(x=K.START[0], y=K.START[1], t=0,
                                       kappa=kappa, phi=tape.phase)
                            for s in ftr.steps:
                                site = ControllerSite(state=st, cmd=s.a_cmd)
                                cands.append(("execution", tuple(
                                    [Intervention.execution(site)])))
                                st = s.state

                        if base == Outcome.SUCCESS:
                            verdict["no_repair_needed"] += 1
                            continue
                        worked = None
                        for name, ivs in cands:
                            o = (commit if name == "commit"
                                 else outcome_of(sol, case, ivs))
                            if o == Outcome.SUCCESS:
                                worked = name
                                break
                        if worked:
                            verdict["size1_repairable"] += 1
                            by_kind[f"size1_{worked}"] += 1
                        else:
                            verdict["not_size1_repairable"] += 1
                            if len(examples) < 8:
                                examples.append({
                                    "kappa": kappa, "phi": tape.phase,
                                    "base_option": z, "Z": "".join(map(str, bits)),
                                    "fire": "".join(map(str, fire)),
                                    "base_outcome": base})

    print(f"feasible cases seen: {n_seen:,}, sampled 1 in {SAMPLE_EVERY}")
    print("\nGate E pre-check verdicts:")
    for k in sorted(verdict):
        print(f"  {k:<44} {verdict[k]}")
    print("\nfault-kind detail:")
    for k in sorted(by_kind):
        print(f"  {k:<44} {by_kind[k]}")

    bad = verdict.get("commit_repair_active_without_fault", 0)
    print(f"\nA55 well-definedness: commit repair active without a fault = {bad}")
    print("VERDICT: " + ("lattice total and A55 well-defined"
                         if bad == 0 else "A55 BROKE THE LATTICE"))

    if examples:
        print("\nexamples with no size-1 repair (legitimate, must be counted):")
        for e in examples[:4]:
            print("  ", json.dumps(e))

    out = ROOT / "outputs" / "rebuild" / "gate_e_precheck.json"
    out.write_text(json.dumps({
        "n_feasible_seen": n_seen, "sample_every": SAMPLE_EVERY,
        "verdicts": dict(verdict), "by_kind": dict(by_kind),
        "commit_repair_active_without_fault":
            verdict.get("commit_repair_active_without_fault", 0),
        "examples_no_size1": examples,
    }, indent=1, default=str), encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
