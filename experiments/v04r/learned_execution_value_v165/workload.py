"""One persistent mixed-context loop perrole exercises both genuine feedback paths."""
from collections import Counter
from pathlib import Path
import hashlib,importlib.util,json,sys,time,traceback
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];PREP=ROOT/'experiments/v03r/a96_dense/b2_prepare'
sys.path[:0]=[str(HERE),str(HERE.parent/'policy_conditioned_query_v162'),str(HERE.parent/'matched_policy_query_v163'),str(HERE.parent/'unified_feedback_agent_v160'),str(HERE.parent/'current_path_reuse_v156'),str(HERE.parent/'alternate_entry_hypothesis_v159'),str(HERE.parent/'no_mismatch_failure_probe_v157'),str(HERE.parent/'witness_context_binding_v154'),str(HERE.parent/'trial_derived_joint_repair_v153'),str(HERE.parent/'intervention_trial_learning_v151'),str(HERE.parent/'observed_prefix_probe_v150'),str(HERE.parent/'stale_experience_exploration_v143'),str(ROOT/'src'),str(HERE.parent/'mechanism_conditioned_experience_v147'),str(HERE.parent/'direct_controller_control_v145'),str(HERE.parent/'controller_horizon_value_v144'),str(HERE.parent/'learned_candidate_choice_v118'),str(HERE.parent/'failure_only_orchestration'),str(PREP/'adaptive_training_v90')]
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
          'transaction' if p.endswith('rfl_rebuild/learner/store.py') and n=='apply_transaction' else
          'public_geometry' if p.endswith('/arrival_query.py') and n=='public_advance' else
          'query_features' if p.endswith('/query_value.py') and n=='query_features' else
          'query_model_fit' if p.endswith('/query_value.py') and n=='fit_query_value' else
          'execution_features' if p.endswith('/execution_value.py') and n=='execution_features' else None)
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
    ref=QReferenceView(rows,name='v165-unchanged-Q-prior')
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
from execution_agent import ExecutionQueryAgent
from execution_value import ExecutionFeatureData,execution_features
from query_value import QueryTrainingPoint,fit_query_value
from contextlib import contextmanager

def sequence(case):
    seq=[{**s,'local_epoch':j} for s in case['schedule'] for j in range(s['count'])];assert len(seq)==6;return seq


def main_plan(case):
    episodes=[]
    for e,s in enumerate(sequence(case)):
        coins=[(1<<64)-1]*12
        if s['force_start_right_at_local_epoch'] is not None and s['local_epoch']==s['force_start_right_at_local_epoch']:coins[0]=0
        episodes.append(L.EngineeringEpisode(e,s['kappa'],1,K.SemanticTape(s['phi'],0,12),tuple(coins),((0,),)*12))
    return L.EngineeringPlan(tuple(episodes),(EvaluationScene(1,0,0,12,1),),.7642000000000008,A.LearningParameters(),'v165-main')


def execution_plan(evidence,prefix,n,greedy):
    coins,rejections=(((1<<64)-1,)*12,((0,),)*12) if greedy else literal_coordinates(prefix)
    episodes=tuple(L.EngineeringEpisode(e,evidence.kappa,1,K.SemanticTape(evidence.phi,0,12),coins,rejections) for e in range(n))
    return L.EngineeringPlan(episodes,(EvaluationScene(evidence.kappa,evidence.phi,0,12,1),),.7642000000000008,A.LearningParameters(),'v165-current-private')


def query_plan(evidence,spec):
    coins,rejections=spec.literal_coordinates()
    ep=L.EngineeringEpisode(0,evidence.kappa,1,K.SemanticTape(evidence.phi,0,12),coins,rejections)
    return L.EngineeringPlan((ep,),(EvaluationScene(evidence.kappa,evidence.phi,0,12,1),),.7642000000000008,A.LearningParameters(),'v165-current-private')


@contextmanager
def private_context(name):
    old=dict(CONTEXT);CONTEXT.update(phase='private',candidate=name)
    try:yield
    finally:CONTEXT.clear();CONTEXT.update(old)


def read_models():
    from model_data import RecordedQueryModelPair
    spec=C['recorded_models']
    for name in ('raw','exit','review'):
        p=spec[name];data=(ROOT/p['path']).read_bytes();assert len(data)==p['bytes'] and hashlib.sha256(data).hexdigest()==p['sha256']
    assert json.loads((ROOT/spec['exit']['path']).read_bytes())['child_exit_code']==0 and json.loads((ROOT/spec['review']['path']).read_bytes())['complete']
    records=[json.loads(s) for s in (ROOT/spec['raw']['path']).read_text(encoding='ascii').splitlines()];selected=[x for x in records if x['tag']=='QUERY_VALUE_MODEL_FROZEN'];assert len(selected)==1
    parameters=selected[0]['payload'];models=RecordedQueryModelPair(spec['raw']['sha256'],parameters).materialize()
    assert A.wire(models)==parameters['models']
    emit('RECORDED_QUERY_MODELS',{'source_seq':selected[0]['seq'],'source_raw_sha256':spec['raw']['sha256'],'frozen_parameters':parameters,'materialized_models':models,'new_fit_calls':0,'restored_issued_identities':0})
    return models

def train_execution_model():
    for cfg in C['execution_training'].values():
        data=(ROOT/cfg['path']).read_bytes();assert len(data)==cfg['bytes'] and hashlib.sha256(data).hexdigest()==cfg['sha256']
    assert json.loads((ROOT/C['execution_training']['exit']['path']).read_bytes())['child_exit_code']==0
    assert json.loads((ROOT/C['execution_training']['review']['path']).read_bytes())['complete']
    rs=[json.loads(s) for s in (ROOT/C['execution_training']['raw']['path']).read_text(encoding='ascii').splitlines()]
    main={r['context']['main_epoch']:r['payload'] for r in rs if r['tag']=='TASK_COMPLETE' and r['context'].get('phase')=='stream' and r['context'].get('arm')=='PolicyUnified'}
    base={r['context']['main_epoch']:r['payload'] for r in rs if r['tag']=='TASK_COMPLETE' and r['context'].get('phase')=='stream' and r['context'].get('arm')=='TaskTD'}
    queries=[r for r in rs if r['tag']=='DIAGNOSTIC_INPUT' and r['context'].get('arm')=='PolicyUnified'];assert len(queries)==2
    def active(store,kk,phi):
        return {ch:store[ch] if ch=='P' else [v for v in store[ch] if (v['address']['state']['kappa'],v['address']['state']['phi'])==(kk,phi)] for ch in ('D','P','X','Q')}
    points=[];audit=[]
    for rec in queries:
        e=rec['context']['main_epoch'];p=rec['payload'];ev=p['evidence'];kk,phi=ev['kappa'],ev['phi']
        assert main[e]['trace']==base[e]['trace'] and active(main[e]['before']['current'],kk,phi)==active(base[e]['before']['current'],kk,phi)
        assert active(main[e]['before']['learning_values'],kk,phi)==active(base[e]['before']['learning_values'],kk,phi)
        data=ExecutionFeatureData.from_recorded(ev,main[e]['before']['learning_values'],p['post_TD']['learning_values']);x=execution_features(data,REFERENCE)
        future=[returned(main[j]) for j in range(e+1,e+4)];ordinary=[returned(base[j]) for j in range(e+1,e+4)]
        paid=sum(r['tag']=='TASK_COMPLETE' and r['context'].get('phase')=='private' and r['context'].get('arm')=='PolicyUnified' and r['context'].get('main_epoch')==e for r in rs)
        y=(sum(future)-sum(ordinary))/paid;points.append(QueryTrainingPoint(x,y));audit.append({'historical_seq':rec['seq'],'historical_epoch':e,'feature_data':data,'x':x,'future_main_returns':future,'ordinary_future_main_returns':ordinary,'paid_private_rollouts':paid,'gain_per_paid_probe':y})
    points=tuple(points);model=fit_query_value(points)
    emit('EXECUTION_MODEL_FROZEN',{'closed_training_points':points,'audit_only_training_sources':audit,'model':model,'refit_during_test':False})
    return model

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
    models=read_models();execution_model=train_execution_model();summaries=[]
    for case in C['cases']:
        CONTEXT={'phase':'source','case':case['name'],'arm':'shared'};initial_count=Counter(COUNTS);source=current.clone();edits=[]
        for item in case['edits']:
            ad=item['address'];st=K.State(**ad['state']);address=DecisionAddress(st,ad['z'],ad['m']) if item['store']=='decision' else K.ControllerSite(st,ad['cmd'])
            edits.append(Edit(item['store'],address,item['value']))
        before=A.stores(source);source.apply_transaction(tuple(edits),q_reference=REFERENCE)
        emit('SHARED_SOURCE',{'before':before,'edits':tuple(edits),'state':A.stores(source),'values':A.stores(values)})
        case_rows=[]
        for arm in C['arms']:
            CONTEXT={'phase':'stream','case':case['name'],'arm':arm}
            loop=ExecutionQueryAgent(source,mode='patch-adaptive',role='treatment',source_label=case['name']+':'+arm,reference=REFERENCE,plan=main_plan(case),emit=emit,
                algorithm=arm,learning_values=values,event_enabled=arm!='TaskTD',query_value_model=models['policy'],value_gate_enabled=arm!='TaskTD',execution_value_model=execution_model,execution_gate_enabled=arm=='AllQueryGate',trial_budget=0 if arm=='TaskTD' else C['trial_task_budget_each_feedback_arm'],private_plan_factory=execution_plan,query_plan_factory=query_plan,public_transition_budget=C['public_transitions_per_proposal'],private_context=private_context)
            emit('MAIN_INITIALIZED',{'state':loop.payload(),'diagnostic_account':loop.diagnostic_account(),'configuration':loop.configuration()});receipts=[]
            for e,spec in enumerate(sequence(case)):
                CONTEXT['main_epoch']=e;mask=K.FaultMask(trap=K.Trap(tuple(spec['trap']['cell']),spec['trap']['t']))
                emit('RUNNER_CONTEXT',{'epoch':e,'stage_audit_only':spec['label'],'kappa':spec['kappa'],'phi':spec['phi']})
                receipt=loop.run_observed_task(mask=mask);receipts.append(receipt);assert loop.payload()['immediate']==A.stores(source)
            vals=[returned(x) for x in receipts];row={'case':case['name'],'arm':arm,'main_tasks':6,'successes':sum(x['terminal']=='SUCCESS' for x in receipts),'returns':vals,'outcomes':[x['terminal'] for x in receipts],
                 'mean_return':sum(vals)/6,'external_updates':loop._external_updates,'final_state':loop.payload(),'diagnostic_account':loop.diagnostic_account()}
            emit('AGENT_FINAL',row);summaries.append(row);case_rows.append(row)
        emit('CASE_RESULT',{'case':case['name'],'complete':True,'counts':{k:v-initial_count[k] for k,v in COUNTS.items() if v-initial_count[k]},'streams':case_rows})

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
