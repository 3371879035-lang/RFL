"""Fresh finite seedless tests for the v90 revision, not old fixture retries."""
from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path[:0] = [str(HERE), str(ROOT / "src")]
import adaptive_training as A
from rfl_rebuild.b2 import environment, training as T
from rfl_rebuild.env import kernel as K
from rfl_rebuild.learner.reference import QReferenceView
from rfl_rebuild.learner.store import (LearnerPersistentState, DecisionAddress,
    QAddress, Edit, DECISION, PROCESS, CONTROLLER, Q, LearnerStateError)

CONTRACT = json.loads((HERE / "contract.json").read_bytes())
COUNTS = Counter()
START = time.monotonic()


def emit(tag, payload):
    print(json.dumps({"tag": tag, "payload": A.wire(payload)}, sort_keys=True,
                     separators=(",", ":")), flush=True)


def profile(frame, event, arg):
    if event != "call":
        return
    code = frame.f_code
    name = code.co_name
    path = code.co_filename.replace("\\", "/")
    if path.endswith("rfl_rebuild/env/kernel.py") and name in ("rollout", "step"):
        COUNTS[name] += 1
        if COUNTS[name] > CONTRACT["budget"][name]:
            raise RuntimeError("prospective native budget exceeded: " + name)
    if path.endswith("rfl_rebuild/learner/store.py") and name == "apply_transaction":
        COUNTS["transaction"] += 1
        if COUNTS["transaction"] > CONTRACT["budget"]["transaction"]:
            raise RuntimeError("transaction budget exceeded")
    if path.endswith("rfl_rebuild/b2/training.py") and name == "sweep_edits":
        COUNTS["sweep"] += 1
    if path.endswith("adaptive_training.py") and name in ("train_episode", "evaluate"):
        COUNTS[name] += 1
    forbidden = ((path.endswith("rfl_rebuild/b2/training.py") and
                  name in ("train_curve", "derive", "key", "mix", "pre_level")) or
                 (path.endswith("rfl_rebuild/env/kernel.py") and name == "sample") or
                 (path.endswith("rfl_rebuild/solve/dp.py") and name == "solve_reference") or
                 (path.endswith("random.py") and name in ("__init__", "random", "randrange")))
    if forbidden:
        COUNTS["forbidden"] += 1
        raise RuntimeError("forbidden formal/key/RNG/DP entry: " + name)
    if time.monotonic() - START > CONTRACT["budget"]["seconds"]:
        raise RuntimeError("wall budget exceeded; no retry")


def reference():
    p = ROOT / CONTRACT["reference_input"]["path"]
    raw = p.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == CONTRACT["reference_input"]["sha256"]
    rows = {}
    for line in raw.decode("utf-8").splitlines():
        if not line.startswith("DECISION_CONTEXT="):
            continue
        d = json.loads(line.split("=", 1)[1])
        x, y, t, kappa, phi, z, m = d["context"]
        rows[K.State(x, y, t, kappa, phi), z, m] = {
            a: float.fromhex(v) for a, v in d["q_row_hex"]}
    assert len(rows) == 13824
    ref = QReferenceView(rows, name="exact-stored-v31-not-recomputed")
    assert ref.digest() == CONTRACT["reference_input"]["q_digest"]
    return ref


def episode(label, *, explore=False, reject=False, proposal=0, rank=53):
    return A.ScriptedEpisode(label, 0, proposal, K.SemanticTape(2, 0, rank),
        (0 if explore else T.M64,) * K.HORIZON,
        ((T.M64, 1) if reject else (1,),) * K.HORIZON)


def source(ref, mode, *, process=True):
    s = LearnerPersistentState()
    z = 1
    owner = DecisionAddress(K.State(1, 1, 0, 0, 2), z, 0)
    sentinel = DecisionAddress(K.State(1, 1, 0, 1, 2), z, 0)
    x = K.ControllerSite(K.State(1, 1, 0, 1, 2), K.WAIT)
    edits = [Edit(CONTROLLER, x, K.RIGHT)]
    if process:
        edits.append(Edit(PROCESS, 0, 1))
    for d in (owner, sentinel):
        if mode == "dq":
            value = max(ref.row(d.state, d.z, d.m).values()) + 1.0
            edits.append(Edit(Q, QAddress(d.state, d.z, d.m, K.WAIT), value))
        else:
            edits.append(Edit(DECISION, d, K.WAIT))
    s.apply_transaction(tuple(edits), q_reference=ref)
    return s, owner, sentinel


def oracle_edits(numeric, trace, e, ref):
    # Independently reconstruct pre-state/in-force and perform binary64 TD.
    work = dict(numeric.q_overrides)
    initial = K.State(1, 1, 0, e.kappa, e.tape.phase)
    control = K.ControlState(trace.option_in_force, 0)
    state, order = initial, []
    value = lambda q: work.get(q, ref.value(q))
    for result in trace.steps:
        q = QAddress(state, control.z, control.m, result.a_cmd)
        current = value(q)
        target = float(result.reward)
        if not result.terminal:
            allowed = K.option_actions(result.control.z, result.control, result.state)
            if allowed:
                target += max(value(QAddress(result.state, result.control.z, result.control.m, a))
                              for a in allowed)
        work[q] = current + 0.5 * (target - current)
        if q not in order:
            order.append(q)
        state, control = result.state, result.control
    return tuple(Edit(Q, q, float(work[q])) for q in order)


class Integration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ref = reference()

    def actor(self, mode="patch-adaptive", *, process=True, role="treatment"):
        s, owner, sentinel = source(self.ref, mode, process=process)
        actor = A.AdaptiveTrainingState(s, mode=mode, role=role,
            source_label="prospective-v90-fixed-input-not-science", reference=self.ref)
        return actor, s, owner, sentinel

    def test_01_full_initial_read_and_inforce(self):
        actor, source_state, owner, sentinel = self.actor()
        e = episode("initial-read")
        r = actor.evaluate(kappa=e.kappa, tape=e.tape, proposal=e.proposal)
        self.assertEqual(r["trace"]["option_in_force"], 1)
        self.assertEqual(r["trace"]["steps"][0]["a_cmd"], K.WAIT)
        self.assertEqual(A.stores(source_state), actor.payload()["immediate"])
        emit("INITIAL_FULL_READ", r)

    def test_02_patch_three_real_episodes_persist_values_and_learn_policy(self):
        actor, s, owner, sentinel = self.actor()
        before = actor.payload()
        for i in range(3):
            r = actor.train_episode(episode("patch-chronology-" + str(i), rank=53 + i))
            emit("PATCH_EPISODE", r)
            self.assertFalse(actor._current.q_overrides)
            self.assertEqual(actor._current.decision_overrides[sentinel], K.WAIT)
            self.assertEqual(actor.payload()["current"]["P"], before["current"]["P"])
            self.assertEqual(actor.payload()["current"]["X"], before["current"]["X"])
            self.assertEqual(A.stores(s), before["immediate"])
            emit("PATCH_CHECKPOINT", actor.evaluate(kappa=0,tape=K.SemanticTape(2,0,53+i),proposal=0))
        self.assertEqual(actor._completed, 3)
        self.assertNotEqual(actor._current.decision_overrides[owner], K.WAIT)

    def test_03_full_dq_differential_three_episodes(self):
        actor, s, owner, sentinel = self.actor("dq")
        legacy = s.clone()
        params = A.LearningParameters()
        for i in range(3):
            e = episode("dq-differential-"+str(i), explore=(i == 1), reject=(i == 1), rank=53+i)
            independent = legacy.clone()
            trace = T.episode_rollout(legacy,e,protocol=params,q_reference=self.ref)
            expected = oracle_edits(independent,trace,e,self.ref)
            edits = T.sweep_edits(legacy,trace,e,protocol=params,q_reference=self.ref)
            self.assertEqual(edits, expected)
            legacy.apply_transaction(edits,q_reference=self.ref)
            r = actor.train_episode(e,parameters=params)
            self.assertEqual(r["trace"],A.wire(trace))
            self.assertEqual(r["numeric_edits"],A.wire(expected))
            self.assertEqual(A.stores(legacy),actor.payload()["current"])
            self.assertIsNone(actor._values)
            actual = environment.learned_rollout(legacy,kappa=0,tape=e.tape,base_option=0,q_reference=self.ref)
            checkpoint = actor.evaluate(kappa=0,tape=e.tape,proposal=0)
            self.assertEqual(checkpoint["trace"],A.wire(actual))
            emit("DQ_ORIGINAL_DIFFERENTIAL", {"revised":r,"original_trace":A.wire(trace),
                "original_edits":A.wire(edits),"original_full_post":A.stores(legacy),
                "original_checkpoint_trace":A.wire(actual),"checkpoint":checkpoint})

    def test_04_exploration_not_shadowed_by_patch_and_rejection_coordinates(self):
        actor, s, owner, sentinel = self.actor()
        r = actor.train_episode(episode("outer-exploration", explore=True,reject=True),
                                parameters=A.LearningParameters(epsilon=Fraction(1,1)))
        self.assertNotEqual(r["trace"]["steps"][0]["a_cmd"],K.WAIT)
        self.assertEqual([d["i"] for d in r["draws"]],list(range(len(r["trace"]["steps"]))))
        self.assertTrue(all(d["explore"] for d in r["draws"]))
        emit("EXPLORATION",r)

    def test_05_eval_zero_draws_zero_writes_and_full_fingerprint(self):
        actor, *_ = self.actor()
        emit("WARMUP_EPISODE",actor.train_episode(episode("learn-before-eval")))
        before = actor.payload()
        r = actor.evaluate(kappa=0,tape=K.SemanticTape(2,0,54),proposal=0)
        self.assertEqual(actor.payload(),before)
        self.assertEqual(r["draws"],[])
        self.assertIsNotNone(r["before"]["learning_values"])
        emit("READONLY_EVAL",r)

    def test_06_protected_immediate_and_independent_roles(self):
        s, *_ = source(self.ref,"patch-adaptive")
        a = A.AdaptiveTrainingState(s,mode="patch-adaptive",role="reference",source_label="pair",reference=self.ref)
        b = A.AdaptiveTrainingState(s,mode="patch-adaptive",role="treatment",source_label="pair",reference=self.ref)
        before_b = b.payload()
        emit("ROLE_EPISODE",a.train_episode(episode("independent-role")))
        self.assertEqual(b.payload(),before_b)
        self.assertIsNot(a._current,b._current)
        self.assertIsNot(a._values,b._values)
        self.assertEqual(a.payload()["immediate"],b.payload()["immediate"])
        emit("INDEPENDENT_ROLES", {"a":a.payload(),"b":b.payload(),"source":A.stores(s)})

    def test_07_empty_patch_mode_stays_patch_and_maps_to_dq(self):
        empty = LearnerPersistentState()
        p = A.AdaptiveTrainingState(empty,mode="patch-adaptive",role="reference",source_label="empty",reference=self.ref)
        q = A.AdaptiveTrainingState(empty,mode="dq",role="treatment",source_label="empty",reference=self.ref)
        e = episode("empty-mode",proposal=1)
        rp,rq = p.train_episode(e),q.train_episode(e)
        self.assertEqual(rp["trace"],rq["trace"])
        self.assertEqual(rp["numeric_edits"],rq["numeric_edits"])
        self.assertEqual(A.stores(p._values)["Q"],A.stores(q._current)["Q"])
        self.assertEqual(p.mode,"patch-adaptive")
        emit("EMPTY_MODE_TRANSFER_NOT_F1",{"patch":rp,"dq":rq})

    def test_08_original_invalid_d_plus_q_guard_unchanged(self):
        s, owner, _ = source(self.ref,"patch-adaptive")
        s.apply_transaction((Edit(Q,QAddress(owner.state,owner.z,owner.m,K.WAIT),9.0),),q_reference=self.ref)
        with self.assertRaises(LearnerStateError):
            A.AdaptiveTrainingState(s,mode="patch-adaptive",role="reference",source_label="invalid",reference=self.ref)
        emit("ORIGINAL_GUARD_RETAINED",{"invalid_full_input":A.stores(s)})

    def test_09_incomplete_attempt_no_retry_no_numeric_or_actor_commit(self):
        actor, *_ = self.actor()
        e = A.ScriptedEpisode("planned-partial",0,0,K.SemanticTape(2,0,53),
                              (0,)*K.HORIZON,((T.M64,),)*K.HORIZON)
        before = actor.payload()
        try:
            actor.train_episode(e,parameters=A.LearningParameters(epsilon=Fraction(1,1)))
        except A.ProtocolError:
            error = traceback.format_exc()
        else:
            self.fail("planned draw exhaustion was not refused")
        after = actor.payload()
        self.assertEqual(before["current"],after["current"])
        self.assertEqual(before["learning_values"],after["learning_values"])
        self.assertEqual(after["completed_episodes"],0)
        counts_before = dict(COUNTS)
        with self.assertRaises(A.ProtocolError):
            actor.train_episode(e)
        self.assertEqual(COUNTS["rollout"],counts_before["rollout"])
        self.assertEqual(COUNTS["step"],counts_before["step"])
        emit("PLANNED_PARTIAL",{"before":before,"after":after,"complete_trace":None,
                                "completed_handle":False,"retry":False,"traceback":error,
                                "native_counts_before_retry_gate":counts_before,
                                "native_counts_after_retry_gate":dict(COUNTS)})

    def test_10_policy_improvement_is_not_numeric_td_gain(self):
        actor, *_ = self.actor(process=False)
        r = actor.train_episode(episode("zero-td-policy",proposal=1))
        emit("ZERO_TD_POLICY_DISTINCTION",r)
        self.assertEqual(r["after"]["learning_values"]["Q"],[])
        self.assertTrue(r["policy_improvement_edits"])
        self.assertFalse(r["scientific_qualification"])

    def test_11_rebinding_mode_source_or_reference_is_refused(self):
        actor, *_ = self.actor()
        counts_before = dict(COUNTS)
        with self.assertRaises(A.ProtocolError):
            environment.learned_rollout(actor,kappa=0,tape=K.SemanticTape(2,0,53),
                                        base_option=0,q_reference=self.ref)
        self.assertEqual(COUNTS["rollout"],counts_before.get("rollout",0))
        actor.mode = "dq"
        with self.assertRaises(A.ProtocolError):
            actor.payload()
        emit("REBINDING_REFUSED",{"changed_field":"mode"})


if __name__ == "__main__":
    sys.setprofile(profile)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Integration)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.setprofile(None)
    emit("RESULT",{"tests":result.testsRun,"failures":len(result.failures),
        "errors":len(result.errors),"skips":len(result.skipped),"counts":dict(COUNTS),
        "elapsed_seconds":time.monotonic()-START,"scientific_PASS":False,
        "qualification_migrated":False,"formal_training_or_collection":False})
    raise SystemExit(0 if result.wasSuccessful() else 1)
