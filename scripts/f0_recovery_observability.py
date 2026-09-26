"""Seedless check: can the fixed recovery threshold see the initial local defect?

No training stream, selector, effect-size choice or operational artifact is read.
The output is a necessary-condition audit, not an F0 design lock.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.b2.environment import learned_rollout
from rfl_rebuild.b2.evalorder import prefix
from rfl_rebuild.b2.initializer import baseline_initializer
from rfl_rebuild.b2.initializer_candidate import optimistic_fixture
from rfl_rebuild.b2.numerics import mean
from rfl_rebuild.b2.utility import RECOVERY_FRACTION, recovery_time
from rfl_rebuild.learner.reference import reference_view_from
from rfl_rebuild.learner.store import LearnerPersistentState
from rfl_rebuild.solve.dp import solve_reference


def evaluate(learner, sample, reference):
    return tuple(learned_rollout(learner, kappa=u.kappa, tape=u.tape,
                                base_option=u.base_option, q_reference=reference).return_value
                 for u in sample)


def audit():
    reference = reference_view_from(solve_reference())
    fixture = optimistic_fixture(q_reference=reference)
    learners = {"healthy": LearnerPersistentState(),
                "rev4": baseline_initializer(q_reference=reference),
                "c1": fixture.initialize(q_reference=reference)}
    rows = []
    for n in (100, 256, 512, 1024, 5760):
        sample = prefix(n)
        vectors = {name: evaluate(learner, sample, reference) for name, learner in learners.items()}
        levels = {name: mean(vector) for name, vector in vectors.items()}
        threshold = RECOVERY_FRACTION * levels["healthy"]
        # This curve is a no-learning negative control, NOT acquired data.
        # With all checkpoints above threshold, tau=0 for every grid with >=3 points.
        no_learning = {
            name: recovery_time((levels[name],) * 3, (0, 1, 2),
                                pre_level=levels["healthy"], t_max=2)
            for name in ("rev4", "c1")}
        rows.append({"bank_size": n, "levels": levels, "threshold": threshold,
                     "deficit": levels["healthy"] - levels["c1"],
                     "degraded_scenes": sum(a < b for a, b in zip(vectors["c1"], vectors["healthy"])),
                     "old_and_new_vectors_identical": vectors["rev4"] == vectors["c1"],
                     "no_learning_recovery_time": no_learning,
                     "defect_below_recovery_threshold": levels["c1"] < threshold})
    observable = all(row["defect_below_recovery_threshold"] for row in rows[:4])
    return {"schema": "seedless-recovery-observability-v1", "scientific_seeds": [],
            "operational_keys": [], "selector_executed": False,
            "verdict": "ENTRY_DEFICIT_OBSERVABLE" if observable else "ENTRY_DEFICIT_BELOW_ENDPOINT_RESOLUTION",
            "candidate_admitted_as_f0_baseline": False,
            "rows": rows, "source_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()}


def main():
    report = audit()
    out = ROOT / "experiments/v03r/c1_recovery_observability.json"
    with out.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["verdict"] == "ENTRY_DEFICIT_OBSERVABLE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
