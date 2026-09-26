"""C3 isolated operational construction. Freeze before run; all outputs exclusive."""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import time
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import f0_zero_baseline_construction as common
from f0_temporal_static import layer_edits, selection
from rfl_rebuild.b2.evalorder import prefix, prefix_digest
from rfl_rebuild.b2.utility import recovery_time
from rfl_rebuild.b2.zero_baseline_candidate import PartitionedZeroLearner
from rfl_rebuild.learner.reference import reference_view_from
from rfl_rebuild.learner.store import LearnerPersistentState
from rfl_rebuild.solve.dp import solve_reference

OUT = ROOT / "experiments/v03r/c3_construction"
SPEC = "docs/rebuild/25-F0-TEMPORAL-BASELINE-CANDIDATE.md"
KEYS = tuple(range(930001, 930033))


class TemporalLearner(PartitionedZeroLearner):
    def __init__(self, reference, *, layer):
        self.reference = reference
        grouped = {(s.kappa, s.phi, z): [] for s, z, m in reference.rows}
        for edit in layer_edits(reference, layer):
            a = edit.address
            grouped[(a.state.kappa, a.state.phi, a.z)].append(edit)
        self.parts = {}
        for cell, edits in sorted(grouped.items()):
            learner = LearnerPersistentState()
            learner.apply_transaction(edits, q_reference=reference)
            self.parts[cell] = learner
        self._returns = {cell: self.evaluate_cell(cell) for cell in self.parts}


def sources():
    hashes = common.sources()
    for name in (SPEC, "scripts/f0_temporal_construction.py", "scripts/f0_temporal_static.py",
                 "tests/rebuild/test_b2_temporal_baseline_candidate.py"):
        hashes[name] = common.digest((ROOT / name).read_bytes())
    return hashes


def static_report(reference):
    report = selection(reference)
    layer = report["selected_layer"]
    if layer is None:
        return report
    learner = TemporalLearner(reference, layer=layer)
    learner.validate_cache(prefix(5760))
    selected = report["layers_inspected"][-1]
    report["no_learning_censored"] = all(
        recovery_time((v,) * 3, (0, 1, 2), pre_level=report["healthy"][n], t_max=2) is None
        for n, v in selected["means"].items())
    report["exact_edits"] = [{"address": repr(e.address), "value": e.value}
                              for e in layer_edits(reference, layer)]
    return report


def plan_for(static):
    return {"schema": "c3-construction-v1", "role": "NON_SCIENTIFIC_CONSTRUCTION",
            "keys": list(KEYS), "layer": static["selected_layer"],
            "budget": {"cells": 48, "horizon": 12, "cap": 576},
            "alpha": [1, 2], "epsilon": [1, 10], "bank_size": 1024,
            "bank_digest": prefix_digest(1024), "cache_checkpoints": [0, 12, 288, 576],
            "sources": sources(), "spec": SPEC,
            "seedless_sha256": common.digest((OUT / "seedless.json").read_bytes()),
            "production_initializer_changed": False, "scientific_endpoints_changed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--freeze", action="store_true")
    group.add_argument("--run", action="store_true")
    args = parser.parse_args()
    reference = reference_view_from(solve_reference())
    OUT.mkdir(parents=True, exist_ok=True)
    if args.freeze:
        static = static_report(reference)
        common.write_new(OUT / "seedless.json", static)
        if static["selected_layer"] is None or not static["no_learning_censored"]:
            return 1
        plan = plan_for(static)
        common.write_new(OUT / "manifest.json", plan)
        with zipfile.ZipFile(OUT / "frozen_sources.zip", "x", compression=zipfile.ZIP_DEFLATED) as z:
            for name, h in plan["sources"].items():
                data = (ROOT / name).read_bytes()
                if common.digest(data) != h:
                    raise RuntimeError("source changed during freeze")
                z.writestr(name, data)
        print(f"C3 frozen: layer={plan['layer']}, cap=576, 32 fresh operational keys")
        return 0
    static = json.loads((OUT / "seedless.json").read_text(encoding="utf-8"))
    manifest_bytes = (OUT / "manifest.json").read_bytes()
    plan = json.loads(manifest_bytes)
    if plan != plan_for(static):
        raise RuntimeError("C3 manifest/source mismatch")
    if plan["layer"] is None or not static["no_learning_censored"]:
        raise RuntimeError("C3 static gate not passed")
    healthy = static["healthy"]["1024"]
    bank = prefix(1024)
    summaries, distinct = [], set()
    start = time.perf_counter()
    with (OUT / "runs.jsonl").open("x", encoding="utf-8", newline="\n") as stream:
        for key in plan["keys"]:
            row = common.acquire(key, plan, bank, healthy, reference,
                                 factory=lambda r: TemporalLearner(r, layer=plan["layer"]))
            stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
            stream.flush()
            distinct.add(tuple(row["curve"]))
            summaries.append({k: v for k, v in row.items() if k not in ("curve", "cell_return_events", "initial_cells")})
            print(f"completed {len(summaries)}/32 key={key}", flush=True)
    if sources() != plan["sources"]:
        raise RuntimeError("C3 source changed during acquisition")
    checks = {"initial_deficit_observable": static["no_learning_censored"],
              "ordinary_q_moves": all(r["first_q_change"] is not None for r in summaries),
              "curve_moves": any(len(set(c)) > 1 for c in distinct),
              "curves_separate": len(distinct) > 1,
              "positive_maintained_recovery": any(r["recovery_episode"] is not None and r["recovery_episode"] > 0
                                                  for r in summaries),
              "fresh_cache_checks_passed": all(r["cache_verified_at"] == plan["cache_checkpoints"] for r in summaries)}
    report = {"role": plan["role"], "checks": checks,
              "verdict": "CANDIDATE_CONSTRUCTION_PASS" if all(checks.values()) else "CANDIDATE_CONSTRUCTION_FAIL",
              "f0_valid": False, "production_initializer_changed": False,
              "scientific_endpoints_changed": False, "layer": plan["layer"], "episodes": 32 * 576,
              "recovered_runs": sum(r["recovery_episode"] is not None for r in summaries),
              "maintained_through_end": sum(r["maintained_through_end"] for r in summaries),
              "summaries": summaries, "runtime_s": round(time.perf_counter() - start, 3),
              "manifest_sha256": common.digest(manifest_bytes),
              "runs_sha256": common.digest((OUT / "runs.jsonl").read_bytes())}
    common.write_new(OUT / "report.json", report)
    print(json.dumps({k: v for k, v in report.items() if k != "summaries"}, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
