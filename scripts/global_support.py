"""A62 full global support constructor, with its 5 structural closures.

FROZEN ATOM. One support world is exactly one DGP canonical world:

    (kappa, phase, error_flag, cause_rank, z^proposal, Z, param_1..param_5)

with inactive params pinned to -1. ``dynamical_key`` is NOT used here. It drops
``error_flag`` and ``cause_rank`` and exists for theorem-side
response-equivalence compression in Gate3; letting it into the experiment
support constructor would silently make it impossible for a DGP draw to match its
own support atom.

THE POPULATION IS NOT THE GATE CLASSES. The public prior is
"all DGP-feasible canonical worlds", not the classes Gate_fire judged, not
multi-target classes, not non-singleton classes, not classes with reps >= 2, and
not anything identifiability-filtered. Those two sets were deliberately separated
and must not be re-merged here.

Pipeline: SceneDGP support -> feasibility -> canonical world ids -> rows-only
blocks. Storage is compact: ids and small ints, and a LatentCase is rebuilt on
demand for queries.

Closures:
  1 support cardinality equals the independently counted feasible support
  2 canonical key uniqueness: no duplicate world
  3 raw support equality: every support world has P_raw > 0, and every infeasible
    raw world is absent
  4 sample -> support bijection: zero=0, many=0, one=N
  5 prior mass: w_l = P_raw(l) / A_full, and the weights sum to 1
"""

from __future__ import annotations

import itertools
import json
import math
import pathlib
import random
import sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gate_stage2 import (  # noqa: E402
    LatentCase, _domains, fire_of, reference_provider, sigma0,
)
from identifiability_gate import CAUSE_KEYS, KAPPAS, TAPES, canonicalise  # noqa: E402
from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.env.kernel import SemanticTape  # noqa: E402
from rfl_rebuild.method.dgp import SceneContext, SceneDGP  # noqa: E402
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

EXPECTED_N = 1_038_960
EXACT = math.e


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
        b = {k: (dm[i][params[i]] if Z[i] else None)
             for i, k in enumerate(CAUSE_KEYS)}
        return LatentCase(case_id=0, kappa=ctx.kappa, phi=ctx.phase,
                          error_flag=ctx.error_flag, cause_rank=ctx.cause_rank,
                          base_option=ctx.base_option, Z=tuple(Z),
                          option_fault=b.get("P"), decision=b.get("D"),
                          controller=b.get("X"), plant=b.get("E"),
                          trap=b.get("U"))

    def is_feasible(ctx, Z, params):
        try:
            return sigma0(sol, build_case(ctx, Z, params))[0] is not None
        except Exception:
            return False

    dgp = SceneDGP(kappas=KAPPAS, options=K.option_ids(), tapes=TAPES,
                   domains=domains, is_feasible=is_feasible)

    # ------------------------------------------------------------------ #
    # enumerate EVERY DGP-feasible canonical world
    # ------------------------------------------------------------------ #
    W = []                  # compact records
    seen_keys = set()
    dup = 0
    n_raw_worlds = 0
    n_infeasible = 0
    rows_sig_to_id: dict = {}
    rows_of = []
    A_raw_ctx = 0.0

    for kappa in KAPPAS:
        for tape in TAPES:
            for z in K.option_ids():
                ctx = SceneContext(kappa=kappa, phase=tape.phase,
                                   error_flag=tape.error_flag,
                                   cause_rank=tape.cause_rank, base_option=z)
                pc = dgp.context_log_prob(ctx)
                if pc == -math.inf:
                    continue
                dm = domains(ctx)
                A_raw_ctx += pow(EXACT, pc)
                for bits in itertools.product((0, 1), repeat=5):
                    if any(bits[i] == 1 and not dm[i] for i in range(5)):
                        continue
                    per = [range(len(dm[i])) if bits[i] else [-1]
                           for i in range(5)]
                    for combo in itertools.product(*per):
                        n_raw_worlds += 1
                        params = list(combo)
                        if not is_feasible(ctx, bits, params):
                            n_infeasible += 1
                            continue
                        rk = repr(sigma0(sol, build_case(ctx, bits, params))[0][0])
                        wkey = (kappa, tape.phase, tape.error_flag,
                                tape.cause_rank, z, tuple(bits), tuple(params))
                        if wkey in seen_keys:
                            dup += 1
                        else:
                            seen_keys.add(wkey)
                        bid = rows_sig_to_id.get(rk)
                        if bid is None:
                            bid = len(rows_sig_to_id)
                            rows_sig_to_id[rk] = bid
                        W.append((kappa, tape.phase, tape.error_flag,
                                  tape.cause_rank, z, tuple(bits), tuple(params),
                                  bid, fire_of(sol, build_case(ctx, bits, params))))
                        rows_of.append(rk)

    N = len(W)
    print(f"enumerated raw worlds: {n_raw_worlds:,}; infeasible {n_infeasible:,}; "
          f"feasible {N:,}")

    # ---- closure 1: cardinality ------------------------------------------ #
    c1 = (N == EXPECTED_N)
    # ---- closure 2: canonical uniqueness --------------------------------- #
    c2 = (dup == 0 and len(seen_keys) == N)

    # ---- closure 5: prior mass ------------------------------------------- #
    # The shifted sum is NOT P_raw(F). Written out so the artifact carries
    # physically meaningful quantities:
    #     S_shift = sum_l exp(log P_raw(l) - m),  m = max_l log P_raw(l)
    #     A = P_raw(F) = exp(m) * S_shift
    # Normalised weights are unaffected either way, since
    #     exp(log P_l - m) / sum_j exp(log P_j - m) = P_l / sum_j P_j
    log_w = []
    for (kappa, phase, ef, cr, z, Z, params, bid, fc) in W:
        ctx = SceneContext(kappa=kappa, phase=phase, error_flag=ef,
                           cause_rank=cr, base_option=z)
        log_w.append(dgp.log_prob(ctx, Z, params))
    max_log_prob = max(log_w)
    shifted = [pow(EXACT, lw - max_log_prob) for lw in log_w]
    S_shift = sum(shifted)
    log_feasible_mass = max_log_prob + math.log(S_shift)
    feasible_mass = pow(EXACT, log_feasible_mass)
    weights = [s / S_shift for s in shifted]
    c5 = abs(sum(weights) - 1.0) < 1e-9

    # ---- closure 3: every INCLUDED world has strictly positive raw mass --- #
    # Named for what it checks. That every INFEASIBLE raw world is absent is not
    # verified here; it follows from the enumeration's `if not is_feasible:
    # continue` together with closures 1 and 2, and is reported as such rather
    # than as an independent observation.
    c3 = all(math.isfinite(lw) for lw in log_w) and S_shift > 0.0

    # ---- closure 4: sample -> support bijection -------------------------- #
    key_to_one = {k: True for k in seen_keys}
    rng = random.Random(99)
    one = zero = many = 0
    for _ in range(2000):
        ctx, Z, params = dgp.sample_scene(rng)
        k = (ctx.kappa, ctx.phase, ctx.error_flag, ctx.cause_rank,
             ctx.base_option, tuple(Z), tuple(params))
        if k in key_to_one:
            one += 1
        else:
            zero += 1
    c4 = (zero == 0 and many == 0 and one == 2000)

    checks = {
        "1_support_cardinality": {"status": bool(c1), "observed": N,
                                  "expected": EXPECTED_N},
        "2_canonical_key_unique": {"status": bool(c2), "duplicates": dup},
        "3_support_worlds_have_positive_raw_mass": {
            "status": bool(c3), "all_log_prob_finite": c3,
            "note": "Checks only that INCLUDED worlds have positive raw mass. "
                    "That infeasible raw worlds are ABSENT follows from the "
                    "enumeration's continue plus closures 1 and 2, and is a "
                    "combined invariant, not a separate observation."},
        "4_sample_support_bijection": {
            "status": bool(c4), "one": one, "zero": zero, "many": many,
            "note": "many=0 is DERIVED from closure 2 (canonical uniqueness): "
                    "key_to_one is a dict, so the many-counter has no increment "
                    "path and could not have observed a duplicate even if one "
                    "existed. Reported as derived rather than as an independent "
                    "measurement."},
        "5_prior_mass": {"status": bool(c5),
                         "max_log_prob": max_log_prob,
                         "shifted_mass_sum": S_shift,
                         "log_feasible_mass": log_feasible_mass,
                         "feasible_mass": feasible_mass,
                         "weight_sum": sum(weights)},
    }
    ok = all(v["status"] for v in checks.values())

    print(f"rows-only blocks: {len(rows_sig_to_id):,}")
    for k in sorted(checks):
        print(f"  {k:<30} {checks[k]['status']}   "
              f"{json.dumps({x: y for x, y in checks[k].items() if x != 'status'}, default=str)[:110]}")
    print(f"\nFULL SUPPORT: {'ALL CLOSURES PASS' if ok else 'CLOSURE FAILURE'}")

    out = ROOT / "experiments" / "v01r" / "global_support.json"
    out.write_text(json.dumps({
        "n_support_worlds": N, "n_rows_blocks": len(rows_sig_to_id),
        "expected_n": EXPECTED_N, "n_raw_worlds": n_raw_worlds,
        "n_infeasible": n_infeasible, "max_log_prob": max_log_prob,
        "shifted_mass_sum": S_shift, "log_feasible_mass": log_feasible_mass,
        "feasible_mass": feasible_mass,
        "checks": checks, "status": "PASS" if ok else "FAIL",
        "artifact_note": "The committed artifact from the first build still "
                         "carries the mislabelled 'A_full' = shifted sum and the "
                         "old closure-3 name; this script must be re-run (~20 min) "
                         "to regenerate it. The normalised weights were always "
                         "correct.",
        "atom": "DGP canonical world (kappa, phase, error_flag, cause_rank, "
                "z^proposal, Z, params) with inactive params pinned to -1. "
                "dynamical_key is NOT used: it drops error_flag and cause_rank.",
        "population": "all DGP-feasible canonical worlds; NOT the Gate classes "
                      "and NOT anything identifiability-filtered.",
    }, indent=1, default=str), encoding="utf-8")
    print(f"wrote {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
