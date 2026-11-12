"""Post-confirmatory descriptive audit: the EXACT DGP marginal of Z^fire.

Zero positives in the sampled scenes does NOT bound the rate by 1/N, and it
certainly does not prove an earlier estimate wrong. The correct one-sided 95%
upper bound for 0 successes in n trials is

    1 - 0.05^(1/n)

which for n=400 is ~0.75%, not 0.25%. But no statistical bound is needed here at
all: the dense support already carries the exact DGP weight of every feasible
world and every world's fire_code, so

    P(Z_i^fire = 1) = sum over feasible worlds of w_l * 1[bit i of fire_code]

is an exact sum over 1,038,960 cached worlds. No rollouts, no scenes, no contact
with the confirmatory data. This distinguishes two very different explanations
for the observed zeros: finite-sample bad luck, versus the presence-x-fire census
approximation in A54/A63 being structurally wrong.
"""

from __future__ import annotations

import json
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from identifiability_gate import CAUSE_KEYS  # noqa: E402
from rfl_rebuild.method.support import DenseSupport  # noqa: E402

CACHE = ROOT / "experiments" / "v01r" / "support_cache"
N_PLANNED = {"smoke": 5, "dev": 32, "conf": 400}
N_TOTAL_SAMPLED = 5 + 32 + 400


def upper95_zero(n: int) -> float:
    """Exact one-sided 95% upper bound on a rate observed as 0/n."""
    return 1.0 - 0.05 ** (1.0 / n)


def main() -> int:
    sup = DenseSupport.load(CACHE, expected_kernel_fingerprint="full",
                            expected_dgp_fingerprint="full")
    n = len(sup)
    mass = {c: 0.0 for c in CAUSE_KEYS}
    tot = 0.0
    for wid in range(n):
        w = sup.weight(wid)
        tot += w
        fc = sup.field(wid, "fire_code")
        for i, c in enumerate(CAUSE_KEYS):
            if (fc >> i) & 1:
                mass[c] += w
    exact = {c: mass[c] / tot for c in CAUSE_KEYS}

    zeros = {"smoke": 5, "dev": 32, "conf": 400}
    bounds = {k: upper95_zero(v) for k, v in zeros.items()}
    bounds["all_sampled"] = upper95_zero(N_TOTAL_SAMPLED)

    print(f"exact DGP marginal of Z^fire over {n:,} feasible worlds")
    for c in CAUSE_KEYS:
        print(f"  P(Z_{c}^fire = 1) = {exact[c]:.6f}")
    print(f"\nexpected U positives at each planned N (exact rate):")
    for k, v in N_PLANNED.items():
        e = exact["U"] * v
        p_zero = (1.0 - exact["U"]) ** v
        print(f"  N={v:<4} expected {e:.4f}   P(observe 0) = {p_zero:.4f}")
    print(f"\n  P(observe 0 at all three sizes) = "
          f"{(1.0 - exact['U']) ** N_TOTAL_SAMPLED:.4f}")
    print(f"\none-sided 95% upper bounds from the ZERO observations")
    for k, v in bounds.items():
        print(f"  {k:<12} n={zeros.get(k, N_TOTAL_SAMPLED):<4} p_U < {v:.5f}")

    out = {
        "exact_dgp_marginal_Zfire": exact,
        "n_worlds": n,
        "expected_U_positives": {k: exact["U"] * v for k, v in N_PLANNED.items()},
        "p_observe_zero_U": {k: (1.0 - exact["U"]) ** v
                             for k, v in N_PLANNED.items()},
        "p_observe_zero_U_all_sampled": (1.0 - exact["U"]) ** N_TOTAL_SAMPLED,
        "one_sided_95_upper_bounds_from_observations": bounds,
        "n_total_sampled_scenes": N_TOTAL_SAMPLED,
        "method": "exact sum of DGP weights over the dense support; no rollouts, "
                  "no scenes, no contact with confirmatory data",
        "why": "Zero positives bound the rate only by 1 - 0.05^(1/n). The exact "
               "marginal is available for free from the cache, so the earlier "
               "sample-based guess does not need to be defended or attacked "
               "statistically.",
        "consumes_scenes": False,
    }
    path = ROOT / "experiments" / "v01r" / "exact_fire_marginals.json"
    path.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(f"\nwrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
