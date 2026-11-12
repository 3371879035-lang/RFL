"""Execute the frozen seed-block protocol (``docs/SEED_BLOCK_PROTOCOL.md``).

At every scheduled look ``N = 100, 200, 300, 400`` this prints two things:

* the **cumulative** pooled estimate over blocks ``B1..Bk``, and
* the **new block alone** (``Bk``).

The second is what distinguishes a genuine reversal from variance shrinkage. A
cumulative move from ``+0.04`` to ``+0.01`` means something completely different
if ``B2`` came in at ``-0.02`` (the effect failed to replicate) than if ``B2``
came in near zero (the pooled mean just regressed as the error bar shrank).

The conclusion is **not** "``p`` crossed 0.05". It is the four-way rule of §4:
where the cumulative CI sits relative to the pre-specified minimum meaningful
effect ``DELTA_MIN = 0.01``:

    SUPPORT_A     L > +DELTA_MIN
    EQUIVALENT    [L, U] subset of [-DELTA_MIN, +DELTA_MIN]
    SUPPORT_B     U < -DELTA_MIN
    INCONCLUSIVE  otherwise

Only ``N = 400`` is confirmatory; earlier looks are diagnostic.

Usage
-----
    python scripts/block_analysis.py outputs/v03_stage5_400
    python scripts/block_analysis.py outputs/ --all
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from robustness_audit import (  # noqa: E402
    TIE_TOL,
    build_contrasts,
    load_arms,
)

DELTA_MIN = 0.01
BLOCK = 100
N_BOOT = 10_000
BOOT_SEED = 20_240_901  # fixed, so every reported interval is reproducible
LOOKS = (100, 200, 300, 400)


def bootstrap_ci(deltas, rng, n_boot: int = N_BOOT, alpha: float = 0.05):
    """Percentile bootstrap CI for the mean of paired deltas."""
    arr = np.asarray(deltas, dtype=float)
    if arr.size == 0:
        return float("nan"), float("nan")
    idx = rng.integers(0, arr.size, size=(n_boot, arr.size))
    means = arr[idx].mean(axis=1)
    lo, hi = np.percentile(means, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return float(lo), float(hi)


def decide(lo: float, hi: float, delta_min: float = DELTA_MIN) -> str:
    """The pre-registered four-way rule."""
    if lo > delta_min:
        return "SUPPORT_A"
    if hi < -delta_min:
        return "SUPPORT_B"
    if lo >= -delta_min and hi <= delta_min:
        return "EQUIVALENT"
    return "INCONCLUSIVE"


def block_of(seed_value: int, seed_base: int) -> int:
    """Which 100-seed block a seed belongs to (1-based)."""
    return (seed_value - seed_base) // BLOCK + 1


def analyse_contrast(label: str, pairs: list[tuple[int, float]], rng) -> dict:
    """pairs: (seed_value, delta) sorted by seed value."""
    pairs = sorted(pairs)
    blocks: dict[int, list[float]] = {}
    for i, (_, d) in enumerate(pairs):
        blocks.setdefault(i // BLOCK + 1, []).append(d)

    looks = []
    for n in LOOKS:
        k = n // BLOCK
        pooled = [d for b in range(1, k + 1) for d in blocks.get(b, [])]
        if len(pooled) < n:
            continue
        lo, hi = bootstrap_ci(pooled, rng)
        looks.append(
            {
                "n": n,
                "mean": st.mean(pooled),
                "median": st.median(pooled),
                "ci": (lo, hi),
                "decision": decide(lo, hi),
            }
        )

    block_rows = []
    for b in sorted(blocks):
        vals = blocks[b]
        lo, hi = bootstrap_ci(vals, rng)
        nz = [x for x in vals if abs(x) > TIE_TOL]
        block_rows.append(
            {
                "block": b,
                "n": len(vals),
                "mean": st.mean(vals),
                "median": st.median(vals),
                "ci": (lo, hi),
                "decision": decide(lo, hi),
                "ties": len(vals) - len(nz),
            }
        )

    return {"label": label, "looks": looks, "blocks": block_rows}


def report(pilot: str, results: list[dict]) -> None:
    print(f"\n{'=' * 96}\n{pilot}\n{'=' * 96}")
    for r in results:
        print(f"\ncontrast: {r['label']}      (Delta_min = {DELTA_MIN})")
        print("  cumulative looks")
        print(f"    {'N':>5}{'mean':>11}{'median':>11}{'95% CI':>26}{'decision':>15}")
        prev = None
        for lk in r["looks"]:
            ci = f"[{lk['ci'][0]:+.5f}, {lk['ci'][1]:+.5f}]"
            print(
                f"    {lk['n']:>5}{lk['mean']:>+11.5f}{lk['median']:>+11.5f}"
                f"{ci:>26}{lk['decision']:>15}"
            )
            if prev is not None:
                # Cumulative mean is the block-size-weighted average:
                #   mean_N = ((k-1)*mean_prev + new) / k
                # so the new block's own mean is recovered exactly as
                #   new = mean_prev + k*(mean_N - mean_prev)
                # This is the number that says whether a cumulative move was a
                # real reversal in the fresh block or just variance shrinkage.
                k = lk["n"] // BLOCK
                shift = lk["mean"] - prev["mean"]
                implied = prev["mean"] + k * shift
                print(
                    f"          change vs N={prev['n']}: {shift:+.5f}"
                    f"  ->  B{k} alone = {implied:+.5f}"
                )
            prev = lk

        print("  per-block (fresh, non-overlapping)")
        print(f"    {'block':>6}{'n':>5}{'mean':>11}{'median':>11}{'95% CI':>26}{'ties':>6}{'decision':>15}")
        for b in r["blocks"]:
            ci = f"[{b['ci'][0]:+.5f}, {b['ci'][1]:+.5f}]"
            print(
                f"    {b['block']:>6}{b['n']:>5}{b['mean']:>+11.5f}{b['median']:>+11.5f}"
                f"{ci:>26}{b['ties']:>6}{b['decision']:>15}"
            )

        finals = [lk for lk in r["looks"] if lk["n"] == max(x["n"] for x in r["looks"])]
        if finals:
            f = finals[0]
            print(f"  CONFIRMATORY (N={f['n']}): {f['decision']}")

        # Did any intermediate look disagree with the confirmatory one in a way
        # that is a real reversal rather than an interval-width artifact?
        if len(r["looks"]) > 1:
            seq = [lk["decision"] for lk in r["looks"]]
            if len(set(seq)) > 1:
                print(f"  decision trajectory: {' -> '.join(seq)}")
            block_means = [b["mean"] for b in r["blocks"]]
            if block_means and max(block_means) > 0 > min(block_means):
                print(
                    "  NOTE: blocks disagree in SIGN "
                    f"(min {min(block_means):+.5f}, max {max(block_means):+.5f}) "
                    "-> the effect does not replicate across blocks"
                )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--baseline", default=None)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--json", default=None, help="also write results to this JSON file")
    args = ap.parse_args()

    rng = np.random.default_rng(BOOT_SEED)
    dumped = {}
    found = 0

    targets: list[Path] = []
    for raw in args.paths:
        root = Path(raw)
        if not root.exists():
            print(f"[skip] {root} missing")
            continue
        if root.is_file():
            targets.append(root)
        elif args.all:
            targets.extend(sorted(root.rglob("summary.json")))
        elif (root / "summary.json").exists():
            targets.append(root / "summary.json")

    for summary in targets:
        try:
            arms = load_arms(summary)
        except Exception:
            continue
        if not arms:
            continue
        contrasts = build_contrasts(arms, args.baseline)
        if not contrasts:
            continue
        results = []
        for label, deltas in contrasts:
            # Recover seed values so blocks are ordered by seed, not by luck.
            results.append(analyse_contrast(label, list(enumerate(deltas)), rng))
        report(summary.parent.name, results)
        dumped[summary.parent.name] = results
        found += 1

    if not found:
        print("no auditable summary.json found")
        return 1
    if args.json:
        Path(args.json).write_text(json.dumps(dumped, indent=1), encoding="utf-8")
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
