"""Seven new SERIAL T L2 config/replay/receipt/ordinary-bank checks; no old fixtures."""
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import replace
import hashlib
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
COUNTS={"rollout":0,"step":0,"transaction":0,"B1":0,"CF_replay":0,"mean":0,"mean_completed":0,"blocked":0}
LIMITS={"rollout":600,"step":7200,"transaction":8,"B1":8,"CF_replay":32,"mean":6}
CURRENT="NOT_STARTED"
OUTPUT_BYTES=0
REPLAYS=[]
ENVELOPES=[]
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
def reverse_fold(raw,t):
    result=0.0
    for row in reversed(raw[t:]):result=float.fromhex(row["reward_hex"])+result
    return result
def iv_wire(iv):
    return {"kind":iv.kind,"t":iv.t,"repr":repr(iv)}
class TransientL2BankTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global CURRENT
        cls.reference=reference_from_stored()
        cls.healthy=base.ready.read_json(PREP/"healthy_reference_candidate.json")
        start=cls.reference.row(K.State(0,2,0,0,2),3,0)
        later=cls.reference.row(K.State(1,2,1,0,2),3,0)
        assert max(start,key=start.get)==K.RIGHT
        assert K.WAIT in later and later[K.WAIT]<max(later.values())
        assert max(later,key=later.get)==K.DOWN
        cls.mask=K.FaultMask(decision=K.DecisionOverride(1,K.WAIT),
            controller=K.ControllerFault(K.State(1,2,1,0,2),K.WAIT,K.LEFT),
            plant=K.PlantFault(1,K.DOWN),trap=K.Trap((1,3),1))
        cls.sources={}
        for label,cause in (("T_L2_CONFIG_PRIMARY",29),("T_L2_CONFIG_FOREIGN",30)):
            CURRENT=label
            scene=base.EvaluationScene(0,2,0,cause,0)
            state=base.LearnerPersistentState()
            emit("SOURCE_INPUT",{"label":label,"pre":base._store_wire(state),"regime":"T",
                "counterfactual":True,"configuration":owner._configuration(scene,cls.mask,3,cls.reference)})
            src=owner.capture_source(state,scene=scene,regime="T",q_reference=cls.reference,
                healthy_reference=cls.healthy,mask=cls.mask,option_fault=3,counterfactual=True)
            cls.sources[label]=src
            emit("OWNED_SOURCE",{"label":label,"audit":owner.source_audit(src)})
        cls.src=cls.sources["T_L2_CONFIG_PRIMARY"]
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

    def test_01_complete_T_config_full_episode_replay_prefix_and_do_only(self):
        for src in self.sources.values():
            config,sd=owner._checked_source(src)
            self.assertEqual(config.option_fault,3)
            self.assertEqual(sd.trace.outcome,K.Outcome.TRAP)
            self.assertEqual(sd.truth["Z_fire"],[True]*5)
            self.assertIsNone(sd.truth["Gamma_P_star"])
            self.assertEqual(set(sd.truth["Gamma_T_star"]),{"ProcessCommit","Decision_1",
                "ControllerSite_1_2_1_4","ExternalPlant","Unknown/NoWrite"})
            self.assertEqual(base._store_wire(sd.pre),{"D":[],"P":[],"Q":[],"X":[]})
            self.assertEqual(sd.episode.factual_trace,sd.trace)
        _,sd=owner._checked_source(self.src)
        factual=base.factual._trace_payload(sd.trace,sd.scene)
        self.assertEqual(len(factual),2)
        self.assertEqual(len(REPLAYS),14)
        for r in REPLAYS:
            self.assertEqual(r["configuration"]["mask"],base.factual._mask_payload(self.mask,3))
            self.assertEqual(r["configuration"]["snapshot_pre"],base._store_wire(sd.pre))
            self.assertEqual(r["configuration"]["base_option"],0)
            self.assertEqual(r["configuration"]["reward_mode"],"A")
            self.assertEqual(r["raw"][0]["pre_state"],[0,2,0,0,2])
            if r["requested_t"] is not None:
                self.assertEqual(r["requested_t"],1);self.assertEqual(r["requested_action"],K.DOWN)
                self.assertEqual(r["raw"][:1],factual[:1])
                self.assertEqual(r["raw"][1]["a_cmd"],K.DOWN)
                self.assertEqual(len(r["actual_interventions"]),1)
            else:self.assertEqual(r["actual_interventions"],[])

    def test_02_original_builder_validator_replays_and_frozen_returns(self):
        _,sd=owner._checked_source(self.src)
        factual=base.factual._trace_payload(sd.trace,sd.scene)
        self.assertEqual(len(ENVELOPES),4)
        cf=[r for r in REPLAYS if r["requested_t"] is not None]
        self.assertEqual(len(cf),12)
        for e in ENVELOPES:
            self.assertEqual(len(e["targets"]),1)
            rec=e["targets"][0]
            self.assertEqual(rec["a_factual"],K.WAIT);self.assertEqual(rec["a_plus"],K.DOWN)
            self.assertEqual(float.fromhex(rec["g_factual_hex"]),reverse_fold(factual,1))
            self.assertEqual(float.fromhex(rec["g_cf_hex"]),reverse_fold(cf[0]["raw"],1))
        for name in self.pairs:
            self.assertEqual(len([r for r in cf if r["label"]==name]),6)

    def test_03_whole_samepre_all_owner_receipts_effective_Q_and_residual(self):
        seen=[]
        for name,pair in self.pairs.items():
            config,sd,_,pd=owner._checked_pair(pair,self.src)
            self.assertEqual(len(pd.projected.addresses),1)
            self.assertEqual(set(pd.projected.whole_units),
                set(pd.projected.cell_units)|set(pd.projected.residual_units))
            self.assertEqual(set(pd.projected.residual_units),{"ProcessCommit",
                "ControllerSite_1_2_1_4","ExternalPlant","Unknown/NoWrite"})
            self.assertEqual(base._stores(pd.clones[0]),base._stores(sd.pre))
            for clone,result in zip(pd.clones,pd.results):
                self.assertEqual(len(result.ledger.receipts),1)
                self.assertTrue(all(clone is not s for s in seen));seen.append(clone)
                for store in ("D","P","X"):self.assertEqual(base._store_wire(clone)[store],[])
            ledger=pd.results[1].ledger
            self.assertEqual(ledger.receipts[0].status,base.APPLIED)
            self.assertTrue(ledger.receipts[0].store_changed)
            self.assertEqual(ledger.n_scalar,1 if name=="CounterfactualReturnWrite" else 2)
            self.assertTrue(ledger.scalar_metrics_applicable)

    def test_04_actual_ordinary_full_banks_not_source_fault_replay_or_curve(self):
        for name,bank in self.banks.items():
            d=addon._checked_bank(bank,self.src)
            _,config,native,sd=addon._inputs(self.futures[name],self.src)
            self.assertEqual(d.payload["source_configuration_not_reused_as_bank_faults"],config.configuration)
            self.assertEqual(d.payload["shared_locked_template"]["grid"],list(range(466)))
            self.assertIsNone(d.payload["shared_locked_template"]["seed"])
            self.assertFalse(d.payload["curve_created"])
            self.assertIsNone(d.payload["primary_Collateral"])
            for arm,rows,mean,state,pinned in zip(d.payload["ordered_arms"],d.traces,d.means,d.starts,native.starts):
                self.assertIsNot(state,pinned);self.assertEqual(base._stores(state),base._stores(pinned))
                self.assertEqual(len(rows),100)
                self.assertEqual([r["scene"] for r in arm["ordered_scenes"]],[list(s.key) for s in native.template["sample"]])
                total=0.0
                for scene,trace,wire in zip(native.template["sample"],rows,arm["ordered_scenes"]):
                    total+=trace.return_value
                    self.assertEqual(trace.mask,K.FaultMask())
                    self.assertFalse(trace.interventions.members)
                    self.assertEqual(trace.option_in_force,scene.base_option)
                    self.assertTrue(all(v is None for v in wire["faults"].values()))
                    self.assertEqual(wire["raw"],base.factual._trace_payload(trace,scene))
                self.assertEqual(mean,total/100)

    def test_05_CF_optionfault_and_foreign_episode_exact_restore_no_replay(self):
        before=COUNTS.copy();config,sd=owner._checked_source(self.src)
        episode=sd.episode;old=episode.option_fault
        try:
            object.__setattr__(episode,"option_fault",1)
            with self.assertRaises(base.ready.ProtocolError):addon.bank_audit(self.banks["DualReturnWrite"],self.src)
        finally:object.__setattr__(episode,"option_fault",old)
        foreign=owner._checked_source(self.sources["T_L2_CONFIG_FOREIGN"])[1].episode
        saved=base._SOURCES[config.native]
        try:
            base._SOURCES[config.native]=replace(saved,episode=foreign)
            with self.assertRaises(base.ready.ProtocolError):owner.source_audit(self.src)
        finally:base._SOURCES[config.native]=saved
        owner.source_audit(self.src)
        self.assertEqual(COUNTS,before)
        emit("SOURCE_ERROR_GATES",{"counts_before":before,"counts_after":COUNTS.copy(),
            "optionfault_exact_restore":True,"foreign_episode_refused":True,"new_episode_constructor":False})

    def test_06_L2_missing_owner_receipt_and_wrong_scalar_refused_no_native(self):
        before=COUNTS.copy();pair=self.pairs["DualReturnWrite"]
        _,_,wrapper,pd=owner._checked_pair(pair,self.src)
        original=pd.results[1]
        for ledger in (replace(original.ledger,receipts=()),
                       replace(original.ledger,n_scalar=original.ledger.n_scalar+1)):
            try:
                altered=replace(original,ledger=ledger)
                base._PAIRS[wrapper.native]=replace(pd,results=(pd.results[0],altered))
                with self.assertRaises(base.ready.ProtocolError):owner.pair_audit(pair,self.src)
            finally:base._PAIRS[wrapper.native]=pd
        owner.pair_audit(pair,self.src)
        self.assertEqual(COUNTS,before)
        emit("RECEIPT_ERROR_GATES",{"counts_before":before,"counts_after":COUNTS.copy(),
            "full_missing_owner_and_scalar_rejected":True,"exact_restored":True})

    def test_07_L2_cell_and_bank_pair_once_foreign_and_caller_payload_refused(self):
        before=COUNTS.copy();foreign=self.sources["T_L2_CONFIG_FOREIGN"]
        for name,pair in self.pairs.items():
            with self.assertRaises(base.ready.ProtocolError):
                owner.run_pair(self.src,architecture="D_Q",tier=base.Tier.L2_COUNTERFACTUAL,law_name=name)
            duplicate=owner.prepare_future_inputs(pair,self.src)
            with self.assertRaises(base.ready.ProtocolError):addon.measure_bank(duplicate,self.src)
            with self.assertRaises(base.ready.ProtocolError):addon.bank_audit(self.banks[name],foreign)
            for kw in ("state","sample","callback","key"):
                with self.assertRaises(TypeError):addon.measure_bank(duplicate,self.src,**{kw:object()})
        self.assertEqual(COUNTS,before)
        emit("ONCE_SOURCE_API_GATES",{"counts_before":before,"counts_after":COUNTS.copy(),
            "no_retry":True,"duplicate_future_no_bypass":True,"wrong_source_refused":True})

if __name__=="__main__":
    with ExitStack() as stack:
        original_rollout=K.rollout;original_step=K.step
        original_tx=base.LearnerPersistentState.apply_transaction;original_B1=base.native_b1._run
        original_measure=addon._measure_original
        original_replay=base.native_cf.CfEpisode.replay
        original_builder=base.native_b1.build_counterfactual_envelope
        def rollout(*a,**kw):
            count("rollout");trace=original_rollout(*a,**kw)
            scene=base.EvaluationScene(kw["kappa"],kw["tape"].phase,kw["tape"].error_flag,
                                      kw["tape"].cause_rank,kw["base_option"])
            emit("NATIVE_RAW_BEFORE_CALLER_TRUTH_TARGET_OR_MEAN",{"label":CURRENT,"ordinal":COUNTS["rollout"],
                "configuration":owner._configuration(scene,kw.get("mask",K.FaultMask()),kw.get("option_fault"),
                                                      TransientL2BankTests.reference),
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
            ENVELOPES.append(record);emit("ORIGINAL_CF_ENVELOPE",record)
            return envelope
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
            (base.LearnerPersistentState,"apply_transaction",transaction),(base.native_b1,"_run",B1),
            (addon,"_measure_original",measure)):
            stack.enter_context(patch.object(obj,name,fn))
        for obj,name in ((training,"train_curve"),(training,"episode_rollout"),(training,"key"),
            (training,"Curve"),(training,"FutureTrainingProtocol"),(training.ExogenousEpisode,"derive"),
            (dp,"solve_reference"),(base.ready,"build_reference"),(base.ready,"solve_reference"),
            (K.SemanticTape,"sample")):
            stack.enter_context(patch.object(obj,name,blocked))
        import random
        stack.enter_context(patch.object(random,"Random",blocked))
        result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TransientL2BankTests))
        emit("FINAL",{"tests":result.testsRun,"failures":len(result.failures),"errors":len(result.errors),
            "skipped":len(result.skipped),"counts":COUNTS,"budget":LIMITS,
            "output_bytes_before_footer":OUTPUT_BYTES,"training":0,"DP":0,"keys_allocated":False,
            "native_calibration":False,"collector":False,"old_fixture_reruns":0,
            "scientific_PASS":False,"research_complete":False})
        sys.exit(0 if result.wasSuccessful() and not COUNTS["blocked"] else 1)
