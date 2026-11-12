"""Freeze and run the isolated, non-scientific C1 construction (no production switch).

python scripts/f0_candidate_construction.py --freeze
python scripts/f0_candidate_construction.py --run
Existing artifacts are never overwritten. Each run validates frozen source hashes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
import time
from fractions import Fraction

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.b2.environment import learned_rollout
from rfl_rebuild.b2.evalorder import prefix, prefix_digest
from rfl_rebuild.b2.initializer_candidate import optimistic_fixture
from rfl_rebuild.b2.numerics import mean
from rfl_rebuild.b2.training import (BaselineAcquisitionPlan, ExogenousEpisode,
                                     episode_rollout, sweep_edits, visited_order)
from rfl_rebuild.learner.reference import reference_view_from
from rfl_rebuild.learner.store import QAddress, LearnerPersistentState
from rfl_rebuild.solve.dp import solve_reference

OUT = ROOT / "experiments/v03r/c1_construction"
SPEC = "docs/rebuild/22-F0-INITIALIZER-CANDIDATE.md"
KEYS = tuple(range(910001, 910033))


def dumps(value):
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def hashes():
    paths = sorted((ROOT / "src/rfl_rebuild").rglob("*.py"))
    paths += [pathlib.Path(__file__).resolve(), ROOT / SPEC]
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in paths}


def new_json(path, data):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(dumps(data))


def frozen_plan(reference):
    fixture = optimistic_fixture(q_reference=reference)
    return {
        "schema": "c1-construction-v1", "role": "NON_SCIENTIFIC_CONSTRUCTION",
        "production_initializer_changed": False, "spec": SPEC,
        "keys": list(KEYS), "alpha": [1, 2], "epsilon": [1, 10],
        "cap": 40, "bank_size": 1024, "bank_digest": prefix_digest(1024),
        "fixture": {"address": repr(fixture.address), "value": fixture.initial_value,
                    "target": fixture.target_value, "best": fixture.best_value,
                    "healthy_action": fixture.healthy_action},
        "sources": hashes(),
        "base_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
    }


def values(learner, bank, reference):
    return tuple(learned_rollout(learner, kappa=u.kappa, tape=u.tape,
                                base_option=u.base_option, q_reference=reference).return_value
                 for u in bank)


def run_key(key, plan, fixture, bank, healthy_values, reference):
    learner = fixture.initialize(q_reference=reference)
    protocol = BaselineAcquisitionPlan(key, Fraction(*plan["alpha"]),
                                      Fraction(*plan["epsilon"]), plan["cap"], bank)
    curves, restored, exact, qs, hits = [], [], [], [], []
    first_moved = None
    entry = False
    for e in range(plan["cap"] + 1):
        measured = values(learner, bank, reference)
        curves.append(mean(measured))
        restored.append(fixture.policy_restored(learner, q_reference=reference)
                        and measured == healthy_values)
        exact.append(fixture.address not in learner.q_overrides)
        qs.append(learner.q_overrides.get(fixture.address, fixture.target_value))
        if e == 0:
            entry = (dict(learner.q_overrides) == {fixture.address: fixture.initial_value}
                     and not fixture.policy_restored(learner, q_reference=reference)
                     and any(a < b for a, b in zip(measured, healthy_values)))
        if e == plan["cap"]:
            break
        before = dict(learner.q_overrides)
        episode = ExogenousEpisode.derive(key, e)
        trace = episode_rollout(learner, episode, protocol=protocol, q_reference=reference)
        addresses = tuple(QAddress(s, c.z, c.m, result.a_cmd)
                          for s, c, result in visited_order(
                              trace, kappa=episode.kappa, phi=episode.tape.phase))
        if fixture.address in addresses:
            hits.append(e)
        edits = sweep_edits(learner, trace, episode, protocol=protocol, q_reference=reference)
        if edits:
            learner.apply_transaction(edits, q_reference=reference)
        if first_moved is None and before != dict(learner.q_overrides):
            first_moved = e + 1
    recovery = next((e for e in range(1, len(restored)) if restored[e]), None)
    return {"key": key, "entry_defect": entry, "curve": curves,
            "first_q_change": first_moved, "behaviour_restored": restored,
            "first_behaviour_recovery": recovery, "exact_override_removed": exact,
            "q_values": qs, "hit_episodes": hits,
            "maintained_after_recovery": recovery is not None and all(restored[recovery:])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--freeze", action="store_true")
    group.add_argument("--run", action="store_true")
    args = parser.parse_args()
    reference = reference_view_from(solve_reference())
    expected = frozen_plan(reference)
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = OUT / "manifest.json"
    if args.freeze:
        new_json(manifest, expected)
        print(f"Frozen, no episodes acquired: {manifest}")
        return 0
    plan = json.loads(manifest.read_text(encoding="utf-8"))
    if plan != expected:
        raise RuntimeError("Frozen plan/source mismatch; refusing acquisition")
    started = time.perf_counter()
    fixture, bank = optimistic_fixture(q_reference=reference), prefix(plan["bank_size"])
    healthy_values = values(LearnerPersistentState(), bank, reference)
    rows = []
    # Exclusive creation preserves even an interrupted attempt; no silent rerun.
    with (OUT / "runs.jsonl").open("x", encoding="utf-8", newline="\n") as stream:
        for key in plan["keys"]:
            row = run_key(key, plan, fixture, bank, healthy_values, reference)
            rows.append(row)
            stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
            stream.flush()
            print(f"key={key} completed {len(rows)}/{len(plan['keys'])}", flush=True)
    checks = {
        "a_entry_defect": all(r["entry_defect"] for r in rows),
        "a_prime_q_changes": any(r["first_q_change"] is not None for r in rows),
        "b1_curve_moves": any(len(set(r["curve"])) > 1 for r in rows),
        "b2_curves_separate": len({tuple(r["curve"]) for r in rows}) > 1,
        "c_behaviour_recovers": any(r["first_behaviour_recovery"] is not None for r in rows),
    }
    # Detect concurrent modifications as well as stale manifests.
    if hashes() != plan["sources"]:
        raise RuntimeError("Source changed during acquisition; evidence cannot be admitted")
    report = {"role": plan["role"], "propositions": checks,
              "verdict": "CANDIDATE_CONSTRUCTION_PASS" if all(checks.values()) else "CANDIDATE_CONSTRUCTION_FAIL",
              "f0_valid": False, "production_initializer_changed": False,
              "runs": len(rows), "episodes": len(rows) * plan["cap"],
              "recovered_runs": sum(r["first_behaviour_recovery"] is not None for r in rows),
              "maintained_runs": sum(r["maintained_after_recovery"] for r in rows),
              "exact_removal_runs": sum(any(r["exact_override_removed"]) for r in rows),
              "hit_episodes": sum(len(r["hit_episodes"]) for r in rows),
              "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
              "runs_sha256": hashlib.sha256((OUT / "runs.jsonl").read_bytes()).hexdigest(),
              "runtime_s": round(time.perf_counter() - started, 3)}
    new_json(OUT / "report.json", report)
    print(dumps(report), flush=True)
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
