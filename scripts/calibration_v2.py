"""A62 — smoke and development calibration on the DenseSupport backend.

Stage order and namespaces are frozen (`06-V01R.md` §5.2): smoke N=5 under
``v01r_smoke_v2``, dev N=32 under ``v01r_dev_v2``. They are new namespaces because
every earlier method-side defect was fixed BEFORE the first fresh smoke, which is
exactly the condition under which a namespace may still be reused.

Scene selection is a function of (DGP, namespace) only. It never reads outcomes
or metrics, and it never consults the Gate partition.

SMOKE gates on plumbing only -- crashes, finiteness, budget, fingerprints -- and
yields NO scientific judgement.
DEV gates on TESTABILITY, never on a winner: it does not require
AUPRC(SeqThenQuery) > AUPRC(DirectFeedback). Metrics are recorded as raw material
for benchmark calibration, not as a result.
"""

from __future__ import annotations

import hashlib
import json
import math
import pathlib
import random
import sys
from dataclasses import asdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gate_stage2 import LatentCase, _domains, reference_provider, sigma0  # noqa: E402
from identifiability_gate import CAUSE_KEYS, KAPPAS, TAPES, canonicalise  # noqa: E402
from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.env.kernel import SemanticTape, State, option_actions  # noqa: E402
from rfl_rebuild.eval import evaluate  # noqa: E402
from rfl_rebuild.method.arms import (  # noqa: E402
    ResponseMemo, arm_direct_feedback, arm_query_only, arm_seq_then_query,
    arm_sequence_evidence,
)
from rfl_rebuild.method.contract import FactualEvidence, FactualStep  # noqa: E402
from rfl_rebuild.method.dgp import SceneContext, SceneDGP  # noqa: E402
from rfl_rebuild.method.registry import build_registry  # noqa: E402
from rfl_rebuild.method.support import DenseSupport  # noqa: E402
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

B_Q = 4
STAGES = {"smoke": (5, "v01r_smoke_v2"), "dev": (32, "v01r_dev_v2")}
CACHE = ROOT / "experiments" / "v01r" / "support_cache"


class Probe:
    def __init__(self, sol, provider):
        self.sol = sol
        self.provider = provider

    def domains(self, ctx):
        tape = SemanticTape(phase=ctx.phase, error_flag=ctx.error_flag,
                            cause_rank=ctx.cause_rank)
        tr = K.rollout(kappa=ctx.kappa, tape=tape, command_provider=self.provider,
                       base_option=ctx.base_option)
        d = _domains(self.sol, ctx.kappa, tape, ctx.base_option, tr)
        return tuple(canonicalise(d[k]) for k in CAUSE_KEYS)

    def rebuild(self, s, wid):
        ctx = SceneContext(kappa=s.field(wid, "kappa"), phase=s.field(wid, "phase"),
                           error_flag=s.field(wid, "error_flag"),
                           cause_rank=s.field(wid, "cause_rank"),
                           base_option=s.field(wid, "proposal"))
        dm = self.domains(ctx)
        b = {k: (dm[i][s.field(wid, f"p{i}")] if s.field(wid, f"p{i}") >= 0
                 else None) for i, k in enumerate(CAUSE_KEYS)}
        zc = s.field(wid, "Z_code")
        return LatentCase(case_id=0, kappa=ctx.kappa, phi=ctx.phase,
                          error_flag=ctx.error_flag, cause_rank=ctx.cause_rank,
                          base_option=ctx.base_option,
                          Z=tuple((zc >> i) & 1 for i in range(5)),
                          option_fault=b.get("P"), decision=b.get("D"),
                          controller=b.get("X"), plant=b.get("E"),
                          trap=b.get("U"))

    def rows_of(self, s, wid):
        return sigma0(self.sol, self.rebuild(s, wid))[0][0]

    def response(self, case, q):
        from gate_stage3 import response as R
        if q[0] == "execution":
            from rfl_rebuild.env.kernel import ControllerSite
            q = ("execution", ControllerSite(
                state=State(x=q[1], y=q[2], t=q[3], kappa=q[4], phi=q[5]),
                cmd=q[6]))
        return R(self.sol, case, q)

    def legal(self, case, q):
        return self.response(case, q) is not None


def main() -> int:
    stage = sys.argv[1] if len(sys.argv) > 1 else "smoke"
    n_scenes, namespace = STAGES[stage]
    sol = solve_reference()
    provider = reference_provider(sol)
    probe = Probe(sol, provider)
    sup = DenseSupport.load(CACHE, expected_kernel_fingerprint="full",
                            expected_dgp_fingerprint="full")
    rows_index = sup.build_rows_index(probe)
    registry = build_registry(horizon=K.HORIZON, options=K.option_ids(),
                              cells=K.OPEN_CELLS, kappas=KAPPAS, phases=range(6),
                              n_actions=len(K.ACTIONS))
    ridx = {q: i for i, q in enumerate(registry)}
    memo = ResponseMemo(sup, probe)
    ctx_ids, i = {}, 0
    for kappa in KAPPAS:
        for tape in TAPES:
            for z in K.option_ids():
                ctx_ids[(kappa, tape.phase, tape.error_flag, tape.cause_rank, z)] = i
                i += 1

    def domains_fn(ctx):
        return probe.domains(ctx)

    def feasible(ctx, Z, params):
        dm = domains_fn(ctx)
        b = {k: (dm[i2][params[i2]] if Z[i2] else None)
             for i2, k in enumerate(CAUSE_KEYS)}
        c = LatentCase(case_id=0, kappa=ctx.kappa, phi=ctx.phase,
                       error_flag=ctx.error_flag, cause_rank=ctx.cause_rank,
                       base_option=ctx.base_option, Z=tuple(Z),
                       option_fault=b.get("P"), decision=b.get("D"),
                       controller=b.get("X"), plant=b.get("E"), trap=b.get("U"))
        return sigma0(sol, c)[0] is not None

    dgp = SceneDGP(kappas=KAPPAS, options=K.option_ids(), tapes=TAPES,
                   domains=domains_fn, is_feasible=feasible)

    def actions(z, m, st):
        return option_actions(z, K.ControlState(z=z, m=m), st)

    # deterministic scene draw from (namespace, DGP) only
    rng = random.Random(int(hashlib.sha256(namespace.encode()).hexdigest()[:12], 16))
    scene_wids, scene_fire = [], []
    while len(scene_wids) < n_scenes:
        ctx, Z, params = dgp.sample_scene(rng)
        cid = ctx_ids[(ctx.kappa, ctx.phase, ctx.error_flag, ctx.cause_rank,
                       ctx.base_option)]
        zc = sum((1 << k) for k in range(5) if Z[k])
        wid = sup.find_world(cid, zc, tuple(params))
        if wid is None:
            continue
        scene_wids.append(wid)
        scene_fire.append(tuple((sup.field(wid, "fire_code") >> k) & 1
                                for k in range(5)))
    print(f"stage={stage} namespace={namespace} scenes={n_scenes} "
          f"blocks={len({sup.field(w,'block_id') for w in scene_wids})}")

    rows_out, per_arm_P, per_arm_Y = [], {}, {}
    query_used = {"QueryOnly": 0, "SeqThenQuery": 0}
    max_trace = {"QueryOnly": 0, "SeqThenQuery": 0}
    diffs = 0
    fp_ok = True

    for n, wid in enumerate(scene_wids):
        case = probe.rebuild(sup, wid)
        obs = sigma0(sol, case)
        rows = obs[0][0]
        claim = obs[0][1]
        ev = FactualEvidence(
            steps=tuple(FactualStep(x=r[0], y=r[1], t=r[2], kappa=r[3], phi=r[4],
                                    z=r[5], m=r[6], a_cmd=r[7], a_realized=r[8],
                                    reward=float(r[9])) for r in rows),
            z_in_force=rows[0][5], kappa=case.kappa, phi=case.phi)
        fp0 = (sup.field(wid, "block_id"), sup.manifest.content_digest)

        preds = {
            "DirectFeedback": arm_direct_feedback(sup, claim).p,
            "SequenceEvidence": arm_sequence_evidence(sup, ev, rows_index).p,
        }
        p_qo, t_qo, _ = arm_query_only(sup, registry, memo, budget=B_Q,
                                       true_wid=wid)
        preds["QueryOnly"] = p_qo.p
        p_st, t_st, _ = arm_seq_then_query(sup, ev, rows_index, registry, memo,
                                           wid, ridx, budget=B_Q,
                                           option_ids=K.option_ids(),
                                           option_actions=actions)
        preds["SeqThenQuery"] = p_st.p
        query_used["QueryOnly"] += int(bool(t_qo))
        query_used["SeqThenQuery"] += int(bool(t_st))
        max_trace["QueryOnly"] = max(max_trace["QueryOnly"], len(t_qo))
        max_trace["SeqThenQuery"] = max(max_trace["SeqThenQuery"], len(t_st))
        if list(preds["SeqThenQuery"]) != list(preds["SequenceEvidence"]):
            diffs += 1
        if (sup.field(wid, "block_id"), sup.manifest.content_digest) != fp0:
            fp_ok = False
        y = list(scene_fire[n])
        for a in preds:
            per_arm_P.setdefault(a, []).append(list(preds[a]))
            per_arm_Y.setdefault(a, []).append(y)
        rows_out.append({"scene": n, "world_id": wid,
                         "block_id": sup.field(wid, "block_id"),
                         "fire": y, "predictions": {a: list(preds[a]) for a in preds},
                         "trace_len": {"QueryOnly": len(t_qo),
                                       "SeqThenQuery": len(t_st)}})

    Y = per_arm_Y["SequenceEvidence"]
    pos = [sum(row[k] for row in Y) for k in range(5)]
    neg = [len(Y) - p for p in pos]
    finite = all(math.isfinite(v) for r in rows_out
                 for a in r["predictions"] for v in r["predictions"][a])

    checks = {
        "all_four_arms_ran_on_every_scene": all(
            len(per_arm_P[a]) == n_scenes for a in per_arm_P) and len(per_arm_P) == 4,
        "all_outputs_finite": finite,
        "no_arm_exceeded_B_Q": max(max_trace.values()) <= B_Q,
        "world_fingerprints_unchanged": fp_ok,
    }
    dev_only = {
        "every_fired_cause_has_pos_and_neg": all(p > 0 for p in pos)
                                              and all(x > 0 for x in neg),
        "seqthenquery_used_a_query": query_used["SeqThenQuery"] > 0,
        "queryonly_used_a_query": query_used["QueryOnly"] > 0,
        "query_changed_inference_on_at_least_one_scene": diffs > 0,
        "predictions_not_all_identical_constant": len(
            {tuple(r["predictions"]["SequenceEvidence"]) for r in rows_out}) > 1,
    }
    applied = checks if stage == "smoke" else {**checks, **dev_only}
    verdict = "PASS" if all(applied.values()) else "FAIL"

    metrics = {a: asdict(evaluate(per_arm_P[a], per_arm_Y[a])) for a in per_arm_P}
    out = {"stage": stage, "namespace": namespace, "n_scenes": n_scenes,
           "B_Q": B_Q, "checks": checks, "dev_only_checks": dev_only,
           "applied_to_this_stage": sorted(applied), "verdict": verdict,
           "coverage_positives": pos, "coverage_negatives": neg,
           "query_used": query_used, "max_trace_len": max_trace,
           "rollouts_memoised": memo.rollouts, "scenes": rows_out,
           "metrics_raw_material_only": metrics,
           "gate_semantics": "SMOKE = plumbing only, no scientific judgement. "
                             "DEV = testability only; it deliberately does NOT "
                             "require SeqThenQuery to beat DirectFeedback.",
           "discipline": f"If this batch exposes a design problem, the same "
                         f"{n_scenes} may then NOT be declared calibration-PASS: "
                         f"keep this artifact and re-run under a new namespace."}
    path = ROOT / "experiments" / "v01r" / f"calibration_{stage}_v2.json"
    path.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")

    for k in sorted(applied):
        print(f"  {k:<52} {applied[k]}")
    print(f"\n  coverage +{pos} -{neg}")
    print(f"  query used {query_used}; max trace {max_trace}; "
          f"rollouts {memo.rollouts:,}")
    for a, mm in metrics.items():
        print(f"  {a:<18} AUPRC={mm['macro_auprc']:.4f} AUROC={mm['macro_auroc']:.4f}")
    print(f"\n{stage.upper()} verdict: {verdict}")
    print(f"wrote {path}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
