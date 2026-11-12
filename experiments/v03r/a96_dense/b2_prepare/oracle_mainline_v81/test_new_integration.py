"""Four new SERIAL original L2 tied-optimal factual-with-alternative checks."""
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
COUNTS={"rollout":0,"step":0,"transaction":0,"B1":0,"CF_replay":0,"validator":0,"plan":0,"mean":0,"mean_completed":0,"blocked":0}
LIMITS={"rollout":500,"step":6000,"transaction":2,"B1":4,"CF_replay":16,"validator":12,"plan":4,"mean":4}
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
class TiedOptimalBankTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global CURRENT
        cls.reference=reference_from_stored()
        cls.healthy=base.ready.read_json(PREP/"healthy_reference_candidate.json")
        start=cls.reference.row(K.State(0,2,0,0,3),1,0)
        cls.row=cls.reference.row(K.State(1,2,1,0,3),1,0)
        assert max(start,key=lambda a:(start[a],-a))==K.RIGHT
        assert max(cls.row,key=lambda a:(cls.row[a],-a))==K.UP
        assert sorted(a for a,v in cls.row.items() if v>=max(cls.row.values())-1e-12)==[K.UP,K.RIGHT]
        assert cls.row[K.DOWN]<max(cls.row.values())
        cls.mask=K.FaultMask(decision=K.DecisionOverride(1,K.RIGHT),
            plant=K.PlantFault(1,K.WAIT),trap=K.Trap((1,2),1))
        CURRENT="T_L2_TIED_OPTIMAL_WITH_ALTERNATIVE"
        scene=base.EvaluationScene(0,3,0,32,1)
        emit("SOURCE_INPUT",{"label":CURRENT,"pre":base._store_wire(base.LearnerPersistentState()),
            "regime":"T","counterfactual":True,
            "configuration":owner._configuration(scene,cls.mask,None,cls.reference),
            "original_full_optimal_actions":[K.UP,K.RIGHT],
            "original_factual_action":K.RIGHT,"original_shared_alternative":K.UP,
            "original_actual_row":[[a,v.hex()] for a,v in sorted(cls.row.items())]})
        cls.src=owner.capture_source(base.LearnerPersistentState(),scene=scene,regime="T",
            q_reference=cls.reference,healthy_reference=cls.healthy,mask=cls.mask,
            option_fault=None,counterfactual=True)
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

    def test_01_factual_tied_optimal_original_T_credit_not_P_filter(self):
        config,sd=owner._checked_source(self.src)
        self.assertEqual(sd.trace.outcome,K.Outcome.TRAP)
        self.assertEqual(sd.truth["Z_fire"],[False,True,False,True,True])
        self.assertEqual(set(sd.truth["Gamma_T_star"]),{"Decision_1","ExternalPlant","Unknown/NoWrite"})
        self.assertIsNone(sd.truth["Gamma_P_star"]);self.assertIsNone(sd.truth["J_L"])
        self.assertEqual(len(sd.truth["R_mech"]),3)
        self.assertIsNone(config.option_fault)
        self.assertIs(sd.episode.factual_trace,sd.trace)
        raw=base.factual._trace_payload(sd.trace,sd.scene)
        self.assertEqual(len(raw),2)
        self.assertEqual(raw[1]["pre_state"],[1,2,1,0,3])
        self.assertEqual((raw[1]["z"],raw[1]["m"]),(1,0))
        self.assertEqual((raw[1]["a_cmd"],raw[1]["u"],raw[1]["a_realized"]),(K.RIGHT,K.RIGHT,K.WAIT))
        self.assertEqual(raw[1]["post_state"],[1,2,2,0,3])

    def test_02_full_optimal_minus_factual_original_replays_and_envelopes(self):
        _,sd=owner._checked_source(self.src)
        raw=base.factual._trace_payload(sd.trace,sd.scene)
        self.assertEqual((len(ENVELOPES),len(VALIDATIONS),len(REPLAYS)),(4,8,13))
        self.assertIsNone(REPLAYS[0]["requested_t"])
        self.assertEqual(REPLAYS[0]["raw"],raw)
        for replay in REPLAYS[1:]:
            self.assertEqual((replay["requested_t"],replay["requested_action"]),(1,K.UP))
            self.assertEqual(replay["configuration"],REPLAYS[0]["configuration"])
            self.assertEqual(replay["raw"][:1],raw[:1])
            self.assertEqual(len(replay["actual_interventions"]),1)
            self.assertEqual((replay["actual_interventions"][0]["kind"],replay["actual_interventions"][0]["t"]),("decision",1))
            self.assertEqual((replay["raw"][1]["a_cmd"],replay["raw"][1]["u"],replay["raw"][1]["a_realized"]),(K.UP,K.UP,K.WAIT))
            self.assertEqual(reverse_fold(replay["raw"],1),-1.02)
        for envelope in ENVELOPES:
            self.assertEqual(len(envelope["targets"]),1)
            r=envelope["targets"][0]
            self.assertEqual((r["a_factual"],r["a_plus"]),(K.RIGHT,K.UP))
            self.assertEqual((float.fromhex(r["g_factual_hex"]),float.fromhex(r["g_cf_hex"])),(-1.02,-1.02))

    def test_03_complete_original_plans_Q_receipts_and_owned_bank_roles(self):
        self.assertEqual(len(PLANS),4)
        for plan in PLANS:
            self.assertEqual(len(plan["plans"]),1)
            self.assertIsNone(plan["plans"][0]["status"])
            self.assertIsNone(plan["plans"][0]["row_op"])
            self.assertEqual(len(plan["plans"][0]["edits"]),
                0 if plan["law"]=="NoWrite" else 1 if plan["law"]=="CounterfactualReturnWrite" else 2)
        _,sd=owner._checked_source(self.src)
        states=[sd.pre]
        for name,pair in self.pairs.items():
            _,_,_,pd=owner._checked_pair(pair,self.src)
            self.assertEqual(pd.projected.cell_units,("Decision_1",))
            self.assertEqual(set(pd.projected.residual_units),{"ExternalPlant","Unknown/NoWrite"})
            for i,(state,result) in enumerate(zip(pd.clones,pd.results)):
                self.assertTrue(all(state is not x for x in states));states.append(state)
                stores=base._store_wire(state)
                self.assertEqual((stores["D"],stores["P"],stores["X"]),([],[],[]))
                ledger=result.ledger
                self.assertEqual(len(ledger.receipts),1)
                self.assertEqual(ledger.receipts[0].status,base.EVALUABLE_NOOP if i==0 else base.APPLIED)
                self.assertEqual(ledger.receipts[0].store_changed,i==1)
                self.assertTrue(ledger.scalar_metrics_applicable)
                expected={} if i==0 else {K.UP:-1.02}
                if i==1 and name=="DualReturnWrite":expected[K.RIGHT]=-1.02
                self.assertEqual({a.a:v for a,v in state.q_overrides.items()},expected)
                self.assertEqual(len(stores["Q"]),len(expected))
                delta=[abs(v-self.row[a]) for a,v in expected.items()]
                self.assertEqual((ledger.n_scalar,ledger.sum_abs_delta,ledger.max_abs_delta),
                    (len(delta),math.fsum(delta),max(delta,default=0.0)))
            bank=addon._checked_bank(self.banks[name],self.src)
            _,config,native,_=addon._inputs(self.futures[name],self.src)
            self.assertEqual(bank.payload["route"],"COMPLETE_ORIGINAL_BANK")
            self.assertEqual(bank.payload["native_bank_rollout_calls"],200)
            self.assertEqual(bank.payload["source_configuration_not_reused_as_bank_faults"],config.configuration)
            self.assertEqual(bank.payload["shared_locked_template"]["grid"],list(range(466)))
            self.assertIsNone(bank.payload["shared_locked_template"]["seed"])
            self.assertFalse(bank.payload["curve_created"]);self.assertIsNone(bank.payload["primary_Collateral"])
            self.assertEqual(len(native.starts),2)
            for role,rows,mean,state,pinned in zip(bank.payload["ordered_arms"],bank.traces,bank.means,bank.starts,native.starts):
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
        self.assertEqual(COUNTS["transaction"],2)

    def test_04_tied_optimal_false_absence_factual_or_nonoptimal_alternative_refused(self):
        global CURRENT
        CURRENT="TIED_OPTIMAL_ENVELOPE_ERROR_GATES"
        before=COUNTS.copy()
        _,sd=owner._checked_source(self.src)
        pd=owner._checked_pair(self.pairs["DualReturnWrite"],self.src)[3]
        addresses=pd.projected.addresses
        envelope=ENVELOPE_OBJECTS[-1];a=addresses[0];rec=envelope[a]
        rows=base.learner_rows(sd.trace,sd.scene.kappa,sd.scene.phase)
        wrong=({a:replace(rec,a_plus=None,g_cf=None)},
            {a:replace(rec,a_plus=K.RIGHT)},
            {a:replace(rec,a_plus=K.DOWN)})
        for candidate in wrong:
            with self.assertRaises(base.ready.ProtocolError):
                base.native_cf.validate_counterfactual_envelope(addresses,candidate,rows,sol=sd.solution,episode=sd.episode)
        expected=before.copy();expected["validator"]+=3
        self.assertEqual(COUNTS,expected)
        emit("TIED_OPTIMAL_ENVELOPE_ERROR_GATES",{"counts_before":before,"counts_after":COUNTS.copy(),
            "false_absence_refused":True,"factual_as_alternative_refused":True,
            "legal_nonoptimal_alternative_refused":True,"native_counts_unchanged_except_validator":True})

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
                                                      TiedOptimalBankTests.reference),
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
        result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TiedOptimalBankTests))
        emit("FINAL",{"tests":result.testsRun,"failures":len(result.failures),"errors":len(result.errors),
            "skipped":len(result.skipped),"counts":COUNTS,"budget":LIMITS,
            "output_bytes_before_footer":OUTPUT_BYTES,"training":0,"DP":0,"keys_allocated":False,
            "native_calibration":False,"collector":False,"old_fixture_reruns":0,
            "scientific_PASS":False,"research_complete":False})
        sys.exit(0 if result.wasSuccessful() and not COUNTS["blocked"] else 1)
