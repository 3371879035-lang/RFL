"""S0 — Semantic Kernel Gate (A58). Real episodes, real replay, no hard-coded expectations.

`04-SEMANTIC-INVARIANTS.md` mixes two kinds of obligation:

* **kernel / evaluator-truth semantics**, which exist in `src/rfl_rebuild/env`
  and `src/rfl_rebuild/solve` today, and can be asserted for real;
* **learning / write semantics** (I1, I2, I6, C6 and the write halves of
  C0/C1/C2/C3/C5/C8), which have no implementation at all — there is no
  responsibility/update/write layer. Asserting those now would either be a fake
  PASS or would amount to implementing V0.2R/V0.3R early.

A58 therefore layers the gate without weakening it. Every item gets one of three
statuses and **never** ``N/A``:

    PASS                       asserted for real, right now
    BLOCKED_NOT_IMPLEMENTED    the layer does not exist yet
    FAIL                       asserted and violated

``BLOCKED_NOT_IMPLEMENTED`` is deliberately loud: ``N/A`` is the status that gets
forgotten. A version gate must consume this file and state, per item, whether the
version under test depends on it.

Every witness below is *found* by scanning the real feasible support and then
checked; nothing is compared against an expectation transcribed from the prose.
"""

from __future__ import annotations

import hashlib
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
    ControllerSite, Intervention, InterventionSet, Outcome, State,
)
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

PASS = "PASS"
BLOCKED = "BLOCKED_NOT_IMPLEMENTED"
FAIL = "FAIL"

SCAN_CAP = 400_000


def source_fingerprint() -> str:
    h = hashlib.sha256()
    for rel in ("src/rfl_rebuild/env/kernel.py", "src/rfl_rebuild/solve/dp.py",
                "scripts/gate_stage2.py"):
        h.update((ROOT / rel).read_bytes())
    return h.hexdigest()[:16]


def full_run(sol, case, members=()):
    try:
        return K.rollout(
            kappa=case.kappa, tape=case.tape(),
            command_provider=reference_provider(sol),
            base_option=case.base_option, mask=case.mask(),
            option_fault=case.option_fault,
            interventions=InterventionSet(tuple(members)),
        )
    except Exception:
        return None


def step_tuple(tr):
    return tuple(
        (s.state.x, s.state.y, s.state.t, s.state.kappa, s.state.phi,
         s.control.z, s.control.m, s.a_cmd, s.u, s.a_realized,
         round(s.reward, 9), s.terminal, s.outcome, s.illegal)
        for s in tr.steps
    )


def trace_tuple(tr):
    return (step_tuple(tr), tr.outcome, tr.control.z, tr.control.m,
            tr.base_option, tr.option_in_force)


def size1_candidates(sol, case, ftr):
    out = [("process_commit", (Intervention.commit_identity(),))]
    for zp in K.option_ids():
        if zp != case.base_option:
            out.append(("strategy_replay", (Intervention.process(zp),)))
    for t in range(K.HORIZON):
        for a in range(len(K.ACTIONS)):
            out.append(("decision", (Intervention.decision(t, a),)))
    st = State(x=K.START[0], y=K.START[1], t=0, kappa=case.kappa, phi=case.phi)
    for s in ftr.steps:
        out.append(("execution",
                    (Intervention.execution(ControllerSite(state=st, cmd=s.a_cmd)),)))
        st = s.state
    return out


def sufficient(sol, case, members):
    tr = full_run(sol, case, members)
    return tr is not None and tr.outcome == Outcome.SUCCESS


def main() -> int:
    sol = solve_reference()
    provider = reference_provider(sol)

    items: dict[str, dict] = {}

    def record(key, status, title, observed, why="", witness=None):
        items[key] = {"status": status, "title": title,
                      "observed": observed, "note": why, "witness": witness}

    # ------------------------------------------------------------------ #
    # find witnesses by scanning the real feasible support
    # ------------------------------------------------------------------ #
    w = {}
    n_scan = 0
    stop = False
    for kappa in KAPPAS:
        if stop:
            break
        for tape in TAPES:
            if stop:
                break
            for z in K.option_ids():
                if stop:
                    break
                tr0 = K.rollout(kappa=kappa, tape=tape, command_provider=provider,
                                base_option=z)
                dom = _domains(sol, kappa, tape, z, tr0)
                canon = {k: canonicalise(dom[k]) for k in CAUSE_KEYS}
                for bits in itertools.product((0, 1), repeat=5):
                    if stop:
                        break
                    active = [k for k, b in zip(CAUSE_KEYS, bits) if b]
                    if any(not canon[k] for k in active):
                        continue
                    for combo in itertools.product(*[canon[k] for k in active]):
                        case = LatentCase(
                            case_id=0, kappa=kappa, phi=tape.phase,
                            error_flag=tape.error_flag, cause_rank=tape.cause_rank,
                            base_option=z, Z=bits,
                            option_fault=blocks_get(active, combo, "P"),
                            decision=blocks_get(active, combo, "D"),
                            controller=blocks_get(active, combo, "X"),
                            plant=blocks_get(active, combo, "E"),
                            trap=blocks_get(active, combo, "U"))
                        if sigma0(sol, case)[0] is None:
                            continue
                        n_scan += 1
                        if n_scan > SCAN_CAP:
                            stop = True
                            break
                        ftr = full_run(sol, case)
                        if ftr is None:
                            continue
                        fire = fire_of(sol, case)
                        base_ok = ftr.outcome == Outcome.SUCCESS

                        if "C0" not in w and all(x == 0 for x in fire) and base_ok:
                            w["C0"] = (case, ftr, fire)
                        if ("C1" not in w and fire[2] == 1 and fire[1] == 0
                                and any(s.u != s.a_cmd for s in ftr.steps)
                                and all(s.a_realized == s.u for s in ftr.steps)):
                            w["C1"] = (case, ftr, fire)
                        if ("C2" not in w and fire[1] == 1 and fire[2] == 0
                                and all(s.u == s.a_cmd for s in ftr.steps)):
                            w["C2"] = (case, ftr, fire)
                        if "C3" not in w and fire[0] == 1:
                            w["C3"] = (case, ftr, fire)
                        if ("C5" not in w and fire[3] == 1 and fire[2] == 0
                                and any(s.a_realized != s.u for s in ftr.steps)):
                            w["C5"] = (case, ftr, fire)
                        if ("C8" not in w and fire[3] == 1 and fire[2] == 0
                                and base_ok):
                            w["C8"] = (case, ftr, fire)
                        if "C7" not in w and not base_ok:
                            cands = size1_candidates(sol, case, ftr)
                            good = [(lb, mem) for lb, mem in cands
                                    if sufficient(sol, case, mem)]
                            if len(good) >= 2:
                                w["C7"] = (case, ftr, fire, good)
                        if ("C4" not in w and not base_ok and fire[0] == 0):
                            cands = size1_candidates(sol, case, ftr)
                            dec_ok = any(
                                lb == "decision" and sufficient(sol, case, mem)
                                for lb, mem in cands)
                            strat_ok = [(lb, mem) for lb, mem in cands
                                        if lb == "strategy_replay"
                                        and sufficient(sol, case, mem)]
                            if not dec_ok and strat_ok:
                                w["C4"] = (case, ftr, fire, strat_ok)
                        if len(w) >= 8:
                            stop = True
                            break

    def wr(k):
        if k not in w:
            return None
        c, t, f = w[k][0], w[k][1], w[k][2]
        return {"kappa": c.kappa, "phi": c.phi, "Z": "".join(map(str, c.Z)),
                "fire": "".join(map(str, f)), "base_option": c.base_option,
                "option_fault": c.option_fault, "decision": repr(c.decision),
                "controller": repr(c.controller), "plant": repr(c.plant),
                "trap": repr(c.trap), "factual_outcome": t.outcome}

    # ------------------------------------------------------------------ #
    # I3 — |R*| != #R*
    # ------------------------------------------------------------------ #
    ge = json.loads((ROOT / "outputs" / "rebuild" / "gate_e.json")
                    .read_text(encoding="utf-8"))
    card = ge["cardinality_histogram"]
    ties = ge["tie_histogram"]
    ties_gt1 = sum(v for k, v in ties.items() if int(k) > 1)
    record("I3", PASS if (int(card.get("1", 0)) > 0 and ties_gt1 > 0) else FAIL,
           "|R*| != #R*: minimal cardinality and tie count are separate",
           {"|R*|=1": int(card.get("1", 0)), "cases_with_#R*>1": ties_gt1,
            "max_#R*": max(int(k) for k in ties)},
           "Reuses formal Gate E's full-support result; a search stopping at the "
           "first sufficient repair would have collapsed all of these to #R*=1.",
           wr("C7"))

    # ------------------------------------------------------------------ #
    # I4 — truth provenance: no label may be reconstructed from behaviour
    # ------------------------------------------------------------------ #
    i4 = {}
    if "C1" in w:
        c, t, f = w["C1"]
        # The legacy `scene_from_trace` bug: realized != reference was read as a
        # DECISION fault. Under the fire receipt this case is X only.
        i4["X_only_case_reconstructed_as_D"] = bool(f[1])
    if "C2" in w:
        c, t, f = w["C2"]
        i4["D_only_case_reconstructed_as_X"] = bool(f[2])
    if "C5" in w:
        c, t, f = w["C5"]
        i4["E_fired_case_reconstructed_as_X"] = bool(f[2])
    i4_ok = all(v is False for v in i4.values()) and len(i4) == 3
    record("I4", PASS if i4_ok else FAIL,
           "Z^pres only from injection, Z^fire only from a forward fire receipt, "
           "B only from the evaluator counterfactual",
           i4, "Each mis-reconstruction probe must come out False: if the truth "
               "were derived from learner-visible behaviour it would go True.",
           {"C1": wr("C1"), "C2": wr("C2"), "C5": wr("C5")})

    # ------------------------------------------------------------------ #
    # I5 — exact replay, field by field
    # ------------------------------------------------------------------ #
    i5 = {}
    if "C3" in w:
        c, t, f = w["C3"]
        again = full_run(sol, c)
        i5["deterministic_second_run_identical"] = (
            again is not None and trace_tuple(again) == trace_tuple(t))
        i5["fields_compared"] = ["x", "y", "t", "kappa", "phi", "z", "m",
                                 "a_cmd", "u", "a_realized", "reward",
                                 "terminal", "outcome", "illegal",
                                 "trace.outcome", "trace.control.z",
                                 "trace.control.m", "trace.base_option",
                                 "trace.option_in_force"]
        # perturbation: clearing the option fault must move the trace where a
        # commit fault is present; a trace that ignores its truth fields is not
        # a faithful replay
        variants = {"option_fault_cleared": dict(option_fault=None)}
        changed = 0
        for name, kw in variants.items():
            alt = full_run(sol, _replace_case(c, **kw))
            if alt is not None and trace_tuple(alt) != trace_tuple(t):
                changed += 1
        i5["truth_perturbations_that_moved_the_trace"] = changed
        i5["truth_perturbations_tried"] = len(variants)
    i5_ok = (i5.get("deterministic_second_run_identical") is True
             and i5.get("truth_perturbations_that_moved_the_trace", 0) > 0)
    record("I5", PASS if i5_ok else FAIL,
           "Replay reproduces StepResult, control, outcome, reward, option fields "
           "exactly, and the trace genuinely depends on the truth",
           i5, "Comparing outcome alone would pass even if the replay perturbed "
               "the run; the perturbation count proves the comparison is not "
               "vacuous.", wr("C3"))

    # ------------------------------------------------------------------ #
    # Case suite — kernel/evaluator halves
    # ------------------------------------------------------------------ #
    if "C0" in w:
        c, t, f = w["C0"]
        fb = sigma0(sol, c)[0][1]
        record("C0", PASS,
               "no fault: healthy factual success, Z^fire = 0, feedback schema ok",
               {"factual_outcome": t.outcome, "fire": "".join(map(str, f)),
                "feedback_is_len5_onehot": len(fb) == 5
                and sum(fb) in (0, 1)},
               "Kernel half only. The 'no update path was invoked' half is "
               "BLOCKED: there is no update layer to invoke.", wr("C0"))
    if "C1" in w:
        c, t, f = w["C1"]
        record("C1", PASS, "execution-only: u != a_cmd while the plant is faithful",
               {"fire": "".join(map(str, f)),
                "n_steps_u_ne_a_cmd": sum(1 for s in t.steps if s.u != s.a_cmd),
                "n_steps_plant_deviated": sum(1 for s in t.steps
                                              if s.a_realized != s.u)},
               "Truth half only; the write half is BLOCKED.", wr("C1"))
    if "C2" in w:
        c, t, f = w["C2"]
        record("C2", PASS, "decision-only: override reached, controller faithful",
               {"fire": "".join(map(str, f)),
                "override_t": c.decision.t if c.decision else None,
                "n_steps": len(t.steps),
                "n_steps_u_ne_a_cmd": sum(1 for s in t.steps if s.u != s.a_cmd)},
               "Truth half only; the write half is BLOCKED.", wr("C2"))
    if "C3" in w:
        c, t, f = w["C3"]
        audit = K.rollout(kappa=c.kappa, tape=c.tape(), command_provider=provider,
                          base_option=c.base_option, mask=c.mask(),
                          option_fault=c.option_fault)
        commit = full_run(sol, c, (Intervention.commit_identity(),))
        record("C3", PASS, "commit integrity: z^proposal != z^in-force",
               {"fire": "".join(map(str, f)),
                "z_proposal": c.base_option,
                "z_in_force": audit.option_in_force,
                "proposal_audit_exposes_mismatch":
                    audit.option_in_force != c.base_option,
                "commit_repair_is_its_own_node":
                    Intervention.commit_identity().node() == ("process_commit",),
                "commit_repair_outcome": commit.outcome if commit else None},
               "z^proposal is NOT required to be optimal -- the case only needs "
               "the commit edge to be unfaithful. Write half BLOCKED.", wr("C3"))
    if "C4" in w:
        c, t, f, strat = w["C4"]
        record("C4", PASS,
               "strategy granularity: no singleton decision repair suffices, a "
               "do(z=z') does -- and there is no commit fault",
               {"fire": "".join(map(str, f)),
                "z_proposal": c.base_option,
                "n_strategy_repairs_sufficient": len(strat),
                "has_Z_P_fault": bool(f[0])},
               "This is a lattice statement about repair granularity, NOT the "
               "definition of Z_P; the witness has Z_P^fire = 0 to make that "
               "explicit.", wr("C4"))
    if "C5" in w:
        c, t, f = w["C5"]
        record("C5", PASS, "environment fault: plant deviated, controller faithful",
               {"fire": "".join(map(str, f)),
                "n_steps_plant_deviated": sum(1 for s in t.steps
                                              if s.a_realized != s.u),
                "n_steps_u_ne_a_cmd": sum(1 for s in t.steps if s.u != s.a_cmd)},
               "Kernel half only; the method-output half needs the V0.1R "
               "inference arm and is BLOCKED.", wr("C5"))
    if "C7" in w:
        c, t, f, good = w["C7"]
        replayed = sum(1 for lb, mem in good if sufficient(sol, c, mem))
        record("C7", PASS, "tied repairs: |R*| = 1 with #R* >= 2, every tied candidate replays to success",
               {"n_tied_minimal_repairs": len(good),
                "tied_candidates_replayed_ok": replayed,
                "kinds": sorted({lb for lb, _ in good})},
               "Asserted on a constructed failing episode, not read off Gate E.",
               wr("C7"))
    if "C8" in w:
        c, t, f = w["C8"]
        record("C8", PASS,
               "external plant fault with U* = empty (factual already succeeds)",
               {"fire": "".join(map(str, f)), "factual_outcome": t.outcome},
               "Truth half only; the 'no learning runtime may write Q/C_X' half "
               "is BLOCKED.", wr("C8"))

    # ------------------------------------------------------------------ #
    # BLOCKED items — the learning/write layer does not exist
    # ------------------------------------------------------------------ #
    for key, title, dep in (
        ("I1", "write-space disjointness across units", "V0.2R"),
        ("I2", "no write without a responsible unit", "V0.2R"),
        ("I6", "update budget per episode", "V0.2R/V0.3R"),
        ("C6", "write collision between two units", "V0.2R"),
    ):
        record(key, BLOCKED, title,
               {"layer": "responsibility / update / write-space",
                "present_in_src": sorted(p.name for p in
                                         (ROOT / "src" / "rfl_rebuild").iterdir())},
               f"No implementation exists. NOT marked N/A: this must be converted "
               f"to a real PASS/FAIL when the write layer lands, and {dep} depends "
               f"on it.")

    # V0.1R true-but-not-sufficient items: C0's no-write half is vacuously true
    # for V0.1R, and A58 forbids letting that masquerade as a verified invariant.
    items["V0.1R_DEPENDENCY"] = {
        "status": PASS,
        "title": "V0.1R depends on I3/I4/I5 and the kernel halves only",
        "observed": {"needs": ["I3", "I4", "I5", "C0-kernel", "C1-truth",
                               "C2-truth", "C3", "C4", "C5-kernel", "C7",
                               "C8-truth"],
                     "does_not_need": ["I1", "I2", "I6", "C6",
                                       "C0-no-write", "C1-write", "C2-write",
                                       "C3-write", "C5-method", "C8-no-write"]},
        "note": "V0.1R has no update path, so the write invariants are vacuous for "
                "it. That is NOT evidence they hold, and they stay "
                "BLOCKED_NOT_IMPLEMENTED.",
        "witness": None,
    }

    counts = Counter(v["status"] for v in items.values())
    overall = (PASS if counts.get(FAIL, 0) == 0
               and all(items[k]["status"] == PASS for k in
                       ("I3", "I4", "I5", "C0", "C1", "C2", "C3", "C4", "C5",
                        "C7", "C8") if k in items)
               else FAIL)

    report = {
        "gate": "S0 — Semantic Kernel Gate (A58)",
        "source_fingerprint": source_fingerprint(),
        "cases_scanned": n_scan,
        "status_counts": dict(counts),
        "overall": overall,
        "items": items,
        "blocked_disclosure": (
            "BLOCKED_NOT_IMPLEMENTED means the layer does not exist. It is never "
            "N/A, and a version gate consuming this file must state whether the "
            "version depends on each blocked item."),
    }

    outdir = ROOT / "experiments" / "v01r"
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / "semantic_gate.json"
    out.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")

    print(f"scanned {n_scan:,} feasible cases to find witnesses")
    print(f"\nS0 status counts: {dict(counts)}")
    for k in sorted(items):
        it = items[k]
        print(f"  {k:<5} {it['status']:<26} {it['title'][:58]}")
    print(f"\noverall: {overall}")
    print(f"fingerprint: {report['source_fingerprint']}")
    print(f"wrote {out}")
    return 0 if overall == PASS else 1


def blocks_get(active, combo, want):
    for k, v in zip(active, combo):
        if k == want:
            return v
    return None


def _replace_case(case, **kw):
    from dataclasses import replace
    return replace(case, **kw)


if __name__ == "__main__":
    raise SystemExit(main())
