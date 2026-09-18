r"""Diagnostic for the V0.3R rebase: how much of the support can pose the question?

The first-layer V0.3R design freezes

    Gamma*  ->  W^update  ->  future consequences

and NoWrite for the unwritable units:

    agent_writeable = false  =>  W^update = empty

Before designing update primitives it is worth knowing how much of the frozen
support is *vacuous by writability* -- worlds whose entire Gamma* lies outside the
writable units, so V0.3R's question has no content there whatever primitive is
chosen. `ExternalPlant` and `Unknown/NoWrite` are unwritable (A69 section 6);
`ProcessCommit`, `Decision_t` and `ControllerSite` are writable.

Read-only: loads the frozen support and recomputes only fire_code and weights.
"""

from __future__ import annotations

import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.method.support import DenseSupport  # noqa: E402

CACHE = ROOT / "experiments" / "v01r" / "support_cache"

#: fire_code bit order is (P, D, X, E, U); P/D/X are writable, E/U are not.
WRITABLE_MASK = 0b00111        # P | D | X
BIT_P, BIT_D, BIT_X, BIT_E, BIT_U = 0, 1, 2, 3, 4
WRITABLE_UNITS = ("ProcessCommit", "Decision_t", "ControllerSite")


def main() -> int:
    sup = DenseSupport.load(CACHE, expected_kernel_fingerprint="full",
                            expected_dgp_fingerprint="full")
    n = len(sup)

    mass_total = 0.0
    mass_vacuous = 0.0
    mass_fire_zero = 0.0
    mass_by_unit = collections.defaultdict(float)
    worlds_vacuous = 0
    hist = collections.Counter()

    for wid in range(n):
        w = sup.weight(wid)
        fc = sup.field(wid, "fire_code")
        mass_total += w

        if fc & WRITABLE_MASK == 0:
            mass_vacuous += w
            worlds_vacuous += 1
        if fc == 0:
            mass_fire_zero += w
        if (fc >> BIT_P) & 1:
            mass_by_unit["ProcessCommit"] += w
        if (fc >> BIT_D) & 1:
            mass_by_unit["Decision_t"] += w
        if (fc >> BIT_X) & 1:
            mass_by_unit["ControllerSite"] += w
        if (fc >> BIT_E) & 1:
            mass_by_unit["ExternalPlant"] += w
        if (fc >> BIT_U) & 1 or fc == 0:
            mass_by_unit["Unknown/NoWrite"] += w
        hist[bin(fc).count("1")] += 1

    active = mass_total - mass_vacuous
    print(f"V0.3R support scoping over {n:,} worlds\n")
    print(f"  total DGP mass                              : {mass_total:.6f}")
    print(f"  mass with Gamma* inside the WRITABLE units  : {active:.6f} "
          f"({100 * active:.2f}%)")
    print(f"  mass VACUOUS BY WRITABILITY (E/U only)      : {mass_vacuous:.6f} "
          f"({100 * mass_vacuous:.2f}%), {worlds_vacuous:,} worlds")
    print(f"    of which Z^fire = 00000                   : {mass_fire_zero:.6f} "
          f"({100 * mass_fire_zero:.2f}%)")
    print(f"\n  mass per credit unit (not exclusive):")
    for u in ("ProcessCommit", "Decision_t", "ControllerSite",
              "ExternalPlant", "Unknown/NoWrite"):
        tag = "writable" if u in WRITABLE_UNITS else "NOT writable"
        print(f"    {u:<16} {mass_by_unit[u]:.6f}  ({tag})")
    print(f"\n  worlds by |fired causes|: {dict(sorted(hist.items()))}")

    out = ROOT / "experiments" / "v02r" / "v03r_scope_diag.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "n_worlds": n,
        "mass_total": mass_total,
        "mass_writable_nonempty": active,
        "mass_vacuous_by_writability": mass_vacuous,
        "worlds_vacuous_by_writability": worlds_vacuous,
        "mass_fire_zero": mass_fire_zero,
        "mass_per_unit": dict(mass_by_unit),
        "writable_units": list(WRITABLE_UNITS),
        "unwritable_units": ["ExternalPlant", "Unknown/NoWrite"],
        "reading": ("mass_vacuous_by_writability is the part of the support where "
                    "V0.3R's question has no content whatever update primitive is "
                    "chosen, because agent_writeable = false forces W^update = "
                    "empty (A69 section 6)"),
        "caveat": ("this measures the writability boundary only. It says nothing "
                   "about whether a writable credit location induces a persistent "
                   "write at all -- that is the hypothesis B0/B2 must test, and the "
                   "Z_D case is the reason it cannot be assumed"),
    }, indent=1), encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
