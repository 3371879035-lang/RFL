"""Read-only evaluator of the exact operational smoke surface."""
import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b2.f0_stages import MANIFEST_PATH, SMOKE_PATH, evaluate_smoke, load_manifest, read_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=pathlib.Path, default=ROOT / MANIFEST_PATH)
    parser.add_argument("--report", type=pathlib.Path, default=ROOT / SMOKE_PATH)
    args = parser.parse_args()
    try:
        manifest, identity = load_manifest(ROOT, args.manifest, "smoke")
        result = evaluate_smoke(read_json(args.report), manifest, identity)
        print(json.dumps(result, sort_keys=True))
        return 0 if result["verdict"] == "PASS" else 3
    except (ProtocolError, OSError, ValueError) as exc:
        print(json.dumps({"verdict": "FAIL", "reason": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
