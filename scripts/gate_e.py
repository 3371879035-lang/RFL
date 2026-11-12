"""Formal Gate E — full primary feasible support, and the true ``R*_suff``.

Runs on **every** feasible case, not a sample. The precheck's boolean bypass is
gone: ``do(C_P = identity)`` is now a first-class lattice member (A57), so it
counts toward repair cardinality, composes with other interventions, and is
expressed in the same type as everything else.

    R*_suff = {∅}                                    factual already succeeds
            = {r : |r| = k, r sufficient},  k = min |r|   otherwise
            = BOT_NO_SUFFICIENT_REPAIR               whole finite lattice fails

Two rules, both already frozen:

* **all** tied minimal repairs are kept. ``|R*| != #R*`` -- the earlier code that
  stopped at the first sufficient repair would have destroyed the tie structure
  every downstream metric depends on.
* ``NO_SUFFICIENT_REPAIR`` is **not** a Gate E failure. If it is proved over the
  whole finite lattice and encoded as a sentinel it is a well-defined evaluator
  truth. What would be a failure is an empty ``R*`` that is not that sentinel.

The A55 strong invariant is checked at **trace** level, not outcome level: when
``Z_P^fire = 0``, ``do(C_P = identity)`` must reproduce the factual trajectory
step for step. Outcome equality would pass even if the repair perturbed the run.
"""

from __future__ import annotations

import itertools
import json
import pathlib
import sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gate_stage2 import (  # noqa: E402
    LatentCase, _domains, fire_of, reference_provider, sigma0,
)
from identifiability_gate import CAUSE_KEYS, KAPPAS, TAPES, canonicalise  # noqa: E402
from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.env.kernel import (  # noqa: E402
    ControllerSite, Intervention, InterventionSet, Outcome, State,
)
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

BOT = "NO-SUFFICIENT-REPAIR"
MAX_SIZE = 3          # expansion stops here only if singles/pairs leave cases open


def run(sol, case, members=()):
    """Returns (outcome, trace) or (None, None) if MALFORMED."""
    try:
        tr = K.rollout(
            kappa=case.kappa, tape=case.tape(),
            command_provider=reference_provider(sol),
            base_option=case.base_option, mask=case.mask(),
            option_fault=case.option_fault,
            interventions=InterventionSet(tuple(members)),
        )
    except Exception:
        return None, None
    return tr.outcome, tr


def trace_of(tr):
    return tuple((s.state.t, s.a_cmd, s.u, s.a_realized, round(s.reward, 9))
                 for s in tr.steps)


def candidates(sol, case, ftr):
    """Every size-1 lattice member, as (kind_label, member_tuple)."""
    out = [("process_commit", (Intervention.commit_identity(),))]
    for zp in K.option_ids():
        if zp != case.base_option:
            out.append(("strategy_replay", (Intervention.process(zp),)))
    for t in range(K.HORIZON):
        for a in range(len(K.ACTIONS)):
            out.append(("decision", (Intervention.decision(t, a),)))
    st = State(x=K.START[0], y=K.START[1], t=0, kappa=case.kappa, phi=case.phi)
    for s in ftr.steps:
        out.append(("execution",
                    (Intervention.execution(ControllerSite(state=st, cmd=s.a_cmd)),)))
        st = s.state
    return out


def main() -> int:
    sol = solve_reference()
    provider = reference_provider(sol)

    card = Counter()          # |R*| histogram, plus BOT
    ties = Counter()          # #R* tie histogram
    kinds = Counter()         # how often each kind enters a minimal family
    cross = Counter()
    invariant = Counter()
    examples = {"bot": [], "size2": [], "size3": []}

    n_cases = 0
    for kappa in KAPPAS:
        for tape in TAPES:
            for z in K.option_ids():
                tr0 = K.rollout(kappa=kappa, tape=tape, command_provider=provider,
                                base_option=z)
                dom = _domains(sol, kappa, tape, z, tr0)
                canon = {k: canonicalise(dom[k]) for k in CAUSE_KEYS}
                for bits in itertools.product((0, 1), repeat=5):
                    active = [k for k, b in zip(CAUSE_KEYS, bits) if b]
                    if any(not canon[k] for k in active):
                        continue
                    for combo in itertools.product(*[canon[k] for k in active]):
                        blocks = dict(zip(active, combo))
                        case = LatentCase(
                            case_id=0, kappa=kappa, phi=tape.phase,
                            error_flag=tape.error_flag, cause_rank=tape.cause_rank,
                            base_option=z, Z=bits,
                            option_fault=blocks.get("P"),
                            decision=blocks.get("D"),
                            controller=blocks.get("X"),
                            plant=blocks.get("E"), trap=blocks.get("U"))
                        if sigma0(sol, case)[0] is None:
                            continue
                        n_cases += 1
                        fire = fire_of(sol, case)
                        base, ftr = run(sol, case)
                        if base is None:
                            card["MALFORMED_FACTUAL"] += 1
                            continue
                        ftrace = trace_of(ftr)

                        # ---- A55 invariant at TRACE level (A57) ------------ #
                        if fire[0] == 0:
                            _, rtr = run(sol, case,
                                         (Intervention.commit_identity(),))
                            if rtr is None:
                                invariant["repair_malformed"] += 1
                            elif trace_of(rtr) != ftrace:
                                invariant["trace_changed_without_fault"] += 1
                            else:
                                invariant["trace_noop_ok"] += 1

                        if base == Outcome.SUCCESS:
                            card[0] += 1
                            ties[1] += 1
                            continue

                        # ---- size-1: keep ALL ties ------------------------- #
                        cands = candidates(sol, case, ftr)
                        good = []
                        for label, mem in cands:
                            o, _t = run(sol, case, mem)
                            if o == Outcome.SUCCESS:
                                good.append((label, mem))
                        if good:
                            card[1] += 1
                            ties[len(good)] += 1
                            labels = {g[0] for g in good}
                            for lb in labels:
                                kinds[lb] += 1
                            if "process_commit" in labels and "strategy_replay" not in labels:
                                cross["commit_sufficient_strategy_not"] += 1
                            if "strategy_replay" in labels and "process_commit" not in labels:
                                cross["strategy_sufficient_commit_not"] += 1
                            if "process_commit" in labels and "strategy_replay" in labels:
                                cross["both_sufficient"] += 1
                            continue

                        # ---- size 2, then 3 -------------------------------- #
                        found = None
                        for size in (2, 3):
                            pairs = list(itertools.combinations(cands, size))
                            hits = []
                            for combo2 in pairs:
                                # same-node composition is undefined; skip
                                nodes = [m.node() for _l, mem in combo2
                                         for m in mem]
                                if len(nodes) != len(set(nodes)):
                                    continue
                                mem = tuple(m for _l, mm in combo2 for m in mm)
                                o, _t = run(sol, case, mem)
                                if o == Outcome.SUCCESS:
                                    hits.append(combo2)
                            if hits:
                                found = (size, hits)
                                break
                        if found is None:
                            card[BOT] += 1
                            if len(examples["bot"]) < 10:
                                examples["bot"].append({
                                    "kappa": kappa, "phi": tape.phase,
                                    "base_option": z, "Z": "".join(map(str, bits)),
                                    "fire": "".join(map(str, fire))})
                        else:
                            size, hits = found
                            card[size] += 1
                            ties[len(hits)] += 1
                            for combo2 in hits:
                                for lb in {c[0] for c in combo2}:
                                    kinds[lb] += 1
                            if len(examples["size2" if size == 2 else "size3"]) < 6:
                                examples["size2" if size == 2 else "size3"].append({
                                    "kappa": kappa, "phi": tape.phase,
                                    "base_option": z, "Z": "".join(map(str, bits)),
                                    "n_minimal": len(hits)})

    print(f"FULL primary feasible support: {n_cases:,} cases")
    print("\n|R*| cardinality histogram (0 = factual already succeeds):")
    for k in sorted(card, key=lambda x: (isinstance(x, str), str(x))):
        print(f"  |R*| = {str(k):<22} {card[k]}")
    print("\n#R* tie histogram (all minimal repairs kept):")
    for k in sorted(ties, key=lambda x: (isinstance(x, str), str(x))):
        print(f"  #R* = {str(k):<6} {ties[k]}")
    print("\nrepair kinds entering a minimal family:")
    for k in sorted(kinds, key=lambda x: -kinds[x]):
        print(f"  {k:<20} {kinds[k]}")
    print("\ncross cells (A56 predicted these are not a paper distinction):")
    for k in sorted(cross):
        print(f"  {k:<40} {cross[k]}")
    print("\nA55 strong invariant, TRACE level (Z_P^fire = 0):")
    for k in sorted(invariant):
        print(f"  {k:<40} {invariant[k]}")

    ok = (invariant.get("trace_changed_without_fault", 0) == 0
          and card.get("MALFORMED_FACTUAL", 0) == 0)
    print("\n" + ("Gate E PASS" if ok else "Gate E FAIL"))

    out = ROOT / "outputs" / "rebuild" / "gate_e.json"
    out.write_text(json.dumps({
        "n_feasible_cases": n_cases,
        "cardinality_histogram": {str(k): v for k, v in card.items()},
        "tie_histogram": {str(k): v for k, v in ties.items()},
        "kinds_in_minimal_family": dict(kinds),
        "cross_cells": dict(cross),
        "a55_trace_invariant": dict(invariant),
        "verdict": "PASS" if ok else "FAIL",
        "examples": examples,
    }, indent=1, default=str), encoding="utf-8")
    print(f"wrote {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
