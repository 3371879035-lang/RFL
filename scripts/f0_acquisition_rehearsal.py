"""Frozen, non-scientific C3/full-U2 acquisition and CF-5 integration rehearsal."""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import time
import zipfile
from fractions import Fraction

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rfl_rebuild.b2.acquisition import iter_master_baseline
from rfl_rebuild.b2.baseline_artifact import (
    canonical_bytes, digest, iter_verified_material, verify_acquisition, write_acquisition,
)
from rfl_rebuild.b2.evalorder import prefix, prefix_digest
from rfl_rebuild.b2.temporal_initializer import INITIALIZER_ID, temporal_initializer
from rfl_rebuild.b2.training import BaselineAcquisitionPlan, FutureTrainingProtocol, train_curve
from rfl_rebuild.learner.reference import reference_view_from
from rfl_rebuild.solve.dp import solve_reference
from inspect_dev_baseline import inspect

OUT = ROOT / "experiments/v03r/c3_acquisition_integration"
KEYS = (940001, 940002)
CAP = 2  # explicitly a small wiring rehearsal, not the 576-episode construction gate
SPEC = "docs/rebuild/27-F0-ACQUISITION-INTEGRATION.md"


def sources():
    paths = list((ROOT / "src/rfl_rebuild").rglob("*.py"))
    paths += [ROOT / p for p in (SPEC, "scripts/f0_acquisition_rehearsal.py",
              "scripts/inspect_dev_baseline.py", "tests/rebuild/test_b2_baseline_artifact.py",
              "tests/rebuild/test_b2_convergence.py", "docs/rebuild/05-STATISTICAL-PROTOCOL.md",
              "docs/rebuild/12-AMENDMENTS.md", "docs/rebuild/20-B2-DEV-PROTOCOL-FREEZE.md")]
    return {p.relative_to(ROOT).as_posix(): digest(p.read_bytes()) for p in sorted(paths)}


def manifest():
    return {"schema": "c3-acquisition-integration-v1", "role": "OPERATIONAL_REHEARSAL",
            "keys": list(KEYS), "cap": CAP, "bank_size": 1024, "bank_digest": prefix_digest(1024),
            "constants": {"initializer": INITIALIZER_ID, "layer": 1, "alpha": [1, 2],
                          "epsilon": [1, 10], "acquisition_cap": CAP, "production_cap": 576},
            "sources": sources(), "head_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "source_identity": "working-tree-sha256-plus-frozen-archive",
            "scientific_seeds": [], "f0_valid": False, "spec": SPEC}


def write_new(path, value):
    with path.open("xb") as out:
        out.write(canonical_bytes(value))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--plan", action="store_true")
    group.add_argument("--freeze", action="store_true")
    group.add_argument("--run", action="store_true")
    args = parser.parse_args()
    plan = manifest()
    if args.plan:
        print(json.dumps({k: v for k, v in plan.items() if k != "sources"}, indent=2))
        return 0
    if args.freeze:
        OUT.mkdir(parents=True, exist_ok=False)
        write_new(OUT / "manifest.json", plan)
        with zipfile.ZipFile(OUT / "frozen_sources.zip", "x", compression=zipfile.ZIP_DEFLATED) as z:
            for name, h in plan["sources"].items():
                data = (ROOT / name).read_bytes()
                if digest(data) != h:
                    raise RuntimeError("source changed during freeze")
                z.writestr(name, data)
        print("Integration rehearsal frozen: 2 operational keys, cap 2, bank 1024, full-U2 incidence")
        return 0
    frozen_bytes = (OUT / "manifest.json").read_bytes()
    if json.loads(frozen_bytes) != plan:
        raise RuntimeError("frozen manifest/source mismatch")
    with zipfile.ZipFile(OUT / "frozen_sources.zip") as z:
        if set(z.namelist()) != set(plan["sources"]):
            raise RuntimeError("frozen archive inventory mismatch")
        for name, h in plan["sources"].items():
            if digest(z.read(name)) != h:
                raise RuntimeError("frozen archive content mismatch")
    reference = reference_view_from(solve_reference())
    envelope = BaselineAcquisitionPlan(KEYS[0], Fraction(1, 2), Fraction(1, 10), CAP, prefix(1024))
    start = time.perf_counter()
    records = iter_master_baseline(envelope, seeds=KEYS, q_reference=reference,
                                   initializer=temporal_initializer)
    index_path = OUT / "baseline.json"
    index = write_acquisition(index_path, plan=envelope, seeds=KEYS, records=records,
                              constants=plan["constants"], execution={
                                  "head_commit": plan["head_commit"],
                                  "manifest_sha256": digest(frozen_bytes), "sources": plan["sources"]},
                              role=plan["role"])
    acquisition_s = time.perf_counter() - start
    print("Full-U2 acquisition and shards complete; verifying all records", flush=True)
    verify_acquisition(index_path)
    # Independent A91 convenience runner: catches initializer/key/episode wiring drift.
    curves = {seed: train_curve(temporal_initializer(reference), q_reference=reference,
              protocol=FutureTrainingProtocol(seed, envelope.alpha, envelope.epsilon, CAP,
                                              tuple(range(CAP + 1)), envelope.evaluation_bank, 1.0))
              for seed in KEYS}
    checked = 0
    for run in iter_verified_material(index_path):
        if run.mean() != curves[run.seed].values[run.episode]:
            raise RuntimeError("serialized acquisition differs from independent A91 replay")
        checked += 1
    preflight = inspect(index_path)
    if sources() != plan["sources"]:
        raise RuntimeError("source changed during rehearsal")
    report = {"role": plan["role"], "verdict": "INTEGRATION_PASS", "f0_valid": False,
              "scientific_seeds": [], "acquisition_training_episodes": len(KEYS) * CAP,
              "independent_a91_replay_episodes": len(KEYS) * CAP,
              "verified_records": checked, "pairs": index["pairs"],
              "archive_sources_verified": len(plan["sources"]),
              "canonical_shards_verified": True, "a91_means_bit_equal": True,
              "acquisition_runtime_s": round(acquisition_s, 3),
              "total_runtime_s": round(time.perf_counter() - start, 3),
              "baseline_index_sha256": digest(index_path.read_bytes()),
              "manifest_sha256": digest(frozen_bytes), "design_lock_preflight": preflight}
    write_new(OUT / "report.json", report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
