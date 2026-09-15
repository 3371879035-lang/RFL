"""Identifiability gate — Gate E / Gate L.

``docs/rebuild/00-INDEX.md`` §7 step 4, `03-IDENTIFIABILITY.md`, amendments
A42–A44.

Stages, in the frozen order:

1. **count-only** over the canonical primary support. If infeasible, **STOP** —
   `03` §1.1 forbids sampling and then calling it exhaustive.
2. factual partition ``ell -> sigma_0(ell)``, built **streaming**; identical
   nuisance rows keep a multiplicity rather than a copied object.
3. per-class legal queries ``Q(C)`` (`03` §1.6).
4. Gate L: non-adaptive search for a separating subset of size <= B_CF. A hit is
   a **sound PASS**; a miss is ``INCONCLUSIVE_NEEDS_ADAPTIVE``, never FAIL.

Frozen by the review:

* **A42** — ``phi`` is enumerated **once**. The tape stays three keys and
  ``|T| = 720``; ``phi`` is *not* a separate axis. Enumerating both double-counted
  it six times. A loop over ``(kappa, phi)`` plus 120 feedback draws is a
  *restricted tape*, not the full tape, and must not be labelled as one.
* **A43** — the canonical primary support: ``P`` keeps all 3 alternatives; each of
  ``D/X/E/U`` keeps **first and last** of its legal domain under a frozen order,
  computed **before** any co-fault outcome is seen. All 32 fault-presence patterns
  are kept. A combination that turns out MALFORMED is **excluded with a structural
  reason**, never silently replaced by "the next usable parameter".
* **A44** — Gate E and Gate L share **one** primary support. They differ only in
  *proof obligation*: E's totality/well-formedness follows structurally (a finite
  set that is non-empty has a minimal-cardinality element, else the sentinel
  applies), while L must be exhaustive.

This module defines no world semantics of its own: it imports the kernel and the
exact reference solution and nothing else.
"""

from __future__ import annotations

import itertools
import json
import pathlib
import sys
from collections import Counter, defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.env.kernel import (  # noqa: E402
    ControllerSite, FaultMask, MalformedIntervention, OptionViolation,
    SemanticTape, State,
)
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

B_CF = 4
KAPPAS = (0, 1)
CAUSE_KEYS = ("P", "D", "X", "E", "U")

# A42: phi is NOT an axis. The tape is the axis, and it carries phi inside it.
TAPES = tuple(
    SemanticTape(phase=p, error_flag=e, cause_rank=r)
    for p, e, r in itertools.product(K.PHASE_DOMAIN, (0, 1), range(60))
)
assert len(TAPES) == 720


def reference_provider(sol):
    def provider(s, c):
        return sol.best_action(s, c.z, c.m)

    return provider


def healthy_trace(sol, kappa: int, tape: SemanticTape, z: int):
    return K.rollout(kappa=kappa, tape=tape,
                     command_provider=reference_provider(sol), base_option=z)


# --------------------------------------------------------------------------- #
# A43 — the canonical primary support
# --------------------------------------------------------------------------- #

def legal_fault_domains(sol, kappa: int, tape: SemanticTape, z: int) -> dict:
    """Each fault block's full legal parameter domain on the **healthy** trace.

    Trajectory-dependent by construction: a decision fault can only substitute an
    action admissible at a state the episode actually visits, which is why ``M``
    was never a free Cartesian product.
    """
    tr = healthy_trace(sol, kappa, tape, z)
    state = State(x=K.START[0], y=K.START[1], t=0, kappa=kappa, phi=tape.phase)
    ctrl = K.initial_control(z)
    dp = sorted(zp for zp in K.option_ids() if zp != z)
    dd, dx, de, du = set(), set(), set(), set()
    for res in tr.steps:
        allowed = K.option_actions(ctrl.z, ctrl, state)
        want = sol.best_action(state, ctrl.z, ctrl.m)
        for a in allowed:
            if a != want:
                dd.add((state.t, a))
        for realized in K.legal_actions(state):
            if realized != res.a_cmd:
                dx.add((state.t, res.a_cmd, realized))
                de.add((state.t, realized))
        for cell in (K.OPEN_CELLS - {K.START, K.GOAL}):
            du.add((state.t, cell))
        state, ctrl = res.state, res.control
    return {
        "P": dp,
        "D": sorted(dd),
        "X": sorted(dx),
        "E": sorted(de),
        "U": sorted(du),
    }


def canonicalise(domain: list) -> list:
    """``first`` and ``last`` under the frozen order, deduplicated.

    Deliberately blind to outcome, ``B``, ``z*`` and any Gate result: the choice
    reads only the healthy trace and the frozen ordering. That is what makes this
    a **pre-declared finite domain** rather than outcome-conditioned sampling.
    """
    if not domain:
        return []
    if len(domain) == 1:
        return [domain[0]]
    return [domain[0], domain[-1]]


def canonical_domains(sol, kappa: int, tape: SemanticTape, z: int) -> dict:
    full = legal_fault_domains(sol, kappa, tape, z)
    return {k: canonicalise(v) for k, v in full.items()}


# --------------------------------------------------------------------------- #
# Stage 1 — count the canonical primary support
# --------------------------------------------------------------------------- #

def stage1(sol) -> dict:
    by_fault_count: Counter = Counter()          # weighted by M assignments
    z_patterns: Counter = Counter()              # weighted by M assignments
    infeasible_patterns: dict[str, int] = {}     # Z vector -> reason count
    total_candidate = 0
    base_contexts = 0

    for kappa in KAPPAS:
        for tape in TAPES:
            for z in K.option_ids():
                base_contexts += 1
                dom = canonical_domains(sol, kappa, tape, z)
                sizes = {k: len(dom[k]) for k in CAUSE_KEYS}
                # a fault may be absent, or take one canonical parameter
                for bits in itertools.product((0, 1), repeat=5):
                    pattern = "".join(map(str, bits))
                    m = 1
                    feasible = True
                    for bit, key in zip(bits, CAUSE_KEYS):
                        if bit:
                            if sizes[key] == 0:
                                feasible = False
                                break
                            m *= sizes[key]
                    if not feasible:
                        infeasible_patterns[pattern] = (
                            infeasible_patterns.get(pattern, 0) + 1)
                        continue
                    by_fault_count[sum(bits)] += m
                    z_patterns[pattern] += m
                    total_candidate += m

    return {
        "base_contexts": base_contexts,
        "L_candidate": total_candidate,
        "by_fault_count": dict(sorted(by_fault_count.items())),
        "by_Z_pattern": dict(sorted(z_patterns.items())),
        "infeasible_pattern_counts": dict(sorted(infeasible_patterns.items())),
        "patterns_with_zero_feasible": sorted(
            set(infeasible_patterns) - set(z_patterns)),
    }


def main() -> int:
    sol = solve_reference()
    print("=" * 78)
    print("Identifiability gate — stage 1 (canonical primary support, A42-A44)")
    print("=" * 78)
    r = stage1(sol)

    print(f"\nbase contexts (kappa x tape x option) = {r['base_contexts']:,}")
    print(f"|L_candidate|                        = {r['L_candidate']:,}")

    print("\nM assignments by active-fault count (weighted):")
    for k, v in r["by_fault_count"].items():
        print(f"  |Z| = {k}: {v:>12,}")

    print("\nM assignments by Z pattern:")
    for k, v in r["by_Z_pattern"].items():
        print(f"  {k}: {v:>12,}")

    if r["infeasible_pattern_counts"]:
        print("\npatterns with infeasible assignments (excluded by structure):")
        for k, v in r["infeasible_pattern_counts"].items():
            print(f"  {k}: excluded in {v:,} base contexts")

    zeros = r["patterns_with_zero_feasible"]
    print(f"\nZ patterns with ZERO feasible cases: {zeros if zeros else 'none'}")

    outdir = ROOT / "outputs" / "rebuild"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "gate_count.json").write_text(json.dumps(r, indent=1), encoding="utf-8")
    print(f"\nwrote {outdir / 'gate_count.json'}")

    if zeros:
        print("\nSTOP — canonicalisation deleted a fault-presence pattern entirely.")
        print("A43: widen the canonical M first; Gate L may not proceed.")
        return 3
    if r["L_candidate"] > 5_000_000:
        print("\nSTOP — still too large for exhaustive enumeration (03 s1.1).")
        return 2
    print("\nStage 1 OK — |L_feasible| is enumerable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
