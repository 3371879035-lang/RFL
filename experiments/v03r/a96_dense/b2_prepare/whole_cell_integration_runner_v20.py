"""Closed full current preparation suite; engineering only, no SCI launcher."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

FOLDER = Path(__file__).resolve().parent
sys.path.insert(0, str(FOLDER))
import readiness as ready


def file_sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    spec = json.loads((FOLDER / "whole_cell_inputs_candidate_v20.json").read_text(encoding="utf-8"))
    before = {name: file_sha(ready.ROOT / name) for name in spec["input_file_hashes"]}
    if before != spec["input_file_hashes"]:
        raise ready.ProtocolError("complete v20 parent/addon/test/runner input bytes changed")
    parent_before = ready.load_parent()
    expected_modules = tuple(spec["complete_preparation_test_modules"])
    actual_modules = tuple(sorted(p.stem for p in FOLDER.glob("test_*.py")))
    if actual_modules != expected_modules:
        raise ready.ProtocolError("full fixed candidate test modules differ; no subset discovery")
    suite = unittest.TestSuite()
    for name in expected_modules: suite.addTests(unittest.defaultTestLoader.loadTestsFromName(name))
    if suite.countTestCases() != spec["expected_case_count"]:
        raise ready.ProtocolError("full fixed candidate case count differs")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    parent_after = ready.load_parent()
    after = {name: file_sha(ready.ROOT / name) for name in spec["input_file_hashes"]}
    if before != after or parent_before != parent_after:
        raise ready.ProtocolError("input/313/native153/F1 bytes changed during full candidate suite")
    if not result.wasSuccessful() or result.skipped:
        return 1
    import test_whole_cell_source_candidate_v20 as tested
    import whole_cell_source_candidate_v20 as whole
    cls = tested.WholeCellTests
    raw = whole.whole_cell_maps_audit(cls.handle, cls.diagnostic_run, cls.source)
    # Full native-in-process construction retained, never a summary-only receipt.
    # Printing to stdout is captured by the command wrapper; this file writes no
    # artifacts, launches no subprocess and accepts no environment seed/CLI plan.
    print("FULL_WHOLE_CELL_RAW_V20=" + json.dumps(raw, sort_keys=True, allow_nan=False))
    import pre_census_source_candidate as census
    record = whole._ISSUED[cls.handle]
    cd = census._checked(record.census, cls.diagnostic_run, cls.source)
    print("FULL_WHOLE_CELL_PRE_CENSUS_V20=" + json.dumps({
        "role": "COMPLETE_STORED_SEEDLESS_PRE_CENSUS_NOT_SCIENTIFIC_RECEIPT",
        "ordered_rows": [[list(s.key), h, list(flags), ts, rs]
                         for s, h, flags, ts, rs in cd.census],
        "science_origin_authenticated": False}, sort_keys=True, allow_nan=False))
    print("FULL_PREPARATION_SUITE_V20=" + json.dumps({
        "schema": "a96-full-preparation-suite-v20-not-collection",
        "input_hashes_before": before, "input_hashes_after": after,
        "ordered_test_modules": list(expected_modules),
        "tests_run": result.testsRun, "failures": len(result.failures),
        "errors": len(result.errors), "skipped": len(result.skipped),
        "parent_sources_digest": parent_after["sources_digest"],
        "lock_sha256": parent_after["lock_sha256"],
        "original_regression_and_six_serial_B2_gates_executed": False,
        "full_dense_B2_workload_resources_certified": False,
        "scientific_keys_allocated": False, "scientific_collection_started": False,
        "collection_authorized": False, "scientific_claim_authorized": False,
        "research_complete": False}, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__": raise SystemExit(main())
