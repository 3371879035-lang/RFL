"""Recompute a stage verdict from its stored artifact, without re-running scenes.

The confirmatory run generated 400 scenes and ran four arms on each (15.9M
memoised rollouts) and then reported FAIL because a check marked INFORMATIONAL
under A63 was still being ANDed into the gate. The data is fine; only the verdict
rule was wrong. Recomputing the verdict from the artifact costs nothing and
avoids spending another multi-hour run to fix arithmetic.
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else "conf"
    path = ROOT / "experiments" / "v01r" / f"calibration_{name}_v2.json"
    d = json.loads(path.read_text(encoding="utf-8"))

    gating = {k: v for k, v in d["checks"].items()}
    gating.update({k: v for k, v in d["dev_only_checks"].items()
                   if not k.endswith("_INFORMATIONAL")})
    informational = {k: v for k, v in d["dev_only_checks"].items()
                     if k.endswith("_INFORMATIONAL")}
    failed = sorted(k for k, v in gating.items() if v is not True)
    verdict = "PASS" if not failed else "FAIL"

    d["applied_to_this_stage"] = sorted(gating)
    d["informational_not_gating"] = informational
    d["failed_gating_checks"] = failed
    d["verdict"] = verdict
    d["verdict_recomputed"] = {
        "reason": "A63: coverage is INFORMATION, not a gate. The original run "
                  "ANDed coverage_every_cause_has_both_classes_INFORMATIONAL "
                  "into the verdict, which A63 forbids.",
        "scenes_redrawn": False,
        "rollouts_not_repeated": d.get("rollouts_memoised"),
        "original_verdict": "FAIL",
    }
    path.write_text(json.dumps(d, indent=1, default=str), encoding="utf-8")

    print(f"{name}: gating checks = {len(gating)}, failed = {failed or 'none'}")
    print(f"  informational (not gating): {informational}")
    print(f"  verdict: FAIL -> {verdict}")
    pc = d.get("primary_contrast") or {}
    c = pc.get("cumulative")
    if c:
        print(f"\n  PRIMARY (SeqThenQuery vs DirectFeedback, macro AUPRC)")
        print(f"    alt  = {c['batch_macro_auprc_alt']:.4f}")
        print(f"    base = {c['batch_macro_auprc_base']:.4f}")
        print(f"    delta = {c['batch_macro_delta']:.4f}  "
              f"({c['position_vs_delta_min']} Delta_min = {c['delta_min']})")
        print(f"    tie_fraction = {c['tie_fraction']:.3f}   "
              f"wins = {c['wins']}  losses = {c['losses']}  "
              f"sign p = {c['sign_test_p_two_sided']:.3g}")
        print(f"    top5_share_of_total_delta = {c['top5_share_of_total_delta']:.4f}")
        for b, v in pc.get("per_block", {}).items():
            print(f"    {b}: delta = {v['batch_macro_delta']:.4f} "
                  f"({v['position_vs_delta_min']})  n = {v['n']}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
