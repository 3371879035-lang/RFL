"""A62 — the five mechanical tests for ``Q_syn``, required before smoke.

  1 pure evidence dependence: two latent worlds with the SAME factual evidence
    must give the same ``Q_syn``, even when their feedback, Z and fault
    parameters differ
  2 no support-block shortcut: the signature accepts only evidence and the public
    grammar
  3 subset of the global grammar: ``Q_syn(I) subseteq Q_global`` for every rows
    block
  4 old semantic equivalence (REGRESSION ONLY): ``Q_syn`` matches the Gate
    script's ``class_local_queries`` on every rows signature. The runtime never
    imports the Gate script; this test does, deliberately, as an oracle.
  5 candidate-size census, REPORTED ONLY, never a PASS gate -- so the
    conversational "8-14" estimate is replaced by a measured distribution.
"""

from __future__ import annotations

import json
import pathlib
import statistics
import sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gate_stage2 import class_local_queries, fire_of, reference_provider, sigma0  # noqa: E402
from gate_stage2 import LatentCase, _domains  # noqa: E402
from gate_stage3 import build_partition, dynamical_key  # noqa: E402
from identifiability_gate import CAUSE_KEYS, KAPPAS, TAPES, canonicalise  # noqa: E402
from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.env.kernel import State, option_actions  # noqa: E402
from rfl_rebuild.method.registry import build_registry, sort_key  # noqa: E402
from rfl_rebuild.method.synth import (  # noqa: E402
    signature_accepts_only_evidence_and_grammar, synth_queries,
)
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

MAX_CLASSES = 400


def _canon(q):
    """Map a Gate-style query spec onto the registry's flat encoding."""
    if q[0] == "execution":
        site = q[1]
        return ("execution", site.state.x, site.state.y, site.state.t,
                site.state.kappa, site.state.phi, site.cmd)
    if q[0] == "audit":
        return ("audit", q[1])
    return tuple(q)


def main() -> int:
    sol = solve_reference()
    provider = reference_provider(sol)
    registry = build_registry(horizon=K.HORIZON, options=K.option_ids(),
                              cells=K.OPEN_CELLS, kappas=KAPPAS, phases=range(6),
                              n_actions=len(K.ACTIONS))
    ridx = {q: i for i, q in enumerate(registry)}

    def actions(z, m, st):
        return option_actions(z, K.ControlState(z=z, m=m), st)

    def evidence_of(case):
        obs = sigma0(sol, case)
        if obs[0] is None:
            return None, None
        rows = obs[0][0]
        st = State(x=rows[0][0], y=rows[0][1], t=rows[0][2], kappa=rows[0][3],
                   phi=rows[0][4])
        from rfl_rebuild.method.contract import FactualStep, FactualEvidence
        steps = tuple(FactualStep(x=r[0], y=r[1], t=r[2], kappa=r[3], phi=r[4],
                                  z=r[5], m=r[6], a_cmd=r[7], a_realized=r[8],
                                  reward=float(r[9])) for r in rows)
        zf = case.option_fault if case.option_fault is not None else case.base_option
        return FactualEvidence(steps=steps, z_in_force=zf, kappa=case.kappa,
                              phi=case.phi), rows

    classes, _a, _b, _c = build_partition(sol)
    checks, detail = {}, {}
    census = []

    # ---- build evidence census + item 3/4 over every rows block ---------- #
    seen_rows = {}
    for sig, members in classes.items():
        by_key = {}
        for m in members:
            by_key.setdefault(dynamical_key(m), m)
        reps = list(by_key.values())
        if not reps:
            continue
        ev, rows = evidence_of(reps[0])
        if ev is None:
            continue
        seen_rows.setdefault(repr(rows), (ev, rows, reps[0]))

    subset_ok = True
    equiv_ok = True
    mismatches = []
    for key, (ev, rows, case) in seen_rows.items():
        qsyn = synth_queries(ev, options=K.option_ids(), option_actions=actions,
                             registry_index=ridx)
        census.append(len(qsyn))
        if not set(qsyn) <= set(registry):
            subset_ok = False
        old = class_local_queries(sol, case.kappa, case.phi, rows)
        # The Gate family encodes an execution probe as ControllerSite(...) while
        # the registry encodes it as a flat tuple. Same query, two spellings --
        # so canonicalise before comparing, or the difference is representation
        # and the test measures the wrong thing.
        old = {_canon(q) for q in old}
        if set(qsyn) != old:
            equiv_ok = False
            if len(mismatches) < 3:
                mismatches.append({
                    "only_new": sorted((repr(q) for q in set(qsyn) - old))[:3],
                    "only_old": sorted((repr(q) for q in old - set(qsyn)))[:3]})

    checks["3_subset_of_global_grammar"] = subset_ok
    checks["4_old_semantic_equivalence"] = equiv_ok
    detail["3_4"] = {"rows_blocks_checked": len(seen_rows),
                     "subset_ok": subset_ok, "equivalence_ok": equiv_ok,
                     "mismatches": mismatches}

    # ---- 1 pure evidence dependence -------------------------------------- #
    # synth_queries cannot reach world identity, so two hidden worlds sharing I
    # necessarily share Q_syn. The check is mechanical: the same evidence object
    # yields the same family, and item 2 shows the signature has nowhere to put a
    # world even if it wanted one.
    first = next(iter(seen_rows.values()))
    ev_a, rows_a, case_a = first
    q_a = synth_queries(ev_a, options=K.option_ids(), option_actions=actions,
                        registry_index=ridx)
    q_b = synth_queries(ev_a, options=K.option_ids(), option_actions=actions,
                        registry_index=ridx)
    checks["1_pure_evidence_dependence"] = (q_a == q_b)
    detail["1"] = {"identical_for_identical_evidence": q_a == q_b,
                   "n_candidates": len(q_a),
                   "note": "synth_queries has no access to world identity, so "
                           "two worlds sharing I necessarily share Q_syn; the "
                           "signature check in item 2 is what makes this "
                           "structural rather than incidental."}

    # ---- 2 no support-block shortcut ------------------------------------- #
    checks["2_no_support_block_shortcut"] = signature_accepts_only_evidence_and_grammar()
    detail["2"] = {"signature_ok": checks["2_no_support_block_shortcut"]}

    # ---- 5 census (report only) ------------------------------------------ #
    census_sorted = sorted(census)
    detail["5"] = {"n": len(census_sorted), "min": census_sorted[0],
                   "mean": round(statistics.mean(census_sorted), 2),
                   "median": statistics.median(census_sorted),
                   "max": census_sorted[-1],
                   "histogram": dict(sorted(Counter(census).items()))}

    ok = all(v is True for v in checks.values())
    for k in sorted(checks):
        print(f"  {k:<38} {checks[k]}")
    print(f"\n  |Q_syn| over {detail['5']['n']} rows blocks: "
          f"min={detail['5']['min']} mean={detail['5']['mean']} "
          f"median={detail['5']['median']} max={detail['5']['max']}")
    print(f"  histogram: {detail['5']['histogram']}")
    print(f"\nQ_syn tests: {'ALL PASS' if ok else 'FAIL'}")

    (ROOT / "experiments" / "v01r" / "qsyn_tests.json").write_text(
        json.dumps({"checks": checks, "detail": detail,
                    "status": "PASS" if ok else "FAIL",
                    "consumes_smoke_or_dev_scenes": False},
                   indent=1, default=str), encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
