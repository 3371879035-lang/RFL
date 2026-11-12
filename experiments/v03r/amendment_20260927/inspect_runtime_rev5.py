"""Read-only runtime progress and final integrity; never inspect effect sizes."""
import argparse
import json
import pathlib
import statistics
import sys
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b2.baseline_artifact import canonical_bytes, digest, verify_acquisition
from rfl_rebuild.b2.design_lock import CONSTANTS, publish_new
from rfl_rebuild.b2.f0_stages import (
    GATE_PATHS, read_json, require, source_inventory, _committed_sources, validate_runtime,
)

EXPECTED_KEYS = {"smoke": list(range(970001, 970006)), "dev_baseline": list(range(970006, 970038))}


def scan_progress(directory, keys):
    """Metadata only. Opening the next shard proves the prior writer loop ended.

    The last visible shard remains unconfirmed even if its size looks complete.
    This is a lower bound inferred from the frozen serial writer, not a hash check
    and not proof the process is alive. No gzip payload or outcome is opened.
    """
    directory = pathlib.Path(directory)
    expected = [f"seed-{key:06d}.jsonl.gz" for key in keys]
    actual = {p.name for p in directory.glob("*") if p.is_file()} if directory.exists() else set()
    require(actual.issubset(expected), "unexpected file in runtime shard directory")
    present = [name in actual for name in expected]
    count = sum(present)
    require(present == [True] * count + [False] * (len(keys) - count), "runtime shard sequence has a gap")
    files = []
    for i, name in enumerate(expected[:count]):
        stat = (directory / name).stat()
        files.append({"seed": keys[i], "bytes": stat.st_size, "mtime": stat.st_mtime,
                      "prior_writer_loop_complete": i < count - 1})
    closed = files[:-1]
    intervals = [b["mtime"] - a["mtime"] for a, b in zip(closed, closed[1:])]
    median = statistics.median(intervals) if len(intervals) >= 2 and all(t > 0 for t in intervals) else None
    return {"shards_visible": count, "completed_dev_runs_lower_bound": len(closed),
            "last_visible_seed": files[-1]["seed"] if files else None,
            "recent_seconds_per_shard": median,
            "rough_remaining_dev_seconds": median * (len(keys) - len(closed)) if median else None,
            "files": files, "hashes_verified": False, "outcome_payloads_opened": False,
            "eta_is_not_a_runtime_bound": True}


def frozen_inputs(root):
    root = pathlib.Path(root)
    path = root / "experiments/v03r/f0_runtime_rev5/frozen_inputs.json"
    frozen = read_json(path)
    require(frozen.get("role") == "OPERATIONAL_BENCHMARK", "wrong runtime role")
    require(frozen.get("keys") == EXPECTED_KEYS, "runtime operational key assignment changed")
    require(frozen.get("constants") == CONSTANTS, "runtime constants changed")
    require(frozen["sources_digest"] == digest(canonical_bytes(frozen["sources"])), "invalid source digest")
    require(source_inventory(root) == frozen["sources"], "frozen instrument changed")
    require(_committed_sources(root, frozen["instrument_commit"], tuple(frozen["sources"])) == frozen["sources"],
            "instrument bytes do not belong to frozen commit")
    return frozen


def verify_metadata(frozen, runtime, index, actual_gate_digests):
    """Validate cross-artifact binding before the expensive full-shard read."""
    validate_runtime(runtime, frozen["sources_digest"])
    require(runtime.get("instrument_commit") == frozen["instrument_commit"], "runtime revision mismatch")
    require(runtime.get("gate_artifact_digests") == actual_gate_digests, "runtime gate artifact drift")
    require(set(actual_gate_digests) == set(GATE_PATHS), "runtime gate artifact inventory mismatch")
    for stage in EXPECTED_KEYS:
        require(runtime[stage]["keys"] == frozen["keys"][stage], "runtime keys differ from frozen inputs")
    require(index["role"] == "OPERATIONAL_REHEARSAL", "benchmark index cannot claim development role")
    require(index["seeds"] == frozen["keys"]["dev_baseline"], "benchmark index seed mismatch")
    require(index["episodes"] == list(range(577)) and index["bank_size"] == 1024,
            "benchmark acquisition envelope mismatch")
    require(index["constants"] == frozen["constants"], "benchmark index constants mismatch")
    require(index["execution"].get("head_commit") == frozen["instrument_commit"]
            and index["execution"].get("sources") == frozen["sources"], "benchmark index provenance mismatch")
    require(index["records"] == runtime["dev_baseline"]["records"] == 32 * 577,
            "runtime acquisition count mismatch")


def inspect(root, *, verify=False):
    root = pathlib.Path(root)
    frozen = frozen_inputs(root)
    output = root / "experiments/v03r/f0_runtime_rev5"
    runtime_path, index_path = output / "runtime.json", output / "baseline.json"
    progress = scan_progress(output / "baseline", frozen["keys"]["dev_baseline"])
    result = {"observed_at": datetime.now(timezone.utc).isoformat(), "f0_valid": False,
              "instrument_commit": frozen["instrument_commit"], "sources_digest": frozen["sources_digest"],
              "inspector_sha256": digest(pathlib.Path(__file__).read_bytes()),
              "formal_stage_authorized": False, "metrics_computed": False,
              "runtime_file_present": runtime_path.exists(), "index_file_present": index_path.exists(),
              "process_liveness_checked": False, "progress": progress,
              "smoke_shaped_runs_completed_by_execution_order": 5 if progress["shards_visible"] else 0,
              "status": "AWAITING_FINAL_VERIFICATION" if runtime_path.exists() else "INCOMPLETE"}
    if not verify:
        return result
    require(runtime_path.is_file() and index_path.is_file(), "runtime measurement not complete; no final evidence")
    from rfl_rebuild.b2.baseline_artifact import read_index
    runtime_hash, index_hash = digest(runtime_path.read_bytes()), digest(index_path.read_bytes())
    runtime, index = read_json(runtime_path), read_index(index_path)
    gates = {name: digest((root / name).read_bytes()) for name in GATE_PATHS}
    verify_metadata(frozen, runtime, index, gates)
    verify_acquisition(index_path)
    require(frozen_inputs(root) == frozen, "instrument changed during verification")
    require(digest(runtime_path.read_bytes()) == runtime_hash and digest(index_path.read_bytes()) == index_hash,
            "completion artifact changed during verification")
    require({name: digest((root / name).read_bytes()) for name in GATE_PATHS} == gates,
            "gate artifacts changed during verification")
    return {**result, "status": "MEASURED_AND_VERIFIED", "all_shards_verified": True,
            "verified_dev_runs": len(index["seeds"]),
            "runtime_sha256": runtime_hash, "index_sha256": index_hash,
            "dev_records": index["records"], "smoke_records": runtime["smoke"]["records"],
            "bounds_seconds": {stage: runtime[stage]["bound_s"] for stage in EXPECTED_KEYS}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--output", type=pathlib.Path, help="Optional NEW snapshot file; never overwrite")
    args = parser.parse_args()
    try:
        report = inspect(ROOT, verify=args.verify)
        if args.output:
            publish_new(args.output, report)
    except (ProtocolError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({"status": "REFUSED", "error": str(exc), "f0_valid": False}))
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
