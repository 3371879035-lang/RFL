r"""A75 pre-check: can a learner-baseline decision defect be seen, and by what?

The V0.3R Regime P needs "a persistent learner defect manifested". The frozen
V0.1R/V0.2R object answers a different question and must NOT be changed:

    Z_D^fire = 1[ the injected DecisionOverride mechanism actually executed ]

which is why it reads ``mask.decision`` and not the action's quality. Replacing it
by a behavioural predicate would reopen V0.1R's closed target. So A75 adds a new
object instead:

    J_D^L = 1[ exists t : a^cmd_t not in A_D^*(s_t, z_t, m_t) ]

where ``A_D^*(s,z,m)`` is the whole argmax SET over ``A_z(m,s)`` -- not the
tie-broken ``best_action``. Reporting a second optimal action as a persistent
defect would manufacture errors that do not exist.

This script checks four things, all read-only.

1. **Frozen semantics.** With NO ``mask.decision`` but a provider that emits a
   strictly suboptimal action at a reachable context: today
   ``fired_mechanisms()["Z_D"] == 0`` while ``J_D^L == 1``. The current truth is
   blind to learner-origin defects, by design.
2. **Mask semantics.** A reachable ``DecisionOverride`` gives ``Z_D^fire == 1``
   whether or not it costs value, including when the override picks a TIED-optimal
   action. That is "mechanism executed", not "behavioural defect" -- recorded, not
   changed.
3. **Tie audit.** Over the whole exact DP support: how many ``(s,z,m)`` have
   ``|A_D^*| > 1``, and inside the current D fault domain how many candidates have
   ``a != best_action`` yet ``a in A_D^*``. A non-zero count is a catalogue of
   "decision faults" that carry no value loss.
4. **Architecture-neutral reproduction.** The SAME ``(s,z,m,a^-)`` is installed
   independently in a Q-backed store (one corrupted value changes the row's
   argmax) and in a patch-backed store (one override entry), with no translation
   between them. Both must produce the same command sequence and the same
   ``J_D^L``. This is the minimal prototype of the defect-family fairness gate.

Read-only: reads the kernel, the exact solver, and the public grammar. Writes only
its own report.
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.env.kernel import DecisionOverride, FaultMask, SemanticTape  # noqa: E402
from rfl_rebuild.env.observation import walk_transition  # noqa: E402
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

VAL_TOL = 1e-12


def optimal_actions(sol, s, z, m) -> tuple:
    r"""``A_D^*(s,z,m)``: the whole argmax set, not the tie-broken policy."""
    row = sol.q[(s, z, m)]
    if not row:
        return ()
    best = max(row.values())
    return tuple(sorted(a for a, v in row.items() if v >= best - VAL_TOL))


def jd_l(sol, trace, kappa: int, phi: int) -> int:
    r"""``J_D^L``: did the learner-owned baseline induce a suboptimal command?"""
    for (s, z, m, a_cmd, _ar, _rw) in walk_transition(
            trace, kappa, phi, trace.option_in_force):
        if a_cmd not in optimal_actions(sol, s, z, m):
            return 1
    return 0


def find_witness(sol, need_strict: bool):
    """Find a reachable (state, z, m) with a qualifying alternative action.

    ``need_strict`` selects a STRICTLY suboptimal alternative (a genuine
    behavioural defect). Otherwise it selects a TIED-optimal alternative that the
    tie-broken policy would not pick -- the case the current D fault domain
    catalogues as a decision fault although it costs no value.
    """
    tapes = [SemanticTape(phase=p, error_flag=0, cause_rank=0)
             for p in K.PHASE_DOMAIN]
    for kappa in (0, 1):
        for tape in tapes:
            for z in K.option_ids():
                tr = K.rollout(kappa=kappa, tape=tape,
                               command_provider=lambda s, c: sol.best_action(
                                   s, c.z, c.m),
                               base_option=z)
                for (s, zz, m, a_cmd, _ar, _rw) in walk_transition(
                        tr, kappa, tape.phase, tr.option_in_force):
                    adm = K.option_actions(zz, K.ControlState(z=zz, m=m), s)
                    opt = set(optimal_actions(sol, s, zz, m))
                    policy = sol.best_action(s, zz, m)
                    if need_strict:
                        bad = [a for a in adm if a not in opt]
                    else:
                        # tied-optimal yet not the tie-broken pick
                        bad = [a for a in adm if a in opt and a != policy]
                    if bad:
                        return {"kappa": kappa, "phi": tape.phase, "z": zz,
                                "state": s, "m": m, "a_minus": bad[0],
                                "a_cmd": a_cmd, "adm": adm,
                                "opt": tuple(sorted(opt))}
    return None


def main() -> int:
    sol = solve_reference()
    report: dict = {}
    checks: dict = {}

    # ---- 3. tie audit (computed first: it tells us whether a tie witness exists)
    n_entries = 0
    n_tied = 0
    tied_examples = []
    for (s, z, m) in list(sol.q):
        adm = K.option_actions(z, K.ControlState(z=z, m=m), s)
        if not adm:
            continue
        n_entries += 1
        opt = optimal_actions(sol, s, z, m)
        if len(opt) > 1:
            n_tied += 1
            if len(tied_examples) < 5:
                tied_examples.append({"state": str(s), "z": z, "m": m,
                                      "optimal": list(opt),
                                      "policy": sol.best_action(s, z, m)})

    # D fault domain membership: current `_domains` excludes the tie-broken
    # best_action but INCLUDES tied alternatives.
    n_domain_candidates = 0
    n_domain_tied = 0
    for (s, z, m) in list(sol.q):
        adm = K.option_actions(z, K.ControlState(z=z, m=m), s)
        if not adm:
            continue
        policy = sol.best_action(s, z, m)
        opt = set(optimal_actions(sol, s, z, m))
        for a in adm:
            if a == policy:
                continue                      # excluded by the current domain
            n_domain_candidates += 1
            if a in opt:
                n_domain_tied += 1

    # ---- 3b. the same question, but on the CANONICAL SUPPORT's actual D slots.
    # The domain count above is potential; this is the operative one, because the
    # frozen support only ever carries first/last of each legal domain.
    from gate_stage2 import reference_provider  # noqa: E402
    from identifiability_gate import KAPPAS, TAPES  # noqa: E402
    from rfl_rebuild.env import fault_grammar as FG  # noqa: E402

    provider = reference_provider(sol)
    ctx_seen = 0
    slots = 0
    slots_tied = 0
    for kappa in KAPPAS:
        for tape in TAPES:
            for z in K.option_ids():
                ctx_seen += 1
                tr = K.rollout(kappa=kappa, tape=tape,
                               command_provider=provider, base_option=z)
                at = {}
                for (s, zz, m, _ac, _ar, _rw) in walk_transition(
                        tr, kappa, tape.phase, tr.option_in_force):
                    at[s.t] = (s, zz, m)
                doms = FG.canonical_domains(sol, kappa, tape, z, tr)
                for d in doms["D"]:
                    slots += 1
                    ctx = at.get(d.t)
                    if ctx is None:
                        continue
                    if d.action in set(optimal_actions(sol, *ctx)):
                        slots_tied += 1

    # ---- 1. frozen semantics: learner-origin defect is invisible to Z_D^fire
    strict = find_witness(sol, need_strict=True)
    learned_provider = None
    if strict is not None:
        target = strict["state"]
        a_minus = strict["a_minus"]

        def learned_provider(s, c, _t=target, _a=a_minus):
            if s == _t:
                return _a
            return sol.best_action(s, c.z, c.m)

        tape = SemanticTape(phase=strict["phi"], error_flag=0, cause_rank=0)
        fm = K.fired_mechanisms(kappa=strict["kappa"], tape=tape,
                                command_provider=learned_provider,
                                base_option=strict["z"], mask=FaultMask())
        tr = K.rollout(kappa=strict["kappa"], tape=tape,
                       command_provider=learned_provider,
                       base_option=strict["z"])
        report["frozen_semantics"] = {
            "witness": {k: str(v) for k, v in strict.items()},
            "fired_mechanisms_Z_D": fm["Z_D"],
            "fired_mechanisms_all": dict(fm),
            "J_D_L": jd_l(sol, tr, strict["kappa"], strict["phi"]),
        }
        checks["1_learner_defect_is_invisible_to_frozen_Z_D"] = fm["Z_D"] == 0
        checks["1_learner_defect_is_visible_to_J_D_L"] = \
            report["frozen_semantics"]["J_D_L"] == 1

    # ---- 2. mask semantics, including a TIED-optimal override
    tie = find_witness(sol, need_strict=False)
    mask_cases = {}
    for label, wit in (("strict_suboptimal_override", strict),
                       ("tied_optimal_override", tie)):
        if wit is None:
            mask_cases[label] = None
            continue
        tape = SemanticTape(phase=wit["phi"], error_flag=0, cause_rank=0)
        ov = DecisionOverride(t=wit["state"].t, action=wit["a_minus"])
        fm = K.fired_mechanisms(kappa=wit["kappa"], tape=tape,
                                command_provider=lambda s, c: sol.best_action(
                                    s, c.z, c.m),
                                base_option=wit["z"], mask=FaultMask(decision=ov))
        tr = K.rollout(kappa=wit["kappa"], tape=tape,
                       command_provider=lambda s, c: sol.best_action(s, c.z, c.m),
                       base_option=wit["z"], mask=FaultMask(decision=ov))
        mask_cases[label] = {
            "override": f"t={ov.t} action={ov.action}",
            "fired_mechanisms_Z_D": fm["Z_D"],
            "J_D_L": jd_l(sol, tr, wit["kappa"], wit["phi"]),
            "value_optimal": wit["a_minus"] in set(wit["opt"]),
        }
    report["mask_semantics"] = mask_cases
    if mask_cases.get("strict_suboptimal_override"):
        checks["2_mask_override_sets_Z_D_fire"] = \
            mask_cases["strict_suboptimal_override"]["fired_mechanisms_Z_D"] == 1
    if mask_cases.get("tied_optimal_override"):
        t = mask_cases["tied_optimal_override"]
        checks["2_tied_override_fires_Z_D_but_is_not_a_defect"] = \
            t["fired_mechanisms_Z_D"] == 1 and t["J_D_L"] == 0

    # ---- 4. architecture-neutral reproduction of one and the same defect
    arch = None
    if strict is not None:
        s0, z0, m0, a_minus = (strict["state"], strict["z"], strict["m"],
                               strict["a_minus"])
        tape = SemanticTape(phase=strict["phi"], error_flag=0, cause_rank=0)
        adm0 = K.option_actions(z0, K.ControlState(z=z0, m=m0), s0)

        # (a) Q-backed: a FULL table initialised to the exact values, then ONE
        #     value corrupted so that the row's argmax becomes a_minus.
        table = {}
        for (s, z, m), row in sol.q.items():
            for a, v in row.items():
                table[(s, z, m, a)] = v
        table[(s0, z0, m0, a_minus)] = max(
            sol.q_value(s0, z0, m0, a) for a in adm0) + 1.0

        def q_backed(s, c):
            row = {a: table[(s, c.z, c.m, a)] for a in
                   K.option_actions(c.z, c, s) if (s, c.z, c.m, a) in table}
            if not row:
                return sol.best_action(s, c.z, c.m)
            best = max(row.values())
            return min(a for a, v in row.items() if v >= best - VAL_TOL)

        # (b) patch-backed: an EMPTY override dict plus ONE entry, no translation
        #     from the Q corruption above.
        patches = {(s0, z0, m0): a_minus}

        def patch_backed(s, c):
            hit = patches.get((s, c.z, c.m))
            return hit if hit is not None else sol.best_action(s, c.z, c.m)

        def run(provider):
            tr = K.rollout(kappa=strict["kappa"], tape=tape,
                           command_provider=provider, base_option=z0)
            cmds = tuple(s.a_cmd for s in tr.steps)
            return cmds, jd_l(sol, tr, strict["kappa"], strict["phi"])

        cmd_q, jd_q = run(q_backed)
        cmd_p, jd_p = run(patch_backed)
        arch = {
            "witness": f"s={s0} z={z0} m={m0} a^-={a_minus}",
            "q_backed_first_command": cmd_q[0] if cmd_q else None,
            "patch_backed_first_command": cmd_p[0] if cmd_p else None,
            "commands_identical": cmd_q == cmd_p,
            "J_D_L_q_backed": jd_q,
            "J_D_L_patch_backed": jd_p,
            "J_D_L_identical": jd_q == jd_p,
            "note": ("both stores were built independently: the Q store was "
                     "corrupted at one value, the patch store got one override "
                     "entry; neither was translated into the other"),
        }
        checks["4_two_architectures_reproduce_the_same_defect"] = \
            (cmd_q == cmd_p) and (jd_q == jd_p)
        checks["4_the_defect_is_visible_to_J_D_L_in_both"] = jd_q == 1 and jd_p == 1

    # ---- verdict
    ok = all(checks.values())
    print("A75 pre-check: learner-baseline decision defects\n")
    print("  3. tie audit")
    print(f"     (s,z,m) entries with an admissible set     : {n_entries:,}")
    print(f"     entries with |A_D^*| > 1 (ties exist)      : {n_tied:,}")
    print(f"     D-domain candidates excluded: == tie-broken")
    print(f"       policy, counted over entries              : {n_domain_candidates:,}")
    print(f"     ...of those, TIED-OPTIMAL (a != best_action")
    print(f"       yet a in A_D^*, i.e. 'faults' with no")
    print(f"       value loss)                              : {n_domain_tied:,} "
          f"({100 * n_domain_tied / max(n_domain_candidates, 1):.1f}% of the domain)")
    print(f"     CANONICAL support D slots over {ctx_seen:,} contexts : {slots:,}")
    print(f"     ...that are TIED-OPTIMAL (no value loss)    : {slots_tied:,} "
          f"({100 * slots_tied / max(slots, 1):.1f}% of actual slots)")
    print("\n  1. frozen semantics (no mask.decision)")
    fs = report.get("frozen_semantics")
    if fs:
        print(f"     witness                                    : "
              f"z={strict['z']} t={strict['state'].t} a^-={strict['a_minus']}")
        print(f"     fired_mechanisms()['Z_D']                  : "
              f"{fs['fired_mechanisms_Z_D']}")
        print(f"     J_D^L                                      : {fs['J_D_L']}")
    print("\n  2. mask semantics")
    for label, c in report.get("mask_semantics", {}).items():
        if c:
            print(f"     {label:<28} {c['override']:<18} "
                  f"Z_D={c['fired_mechanisms_Z_D']} J_D^L={c['J_D_L']} "
                  f"value_optimal={c['value_optimal']}")
    print("\n  4. architecture-neutral reproduction")
    if arch:
        print(f"     commands identical (Q vs patch)            : "
              f"{arch['commands_identical']}")
        print(f"     J_D^L identical (Q vs patch)               : "
              f"{arch['J_D_L_identical']}  ({arch['J_D_L_q_backed']} / "
              f"{arch['J_D_L_patch_backed']})")
    print()
    for k, v in checks.items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    print(f"\nA75 pre-check: {'ALL PASS' if ok else 'FAIL'}")

    out = ROOT / "experiments" / "v02r" / "a75_jd_manifestation_precheck.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "tie_audit": {
            "n_entries_with_admissible_set": n_entries,
            "n_entries_with_ties": n_tied,
            "n_D_domain_candidates": n_domain_candidates,
            "n_D_domain_candidates_that_are_tied_optimal": n_domain_tied,
            "tie_examples": tied_examples,
            "n_contexts_scanned_for_canonical_slots": ctx_seen,
            "n_canonical_D_slots": slots,
            "n_canonical_D_slots_that_are_tied_optimal": slots_tied,
            "reading": ("the frozen D fault domain excludes the tie-broken "
                        "best_action but INCLUDES tied alternatives, so a share of "
                        "catalogued 'decision faults' carry no value loss. "
                        "'a decision fault happened' is therefore weaker than 'a "
                        "bad decision happened'. Recorded against V0.1R/V0.2R, not "
                        "changed"),
        },
        "frozen_semantics": report.get("frozen_semantics"),
        "mask_semantics": report.get("mask_semantics"),
        "architecture_neutral_reproduction": arch,
        "J_D_L_definition": ("J_D^L = 1[exists t : a^cmd_t not in A_D^*(s_t,z_t,m_t)] "
                             "with A_D^* the whole argmax SET, not the tie-broken "
                             "best_action"),
        "why_not_replace_Z_D": ("Z_D^fire answers 'did the injected DecisionOverride "
                               "mechanism execute', which is V0.1R's closed target. "
                               "Replacing it with a behavioural predicate would "
                               "reopen that semantics; A75 adds J_D^L instead"),
        "checks": checks,
        "status": "PASS" if ok else "FAIL",
    }, indent=1, default=str), encoding="utf-8")
    print(f"wrote {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
