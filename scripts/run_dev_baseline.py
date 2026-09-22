r"""$F_0$ §7's development-baseline command: `--seeds-file .../dev_seeds.txt`.

Three modes, and the difference between them is the point:

* `--plan` validates the seed sets and prints what would run; it needs no authorisation and writes
  nothing;
* `--benchmark` times the **seedless** evaluation-sample pass that $F_0$ §8's bound is derived from. It
  draws no seed, writes no stage artifact and needs no authorisation, because a benchmark is not a stage;
* without either flag it refuses unless the manifest's `currently_authorises` names `dev32`.
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
    ap = argparse.ArgumentParser(description="F0 development-baseline acquisition (baseline/static only).")
    ap.add_argument("--seeds-file", default=str(devstage.dev_seeds_file()))
    ap.add_argument("--plan", action="store_true",
                    help="validate inputs and print the plan; runs no episode, writes nothing")
    ap.add_argument("--benchmark", action="store_true",
                    help="time the seedless evaluation-sample pass; writes nothing")
    ap.add_argument("--scenes", type=int, default=devstage.BENCHMARK_SCENES)
    args = ap.parse_args(argv)
    try:
        if args.plan and args.benchmark:
            raise ProtocolError("--plan and --benchmark are different questions; pass one")
        if args.plan:
            payload = devstage.plan("dev_baseline", seeds_path=args.seeds_file)
        elif args.benchmark:
            payload = devstage.benchmark_eval_sample(args.scenes)
        else:
            payload = devstage.run_stage("dev_baseline", seeds_path=args.seeds_file)
    except ProtocolError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
