"""Finite new direct-Oracle conformance and SERIAL challenges; not calibration."""
from contextlib import ExitStack
from dataclasses import replace
import ast
import hashlib
import json
from pathlib import Path
import sys
import traceback
import unittest
from unittest.mock import patch

PREP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PREP))
import oracle_mainline_v74 as addon
from rfl_rebuild.b2 import training
from rfl_rebuild.learner.store import DECISION, Q, DecisionAddress, Edit, QAddress
from rfl_rebuild.solve import dp

COUNTS = {"rollout": 0, "step": 0, "transaction": 0, "B1": 0, "blocked": 0}
LIMITS = {"rollout": 256, "step": 4096, "transaction": 32, "B1": 16}
CURRENT = "NOT_STARTED"
OUTPUT_BYTES = 0
def emit(tag, value):
    global OUTPUT_BYTES
    line = tag + "=" + json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    OUTPUT_BYTES += len((line + "\n").encode("utf-8"))
    if OUTPUT_BYTES > 5000000:
        raise RuntimeError("fixed output budget exceeded; preserve partial, no retry")
    print(line, flush=True)
def count(name):
    COUNTS[name] += 1
    if COUNTS[name] > LIMITS[name]:
        raise RuntimeError("fixed native conformance budget exceeded: " + name)
def blocked(*a, **kw):
    COUNTS["blocked"] += 1
    raise AssertionError("no DP/key/RNG/future training/collector/calibration allowed")

def reference_from_stored():
    path = PREP / "grammar_catalog_v31/evidence/stdout.log"
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "d0aafb6dc20b1cc0c872ac4c48497d94feb707ffe14448bd1c2f3ddd1bbb467b"
    rows = {}
    for line in raw.splitlines():
        if line.startswith(b"DECISION_CONTEXT="):
            v = json.loads(line.split(b"=", 1)[1])
            x,y,t,k,p,z,m = v["context"]
            key = (addon.K.State(x,y,t,k,p),z,m)
            assert key not in rows
            rows[key] = {a: float.fromhex(h) for a,h in v["q_row_hex"]}
    assert len(rows) == 13824
    return addon.QReferenceView(rows)

def fixture(reference, architecture):
    state = addon.LearnerPersistentState()
    edits = []
    for t in range(12):
        s = addon.K.State(0,2,t,1,1)
        if architecture == "D_Q":
            edits.append(Edit(Q, QAddress(s,2,0,4), max(reference.row(s,2,0).values()) + 1.0))
        else:
            edits.append(Edit(DECISION, DecisionAddress(s,2,0),4))
    # Fixed unconsulted kappa0 sentinel, source identity and preservation only.
    s = addon.K.State(0,2,0,0,1)
    if architecture == "D_Q":
        edits.append(Edit(Q, QAddress(s,2,0,4), max(reference.row(s,2,0).values()) + 2.0))
    else:
        edits.append(Edit(DECISION, DecisionAddress(s,2,0),4))
    state.apply_transaction(edits,q_reference=reference)
    return state

class NewTierIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global CURRENT
        cls.reference = reference_from_stored()
        cls.healthy = addon.ready.read_json(PREP / "healthy_reference_candidate.json")
        cls.scene = addon.EvaluationScene(1,1,0,0,2)
        cls.sources = {}
        for arch in ("D_Q","D_patch"):
            CURRENT = arch
            state = fixture(cls.reference, arch)
            emit("SOURCE_INPUT", {"label":CURRENT,"scene":list(cls.scene.key),"regime":"P",
                "full_pre":addon._store_wire(state),"q_reference":cls.reference.digest(),
                "counterfactual":arch=="D_Q"})
            src = addon.capture_oracle_source(state,scene=cls.scene,regime="P",
                q_reference=cls.reference,healthy_reference=cls.healthy,counterfactual=arch=="D_Q")
            cls.sources[arch] = src
            emit("OWNED_SOURCE", {"label":CURRENT,"payload":addon._SOURCES[src].payload,
                "seal":addon._SOURCES[src].seal})
        CURRENT = "T_HEALTHY"
        cls.success = addon.capture_oracle_source(addon.LearnerPersistentState(),
            scene=cls.scene,regime="T",q_reference=cls.reference,healthy_reference=cls.healthy)
        emit("OWNED_SOURCE",{"label":CURRENT,"payload":addon._SOURCES[cls.success].payload,
            "seal":addon._SOURCES[cls.success].seal})
        cls.pairs = {}
        cls.futures = {}
        for arch,tier,name in (
            ("D_Q",addon.Tier.L2_COUNTERFACTUAL,"CounterfactualReturnWrite"),
            ("D_Q",addon.Tier.L2_COUNTERFACTUAL,"DualReturnWrite"),
            ("D_patch",addon.Tier.L1_CORRECTIVE,"SetAlternative"),
            ("D_patch",addon.Tier.L3_ORACLE,"LocalOracleRestore")):
            CURRENT = arch + "/" + tier.name + "/" + name
            src = cls.sources[arch]
            p = addon.run_oracle_pair(src,architecture=arch,tier=tier,law_name=name)
            cls.pairs[name] = p
            f = addon.prepare_future_inputs(p,src)
            cls.futures[name] = f
            emit("NEW_PAIR",addon.pair_audit(p,src))
            emit("OWNED_FUTURE",addon.future_inputs_audit(f,src))

    def test_01_new_tiers_whole_owners_receipts_and_sentinel(self):
        for name,p in self.pairs.items():
            d = addon._PAIRS[p]; src = self.sources[d.architecture]; sd=addon._SOURCES[src]
            audit=addon.pair_audit(p,src)["payload"]
            self.assertEqual(audit["native_B1_arm_calls"],2)
            self.assertGreater(len(d.projected.addresses),1)
            self.assertEqual(set(d.projected.whole_units),set(sd.truth["Gamma_P_star"]))
            for arm in audit["all_owner_receipts"]:
                self.assertEqual(len(arm["ordered_receipts"]),len(d.projected.addresses))
            for clone in d.clones:
                view=getattr(clone,addon._VIEW[d.architecture])
                pre=getattr(sd.pre,addon._VIEW[d.architecture])
                self.assertEqual({a:v for a,v in view.items() if a.state.kappa==0},
                                 {a:v for a,v in pre.items() if a.state.kappa==0})

    def test_02_owned_CF_same_complete_configuration(self):
        sd=addon._checked_source(self.sources["D_Q"])
        self.assertIs(sd.episode.factual_trace,sd.trace)
        self.assertEqual(addon._stores(sd.episode.snapshot_pre),addon._stores(sd.pre))
        self.assertIs(sd.solution.q,sd.reference.rows)
        self.assertEqual(sd.episode.reward_mode,"A")
        self.assertFalse(sd.episode.interventions.members)

    def test_03_owned_future_shared_template_independent_all_stores(self):
        for name,f in self.futures.items():
            pd=addon._PAIRS[self.pairs[name]];src=self.sources[pd.architecture]
            fd=addon._checked_future(f,src)
            self.assertEqual(fd.template["grid"],tuple(range(466)))
            self.assertEqual(len(fd.template["sample"]),100)
            for i,role in enumerate(("reference","treatment")):
                c=addon.clone_future_start(f,src,role=role)
                self.assertEqual(addon._stores(c),addon._stores(pd.clones[i]))
                self.assertIsNot(c,fd.starts[i])
                self.assertIsNot(c,pd.clones[i])

    def test_04_empty_cell_no_fake_receipt_or_future(self):
        src=self.sources["D_Q"]
        p=addon.run_oracle_pair(src,architecture="X",tier=addon.Tier.L0_FACTUAL,law_name="X_id")
        self.assertEqual(addon.pair_audit(p,src)["payload"]["native_B1_arm_calls"],0)
        self.assertTrue(addon._PAIRS[p].projected.residual_units)
        f=addon.prepare_future_inputs(p,src)
        self.assertEqual(addon._checked_future(f,src).starts,())
        with self.assertRaises(addon.ready.ProtocolError):
            addon.clone_future_start(f,src,role="reference")
        emit("EMPTY_CELL",addon.pair_audit(p,src))

    def test_05_T_success_no_reflection(self):
        src=self.success
        self.assertEqual(addon._checked_source(src).payload["route"],"SUCCESS_NO_REFLECTION")
        p=addon.run_oracle_pair(src,architecture="D_patch",tier=addon.Tier.L1_CORRECTIVE,law_name="SetAlternative")
        self.assertEqual(addon._PAIRS[p].results,())
        self.assertEqual(addon._checked_future(addon.prepare_future_inputs(p,src),src).starts,())

    def test_06_wrong_source_and_role_refused(self):
        p=self.pairs["DualReturnWrite"]
        with self.assertRaises(addon.ready.ProtocolError):
            addon.pair_audit(p,self.sources["D_patch"])
        for role in (True,"first","T","D_Q"):
            with self.assertRaises(addon.ready.ProtocolError):
                addon.clone_immediate_post(p,self.sources["D_Q"],role=role)

    def test_07_general_patch_source_cannot_be_L2_or_CF(self):
        src=self.sources["D_patch"]
        with self.assertRaises(addon.ready.ProtocolError):
            addon.run_oracle_pair(src,architecture="D_Q",tier=addon.Tier.L2_COUNTERFACTUAL,law_name="DualReturnWrite")
        sd=addon._SOURCES[src];before=COUNTS["rollout"]
        with self.assertRaises(addon.ready.ProtocolError):
            addon.capture_oracle_source(sd.pre,scene=self.scene,regime="P",q_reference=self.reference,
                healthy_reference=self.healthy,counterfactual=True)
        self.assertEqual(COUNTS["rollout"],before)

    def mutate_pair(self,transform):
        p=self.pairs["DualReturnWrite"];src=self.sources["D_Q"];saved=addon._PAIRS[p]
        try:
            addon._PAIRS[p]=transform(saved)
            with self.assertRaises(addon.ready.ProtocolError):
                addon.pair_audit(p,src)
        finally:
            addon._PAIRS[p]=saved
        addon.pair_audit(p,src)

    def test_08_partial_receipt_population_refused(self):
        self.mutate_pair(lambda d: replace(d,results=(d.results[0],
            replace(d.results[1],ledger=replace(d.results[1].ledger,receipts=d.results[1].ledger.receipts[:-1])))))

    def test_09_independent_scalar_catches_plausible_false_count(self):
        self.mutate_pair(lambda d: replace(d,results=(d.results[0],
            replace(d.results[1],ledger=replace(d.results[1].ledger,n_scalar=d.results[1].ledger.n_scalar+1)))))

    def test_10_future_alias_and_role_swap_refused(self):
        f=self.futures["DualReturnWrite"];src=self.sources["D_Q"];saved=addon._FUTURES[f]
        for starts in ((saved.starts[0],saved.starts[0]),saved.starts[::-1]):
            try:
                addon._FUTURES[f]=replace(saved,starts=starts)
                with self.assertRaises(addon.ready.ProtocolError):
                    addon.future_inputs_audit(f,src)
            finally:
                addon._FUTURES[f]=saved
        addon.future_inputs_audit(f,src)

    def test_11_source_payload_tamper_refused_and_restored(self):
        src=self.sources["D_Q"];d=addon._SOURCES[src];old=d.payload["route"]
        try:
            d.payload["route"]="SUCCESS_NO_REFLECTION"
            with self.assertRaises(addon.ready.ProtocolError):
                addon._checked_source(src)
        finally:
            d.payload["route"]=old
        addon._checked_source(src)

    def test_12_failure_after_first_original_arm_no_handle_or_retry(self):
        global CURRENT
        CURRENT="D_Q/EXPECTED_SECOND_ARM_FAILURE"
        src=self.sources["D_Q"];before=len(addon._PAIRS);calls=[]
        original=addon._apply_original
        def second_fails(law,*a,**kw):
            calls.append(law.name)
            if len(calls)==2:
                raise RuntimeError("PREDECLARED_SERIAL_SECOND_ARM_FAILURE")
            return original(law,*a,**kw)
        with patch.object(addon,"_apply_original",second_fails):
            try:
                addon.run_oracle_pair(src,architecture="D_Q",tier=addon.Tier.L3_ORACLE,law_name="LocalOracleRestore")
                self.fail("partial pair issued")
            except RuntimeError as exc:
                self.assertEqual(str(exc),"PREDECLARED_SERIAL_SECOND_ARM_FAILURE")
                emit("EXPECTED_FAILURE_PRESERVED",{"error":str(exc),"traceback":traceback.format_exc(),
                    "actual_original_arms_before_failure":1,"pair_issued":False,"retry":False})
        self.assertEqual(len(addon._PAIRS),before)
        before_calls=COUNTS["B1"]
        with self.assertRaises(addon.ready.ProtocolError):
            addon.run_oracle_pair(src,architecture="D_Q",tier=addon.Tier.L3_ORACLE,law_name="LocalOracleRestore")
        self.assertEqual(COUNTS["B1"],before_calls)
        self.assertEqual(calls,["NoWrite","LocalOracleRestore"])

    def test_13_all_cell_receipts_role_partial_or_counter_tamper_refused(self):
        for name,p in self.pairs.items():
            d=addon._PAIRS[p];src=self.sources[d.architecture]
            try:
                addon._PAIRS[p]=replace(d,results=d.results[:1],clones=d.clones[:1])
                with self.assertRaises(addon.ready.ProtocolError):
                    addon.pair_audit(p,src)
            finally:
                addon._PAIRS[p]=d

    def test_14_new_registration_no_original_mutation(self):
        for a,t,n in (("D_Q",addon.Tier.L2_COUNTERFACTUAL,"DualReturnWrite"),
                      ("D_patch",addon.Tier.L1_CORRECTIVE,"SetAlternative"),
                      ("D_patch",addon.Tier.L3_ORACLE,"LocalOracleRestore")):
            ref,treat=addon._registered(a,t,n)
            self.assertIs(ref.tier,treat.tier)
        self.assertEqual(addon.laws.LAWS,(addon.laws.NoWrite,addon.laws.DeleteFactualPatch,
            addon.laws.SetAlternative,addon.laws.LocalOracleRestore))

if __name__=="__main__":
    with ExitStack() as stack:
        original_rollout=addon.K.rollout;original_step=addon.K.step
        original_tx=addon.LearnerPersistentState.apply_transaction;original_B1=addon.native_b1._run
        def rollout(*a,**kw):
            count("rollout")
            trace=original_rollout(*a,**kw)
            scene=addon.EvaluationScene(kw["kappa"],kw["tape"].phase,kw["tape"].error_flag,
                kw["tape"].cause_rank,kw.get("base_option",1))
            emit("NATIVE_RAW_BEFORE_CALLER_TRUTH",{"label":CURRENT,"ordinal":COUNTS["rollout"],
                "scene":list(scene.key),"mask":addon.factual._mask_payload(kw.get("mask",addon.K.FaultMask()),
                    kw.get("option_fault")),"interventions":[repr(x) for x in kw.get("interventions",addon.K.InterventionSet()).members],
                "raw":addon.factual._trace_payload(trace,scene),"outcome":trace.outcome})
            return trace
        def step(*a,**kw):
            count("step");return original_step(*a,**kw)
        def transaction(state,edits,*a,**kw):
            count("transaction");pre=addon._store_wire(state)
            emit("TX_BEGIN",{"label":CURRENT,"ordinal":COUNTS["transaction"],"pre":pre,"edits":[repr(x) for x in edits]})
            result=original_tx(state,edits,*a,**kw)
            emit("TX_END",{"label":CURRENT,"ordinal":COUNTS["transaction"],"post":addon._store_wire(state)})
            return result
        def B1(law,tier,pre,addresses,targets,spec,*a,**kw):
            count("B1")
            emit("B1_BEGIN",{"label":CURRENT,"ordinal":COUNTS["B1"],"law":law.name,"tier":tier.name,
                "addresses":[spec.domain.canonical(x) for x in addresses],"pre":addon._store_wire(pre)})
            result=original_B1(law,tier,pre,addresses,targets,spec,*a,**kw)
            emit("B1_END",{"label":CURRENT,"ordinal":COUNTS["B1"],"post":addon._store_wire(pre),
                "ledger":json.loads(result.ledger.canonical())})
            return result
        for obj,name,fn in ((addon.K,"rollout",rollout),(addon.K,"step",step),
            (addon.LearnerPersistentState,"apply_transaction",transaction),(addon.native_b1,"_run",B1)):
            stack.enter_context(patch.object(obj,name,fn))
        for obj,name in ((training,"train_curve"),(training,"episode_rollout"),(training,"key"),
            (training.ExogenousEpisode,"derive"),(dp,"solve_reference"),(addon.ready,"build_reference"),
            (addon.ready,"solve_reference"),(addon.K.SemanticTape,"sample")):
            stack.enter_context(patch.object(obj,name,blocked))
        import random
        stack.enter_context(patch.object(random,"Random",blocked))
        result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(NewTierIntegrationTests))
        emit("FINAL",{"role":"FINITE_NEW_INTERFACE_NATIVE_CONFORMANCE_NOT_CALIBRATION_OR_SCIENCE",
            "tests":result.testsRun,"failures":len(result.failures),"errors":len(result.errors),"skipped":len(result.skipped),
            "actual_native_counts":COUNTS,"budget":LIMITS,"output_bytes_before_footer":OUTPUT_BYTES,
            "DP":0,"keys_allocated":False,"future_training":0,"collector":False,"calibration":False,
            "scientific_PASS":False,"research_complete":False,"old_fixture_reruns":0})
        sys.exit(0 if result.wasSuccessful() and not COUNTS["blocked"] else 1)
