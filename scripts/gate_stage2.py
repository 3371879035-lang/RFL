"""Gate stage 2 — candidate -> feasible filtering, and the factual partition.

Correction pass A45-A49. Four P0 defects in the first version, all of which would
have changed the Gate L verdict:

* ``itertools.product()`` over an empty active-fault list yields **one** ``()``, so
  the ``or [[]]`` guard was not needed and was actively wrong: it made
  ``product([])``, which yields *nothing*, silently deleting all 5,760 clean
  ``Z = 00000`` cases. The giveaway was ``1,166,400 - 1,160,640 = 5,760``.
* the factual record mixed a **post-action** ``s_{t+1}`` with a **pre-action**
  ``(z_t, m_t, a_t)``, and omitted ``kappa`` and ``phi`` although both are
  learner-visible parts of ``s_t``. So the classes were built from a timeline that
  no learner ever observes, and "0 query-family conflicts" only showed that the
  same misaligned function was self-consistent.
* the stored latent descriptor was ``tuple(sorted(blocks))`` — the **fault names**,
  not the parameters. ``D(t=1,LEFT)`` and ``D(t=7,WAIT)`` stored identically, so
  Stage 3 could not have replayed them.
* the execution query family emitted one query per *alternative action* instead of
  one per **ControllerSite**. The frozen primitive is
  ``do(C_X(s*, a^cmd) = a^cmd)`` and has no alternative parameter, so four
  alternatives were being counted as four queries against ``B_CF = 4``.

Also: ``Outcome`` is evaluator truth, not a learner observation, and is no longer
part of the signature unless the spec says otherwise.
"""

from __future__ import annotations

import itertools
import json
import pathlib
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.env.kernel import (  # noqa: E402
    ControllerFault, ControllerSite, DecisionOverride, FaultMask,
    MalformedIntervention, OptionViolation, PlantFault, SemanticTape, State, Trap,
)
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402
from identifiability_gate import (  # noqa: E402
    CAUSE_KEYS, KAPPAS, TAPES, canonicalise, reference_provider,
)

EXPECTED_L_CANDIDATE = 1_166_400
EXPECTED_CLEAN = 5_760


# --------------------------------------------------------------------------- #
# The one timeline both sigma_0 and Q(C) use
# --------------------------------------------------------------------------- #

def walk_transition(trace, kappa: int, phi: int, z_in_force: int):
    """Yield ``(s_pre, z, m, a_cmd, a_realized, reward)`` per step.

    ``StepResult.state`` is the state *after* the move, so pairing it with the
    pre-action control state produced a mixed timeline. One helper, used by both
    the signature and the query family, is the only way to keep them aligned.
    """
    state = State(x=K.START[0], y=K.START[1], t=0, kappa=kappa, phi=phi)
    ctrl = K.initial_control(z_in_force)
    for res in trace.steps:
        yield state, ctrl.z, ctrl.m, res.a_cmd, res.a_realized, res.reward
        state, ctrl = res.state, res.control


# --------------------------------------------------------------------------- #
# Latent case — a full, replayable descriptor
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class LatentCase:
    case_id: int
    kappa: int
    phi: int
    error_flag: int
    cause_rank: int
    base_option: int
    Z: tuple
    option_fault: int | None = None
    decision: DecisionOverride | None = None
    controller: ControllerFault | None = None
    plant: PlantFault | None = None
    trap: Trap | None = None

    def mask(self) -> FaultMask:
        return FaultMask(decision=self.decision, controller=self.controller,
                         plant=self.plant, trap=self.trap)

    def tape(self) -> SemanticTape:
        return SemanticTape(phase=self.phi, error_flag=self.error_flag,
                            cause_rank=self.cause_rank)

    def describe(self) -> dict:
        def fmt(o):
            return None if o is None else repr(o)
        return {"case_id": self.case_id, "kappa": self.kappa, "phi": self.phi,
                "error_flag": self.error_flag, "cause_rank": self.cause_rank,
                "base_option": self.base_option, "Z": "".join(map(str, self.Z)),
                "P": self.option_fault,
                "D": fmt(self.decision), "X": fmt(self.controller),
                "E": fmt(self.plant), "U": fmt(self.trap)}


def replay(sol, case: LatentCase):
    return K.rollout(kappa=case.kappa, tape=case.tape(),
                     command_provider=reference_provider(sol),
                     base_option=case.base_option, mask=case.mask(),
                     option_fault=case.option_fault)


# --------------------------------------------------------------------------- #
# sigma_0 and Q(C)
# --------------------------------------------------------------------------- #

_FIRE_KEYS = ("Z_P", "Z_D", "Z_X", "Z_E", "Z_U")
_fire_cache: dict = {}


def fire_of(sol, case: LatentCase) -> tuple[int, ...]:
    """``Z^fire`` (A54): which configured mechanisms actually executed.

    Same key order as ``case.Z``, so ``Z^pres[i] >= Z^fire[i]`` always holds and
    the two vectors are directly comparable. Memoised on the full world because
    ``sigma_0`` and every query response need it, and it costs a rollout.
    """
    key = (case.kappa, case.phi, case.error_flag, case.cause_rank,
           case.base_option, case.Z, case.option_fault, case.decision,
           case.controller, case.plant, case.trap)
    hit = _fire_cache.get(key)
    if hit is None:
        d = K.fired_mechanisms(
            kappa=case.kappa, tape=case.tape(),
            command_provider=reference_provider(sol),
            base_option=case.base_option, mask=case.mask(),
            option_fault=case.option_fault)
        hit = tuple(d[k] for k in _FIRE_KEYS)
        _fire_cache[key] = hit
    return hit


def sigma0(sol, case: LatentCase):
    """``(I_t)_{t}`` with the full ``s_t``, plus the terminal feedback claim."""
    try:
        tr = replay(sol, case)
    except MalformedIntervention as exc:
        return None, ("MALFORMED", str(exc).split("—")[-1].strip()[:70])
    except OptionViolation as exc:
        return None, ("OPTION_VIOLATION", str(exc)[:70])

    z_in_force = tr.option_in_force
    rows = tuple(
        (s.x, s.y, s.t, s.kappa, s.phi, z, m, a_cmd, a_realized, round(r, 6))
        for (s, z, m, a_cmd, a_realized, r)
        in walk_transition(tr, case.kappa, case.phi, z_in_force)
    )
    # A54: the feedback channel reports what HAPPENED, so it is driven by the
    # fire vector. Driving it by presence let a truthful claim point at a
    # dormant fault that never executed.
    feedback = tuple(case.tape().decode_feedback(list(fire_of(sol, case))))
    return (rows, feedback), None


def class_local_queries(sol, kappa: int, phi: int, rows: tuple) -> frozenset:
    """``Q(C)`` from the factual ``I_t`` alone.

    One execution query per **ControllerSite** — the frozen primitive
    ``do(C_X(s*,a^cmd)=a^cmd)`` takes no alternative action, so a site with four
    other legal actions is still exactly one query.

    A53 adds one more family: ``("audit", t)``, the on-demand plant-input audit
    ``q^plant_t = audit_plant_input(t)`` whose response is ``u_t``, the low-level
    command the plant actually received. It is included here because its
    availability is class-local in exactly the same way: every member of a
    factual class shares ``sigma_0``, hence the same timestep structure, so the
    audit is legal on the whole class and cannot be MALFORMED. It changes no
    world and reads no ``Z``, ``M`` or ``B`` — only the interface telemetry the
    real system already produces.

    A55 adds the parallel one for process integrity: ``("proc_audit",)``, the
    provenance query ``q^proc = audit_process_proposal()`` whose response is
    ``z^proposal`` — the option the upstream planner actually proposed. It is
    always available, since "what did the planner propose" is well posed in every
    world, and it is informative precisely because ``z^in-force`` is already
    visible in ``I_t`` while ``z^proposal`` is not.
    """
    out = set()
    out.add(("proc_audit",))
    z_seen = {r[5] for r in rows}
    for zf in z_seen:
        for zp in K.option_ids():
            if zp != zf:
                out.add(("process", zp))
    for (_x, _y, t, kp, ph, z, m, a_cmd, _realized, _r) in rows:
        out.add(("audit", t))
        cell = (_x, _y)
        if cell == K.GOAL:
            continue
        st = State(x=_x, y=_y, t=t, kappa=kp, phi=ph)
        ctrl = K.ControlState(z=z, m=m)
        for a in K.option_actions(z, ctrl, st):
            if a != a_cmd:
                out.add(("decision", t, a))
        out.add(("execution", ControllerSite(state=st, cmd=a_cmd)))
    return frozenset(out)


# --------------------------------------------------------------------------- #
# Stage 2
# --------------------------------------------------------------------------- #

def main() -> int:
    sol = solve_reference()
    provider = reference_provider(sol)

    excluded: Counter = Counter()
    classes: dict[tuple, list[int]] = defaultdict(list)
    case_index: dict[int, LatentCase] = {}
    class_queries: dict[tuple, frozenset] = {}
    conflicts = 0
    n_candidate = 0
    n_clean = 0
    next_id = 0

    for kappa in KAPPAS:
        for tape in TAPES:
            for z in K.option_ids():
                tr = K.rollout(kappa=kappa, tape=tape,
                               command_provider=provider, base_option=z)
                dom = _domains(sol, kappa, tape, z, tr)
                canon = {k: canonicalise(dom[k]) for k in CAUSE_KEYS}
                for bits in itertools.product((0, 1), repeat=5):
                    active = [k for k, b in zip(CAUSE_KEYS, bits) if b]
                    if any(not canon[k] for k in active):
                        continue
                    # NOTE: product() over an empty list yields exactly one (),
                    # which is the clean case. No `or [[]]` guard.
                    per_block = [canon[k] for k in active]
                    for combo in itertools.product(*per_block):
                        n_candidate += 1
                        blocks = dict(zip(active, combo))
                        case = LatentCase(
                            case_id=next_id, kappa=kappa, phi=tape.phase,
                            error_flag=tape.error_flag, cause_rank=tape.cause_rank,
                            base_option=z, Z=bits,
                            option_fault=blocks.get("P"),
                            decision=blocks.get("D"),
                            controller=blocks.get("X"),
                            plant=blocks.get("E"), trap=blocks.get("U"),
                        )
                        next_id += 1
                        if not active:
                            n_clean += 1
                        sig, err = sigma0(sol, case)
                        if sig is None:
                            excluded[err[0]] += 1
                            continue
                        case_index[case.case_id] = case
                        classes[sig].append(case.case_id)
                        qf = class_local_queries(
                            sol, kappa, tape.phase, sig[0])
                        prev = class_queries.get(sig)
                        if prev is None:
                            class_queries[sig] = qf
                        elif prev != qf:
                            conflicts += 1

    sizes = [len(v) for v in classes.values()]
    multi = sum(1 for v in classes.values()
                if len({case_index[i].Z for i in v}) > 1)
    n_feasible = sum(sizes)

    report = {
        "L_candidate": n_candidate,
        "L_feasible": n_feasible,
        "n_clean_cases": n_clean,
        "n_stored_descriptors": len(case_index),
        "excluded_by_reason": dict(excluded),
        "n_factual_classes": len(classes),
        "max_class_size": max(sizes) if sizes else 0,
        "mean_class_size": (n_feasible / len(sizes)) if sizes else 0.0,
        "class_size_distribution": dict(sorted(Counter(sizes).items())),
        "classes_with_multiple_Z": multi,
        "query_family_conflicts": conflicts,
    }

    print("=" * 78)
    print("Gate stage 2 (corrected) — feasible filtering and factual partition")
    print("=" * 78)
    for k, v in report.items():
        if not isinstance(v, dict):
            print(f"  {k:<32} {v}")

    # ---- mechanical assertions the review required ------------------------ #
    failures = []
    if n_candidate != EXPECTED_L_CANDIDATE:
        failures.append(f"L_candidate {n_candidate} != {EXPECTED_L_CANDIDATE}")
    if n_clean != EXPECTED_CLEAN:
        failures.append(f"clean cases {n_clean} != {EXPECTED_CLEAN}")
    if len(case_index) != n_feasible:
        failures.append(f"descriptors {len(case_index)} != feasible {n_feasible}")
    if conflicts:
        failures.append(f"{conflicts} query-family conflicts")

    print()
    for name, cond in (
        (f"L_candidate == {EXPECTED_L_CANDIDATE:,}", n_candidate == EXPECTED_L_CANDIDATE),
        (f"N(Z=00000) == {EXPECTED_CLEAN:,}", n_clean == EXPECTED_CLEAN),
        ("#descriptors == L_feasible", len(case_index) == n_feasible),
        ("every class-local Q legal is consistent", conflicts == 0),
    ):
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")

    outdir = ROOT / "outputs" / "rebuild"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "gate_stage2.json").write_text(
        json.dumps(report, indent=1, default=str), encoding="utf-8")
    import gzip
    # gzipped: the raw dump is ~257 MB, over GitHub's 100 MB limit (the legacy
    # project hit the same wall with a 484 MB evidence file). Written as .gz
    # DIRECTLY so a clean checkout cannot regenerate the plain file -- an earlier
    # attempt gzipped the artifact by hand but left this open() in place.
    with gzip.open(outdir / "gate_stage2_cases.jsonl.gz", "wt",
                   encoding="utf-8", compresslevel=9) as fh:
        for v in classes.values():
            for cid in v:
                fh.write(json.dumps(case_index[cid].describe()) + "\n")
    print(f"\nwrote {outdir / 'gate_stage2.json'} and gate_stage2_cases.jsonl.gz")

    if failures:
        print("\nSTOP — " + "; ".join(failures))
        return 5
    return 0


def _domains(sol, kappa, tape, z, tr) -> dict:
    """Full legal fault-parameter domains on the healthy trace."""
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


if __name__ == "__main__":
    raise SystemExit(main())
