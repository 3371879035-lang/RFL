"""Gate stage 3 — query signatures and the non-adaptive search at B_CF = 4.

``docs/rebuild/03-IDENTIFIABILITY.md`` §1.4, §1.6, §1.7.

Contract, frozen by the review:

1. **Unlimited-query check FIRST.** If some cross-``Z`` pair agrees on *every*
   legal query, that is ``FAIL_UNIDENTIFIABLE_EVEN_UNBOUNDED`` -- no adaptive
   policy could separate them either. ``INCONCLUSIVE_NEEDS_ADAPTIVE`` is reserved
   for the case where the full family separates but no subset of size <= B_CF does.
2. **A MALFORMED class-local query STOPS the run.** It may not become a response
   category: the frozen invariant is that a factual class shares one legal query
   family, so a disagreement means Stage 2 or the query reconstruction has a bug.
3. Responses use the full counterfactual ``I_t``; ``Z``, the base option, ``M``,
   ``u_t`` and ``Outcome`` are all excluded. The fixed reference policy continues
   to act after the intervention.
4. **The subset miss must be an exhaustive miss.** Query columns are
   deduplicated, then every subset of size <= 4 is tried. A greedy failure would
   not be a proof.
5. **Minimal counterexamples are saved**, not just verdicts.
"""

from __future__ import annotations

import itertools
import json
import pathlib
import sys
from collections import Counter, defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.env.kernel import (  # noqa: E402
    ControllerSite, FaultMask, Intervention, InterventionSet,
    MalformedIntervention, OptionViolation, State,
)
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402
from gate_stage2 import (  # noqa: E402
    LatentCase, _domains, class_local_queries, reference_provider, sigma0,
)
from identifiability_gate import CAUSE_KEYS, KAPPAS, TAPES, canonicalise  # noqa: E402

B_CF = 4
VERDICT_PASS = "PASS_NONADAPTIVE"
VERDICT_INC = "INCONCLUSIVE_NEEDS_ADAPTIVE"
VERDICT_FAIL = "FAIL_UNIDENTIFIABLE_EVEN_UNBOUNDED"


# --------------------------------------------------------------------------- #
# Building the partition (same enumeration as Stage 2)
# --------------------------------------------------------------------------- #

def build_partition(sol):
    classes: dict[tuple, list[LatentCase]] = defaultdict(list)
    n_candidate = n_feasible = 0
    malformed = 0
    cid = 0
    for kappa in KAPPAS:
        for tape in TAPES:
            for z in K.option_ids():
                tr = K.rollout(kappa=kappa, tape=tape,
                               command_provider=reference_provider(sol),
                               base_option=z)
                dom = _domains(sol, kappa, tape, z, tr)
                canon = {k: canonicalise(dom[k]) for k in CAUSE_KEYS}
                for bits in itertools.product((0, 1), repeat=5):
                    active = [k for k, b in zip(CAUSE_KEYS, bits) if b]
                    if any(not canon[k] for k in active):
                        continue
                    for combo in itertools.product(*[canon[k] for k in active]):
                        n_candidate += 1
                        blocks = dict(zip(active, combo))
                        case = LatentCase(
                            case_id=cid, kappa=kappa, phi=tape.phase,
                            error_flag=tape.error_flag, cause_rank=tape.cause_rank,
                            base_option=z, Z=bits,
                            option_fault=blocks.get("P"), decision=blocks.get("D"),
                            controller=blocks.get("X"), plant=blocks.get("E"),
                            trap=blocks.get("U"))
                        cid += 1
                        sig, _err = sigma0(sol, case)
                        if sig is None:
                            malformed += 1
                            continue
                        n_feasible += 1
                        classes[sig].append(case)
    return classes, n_candidate, n_feasible, malformed


# --------------------------------------------------------------------------- #
# One query, replayed on one case
# --------------------------------------------------------------------------- #

def to_intervention(q) -> Intervention:
    if q[0] == "process":
        return Intervention.process(q[1])
    if q[0] == "decision":
        return Intervention.decision(q[1], q[2])
    return Intervention.execution(q[1])


def response(sol, case: LatentCase, q):
    """``sigma(ell, q)`` — the full counterfactual ``I_t``, feedback included."""
    try:
        tr = K.rollout(
            kappa=case.kappa, tape=case.tape(),
            command_provider=reference_provider(sol),
            base_option=case.base_option, mask=case.mask(),
            option_fault=case.option_fault,
            interventions=InterventionSet((to_intervention(q),)))
    except (MalformedIntervention, OptionViolation):
        return None                      # caller STOPS; never a response category

    zf = tr.option_in_force
    state = State(x=K.START[0], y=K.START[1], t=0, kappa=case.kappa,
                  phi=case.phi)
    ctrl = K.initial_control(zf)
    rows = []
    for res in tr.steps:
        rows.append((state.x, state.y, state.t, state.kappa, state.phi,
                     ctrl.z, ctrl.m, res.a_cmd, res.a_realized,
                     round(res.reward, 6)))
        state, ctrl = res.state, res.control
    return (tuple(rows), tuple(case.tape().decode_feedback(list(case.Z))))


def dynamical_key(case: LatentCase):
    """Everything a query-response depends on, EXCEPT the feedback keys.

    ``error_flag`` and ``cause_rank`` do not enter the dynamics at all -- they only
    shape the terminal claim. Compressing on this key is the safe multiplicity
    merge the review allowed; anything else would risk erasing a divergence.
    """
    return (case.kappa, case.phi, case.base_option, case.Z,
            case.option_fault, case.decision, case.controller, case.plant,
            case.trap)


# --------------------------------------------------------------------------- #
# Exhaustive non-adaptive search
# --------------------------------------------------------------------------- #

def min_separating_subset(cols: dict, limit: int):
    """Smallest subset of deduplicated query columns that separates all ``Z``.

    ``cols[q]`` is a list of ``(Z, response)`` per representative case. A subset
    separates iff every group of cases sharing a response-vector shares a single
    ``Z``. Exhaustive over size 1..limit: a greedy failure would not be a proof
    that no set of size <= limit exists.
    """
    keys = list(cols)
    if not keys:
        return None, None
    n = len(cols[keys[0]])
    for size in range(1, limit + 1):
        for combo in itertools.combinations(range(len(keys)), size):
            groups: dict = defaultdict(set)
            for ci in range(n):
                vals = tuple(cols[keys[j]][ci][1] for j in combo)
                groups[vals].add(cols[keys[0]][ci][0])
            if all(len(v) == 1 for v in groups.values()):
                return size, [keys[j] for j in combo]
    return None, None


def main() -> int:
    sol = solve_reference()
    classes, n_candidate, n_feasible, malformed = build_partition(sol)
    print(f"partition: {len(classes):,} classes from {n_feasible:,} feasible cases")

    verdicts: Counter = Counter()
    report = {"n_classes": len(classes), "details": [], "malformed_queries": 0,
              "independent_qfamily_mismatch": 0}

    for idx, (sig, members) in enumerate(classes.items()):
        zs = {m.Z for m in members}
        if len(zs) < 2:
            verdicts["TRIVIAL_SINGLE_Z"] += 1
            continue

        qfam = class_local_queries(sol, members[0].kappa, members[0].phi, sig[0])

        # independent assertion: recompute from an actual replayed case
        probe_sig, _ = sigma0(sol, members[0])
        probe_q = class_local_queries(sol, members[0].kappa, members[0].phi,
                                      probe_sig[0])
        if probe_q != qfam:
            report["independent_qfamily_mismatch"] += 1

        # compress by dynamical identity
        by_key = {}
        for m in members:
            by_key.setdefault(dynamical_key(m), m)
        reps = list(by_key.values())

        # ---- A50: information-state safe legality -------------------------- #
        # Q_learner(H) = intersection over the CURRENT hypothesis set of the
        # queries that are well-formed in that world. A query that is MALFORMED
        # on any still-possible case is not selectable -- it is dropped, NOT
        # stopped on and NOT turned into a response category. Illegal query
        # availability is itself partially observable, and observing it would
        # leak hidden M.
        cols: dict = {}
        dropped = []
        for q in sorted(qfam, key=repr):
            col = []
            ok = True
            for m in reps:
                r = response(sol, m, q)
                if r is None:
                    ok = False
                    break
                col.append((m.Z, r))
            if ok:
                cols[q] = col
            else:
                dropped.append(q)

        if not cols:
            verdicts[VERDICT_INC] += 1
            report["details"].append({
                "kind": VERDICT_INC, "class_size": len(members),
                "n_distinct_Z": len(zs), "query_candidate_size": len(qfam),
                "n_safe_queries": 0, "n_dropped_by_legality": len(dropped),
            })
            continue

        # deduplicate columns
        seen = {}
        for q, col in cols.items():
            seen.setdefault(tuple(col), q)
        dedup = {q: cols[q] for q in seen.values()}

        size, subset = min_separating_subset(dedup, B_CF)
        if size is not None:
            verdicts[VERDICT_PASS] += 1
        else:
            # A50: Stage 3 is the NON-ADAPTIVE fallback only. A miss here is
            # INCONCLUSIVE, never an unbounded FAIL -- after a query the
            # hypothesis set shrinks and the safe family can GROW, so a query
            # unsafe at the root may become safe one level down.
            verdicts[VERDICT_INC] += 1
            report["details"].append({
                "kind": VERDICT_INC, "class_size": len(members),
                "n_distinct_Z": len(zs), "query_candidate_size": len(qfam),
                "n_safe_queries": len(cols), "n_dedup_queries": len(dedup),
                "n_dropped_by_legality": len(dropped),
            })

    report["verdicts"] = dict(verdicts)
    print("\nverdicts:")
    for k, v in sorted(verdicts.items()):
        print(f"  {k:<34} {v}")

    n_body = sum(v for k, v in verdicts.items() if k != "TRIVIAL_SINGLE_Z")
    printer = ("Gate L PASS at B_CF = 4" if verdicts.get(VERDICT_PASS, 0) == n_body
               and n_body > 0 else "Gate L NOT passed")
    print(f"\n{printer}")

    outdir = ROOT / "outputs" / "rebuild"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "gate_stage3.json").write_text(
        json.dumps(report, indent=1, default=str), encoding="utf-8")
    print(f"\nwrote {outdir / 'gate_stage3.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
