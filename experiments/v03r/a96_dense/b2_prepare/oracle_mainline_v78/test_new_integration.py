"""Ten new SERIAL nonempty-T original-bank/internal capture checks, no old fixture rerun."""
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import traceback
import unittest
from unittest.mock import patch
PREP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PREP))
import oracle_mainline_v77 as addon
owner = addon.owner
base = addon.base
K = base.K
from rfl_rebuild.b2 import environment, training
from rfl_rebuild.learner.store import DECISION, PROCESS, CONTROLLER, Q, DecisionAddress, QAddress, Edit
from rfl_rebuild.solve import dp
COUNTS = {"rollout":0,"step":0,"transaction":0,"B1":0,"mean":0,"mean_completed":0,"blocked":0}
LIMITS = {"rollout":1200,"step":15000,"transaction":16,"B1":16,"mean":12}
CURRENT = "NOT_STARTED"
OUTPUT_BYTES = 0
def emit(tag,value):
    global OUTPUT_BYTES
    line=tag+"="+json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False)
    OUTPUT_BYTES+=len((line+"\n").encode("utf8"))
    if OUTPUT_BYTES>10000000:raise RuntimeError("predeclared stdout guard; no retry")
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
class TransientBankTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global CURRENT
        cls.reference=reference_from_stored()
        cls.healthy=base.ready.read_json(PREP/"healthy_reference_candidate.json")
        row=cls.reference.row(K.State(0,2,0,0,5),3,0)
        assert K.WAIT in row and row[K.WAIT]<max(row.values())
        cls.mask=K.FaultMask(decision=K.DecisionOverride(0,K.WAIT),
            controller=K.ControllerFault(K.State(0,2,0,0,5),K.WAIT,K.LEFT),
            plant=K.PlantFault(0,K.RIGHT),trap=K.Trap((1,2),0))
        cls.sources={}
        for label,cause in (("T_ALL_FIVE_PRIMARY",23),("T_ALL_FIVE_FOREIGN_DESCRIPTOR",24)):
            CURRENT=label
            scene=base.EvaluationScene(0,5,0,cause,0)
            state=base.LearnerPersistentState()
            emit("SOURCE_INPUT",{"label":label,"regime":"T","pre":base._store_wire(state),
                "configuration":owner._configuration(scene,cls.mask,3,cls.reference)})
            src=owner.capture_source(state,scene=scene,regime="T",q_reference=cls.reference,
                healthy_reference=cls.healthy,mask=cls.mask,option_fault=3)
            cls.sources[label]=src
            emit("OWNED_SOURCE",{"label":label,"audit":owner.source_audit(src)})
        cls.src=cls.sources["T_ALL_FIVE_PRIMARY"]
        cls.cells=(("D_Q",base.Tier.L0_FACTUAL,"FactualReturnWrite"),
                   ("D_patch",base.Tier.L0_FACTUAL,"DeleteFactualPatch"),
                   ("X",base.Tier.L0_FACTUAL,"X_id"),
                   ("P",base.Tier.L1_CORRECTIVE,"P_id"))
        cls.pairs={};cls.futures={};cls.banks={}
        for i,(arch,tier,law) in enumerate(cls.cells):
            CURRENT=f"cell{i}/T_ALL_FIVE_PRIMARY/{arch}"
            pair=owner.run_pair(cls.src,architecture=arch,tier=tier,law_name=law,
                assisted=base.AssistedInput(0) if arch=="P" else None)
            cls.pairs[i]=pair
            emit("NEW_PAIR",{"index":i,"audit":owner.pair_audit(pair,cls.src)})
            future=owner.prepare_future_inputs(pair,cls.src)
            cls.futures[i]=future
            emit("OWNED_FUTURE",{"index":i,"audit":owner.future_audit(future,cls.src)})
            if i<3:
                bank=addon.measure_bank(future,cls.src);cls.banks[i]=bank
                emit("OWNED_BANK",{"index":i,"audit":addon.bank_audit(bank,cls.src)})

    def test_01_nonempty_T_complete_source_five_mechanisms_residual(self):
        for src in self.sources.values():
            config,sd=owner._checked_source(src)
            self.assertEqual(sd.trace.outcome,K.Outcome.TRAP)
            self.assertEqual(sd.truth["Z_fire"],[True]*5)
            self.assertIsNone(sd.truth["Gamma_P_star"])
            self.assertEqual(sd.truth["Gamma_T_star"],
                ["ProcessCommit","Decision_0","ControllerSite_0_2_0_4","ExternalPlant","Unknown/NoWrite"])
            self.assertEqual(base._store_wire(sd.pre),{"D":[],"P":[],"Q":[],"X":[]})
            self.assertEqual(config.option_fault,3)
        self.assertNotEqual(owner._SOURCES[self.src].seal,
            owner._SOURCES[self.sources["T_ALL_FIVE_FOREIGN_DESCRIPTOR"]].seal)
        for i in range(4):
            pd=owner._checked_pair(self.pairs[i],self.src)[3]
            self.assertEqual(len(pd.projected.addresses),1)
            self.assertIn("ExternalPlant",pd.projected.residual_units)
            self.assertIn("Unknown/NoWrite",pd.projected.residual_units)
            self.assertEqual(set(pd.projected.whole_units),
                set(pd.projected.cell_units)|set(pd.projected.residual_units))

    def test_02_each_original_whole_samepre_receipt_nonown_scalar(self):
        pre=base._stores(owner._checked_source(self.src)[1].pre)
        seen=[]
        for i in range(4):
            pd=owner._checked_pair(self.pairs[i],self.src)[3]
            self.assertEqual(base._stores(pd.clones[0]),pre)
            for clone,result in zip(pd.clones,pd.results):
                self.assertEqual(len(result.ledger.receipts),1)
                self.assertTrue(all(clone is not other for other in seen))
                seen.append(clone)
            post=base._store_wire(pd.clones[1])
            for store in ("D","P","X"):
                self.assertEqual(post[store],[])
            ledger=pd.results[1].ledger
            if i==0:
                self.assertEqual(ledger.n_scalar,1)
                self.assertTrue(ledger.scalar_metrics_applicable)
                self.assertEqual(len(post["Q"]),1)
            else:
                self.assertEqual(post["Q"],[])
                self.assertFalse(ledger.scalar_metrics_applicable)
                self.assertEqual(ledger.n_scalar,0)

    def check_bank(self,i):
        d=addon._checked_bank(self.banks[i],self.src)
        _,config,native,sd=addon._inputs(self.futures[i],self.src)
        self.assertEqual(d.payload["source_configuration_not_reused_as_bank_faults"],
                         config.configuration)
        self.assertTrue(any(v is not None for v in config.configuration["faults"].values()))
        for arm,rows,mean,state,pinned in zip(d.payload["ordered_arms"],d.traces,d.means,
                                            d.starts,native.starts):
            self.assertEqual(len(rows),100)
            self.assertEqual(base._stores(state),base._stores(pinned))
            self.assertIsNot(state,pinned)
            self.assertEqual([r["scene"] for r in arm["ordered_scenes"]],
                [list(s.key) for s in native.template["sample"]])
            total=0.0
            for scene,trace,wire in zip(native.template["sample"],rows,arm["ordered_scenes"]):
                total+=trace.return_value
                self.assertEqual(trace.mask,K.FaultMask())
                self.assertFalse(trace.interventions.members)
                self.assertEqual(trace.option_in_force,scene.base_option)
                self.assertTrue(all(v is None for v in wire["faults"].values()))
                self.assertEqual(wire["raw"],base.factual._trace_payload(trace,scene))
            self.assertEqual(mean,total/100)
            self.assertEqual(arm["original_ordered_mean_hex"],mean.hex())
        self.assertIsNot(d.starts[0],d.starts[1])
        self.assertEqual(d.payload["native_bank_rollout_calls"],200)

    def test_03_actual_ordinary_bank_fault_isolation_complete_order_mean(self):
        for i in range(3):self.check_bank(i)

    def test_04_actual_full_roles_shared_original_lock_not_future_curve(self):
        for i in range(3):
            d=addon._checked_bank(self.banks[i],self.src)
            t=d.payload["shared_locked_template"]
            self.assertEqual(t["grid"],list(range(466)))
            self.assertEqual(t["alpha"],[1,2]);self.assertEqual(t["epsilon"],[1,10])
            self.assertEqual(t["T"],465);self.assertEqual(len(t["evaluation_units"]),100)
            self.assertIsNone(t["seed"]);self.assertEqual(d.payload["training_episodes"],0)
            self.assertFalse(d.payload["curve_created"]);self.assertIsNone(d.payload["primary_Collateral"])
            self.assertEqual([a["role"] for a in d.payload["ordered_arms"]],["reference","treatment"])

    def test_05_T_source_option_mask_payload_tamper_exact_restore(self):
        before=COUNTS.copy();saved=owner._SOURCES[self.src]
        for bad in (replace(saved,option_fault=None),replace(saved,mask=K.FaultMask())):
            try:
                owner._SOURCES[self.src]=bad
                with self.assertRaises(base.ready.ProtocolError):addon.bank_audit(self.banks[0],self.src)
            finally:owner._SOURCES[self.src]=saved
        old=deepcopy(saved.payload)
        try:
            saved.payload["configuration_declared_before_native"]["faults"]["option_fault"]=1
            with self.assertRaises(base.ready.ProtocolError):addon.bank_audit(self.banks[0],self.src)
        finally:saved.payload.clear();saved.payload.update(old)
        addon.bank_audit(self.banks[0],self.src)
        self.assertEqual(COUNTS,before)

    def test_06_T_role_alias_swap_and_bank_raw_seal_restore(self):
        before=COUNTS.copy();d=addon._BANKS[self.banks[0]]
        for bad in (replace(d,starts=d.starts[::-1]),replace(d,starts=(d.starts[0],d.starts[0]))):
            try:
                addon._BANKS[self.banks[0]]=bad
                with self.assertRaises(base.ready.ProtocolError):addon.bank_audit(self.banks[0],self.src)
            finally:addon._BANKS[self.banks[0]]=d
        old=deepcopy(d.payload)
        try:
            d.payload["ordered_arms"][0]["ordered_scenes"][0]["faults"]["option_fault"]=3
            with self.assertRaises(base.ready.ProtocolError):addon.bank_audit(self.banks[0],self.src)
        finally:d.payload.clear();d.payload.update(old)
        addon.bank_audit(self.banks[0],self.src)
        self.assertEqual(COUNTS,before)

    def test_07_wrong_issued_T_source_no_caller_state_sample_fault_callback_key(self):
        before=COUNTS.copy()
        foreign=self.sources["T_ALL_FIVE_FOREIGN_DESCRIPTOR"]
        with self.assertRaises(base.ready.ProtocolError):addon.bank_audit(self.banks[0],foreign)
        with self.assertRaises(base.ready.ProtocolError):addon.measure_bank(self.futures[3],foreign)
        with self.assertRaises(base.ready.ProtocolError):addon.measure_bank(object(),self.src)
        for kw in ("state","sample","mask","option_fault","callback","key"):
            with self.assertRaises(TypeError):addon.measure_bank(self.futures[3],self.src,**{kw:object()})
        self.assertEqual(COUNTS,before)

    def test_08_inside_first_bank_real_three_raw_prefix_finally_nohandle(self):
        global CURRENT
        CURRENT="EXPECTED_INTERNAL_CAPTURE_PARTIAL"
        pair=owner.run_pair(self.src,architecture="D_Q",tier=base.Tier.L3_ORACLE,
                            law_name="LocalOracleRestore")
        type(self).partial_pair=pair
        emit("PARTIAL_CHALLENGE_PAIR",owner.pair_audit(pair,self.src))
        future=owner.prepare_future_inputs(pair,self.src)
        type(self).partial_future=future
        emit("PARTIAL_CHALLENGE_FUTURE",owner.future_audit(future,self.src))
        before=COUNTS.copy();issued=len(addon._BANKS)
        original=environment.rollout;calls=[];states=[]
        def fail_fourth(*a,**kw):
            self.assertTrue(addon._BUSY)
            self.assertIsNot(training.learned_rollout,addon._ORIGINAL_LEARNED)
            calls.append(1)
            if len(calls)==4:raise RuntimeError("PREDECLARED_INTERNAL_CAPTURE_BEFORE_FOURTH_NATIVE")
            return original(*a,**kw)
        original_measure=addon._measure_original
        def keep_state(state,*a,**kw):
            states.append((state,base._store_wire(state)))
            return original_measure(state,*a,**kw)
        with patch.object(environment,"rollout",fail_fourth),patch.object(addon,"_measure_original",keep_state):
            try:
                addon.measure_bank(future,self.src)
                self.fail("partial bank handle issued")
            except RuntimeError as exc:
                self.assertEqual(str(exc),"PREDECLARED_INTERNAL_CAPTURE_BEFORE_FOURTH_NATIVE")
                emit("EXPECTED_INTERNAL_FAILURE_PRESERVED",{
                    "error":str(exc),"traceback":traceback.format_exc(),
                    "completed_raw_prefix":COUNTS["rollout"]-before["rollout"],
                    "original_mean_started":COUNTS["mean"]-before["mean"],
                    "original_mean_completed":COUNTS["mean_completed"]-before["mean_completed"],
                    "training_alias_restored":training.learned_rollout is addon._ORIGINAL_LEARNED,
                    "busy_restored_false":not addon._BUSY,
                    "all_actual_partial_role_stores":[{"before":b,"after":base._store_wire(s)} for s,b in states],
                    "bank_handle_issued":False,"retry":False})
        self.assertIs(environment.rollout,original)
        self.assertIs(training.learned_rollout,addon._ORIGINAL_LEARNED)
        self.assertFalse(addon._BUSY)
        self.assertEqual(len(addon._BANKS),issued)
        self.assertEqual(len(calls),4);self.assertEqual(len(states),1)
        self.assertEqual(COUNTS["rollout"]-before["rollout"],3)
        self.assertEqual(COUNTS["mean"]-before["mean"],1)
        self.assertEqual(COUNTS["mean_completed"],before["mean_completed"])
        for state,wire in states:self.assertEqual(base._store_wire(state),wire)

    def test_09_partial_pair_once_duplicate_future_refused_native_zero(self):
        before=COUNTS.copy()
        pair=type(self).partial_pair;future=type(self).partial_future
        duplicate=owner.prepare_future_inputs(pair,self.src)
        for f in (future,duplicate):
            with self.assertRaises(base.ready.ProtocolError):addon.measure_bank(f,self.src)
        self.assertTrue(addon._ATTEMPTED[pair])
        self.assertEqual(COUNTS,before)
        emit("PARTIAL_DUPLICATE_REFUSAL",{"pair_consumed":True,"new_future_does_not_bypass":True,
            "counts_before":before,"counts_after":COUNTS.copy(),"retry":False})

    def test_10_after_exception_different_unconsumed_P_pair_real_original_bank(self):
        global CURRENT
        CURRENT="cell3/T_ALL_FIVE_PRIMARY/P/AFTER_INTERNAL_EXCEPTION"
        before=COUNTS.copy()
        self.assertFalse(addon._BUSY)
        self.assertIs(training.learned_rollout,addon._ORIGINAL_LEARNED)
        self.assertNotIn(self.pairs[3],addon._ATTEMPTED)
        bank=addon.measure_bank(self.futures[3],self.src);self.banks[3]=bank
        emit("OWNED_BANK",{"index":3,"audit":addon.bank_audit(bank,self.src)})
        self.check_bank(3)
        self.assertEqual(COUNTS["rollout"]-before["rollout"],200)
        self.assertEqual(COUNTS["mean_completed"]-before["mean_completed"],2)
        emit("RESTORED_NEXT_INDEPENDENT_PAIR_COMPLETE",{"index":3,"real_rollouts":200,
            "real_original_means":2,"failed_pair_not_retried":True})

if __name__=="__main__":
    with ExitStack() as stack:
        original_rollout=K.rollout;original_step=K.step
        original_tx=base.LearnerPersistentState.apply_transaction;original_B1=base.native_b1._run
        original_measure=addon._measure_original
        def rollout(*a,**kw):
            count("rollout");trace=original_rollout(*a,**kw)
            scene=base.EvaluationScene(kw["kappa"],kw["tape"].phase,kw["tape"].error_flag,
                                      kw["tape"].cause_rank,kw["base_option"])
            emit("NATIVE_RAW_BEFORE_CALLER_TRUTH_OR_MEAN",{"label":CURRENT,"ordinal":COUNTS["rollout"],
                "configuration":owner._configuration(scene,kw.get("mask",K.FaultMask()),kw.get("option_fault"),
                                                     TransientBankTests.reference),
                "raw":base.factual._trace_payload(trace,scene),"outcome":trace.outcome,
                "return_hex":trace.return_value.hex(),"option_in_force":trace.option_in_force})
            return trace
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
                           (base.LearnerPersistentState,"apply_transaction",transaction),
                           (base.native_b1,"_run",B1),(addon,"_measure_original",measure)):
            stack.enter_context(patch.object(obj,name,fn))
        for obj,name in ((training,"train_curve"),(training,"episode_rollout"),(training,"key"),
            (training,"Curve"),(training,"FutureTrainingProtocol"),(training.ExogenousEpisode,"derive"),
            (dp,"solve_reference"),(base.ready,"build_reference"),(base.ready,"solve_reference"),
            (K.SemanticTape,"sample")):
            stack.enter_context(patch.object(obj,name,blocked))
        import random
        stack.enter_context(patch.object(random,"Random",blocked))
        result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TransientBankTests))
        emit("FINAL",{"tests":result.testsRun,"failures":len(result.failures),"errors":len(result.errors),
              "skipped":len(result.skipped),"counts":COUNTS,"budget":LIMITS,
              "output_bytes_before_footer":OUTPUT_BYTES,"training":0,"DP":0,"keys_allocated":False,
              "native_calibration":False,"collector":False,"old_fixture_reruns":0,
              "scientific_PASS":False,"research_complete":False})
        sys.exit(0 if result.wasSuccessful() and not COUNTS["blocked"] else 1)
