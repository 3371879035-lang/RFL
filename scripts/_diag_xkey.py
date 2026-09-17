"""Diagnostic: is the frozen 893-class (block, fire) partition an X-partition?

`sigma0` returns `I^factual = (rows, feedback)`. `rows` carries
`(x, y, t, kappa, phi, z, m, a_cmd, a_realized, reward)`, so kappa and phi are
already learner-visible. `feedback = decode_feedback(Z^fire)` depends on
`(error_flag, cause_rank)`, which do NOT appear in `rows`.

The frozen 893 classes are `(block_id, fire_code)` with `block_id = repr(rows)`.
So if `I^factual` retains its feedback channel, two worlds with identical rows and
identical fire vector but different `(error_flag, cause_rank)` lie in the SAME
frozen class while having DIFFERENT X. This script measures the gap.

Read-only: loads the frozen support cache and recomputes feedback from the stored
(error_flag, cause_rank, fire_code). Mutates nothing.
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.env.kernel import SemanticTape  # noqa: E402
from rfl_rebuild.method.support import DenseSupport  # noqa: E402

CACHE = ROOT / "experiments" / "v01r" / "support_cache"


def main() -> int:
    if not CACHE.with_suffix(".json").exists():
        print(f"{CACHE}.json not found -- the cache is gitignored; rebuild first")
        return 2

    sup = DenseSupport.load(CACHE, expected_kernel_fingerprint="full",
                            expected_dgp_fingerprint="full")
    n = len(sup) if hasattr(sup, "__len__") else sup.manifest.n_worlds
    print(f"worlds: {n:,}   weight_sum: {sup.manifest.weight_sum:.12f}")

    fld = sup.field
    fb_per_class: dict[tuple[int, int], set] = collections.defaultdict(set)
    mass_per_class: dict[tuple[int, int], float] = collections.defaultdict(float)

    for wid in range(n):
        blk, fc = fld(wid, "block_id"), fld(wid, "fire_code")
        bits = [(fc >> b) & 1 for b in range(5)]
        fb = SemanticTape(phase=0, error_flag=fld(wid, "error_flag"),
                          cause_rank=fld(wid, "cause_rank")).decode_feedback(bits)
        key = (blk, fc)
        fb_per_class[key].add(fb)
        mass_per_class[key] += sup.weight(wid)

    frozen_classes = len(fb_per_class)
    x_classes = sum(len(v) for v in fb_per_class.values())
    multis = collections.Counter(len(v) for v in fb_per_class.values())

    print(f"\nfrozen (block_id, fire_code) classes : {frozen_classes:,}")
    print(f"X-classes with feedback retained     : {x_classes:,}")
    print(f"ratio                                : {x_classes / frozen_classes:.4f}x")
    print(f"distinct-feedback-count histogram    : {dict(sorted(multis.items()))}")
    print(f"classes with exactly ONE feedback    : {multis.get(1, 0):,}")

    split = [k for k, v in fb_per_class.items() if len(v) > 1]
    split_mass = sum(mass_per_class[k] for k in split)
    print(f"\nclasses SPLIT by the feedback channel : {len(split):,} / {frozen_classes:,} "
          f"({100.0 * len(split) / frozen_classes:.2f}% of classes)")
    print(f"DGP mass in split classes            : {split_mass:.6f} "
          f"({100.0 * split_mass:.4f}% of mass)")

    out = ROOT / "outputs" / "rebuild" / "xkey_partition_diag.json"
    out.write_text(json.dumps({
        "worlds": n,
        "frozen_classes_block_fire": frozen_classes,
        "x_classes_with_feedback": x_classes,
        "ratio": x_classes / frozen_classes,
        "distinct_feedback_histogram": {str(k): v for k, v in sorted(multis.items())},
        "classes_with_single_feedback": multis.get(1, 0),
        "classes_split_by_feedback": len(split),
        "dgp_mass_in_split_classes": split_mass,
    }, indent=1), encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
