"""Three fresh current roles investigate native failures without command/realization mismatch."""
from collections import Counter
from pathlib import Path
import hashlib,importlib.util,json,sys,time,traceback
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];PREP=ROOT/'experiments/v03r/a96_dense/b2_prepare'
sys.path[:0]=[str(HERE),str(HERE.parent/'no_mismatch_failure_probe_v157'),str(HERE.parent/'witness_context_binding_v154'),str(HERE.parent/'trial_derived_joint_repair_v153'),str(HERE.parent/'intervention_trial_learning_v151'),str(HERE.parent/'observed_prefix_probe_v150'),str(HERE.parent/'stale_experience_exploration_v143'),str(ROOT/'src'),str(HERE.parent/'mechanism_conditioned_experience_v147'),str(HERE.parent/'direct_controller_control_v145'),str(HERE.parent/'controller_horizon_value_v144'),str(HERE.parent/'learned_candidate_choice_v118'),str(HERE.parent/'failure_only_orchestration'),str(PREP/'adaptive_training_v90')]
C=json.loads((HERE/'contract.json').read_bytes());COUNTS=Counter();CONTEXT={};RECORDS=0;STREAM=None;START=time.monotonic();REFERENCE=None

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod)
    return mod

def emit(tag,payload):
    global RECORDS
    line=json.dumps({'seq':RECORDS,'context':dict(CONTEXT),'tag':tag,'payload':A.wire(payload)},
                    sort_keys=True,separators=(',',':'),ensure_ascii=True)+'\n'
    STREAM.write(line);STREAM.flush();RECORDS+=1
    if STREAM.tell()>C['budget']['raw_bytes'] or time.monotonic()-START>C['budget']['seconds']:
        raise RuntimeError('prospective resource budget exceeded')

def profile(frame,event,arg):
    if event!='call':return
    p,n=frame.f_code.co_filename.replace('\\','/'),frame.f_code.co_name
    name=(n if p.endswith('rfl_rebuild/env/kernel.py') and n in ('rollout','step') else
          'transaction' if p.endswith('rfl_rebuild/learner/store.py') and n=='apply_transaction' else None)
    if name:
        COUNTS[name]+=1
        if COUNTS[name]>C['budget'][name]:raise RuntimeError('native budget '+name)

def read_reference():
    spec=C['reference'];data=(ROOT/spec['path']).read_bytes()
    assert hashlib.sha256(data).hexdigest()==spec['sha256']
    rows={}
    for line in data.decode('utf-8').splitlines():
        if line.startswith('DECISION_CONTEXT='):
            item=json.loads(line.split('=',1)[1]);x,y,t,k,p,z,m=item['context']
            rows[K.State(x,y,t,k,p),z,m]={a:float.fromhex(v) for a,v in item['q_row_hex']}
    ref=QReferenceView(rows,name='v158-unchanged-Q-prior')
    assert ref.digest()==spec['q_digest'];return ref

def returned(receipt):return sum(float.fromhex(s['reward']['binary64_hex']) for s in receipt['trace']['steps'])

load('v105_normal_td',PREP/'complete_curve_source_gates_v105/variants/normal/td.py')
L=load('v105_normal_learning',PREP/'complete_curve_source_gates_v105/variants/normal/learning.py')
import adaptive_training as A
from mechanism_loop import ObservationTaskLoop as NativeLoop
from candidate_loop import Proposal
from value_policy import candidate,EmpiricalHorizonValue
from rfl_rebuild.env import kernel as K
from rfl_rebuild.b2.unaffected import EvaluationScene
from rfl_rebuild.learner.reference import QReferenceView
from rfl_rebuild.learner.store import LearnerPersistentState,DECISION,CONTROLLER,Edit,DecisionAddress


from checkpoint import RecordedOrdinaryCheckpoint

from prefix_probe import compile_observed_prefix,literal_coordinates,assess_actual_reach

from bound_agent import StrictTrialDerivedAgent
from probe_agent import NoMismatchProbeAgent
from contextlib import contextmanager

def sequence():
    seq=[s for s in C['schedule'] for _ in range(s['count'])];assert len(seq)==12;return seq


def main_plan():
    episodes=tuple(L.EngineeringEpisode(e,s['kappa'],1,K.SemanticTape(s['phi'],0,12),((1<<64)-1,)*12,((0,),)*12) for e,s in enumerate(sequence()))
    return L.EngineeringPlan(episodes,(EvaluationScene(1,0,0,12,1),),.7642000000000008,A.LearningParameters(),'v158-main')


def query_plan(evidence,spec,greedy):
    coins,rejections=(((1<<64)-1,)*12,((0,),)*12) if greedy else spec.literal_coordinates()
    ep=L.EngineeringEpisode(0,evidence.kappa,1,K.SemanticTape(evidence.phi,0,12),coins,rejections)
    return L.EngineeringPlan((ep,),(EvaluationScene(evidence.kappa,evidence.phi,0,12,1),),.7642000000000008,A.LearningParameters(),'v158-current-private')


@contextmanager
def private_context(name):
    old=dict(CONTEXT);CONTEXT.update(phase='private',candidate=name)
    try:yield
    finally:CONTEXT.clear();CONTEXT.update(old)


def experiment():
    global CONTEXT
    spec=C['ordinary_checkpoint']
    for field in ('raw','exit','review'):
        cfg=spec[field];b=(ROOT/cfg['path']).read_bytes();assert len(b)==cfg['bytes'] and hashlib.sha256(b).hexdigest()==cfg['sha256']
    ex=json.loads((ROOT/spec['exit']['path']).read_bytes());review=json.loads((ROOT/spec['review']['path']).read_bytes())
    assert ex['child_exit_code']==0 and ex['input_bytes_unchanged'] and review['complete']
    records=[json.loads(s) for s in (ROOT/spec['raw']['path']).read_text(encoding='ascii').splitlines()]
    selected=[r for r in records if r['tag']=='PREPARATION_COMPLETE'];assert len(selected)==1
    payload=selected[0]['payload']['state'];cp=RecordedOrdinaryCheckpoint(spec['raw']['sha256'],1,0,payload)
    CONTEXT={'phase':'checkpoint'};count=Counter(COUNTS);immediate,current,values=cp.materialize(REFERENCE)
    emit('RECORDED_ORDINARY_MATERIALIZED',{'source_seq':selected[0]['seq'],'source_raw_sha256':cp.raw_sha256,'recorded_payload':payload,
         'immediate':A.stores(immediate),'current':A.stores(current),'learning_values':A.stores(values),
         'native_delta':{k:COUNTS[k]-count[k] for k in ('rollout','step','transaction')},'restored_issued_identities':0})
    source=current.clone();CONTEXT={'phase':'source','arm':'shared'};emit('SHARED_UNEDITED_SOURCE',{'state':A.stores(source),'values':A.stores(values),'source_install_TX':0})
    summaries=[]
    for arm in C['arms']:
        CONTEXT={'phase':'stream','arm':arm}
        loop=NoMismatchProbeAgent(source,mode='patch-adaptive',role='treatment',source_label=arm,reference=REFERENCE,plan=main_plan(),emit=emit,
            algorithm=arm,trial_budget=0 if arm=='TaskTD' else C['trial_task_budget_each'],private_plan_factory=None,query_plan_factory=query_plan,private_context=private_context)
        loop._values=values.clone();loop._check();emit('MAIN_INITIALIZED',{'state':loop.payload(),'diagnostic_account':loop.diagnostic_account()});receipts=[]
        for e,s in enumerate(sequence()):
            CONTEXT['main_epoch']=e;mask=K.FaultMask(trap=K.Trap(tuple(s['trap']['cell']),s['trap']['t']))
            emit('RUNNER_CONTEXT',{'epoch':e,'stage_audit_only':s['label'],'kappa':s['kappa'],'phi':s['phi']})
            receipt=loop.run_observed_task(mask=mask);receipts.append(receipt);assert loop.payload()['immediate']==A.stores(source)
        vals=[returned(x) for x in receipts]
        row={'arm':arm,'main_tasks':12,'successes':sum(x['terminal']=='SUCCESS' for x in receipts),'returns':vals,'outcomes':[x['terminal'] for x in receipts],
             'mean_return':sum(vals)/12,'external_updates':loop._external_updates,'final_state':loop.payload(),'diagnostic_account':loop.diagnostic_account()}
        emit('AGENT_FINAL',row);summaries.append(row)
    return summaries


def main():
    global STREAM,REFERENCE
    STREAM=(HERE/'evidence/raw.jsonl').open('x',encoding='ascii',newline='\n');previous=sys.getprofile();ok=False
    try:
        REFERENCE=read_reference();emit('REFERENCE',{'digest':REFERENCE.digest(),'rows':len(REFERENCE)})
        sys.setprofile(profile);rows=experiment();emit('RESULT',{'complete':True,'counts':dict(COUNTS),'streams':rows,'new_keys':0,'formal_collection':False});ok=True
    except BaseException as error:
        emit('FAILURE',{'type':type(error).__name__,'error':str(error),'traceback':traceback.format_exc(),'counts':dict(COUNTS)});traceback.print_exc()
    finally:
        sys.setprofile(previous);emit('FINAL',{'complete':ok,'profile_restored':sys.getprofile() is previous,'counts':dict(COUNTS),'wall_seconds':time.monotonic()-START});STREAM.close()
    return 0 if ok else 1

if __name__=='__main__':raise SystemExit(main())
