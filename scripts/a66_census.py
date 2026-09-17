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
# A67: pi_credit, frozen. Mechanism-repair DESCRIPTOR -> credit unit. P/D/X have
# executable agent interventions; E and U have structural descriptors with no
# agent write, which is the only way ExternalPlant and Unknown/NoWrite can enter
# Gamma* at all.
GAMMA_OF_DESCRIPTOR = {
    "commit": "ProcessCommit",
    "decision": "Decision_t",
    "execution": "ControllerSite",
    "external_plant": "ExternalPlant",
    "unknown_terminal": "Unknown/NoWrite",
}
AGENT_WRITEABLE = {"ProcessCommit": True, "Decision_t": True,
                   "ControllerSite": True, "ExternalPlant": False,
                   "Unknown/NoWrite": False}


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

    def mech_primitives(case, ftr, fire):
        """{cause: [mechanism-repair descriptor]} for causes that have one.

        A67: R^mech is a set of mechanism-repair DESCRIPTORS, not only executable
        agent interventions. P/D/X have executable ones; E and U have structural
        descriptors with no agent write, which is how ExternalPlant and
        Unknown/NoWrite can ever enter Gamma* at all.
        """
        out: dict = {}
        # A67 basis: FIRED mechanisms. An earlier version gated P/D/X/E on fault
        # PRESENCE (`case.option_fault is not None` etc.) and U on FIRE, which is
        # inconsistent and materially different -- a67_structural.json measures
        # 1,541,400 (world, cause) pairs where presence differs from fire, because
        # A54 showed dormant faults are common. There is nothing to repair in a
        # mechanism that never executed.
        if fire[CAUSE_KEYS.index("P")] == 1:
            out["P"] = [("commit", Intervention.commit_identity())]
        if fire[CAUSE_KEYS.index("D")] == 1:
            # The override's nominal action is pi*(s_t, z_t, m_t) at the FACTUAL
            # pre-action state of time t. An earlier version used START, the
            # proposal option and m=0 -- all three are lookup keys of pi_D*, so
            # that produced the wrong nominal action for every later override.
            nominal = _override_nominal(case, ftr)
            if nominal is not None:
                out["D"] = [("decision",
                             Intervention.decision(case.decision.t, nominal))]
        if fire[CAUSE_KEYS.index("X")] == 1:
            f = case.controller
            out["X"] = [("execution", Intervention.execution(
                ControllerSite(state=f.state, cmd=f.cmd)))]
        if fire[CAUSE_KEYS.index("E")] == 1:
            out["E"] = [("external_plant", None)]     # non-agent descriptor
        if fire[CAUSE_KEYS.index("U")] == 1:
            out["U"] = [("unknown_terminal", None)]   # non-agent descriptor
        return out

    def _override_nominal(case, ftr):
        """pi*(s_t, z_t, m_t) at the factual pre-action state of the override."""
        st = State(x=K.START[0], y=K.START[1], t=0, kappa=case.kappa, phi=case.phi)
        ctrl = K.initial_control(ftr.option_in_force)
        for res in ftr.steps:
            if st.t == case.decision.t:
                return sol.best_action(st, ctrl.z, ctrl.m)
            st, ctrl = res.state, res.control
        return None

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
    ambiguity_live = False
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

        prims = mech_primitives(case, ftr, fire)
        fired_repaired = [k for k in CAUSE_KEYS
                          if fire[CAUSE_KEYS.index(k)] == 1 and k in prims]

        # reading (a): undo EVERY firing -> all descriptors of those causes
        a_kinds = tuple(kind for k in fired_repaired
                        for kind, _iv in prims[k])
        # reading (b): undo at least one firing per fired repairable cause
        per_cause_choices = [prims[k] for k in fired_repaired]
        b_sizes = set()
        if per_cause_choices:
            for combo in itertools.product(*per_cause_choices):
                b_sizes.add(len(combo))
        counts["mech_a_size_%d" % len(a_kinds)] += 1
        mass["mech_a_size_%d" % len(a_kinds)] += w
        for kind in a_kinds:
            counts[f"mech_kind_{kind}"] += 1
        if b_sizes:
            bsz = min(b_sizes)
            counts["mech_b_size_%d" % bsz] += 1
            mass["mech_b_size_%d" % bsz] += w
            if bsz != len(a_kinds):
                ambiguity_live = True
        ties_mech[len(b_sizes)] += 1
        # A67 structural check: <=1 mechanism primitive per cause per world
        if max((len(prims[k]) for k in prims), default=0) > 1:
            counts["mech_multi_primitive_per_cause"] += 1

        # A67: the projection, frozen. E and U enter Gamma* INDEPENDENTLY of any
        # rescue -- that is the whole point of separating them from Unknown.
        gamma_star = []
        for k in fired_repaired:
            for kind, _iv in prims[k]:
                gamma_star.append(GAMMA_OF_DESCRIPTOR[kind])
        if not gamma_star:
            gamma_star = ["Unknown/NoWrite"]      # NoWrite, not "we don't know"
        crosstab["gamma_star_" + "|".join(sorted(set(gamma_star)))] += 1

        base_ok = ftr.outcome == Outcome.SUCCESS
        if base_ok:
            counts["rescue_size_0"] += 1
            mass["rescue_size_0"] += w
            best_rescue_kinds = {"none"}
            rescue_size = 0
        else:
            # P0-2: a singleton miss is NOT bottom. Enumerate pairs, then
            # triples, before concluding anything -- Gate E's old singleton
            # result is a regression reference, not an inherited theorem.
            cands = rescue_candidates(case, ftr)
            good, found_size = [], None
            for size in (1, 2, 3):
                for combo in itertools.combinations(cands, size):
                    nodes = [iv.node() for _kd, mem in combo for iv in mem]
                    if len(nodes) != len(set(nodes)):
                        continue
                    mem = tuple(iv for _kd, mm in combo for iv in mm)
                    if outcome_after(case, mem) == Outcome.SUCCESS:
                        good.append(combo)
                if good:
                    found_size = size
                    break
            ties_rescue[len(good)] += 1
            if good:
                rescue_size = found_size
                counts[f"rescue_size_{found_size}"] += 1
                mass[f"rescue_size_{found_size}"] += w
                best_rescue_kinds = {kd for combo in good for kd, _m in combo}
            else:
                rescue_size = None
                counts["rescue_UNRESOLVED_GT3"] += 1
                mass["rescue_UNRESOLVED_GT3"] += w
                best_rescue_kinds = {"none"}

        # the cross-tab that A65 exists to expose
        has_mech = bool(a_kinds)
        has_strategy_rescue = "strategy" in (best_rescue_kinds or set())
        if has_mech and rescue_size == 0:
            crosstab["mech_present_and_already_succeeded"] += 1
        elif has_mech and has_strategy_rescue:
            crosstab["mech_present_and_strategy_also_rescues"] += 1
        elif has_mech and "commit" in (best_rescue_kinds or set()):
            crosstab["mech_present_and_commit_rescues"] += 1
        elif not has_mech and has_strategy_rescue:
            crosstab["NO_mech_but_strategy_rescues"] += 1
        if has_strategy_rescue and "ExternalPlant" in gamma_star:
            crosstab["PLANT_FAULT_and_strategy_rescues_truth_still_ExternalPlant"] += 1

    # `counts` holds SEVERAL overlapping classifications (mech_a, mech_b, rescue),
    # so summing it double- and triple-counts worlds. Usable = scanned - malformed.
    n = int(total_w_scanned - counts["malformed"])
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
