"""Six new SERIAL original L2 no-alternative/zero-write owned-bank checks."""
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
COUNTS={"rollout":0,"step":0,"transaction":0,"B1":0,"CF_replay":0,"validator":0,"plan":0,"mean":0,"mean_completed":0,"blocked":0}
LIMITS={"rollout":500,"step":6000,"transaction":2,"B1":6,"CF_replay":4,"validator":16,"plan":6,"mean":6}
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
class ZeroAlternativeBankTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global CURRENT
        cls.reference=reference_from_stored()
        cls.healthy=base.ready.read_json(PREP/"healthy_reference_candidate.json")
        start=cls.reference.row(K.State(0,2,0,0,3),1,0)
        generation=cls.reference.row(K.State(1,2,1,0,3),1,0)
        actual=cls.reference.row(K.State(1,2,1,0,3),3,0)
        assert max(start,key=lambda a:(start[a],-a))==K.RIGHT
        assert max(generation,key=lambda a:(generation[a],-a))==K.UP
        assert K.DOWN in generation and generation[K.DOWN]<max(generation.values())
        assert [a for a,v in actual.items() if v>=max(actual.values())-1e-12]==[K.DOWN]
        cls.mask=K.FaultMask(decision=K.DecisionOverride(1,K.DOWN),
            plant=K.PlantFault(1,K.WAIT),trap=K.Trap((1,2),1))
        CURRENT="T_L2_NO_ALT_COFAULT"
        scene=base.EvaluationScene(0,3,0,31,1)
        emit("SOURCE_INPUT",{"label":CURRENT,"pre":base._store_wire(base.LearnerPersistentState()),
            "regime":"T","counterfactual":True,
            "configuration":owner._configuration(scene,cls.mask,3,cls.reference),
            "original_generation_row":[[a,v.hex()] for a,v in sorted(generation.items())],
            "original_actual_row":[[a,v.hex()] for a,v in sorted(actual.items())]})
        cls.src=owner.capture_source(base.LearnerPersistentState(),scene=scene,regime="T",
            q_reference=cls.reference,healthy_reference=cls.healthy,mask=cls.mask,
            option_fault=3,counterfactual=True)
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

    def test_01_original_cofault_source_structural_credit_not_optimality_filter(self):
        config,sd=owner._checked_source(self.src)
        self.assertEqual(sd.trace.outcome,K.Outcome.TRAP)
        self.assertEqual(sd.truth["Z_fire"],[True,True,False,True,True])
        self.assertIsNone(sd.truth["Gamma_P_star"])
        self.assertEqual(set(sd.truth["Gamma_T_star"]),
            {"ProcessCommit","Decision_1","ExternalPlant","Unknown/NoWrite"})
        self.assertEqual(len(sd.truth["R_mech"]),4)
        self.assertEqual(config.option_fault,3)
        self.assertIs(sd.episode.factual_trace,sd.trace)
        raw=base.factual._trace_payload(sd.trace,sd.scene)
        self.assertEqual(len(raw),2)
        self.assertEqual(raw[1]["pre_state"],[1,2,1,0,3])
        self.assertEqual((raw[1]["a_cmd"],raw[1]["u"],raw[1]["a_realized"]),(K.DOWN,K.DOWN,K.WAIT))
        self.assertEqual(raw[1]["post_state"],[1,2,2,0,3])

    def test_02_complete_None_pair_original_builders_validators_no_CF_replay(self):
        self.assertEqual(len(ENVELOPES),4)
        self.assertEqual(len(VALIDATIONS),8)
        self.assertEqual(len(REPLAYS),1)
        self.assertIsNone(REPLAYS[0]["requested_t"])
        for envelope in ENVELOPES:
            self.assertEqual(len(envelope["targets"]),1)
            rec=envelope["targets"][0]
            self.assertEqual(rec["a_factual"],K.DOWN)
            self.assertIsNone(rec["a_plus"]);self.assertIsNone(rec["g_cf_hex"])
            self.assertEqual(float.fromhex(rec["g_factual_hex"]),-1.02)

    def test_03_zero_edit_original_plans_complete_owner_status_not_factual_half(self):
        self.assertEqual(len(PLANS),4)
        for plan in PLANS:
            self.assertEqual(len(plan["plans"]),1)
            self.assertEqual(plan["plans"][0]["edits"],[])
            self.assertIsNone(plan["plans"][0]["row_op"])
            self.assertEqual(plan["plans"][0]["status"],
                None if plan["law"]=="NoWrite" else base.NO_VALID_ALTERNATIVE)
        _,sd=owner._checked_source(self.src)
        states=[sd.pre]
        for name,pair in self.pairs.items():
            _,_,_,pd=owner._checked_pair(pair,self.src)
            self.assertEqual(pd.projected.cell_units,("Decision_1",))
            self.assertEqual(set(pd.projected.residual_units),{"ProcessCommit","ExternalPlant","Unknown/NoWrite"})
            for i,(state,result) in enumerate(zip(pd.clones,pd.results)):
                self.assertTrue(all(state is not x for x in states));states.append(state)
                self.assertEqual(base._store_wire(state),{"D":[],"P":[],"Q":[],"X":[]})
                ledger=result.ledger
                self.assertEqual(len(ledger.receipts),1)
                self.assertEqual(ledger.receipts[0].status,
                    base.EVALUABLE_NOOP if i==0 else base.NO_VALID_ALTERNATIVE)
                self.assertFalse(ledger.receipts[0].store_changed)
                self.assertTrue(ledger.scalar_metrics_applicable)
                self.assertEqual((ledger.n_scalar,ledger.sum_abs_delta,ledger.max_abs_delta),(0,0.0,0.0))
        self.assertEqual(COUNTS["transaction"],0)

    def test_04_zero_write_complete_pairs_not_dropped_actual_owned_bank100(self):
        states=[]
        for name,bank in self.banks.items():
            d=addon._checked_bank(bank,self.src)
            _,config,native,_=addon._inputs(self.futures[name],self.src)
            self.assertEqual(d.payload["route"],"COMPLETE_ORIGINAL_BANK")
            self.assertEqual(d.payload["native_bank_rollout_calls"],200)
            self.assertEqual(len(native.starts),2)
            self.assertEqual(d.payload["source_configuration_not_reused_as_bank_faults"],config.configuration)
            self.assertEqual(d.payload["shared_locked_template"]["grid"],list(range(466)))
            self.assertIsNone(d.payload["shared_locked_template"]["seed"])
            self.assertFalse(d.payload["curve_created"])
            self.assertIsNone(d.payload["primary_Collateral"])
            for role,rows,mean,state,pinned in zip(d.payload["ordered_arms"],d.traces,d.means,d.starts,native.starts):
                self.assertTrue(all(state is not x for x in states));states.append(state)
                self.assertIsNot(state,pinned)
                self.assertEqual(base._stores(state),base._stores(pinned))
                self.assertEqual(len(rows),100)
                self.assertEqual([r["scene"] for r in role["ordered_scenes"]],[list(s.key) for s in native.template["sample"]])
                total=0.0
                for scene,trace,wire in zip(native.template["sample"],rows,role["ordered_scenes"]):
                    total+=trace.return_value
                    self.assertEqual(trace.mask,K.FaultMask())
                    self.assertFalse(trace.interventions.members)
                    self.assertEqual(trace.option_in_force,scene.base_option)
                    self.assertEqual(wire["raw"],base.factual._trace_payload(trace,scene))
                self.assertEqual(mean,total/100)

    def test_05_absent_alternative_not_missing_or_forged_CF_half_no_native(self):
        global CURRENT
        CURRENT="NO_ALT_ENVELOPE_ERROR_GATES"
        before=COUNTS.copy()
        _,sd=owner._checked_source(self.src)
        pd=owner._checked_pair(self.pairs["DualReturnWrite"],self.src)[3]
        addresses=pd.projected.addresses
        envelope=ENVELOPE_OBJECTS[-1];a=addresses[0];rec=envelope[a]
        rows=base.learner_rows(sd.trace,sd.scene.kappa,sd.scene.phase)
        wrong=({},{a:replace(rec,g_cf=0.0)},
            {a:replace(rec,a_plus=K.WAIT,g_cf=0.0)})
        for candidate in wrong:
            with self.assertRaises(base.ready.ProtocolError):
                base.native_cf.validate_counterfactual_envelope(addresses,candidate,rows,sol=sd.solution,episode=sd.episode)
        expected=before.copy();expected["validator"]+=3
        self.assertEqual(COUNTS,expected)
        emit("NO_ALT_ENVELOPE_ERROR_GATES",{"counts_before":before,"counts_after":COUNTS.copy(),
            "missing_record_not_None":True,"None_with_CF_half_refused":True,
            "legal_but_false_alternative_refused":True,"native_counts_unchanged_except_validator":True})

    def test_06_zero_write_status_equal_content_alias_and_once_not_bypassed(self):
        global CURRENT
        CURRENT="ZERO_WRITE_OWNERSHIP_ERROR_GATES"
        before=COUNTS.copy()
        pair=self.pairs["DualReturnWrite"]
        _,_,wrapper,pd=owner._checked_pair(pair,self.src)
        original=pd.results[1]
        receipt=replace(original.ledger.receipts[0],status=base.EVALUABLE_NOOP)
        ledger=replace(original.ledger,receipts=(receipt,))
        try:
            base._PAIRS[wrapper.native]=replace(pd,
                results=(pd.results[0],replace(original,ledger=ledger)))
            with self.assertRaises(base.ready.ProtocolError):owner.pair_audit(pair,self.src)
        finally:base._PAIRS[wrapper.native]=pd
        fd,_=owner._checked_future(self.futures["DualReturnWrite"],self.src)
        config=owner._checked_source(self.src)[0]
        saved=base._FUTURES[fd.native]
        try:
            base._FUTURES[fd.native]=replace(saved,starts=(saved.starts[0],saved.starts[0]))
            with self.assertRaises(base.ready.ProtocolError):addon.bank_audit(self.banks["DualReturnWrite"],self.src)
        finally:base._FUTURES[fd.native]=saved
        for name,pair in self.pairs.items():
            duplicate=owner.prepare_future_inputs(pair,self.src)
            with self.assertRaises(base.ready.ProtocolError):addon.measure_bank(duplicate,self.src)
        owner.pair_audit(self.pairs["DualReturnWrite"],self.src)
        addon.bank_audit(self.banks["DualReturnWrite"],self.src)
        self.assertEqual(COUNTS,before)
        emit("ZERO_WRITE_OWNERSHIP_ERROR_GATES",{"counts_before":before,"counts_after":COUNTS.copy(),
            "NoAlt_status_not_laundered_to_NOOP":True,"equal_full_content_role_alias_refused":True,
            "zero_write_pair_still_consumed_once":True,"exact_restore":True})

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
                                                      ZeroAlternativeBankTests.reference),
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
        result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ZeroAlternativeBankTests))
        emit("FINAL",{"tests":result.testsRun,"failures":len(result.failures),"errors":len(result.errors),
            "skipped":len(result.skipped),"counts":COUNTS,"budget":LIMITS,
            "output_bytes_before_footer":OUTPUT_BYTES,"training":0,"DP":0,"keys_allocated":False,
            "native_calibration":False,"collector":False,"old_fixture_reruns":0,
            "scientific_PASS":False,"research_complete":False})
        sys.exit(0 if result.wasSuccessful() and not COUNTS["blocked"] else 1)
