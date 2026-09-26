"""Read-only CF-5 integrity preflight; this is not the F1 statistical selector."""
import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b2.baseline_artifact import verify_acquisition
from rfl_rebuild.b2.temporal_initializer import ACQUISITION_CAP, INITIALIZER_ID


def inspect(path):
    index = verify_acquisition(path)  # every shard, before considering any design field
    blockers = []
    if index["role"] != "DEVELOPMENT_BASELINE":
        blockers.append("OPERATIONAL_DATA_IS_NOT_DEVELOPMENT_DATA")
    if index["seeds"] != list(range(1000, 1032)):
        blockers.append("NOT_THE_FROZEN_DEVELOPMENT_SEED_SET")
    if index["bank_size"] != 1024 or index["episodes"] != list(range(ACQUISITION_CAP + 1)):
        blockers.append("NOT_THE_FULL_C3_ACQUISITION_ENVELOPE")
    if index["constants"].get("initializer") != INITIALIZER_ID:
        blockers.append("NOT_THE_EXPLICIT_C3_INITIALIZER")
    # Repository readiness, not findings inferred from these baseline values.
    blockers.extend([
        "F0_C3_AMENDMENT_AND_STAGE_MANIFEST_NOT_VALIDATED",
        "F0_SMOKE_AND_BASELINE_STAGE_RUNNERS_NOT_COMPLETED",
        "P_RMST_PRACTICAL_THRESHOLD_NOT_RATIFIED",
    ])
    return {"artifact_valid": True, "schema": index["schema"], "role": index["role"],
            "records": index["records"], "pairs": index["pairs"],
            "design_metrics_computed": False, "f1_lock_written": False,
            "ready_for_design_lock": not blockers, "blockers": blockers}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        result = inspect(args.design)
    except (ProtocolError, OSError) as exc:
        print(json.dumps({"artifact_valid": False, "error": str(exc)}))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ready_for_design_lock"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
