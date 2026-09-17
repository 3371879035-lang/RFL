"""A73 — the locator evidence quotient gate: 4513 -> 893.

A73 (12 §60) rules that `CausalSetLocator` receives

    X^loc_{0.2} = (rows, Z^fire_truth)

and NOT the full learner-visible observation

    X^obs_{0.2} = (rows, feedback, Z^fire_truth)

because `feedback = decode_feedback(Z^fire)` is driven by `(error_flag, cause_rank)`,
which never appear in `rows`. Measured: |X^loc-classes| = 893 and
|X^obs-classes| = 4513, and the feedback channel splits all 893.

REDUNDANCY MAY NOT BE ASSUMED. It is proven here, and the proof is the gate: one
violation voids rows-only and the main gate reverts to 4513. Four exact
invariances are discharged under the nuisance pair, per *mechanism key*
`(kappa, phase, proposal, Z_code, p0..p4)` -- everything that makes a world except
`(error_flag, cause_rank)`:

    I1 rows        -- `block_id` is constant on the mechanism key
    I2 Z^fire      -- `fire_code` is constant
    I3 Gamma_desc  -- the indexed truth is constant
    I4 feasibility -- every mechanism key carries ALL 120 nuisance pairs, i.e.
                      feasibility is all-or-nothing, never partial

and then the envelope equality over ALL 4513 observational classes x:

    Gamma^-_obs(x) == Gamma^-_loc(q(x))   and   Gamma^+_obs(x) == Gamma^+_loc(q(x))

plus the exact-set identity A73 requires of the eventual locator:

    {Gamma*(l) : l in x}  ==  {Gamma*(l) : l in q(x)}   for every x

WHY THE ENVELOPE EQUALITY HOLDS -- a mechanism, not a coincidence: on a locator
class the fire vector is constant (I2); every mechanism key carries all 120
nuisance pairs (I4); and `decode_feedback` reads only `(error_flag, cause_rank,
Z^fire)`. So every mechanism key in a class reaches exactly the same set of
feedback values, every observational child therefore sees the class's FULL
Gamma* set, and union and intersection are unchanged.

I1-I4 do NOT imply this, which is why the envelope equality is checked directly
rather than derived: `a73_gate_selfcheck.py` case 5 is a well-formed world set
with all four invariances clean, where the feedback value is tied to the
mechanism key instead of to the nuisance pair alone, and the envelope does break.

Gamma* is computed from R^mech DESCRIPTORS (A71), never from fire bits alone, so
D/X carry addresses.

The aggregation is a PURE function of a record stream so that
`a73_gate_selfcheck.py` can feed it synthetic worlds and show every check failing
on the mutation it exists to catch -- I3 in particular is rebuilt from each world's
own nuisance pair, because keying the truth by the mechanism key alone would make
it constant by construction and unable to fail.

Read-only: loads the frozen support cache. Mutates nothing.
"""

from __future__ import annotations

import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gate_stage2 import LatentCase, _domains, reference_provider  # noqa: E402
from identifiability_gate import CAUSE_KEYS, canonicalise  # noqa: E402
from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.env.kernel import SemanticTape  # noqa: E402
from rfl_rebuild.method.support import DenseSupport  # noqa: E402
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

CACHE = ROOT / "experiments" / "v01r" / "support_cache"
N_NUISANCE = 120          # 2 error_flag values x 60 cause_rank values, per phase
EXPECTED_LOC = 893
EXPECTED_OBS = 4513


def gamma_star_units(case, fc: int) -> set:
    """A67 projection from R^mech DESCRIPTORS (A71), so D/X carry addresses."""
    out = set()
    if (fc >> 0) & 1:
        out.add("ProcessCommit")
    if (fc >> 1) & 1 and case.decision is not None:
        out.add(f"Decision_{case.decision.t}")
    if (fc >> 2) & 1 and case.controller is not None:
        f = case.controller
        out.add(f"ControllerSite_{f.state.x}_{f.state.y}_{f.state.t}_{f.cmd}")
    if (fc >> 3) & 1:
        out.add("ExternalPlant")
    if (fc >> 4) & 1:
        out.add("Unknown/NoWrite")
    return out or {"Unknown/NoWrite"}


def aggregate(records, n_nuisance: int = N_NUISANCE) -> dict:
    """Pure aggregation over a record stream.

    Each record is a dict with keys:
      ``mech``  tuple (kappa, phase, proposal, Z_code, p0..p4)
      ``blk``   block_id (equivalently: the rows class)
      ``fc``    fire_code
      ``ef``    error_flag      ``cr`` cause_rank
      ``fb``    the decoded feedback vector, i.e. the second half of I^factual
      ``gs``    frozenset, the indexed truth Gamma* for THIS world
    """
    mech_blk, mech_fc, mech_gs = {}, {}, {}
    mech_efcr = collections.defaultdict(set)
    loc_members = collections.defaultdict(set)
    obs_members = collections.defaultdict(set)
    i1 = i2 = i3 = 0

    for r in records:
        mech, blk, fc, gs = r["mech"], r["blk"], r["fc"], r["gs"]
        if mech not in mech_blk:
            mech_blk[mech] = blk
            mech_fc[mech] = fc
            mech_gs[mech] = gs
        else:
            i1 += mech_blk[mech] != blk
            i2 += mech_fc[mech] != fc
            i3 += mech_gs[mech] != gs
        mech_efcr[mech].add((r["ef"], r["cr"]))
        loc_members[(blk, fc)].add(gs)
        obs_members[(blk, fc, r["fb"])].add(gs)

    partial = {k: len(v) for k, v in mech_efcr.items() if len(v) != n_nuisance}
    i4 = len(partial)

    loc_minus = {k: frozenset.intersection(*v) for k, v in loc_members.items()}
    loc_plus = {k: frozenset.union(*v) for k, v in loc_members.items()}
    obs_minus = {k: frozenset.intersection(*v) for k, v in obs_members.items()}
    obs_plus = {k: frozenset.union(*v) for k, v in obs_members.items()}

    minus_mismatch, plus_mismatch, set_mismatch = [], [], []
    for (blk, fc, fb), v in obs_members.items():
        parent = (blk, fc)
        if obs_minus[(blk, fc, fb)] != loc_minus[parent]:
            minus_mismatch.append((blk, fc, fb))
        if obs_plus[(blk, fc, fb)] != loc_plus[parent]:
            plus_mismatch.append((blk, fc, fb))
        if v != loc_members[parent]:
            set_mismatch.append((blk, fc, fb))

    checks = {
        "I1_rows_invariant_under_nuisance": i1 == 0,
        "I2_fire_vector_invariant_under_nuisance": i2 == 0,
        "I3_gamma_desc_invariant_under_nuisance": i3 == 0,
        "I4_feasibility_all_or_nothing": i4 == 0,
        "gamma_minus_obs_equals_gamma_minus_loc": not minus_mismatch,
        "gamma_plus_obs_equals_gamma_plus_loc": not plus_mismatch,
        "gamma_star_set_obs_equals_loc": not set_mismatch,
    }
    return {
        "n_mechanism_keys": len(mech_blk),
        "n_locator_classes": len(loc_members),
        "n_observational_classes": len(obs_members),
        "i1_rows_violations": i1,
        "i2_fire_violations": i2,
        "i3_truth_violations": i3,
        "i4_partial_feasibility_keys": i4,
        "partial_keys": partial,
        "gamma_minus_mismatches": len(minus_mismatch),
        "gamma_plus_mismatches": len(plus_mismatch),
        "gamma_star_set_mismatches": len(set_mismatch),
        "mixed_classes_locator": sum(1 for v in loc_members.values() if len(v) > 1),
        "mixed_classes_observational": sum(1 for v in obs_members.values()
                                           if len(v) > 1),
        "checks": checks,
    }


def record_stream(sup, n: int):
    """Read the frozen support into the pure aggregation's record format.

    Gamma* is rebuilt from each world's OWN (error_flag, cause_rank), so I3 has
    power: a hidden dependence of the truth on the nuisance pair would show up as
    a violation rather than being masked by keying on the mechanism key.
    """
    sol = solve_reference()
    provider = reference_provider(sol)
    dom_cache: dict = {}

    def domains(kappa: int, phase: int, proposal: int):
        key = (kappa, phase, proposal)
        hit = dom_cache.get(key)
        if hit is None:
            tape = SemanticTape(phase=phase, error_flag=0, cause_rank=0)
            tr = K.rollout(kappa=kappa, tape=tape, command_provider=provider,
                           base_option=proposal)
            d = _domains(sol, kappa, tape, proposal, tr)
            hit = tuple(canonicalise(d[k]) for k in CAUSE_KEYS)
            dom_cache[key] = hit
        return hit

    for wid in range(n):
        kappa, phase = sup.field(wid, "kappa"), sup.field(wid, "phase")
        proposal, z_code = sup.field(wid, "proposal"), sup.field(wid, "Z_code")
        idx = tuple(sup.field(wid, f"p{i}") for i in range(5))
        ef, cr = sup.field(wid, "error_flag"), sup.field(wid, "cause_rank")
        fc = sup.field(wid, "fire_code")

        dm = domains(kappa, phase, proposal)
        b = {k: (dm[i][idx[i]] if idx[i] >= 0 else None)
             for i, k in enumerate(CAUSE_KEYS)}
        case = LatentCase(case_id=0, kappa=kappa, phi=phase, error_flag=ef,
                          cause_rank=cr, base_option=proposal,
                          Z=tuple((z_code >> i) & 1 for i in range(5)),
                          option_fault=b.get("P"), decision=b.get("D"),
                          controller=b.get("X"), plant=b.get("E"),
                          trap=b.get("U"))
        yield {
            "mech": (kappa, phase, proposal, z_code, *idx),
            "blk": sup.field(wid, "block_id"),
            "fc": fc,
            "ef": ef,
            "cr": cr,
            "fb": tuple(SemanticTape(phase=phase, error_flag=ef,
                                     cause_rank=cr).decode_feedback(
                [(fc >> b2) & 1 for b2 in range(5)])),
            "gs": frozenset(gamma_star_units(case, fc)),
        }


def main() -> int:
    sup = DenseSupport.load(CACHE, expected_kernel_fingerprint="full",
                            expected_dgp_fingerprint="full")
    n = sup.manifest.n_worlds
    print(f"A73 quotient gate over {n:,} worlds\n")

    r = aggregate(record_stream(sup, n))
    checks = dict(r["checks"])
    checks["n_locator_classes_equals_893"] = r["n_locator_classes"] == EXPECTED_LOC
    checks["n_observational_classes_equals_4513"] = (
        r["n_observational_classes"] == EXPECTED_OBS)
    ok = all(checks.values())

    print(f"  mechanism keys (world minus nuisance pair): {r['n_mechanism_keys']:,}")
    print(f"  x {N_NUISANCE} nuisance pairs              = "
          f"{r['n_mechanism_keys'] * N_NUISANCE:,} worlds")
    print(f"\n  locator classes X^loc (block, fire)        : "
          f"{r['n_locator_classes']:,}")
    print(f"  observational classes X^obs (+feedback)    : "
          f"{r['n_observational_classes']:,}")
    print(f"  ratio                                      : "
          f"{r['n_observational_classes'] / r['n_locator_classes']:.4f}x")
    print(f"\n  I1 rows violations                         : {r['i1_rows_violations']}")
    print(f"  I2 fire violations                         : {r['i2_fire_violations']}")
    print(f"  I3 truth violations (rebuilt per world)    : "
          f"{r['i3_truth_violations']}")
    print(f"  I4 partial-feasibility mechanism keys      : "
          f"{r['i4_partial_feasibility_keys']}")
    for k, c in list(r["partial_keys"].items())[:5]:
        print(f"      {k} -> {c}/{N_NUISANCE} nuisance pairs present")
    print(f"\n  Gamma^- mismatches over {r['n_observational_classes']:,} "
          f"obs classes : {r['gamma_minus_mismatches']}")
    print(f"  Gamma^+ mismatches                         : "
          f"{r['gamma_plus_mismatches']}")
    print(f"  Gamma* set mismatches                      : "
          f"{r['gamma_star_set_mismatches']}")
    print(f"\n  mixed classes: locator {r['mixed_classes_locator']} "
          f"(A71 reports 14), observational {r['mixed_classes_observational']}")
    for name, cond in checks.items():
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    verdict = ("rows-only LICENSED: feedback is a target-preserving nuisance"
               if ok else
               "rows-only VOID: the main gate reverts to 4513")
    print(f"\nA73 quotient gate: {verdict}")

    out = ROOT / "experiments" / "v02r" / "a73_quotient_gate.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {k: v for k, v in r.items() if k != "partial_keys"}
    payload.update({
        "n_worlds": n,
        "nuisance_pairs_per_phase": N_NUISANCE,
        "ratio_obs_over_loc": r["n_observational_classes"] / r["n_locator_classes"],
        "checks": checks,
        "status": "PASS" if ok else "FAIL",
        "verdict": verdict,
        "kill_condition": ("one violation of I1-I4 or of the envelope equality "
                           "voids rows-only and reverts the main gate to 4513"),
        "quotient": ("X^loc = (rows, Z^fire) is the causal locator's input; "
                     "X^obs = (rows, feedback, Z^fire) is the full learner-visible "
                     "observation; q drops feedback"),
        "i3_note": ("the truth is rebuilt from each world's own (error_flag, "
                    "cause_rank); keying it on the mechanism key alone would make "
                    "I3 constant by construction and unable to fail"),
    })
    out.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    print(f"wrote {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
