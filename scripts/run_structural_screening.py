r"""Run the A86/A87 structural screening once, and write its evidence artifact.

Authorised by A87 §75.5: the continuation instrument is CLOSED, which is the gate on this run. What
this script does **not** do is equally part of the contract -- it draws no scientific seed, selects no
development-stage quantity, and touches no architecture outside the three preregistered ones. The
artifact it writes is the seedless screening of `docs/rebuild/12-AMENDMENTS.md` §74.3 over §75's
fixtures, and nothing else.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.b2.screening import (  # noqa: E402
    ARCHITECTURES,
    DECLARED_DIRECTION,
    UNIT_1,
    UNIT_2,
    run_screening,
    u1_domain,
    u2_domain,
)
from rfl_rebuild.learner.reference import reference_view_from  # noqa: E402
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

OUT = ROOT / "experiments" / "v03r" / "structural_screening.json"


def digest(obj: object) -> str:
    """A canonical digest of a mapping or tuple, so the artifact can be re-derived and compared."""
    if isinstance(obj, dict):
        items = sorted((str(k), obj[k]) for k in obj)
    else:
        items = list(obj)
    blob = json.dumps(items, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def main() -> int:
    solution = solve_reference()
    reference = reference_view_from(solution)

    u1, u2 = u1_domain(), u2_domain()
    report = run_screening(q_reference=reference)

    payload = {
        "what": "A86 §74.3 structural screening over A87 §75's fixtures",
        "instrument": {
            "unit_1": {"domain": "X_D", "size": len(u1), "lift": "SemanticTape(s.phi, 0, 0)",
                       "entry": "b2.continuation.continuation"},
            "unit_2": {"domain": "K x T x Z", "size": len(u2),
                       "entry": "b2.environment.learned_rollout"},
            "reward_mode": "A",
            "declared_direction": DECLARED_DIRECTION,
            "reference_artifact": {
                "role": "one fixed nominal artifact shared by every cell and both sides of the pair",
                "rows": len(getattr(solution, "q", {}) or {}),
                "canonical_digest": digest(getattr(solution, "q", {}) or getattr(solution, "v", {})),
            },
            "domains_canonical_digest": {"U1": digest(u1), "U2": digest(u2)},
        },
        "measurement": {
            "closed_map": True,
            "short_circuit_on_positive": False,
            "missing_or_extra_units": "refused",
            "map_digests": {f"{k[0]}|{k[1]}": digest(v) for k, v in report.maps.items()},
            "map_sizes": {f"{k[0]}|{k[1]}": len(v) for k, v in report.maps.items()},
        },
        "cells": [
            {
                "unit": r.unit, "arch": r.arch, "status": r.status,
                "coverage": r.coverage, "detection": r.detection,
                "d_A": r.d_A, "measured_sign": r.measured_sign,
                "n_units": r.n_units, "n_moved": r.n_moved,
                "witness_pre": r.witness_pre, "witness_post": r.witness_post,
                "witness_delta": r.witness_delta, "rejected": r.rejected,
            }
            for r in report.cells
        ],
        "verdict": report.verdict,
        "verdict_space_note": (
            "A86 §74.4 defines three conclusions; A87 §75.7 shows this instance cannot reach "
            "SCREENING_INCONCLUSIVE because every declared direction is numeric, so every cell is "
            "STRUCTURAL_PASS or a STRUCTURAL_REJECT."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")

    print("%-4s %-4s %-22s %-9s %-9s %s" % ("unit", "arch", "status", "detection", "measured", "moved"))
    for r in report.cells:
        print("%-4s %-4s %-22s %-9s %-9s %d/%d" % (
            r.unit, r.arch, r.status, r.detection, r.measured_sign, r.n_moved, r.n_units))
    print("verdict:", report.verdict)
    print("artifact:", OUT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
