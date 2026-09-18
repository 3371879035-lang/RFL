r"""A76 blocker 1: is the a^+ guard reachable on the frozen T support?

`a_t^+ = min(A_D^*(s_t,z_t,m_t) \ {a_t^F})` is undefined iff
`A_D^*(x_t) = {a_t^F}`, i.e. iff the executed command was the UNIQUE optimum at the
REALIZED pre-action context.

The A76 draft argued unreachability from the canonical D domain, on the grounds that
it excludes the tie-broken `best_action`. That argument does not hold, and the review
was right to reject it: the domain is generated on the HEALTHY trace
(`fault_grammar.legal_fault_domains` walks `tr = rollout(...)` with no mask), so

    a_D != pi_D*(x_generation)     does NOT imply     a_D != unique optimum at x_factual

because in a co-fault world the realized context at step t can differ from the
generation context -- a P fault changes z^in-force, earlier X/E faults change the path,
and the automaton state m follows the path.

So this is measured rather than argued. For every decision-credited address on the
frozen support it reads the REALIZED pre-action context and reports whether the
alternative set is empty, decomposed by fire pattern.

Read-only.
"""

from __future__ import annotations

import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from a73_locator_gate import rebuild_case  # noqa: E402
from gate_stage2 import fire_of, reference_provider  # noqa: E402
from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.env.observation import walk_transition  # noqa: E402
from rfl_rebuild.method.support import DenseSupport  # noqa: E402
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

CACHE = ROOT / "experiments" / "v01r" / "support_cache"
BIT_D = 1
VAL_TOL = 1e-12


def optimal_actions(sol, s, z, m) -> tuple:
    row = sol.q.get((s, z, m))
    if not row:
        return ()
    best = max(row.values())
    return tuple(sorted(a for a, v in row.items() if v >= best - VAL_TOL))


def main() -> int:
    sol = solve_reference()
    provider = reference_provider(sol)
    sup = DenseSupport.load(CACHE, expected_kernel_fingerprint="full",
                            expected_dgp_fingerprint="full")
    n = len(sup)

    decision_credit = 0
    empty_alt = 0
    not_in_opt = 0          # the normal case: a^F is suboptimal at the realized ctx
    tied_opt = 0            # a^F is one of several optima at the realized ctx
    by_pattern = collections.defaultdict(lambda: [0, 0])   # fc -> [credit, empty]
    witnesses = []
    context_differs = 0
    checked_ctx = 0

    for wid in range(n):
        fc = sup.field(wid, "fire_code")
        if not (fc >> BIT_D) & 1:
            continue
        case, _idx = rebuild_case(sol, provider, sup, wid)
        if case.decision is None:
            continue
        decision_credit += 1
        t_star = case.decision.t

        tr = K.rollout(kappa=case.kappa, tape=case.tape(),
                       command_provider=provider, base_option=case.base_option,
                       mask=case.mask(), option_fault=case.option_fault)
        ctx = None
        for (s, z, m, a_cmd, _ar, _rw) in walk_transition(
                tr, case.kappa, case.phi, tr.option_in_force):
            if s.t == t_star:
                ctx = (s, z, m, a_cmd)
                break
        if ctx is None:
            continue
        s_t, z_t, m_t, a_F = ctx
        checked_ctx += 1

        opt = set(optimal_actions(sol, s_t, z_t, m_t))
        # Does the realized context still disagree with the generation context?
        if a_F not in opt:
            not_in_opt += 1
        elif len(opt) > 1:
            tied_opt += 1
        alt = opt - {a_F}
        by_pattern[format(fc, "05b")][0] += 1
        if not alt:
            empty_alt += 1
            by_pattern[format(fc, "05b")][1] += 1
            if len(witnesses) < 5:
                witnesses.append({
                    "world": wid, "fire": format(fc, "05b"),
                    "state": str(s_t), "z": z_t, "m": m_t,
                    "a_F": a_F, "A_D_star": sorted(opt),
                    "descriptor_t": t_star,
                })

    checks = {
        "every_decision_credited_address_was_readable": checked_ctx == decision_credit,
        "a_plus_guard_is_unreachable_on_the_frozen_support": empty_alt == 0,
    }
    ok = all(checks.values())

    print("A76 blocker 1: a^+ guard reachability on the frozen T support\n")
    print(f"  worlds scanned                             : {n:,}")
    print(f"  decision-credited addresses (Gamma_T*  ni Decision_t) : "
          f"{decision_credit:,}")
    print(f"  addresses whose realized context was read  : {checked_ctx:,}")
    print(f"\n  a^F NOT in A_D^* at the realized context   : {not_in_opt:,}")
    print(f"  a^F tied-optimal at the realized context   : {tied_opt:,}")
    print(f"  a^F is the UNIQUE optimum (EMPTY alt set)  : {empty_alt:,}")
    print(f"\n  per fire pattern (credit / empty-alt):")
    for fc, (c, e) in sorted(by_pattern.items(), key=lambda kv: -kv[1][0]):
        flag = "  <-- EMPTY" if e else ""
        print(f"    {fc}  credit={c:>7,}  empty={e:>5}{flag}")
    for k, v in checks.items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    if witnesses:
        print("\n  witnesses:")
        for w in witnesses:
            print(f"    {w}")
    verdict = ("exhaustive support invariant: the guard never fires on the frozen "
               "support" if empty_alt == 0 else
               "THE GUARD IS LIVE: NOT_EVALUABLE must enter the denominator and "
               "reporting rules")
    print(f"\nA76 blocker 1: {verdict}")

    out = ROOT / "experiments" / "v02r" / "a76_aplus_guard_reachability.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "worlds_scanned": n,
        "decision_credited_addresses": decision_credit,
        "addresses_read": checked_ctx,
        "a_F_suboptimal_at_realized_context": not_in_opt,
        "a_F_tied_optimal_at_realized_context": tied_opt,
        "empty_alternative_set": empty_alt,
        "by_fire_pattern": {k: {"credit": v[0], "empty": v[1]}
                            for k, v in sorted(by_pattern.items())},
        "witnesses": witnesses,
        "checks": checks,
        "status": "PASS" if ok else "FAIL",
        "verdict": verdict,
        "why_the_draft_argument_failed": ("legal_fault_domains is generated on the "
                                          "HEALTHY trace, so a_D != pi_D*(x_generation) "
                                          "does not imply a_D != unique optimum at the "
                                          "REALIZED context x_factual; a P fault can "
                                          "change z^in-force and earlier X/E faults "
                                          "change the path, and m follows the path"),
        "naming": ("if empty_alt is 0 this is an EXHAUSTIVE SUPPORT INVARIANT, not a "
                   "schema theorem: it is established by enumeration over the frozen "
                   "support, not by a structural proof"),
    }, indent=1, default=str), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
