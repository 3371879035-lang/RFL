"""A70 — exact representation-granularity census over the FULL support.

Primary is an exact enumeration, not a sampled experiment: all three output rules
are deterministic and the population is DGP-enumerable, so drawing 400 scenes to
approximate this would have no statistical content.

  Fine / Identity Reference   E_Gamma(l) = Gamma*(l)          Coverage 1, FCR 0 BY CONSTRUCTION
  Module   (coarse)           Gamma* -> H/L -> eta_module      the over-credit of a 2-way compression
  Trajectory (coarsest)       Gamma* -> Episode -> Gamma(I)    the over-credit of naming the whole run

Both a world-count mean and a DGP-weighted mean are reported, because V0.1R showed
those can differ by an order of magnitude on this very support.

The Fine reference's perfect score is a CONSTRUCTIONAL IDENTITY, not an empirical
finding, and is checked as an assertion rather than reported as a result.
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gate_stage2 import LatentCase, _domains, reference_provider  # noqa: E402
from identifiability_gate import CAUSE_KEYS  # noqa: E402
from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.env.kernel import SemanticTape, State  # noqa: E402
from rfl_rebuild.method.credit import (  # noqa: E402
    CausalProposal, FactualShape, ModuleProposal, TrajectoryProposal, coverage,
    expand, false_credit_rate,
)
from rfl_rebuild.method.support import DenseSupport  # noqa: E402
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

CACHE = ROOT / "experiments" / "v01r" / "support_cache"
# cause index -> credit unit (A67 projection)
UNIT_OF_CAUSE = {0: "ProcessCommit", 1: "Decision_t", 2: "ControllerSite",
                 3: "ExternalPlant", 4: "Unknown/NoWrite"}
NON_INDEXED = {"ProcessCommit", "ExternalPlant", "Unknown/NoWrite"}


def main() -> int:
    sol = solve_reference()
    provider = reference_provider(sol)
    sup = DenseSupport.load(CACHE, expected_kernel_fingerprint="full",
                            expected_dgp_fingerprint="full")
    n = len(sup)

    agg = {a: {"cov_w": 0.0, "fcr_w": 0.0, "size_w": 0.0,
               "cov_c": 0.0, "fcr_c": 0.0, "size_c": 0.0}
           for a in ("Fine", "Module", "Trajectory")}
    mass_seen = 0.0
    fine_exact = True
    gamma_star_hist = {}

    for wid in range(n):
        w = sup.weight(wid)
        mass_seen += w
        fc = sup.field(wid, "fire_code")
        gamma_star = frozenset(UNIT_OF_CAUSE[i] for i in range(5)
                               if (fc >> i) & 1) or frozenset({"Unknown/NoWrite"})

        case = LatentCase(
            case_id=0, kappa=sup.field(wid, "kappa"), phi=sup.field(wid, "phase"),
            error_flag=sup.field(wid, "error_flag"),
            cause_rank=sup.field(wid, "cause_rank"),
            base_option=sup.field(wid, "proposal"),
            Z=tuple((sup.field(wid, "Z_code") >> i) & 1 for i in range(5)),
            option_fault=None, decision=None, controller=None, plant=None,
            trap=None)
        tr = K.rollout(kappa=case.kappa, tape=case.tape(),
                       command_provider=provider, base_option=case.base_option)
        steps = tr.steps
        # StepResult carries the POST-state, so the pre-action state timeline is
        # walked from START exactly as gate_stage2 does. One site per visited
        # ControllerSite, keyed the way class_local_queries keys it.
        st = State(x=K.START[0], y=K.START[1], t=0, kappa=case.kappa,
                   phi=case.phi)
        sites = []
        for s in steps:
            sites.append(f"{st.x}_{st.y}_{st.t}_{s.a_cmd}")
            st = s.state
        shape = FactualShape(timesteps=tuple(range(len(steps))),
                             sites=tuple(sites))

        fine = gamma_star
        h = {UNIT_OF_CAUSE[i] for i in range(5) if (fc >> i) & 1} & NON_INDEXED
        l = {UNIT_OF_CAUSE[i] for i in range(5) if (fc >> i) & 1} - NON_INDEXED
        module = expand("module",
                        ModuleProposal(frozenset(
                            ({"H"} if h else set()) | ({"L"} if l else set()))),
                        shape)
        traj = expand("trajectory", TrajectoryProposal(frozenset({"Episode"})),
                      shape)

        for name, pred in (("Fine", fine), ("Module", module),
                           ("Trajectory", traj)):
            c = coverage(pred, gamma_star)
            f = false_credit_rate(pred, gamma_star)
            a = agg[name]
            a["cov_w"] += w * c
            a["fcr_w"] += w * f
            a["size_w"] += w * len(pred)
            a["cov_c"] += c
            a["fcr_c"] += f
            a["size_c"] += len(pred)
        if not (coverage(fine, gamma_star) == 1.0
                and false_credit_rate(fine, gamma_star) == 0.0):
            fine_exact = False
        k = "|".join(sorted(gamma_star))
        gamma_star_hist[k] = gamma_star_hist.get(k, 0) + 1

    for a in agg.values():
        for k in list(a):
            # weighted means divide by the TOTAL MASS, count means by n. An
            # earlier version divided both by n, so every mass column printed as
            # 0.0000 -- the weighted sums are O(1) and n is ~1e6.
            a[k] = a[k] / mass_seen if k.endswith("_w") else a[k] / n
    checks = {
        "fine_reference_is_lossless_by_construction": fine_exact,
        "mass_scanned_is_one": abs(mass_seen - 1.0) < 1e-9,
    }
    ok = all(checks.values())

    print(f"A70 exact granularity census over {n:,} worlds\n")
    print(f"{'representation':<14}{'Cov(count)':>12}{'Cov(mass)':>12}"
          f"{'FCR(count)':>12}{'FCR(mass)':>12}{'|G|(count)':>12}")
    for name in ("Fine", "Module", "Trajectory"):
        a = agg[name]
        print(f"{name:<14}{a['cov_c']:>12.4f}{a['cov_w']:>12.4f}"
              f"{a['fcr_c']:>12.4f}{a['fcr_w']:>12.4f}{a['size_c']:>12.2f}")
    print()
    for k in sorted(checks):
        print(f"  {k:<48} {checks[k]}")
    print(f"\ndistinct Gamma* sets: {len(gamma_star_hist)}")
    print(f"A70 census: {'PASS' if ok else 'FAIL'}")

    out = {"n_worlds": n, "aggregate": agg, "checks": checks,
           "status": "PASS" if ok else "FAIL",
           "distinct_gamma_star": len(gamma_star_hist),
           "claim_boundary":
               "This measures over-credit under a FIXED ontology (A65/A67). It does "
               "NOT validate that ontology: that needs an external criterion not "
               "defined by Gamma*, i.e. downstream consequences.",
           "primary_is_exact": "all three rules are deterministic and the "
                               "population is enumerable, so no smoke/dev/"
                               "confirmatory ladder is used in V0.2R primary"}
    p = ROOT / "experiments" / "v02r" / "granularity_census.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(f"wrote {p}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
