"""V85 new finite owned sources and three previously unexecuted registered positive chains.
Mechanical capture scaffolding reused read-only; v83 fixture/native is never executed.
Additional source work is explicit, not a serialized-handle reconstruction or old partial retry.
"""
from contextlib import ExitStack
import hashlib
import json
import math
import inspect
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
PREP=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PREP))
sys.path.insert(0,str(PREP/"oracle_plan_signature_preflight_v84"))
from plan_capture import plan_capture
import oracle_mainline_v77 as addon
owner=addon.owner
base=addon.base
K=base.K
from rfl_rebuild.b2 import environment,training
from rfl_rebuild.b1 import targets
from rfl_rebuild.solve import dp
from rfl_rebuild.learner.store import DECISION,Q,PROCESS,CONTROLLER,QAddress,Edit,DecisionAddress
COUNTS={"rollout":0,"step":0,"transaction":0,"B1":0,"plan":0,"patch_builder":0,"patch_validator":0,
        "mean":0,"mean_completed":0,"blocked":0,"preflight_contract":0}
LIMITS={"rollout":700,"step":8400,"transaction":5,"B1":6,"plan":6,
        "patch_builder":2,"patch_validator":2,"mean":6,"preflight_contract":12}
CURRENT="NOT_STARTED"
OUTPUT_BYTES=0
PLANS=[]
ENVELOPES=[]
VALIDATIONS=[]
def emit(tag,value):
    global OUTPUT_BYTES
    line=tag+"="+json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False)
    OUTPUT_BYTES+=len((line+"\n").encode("utf8"))
    if OUTPUT_BYTES>20000000:raise RuntimeError("predeclared stdout budget; no retry")
    print(line,flush=True)
def count(name):
    COUNTS[name]+=1
    if COUNTS[name]>LIMITS[name]:raise RuntimeError("predeclared native budget "+name)
def blocked(*a,**kw):
    COUNTS["blocked"]+=1
    raise AssertionError("no CF substitution/keys/DP/training/curve/collector/calibration")
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
def envelope_wire(addresses,envelope):
    return {"addresses":[base.PATCH_SLICE.domain.canonical(a) for a in addresses],
        "targets":[{"address":base.PATCH_SLICE.domain.canonical(a),"alternative":envelope[a].alternative,
                    "factual_command":envelope[a].factual_command} for a in addresses]}
class RegisteredBankPositiveV85Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global CURRENT
        cls.reference=reference_from_stored()
        cls.healthy=base.ready.read_json(PREP/"healthy_reference_candidate.json")
        scope=sorted([[s.x,s.y,s.t,s.kappa,s.phi,z,m,K.WAIT in row]
            for (s,z,m),row in cls.reference.rows.items() if (s.kappa,s.phi,z)==(1,5,2)])
        assert len(scope)==288 and sum(x[-1] for x in scope)==276
        cls.sources={}
        # Two independent literal constructors; neither store is generated from the other.
        for architecture in ("D_Q","D_patch"):
            CURRENT="INSTALL_P_GENERAL_"+architecture
            state=base.LearnerPersistentState()
            edits=[Edit(PROCESS,0,2),Edit(PROCESS,3,1)]
            for (s,z,m),row in sorted(cls.reference.rows.items(),key=lambda x:
                    (x[0][0].x,x[0][0].y,x[0][0].t,x[0][0].kappa,x[0][0].phi,x[0][1],x[0][2])):
                if (s.kappa,s.phi,z)==(1,5,2) and K.WAIT in row:
                    if architecture=="D_Q":
                        edits.append(Edit(Q,QAddress(s,z,m,K.WAIT),max(row.values())+1.0))
                    else:
                        edits.append(Edit(DECISION,DecisionAddress(s,z,m),K.WAIT))
            sentinel=K.State(0,2,0,0,5)
            if architecture=="D_Q":
                edits.append(Edit(Q,QAddress(sentinel,2,0,K.WAIT),
                                  max(cls.reference.row(sentinel,2,0).values())+2.0))
            else:
                edits.append(Edit(DECISION,DecisionAddress(sentinel,2,0),K.WAIT))
            edits += [Edit(CONTROLLER,K.ControllerSite(K.State(0,2,0,1,5),K.WAIT),K.RIGHT),
                      Edit(CONTROLLER,K.ControllerSite(K.State(1,2,1,1,5),K.WAIT),K.LEFT),
                      Edit(CONTROLLER,K.ControllerSite(sentinel,K.WAIT),K.RIGHT)]
            emit("INSTALL_DECLARED_CONTEXT_SCOPE",{"architecture":architecture,"all_contexts":scope,
                "illegal_WAIT_contexts_preserved":[x[:-1] for x in scope if not x[-1]],
                "selection":"original legal context/domain and missing registered positive chain, not outcomes",
                "literal_edits":[repr(e) for e in edits]})
            state.apply_transaction(edits,q_reference=cls.reference)
            environment.learner_channels(state.snapshot(),cls.reference)
            CURRENT="P_GENERAL_"+architecture
            scene=base.EvaluationScene(1,5,0,35,0)
            emit("SOURCE_INPUT",{"label":CURRENT,"pre":base._store_wire(state),"regime":"P",
                "counterfactual":False,"configuration":owner._configuration(scene,K.FaultMask(),None,cls.reference)})
            src=owner.capture_source(state,scene=scene,regime="P",q_reference=cls.reference,
                healthy_reference=cls.healthy,mask=K.FaultMask(),option_fault=None,counterfactual=False)
            cls.sources[architecture]=src
            emit("OWNED_SOURCE",{"label":CURRENT,"audit":owner.source_audit(src)})
        cls.pairs={};cls.futures={};cls.banks={}
        cells=(("DQ_L3","D_Q",base.Tier.L3_ORACLE,"LocalOracleRestore"),
               ("PATCH_L1","D_patch",base.Tier.L1_CORRECTIVE,"SetAlternative"),
               ("PATCH_L3","D_patch",base.Tier.L3_ORACLE,"LocalOracleRestore"))
        for name,architecture,tier,law in cells:
            CURRENT=name;src=cls.sources[architecture]
            pair=owner.run_pair(src,architecture=architecture,tier=tier,law_name=law)
            cls.pairs[name]=pair
            emit("NEW_PAIR",{"label":name,"audit":owner.pair_audit(pair,src)})
            future=owner.prepare_future_inputs(pair,src);cls.futures[name]=future
            emit("OWNED_FUTURE",{"label":name,"audit":owner.future_audit(future,src)})
            bank=addon.measure_bank(future,src);cls.banks[name]=bank
            emit("OWNED_BANK",{"label":name,"audit":addon.bank_audit(bank,src)})

    def test_01_independent_extensional_sources_full_P_truth_no_Q_CF_substitution(self):
        records=[]
        for architecture,src in self.sources.items():
            config,sd=owner._checked_source(src)
            self.assertEqual(sd.regime,"P");self.assertIsNone(sd.episode)
            self.assertIsNone(sd.payload["owned_cf_configuration"])
            self.assertEqual(sd.trace.outcome,K.Outcome.TIMEOUT)
            self.assertEqual(sd.truth["J_L"],[True,True,True])
            self.assertIsNone(sd.truth["Gamma_T_star"]);self.assertIsNone(sd.truth["R_mech"])
            self.assertEqual(config.mask,K.FaultMask());self.assertIsNone(config.option_fault)
            stores=base._store_wire(sd.pre)
            self.assertEqual({k:len(v) for k,v in stores.items()},
                {"D":0,"P":2,"Q":277,"X":3} if architecture=="D_Q" else
                {"D":277,"P":2,"Q":0,"X":3})
            raw=base.factual._trace_payload(sd.trace,sd.scene);times=[]
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
            records.append((raw,sd.truth))
        self.assertEqual(records[0],records[1])

    def test_02_original_all_owner_plans_L1_adapter_L3_empty_fields_and_single_whole_transactions(self):
        self.assertEqual((len(PLANS),len(ENVELOPES),len(VALIDATIONS)),(6,2,2))
        self.assertTrue(all(v["result"]=="VALID" for v in VALIDATIONS))
        for name,pair in self.pairs.items():
            arch="D_Q" if name=="DQ_L3" else "D_patch";src=self.sources[arch]
            _,sd,_,pd=owner._checked_pair(pair,src)
            addresses=pd.projected.addresses
            self.assertGreater(len(addresses),1)
            self.assertEqual(set(pd.projected.whole_units),set(sd.truth["Gamma_P_star"]))
            self.assertEqual(set(pd.projected.residual_units),
                {"ProcessCommit","ControllerSite_0_2_0_4","ControllerSite_1_2_1_4"})
            for p in [p for p in PLANS if p["label"]==name]:
                self.assertEqual([v["address"] for v in p["plans"]],
                    [base.PATCH_SLICE.domain.canonical(a) for a in addresses])
                if p["law"]=="NoWrite":
                    self.assertTrue(all(not v["edits"] and v["row_op"] is None for v in p["plans"]))
                elif name=="DQ_L3":
                    self.assertTrue(all(not v["edits"] and v["row_op"] is not None for v in p["plans"]))
                    self.assertIsNone(p["delivered_fields"])
                elif name=="PATCH_L3":
                    self.assertTrue(all(len(v["edits"])==1 and v["row_op"] is None for v in p["plans"]))
                    self.assertIsNone(p["delivered_fields"])
                else:
                    raw=base.factual._trace_payload(sd.trace,sd.scene)
                    for a,rec in zip(addresses,ENVELOPES[0]["targets"]):
                        row=self.reference.row(a.state,a.z,a.m)
                        optimal=[x for x,v in row.items() if v>=max(row.values())-1e-12]
                        alt=min(x for x in optimal if x!=raw[a.state.t]["a_cmd"])
                        self.assertEqual((rec["alternative"],rec["factual_command"]),
                                         (alt,raw[a.state.t]["a_cmd"]))
                    self.assertEqual(list(p["delivered_fields"][0]["fields"]),["alternative"])
        self.assertEqual(COUNTS["transaction"],5)

    def test_03_full_post_all_receipts_nonowner_sentinels_effective_Q_and_categorical_write(self):
        states=[owner._checked_source(s)[1].pre for s in self.sources.values()]
        for name,pair in self.pairs.items():
            arch="D_Q" if name=="DQ_L3" else "D_patch";src=self.sources[arch]
            _,sd,_,pd=owner._checked_pair(pair,src);pre=base._store_wire(sd.pre)
            addresses=pd.projected.addresses;owners=set(addresses)
            for i,(state,result) in enumerate(zip(pd.clones,pd.results)):
                self.assertTrue(all(state is not s for s in states));states.append(state)
                post=base._store_wire(state);ledger=result.ledger
                for k in ("P","X"):self.assertEqual(post[k],pre[k])
                self.assertEqual(post["D" if arch=="D_Q" else "Q"],pre["D" if arch=="D_Q" else "Q"])
                self.assertEqual([r.address for r in ledger.receipts],list(addresses))
                self.assertEqual(ledger.scalar_metrics_applicable,arch=="D_Q")
                if i==0:
                    self.assertEqual(post,pre)
                    self.assertTrue(all(r.status==base.EVALUABLE_NOOP and not r.store_changed for r in ledger.receipts))
                else:
                    self.assertTrue(all(r.status==base.APPLIED and r.store_changed for r in ledger.receipts))
                if arch=="D_Q":
                    before=dict(sd.pre.q_overrides);after=dict(state.q_overrides)
                    changed=sorted((a for a in set(before)|set(after) if before.get(a)!=after.get(a)),
                        key=lambda a:(a.state.x,a.state.y,a.state.t,a.state.kappa,a.state.phi,a.z,a.m,a.a))
                    delta=[abs(float(after[a] if a in after else self.reference.value(a))-
                        float(before[a] if a in before else self.reference.value(a))) for a in changed]
                    self.assertEqual((ledger.n_scalar,ledger.sum_abs_delta,ledger.max_abs_delta),
                        (len(delta),math.fsum(delta),max(delta,default=0.0)))
                    expected={a:v for a,v in before.items() if not i or DecisionAddress(a.state,a.z,a.m) not in owners}
                    self.assertEqual(after,expected)
                else:
                    before=dict(sd.pre.decision_overrides);after=dict(state.decision_overrides)
                    expected=dict(before)
                    if i:
                        for a in addresses:
                            if name=="PATCH_L3":expected.pop(a,None)
                            else:
                                row=self.reference.row(a.state,a.z,a.m)
                                optimal=[x for x,v in row.items() if v>=max(row.values())-1e-12]
                                expected[a]=min(x for x in optimal if x!=K.WAIT)
                    self.assertEqual(after,expected)
                    self.assertEqual((ledger.n_scalar,ledger.sum_abs_delta,ledger.max_abs_delta),(0,0.0,0.0))
                self.assertFalse(state.snapshot().healthy)

    def test_04_all_six_fresh_ordinary_bank_roles_full_P_X_actual_Q_or_patch_and_original_ordered_mean(self):
        states=[owner._checked_source(s)[1].pre for s in self.sources.values()]
        for name,pair in self.pairs.items():
            arch="D_Q" if name=="DQ_L3" else "D_patch";src=self.sources[arch]
            _,_,_,pd=owner._checked_pair(pair,src)
            bank=addon._checked_bank(self.banks[name],src)
            _,_,native,_=addon._inputs(self.futures[name],src)
            self.assertEqual(bank.payload["route"],"COMPLETE_ORIGINAL_BANK")
            self.assertEqual(bank.payload["native_bank_rollout_calls"],200)
            template=bank.payload["shared_locked_template"]
            self.assertEqual(template["grid"],list(range(466)));self.assertIsNone(template["seed"])
            self.assertEqual(template["v_pre_hex"],float(0.7642000000000008).hex())
            self.assertEqual((template["alpha"],template["epsilon"]),([1,2],[1,10]))
            for role,rows,mean,state,pinned,post in zip(bank.payload["ordered_arms"],bank.traces,
                    bank.means,bank.starts,native.starts,pd.clones):
                self.assertTrue(all(state is not s for s in states));states.append(state)
                self.assertIsNot(state,pinned);self.assertIsNot(state,post)
                self.assertEqual(base._stores(state),base._stores(pinned))
                self.assertEqual(base._stores(state),base._stores(post))
                self.assertFalse(state.snapshot().healthy)
                self.assertEqual(base._store_wire(state)["P"],[[0,2],[3,1]])
                total=0.0
                for scene,trace,wire in zip(native.template["sample"],rows,role["ordered_scenes"]):
                    total+=trace.return_value
                    self.assertEqual(trace.mask,K.FaultMask());self.assertFalse(trace.interventions.members)
                    self.assertEqual(trace.option_in_force,state.process_overrides.get(scene.base_option,scene.base_option))
                    self.assertEqual(wire["raw"],base.factual._trace_payload(trace,scene))
                    self.assertEqual(wire["scene"],list(scene.key))
                self.assertEqual(len(rows),100);self.assertEqual(mean,total/100)
        self.assertEqual((COUNTS["mean"],COUNTS["mean_completed"]),(6,6))

if __name__=="__main__":
    with ExitStack() as stack:
        original_rollout=K.rollout;original_step=K.step
        original_tx=base.LearnerPersistentState.apply_transaction;original_B1=base.native_b1._run
        original_measure=addon._measure_original
        original_builder=base.native_b1.build_target_envelope
        original_validator=targets.validate_envelope
        def rollout(*a,**kw):
            count("rollout");trace=original_rollout(*a,**kw)
            scene=base.EvaluationScene(kw["kappa"],kw["tape"].phase,kw["tape"].error_flag,
                                      kw["tape"].cause_rank,kw["base_option"])
            emit("NATIVE_RAW_BEFORE_CALLER_TRUTH_TARGET_OR_MEAN",{"label":CURRENT,"ordinal":COUNTS["rollout"],
                "configuration":owner._configuration(scene,kw.get("mask",K.FaultMask()),kw.get("option_fault"),
                                                      RegisteredBankPositiveV85Tests.reference),
                "actual_interventions":[repr(iv) for iv in trace.interventions.members],
                "raw":base.factual._trace_payload(trace,scene),"outcome":trace.outcome,
                "return_hex":trace.return_value.hex(),"option_in_force":trace.option_in_force})
            return trace
        def builder(sol,addresses,trace,kappa,phi):
            count("patch_builder");result=original_builder(sol,addresses,trace,kappa,phi)
            record={"label":CURRENT,"ordinal":COUNTS["patch_builder"],**envelope_wire(addresses,result)}
            ENVELOPES.append(record);emit("ORIGINAL_PATCH_ENVELOPE",record);return result
        def validator(addresses,envelope):
            count("patch_validator");record={"label":CURRENT,"ordinal":COUNTS["patch_validator"],
                **envelope_wire(addresses,envelope)}
            original_validator(addresses,envelope);record["result"]="VALID"
            VALIDATIONS.append(record);emit("ORIGINAL_PATCH_VALIDATION",record)
        def record_plan(law,addresses,delivery,result):
            fields=None if delivery is None else [{"address":base.PATCH_SLICE.domain.canonical(a),
                "fields":dict(delivery[a])} for a in addresses]
            record={"label":CURRENT,"ordinal":COUNTS["plan"],"law":law.name,"delivered_fields":fields,
                "plans":[{"address":base.PATCH_SLICE.domain.canonical(p.address),
                    "edits":[repr(e) for e in p.edits],"status":p.status,
                    "row_op":None if p.row_op is None else repr(p.row_op)} for p in result.plans]}
            PLANS.append(record);emit("ORIGINAL_LAW_PLAN",record)
        def step(*a,**kw):
            count("step");return original_step(*a,**kw)
        def transaction(state,edits,*a,**kw):
            count("transaction");emit("TX_BEGIN",{"label":CURRENT,"ordinal":COUNTS["transaction"],
                "pre":base._store_wire(state),"edits":[repr(e) for e in edits]})
            result=original_tx(state,edits,*a,**kw)
            emit("TX_END",{"label":CURRENT,"ordinal":COUNTS["transaction"],"post":base._store_wire(state)})
            return result
        def B1(law,tier,pre,addresses,delivery,spec,*a,**kw):
            count("B1");emit("B1_BEGIN",{"label":CURRENT,"ordinal":COUNTS["B1"],"law":law.name,
                "tier":tier.name,"addresses":[spec.domain.canonical(x) for x in addresses],
                "pre":base._store_wire(pre)})
            result=original_B1(law,tier,pre,addresses,delivery,spec,*a,**kw)
            emit("B1_END",{"label":CURRENT,"ordinal":COUNTS["B1"],"post":base._store_wire(pre),
                          "ledger":json.loads(result.ledger.canonical())});return result
        def measure(state,sample,reference):
            count("mean");emit("BANK_ROLE_BEGIN",{"label":CURRENT,"ordinal":COUNTS["mean"],
                "pre":base._store_wire(state),"sample":[list(s.key) for s in sample],"rollout_offset":COUNTS["rollout"]})
            traces,mean=original_measure(state,sample,reference)
            COUNTS["mean_completed"]+=1
            emit("BANK_ROLE_NATIVE_COMPLETE",{"label":CURRENT,"ordinal":COUNTS["mean"],
                "post":base._store_wire(state),"rollout_end":COUNTS["rollout"],"mean_hex":mean.hex(),
                "ordered_returns":[t.return_value.hex() for t in traces]});return traces,mean
        for obj,name,fn in ((K,"rollout",rollout),(environment,"rollout",rollout),(K,"step",step),
            (base.LearnerPersistentState,"apply_transaction",transaction),(base.native_b1,"_run",B1),
            (addon,"_measure_original",measure),(base.native_b1,"build_target_envelope",builder),
            (targets,"validate_envelope",validator)):
            stack.enter_context(patch.object(obj,name,fn))
        defining_classes=(base.laws.NoWriteRef,base.laws.DQLocalOracleRestore,
                          base.laws.SetAlternative,base.laws.DeleteFactualPatch)
        original_plans={c:c.plan for c in defining_classes}
        original_registries=(base.laws.DQ_LAWS,base.laws.LAWS,base.laws.P_LAWS,base.laws.X_LAWS)
        def preflight(phase):
            assert not any(COUNTS[k] for k in ("rollout","step","transaction","B1","plan","mean"))
            assert base.laws.LocalOracleRestore.plan is base.laws.DeleteFactualPatch.plan
            assert "plan" not in base.laws.LocalOracleRestore.__dict__
            roles=(("DQ_L3_NoWrite",base.laws.NoWriteRef(base.Tier.L3_ORACLE),base.DQ_SLICE),
                   ("DQ_L3_LocalOracleRestore",base.laws.DQLocalOracleRestore(),base.DQ_SLICE),
                   ("PATCH_L1_NoWrite",base.laws.NoWriteRef(base.Tier.L1_CORRECTIVE),base.PATCH_SLICE),
                   ("PATCH_L1_SetAlternative",base.laws.SetAlternative(),base.PATCH_SLICE),
                   ("PATCH_L3_NoWrite",base.laws.NoWriteRef(base.Tier.L3_ORACLE),base.PATCH_SLICE),
                   ("PATCH_L3_LocalOracleRestore",base.laws.LocalOracleRestore(),base.PATCH_SLICE))
            for label,law,spec in roles:
                count("preflight_contract")
                sig=inspect.signature(law.plan,follow_wrapped=False)
                assert tuple(sig.parameters)==("addresses","targets")
                assert all(p.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD and
                           p.default is inspect.Parameter.empty for p in sig.parameters.values())
                assert "__signature__" not in law.plan.__func__.__dict__
                assert "__wrapped__" not in law.plan.__func__.__dict__
                checked,tier=base.native_b1._law_contract(law,spec)
                assert checked is law and tier is law.tier
                emit("PRE_SOURCE_ACTUAL_BOUND_API",{"phase":phase,"label":label,
                    "names":list(sig.parameters),"kinds":[p.kind.name for p in sig.parameters.values()],
                    "fields":sorted(spec.fields(tier)),"real_plan_executed":False,
                    "native_counts_before_source":{k:COUNTS[k] for k in ("rollout","step","transaction","B1","plan","mean")}})
        preflight("original")
        for law,original in original_plans.items():
            stack.enter_context(patch.object(law,"plan",plan_capture(original,record_plan)))
        preflight("hooked")
        assert base.laws.LocalOracleRestore.plan is base.laws.DeleteFactualPatch.plan
        assert "plan" not in base.laws.LocalOracleRestore.__dict__
        for obj,name in ((training,"train_curve"),(training,"episode_rollout"),(training,"key"),
            (training,"Curve"),(training,"FutureTrainingProtocol"),(training.ExogenousEpisode,"derive"),
            (dp,"solve_reference"),(base.ready,"build_reference"),(base.ready,"solve_reference"),
            (K.SemanticTape,"sample"),(base.native_cf.CfEpisode,"replay"),
            (base.native_b1,"build_counterfactual_envelope")):
            stack.enter_context(patch.object(obj,name,blocked))
        import random
        stack.enter_context(patch.object(random,"Random",blocked))
        old_profile=sys.getprofile()
        def profile(frame,event,arg):
            if event=="call" and frame.f_globals.get("__name__")=="rfl_rebuild.b1.laws" and frame.f_code.co_name=="plan":
                count("plan")
        sys.setprofile(profile)
        try:
            result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RegisteredBankPositiveV85Tests))
        finally:
            sys.setprofile(old_profile)
    # These identity assertions are actual runtime restoration, not inferred from hashes.
    assert all(c.plan is f for c,f in original_plans.items())
    assert base.laws.LocalOracleRestore.plan is base.laws.DeleteFactualPatch.plan
    assert "plan" not in base.laws.LocalOracleRestore.__dict__
    assert all(a is b for a,b in zip(original_registries,
        (base.laws.DQ_LAWS,base.laws.LAWS,base.laws.P_LAWS,base.laws.X_LAWS)))
    assert K.rollout is original_rollout and K.step is original_step
    assert base.LearnerPersistentState.apply_transaction is original_tx
    assert base.native_b1._run is original_B1 and addon._measure_original is original_measure
    assert training.learned_rollout is addon._ORIGINAL_LEARNED and addon._BUSY is False
    emit("RUNTIME_ALIAS_AND_CAPTURE_RESTORED",{"alias_parent_identity_before_during_after":True,
        "no_own_alias_plan":True,"all_original_plan_function_and_registry_identities":True,
        "native_capture_and_original_mean_alias_restored":True,"extra_real_sources":2,
        "old_fixture_or_partial_retry":False})
    emit("FINAL",{"tests":result.testsRun,"failures":len(result.failures),"errors":len(result.errors),
            "skipped":len(result.skipped),"counts":COUNTS,"budget":LIMITS,"output_bytes_before_footer":OUTPUT_BYTES,
            "extra_actual_source_work":2,"source_descriptor":[1,5,0,35,0],
            "training":0,"DP":0,"CF_replay":0,"keys_allocated":False,"native_calibration":False,"collector":False,
            "old_fixture_reruns":0,"scientific_PASS":False,"research_complete":False})
    sys.exit(0 if result.wasSuccessful() and not COUNTS["blocked"] else 1)
