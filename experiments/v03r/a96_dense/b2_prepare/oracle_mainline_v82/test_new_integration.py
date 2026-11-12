"""Four new SERIAL original P multi-owner L2 to owned-bank checks."""
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import replace
import hashlib
import math
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
PREP=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PREP))
import oracle_mainline_v77 as addon
owner=addon.owner
base=addon.base
K=base.K
from rfl_rebuild.b2 import environment,training
from rfl_rebuild.solve import dp
from rfl_rebuild.learner.store import Q, PROCESS, CONTROLLER, QAddress, Edit
COUNTS={"rollout":0,"step":0,"transaction":0,"B1":0,"CF_replay":0,"validator":0,"plan":0,"mean":0,"mean_completed":0,"blocked":0}
LIMITS={"rollout":550,"step":6600,"transaction":3,"B1":4,"CF_replay":145,"validator":8,"plan":4,"mean":4}
CURRENT="NOT_STARTED"
OUTPUT_BYTES=0
REPLAYS=[]
ENVELOPES=[]
ENVELOPE_OBJECTS=[]
PLANS=[]
VALIDATIONS=[]
def emit(tag,value):
    global OUTPUT_BYTES
    line=tag+"="+json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False)
    OUTPUT_BYTES+=len((line+"\n").encode("utf8"))
    if OUTPUT_BYTES>20000000:raise RuntimeError("predeclared stdout guard; no retry")
    print(line,flush=True)
def count(name):
    COUNTS[name]+=1
    if COUNTS[name]>LIMITS[name]:raise RuntimeError("predeclared native budget "+name)
def blocked(*a,**kw):
    COUNTS["blocked"]+=1
    raise AssertionError("no keys/DP/training/curve/collector/calibration")
def reference_from_stored():
    raw=(PREP/"grammar_catalog_v31/evidence/stdout.log").read_bytes()
    assert hashlib.sha256(raw).hexdigest()=="d0aafb6dc20b1cc0c872ac4c48497d94feb707ffe14448bd1c2f3ddd1bbb467b"
    rows={}
    for line in raw.splitlines():
        if line.startswith(b"DECISION_CONTEXT="):
            v=json.loads(line.split(b"=",1)[1]);x,y,t,k,p,z,m=v["context"]
            key=(K.State(x,y,t,k,p),z,m);assert key not in rows
            rows[key]={a:float.fromhex(h) for a,h in v["q_row_hex"]}
    assert len(rows)==13824
    return base.QReferenceView(rows)
def reverse_fold(raw,t):
    result=0.0
    for row in reversed(raw[t:]):result=float.fromhex(row["reward_hex"])+result
    return result
def iv_wire(iv):
    return {"kind":iv.kind,"t":iv.t,"repr":repr(iv)}
class PersistentMultiOwnerBankTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global CURRENT
        cls.reference=reference_from_stored()
        cls.healthy=base.ready.read_json(PREP/"healthy_reference_candidate.json")
        cls.scope=sorted([[s.x,s.y,s.t,s.kappa,s.phi,z,m,K.WAIT in row]
            for (s,z,m),row in cls.reference.rows.items() if (s.kappa,s.phi,z)==(1,4,2)])
        assert len(cls.scope)==288 and sum(x[-1] for x in cls.scope)==276
        CURRENT="INSTALL_P_Q_X_L2_MULTI_OWNER"
        state=base.LearnerPersistentState()
        edits=[Edit(PROCESS,0,2),Edit(PROCESS,3,1)]
        for (s,z,m),row in sorted(cls.reference.rows.items(),key=lambda x:
                (x[0][0].x,x[0][0].y,x[0][0].t,x[0][0].kappa,x[0][0].phi,x[0][1],x[0][2])):
            if (s.kappa,s.phi,z)==(1,4,2) and K.WAIT in row:
                edits.append(Edit(Q,QAddress(s,z,m,K.WAIT),max(row.values())+1.0))
        sentinel=K.State(0,2,0,0,4)
        edits.append(Edit(Q,QAddress(sentinel,2,0,K.WAIT),
                          max(cls.reference.row(sentinel,2,0).values())+2.0))
        edits += [Edit(CONTROLLER,K.ControllerSite(K.State(0,2,0,1,4),K.WAIT),K.RIGHT),
                  Edit(CONTROLLER,K.ControllerSite(K.State(1,2,1,1,4),K.WAIT),K.LEFT),
                  Edit(CONTROLLER,K.ControllerSite(sentinel,K.WAIT),K.RIGHT)]
        emit("INSTALL_DECLARED_CONTEXT_SCOPE",{"all_contexts":cls.scope,
            "illegal_WAIT_contexts_preserved":[x[:-1] for x in cls.scope if not x[-1]],
            "selection":"original complete context legality before native, never outcome/effects",
            "literal_edits":[repr(e) for e in edits]})
        state.apply_transaction(edits,q_reference=cls.reference)
        environment.learner_channels(state.snapshot(),cls.reference)
        CURRENT="P_Q_X_L2_MULTI_OWNER"
        scene=base.EvaluationScene(1,4,0,33,0)
        emit("SOURCE_INPUT",{"label":CURRENT,"pre":base._store_wire(state),
            "regime":"P","counterfactual":True,
            "configuration":owner._configuration(scene,K.FaultMask(),None,cls.reference)})
        cls.src=owner.capture_source(state,scene=scene,regime="P",q_reference=cls.reference,
            healthy_reference=cls.healthy,mask=K.FaultMask(),option_fault=None,counterfactual=True)
        emit("OWNED_SOURCE",{"label":CURRENT,"audit":owner.source_audit(cls.src)})
        cls.pairs={};cls.futures={};cls.banks={}
        for name in ("CounterfactualReturnWrite","DualReturnWrite"):
            CURRENT=name
            pair=owner.run_pair(cls.src,architecture="D_Q",tier=base.Tier.L2_COUNTERFACTUAL,law_name=name)
            cls.pairs[name]=pair
            emit("NEW_PAIR",{"law":name,"audit":owner.pair_audit(pair,cls.src)})
            future=owner.prepare_future_inputs(pair,cls.src);cls.futures[name]=future
            emit("OWNED_FUTURE",{"law":name,"audit":owner.future_audit(future,cls.src)})
            bank=addon.measure_bank(future,cls.src);cls.banks[name]=bank
            emit("OWNED_BANK",{"law":name,"audit":addon.bank_audit(bank,cls.src)})

    def test_01_original_P_full_baseline_credit_and_residuals(self):
        config,sd=owner._checked_source(self.src)
        self.assertEqual(sd.regime,"P")
        self.assertEqual(sd.trace.outcome,K.Outcome.TIMEOUT)
        self.assertEqual(sd.truth["J_L"],[True,True,True])
        self.assertIsNone(sd.truth["Gamma_T_star"]);self.assertIsNone(sd.truth["R_mech"])
        self.assertIsNone(config.option_fault);self.assertEqual(config.mask,K.FaultMask())
        self.assertIs(sd.episode.factual_trace,sd.trace)
        stores=base._store_wire(sd.pre)
        self.assertEqual({k:len(v) for k,v in stores.items()},{"D":0,"P":2,"Q":277,"X":3})
        raw=base.factual._trace_payload(sd.trace,sd.scene)
        times=[]
        for r in raw:
            s=K.State(*r["pre_state"]);row=self.reference.row(s,r["z"],r["m"])
            optimal=sorted(a for a,v in row.items() if v>=max(row.values())-1e-12)
            if r["a_cmd"] not in optimal:times.append(s.t)
        self.assertGreater(len(times),1)
        self.assertEqual(sd.truth["manifested_decision_timesteps"],times)
        self.assertEqual(set(sd.truth["Gamma_P_star"]),
            {"ProcessCommit","ControllerSite_0_2_0_4","ControllerSite_1_2_1_4"}|
            {f"Decision_{t}" for t in times})
        self.assertEqual(sd.trace.option_in_force,2)
        self.assertEqual(stores["P"],[[0,2],[3,1]])

    def test_02_all_owner_original_full_CF_targets_same_pre_configuration(self):
        _,sd=owner._checked_source(self.src)
        raw=base.factual._trace_payload(sd.trace,sd.scene)
        pd=owner._checked_pair(self.pairs["DualReturnWrite"],self.src)[3]
        addresses=pd.projected.addresses;by_t={a.state.t:a for a in addresses}
        self.assertEqual((len(ENVELOPES),len(VALIDATIONS),len(REPLAYS)),(4,8,1+12*len(addresses)))
        self.assertEqual(REPLAYS[0]["raw"],raw);self.assertIsNone(REPLAYS[0]["requested_t"])
        for a in addresses:
            row=self.reference.row(a.state,a.z,a.m)
            optimal=sorted(x for x,v in row.items() if v>=max(row.values())-1e-12)
            alt=min(x for x in optimal if x!=raw[a.state.t]["a_cmd"])
            self.assertEqual(sum(r["requested_t"]==a.state.t for r in REPLAYS[1:]),12)
            for r in (r for r in REPLAYS[1:] if r["requested_t"]==a.state.t):
                self.assertEqual(r["requested_action"],alt)
                self.assertEqual(r["configuration"],REPLAYS[0]["configuration"])
                self.assertEqual(r["raw"][:a.state.t],raw[:a.state.t])
                self.assertEqual(len(r["actual_interventions"]),1)
                self.assertEqual((r["actual_interventions"][0]["kind"],r["actual_interventions"][0]["t"]),
                                 ("decision",a.state.t))
                self.assertEqual(r["raw"][a.state.t]["a_cmd"],alt)
        for e in ENVELOPES:
            self.assertEqual([r["address"] for r in e["targets"]],
                [base.DQ_SLICE.domain.canonical(a) for a in addresses])
            for rec in e["targets"]:
                a=next(a for a in addresses if base.DQ_SLICE.domain.canonical(a)==rec["address"])
                replay=next(r for r in REPLAYS[1:] if r["requested_t"]==a.state.t)
                self.assertEqual(rec["a_factual"],raw[a.state.t]["a_cmd"])
                self.assertEqual(float.fromhex(rec["g_factual_hex"]),reverse_fold(raw,a.state.t))
                self.assertEqual(float.fromhex(rec["g_cf_hex"]),reverse_fold(replay["raw"],a.state.t))
        self.assertTrue(all(v["result"]=="VALID" for v in VALIDATIONS))

    def test_03_whole_each_law_once_full_owner_receipts_and_effective_Q(self):
        _,sd=owner._checked_source(self.src)
        pre=base._store_wire(sd.pre)
        all_states=[sd.pre]
        self.assertEqual(len(PLANS),4)
        for name,pair in self.pairs.items():
            pd=owner._checked_pair(pair,self.src)[3]
            addresses=pd.projected.addresses
            self.assertGreater(len(addresses),1)
            self.assertEqual(set(pd.projected.whole_units),set(sd.truth["Gamma_P_star"]))
            self.assertEqual(set(pd.projected.residual_units),
                {"ProcessCommit","ControllerSite_0_2_0_4","ControllerSite_1_2_1_4"})
            self.assertEqual(set(pd.projected.cell_units),
                {f"Decision_{a.state.t}" for a in addresses})
            for i,(state,result) in enumerate(zip(pd.clones,pd.results)):
                self.assertTrue(all(state is not x for x in all_states));all_states.append(state)
                post=base._store_wire(state)
                for k in ("D","P","X"):self.assertEqual(post[k],pre[k])
                ledger=result.ledger
                self.assertEqual([r.address for r in ledger.receipts],list(addresses))
                self.assertTrue(ledger.scalar_metrics_applicable)
                before=dict(sd.pre.q_overrides);after=dict(state.q_overrides)
                changed=sorted((a for a in set(before)|set(after) if before.get(a)!=after.get(a)),
                    key=lambda a:(a.state.x,a.state.y,a.state.t,a.state.kappa,a.state.phi,a.z,a.m,a.a))
                delta=[abs(float(after[a] if a in after else self.reference.value(a))-
                    float(before[a] if a in before else self.reference.value(a))) for a in changed]
                self.assertEqual((ledger.n_scalar,ledger.sum_abs_delta,ledger.max_abs_delta),
                    (len(delta),math.fsum(delta),max(delta,default=0.0)))
                for receipt in ledger.receipts:
                    flag=any((a.state,a.z,a.m)==(receipt.address.state,receipt.address.z,receipt.address.m)
                             for a in changed)
                    self.assertEqual(receipt.store_changed,flag)
                    self.assertEqual(receipt.status,base.APPLIED if flag else base.EVALUABLE_NOOP)
                if i==0:self.assertEqual(post,pre)
                else:
                    envelope=next(e for e in ENVELOPES if e["label"]==name)["targets"]
                    expected=dict(before)
                    for rec,a in zip(envelope,addresses):
                        edits=[(rec["a_plus"],float.fromhex(rec["g_cf_hex"]))]
                        if name=="DualReturnWrite":edits.insert(0,(rec["a_factual"],float.fromhex(rec["g_factual_hex"])))
                        for action,value in edits:
                            entry=QAddress(a.state,a.z,a.m,action)
                            if value==self.reference.value(entry):expected.pop(entry,None)
                            else:expected[entry]=value
                    self.assertEqual(after,expected)
        for p in PLANS:
            pd=owner._checked_pair(self.pairs[p["label"]],self.src)[3]
            self.assertEqual([r["address"] for r in p["plans"]],
                [base.DQ_SLICE.domain.canonical(a) for a in pd.projected.addresses])
            self.assertTrue(all(r["status"] is None and r["row_op"] is None for r in p["plans"]))
            self.assertTrue(all(len(r["edits"])==(0 if p["law"]=="NoWrite" else
                1 if p["law"]=="CounterfactualReturnWrite" else 2) for r in p["plans"]))
        self.assertEqual(COUNTS["transaction"],3)  # one installation, two whole original treatments

    def test_04_owned_ordinary_bank_full_P_X_retained_not_T_or_healthy(self):
        _,sd=owner._checked_source(self.src)
        states=[sd.pre]
        for name in self.pairs:
            pd=owner._checked_pair(self.pairs[name],self.src)[3]
            bank=addon._checked_bank(self.banks[name],self.src)
            _,config,native,_=addon._inputs(self.futures[name],self.src)
            self.assertEqual(bank.payload["route"],"COMPLETE_ORIGINAL_BANK")
            self.assertEqual(bank.payload["native_bank_rollout_calls"],200)
            self.assertEqual(bank.payload["shared_locked_template"]["grid"],list(range(466)))
            self.assertIsNone(bank.payload["shared_locked_template"]["seed"])
            self.assertEqual(bank.payload["shared_locked_template"]["v_pre_hex"],
                             float(0.7642000000000008).hex())
            for role,rows,mean,state,pinned,post in zip(bank.payload["ordered_arms"],bank.traces,
                    bank.means,bank.starts,native.starts,pd.clones):
                self.assertTrue(all(state is not x for x in states));states.append(state)
                self.assertIsNot(state,pinned);self.assertIsNot(state,post)
                self.assertEqual(base._stores(state),base._stores(pinned))
                self.assertEqual(base._stores(state),base._stores(post))
                self.assertFalse(state.snapshot().healthy)
                self.assertEqual(base._store_wire(state)["P"],[[0,2],[3,1]])
                self.assertEqual(base._store_wire(state)["X"],base._store_wire(sd.pre)["X"])
                total=0.0
                for scene,trace,wire in zip(native.template["sample"],rows,role["ordered_scenes"]):
                    total+=trace.return_value
                    self.assertEqual(trace.mask,K.FaultMask());self.assertFalse(trace.interventions.members)
                    self.assertEqual(trace.option_in_force,state.process_overrides.get(scene.base_option,scene.base_option))
                    self.assertEqual(wire["raw"],base.factual._trace_payload(trace,scene))
                    self.assertEqual(wire["scene"],list(scene.key))
                self.assertEqual(len(rows),100);self.assertEqual(mean,total/100)
        self.assertEqual((COUNTS["mean"],COUNTS["mean_completed"]),(4,4))

if __name__=="__main__":
    with ExitStack() as stack:
        original_rollout=K.rollout;original_step=K.step
        original_tx=base.LearnerPersistentState.apply_transaction;original_B1=base.native_b1._run
        original_measure=addon._measure_original
        original_replay=base.native_cf.CfEpisode.replay
        original_builder=base.native_b1.build_counterfactual_envelope
        original_validator=base.native_cf.validate_counterfactual_envelope
        def rollout(*a,**kw):
            count("rollout");trace=original_rollout(*a,**kw)
            scene=base.EvaluationScene(kw["kappa"],kw["tape"].phase,kw["tape"].error_flag,
                                      kw["tape"].cause_rank,kw["base_option"])
            emit("NATIVE_RAW_BEFORE_CALLER_TRUTH_TARGET_OR_MEAN",{"label":CURRENT,"ordinal":COUNTS["rollout"],
                "configuration":owner._configuration(scene,kw.get("mask",K.FaultMask()),kw.get("option_fault"),
                                                      PersistentMultiOwnerBankTests.reference),
                "actual_interventions":[iv_wire(iv) for iv in trace.interventions.members],
                "raw":base.factual._trace_payload(trace,scene),"outcome":trace.outcome,
                "return_hex":trace.return_value.hex(),"option_in_force":trace.option_in_force})
            return trace
        def replay(episode,t=None,action=None):
            count("CF_replay");ordinal=COUNTS["CF_replay"]
            config=base._episode_wire(episode)
            emit("CF_REPLAY_BEGIN",{"label":CURRENT,"ordinal":ordinal,"configuration":config,
                                  "requested_t":t,"requested_action":action})
            trace=original_replay(episode,t,action)
            scene=base.EvaluationScene(episode.kappa,episode.phi,episode.tape.error_flag,
                                      episode.tape.cause_rank,episode.base_option)
            record={"label":CURRENT,"ordinal":ordinal,"configuration":config,"requested_t":t,
                "requested_action":action,"raw":base.factual._trace_payload(trace,scene),
                "actual_interventions":[iv_wire(iv) for iv in trace.interventions.members],
                "outcome":trace.outcome,"return_hex":trace.return_value.hex()}
            REPLAYS.append(record);emit("CF_REPLAY_COMPLETE",record)
            return trace
        def builder(*a,**kw):
            envelope=original_builder(*a,**kw)
            record={"label":CURRENT,"targets":[{"address":base.DQ_SLICE.domain.canonical(addr),
                "a_factual":r.a_factual,"g_factual_hex":float(r.g_factual).hex(),
                "a_plus":r.a_plus,"g_cf_hex":None if r.g_cf is None else float(r.g_cf).hex()}
                for addr,r in envelope.items()]}
            ENVELOPE_OBJECTS.append(envelope)
            ENVELOPES.append(record);emit("ORIGINAL_CF_ENVELOPE",record)
            return envelope
        def validate(addresses,envelope,rows,*,sol,episode):
            count("validator")
            record={"label":CURRENT,"ordinal":COUNTS["validator"],
                "addresses":[base.DQ_SLICE.domain.canonical(a) for a in addresses],
                "targets":[{"address":base.DQ_SLICE.domain.canonical(a),
                    "a_factual":r.a_factual,"g_factual_hex":float(r.g_factual).hex(),
                    "a_plus":r.a_plus,"g_cf_hex":None if r.g_cf is None else float(r.g_cf).hex()}
                    for a,r in envelope.items()]}
            try:
                result=original_validator(addresses,envelope,rows,sol=sol,episode=episode)
            except base.ready.ProtocolError as exc:
                record["result"]="PROTOCOL_ERROR";record["exception"]=str(exc)
                VALIDATIONS.append(record);emit("ORIGINAL_CF_VALIDATION",record)
                raise
            record["result"]="VALID"
            VALIDATIONS.append(record);emit("ORIGINAL_CF_VALIDATION",record)
            return result
        def plan_capture(original):
            def captured(law,addresses,targets):
                count("plan");result=original(law,addresses,targets)
                record={"label":CURRENT,"ordinal":COUNTS["plan"],"law":law.name,
                    "plans":[{"address":base.DQ_SLICE.domain.canonical(p.address),
                        "edits":[repr(e) for e in p.edits],"status":p.status,
                        "row_op":None if p.row_op is None else repr(p.row_op)} for p in result.plans]}
                PLANS.append(record);emit("ORIGINAL_LAW_PLAN",record)
                return result
            return captured
        def step(*a,**kw):
            count("step");return original_step(*a,**kw)
        def transaction(state,edits,*a,**kw):
            count("transaction");emit("TX_BEGIN",{"label":CURRENT,"ordinal":COUNTS["transaction"],
                "pre":base._store_wire(state),"edits":[repr(e) for e in edits]})
            result=original_tx(state,edits,*a,**kw)
            emit("TX_END",{"label":CURRENT,"ordinal":COUNTS["transaction"],"post":base._store_wire(state)})
            return result
        def B1(law,tier,pre,addresses,targets,spec,*a,**kw):
            count("B1");emit("B1_BEGIN",{"label":CURRENT,"ordinal":COUNTS["B1"],"law":law.name,
                "tier":tier.name,"addresses":[spec.domain.canonical(a) for a in addresses],
                "pre":base._store_wire(pre)})
            result=original_B1(law,tier,pre,addresses,targets,spec,*a,**kw)
            emit("B1_END",{"label":CURRENT,"ordinal":COUNTS["B1"],"post":base._store_wire(pre),
                          "ledger":json.loads(result.ledger.canonical())})
            return result
        def measure(state,sample,reference):
            count("mean");emit("BANK_ROLE_BEGIN",{"label":CURRENT,"ordinal":COUNTS["mean"],
                "pre":base._store_wire(state),"sample":[list(s.key) for s in sample],
                "rollout_offset":COUNTS["rollout"]})
            traces,mean=original_measure(state,sample,reference)
            COUNTS["mean_completed"]+=1
            emit("BANK_ROLE_NATIVE_COMPLETE",{"label":CURRENT,"ordinal":COUNTS["mean"],
                "post":base._store_wire(state),"rollout_end":COUNTS["rollout"],
                "mean_hex":mean.hex(),"ordered_returns":[t.return_value.hex() for t in traces]})
            return traces,mean
        for obj,name,fn in ((K,"rollout",rollout),(environment,"rollout",rollout),(K,"step",step),
            (base.native_cf.CfEpisode,"replay",replay),(base.native_b1,"build_counterfactual_envelope",builder),
            (base.native_cf,"validate_counterfactual_envelope",validate),
            (base.native_b1,"validate_counterfactual_envelope",validate),
            (base.LearnerPersistentState,"apply_transaction",transaction),(base.native_b1,"_run",B1),
            (addon,"_measure_original",measure)):
            stack.enter_context(patch.object(obj,name,fn))
        for law in (base.laws.NoWriteRef,base.laws.CounterfactualReturnWrite,base.laws.DualReturnWrite):
            stack.enter_context(patch.object(law,"plan",plan_capture(law.plan)))
        for obj,name in ((training,"train_curve"),(training,"episode_rollout"),(training,"key"),
            (training,"Curve"),(training,"FutureTrainingProtocol"),(training.ExogenousEpisode,"derive"),
            (dp,"solve_reference"),(base.ready,"build_reference"),(base.ready,"solve_reference"),
            (K.SemanticTape,"sample")):
            stack.enter_context(patch.object(obj,name,blocked))
        import random
        stack.enter_context(patch.object(random,"Random",blocked))
        result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PersistentMultiOwnerBankTests))
        emit("FINAL",{"tests":result.testsRun,"failures":len(result.failures),"errors":len(result.errors),
            "skipped":len(result.skipped),"counts":COUNTS,"budget":LIMITS,
            "output_bytes_before_footer":OUTPUT_BYTES,"training":0,"DP":0,"keys_allocated":False,
            "native_calibration":False,"collector":False,"old_fixture_reruns":0,
            "scientific_PASS":False,"research_complete":False})
        sys.exit(0 if result.wasSuccessful() and not COUNTS["blocked"] else 1)
