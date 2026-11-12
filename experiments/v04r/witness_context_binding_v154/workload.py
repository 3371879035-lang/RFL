"""Actual cross-context witness counterexample and narrowed admission validation."""
from collections import Counter
from pathlib import Path
import hashlib,importlib.util,json,sys,time,traceback
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];PREP=ROOT/'experiments/v03r/a96_dense/b2_prepare'
sys.path[:0]=[str(HERE),str(HERE.parent/'trial_derived_joint_repair_v153'),str(HERE.parent/'intervention_trial_learning_v151'),str(HERE.parent/'observed_prefix_probe_v150'),str(HERE.parent/'stale_experience_exploration_v143'),str(ROOT/'src'),str(HERE.parent/'mechanism_conditioned_experience_v147'),str(HERE.parent/'direct_controller_control_v145'),str(HERE.parent/'controller_horizon_value_v144'),str(HERE.parent/'learned_candidate_choice_v118'),str(HERE.parent/'failure_only_orchestration'),str(PREP/'adaptive_training_v90')]
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
from strict_witness import StrictWitnessLoop
from contextlib import contextmanager

def plan(view=None,*,phase=None):
    k,p=1,0
    if view is None:coins,rejections=((1<<64)-1,)*12,((0,),)*12
    else:
        k,p=view.kappa,view.phi;coins,rejections=literal_coordinates(compile_observed_prefix(view))
    if phase is not None:p=phase
    episode=L.EngineeringEpisode(0,k,1,K.SemanticTape(p,0,12),coins,rejections)
    return L.EngineeringPlan((episode,),(EvaluationScene(k,p,0,12,1),),.7642000000000008,A.LearningParameters(),'v154-single-native-episode')


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
    ex=json.loads((ROOT/spec['exit']['path']).read_bytes());review=json.loads((ROOT/spec['review']['path']).read_bytes());assert ex['child_exit_code']==0 and ex['input_bytes_unchanged'] and review['complete']
    records=[json.loads(s) for s in (ROOT/spec['raw']['path']).read_text().splitlines()];selected=[r for r in records if r['tag']=='PREPARATION_COMPLETE'];assert len(selected)==1
    payload=selected[0]['payload']['state'];cp=RecordedOrdinaryCheckpoint(spec['raw']['sha256'],1,0,payload)
    CONTEXT={'phase':'checkpoint'};counts=Counter(COUNTS);immediate,current,values=cp.materialize(REFERENCE)
    emit('RECORDED_ORDINARY_MATERIALIZED',{'source_seq':selected[0]['seq'],'source_raw_sha256':cp.raw_sha256,'recorded_payload':payload,'immediate':A.stores(immediate),'current':A.stores(current),'learning_values':A.stores(values),
         'native_delta':{k:COUNTS[k]-counts[k] for k in ('rollout','step','transaction')},'restored_issued_identities':0})
    CONTEXT={'phase':'source','arm':'shared'};source=current.clone()
    edits=(Edit(CONTROLLER,K.ControllerSite(K.State(0,2,0,1,0),4),3),Edit(CONTROLLER,K.ControllerSite(K.State(1,2,2,1,0),0),3),
       Edit(DECISION,DecisionAddress(K.State(0,2,0,1,3),1,0),4),Edit(CONTROLLER,K.ControllerSite(K.State(0,2,0,1,3),4),3),
       Edit(CONTROLLER,K.ControllerSite(K.State(3,4,10,0,5),4),0))
    before=A.stores(source);source.apply_transaction(edits,q_reference=REFERENCE);emit('SHARED_SOURCE',{'before':before,'edits':edits,'state':A.stores(source),'values':A.stores(values)})
    rows=[];mask=K.FaultMask(trap=K.Trap((1,2),0))
    for arm in C['cases']:
        CONTEXT={'phase':'stream','arm':arm,'main_epoch':0};loop=None;pending={}
        def diagnose(terminal,evidence,budget):
            first=candidate(evidence);prefix=compile_observed_prefix(evidence);base=loop.payload()
            emit('DIAGNOSTIC_INPUT',{'evidence':evidence,'post_TD':base,'candidate':first,'prefix':prefix})
            def run(name,proposal,view,foreign=False,legacy_registration=False):
                with private_context(name):
                    pp=plan(view,phase=3 if foreign else None)
                    factory=LegacyEvidenceLoop.issue_branch if legacy_registration else None
                    branch=factory(loop,proposal,plan=pp,label=arm+':'+name) if factory else loop.issue_branch(proposal,plan=pp,label=arm+':'+name)
                    emit('PRIVATE_START',{'state':branch.payload(),'parent':base,'n':1,'foreign_plan':foreign,'legacy_registration':legacy_registration})
                    receipt=branch.run_task(mask=mask);obs=branch.owned_observation()
                    emit('PRIVATE_COMPLETE',{'returns':[returned(receipt)],'state':branch.payload(),'n':1,'observation_id':obs.observation_id})
                    return branch,obs,returned(receipt)
            if arm in ('LegacyForeign','StrictForeign'):
                if arm=='StrictForeign':
                    count=Counter(COUNTS);pre=loop.payload();regbefore=len(loop._owned_registry)
                    try:loop.issue_branch(first,plan=plan(evidence,phase=3),label=arm+':foreign-factory-rejected')
                    except ProtocolError as error:
                        emit('STRICT_FACTORY_REJECTED',{'error_type':type(error).__name__,'error':str(error),'before':pre,'after':loop.payload(),
                           'registrations_before':regbefore,'registrations_after':len(loop._owned_registry),'native_delta':{k:COUNTS[k]-count[k] for k in ('rollout','step','transaction')}})
                    else:raise AssertionError('strict foreignfactory accepted')
                branch,observation,_=run('foreign',first,evidence,foreign=True,legacy_registration=arm=='StrictForeign')
                count=Counter(COUNTS);pre=loop.payload();authority_before=len(loop._trial_extensions)
                if arm=='LegacyForeign':
                    result=loop.extend_from_failed_trial(observation);assert result is not None
                    joint,view=result;loop.validate_evidenced_proposal(joint)
                    emit('LEGACY_FOREIGN_AUTHORIZED',{'observation':observation.audit(),'proposal':joint,'before':pre,'after':loop.payload(),
                         'authority_before':authority_before,'authority_after':len(loop._trial_extensions),'live_commit':False,
                         'native_delta':{k:COUNTS[k]-count[k] for k in ('rollout','step','transaction')}})
                else:
                    try:loop.extend_from_failed_trial(observation)
                    except ProtocolError as error:
                        emit('STRICT_WITNESS_REJECTED',{'observation':observation.audit(),'error_type':type(error).__name__,'error':str(error),'before':pre,'after':loop.payload(),
                           'authority_before':authority_before,'authority_after':len(loop._trial_extensions),'live_commit':False,
                           'native_delta':{k:COUNTS[k]-count[k] for k in ('rollout','step','transaction')}})
                    else:raise AssertionError('strict foreignwitness accepted')
                assert loop.payload()==base;return Proposal()
            first_source,observation,_=run('first',first,evidence)
            derived=loop.extend_from_failed_trial(observation);assert derived is not None;joint,view=derived
            baseline,keepobs,kv=run('baseline',Proposal(),view)
            treatment,jointobs,jv=run('joint',joint,view)
            assert baseline.plan.episodes==treatment.plan.episodes and baseline.plan.parameters==treatment.plan.parameters
            loop.validate_evidenced_proposal(joint)
            emit('STRICT_VALID_FLOW',{'proposal':joint,'witness':observation.audit(),'baseline_return':kv,'joint_return':jv,
                 'same_literal_episode':baseline.plan.episodes==treatment.plan.episodes,'same_parameters':True,'main_before':base,'main_after':loop.payload()})
            assert loop.payload()==base;pending['observations']=(keepobs,jointobs)
            return joint if jv>kv else Proposal()
        cls=LegacyEvidenceLoop if arm=='LegacyForeign' else StrictWitnessLoop
        loop=cls(source,mode='patch-adaptive',role='treatment',source_label=arm,reference=REFERENCE,plan=plan(),diagnose=diagnose,max_writes=2,emit=emit,diagnostic_enabled=True)
        loop._values=values.clone();loop._check();emit('MAIN_INITIALIZED',{'state':loop.payload(),'implementation':cls.__name__})
        receipt=loop.run_task(mask=mask)
        if 'observations' in pending:loop.consume_owned_batch(pending.pop('observations'))
        row={'case':arm,'receipt':receipt,'final_state':loop.payload(),'authority_records':len(loop._trial_extensions),'registered_sources':len(loop._owned_registry),
             'external_updates':loop._external_updates,'main_tasks':loop._completed}
        emit('CASE_FINAL',row);rows.append(row)
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
