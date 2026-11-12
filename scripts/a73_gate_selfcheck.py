"""Power test for the A73 quotient gate.

The gate licenses a design decision: it says feedback may be dropped from the
locator's input, which moves the main gate from 4513 classes to 893. A gate that
has never been observed to fail is not evidence -- this project has already
recorded two checks that reported PASS while being unsatisfiable, and the first
draft of this very gate contained a third (I3 was keyed by the mechanism key, so
constancy was true by construction and the check could not fail).

So every check is fed a synthetic world set built to break exactly it, and must
report the break. No support cache and no kernel are touched.

Usage
-----
    python scripts/a73_gate_selfcheck.py
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from a73_quotient_gate import aggregate  # noqa: E402

N = 120          # nuisance pairs, small enough that synthetic sets stay readable
failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def rec(mech, blk, fc, ef, cr, fb, gs):
    return {"mech": mech, "blk": blk, "fc": fc, "ef": ef, "cr": cr,
            "fb": fb, "gs": frozenset(gs)}


def healthy(mech, blk, fc, gs, fbs):
    """All N nuisance pairs for one mechanism key, cycling over the given feedbacks."""
    return [rec(mech, blk, fc, i % 2, i // 2, fbs[i % len(fbs)], gs)
            for i in range(N)]


print("A73 quotient gate power test -- each case breaks one invariance")

# --- baseline: a well-formed two-mechanism universe must be clean ---------- #
# Both mechanism keys must span BOTH feedback values. That is not a fixture
# convenience: in real data each mechanism key carries all 120 nuisance pairs,
# and `decode_feedback` reads only (error_flag, cause_rank, Z^fire) with the fire
# vector constant on a locator class -- so every mechanism key reaches the same
# set of feedback values, and every observational child sees the class's FULL
# truth set. Giving each key only one feedback would model a different world set
# (that is case 5), not the healthy one.
ALL_FB = [("a",), ("b",)]
base_recs = (healthy(("m1",), 1, 0b00001, {"ProcessCommit"}, ALL_FB) +
             healthy(("m2",), 1, 0b00001, {"ExternalPlant"}, ALL_FB))
r = aggregate(base_recs)
print(f"\nbaseline: loc={r['n_locator_classes']} obs={r['n_observational_classes']} "
      f"i1={r['i1_rows_violations']} i2={r['i2_fire_violations']} "
      f"i3={r['i3_truth_violations']} i4={r['i4_partial_feasibility_keys']}")
check("baseline has no violations", all(r["checks"].values()),
      f"{[k for k, v in r['checks'].items() if not v]}")
check("baseline merges two mechanism keys into ONE locator class "
      "(one block, one fire)", r["n_locator_classes"] == 1)
check("baseline splits that class into TWO observational classes (two feedbacks)",
      r["n_observational_classes"] == 2)

# --- case 1: rows leak the nuisance pair (block_id varies) ----------------- #
r1 = aggregate(healthy(("m1",), 1, 0b1, {"A"}, [("a",)]) +
               [rec(("m1",), 2, 0b1, 1, 1, ("a",), {"A"})])
check("I1 fires when block_id varies within a mechanism key",
      r1["i1_rows_violations"] == 1, f"i1={r1['i1_rows_violations']}")

# --- case 2: the fire vector leaks the nuisance pair ----------------------- #
r2 = aggregate(healthy(("m1",), 1, 0b1, {"A"}, [("a",)]) +
               [rec(("m1",), 1, 0b10, 1, 1, ("a",), {"A"})])
check("I2 fires when fire_code varies within a mechanism key",
      r2["i2_fire_violations"] == 1, f"i2={r2['i2_fire_violations']}")

# --- case 3: THE one that was vacuous. The truth must be rebuilt per world,
# so a mechanism key carrying two different Gamma* must be caught. ---------- #
r3 = aggregate(healthy(("m1",), 1, 0b1, {"A"}, [("a",)]) +
               [rec(("m1",), 1, 0b1, 1, 1, ("a",), {"B"})])
check("I3 fires when Gamma* varies within a mechanism key (non-vacuous)",
      r3["i3_truth_violations"] == 1, f"i3={r3['i3_truth_violations']}")

# --- case 4: feasibility becomes partial ---------------------------------- #
r4 = aggregate([rec(("m1",), 1, 0b1, 0, 0, ("a",), {"A"})])
check("I4 fires when a mechanism key has fewer than all nuisance pairs",
      r4["i4_partial_feasibility_keys"] == 1,
      f"i4={r4['i4_partial_feasibility_keys']}")

# --- case 5: the envelope check itself, and the reason it must be checked
# directly rather than derived from I1-I4. This world set satisfies ALL FOUR
# invariances -- each mechanism key is complete over the nuisance pair, the fire
# vector and block are constant, Gamma* is constant per key -- and yet the
# quotient is NOT target-preserving, because here the feedback value is tied to
# the mechanism key instead of to the nuisance pair alone. One locator class, two
# feedback children, each seeing only ONE of the two truths; the union over the
# parent differs from both children. -------------------------------------- #
r5 = aggregate(healthy(("m1",), 1, 0b1, {"A"}, [("a",)]) +
               healthy(("m2",), 1, 0b1, {"B"}, [("b",)]))
print(f"\ncase 5 universe: loc={r5['n_locator_classes']} "
      f"obs={r5['n_observational_classes']} "
      f"plus_mismatch={r5['gamma_plus_mismatches']} "
      f"set_mismatch={r5['gamma_star_set_mismatches']}")
check("case 5 satisfies I1-I4, so the envelope failure is NOT implied by them",
      r5["i1_rows_violations"] == 0 and r5["i2_fire_violations"] == 0
      and r5["i3_truth_violations"] == 0 and r5["i4_partial_feasibility_keys"] == 0,
      f"i1={r5['i1_rows_violations']} i2={r5['i2_fire_violations']} "
      f"i3={r5['i3_truth_violations']} i4={r5['i4_partial_feasibility_keys']}")
check("Gamma^+ mismatch is detected when feedback splits two different truths",
      r5["gamma_plus_mismatches"] == 2,
      f"got {r5['gamma_plus_mismatches']}")
check("the exact Gamma* set identity also fails on that universe",
      r5["gamma_star_set_mismatches"] == 2,
      f"got {r5['gamma_star_set_mismatches']}")
check("the union over the parent still differs from each child",
      r5["checks"]["gamma_plus_obs_equals_gamma_plus_loc"] is False)

# --- case 6: the same universe, but BOTH nuisance pairs see BOTH truths.
# Now dropping feedback is genuinely harmless and the gate must NOT fire. --- #
r6 = aggregate(healthy(("m1",), 1, 0b1, {"A", "B"}, ALL_FB) +
               healthy(("m2",), 1, 0b1, {"A", "B"}, ALL_FB))
check("no false positive when both children carry both truths",
      r6["checks"]["gamma_plus_obs_equals_gamma_plus_loc"] is True
      and r6["checks"]["gamma_star_set_obs_equals_loc"] is True,
      f"plus={r6['gamma_plus_mismatches']} set={r6['gamma_star_set_mismatches']}")

print()
if failures:
    print(f"POWER TEST FAILED: {len(failures)} case(s) -- {failures}")
    sys.exit(1)
print("POWER TEST PASSED: every A73 invariance was observed to fail on the "
      "mutation it exists to catch, and the envelope check does not fire on a "
      "genuinely harmless quotient")
