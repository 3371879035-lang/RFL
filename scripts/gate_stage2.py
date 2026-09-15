"""Gate stage 2 — candidate -> feasible filtering, and the factual partition.

``docs/rebuild/03-IDENTIFIABILITY.md`` §1.6, amendments A42–A45.

This stage answers exactly three questions and no more:

1. of the ``|L_candidate|`` combinations counted in stage 1, how many actually
   survive a joint SCM rollout, and what are the structural reasons for the rest;
2. how do feasible cases partition by ``sigma_0``;
3. how many factual classes contain **more than one** fault-presence vector.

Four constraints are load-bearing, and each has cost a defect elsewhere in this
project when it was missed:

* **sigma_0 carries the full ``I_t``**, including the terminal feedback claim. The
  kernel's ``StepResult`` has no feedback field, so it is easy to leave out and
  thereby *lower* identifiability artificially.
* **``z_t`` is the option in force, not the latent base option.** After ``Z_P`` the
  learner legitimately knows ``z'``; putting the replaced base ``z`` in the
  signature would contaminate the gate with oracle information.
* **A factual class is NOT collapsed to one row plus a multiplicity.** Two latent
  cases with the same ``sigma_0`` may still diverge under some counterfactual
  query, and collapsing them would erase the very collisions the gate exists to
  find.
* **Class-local legality is asserted, not assumed.** If two members of one factual
  class have different legal query families, this STOPS — it would mean the
  class-local legality definition or the trace reconstruction has a hole.

No environment change. A collision is reported, never smoothed.
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

from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.env.kernel import (  # noqa: E402
    ControllerFault, ControllerSite, DecisionOverride, FaultMask,
    Intervention, MalformedIntervention, OptionViolation, PlantFault,
    SemanticTape, State, Trap,
)
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402
from identifiability_gate import (  # noqa: E402
    CAUSE_KEYS, KAPPAS, TAPES, canonicalise, reference_provider,
)

# A fault block absent, or one canonical parameter per active block.
_BLOCK_ORDER = ("P", "D", "X", "E", "U")


# --------------------------------------------------------------------------- #
# Fault-parameter domains, as ready-to-use objects
# --------------------------------------------------------------------------- #

def fault_domains(sol, kappa: int, tape: SemanticTape, z: int) -> dict:
    """Full legal parameter domain per block, on the healthy reference trace.

    Returns objects the kernel accepts directly, so building a mask is a lookup
    and not a reconstruction.
    """
    tr = K.rollout(kappa=kappa, tape=tape, command_provider=reference_provider(sol),
                   base_option=z)
    state = State(x=K.START[0], y=K.START[1], t=0, kappa=kappa, phi=tape.phase)
    ctrl = K.initial_control(z)

    dp = sorted(zp for zp in K.option_ids() if zp != z)
    dd, dx, de, du = set(), set(), set(), set()
    for res in tr.steps:
        want = sol.best_action(state, ctrl.z, ctrl.m)
        for a in K.option_actions(ctrl.z, ctrl, state):
            if a != want:
                dd.add(DecisionOverride(t=state.t, action=a))
        for realized in K.legal_actions(state):
            if realized != res.a_cmd:
                dx.add(ControllerFault(state=state, cmd=res.a_cmd, realized=realized))
                de.add(PlantFault(t=state.t, realized=realized))
        for cell in (K.OPEN_CELLS - {K.START, K.GOAL}):
            try:
                du.add(Trap(cell=cell, t=state.t))
            except ValueError:
                pass
        state, ctrl = res.state, res.control

    return {
        "P": dp,
        "D": sorted(dd, key=lambda d: (d.t, d.action)),
        "X": sorted(dx, key=lambda f: (f.state.t, f.cmd, f.realized)),
        "E": sorted(de, key=lambda f: (f.t, f.realized)),
        "U": sorted(du, key=lambda t: (t.t, t.cell)),
    }


def build_mask(z: int, blocks: dict) -> tuple[FaultMask, int | None]:
    """``(mask, option_fault)``.

    ``Z_P`` is not a field of :class:`FaultMask`: the kernel takes it as
    ``rollout(option_fault=...)``, because it replaces the episode's option rather
    than perturbing a mechanism inside one episode (A28).
    """
    mask = FaultMask(
        decision=blocks.get("D"),
        controller=blocks.get("X"),
        plant=blocks.get("E"),
        trap=blocks.get("U"),
    )
    return mask, blocks.get("P")


# --------------------------------------------------------------------------- #
# sigma_0 — the full I_t, with in-force z and the terminal feedback claim
# --------------------------------------------------------------------------- #

def sigma0(sol, kappa: int, tape: SemanticTape, z_base: int, mask: FaultMask,
           option_fault: int | None, fault_presence: tuple) -> tuple | None:
    """The factual signature, or ``None`` for a structural exclusion."""
    try:
        tr = K.rollout(kappa=kappa, tape=tape,
                       command_provider=reference_provider(sol),
                       base_option=z_base, mask=mask, option_fault=option_fault)
    except MalformedIntervention as exc:
        return ("MALFORMED", str(exc).split("—")[-1].strip()[:60])
    except OptionViolation as exc:
        return ("OPTION_VIOLATION", str(exc)[:60])

    z_in_force = tr.option_in_force          # NOT z_base: Z_P replaces it
    state = State(x=K.START[0], y=K.START[1], t=0, kappa=kappa, phi=tape.phase)
    ctrl = K.initial_control(z_in_force)

    rows = []
    for res in tr.steps:
        rows.append((res.state.cell, res.state.t, res.a_cmd, res.a_realized,
                     round(res.reward, 6), ctrl.z, ctrl.m))
        state, ctrl = res.state, res.control

    feedback = tape.decode_feedback(list(fault_presence))   # terminal observation
    return (tuple(rows), tr.outcome, feedback)


def legal_query_family(sol, kappa: int, tape: SemanticTape, z_in_force: int,
                       trace_like: tuple) -> frozenset:
    """``Q_legal`` for a member of a factual class.

    Derived from ``sigma_0`` alone — the factual ``I_t`` — since that is all a
    member of the class has in common. If two members disagree, the class-local
    legality definition is broken and stage 2 stops (asserted by the caller).
    """
    out = set()
    for zp in K.option_ids():
        if zp != z_in_force:
            out.add(("process", zp))
    for _cell, t, a_cmd, _realized, _r, zt, mt in trace_like:
        if _cell == K.GOAL:
            continue        # terminal; the goal is never a decision point (A39)
        st = State(x=_cell[0], y=_cell[1], t=t, kappa=kappa, phi=tape.phase)
        ctrl = K.ControlState(z=zt, m=mt)
        for a in K.option_actions(zt, ctrl, st):
            if a != a_cmd:
                out.add(("decision", t, a))
        for a in K.legal_actions(st):
            if a != a_cmd:
                out.add(("execution", t, a))
    return frozenset(out)


# --------------------------------------------------------------------------- #
# Stage 2
# --------------------------------------------------------------------------- #

def main() -> int:
    sol = solve_reference()
    provider = reference_provider(sol)

    excluded: Counter = Counter()
    classes: dict[tuple, list] = defaultdict(list)
    class_queries: dict[tuple, frozenset] = {}
    n_candidate = 0
    n_feasible = 0
    query_conflicts = []

    for kappa in KAPPAS:
        for tape in TAPES:
            for z in K.option_ids():
                dom = fault_domains(sol, kappa, tape, z)
                canon = {k: canonicalise(dom[k]) for k in CAUSE_KEYS}
                for bits in itertools.product((0, 1), repeat=5):
                    active = [k for k, b in zip(CAUSE_KEYS, bits) if b]
                    if any(not canon[k] for k in active):
                        continue                       # recorded in stage 1
                    per_block = [canon[k] for k in active] or [[]]
                    for combo in itertools.product(*per_block):
                        n_candidate += 1
                        blocks = dict(zip(active, combo))
                        mask, opt_fault = build_mask(z, blocks)
                        sig = sigma0(sol, kappa, tape, z, mask, opt_fault, bits)
                        if sig is None or sig[0] in ("MALFORMED", "OPTION_VIOLATION"):
                            excluded[sig[0] if sig else "NONE"] += 1
                            continue
                        n_feasible += 1
                        key = sig
                        classes[key].append(
                            (kappa, tape.phase, tape.error_flag, tape.cause_rank,
                             z, bits, tuple(sorted(blocks))))
                        qf = legal_query_family(sol, kappa, tape,
                                                key[0][0][5] if key[0] else z, key[0])
                        prev = class_queries.get(key)
                        if prev is None:
                            class_queries[key] = qf
                        elif prev != qf:
                            query_conflicts.append(key)

    sizes = [len(v) for v in classes.values()]
    multi = [k for k, v in classes.items()
             if len({case[5] for case in v}) > 1]

    report = {
        "L_candidate": n_candidate,
        "L_feasible": n_feasible,
        "excluded_by_reason": dict(excluded),
        "n_factual_classes": len(classes),
        "max_class_size": max(sizes) if sizes else 0,
        "mean_class_size": (sum(sizes) / len(sizes)) if sizes else 0.0,
        "class_size_distribution": dict(sorted(Counter(sizes).items())),
        "classes_with_multiple_Z": len(multi),
        "query_family_conflicts": len(query_conflicts),
    }

    print("=" * 78)
    print("Gate stage 2 — feasible filtering and factual partition")
    print("=" * 78)
    for k, v in report.items():
        print(f"  {k:<34} {v if not isinstance(v, dict) else ''}")
    if isinstance(report["class_size_distribution"], dict):
        print("\n  class-size distribution (size: count), first 15:")
        for k, v in list(report["class_size_distribution"].items())[:15]:
            print(f"    {k:>6}: {v:>10,}")

    outdir = ROOT / "outputs" / "rebuild"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "gate_stage2.json").write_text(
        json.dumps(report, indent=1, default=str), encoding="utf-8")
    print(f"\nwrote {outdir / 'gate_stage2.json'}")

    if query_conflicts:
        print(f"\nSTOP — {len(query_conflicts)} factual classes have members with "
              f"DIFFERENT legal query families. Class-local legality is broken.")
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
