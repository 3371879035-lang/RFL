r"""Run the eighteen A89 §77.7 calibration cells once, and write the evidence artifact.

Seedless instrument calibration: the fixture of each cell is frozen before its measurement, the
prediction is formed from the frozen solver and the unedited trajectory, and the measured side is the
same functional over the same unit set through the audited environment. Nothing here selects a
candidate, compares candidates by magnitude, or draws a scientific seed -- per §77.7, calibration
answers *can this be detected*, and that is all.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.b2.calibration import (  # noqa: E402
    CAL_SITES,
    aggregate_reference,
    spillover_edit,
)
from rfl_rebuild.b2.collateral import measured_scene_collateral  # noqa: E402
from rfl_rebuild.b2.unaffected import (  # noqa: E402
    REFINEMENTS,
    build_unaffected,
    pre_update_traces,
    scene_domain,
)
from rfl_rebuild.learner.reference import reference_view_from  # noqa: E402
from rfl_rebuild.learner.store import LearnerPersistentState  # noqa: E402
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

OUT = ROOT / "experiments" / "v03r" / "calibration_report.json"
REL_TOL, ABS_TOL = 1e-6, 1e-12


def digest(obj: object) -> str:
    if isinstance(obj, dict):
        items = sorted((str(k), obj[k]) for k in obj)
    else:
        items = list(obj)
    return hashlib.sha256(json.dumps(items, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def fixture_key(edit) -> dict:
    address = edit.channel_address
    if edit.channel == "D_Q":
        rendered = f"QAddress({address.state},{address.z},{address.m},{address.a})"
    elif edit.channel == "X":
        rendered = f"ControllerSite({address.state},{address.cmd})"
    else:
        rendered = f"P({address})"
    return {
        "unit": list(edit.unit.key),
        "channel_address": rendered,
        "owner_site": edit.site.render(),
        "credited_site": CAL_SITES[edit.channel].render(),
        "substrate_edit": f"{edit.substrate_edit.store}:{edit.substrate_edit.address!r}"
                          f"<-{edit.substrate_edit.value!r}",
        "applied_action": edit.applied_action,
        "applied_option": edit.applied_option,
        "off_target": edit.site.render() != CAL_SITES[edit.channel].render(),
    }


def main() -> int:
    solution = solve_reference()
    reference = reference_view_from(solution)
    traces = pre_update_traces(q_reference=reference)
    domains = scene_domain()

    cells, worst = [], 0.0
    for channel in ("D_Q", "X", "P"):
        for name in REFINEMENTS:
            predicted = aggregate_reference(channel, traces, name, solution=solution)
            units = build_unaffected(CAL_SITES[channel], traces, name)
            measured = measured_scene_collateral(units, LearnerPersistentState(), predicted["edit"],
                                                 q_reference=reference)
            gap = abs(measured["value"] - predicted["B_ref"])
            worst = max(worst, gap)
            nonzero = sum(1 for unit in units.units
                          if measured["values_pre"][unit] != measured["values_post"][unit])
            cells.append({
                "channel": channel,
                "refinement": name,
                "size": int(units.size),
                "B_ref": predicted["B_ref"],
                "d_ref": predicted["d_ref"],
                "measured": measured["value"],
                "abs_gap": gap,
                "agrees_within_tolerance": gap <= max(ABS_TOL, REL_TOL * abs(predicted["B_ref"])),
                "nonzero_units": nonzero,
                "post_overrides": measured["post_overrides"],
                "fixture": fixture_key(predicted["edit"]),
                "status": "CALIBRATED",
            })

    payload = {
        "what": "A89 section 77.7 synthetic calibration, eighteen cells",
        "instrument": {
            "tolerance": {"rel": REL_TOL, "abs": ABS_TOL, "source": "section 75.6 G5"},
            "credited_sites": {channel: site.render() for channel, site in CAL_SITES.items()},
            "functional": "BehavioralCollateral = mean over C of (V_pre(u) - V_post(u))",
            "prediction": "prefix + r(edited step) + V*(successor), from frozen rows and the "
                          "unedited trajectory",
            "reference_artifact_digest": digest(getattr(solution, "q", {}) or {}),
            "domains": {"U2": len(domains)},
        },
        "cells": cells,
        "summary": {
            "cells": len(cells),
            "calibrated": sum(1 for c in cells if c["status"] == "CALIBRATED"),
            "all_agree": all(c["agrees_within_tolerance"] for c in cells),
            "worst_abs_gap": worst,
            "failures": [f"{c['channel']}/{c['refinement']}" for c in cells
                         if not c["agrees_within_tolerance"]],
        },
        "note": "Calibration is instrument sensitivity, not candidate selection: magnitudes may not rank "
                "candidates (A79 section 67.4's development-seed decision stays unauthorised).",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")

    print("%-4s %-30s %-12s %-12s %-8s %s" % ("ch", "refinement", "B_ref", "measured", "nonzero", "agrees"))
    for c in cells:
        print("%-4s %-30s %-12.6f %-12.6f %-8d %s" % (
            c["channel"], c["refinement"], c["B_ref"], c["measured"], c["nonzero_units"],
            c["agrees_within_tolerance"]))
    print("cells:", payload["summary"]["calibrated"], "/", payload["summary"]["cells"],
          "| worst abs gap: %.3e" % worst)
    print("artifact:", OUT.relative_to(ROOT))
    return 0 if payload["summary"]["all_agree"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
