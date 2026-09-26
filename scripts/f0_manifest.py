"""Generate an exclusive F0 draft, or finalize from explicit review and full runtime evidence."""
import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b2.design_lock import publish_new
from rfl_rebuild.b2.f0_stages import MANIFEST_PATH, build_manifest, read_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=pathlib.Path, default=ROOT / MANIFEST_PATH)
    parser.add_argument("--runtime", type=pathlib.Path)
    parser.add_argument("--review", type=pathlib.Path)
    parser.add_argument("--finalize", action="store_true")
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()
    try:
        manifest = build_manifest(ROOT, runtime=read_json(args.runtime) if args.runtime else None,
                                  review=read_json(args.review) if args.review else None, finalize=args.finalize)
        if not args.plan:
            publish_new(args.output, manifest)
        print(json.dumps({"status": manifest["status"], "blockers": manifest["blockers"],
                          "sources": len(manifest["sources"]), "sources_digest": manifest["sources_digest"],
                          "written": not args.plan, "currently_authorises": manifest["currently_authorises"]}, sort_keys=True))
        return 0
    except (ProtocolError, OSError, ValueError) as exc:
        print(json.dumps({"status": "PROTOCOL_ERROR", "error": str(exc), "written": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
