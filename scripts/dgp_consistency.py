"""A62 — exact and empirical consistency of the scene DGP.

Two checks, neither of which consumes a smoke or development scene:

EXACT   on a context small enough to enumerate,
            sum over (Z, params) of P(Z, params | ctx) = 1
        This is the check that makes "one probability definition" real rather
        than aspirational: if the sampler and the prior drifted apart, this sum
        would not be 1.

EMPIRICAL   sample many contexts and worlds and compare the marginal
        distribution of |Z| against the analytic one. They are NOT expected to
        match the all-five-causes-available figure exactly, because contexts
        with an empty canonical domain force that cause to 0 and therefore push
        P(|Z| <= 1) UP. The doc's 0.737 is the all-available value; the run prints
        both so the difference is visible rather than hidden.
"""

from __future__ import annotations

import json
import pathlib
import random
import sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gate_stage2 import _domains, reference_provider  # noqa: E402
from identifiability_gate import CAUSE_KEYS, KAPPAS, TAPES, canonicalise  # noqa: E402
from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.env.kernel import SemanticTape  # noqa: E402
from rfl_rebuild.method.dgp import SceneContext, SceneDGP  # noqa: E402
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

N_MC = 20_000


def main() -> int:
    sol = solve_reference()
    provider = reference_provider(sol)

    def domains(ctx: SceneContext):
        tape = SemanticTape(phase=ctx.phase, error_flag=ctx.error_flag,
                            cause_rank=ctx.cause_rank)
        tr = K.rollout(kappa=ctx.kappa, tape=tape, command_provider=provider,
                       base_option=ctx.base_option)
        d = _domains(sol, ctx.kappa, tape, ctx.base_option, tr)
        return tuple(canonicalise(d[k]) for k in CAUSE_KEYS)

    dgp = SceneDGP(kappas=KAPPAS, options=K.option_ids(), tapes=TAPES,
                   domains=domains)

    totals = {}
    for err in (0, 1):
        for z in K.option_ids():
            ctx = SceneContext(kappa=0, phase=0, error_flag=err, cause_rank=0,
                               base_option=z)
            totals[f"err={err},z={z}"] = dgp.slice_total(ctx)
    worst = max(abs(v - 1.0) for v in totals.values())

    rng = random.Random(20250814)
    hist = Counter()
    avail = Counter()
    for _ in range(N_MC):
        ctx = dgp.sample_context(rng)
        Z, _p = dgp.sample_world(rng, ctx)
        hist[sum(Z)] += 1
        avail[sum(1 for x in domains(ctx) if x)] += 1

    mc = {k: v / N_MC for k, v in sorted(hist.items())}
    mc_le1 = sum(v for k, v in mc.items() if k <= 1)
    analytic_all5 = 0.8 ** 5 + 5 * 0.2 * 0.8 ** 4

    exact_ok = worst < 1e-9
    print(f"EXACT slice totals (must all be 1): worst |sum-1| = {worst:.3e}")
    print(f"EMPIRICAL |Z| distribution over {N_MC} draws:")
    for k in sorted(mc):
        print(f"  |Z|={k}: {mc[k]:.4f}")
    print(f"  P(|Z|<=1) empirical      = {mc_le1:.4f}")
    print(f"  P(|Z|<=1) analytic all-5 = {analytic_all5:.4f}")
    print(f"  mean available causes    = "
          f"{sum(k*v for k, v in avail.items())/N_MC:.3f}")
    print(f"\nEXACT check: {'PASS' if exact_ok else 'FAIL'}")

    out = ROOT / "experiments" / "v01r" / "dgp_consistency.json"
    out.write_text(json.dumps({
        "slice_totals": totals, "worst_abs_error": worst,
        "exact_normalisation": "PASS" if exact_ok else "FAIL",
        "n_mc": N_MC, "mc_absZ": mc, "mc_p_le1": mc_le1,
        "analytic_p_le1_all_causes_available": analytic_all5,
        "mean_available_causes":
            sum(k * v for k, v in avail.items()) / N_MC,
        "note": "The empirical P(|Z|<=1) is expected to EXCEED the all-available "
                "0.737, because contexts with an empty canonical domain force Z_i "
                "to 0 and reduce |Z|. The two are printed side by side so the gap "
                "is visible rather than smoothed over.",
        "consumes_smoke_or_dev_scenes": False,
    }, indent=1, default=str), encoding="utf-8")
    print(f"wrote {out}")
    return 0 if exact_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
