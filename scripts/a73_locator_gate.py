r"""A72 §8.3 / A73 §60 — the 893/893 locator gate.

FOUR LAYERS, as frozen.

1. **Evaluator reference.** $\Gamma^+_{\text{eval}}(X)$, $\Gamma^-_{\text{eval}}(X)$
   and the reference world set $H_{\text{eval}}(X)$ are enumerated from the frozen
   ``DenseSupport`` plus the indexed truth, using A71's own projection.
2. **Method side.** $\hat\Gamma_{\text{CSL}}(X)$ is re-derived *only* from
   $X^{\text{loc}} = (\text{rows}, Z^{\text{fire}})$ through ``PublicSCMView``.
   The two sides use separately written projections, which is what makes the
   agreement evidence rather than a tautology.

   Main gate: ``893/893`` $\hat\Gamma_{\text{CSL}} = \Gamma^+_{\text{eval}}$
   **and** ``893/893`` $\Gamma^-_{\text{CSL}} = \Gamma^-_{\text{eval}}$, so neither
   the union nor the intersection can be implemented on only one side. A73's
   stronger exact-set form is checked too:
   $\{\Gamma^\ast(\tilde\ell) : \tilde\ell \in \mathcal C_{\text{SCM}}(X)\}
   = \{\Gamma^\ast(\ell) : \ell \in H_{\text{eval}}(X)\}$.
3. **Dependency audit.** ``causal_locator.py`` may not import ``support``, ``dgp``,
   ``belief``, ``gate_stage2`` or ``a71_indexed_truth``; its package imports are an
   allowlist.
4. **Mutation control.** Erasing the controller/plant mechanism boundary must make
   the gate fail. The failing classes are **recorded**, not merely counted: a
   mutation that failed somewhere unrelated would otherwise masquerade as a valid
   power test. The report names the failures, their overlap with A71's ambiguous
   classes, and whether the kill is attributable to the boundary being erased.

Read-only with respect to the frozen artifacts.
"""

from __future__ import annotations

import json
import pathlib
import sys
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from a73_public_scm_gate import audit_imports  # noqa: E402
from gate_stage2 import LatentCase, fire_of, reference_provider, sigma0  # noqa: E402
from identifiability_gate import CAUSE_KEYS  # noqa: E402
from rfl_rebuild.env import fault_grammar as FG  # noqa: E402
from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.env.kernel import (  # noqa: E402
    ControllerFault, PlantFault, Trap, DecisionOverride,
)
from rfl_rebuild.method.belief import fire_code  # noqa: E402
from rfl_rebuild.method.causal_locator import (  # noqa: E402
    BIT_D, BIT_E, BIT_X, CausalSetLocator, LocatorResult, XLoc,
)
from rfl_rebuild.method.public_scm import PublicSCMView  # noqa: E402
from rfl_rebuild.method.support import DenseSupport  # noqa: E402
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

CACHE = ROOT / "experiments" / "v01r" / "support_cache"
N_CLASSES = 893


# --------------------------------------------------------------------------- #
# evaluator-side reference (A71's projection, written independently of the view)
# --------------------------------------------------------------------------- #

def reference_gamma_star(case: LatentCase, fc: int) -> frozenset:
    out = set()
    if (fc >> 0) & 1:
        out.add("ProcessCommit")
    if (fc >> 1) & 1 and case.decision is not None:
        out.add(f"Decision_{case.decision.t}")
    if (fc >> 2) & 1 and case.controller is not None:
        f = case.controller
        out.add(f"ControllerSite_{f.state.x}_{f.state.y}_{f.state.t}_{f.cmd}")
    if (fc >> 3) & 1:
        out.add("ExternalPlant")
    if (fc >> 4) & 1:
        out.add("Unknown/NoWrite")
    return frozenset(out) if out else frozenset({"Unknown/NoWrite"})


# --------------------------------------------------------------------------- #
# layer 4: the mutation control
# --------------------------------------------------------------------------- #

class MergedControllerPlantView(PublicSCMView):
    """A72 §8.3: the controller/plant mechanism boundary is erased.

    A fired execution mechanism (``C_X``) is reported as the *plant* mechanism, so
    downstream the two kinds cannot be told apart. The learner-visible rows and the
    fire vector are untouched, so this mutates the mechanism boundary and nothing
    else.
    """

    def credit_unit(self, descriptor) -> str:  # type: ignore[override]
        if isinstance(descriptor, (ControllerFault, PlantFault)):
            return "ExternalPlant"
        return PublicSCMView.credit_unit(descriptor)


class GenericUnitView(PublicSCMView):
    """A71's own P0, replayed as a mutation control.

    The projection emits the generic **type** names ``Decision_t`` /
    ``ControllerSite`` instead of episode-local addresses. Intersecting those
    against concretely-expanded predictions yields the empty set, which is how the
    A70 census produced systematic false negatives. If the gate cannot kill this,
    the gate would not have caught the bug A71 exists to fix.
    """

    def credit_unit(self, descriptor) -> str:  # type: ignore[override]
        if isinstance(descriptor, DecisionOverride):
            return "Decision_t"
        if isinstance(descriptor, ControllerFault):
            return "ControllerSite"
        return PublicSCMView.credit_unit(descriptor)


# --------------------------------------------------------------------------- #
# shared comparison
# --------------------------------------------------------------------------- #

def evaluate(make_view, ref, rows_by_class, fire_by_class):
    """Run the locator over every class; return per-class agreement and failures."""
    locator = CausalSetLocator(make_view(ref))
    plus_bad, minus_bad, set_bad, empty = [], [], [], []
    n = 0
    for key, (rows, fc) in rows_by_class.items():
        n += 1
        try:
            res = locator.locate(XLoc(rows=rows, fire_code=fc))
        except Exception as exc:                    # EmptyCompatibleSet included
            empty.append((key, type(exc).__name__))
            continue
        e_plus, e_minus, e_set = fire_by_class[key]
        if res.gamma_plus != e_plus:
            plus_bad.append(key)
        if res.gamma_minus != e_minus:
            minus_bad.append(key)
        if res.units_set != e_set:
            set_bad.append(key)
    return {"n": n, "plus": plus_bad, "minus": minus_bad, "set": set_bad,
            "empty": empty}


def rebuild_case(sol, provider, sup, wid):
    r"""Reconstruct a support world as a replayable ``LatentCase`` plus its params.

    Module level so the corrected representation census can share it instead of
    keeping a second copy of the support-decoding logic.
    """
    kappa, phi = sup.field(wid, "kappa"), sup.field(wid, "phase")
    prop = sup.field(wid, "proposal")
    tape = PublicSCMView._tape(phi)
    healthy = K.rollout(kappa=kappa, tape=tape, command_provider=provider,
                        base_option=prop)
    doms = FG.canonical_domains(sol, kappa, tape, prop, healthy)
    idx = [sup.field(wid, f"p{i}") for i in range(5)]
    presence = [(sup.field(wid, "Z_code") >> i) & 1 for i in range(5)]
    b = FG.assign(doms, presence, idx)
    case = LatentCase(case_id=0, kappa=kappa, phi=phi,
                      error_flag=sup.field(wid, "error_flag"),
                      cause_rank=sup.field(wid, "cause_rank"),
                      base_option=prop, Z=tuple(presence),
                      option_fault=b.get("P"), decision=b.get("D"),
                      controller=b.get("X"), plant=b.get("E"),
                      trap=b.get("U"))
    return case, idx


def main() -> int:
    sol = solve_reference()
    provider = reference_provider(sol)
    sup = DenseSupport.load(CACHE, expected_kernel_fingerprint="full",
                            expected_dgp_fingerprint="full")

    # ---- layer 1: evaluator reference, one X per (block, fire) class ----- #
    rows_by_class: dict = {}
    fire_by_class: dict = {}
    truth_mass: dict = defaultdict(float)
    members: dict = defaultdict(set)
    for wid in range(len(sup)):
        key = (sup.field(wid, "block_id"), sup.field(wid, "fire_code"))
        members[key].add(wid)
        truth_mass[key] += sup.weight(wid)

    def rebuild(wid):
        return rebuild_case(sol, provider, sup, wid)

    truth_sets: dict = {}
    for key, wids in members.items():
        gammas = set()
        rows = None
        fc = None
        for wid in wids:
            case, _idx = rebuild(wid)
            if rows is None:
                sig, _err = sigma0(sol, case)
                rows = sig[0]
                fc = fire_code(fire_of(sol, case))
            gammas.add(reference_gamma_star(case, fc))
        rows_by_class[key] = (rows, fc)
        truth_sets[key] = frozenset(gammas)
        if len(gammas) == 1:
            minus = frozenset(next(iter(gammas)))
        else:
            minus = frozenset.intersection(*gammas)
        fire_by_class[key] = (frozenset().union(*gammas), minus,
                              frozenset(gammas))

    # ---- layer 2: the method side --------------------------------------- #
    clean = evaluate(PublicSCMView, sol, rows_by_class, fire_by_class)

    # ---- layer 3: dependency audit -------------------------------------- #
    loc = ROOT / "src" / "rfl_rebuild" / "method" / "causal_locator.py"
    bad, mods = audit_imports(loc)

    # ---- layer 4: mutation control -------------------------------------- #
    mutated = evaluate(MergedControllerPlantView, sol, rows_by_class, fire_by_class)
    killed = sorted(set(mutated["plus"]) | set(mutated["minus"]) | set(mutated["set"]))
    ambiguous = {k for k, v in truth_sets.items() if len(v) > 1}
    xe = {k: bool((k[1] >> BIT_X) & 1) or bool((k[1] >> BIT_E) & 1)
          for k in truth_sets}
    n_xe_classes = sum(1 for v in xe.values() if v)
    x_only = {k for k in truth_sets if (k[1] >> BIT_X) & 1}
    e_only = {k for k in truth_sets if (k[1] >> BIT_E) & 1}
    d_or_x = {k for k in truth_sets
              if ((k[1] >> BIT_D) & 1) or ((k[1] >> BIT_X) & 1)}
    killed_xe = [k for k in killed if xe[k]]
    killed_mixed = [k for k in killed if k in ambiguous]

    # second control: A71's own generic-unit P0 must also be killed
    generic = evaluate(GenericUnitView, sol, rows_by_class, fire_by_class)
    generic_killed = sorted(set(generic["plus"]) | set(generic["minus"])
                            | set(generic["set"]))

    checks = {
        "layer1_reference_covers_893_classes": clean["n"] == N_CLASSES,
        "main_gate_gamma_plus_893_of_893": not clean["plus"],
        "main_gate_gamma_minus_893_of_893": not clean["minus"],
        "exact_set_identity_893_of_893": not clean["set"],
        "no_empty_compatible_sets": not clean["empty"],
        "layer3_locator_import_allowlist_clean": not bad,
        "layer4_mutation_is_killed": bool(killed),
        "layer4_kill_touches_controller_plant_classes": bool(killed_xe),
        "layer4_kill_includes_A71_ambiguous_classes": bool(killed_mixed),
        "layer4_kill_is_exactly_the_controller_firing_classes":
            set(killed) == x_only,
        "layer4_kill_does_not_touch_plant_only_classes":
            not (set(killed) & (e_only - x_only)),
        "layer4_second_control_kills_A71_generic_unit_P0": bool(generic_killed),
        "layer4_second_control_kill_is_exactly_the_D_or_X_classes":
            set(generic_killed) == d_or_x,
    }
    ok = all(checks.values())

    print("A73 locator gate — 893/893\n")
    print(f"  layer 1  classes with an evaluator reference : {clean['n']}")
    print(f"  layer 2  Gamma^+ mismatches                  : {len(clean['plus'])}")
    print(f"           Gamma^- mismatches                  : {len(clean['minus'])}")
    print(f"           exact Gamma* set mismatches         : {len(clean['set'])}")
    print(f"           empty compatible sets               : {len(clean['empty'])}")
    print(f"  layer 3  locator imports                     : {mods}")
    print(f"           disallowed                           : {bad}")
    print(f"  layer 4  X-firing classes in total           : {len(x_only)}")
    print(f"           E-firing classes in total           : {len(e_only)}")
    print(f"           X-or-E-firing classes in total      : {n_xe_classes}")
    print(f"           mutated-view killed classes          : {len(killed)}")
    print(f"           kill set == X-firing classes exactly : "
          f"{set(killed) == x_only}")
    print(f"           ...A71-ambiguous classes killed      : {len(killed_mixed)}"
          f" / {len(ambiguous)}")
    print(f"           second control (A71 generic units)   : "
          f"{len(generic_killed)} killed, == D-or-X classes: "
          f"{set(generic_killed) == d_or_x}")
    for name, cond in checks.items():
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if killed_mixed:
        print(f"\n  A71 ambiguous classes killed by the mutation (first 8):")
        for k in killed_mixed[:8]:
            print(f"    block={k[0]} fire={k[1]:05b} "
                  f"Gamma* options={len(truth_sets[k])}")

    verdict = ("exact SCM set inversion confirmed at 893/893, and the "
               "controller/plant boundary mutation is killed"
               if ok else "gate not satisfied")
    print(f"\nA73 locator gate: {verdict}")

    out = ROOT / "experiments" / "v02r" / "a73_locator_gate.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "n_classes": clean["n"],
        "gamma_plus_mismatches": len(clean["plus"]),
        "gamma_minus_mismatches": len(clean["minus"]),
        "exact_set_mismatches": len(clean["set"]),
        "empty_compatible_sets": len(clean["empty"]),
        "locator_imports": mods,
        "locator_disallowed_imports": bad,
        "mutation_killed_classes": len(killed),
        "mutation_killed_with_x_or_e": len(killed_xe),
        "x_firing_classes_total": len(x_only),
        "e_firing_classes_total": len(e_only),
        "x_or_e_firing_classes_total": n_xe_classes,
        "mutation_kill_set_equals_x_firing_classes": set(killed) == x_only,
        "mutation_killed_all_have_x_or_e":
            len(killed_xe) == len(killed) and bool(killed),
        "mutation_killed_among_A71_ambiguous": len(killed_mixed),
        "A71_ambiguous_classes": len(ambiguous),
        "second_control_generic_unit_killed_classes": len(generic_killed),
        "mutation_killed_class_list": [f"{k[0]}:{k[1]:05b}" for k in killed],
        "mutation_killed_A71_ambiguous_list": [f"{k[0]}:{k[1]:05b}"
                                               for k in killed_mixed],
        "checks": checks,
        "status": "PASS" if ok else "FAIL",
        "verdict": verdict,
        "mutation": ("MergedControllerPlantView reports a fired execution "
                     "mechanism C_X as the plant mechanism, erasing the "
                     "controller/plant boundary; rows and the fire vector are "
                     "untouched"),
    }, indent=1, default=str), encoding="utf-8")
    print(f"wrote {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
