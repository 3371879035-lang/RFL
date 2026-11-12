"""New actual-START patch-hit branches. Does NOT import/run the failed v90 tests.
Frozen v90 learner implementation is reused unchanged. Real native return values
are captured BEFORE assertions, including the step prefix of a partial rollout.
"""
from collections import Counter
from fractions import Fraction
import hashlib,json
from pathlib import Path
import sys,time,traceback,unittest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
CORE=HERE.parent/'adaptive_training_v90'
sys.path[:0]=[str(CORE),str(ROOT/'src')]
import adaptive_training as A
from rfl_rebuild.b2 import training as T, environment
from rfl_rebuild.env import kernel as K
from rfl_rebuild.learner.reference import QReferenceView
from rfl_rebuild.learner.store import LearnerPersistentState,Edit,DecisionAddress,QAddress,DECISION,PROCESS,CONTROLLER,Q

C=json.loads((HERE/'contract.json').read_bytes())
COUNTS=Counter();START=time.monotonic();CASE='reference-construction'


def emit(tag,data):
    print(json.dumps({'tag':tag,'case':CASE,'payload':A.wire(data)},sort_keys=True,separators=(',',':')),flush=True)


def profile(frame,event,arg):
    path=frame.f_code.co_filename.replace('\\','/');name=frame.f_code.co_name
    kernel=path.endswith('rfl_rebuild/env/kernel.py')
    if event=='call':
        if kernel and name in ('rollout','step'):
            COUNTS[name]+=1
            if COUNTS[name]>C['budget'][name]:raise RuntimeError('native budget exceeded')
        if path.endswith('rfl_rebuild/learner/store.py') and name=='apply_transaction':
            COUNTS['transaction']+=1
            if COUNTS['transaction']>C['budget']['transaction']:raise RuntimeError('transaction budget exceeded')
        forbidden=((path.endswith('rfl_rebuild/b2/training.py') and name in ('derive','key','mix','train_curve','pre_level')) or
            (kernel and name=='sample') or (path.endswith('rfl_rebuild/solve/dp.py') and name=='solve_reference') or
            (path.endswith('random.py') and name in ('__init__','random','randrange')))
        if forbidden:COUNTS['forbidden']+=1;raise RuntimeError('forbidden entry '+name)
        if time.monotonic()-START>C['budget']['seconds']:raise RuntimeError('wall budget exceeded')
    elif event=='return':
        if kernel and name=='step' and type(arg) is K.StepResult:
            emit('RAW_STEP',{'pre_state':frame.f_locals['state'],'pre_control':frame.f_locals['control'],
                             'a_cmd':frame.f_locals['a_cmd'],'result':arg})
        elif kernel and name=='rollout':
            if type(arg) is K.RolloutTrace:
                emit('RAW_ROLLOUT',arg)
            else:
                emit('INCOMPLETE_ROLLOUT',{'complete_trace':None})
        elif path.endswith('adaptive_training.py') and name=='train_episode' and isinstance(arg,dict):
            emit('TRAIN_RECEIPT',arg);COUNTS['complete_revised_episodes']+=1
        elif path.endswith('adaptive_training.py') and name=='evaluate' and isinstance(arg,dict):
            emit('EVAL_RECEIPT',arg)


def reference():
    p=ROOT/C['reference_input']['path'];raw=p.read_bytes()
    assert hashlib.sha256(raw).hexdigest()==C['reference_input']['sha256']
    rows={}
    for line in raw.decode('utf-8').splitlines():
        if line.startswith('DECISION_CONTEXT='):
            d=json.loads(line.split('=',1)[1]);x,y,t,k,phi,z,m=d['context']
            rows[K.State(x,y,t,k,phi),z,m]={a:float.fromhex(v) for a,v in d['q_row_hex']}
    ref=QReferenceView(rows,name='unchanged-stored-reference-v91')
    assert ref.digest()==C['reference_input']['q_digest']
    assert K.START==(0,2)==tuple(C['actual_start'])
    return ref


def make_source(ref,mode,active_x=False,partial=False):
    state=LearnerPersistentState()
    owner=DecisionAddress(K.State(1,2,1,0,2),1,0) if partial else DecisionAddress(K.State(*K.START,0,0,2),1,0)
    sentinel=DecisionAddress(K.State(*K.START,0,1,2),1,0)
    target=K.RIGHT if partial else K.WAIT
    edits=[Edit(PROCESS,0,1),Edit(CONTROLLER,K.ControllerSite(sentinel.state,K.WAIT),K.RIGHT)]
    if active_x:edits.append(Edit(CONTROLLER,K.ControllerSite(owner.state,K.WAIT),K.RIGHT))
    for addr,a in ((owner,target),(sentinel,K.WAIT)):
        edits.append(Edit(DECISION,addr,a) if mode=='patch-adaptive' else
                     Edit(Q,QAddress(addr.state,addr.z,addr.m,a),max(ref.row(addr.state,addr.z,addr.m).values())+1.0))
    state.apply_transaction(tuple(edits),q_reference=ref)
    emit('NEW_FULL_SOURCE',{'mode':mode,'state':A.stores(state),'owner':owner,'sentinel':sentinel,
                          'active_x':active_x,'original_B1_issued_pair':False})
    return state,owner,sentinel


def ep(label,coins=None,draws=None):
    return A.ScriptedEpisode(label,0,0,K.SemanticTape(2,0,57),
        coins or (T.M64,)*K.HORIZON,draws or ((0,),)*K.HORIZON)


def independent_td(state,trace,episode,ref):
    work=dict(state.q_overrides);s=K.State(0,2,0,episode.kappa,episode.tape.phase)
    z=trace.option_in_force;m=0;order=[]
    value=lambda q:work.get(q,ref.value(q))
    for row in trace.steps:
        q=QAddress(s,z,m,row.a_cmd);current=value(q);target=float(row.reward)
        if not row.terminal:
            target+=max(value(QAddress(row.state,row.control.z,row.control.m,a))
                for a in K.option_actions(row.control.z,row.control,row.state))
        work[q]=current+.5*(target-current)
        if q not in order:order.append(q)
        s,z,m=row.state,row.control.z,row.control.m
    return tuple(Edit(Q,q,float(work[q])) for q in order)


class ActualHitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.ref=reference()

    def setUp(self):
        global CASE
        CASE=self._testMethodName

    def actor(self,mode='patch-adaptive',active_x=False,partial=False):
        s,o,sentinel=make_source(self.ref,mode,active_x,partial)
        a=A.AdaptiveTrainingState(s,mode=mode,role='treatment',source_label=CASE,reference=self.ref)
        return a,s,o,sentinel

    def test_01_actual_initial_literal_hit_and_learning_release(self):
        a,s,o,sentinel=self.actor()
        before=a.evaluate(kappa=0,tape=K.SemanticTape(2,0,57),proposal=0)
        self.assertEqual(before['trace']['steps'][0]['a_cmd'],K.WAIT)
        r=a.train_episode(ep('actual-hit-learning'))
        self.assertEqual(r['trace']['steps'][0]['a_cmd'],K.WAIT)
        self.assertEqual(r['trace']['option_in_force'],1)
        self.assertEqual(a._current.decision_overrides[o],K.RIGHT)
        after=a.evaluate(kappa=0,tape=K.SemanticTape(2,0,57),proposal=0)
        self.assertEqual(after['trace']['steps'][0]['a_cmd'],K.RIGHT)
        self.assertEqual(a._current.decision_overrides[sentinel],K.WAIT)
        self.assertEqual(A.stores(s),r['before']['immediate'])

    def test_02_real_value_state_persists_with_D_P_X(self):
        a,s,o,sentinel=self.actor(active_x=True)
        initial=a.payload()
        for i in range(3):
            a.train_episode(ep('value-persistence-'+str(i)))
            a.evaluate(kappa=0,tape=K.SemanticTape(2,0,57),proposal=0)
            self.assertFalse(a._current.q_overrides)
            self.assertEqual(a._current.decision_overrides[sentinel],K.WAIT)
            self.assertEqual(a.payload()['current']['P'],initial['current']['P'])
            self.assertEqual(a.payload()['current']['X'],initial['current']['X'])
            self.assertEqual(A.stores(s),initial['immediate'])
        self.assertTrue(a._values.q_overrides)
        self.assertEqual(a._completed,3)

    def test_03_new_dq_source_exact_original_action_td_and_eval(self):
        a,s,_,_=self.actor('dq',active_x=True)
        baseline=s.clone();parameters=A.LearningParameters()
        for i in range(2):
            e=ep('actual-dq-'+str(i))
            trace=T.episode_rollout(baseline,e,protocol=parameters,q_reference=self.ref)
            expected=independent_td(baseline,trace,e,self.ref)
            edits=T.sweep_edits(baseline,trace,e,protocol=parameters,q_reference=self.ref)
            self.assertEqual(edits,expected)
            baseline.apply_transaction(edits,q_reference=self.ref)
            r=a.train_episode(e)
            self.assertEqual(r['trace'],A.wire(trace))
            self.assertEqual(r['numeric_edits'],A.wire(expected))
            self.assertEqual(a.payload()['current'],A.stores(baseline))
            old_eval=environment.learned_rollout(baseline,kappa=0,tape=e.tape,base_option=0,q_reference=self.ref)
            new_eval=a.evaluate(kappa=0,tape=e.tape,proposal=0)
            self.assertEqual(new_eval['trace'],A.wire(old_eval))
            emit('DQ_DIFFERENTIAL',{'revised':r,'original_edits':expected,'original_post':A.stores(baseline)})

    def test_04_exploration_at_hit_and_true_five_action_rejection(self):
        a,*_=self.actor()
        draws=((0,),(T.M64,0))+((0,),)*(K.HORIZON-2)
        r=a.train_episode(ep('true-rejection',(0,)*K.HORIZON,draws),
                          parameters=A.LearningParameters(epsilon=Fraction(1,1)))
        self.assertEqual(r['trace']['steps'][0]['a_cmd'],K.RIGHT)
        self.assertEqual(r['draws'][1]['admissible'],[0,1,2,3,4])
        self.assertEqual(r['trace']['steps'][1]['a_cmd'],K.UP)
        self.assertEqual([d['i'] for d in r['draws']],list(range(len(r['trace']['steps']))))

    def test_05_true_partial_step_prefix_consumed_no_retry(self):
        a,*_=self.actor(partial=True)
        coins=(T.M64,0)+(T.M64,)*(K.HORIZON-2)
        draws=((0,),(T.M64,))+((0,),)*(K.HORIZON-2)
        e=ep('true-partial',coins,draws);before=a.payload()
        try:a.train_episode(e)
        except A.ProtocolError:error=traceback.format_exc()
        else:self.fail('scripted rejection should exhaust at step1')
        after=a.payload()
        self.assertEqual(before['current'],after['current'])
        self.assertEqual(before['learning_values'],after['learning_values'])
        self.assertEqual(after['completed_episodes'],0)
        calls=dict(COUNTS)
        with self.assertRaises(A.ProtocolError):a.train_episode(e)
        self.assertEqual(dict(COUNTS),calls)
        emit('PARTIAL_NO_RETRY',{'before':before,'after':after,'traceback':error,
                                'complete_trace':None,'numeric_or_actor_commit':False})

    def test_06_zero_numeric_TD_is_not_reward_learning(self):
        a,_,o,_=self.actor()
        r=a.train_episode(ep('true-zero-td'))
        self.assertEqual(r['after']['learning_values']['Q'],[])
        self.assertEqual(a._current.decision_overrides[o],K.RIGHT)
        emit('ZERO_TD_LIMIT',{'numeric_value_changes':0,'policy_improvement_edits':r['policy_improvement_edits'],
            'interpretation':'POLICY_IMPROVEMENT_FROM_EXISTING_Q_STAR_PRIOR_NOT_NEW_REWARD_VALUE_LEARNING',
            'scientific_qualification':False})


if __name__=='__main__':
    sys.setprofile(profile)
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ActualHitTests))
    sys.setprofile(None)
    emit('RESULT',{'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
        'skips':len(result.skipped),'counts':dict(COUNTS),'seconds':time.monotonic()-START,
        'scientific_PASS':False,'formal_training_or_collection':False})
    raise SystemExit(0 if result.wasSuccessful() else 1)
