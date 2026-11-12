"""Actual cross-context witness counterexample and narrowed admission validation."""
from collections import Counter
from pathlib import Path
import hashlib,importlib.util,json,sys,time,traceback
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];PREP=ROOT/'experiments/v03r/a96_dense/b2_prepare'
V04=ROOT/'experiments/v04r'
sys.path[:0]=[str(HERE.parent),str(V04/'trial_derived_joint_repair_v153'),str(V04/'observed_prefix_probe_v150'),str(V04/'stale_experience_exploration_v143'),str(ROOT/'src'),str(V04/'mechanism_conditioned_experience_v147'),str(V04/'controller_horizon_value_v144'),str(V04/'learned_candidate_choice_v118'),str(V04/'failure_only_orchestration'),str(PREP/'adaptive_training_v90')]
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
    ref=QReferenceView(rows,name='v154-unchanged-Q-prior')
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

from evidence_loop import EvidenceExperienceLoop as LegacyEvidenceLoop,ProtocolError
from bound_agent import StrictTrialDerivedAgent
from contextlib import contextmanager

def main_plan():
    e=L.EngineeringEpisode(0,1,1,K.SemanticTape(3,0,12),((1<<64)-1,)*12,((0,),)*12)
    return L.EngineeringPlan((e,),(EvaluationScene(1,3,0,12,1),),.7642000000000008,A.LearningParameters(),'v154-bound-main')


def private_plan(view,prefix,n,greedy,foreign=False):
    coins,rejections=(((1<<64)-1,)*12,((0,),)*12) if greedy else literal_coordinates(prefix)
    episodes=tuple(L.EngineeringEpisode(e,view.kappa,1,K.SemanticTape(0 if foreign else view.phi,0,12),coins,rejections) for e in range(n))
    return L.EngineeringPlan(episodes,(EvaluationScene(1,0 if foreign else view.phi,0,12,1),),.7642000000000008,A.LearningParameters(),'v154-bound-private')


@contextmanager
def private_context(name):
    old=dict(CONTEXT);CONTEXT.update(phase='private',candidate=name)
    try:yield
    finally:CONTEXT.clear();CONTEXT.update(old)


def experiment():
    global CONTEXT
    spec=C['ordinary_checkpoint'];data=(ROOT/spec['raw']['path']).read_bytes();assert len(data)==spec['raw']['bytes'] and hashlib.sha256(data).hexdigest()==spec['raw']['sha256']
    for f in ('exit','review'):
        b=(ROOT/spec[f]['path']).read_bytes();assert len(b)==spec[f]['bytes'] and hashlib.sha256(b).hexdigest()==spec[f]['sha256']
    state=next(json.loads(line)['payload']['state'] for line in data.decode().splitlines() if json.loads(line)['tag']=='PREPARATION_COMPLETE')
    cp=RecordedOrdinaryCheckpoint(spec['raw']['sha256'],1,0,state);CONTEXT={'phase':'checkpoint'};immediate,current,values=cp.materialize(REFERENCE)
    emit('RECORDED_ORDINARY_MATERIALIZED',{'recorded_payload':state,'immediate':A.stores(immediate),'current':A.stores(current),'learning_values':A.stores(values),'materialization_TX':3})
    source=current.clone();edits=(Edit(DECISION,DecisionAddress(K.State(0,2,0,1,3),1,0),4),Edit(CONTROLLER,K.ControllerSite(K.State(0,2,0,1,3),4),3),Edit(CONTROLLER,K.ControllerSite(K.State(1,2,2,1,3),0),3))
    CONTEXT={'phase':'source'};before=A.stores(source);source.apply_transaction(edits,q_reference=REFERENCE);emit('SHARED_SOURCE',{'before':before,'edits':edits,'state':A.stores(source),'values':A.stores(values)})
    rows=[]
    for case in C['cases']:
        CONTEXT={'phase':'stream','arm':case,'main_epoch':0}
        foreign=case=='ForeignPlanAgent'
        def factory(view,prefix,n,greedy):return private_plan(view,prefix,n,greedy,foreign=foreign)
        agent=StrictTrialDerivedAgent(source,mode='patch-adaptive',role='treatment',source_label=case,reference=REFERENCE,plan=main_plan(),emit=emit,
            algorithm='TrialExpanded',trial_budget=5,private_plan_factory=factory,private_context=private_context)
        agent._values=values.clone();agent._check();emit('MAIN_INITIALIZED',{'state':agent.payload(),'MRO':[x.__name__ for x in type(agent).__mro__]})
        count=Counter(COUNTS)
        try:receipt=agent.run_observed_task(mask=K.FaultMask(trap=K.Trap((1,2),0)))
        except ProtocolError as error:
            assert foreign and agent._failed and not agent.task_receipts and not agent._owned_registry and not agent._trial_extensions and agent._completed==1
            row={'case':case,'main_complete':False,'expected_protocol_rejection':True,'error_type':type(error).__name__,'error':str(error),'closed':agent._failed,
                 'complete_receipts':len(agent.task_receipts),'registered_sources':len(agent._owned_registry),'authority_records':len(agent._trial_extensions),
                 'state':agent.payload(),'diagnostic_account':agent.diagnostic_account(),'native_delta':{k:COUNTS[k]-count[k] for k in ('rollout','step','transaction')}}
            emit('EXPECTED_PARTIAL_AGENT',row)
        else:
            assert not foreign
            row={'case':case,'main_complete':True,'expected_protocol_rejection':False,'receipt':receipt,'closed':agent._failed,'complete_receipts':len(agent.task_receipts),
                 'registered_sources':len(agent._owned_registry),'authority_records':len(agent._trial_extensions),'state':agent.payload(),'diagnostic_account':agent.diagnostic_account(),
                 'native_delta':{k:COUNTS[k]-count[k] for k in ('rollout','step','transaction')}}
            emit('VALID_BOUND_AGENT',row)
        assert agent.payload()['immediate']==A.stores(source);rows.append(row)
    return rows


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
