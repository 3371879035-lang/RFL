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
sys.path[:0]=[str(HERE),str(HERE.parent/'evidence_value_transfer_v121'),str(HERE.parent/'factual_address_choice_v119'),str(HERE.parent/'learned_candidate_choice_v118'),str(ROOT/'src'),str(HERE.parent/'failure_only_orchestration'),
               str(PREP/'adaptive_training_v90')]

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod)
    return mod

load('v105_normal_td',PREP/'complete_curve_source_gates_v105/variants/normal/td.py')
L=load('v105_normal_learning',PREP/'complete_curve_source_gates_v105/variants/normal/learning.py')
import adaptive_training as A
from observation_loop import ObservationTaskLoop as CandidateTaskLoop, ProtocolError
from selector import FrozenAddressSelector, available_actions, candidate as original_candidate, feature
from evidence_selector import FrozenEvidenceSelector
from practice_policy import ambiguous_singles, choose_actual
from probe_policy import probe_order, needs_alternate
from diagnostic_memory import DiagnosticMemory, memory_key
from frozen_memory import FrozenMemory
from trial_memory import TrialMemory
from trial_replay import build_replay, replay_memory_key
from policy_equivalence import compare_to_keep
from mode_neutral_candidates import memory_menu
from memory_policy import reconsider, conflicting_keys
from failure_review import requires_review
from rfl_rebuild.env import kernel as K
from rfl_rebuild.b2.unaffected import EvaluationScene
from rfl_rebuild.learner.reference import QReferenceView
from rfl_rebuild.learner.store import (LearnerPersistentState, Q, DECISION, PROCESS,
                                      QAddress,DecisionAddress,Edit)

C=json.loads((HERE/'contract.json').read_bytes())
COUNTS=Counter();CONTEXT={};RECORDS=0;STREAM=None;START=time.monotonic();REFERENCE=None
SCHEDULES=C['schedules']

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
    ref=QReferenceView(rows,name='v141-shared-unchanged-Q-prior')
    assert ref.digest()==spec['q_digest'];return ref

def plan(case_id):
    episodes=tuple(L.EngineeringEpisode(e,item['kappa'],1,K.SemanticTape(item['phi'],0,12),
                         ((1<<64)-1,)*12,(((1<<64)-1,0),)*12) for e,item in enumerate(SCHEDULES[case_id]))
    scenes=tuple(EvaluationScene(x['kappa'],x['phi'],0,12,1) for x in C['retention_scenes'])
    return L.EngineeringPlan(episodes,scenes,0.7642000000000008,A.LearningParameters(),
                             'v141-finite-recurrent-stream-not-keyed-qualification')

def start(mode,case_id):
    cfg=C['cases'][case_id];edits=[]
    for d in cfg['sources']:
        kappa=d['kappa'];x,y=d['cell']
        for t in range(d['prefix'],12):
            for m in (0,1):
                a=DecisionAddress(K.State(x,y,t,kappa,d['phi']),1,m)
                edits.append(Edit(Q,QAddress(a.state,1,m,K.WAIT),6.0) if mode=='dq' else Edit(DECISION,a,K.WAIT))
    for t in cfg['prefix_wait_source']['times']:
        for m in (0,1):
            a=DecisionAddress(K.State(0,2,t,cfg['prefix_wait_source']['kappa'],cfg['prefix_wait_source']['phi']),1,m)
            edits.append(Edit(Q,QAddress(a.state,1,m,K.WAIT),6.0) if mode=='dq' else Edit(DECISION,a,K.WAIT))
    script=cfg['scripted_source']
    for item in script['entries']:
        for m in (0,1):
            a=DecisionAddress(K.State(item['x'],item['y'],item['t'],item.get('kappa',script['kappa']),item.get('phi',script['phi'])),1,m)
            edits.append(Edit(Q,QAddress(a.state,1,m,item['action']),6.0) if mode=='dq' else Edit(DECISION,a,item['action']))
    a=DecisionAddress(K.State(1,2,1,0,4),1,0)
    edits.append(Edit(Q,QAddress(a.state,1,0,K.RIGHT),9.0) if mode=='dq' else Edit(DECISION,a,K.RIGHT))
    edits.append(Edit(PROCESS,3,2));state=LearnerPersistentState()
    emit('SOURCE_SETUP',{'mode':mode,'case':case_id,'edits':edits,'before':A.stores(state)})
    state.apply_transaction(tuple(edits),q_reference=REFERENCE)
    emit('SOURCE_READY',{'case':case_id,'stores':A.stores(state),'healthy':state.healthy})
    return state

def actor(initial,mode,p,diagnose,enabled,label):
    return CandidateTaskLoop(initial,mode=mode,role='treatment',source_label=label,
            reference=REFERENCE,plan=p,diagnose=diagnose,max_writes=12,emit=emit,
            diagnostic_enabled=enabled)



def returned(receipt):
    return float(sum(float.fromhex(s['reward']['binary64_hex']) for s in receipt['trace']['steps']))

def models():
    record=json.loads((HERE/'parameters.json').read_bytes())
    for field in ('evidence_source','ordinal_source'):
        item=record[field];data=(ROOT/item['path']).read_bytes()
        assert len(data)==item['bytes'] and hashlib.sha256(data).hexdigest()==item['sha256']
        if field=='evidence_source':
            r=json.loads(data.splitlines()[record['source_seq']])
            assert r['tag']=='FROZEN_EVIDENCE_MODEL' and r['payload']['model']==record['evidence_model']
        else:assert json.loads(data)['table']==record['ordinal_model']['table']
    ordinal=FrozenAddressSelector(tuple((tuple(k),a,n,float.fromhex(v['binary64_hex']),cost) for k,a,n,v,cost in record['ordinal_model']['table']))
    evidence=FrozenEvidenceSelector(tuple((tuple(k),n,float.fromhex(v['binary64_hex'])) for k,n,v in record['evidence_model']['table']))
    emit('FROZEN_MODELS',{'ordinal':ordinal,'evidence':evidence})
    return ordinal,evidence


def retention(loop,completed):
    before=loop.payload();base=Counter(COUNTS)
    snap=loop._current.snapshot();command=loop._greedy();results=[]
    for scene in C['retention_scenes']:
        kappa=scene['kappa'];phi=scene['phi']
        raw=K.rollout(kappa=kappa,tape=K.SemanticTape(phi,0,12),base_option=1,
                      command_provider=command,controller=snap.controller_mapping(),
                      learner_process_commit=snap.process_commit_provider(),reward_mode='A')
        results.append({'kappa':kappa,'phi':phi,'trace':raw,'return_hex':raw.return_value.hex()})
    after=loop.payload();delta={k:COUNTS[k]-base[k] for k in ('rollout','step','transaction')}
    emit('RETENTION_BANK',{'completed_tasks':completed,'before':before,'after':after,'results':results,
                          'native_delta':delta,'draws':0,'TD':0,'diagnostic_calls':0})
    assert before==after and delta['rollout']==len(C['retention_scenes']) and delta['transaction']==0


def practice_plan(kappa,phi,n):
    episodes=tuple(L.EngineeringEpisode(i,kappa,1,K.SemanticTape(phi,0,12),
                  ((1<<64)-1,)*12,(((1<<64)-1,0),)*12) for i in range(n))
    return L.EngineeringPlan(episodes,(EvaluationScene(kappa,phi,0,12,1),),0.7642000000000008,
                             A.LearningParameters(),'v141-current-condition-practice-not-future-stream')


def proposal_for(origin,visible,action):
    return origin._replay_candidates[action].proposal if action in origin._replay_candidates else original_candidate(origin.mode,visible,action)


def event_key(origin,terminal,visible,action):
    if action in origin._replay_candidates:return replay_memory_key(origin.mode,terminal,visible,origin._replay_candidates[action])
    return origin._memory.key(origin.mode,terminal,visible,action)


def maybe_practice(origin,terminal,visible,chosen,decision,current_mask):
    global CONTEXT
    if origin._entry=='mode-neutral-family':
        inventory=memory_menu(origin.mode,terminal,visible,origin._catalog)
        emit('MEMORY_CANDIDATES',{'epoch':origin._completed-1,'inventory':inventory,'table':origin._memory.snapshot()})
        decision=dict(decision,entry_inventory=inventory)
        singles,eligible=inventory.actions[1:],inventory.eligible
        if not singles:return 'keep',dict(decision,practice_status='no-supported-family',eligible=eligible)
    else:
        singles,eligible=ambiguous_singles(chosen,decision)
        if not singles:return chosen,dict(decision,practice_status='no-ambiguity',eligible=eligible)
    menu=('keep',)+singles;policy=origin._policy;recalled=None;info=None
    if origin._practice_used>=C['practice']['event_cap']:return ('keep' if origin._entry=='mode-neutral-family' else chosen),dict(decision,practice_status='budget-exhausted',eligible=eligible)
    origin._practice_used+=1;parent_context=dict(CONTEXT);before=origin.payload();epoch=origin._completed-1
    base_count=Counter(COUNTS)
    proofs=tuple(compare_to_keep(origin,proposal_for(origin,visible,a),a) for a in menu if a!='keep')
    pruned=tuple(p.action for p in proofs if p.equivalent_to_keep)
    order=tuple(a for a in menu if a not in pruned)
    proof_delta={k:COUNTS[k]-base_count[k] for k in ('rollout','step','transaction')}
    emit('POLICY_KEEP_EQUIVALENCE',{'epoch':epoch,'before':before,'after':origin.payload(),'menu':menu,
         'comparisons':proofs,'pruned':pruned,'representatives':order,'native_delta':proof_delta,
         'scope':'current-frozen-policy-one-episode-only','samples_fabricated':False})
    assert before==origin.payload() and not any(proof_delta.values())
    extra=None;strategy='keep-equivalence-plus-trial-replay';n=1;order=list(order)
    emit('PRACTICE_BEGIN',{'parent_epoch':epoch,'event_number':origin._practice_used,'eligible':eligible,'actions':menu,
         'before':before,'frozen_choice':chosen,'frozen_decision':decision,'strategy':strategy,'hypothesis':recalled,
         'execution_order':order,'episodes_per_branch':n,'comparison_candidate':extra,'policy_pruned':pruned})
    returns={};costs={};observed={}
    try:
        for action in order:
            if strategy=='verify-one' and action not in ('keep',recalled) and not needs_alternate(observed,recalled) and action!=extra:break
            CONTEXT={'phase':'practice','mode':origin.mode,'arm':parent_context['arm'],'candidate':action,'scenario_audit_only':str(epoch),'case':parent_context['case']}
            proposal=proposal_for(origin,visible,action)
            branch=actor(origin._current.clone(),origin.mode,practice_plan(visible.kappa,visible.phi,n),lambda *_:None,False,
                         origin.source_label+':practice:'+str(epoch)+':'+action)
            if origin._values is not None:branch._values=origin._values.clone()
            branch._check()
            assert branch._current is not origin._current and branch._immediate is not origin._immediate
            assert branch.payload()['current']==before['current'] and branch.payload()['learning_values']==before['learning_values']
            if branch._values is not None:assert branch._values is not origin._values
            emit('PRACTICE_BRANCH',{'parent_epoch':epoch,'origin':before,'branch_before':branch.payload(),'proposal':proposal})
            if proposal.action=='apply':
                emit('PRACTICE_TX_BEGIN',{'before':branch.payload(),'edits':proposal.edits})
                state=branch._current.clone();state.apply_transaction(proposal.edits,q_reference=REFERENCE)
                branch._current=state;branch._check();emit('PRACTICE_TX_END',{'after':branch.payload()})
            if action=='keep':origin.register_trial_source(branch)
            results=[branch.run_task(mask=current_mask) for _ in range(n)]
            if action=='keep':origin._pending_trial_observations.append(branch.issued_observation())
            returns[action]=tuple(returned(r) for r in results);costs[action]=len(proposal.edits)
            observed[action]=(results[0]['terminal'],returns[action][0])
            emit('PRACTICE_SAMPLE',{'parent_epoch':epoch,'candidate':action,'returns':returns[action],
                 'outcomes':[r['terminal'] for r in results],'cost':costs[action]})
            assert origin.payload()==before
            if action=='keep' and branch._last_evidence is not None:
                replay=build_replay(origin.mode,visible,branch._last_evidence)
                if replay is not None:
                    assert replay.action not in menu
                    origin._replay_candidates[replay.action]=replay
                    unsupported=compare_to_keep(origin,replay.proposal,replay.action)
                    assert not unsupported.supported and not unsupported.equivalent_to_keep
                    emit('TRIAL_REPLAY_PROPOSED',{'parent_epoch':epoch,'origin':before,'factual_evidence':visible,
                         'probe_evidence':branch._last_evidence,'candidate':replay,'proof':unsupported,
                         'from_actual_private_action':'keep','from_actual_private_terminal':results[0]['terminal']})
                    menu=menu+(replay.action,);order.append(replay.action)
    finally:CONTEXT=parent_context
    tested=tuple(returns);canonical=tuple(a for a in menu if a in returns)
    selected,means=choose_actual(returns,costs,canonical);unprobed=tuple(a for a in menu if a not in returns)
    emit('PRACTICE_END',{'parent_epoch':epoch,'before':before,'after':origin.payload(),'actions':tested,'canonical_menu':menu,
         'unprobed':unprobed,'returns':returns,'means':means,'costs':costs,'selected':selected,'strategy':strategy,'policy_pruned':pruned})
    assert origin.payload()==before
    samples=[{'key':event_key(origin,terminal,visible,a),'returns':returns[a]} for a in tested]
    previous_memory=origin._memory.snapshot()
    if origin._memory_kind in ('trial-observations',):
        for item in samples:origin._memory.observe(item['key'],item['returns'])
        origin._memory_train_events+=1
        emit('MEMORY_UPDATE',{'epoch':epoch,'before':previous_memory,'after':origin._memory.snapshot(),'samples':samples,'trained':True})
    else:emit('FROZEN_PRACTICE_LABELS',{'epoch':epoch,'before':previous_memory,'after':origin._memory.snapshot(),'samples':samples,'trained':False})
    previous=tuple(sorted(origin._needs_retest));tested_keys={event_key(origin,terminal,visible,a) for a in tested}
    origin._needs_retest.difference_update(tested_keys)
    emit('RETEST_COMPLETED',{'epoch':epoch,'before':previous,'after':tuple(sorted(origin._needs_retest)),'tested_keys':tuple(sorted(tested_keys))})
    keys={a:event_key(origin,terminal,visible,a) for a in tested};conflicts=conflicting_keys(keys,returns);previous=tuple(sorted(origin._contested))
    origin._contested.update(conflicts)
    emit('MEMORY_CONFLICT_UPDATE',{'epoch':epoch,'before':previous,'after':tuple(sorted(origin._contested)),
         'conflicts':[{'key':k,'action_means':v} for k,v in sorted(conflicts.items())]})
    if recalled is not None and selected==recalled:
        origin._current_claim={'epoch':epoch,'context':(visible.kappa,visible.phi),'candidate':recalled,
                               'key':info['keys'][recalled],'predicted_mean':info['scores'][recalled]}
    return selected,dict(decision,practice_status='completed',frozen_choice=chosen,practice_means=means,
                         practice_actions=tested,practice_menu=menu,unprobed=unprobed,eligible=eligible,policy_pruned=pruned)



def experiment(ordinal,evidence):
    global CONTEXT
    rows=[];pins=(A.digest(A.wire(ordinal)),A.digest(A.wire(evidence)))
    recorded=json.loads((HERE/'frozen_diagnostic.json').read_bytes());emit('HISTORICAL_FAMILY_CATALOG',recorded)
    for mode in C['modes']:
        initials={}
        for case_id in C['cases']:
            CONTEXT={'phase':'stream','mode':mode,'arm':'setup:'+case_id,'case':case_id}
            initials[case_id]=start(mode,case_id)
        for arm in C['arms']:
            spec=C['roles'][arm];case_id=spec['case'];policy=spec['policy']
            initial=initials[case_id];initial_pin=A.digest(A.stores(initial))
            CONTEXT={'phase':'stream','mode':mode,'arm':arm,'case':case_id}
            def diagnose(terminal,visible,budget):
                if policy!='task' and loop._pending_claim is not None:
                    previous_keys=tuple(sorted(loop._needs_retest))
                    review=requires_review(loop._pending_claim,loop._completed-1,terminal,(visible.kappa,visible.phi))
                    if review:loop._needs_retest.add(loop._pending_claim['key'])
                    emit('PREDICTION_REVIEW',{'epoch':loop._completed-1,'terminal':terminal,'context':(visible.kappa,visible.phi),
                         'pending':loop._pending_claim,'requires_retest':review,'before':previous_keys,
                         'after':tuple(sorted(loop._needs_retest)),'memory_unchanged':loop._memory.snapshot()})
                action,decision=evidence.choose(mode,terminal,visible)
                if policy!='task':
                    action,decision=maybe_practice(loop,terminal,visible,action,decision,mask)
                measured_winner=action
                if not spec['apply_literal_repair']:action='keep'
                decision=dict(decision,measured_winner=measured_winner,force_no_write=not spec['apply_literal_repair'])
                proposal=proposal_for(loop,visible,action)
                emit('SELECTION',{'arm':arm,'candidate':action,'proposal':proposal,'decision':decision,
                     'candidate_count':len(available_actions(mode,visible))+len(loop._replay_candidates)})
                return proposal
            loop=actor(initial.clone(),mode,plan(case_id),diagnose,policy!='task','stream:'+mode+':'+arm)
            assert A.digest(loop.payload()['current'])==initial_pin
            loop._policy=policy;loop._entry=spec['entry'];loop._investigation=spec['investigation']
            loop._practice_used=0
            loop._memory_kind=spec['memory'];loop._memory_train_events=0
            loop._memory=TrialMemory();loop._replay_candidates={};loop._pending_trial_observations=[]
            loop._catalog=tuple(tuple(x['key']) for x in recorded['recorded_practice_examples'])
            frozen_weights=None
            loop._memory_hits=0;loop._contested=set()
            loop._needs_retest=set();loop._pending_claim=None;loop._current_claim=None
            receipts=[]
            for e,item in enumerate(SCHEDULES[case_id]):
                mask=K.FaultMask(trap=K.Trap((1,2),0)) if item['trap'] else K.FaultMask()
                loop._current_claim=None;loop._replay_candidates={};loop._pending_trial_observations=[]
                receipt=loop.run_task(mask=mask);receipts.append(receipt)
                for observation in loop._pending_trial_observations:
                    loop.consume_trial_observation(observation)
                    unchanged=loop.payload();count=Counter(COUNTS)
                    try:loop.consume_trial_observation(observation)
                    except ProtocolError as error:
                        assert loop.payload()==unchanged and COUNTS==count
                        emit('OBSERVATION_DUPLICATE_REJECTED',{'main_epoch':e,'observation_id':observation.observation_id,
                             'error':str(error),'native_delta':{k:COUNTS[k]-count[k] for k in ('rollout','step','transaction')},'state_unchanged':True})
                    else:raise AssertionError('native observation consumed twice')
                emit('POST_MAIN_LEARNING_STATE',{'main_epoch':e,'state':loop.payload(),'observations_consumed':len(loop._pending_trial_observations)})
                if policy!='task':
                    previous=loop._pending_claim;loop._pending_claim=loop._current_claim
                    emit('RECALL_MONITOR',{'epoch':e,'terminal':receipt['terminal'],'before':previous,
                          'after':loop._pending_claim,'needs_retest':tuple(sorted(loop._needs_retest)),
                          'diagnostic_memory':loop._memory.snapshot()})
                if e+1 in C['retention_checkpoints_completed_tasks']:retention(loop,e+1)
                assert (A.digest(A.wire(ordinal)),A.digest(A.wire(evidence)))==pins
                if frozen_weights is not None:assert loop._memory.weight_snapshot()==frozen_weights
            returns=[returned(r) for r in receipts]
            row={'mode':mode,'arm':arm,'initial_state_sha256':initial_pin,'returns':returns,
                 'outcomes':[r['terminal'] for r in receipts],'total_return':sum(returns),'mean_return':sum(returns)/len(returns),
                 'successes':sum(r['terminal']=='SUCCESS' for r in receipts),
                 'diagnostic_calls':sum(r['counters']['diagnostic_calls'] for r in receipts),
                 'diagnostic_transactions':sum(r['counters']['diagnostic_transactions'] for r in receipts),
                 'diagnostic_edit_attempts':sum(r['counters']['diagnostic_edit_addresses'] for r in receipts),
                 'external_updates':loop._external_updates,'diagnostic_memory_updates':loop._memory_train_events,'memory_kind':loop._memory_kind,'ordinary_updates':len(receipts),'practice_events':loop._practice_used,'memory_retrievals':loop._memory_hits,'diagnostic_memory':loop._memory.snapshot(),'contested_keys':tuple(sorted(loop._contested)),'needs_retest':tuple(sorted(loop._needs_retest)),'pending_recall':loop._pending_claim,'final_state':loop.payload()}
            emit('STREAM_ARM',row);rows.append(row)
    return rows


def main():
    global STREAM,REFERENCE
    STREAM=(HERE/'evidence/raw.jsonl').open('x',encoding='ascii',newline='\n')
    prior=sys.getprofile();ok=False
    try:
        REFERENCE=read_reference();emit('REFERENCE',{'digest':REFERENCE.digest(),'rows':len(REFERENCE)})
        sys.setprofile(profile)
        ordinal,evidence=models();rows=experiment(ordinal,evidence)
        emit('RESULT',{'complete':True,'counts':dict(COUNTS),'streams':rows,'ordinal_model':ordinal,'evidence_model':evidence,
                      'parameter_updates':0,'new_keys':0,'formal_collection':False})
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
