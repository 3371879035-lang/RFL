"""Actual candidate-trial observations enter mechanism-conditioned ordinary TD batches."""
from collections import Counter
from pathlib import Path
import hashlib,importlib.util,json,sys,time,traceback
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];PREP=ROOT/'experiments/v03r/a96_dense/b2_prepare'
sys.path[:0]=[str(HERE),str(HERE.parent/'observed_prefix_probe_v150'),str(HERE.parent/'stale_experience_exploration_v143'),str(ROOT/'src'),str(HERE.parent/'mechanism_conditioned_experience_v147'),str(HERE.parent/'direct_controller_control_v145'),str(HERE.parent/'controller_horizon_value_v144'),str(HERE.parent/'learned_candidate_choice_v118'),str(HERE.parent/'failure_only_orchestration'),str(PREP/'adaptive_training_v90')]
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
    ref=QReferenceView(rows,name='v151-unchanged-Q-prior')
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
from mechanism_loop import ObservationTaskLoop as NativeLoop
from candidate_loop import Proposal
from value_policy import candidate,EmpiricalHorizonValue
from rfl_rebuild.env import kernel as K
from rfl_rebuild.b2.unaffected import EvaluationScene
from rfl_rebuild.learner.reference import QReferenceView
from rfl_rebuild.learner.store import LearnerPersistentState,DECISION,CONTROLLER,Edit,DecisionAddress


from checkpoint import RecordedOrdinaryCheckpoint

from prefix_probe import compile_observed_prefix,literal_coordinates,assess_actual_reach

from intervention_experience import InterventionExperienceLoop,ProtocolError

def plan(n,case,*,main=False,spec=None):
    k,p=C['test_context'];episodes=[]
    for e in range(n):
        coins=[(1<<64)-1]*12;rejections=[(0,)]*12
        if main and case=='late_repair' and e==1:coins[:3]=[0]*3;rejections[:3]=[(1,),(0,),(0,)]
        if spec is not None:
            assert n==1;coins,rejections=literal_coordinates(spec)
        episodes.append(L.EngineeringEpisode(e,k,1,K.SemanticTape(p,0,12),tuple(coins),tuple(rejections)))
    return L.EngineeringPlan(tuple(episodes),(EvaluationScene(k,p,0,12,1),),.7642000000000008,A.LearningParameters(),
                            'v151-main' if main else 'v151-intervention-private')


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
    k,p=C['test_context'];sources={}
    for case in C['cases']:
        CONTEXT={'phase':'source','case':case};source=current.clone()
        site=K.ControllerSite(K.State(0,2,0,k,p),4) if case=='first_failure_then_gain' else K.ControllerSite(K.State(1,2,2,k,p),0)
        edits=(Edit(CONTROLLER,site,3),);before=A.stores(source);source.apply_transaction(edits,q_reference=REFERENCE)
        emit('SOURCE_CASE',{'before':before,'edits':edits,'state':A.stores(source),'values':A.stores(values)});sources[case]=source
    summaries=[]
    for case in C['cases']:
      mask=K.FaultMask(trap=K.Trap((1,2),0)) if case=='first_failure_then_gain' else K.FaultMask()
      for arm in C['arms']:
        CONTEXT={'phase':'stream','case':case,'arm':arm};used=False;pending={};loop=None
        def diagnose(term,evidence,budget):
            nonlocal used
            if used:emit('DIAGNOSTIC_KEEP',{'used':True});return Proposal()
            used=True;base=loop.payload();proposal=candidate(evidence);prefix=compile_observed_prefix(evidence);n=2 if case=='first_failure_then_gain' else 1
            emit('DIAGNOSTIC_INPUT',{'evidence':evidence,'post_TD':base,'candidate':proposal,'prefix':prefix,'horizon':n})
            parent=dict(CONTEXT);observed={};owned=[]
            for name,prop in (('keep',Proposal()),('controller-delete',proposal)):
                CONTEXT.update({'phase':'private','candidate':name})
                pp=plan(n,case,spec=prefix if n==1 else None)
                branch=loop.issue_branch(prop,plan=pp,label=loop.source_label+':'+name)
                emit('PRIVATE_START',{'state':branch.payload(),'parent':base,'n':n});returns=[];first=None
                for j in range(n):
                    receipt=branch.run_task(mask=mask);returns.append(returned(receipt))
                    if j==0:first=branch.owned_observation()
                assert branch.owned_observation() is first;owned.append(first)
                emit('PRIVATE_COMPLETE',{'returns':returns,'state':branch.payload(),'n':n,'first_task_target_reach':assess_actual_reach(prefix,branch.task_receipts[0]['trace'])})
                observed[name]=returns;CONTEXT.clear();CONTEXT.update(parent)
            assert loop.payload()==base
            value=EmpiricalHorizonValue(n);value.fit(observed);decision=value.choose();chosen=proposal if decision=='controller-delete' else Proposal()
            emit('ACTUAL_QUERY_VALUE',{'model':value,'observed':observed,'choice':decision,'horizon':n})
            pending['observations']=tuple(owned)
            emit('SELECTED_FEEDBACK',{'proposal':chosen,'target_index':prefix.target_index});return chosen
        loop=actor(InterventionExperienceLoop,sources[case],values,plan(6,case,main=True),case+':'+arm,diagnose,True)
        emit('MAIN_INITIALIZED',{'state':loop.payload()});receipts=[]
        for e in range(6):
            receipt=loop.run_task(mask=mask);receipts.append(receipt)
            if 'observations' in pending:
                observations=pending.pop('observations');requested=() if arm=='NoTrialLearning' else observations[:1] if arm=='KeepOnly' else observations[1:] if arm=='CandidateOnly' else observations
                before=loop.payload();count=Counter(COUNTS)
                if requested:
                    transfers=loop.consume_owned_batch(requested)
                    emit('BATCH_TRANSFER_RESULT',{'receipts':transfers,'observation_ids':[o.observation_id for o in requested],'before':before,'after':loop.payload(),
                        'native_delta':{k:COUNTS[k]-count[k] for k in ('rollout','step','transaction')}})
                    count=Counter(COUNTS);pre=loop.payload()
                    try:loop.consume_owned_batch(requested)
                    except ProtocolError as error:
                        assert loop.payload()==pre
                        emit('OWNED_DUPLICATE_REJECTED',{'error_type':type(error).__name__,'error':str(error),'observation_ids':[o.observation_id for o in requested],
                             'native_delta':{k:COUNTS[k]-count[k] for k in ('rollout','step','transaction')},'state_unchanged':True})
                    else:raise AssertionError('duplicate owned batch accepted')
                else:
                    emit('NO_TRIAL_INGESTION',{'observation_ids':[o.observation_id for o in observations],'before':before,'after':loop.payload(),'native_delta':{k:COUNTS[k]-count[k] for k in ('rollout','step','transaction')}})
            emit('POST_MAIN_STATE',{'epoch':e,'state':loop.payload()})
        vals=[returned(r) for r in receipts]
        row={'case':case,'arm':arm,'main_tasks':6,'successes':sum(r['terminal']=='SUCCESS' for r in receipts),'returns':vals,
             'outcomes':[r['terminal'] for r in receipts],'mean_return':sum(vals)/6,'external_updates':loop._external_updates,'final_state':loop.payload()}
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
