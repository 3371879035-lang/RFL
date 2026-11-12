"""Fresh authentic-source mechanism-conditioned transfer vs original consumer."""
from collections import Counter
from pathlib import Path
import hashlib,importlib.util,json,sys,time,traceback
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];PREP=ROOT/'experiments/v03r/a96_dense/b2_prepare'
sys.path[:0]=[str(HERE),str(ROOT/'src'),str(HERE.parent/'direct_controller_control_v145'),str(HERE.parent/'controller_horizon_value_v144'),str(HERE.parent/'stale_experience_exploration_v143'),str(HERE.parent/'learned_candidate_choice_v118'),str(HERE.parent/'failure_only_orchestration'),str(PREP/'adaptive_training_v90')]
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
    ref=QReferenceView(rows,name='v147-shared-unchanged-Q-prior')
    assert ref.digest()==spec['q_digest'];return ref

def returned(receipt):return sum(float.fromhex(s['reward']['binary64_hex']) for s in receipt['trace']['steps'])

def forbid(*args):raise AssertionError('private task must not diagnose')

load('v105_normal_td',PREP/'complete_curve_source_gates_v105/variants/normal/td.py')
L=load('v105_normal_learning',PREP/'complete_curve_source_gates_v105/variants/normal/learning.py')
import adaptive_training as A
from mechanism_loop import ObservationTaskLoop as NativeLoop,ProtocolError
from conditioned_experience import ConditionedObservationLoop,ObservationTransferResult
from candidate_loop import Proposal
from direct_policy import choose
from checkpoint import RecordedOrdinaryCheckpoint
from rfl_rebuild.env import kernel as K
from rfl_rebuild.b2.unaffected import EvaluationScene
from rfl_rebuild.learner.reference import QReferenceView
from rfl_rebuild.learner.store import DECISION,CONTROLLER,Edit,DecisionAddress


def plan(n,case,private=False):
    eps=[]
    for e in range(n):
        coins=[(1<<64)-1]*12
        if case=='affected' and e==(0 if private else 1):coins[0]=0
        eps.append(L.EngineeringEpisode(e,0,1,K.SemanticTape(3,0,12),tuple(coins),((0,),)*12))
    return L.EngineeringPlan(tuple(eps),(EvaluationScene(0,3,0,12,1),),.7642000000000008,A.LearningParameters(),
                            'v147-owned-private-observation' if private else 'v147-new-main-condition-test')

def actor(cls,initial,values,p,label,diagnose,enabled):
    a=cls(initial,mode='patch-adaptive',role='treatment',source_label=label,reference=REFERENCE,plan=p,
          diagnose=diagnose,max_writes=1 if enabled else 0,emit=emit,diagnostic_enabled=enabled)
    a._values=values.clone();a._check();return a


def experiment():
    global CONTEXT
    cp=RecordedOrdinaryCheckpoint.read(ROOT,C['checkpoint']);CONTEXT={'phase':'bootstrap'}
    emit('CHECKPOINT_BEFORE',{'payload':cp.full_payload,'sha256':cp.raw_sha256});oldI,current,values=cp.materialize(REFERENCE)
    emit('CHECKPOINT_MATERIALIZED',{'immediate':A.stores(oldI),'current':A.stores(current),'learning_values':A.stores(values)})
    starts={}
    for case in C['cases']:
        CONTEXT={'phase':'source','case':case};s=current.clone()
        edits=((Edit(DECISION,DecisionAddress(K.State(0,2,0,0,3),1,0),3),Edit(CONTROLLER,K.ControllerSite(K.State(0,2,0,0,3),3),4),
                 Edit(DECISION,DecisionAddress(K.State(1,2,2,0,3),1,0),3)) if case=='affected' else
               (Edit(CONTROLLER,K.ControllerSite(K.State(0,2,0,0,3),4),3),))
        before=A.stores(s);s.apply_transaction(edits,q_reference=REFERENCE);emit('SOURCE_INSTALL',{'case':case,'before':before,'edits':edits,'after':A.stores(s),'values':A.stores(values)});starts[case]=s
    mask=K.FaultMask(trap=K.Trap((1,2),0));summaries=[]
    for case in C['cases']:
      for arm in C['arms']:
        CONTEXT={'phase':'stream','case':case,'arm':arm};pending={};used=False;loop=None;accepted=None
        def diagnose(term,evidence,budget):
            nonlocal used
            if used:
                emit('DIAGNOSTIC_KEEP',{'used':True});return Proposal()
            used=True;p,decision=choose(evidence,loop._current.controller_overrides)
            emit('OBSERVATION_SOURCE_BEGIN',{'evidence':evidence,'proposal':p,'direct_decision':decision,'post_TD':loop.payload()})
            parent=dict(CONTEXT);CONTEXT.update({'phase':'private','candidate':'keep'})
            source=actor(NativeLoop,loop._current.clone(),loop._values,plan(1,case,True),loop.source_label+':native-source',forbid,False)
            loop.register_trial_source(source);emit('SOURCE_READY',{'state':source.payload(),'parent':loop.payload()})
            r=source.run_task(mask=mask);obs=source.issued_observation();pending['observation']=obs
            emit('SOURCE_COMPLETE',{'state':source.payload(),'return':returned(r),'observation_id':obs.observation_id})
            CONTEXT.clear();CONTEXT.update(parent);return p
        cls=NativeLoop if arm=='Legacy' else ConditionedObservationLoop
        loop=actor(cls,starts[case],values,plan(3,case),case+':'+arm,diagnose,True);emit('MAIN_INITIALIZED',{'state':loop.payload()});receipts=[]
        for e in range(3):
            r=loop.run_task(mask=mask);receipts.append(r)
            if 'observation' in pending:
                obs=pending.pop('observation');before=loop.payload();count=Counter(COUNTS)
                transfer=loop.consume_trial_observation(obs);after=loop.payload();delta={k:COUNTS[k]-count[k] for k in ('rollout','step','transaction')}
                accepted=after['external_updates']==before['external_updates']+1
                if arm=='Conditioned':assert type(transfer) is ObservationTransferResult and transfer.applied==accepted
                else:assert transfer is None and accepted
                emit('TRANSFER_RESULT',{'observation_id':obs.observation_id,'legacy_return_none':transfer is None,'typed_receipt':transfer,
                      'applied':accepted,'before':before,'after':after,'native_delta':delta,'main_closed':loop._failed})
                before_retry=loop.payload();count=Counter(COUNTS)
                try:loop.consume_trial_observation(obs)
                except ProtocolError as error:
                    assert before_retry==loop.payload() and count==COUNTS
                    emit('DUPLICATE_REJECTED',{'observation_id':obs.observation_id,'message':str(error),'native_delta':{k:COUNTS[k]-count[k] for k in ('rollout','step','transaction')},'state_unchanged':True})
                else:raise AssertionError('same native observation re-consumed')
            emit('POST_MAIN_STATE',{'epoch':e,'state':loop.payload()})
        vals=[returned(r) for r in receipts]
        row={'case':case,'arm':arm,'main_tasks':3,'successes':sum(r['terminal']=='SUCCESS' for r in receipts),'returns':vals,'outcomes':[r['terminal'] for r in receipts],
             'mean_return':sum(vals)/3,'observation_applied':accepted,'external_updates':loop._external_updates,'main_closed':loop._failed,'final_state':loop.payload()}
        emit('STREAM_ARM',row);summaries.append(row)
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
