"""A62 — exact and empirical consistency of the scene DGP.

Neither check consumes a smoke or development scene.

EXACT 1  ``sum over contexts of P(ctx) = 1``. A62 rev1 sampled the phase with
         ``rng.choice`` but never paid ``P(phi)`` in ``log_prob``, so the context
         level was not one measure. Equal phase frequencies would have cancelled
         in a normalised posterior, but "it cancels by coincidence" is not a
         single probability definition.
EXACT 2  ``sum over (Z, params) of P(Z, params | ctx) = 1``, with the canonical
         encoding enforced (``Z_i = 0 => param_i = -1``).
EMPIRICAL  draws use WHOLE-SCENE rejection, so the sampler targets
         ``P_raw(ell | ell in F)`` where F is factual well-formedness. Stage2
         already measured 127,440 MALFORMED factual cases out of 1,166,400
         candidates, so this conditioning is not hypothetical.
"""

from __future__ import annotations

import itertools
import json
import pathlib
import random
import sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gate_stage2 import (  # noqa: E402
    LatentCase, _domains, reference_provider, sigma0,
)
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

    def build_case(ctx, Z, params):
        dm = domains(ctx)
        blocks = {}
        for i, key in enumerate(CAUSE_KEYS):
            blocks[key] = dm[i][params[i]] if Z[i] else None
        return LatentCase(case_id=0, kappa=ctx.kappa, phi=ctx.phase,
                          error_flag=ctx.error_flag, cause_rank=ctx.cause_rank,
                          base_option=ctx.base_option, Z=tuple(Z),
                          option_fault=blocks.get("P"), decision=blocks.get("D"),
                          controller=blocks.get("X"), plant=blocks.get("E"),
                          trap=blocks.get("U"))

    def is_feasible(ctx, Z, params):
        try:
            return sigma0(sol, build_case(ctx, Z, params))[0] is not None
        except Exception:
            return False

    dgp = SceneDGP(kappas=KAPPAS, options=K.option_ids(), tapes=TAPES,
                   domains=domains, is_feasible=is_feasible)

    context_total = dgp.context_total()

    totals = {}
    for err in (0, 1):
        for z in K.option_ids():
            ctx = SceneContext(kappa=0, phase=0, error_flag=err, cause_rank=0,
                               base_option=z)
            totals[f"err={err},z={z}"] = dgp.slice_total(ctx)
    worst = max(abs(v - 1.0) for v in totals.values())

    # exact feasibility slice at one context: how much of the raw mass survives
    ctx0 = SceneContext(kappa=0, phase=0, error_flag=0, cause_rank=0,
                        base_option=0)
    dm0 = domains(ctx0)
    n_raw = n_feas = 0
    raw_mass = feas_mass = 0.0
    for bits in range(1 << 5):
        Z = [(bits >> i) & 1 for i in range(5)]
        if any(Z[i] == 1 and not dm0[i] for i in range(5)):
            continue
        for combo in itertools.product(*[range(len(dm0[i])) if Z[i] else [-1]
                                         for i in range(5)]):
            n_raw += 1
            m = (dgp.world_log_prob(ctx0, Z, list(combo))
                 + dgp.context_log_prob(ctx0))
            raw_mass += pow(2.718281828459045, m)
            if is_feasible(ctx0, Z, combo):
                n_feas += 1
                feas_mass += pow(2.718281828459045, m)

    rng = random.Random(20250814)
    hist, avail = Counter(), Counter()
    for _ in range(N_MC):
        ctx, Z, _p = dgp.sample_scene(rng)
        hist[sum(Z)] += 1
        avail[sum(1 for x in domains(ctx) if x)] += 1

    mc = {k: v / N_MC for k, v in sorted(hist.items())}
    mc_le1 = sum(v for k, v in mc.items() if k <= 1)
    analytic_all5 = 0.8 ** 5 + 5 * 0.2 * 0.8 ** 4

    ctx_ok = abs(context_total - 1.0) < 1e-9
    exact_ok = worst < 1e-9
    print(f"EXACT  sum over contexts of P(ctx) = {context_total!r}  "
          f"[{'PASS' if ctx_ok else 'FAIL'}]")
    print(f"EXACT  conditional slice totals, worst |sum-1| = {worst:.3e}  "
          f"[{'PASS' if exact_ok else 'FAIL'}]")
    print(f"\nfeasibility at one context: kept {n_feas}/{n_raw} worlds "
          f"({n_feas/max(n_raw,1):.1%}); mass kept "
          f"{feas_mass/max(raw_mass,1e-30):.1%}")
    print(f"EMPIRICAL |Z| over {N_MC} FEASIBLE draws:")
    for k in sorted(mc):
        print(f"  |Z|={k}: {mc[k]:.4f}")
    print(f"  P(|Z|<=1) empirical                 = {mc_le1:.4f}")
    print(f"  P(|Z|<=1) analytic, all 5 available  = {analytic_all5:.4f}")
    print(f"  mean available causes                = "
          f"{sum(k*v for k, v in avail.items())/N_MC:.3f}")

    out = ROOT / "experiments" / "v01r" / "dgp_consistency.json"
    out.write_text(json.dumps({
        "context_total": context_total,
        "context_normalisation": "PASS" if ctx_ok else "FAIL",
        "phase_mass": dgp.phase_mass,
        "slice_totals": totals, "worst_abs_error": worst,
        "conditional_normalisation": "PASS" if exact_ok else "FAIL",
        "feasibility_slice": {
            "raw_worlds": n_raw, "feasible_worlds": n_feas,
            "kept_fraction": n_feas / max(n_raw, 1),
            "raw_mass": raw_mass, "feasible_mass": feas_mass,
            "mass_kept_fraction": feas_mass / max(raw_mass, 1e-30)},
        "n_mc": N_MC, "mc_absZ": mc, "mc_p_le1": mc_le1,
        "analytic_p_le1_all_causes_available": analytic_all5,
        "mean_available_causes": sum(k * v for k, v in avail.items()) / N_MC,
        "note": "Draws use WHOLE-SCENE rejection, so the sampler targets "
                "P_raw(ell | ell in F). The empirical P(|Z|<=1) is compared with "
                "the all-five-causes-available figure for orientation only; "
                "contexts with an empty canonical domain force Z_i to 0 and push "
                "it UP. feasibility_slice carries the exact conditioning mass.",
        "consumes_smoke_or_dev_scenes": False,
    }, indent=1, default=str), encoding="utf-8")
    print(f"wrote {out}")
    return 0 if (ctx_ok and exact_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
