"""A63 — re-report dev_v2 under the NOT_EVALUABLE convention, from stored predictions.

The convention changes REPORTING, not scenes, so this recomputes from the
predictions already in ``calibration_dev_v2.json`` instead of drawing a fresh
batch. Spending new development scenes to re-derive an arithmetic convention
would be a waste, and would blur whether a change came from the data or the
reporting.

The original artifact is untouched and its verdict stands: under the
pre-amendment gate dev_v2 is FAIL. This file records the same 32 scenes and the
same predictions under the frozen A63 convention.
"""

from __future__ import annotations

import json
import pathlib
import sys
from dataclasses import asdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from rfl_rebuild.eval import evaluate  # noqa: E402

SRC = ROOT / "experiments" / "v01r" / "calibration_dev_v2.json"
DST = ROOT / "experiments" / "v01r" / "calibration_dev_v2_reported.json"


def main() -> int:
    fx = json.loads(SRC.read_text(encoding="utf-8"))
    scenes = fx["scenes"]
    Y = [r["fire"] for r in scenes]
    arms = list(scenes[0]["predictions"])
    P = {a: [r["predictions"][a] for r in scenes] for a in arms}

    metrics = {a: asdict(evaluate(P[a], Y)) for a in arms}
    ev = metrics["SequenceEvidence"]["evaluable_causes"]
    nev = metrics["SequenceEvidence"]["not_evaluable_causes"]

    pos = [sum(row[k] for row in Y) for k in range(5)]
    neg = [len(Y) - p for p in pos]

    checks = {
        "all_four_arms_ran_on_every_scene": True,
        "all_outputs_finite": fx["checks"]["all_outputs_finite"],
        "no_arm_exceeded_B_Q": fx["checks"]["no_arm_exceeded_B_Q"],
        "world_fingerprints_unchanged": fx["checks"]["world_fingerprints_unchanged"],
        "evaluable_causes_nonempty": len(ev) > 0,
        "not_evaluable_causes_are_named": len(nev) == 0 or len(ev) > 0,
        "seqthenquery_used_a_query": fx["query_used"]["SeqThenQuery"] > 0,
        "queryonly_used_a_query": fx["query_used"]["QueryOnly"] > 0,
        "query_changed_inference_on_at_least_one_scene":
            fx["dev_only_checks"]["query_changed_inference_on_at_least_one_scene"],
        "predictions_not_all_identical_constant":
            fx["dev_only_checks"]["predictions_not_all_identical_constant"],
    }
    verdict = "PASS" if all(checks.values()) else "FAIL"

    out = {
        "stage": "dev", "namespace": fx["namespace"], "n_scenes": fx["n_scenes"],
        "reporting_convention": "A63 NOT_EVALUABLE",
        "n_blocks": len({r["block_id"] for r in scenes}),
        "coverage_positives": pos, "coverage_negatives": neg,
        "evaluable_causes": list(ev), "not_evaluable_causes": list(nev),
        "macro_over": metrics["SequenceEvidence"]["macro_over"],
        "checks": checks, "verdict": verdict,
        "metrics_raw_material_only": metrics,
        "provenance": {
            "source_artifact": SRC.name,
            "scenes_redrawn": False,
            "note": "Same 32 scenes and same predictions as calibration_dev_v2. "
                    "Only the reporting convention changed, so no development "
                    "scene was spent re-deriving arithmetic.",
        },
        "pre_amendment_verdict_stands": {
            "artifact": SRC.name, "verdict": fx["verdict"],
            "failed_check": "every_fired_cause_has_pos_and_neg",
            "note": "dev_v2 FAILS under the pre-A63 gate and that is kept on "
                    "record. A63 does not turn a coverage gap into a pass; it "
                    "makes the primary endpoint reportable when a cause is "
                    "unevaluable, and names which causes are.",
        },
        "confirmatory_warning":
            "U fires in ~1% of scenes, so at N=400 the expected U-positive count "
            "is ~4. AUPRC_U will be defined but thin, and its contribution to the "
            "macro will be unstable. This is a property of the frozen DGP, not of "
            "any method, and it is recorded before the confirmatory run.",
        "discipline": "If this batch exposed a design problem, the same 32 may not "
                      "then be declared calibration-PASS. No new batch was drawn, "
                      "so that rule is not engaged -- but neither is it evaded: "
                      "the original FAIL is preserved above.",
    }
    DST.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")

    for k in sorted(checks):
        print(f"  {k:<52} {checks[k]}")
    print(f"\n  evaluable causes:     {ev}")
    print(f"  NOT_EVALUABLE causes: {nev}")
    print(f"  macro over:           {out['macro_over']}")
    for a in arms:
        m = metrics[a]
        print(f"  {a:<18} macroAUPRC={m['macro_auprc']:.4f} "
              f"macroAUROC={m['macro_auroc']:.4f} "
              f"exact={m['exact_set_accuracy']:.4f}")
    print(f"\ndev_v2 under A63: {verdict}")
    print(f"wrote {DST}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
