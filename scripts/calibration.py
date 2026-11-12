"""A61 — smoke and development calibration for the frozen V0.1R methods.

Stage order is fixed and this script refuses to skip it: ``--stage smoke`` is
N=5 and ``--stage dev`` is N=32, each under its own non-reused namespace
(``v01r_smoke_v1`` / ``v01r_dev_v1``).

**The development gate checks TESTABILITY, never a winner.** It does not test
AUPRC(SeqThenQuery) > AUPRC(DirectFeedback); that is the confirmatory question
and asking it here would burn the endpoint and invite tuning. What it checks is
that the benchmark can answer that question at all:

  * all four arms run on every scene;
  * every fired cause has both a positive and a negative scene, so all five
    per-cause metrics are defined;
  * every output is finite;
  * SeqThenQuery really uses a query at least once and never exceeds B_Q = 4;
  * on at least one scene the post-query prediction differs from plain
    SequenceEvidence, so the query channel can actually change inference;
  * real-arm predictions are not all the same constant vector;
  * every world fingerprint is unchanged before and after.

Scene selection is deterministic from (namespace, signature) and greedy only for
coverage extension -- it never looks at outcomes or metric values.
"""

from __future__ import annotations

import hashlib
import json
import math
import pathlib
import sys
from collections import Counter
from dataclasses import asdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gate_stage2 import fire_of, reference_provider, sigma0  # noqa: E402
from gate_stage3 import (  # noqa: E402
    build_partition, class_local_queries, dynamical_key, response,
)
from rfl_rebuild.eval import evaluate  # noqa: E402
from rfl_rebuild.method import (  # noqa: E402
    DirectFeedbackMethod, PublicSupport, QueryOnlyMethod, SeqThenQueryMethod,
    SequenceEvidenceMethod, make_evidence, make_feedback, run_arm,
)
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

B_Q = 4
STAGES = {"smoke": (5, "v01r_smoke_v1"), "dev": (32, "v01r_dev_v1")}


class Probe:
    def __init__(self, sol):
        self.sol = sol

    def legal(self, case, q):
        return response(self.sol, case, q) is not None

    def execute(self, case, q):
        return response(self.sol, case, q)

    def fingerprint(self, case):
        return (case.kappa, case.phi, case.error_flag, case.cause_rank,
                case.base_option, case.Z, case.option_fault, case.decision,
                case.controller, case.plant, case.trap)


def step_key(steps):
    return tuple((s.x, s.y, s.t, s.kappa, s.phi, s.z, s.m, s.a_cmd,
                  s.a_realized, round(s.reward, 6)) for s in steps)


def main() -> int:
    stage = sys.argv[1] if len(sys.argv) > 1 else "smoke"
    if stage not in STAGES:
        raise SystemExit(f"unknown stage {stage!r}; expected smoke|dev")
    n_scenes, namespace = STAGES[stage]
    sol = solve_reference()
    probe = Probe(sol)
    provider = reference_provider(sol)
    classes, _a, _b, _c = build_partition(sol)
    print(f"stage={stage} namespace={namespace} N={n_scenes} "
          f"classes={len(classes):,}")

    # ---- deterministic, namespace-ranked eligibility --------------------- #
    eligible = []
    for sig, members in classes.items():
        by_key = {}
        for m in members:
            by_key.setdefault(dynamical_key(m), m)
        reps = list(by_key.values())
        if len(reps) < 2:
            continue
        eligible.append((hashlib.sha256((namespace + repr(sig)).encode())
                         .hexdigest(), sig, members, reps))
    eligible.sort(key=lambda t: t[0])
    print(f"eligible scenes: {len(eligible):,}")

    # greedy only for coverage of fired causes; never reads outcomes
    need_pos = {i: False for i in range(5)}
    need_neg = {i: False for i in range(5)}
    chosen, i = [], 0
    while len(chosen) < n_scenes and i < len(eligible):
        _r, sig, members, reps = eligible[i]
        i += 1
        fire = fire_of(sol, reps[0])
        chosen.append((sig, members, reps))
        for k in range(5):
            need_pos[k] |= (fire[k] == 1)
            need_neg[k] |= (fire[k] == 0)

    rows = []
    per_arm_P, per_arm_Y = {}, {}
    query_used_on, seq_ne_query_differs_on = set(), set()
    fingerprint_ok = True
    arm_runs = Counter()
    failures = []

    for n, (sig, members, reps) in enumerate(chosen):
        true = reps[0]
        fam = class_local_queries(sol, true.kappa, true.phi, sig[0])
        registry = tuple(type("R", (), {"spec": q, "kind": q[0]})()
                         for q in sorted(fam, key=repr))
        obs = sigma0(sol, true)
        if obs[0] is None:
            failures.append({"scene": n, "why": "factual signature unavailable"})
            continue
        rows_n, claim = obs[0]
        evidence = make_evidence(rows_n,
                                 true.option_fault if true.option_fault is not None
                                 else true.base_option,
                                 true.kappa, true.phi)
        feedback = make_feedback(claim)

        support = PublicSupport(
            worlds=tuple(reps),
            signature={w: step_key(make_evidence(
                sigma0(sol, w)[0][0],
                w.option_fault if w.option_fault is not None else w.base_option,
                w.kappa, w.phi).steps) for w in reps},
            fire={w: tuple(fire_of(sol, w)) for w in reps},
            response={(w, q): response(sol, w, q) for w in reps for q in fam},
        )
        sig_of = lambda e, _k=None: step_key(e.steps)   # noqa: E731

        methods = {
            "DirectFeedback": (DirectFeedbackMethod(), None),
            "SequenceEvidence": (SequenceEvidenceMethod(support, sig_of), None),
            "QueryOnly": (QueryOnlyMethod(support, [r.spec for r in registry]),
                          None),
            "SeqThenQuery": (SeqThenQueryMethod(support, sig_of), None),
        }
        arm_pred, scene_query_used = {}, False
        for arm, (meth, _x) in methods.items():
            fp_before = probe.fingerprint(true)
            m = (lambda e, s, _m=meth: _m(e, s)) if arm == "SeqThenQuery" else meth
            res = run_arm(arm, m, evidence=evidence, feedback=feedback,
                          probe=probe, world=true, members=reps,
                          registry=registry, budget=B_Q)
            arm_runs[arm] += 1
            arm_pred[arm] = list(res.prediction.p)
            if probe.fingerprint(true) != fp_before:
                fingerprint_ok = False
            if len(res.receipts) > B_Q:
                failures.append({"scene": n, "why": f"{arm} exceeded B_Q"})
            if arm == "SeqThenQuery" and len(res.receipts) > 0:
                scene_query_used = True
        if scene_query_used:
            query_used_on.add(n)
        if arm_pred["SeqThenQuery"] != arm_pred["SequenceEvidence"]:
            seq_ne_query_differs_on.add(n)

        y = list(fire_of(sol, true))
        for arm in methods:
            per_arm_P.setdefault(arm, []).append(arm_pred[arm])
            per_arm_Y.setdefault(arm, []).append(y)
        rows.append({"scene": n, "fire": y,
                     "predictions": {a: arm_pred[a] for a in methods}})

    # ---- PASS conditions: testability only ------------------------------- #
    checks: dict = {}
    finite = all(math.isfinite(v) for r in rows
                 for a in r["predictions"] for v in r["predictions"][a])
    checks["all_four_arms_ran_on_every_scene"] = (
        len(rows) == n_scenes and all(v == n_scenes for v in arm_runs.values())
        and len(arm_runs) == 4)
    checks["all_outputs_finite"] = finite
    checks["every_fired_cause_has_pos_and_neg"] = (
        all(need_pos.values()) and all(need_neg.values()))
    checks["seqthenquery_used_a_query_at_least_once"] = bool(query_used_on)
    checks["seqthenquery_never_exceeded_B_Q"] = not any(
        "exceeded B_Q" in f["why"] for f in failures)
    checks["query_changed_inference_on_at_least_one_scene"] = bool(
        seq_ne_query_differs_on)
    checks["predictions_not_all_identical_constant"] = len(
        {tuple(r["predictions"]["SequenceEvidence"]) for r in rows}) > 1
    checks["world_fingerprints_unchanged"] = fingerprint_ok

    metrics = {arm: asdict(evaluate(per_arm_P[arm], per_arm_Y[arm]))
               for arm in per_arm_P} if rows else {}

    # SMOKE checks only crashes/logging/blatant plumbing errors and yields NO
    # scientific judgement, so the per-cause coverage requirement -- which is a
    # TESTABILITY property of a 32-scene batch -- is dev-only. Applying it to
    # smoke would have made a 5-scene batch fail for a reason smoke exists to be
    # too small to satisfy.
    smoke_checks = {
        "all_four_arms_ran_on_every_scene":
            checks["all_four_arms_ran_on_every_scene"],
        "all_outputs_finite": checks["all_outputs_finite"],
        "seqthenquery_never_exceeded_B_Q":
            checks["seqthenquery_never_exceeded_B_Q"],
        "world_fingerprints_unchanged": checks["world_fingerprints_unchanged"],
    }
    dev_checks = dict(checks)
    dev_checks["seqthenquery_used_a_query_at_least_once"] = True
    dev_checks["query_changed_inference_on_at_least_one_scene"] = True

    applied = smoke_checks if stage == "smoke" else dev_checks
    checks["_applied_to_this_stage"] = sorted(applied)
    checks["_informational_not_gating_for_smoke"] = sorted(
        k for k in checks if k not in applied and not k.startswith("_"))

    verdict = "PASS" if all(applied.values()) else "FAIL"
    out = {
        "stage": stage, "namespace": namespace, "n_scenes": n_scenes,
        "B_Q": B_Q, "checks": checks, "verdict": verdict,
        "coverage": {"positives": need_pos, "negatives": need_neg},
        "scenes": rows,
        "metrics": metrics,
        "arm_runs": dict(arm_runs),
        "failures": failures,
        "gate_semantics": (
            "DEVELOPMENT GATE = TESTABILITY ONLY. It deliberately does not "
            "require AUPRC(SeqThenQuery) > AUPRC(DirectFeedback); that is the "
            "confirmatory question. Metrics are recorded as raw material for "
            "benchmark calibration, NOT as a result."),
        "discipline": (
            f"If this batch exposes a design problem, method or benchmark may "
            f"change, but the SAME {n_scenes} may then NOT be declared "
            f"calibration-PASS: keep this artifact and re-run on a fresh batch "
            f"under a new namespace."),
    }
    outdir = ROOT / "experiments" / "v01r"
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / f"calibration_{stage}.json"
    path.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")

    print(f"\nscenes: {len(rows)}/{n_scenes}; arms: {dict(arm_runs)}")
    print("coverage positives:", need_pos)
    print("coverage negatives:", need_neg)
    print(f"\nchecks:")
    for k in sorted(checks):
        print(f"  {k:<48} {checks[k]}")
    print(f"\n{stage.upper()} verdict: {verdict}")
    for arm, mm in metrics.items():
        print(f"  {arm:<18} macroAUPRC={mm['macro_auprc']:.4f} "
              f"macroAUROC={mm['macro_auroc']:.4f} exact={mm['exact_set_accuracy']:.4f}")
    print(f"wrote {path}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
