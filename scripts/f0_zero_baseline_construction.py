"""Freeze then execute C2's one operational construction. Never enables production.

python scripts/f0_zero_baseline_construction.py --freeze
python scripts/f0_zero_baseline_construction.py --run
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
import time
import zipfile
from fractions import Fraction

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.b2.environment import learned_rollout
from rfl_rebuild.b2.evalorder import prefix, prefix_digest
from rfl_rebuild.b2.numerics import mean
from rfl_rebuild.b2.training import BaselineAcquisitionPlan, ExogenousEpisode
from rfl_rebuild.b2.utility import recovery_time
from rfl_rebuild.b2.zero_baseline_candidate import PartitionedZeroLearner, envelope
from rfl_rebuild.env.kernel import State, START, initial_control
from rfl_rebuild.learner.reference import reference_view_from
from rfl_rebuild.learner.store import LearnerPersistentState
from rfl_rebuild.solve.dp import solve_reference

OUT = ROOT / "experiments/v03r/c2_construction"
KEYS = tuple(range(920001, 920033))
SPEC = "docs/rebuild/24-F0-ZERO-BASELINE-CANDIDATE.md"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sources():
    paths = sorted((ROOT / "src/rfl_rebuild").rglob("*.py"))
    paths += [ROOT / SPEC, pathlib.Path(__file__).resolve(),
              ROOT / "tests/rebuild/test_b2_zero_baseline_candidate.py"]
    return {p.relative_to(ROOT).as_posix(): digest(p.read_bytes()) for p in paths}


def write_new(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as f:
        json.dump(value, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")


def seedless(reference):
    learner = PartitionedZeroLearner(reference)
    bank = prefix(5760)
    learner.validate_cache(bank)
    healthy = LearnerPersistentState()
    healthy_cells = {}
    for u in bank:
        cell = (u.kappa, u.phase, u.base_option)
        if cell not in healthy_cells:
            healthy_cells[cell] = learned_rollout(healthy, kappa=u.kappa, tape=u.tape,
                                                  base_option=u.base_option,
                                                  q_reference=reference).return_value
    healthy_values = tuple(healthy_cells[(u.kappa, u.phase, u.base_option)] for u in bank)
    initial_values = learner.bank_values(bank)
    root_lower_bound = []
    for u in bank:
        s = State(*START, t=0, kappa=u.kappa, phi=u.phase)
        row = reference.rows[(s, u.base_option, initial_control(u.base_option).m)]
        root_lower_bound.append(min(row.values()))
    rows = []
    for n in (100, 256, 512, 1024, 5760):
        h, zero = mean(healthy_values[:n]), mean(initial_values[:n])
        bound = mean(root_lower_bound[:n])
        rows.append({"bank_size": n, "healthy": h, "zero_q": zero,
                     "threshold": 0.95 * h, "zero_below_threshold": zero < .95 * h,
                     "no_learning_recovery": recovery_time((zero,) * 3, (0, 1, 2), pre_level=h, t_max=2),
                     "t0_only_lower_bound": bound,
                     "t0_only_cannot_clear_threshold": bound > .95 * h})
    return {"role": "SEEDLESS_CONSTRUCTION", "scientific_seeds": [],
            "rows": rows, "passes": all(r["zero_below_threshold"] and
                                          r["no_learning_recovery"] is None for r in rows)}


def expected_plan(reference):
    return {"schema": "c2-construction-v1", "role": "NON_SCIENTIFIC_CONSTRUCTION",
            "keys": list(KEYS), "budget": envelope(reference),
            "alpha": [1, 2], "epsilon": [1, 10], "bank_size": 1024,
            "bank_digest": prefix_digest(1024), "sources": sources(), "spec": SPEC,
            "cache_checkpoints": [0, 12, envelope(reference)["cap"] // 2, envelope(reference)["cap"]],
            "production_initializer_changed": False, "scientific_endpoints_changed": False,
            "base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()}


def acquire(key, plan, bank, healthy_level, reference, *, factory=PartitionedZeroLearner):
    cap = plan["budget"]["cap"]
    protocol = BaselineAcquisitionPlan(key, Fraction(*plan["alpha"]), Fraction(*plan["epsilon"]), cap, bank)
    learner = factory(reference)
    curves = [learner.bank_mean(bank)]
    initial_cells = [[list(c), v] for c, v in learner._returns.items()]
    events = []
    first_change = None
    learner.validate_cache(bank)
    for e in range(cap):
        xi = ExogenousEpisode.derive(key, e)
        changed = learner.train(xi, protocol=protocol)
        if changed and first_change is None:
            first_change = e + 1
        cell = (xi.kappa, xi.tape.phase, xi.proposal)
        events.append([list(cell), learner._returns[cell]])
        curves.append(learner.bank_mean(bank))
        if e + 1 in plan["cache_checkpoints"]:
            learner.validate_cache(bank)
        if (e + 1) % 2304 == 0:
            print(f"key={key} episode={e+1}/{cap}", flush=True)
    tau = recovery_time(curves, range(cap + 1), pre_level=healthy_level, t_max=cap)
    # No endpoint selection or effect estimation. tau is the fixed gate's witness.
    return {"key": key, "curve": curves, "first_q_change": first_change,
            "recovery_episode": tau, "initial_cells": initial_cells,
            "cell_return_events": events,
            "cache_verified_at": plan["cache_checkpoints"],
            "final_mean": curves[-1],
            "maintained_through_end": tau is not None and all(v >= .95 * healthy_level for v in curves[tau:])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--freeze", action="store_true")
    group.add_argument("--run", action="store_true")
    args = parser.parse_args()
    reference = reference_view_from(solve_reference())
    expected = expected_plan(reference)
    OUT.mkdir(parents=True, exist_ok=True)
    if args.freeze:
        static = seedless(reference)
        write_new(OUT / "seedless.json", static)
        if not static["passes"]:
            print("Seedless negative-control gate failed; no stream is authorised")
            return 1
        expected["seedless_sha256"] = digest((OUT / "seedless.json").read_bytes())
        write_new(OUT / "manifest.json", expected)
        with zipfile.ZipFile(OUT / "frozen_sources.zip", "x", compression=zipfile.ZIP_DEFLATED) as z:
            for name, h in expected["sources"].items():
                data = (ROOT / name).read_bytes()
                if digest(data) != h:
                    raise RuntimeError("Source changed during freeze")
                z.writestr(name, data)
        print(json.dumps({"frozen": True, "budget": expected["budget"], "seedless": static}, indent=2))
        return 0
    manifest_bytes = (OUT / "manifest.json").read_bytes()
    plan = json.loads(manifest_bytes)
    expected["seedless_sha256"] = digest((OUT / "seedless.json").read_bytes())
    if plan != expected:
        raise RuntimeError("Manifest/source mismatch")
    static = json.loads((OUT / "seedless.json").read_text(encoding="utf-8"))
    if not static["passes"]:
        raise RuntimeError("Seedless gate not passed")
    healthy = next(r["healthy"] for r in static["rows"] if r["bank_size"] == 1024)
    bank = prefix(1024)
    start = time.perf_counter()
    summaries, curves = [], set()
    with (OUT / "runs.jsonl").open("x", encoding="utf-8", newline="\n") as f:
        for key in plan["keys"]:
            row = acquire(key, plan, bank, healthy, reference)
            f.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
            f.flush()
            curves.add(tuple(row["curve"]))
            summaries.append({k: v for k, v in row.items() if k not in ("curve", "cell_return_events", "initial_cells")})
            print(f"completed {len(summaries)}/{len(plan['keys'])} key={key}", flush=True)
    if sources() != plan["sources"]:
        raise RuntimeError("Source changed during acquisition")
    checks = {"initial_deficit_observable": static["passes"],
              "ordinary_q_moves": all(r["first_q_change"] is not None for r in summaries),
              "curve_moves": any(len(set(c)) > 1 for c in curves),
              "curves_separate": len(curves) > 1,
              "positive_maintained_recovery": any(r["recovery_episode"] is not None and r["recovery_episode"] > 0
                                                  for r in summaries),
              "fresh_cache_checks_passed": all(r["cache_verified_at"] == plan["cache_checkpoints"] for r in summaries)}
    report = {"role": plan["role"], "checks": checks,
              "verdict": "CANDIDATE_CONSTRUCTION_PASS" if all(checks.values()) else "CANDIDATE_CONSTRUCTION_FAIL",
              "f0_valid": False, "production_initializer_changed": False,
              "episodes": len(plan["keys"]) * plan["budget"]["cap"],
              "recovered_runs": sum(r["recovery_episode"] is not None for r in summaries),
              "recovery_witnesses": {r["key"]: r["recovery_episode"] for r in summaries},
              "summaries": summaries, "runtime_s": round(time.perf_counter() - start, 3),
              "manifest_sha256": digest(manifest_bytes),
              "runs_sha256": digest((OUT / "runs.jsonl").read_bytes())}
    write_new(OUT / "report.json", report)
    print(json.dumps({k: v for k, v in report.items() if k != "summaries"}, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
