"""Measure the full frozen envelope with operational keys; never authorize F0."""
import argparse
import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b2.baseline_artifact import canonical_bytes, digest, write_acquisition
from rfl_rebuild.b2.design_lock import CONSTANTS, publish_new
from rfl_rebuild.b2.f0_stages import (
    GATES, GATE_PATHS, source_inventory, _committed_sources, require,
    records_for, discard_complete, run_gate_suite, validate_runtime,
)

KEYS = {"smoke": tuple(range(950001, 950006)), "dev_baseline": tuple(range(950006, 950038))}


def benchmark(root, output, *, plan_only=False):
    root, output = pathlib.Path(root), pathlib.Path(output)
    if plan_only:
        return {"status": "PLAN_ONLY", "scientific_seed_draws": 0, "written": False,
                "keys": KEYS, "cap": 576, "bank_size": 1024, "checkpoints": 37 * 577,
                "training_episodes": 37 * 576, "gate_suite": GATES}
    sources = source_inventory(root)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    require(_committed_sources(root, revision, tuple(sources)) == sources, "commit the instrument before benchmarking")
    # An interrupted reservation cannot be silently reused.
    output.mkdir(parents=False, exist_ok=False)
    identity = digest(canonical_bytes(sources))
    publish_new(output / "frozen_inputs.json", {"role": "OPERATIONAL_BENCHMARK", "sources": sources,
                "sources_digest": identity, "instrument_commit": revision, "keys": KEYS, "constants": CONSTANTS})
    start = time.perf_counter()
    codes = run_gate_suite(root)
    suite_s = time.perf_counter() - start
    require(codes == [0] * len(GATES), "benchmark gate suite failed")
    report = {"schema": "f0-runtime-v1", "sources_digest": identity, "suite_s": suite_s,
              "gate_exit_codes": codes, "instrument_commit": revision,
              "gate_artifact_digests": {name: digest((root / name).read_bytes()) for name in GATE_PATHS}}
    for stage, keys in KEYS.items():
        require(source_inventory(root) == sources, "instrument changed during benchmark")
        started = time.perf_counter()
        plan, records = records_for({"constants": CONSTANTS}, keys)
        if stage == "smoke":
            count = discard_complete(records, keys, 576)
        else:
            index = write_acquisition(output / "baseline.json", plan=plan, seeds=keys, records=records,
                constants=CONSTANTS, execution={"sources": sources, "head_commit": revision}, role="OPERATIONAL_REHEARSAL")
            count = index["records"]
        seconds = time.perf_counter() - started
        report[stage] = {"role": "OPERATIONAL_BENCHMARK", "seed_count": len(keys), "keys": list(keys),
                         "cap": 576, "bank_size": 1024, "records": count, "elapsed_s": seconds,
                         "bound_s": 2 * (suite_s + 10 * seconds)}
    require(source_inventory(root) == sources, "instrument changed during benchmark")
    validate_runtime(report, identity)
    publish_new(output / "runtime.json", report)
    return {"status": "MEASURED", "f0_valid": False, "path": str(output / "runtime.json")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=pathlib.Path, default=ROOT / "experiments/v03r/f0_runtime")
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()
    try:
        result = benchmark(ROOT, args.output_dir, plan_only=args.plan)
    except (ProtocolError, OSError) as exc:
        print(json.dumps({"status": "REFUSED", "error": str(exc)}))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
