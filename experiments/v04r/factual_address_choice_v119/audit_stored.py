"""Separate stdlib stored review of the new v119 capture; no old checker imports."""
from collections import Counter,defaultdict
from copy import deepcopy
from datetime import datetime,timezone
import ast
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
HELPER_NAMES=("number","state","address","stores","identical","maps_equal","ordinary_expected")

def number(x): return float.fromhex(x['binary64_hex'])

def state(x): return tuple(x[k] for k in ('x','y','t','kappa','phi'))

def address(x,ch):
    if ch=='P':return x
    if ch=='X':return state(x['state'])+(x['cmd'],)
    return state(x['state'])+(x['z'],x['m'])+((x['a'],) if ch=='Q' else ())

def stores(x):
    return {ch:{address(e['address'],ch):number(e['value']) if ch=='Q' else e['value']
                for e in x[ch]} for ch in ('D','P','X','Q')}

def identical(a,b):
    return a.keys()==b.keys() and all((v.hex()==b[k].hex() if type(v) is float else v==b[k]) for k,v in a.items())

def maps_equal(a,b):return all(identical(a[ch],b[ch]) for ch in a)

def ordinary_expected(before, raw, rows):
    mode=before['mode'];cur=stores(before['current'])
    numeric=cur if mode=='dq' else stores(before['learning_values'])
    work=dict(numeric['Q']);trace=raw['trace']
    st=(0,2,0,raw['_episode']['kappa'],raw['_episode']['tape']['phase'])
    z,m=trace['option_in_force'],0;visited=[];seen=[]
    for step in trace['steps']:
        key=st+(z,m);q=key+(step['a_cmd'],);old=work.get(q,rows[key][q[-1]])
        target=number(step['reward'])
        if not step['terminal']:
            nxt=state(step['state'])+(step['control']['z'],step['control']['m'])
            target+=max(work.get(nxt+(a,),value) for a,value in rows[nxt].items())
        work[q]=old+0.5*(target-old)
        if q not in seen:seen.append(q)
        visited.append(key)
        st=state(step['state']);z,m=step['control']['z'],step['control']['m']
    qfinal={q:v for q,v in work.items() if v!=rows[q[:-1]][q[-1]]}
    expected=deepcopy(cur);policy=[]
    if mode=='dq':expected['Q']=qfinal;values=None
    else:
        values=deepcopy(numeric);values['Q']=qfinal
        done=set()
        for key in visited:
            if key in cur['D'] and key not in done:
                row={a:qfinal.get(key+(a,),value) for a,value in rows[key].items()}
                expected['D'][key]=min(a for a,v in row.items() if v==max(row.values()))
                policy.append(key);done.add(key)
    return expected,values,seen,policy,visited


def canonical(x):
    return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=True)

def digest(x):return hashlib.sha256(canonical(x).encode('ascii')).hexdigest()
def meta(p):
    b=p.read_bytes();return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def load(p):return json.loads(p.read_bytes())
def context_key(c):
    return tuple(c.get(x) for x in ('phase','mode','scenario_audit_only','arm','candidate'))
def return_value(receipt):
    return float(sum(number(s['reward']) for s in receipt['trace']['steps']))

def proposal_from_visible(mode, task, action):
    if action=='keep':return {'action':'keep','edits':[]}
    edits=[];seen=set()
    for key,step in zip(task['visited'],task['raw']['trace']['steps']):
        address=dict(state=dict(zip(('x','y','t','kappa','phi'),key[:5])),z=key[5],m=key[6])
        token=key+(step['a_cmd'],) if mode=='dq' else key
        if token in seen:continue
        seen.add(token)
        if mode=='dq':address['a']=step['a_cmd']
        edits.append({'store':'q' if mode=='dq' else 'decision','address':address,'value':None})
    if action.startswith('single:'):
        edits=[edits[int(action.split(':')[1])]]
    return {'action':'apply','edits':edits}

def main():
    out=HERE/'evidence_audit';assert not out.exists(),'audit already attempted; no retry'
    out.mkdir()
    def save(p,x):
        with p.open('x',encoding='utf-8',newline='\n') as stream:
            stream.write(json.dumps(x,sort_keys=True,ensure_ascii=True,indent=2)+'\n')
    save(out/'claim.json',{'audit_source':meta(Path(__file__)),'native_receipt':meta(HERE/'evidence/exit.json'),
                          'automatic_retry':False,'started_at_utc':datetime.now(timezone.utc).isoformat()})
    claim=load(HERE/'evidence/claim.json');ex=load(HERE/'evidence/exit.json')
    assert ex['child_exit_code']==0 and ex['input_bytes_unchanged'] and not ex['automatic_retry']
    assert claim['input_binding_before']==ex['input_binding_after']
    for name,pin in claim['input_binding_before'].items():assert meta(ROOT/name)==pin,name
    assert meta(HERE/'evidence/raw.jsonl')==ex['raw']
    for name in ('stdout','stderr'):assert meta(HERE/('evidence/'+name+'.log'))==ex[name]
    contract=load(HERE/'contract.json')
    ref=(ROOT/contract['reference']['path']).read_bytes()
    assert hashlib.sha256(ref).hexdigest()==contract['reference']['sha256']
    rows={}
    for line in ref.decode('utf-8').splitlines():
        if line.startswith('DECISION_CONTEXT='):
            d=json.loads(line.split('=',1)[1]);rows[tuple(d['context'])]={a:float.fromhex(v) for a,v in d['q_row_hex']}
    # Reused pure arithmetic functions are source-identical to the v117 stored
    # review; that prior checker is only parsed, never imported/executed.
    old=(HERE.parent/'observed_task_loop_v117/audit_stored.py').read_text(encoding='utf-8')
    new=Path(__file__).read_text(encoding='utf-8')
    ot,nt=ast.parse(old),ast.parse(new)
    for name in HELPER_NAMES:
        a=next(x for x in ot.body if isinstance(x,ast.FunctionDef) and x.name==name)
        b=next(x for x in nt.body if isinstance(x,ast.FunctionDef) and x.name==name)
        assert ast.get_source_segment(old,a)==ast.get_source_segment(new,b)
    rs=[json.loads(line) for line in (HERE/'evidence/raw.jsonl').read_text(encoding='ascii').splitlines()]
    assert [x['seq'] for x in rs]==list(range(len(rs)))
    tags=Counter();tasks=defaultdict(list);samples={};costs={};facts={};fact_views={};evals=[];frozen=None;task=None;tx=None;probe_tx=None
    raw_steps=0;ordinary_checks=0;diag_writes=0;probe_writes=0;success_diag=0
    for r in rs:
        tag,p,c=r['tag'],r['payload'],r['context'];tags[tag]+=1;k=context_key(c)
        if tag=='SOURCE_READY' and c['scenario_audit_only']=='external_trap':
            assert p['healthy'] and all(not p['stores'][ch] for ch in ('D','P','X','Q'))
        elif tag=='TASK_BEGIN':
            assert task is None
            task={'before':p['before'],'episode':p['episode'],'epoch':p['epoch'],'key':k,
                  'diag_calls':0,'transactions':0,'writes':0,'context':c}
            assert p['episode']['kappa']==(0 if c['phase']=='development' else 1)
            assert p['episode']['tape']=={'phase':2,'error_flag':0,'cause_rank':3 if c['phase']=='development' else 4}
        elif tag=='TASK_RAW':
            assert task is not None
            task['raw']=deepcopy(p);task['raw']['_episode']=task['episode']
            tr=p['trace'];st=tr['steps'];raw_steps+=len(st)
            assert st and st[-1]['terminal'] is True and tr['outcome']==st[-1]['outcome']
            assert tr['outcome'] in ('SUCCESS','COLLISION','TRAP','TIMEOUT')
            assert len(st)==len(p['draws']) and all(not d['explore'] for d in p['draws'])
            assert p['coordinates']==[[i,0,0,(1<<64)-1] for i in range(len(st))]
            assert float(sum(number(s['reward']) for s in st)).hex()==p['return_hex']
        elif tag=='ORDINARY_UPDATE':
            expected,values,seen,policy,visited=ordinary_expected(task['before'],task['raw'],rows)
            task['visited']=visited;task['ordinary']=p['after'];ordinary_checks+=1
            assert maps_equal(stores(p['after']['current']),expected)
            if values is None:assert p['after']['learning_values'] is None
            else:assert maps_equal(stores(p['after']['learning_values']),values)
            assert [address(e['address'],'Q') for e in p['numeric_edits']]==seen
            assert [address(e['address'],'D') for e in p['policy_edits']]==policy
            assert p['after']['immediate']==task['before']['immediate']
        elif tag=='DIAGNOSE_BEGIN':
            assert task['raw']['trace']['outcome']!='SUCCESS' and p['state_before']==task['ordinary']
            assert c['phase']=='held_out' and c['arm']!='TaskTD' and task['epoch']==0
            task['diag_calls']+=1
            ev=p['evidence'];assert set(ev)=={'steps','z_in_force','kappa','phi'}
            assert p['budget']=={'remaining_queries':0,'remaining_writes':12}
            visible=[]
            for key,step in zip(task['visited'],task['raw']['trace']['steps']):
                item=dict(zip(('x','y','t','kappa','phi','z','m'),key))
                item.update(a_cmd=step['a_cmd'],a_realized=step['a_realized'],
                            reward={'binary64_hex':round(number(step['reward']),6).hex()})
                visible.append(item)
            assert ev['steps']==visible
        elif tag=='SELECTION':
            assert frozen is not None
            ft=[c['mode'],task['raw']['trace']['outcome'],any(s['a_cmd']!=s['a_realized'] for s in task['raw']['trace']['steps'])]
            assert p['feature']==ft
            scores={action:number(mean) for key,action,count,mean,cost in frozen['table'] if key==ft}
            n=len(proposal_from_visible(c['mode'],task,'clear_factual')['edits'])
            actions=['keep']+['single:'+str(i) for i in range(n)]+['clear_factual']
            ac={a:len(proposal_from_visible(c['mode'],task,a)['edits']) for a in actions}
            assert set(scores)==set(actions)
            expected='clear_factual' if c['arm']=='AlwaysClear' else min(actions,key=lambda a:(-scores[a],ac[a],actions.index(a)))
            assert p['candidate']==expected
            assert p['proposal']==proposal_from_visible(c['mode'],task,expected)
            if c['arm']=='LearnedAddress':
                assert p['decision']['feature']==ft and not p['decision']['unknown']
                assert {a:number(v) for a,v in p['decision']['scores'].items()}==scores
                assert p['decision']['address_costs']==ac
            task['selection']=p
        elif tag=='DIAGNOSTIC_TX_BEGIN':
            assert p['before']==task['ordinary'] and tx is None
            assert p['edits']==task['selection']['proposal']['edits'] and len(p['edits'])<=12
            target=deepcopy(stores(p['before']['current']))
            for edit in p['edits']:
                ch='Q' if edit['store']=='q' else 'D';key=address(edit['address'],ch)
                assert (key[:-1] if ch=='Q' else key) in task['visited'] and edit['value'] is None
                target[ch].pop(key,None)
            tx=(target,p['before']);task['writes']+=len(p['edits']);diag_writes+=len(p['edits'])
        elif tag=='DIAGNOSTIC_TX_END':
            assert tx is not None and maps_equal(stores(p['after']['current']),tx[0])
            assert p['after']['learning_values']==tx[1]['learning_values'] and p['after']['immediate']==tx[1]['immediate']
            task['transactions']+=1;tx=None
        elif tag=='TASK_COMPLETE':
            assert task['key']==k and p['trace']==task['raw']['trace']
            assert p['counters']['ordinary_updates']==1 and p['counters']['query_calls']==0
            assert p['counters']['diagnostic_calls']==task['diag_calls']
            assert p['counters']['diagnostic_transactions']==task['transactions']
            assert p['counters']['diagnostic_edit_addresses']==task['writes']
            assert p['route']['write_spend']==task['writes']
            assert p['ordinary_after']==task['ordinary'] and p['after']['immediate']==task['before']['immediate']
            if p['terminal']=='SUCCESS':assert task['diag_calls']==task['writes']==0
            if task['diag_calls']==0:assert p['after']==task['ordinary']
            tasks[k].append(p)
            if c['phase']=='development' and c['arm']=='TaskTD':fact_views[(c['mode'],c['scenario_audit_only'])]=task
            task=None
        elif tag=='DEVELOPMENT_FACTUAL':
            assert frozen is None and p['receipt']==tasks[k][-1]
            facts[(c['mode'],c['scenario_audit_only'])]=p['receipt']
        elif tag=='SUCCESS_NO_MODEL_TRAINING':
            assert frozen is None and facts[(c['mode'],c['scenario_audit_only'])]['terminal']=='SUCCESS'
        elif tag=='LIVE_BRANCH':
            assert frozen is None
            original=facts[(c['mode'],c['scenario_audit_only'])]['after']
            assert p['source']==original
            assert p['proposal']==proposal_from_visible(c['mode'],fact_views[(c['mode'],c['scenario_audit_only'])],c['candidate'])
            assert p['branch_before']['current']==original['current']
            assert p['branch_before']['learning_values']==original['learning_values']
            assert p['branch_before']['completed_episodes']==0
        elif tag=='PROBE_CANDIDATE_TX_BEGIN':
            assert frozen is None and c['candidate']!='keep'
            assert p['edits']==proposal_from_visible(c['mode'],fact_views[(c['mode'],c['scenario_audit_only'])],c['candidate'])['edits']
            probe_before=p['before']
            probe_tx=deepcopy(stores(p['before']['current']))
            for edit in p['edits']:
                assert edit['value'] is None
                ch='Q' if edit['store']=='q' else 'D';probe_tx[ch].pop(address(edit['address'],ch),None)
            probe_writes+=len(p['edits'])
        elif tag=='PROBE_CANDIDATE_TX_END':
            assert probe_tx is not None and maps_equal(stores(p['after']['current']),probe_tx)
            assert p['after']['learning_values']==probe_before['learning_values'] and p['after']['immediate']==probe_before['immediate']
            probe_tx=None
        elif tag=='VALUE_TRAINING_SAMPLE':
            assert frozen is None and p['source_post_TD_unchanged'] and len(tasks[k])==2
            actual=[return_value(x) for x in tasks[k]]
            assert [number(x) for x in p['returns']]==actual
            assert p['outcomes']==[x['terminal'] for x in tasks[k]]
            fact=facts[(c['mode'],c['scenario_audit_only'])]
            assert fact['terminal']!='SUCCESS'
            ft=(c['mode'],fact['terminal'],any(s['a_cmd']!=s['a_realized'] for s in fact['trace']['steps']))
            assert list(ft)==p['feature'] and p['candidate']==c['candidate']
            cost=len(proposal_from_visible(c['mode'],fact_views[(c['mode'],c['scenario_audit_only'])],c['candidate'])['edits'])
            assert p['address_edits']==cost
            costs[ft,p['candidate']]=cost
            samples.setdefault((ft,p['candidate']),[]).extend(actual)
        elif tag=='FROZEN_SELECTOR':
            assert frozen is None and len(samples)==42
            frozen={'table':[[list(key),action,len(vals),{'binary64_hex':(sum(vals)/len(vals)).hex()},costs[key,action]]
                            for (key,action),vals in sorted(samples.items())]}
            assert p['table']==frozen['table']
        elif tag=='EVALUATION_ARM':
            assert frozen is not None and len(tasks[k])==3
            factual,*future=tasks[k]
            assert p['initial_state_sha256']==digest(factual['before']['current'])
            assert p['factual_terminal']==factual['terminal'] and number(p['factual_return'])==return_value(factual)
            assert [number(x) for x in p['future_returns']]==[return_value(x) for x in future]
            assert p['future_outcomes']==[x['terminal'] for x in future]
            assert number(p['mean_future_return'])==sum(return_value(x) for x in future)/2
            assert p['diagnostic_calls']==factual['counters']['diagnostic_calls']
            assert p['diagnostic_edit_addresses']==factual['counters']['diagnostic_edit_addresses']
            assert p['decision']==factual['route']['decision']
            selections=[x['payload'] for x in rs if x['tag']=='SELECTION' and context_key(x['context'])==k]
            assert p['selected_candidate']==(selections[0]['candidate'] if selections else None)
            assert p['diagnostic_transactions']==factual['counters']['diagnostic_transactions']
            assert p['actual_diagnostic_store_changed']==(factual['ordinary_after']['current']!=factual['after']['current'])
            assert p['ordinary_updates']==3 and all(x['counters']['diagnostic_calls']==0 for x in future)
            evals.append(p)
        elif tag=='RESULT':
            assert p['frozen_selector']==frozen and p['frozen_selector_sha256']==digest(frozen)
            assert p['evaluation']==evals
            result=p
    assert task is None and tx is None and probe_tx is None
    final=rs[-1]['payload'];assert rs[-1]['tag']=='FINAL' and final['complete'] and final['profile_restored']
    assert final['counts']==result['counts']
    assert tags['TASK_RAW']==ordinary_checks==tags['TASK_COMPLETE']==final['counts']['rollout']==164
    assert raw_steps==final['counts']['step']
    setup_tx=sum(bool(x['payload']['edits']) for x in rs if x['tag']=='SOURCE_SETUP')
    policy_tx=sum(bool(x['payload']['policy_edits']) for x in rs if x['tag']=='ORDINARY_UPDATE')
    expected_tx=setup_tx+ordinary_checks+policy_tx+tags['PROBE_CANDIDATE_TX_END']+tags['DIAGNOSTIC_TX_END']
    assert expected_tx==final['counts']['transaction']
    assert tags['SELECTION']==tags['DIAGNOSE_BEGIN']==12 and len(evals)==24
    paired=[];aggregate=[]
    for mode in ('dq','patch-adaptive'):
        for scenario in ('collision','timeout','external_trap','success'):
            case=[x for x in evals if x['mode']==mode and x['scenario_audit_only']==scenario]
            assert len(case)==3 and len({x['initial_state_sha256'] for x in case})==1
            assert len({(x['factual_terminal'],number(x['factual_return']).hex()) for x in case})==1
            vals={x['arm']:number(x['mean_future_return']) for x in case}
            paired.append({'mode':mode,'case':scenario,'means':vals,
                           'LearnedAddress_minus_TaskTD':vals['LearnedAddress']-vals['TaskTD'],
                           'LearnedAddress_minus_AlwaysClear':vals['LearnedAddress']-vals['AlwaysClear']})
        armstats={}
        for arm in ('TaskTD','AlwaysClear','LearnedAddress'):
            a=[x for x in evals if x['mode']==mode and x['arm']==arm]
            armstats[arm]={'descriptive_mean_future_return_over_four_fixed_cases':sum(number(x['mean_future_return']) for x in a)/4,
                          'future_successes':sum(sum(y=='SUCCESS' for y in x['future_outcomes']) for x in a),
                          'future_tasks':8,'online_diagnostic_transactions':sum(x['diagnostic_transactions'] for x in a),
                          'online_diagnostic_address_edits':sum(x['diagnostic_edit_addresses'] for x in a)}
        aggregate.append({'mode':mode,'arms':armstats})
    output={'schema':'V119_NEW_STDLIB_STORED_LEARNED_SELECTION_REVIEW','complete':True,
            'native_counts':final['counts'],'records':len(rs),'declared_input_pins':len(claim['input_binding_before']),
            'all_ordinary_TD_full_R_L_updates_verified':ordinary_checks,'development_probe_rollouts':84,
            'candidate_branches':tags['LIVE_BRANCH'],'training_samples':len(samples),'frozen_before_held_out':True,'no_held_out_model_updates':True,
            'online_diagnostic_address_edits':diag_writes,'development_candidate_address_edits':probe_writes,
            'paired_cases':paired,'descriptive_fixed_case_aggregates':aggregate,
            'raw_file':meta(HERE/'evidence/raw.jsonl'),'native_first_exit':0,'old_checker_RFL_or_native_reruns':0,
            'helper_source_transport_count':len(HELPER_NAMES),'scientific_qualification':False,
            'selected_candidates':[{'mode':x['mode'],'case':x['scenario_audit_only'],'arm':x['arm'],'candidate':x['selected_candidate'],'future_returns':[number(v) for v in x['future_returns']],'address_edits':x['diagnostic_edit_addresses']} for x in evals],
            'notes':'Same simple four-mechanism family reused to isolate address granularity, not independent replication/seeds/population inference; temporal-position value learning, not causal posterior.'}
    save(HERE/'stored_audit_result.json',output)
    save(out/'exit.json',{'complete':True,'completed_at_utc':datetime.now(timezone.utc).isoformat(),
                         'result':meta(HERE/'stored_audit_result.json')})
    print(json.dumps(output,sort_keys=True))

if __name__=='__main__':main()
