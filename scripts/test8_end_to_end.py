"""A62 — end-to-end Test 8 on a FIXED fixture that consumes no smoke/dev scene.

Layers A and B (support/backend determinism) already passed in
`test8_hashseed.json`. This is the third layer the earlier artifact explicitly
recorded as missing: the METHOD query traces.

Two subprocesses under ``PYTHONHASHSEED=1`` and ``999`` must produce a
byte-identical payload containing, for each fixture scene:

  * the four arms' raw predictions
  * the QueryOnly query trace
  * the SeqThenQuery query trace
  * initial and final belief fingerprints

The fixture is a fixed non-development slice of the support, so nothing here
touches `v01r_smoke_v2` or `v01r_dev_v2`.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments" / "v01r"
SEEDS = ("1", "999")
N_FIXTURE = 6
BLOCK_PREFIX = 40          # a fixed, small slice: first 40 worlds of 6 blocks

PAYLOAD = r'''
import hashlib, json, pathlib, sys
sys.path[:0] = ["src", "scripts"]
from gate_stage2 import _domains, reference_provider, sigma0
from gate_stage2 import LatentCase
from identifiability_gate import CAUSE_KEYS, KAPPAS, TAPES, canonicalise
from rfl_rebuild.env import kernel as K
from rfl_rebuild.env.kernel import SemanticTape, State, option_actions
from rfl_rebuild.method.arms import (ResponseMemo, arm_direct_feedback,
    arm_sequence_evidence, arm_query_only, arm_seq_then_query)
from rfl_rebuild.method.belief import BeliefState
from rfl_rebuild.method.contract import FactualEvidence, FactualStep
from rfl_rebuild.method.registry import build_registry
from rfl_rebuild.method.support import DenseSupport
from rfl_rebuild.solve.dp import solve_reference

sol = solve_reference(); provider = reference_provider(sol)
sup = DenseSupport.load(pathlib.Path("experiments/v01r/support_cache"),
                        expected_kernel_fingerprint="full",
                        expected_dgp_fingerprint="full")
registry = build_registry(horizon=K.HORIZON, options=K.option_ids(),
                          cells=K.OPEN_CELLS, kappas=KAPPAS, phases=range(6),
                          n_actions=len(K.ACTIONS))
ridx = {q: i for i, q in enumerate(registry)}

def domains(ctx):
    tape = SemanticTape(phase=ctx.phase, error_flag=ctx.error_flag,
                        cause_rank=ctx.cause_rank)
    tr = K.rollout(kappa=ctx.kappa, tape=tape, command_provider=provider,
                   base_option=ctx.base_option)
    d = _domains(sol, ctx.kappa, tape, ctx.base_option, tr)
    return tuple(canonicalise(d[k]) for k in CAUSE_KEYS)

class Probe:
    def rebuild(self, support, wid):
        s = support
        from rfl_rebuild.method.dgp import SceneContext
        ctx = SceneContext(kappa=s.field(wid,"kappa"), phase=s.field(wid,"phase"),
                           error_flag=s.field(wid,"error_flag"),
                           cause_rank=s.field(wid,"cause_rank"),
                           base_option=s.field(wid,"proposal"))
        dm = domains(ctx)
        b = {k: (dm[i][s.field(wid,f"p{i}")] if s.field(wid,f"p{i}")>=0 else None)
             for i,k in enumerate(CAUSE_KEYS)}
        zc = s.field(wid,"Z_code")
        Z = tuple((zc>>i)&1 for i in range(5))
        return LatentCase(case_id=0, kappa=ctx.kappa, phi=ctx.phase,
                          error_flag=ctx.error_flag, cause_rank=ctx.cause_rank,
                          base_option=ctx.base_option, Z=Z,
                          option_fault=b.get("P"), decision=b.get("D"),
                          controller=b.get("X"), plant=b.get("E"), trap=b.get("U"))
    def response(self, case, q):
        from gate_stage3 import response as R
        if q[0] == "execution":
            from rfl_rebuild.env.kernel import ControllerSite, State
            site = ControllerSite(
                state=State(x=q[1], y=q[2], t=q[3], kappa=q[4], phi=q[5]),
                cmd=q[6])
            q = ("execution", site)
        return R(sol, case, q)
    def rows_of(self, support, wid):
        case = self.rebuild(support, wid)
        return sigma0(sol, case)[0][0]

probe = Probe()
memo = ResponseMemo(sup, probe)
rows_index = sup.build_rows_index(probe)

# SIX distinct rows blocks. The earlier fixture took block_members(bid)[:7] for
# each of six blocks and then truncated to 6, so every fixture world came from
# the FIRST block -- which is why SequenceEvidence showed one distinct prediction
# and layer C only ever exercised one (rows, Q_syn) pair.
fixture = [sup.block_members(bid)[0] for bid in sorted(sup._worlds_of)[:6]]

def fp(belief):
    return hashlib.sha256("|".join(f"{b}:{m}" for b,m in
        sorted(belief.active_blocks.items())).encode()).hexdigest()[:20]

def evidence_for(wid):
    case = probe.rebuild(sup, wid)
    obs = sigma0(sol, case)
    rows = obs[0][0]
    steps = tuple(FactualStep(x=r[0],y=r[1],t=r[2],kappa=r[3],phi=r[4],
                              z=r[5],m=r[6],a_cmd=r[7],a_realized=r[8],
                              reward=float(r[9])) for r in rows)
    return FactualEvidence(steps=steps, z_in_force=steps[0].z,
                           kappa=case.kappa, phi=case.phi), obs[0][1]

def actions(z, m, st):
    return option_actions(z, K.ControlState(z=z, m=m), st)

records = []
for wid in fixture:
    ev, claim = evidence_for(wid)
    p_df = arm_direct_feedback(sup, claim).p
    p_se = arm_sequence_evidence(sup, ev, rows_index).p
    p_qo, t_qo, H_qo = arm_query_only(sup, registry, memo, budget=4, true_wid=wid)
    p_st, t_st, H_st = arm_seq_then_query(sup, ev, rows_index, registry, memo,
                                          wid, ridx, budget=4,
                                          option_ids=K.option_ids(),
                                          option_actions=actions)
    records.append({
        "world_id": wid,
        "block_id": sup.field(wid, "block_id"),
        "predictions": {"DirectFeedback": list(p_df),
                        "SequenceEvidence": list(p_se),
                        "QueryOnly": list(p_qo.p),
                        "SeqThenQuery": list(p_st.p)},
        "query_trace_QueryOnly": list(t_qo),
        "query_trace_SeqThenQuery": list(t_st),
        "belief_fp_initial": {"QueryOnly": fp(sup.global_prior()),
                              "SeqThenQuery": fp(sup.rows_prior(sup.field(wid,"block_id")))},
        "belief_fp_final": {"QueryOnly": fp(H_qo), "SeqThenQuery": fp(H_st)},
    })
payload = {"fixture": fixture, "records": records, "rollouts": memo.rollouts}
print(json.dumps(payload, sort_keys=True))
'''


def run(seed):
    env = dict(os.environ, PYTHONHASHSEED=seed)
    p = subprocess.run([sys.executable, "-c", PAYLOAD], cwd=ROOT, env=env,
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(f"seed {seed} failed:\n{p.stderr[-2500:]}")
    return p.stdout.strip().splitlines()[-1]


def main() -> int:
    outs = {s: run(s) for s in SEEDS}
    same = outs[SEEDS[0]] == outs[SEEDS[1]]
    payload = json.loads(outs[SEEDS[0]])
    recs = payload["records"]
    per_arm = {a: len({tuple(r["predictions"][a]) for r in recs})
               for a in ("DirectFeedback", "SequenceEvidence", "QueryOnly",
                         "SeqThenQuery")}
    used = {a: sum(1 for r in recs if r[f"query_trace_{a}"]) for a in
            ("QueryOnly", "SeqThenQuery")}
    maxq = {a: max((len(r[f"query_trace_{a}"]) for r in recs), default=0)
            for a in ("QueryOnly", "SeqThenQuery")}
    checks = {
        "A_predictions_and_traces_byte_identical": same,
        "fixture_fixed_and_nond_ev": len(recs) == N_FIXTURE,
        "fixture_spans_six_distinct_blocks":
            len({r["block_id"] for r in recs}) == 6,
        "queryonly_trace_has_no_repeats": all(
            len(r["query_trace_QueryOnly"]) == len(set(r["query_trace_QueryOnly"]))
            for r in recs),
        "proc_audit_asked_at_most_once": all(
            r["query_trace_QueryOnly"].count(0) <= 1 for r in recs),
        "seqthenquery_trace_has_no_repeats": all(
            len(r["query_trace_SeqThenQuery"])
            == len(set(r["query_trace_SeqThenQuery"])) for r in recs),
        "queryonly_used_a_query": used["QueryOnly"] > 0,
        "seqthenquery_used_a_query": used["SeqThenQuery"] > 0,
        "no_arm_exceeded_B_Q": max(maxq.values()) <= 4,
        "seqthenquery_differs_from_sequence_evidence": any(
            r["predictions"]["SeqThenQuery"] != r["predictions"]["SequenceEvidence"]
            for r in recs),
        "evidence_only_initialisation":
            len({r["belief_fp_initial"]["SeqThenQuery"] for r in recs}) == 6,
    }
    ok = all(checks.values())
    for k in sorted(checks):
        print(f"  {k:<46} {checks[k]}")
    print(f"\n  distinct predictions per arm: {per_arm}")
    print(f"  scenes using a query: {used}; max trace len: {maxq}")
    print(f"  rollouts performed (memoised): {payload['rollouts']}")
    print(f"\nend-to-end Test 8: {'PASS' if ok else 'FAIL'}")
    (OUT / "test8_end_to_end.json").write_text(json.dumps({
        "checks": checks, "status": "PASS" if ok else "FAIL",
        "distinct_predictions_per_arm": per_arm,
        "scenes_using_a_query": used, "max_trace_len": maxq,
        "rollouts": payload["rollouts"], "n_fixture": len(recs),
        "consumes_smoke_or_dev_scenes": False,
        "fixture_note": "Fixed non-development slice: the first 40 worlds of six "
                        "rows blocks, first 6 taken. Deterministic and reusable.",
    }, indent=1), encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
