"""Authorized validation-only dispatch amendment; original F1 functions unchanged.

All input laws remain the original validator. No cache, reordered selection,
new acquisition, selector edits or changes to the scientific F1 payload.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments/v03r/parallel_verify_20261008"))
import parallel_verify as pv
from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b2 import baseline_artifact as ba, design_lock as dl
from rfl_rebuild.b2.f0_stages import require

ORIGINAL_VERIFY = ba.verify_acquisition
ORIGINAL_ITERATOR = ba.iter_verified_material
ORIGINAL_SHARD = ba._shard_records


class FreshParallelValidation:
    def __init__(self, folder, guard):
        self.folder, self.guard, self.calls = Path(folder), guard, 0
        self.folder.mkdir(exist_ok=False)

    def __call__(self, path):
        self.guard()
        require(pv.MAX_WORKERS == 16 and pv._shard_records is ORIGINAL_SHARD,
                "parallel verifier or worker count changed")
        self.calls += 1
        pass_folder = self.folder / f"pass-{self.calls:03d}"
        pass_folder.mkdir(exist_ok=False)
        dl.publish_new(pass_folder / "reservation.json", {
            "status": "RESERVED_NOT_PASS", "index_path": str(Path(path).resolve()),
            "pass": self.calls, "validation_cache": False})
        result = pv.verify_parallel(path, progress_folder=pass_folder / "workers")
        self.guard()
        require(result["status"] == "ALL_SHARDS_VERIFIED" and not result["validation_reduced"],
                "full original validation did not finish")
        index = ba.read_index(path)
        require(ba.digest(Path(path).read_bytes()) == result["index_sha256"] and
                index["records"] == result["records"] and index["pairs"] == result["pairs"] and
                [r["seed"] for r in result["shards"]] == index["seeds"], "final verified index differs")
        dl.publish_new(pass_folder / "completed.json", result)
        print(f"FULL_VALIDATION_COMPLETED pass={self.calls} shards={len(result['shards'])} "
              f"records={result['records']} elapsed_s={result['elapsed_s']:.3f}", flush=True)
        return index


@contextmanager
def validation_dispatch(validator):
    """In-memory dispatch only; keep the original ordered iterator and all laws."""
    require(ba.verify_acquisition is ORIGINAL_VERIFY and dl.verify_acquisition is ORIGINAL_VERIFY,
            "unexpected installed validator")
    require(ba.iter_verified_material is ORIGINAL_ITERATOR and dl.iter_verified_material is ORIGINAL_ITERATOR
            and ba._shard_records is ORIGINAL_SHARD and pv._shard_records is ORIGINAL_SHARD,
            "original iterator/parser changed")
    ba.verify_acquisition = dl.verify_acquisition = validator
    try:
        yield
    finally:
        ba.verify_acquisition = dl.verify_acquisition = ORIGINAL_VERIFY


def result_code(result):
    return 0 if result["status"] in ("LOCKED", "PLAN_VALID") else 3


def execute(*, root, design_path, manifest_path, output_path, plan_only, validator):
    with validation_dispatch(validator):
        # EXACT original orchestration, checks, selectors, arithmetic and payload.
        return dl.run_lock(root, design_path=design_path, manifest_path=manifest_path,
                           output_path=output_path, plan_only=plan_only)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()
    result, code = None, 2
    try:
        import control_f1_parallel as control
        identity = control.context()
        review = control.p.read_json(HERE / "source_bound_parallel_f1_review.json")
        require(review["decision"] == "VALID" and review["operational_control_files"] == identity["operational_control_files"]
                and review["sources_digest"] == identity["sources_digest"], "new dispatch review missing/mismatched")
        control.require_committed(HERE / "source_bound_parallel_f1_review.json")
        control.require_parent_exited()
        def guard():
            require(control.context() == identity, "bound input/source/operational drift")
        validator = FreshParallelValidation(HERE / ("plan_validation" if args.plan else "f1_validation"), guard)
        result = execute(root=ROOT, design_path=control.INDEX, manifest_path=control.MANIFEST,
                         output_path=ROOT / "experiments/v03r/dev_lock.json", plan_only=args.plan,
                         validator=validator)
        guard()
        code = result_code(result)
        dl.publish_new(HERE / ("plan_execution.json" if args.plan else "f1_execution.json"), {
            "role": "SUPPLEMENTAL_OPERATIONAL_EXECUTION_NOT_NEW_F0_OR_NEW_TIMING",
            "result": result, "native_result_code": code, "full_validation_passes": validator.calls,
            "review_sha256": ba.digest((HERE / "source_bound_parallel_f1_review.json").read_bytes()),
            "binding": identity, "selection_order_changed": False, "scientific_parameters_changed": False})
    except Exception as exc:
        code = 2
        result = {"status": "PROTOCOL_ERROR", "message": str(exc), "error_type": type(exc).__name__, "written": False}
    print("F1_RESULT_JSON=" + json.dumps(result, sort_keys=True, allow_nan=False), flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
