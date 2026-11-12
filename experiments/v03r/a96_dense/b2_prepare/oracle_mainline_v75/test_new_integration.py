"""New finite v75 mixed-source/owned-post SERIAL conformance, not calibration."""
from contextlib import ExitStack
from dataclasses import replace
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import traceback
import unittest
from unittest.mock import patch

PREP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PREP))
import oracle_mainline_v75 as addon
base = addon.base
from rfl_rebuild.b2 import training
from rfl_rebuild.learner.store import DECISION, PROCESS, CONTROLLER, Q, DecisionAddress, QAddress, Edit
from rfl_rebuild.solve import dp

COUNTS = {"rollout": 0, "step": 0, "transaction": 0, "B1": 0, "blocked": 0}
LIMITS = {"rollout": 64, "step": 768, "transaction": 32, "B1": 32}
CURRENT = "NOT_STARTED"
OUTPUT_BYTES = 0
def emit(tag, value):
    global OUTPUT_BYTES
    line = tag + "=" + json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    OUTPUT_BYTES += len((line+"\n").encode("utf8"))
    if OUTPUT_BYTES > 5000000:
        raise RuntimeError("predeclared stdout budget exceeded; no retry")
    print(line, flush=True)
def count(name):
    COUNTS[name] += 1
    if COUNTS[name] > LIMITS[name]:
        raise RuntimeError("predeclared native budget exceeded: "+name)
def blocked(*a, **kw):
    COUNTS["blocked"] += 1
    raise AssertionError("no DP/key/RNG/training/collector/calibration")
def reference_from_stored():
    raw = (PREP/"grammar_catalog_v31/evidence/stdout.log").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "d0aafb6dc20b1cc0c872ac4c48497d94feb707ffe14448bd1c2f3ddd1bbb467b"
    rows = {}
    for line in raw.splitlines():
        if line.startswith(b"DECISION_CONTEXT="):
            v=json.loads(line.split(b"=",1)[1]);x,y,t,k,p,z,m=v["context"]
            key=(base.K.State(x,y,t,k,p),z,m)
            assert key not in rows
            rows[key]={a:float.fromhex(h) for a,h in v["q_row_hex"]}
    assert len(rows)==13824
    return base.QReferenceView(rows)
def fixture(reference, arch):
    state=base.LearnerPersistentState()
    edits=[Edit(PROCESS,0,1),Edit(PROCESS,3,2)]
    # Full fixed z1 context support at kappa1/phase4, not actual outcome selection.
    for (s,z,m), row in sorted(reference.rows.items(),key=lambda x:
            (x[0][0].x,x[0][0].y,x[0][0].t,x[0][0].kappa,x[0][0].phi,x[0][1],x[0][2])):
        if (s.kappa,s.phi,z)==(1,4,1):
            assert K.WAIT in row
            if arch=="D_Q":
                edits.append(Edit(Q,QAddress(s,z,m,K.WAIT),max(row.values())+1.0))
            else:
                edits.append(Edit(DECISION,DecisionAddress(s,z,m),K.WAIT))
    s=K.State(0,2,0,0,4)
    if arch=="D_Q":
        edits.append(Edit(Q,QAddress(s,1,0,K.WAIT),max(reference.row(s,1,0).values())+2.0))
    else:
        edits.append(Edit(DECISION,DecisionAddress(s,1,0),K.WAIT))
    edits += [Edit(CONTROLLER,K.ControllerSite(K.State(0,2,0,1,4),K.WAIT),K.RIGHT),
              Edit(CONTROLLER,K.ControllerSite(K.State(1,2,1,1,4),K.WAIT),K.LEFT),
              Edit(CONTROLLER,K.ControllerSite(K.State(0,2,0,0,4),K.WAIT),K.RIGHT)]
    state.apply_transaction(edits,q_reference=reference)
    return state
K=base.K

class MixedImmediateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global CURRENT
        cls.reference=reference_from_stored()
        cls.healthy=base.ready.read_json(PREP/"healthy_reference_candidate.json")
        cls.scene=base.EvaluationScene(1,4,0,7,0)
        cls.sources={}
        for arch in ("D_Q","D_patch"):
            CURRENT="P_MIXED_"+arch
            pre=fixture(cls.reference,arch)
            emit("SOURCE_INPUT",{"label":CURRENT,"scene":list(cls.scene.key),"regime":"P",
                "configuration":addon._configuration(cls.scene,K.FaultMask(),None,cls.reference),
                "pre":base._store_wire(pre),"selection":"fixed context support, not outcomes"})
            src=addon.capture_source(pre,scene=cls.scene,regime="P",q_reference=cls.reference,
                                     healthy_reference=cls.healthy)
            cls.sources[CURRENT]=src
            emit("OWNED_SOURCE",{"label":CURRENT,"audit":addon.source_audit(src)})
        CURRENT="T_MIXED"
        cls.mask=K.FaultMask(decision=K.DecisionOverride(0,K.WAIT),
            controller=K.ControllerFault(K.State(0,2,0,1,4),K.WAIT,K.LEFT),
            plant=K.PlantFault(0,K.RIGHT),trap=K.Trap((1,2),0))
        emit("SOURCE_INPUT",{"label":CURRENT,"scene":list(cls.scene.key),"regime":"T",
            "configuration":addon._configuration(cls.scene,cls.mask,1,cls.reference),
            "pre":base._store_wire(base.LearnerPersistentState()),"selection":"literal original descriptors"})
        cls.sources[CURRENT]=addon.capture_source(base.LearnerPersistentState(),scene=cls.scene,regime="T",
            q_reference=cls.reference,healthy_reference=cls.healthy,mask=cls.mask,option_fault=1)
        emit("OWNED_SOURCE",{"label":CURRENT,"audit":addon.source_audit(cls.sources[CURRENT])})
        cls.pairs={};cls.measurements={};cls.futures={}
        cls.cells=(
            ("P_MIXED_D_Q","D_Q",base.Tier.L0_FACTUAL,"FactualReturnWrite"),
            ("P_MIXED_D_Q","X",base.Tier.L0_FACTUAL,"X_id"),
            ("P_MIXED_D_Q","P",base.Tier.L1_CORRECTIVE,"P_id"),
            ("P_MIXED_D_patch","D_patch",base.Tier.L0_FACTUAL,"DeleteFactualPatch"),
            ("P_MIXED_D_patch","X",base.Tier.L3_ORACLE,"LocalOracleRestore"),
            ("P_MIXED_D_patch","P",base.Tier.L3_ORACLE,"LocalOracleRestore"),
            ("T_MIXED","D_Q",base.Tier.L0_FACTUAL,"FactualReturnWrite"),
            ("T_MIXED","D_patch",base.Tier.L0_FACTUAL,"DeleteFactualPatch"),
            ("T_MIXED","X",base.Tier.L0_FACTUAL,"X_id"),
            ("T_MIXED","P",base.Tier.L1_CORRECTIVE,"P_id"))
        for i,(label,arch,tier,law) in enumerate(cls.cells):
            CURRENT=f"cell{i}/{label}/{arch}/{tier.name}/{law}"
            src=cls.sources[label]
            pair=addon.run_pair(src,architecture=arch,tier=tier,law_name=law,
                assisted=base.AssistedInput(0) if arch=="P" else None)
            cls.pairs[i]=pair
            emit("NEW_PAIR",{"index":i,"label":CURRENT,"audit":addon.pair_audit(pair,src)})
            m=addon.measure_immediate(pair,src);cls.measurements[i]=m
            emit("OWNED_IMMEDIATE",{"index":i,"label":CURRENT,"audit":addon.immediate_audit(m,src)})
            f=addon.prepare_future_inputs(pair,src);cls.futures[i]=f
            emit("OWNED_FUTURE",{"index":i,"label":CURRENT,"audit":addon.future_audit(f,src)})

    def test_01_mixed_P_all_Gamma_and_residual_not_filtered(self):
        for i,(label,arch,tier,law) in enumerate(self.cells):
            if not label.startswith("P"):continue
            _,sd,_,native=addon._checked_pair(self.pairs[i],self.sources[label])
            truth=set(sd.truth["Gamma_P_star"]);pr=native.projected
            self.assertTrue(sd.truth["J_L"]==[True,True,True])
            self.assertEqual(set(pr.whole_units),truth)
            self.assertEqual(set(pr.cell_units)|set(pr.residual_units),truth)
            self.assertFalse(set(pr.cell_units)&set(pr.residual_units))
            self.assertTrue(pr.residual_units)
            self.assertTrue(pr.addresses)
    def test_02_independent_architectures_same_extensional_raw(self):
        _,q=addon._checked_source(self.sources["P_MIXED_D_Q"])
        _,p=addon._checked_source(self.sources["P_MIXED_D_patch"])
        self.assertEqual(q.payload["raw_factual"],p.payload["raw_factual"])
        self.assertTrue(q.pre.q_overrides and not q.pre.decision_overrides)
        self.assertTrue(p.pre.decision_overrides and not p.pre.q_overrides)
    def test_03_T_complete_five_mechanisms_and_environment_residual(self):
        src=self.sources["T_MIXED"];_,sd=addon._checked_source(src)
        self.assertEqual(sd.truth["Z_fire"],[True]*5)
        self.assertIsNone(sd.truth["Gamma_P_star"])
        for i in range(6,10):
            native=addon._checked_pair(self.pairs[i],src)[3]
            self.assertIn("ExternalPlant",native.projected.residual_units)
            self.assertIn("Unknown/NoWrite",native.projected.residual_units)
    def test_04_whole_receipts_nonown_stores_and_fixed_sentinels(self):
        for i,(label,arch,tier,law) in enumerate(self.cells):
            _,sd,_,pd=addon._checked_pair(self.pairs[i],self.sources[label])
            self.assertEqual(len(pd.results),2)
            for state,res in zip(pd.clones,pd.results):
                self.assertEqual(len(res.ledger.receipts),len(pd.projected.addresses))
                for view in base._VIEWS:
                    if view!=base._VIEW[arch]:
                        self.assertEqual(dict(getattr(state,view)),dict(getattr(sd.pre,view)))
                if label.startswith("P"):
                    self.assertEqual(state.process_overrides.get(3),2)
                    for view in ("q_overrides","decision_overrides","controller_overrides"):
                        self.assertEqual({a:v for a,v in getattr(state,view).items() if a.state.kappa==0},
                                         {a:v for a,v in getattr(sd.pre,view).items() if a.state.kappa==0})
    def test_05_actual_immediate_full_readonly_config_and_two_roles(self):
        for i,(label,*_) in enumerate(self.cells):
            src=self.sources[label];md=addon._checked_immediate(self.measurements[i],src)
            self.assertEqual(len(md.traces),2)
            self.assertEqual(md.payload["exact_configuration"],addon._SOURCES[src].configuration)
            self.assertEqual([a["role"] for a in md.payload["ordered_arms"]],["reference","treatment"])
            self.assertIsNone(md.payload["primary_Collateral"])
    def test_06_NoWrite_reproduces_complete_original_factual(self):
        for i,(label,*_) in enumerate(self.cells):
            src=self.sources[label];_,sd=addon._checked_source(src)
            md=addon._checked_immediate(self.measurements[i],src)
            self.assertEqual(md.payload["ordered_arms"][0]["raw"],sd.payload["raw_factual"])
    def test_07_future_full_starts_locked_shared_design(self):
        for i,(label,*_) in enumerate(self.cells):
            src=self.sources[label];_,_,_,pd=addon._checked_pair(self.pairs[i],src)
            f=self.futures[i];fd,d=addon._checked_future(f,src);native=base._checked_future(fd.native,d.native)
            self.assertEqual(native.template["grid"],tuple(range(466)))
            self.assertEqual(len(native.template["sample"]),100)
            for j,role in enumerate(("reference","treatment")):
                clone=addon.clone_future_start(f,src,role=role)
                self.assertEqual(base._stores(clone),base._stores(pd.clones[j]))
                self.assertIsNot(clone,native.starts[j])
    def test_08_wrong_source_nominal_foreign_handles_before_native(self):
        before=COUNTS.copy()
        with self.assertRaises(base.ready.ProtocolError):
            addon.immediate_audit(self.measurements[0],self.sources["T_MIXED"])
        d=addon._SOURCES[self.sources["P_MIXED_D_Q"]]
        with self.assertRaises(base.ready.ProtocolError):
            addon.measure_immediate(addon._PAIRS[self.pairs[0]].native,d.native)
        for cls in (addon.OwnedSource,addon.OwnedPair,addon.OwnedImmediate,addon.OwnedFutureInputs):
            with self.assertRaises(base.ready.ProtocolError):cls()
        self.assertEqual(COUNTS,before)
    def test_09_config_option_fault_tamper_and_exact_restore(self):
        src=self.sources["T_MIXED"];saved=addon._SOURCES[src]
        try:
            addon._SOURCES[src]=replace(saved,option_fault=None)
            with self.assertRaises(base.ready.ProtocolError):addon.source_audit(src)
        finally:addon._SOURCES[src]=saved
        addon.source_audit(src)
    def test_10_source_config_payload_tamper_restore(self):
        src=self.sources["T_MIXED"];d=addon._SOURCES[src];saved=deepcopy(d.payload)
        try:
            d.payload["configuration_declared_before_native"]["faults"]["option_fault"]=0
            with self.assertRaises(base.ready.ProtocolError):addon.source_audit(src)
        finally:
            d.payload.clear();d.payload.update(saved)
        addon.source_audit(src)
    def test_11_immediate_partial_or_alias_population_refused(self):
        h=self.measurements[0];src=self.sources["P_MIXED_D_Q"];saved=addon._IMMEDIATES[h]
        for bad in (replace(saved,traces=saved.traces[:1]),replace(saved,starts=(saved.starts[0],saved.starts[0]))):
            try:
                addon._IMMEDIATES[h]=bad
                with self.assertRaises(base.ready.ProtocolError):addon.immediate_audit(h,src)
            finally:addon._IMMEDIATES[h]=saved
        addon.immediate_audit(h,src)
    def test_12_immediate_raw_payload_tamper_refused_restore(self):
        h=self.measurements[0];d=addon._IMMEDIATES[h];old=d.payload["ordered_arms"][1]["return_hex"]
        try:
            d.payload["ordered_arms"][1]["return_hex"]="0x0.0p+0"
            with self.assertRaises(base.ready.ProtocolError):
                addon.immediate_audit(h,self.sources["P_MIXED_D_Q"])
        finally:d.payload["ordered_arms"][1]["return_hex"]=old
    def test_13_measured_cell_reentry_refused_without_native(self):
        before=COUNTS.copy()
        with self.assertRaises(base.ready.ProtocolError):
            addon.measure_immediate(self.pairs[0],self.sources["P_MIXED_D_Q"])
        self.assertEqual(COUNTS,before)
    def test_14_future_wrong_source_role_and_alias_refused(self):
        f=self.futures[0];src=self.sources["P_MIXED_D_Q"]
        with self.assertRaises(base.ready.ProtocolError):addon.future_audit(f,self.sources["T_MIXED"])
        for role in ("first",True,"P"):
            with self.assertRaises(base.ready.ProtocolError):addon.clone_future_start(f,src,role=role)
        fd,d=addon._checked_future(f,src);saved=base._FUTURES[fd.native]
        try:
            base._FUTURES[fd.native]=replace(saved,starts=(saved.starts[0],saved.starts[0]))
            with self.assertRaises(base.ready.ProtocolError):addon.future_audit(f,src)
        finally:base._FUTURES[fd.native]=saved
        addon.future_audit(f,src)
    def test_15_predeclared_partial_post_preserved_no_handle_retry(self):
        global CURRENT
        CURRENT="EXPECTED_PARTIAL_IMMEDIATE"
        src=self.sources["P_MIXED_D_Q"]
        pair=addon.run_pair(src,architecture="D_Q",tier=base.Tier.L3_ORACLE,law_name="LocalOracleRestore")
        emit("PARTIAL_CHALLENGE_PAIR",addon.pair_audit(pair,src))
        original=K.rollout;calls=[];before=len(addon._IMMEDIATES)
        def second_fails(*a,**kw):
            calls.append(1)
            if len(calls)==2:raise RuntimeError("PREDECLARED_SECOND_POST_BEFORE_NATIVE")
            return original(*a,**kw)
        with patch.object(K,"rollout",second_fails):
            try:
                addon.measure_immediate(pair,src);self.fail("partial measurement issued")
            except RuntimeError as exc:
                self.assertEqual(str(exc),"PREDECLARED_SECOND_POST_BEFORE_NATIVE")
                emit("EXPECTED_FAILURE_PRESERVED",{"error":str(exc),"traceback":traceback.format_exc(),
                    "actual_post_before_failure":1,"measurement_issued":False,"retry":False})
        self.assertEqual(len(addon._IMMEDIATES),before)
        count_before=COUNTS.copy()
        with self.assertRaises(base.ready.ProtocolError):addon.measure_immediate(pair,src)
        self.assertEqual(COUNTS,count_before)

if __name__=="__main__":
    with ExitStack() as stack:
        original_rollout=K.rollout;original_step=K.step
        original_tx=base.LearnerPersistentState.apply_transaction;original_B1=base.native_b1._run
        def rollout(*a,**kw):
            count("rollout");trace=original_rollout(*a,**kw)
            scene=base.EvaluationScene(kw["kappa"],kw["tape"].phase,kw["tape"].error_flag,
                kw["tape"].cause_rank,kw["base_option"])
            emit("NATIVE_RAW_BEFORE_CALLER_TRUTH",{"label":CURRENT,"ordinal":COUNTS["rollout"],
                "configuration":addon._configuration(scene,kw.get("mask",K.FaultMask()),kw.get("option_fault"),
                                                     MixedImmediateTests.reference),
                "raw":base.factual._trace_payload(trace,scene),"outcome":trace.outcome,
                "return_hex":trace.return_value.hex(),"option_in_force":trace.option_in_force})
            return trace
        def step(*a,**kw):
            count("step");return original_step(*a,**kw)
        def transaction(state,edits,*a,**kw):
            count("transaction");emit("TX_BEGIN",{"label":CURRENT,"ordinal":COUNTS["transaction"],
                "pre":base._store_wire(state),"edits":[repr(x) for x in edits]})
            result=original_tx(state,edits,*a,**kw)
            emit("TX_END",{"label":CURRENT,"ordinal":COUNTS["transaction"],"post":base._store_wire(state)})
            return result
        def B1(law,tier,pre,addresses,targets,spec,*a,**kw):
            count("B1");emit("B1_BEGIN",{"label":CURRENT,"ordinal":COUNTS["B1"],"law":law.name,
                "tier":tier.name,"addresses":[spec.domain.canonical(x) for x in addresses],
                "pre":base._store_wire(pre)})
            result=original_B1(law,tier,pre,addresses,targets,spec,*a,**kw)
            emit("B1_END",{"label":CURRENT,"ordinal":COUNTS["B1"],"post":base._store_wire(pre),
                "ledger":json.loads(result.ledger.canonical())})
            return result
        for obj,name,fn in ((K,"rollout",rollout),(K,"step",step),
            (base.LearnerPersistentState,"apply_transaction",transaction),(base.native_b1,"_run",B1)):
            stack.enter_context(patch.object(obj,name,fn))
        for obj,name in ((training,"train_curve"),(training,"episode_rollout"),(training,"key"),
            (training.ExogenousEpisode,"derive"),(dp,"solve_reference"),(base.ready,"build_reference"),
            (base.ready,"solve_reference"),(K.SemanticTape,"sample")):
            stack.enter_context(patch.object(obj,name,blocked))
        import random
        stack.enter_context(patch.object(random,"Random",blocked))
        result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(MixedImmediateTests))
        emit("FINAL",{"tests":result.testsRun,"failures":len(result.failures),"errors":len(result.errors),
            "skipped":len(result.skipped),"counts":COUNTS,"budget":LIMITS,"output_bytes_before_footer":OUTPUT_BYTES,
            "future_training":0,"DP":0,"keys_allocated":False,"new_calibration":False,"collector":False,
            "old_fixture_reruns":0,"scientific_PASS":False,"research_complete":False})
        sys.exit(0 if result.wasSuccessful() and not COUNTS["blocked"] else 1)
