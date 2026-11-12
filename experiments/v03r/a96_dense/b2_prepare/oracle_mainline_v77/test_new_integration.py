"""Seventeen NEW SERIAL owned-bank interface checks. No old fixture/calibration rerun."""
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
COUNTS = {"rollout":0,"step":0,"transaction":0,"B1":0,"mean":0,"blocked":0}
LIMITS = {"rollout":1500,"step":18000,"transaction":32,"B1":32,"mean":16}
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
def fixture(reference, architecture):
    """Independent fixed literal installation; D/Q always exclusive."""
    state=base.LearnerPersistentState()
    edits=[Edit(PROCESS,0,2),Edit(PROCESS,3,1)]
    for (s,z,m),row in sorted(reference.rows.items(),key=lambda x:
          (x[0][0].x,x[0][0].y,x[0][0].t,x[0][0].kappa,x[0][0].phi,x[0][1],x[0][2])):
        if (s.kappa,s.phi,z)==(1,3,2) and K.WAIT in row:
            if architecture=="D_Q":
                edits.append(Edit(Q,QAddress(s,z,m,K.WAIT),max(row.values())+1.0))
            else:
                edits.append(Edit(DECISION,DecisionAddress(s,z,m),K.WAIT))
    sentinel=K.State(0,2,0,0,3)
    if architecture=="D_Q":
        edits.append(Edit(Q,QAddress(sentinel,2,0,K.WAIT),
                          max(reference.row(sentinel,2,0).values())+2.0))
    else:
        edits.append(Edit(DECISION,DecisionAddress(sentinel,2,0),K.WAIT))
    edits += [Edit(CONTROLLER,K.ControllerSite(K.State(0,2,0,1,3),K.WAIT),K.RIGHT),
              Edit(CONTROLLER,K.ControllerSite(K.State(1,2,1,1,3),K.WAIT),K.LEFT),
              Edit(CONTROLLER,K.ControllerSite(sentinel,K.WAIT),K.RIGHT)]
    state.apply_transaction(edits,q_reference=reference)
    snap=state.snapshot()
    assert not (snap.decision_overrides and snap.q_overrides)
    environment.learner_channels(snap,reference)  # construction only, no rollout
    return state

class OwnedBankTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global CURRENT
        cls.reference=reference_from_stored()
        cls.healthy=base.ready.read_json(PREP/"healthy_reference_candidate.json")
        scope=sorted([[s.x,s.y,s.t,s.kappa,s.phi,z,m,K.WAIT in row]
            for (s,z,m),row in cls.reference.rows.items() if (s.kappa,s.phi,z)==(1,3,2)])
        assert len(scope)==288 and sum(x[-1] for x in scope)==276
        emit("INSTALL_DECLARED_CONTEXT_SCOPE",{"all_contexts":scope,
             "illegal_WAIT_contexts_preserved":[x[:-1] for x in scope if not x[-1]],
             "selection":"original action legality before native, never effects"})
        CURRENT="INSTALL_P_Q_MIXED";qstate=fixture(cls.reference,"D_Q")
        CURRENT="INSTALL_P_PATCH_MIXED";patchstate=fixture(cls.reference,"D_patch")
        CURRENT="INSTALL_P_NO_MANIFEST_FAILURE"
        no_manifest=base.LearnerPersistentState()
        no_manifest.apply_transaction([Edit(DECISION,DecisionAddress(K.State(0,2,0,1,3),1,0),K.WAIT)],
                                      q_reference=cls.reference)
        specs=[
          ("P_Q_MIXED",qstate,base.EvaluationScene(1,3,0,9,0),"P",K.FaultMask()),
          ("P_PATCH_MIXED",patchstate,base.EvaluationScene(1,3,0,9,0),"P",K.FaultMask()),
          ("T_UNKNOWN_ONLY",base.LearnerPersistentState(),base.EvaluationScene(0,3,0,11,0),"T",
           K.FaultMask(trap=K.Trap((1,2),0))),
          ("T_SUCCESS",base.LearnerPersistentState(),base.EvaluationScene(0,3,0,11,0),"T",K.FaultMask()),
          ("P_NO_MANIFEST_FAILURE",no_manifest,base.EvaluationScene(0,2,0,13,0),"P",K.FaultMask())]
        cls.sources={}
        for label,state,scene,regime,mask in specs:
            CURRENT=label
            emit("SOURCE_INPUT",{"label":label,"pre":base._store_wire(state),"regime":regime,
                  "configuration":owner._configuration(scene,mask,None,cls.reference)})
            src=owner.capture_source(state,scene=scene,regime=regime,q_reference=cls.reference,
                                      healthy_reference=cls.healthy,mask=mask)
            cls.sources[label]=src;emit("OWNED_SOURCE",{"label":label,"audit":owner.source_audit(src)})
        cls.pairs={};cls.futures={};cls.banks={}
        cls.cells=[("P_Q_MIXED","D_Q",base.Tier.L0_FACTUAL,"FactualReturnWrite"),
                   ("P_Q_MIXED","X",base.Tier.L0_FACTUAL,"X_id"),
                   ("P_Q_MIXED","P",base.Tier.L1_CORRECTIVE,"P_id"),
                   ("P_PATCH_MIXED","D_patch",base.Tier.L0_FACTUAL,"DeleteFactualPatch"),
                   ("P_PATCH_MIXED","X",base.Tier.L3_ORACLE,"LocalOracleRestore"),
                   ("P_PATCH_MIXED","P",base.Tier.L3_ORACLE,"LocalOracleRestore"),
                   ("T_UNKNOWN_ONLY","D_Q",base.Tier.L0_FACTUAL,"FactualReturnWrite"),
                   ("T_SUCCESS","D_Q",base.Tier.L0_FACTUAL,"FactualReturnWrite"),
                   ("P_NO_MANIFEST_FAILURE","D_Q",base.Tier.L0_FACTUAL,"FactualReturnWrite")]
        for i,(label,arch,tier,law) in enumerate(cls.cells):
            CURRENT=f"cell{i}/{label}/{arch}"
            src=cls.sources[label]
            pair=owner.run_pair(src,architecture=arch,tier=tier,law_name=law,
                 assisted=base.AssistedInput(0) if arch=="P" else None)
            cls.pairs[i]=pair
            emit("NEW_PAIR",{"index":i,"audit":owner.pair_audit(pair,src)})
            future=owner.prepare_future_inputs(pair,src);cls.futures[i]=future
            emit("OWNED_FUTURE",{"index":i,"audit":owner.future_audit(future,src)})
            bank=addon.measure_bank(future,src);cls.banks[i]=bank
            emit("OWNED_BANK",{"index":i,"audit":addon.bank_audit(bank,src)})
    def test_01_complete_four_stores_exclusive_independent_extensional_Gamma(self):
        a=owner._checked_source(self.sources["P_Q_MIXED"])[1]
        b=owner._checked_source(self.sources["P_PATCH_MIXED"])[1]
        self.assertEqual(base.factual._trace_payload(a.trace,a.scene),base.factual._trace_payload(b.trace,b.scene))
        self.assertEqual(a.truth,b.truth)
        for label,active,empty in (("P_Q_MIXED","Q","D"),("P_PATCH_MIXED","D","Q")):
            sd=owner._checked_source(self.sources[label])[1];stores=base._store_wire(sd.pre)
            self.assertEqual(set(stores),{"D","P","Q","X"})
            self.assertTrue(stores[active]);self.assertEqual(stores[empty],[])
            self.assertEqual(sd.truth["J_L"],[True]*3)
        for i in range(6):
            src=self.sources[self.cells[i][0]];sd=owner._checked_source(src)[1]
            pr=owner._checked_pair(self.pairs[i],src)[3].projected
            self.assertEqual(set(pr.whole_units),set(sd.truth["Gamma_P_star"]))
            self.assertEqual(set(pr.cell_units)|set(pr.residual_units),set(pr.whole_units))
            self.assertFalse(set(pr.cell_units)&set(pr.residual_units));self.assertTrue(pr.addresses)
    def test_02_independent_cells_samepre_whole_receipts(self):
        for i in range(6):
            src=self.sources[self.cells[i][0]];sd=owner._checked_source(src)[1]
            pd=owner._checked_pair(self.pairs[i],src)[3]
            for state,res in zip(pd.clones,pd.results):
                self.assertEqual(len(res.ledger.receipts),len(pd.projected.addresses))
            self.assertEqual(base._stores(pd.clones[0]),base._stores(sd.pre))
            for j in range(i):
                other=owner._checked_pair(self.pairs[j],self.sources[self.cells[j][0]])[3]
                self.assertTrue(all(a is not b for a in pd.clones for b in other.clones))
    def test_03_original_complete100_order_raw_mean(self):
        
        for i in range(6):
            src=self.sources[self.cells[i][0]]
            d=addon._checked_bank(self.banks[i],src)
            f,config,native,sd=addon._inputs(self.futures[i],src)
            self.assertEqual([a["role"] for a in d.payload["ordered_arms"]],["reference","treatment"])
            for rows,mean,arm in zip(d.traces,d.means,d.payload["ordered_arms"]):
                self.assertEqual(len(rows),100)
                self.assertEqual([r["scene"] for r in arm["ordered_scenes"]],
                                 [list(s.key) for s in native.template["sample"]])
                total=0.0
                for t in rows:total+=t.return_value
                self.assertEqual(mean,total/100)
                self.assertEqual(arm["original_ordered_mean_hex"],mean.hex())
                self.assertTrue(all(t.mask==K.FaultMask() and not t.interventions.members for t in rows))
    def test_04_full_role_starts_nonown_sentinel_readonly(self):
        
        for i in range(6):
            src=self.sources[self.cells[i][0]]
            _,sd=owner._checked_source(src)
            d=addon._checked_bank(self.banks[i],src);pd=owner._checked_pair(self.pairs[i],src)[3]
            for state,pinned in zip(d.starts,pd.clones):
                self.assertEqual(base._stores(state),base._stores(pinned));self.assertIsNot(state,pinned)
                self.assertEqual(state.process_overrides.get(3),1)
                for view in ("decision_overrides","q_overrides","controller_overrides"):
                    self.assertEqual({a:v for a,v in getattr(state,view).items() if a.state.kappa==0},
                                     {a:v for a,v in getattr(sd.pre,view).items() if a.state.kappa==0})
    def test_05_shared_locked_original_template_not_curve(self):
        
        for i in range(6):
            src=self.sources[self.cells[i][0]]
            d=addon._checked_bank(self.banks[i],src);t=d.payload["shared_locked_template"]
            self.assertEqual(t["grid"],list(range(466)));self.assertEqual(t["T"],465)
            self.assertEqual(t["alpha"],[1,2]);self.assertEqual(t["epsilon"],[1,10])
            self.assertEqual(len(t["evaluation_units"]),100);self.assertIsNone(t["seed"])
            self.assertFalse(d.payload["curve_created"]);self.assertIsNone(d.payload["primary_Collateral"])
            self.assertEqual(d.payload["training_episodes"],0)
    def check_empty(self,i):
        label=self.cells[i][0];src=self.sources[label]
        pd=owner._checked_pair(self.pairs[i],src)[3]
        bank=addon._checked_bank(self.banks[i],src)
        self.assertEqual(pd.results,());self.assertEqual(bank.starts,());self.assertEqual(bank.means,())
        self.assertEqual(bank.payload["ordered_arms"],[])
        self.assertIsNone(bank.payload["shared_locked_template"])
        self.assertEqual(bank.payload["native_bank_rollout_calls"],0)
        self.assertEqual(bank.payload["route"],"INAPPLICABLE_NO_FAKE_BANK")
    def test_06_unknown_only_empty_projection_no_fake_bank(self):
        self.check_empty(6);_,sd=owner._checked_source(self.sources["T_UNKNOWN_ONLY"])
        self.assertEqual(sd.truth["Gamma_T_star"],["Unknown/NoWrite"])
        pd=owner._checked_pair(self.pairs[6],self.sources["T_UNKNOWN_ONLY"])[3]
        self.assertEqual(pd.projected.residual_units,("Unknown/NoWrite",))
    def test_07_T_success_no_reflection_bank(self):
        self.check_empty(7);_,sd=owner._checked_source(self.sources["T_SUCCESS"])
        self.assertEqual(sd.trace.outcome,K.Outcome.SUCCESS);self.assertIsNone(sd.truth)
    def test_08_P_failure_without_manifest_no_fake_zero(self):
        self.check_empty(8);_,sd=owner._checked_source(self.sources["P_NO_MANIFEST_FAILURE"])
        self.assertNotEqual(sd.trace.outcome,K.Outcome.SUCCESS)
        self.assertEqual(sd.truth["Gamma_P_star"],[])
    def test_09_foreign_nominal_wrongsource_before_native(self):
        before=COUNTS.copy();src=self.sources["P_Q_MIXED"]
        with self.assertRaises(base.ready.ProtocolError):addon.OwnedBank()
        with self.assertRaises(base.ready.ProtocolError):addon.bank_audit(self.banks[0],self.sources["T_SUCCESS"])
        with self.assertRaises(base.ready.ProtocolError):addon.measure_bank(object(),src)
        with self.assertRaises(base.ready.ProtocolError):addon.measure_bank(self.futures[0],object())
        self.assertEqual(COUNTS,before)
    def test_10_bank_template_order_tamper_restore(self):
        src=self.sources["P_Q_MIXED"];fd,config=owner._checked_future(self.futures[0],src)
        saved=base._FUTURES[fd.native];bad=dict(saved.template);bad["sample"]=tuple(reversed(bad["sample"]))
        try:
            base._FUTURES[fd.native]=replace(saved,template=bad)
            with self.assertRaises(base.ready.ProtocolError):addon.bank_audit(self.banks[0],src)
        finally:base._FUTURES[fd.native]=saved
        addon.bank_audit(self.banks[0],src)
    def test_11_future_role_swap_alias_restore(self):
        src=self.sources["P_Q_MIXED"];fd,config=owner._checked_future(self.futures[0],src)
        saved=base._FUTURES[fd.native]
        for bad in (saved.starts[::-1],(saved.starts[0],saved.starts[0])):
            try:
                base._FUTURES[fd.native]=replace(saved,starts=bad)
                with self.assertRaises(base.ready.ProtocolError):addon.bank_audit(self.banks[0],src)
            finally:base._FUTURES[fd.native]=saved
    def test_12_partial_bank_or_wrong_role_starts_refused(self):
        src=self.sources["P_Q_MIXED"];h=self.banks[0];saved=addon._BANKS[h]
        for bad in (replace(saved,traces=(saved.traces[0][:-1],saved.traces[1])),
                    replace(saved,means=saved.means[:1]),replace(saved,starts=saved.starts[::-1]),
                    replace(saved,starts=(saved.starts[0],saved.starts[0]))):
            try:
                addon._BANKS[h]=bad
                with self.assertRaises(base.ready.ProtocolError):addon.bank_audit(h,src)
            finally:addon._BANKS[h]=saved
    def test_13_raw_mean_payload_tamper_restore(self):
        src=self.sources["P_Q_MIXED"];d=addon._BANKS[self.banks[0]]
        old=deepcopy(d.payload)
        try:
            d.payload["ordered_arms"][0]["ordered_scenes"][0]["return_hex"]="0x0.0p+0"
            with self.assertRaises(base.ready.ProtocolError):addon.bank_audit(self.banks[0],src)
        finally:d.payload.clear();d.payload.update(old)
        addon.bank_audit(self.banks[0],src)
    def test_14_exact_source_config_tamper_restore(self):
        src=self.sources["P_Q_MIXED"];saved=owner._SOURCES[src]
        try:
            owner._SOURCES[src]=replace(saved,option_fault=1)
            with self.assertRaises(base.ready.ProtocolError):addon.bank_audit(self.banks[0],src)
        finally:owner._SOURCES[src]=saved
        addon.bank_audit(self.banks[0],src)
    def test_15_once_by_pair_not_duplicate_future_handle(self):
        src=self.sources["P_Q_MIXED"];before=COUNTS.copy()
        other=owner.prepare_future_inputs(self.pairs[0],src)
        for f in (self.futures[0],other):
            with self.assertRaises(base.ready.ProtocolError):addon.measure_bank(f,src)
        self.assertEqual(COUNTS,before)
    def test_16_partial_first100_native_second_pre_native_nohandle_noretry(self):
        global CURRENT
        CURRENT="EXPECTED_PARTIAL_BANK";src=self.sources["P_Q_MIXED"]
        pair=owner.run_pair(src,architecture="D_Q",tier=base.Tier.L3_ORACLE,law_name="LocalOracleRestore")
        emit("PARTIAL_CHALLENGE_PAIR",owner.pair_audit(pair,src))
        f=owner.prepare_future_inputs(pair,src);emit("PARTIAL_CHALLENGE_FUTURE",owner.future_audit(f,src))
        original=addon._measure_original;calls=[];issued=len(addon._BANKS);before=COUNTS.copy()
        def fail_second(*a,**kw):
            calls.append(1)
            if len(calls)==2:raise RuntimeError("PREDECLARED_SECOND_BANK_BEFORE_NATIVE")
            return original(*a,**kw)
        with patch.object(addon,"_measure_original",fail_second):
            try:
                addon.measure_bank(f,src);self.fail("partial bank handle issued")
            except RuntimeError as exc:
                self.assertEqual(str(exc),"PREDECLARED_SECOND_BANK_BEFORE_NATIVE")
                emit("EXPECTED_FAILURE_PRESERVED",{"error":str(exc),"traceback":traceback.format_exc(),
                    "actual_first_bank_rollouts":COUNTS["rollout"]-before["rollout"],
                    "bank_handle_issued":False,"retry":False})
        self.assertEqual(len(addon._BANKS),issued);self.assertEqual(COUNTS["rollout"]-before["rollout"],100)
        before=COUNTS.copy();other=owner.prepare_future_inputs(pair,src)
        for h in (f,other):
            with self.assertRaises(base.ready.ProtocolError):addon.measure_bank(h,src)
        self.assertEqual(COUNTS,before)

    def test_17_original_A77_both_entrypoints_construction_reject_no_native(self):
        global CURRENT
        from rfl_rebuild.learner.store import LearnerStateError
        CURRENT="PREDECLARED_A77_INVALID_SMALL_STATE"
        state=base.LearnerPersistentState()
        s=K.State(0,2,0,0,5)
        state.apply_transaction([Edit(DECISION,DecisionAddress(s,1,0),K.WAIT),
            Edit(Q,QAddress(s,1,0,K.WAIT),max(self.reference.row(s,1,0).values())+1.0)],
            q_reference=self.reference)
        before=COUNTS.copy();snap=state.snapshot();saved=base._store_wire(state);calls=[]
        def forbidden_provider(*args,**kwargs):
            calls.append(1);raise AssertionError("base provider entered")
        for label,call in (
            ("decision_provider",lambda:snap.decision_provider(forbidden_provider)),
            ("q_decision_provider",lambda:snap.q_decision_provider(self.reference)),
            ("shared_learner_channels",lambda:environment.learner_channels(snap,self.reference)),
            ("original_learned_rollout",lambda:environment.learned_rollout(state,kappa=0,
               tape=base.EvaluationScene(0,5,0,17,1).tape,base_option=1,q_reference=self.reference))):
            with self.assertRaises(LearnerStateError) as exc:call()
            emit("EXPECTED_A77_REJECTION",{"entrypoint":label,"full_stores":saved,
                "error":str(exc.exception),"base_provider_called":False,"kernel_rollout_delta":0})
        self.assertEqual(COUNTS,before);self.assertEqual(calls,[])
        self.assertEqual(base._store_wire(state),saved)

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
                                                     OwnedBankTests.reference),
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
        result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(OwnedBankTests))
        emit("FINAL",{"tests":result.testsRun,"failures":len(result.failures),"errors":len(result.errors),
              "skipped":len(result.skipped),"counts":COUNTS,"budget":LIMITS,
              "output_bytes_before_footer":OUTPUT_BYTES,"training":0,"DP":0,"keys_allocated":False,
              "native_calibration":False,"collector":False,"old_fixture_reruns":0,
              "scientific_PASS":False,"research_complete":False})
        sys.exit(0 if result.wasSuccessful() and not COUNTS["blocked"] else 1)
