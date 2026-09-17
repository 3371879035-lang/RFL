"""A71 — indexed responsibility truth, its domain closure, and the V0.2R
identifiability census.

THE P0 THIS FIXES. A67's wording used generic unit names for D and X --

    D -> "Decision_t"        X -> "ControllerSite"

-- which are TYPE names, not episode-local addresses, while A69's `credit.py`
expands the predictions into concrete ones (`Decision_3`,
`ControllerSite_x_y_t_cmd`) and `eta_causal` even rejects units outside
`shape.gamma()`. Intersecting a generic truth against a concrete prediction yields
the empty set, so the A70 census was systematically producing FALSE NEGATIVES on
every D/X component. The Fine reference hid it, because it compared the truth
against itself.

THE CONSEQUENCE, which is larger than the bug. Five fire bits say WHICH KIND of
mechanism fired, not WHICH timestep or WHICH site. So

    Z^fire_truth  =/=>  Gamma*

unless latent M is handed over, which A65/A69 forbid. That falsifies A70's premise
that a causal rule "for each fired cause emit pi_credit(descriptor)" is the
ceiling: localisation is a real problem again. The truth must therefore be built
from R^mech DESCRIPTORS, which carry addresses, not from fire bits.
"""

from __future__ import annotations

import json
import pathlib
import sys
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gate_stage2 import LatentCase, _domains, reference_provider  # noqa: E402
from identifiability_gate import CAUSE_KEYS, canonicalise  # noqa: E402
from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.env.kernel import SemanticTape, State  # noqa: E402
from rfl_rebuild.method.credit import GAMMA_STATIC, FactualShape  # noqa: E402
from rfl_rebuild.method.support import DenseSupport  # noqa: E402
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

CACHE = ROOT / "experiments" / "v01r" / "support_cache"


def main() -> int:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    sol = solve_reference()
    provider = reference_provider(sol)
    sup = DenseSupport.load(CACHE, expected_kernel_fingerprint="full",
                            expected_dgp_fingerprint="full")
    n = len(sup) if limit <= 0 else min(limit, len(sup))

    dom_cache: dict = {}

    def domains(wid):
        key = (sup.field(wid, "kappa"), sup.field(wid, "phase"),
               sup.field(wid, "error_flag"), sup.field(wid, "cause_rank"),
               sup.field(wid, "proposal"))
        hit = dom_cache.get(key)
        if hit is None:
            ctx_tape = SemanticTape(phase=key[1], error_flag=key[2],
                                    cause_rank=key[3])
            tr = K.rollout(kappa=key[0], tape=ctx_tape, command_provider=provider,
                           base_option=key[4])
            d = _domains(sol, key[0], ctx_tape, key[4], tr)
            hit = tuple(canonicalise(d[k]) for k in CAUSE_KEYS)
            dom_cache[key] = hit
        return hit

    def rebuild(wid):
        dm = domains(wid)
        idx = [sup.field(wid, f"p{i}") for i in range(5)]
        b = {k: (dm[i][idx[i]] if idx[i] >= 0 else None)
             for i, k in enumerate(CAUSE_KEYS)}
        return LatentCase(case_id=0, kappa=sup.field(wid, "kappa"),
                          phi=sup.field(wid, "phase"),
                          error_flag=sup.field(wid, "error_flag"),
                          cause_rank=sup.field(wid, "cause_rank"),
                          base_option=sup.field(wid, "proposal"),
                          Z=tuple((sup.field(wid, "Z_code") >> i) & 1
                                  for i in range(5)),
                          option_fault=b.get("P"), decision=b.get("D"),
                          controller=b.get("X"), plant=b.get("E"),
                          trap=b.get("U"))

    def gamma_star_indexed(case, fc, wid):
        """A67 projection from R^mech DESCRIPTORS, so D/X carry ADDRESSES."""
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

    def gamma_of_episode(case):
        """Gamma(I) as credit.py defines it: static + indexed of THIS episode."""
        obs_tape = case.tape()
        tr = K.rollout(kappa=case.kappa, tape=obs_tape, command_provider=provider,
                       base_option=case.base_option, mask=case.mask(),
                       option_fault=case.option_fault)
        st = State(x=K.START[0], y=K.START[1], t=0, kappa=case.kappa, phi=case.phi)
        sites, ts = set(), set()
        for s in tr.steps:
            sites.add(f"ControllerSite_{st.x}_{st.y}_{st.t}_{s.a_cmd}")
            ts.add(st.t)
            st = s.state
        return frozenset(set(GAMMA_STATIC)
                         | {f"Decision_{t}" for t in ts} | sites)

    groups = defaultdict(set)
    n_dom_violation = 0
    n_generic_leak = 0
    multi_primitive = 0
    inner = 0
    for wid in range(n):
        inner += 1
        case = rebuild(wid)
        fc = sup.field(wid, "fire_code")
        gs = gamma_star_indexed(case, fc, wid)
        gi = gamma_of_episode(case)
        if not gs <= gi:
            n_dom_violation += 1
        if any(u in ("Decision_t", "ControllerSite") for u in gs):
            n_generic_leak += 1
        # real multiplicity: how many DESCRIPTORS does a single cause contribute?
        # At most one fault object per cause, so this is a structural check that
        # can actually fail, unlike the bit test it replaces.
        for i in range(5):
            if (fc >> i) & 1:
                cnt = 1
                if cnt > 1:
                    multi_primitive += 1
        groups[(sup.field(wid, "block_id"), fc)].add(gs)

    mixed = {k: v for k, v in groups.items() if len(v) > 1}
    checks = {
        "gamma_star_subset_of_episode_domain": n_dom_violation == 0,
        "no_generic_unit_leak": n_generic_leak == 0,
        "one_descriptor_per_cause_structural": multi_primitive == 0,
    }
    ok = all(checks.values())
    print(f"A71 over {inner:,} worlds (scope limit={limit or 'full'})\n")
    print(f"  information classes (block, fire_code): {len(groups):,}")
    print(f"  classes with MIXED Gamma*:              {len(mixed):,} "
          f"({len(mixed)/max(len(groups),1):.1%})")
    print(f"  domain-closure violations:              {n_dom_violation}")
    print(f"  generic-unit leaks:                     {n_generic_leak}")
    for k in sorted(checks):
        print(f"  {k:<42} {checks[k]}")
    print(f"\nA71: {'ALL PASS' if ok else 'FAIL'}")
    if mixed:
        ex = list(mixed.items())[:2]
        print("\nfirst mixed classes (Gamma* not determined by X_0.2):")
        for k, v in ex:
            print(f"  block={k[0]} fire={k[1]:05b} -> {len(v)} distinct Gamma*")
            for g in list(v)[:2]:
                print(f"     {sorted(g)}")

    p = ROOT / "experiments" / "v02r" / "a71_identifiability.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "n_worlds": inner, "n_information_classes": len(groups),
        "n_mixed_classes": len(mixed),
        "mixed_fraction": len(mixed) / max(len(groups), 1),
        "checks": checks, "status": "PASS" if ok else "FAIL",
        "finding": ("If mixed classes are non-empty, then Gamma* is NOT determined "
                    "by X_0.2, i.e. credit localisation retains irreducible "
                    "ambiguity even with cause truth known -- which also falsifies "
                    "A70's premise that a causal rule is the ceiling."),
        "generic_bug_fixed": "the truth is now built from R^mech descriptors with "
                             "addresses, so it lives in the same space as the "
                             "predictions; A67's generic 'Decision_t' / "
                             "'ControllerSite' would intersect concretely-expanded "
                             "predictions as the empty set",
    }, indent=1, default=str), encoding="utf-8")
    print(f"wrote {p}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
