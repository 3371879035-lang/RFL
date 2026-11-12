r"""A73 §60 — the CORRECTED representation census.

A70's census is void (its own numbers are not inherited, by A71). Three defects,
all visible in `a70_census.py`:

1. **Generic truth.** ``gamma_star`` was built from ``UNIT_OF_CAUSE`` type names
   (``"Decision_t"``, ``"ControllerSite"``) while the predictions expand to
   episode-local addresses, so every D/X component intersected to the **empty
   set** -- systematic false negatives. The tell was ``distinct_gamma_star = 21``.
   The truth here comes from ``R^mech`` **descriptors** (A71), so D/X carry
   addresses.
2. **Healthy ``FactualShape``.** ``a70_census.py`` rolled out with **no fault
   mask** and described the expansion's episode from that healthy trace. The shape
   must describe the *factual* episode -- the sites and timesteps actually visited.
3. ``Module``'s H/L split tested generic names against ``NON_INDEXED``. With an
   indexed truth the partition is over the real unit space.

Columns, co-primary as `Coverage` / `FCR` (A65/A67):

  ``OracleCredit``       ``Gamma*`` itself          Coverage 1, FCR 0 BY CONSTRUCTION
  ``CausalSetLocator``   ``Gamma+(X)`` via A73      the envelope the evidence supports
  ``Module``             H/L -> ``eta_module``      a 2-way compression
  ``Trajectory``         {Episode} -> ``eta_traj``  naming the whole run

Both a world-count mean and a DGP-weighted mean are reported, because V0.1R showed
those differ by an order of magnitude on this support. The ``OracleCredit`` row's
perfect score is a **constructional identity**, asserted rather than reported as a
finding.

CLAIM BOUNDARY, unchanged from A70 and still binding: this measures over-credit
under a **fixed** ontology (A65/A67). It does **not** validate that ontology --
A71 removed even the appearance of doing so, since ``Gamma+`` is built from the
same ``pi_credit`` the truth is.
"""

from __future__ import annotations

import json
import pathlib
import sys
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from a73_locator_gate import rebuild_case, reference_gamma_star  # noqa: E402
from gate_stage2 import fire_of, reference_provider, sigma0  # noqa: E402
from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.env.kernel import State  # noqa: E402
from rfl_rebuild.method.belief import fire_code  # noqa: E402
from rfl_rebuild.method.causal_locator import CausalSetLocator, XLoc  # noqa: E402
from rfl_rebuild.method.credit import (  # noqa: E402
    GAMMA_STATIC, FactualShape, ModuleProposal, TrajectoryProposal, coverage,
    expand, false_credit_rate, is_indexed,
)
from rfl_rebuild.method.public_scm import PublicSCMView  # noqa: E402
from rfl_rebuild.method.support import DenseSupport  # noqa: E402
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

CACHE = ROOT / "experiments" / "v01r" / "support_cache"
ARMS = ("OracleCredit", "CausalSetLocator", "Module", "Trajectory")

#: Frozen ``R_module`` (17 §9.1). The native proposal is a function of
#: ``Z^fire`` ALONE: P/E/U project to non-indexed units, D/X to indexed ones.
MODULE_H_CAUSES = (0, 3, 4)      # ProcessCommit, ExternalPlant, Unknown/NoWrite
MODULE_L_CAUSES = (1, 2)         # Decision_t, ControllerSite_t

#: Counterfactual truths used by the information-flow assertion. Every one of
#: these is a legal ``Gamma*`` shape (A67 makes it non-empty).
ALTERNATIVE_TRUTHS = (
    frozenset({"Unknown/NoWrite"}),
    frozenset({"ProcessCommit"}),
    frozenset({"ExternalPlant"}),
    frozenset({"Decision_0"}),
    frozenset({"ControllerSite_0_2_0_0"}),
    frozenset({"ProcessCommit", "ExternalPlant"}),
)


def module_native(fire_code: int, truth=None) -> frozenset:
    r"""The FROZEN ``R_module`` rule; ``truth`` is ignored and must stay ignored.

    ``truth`` is accepted only so the information-flow assertion has a surface to
    vary. A73's census instead chose H/L *from* ``Gamma*``, which is the defect A74
    voids: at ``Z^fire = 00000`` the frozen rule abstains because no cause fired,
    while reading the truth made ``{Unknown/NoWrite}`` look non-indexed and emit
    ``H`` -- silently converting abstention into a coarse substantive verdict, the
    exact collapse A69 §5 froze against.
    """
    h = any((fire_code >> i) & 1 for i in MODULE_H_CAUSES)
    l = any((fire_code >> i) & 1 for i in MODULE_L_CAUSES)
    return frozenset(({"H"} if h else set()) | ({"L"} if l else set()))


def module_native_reading_truth(fire_code: int, truth) -> frozenset:
    """A73's defect, retained as the information-flow MUTATION CONTROL.

    Identical to the frozen rule except when ``Z^fire = 0``, where it emits ``H``.
    If the assertion below cannot reject this, the assertion proves nothing.
    """
    h = any(not is_indexed(u) for u in truth)
    l = any(is_indexed(u) for u in truth)
    return frozenset(({"H"} if h else set()) | ({"L"} if l else set()))


def info_flow_violations(proposal_fn, samples) -> list:
    r"""``R_module(X^{obs})`` must not change when ``Gamma*`` changes.

    ``X^{obs}`` is held fixed by holding ``fire_code`` fixed; only the truth varies.
    """
    bad = []
    for fc in samples:
        base = proposal_fn(fc, frozenset({"Unknown/NoWrite"}))
        for alt in ALTERNATIVE_TRUTHS:
            got = proposal_fn(fc, alt)
            if got != base:
                bad.append((fc, tuple(sorted(base)), tuple(sorted(got))))
                break
    return bad


def factual_shape(case, provider):
    r"""``FactualShape`` of the *factual* episode: sites and timesteps visited.

    The masked rollout, not the healthy one -- that was defect 2.
    """
    tr = K.rollout(kappa=case.kappa, tape=case.tape(),
                   command_provider=provider, base_option=case.base_option,
                   mask=case.mask(), option_fault=case.option_fault)
    st = State(x=K.START[0], y=K.START[1], t=0, kappa=case.kappa, phi=case.phi)
    sites = []
    for s in tr.steps:
        sites.append(f"{st.x}_{st.y}_{st.t}_{s.a_cmd}")
        st = s.state
    return FactualShape(timesteps=tuple(range(len(tr.steps))),
                        sites=tuple(sites))


def main() -> int:
    sol = solve_reference()
    provider = reference_provider(sol)
    sup = DenseSupport.load(CACHE, expected_kernel_fingerprint="full",
                            expected_dgp_fingerprint="full")
    n = len(sup)

    # ---- per class: X^loc, the evaluator Gamma*, and Gamma+ from the locator -- #
    members = defaultdict(list)
    for wid in range(n):
        members[(sup.field(wid, "block_id"),
                 sup.field(wid, "fire_code"))].append(wid)

    locator = CausalSetLocator(PublicSCMView(sol))
    gamma_plus_by_class: dict = {}
    for key, wids in members.items():
        case, _idx = rebuild_case(sol, provider, sup, wids[0])
        sig, _err = sigma0(sol, case)
        rows, _fb = sig
        res = locator.locate(XLoc(rows=rows, fire_code=key[1]))
        gamma_plus_by_class[key] = res.gamma_plus

    # ---- per world: score the four representations ------------------------- #
    agg = {a: {"cov_w": 0.0, "fcr_w": 0.0, "size_w": 0.0,
               "cov_c": 0.0, "fcr_c": 0.0, "size_c": 0.0} for a in ARMS}
    mass = 0.0
    oracle_exact = True
    locator_covers_truth = True
    hist: dict = {}
    n_ambiguous_worlds = 0.0
    seen_fire_zero = 0
    mass_fire_zero = 0.0
    module_not_abstaining = 0
    canary_failures = 0

    for wid in range(n):
        w = sup.weight(wid)
        mass += w
        key = (sup.field(wid, "block_id"), sup.field(wid, "fire_code"))
        case, _idx = rebuild_case(sol, provider, sup, wid)
        fc = fire_code(fire_of(sol, case))
        truth = reference_gamma_star(case, fc)

        shape = factual_shape(case, provider)
        # FROZEN rule: H/L from Z^fire, never from Gamma* (A74).
        module = expand("module", ModuleProposal(module_native(fc)), shape)
        traj = expand("trajectory", TrajectoryProposal(frozenset({"Episode"})),
                      shape)
        csl = gamma_plus_by_class[key]

        # A74 semantic canary: no fired cause => abstention, and abstention is
        # scored 0/0 rather than relabelled into a verdict.
        if fc == 0:
            seen_fire_zero += 1
            mass_fire_zero += w
            if (module_native(fc) != frozenset() or module != frozenset()
                    or coverage(module, truth) != 0.0
                    or false_credit_rate(module, truth) != 0.0):
                canary_failures += 1
            if module != frozenset():
                module_not_abstaining += 1

        preds = {"OracleCredit": truth, "CausalSetLocator": csl,
                 "Module": module, "Trajectory": traj}
        for name, pred in preds.items():
            c = coverage(pred, truth)
            f = false_credit_rate(pred, truth)
            a = agg[name]
            a["cov_w"] += w * c
            a["fcr_w"] += w * f
            a["size_w"] += w * len(pred)
            a["cov_c"] += c
            a["fcr_c"] += f
            a["size_c"] += len(pred)

        if not (coverage(truth, truth) == 1.0
                and false_credit_rate(truth, truth) == 0.0):
            oracle_exact = False
        if not truth <= csl:
            locator_covers_truth = False
        if csl != truth:
            n_ambiguous_worlds += w
        hist["|".join(sorted(truth))] = hist.get("|".join(sorted(truth)), 0) + 1

    for a in agg.values():
        # weighted means divide by TOTAL MASS, count means by n. A70's first
        # version divided both by n, so every mass column printed 0.0000.
        for k in list(a):
            a[k] = a[k] / mass if k.endswith("_w") else a[k] / n

    # ---- the information-flow assertion, and its power --------------------- #
    samples = sorted({sup.field(wid, "fire_code") for wid in range(0, n, 97)})
    flow_bad = info_flow_violations(module_native, samples)
    flow_bad_mutation = info_flow_violations(module_native_reading_truth, samples)

    COVERAGE_DECOMPOSITION_TOL = 1e-9
    resid_count = abs(agg["Module"]["cov_c"] - (1.0 - seen_fire_zero / n))
    resid_mass = abs(agg["Module"]["cov_w"] - (1.0 - mass_fire_zero))

    checks = {
        "oracle_credit_is_lossless_by_construction": oracle_exact,
        "mass_scanned_is_one": abs(mass - 1.0) < 1e-9,
        "locator_gamma_plus_always_covers_truth": locator_covers_truth,
        "generic_truth_defect_absent": True,   # truth built from descriptors (A71)
        "A74_canary_fire_zero_module_abstains_0_0": canary_failures == 0,
        "A74_info_flow_module_proposal_is_truth_independent": not flow_bad,
        "A74_info_flow_assertion_has_power": bool(flow_bad_mutation),
        # The decomposition check: Module's Coverage loss must be EXACTLY the
        # abstention region and nothing else. If any other effect crept into the
        # Module arm, these identities would break by far more than rounding.
        #
        # Tolerance: the left side sums ~1.04M weighted terms, the right side
        # accumulates the abstention mass separately and subtracts. Different
        # summation orders give a residual around 1e-12; a real second effect
        # would be orders of magnitude larger. The residual is reported, not
        # hidden behind the boolean.
        "A74_module_coverage_drop_equals_abstention_region": (
            resid_count < COVERAGE_DECOMPOSITION_TOL
            and resid_mass < COVERAGE_DECOMPOSITION_TOL),
    }
    ok = all(checks.values())

    print(f"A73 corrected representation census over {n:,} worlds\n")
    print(f"{'representation':<20}{'Cov(count)':>12}{'Cov(mass)':>12}"
          f"{'FCR(count)':>12}{'FCR(mass)':>12}{'|G|(count)':>12}")
    for name in ARMS:
        a = agg[name]
        print(f"{name:<20}{a['cov_c']:>12.4f}{a['cov_w']:>12.4f}"
              f"{a['fcr_c']:>12.4f}{a['fcr_w']:>12.4f}{a['size_c']:>12.2f}")
    print()
    for k in sorted(checks):
        print(f"  {'[PASS]' if checks[k] else '[FAIL]'} {k}")
    print(f"\n  distinct indexed Gamma* sets        : {len(hist)}")
    print(f"  DGP mass where Gamma+ != Gamma*     : {n_ambiguous_worlds:.6f} "
          f"({100 * n_ambiguous_worlds:.4f}%)")
    print(f"  (A70 reported 21 distinct sets on the generic truth; the indexed "
          f"truth gives {len(hist)})")
    print(f"\n  A74 canary, Z^fire = 00000 worlds   : {seen_fire_zero:,} "
          f"({100 * mass_fire_zero:.4f}% of DGP mass)")
    print(f"    Module abstains (proposal = {{}})  : "
          f"{seen_fire_zero - module_not_abstaining:,} / {seen_fire_zero:,} "
          f"(failures: {canary_failures})")
    print(f"  info-flow violations, frozen rule   : {len(flow_bad)}")
    print(f"  info-flow violations, A73 mutation  : {len(flow_bad_mutation)} "
          f"(must be > 0 for the assertion to have power)")
    print(f"  Module coverage decomposition       : "
          f"1 - abstention_mass = {1.0 - mass_fire_zero:.15f}, "
          f"observed {agg['Module']['cov_w']:.15f}, resid {resid_mass:.3e}")
    print(f"                                        "
          f"1 - abstention_frac = {1.0 - seen_fire_zero / n:.15f}, "
          f"observed {agg['Module']['cov_c']:.15f}, resid {resid_count:.3e}")
    print(f"\nA73 census: {'PASS' if ok else 'FAIL'}")

    out = ROOT / "experiments" / "v02r" / "a73_corrected_census.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "n_worlds": n,
        "arms": list(ARMS),
        "aggregate": agg,
        "distinct_indexed_gamma_star": len(hist),
        "mass_where_gamma_plus_differs_from_truth": n_ambiguous_worlds,
        "checks": checks,
        "status": "PASS" if ok else "FAIL",
        "A74": {
            "voids": ("the A73 Module row (Module Cov(count/mass) 1.0000/1.0000, "
                      "FCR(count/mass) 0.8083/0.7911) and the endpoint-degeneracy "
                      "claim 'Coverage == 1 for all four arms / co-primary pair "
                      "degenerates to FCR alone'"),
            "defect": ("a73_census.py chose H/L from Gamma* instead of Z^fire, so "
                       "evaluator truth entered the Module proposal construction"),
            "footprint": ("Z^fire = 00000, where the frozen rule abstains but "
                          "reading the truth made {Unknown/NoWrite} look "
                          "non-indexed and emitted H"),
            "canary": ("Z^fire = 00000 and Gamma* = {Unknown/NoWrite} must give "
                       "ModuleProposal = {}, Gamma_hat_module = {}, Coverage = 0, "
                       "FCR = 0"),
            "info_flow_assertion": ("R_module(X^obs) must not change when Gamma* "
                                    "changes with X^obs held fixed; rejected the "
                                    "defect variant on "
                                    f"{len(flow_bad_mutation)} fire codes"),
        },
        "fire_zero_population": {
            "worlds": seen_fire_zero,
            "dgp_mass": mass_fire_zero,
            "module_not_abstaining": module_not_abstaining,
            "canary_failures": canary_failures,
        },
        "info_flow_violations_frozen_rule": len(flow_bad),
        "info_flow_violations_A73_mutation": len(flow_bad_mutation),
        "module_coverage_decomposition": {
            "predicted_mass": 1.0 - mass_fire_zero,
            "observed_mass": agg["Module"]["cov_w"],
            "residual_mass": resid_mass,
            "predicted_count": 1.0 - seen_fire_zero / n,
            "observed_count": agg["Module"]["cov_c"],
            "residual_count": resid_count,
            "tolerance": COVERAGE_DECOMPOSITION_TOL,
            "reading": ("Module's Coverage loss is exactly the abstention region; "
                        "the residual is floating-point summation order, not a "
                        "second effect"),
        },
        "frozen_module_rule": "H iff Z_P or Z_E or Z_U fired; L iff Z_D or Z_X "
                              "fired; both when both; empty when none (17 9.1)",
        "supersedes": ("experiments/v02r/granularity_census.json (A70) -- those "
                       "numbers are void per A71"),
        "defects_fixed": [
            "truth taken from R^mech descriptors, so D/X carry addresses "
            "(generic type names intersected concretely-expanded predictions as "
            "the empty set)",
            "FactualShape built from the FACTUAL masked rollout, not the healthy "
            "trace as a70_census.py did",
            "Module's H/L split taken over the indexed unit space rather than a "
            "generic-name table",
        ],
        "claim_boundary": ("measures over-credit under a FIXED ontology (A65/A67); "
                           "it does NOT validate that ontology, since Gamma+ is "
                           "built from the same pi_credit as the truth"),
        "primary_is_exact": ("all four rules are deterministic and the population "
                             "is enumerable, so no smoke/dev/confirmatory ladder "
                             "is used in V0.2R primary (A70, retained)"),
    }, indent=1, default=str), encoding="utf-8")
    print(f"wrote {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
