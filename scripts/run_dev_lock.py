"""F1 baseline-only combined design/threshold lock; refuses before F0 authorization."""
import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b2.design_lock import run_lock, publish_new
from rfl_rebuild.b2.protocol_profile import STAGE_ROOT
from rfl_rebuild.b2.f0_stages import MANIFEST_PATH


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", type=pathlib.Path, required=True)
    parser.add_argument("--manifest", type=pathlib.Path, default=ROOT / MANIFEST_PATH)
    parser.add_argument("--execution-dir", type=pathlib.Path)
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()
    try:
        result = run_lock(ROOT, design_path=args.design, manifest_path=args.manifest,
                          output_path=ROOT / STAGE_ROOT / "dev_lock.json", plan_only=args.plan,
                          execution_dir=args.execution_dir or ROOT / STAGE_ROOT / ("f1_plan" if args.plan else "f1_execution"))
        publish_new(ROOT / STAGE_ROOT / ("f1_plan_result.json" if args.plan else "f1_result.json"), result)
    except (ProtocolError, OSError, ValueError) as exc:
        print(json.dumps({"status": "PROTOCOL_ERROR", "message": str(exc), "written": False}))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0 if result["status"] in ("LOCKED", "PLAN_VALID") else 3


if __name__ == "__main__":
    raise SystemExit(main())
