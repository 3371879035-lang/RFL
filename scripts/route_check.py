"""route_check — discharge properties P1a/P1b/P1c and P2/P3/P4 by enumeration.

``docs/rebuild/00-INDEX.md`` §7 step 3, and `11-ENVIRONMENT.md` §4.

**This script defines no world semantics.** It imports the kernel and the exact
reference solution and nothing else:

* the healthy command comes from ``ReferenceSolution.best_action(s, z, m)``;
* every counterfactual goes through ``kernel.rollout`` / ``InterventionSet``;
* transition, hazard, automaton and repair semantics are never re-implemented
  here. A second simulator is exactly what A16 and A19 were about.

**Positive witnesses may stop early; negative conditions may not.** P2/P3/P4 have
the shape "there exists a witness, *and* no member of family F suffices". The first
half can return on the first hit. The second half must enumerate F to exhaustion —
stopping at the first non-rescuing member would prove nothing.

Output: ``outputs/rebuild/route_check.json`` plus a readable summary.
"""

from __future__ import annotations

import itertools
import json
import pathlib
import sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.env.kernel import (  # noqa: E402
    ControllerSite, DecisionOverride, FaultMask, Intervention, InterventionSet,
    MalformedIntervention, OptionViolation, SemanticTape, State,
)
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

CONTEXTS = [(k, p) for k in (0, 1) for p in K.PHASE_DOMAIN]


def tape_for(kappa: int, phi: int) -> SemanticTape:
    return SemanticTape(phase=phi, error_flag=0, cause_rank=0)


def healthy_provider(sol):
    def provider(s: State, c: K.ControlState) -> int:
        return sol.best_action(s, c.z, c.m)

    return provider


# --------------------------------------------------------------------------- #
# P1a / P1b / P1c
# --------------------------------------------------------------------------- #

def check_p1(sol) -> dict:
    provider = healthy_provider(sol)
    safe, unsafe = [], []
    bad = []
    for kappa, phi in CONTEXTS:
        tr = K.rollout(kappa=kappa, tape=tape_for(kappa, phi),
                       command_provider=provider, base_option=0)
        actual = K.hazard_at(2, kappa, phi)
        if actual:
            unsafe.append((kappa, phi))
            ok = (tr.outcome == K.Outcome.COLLISION
                  and len(tr.steps) == 2
                  and tr.visited()[-1] == K.CONTESTED)
            if not ok:
                bad.append((kappa, phi, "P1b", tr.outcome, len(tr.steps)))
        else:
            safe.append((kappa, phi))
            ok = tr.success and len(tr.steps) == 4
            if not ok:
                bad.append((kappa, phi, "P1a", tr.outcome, len(tr.steps)))

    zstar = {}
    for kappa, phi in CONTEXTS:
        s0 = State(0, 2, 0, kappa, phi)
        zstar[f"k{kappa}_p{phi}"] = K.option_name(sol.context_option(kappa, phi))
    distinct = sorted(set(zstar.values()))

    return {
        "P1a": {"safe_contexts": len(safe), "failures": [b for b in bad if b[2] == "P1a"],
                "verdict": "PASS" if not [b for b in bad if b[2] == "P1a"] else "FAIL"},
        "P1b": {"dangerous_contexts": len(unsafe), "witness": unsafe[0] if unsafe else None,
                "failures": [b for b in bad if b[2] == "P1b"],
                "verdict": "PASS" if not [b for b in bad if b[2] == "P1b"] else "FAIL"},
        "P1c": {"distinct_options": distinct, "count": len(distinct),
                "by_context": zstar,
                "verdict": "PASS" if len(distinct) >= 2 else "FAIL"},
    }


# --------------------------------------------------------------------------- #
# Intervention families — enumerated fully, never sampled
# --------------------------------------------------------------------------- #

def walk(trace, kappa: int, phi: int, base_option: int):
    """Yield ``(state_before, control_before, step_result)`` for each step.

    ``StepResult`` carries the state *after* the move, and the goal is terminal,
    so the post-state is not a decision point and ``option_actions`` refuses it.
    Admissible sets and controller sites are properties of the pre-step state, so
    the walk reconstructs it rather than misusing the result.
    """
    state = State(x=K.START[0], y=K.START[1], t=0, kappa=kappa, phi=phi)
    control = K.initial_control(base_option)
    for res in trace.steps:
        yield state, control, res
        state, control = res.state, res.control


def decision_family(trace, kappa: int, phi: int, base_option: int) -> list[Intervention]:
    """Every size-1 decision intervention admissible on the FACTUAL trajectory."""
    out = []
    for state, control, res in walk(trace, kappa, phi, base_option):
        allowed = K.option_actions(control.z, control, state)
        for a in allowed:
            out.append(Intervention.decision(state.t, a))
    return out


def execution_family(trace, kappa: int, phi: int, base_option: int) -> list[Intervention]:
    """Every size-1 execution intervention on the factual trajectory."""
    return [
        Intervention.execution(ControllerSite(state=state, cmd=res.a_cmd))
        for state, _control, res in walk(trace, kappa, phi, base_option)
    ]


def try_intervention(sol, kappa, phi, base_option, iv, mask=FaultMask()):
    provider = healthy_provider(sol)
    try:
        tr = K.rollout(
            kappa=kappa, tape=tape_for(kappa, phi), command_provider=provider,
            base_option=base_option, mask=mask,
            interventions=InterventionSet((iv,)),
        )
        return tr.success, tr
    except (MalformedIntervention, OptionViolation) as e:
        return None, str(e)


def process_family() -> list[Intervention]:
    return [Intervention.process(z) for z in K.option_ids()]


# --------------------------------------------------------------------------- #
# P2 (A40) — a singleton DECISION minimal repair EXISTS; uniqueness is NOT required
# --------------------------------------------------------------------------- #

def size1_family(trace, kappa: int, phi: int, base_option: int) -> list[Intervention]:
    """The full size-1 family ``F_1 = F_process u F_decision u F_execution``.

    Earlier revisions enumerated only decision + execution, so any claim about
    ``R*``'s size-1 candidates was unsupported: ``do(z=z')`` could rescue too and
    was simply never tried (A40).
    """
    process = [Intervention.process(zp) for zp in K.option_ids()
               if zp != base_option]
    return (process
            + decision_family(trace, kappa, phi, base_option)
            + execution_family(trace, kappa, phi, base_option))


def _rescuer_summary(rescuers: list[Intervention]) -> dict:
    """Candidate count, unique-site count, and per-kind counts.

    ``do(d_2=UP)`` and ``do(d_2=WAIT)`` are two *candidates* but one *site*, and
    for a credit representation they are the same unit ``Decision_2``. V0.2R
    compares representations on *where to change* before *what target*, so the
    two counts must not be conflated.
    """
    kinds = Counter(iv.kind for iv in rescuers)
    sites = set()
    for iv in rescuers:
        sites.add(("process", iv.option) if iv.kind == "process"
                  else (iv.kind, iv.node()[1]))
    return {
        "n_candidates": len(rescuers),
        "n_unique_sites": len(sites),
        "n_process": kinds.get("process", 0),
        "n_decision": kinds.get("decision", 0),
        "n_execution": kinds.get("execution", 0),
        "candidate_sites": sorted(f"{k}:{v}" for k, v in sites),
    }


def check_p2(sol) -> dict:
    """A40: P2 asks for a **singleton Decision minimal repair**, not uniqueness.

    $$\\exists e:\\ \\min_{r\\,\\text{sufficient}} |r| = 1 \\ \\wedge\\
      \\exists r \\in R^*(e),\\ r = \\{do(d_t = d')\\}$$

    It deliberately does **not** require ``#R* = 1``. Multiple tied size-1 repairs
    are first-class (``02-SCM.md`` §5.2), and demanding uniqueness here would
    contradict the repair-truth ontology and delete the tie cases V0.2R exists to
    face. **Ties are a result, never a failure condition**, and the environment is
    not tuned to remove them.

    P2 is an **environment coverage gate**: it asks whether this benchmark
    contains the object *"a local Decision-level repair"* at all. It does not ask
    whether a Decision is the only correct explanation — that is V0.2R's question.
    A weak P2 is not a bug; making P2 look like a main hypothesis would be.
    """
    provider = healthy_provider(sol)
    counts: Counter = Counter()
    for kappa, phi in CONTEXTS:
        for z in K.option_ids():
            clean = K.rollout(kappa=kappa, tape=tape_for(kappa, phi),
                              command_provider=provider, base_option=z)
            if not clean.success:
                continue
            for st, ctrl, res in walk(clean, kappa, phi, z):
                allowed = K.option_actions(ctrl.z, ctrl, st)
                if len(allowed) < 2:
                    continue
                for a in allowed:
                    if a == res.a_cmd:
                        continue
                    fault = FaultMask(decision=DecisionOverride(t=st.t, action=a))
                    try:
                        fact = K.rollout(
                            kappa=kappa, tape=tape_for(kappa, phi),
                            command_provider=provider, base_option=z, mask=fault,
                        )
                    except (MalformedIntervention, OptionViolation):
                        continue
                    if fact.success:
                        continue
                    # Factual failure established. The negative half is
                    # exhaustive: every size-1 candidate of every kind is tried.
                    family = size1_family(fact, kappa, phi, z)
                    rescuing, malformed = [], 0
                    for iv in family:
                        ok, _ = try_intervention(sol, kappa, phi, z, iv, fault)
                        if ok is True:
                            rescuing.append(iv)
                        elif ok is None:
                            malformed += 1
                    counts[len(rescuing)] += 1
                    # A40: one Decision singleton rescuer is sufficient.
                    if any(iv.kind == "decision" for iv in rescuing):
                        return {
                            "verdict": "PASS",
                            "witness": {
                                "kappa": kappa, "phi": phi,
                                "option": K.option_name(z),
                                "fault_t": st.t,
                                "fault_action": K.ACTIONS[a],
                                "factual_outcome": fact.outcome,
                                "minimal_size": 1,
                                "family_size": len(family),
                                "malformed": malformed,
                                **_rescuer_summary(rescuing),
                            },
                            "ties_are_expected": (
                                "heavy ties are a result, not a failure (A40); "
                                "they are the pressure V0.2R's tie-handling "
                                "endpoint exists to face"
                            ),
                        }
    return {
        "verdict": "FAIL",
        "reason": "no size-1 Decision repair candidate found in any context",
        "rescuer_count_distribution": dict(sorted(counts.items())),
    }


# --------------------------------------------------------------------------- #
# P3 — z1 fails where z3 succeeds, and NO size-1 local repair rescues
# --------------------------------------------------------------------------- #

def check_p3(sol) -> dict:
    provider = healthy_provider(sol)
    attempted = 0
    closest = None
    for kappa, phi in CONTEXTS:
        if not K.hazard_at(2, kappa, phi):
            continue
        z1 = K.rollout(kappa=kappa, tape=tape_for(kappa, phi),
                       command_provider=provider, base_option=0)
        if z1.success:
            continue
        z3 = K.rollout(kappa=kappa, tape=tape_for(kappa, phi),
                       command_provider=provider, base_option=2)
        if not z3.success:
            continue
        # the negative half must be exhaustive
        fam = decision_family(z1, kappa, phi, 0) + execution_family(z1, kappa, phi, 0)
        attempted += len(fam)
        rescuing, malformed = [], 0
        for iv in fam:
            ok, _ = try_intervention(sol, kappa, phi, 0, iv)
            if ok is True:
                rescuing.append(f"{iv.kind}{iv.node()}")
            elif ok is None:
                malformed += 1
        if not rescuing:
            return {
                "verdict": "PASS",
                "witness": {"kappa": kappa, "phi": phi, "z1_outcome": z1.outcome,
                            "z3_outcome": z3.outcome,
                            "family_size": len(fam), "malformed": malformed,
                            "note": "no size-1 local Decision/Execution repair rescues z1"},
            }
        closest = {"kappa": kappa, "phi": phi, "family_size": len(fam),
                   "rescuing": rescuing}
    return {"verdict": "FAIL", "family_members_tried": attempted, "closest": closest}


# --------------------------------------------------------------------------- #
# P4 — only a PROCESS repair rescues
# --------------------------------------------------------------------------- #

def check_p4(sol) -> dict:
    provider = healthy_provider(sol)
    closest = None
    for kappa, phi in CONTEXTS:
        for z in K.option_ids():
            fact = K.rollout(kappa=kappa, tape=tape_for(kappa, phi),
                             command_provider=provider, base_option=z)
            if fact.success:
                continue
            local = decision_family(fact, kappa, phi, z) + execution_family(fact, kappa, phi, z)
            local_rescue, malformed = [], 0
            for iv in local:
                ok, _ = try_intervention(sol, kappa, phi, z, iv)
                if ok is True:
                    local_rescue.append(f"{iv.kind}{iv.node()}")
                elif ok is None:
                    malformed += 1
            if local_rescue:
                continue
            proc_rescue = []
            for iv in process_family():
                if iv.option == z:
                    continue
                ok, _ = try_intervention(sol, kappa, phi, z, iv)
                if ok is True:
                    proc_rescue.append(K.option_name(iv.option))
            if proc_rescue:
                return {
                    "verdict": "PASS",
                    "witness": {"kappa": kappa, "phi": phi,
                                "failing_option": K.option_name(z),
                                "outcome": fact.outcome,
                                "local_family_size": len(local), "malformed": malformed,
                                "process_repairs": proc_rescue},
                }
            closest = {"kappa": kappa, "phi": phi,
                       "option": K.option_name(z), "outcome": fact.outcome,
                       "local_family_size": len(local)}
    return {"verdict": "FAIL", "closest": closest,
            "reason": "no episode where all size-1 local repairs fail but a process repair works"}


# --------------------------------------------------------------------------- #

def main() -> int:
    sol = solve_reference()
    results = {
        "P1": check_p1(sol),
        "P2": check_p2(sol),
        "P3": check_p3(sol),
        "P4": check_p4(sol),
    }

    print("=" * 78)
    print("route_check — P1a/P1b/P1c, P2, P3, P4")
    print("=" * 78)
    p1 = results["P1"]
    print(f"\nP1a  {p1['P1a']['verdict']}  "
          f"({p1['P1a']['safe_contexts']} safe contexts, "
          f"{len(p1['P1a']['failures'])} failures)")
    print(f"P1b  {p1['P1b']['verdict']}  "
          f"({p1['P1b']['dangerous_contexts']} dangerous contexts)")
    print(f"P1c  {p1['P1c']['verdict']}  distinct z* = {p1['P1c']['distinct_options']}")
    for name in ("P2", "P3", "P4"):
        r = results[name]
        print(f"\n{name}   {r['verdict']}")
        w = r.get("witness") or r.get("closest") or r.get("reason")
        print(f"      {json.dumps(w)}")

    outdir = ROOT / "outputs" / "rebuild"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "route_check.json").write_text(
        json.dumps(results, indent=1), encoding="utf-8")
    print(f"\nwrote {outdir / 'route_check.json'}")
    return 0 if all(
        results["P1"][k]["verdict"] == "PASS" for k in ("P1a", "P1b", "P1c")
    ) and all(results[k]["verdict"] == "PASS" for k in ("P2", "P3", "P4")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
