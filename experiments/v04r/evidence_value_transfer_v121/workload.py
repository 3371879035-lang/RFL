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
sys.path[:0]=[str(HERE),str(HERE.parent/'factual_address_choice_v119'),str(HERE.parent/'learned_candidate_choice_v118'),str(ROOT/'src'),str(HERE.parent/'failure_only_orchestration'),
               str(PREP/'adaptive_training_v90')]

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod)
    return mod

load('v105_normal_td',PREP/'complete_curve_source_gates_v105/variants/normal/td.py')
L=load('v105_normal_learning',PREP/'complete_curve_source_gates_v105/variants/normal/learning.py')
import adaptive_training as A
from candidate_loop import CandidateTaskLoop
from selector import FrozenAddressSelector, available_actions, candidate, feature
from evidence_selector import EvidenceValueTrainer, evidence_key, historical_visible
from rfl_rebuild.env import kernel as K
from rfl_rebuild.b2.unaffected import EvaluationScene
from rfl_rebuild.learner.reference import QReferenceView
from rfl_rebuild.learner.store import (LearnerPersistentState, Q, DECISION, PROCESS,
                                      QAddress,DecisionAddress,Edit)

C=json.loads((HERE/'contract.json').read_bytes())
COUNTS=Counter();CONTEXT={};RECORDS=0;STREAM=None;START=time.monotonic();REFERENCE=None
CASES=C['held_out_cases']

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
    ref=QReferenceView(rows,name='v121-shared-unchanged-Q-prior')
    assert ref.digest()==spec['q_digest'];return ref

def plan(k,rank,n=3):
    episodes=tuple(L.EngineeringEpisode(e,k,1,K.SemanticTape(2,0,rank),
                         ((1<<64)-1,)*12,(((1<<64)-1,0),)*12) for e in range(n))
    return L.EngineeringPlan(episodes,(EvaluationScene(k,2,0,rank,1),),
        0.7642000000000008,A.LearningParameters(),'v121-finite-plan-not-keyed-qualification')

def start(mode,descriptor,kappa):
    prefix=descriptor['prefix'];x,y=descriptor['cell'];edits=[]
    for t in range(prefix,12):
        for m in (0,1):
            addr=DecisionAddress(K.State(x,y,t,kappa,2),1,m)
            edits.append(Edit(Q,QAddress(addr.state,1,m,K.WAIT),6.0) if mode=='dq'
                         else Edit(DECISION,addr,K.WAIT))
    sentinel=DecisionAddress(K.State(1,2,1,1-kappa,2),1,0)
    edits.append(Edit(Q,QAddress(sentinel.state,1,0,K.RIGHT),9.0) if mode=='dq'
                 else Edit(DECISION,sentinel,K.RIGHT))
    edits.append(Edit(PROCESS,3,2));state=LearnerPersistentState()
    emit('SOURCE_SETUP',{'mode':mode,'descriptor_audit_only':descriptor,'edits':edits,'before':A.stores(state)})
    state.apply_transaction(tuple(edits),q_reference=REFERENCE)
    emit('SOURCE_READY',{'stores':A.stores(state),'healthy':state.healthy})
    return state

def actor(initial,mode,p,diagnose,enabled,label):
    return CandidateTaskLoop(initial,mode=mode,role='treatment',source_label=label,
            reference=REFERENCE,plan=p,diagnose=diagnose,max_writes=12,emit=emit,
            diagnostic_enabled=enabled)



def returned(receipt):
    return float(sum(float.fromhex(s['reward']['binary64_hex']) for s in receipt['trace']['steps']))

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

def load_ordinal():
    record=json.loads((HERE.parent/'position_transfer_v120/frozen_parameters.json').read_bytes())
    data=(ROOT/record['source_raw']['path']).read_bytes()
    assert hashlib.sha256(data).hexdigest()==record['source_raw']['sha256']
    assert json.loads(data.splitlines()[record['source_record_seq']])['payload']['table']==record['table']
    model=FrozenAddressSelector(tuple((tuple(ft),a,n,float.fromhex(v['binary64_hex']),cost) for ft,a,n,v,cost in record['table']))
    emit('FROZEN_ORDINAL_PARAMETERS',{'model':model})
    return model,data


def historical_training(trainer,data):
    global CONTEXT
    facts={};branches={};n=0
    for line in data.splitlines():
        row=json.loads(line);tag,p,c=row['tag'],row['payload'],row['context']
        if c.get('phase')!='development':continue
        token=(c.get('mode'),c.get('scenario_audit_only'))
        if tag=='DEVELOPMENT_FACTUAL':facts[token]=p['receipt']
        elif tag=='TASK_COMPLETE' and c['arm']=='branch':branches.setdefault(token+(c['candidate'],),[]).append(p)
        elif tag=='VALUE_TRAINING_SAMPLE':
            factual=facts[token];assert factual['terminal']!='SUCCESS'
            evidence=historical_visible(factual);key=evidence_key(c['mode'],factual['terminal'],evidence,p['candidate'])
            receipts=branches[token+(p['candidate'],)];assert len(receipts)==2
            returns=tuple(returned(x) for x in receipts)
            assert returns==tuple(float.fromhex(x['binary64_hex']) for x in p['returns'])
            trainer.observe(key,returns)
            CONTEXT={'phase':'historical','mode':c['mode'],'scenario_audit_only':c['scenario_audit_only'],'arm':'dataset','candidate':p['candidate']}
            emit('HISTORICAL_VALUE_SAMPLE',{'source_seq':row['seq'],'key':key,'candidate':p['candidate'],'returns':returns})
            n+=1
    assert n==42


def developmental_training(trainer):
    global CONTEXT
    for mode in C['modes']:
        for descriptor in C['development_cases']:
            scenario='prefix'+str(descriptor['prefix'])
            CONTEXT={'phase':'development','mode':mode,'scenario_audit_only':scenario,'arm':'TaskTD'}
            initial=start(mode,descriptor,0);origin=actor(initial,mode,plan(0,6),lambda *_:None,False,'development:'+mode+':'+scenario)
            factual=origin.run_task();emit('DEVELOPMENT_FACTUAL',{'receipt':factual})
            if factual['terminal']=='SUCCESS':
                emit('SUCCESS_NO_MODEL_TRAINING',{});continue
            evidence=origin._last_evidence;snapshot=origin.payload()
            for action in available_actions(mode,evidence):
                CONTEXT={'phase':'development','mode':mode,'scenario_audit_only':scenario,'arm':'branch','candidate':action}
                proposal=candidate(mode,evidence,action);branch=ordinary_fork(origin,plan(0,6,n=2),proposal)
                receipts=[branch.run_task() for _ in range(2)];returns=tuple(returned(x) for x in receipts)
                key=evidence_key(mode,factual['terminal'],evidence,action);trainer.observe(key,returns)
                emit('VALUE_TRAINING_SAMPLE',{'key':key,'candidate':action,'returns':returns,'address_edits':len(proposal.edits),
                     'outcomes':[x['terminal'] for x in receipts],'source_post_TD_unchanged':origin.payload()==snapshot})
                assert origin.payload()==snapshot
    frozen=trainer.freeze();emit('FROZEN_EVIDENCE_MODEL',{'model':frozen})
    return frozen


def evaluate(ordinal,model):
    global CONTEXT
    rows=[];pins=(A.digest(A.wire(ordinal)),A.digest(A.wire(model)))
    for mode in C['modes']:
        for descriptor in CASES:
            scenario='prefix'+str(descriptor['prefix'])
            CONTEXT={'phase':'held_out','mode':mode,'scenario_audit_only':scenario,'arm':'setup'}
            initial=start(mode,descriptor,1);p=plan(1,7);initial_pin=A.digest(A.stores(initial))
            for arm in C['arms']:
                CONTEXT={'phase':'held_out','mode':mode,'scenario_audit_only':scenario,'arm':arm}
                def diagnose(terminal,evidence,budget):
                    if arm=='AlwaysClear':action='clear_factual';decision={'source':'unconditional-failure baseline'}
                    elif arm=='FrozenOrdinal':action,decision=ordinal.choose(mode,terminal,evidence)
                    else:action,decision=model.choose(mode,terminal,evidence)
                    proposal=candidate(mode,evidence,action);loop._selected_action=action
                    emit('SELECTION',{'arm':arm,'candidate':action,'proposal':proposal,'decision':decision,
                         'candidate_count':len(available_actions(mode,evidence))})
                    return proposal
                loop=actor(initial.clone(),mode,p,diagnose,arm!='TaskTD','heldout:'+mode+':'+scenario+':'+arm)
                factual=loop.run_task();loop._diagnostic_enabled=False
                future=[loop.run_task() for _ in range(2)];returns=[returned(x) for x in future]
                row={'mode':mode,'scenario_audit_only':scenario,'arm':arm,'initial_state_sha256':initial_pin,
                     'factual_terminal':factual['terminal'],'factual_return':returned(factual),'factual_steps':len(factual['trace']['steps']),
                     'selected_candidate':getattr(loop,'_selected_action',None),'decision':factual['route']['decision'],
                     'future_returns':returns,'future_outcomes':[x['terminal'] for x in future],'mean_future_return':sum(returns)/2,
                     'diagnostic_calls':factual['counters']['diagnostic_calls'],'diagnostic_edit_addresses':factual['counters']['diagnostic_edit_addresses'],
                     'diagnostic_transactions':factual['counters']['diagnostic_transactions'],
                     'actual_diagnostic_store_changed':factual['ordinary_after']['current']!=factual['after']['current'],'ordinary_updates':3}
                emit('EVALUATION_ARM',row);rows.append(row)
                assert (A.digest(A.wire(ordinal)),A.digest(A.wire(model)))==pins
    return rows


def main():
    global STREAM,REFERENCE
    STREAM=(HERE/'evidence/raw.jsonl').open('x',encoding='ascii',newline='\n')
    prior=sys.getprofile();ok=False
    try:
        REFERENCE=read_reference();emit('REFERENCE',{'digest':REFERENCE.digest(),'rows':len(REFERENCE)})
        sys.setprofile(profile)
        ordinal,data=load_ordinal();trainer=EvidenceValueTrainer()
        historical_training(trainer,data);model=developmental_training(trainer);rows=evaluate(ordinal,model)
        emit('RESULT',{'complete':True,'counts':dict(COUNTS),'evaluation':rows,'ordinal_model':ordinal,'evidence_model':model,
             'held_out_parameter_updates':0,'ordinary_parameters':A.LearningParameters(),'formal_collection':False,'new_keys':0})
        ok=True
    except BaseException as error:
        emit('FAILURE',{'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc(),'counts':dict(COUNTS),'complete':False})
        traceback.print_exc()
    finally:
        sys.setprofile(prior)
        emit('FINAL',{'complete':ok,'counts':dict(COUNTS),'profile_restored':sys.getprofile() is prior,'wall_seconds':time.monotonic()-START})
        STREAM.close()
    return 0 if ok else 1

if __name__=='__main__':raise SystemExit(main())
