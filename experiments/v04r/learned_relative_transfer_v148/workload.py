"""Frozen learned relative value trained on old actual pairs, evaluated in a new coordinate."""
from collections import Counter
from pathlib import Path
import hashlib,importlib.util,json,sys,time,traceback
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];PREP=ROOT/'experiments/v03r/a96_dense/b2_prepare'
sys.path[:0]=[str(HERE),str(ROOT/'src'),str(HERE.parent/'mechanism_conditioned_experience_v147'),str(HERE.parent/'direct_controller_control_v145'),str(HERE.parent/'controller_horizon_value_v144'),str(HERE.parent/'learned_candidate_choice_v118'),str(HERE.parent/'failure_only_orchestration'),str(PREP/'adaptive_training_v90')]
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
    ref=QReferenceView(rows,name='v148-shared-unchanged-Q-prior')
    assert ref.digest()==spec['q_digest'];return ref

def returned(receipt):return sum(float.fromhex(s['reward']['binary64_hex']) for s in receipt['trace']['steps'])

def forbid(*args):raise AssertionError('private task must not diagnose')

def actor(cls,initial,values,p,label,diagnose,enabled):
    a=cls(initial,mode='patch-adaptive',role='treatment',source_label=label,reference=REFERENCE,plan=p,
          diagnose=diagnose,max_writes=1 if enabled else 0,emit=emit,diagnostic_enabled=enabled)
    a._values=values.clone();a._check();return a

load('v105_normal_td',PREP/'complete_curve_source_gates_v105/variants/normal/td.py')
L=load('v105_normal_learning',PREP/'complete_curve_source_gates_v105/variants/normal/learning.py')
import adaptive_training as A
import relative_model as M
from mechanism_loop import ObservationTaskLoop as NativeLoop
from conditioned_experience import ConditionedObservationLoop,ObservationTransferResult
from candidate_loop import Proposal
from direct_policy import choose as direct_choose
from value_policy import candidate,EmpiricalHorizonValue
from rfl_rebuild.env import kernel as K
from rfl_rebuild.b2.unaffected import EvaluationScene
from rfl_rebuild.learner.reference import QReferenceView
from rfl_rebuild.learner.store import LearnerPersistentState,DECISION,CONTROLLER,Edit,DecisionAddress


def plan(n,case,private=False):
    k,p=C['test_context'];episodes=[]
    for e in range(n):
        coins=[(1<<64)-1]*12
        if case=='protective' and e==(0 if private else 1):coins[0]=0
        episodes.append(L.EngineeringEpisode(e,k,1,K.SemanticTape(p,0,12),tuple(coins),((0,),)*12))
    return L.EngineeringPlan(tuple(episodes),(EvaluationScene(k,p,0,12,1),),.7642000000000008,A.LearningParameters(),
                            'v148-finite-private' if private else 'v148-new-main-stream')


def experiment():
    global CONTEXT
    CONTEXT={'phase':'model'};before_fit={k:COUNTS[k] for k in ('rollout','step','transaction')};assert not any(before_fit.values())
    points=M.read_training(ROOT,C['training_sources']);assert all(p['context']==C['training_context'] for p in points) and C['test_context']!=C['training_context']
    tree=M.fit(points);sealed=A.digest(A.wire(tree));model_file={'schema':'V148_FROZEN_RELATIVE_VALUE_TREE','points':points,'tree':tree,'wire_digest':sealed,'native_work_before_fit':before_fit}
    with (HERE/'frozen_model.json').open('x',encoding='utf-8',newline='\n') as f:json.dump(model_file,f,sort_keys=True,ensure_ascii=True,indent=2);f.write('\n')
    emit('FROZEN_RELATIVE_MODEL',model_file)
    k,p=C['test_context'];CONTEXT={'phase':'prep','case':'shared','arm':'shared'}
    seed=LearnerPersistentState();edits=(Edit(DECISION,DecisionAddress(K.State(0,2,0,k,p),1,0),3),)
    seed.apply_transaction(edits,q_reference=REFERENCE);emit('PREP_SEED',{'edits':edits,'state':A.stores(seed)})
    prep=actor(NativeLoop,seed,LearnerPersistentState(),plan(1,'prep'),'v148-common-actual-prep',forbid,False)
    mask=K.FaultMask(trap=K.Trap((1,2),0));r=prep.run_task(mask=mask)
    emit('PREPARATION_COMPLETE',{'receipt':r,'state':prep.payload()});current,values=prep._current,prep._values
    starts={}
    for case in C['cases']:
        CONTEXT={'phase':'source','case':case};state=current.clone();edits=()
        if case=='broken':edits=(Edit(CONTROLLER,K.ControllerSite(K.State(0,2,0,k,p),4),3),)
        if case=='protective':edits=(Edit(DECISION,DecisionAddress(K.State(0,2,0,k,p),1,0),3),
            Edit(CONTROLLER,K.ControllerSite(K.State(0,2,0,k,p),3),4),Edit(DECISION,DecisionAddress(K.State(1,2,2,k,p),1,0),3))
        before=A.stores(state)
        if edits:state.apply_transaction(edits,q_reference=REFERENCE)
        emit('SOURCE_CASE',{'before':before,'edits':edits,'state':A.stores(state),'values':A.stores(values)});starts[case]=state
    summaries=[]
    for case in C['cases']:
      mask=K.FaultMask(trap=K.Trap((1,2),0),plant=K.PlantFault(0,3) if case=='plant' else None)
      for arm in C['arms']:
        CONTEXT={'phase':'stream','case':case,'arm':arm};used=False;pending={};loop=None
        def diagnose(term,evidence,budget):
            nonlocal used
            if used:
                emit('DIAGNOSTIC_KEEP',{'used':True});return Proposal()
            used=True;base=loop.payload();proposal=candidate(evidence);x=M.features(A.wire(evidence),base['current'])
            assert A.digest(A.wire(tree))==sealed
            if arm=='NoWrite':chosen=Proposal()
            elif arm=='DirectSite':chosen=direct_choose(evidence,loop._current.controller_overrides)[0]
            elif arm=='FrozenLearned':
                prediction=M.predict(tree,x);chosen=proposal if prediction>0 and proposal is not None else Proposal()
                emit('FROZEN_PREDICTION',{'features':x,'predicted_delta':prediction,'proposal':chosen,'frozen_digest':sealed})
            else:chosen=None
            emit('DIAGNOSTIC_INPUT',{'evidence':evidence,'post_TD':base,'features':x,'candidate':proposal,'trial_horizon':2 if arm=='Validated' else 1})
            parent=dict(CONTEXT);observed={}
            menu=(('keep',Proposal()),('controller-delete',proposal)) if arm=='Validated' else (('keep',Proposal()),)
            for name,prop in menu:
                CONTEXT.update({'phase':'private','candidate':name});initial=loop._current.clone()
                if prop.edits:
                    old=A.stores(initial);initial.apply_transaction(prop.edits,q_reference=REFERENCE);emit('PRIVATE_EDIT',{'before':old,'edits':prop.edits,'after':A.stores(initial)})
                n=2 if arm=='Validated' else 1
                branch=actor(NativeLoop,initial,loop._values,plan(n,case,True),loop.source_label+':'+name,forbid,False)
                if name=='keep':loop.register_trial_source(branch)
                emit('PRIVATE_START',{'state':branch.payload(),'parent':base,'n':n});returns=[];first=None
                for j in range(n):
                    r=branch.run_task(mask=mask);returns.append(returned(r))
                    if name=='keep' and j==0:first=branch.issued_observation()
                if name=='keep':assert branch.issued_observation() is first;pending['observation']=first
                emit('PRIVATE_COMPLETE',{'returns':returns,'state':branch.payload(),'n':n});observed[name]=returns
                CONTEXT.clear();CONTEXT.update(parent)
            assert loop.payload()==base
            if arm=='Validated':
                value=EmpiricalHorizonValue(2);value.fit(observed);decision=value.choose();chosen=proposal if decision=='controller-delete' else Proposal()
                emit('ACTUAL_PAIRED_VALUE',{'model':value,'observed':observed,'choice':decision})
            emit('SELECTED_FEEDBACK',{'proposal':chosen,'features':x,'frozen_digest':sealed})
            return chosen
        loop=actor(ConditionedObservationLoop,starts[case],values,plan(6,case),case+':'+arm,diagnose,True)
        emit('MAIN_INITIALIZED',{'state':loop.payload()});receipts=[]
        for e in range(6):
            r=loop.run_task(mask=mask);receipts.append(r)
            if 'observation' in pending:
                obs=pending.pop('observation');before=loop.payload();count=Counter(COUNTS);transfer=loop.consume_trial_observation(obs)
                assert type(transfer) is ObservationTransferResult
                emit('TRANSFER_RESULT',{'receipt':transfer,'observation_id':obs.observation_id,'before':before,'after':loop.payload(),
                       'native_delta':{k:COUNTS[k]-count[k] for k in ('rollout','step','transaction')}})
            emit('POST_MAIN_STATE',{'epoch':e,'state':loop.payload()})
        vals=[returned(r) for r in receipts]
        row={'case':case,'arm':arm,'main_tasks':6,'successes':sum(r['terminal']=='SUCCESS' for r in receipts),'returns':vals,'outcomes':[r['terminal'] for r in receipts],
             'mean_return':sum(vals)/6,'external_updates':loop._external_updates,'final_state':loop.payload()}
        emit('STREAM_ARM',row);summaries.append(row)
    assert A.digest(A.wire(tree))==sealed
    emit('MODEL_STILL_FROZEN',{'digest':sealed,'new_value_labels_used_for_training':0})
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
