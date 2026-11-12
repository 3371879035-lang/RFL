"""First finite, actual-task integration run; no old workload or tests imported."""
from dataclasses import replace
from fractions import Fraction
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import traceback
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PREP = ROOT / 'experiments/v03r/a96_dense/b2_prepare'
sys.path[:0] = [str(ROOT/'src'), str(HERE), str(HERE.parent/'failure_only_orchestration'),
               str(PREP/'adaptive_training_v90')]

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

load('v105_normal_td', PREP/'complete_curve_source_gates_v105/variants/normal/td.py')
L = load('v105_normal_learning', PREP/'complete_curve_source_gates_v105/variants/normal/learning.py')
import adaptive_training as A
from orchestration import ProtocolError
from task_loop import ObservedTaskLoop, Proposal, observed_terminal
from rfl_rebuild.env import kernel as K
from rfl_rebuild.b2.unaffected import EvaluationScene
from rfl_rebuild.learner.reference import QReferenceView
from rfl_rebuild.learner.store import (LearnerPersistentState, QAddress, DecisionAddress,
                                      Edit, Q, DECISION, PROCESS)

C = json.loads((HERE/'contract.json').read_bytes())
STARTED = time.monotonic()
COUNTS = {'rollout': 0, 'step': 0, 'transaction': 0}
RECORDS = []
STREAM = None
CASE = None
REFERENCE = None

def emit(tag, payload):
    record = {'seq': len(RECORDS), 'case': CASE, 'tag': tag, 'payload': A.wire(payload)}
    line = json.dumps(record, sort_keys=True, separators=(',', ':'), ensure_ascii=True)+'\n'
    STREAM.write(line); STREAM.flush()
    RECORDS.append(record)
    if STREAM.tell() > C['budget']['raw_bytes'] or time.monotonic()-STARTED > C['budget']['seconds']:
        raise RuntimeError('prospective finite run budget exhausted')

def observe(frame, event, arg):
    if event != 'call': return
    p, n = frame.f_code.co_filename.replace('\\', '/'), frame.f_code.co_name
    counter = (n if p.endswith('rfl_rebuild/env/kernel.py') and n in ('step','rollout') else
               'transaction' if p.endswith('rfl_rebuild/learner/store.py') and n=='apply_transaction' else None)
    if counter:
        COUNTS[counter] += 1
        if COUNTS[counter] > C['budget'][counter]: raise RuntimeError('native extent budget '+counter)

def reference():
    pin=C['source_reference']; raw=(ROOT/pin['path']).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==pin['sha256']
    rows={}
    for line in raw.decode('utf-8').splitlines():
        if line.startswith('DECISION_CONTEXT='):
            d=json.loads(line.split('=',1)[1]);x,y,t,k,phi,z,m=d['context']
            rows[K.State(x,y,t,k,phi),z,m]={a:float.fromhex(v) for a,v in d['q_row_hex']}
    ref=QReferenceView(rows,name='v117-original-reference')
    assert ref.digest()==pin['q_digest']
    return ref

def context(k=0):
    return DecisionAddress(K.State(1,2,1,k,2),1,0)

def bad_q(k=0):
    a=context(k);return QAddress(a.state,a.z,a.m,K.RIGHT)

def make_state(mode, kind):
    state=LearnerPersistentState();edits=[]
    if kind=='success-value':
        edits=[Edit(Q,QAddress(K.State(0,2,0,0,2),1,0,K.RIGHT),2.0)]
    elif kind=='collision':
        for k in (0,1):
            a=context(k)
            edits.append(Edit(Q,bad_q(k),max(REFERENCE.row(a.state,a.z,a.m).values())+1.0)
                         if mode=='dq' else Edit(DECISION,a,K.RIGHT))
    elif kind=='timeout':
        edits=[Edit(DECISION,DecisionAddress(K.State(0,2,t,0,2),1,m),K.WAIT)
               for t in range(12) for m in (0,1)]
    # A process sentinel is unread in all base-option1 tasks.
    edits.append(Edit(PROCESS,3,2))
    emit('SETUP', {'mode':mode,'kind':kind,'edits':edits})
    state.apply_transaction(tuple(edits),q_reference=REFERENCE)
    return state

def plan(n=1):
    episodes=tuple(L.EngineeringEpisode(e,0,1,K.SemanticTape(2,0,0),
                    ((1<<64)-1,)*12,(((1<<64)-1,0),)*12) for e in range(n))
    return L.EngineeringPlan(episodes,(EvaluationScene(0,2,0,0,1),),
                            0.7642000000000008,A.LearningParameters(),
                            'v117-keyfree-finite-plan-not-old-F1-qualification')

def independent_numeric_update(before, trace, episode, ref):
    """Own chronological TD reconstruction; does not call the reused sweep."""
    values=dict(before.q_overrides);visited=[]
    state=K.State(0,2,0,episode.kappa,episode.tape.phase)
    control=K.initial_control(trace.option_in_force)
    for step in trace.steps:
        q=QAddress(state,control.z,control.m,step.a_cmd)
        old=values.get(q,ref.value(q));target=float(step.reward)
        if not step.terminal:
            acts=K.option_actions(step.control.z,step.control,step.state)
            if acts: target += max(values.get(QAddress(step.state,step.control.z,step.control.m,a),
                                               ref.value(QAddress(step.state,step.control.z,step.control.m,a))) for a in acts)
        values[q]=old+float(Fraction(1,2))*(target-old)
        visited.append(q);state,control=step.state,step.control
    return {q:v for q,v in values.items() if v!=ref.value(q)}

class Tasks(unittest.TestCase):
    def setUp(self):
        global CASE
        CASE=self._testMethodName
        self.emit_begin=len(RECORDS)
        self.actors=[]
        emit('CASE_BEGIN',{'name':CASE})

    def actor(self,mode,kind,diagnose,writes=1,n=1):
        actor=ObservedTaskLoop(make_state(mode,kind),mode=mode,role='treatment',
                              source_label='v117:'+CASE,reference=REFERENCE,plan=plan(n),
                              diagnose=diagnose,max_writes=writes,emit=emit)
        self.actors.append(actor);return actor

    def tearDown(self):
        emit('CASE_END',{'actors':[x.payload() for x in self.actors]})

    def check_receipt(self,actor,r):
        self.assertEqual(r['counters']['ordinary_updates'],1)
        self.assertEqual(r['before']['immediate'],r['after']['immediate'])
        self.assertEqual(r['before']['current']['P'],r['after']['current']['P'])
        self.assertEqual(r['before']['current']['X'],r['after']['current']['X'])
        rows=[x for x in RECORDS[self.emit_begin:] if x['tag']=='TASK_RAW']
        self.assertTrue(rows)

    def test_01_success_real_TD_no_diagnosis(self):
        def forbidden(*_):raise AssertionError('success diagnosis called')
        a=self.actor('dq','success-value',forbidden)
        initial=a._current.clone();r=a.run_task();self.check_receipt(a,r)
        self.assertEqual(r['terminal'],'SUCCESS')
        self.assertNotEqual(r['before']['current']['Q'],r['after']['current']['Q'])
        self.assertEqual(r['counters']['diagnostic_calls'],0)
        self.assertEqual(r['counters']['diagnostic_transactions'],0)
        # Reconstruct using the actual original task trace retained in raw profile.
        trace=LAST_TASK_TRACES[-1]
        expected=independent_numeric_update(initial,trace,a.plan.episodes[0],REFERENCE)
        self.assertEqual(dict(a._current.q_overrides),expected)

    def test_02_patch_success_no_diagnosis(self):
        a=self.actor('patch-adaptive','healthy',lambda *_:self.fail('diagnosis on success'))
        r=a.run_task();self.check_receipt(a,r);self.assertEqual(r['terminal'],'SUCCESS')
        self.assertEqual(r['counters']['diagnostic_calls'],0)

    def test_03_collision_apply_then_real_success(self):
        calls=[]
        def diagnostic(term,evidence,budget):
            calls.append((term,evidence,budget))
            self.assertFalse(hasattr(evidence,'mask'))
            self.assertFalse(hasattr(evidence,'truth'))
            self.assertEqual(budget.remaining_queries,0)
            return Proposal('apply',(Edit(Q,bad_q(),None),))
        a=self.actor('dq','collision',diagnostic,n=2)
        sentinel=a._current.q_overrides[bad_q(1)]
        r=a.run_task();self.check_receipt(a,r)
        self.assertEqual(r['terminal'],'COLLISION')
        self.assertEqual(r['counters']['diagnostic_transactions'],1)
        self.assertEqual(r['route']['write_spend'],1)
        self.assertNotEqual(r['ordinary_after']['current'],r['after']['current'])
        self.assertEqual(a._current.q_overrides[bad_q(1)],sentinel)
        second=a.run_task();self.assertEqual(second['terminal'],'SUCCESS')
        self.assertEqual(len(calls),1)

    def test_04_patch_collision_keep(self):
        a=self.actor('patch-adaptive','collision',lambda *_:Proposal())
        r=a.run_task();self.check_receipt(a,r);self.assertEqual(r['terminal'],'COLLISION')
        self.assertEqual(r['route']['decision'],'keep')
        self.assertEqual(r['counters']['diagnostic_transactions'],0)
        self.assertNotEqual(r['before']['current']['D'],r['ordinary_after']['current']['D'])

    def test_05_actual_timeout_keep(self):
        a=self.actor('patch-adaptive','timeout',lambda *_:Proposal())
        r=a.run_task();self.check_receipt(a,r);self.assertEqual(r['terminal'],'TIMEOUT')
        self.assertEqual(r['route']['decision'],'keep')

    def test_06_actual_environment_trap_keep(self):
        def diagnostic(term,evidence,budget):
            self.assertEqual(term,'TRAP');self.assertFalse(hasattr(evidence,'mask'))
            return Proposal()
        a=self.actor('dq','healthy',diagnostic)
        r=a.run_task(mask=K.FaultMask(trap=K.Trap((1,2),0)))
        self.check_receipt(a,r);self.assertEqual(r['terminal'],'TRAP')

    def test_07_write_budget_prevents_real_transaction(self):
        a=self.actor('dq','collision',lambda *_:Proposal('apply',(Edit(Q,bad_q(),None),)),writes=0)
        with self.assertRaisesRegex(ProtocolError,'write budget'):
            a.run_task()
        self.assertEqual(len(a.task_receipts),0);self.assertEqual(a._completed,1)
        old=dict(COUNTS)
        with self.assertRaisesRegex(ProtocolError,'no retry'):a.run_task()
        self.assertEqual(COUNTS,old)
        part=next(x['payload'] for x in reversed(RECORDS) if x['tag']=='TASK_PARTIAL')
        self.assertTrue(part['ordinary_committed'])
        self.assertEqual(part['counters']['diagnostic_transactions'],0)

    def test_08_unvisited_write_rejected(self):
        a=self.actor('dq','collision',lambda *_:Proposal('apply',(Edit(Q,bad_q(1),None),)))
        with self.assertRaisesRegex(ProtocolError,'not visited'):a.run_task()
        self.assertEqual(len(a.task_receipts),0)
        self.assertEqual(RECORDS[-1]['payload']['counters']['diagnostic_transactions'],0)

    def test_09_diagnostic_failure_retains_ordinary_and_closes(self):
        def diagnostic(*_):raise RuntimeError('planned diagnostic dependency failure')
        a=self.actor('dq','collision',diagnostic)
        with self.assertRaisesRegex(RuntimeError,'planned'):a.run_task()
        self.assertEqual(a._completed,1);self.assertEqual(len(a.task_receipts),0)
        self.assertTrue(RECORDS[-1]['payload']['ordinary_committed'])
        old=dict(COUNTS)
        with self.assertRaisesRegex(ProtocolError,'no retry'):a.run_task()
        self.assertEqual(COUNTS,old)

    def test_10_terminal_validation_no_new_rollout(self):
        old=dict(COUNTS);trace=LAST_TASK_TRACES[-1]
        for invalid in (None,replace(trace,outcome='UNKNOWN'),replace(trace,steps=())):
            with self.assertRaises(ProtocolError):observed_terminal(invalid)
        self.assertEqual(COUNTS,old)


LAST_TASK_TRACES=[]

def profile(frame,event,arg):
    observe(frame,event,arg)
    if event=='return' and frame.f_code.co_name=='rollout' and type(arg) is K.RolloutTrace:
        LAST_TASK_TRACES.append(arg)

def main():
    global STREAM,REFERENCE
    STREAM=(HERE/'evidence/raw.jsonl').open('x',encoding='ascii',newline='\n')
    old_profile=sys.getprofile();result=None;failure=None
    try:
        REFERENCE=reference();emit('REFERENCE',{'digest':REFERENCE.digest(),'rows':len(REFERENCE)})
        sys.setprofile(profile)
        result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tasks))
    except BaseException as exc:
        failure={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
        emit('UNEXPECTED_FAILURE',failure)
    finally:
        sys.setprofile(old_profile)
        emit('FINAL',{'tests':0 if result is None else result.testsRun,
             'failures':None if result is None else len(result.failures),
             'errors':None if result is None else len(result.errors),
             'counts':COUNTS,'profile_restored':sys.getprofile() is old_profile,
             'unexpected_failure':failure,'wall_seconds':time.monotonic()-STARTED})
        STREAM.close()
    return 0 if result is not None and result.wasSuccessful() and failure is None else 1

if __name__=='__main__':raise SystemExit(main())
