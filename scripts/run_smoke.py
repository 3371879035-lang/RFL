r"""$F_0$ §7's smoke command: `python scripts/run_smoke.py --seeds-file .../smoke_seeds.txt`.

Smoke decides whether the instrument runs, never whether an effect is present, so this wrapper prints
the operational report and nothing else. Without `--plan` it refuses unless the manifest's
`currently_authorises` names `smoke5` -- the refusal is the boundary, not a convenience.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.b1.errors import ProtocolError  # noqa: E402
from rfl_rebuild.b2 import devstage  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="F0 smoke stage (operational only).")
    ap.add_argument("--seeds-file", default=str(devstage.smoke_seeds_file()))
    ap.add_argument("--plan", action="store_true",
                    help="validate inputs and print the plan; runs no episode, writes nothing")
    args = ap.parse_args(argv)
    try:
        payload = (devstage.plan("smoke", seeds_path=args.seeds_file) if args.plan
                   else devstage.run_stage("smoke", seeds_path=args.seeds_file))
    except ProtocolError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
