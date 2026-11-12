"""Frozen-model hard cases and targeted first-command diagnostic probes."""
from collections import Counter
from pathlib import Path
import hashlib,importlib.util,json,sys,time,traceback
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];PREP=ROOT/'experiments/v03r/a96_dense/b2_prepare'
sys.path[:0]=[str(HERE),str(HERE.parent/'learned_relative_transfer_v148'),str(HERE.parent/'stale_experience_exploration_v143'),str(ROOT/'src'),str(HERE.parent/'mechanism_conditioned_experience_v147'),str(HERE.parent/'direct_controller_control_v145'),str(HERE.parent/'controller_horizon_value_v144'),str(HERE.parent/'learned_candidate_choice_v118'),str(HERE.parent/'failure_only_orchestration'),str(PREP/'adaptive_training_v90')]
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
    ref=QReferenceView(rows,name='v149-unchanged-Q-prior')
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


from checkpoint import RecordedOrdinaryCheckpoint

def plan(n,case,private=False,replay_command=None):
    k,p=C['test_context'];episodes=[]
    for e in range(n):
        coins=[(1<<64)-1]*12;chi=0
        if case=='delayed_damage' and e==(0 if private else 1):coins[0]=0
        if replay_command is not None:
            assert n==1 and replay_command in (3,4)
            coins[0]=0;chi=(3,4).index(replay_command)
        rejections=[(0,)]*12;rejections[0]=(chi,)
        episodes.append(L.EngineeringEpisode(e,k,1,K.SemanticTape(p,0,12),tuple(coins),tuple(rejections)))
    return L.EngineeringPlan(tuple(episodes),(EvaluationScene(k,p,0,12,1),),.7642000000000008,A.LearningParameters(),
                            'v149-private' if private else 'v149-main')


def experiment():
    global CONTEXT
    CONTEXT={'phase':'model'}
    for spec in (C['frozen_model'],C['model_code'],*tuple(C['ordinary_checkpoint'][f] for f in ('raw','exit','review'))):
        b=(ROOT/spec['path']).read_bytes();assert len(b)==spec['bytes'] and hashlib.sha256(b).hexdigest()==spec['sha256']
    frozen=json.loads((ROOT/C['frozen_model']['path']).read_bytes());tree=frozen['tree'];sealed=frozen['wire_digest']
    assert A.digest(A.wire(tree))==sealed and not any(COUNTS.values());emit('REUSED_FROZEN_MODEL',{'model':frozen,'new_fit_calls':0})
    spec=C['ordinary_checkpoint'];old=json.loads((ROOT/spec['exit']['path']).read_bytes());review=json.loads((ROOT/spec['review']['path']).read_bytes())
    assert old['child_exit_code']==0 and old['input_bytes_unchanged'] and review['complete']
    records=[json.loads(s) for s in (ROOT/spec['raw']['path']).read_text(encoding='ascii').splitlines()]
    assert [r['seq'] for r in records]==list(range(len(records)))
    selected=[r for r in records if r['tag']==spec['selector']['tag']];assert len(selected)==1
    payload=selected[0]['payload']['state'];assert payload['completed_episodes']==1 and payload['external_updates']==0
    cp=RecordedOrdinaryCheckpoint(spec['raw']['sha256'],1,0,payload)
    CONTEXT={'phase':'checkpoint'};count=Counter(COUNTS);immediate,current,values=cp.materialize(REFERENCE)
    emit('RECORDED_ORDINARY_MATERIALIZED',{'source_seq':selected[0]['seq'],'source_raw_sha256':cp.raw_sha256,'recorded_payload':payload,
         'immediate':A.stores(immediate),'current':A.stores(current),'learning_values':A.stores(values),
         'native_delta':{k:COUNTS[k]-count[k] for k in ('rollout','step','transaction')},'restored_issued_identities':0})
    k,p=C['test_context'];starts={}
    for case in C['cases']:
        CONTEXT={'phase':'source','case':case};state=current.clone()
        if case=='delayed_damage':edits=(Edit(DECISION,DecisionAddress(K.State(0,2,0,k,p),1,0),3),Edit(CONTROLLER,K.ControllerSite(K.State(0,2,0,k,p),3),4))
        else:edits=(Edit(CONTROLLER,K.ControllerSite(K.State(0,2,0,k,p),4),3),)
        before=A.stores(state);state.apply_transaction(edits,q_reference=REFERENCE)
        emit('SOURCE_CASE',{'before':before,'edits':edits,'state':A.stores(state),'values':A.stores(values)});starts[case]=state
    summaries=[]
    for case in C['cases']:
      mask=(K.FaultMask(trap=K.Trap((2,1),3)) if case=='delayed_damage' else K.FaultMask(trap=K.Trap((1,2),0),plant=K.PlantFault(0,3)))
      for arm in C['arms']:
        CONTEXT={'phase':'stream','case':case,'arm':arm};used=False;pending={};loop=None
        def diagnose(term,evidence,budget):
            nonlocal used
            if used:emit('DIAGNOSTIC_KEEP',{'used':True});return Proposal()
            used=True;base=loop.payload();proposal=candidate(evidence);x=M.features(A.wire(evidence),base['current'])
            assert proposal is not None and A.digest(A.wire(tree))==sealed
            if arm=='NoWrite':chosen=Proposal()
            elif arm=='DirectSite':chosen=direct_choose(evidence,loop._current.controller_overrides)[0]
            elif arm=='FrozenLearned':
                prediction=M.predict(tree,x);chosen=proposal if prediction>0 else Proposal()
                emit('FROZEN_PREDICTION',{'features':x,'predicted_delta':prediction,'proposal':chosen,'frozen_digest':sealed})
            else:chosen=None
            emit('DIAGNOSTIC_INPUT',{'evidence':evidence,'post_TD':base,'features':x,'candidate':proposal,'trial_horizon':2 if arm=='Validated' else 1})
            parent=dict(CONTEXT);observed={};common=None;common_initial=None;common_returns=None
            def branch(name,prop,n,pplan,register=False):
                CONTEXT.update({'phase':'private','candidate':name});initial=loop._current.clone()
                if prop.edits:
                    old=A.stores(initial);initial.apply_transaction(prop.edits,q_reference=REFERENCE);emit('PRIVATE_EDIT',{'before':old,'edits':prop.edits,'after':A.stores(initial)})
                b=actor(NativeLoop,initial,loop._values,pplan,loop.source_label+':'+name,forbid,False)
                if register:loop.register_trial_source(b)
                initial_payload=b.payload();emit('PRIVATE_START',{'state':initial_payload,'parent':base,'n':n});vals=[];first=None
                for j in range(n):
                    receipt=b.run_task(mask=mask);vals.append(returned(receipt))
                    if register and j==0:first=b.issued_observation()
                if register:assert b.issued_observation() is first;pending['observation']=first
                emit('PRIVATE_COMPLETE',{'returns':vals,'state':b.payload(),'n':n})
                CONTEXT.clear();CONTEXT.update(parent)
                return b,initial_payload,vals
            n=2 if arm=='Validated' else 1
            common,common_initial,common_returns=branch('keep',Proposal(),n,plan(n,case,True),True);observed['keep']=common_returns
            if arm=='Validated':
                _,_,observed['controller-delete']=branch('controller-delete',proposal,2,plan(2,case,True))
                value=EmpiricalHorizonValue(2);value.fit(observed);decision=value.choose();chosen=proposal if decision=='controller-delete' else Proposal()
                emit('ACTUAL_PAIRED_VALUE',{'model':value,'observed':observed,'choice':decision})
            elif arm=='TargetedProbe':
                steps=evidence.steps;assert steps[0].a_cmd!=steps[0].a_realized
                command=steps[0].a_cmd;probe_plan=plan(1,case,True,command)
                proof={'episode_equal':common.plan.episodes==probe_plan.episodes,'parameters_equal':common.plan.parameters==probe_plan.parameters,
                     'same_reference_object':common.reference is REFERENCE,'mode_role_equal':(common.mode,common.role)==(loop.mode,loop.role),
                     'same_initial_R_L':all(common_initial[f]==base[f] for f in ('current','learning_values')),
                     'complete_one_task':common._completed==1 and not common._failed and not common._active}
                if all(proof.values()):
                    keep_value=common_returns[0]
                    emit('LIVE_KEEP_REUSE',{'proof':proof,'source_label':common.source_label,'episode':common.plan.episodes[0],
                         'initial':common_initial,'return':keep_value,'actual_trace':common.task_receipts[0]['trace'],'new_native_calls':0,'new_samples':0})
                else:
                    emit('LIVE_KEEP_NOT_REUSABLE',{'proof':proof,'desired_episode':probe_plan.episodes[0],'existing_episode':common.plan.episodes[0]})
                    _,_,vr=branch('probe-keep',Proposal(),1,probe_plan);keep_value=vr[0]
                _,_,vr=branch('probe-delete',proposal,1,plan(1,case,True,command));delete_value=vr[0]
                decision='controller-delete' if delete_value>keep_value else 'keep';chosen=proposal if decision=='controller-delete' else Proposal()
                emit('TARGETED_PROBE_VALUE',{'first_command':command,'keep_return':keep_value,'delete_return':delete_value,
                     'delta':delete_value-keep_value,'choice':decision,'estimand':'one-task-forced-first-factual-command-not-two-task-future-mean'})
            assert loop.payload()==base
            emit('SELECTED_FEEDBACK',{'proposal':chosen,'features':x,'frozen_digest':sealed});return chosen
        loop=actor(ConditionedObservationLoop,starts[case],values,plan(6,case),case+':'+arm,diagnose,True)
        emit('MAIN_INITIALIZED',{'state':loop.payload()});receipts=[]
        for e in range(6):
            receipt=loop.run_task(mask=mask);receipts.append(receipt)
            if 'observation' in pending:
                obs=pending.pop('observation');before=loop.payload();count=Counter(COUNTS);transfer=loop.consume_trial_observation(obs)
                assert type(transfer) is ObservationTransferResult
                emit('TRANSFER_RESULT',{'receipt':transfer,'observation_id':obs.observation_id,'before':before,'after':loop.payload(),
                     'native_delta':{k:COUNTS[k]-count[k] for k in ('rollout','step','transaction')}})
            emit('POST_MAIN_STATE',{'epoch':e,'state':loop.payload()})
        vals=[returned(r) for r in receipts]
        row={'case':case,'arm':arm,'main_tasks':6,'successes':sum(r['terminal']=='SUCCESS' for r in receipts),'returns':vals,
             'outcomes':[r['terminal'] for r in receipts],'mean_return':sum(vals)/6,'external_updates':loop._external_updates,'final_state':loop.payload()}
        emit('STREAM_ARM',row);summaries.append(row)
    assert A.digest(A.wire(tree))==sealed;emit('MODEL_STILL_FROZEN',{'digest':sealed,'new_value_labels_used_for_training':0})
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
