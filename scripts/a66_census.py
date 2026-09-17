"""A66 — mechanism-repair vs rescue enumerators, and the truth census.

The two truths A65 separated:

  R^mech   interventions that RESTORE a faulty mechanism
  R^rescue interventions that make the episode SUCCEED, by any means

R^mech is structural and needs no simulation. R^rescue does need it, so it is
enumerated the way Gate E enumerated R*_suff.

Census reports WORLD COUNTS AND DGP-WEIGHTED MASS side by side. V0.1R already
showed those differ by an order of magnitude on the same support (the enumeration
ratio 10.9% versus the DGP mass 0.8%), so a count alone is not a probability.

A DEFINITION AMBIGUITY IS REPORTED, NOT RESOLVED. "Restore the mechanism" can
mean (a) undo EVERY firing of that cause, or (b) undo at least one. They give
different |R^mech|. Both are computed and reported so the choice is made in the
open rather than baked into a script.

Agent-side repair primitives, per fired cause:

  Z_P  do(C_P = identity)                      -- A57, restores a faithful commit
  Z_D  do(d_t = pi*(s_t, z, m)) at the override -- undo the override
  Z_X  do(C_X(s*, a^cmd) = a^cmd) per deviating site -- A7 single-cell primitive
  Z_E  NONE: the plant is external; no agent-side write restores it
  Z_U  NONE: the trap already terminated the episode

R^mech, and R^rescue need not coincide, and when they differ that difference is
the structure V0.2R exists to study. In particular a rescue can succeed by
strategy replay while repairing no mechanism at all.
"""

from __future__ import annotations

import itertools
import json
import math
import pathlib
import sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gate_stage2 import LatentCase, _domains, reference_provider, sigma0  # noqa: E402
from identifiability_gate import CAUSE_KEYS, KAPPAS, TAPES, canonicalise  # noqa: E402
from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.env.kernel import (  # noqa: E402
    ControllerSite, Intervention, InterventionSet, Outcome, SemanticTape, State,
)
from rfl_rebuild.method.dgp import SceneContext  # noqa: E402
from rfl_rebuild.method.support import DenseSupport  # noqa: E402
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

CACHE = ROOT / "experiments" / "v01r" / "support_cache"
REPAIRABLE = {"P", "D", "X"}          # causes with an agent-side primitive
UNREPAIRABLE = {"E", "U"}


def main() -> int:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    sol = solve_reference()
    provider = reference_provider(sol)
    sup = DenseSupport.load(CACHE, expected_kernel_fingerprint="full",
                            expected_dgp_fingerprint="full")

    def domains(ctx):
        tape = SemanticTape(phase=ctx.phase, error_flag=ctx.error_flag,
                            cause_rank=ctx.cause_rank)
        tr = K.rollout(kappa=ctx.kappa, tape=tape, command_provider=provider,
                       base_option=ctx.base_option)
        d = _domains(sol, ctx.kappa, tape, ctx.base_option, tr)
        return tuple(canonicalise(d[k]) for k in CAUSE_KEYS)

    def rebuild(wid):
        ctx = SceneContext(kappa=sup.field(wid, "kappa"),
                           phase=sup.field(wid, "phase"),
                           error_flag=sup.field(wid, "error_flag"),
                           cause_rank=sup.field(wid, "cause_rank"),
                           base_option=sup.field(wid, "proposal"))
        dm = domains(ctx)
        b = {k: (dm[i][sup.field(wid, f"p{i}")]
                 if sup.field(wid, f"p{i}") >= 0 else None)
             for i, k in enumerate(CAUSE_KEYS)}
        zc = sup.field(wid, "Z_code")
        return LatentCase(case_id=0, kappa=ctx.kappa, phi=ctx.phase,
                          error_flag=ctx.error_flag, cause_rank=ctx.cause_rank,
                          base_option=ctx.base_option,
                          Z=tuple((zc >> i) & 1 for i in range(5)),
                          option_fault=b.get("P"), decision=b.get("D"),
                          controller=b.get("X"), plant=b.get("E"), trap=b.get("U"))

    def mech_primitives(case):
        """{cause: [Intervention, ...]} for the causes that have a primitive."""
        out: dict = {}
        if case.option_fault is not None:
            out["P"] = [Intervention.commit_identity()]
        if case.decision is not None:
            st = State(x=K.START[0], y=K.START[1], t=case.decision.t,
                       kappa=case.kappa, phi=case.phi)
            nominal = sol.best_action(st, case.base_option, 0)
            out["D"] = [Intervention.decision(case.decision.t, nominal)]
        if case.controller is not None:
            # ControllerFault carries (state, cmd, realized); the A7 single-cell
            # primitive is defined on the SITE the fault acted at.
            f = case.controller
            out["X"] = [Intervention.execution(ControllerSite(state=f.state,
                                                              cmd=f.cmd))]
        return out

    def outcome_after(case, members):
        try:
            tr = K.rollout(kappa=case.kappa, tape=case.tape(),
                           command_provider=provider, base_option=case.base_option,
                           mask=case.mask(), option_fault=case.option_fault,
                           interventions=InterventionSet(tuple(members)))
        except Exception:
            return None
        return tr.outcome

    def rescue_candidates(case, ftr):
        out = [("commit", (Intervention.commit_identity(),))]
        for zp in K.option_ids():
            if zp != case.base_option:
                out.append(("strategy", (Intervention.process(zp),)))
        for t in range(K.HORIZON):
            for a in range(len(K.ACTIONS)):
                out.append(("decision", (Intervention.decision(t, a),)))
        st = State(x=K.START[0], y=K.START[1], t=0, kappa=case.kappa, phi=case.phi)
        for s in ftr.steps:
            out.append(("execution", (Intervention.execution(
                ControllerSite(state=st, cmd=s.a_cmd)),)))
            st = s.state
        return out

    counts = Counter()
    mass = Counter()
    crosstab = Counter()
    ties_mech = Counter()
    ties_rescue = Counter()
    total_w = total_w_scanned = 0.0

    for wid in range(min(limit, len(sup))):
        w = sup.weight(wid)
        total_w += w
        total_w_scanned += 1
        case = rebuild(wid)
        fire = tuple((sup.field(wid, "fire_code") >> i) & 1 for i in range(5))
        ftr = None
        try:
            ftr = K.rollout(kappa=case.kappa, tape=case.tape(),
                            command_provider=provider,
                            base_option=case.base_option, mask=case.mask(),
                            option_fault=case.option_fault)
        except Exception:
            counts["malformed"] += 1
            continue

        prims = mech_primitives(case)
        fired_repairable = [k for k in REPAIRABLE
                            if fire[CAUSE_KEYS.index(k)] == 1 and k in prims]

        # reading (a): undo EVERY firing -> the union of that cause's primitives
        a_mech = tuple(iv for k in sorted(fired_repairable) for iv in prims[k])
        # reading (b): undo at least one firing per repairable fired cause
        per_cause_choices = [prims[k] for k in sorted(fired_repairable)]
        b_sizes = set()
        if per_cause_choices:
            for combo in itertools.product(*per_cause_choices):
                b_sizes.add(len(combo))
        counts["mech_a_size_%d" % len(a_mech)] += 1
        mass["mech_a_size_%d" % len(a_mech)] += w
        if b_sizes:
            bsz = min(b_sizes)
            counts["mech_b_size_%d" % bsz] += 1
            mass["mech_b_size_%d" % bsz] += w
        ties_mech[len(b_sizes)] += 1

        base_ok = ftr.outcome == Outcome.SUCCESS
        if base_ok:
            counts["rescue_size_0"] += 1
            mass["rescue_size_0"] += w
            best_rescue_kinds = {"none"}
            rescue_size = 0
        else:
            good = []
            for kind, mem in rescue_candidates(case, ftr):
                if outcome_after(case, mem) == Outcome.SUCCESS:
                    good.append(kind)
            ties_rescue[len(good)] += 1
            if good:
                rescue_size = 1
                counts["rescue_size_1"] += 1
                mass["rescue_size_1"] += w
                best_rescue_kinds = set(good)
            else:
                rescue_size = None
                counts["rescue_BOT"] += 1
                mass["rescue_BOT"] += w
                best_rescue_kinds = {"none"}

        # the cross-tab that A65 exists to expose
        has_mech = bool(a_mech)
        if has_mech and rescue_size == 0:
            crosstab["mech_present_and_already_succeeded"] += 1
        elif has_mech and "strategy" in (best_rescue_kinds or set()):
            crosstab["mech_present_and_strategy_also_rescues"] += 1
        elif has_mech and "commit" in (best_rescue_kinds or set()):
            crosstab["mech_present_and_commit_rescues"] += 1
        elif not has_mech and rescue_size == 1 and "strategy" in (
                best_rescue_kinds or set()):
            crosstab["NO_mech_but_strategy_rescues"] += 1

    # `counts` holds SEVERAL overlapping classifications (mech_a, mech_b, rescue),
    # so summing it double- and triple-counts worlds. Usable = scanned - malformed.
    n = int(total_w_scanned - counts["malformed"])
    # Whether the R^mech ambiguity (undo every firing vs undo at least one) is
    # currently vacuous: it is exactly when every repairable cause has a single
    # primitive, in which case readings (a) and (b) coincide.
    ambiguity_live = any(
        counts.get(f"mech_a_size_{k}", 0) != counts.get(f"mech_b_size_{k}", 0)
        for k in range(0, 6))
    print(f"A66 census on the first {limit:,} worlds "
          f"({total_w:.4f} of DGP mass, {n:,} usable)\n")
    print("R^mech, reading (a) undo EVERY firing / (b) undo at least one:")
    for k in sorted(counts):
        if k.startswith("mech_"):
            print(f"  {k:<22} count={counts[k]:>7}  mass={mass[k]:.5f}")
    print("\nR^rescue cardinality (0 = factual already succeeded):")
    for k in sorted(counts):
        if k.startswith("rescue_"):
            print(f"  {k:<22} count={counts[k]:>7}  mass={mass[k]:.5f}")
    print(f"\nties: #R^mech histogram {dict(ties_mech)}")
    print(f"      #R^rescue histogram {dict(ties_rescue)}")
    print(f"\nR^mech ambiguity (a) vs (b) is "
          f"{'LIVE' if ambiguity_live else 'VACUOUS on this slice'}"
          f"{'' if ambiguity_live else ': each repairable cause has a single primitive here'}")
    print("\ncross-tab (the A65 structure):")
    for k in sorted(crosstab):
        print(f"  {k:<40} {crosstab[k]}")

    out = {"limit": limit, "n_usable": n, "dgp_mass_scanned": total_w,
           "counts": dict(counts), "mass": dict(mass),
           "ties_mech": {str(k): v for k, v in ties_mech.items()},
           "ties_rescue": {str(k): v for k, v in ties_rescue.items()},
           "crosstab": dict(crosstab), "ambiguity_live": bool(ambiguity_live),
           "scope_note": f"FIRST {limit} worlds of the cache, not the full "
                         f"support; {total_w:.4f} of DGP mass. The full census is "
                         f"a separate run.",
           "ambiguity_reported_not_resolved": "R^mech has two readings (undo every "
                                               "firing vs undo at least one); both "
                                               "are reported so the choice is made "
                                               "in the open.",
           "gate_e_comparison": "Gate E's old PASS was under the pre-A65 ontology "
                                "and is a regression reference only."}
    path = ROOT / "experiments" / "v01r" / "a66_census.json"
    path.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(f"\nwrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
