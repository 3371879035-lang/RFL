"""Prospective direct correction control, old two-step results are read-only comparators."""
from collections import Counter
from pathlib import Path
import hashlib,importlib.util,json,sys,time,traceback
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];PREP=ROOT/'experiments/v03r/a96_dense/b2_prepare'
sys.path[:0]=[str(HERE),str(ROOT/'src'),str(HERE.parent/'controller_horizon_value_v144'),str(HERE.parent/'stale_experience_exploration_v143'),str(HERE.parent/'learned_candidate_choice_v118'),str(HERE.parent/'failure_only_orchestration'),str(PREP/'adaptive_training_v90')]
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
    ref=QReferenceView(rows,name='v145-shared-unchanged-Q-prior')
    assert ref.digest()==spec['q_digest'];return ref

def plan(n,label):
    eps=tuple(L.EngineeringEpisode(i,0,1,K.SemanticTape(3,0,12),((1<<64)-1,)*12,((0,),)*12) for i in range(n))
    return L.EngineeringPlan(eps,(EvaluationScene(0,3,0,12,1),),.7642000000000008,A.LearningParameters(),label)

def returned(receipt):return sum(float.fromhex(s['reward']['binary64_hex']) for s in receipt['trace']['steps'])

def forbid(*args):raise AssertionError('private task must not diagnose')

def actor(initial,values,p,label,diagnose,enabled):
    a=ObservationTaskLoop(initial,mode='patch-adaptive',role='treatment',source_label=label,reference=REFERENCE,plan=p,
                          diagnose=diagnose,max_writes=1 if enabled else 0,emit=emit,diagnostic_enabled=enabled)
    a._values=values.clone();a._check();return a

load('v105_normal_td',PREP/'complete_curve_source_gates_v105/variants/normal/td.py')
L=load('v105_normal_learning',PREP/'complete_curve_source_gates_v105/variants/normal/learning.py')
import adaptive_training as A
from mechanism_loop import ObservationTaskLoop
from candidate_loop import Proposal
from direct_policy import choose
from checkpoint import RecordedOrdinaryCheckpoint
from rfl_rebuild.env import kernel as K
from rfl_rebuild.b2.unaffected import EvaluationScene
from rfl_rebuild.learner.reference import QReferenceView
from rfl_rebuild.learner.store import CONTROLLER,Edit


def experiment():
    global CONTEXT
    cp=RecordedOrdinaryCheckpoint.read(ROOT,C['checkpoint']);CONTEXT={'phase':'bootstrap'}
    emit('CHECKPOINT_BEFORE',{'payload':cp.full_payload,'sha256':cp.raw_sha256})
    oldI,current,values=cp.materialize(REFERENCE)
    emit('CHECKPOINT_MATERIALIZED',{'immediate':A.stores(oldI),'current':A.stores(current),'learning_values':A.stores(values)})
    initials={}
    for case,cfg in C['cases'].items():
        CONTEXT={'phase':'source','case':case};s=current.clone()
        if cfg['install_controller']:
            edits=(Edit(CONTROLLER,K.ControllerSite(K.State(0,2,0,0,3),K.WAIT),K.RIGHT),)
            before=A.stores(s);s.apply_transaction(edits,q_reference=REFERENCE)
            emit('SOURCE_X_INSTALL',{'before':before,'edits':edits,'after':A.stores(s)})
        emit('SOURCE_CASE',{'case':case,'new_role_immediate':A.stores(s),'values':A.stores(values)});initials[case]=s
    summaries=[]
    for case,cfg in C['cases'].items():
      mask=K.FaultMask(trap=K.Trap((1,2),0),plant=K.PlantFault(0,K.RIGHT) if cfg['plant_fault'] else None)
      for arm in C['arms']:
        CONTEXT={'phase':'stream','case':case,'arm':arm};pending={};used=False;loop=None
        def diagnose(term,evidence,budget):
            nonlocal used
            if used:
                emit('DIAGNOSTIC_KEEP',{'used':True});return Proposal()
            used=True;proposal,decision=choose(evidence,loop._current.controller_overrides)
            parent=dict(CONTEXT);base=loop.payload()
            emit('DIRECT_DECISION',{'evidence':evidence,'decision':decision,'proposal':proposal,'post_TD':base,
                 'plus_experience':arm=='DirectSitePlusExperience'})
            if arm=='DirectSitePlusExperience':
                CONTEXT.update({'phase':'practice','candidate':'keep'})
                branch=actor(loop._current.clone(),loop._values,plan(1,'v145-one-real-keep-experience'),loop.source_label+':keep',forbid,False)
                loop.register_trial_source(branch)
                emit('PRACTICE_START',{'state':branch.payload(),'parent':base})
                r=branch.run_task(mask=mask);obs=branch.issued_observation();pending['observation']=obs
                emit('PRACTICE_COMPLETE',{'return':returned(r),'state':branch.payload(),'observation_id':obs.observation_id})
                CONTEXT.clear();CONTEXT.update(parent)
            assert loop.payload()==base
            return proposal
        loop=actor(initials[case],values,plan(6,'v145-six-new-main-tasks'),case+':'+arm,diagnose,True)
        emit('MAIN_INITIALIZED',{'state':loop.payload()});receipts=[]
        for e in range(6):
            r=loop.run_task(mask=mask);receipts.append(r)
            if 'observation' in pending:
                obs=pending.pop('observation');loop.consume_trial_observation(obs)
                emit('KEEP_EXPERIENCE_LEARNED',{'main_epoch':e,'observation_id':obs.observation_id,'source_completed':obs.issuer._completed,'observed_epoch':obs.episode.epoch,'after':loop.payload()})
            emit('POST_MAIN_STATE',{'epoch':e,'state':loop.payload()})
        returns=[returned(r) for r in receipts]
        row={'case':case,'arm':arm,'main_tasks':6,'successes':sum(r['terminal']=='SUCCESS' for r in receipts),'returns':returns,
             'outcomes':[r['terminal'] for r in receipts],'mean_return':sum(returns)/6,'direct_events':int(used),
             'external_updates':loop._external_updates,'final_state':loop.payload()}
        emit('STREAM_ARM',row);summaries.append(row)
    return summaries


def main():
    global STREAM,REFERENCE
    STREAM=(HERE/'evidence/raw.jsonl').open('x',encoding='ascii',newline='\n');previous=sys.getprofile();ok=False
    try:
        REFERENCE=read_reference();emit('REFERENCE',{'digest':REFERENCE.digest(),'rows':len(REFERENCE)})
        sys.setprofile(profile);rows=experiment();emit('RESULT',{'complete':True,'counts':dict(COUNTS),'streams':rows,'new_keys':0,'formal_collection':False});ok=True
    except BaseException as error:
        emit('FAILURE',{'type':type(error).__name__,'error':str(error),'traceback':traceback.format_exc(),'counts':dict(COUNTS)})
        traceback.print_exc()
    finally:
        sys.setprofile(previous);emit('FINAL',{'complete':ok,'profile_restored':sys.getprofile() is previous,'counts':dict(COUNTS),'wall_seconds':time.monotonic()-START});STREAM.close()
    return 0 if ok else 1

if __name__=='__main__':raise SystemExit(main())
