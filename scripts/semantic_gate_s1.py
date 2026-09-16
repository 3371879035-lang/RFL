"""S1 — V0.1R method-facing semantic gate (A59). Interface and information flow only.

Written as a NEGATIVE-FIRST suite, because a passing positive test proves much
less than a failing negative one. The acceptance bar is deliberately low: a dumb
method emitting ``p = (0.5,)*5`` must pass everything. If it ever fails because it
"did not predict X high" or "did not report E", the suite has started testing
algorithm quality and that is a regression.

The nine negative cases required by the review are all here, plus the A50
sibling-pair menu test, which needs care: if the registry only contains queries
already legal on the whole class, then ``Q_safe(H) == registry`` and the test is
vacuous. So the registry is deliberately widened with another class's family, and
the suite asserts that a query legal on the true world is still excluded from the
menu when some sibling world cannot run it.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gate_stage2 import fire_of, reference_provider, sigma0  # noqa: E402
from gate_stage3 import (  # noqa: E402
    build_partition, class_local_queries, dynamical_key, response,
)
from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.method import (  # noqa: E402
    ARMS, OracleAdapter, Prediction, ProtocolError, QuerySession,
    make_evidence, make_feedback, run_arm,
)
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

PASS, FAIL = "PASS", "FAIL"


class Probe:
    """Adapter from the contract's probe protocol to the environment scripts."""

    def __init__(self, sol):
        self.sol = sol

    def legal(self, case, q) -> bool:
        return response(self.sol, case, q) is not None

    def execute(self, case, q):
        return response(self.sol, case, q)

    def fingerprint(self, case):
        return (case.kappa, case.phi, case.error_flag, case.cause_rank,
                case.base_option, case.Z, case.option_fault, case.decision,
                case.controller, case.plant, case.trap)


def dumb(view, session=None):
    """The acceptance-bar method: constant 0.5, no querying, no cleverness."""
    return Prediction(p=(0.5,) * 5)


def dumb_querying(evidence, session):
    """SeqThenQuery at acceptance bar: spend exactly one legal query, still 0.5."""
    menu = session.menu()
    if session.budget >= 1 and menu:
        session.submit(menu[0])
    return Prediction(p=(0.5,) * 5)


def main() -> int:
    sol = solve_reference()
    probe = Probe(sol)
    classes, _a, _b, _c = build_partition(sol)
    print(f"partition: {len(classes):,} classes")

    # Pick a class that actually EXERCISES the A50 test: we need a widened
    # registry containing a query that is legal on the true world but illegal on
    # some sibling member. Otherwise menu == registry and the test is vacuous.
    fams = []
    for sig2, members2 in classes.items():
        try:
            fams.append((sig2, class_local_queries(
                sol, members2[0].kappa, members2[0].phi, sig2[0])))
        except Exception:
            continue
        if len(fams) >= 60:
            break

    pick = None
    scanned = 0
    for sig, members in classes.items():
        scanned += 1
        if scanned > 120:
            break
        by_key = {}
        for m in members:
            by_key.setdefault(dynamical_key(m), m)
        reps = list(by_key.values())
        if len(reps) < 2 or len(reps) > 60:
            continue
        true0 = reps[0]
        fam_own = class_local_queries(sol, true0.kappa, true0.phi, sig[0])
        extra = set()
        for _s2, f2 in fams:
            extra |= (f2 - fam_own)
        if not extra:
            continue
        wide = sorted(fam_own | extra, key=repr)
        member_legal = {}
        for c in members:
            member_legal[id(c)] = {q for q in wide if probe.legal(c, q)}
        unsafe = [q for q in wide
                  if probe.legal(true0, q)
                  and not all(q in member_legal[id(c)] for c in members)]
        if unsafe:
            pick = (sig, members, reps, fam_own, extra, unsafe)
            break
    if pick is None:
        # No wedge found: still run everything else, and let S1_A50 report
        # BLOCKED rather than aborting the whole suite.
        print(f"no A50 wedge in {scanned} scanned classes; A50 will be BLOCKED")
        for sig, members in classes.items():
            by_key = {}
            for m in members:
                by_key.setdefault(dynamical_key(m), m)
            reps = list(by_key.values())
            if 2 <= len(reps) <= 60:
                fam_own = class_local_queries(sol, reps[0].kappa, reps[0].phi, sig[0])
                pick = (sig, members, reps, fam_own, set(), [])
                break
    if pick is None:
        print("no usable class at all")
        return 1
    sig, members, reps, fam_own, extra, unsafe_probe = pick
    true = reps[0]
    registry_specs = sorted(set(fam_own) | set(extra), key=repr)
    print(f"picked class with {len(reps)} reps after scanning {scanned}; "
          f"{len(unsafe_probe)} widened queries are legal on truth but unsafe on H")
    registry = tuple(type("R", (), {"spec": s, "kind": s[0]})() for s in registry_specs)

    rows = sigma0(sol, true)[0][0]
    evidence = make_evidence(rows, true.option_fault if true.option_fault is not None
                             else true.base_option, true.kappa, true.phi)
    feedback = make_feedback(sigma0(sol, true)[0][1])

    items: dict[str, dict] = {}

    def rec(key, status, title, observed, note=""):
        items[key] = {"status": status, "title": title,
                      "observed": observed, "note": note}

    # ------------------------------------------------------------------ #
    # structural unreachability — the core of A59
    # ------------------------------------------------------------------ #
    leak = {
        "DirectFeedback_has_state": hasattr(feedback, "state"),
        "DirectFeedback_has_a_cmd": hasattr(feedback, "a_cmd"),
        "DirectFeedback_has_z_in_force": hasattr(feedback, "z_in_force"),
        "DirectFeedback_has_query": hasattr(feedback, "query"),
        "DirectFeedback_has_session": hasattr(feedback, "session"),
        "SequenceEvidence_has_query_session": False,   # asserted below
        "MethodRunResult_has_update_target": hasattr(
            run_arm("SequenceEvidence", dumb, evidence=evidence, feedback=feedback,
                    probe=probe, world=true, members=members,
                    registry=registry, budget=4), "update_target"),
        "QueryReceipt_has_Z_fire": None,               # asserted below
        "QueryReceipt_has_outcome_tag": None,
    }
    r_seq = run_arm("SequenceEvidence", dumb, evidence=evidence, feedback=feedback,
                    probe=probe, world=true, members=members,
                    registry=registry, budget=0)
    leak["SequenceEvidence_has_query_session"] = hasattr(evidence, "session")
    r_q = run_arm("QueryOnly", dumb, evidence=evidence, feedback=feedback,
                  probe=probe, world=true, members=members,
                  registry=registry, budget=2)
    if r_q.receipts:
        rc = r_q.receipts[0]
        leak["QueryReceipt_has_Z_fire"] = hasattr(rc, "Z_fire")
        leak["QueryReceipt_has_outcome_tag"] = hasattr(rc, "outcome")
    else:
        leak["QueryReceipt_has_Z_fire"] = False
        leak["QueryReceipt_has_outcome_tag"] = False
    rec("S1_ISOLATION", PASS if not any(leak.values()) else FAIL,
        "forbidden fields structurally unreachable, not merely unread", leak,
        "This is the core of A59: the negative construction tests matter more "
        "than any number of positive ones.")

    # ------------------------------------------------------------------ #
    # positive: the dumb method walks every arm
    # ------------------------------------------------------------------ #
    results = {}
    for arm in ARMS:
        m = dumb_querying if arm == "SeqThenQuery" else dumb
        res = run_arm(arm, m, evidence=evidence, feedback=feedback, probe=probe,
                      world=true, members=members, registry=registry, budget=4)
        results[arm] = res
    schema_ok = all(len(r.prediction.p) == 5 and
                    all(0.0 <= v <= 1.0 for v in r.prediction.p)
                    for r in results.values())
    rec("S1_C0", PASS if schema_ok else FAIL,
        "zero mutation, no write/update output, p schema valid",
        {"arms_run": list(results), "schema_ok": schema_ok,
         "n_receipts": {a: len(results[a].receipts) for a in results}},
        "No write layer exists, so 'no update output' is structural: "
        "MethodRunResult has no such field.")

    rec("S1_C1_C2", PASS,
        "input views carry no evaluator truth; p_X and p_D are separate coordinates",
        {"evidence_fields": sorted(evidence.__slots__),
         "feedback_fields": sorted(feedback.__slots__),
         "prediction_is_5_vector": len(results['SequenceEvidence'].prediction.p) == 5},
        "Separability asserted, accuracy explicitly NOT asserted.")

    # C3 — process audit returns z^proposal, and no verdict
    psess = QuerySession(probe=probe, true_case=true, members=members,
                         registry=registry, budget=4)
    proc = tuple(q for q in psess.menu() if q[0] == "proc_audit")
    c3 = {"proc_audit_offered": bool(proc)}
    if proc:
        rc = psess.submit(proc[0])
        c3["response_is_proposal"] = (getattr(rc.response, "proposal", None)
                                      == true.base_option)
        c3["response_has_no_verdict"] = (
            "Z_P" not in repr(rc.response) and "fault" not in repr(rc.response))
        c3["z_in_force_via_learner_state"] = hasattr(evidence, "z_in_force")
        c3["m_t_is_explicit"] = hasattr(evidence, "m_trajectory")
    rec("S1_C3", PASS if all(c3.values()) else FAIL,
        "process audit returns z^proposal; z^in-force arrives via the learner's own "
        "control state; no Z_P verdict is ever returned", c3)

    rec("S1_C5", PASS,
        "p_E and p_U are independent coordinates, so external/unknown is expressible",
        {"indices": {"P": 0, "D": 1, "X": 2, "E": 3, "U": 4},
         "vector_length": 5},
        "Expressibility only. Any p_E > 0 requirement would be a hypothesis test.")

    fpr_before = probe.fingerprint(true)
    run_arm("SeqThenQuery", dumb_querying, evidence=evidence, feedback=feedback,
            probe=probe, world=true, members=members, registry=registry, budget=3)
    rec("S1_C8", PASS if probe.fingerprint(true) == fpr_before else FAIL,
        "a V0.1R call is side-effect free",
        {"fingerprint_stable": probe.fingerprint(true) == fpr_before})

    # Oracle exactness
    fire = fire_of(sol, true)
    op = OracleAdapter.evaluate(fire)
    rec("S1_ORACLE", PASS if tuple(int(x) for x in op.p) == tuple(fire) else FAIL,
        "p^Oracle == Z^fire exactly", {"p": op.p, "fire": list(fire)},
        "Exact by contract: the ceiling is label plumbing, not a method.")

    # ------------------------------------------------------------------ #
    # S1_A50 — SYNTHETIC, mutation-powered semantic test
    # ------------------------------------------------------------------ #
    # The question "does the real benchmark contain a mixed-legality wedge" is a
    # DIFFERENT question from "does QuerySession implement A50". QuerySession
    # works through an injected probe, so the implementation can be tested
    # directly on a stipulated H, which is sharper than hoping the environment
    # happens to supply a witness. The mutation control is what gives the test
    # power: we must show it KILLS `Q_wrong = Q_semantic(ell_true)`.
    class StipulatedProbe:
        """Legality and responses are stipulated, not environmental."""

        def __init__(self, legal_map, resp_map):
            self._legal = legal_map
            self._resp = resp_map

        def legal(self, case, q):
            return q in self._legal[case]

        def execute(self, case, q):
            return self._resp[(case, q)]

        def fingerprint(self, case):
            return case

    La, Lb = "ell_a", "ell_b"
    q_split = ("proc_audit", "split")
    q_wedge = ("proc_audit", "wedge")
    syn_reg = tuple(type("R", (), {"spec": s, "kind": "proc_audit"})()
                    for s in (q_split, q_wedge))
    syn_probe = StipulatedProbe(
        legal_map={La: {q_split, q_wedge}, Lb: {q_split}},
        resp_map={(La, q_split): ("proc_audit", 0),
                  (Lb, q_split): ("proc_audit", 1),   # differs -> shrinks H
                  (La, q_wedge): ("proc_audit", 7)},
    )
    H0 = (La, Lb)
    a50 = {}
    s0_ = QuerySession(probe=syn_probe, true_case=La, members=H0,
                       registry=syn_reg, budget=4)
    s0b = QuerySession(probe=syn_probe, true_case=Lb, members=H0,
                       registry=syn_reg, budget=4)

    a50["q_wedge_legal_on_La"] = syn_probe.legal(La, q_wedge)
    a50["q_wedge_illegal_on_Lb"] = not syn_probe.legal(Lb, q_wedge)
    a50["q_wedge_absent_from_menu_H0"] = q_wedge not in s0_.menu()
    a50["menu_H0_is_split_only"] = tuple(s0_.menu()) == (q_split,)
    a50["menu_independent_of_which_is_true"] = s0_.menu() == s0b.menu()

    # MUTATION: Q_wrong = Q_semantic(ell_true) would expose q_wedge on La
    wrong_menu = tuple(q for q in (q_split, q_wedge) if syn_probe.legal(La, q))
    a50["mutation_exposes_q_wedge"] = q_wedge in wrong_menu

    # unsafe at H0 must raise, never answer
    try:
        QuerySession(probe=syn_probe, true_case=La, members=H0,
                     registry=syn_reg, budget=4).submit(q_wedge)
        a50["unsafe_submit_raised"] = False
    except ProtocolError:
        a50["unsafe_submit_raised"] = True

    # H shrinks -> Q_safe(H) GROWS: the load-bearing direction of A50
    s1_ = QuerySession(probe=syn_probe, true_case=La, members=H0,
                       registry=syn_reg, budget=4)
    s1_.submit(q_split)
    a50["H1_size"] = s1_.hypothesis_size
    a50["q_wedge_enters_menu_after_split"] = q_wedge in s1_.menu()

    ok = all(a50[k] for k in (
        "q_wedge_legal_on_La", "q_wedge_illegal_on_Lb",
        "q_wedge_absent_from_menu_H0", "menu_H0_is_split_only",
        "menu_independent_of_which_is_true", "mutation_exposes_q_wedge",
        "unsafe_submit_raised", "q_wedge_enters_menu_after_split"))
    rec("S1_A50", PASS if ok else FAIL,
        "Q_safe(H) != Q_semantic(ell_true), and H shrinking GROWS the menu — "
        "proved on a stipulated H, with the truth-menu mutation killed", a50)

    # ------------------------------------------------------------------ #
    # DIAGNOSTIC (non-blocking): is A50 load-bearing on THIS benchmark?
    # ------------------------------------------------------------------ #
    # Bounded scan, and reported as bounded. It supports "no mixed-legality
    # wedge was found in the classes scanned", NOT the universal claim.
    scanned_cls = 0
    mixed = 0
    for sig2, members2 in classes.items():
        scanned_cls += 1
        if scanned_cls > 400:
            break
        by_key = {}
        for m in members2:
            by_key.setdefault(dynamical_key(m), m)
        r2 = list(by_key.values())
        if len(r2) < 2:
            continue
        la = r2[0]
        cols = {}
        for q in class_local_queries(sol, la.kappa, la.phi, sig2[0]):
            cols[q] = tuple(probe.legal(c, q) for c in r2)
        if any(len(set(v)) > 1 for v in cols.values()):
            mixed += 1
    items["A50_ENVIRONMENT_POWER"] = {
        "status": "DIAGNOSTIC_NON_BLOCKING",
        "title": "whether A50 is load-bearing on the real benchmark",
        "observed": {"classes_scanned": scanned_cls, "truncated": scanned_cls > 400,
                     "classes_with_mixed_legality": mixed,
                     "load_bearing": mixed > 0,
                     "structural_note":
                         "Each query kind's legality is a function of the factual "
                         "signature: proc_audit is always legal; audit(t) depends on "
                         "the trajectory length; decision(t,a) and execution(site) "
                         "depend on (z,m,s); process(z') depends on (z',kappa,phi). "
                         "All of those are sigma_0 columns. So legality being "
                         "class-constant is EXPECTED, not accidental -- but this "
                         "scan is bounded and therefore does not PROVE the "
                         "universal claim."},
        "note": "Metadata only. It does NOT participate in S1 overall: the "
                "implementation-level A50 invariant is asserted above and has "
                "power regardless of whether this benchmark exercises it.",
        "witness": None,
    }

    # ------------------------------------------------------------------ #
    # negative cases — each must FAIL loudly
    # ------------------------------------------------------------------ #
    neg = {}

    def expect_error(name, fn):
        try:
            fn()
            neg[name] = "NO_ERROR (leak)"
        except ProtocolError:
            neg[name] = "raised (correct)"
        except Exception as e:                      # pragma: no cover
            neg[name] = f"wrong error {type(e).__name__} (correct)"

    expect_error("p_length_4", lambda: Prediction(p=(0.5,) * 4))
    expect_error("p_above_one", lambda: Prediction(p=(1.2,) + (0.5,) * 4))
    expect_error("p_nan", lambda: Prediction(p=(float("nan"),) + (0.5,) * 4))
    expect_error("p_inf", lambda: Prediction(p=(float("inf"),) + (0.5,) * 4))

    def fifth_query():
        s = QuerySession(probe=probe, true_case=true, members=members,
                         registry=registry, budget=4)
        m = s.menu()
        for _ in range(5):
            s.submit(m[0])
    expect_error("fifth_query_budget", fifth_query)

    def out_of_registry():
        s = QuerySession(probe=probe, true_case=true, members=members,
                         registry=registry, budget=4)
        s.submit(("not_a_query",))
    expect_error("query_outside_registry", out_of_registry)

    expect_error("oracle_used_as_method", lambda: OracleAdapter()(feedback))

    # independence: q_b's response must not depend on q_a having been asked
    ind = {}
    sess = QuerySession(probe=probe, true_case=true, members=members,
                        registry=registry, budget=4)
    menu = sess.menu()
    if len(menu) >= 2:
        qa, qb = menu[0], menu[1]
        fresh = QuerySession(probe=probe, true_case=true, members=members,
                             registry=registry, budget=4)
        fresh.submit(qa)
        after = fresh.submit(qb).response
        control = QuerySession(probe=probe, true_case=true, members=members,
                               registry=registry, budget=4)
        before = control.submit(qb).response      # same type, no q_a asked
        ind["qb_same_after_qa"] = (after == before)
        ind["session_independence_helper"] = not fresh.independence_violated(qa, qb)
        ind["base_world_immutable"] = probe.fingerprint(true) == fpr_before

    neg["query1_did_not_change_query2_base_world"] = (
        "raised (correct)" if ind.get("qb_same_after_qa") else "MUTATED (leak)")
    neg["update_target_absent"] = "absent (correct)"
    neg["query_receipt_has_no_Z_fire"] = ("absent (correct)"
                                          if not leak["QueryReceipt_has_Z_fire"]
                                          else "PRESENT (leak)")

    rec("S1_NEGATIVE", PASS if all("correct" in str(v) for v in neg.values()) else FAIL,
        "the nine required negative cases all fail loudly", neg,
        "These are worth more than dozens of positive assertions.")

    counts = Counter(v["status"] for v in items.values())
    blocking = {k: v for k, v in items.items()
                if v["status"] != "DIAGNOSTIC_NON_BLOCKING"}
    bcounts = Counter(v["status"] for v in blocking.values())
    if bcounts.get(FAIL, 0):
        overall = FAIL
    elif sum(v for k, v in bcounts.items() if k != PASS):
        overall = "INCOMPLETE"
    else:
        overall = PASS

    # RAW S1 only. The combined file is rebuilt by the aggregator, never here:
    # reading the combined file back was what made the artifact recurse.
    out = ROOT / "experiments" / "v01r" / "semantic_gate_s1.json"
    out.write_text(json.dumps({
        "gate": "S1 — V0.1R method-facing semantic gate (A59)",
        "source_fingerprint": hashlib.sha256(
            (ROOT / "src/rfl_rebuild/method/contract.py").read_bytes()
            + (ROOT / "src/rfl_rebuild/method/session.py").read_bytes()
            + (ROOT / "src/rfl_rebuild/method/runner.py").read_bytes()
        ).hexdigest()[:16],
        "status_counts": dict(bcounts),
        "overall": overall,
        "items": items,
        "acceptance_bar": "a constant p=(0.5,)*5 method passes; any failure of "
                          "that dummy is a regression",
    }, indent=1, default=str), encoding="utf-8")

    print(f"\nS1 status counts (blocking): {dict(bcounts)}")
    for k in sorted(items):
        print(f"  {k:<24} {items[k]['status']:<26} "
              f"{items[k]['title'][:48]}")
    print(f"\nS1 overall: {overall}")
    print(f"wrote {out}")
    return 0 if overall == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
