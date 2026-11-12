"""New prospective finite learning/evaluation run, no old tests imported."""
from collections import Counter
from dataclasses import asdict
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
sys.path[:0]=[str(HERE),str(HERE.parent/'learned_candidate_choice_v118'),str(ROOT/'src'),str(HERE.parent/'failure_only_orchestration'),
               str(PREP/'adaptive_training_v90')]

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod)
    return mod

load('v105_normal_td',PREP/'complete_curve_source_gates_v105/variants/normal/td.py')
L=load('v105_normal_learning',PREP/'complete_curve_source_gates_v105/variants/normal/learning.py')
import adaptive_training as A
from candidate_loop import CandidateTaskLoop
from selector import available_actions, ValueTrainer, candidate, feature
from rfl_rebuild.env import kernel as K
from rfl_rebuild.b2.unaffected import EvaluationScene
from rfl_rebuild.learner.reference import QReferenceView
from rfl_rebuild.learner.store import (LearnerPersistentState, Q, DECISION, PROCESS,
                                      QAddress,DecisionAddress,Edit)

C=json.loads((HERE/'contract.json').read_bytes())
COUNTS=Counter();CONTEXT={};RECORDS=0;STREAM=None;START=time.monotonic();REFERENCE=None
OUTCOMES=('collision','timeout','external_trap','success')

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
    ref=QReferenceView(rows,name='v119-shared-unchanged-Q-prior')
    assert ref.digest()==spec['q_digest'];return ref

def plan(k,rank,n=3):
    episodes=tuple(L.EngineeringEpisode(e,k,1,K.SemanticTape(2,0,rank),
                         ((1<<64)-1,)*12,(((1<<64)-1,0),)*12) for e in range(n))
    return L.EngineeringPlan(episodes,(EvaluationScene(k,2,0,rank,1),),
        0.7642000000000008,A.LearningParameters(),'v119-finite-plan-not-keyed-qualification')

def start(mode,scenario,k,phase):
    qmag=(4.0 if phase=='development' else 6.0) if scenario=='collision' else (
          8.0 if phase=='development' else 6.0)
    edits=[];s=LearnerPersistentState()
    if scenario=='collision':
        address=DecisionAddress(K.State(1,2,1,k,2),1,0)
        edits.append(Edit(Q,QAddress(address.state,1,0,K.RIGHT),qmag) if mode=='dq'
                     else Edit(DECISION,address,K.RIGHT))
    elif scenario=='timeout':
        for t in range(12):
            for m in (0,1):
                address=DecisionAddress(K.State(0,2,t,k,2),1,m)
                edits.append(Edit(Q,QAddress(address.state,1,m,K.WAIT),qmag) if mode=='dq'
                             else Edit(DECISION,address,K.WAIT))
    elif scenario=='success' and mode=='dq':
        edits.append(Edit(Q,QAddress(K.State(0,2,0,k,2),1,0,K.RIGHT),2.0))
    if scenario in ('collision','timeout'):
        sentinel=DecisionAddress(K.State(1,2,1,1-k,2),1,0)
        edits.append(Edit(Q,QAddress(sentinel.state,1,0,K.RIGHT),9.0) if mode=='dq'
                     else Edit(DECISION,sentinel,K.RIGHT))
        edits.append(Edit(PROCESS,3,2))
    emit('SOURCE_SETUP',{'mode':mode,'scenario_audit_only':scenario,'phase':phase,
                         'kappa_audit_only':k,'edits':edits,'before':A.stores(s)})
    if edits:s.apply_transaction(tuple(edits),q_reference=REFERENCE)
    emit('SOURCE_READY',{'stores':A.stores(s),'healthy':s.healthy})
    mask=K.FaultMask(trap=K.Trap((1,2),0)) if scenario=='external_trap' else K.FaultMask()
    if scenario=='external_trap':assert s.healthy
    return s,mask

def actor(initial,mode,p,diagnose,enabled,label):
    return CandidateTaskLoop(initial,mode=mode,role='treatment',source_label=label,
            reference=REFERENCE,plan=p,diagnose=diagnose,max_writes=12,emit=emit,
            diagnostic_enabled=enabled)

def ordinary_fork(original,p,proposal):
    # Live clone from a real completed ordinary task. Not a reconstructed B1
    # source/pair/handle. Both R and L must survive this engineering fork.
    before=original.payload()
    branch=actor(original._current.clone(),original.mode,p,lambda *_:None,False,
                 original.source_label+':live-branch')
    if original._values is not None:branch._values=original._values.clone()
    branch._check();base=branch.payload()
    assert base['current']==before['current'] and base['learning_values']==before['learning_values']
    assert branch._current is not original._current and branch._immediate is not original._immediate
    if branch._values is not None:assert branch._values is not original._values
    emit('LIVE_BRANCH',{'source':before,'branch_before':base,'proposal':proposal})
    if proposal.action=='apply':
        assert 0<len(proposal.edits)<=12
        emit('PROBE_CANDIDATE_TX_BEGIN',{'before':branch.payload(),'edits':proposal.edits})
        cand=branch._current.clone();cand.apply_transaction(proposal.edits,q_reference=REFERENCE)
        branch._current=cand;branch._check()
        emit('PROBE_CANDIDATE_TX_END',{'after':branch.payload()})
    emit('LIVE_BRANCH_READY',{'after':branch.payload()})
    assert original.payload()==before
    return branch

def returned(receipt):
    return float(sum(float.fromhex(s['reward']['binary64_hex']) for s in receipt['trace']['steps']))

def developmental_training():
    global CONTEXT
    trainer=ValueTrainer();training=[]
    for mode in ('dq','patch-adaptive'):
        for scenario in OUTCOMES:
            CONTEXT={'phase':'development','mode':mode,'scenario_audit_only':scenario,'arm':'TaskTD'}
            initial,mask=start(mode,scenario,0,'development');p=plan(0,3)
            origin=actor(initial,mode,p,lambda *_:None,False,'development:'+mode+':'+scenario)
            factual=origin.run_task(mask=mask)
            emit('DEVELOPMENT_FACTUAL',{'receipt':factual})
            if factual['terminal']=='SUCCESS':
                assert origin._last_evidence is None
                emit('SUCCESS_NO_MODEL_TRAINING',{'mode':mode});continue
            evidence=origin._last_evidence;key=feature(mode,factual['terminal'],evidence)
            snapshot=origin.payload();case=[]
            for action in available_actions(mode,evidence):
                CONTEXT={'phase':'development','mode':mode,'scenario_audit_only':scenario,
                         'arm':'branch','candidate':action}
                proposal=candidate(mode,evidence,action)
                branch=ordinary_fork(origin,plan(0,3,n=2),proposal)
                outcomes=[]
                for _ in range(2):
                    rec=branch.run_task(mask=mask);outcomes.append(rec)
                returns=tuple(returned(x) for x in outcomes)
                trainer.observe(key,action,returns,len(proposal.edits))
                emit('VALUE_TRAINING_SAMPLE',{'feature':key,'candidate':action,'returns':returns,
                     'address_edits':len(proposal.edits),'outcomes':[x['terminal'] for x in outcomes],
                     'source_post_TD_unchanged':origin.payload()==snapshot})
                assert origin.payload()==snapshot
                case.append({'candidate':action,'returns':returns})
            training.append({'feature':key,'branches':case})
    frozen=trainer.freeze();emit('FROZEN_SELECTOR',{'table':frozen.table,'training':training})
    return frozen

def evaluate(model):
    global CONTEXT
    rows=[];model_before=A.digest(A.wire(model))
    for mode in ('dq','patch-adaptive'):
        for scenario in OUTCOMES:
            CONTEXT={'phase':'held_out','mode':mode,'scenario_audit_only':scenario,'arm':'setup'}
            initial,mask=start(mode,scenario,1,'held_out');p=plan(1,4);case=[]
            initial_pin=A.digest(A.stores(initial))
            for arm in C['declared_arms']:
                CONTEXT={'phase':'held_out','mode':mode,'scenario_audit_only':scenario,'arm':arm}
                def diagnose(terminal,evidence,budget):
                    if arm=='AlwaysClear':action='clear_factual';decision={'source':'unconditional-failure baseline'}
                    else:action,decision=model.choose(mode,terminal,evidence)
                    proposal=candidate(mode,evidence,action)
                    loop._selected_action=action
                    emit('SELECTION',{'arm':arm,'feature':feature(mode,terminal,evidence),
                         'decision':decision,'candidate':action,'proposal':proposal})
                    return proposal
                loop=actor(initial.clone(),mode,p,diagnose,arm!='TaskTD',
                           'held-out:'+mode+':'+scenario+':'+arm)
                assert A.digest(loop.payload()['current'])==initial_pin
                factual=loop.run_task(mask=mask)
                # Exactly one declared failure event is considered for repair.
                # Every arm then receives two identical ordinary continuations.
                loop._diagnostic_enabled=False
                future=[loop.run_task(mask=mask) for _ in range(2)]
                returns=[returned(x) for x in future]
                row={'mode':mode,'scenario_audit_only':scenario,'arm':arm,
                     'initial_state_sha256':initial_pin,'factual_terminal':factual['terminal'],
                     'factual_return':returned(factual),'decision':factual['route']['decision'],
                     'selected_candidate':getattr(loop,'_selected_action',None),
                     'future_returns':returns,'future_outcomes':[x['terminal'] for x in future],
                     'mean_future_return':sum(returns)/len(returns),
                     'diagnostic_calls':factual['counters']['diagnostic_calls'],
                     'diagnostic_edit_addresses':factual['counters']['diagnostic_edit_addresses'],
                     'diagnostic_transactions':factual['counters']['diagnostic_transactions'],
                     'actual_diagnostic_store_changed':factual['ordinary_after']['current']!=factual['after']['current'],
                     'ordinary_updates':1+len(future)}
                emit('EVALUATION_ARM',row);rows.append(row);case.append(row)
                assert A.digest(A.wire(model))==model_before
            assert len({(x['factual_terminal'],float(x['factual_return']).hex()) for x in case})==1
            assert len({x['initial_state_sha256'] for x in case})==1
    return rows,model_before

def main():
    global STREAM,REFERENCE
    STREAM=(HERE/'evidence/raw.jsonl').open('x',encoding='ascii',newline='\n')
    prior=sys.getprofile();ok=False
    try:
        REFERENCE=read_reference();emit('REFERENCE',{'digest':REFERENCE.digest(),'rows':len(REFERENCE)})
        sys.setprofile(profile)
        model=developmental_training();rows,pin=evaluate(model)
        assert COUNTS['rollout']<=C['budget']['rollout']
        emit('RESULT',{'complete':True,'counts':dict(COUNTS),'evaluation':rows,
             'frozen_selector':model,'frozen_selector_sha256':pin,'ordinary_parameters':A.LearningParameters(),
             'learned_causal_posterior':False,'formal_collection':False,'new_keys':0})
        ok=True
    except BaseException as error:
        emit('FAILURE',{'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc(),
                         'counts':dict(COUNTS),'complete':False})
        traceback.print_exc()
    finally:
        sys.setprofile(prior)
        emit('FINAL',{'complete':ok,'counts':dict(COUNTS),'profile_restored':sys.getprofile() is prior,
                      'wall_seconds':time.monotonic()-START})
        STREAM.close()
    return 0 if ok else 1

if __name__=='__main__':raise SystemExit(main())
