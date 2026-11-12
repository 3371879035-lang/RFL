"""Pilot Gamma interactions, recomputed at the correct unit of analysis.

Why this script exists
----------------------
`pilot_v04_gamma.py` computed the two interactions like this::

    for label, pick in (
        ("reward_B_minus_A",   lambda r, s: (("B", s), ("A", s))),
        ("severe_minus_mild",  lambda r, s: ((r, "severe"), (r, "mild"))),
    ):
        for r in REWARDS:
            for s, _ in SEVERITIES:
                hi, lo = pick(r, s)
                xs.append(get(hi)); ys.append(get(lo))

Both `pick` functions ignore one of their two arguments:

* ``reward_B_minus_A`` ignores ``r``, so the loop over the two rewards appends the
  **same** ``(B|s, A|s)`` pair twice for every severity;
* ``severe_minus_mild`` ignores ``s``, so the loop over the two severities appends
  the **same** ``(r|severe, r|mild)`` pair twice for every reward.

Every observation therefore entered the paired test **exactly twice**. A mean is
untouched by duplication, which is why the reported effect sizes are fine. But the
bootstrap CI, the sign-flip permutation p and the Wilcoxon test all treat *n* as
twice the number of independent observations, so they are anti-conservative: the
intervals come out too narrow and the p-values too small.

There is a second, independent problem. The unit of analysis in this project is
the **seed**, and one seed contributes *two* severity cells to the reward
interaction. Feeding cell-level pairs into a paired test treats within-seed cells
as independent samples, which they are not: the severity cells of one seed share
its environment draws and its noise tape.

What this script does
---------------------
Aggregates to the seed first, then tests across seeds:

* ``reward_B_minus_A``  -- per seed, the **mean over severities** of ``B|s - A|s``
* ``severe_minus_mild`` -- per seed, the **mean over rewards** of ``r|severe - r|mild``

then runs a one-sample test on the resulting ``n = 400`` seed-level values, and
applies the same four-way rule as the rest of the frozen protocol
(``Delta_min = 0.01``).

It also reports the original duplicated, cell-level computation side by side so
the size of the inflation is on the record rather than asserted.

Note on episodes: the 400-seed Gamma run was launched with ``--episodes 1000``,
so it used 1,000 training episodes, not the 2,000 that
``pilot_v04_gamma.py`` prints in its "per 2000 episodes" line. That string is
hardcoded and is wrong for this run; ``n_negative_td`` figures are per 1,000.

Usage
-----
    python scripts/v04_gamma_seedlevel.py outputs/v04_gamma_400
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from block_analysis import DELTA_MIN, bootstrap_ci, decide  # noqa: E402
from robustness_audit import TIE_TOL  # noqa: E402

REWARDS = ("A", "B")
SEVERITIES = ("mild", "severe")
MECHANISMS = ("NoCorrection", "NegativeOnly", "DecisionOracle")

N_PERM = 5000
N_BOOT = 5000
SEED_RNG = 20_240_901


def sign_flip_p(values: np.ndarray, rng, n_perm: int = N_PERM) -> float:
    """Two-sided sign-flip permutation test on the mean."""
    n = values.size
    if n == 0:
        return float("nan")
    obs = abs(values.mean())
    signs = rng.choice([-1.0, 1.0], size=(n_perm, n))
    perm = np.abs((signs * values).mean(axis=1))
    return float((np.sum(perm >= obs) + 1) / (n_perm + 1))


def load_cells(path: Path) -> dict:
    doc = json.loads(path.read_text(encoding="utf-8"))
    cells: dict[tuple[str, str, str], dict[int, float]] = {}
    for row in doc["rows"]:
        reward, severity, mech = row["cell"].split("|")
        cells.setdefault((reward, severity, mech), {})[row["seed"]] = float(
            row["success_auc"]
        )
    return cells


def seed_level_reward(cells, mech):
    """Per seed: mean over severities of (B - A)."""
    out = {}
    seeds = sorted(cells[("A", "mild", mech)])
    for s in seeds:
        diffs = [
            cells[("B", sev, mech)][s] - cells[("A", sev, mech)][s]
            for sev in SEVERITIES
        ]
        out[s] = float(np.mean(diffs))
    return out


def seed_level_severity(cells, mech):
    """Per seed: mean over rewards of (severe - mild)."""
    out = {}
    seeds = sorted(cells[("A", "mild", mech)])
    for s in seeds:
        diffs = [
            cells[(r, "severe", mech)][s] - cells[(r, "mild", mech)][s]
            for r in REWARDS
        ]
        out[s] = float(np.mean(diffs))
    return out


def cell_level_duplicated(cells, mech, kind):
    """The original computation, duplication and all, for comparison."""
    xs, ys = [], []
    for s in sorted(cells[("A", "mild", mech)]):
        for _r in REWARDS:              # the bug: reward loop is a no-op here
            for _sev in SEVERITIES:     # and the severity loop is a no-op here
                if kind == "reward":
                    for sev in SEVERITIES:
                        xs.append(cells[("B", sev, mech)][s])
                        ys.append(cells[("A", sev, mech)][s])
                else:
                    for r in REWARDS:
                        xs.append(cells[(r, "severe", mech)][s])
                        ys.append(cells[(r, "mild", mech)][s])
    return np.array(xs), np.array(ys)


def report(name: str, vals: dict[int, float], rng) -> dict:
    v = np.array([vals[s] for s in sorted(vals)], dtype=float)
    lo, hi = bootstrap_ci(v.tolist(), rng)
    nz = v[np.abs(v) > TIE_TOL]
    pos, neg = int((nz > 0).sum()), int((nz < 0).sum())

    ordered = np.sort(v)
    top = ordered[np.argsort(-np.abs(v))][:5]
    net = float(v.sum())
    share = float(top.sum() / net * 100) if abs(net) > TIE_TOL else float("nan")
    wo = float((net - top.sum()) / (v.size - 5)) if v.size > 5 else float("nan")

    return {
        "n": int(v.size),
        "mean": float(v.mean()),
        "median": float(np.median(v)),
        "ci": (lo, hi),
        "decision": decide(lo, hi),
        "sign_flip_p": sign_flip_p(v, rng),
        "ties": int(v.size - nz.size),
        "pos": pos,
        "neg": neg,
        "top5_share": share,
        "mean_wo_top5": wo,
    }


def line(tag: str, r: dict) -> str:
    return (
        f"  {tag:<34} n={r['n']:<4} mean={r['mean']:+.5f}  "
        f"CI [{r['ci'][0]:+.5f}, {r['ci'][1]:+.5f}]  p={r['sign_flip_p']:.4f}  "
        f"ties={r['ties']:<4} {r['pos']:+d}/{-r['neg']:+d}  "
        f"top5={r['top5_share']:.0f}%  -> {r['decision']}"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("outdir", nargs="?", default="outputs/v04_gamma_400")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    path = Path(args.outdir) / "summary.json"
    if not path.exists():
        print(f"missing {path}")
        return 1
    cells = load_cells(path)
    rng = np.random.default_rng(SEED_RNG)

    print("=" * 108)
    print("Pilot Gamma interactions -- seed-level (correct) vs cell-level duplicated (as published)")
    print(f"Delta_min = {DELTA_MIN}; unit = seed; one seed contributes 2 cells per interaction")
    print("=" * 108)

    out = {}
    for mech in MECHANISMS:
        print(f"\n{mech}")
        for kind, label, fn in (
            ("reward", "reward_B_minus_A", seed_level_reward),
            ("severity", "severe_minus_mild", seed_level_severity),
        ):
            correct = report(label, fn(cells, mech), rng)
            xs, ys = cell_level_duplicated(cells, mech, kind)
            d = xs - ys
            dup = {
                "n": int(d.size),
                "mean": float(d.mean()),
                "ci": bootstrap_ci(d.tolist(), rng),
                "sign_flip_p": sign_flip_p(d, rng),
            }
            dup["decision"] = decide(*dup["ci"])
            out[f"{mech}:{label}"] = {"seed_level": correct, "cell_level": dup}

            print(line("seed-level  (correct)", correct))
            print(
                f"  {'cell-level  (as published)':<34} n={dup['n']:<4} "
                f"mean={dup['mean']:+.5f}  "
                f"CI [{dup['ci'][0]:+.5f}, {dup['ci'][1]:+.5f}]  "
                f"p={dup['sign_flip_p']:.4f}  -> {dup['decision']}"
            )
            widen = (dup["ci"][1] - dup["ci"][0]) and (
                (correct["ci"][1] - correct["ci"][0])
                / (dup["ci"][1] - dup["ci"][0])
            )
            print(
                f"  {'':<34} CI is {widen:.2f}x wider once duplicated n is collapsed "
                f"to the seed; mean identical to 5dp: "
                f"{abs(correct['mean'] - dup['mean']) < 5e-6}"
            )

    if args.json:
        Path(args.json).write_text(json.dumps(out, indent=1), encoding="utf-8")
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
