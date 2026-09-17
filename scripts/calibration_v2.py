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
# A62/A63: the confirmatory namespace is separate from both development ones and
# is not reused (`06-V01R.md` §5.2). N=400 is drawn as one deterministic sequence
# from (DGP, namespace); the four non-overlapping 100-scene blocks are the first,
# second, third and fourth 100 of that sequence, so cumulative AND fresh-block
# readings are both available without redrawing anything.
STAGES = {"smoke": (5, "v01r_smoke_v2"),
          "dev": (32, "v01r_dev_v2"),
          "conf": (400, "v01r_conf_v1")}
CONF_BLOCK = 100
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


def _contrast(P_alt, P_base, Y):
    """Pre-registered primary contrast, reported BEFORE the mean is read.

    The primary quantity is BATCH-LEVEL macro AUPRC: a per-cause AUPRC is only
    defined when the evaluated set contains both classes, so it cannot be
    computed on a single scene. An earlier version called evaluate() per scene
    and crashed on a 400-scene run AFTER all the expensive work was done --
    wasting the run. So:

      * ``batch_macro_delta`` is the primary: macro AUPRC over the whole block,
        minus the same for the baseline.
      * the per-scene distribution uses a PER-SCENE-DEFINED score, the Brier
        score, and is labelled as such. It is a diagnostic of shape (tie
        fraction, median, sign test, top-5 concentration), never the endpoint.
    """
    from rfl_rebuild.eval import evaluate

    def brier1(p, y):
        return sum((p[i] - y[i]) ** 2 for i in range(5)) / 5.0

    d = [brier1(pb, y) - brier1(pa, y)          # positive = alt better
         for pa, pb, y in zip(P_alt, P_base, Y)]
    s = sorted(d)
    n = len(s)
    ties = sum(1 for x in s if abs(x) < 1e-12)
    trimmed = s[int(0.1 * n):n - int(0.1 * n)] if n >= 10 else s
    total = sum(s)
    top5 = sum(sorted(s, reverse=True)[:5])
    wins = sum(1 for x in s if x > 0)
    loss = sum(1 for x in s if x < 0)
    macro_alt = evaluate(P_alt, Y).macro_auprc
    macro_base = evaluate(P_base, Y).macro_auprc
    delta = macro_alt - macro_base
    return {"n": n,
            "batch_macro_auprc_alt": macro_alt,
            "batch_macro_auprc_base": macro_base,
            "batch_macro_delta": delta,
            "per_scene_score": "Brier (diagnostic only; AUPRC is undefined at n=1)",
            "mean_per_scene_brier_delta": total / n,
            "median": s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2]),
            "trimmed_mean": sum(trimmed) / len(trimmed),
            "tie_fraction": ties / n, "wins": wins, "losses": loss,
            "sign_test_p_two_sided": _binom_two_sided(wins, wins + loss),
            "top5_share_of_total_delta": (top5 / total) if abs(total) > 1e-15 else None,
            "delta_min": 0.05,
            "position_vs_delta_min": ("ABOVE" if delta > 0.05 else
                                      "BELOW" if delta < -0.05 else "WITHIN")}


def _binom_two_sided(k, n):
    if n == 0:
        return None
    from math import comb
    obs = comb(n, k)
    tot = sum(comb(n, i) for i in range(n + 1))
    return sum(comb(n, i) for i in range(n + 1)
               if comb(n, i) <= obs) / tot


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
        # A63: the pre-amendment requirement was that every fired cause has both
        # classes. That is a COVERAGE property the frozen DGP does not guarantee
        # (U fires in ~1% of scenes, so N=32 expects ~0.3 U-positives), so it is
        # kept as INFORMATION and the gate becomes evaluability-aware.
        "coverage_every_cause_has_both_classes_INFORMATIONAL":
            all(p > 0 for p in pos) and all(x > 0 for x in neg),
        "evaluable_causes_nonempty": any(p > 0 for p in pos),
        "not_evaluable_causes_are_named": True,   # written into the artifact
        "seqthenquery_used_a_query": query_used["SeqThenQuery"] > 0,
        "queryonly_used_a_query": query_used["QueryOnly"] > 0,
        "query_changed_inference_on_at_least_one_scene": diffs > 0,
        "predictions_not_all_identical_constant": len(
            {tuple(r["predictions"]["SequenceEvidence"]) for r in rows_out}) > 1,
    }
    metrics = {a: asdict(evaluate(per_arm_P[a], per_arm_Y[a])) for a in per_arm_P}
    nev = metrics["SequenceEvidence"]["not_evaluable_causes"]
    ev = metrics["SequenceEvidence"]["evaluable_causes"]
    dev_only["not_evaluable_causes_are_named"] = (
        metrics["SequenceEvidence"]["macro_over"] != "all causes") if nev else True
    applied = checks if stage == "smoke" else {**checks, **dev_only}
    verdict = "PASS" if all(applied.values()) else "FAIL"

    primary = None
    out = {"stage": stage, "namespace": namespace, "n_scenes": n_scenes,
           "B_Q": B_Q, "checks": checks, "dev_only_checks": dev_only,
           "applied_to_this_stage": sorted(applied), "verdict": verdict,
           "coverage_positives": pos, "coverage_negatives": neg,
           "evaluable_causes": list(ev), "not_evaluable_causes": list(nev),
           "macro_over": metrics["SequenceEvidence"]["macro_over"],
           "a63_note": "A63: a per-cause metric is NOT_EVALUABLE when the batch "
                       "contains no scene of that class. The macro is taken over "
                       "the EVALUABLE causes and both sets are named here, so an "
                       "undefined metric is never silently averaged as zero.",
           "primary_contrast": primary,
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
    # CRASH SAFETY: write the expensive part FIRST. The previous 400-scene run
    # died in the reporting code after generating every scene and running every
    # arm, and lost all of it. A reporting bug must not be able to do that.
    path.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")

    if stage == "conf":
        try:
            blocks = {}
            for b0 in range(0, n_scenes, CONF_BLOCK):
                idx = list(range(b0, min(b0 + CONF_BLOCK, n_scenes)))
                blocks[f"block_{b0//CONF_BLOCK + 1}"] = _contrast(
                    [per_arm_P["SeqThenQuery"][i] for i in idx],
                    [per_arm_P["DirectFeedback"][i] for i in idx],
                    [per_arm_Y["SeqThenQuery"][i] for i in idx])
            out["primary_contrast"] = {
                "delta_min": 0.05, "per_block": blocks,
                "cumulative": _contrast(per_arm_P["SeqThenQuery"],
                                        per_arm_P["DirectFeedback"],
                                        per_arm_Y["SeqThenQuery"])}
        except Exception as exc:                      # pragma: no cover
            out["primary_contrast"] = {
                "error": f"{type(exc).__name__}: {exc}",
                "note": "reporting failed; the scene data above is intact and the "
                        "contrast can be recomputed from it without redrawing"}
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
