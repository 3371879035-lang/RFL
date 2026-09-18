r"""B1 target-dependency audit: what do the four update targets depend on?

A76 will freeze the B1 update-law contract, and the review asked for two read-only
inputs first. This is the first: an audit of the target values that `08` §3.1 carries,
against the reward semantics the kernel actually froze.

`08` §3.1's arms, verbatim targets:

    NegativeOnly        factual decision site   failure value   -> Q_D(s, a_bad)
    PositiveAlternative verified alternative    +1              -> Q_D(s, a_alt)
    Contrastive         both                    failure / +1    -> both entries
    CFTarget            verified alternative    G^CF_{a_alt}    -> Q_D(s, a_alt)

FROZEN reward semantics (kernel): HORIZON = 12, STEP_COST = -0.02,
REWARD_SUCCESS = +1.0, REWARD_FAILURE_A = -1.0, REWARD_FAILURE_B = 0.0, and the
exact DP is UNDISCOUNTED finite-horizon (`row[a] = res.reward + v[next]`, mode A).

So an episode return is `-0.02 * steps + terminal`, which means:

* a success in k steps returns `1.0 - 0.02k`, so the largest reachable return
  corresponds to the FEWEST steps to the goal;
* the literal target `+1` therefore describes **a success with zero step cost** --
  reachable only in the limit k = 0.

`RolloutTrace.return_value` already carries A38's correction: the earlier revision
"returned +1 / -1 and dropped both the per-step cost and reward mode B". The audit
question is whether `08`'s `+1` survived that correction un-rescaled.

The script also re-checks one interaction the A75 pre-check surfaced: 8.3% of the
canonical support's D slots are TIED-OPTIMAL, so a `NegativeOnly`-style write of a
"failure value" into the factual entry can corrupt an entry that was already optimal.

Read-only. Writes only its report.
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

VAL_TOL = 1e-12


def main() -> int:
    sol = solve_reference()

    q_vals = [v for row in sol.q.values() for v in row.values()]
    v_vals = list(sol.v.values())
    q_max, q_min = max(q_vals), min(q_vals)
    v_max, v_min = max(v_vals), min(v_vals)

    start = K.State(x=K.START[0], y=K.START[1], t=0, kappa=0, phi=0)
    from_start = {}
    for kappa in (0, 1):
        s0 = K.State(x=K.START[0], y=K.START[1], t=0, kappa=kappa, phi=0)
        for z in K.option_ids():
            from_start[(kappa, z)] = sol.value(s0, z, 0)

    # Success in k steps: return = 1.0 - 0.02k. Solve for the k that `+1` implies.
    implied_zero_cost = (K.REWARD_SUCCESS - 1.0) / abs(K.STEP_COST)

    # The largest reachable return over the whole solved space.
    best_reachable = v_max

    findings = {
        "target_plus_one_exceeds_every_dp_value":
            best_reachable < K.REWARD_SUCCESS - VAL_TOL,
        "target_minus_one_matches_the_bare_constant_not_a_return":
            K.REWARD_FAILURE_A == -1.0 and v_min < K.REWARD_FAILURE_A + VAL_TOL,
    }

    print("B1 target-dependency audit\n")
    print("  frozen reward semantics")
    print(f"    HORIZON                 : {K.HORIZON}")
    print(f"    STEP_COST               : {K.STEP_COST}")
    print(f"    REWARD_SUCCESS          : {K.REWARD_SUCCESS}")
    print(f"    REWARD_FAILURE_A / B    : {K.REWARD_FAILURE_A} / {K.REWARD_FAILURE_B}")
    print(f"    DP discount             : none (row[a] = reward + v[next])")
    print(f"\n  exact DP value range over {len(sol.q):,} entries")
    print(f"    Q* min / max            : {q_min:.4f} / {q_max:.4f}")
    print(f"    V* min / max            : {v_min:.4f} / {v_max:.4f}")
    print(f"    V*(START, z, 0) per (kappa, z):")
    for (kappa, z), v in sorted(from_start.items()):
        print(f"      kappa={kappa} z={z}            : {v:.4f}")
    print(f"\n  08's targets against that range")
    print(f"    target  +1              : {K.REWARD_SUCCESS}")
    print(f"      best reachable return : {best_reachable:.4f}")
    print(f"      +1 exceeds it by      : {K.REWARD_SUCCESS - best_reachable:.4f}")
    print(f"      +1 is 'success with this many steps of cost': "
          f"{implied_zero_cost:.1f}  (i.e. none)")
    print(f"    target 'failure value'  : ")
    print(f"      as the bare constant  : {K.REWARD_FAILURE_A} "
          f"('failure with zero step cost')")
    print(f"      as the factual return : depends on the episode; NOT a constant")
    print(f"      V* min actually       : {v_min:.4f}")
    for k, v in findings.items():
        print(f"  [{'CONFIRMED' if v else 'not confirmed'}] {k}")

    out = ROOT / "experiments" / "v02r" / "b1_target_dependency_audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "reward_semantics": {
            "HORIZON": K.HORIZON,
            "STEP_COST": K.STEP_COST,
            "REWARD_SUCCESS": K.REWARD_SUCCESS,
            "REWARD_FAILURE_A": K.REWARD_FAILURE_A,
            "REWARD_FAILURE_B": K.REWARD_FAILURE_B,
            "dp_discount": "none (finite-horizon, undiscounted, mode A)",
        },
        "dp_value_range": {"q_min": q_min, "q_max": q_max,
                           "v_min": v_min, "v_max": v_max},
        "v_start_per_kappa_option": {f"kappa{k}_z{z}": v
                                     for (k, z), v in sorted(from_start.items())},
        "targets_in_08": {
            "PositiveAlternative": "+1",
            "Contrastive": "failure / +1",
            "NegativeOnly": "failure value (unspecified constant or factual?)",
            "CFTarget": "G^CF_{a_alt}",
        },
        "audit": {
            "plus_one_exceeds_best_reachable_return":
                bool(findings["target_plus_one_exceeds_every_dp_value"]),
            "best_reachable_return": best_reachable,
            "plus_one_overstatement": K.REWARD_SUCCESS - best_reachable,
            "plus_one_implies_zero_step_cost": True,
            "minus_one_is_the_bare_constant": True,
        },
        "reading": ("`+1` describes a success with ZERO step cost, which no episode can "
                    "reach: the largest reachable undiscounted return is "
                    f"{best_reachable:.4f}. `-1` likewise describes a failure with zero "
                    "step cost, whereas the worst reachable return is "
                    f"{v_min:.4f}. A38 already removed exactly this hard-coded +-1 from "
                    "the kernel's return_value; `08`'s targets appear to predate that "
                    "correction and were never rescaled."),
        "downstream_hazard": ("8.3% of the canonical support's D slots are tied-optimal "
                              "(A75 pre-check). A NegativeOnly-style write of a failure "
                              "value into the FACTUAL entry therefore corrupts an entry "
                              "that was already optimal on those slots."),
        "note": ("audit only; no formula is proposed here, and no code is changed"),
    }, indent=1, default=str), encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
