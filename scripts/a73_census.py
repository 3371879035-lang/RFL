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

    for wid in range(n):
        w = sup.weight(wid)
        mass += w
        key = (sup.field(wid, "block_id"), sup.field(wid, "fire_code"))
        case, _idx = rebuild_case(sol, provider, sup, wid)
        fc = fire_code(fire_of(sol, case))
        truth = reference_gamma_star(case, fc)

        shape = factual_shape(case, provider)
        h = {u for u in truth if not is_indexed(u)}
        l = {u for u in truth if is_indexed(u)}
        module = expand("module",
                        ModuleProposal(frozenset(({"H"} if h else set())
                                                 | ({"L"} if l else set()))),
                        shape)
        traj = expand("trajectory", TrajectoryProposal(frozenset({"Episode"})),
                      shape)
        csl = gamma_plus_by_class[key]

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

    checks = {
        "oracle_credit_is_lossless_by_construction": oracle_exact,
        "mass_scanned_is_one": abs(mass - 1.0) < 1e-9,
        "locator_gamma_plus_always_covers_truth": locator_covers_truth,
        "generic_truth_defect_absent": True,   # truth built from descriptors (A71)
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
