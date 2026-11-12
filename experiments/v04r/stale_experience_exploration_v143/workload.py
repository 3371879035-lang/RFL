"""Four new ordinary continuations, no old prefix/native/checker replay."""
from collections import Counter
import hashlib,importlib.util,json,sys,time,traceback
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
PREP=ROOT/'experiments/v03r/a96_dense/b2_prepare'
sys.path[:0]=[str(HERE),str(ROOT/'src'),str(HERE.parent/'ordinary_extra_control_v142'),str(HERE.parent/'learned_candidate_choice_v118'),str(HERE.parent/'failure_only_orchestration'),str(PREP/'adaptive_training_v90')]
C=json.loads((HERE/'contract.json').read_bytes())
COUNTS=Counter();CONTEXT={};RECORDS=0;STREAM=None;START=time.monotonic();REFERENCE=None

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
    ref=QReferenceView(rows,name='v143-shared-unchanged-Q-prior')
    assert ref.digest()==spec['q_digest'];return ref

load('v105_normal_td',PREP/'complete_curve_source_gates_v105/variants/normal/td.py')
L=load('v105_normal_learning',PREP/'complete_curve_source_gates_v105/variants/normal/learning.py')
import adaptive_training as A
from observation_loop import ObservationTaskLoop
from checkpoint import RecordedOrdinaryCheckpoint,initialize
from rfl_rebuild.env import kernel as K
from rfl_rebuild.b2.unaffected import EvaluationScene
from rfl_rebuild.learner.reference import QReferenceView
from rfl_rebuild.learner.store import QAddress,DecisionAddress


def forbid(*args):raise AssertionError('all tasks are ordinary, diagnostic disabled')


def plan(arm):
    n=C['ordinary_protocol']['episodes_each'];episodes=[]
    for e in range(n):
        coins=[(1<<64)-1]*12
        if e in arm['explore_epochs']:coins[0]=0
        episodes.append(L.EngineeringEpisode(e,0,1,K.SemanticTape(3,0,12),tuple(coins),((0,),)*12))
    return L.EngineeringPlan(tuple(episodes),(EvaluationScene(0,3,0,12,1),),0.7642000000000008,A.LearningParameters(),
                             'v143-predeclared-literal-coordinates-not-sampled-keyed-frequency')


def start_values(loop):
    state=K.State(0,2,0,0,3);ctrl=K.initial_control(1);row=loop._values.snapshot().q_decision_provider(REFERENCE)
    return {'RIGHT':loop._values.q_overrides.get(QAddress(state,1,0,3),REFERENCE.row(state,1,0)[3]),
            'WAIT':loop._values.q_overrides.get(QAddress(state,1,0,4),REFERENCE.row(state,1,0)[4]),
            'greedy_command':loop._greedy()(state,ctrl)}


def experiment():
    global CONTEXT
    cp=RecordedOrdinaryCheckpoint.read(ROOT,C['checkpoint'])
    CONTEXT={'phase':'bootstrap'};emit('CHECKPOINT_BEFORE',{'source_raw_sha256':cp.raw_sha256,'full_payload':cp.full_payload})
    states=cp.materialize(REFERENCE)
    emit('CHECKPOINT_MATERIALIZED',{'immediate':A.stores(states[0]),'current':A.stores(states[1]),'learning_values':A.stores(states[2]),
          'materialization_TX':3,'old_issued_identity_restored':False})
    summary=[]
    for arm in C['arms']:
        CONTEXT={'phase':'continuation','arm':arm['name']}
        loop=initialize(ObservationTaskLoop,cp,states,reference=REFERENCE,plan=plan(arm),label='v143-continuation:'+arm['name'],emit=emit,diagnose=forbid)
        returns=[];terminals=[];starts=[]
        for e in range(C['ordinary_protocol']['episodes_each']):
            before=start_values(loop)
            mask=K.FaultMask(trap=K.Trap((1,2),0)) if arm['trap'] else K.FaultMask()
            receipt=loop.run_task(mask=mask)
            value=float(sum(float.fromhex(s['reward']['binary64_hex']) for s in receipt['trace']['steps']))
            row={'epoch':e,'before_start':before,'after_start':start_values(loop),'first_command':receipt['trace']['steps'][0]['a_cmd'],
                 'explore_planned':e in arm['explore_epochs'],'terminal':receipt['terminal'],'return':value}
            emit('START_VALUE_UPDATE',row);starts.append(row);returns.append(value);terminals.append(receipt['terminal'])
        row={'arm':arm['name'],'tasks':len(returns),'successes':terminals.count('SUCCESS'),'returns':returns,'return_mean':sum(returns)/len(returns),
             'outcomes':terminals,'start_values':starts,'final_state':loop.payload()}
        emit('STREAM_ARM',row);summary.append(row)
    return summary


def main():
    global STREAM,REFERENCE
    STREAM=(HERE/'evidence/raw.jsonl').open('x',encoding='ascii',newline='\n');previous=sys.getprofile();ok=False
    try:
        REFERENCE=read_reference();emit('REFERENCE',{'digest':REFERENCE.digest(),'rows':len(REFERENCE)})
        sys.setprofile(profile);rows=experiment();emit('RESULT',{'complete':True,'counts':dict(COUNTS),'streams':rows,'new_keys':0,'formal_collection':False});ok=True
    except BaseException as error:
        emit('FAILURE',{'complete':False,'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc(),'counts':dict(COUNTS)})
        traceback.print_exc()
    finally:
        sys.setprofile(previous);emit('FINAL',{'complete':ok,'counts':dict(COUNTS),'profile_restored':sys.getprofile() is previous,'wall_seconds':time.monotonic()-START});STREAM.close()
    return 0 if ok else 1

if __name__=='__main__':raise SystemExit(main())
