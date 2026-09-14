"""Robustness audit for a pilot's ``summary.json``.

Motivation
----------
This project repeatedly re-ran pilots at larger seed counts and watched
conclusions flip: v0.4 Alpha flipped sign between 12 and 100 seeds, v0.3 Alpha's
bootstrap CI crossed zero between 100 and 200, and v0.3 Stage 5 reversed three
times. Re-running at ever larger N is one response, but it treats the symptom.
This script tests the mechanism.

The mechanism is that per-seed paired deltas in this codebase are
**zero-inflated and heavy-tailed**:

* a large fraction of seeds produce *bit-identical* runs across two arms, so the
  paired delta is exactly ``0.0`` — e.g. 70% of seeds in v0.3 Alpha;
* the seeds that do differ can differ by a lot, because a single divergent
  bootstrap changes which fixed point the tabular Q-iteration lands in.

A mean (and therefore a bootstrap CI around a mean) over such a distribution is
dominated by a handful of large-magnitude seeds. The sign of the mean can
disagree with the sign of the median, and a CI that excludes zero can coexist
with a sign test that is indistinguishable from a coin flip.

What this script reports, per paired contrast
---------------------------------------------
``mean`` / ``median`` / ``trimmed5%``
    Location. When these disagree in sign, the mean is being carried by tails.
``ties``
    Seeds where the two arms are identical to ``1e-12``. A high tie fraction
    means the effective sample size is far below N.
``+/-`` and ``sign_test_p``
    Exact binomial test on the non-tied seeds only. This is the assumption-light
    counterpart to the bootstrap CI: it uses only the *direction* of each
    non-tied seed, never its magnitude.
``wilcoxon_p``
    Signed-rank, uses magnitudes but is rank-based, so it is robust to a few
    enormous seeds. Reported both raw and Holm-corrected across all contrasts
    printed in one invocation.
``top5_share``
    Percentage of the net sum contributed by the five largest ``|delta|`` seeds.
    Above ~50% the mean is a statement about five seeds, not about the arm.
``mean_wo_top5``
    The mean after dropping those five seeds. This is the single most diagnostic
    number here: if it collapses toward zero, the published effect was tail.

Usage
-----
    python scripts/robustness_audit.py outputs/v03_stage5_300
    python scripts/robustness_audit.py outputs/v04_alpha_300 --baseline NoCorrection
    python scripts/robustness_audit.py outputs/ --all

With ``--all`` the script walks a directory tree, audits every ``summary.json``
it recognises, and prints one block per pilot, so the same statistic can be read
off at 100 / 200 / 300 / 400 seeds side by side.
"""

from __future__ import annotations

import argparse
import json
import statistics as st
from collections import defaultdict
from pathlib import Path

try:
    from scipy.stats import binomtest, wilcoxon

    HAVE_SCIPY = True
except Exception:  # pragma: no cover - scipy is present in this project's venv
    HAVE_SCIPY = False

TIE_TOL = 1e-12


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #

def _load(path: Path):
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _from_seed_rows(doc: dict) -> dict[str, dict[int, float]]:
    """v0.3 / v0.4 pilot layout: ``seeds`` is a flat list of arm-per-seed rows."""
    per: dict[str, dict[int, float]] = defaultdict(dict)
    for row in doc.get("seeds", []):
        if "arm" not in row:
            continue
        key = row.get("seed")
        val = row.get("success_auc")
        if key is None or val is None:
            continue
        per[row["arm"]][key] = float(val)
    return dict(per)


def _from_stage5_rows(doc: dict) -> dict[str, dict[int, float]]:
    """Stage 5 layout: ``rows`` carries one difficulty setting per row."""
    per: dict[str, dict[int, float]] = defaultdict(dict)
    for row in doc.get("rows", []):
        setting = row.get("setting")
        if setting is None or "traditional_auc" not in row:
            continue
        # Two synthetic arms per setting, so the generic contrast machinery works.
        per[f"{setting}|traditional"][row["seed"]] = float(row["traditional_auc"])
        per[f"{setting}|oracle"][row["seed"]] = float(row["oracle_auc"])
    return dict(per)


def load_arms(path: Path) -> dict[str, dict[int, float]]:
    doc = _load(path)
    arms = _from_seed_rows(doc)
    if not arms:
        arms = _from_stage5_rows(doc)
    return arms


# --------------------------------------------------------------------------- #
# statistics
# --------------------------------------------------------------------------- #

def holm(pvals: list[float]) -> list[float]:
    """Holm-Bonferroni step-down, returned in the input order."""
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    out = [1.0] * m
    running = 0.0
    for rank, idx in enumerate(order):
        adj = min(1.0, (m - rank) * pvals[idx])
        running = max(running, adj)
        out[idx] = running
    return out


def contrast_stats(deltas: list[float]) -> dict:
    """All robustness statistics for one paired contrast."""
    n = len(deltas)
    ordered = sorted(deltas)
    nz = [x for x in ordered if abs(x) > TIE_TOL]
    pos = sum(1 for x in nz if x > 0)
    neg = len(nz) - pos

    k = max(1, int(0.05 * n))
    trimmed = ordered[k:n - k] if n - 2 * k >= 1 else ordered

    by_mag = sorted(ordered, key=abs, reverse=True)
    top5 = by_mag[:5]
    net = sum(ordered)
    top5_share = (sum(top5) / net * 100.0) if abs(net) > TIE_TOL else float("nan")
    mean_wo = (net - sum(top5)) / (n - len(top5)) if n > len(top5) else float("nan")

    if HAVE_SCIPY and nz:
        sign_p = float(binomtest(pos, len(nz), 0.5).pvalue)
        wilcox_p = float(wilcoxon(ordered).pvalue)
    else:
        sign_p = wilcox_p = float("nan")

    return {
        "n": n,
        "mean": st.mean(ordered),
        "median": st.median(ordered),
        "trimmed": st.mean(trimmed),
        "ties": n - len(nz),
        "tie_frac": (n - len(nz)) / n if n else float("nan"),
        "pos": pos,
        "neg": neg,
        "sign_p": sign_p,
        "wilcox_p": wilcox_p,
        "top5_share": top5_share,
        "mean_wo_top5": mean_wo,
        "max_abs": max(abs(x) for x in nz) if nz else 0.0,
    }


def build_contrasts(
    arms: dict[str, dict[int, float]], baseline: str | None
) -> list[tuple[str, list[float]]]:
    """Pair up arms on shared seeds. Stage 5 settings are paired internally."""
    names = list(arms)

    # Stage 5: one natural contrast per setting, no cross-setting pairing.
    if names and all("|" in n for n in names):
        out = []
        for name in names:
            if not name.endswith("|traditional"):
                continue
            other = name[: -len("|traditional")] + "|oracle"
            if other not in arms:
                continue
            shared = sorted(set(arms[name]) & set(arms[other]))
            label = name.split("|")[0]
            out.append((label, [arms[other][s] - arms[name][s] for s in shared]))
        return out

    if not names:
        return []
    base = baseline if baseline in arms else names[0]
    out = []
    for name in names:
        if name == base:
            continue
        shared = sorted(set(arms[base]) & set(arms[name]))
        if not shared:
            continue
        out.append((f"{name} - {base}", [arms[name][s] - arms[base][s] for s in shared]))
    return out


# --------------------------------------------------------------------------- #
# reporting
# --------------------------------------------------------------------------- #

HEADER = (
    f"{'contrast':<34}{'n':>5}{'mean':>10}{'median':>10}{'trim5%':>10}"
    f"{'ties':>7}{'+/-':>9}{'sign_p':>9}{'wcx_p':>9}{'holm':>9}"
    f"{'top5%':>8}{'mean_wo5':>11}"
)


def verdict(s: dict) -> str:
    """A coarse, deliberately conservative reading of one contrast."""
    if s["ties"] == s["n"]:
        return "IDENTICAL — arms never differ; no test applicable"
    if s["sign_p"] != s["sign_p"]:  # NaN
        return "NO SCIPY — sign test unavailable"

    same_sign = (s["mean"] > 0) == (s["median"] > 0) == (s["trimmed"] > 0)
    if not same_sign:
        if abs(s["median"]) <= TIE_TOL:
            return (
                f"TAIL-DRIVEN — median exactly 0 ({s['ties']}/{s['n']} ties); "
                "the mean is carried by the minority that moved"
            )
        return "TAIL-DRIVEN — mean and median disagree in sign"

    if abs(s["mean"]) > TIE_TOL:
        share = s["top5_share"]
        shrunk = abs(s["mean_wo_top5"]) < 0.25 * abs(s["mean"])
        if (share == share and abs(share) > 50) or shrunk:
            return "TAIL-DRIVEN — 5 seeds carry the mean"

    if s["sign_p"] >= 0.01:
        return "DIRECTION UNRESOLVED — sign test not significant"
    return "ROBUST"


def report_block(title: str, contrasts: list[tuple[str, list[float]]]) -> None:
    if not contrasts:
        return
    stats = [(label, contrast_stats(d)) for label, d in contrasts]
    adj = holm([s["wilcox_p"] for _, s in stats]) if HAVE_SCIPY else [float("nan")] * len(stats)

    print(f"\n=== {title} ===")
    print(HEADER)
    for (label, s), h in zip(stats, adj):
        pm = f"{s['pos']}/-{s['neg']}"
        print(
            f"{label:<34}{s['n']:>5}{s['mean']:>+10.5f}{s['median']:>+10.5f}"
            f"{s['trimmed']:>+10.5f}{s['ties']:>7}{pm:>9}"
            f"{s['sign_p']:>9.4f}{s['wilcox_p']:>9.4f}{h:>9.4f}"
            f"{s['top5_share']:>8.0f}{s['mean_wo_top5']:>+11.5f}"
        )
    print()
    for label, s in stats:
        print(f"  {label:<32} {verdict(s)}")


def audit_one(path: Path, baseline: str | None, quiet: bool = False) -> bool:
    try:
        arms = load_arms(path)
    except Exception:
        return False
    if not arms:
        return False
    contrasts = build_contrasts(arms, baseline)
    if not contrasts:
        return False
    if not quiet:
        report_block(str(path.parent.name), contrasts)
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="+", help="pilot output dir(s) or a tree to walk")
    ap.add_argument("--baseline", default=None, help="baseline arm for the contrasts")
    ap.add_argument("--all", action="store_true", help="walk each path recursively")
    args = ap.parse_args()

    found = 0
    for raw in args.paths:
        root = Path(raw)
        if not root.exists():
            print(f"[skip] {root} does not exist")
            continue
        if args.all and root.is_dir():
            for summary in sorted(root.rglob("summary.json")):
                found += audit_one(summary, args.baseline)
        elif root.is_dir():
            summary = root / "summary.json"
            if summary.exists():
                found += audit_one(summary, args.baseline)
            else:
                print(f"[skip] {summary} not found")
        else:
            found += audit_one(root, args.baseline)

    if not found:
        print("no auditable summary.json found")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
