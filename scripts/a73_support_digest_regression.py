"""A73 §60 — public-support exact-set regression.

`support_build.domains()` has been re-pointed from the historical pair

    gate_stage2._domains + identifiability_gate.canonicalise

to the single public grammar

    rfl_rebuild.env.fault_grammar

This script proves the re-pointing changed nothing, end to end: it rebuilds the
FULL support with the new grammar and compares the manifest it produces against
the COMMITTED frozen manifest. The grammar determines the candidate parameter set;
`sigma0` feasibility and the rows/block/fire derivation are untouched, so a
matching `content_digest` over 1,038,960 worlds is the strongest available
statement that the public grammar and the frozen evaluator support are the same
object.

SAFETY. `support_build.main()` calls `sup.save(path)` and would overwrite the
115 MB regenerable payload `experiments/v01r/support_cache.json`. This script calls
`build()` directly and NEVER saves, so the frozen payload is untouched even if the
run fails or is interrupted. It writes only its own report.

Run it in the background: the committed manifest records ~20 min for a full build.

    python scripts/a73_support_digest_regression.py
"""

from __future__ import annotations

import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gate_stage2 import reference_provider  # noqa: E402
from identifiability_gate import KAPPAS  # noqa: E402
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402
import support_build  # noqa: E402

FROZEN = ROOT / "experiments" / "v01r" / "support_cache.manifest.json"
REPORT = ROOT / "experiments" / "v02r" / "a73_support_digest_regression.json"


def main() -> int:
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    print("A73 public-support exact-set regression\n")
    print(f"  frozen manifest: n_worlds={frozen['n_worlds']:,} "
          f"n_rows_blocks={frozen['n_rows_blocks']} "
          f"digest={frozen['content_digest']}")
    print("  rebuilding the FULL support with the public grammar, NOT saving...")

    sol = solve_reference()
    provider = reference_provider(sol)
    t0 = time.time()
    sup, dgp, domains, build_case = support_build.build(sol, provider, KAPPAS,
                                                        "full")
    dt = time.time() - t0
    got = sup.manifest

    checks = {
        "n_worlds_identical": got.n_worlds == frozen["n_worlds"],
        "n_rows_blocks_identical": got.n_rows_blocks == frozen["n_rows_blocks"],
        "atom_schema_identical": list(got.atom_schema) == list(frozen["atom_schema"]),
        "weight_sum_identical": abs(got.weight_sum - frozen["weight_sum"]) < 1e-12,
        "content_digest_identical": got.content_digest == frozen["content_digest"],
    }
    ok = all(checks.values())

    print(f"\n  rebuild took {dt / 60:.1f} min")
    print(f"  rebuilt: n_worlds={got.n_worlds:,} n_rows_blocks={got.n_rows_blocks} "
          f"weight_sum={got.weight_sum:.12f}")
    print(f"  rebuilt digest: {got.content_digest}")
    print(f"  frozen  digest: {frozen['content_digest']}")
    for name, cond in checks.items():
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    verdict = ("public grammar reproduces the frozen support EXACTLY"
               if ok else
               "MISMATCH: the public grammar is NOT the frozen support")
    print(f"\nA73 public-support regression: {verdict}")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({
        "frozen_manifest": frozen,
        "rebuilt": {
            "n_worlds": got.n_worlds,
            "n_rows_blocks": got.n_rows_blocks,
            "atom_schema": list(got.atom_schema),
            "weight_sum": got.weight_sum,
            "content_digest": got.content_digest,
        },
        "rebuild_seconds": dt,
        "checks": checks,
        "status": "PASS" if ok else "FAIL",
        "verdict": verdict,
        "saved_payload": False,
        "note": ("build() called directly; sup.save() is never reached, so the "
                 "frozen support_cache.json was not overwritten"),
    }, indent=1), encoding="utf-8")
    print(f"wrote {REPORT}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
