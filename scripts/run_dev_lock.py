"""F1 baseline-only combined design/threshold lock; refuses before F0 authorization."""
import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b2.design_lock import run_lock


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", type=pathlib.Path, required=True)
    parser.add_argument("--manifest", type=pathlib.Path, default=ROOT / "experiments/v03r/f0_manifest.json")
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()
    try:
        result = run_lock(ROOT, design_path=args.design, manifest_path=args.manifest,
                          output_path=ROOT / "experiments/v03r/dev_lock.json", plan_only=args.plan)
    except (ProtocolError, OSError, ValueError) as exc:
        print(json.dumps({"status": "PROTOCOL_ERROR", "message": str(exc), "written": False}))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0 if result["status"] in ("LOCKED", "PLAN_VALID") else 3


if __name__ == "__main__":
    raise SystemExit(main())
