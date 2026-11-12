"""Prospective ordinary-extra-training control, no diagnostic policy imported."""
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import traceback
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
PREP=ROOT/'experiments/v03r/a96_dense/b2_prepare'
sys.path[:0]=[str(HERE),str(ROOT/'src'),str(HERE.parent/'learned_candidate_choice_v118'),str(HERE.parent/'failure_only_orchestration'),str(PREP/'adaptive_training_v90')]

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod)
    return mod

load('v105_normal_td',PREP/'complete_curve_source_gates_v105/variants/normal/td.py')
L=load('v105_normal_learning',PREP/'complete_curve_source_gates_v105/variants/normal/learning.py')
import adaptive_training as A
from observation_loop import ObservationTaskLoop,ProtocolError
from rfl_rebuild.env import kernel as K
from rfl_rebuild.b2.unaffected import EvaluationScene
from rfl_rebuild.learner.reference import QReferenceView
from rfl_rebuild.learner.store import LearnerPersistentState,Q,DECISION,PROCESS,QAddress,DecisionAddress,Edit
C=json.loads((HERE/'contract.json').read_bytes());SCHEDULES=C['schedules']
COUNTS=Counter();CONTEXT={};RECORDS=0;STREAM=None;START=time.monotonic();REFERENCE=None
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
    ref=QReferenceView(rows,name='v142-shared-unchanged-Q-prior')
    assert ref.digest()==spec['q_digest'];return ref

def plan(case_id):
    episodes=tuple(L.EngineeringEpisode(e,item['kappa'],1,K.SemanticTape(item['phi'],0,12),
                         ((1<<64)-1,)*12,(((1<<64)-1,0),)*12) for e,item in enumerate(SCHEDULES[case_id]))
    scenes=tuple(EvaluationScene(x['kappa'],x['phi'],0,12,1) for x in C['retention_scenes'])
    return L.EngineeringPlan(episodes,scenes,0.7642000000000008,A.LearningParameters(),
                             'v142-finite-recurrent-stream-not-keyed-qualification')

def start(mode,case_id):
    cfg=C['cases'][case_id];edits=[]
    for d in cfg['sources']:
        kappa=d['kappa'];x,y=d['cell']
        for t in range(d['prefix'],12):
            for m in (0,1):
                a=DecisionAddress(K.State(x,y,t,kappa,d['phi']),1,m)
                edits.append(Edit(Q,QAddress(a.state,1,m,K.WAIT),6.0) if mode=='dq' else Edit(DECISION,a,K.WAIT))
    for t in cfg['prefix_wait_source']['times']:
        for m in (0,1):
            a=DecisionAddress(K.State(0,2,t,cfg['prefix_wait_source']['kappa'],cfg['prefix_wait_source']['phi']),1,m)
            edits.append(Edit(Q,QAddress(a.state,1,m,K.WAIT),6.0) if mode=='dq' else Edit(DECISION,a,K.WAIT))
    script=cfg['scripted_source']
    for item in script['entries']:
        for m in (0,1):
            a=DecisionAddress(K.State(item['x'],item['y'],item['t'],item.get('kappa',script['kappa']),item.get('phi',script['phi'])),1,m)
            edits.append(Edit(Q,QAddress(a.state,1,m,item['action']),6.0) if mode=='dq' else Edit(DECISION,a,item['action']))
    a=DecisionAddress(K.State(1,2,1,0,4),1,0)
    edits.append(Edit(Q,QAddress(a.state,1,0,K.RIGHT),9.0) if mode=='dq' else Edit(DECISION,a,K.RIGHT))
    edits.append(Edit(PROCESS,3,2));state=LearnerPersistentState()
    emit('SOURCE_SETUP',{'mode':mode,'case':case_id,'edits':edits,'before':A.stores(state)})
    state.apply_transaction(tuple(edits),q_reference=REFERENCE)
    emit('SOURCE_READY',{'case':case_id,'stores':A.stores(state),'healthy':state.healthy})
    return state

def returned(receipt):
    return float(sum(float.fromhex(s['reward']['binary64_hex']) for s in receipt['trace']['steps']))

def practice_plan(kappa,phi,n):
    episodes=tuple(L.EngineeringEpisode(i,kappa,1,K.SemanticTape(phi,0,12),
                  ((1<<64)-1,)*12,(((1<<64)-1,0),)*12) for i in range(n))
    return L.EngineeringPlan(episodes,(EvaluationScene(kappa,phi,0,12,1),),0.7642000000000008,
                             A.LearningParameters(),'v142-current-condition-practice-not-future-stream')

def forbidden_diagnosis(*args):
    raise AssertionError('ordinary-extra control has no diagnostic callback')


def actor(initial,p,label):
    return ObservationTaskLoop(initial,mode='patch-adaptive',role='treatment',source_label=label,
            reference=REFERENCE,plan=p,diagnose=forbidden_diagnosis,max_writes=0,
            emit=emit,diagnostic_enabled=False)


def experiment():
    global CONTEXT
    initials={}
    for case in C['cases']:
        CONTEXT={'phase':'stream','mode':'patch-adaptive','arm':'setup:'+case,'case':case}
        initials[case]=start('patch-adaptive',case)
    rows=[]
    for arm in C['arms']:
        case=C['roles'][arm]['case'];CONTEXT={'phase':'stream','mode':'patch-adaptive','arm':arm,'case':case}
        loop=actor(initials[case].clone(),plan(case),'ordinary-extra:'+arm)
        receipts=[];extra_events=0;extra_episodes=0
        for e,item in enumerate(SCHEDULES[case]):
            parent=dict(CONTEXT);mask=K.FaultMask(trap=K.Trap((1,2),0)) if item['trap'] else K.FaultMask()
            receipt=loop.run_task(mask=mask);receipts.append(receipt);used=0
            if receipt['terminal']!='SUCCESS' and extra_events<3:
                extra_events+=1
                emit('ORDINARY_EXTRA_BEGIN',{'main_epoch':e,'event_number':extra_events,'before':loop.payload(),'max_extra_episodes':2})
                for j in range(2):
                    CONTEXT={**parent,'phase':'ordinary-extra','main_epoch':e,'extra_index':j}
                    branch=actor(loop._current.clone(),practice_plan(item['kappa'],item['phi'],1),loop.source_label+':extra:'+str(e)+':'+str(j))
                    branch._values=loop._values.clone();branch._check()
                    assert branch._current is not loop._current and branch._values is not loop._values
                    loop.register_trial_source(branch)
                    extra=branch.run_task(mask=mask);observation=branch.issued_observation()
                    CONTEXT=parent
                    loop.consume_trial_observation(observation)
                    unchanged=loop.payload();count=Counter(COUNTS)
                    try:loop.consume_trial_observation(observation)
                    except ProtocolError as error:
                        assert unchanged==loop.payload() and count==COUNTS
                        emit('OBSERVATION_DUPLICATE_REJECTED',{'main_epoch':e,'observation_id':observation.observation_id,'error':str(error),
                             'native_delta':{k:COUNTS[k]-count[k] for k in ('rollout','step','transaction')},'state_unchanged':True})
                    else:raise AssertionError('native observation consumed twice')
                    extra_episodes+=1;used+=1
                    emit('ORDINARY_EXTRA_EPISODE',{'main_epoch':e,'extra_index':j,'observation_id':observation.observation_id,
                         'actual_terminal':extra['terminal'],'actual_return':returned(extra),'after':loop.payload()})
                    if extra['terminal']=='SUCCESS':break
                emit('ORDINARY_EXTRA_END',{'main_epoch':e,'event_number':extra_events,'extra_episodes':used,'after':loop.payload()})
            emit('POST_MAIN_LEARNING_STATE',{'main_epoch':e,'state':loop.payload(),'observations_consumed':used})
        returns=[returned(r) for r in receipts]
        row={'mode':'patch-adaptive','arm':arm,'case':case,'main_tasks':20,'returns':returns,'outcomes':[r['terminal'] for r in receipts],
             'successes':sum(r['terminal']=='SUCCESS' for r in receipts),'return_sum':sum(returns),'return_mean':sum(returns)/20,
             'extra_events':extra_events,'extra_episodes':extra_episodes,'external_updates':loop._external_updates,
             'diagnostic_calls':sum(r['counters']['diagnostic_calls'] for r in receipts),'final_state':loop.payload()}
        emit('STREAM_ARM',row);rows.append(row)
    return rows


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
