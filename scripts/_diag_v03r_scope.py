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
    mass_mixed = 0.0
    mass_by_unit = collections.defaultdict(float)
    worlds_vacuous = 0
    hist = collections.Counter()
    mass_by_fire = collections.defaultdict(float)
    worlds_by_fire = collections.Counter()

    for wid in range(n):
        w = sup.weight(wid)
        fc = sup.field(wid, "fire_code")
        mass_total += w

        if fc & WRITABLE_MASK == 0:
            mass_vacuous += w
            worlds_vacuous += 1
        elif fc & ~WRITABLE_MASK:
            # writable projection non-empty AND an unwritable cause also fired
            mass_mixed += w
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
        mass_by_fire[fc] += w
        worlds_by_fire[fc] += 1

    active = mass_total - mass_vacuous
    pure = active - mass_mixed

    # Cross-check: the stratum can be computed two ways -- once by accumulating
    # inside the world loop, once by summing the per-pattern table. They must
    # agree. An earlier revision computed `mass_mixed` with a generator whose `w`
    # leaked from the preceding loop, so it summed the LAST world's weight over
    # and over and reported 0.000423 instead of 0.045898 -- a factor of 115, and
    # only the second computation exposed it.
    #
    # Tolerances are split on purpose. The two algebraic identities are exact in
    # floating point and get a tight bound; "the 1.04M weights add up to 1" is an
    # accumulation residual, not an identity, and gets a justified looser bound --
    # comparing it to exactly 1.0 at 1e-12 measures summation order, nothing else.
    mixed_from_table = sum(m for fc, m in mass_by_fire.items()
                           if (fc & WRITABLE_MASK) and (fc & ~WRITABLE_MASK))
    total_residual = mass_total - 1.0
    mixed_residual = mixed_from_table - mass_mixed
    consistency = {
        "mixed_mass_agrees_across_two_computations": abs(mixed_residual) < 1e-9,
        "S_plus_plus_S_zero_equals_total":
            abs(active + mass_vacuous - mass_total) < 1e-15,
        "total_mass_accumulates_to_one": abs(total_residual) < 1e-9,
        "pattern_masses_sum_to_one": abs(sum(mass_by_fire.values()) - 1.0) < 1e-9,
    }

    print(f"V0.3R support scoping over {n:,} worlds\n")
    print(f"  total DGP mass                              : {mass_total:.6f}")
    print(f"  S_+ : non-empty WRITABLE PROJECTION of G*   : {active:.6f} "
          f"({100 * active:.2f}%)")
    print(f"        of which PURE (G* entirely writable) : {pure:.6f} "
          f"({100 * pure:.2f}%)")
    print(f"        of which MIXED (E or U also present) : {mass_mixed:.6f} "
          f"({100 * mass_mixed:.2f}%)")
    print(f"  S_0 : writable projection empty             : {mass_vacuous:.6f} "
          f"({100 * mass_vacuous:.2f}%), {worlds_vacuous:,} worlds")
    print(f"    of which Z^fire = 00000                   : {mass_fire_zero:.6f} "
          f"({100 * mass_fire_zero:.2f}%)")
    print(f"\n  mass per credit unit (not exclusive):")
    for u in ("ProcessCommit", "Decision_t", "ControllerSite",
              "ExternalPlant", "Unknown/NoWrite"):
        tag = "writable" if u in WRITABLE_UNITS else "NOT writable"
        print(f"    {u:<16} {mass_by_unit[u]:.6f}  ({tag})")
    print(f"\n  worlds by |fired causes|: {dict(sorted(hist.items()))}")
    print(f"\n  consistency:")
    for k, v in consistency.items():
        print(f"    [{'PASS' if v else 'FAIL'}] {k}")
    print(f"    (total-mass accumulation residual: {total_residual:.3e}; "
          f"mixed two-way residual: {mixed_residual:.3e})")
    print(f"\n  fire patterns by DGP mass (all {len(mass_by_fire)} distinct):")
    print(f"    {'P D X E U':<12}{'mass':>12}{'worlds':>12}   stratum")
    for fc, m in sorted(mass_by_fire.items(), key=lambda kv: -kv[1]):
        bits = " ".join(str((fc >> i) & 1) for i in range(5))
        st = "S_+" if fc & WRITABLE_MASK else "S_0"
        if fc & WRITABLE_MASK and fc & ~WRITABLE_MASK:
            st = "S_+ mixed"
        print(f"    {bits:<12}{m:>12.6f}{worlds_by_fire[fc]:>12,}   {st}")

    out = ROOT / "experiments" / "v02r" / "v03r_scope_diag.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "n_worlds": n,
        "mass_total": mass_total,
        "S_plus_mass": active,
        "S_plus_pure_mass": pure,
        "S_plus_mixed_mass": mass_mixed,
        "S_zero_mass": mass_vacuous,
        "worlds_S_zero": worlds_vacuous,
        "mass_fire_zero": mass_fire_zero,
        "mass_per_unit": dict(mass_by_unit),
        "mass_by_fire_pattern": {format(fc, "05b"): m
                                 for fc, m in sorted(mass_by_fire.items())},
        "consistency": consistency,
        "total_mass_accumulation_residual": total_residual,
        "mixed_mass_two_way_residual": mixed_residual,
        "writable_units": list(WRITABLE_UNITS),
        "unwritable_units": ["ExternalPlant", "Unknown/NoWrite"],
        "label_correction": ("earlier wording said 'mass with Gamma* inside the "
                             "writable units', which would mean Gamma* is a SUBSET "
                             "of the writable units. The correct statement is 'mass "
                             "with a NON-EMPTY WRITABLE PROJECTION of Gamma*': "
                             "Gamma*_W != empty is not Gamma* subset-of Writable, "
                             "and S_+ contains mixed truths such as "
                             "{ControllerSite, ExternalPlant}"),
        "reading": ("S_+ = {l : Gamma*_W(l) != empty} is where a positive update "
                    "primitive is even defined; S_0 = {l : Gamma*_W(l) = empty} is "
                    "positive-write-INELIGIBLE, not scientifically vacuous -- "
                    "'this feedback should cause no internal update' is itself a "
                    "learning decision, and S_0 carries the FalseWriteRate / "
                    "non-interference question"),
        "stratification_rule": ("the stratum is fixed by the ontology boundary "
                                "Gamma*_W, NOT by whether the method actually wrote. "
                                "Conditioning on W^update != empty would let B0/B1 "
                                "abstain on hard worlds and score B2 only on easy "
                                "ones -- a selection bias of the A74 shape"),
        "mixed_cases": ("in S_+ mixed worlds a correct persistent update can only "
                        "address the learner-owned part; it cannot be required to "
                        "repair the external component, which is why B2+ should "
                        "compare Delta(Outcome) = post-update minus no-update "
                        "rather than demanding absolute success"),
        "caveat": ("this measures the writability boundary only. It says nothing "
                   "about whether a writable credit location has a persistent "
                   "referent at all -- the Decision_t question, where the SCM names "
                   "no decision parameter (it names C_X as a function, and defines "
                   "the decision override only relative to the evaluator-side "
                   "pi_D*)"),
    }, indent=1), encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
