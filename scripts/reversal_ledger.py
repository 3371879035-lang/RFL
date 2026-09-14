"""Reversal ledger — at exactly which N did each conclusion change?

The project re-ran pilots at 100 / 200 / 300 / 400 seeds and conclusions moved.
"Conclusion changed" is a slippery phrase, and the whole reason
``docs/SEED_BLOCK_PROTOCOL.md`` exists is that the naive reading of it --
"the p-value crossed 0.05" -- is wrong. This script therefore records **two**
readings side by side at every scheduled look:

``CI`` reading (what the old rule used)
    does the 95% bootstrap CI of the cumulative mean exclude zero? This is the
    reading that produced the three recorded "reversals", and it is reported
    here only so the record shows what it said.

``4-way`` reading (the frozen rule, the one that counts)
    where the CI sits relative to the pre-specified minimum meaningful effect
    ``Delta_min = 0.01``: ``SUPPORT_A`` / ``EQUIVALENT`` / ``SUPPORT_B`` /
    ``INCONCLUSIVE``.

A **reversal** is defined as a change in the ``4-way`` verdict between two
scheduled looks. A ``CI`` flip that leaves the ``4-way`` verdict untouched is
recorded as ``(no-op)`` -- it is exactly the ``p = 0.04 -> 0.07`` case that must
not be written up as a reversal.

For every reversal the ledger also reports *why*, using the block that caused
it: the fresh block's own mean, recovered exactly as
``mean_prev + k*(mean_N - mean_prev)``.

Usage
-----
    python scripts/reversal_ledger.py                 # all *_400 pilots
    python scripts/reversal_ledger.py --json out.json
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from block_analysis import BLOCK, DELTA_MIN, LOOKS, bootstrap_ci, decide  # noqa: E402
from robustness_audit import TIE_TOL, build_contrasts, load_arms  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# Pilot -> baseline arm. Each pilot's contrast is read against its own baseline;
# `None` lets build_contrasts pick for single-contrast pilots (Stage 5).
PILOTS = {
    "v03_stage5_400": None,
    "v03_alpha_400": "traditional",
    "v03_stage4_400": "traditional",
    "v04_alpha_400": "ModuleOracle",
    "v04_beta_400": "NegativeOnly",
}

BOOT_SEED = 20_240_901


def ci_excludes_zero(pooled: list[float], rng) -> tuple[bool, float, float]:
    lo, hi = bootstrap_ci(pooled, rng)
    return (lo > 0 or hi < 0), lo, hi


def trail(deltas: list[float], rng) -> dict:
    """Verdicts at every scheduled look, plus where they changed."""
    looks = []
    for n in LOOKS:
        k = n // BLOCK
        pooled = deltas[:n]
        if len(pooled) < n:
            continue
        lo, hi = bootstrap_ci(pooled, rng)
        excludes, _, _ = ci_excludes_zero(pooled, rng)

        # The fresh block's own mean, via the decomposition identity.
        prev = deltas[: n - BLOCK]
        block_mean = None
        if prev:
            m_prev = st.mean(prev)
            m_cur = st.mean(pooled)
            block_mean = m_prev + k * (m_cur - m_prev)

        looks.append(
            {
                "n": n,
                "mean": st.mean(pooled),
                "ci": (lo, hi),
                "ci_excludes_zero": excludes,
                "verdict": decide(lo, hi),
                "new_block_mean": block_mean,
                "new_block": k,
            }
        )
    return {"looks": looks}


def reversals(looks: list[dict]) -> list[dict]:
    """Every change of the frozen verdict, with the block responsible."""
    out = []
    for prev, cur in zip(looks, looks[1:]):
        if prev["verdict"] == cur["verdict"]:
            continue
        out.append(
            {
                "at_n": cur["n"],
                "from": prev["verdict"],
                "to": cur["verdict"],
                "block": cur["new_block"],
                "block_mean": cur["new_block_mean"],
                "mean_before": prev["mean"],
                "mean_after": cur["mean"],
                "ci_before": prev["ci"],
                "ci_after": cur["ci"],
            }
        )
    return out


def ci_only_flips(looks: list[dict]) -> list[dict]:
    """Looks where the CI sign flipped but the frozen verdict did not move.

    These are the false alarms: the ones the old rule reported as reversals.
    """
    out = []
    for prev, cur in zip(looks, looks[1:]):
        if prev["ci_excludes_zero"] != cur["ci_excludes_zero"]:
            out.append(
                {
                    "at_n": cur["n"],
                    "before": prev["ci_excludes_zero"],
                    "after": cur["ci_excludes_zero"],
                    "verdict": cur["verdict"],
                    "no_op": prev["verdict"] == cur["verdict"],
                }
            )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", default=None)
    ap.add_argument("--outdir", default="outputs")
    args = ap.parse_args()

    rng = np.random.default_rng(BOOT_SEED)
    ledger: dict = {}

    for pilot, baseline in PILOTS.items():
        summary = ROOT / args.outdir / pilot / "summary.json"
        if not summary.exists():
            print(f"[skip] {pilot}: no summary.json")
            continue
        arms = load_arms(summary)
        contrasts = build_contrasts(arms, baseline)
        ledger[pilot] = {}

        for label, deltas in contrasts:
            deltas = list(deltas)
            if len(deltas) < 400:
                continue
            tr = trail(deltas, rng)
            rev = reversals(tr["looks"])
            flips = ci_only_flips(tr["looks"])
            ledger[pilot][label] = {"looks": tr["looks"], "reversals": rev,
                                    "ci_flips": flips}

            seq = " -> ".join(lk["verdict"][:4] for lk in tr["looks"])
            print(f"\n{pilot}  |  {label}")
            print(f"  frozen verdict by look: {seq}")
            for lk in tr["looks"]:
                bm = lk["new_block_mean"]
                bms = f"  B{lk['new_block']} alone {bm:+.5f}" if bm is not None else ""
                print(
                    f"    N={lk['n']:<4} mean {lk['mean']:+.5f}  "
                    f"CI [{lk['ci'][0]:+.5f}, {lk['ci'][1]:+.5f}]  "
                    f"{lk['verdict']}{bms}"
                )
            if rev:
                for r in rev:
                    print(
                        f"  ** REVERSAL at N={r['at_n']}: {r['from']} -> {r['to']}"
                        f"   caused by B{r['block']} alone = {r['block_mean']:+.5f}"
                    )
            else:
                print("  no reversal in the frozen verdict")
            for f in flips:
                tag = "NO-OP (verdict unchanged)" if f["no_op"] else "verdict moved too"
                print(
                    f"  ~ CI-exclusion flip at N={f['at_n']}: "
                    f"{f['before']} -> {f['after']}  [{tag}; verdict {f['verdict']}]"
                )

    if args.json:
        Path(args.json).write_text(json.dumps(ledger, indent=1, default=str),
                                   encoding="utf-8")
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
