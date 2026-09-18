r"""Probe: is the frozen reverse fold bit-exact against the DP, and is it necessary?

Before freezing "return-to-go uses the frozen reverse Bellman fold" as a normative
clause, the clause has to survive two questions that its justification assumes:

1. **Is it exact?** On a healthy trajectory the write $Q_D^L(x_t,a_t^F)\leftarrow
   G_t^F$ must land on exactly the reference value, or the canonicalisation to
   deletion never fires and a tiny override appears -- polluting ``healthy``,
   $N_{\text{scalar}}$, $\Sigma$ and the fingerprint. So $G_t^F$ must be
   **bit-identical** to `dp.py`'s stored $Q_D^\ast(x_t,a_t^F)$.

2. **Is it necessary?** If a plain left-to-right ``sum`` or ``math.fsum`` happened
   to agree everywhere on this support, the clause would be harmless but its stated
   reason would be unproven -- and this project does not freeze a rule on an
   unmeasured failure mode.

The DP has **two** branches (``solve_reference``):

    row[a] = res.reward                       if res.terminal
    row[a] = res.reward + v[(next, z, m)]     otherwise

so a fold written ``G_T = 0; G_j = r_j + G_{j+1}`` computes ``r + 0.0`` at the
last step where the DP computes ``r``. Those are bit-identical for every finite
float except ``-0.0`` (``(-0.0) + 0.0 = +0.0``), and ``float.hex()`` in the
fingerprint distinguishes the two zeros. So both forms are measured, plus a count
of negative-zero rewards.

Usage::

    python scripts/_diag_dq_return_fold.py [--json PATH]
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.env import kernel as K                      # noqa: E402
from rfl_rebuild.env.observation import walk_transition       # noqa: E402
from rfl_rebuild.solve.dp import solve_reference              # noqa: E402

KAPPAS = (0, 1)
PHIS = K.PHASE_DOMAIN


def _hex(x: float) -> str:
    return float(x).hex()


def healthy_trace(kappa: int, phi: int, z0: int, sol):
    provider = lambda s, c: sol.best_action(s, c.z, c.m)      # noqa: E731
    return K.rollout(
        kappa=kappa,
        tape=K.SemanticTape(phase=phi, error_flag=0, cause_rank=0),
        command_provider=provider,
        base_option=z0,
    )


def fold_A(rewards, t: int) -> float:
    """``G_T = 0; G_j = r_j + G_{j+1}`` -- the clause as literally written."""
    g = 0.0
    for j in range(len(rewards) - 1, t - 1, -1):
        g = rewards[j] + g
    return g


def fold_B(rewards, t: int) -> float:
    """DP-branch-faithful: the last step is terminal, so ``G_last = r_last``."""
    g = rewards[-1]
    for j in range(len(rewards) - 2, t - 1, -1):
        g = rewards[j] + g
    return g


def left_to_right(rewards, t: int) -> float:
    total = 0.0
    for j in range(t, len(rewards)):
        total = total + rewards[j]
    return total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(ROOT / "experiments" / "v03r"
                                         / "dq_return_fold.json"))
    args = ap.parse_args()

    sol = solve_reference()
    stats: Counter = Counter()
    mismatches: list[dict] = []
    per_fold = {"A_literal_zero_start": 0, "B_dp_terminal_branch": 0,
                "left_to_right": 0, "fsum": 0}
    exact = {"A_literal_zero_start": 0, "B_dp_terminal_branch": 0,
             "left_to_right": 0, "fsum": 0}
    nonzero_diff_A_B: list[dict] = []
    trace_lengths: Counter = Counter()

    for kappa in KAPPAS:
        for phi in PHIS:
            for z0 in K.option_ids():
                tr = healthy_trace(kappa, phi, z0, sol)
                rows = list(walk_transition(tr, kappa, phi, tr.option_in_force))
                rewards = [r for (_s, _z, _m, _a, _ar, r) in rows]
                trace_lengths[len(rows)] += 1
                for (_s, _z, _m, _a, _ar, r) in rows:
                    if r == 0.0 and math.copysign(1.0, r) < 0:
                        stats["negative_zero_rewards"] += 1
                for t, (s, z, m, a_cmd, _ar, _r) in enumerate(rows):
                    ctx = (s, z, m)
                    ref = sol.q.get(ctx, {}).get(a_cmd)
                    if ref is None:
                        stats["no_reference_entry"] += 1
                        continue
                    stats["addresses"] += 1
                    got = {
                        "A_literal_zero_start": fold_A(rewards, t),
                        "B_dp_terminal_branch": fold_B(rewards, t),
                        "left_to_right": left_to_right(rewards, t),
                        "fsum": math.fsum(rewards[t:]),
                    }
                    for k, v in got.items():
                        if _hex(v) == _hex(ref):
                            exact[k] += 1
                        else:
                            per_fold[k] += 1
                            if len(mismatches) < 12:
                                mismatches.append({
                                    "fold": k, "kappa": kappa, "phi": phi, "z0": z0,
                                    "t": t, "T": len(rows), "ref": _hex(ref),
                                    "got": _hex(v),
                                })
                    if _hex(got["A_literal_zero_start"]) != \
                            _hex(got["B_dp_terminal_branch"]):
                        nonzero_diff_A_B.append({
                            "kappa": kappa, "phi": phi, "z0": z0, "t": t,
                            "A": _hex(got["A_literal_zero_start"]),
                            "B": _hex(got["B_dp_terminal_branch"]),
                        })

    total = stats["addresses"]
    payload = {
        "check": "reverse-fold bit-exactness against the reference DP",
        "n_trajectories": sum(trace_lengths.values()),
        "trace_length_histogram": dict(sorted(trace_lengths.items())),
        "decision_addresses": total,
        "negative_zero_rewards": stats["negative_zero_rewards"],
        "no_reference_entry": stats["no_reference_entry"],
        "exact_by_fold": exact,
        "mismatch_by_fold": per_fold,
        "A_vs_B_differing_bit_patterns": len(nonzero_diff_A_B),
        "sample_mismatches": mismatches,
        "sample_A_vs_B": nonzero_diff_A_B[:5],
        "verdict": {
            "clause_as_written_exact": per_fold["A_literal_zero_start"] == 0,
            "dp_terminal_branch_exact": per_fold["B_dp_terminal_branch"] == 0,
            "clause_is_necessary": per_fold["left_to_right"] > 0
            or per_fold["fsum"] > 0,
        },
        "obligation": (
            "healthy-trajectory exhaustive-support invariant: after any change to the "
            "solver, the reward function or the grid, re-measure; a nonzero mismatch "
            "means a healthy write would leave a non-canonical override"
        ),
    }
    out = pathlib.Path(args.json)
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print("reverse-fold probe")
    print(f"  trajectories                 : {payload['n_trajectories']}")
    print(f"  trace lengths                : {payload['trace_length_histogram']}")
    print(f"  decision addresses           : {total}")
    print(f"  negative-zero rewards        : {stats['negative_zero_rewards']}")
    for k in exact:
        print(f"  exact  {k:24}: {exact[k]:>7}   mismatch {per_fold[k]}")
    print(f"  A vs B differing patterns    : {len(nonzero_diff_A_B)}")
    print(f"  verdict                      : {payload['verdict']}")
    print(f"  written                      : {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
