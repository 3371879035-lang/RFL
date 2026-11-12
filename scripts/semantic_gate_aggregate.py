"""Aggregate the semantic gate arifact from the two canonical raw files.

The combined file must be a PURE FUNCTION of the raw ones. An earlier revision
had the S1 runner read `semantic_gate.json` and re-wrap it as its own ``s0``
input, so every re-run added a layer:

    s0 -> combined -> s0 -> combined -> s0 -> original S0

That made the artifact non-idempotent, grew it without bound, buried the true
S0 source fingerprint, and would have made it impossible to tell which layer was
canonical once Oracle/calibration merged on top.

So: raw S0 and raw S1 are written by their own runners and **never read back by
a runner**; this script is the only thing that writes the combined file, and it
is deterministic given the two inputs. Re-running it is a no-op.
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments" / "v01r"


def _load(name):
    p = OUT / name
    if not p.exists():
        raise SystemExit(f"missing canonical raw input: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def build() -> dict:
    s0 = _load("semantic_gate_s0.json")
    s1 = _load("semantic_gate_s1.json")
    # Do not nest either raw document under a key that a raw writer also emits:
    # the combined view carries them verbatim, and re-running this function on
    # its own output is impossible because it only ever reads the RAW files.
    return {
        "gate": "semantic gate — combined S0 (kernel) + V0.1R-S1 (method)",
        "layout": {
            "raw": ["semantic_gate_s0.json", "semantic_gate_s1.json"],
            "combined": "semantic_gate.json (this file, rebuilt by "
                        "scripts/semantic_gate_aggregate.py)",
            "rule": "a runner must NEVER read the combined file; that is what "
                    "made the artifact recurse.",
        },
        "s0": s0,
        "s1_v01r": s1,
        "blocked_disclosure": (
            "BLOCKED_NOT_IMPLEMENTED (S0: I1, I2, I6, C6) means the layer does not "
            "exist. It is never N/A. V0.1R declares its dependency in "
            "S0.items.V0.1R_DEPENDENCY."
        ),
    }


def main() -> int:
    combined = build()
    out = OUT / "semantic_gate.json"
    text = json.dumps(combined, indent=1, default=str)
    out.write_text(text, encoding="utf-8")

    # idempotence regression: rebuilding from the same raws is byte-identical
    again = json.dumps(build(), indent=1, default=str)
    ok = again == text
    depth_before = json.dumps(combined).count('"gate"')
    print(f"wrote {out}")
    print(f"idempotent rebuild: {'OK' if ok else 'FAILED'}")
    print(f"nested 'gate' keys in combined: {depth_before} (must be 3: "
          f"combined + s0 + s1)")
    if not ok:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
