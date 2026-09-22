r"""$F_0$ §7's design-lock command: `python scripts/run_dev_lock.py --design .../dev_baseline.json`.

The lock is the evaluation of the frozen rules of $F_0$ §4 on one acquisition, and those rules read an
**episode-indexed baseline curve** whose construction in this rebuild line is still `[PROPOSED]` in
$F_0$ §3. So this command refuses rather than inventing one, and it refuses *after* the authorisation
check rather than instead of it:

$$\boxed{\text{a command that cannot yet compute its answer must say so, not produce one}}$$
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
    ap = argparse.ArgumentParser(description="F0 design lock (evaluates the frozen rules on one acquisition).")
    ap.add_argument("--design", default=str(ROOT / devstage.ARTIFACTS["dev_baseline"]))
    ap.add_argument("--plan", action="store_true",
                    help="validate inputs and print the plan; evaluates no rule, writes nothing")
    args = ap.parse_args(argv)
    try:
        payload = (devstage.plan("dev_lock", design=args.design) if args.plan
                   else devstage.run_stage("dev_lock", design=args.design))
    except ProtocolError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
