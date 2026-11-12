"""Frozen serial gate suite and full-envelope smoke, with no scientific payload."""
import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b2.f0_stages import MANIFEST_PATH, run_smoke


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds-file", type=pathlib.Path, required=True)
    parser.add_argument("--manifest", type=pathlib.Path, default=ROOT / MANIFEST_PATH)
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()
    try:
        result = run_smoke(ROOT, manifest_path=args.manifest, seeds_file=args.seeds_file, plan_only=args.plan)
    except (ProtocolError, OSError, ValueError) as exc:
        print(json.dumps({"status": "PROTOCOL_ERROR", "error": str(exc), "written": False}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("verdict") == "PASS" or result.get("status") == "PLAN_VALID" else 3


if __name__ == "__main__":
    raise SystemExit(main())
