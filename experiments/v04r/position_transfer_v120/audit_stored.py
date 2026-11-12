"""Separate stdlib stored review of the new v120 capture; no old checker imports."""
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
    contract=load(HERE/'contract.json');params=load(HERE/'frozen_parameters.json')
    pin=params['source_raw'];data=(ROOT/pin['path']).read_bytes()
    assert meta(ROOT/pin['path'])=={k:pin[k] for k in ('bytes','sha256')}
    origin=json.loads(data.splitlines()[params['source_record_seq']])
    assert origin['tag']=='FROZEN_SELECTOR' and params['table']==origin['payload']['table']
    frozen={'table':params['table']}
    rows={};ref=contract['reference'];assert meta(ROOT/ref['path'])['sha256']==ref['sha256']
    for line in (ROOT/ref['path']).read_text(encoding='utf-8').splitlines():
        if line.startswith('DECISION_CONTEXT='):
            d=json.loads(line.split('=',1)[1]);rows[tuple(d['context'])]={a:float.fromhex(v) for a,v in d['q_row_hex']}
    old=(HERE.parent/'observed_task_loop_v117/audit_stored.py').read_text(encoding='utf-8')
    new=Path(__file__).read_text(encoding='utf-8');ot,nt=ast.parse(old),ast.parse(new)
    for name in HELPER_NAMES:
        a=next(x for x in ot.body if isinstance(x,ast.FunctionDef) and x.name==name)
        b=next(x for x in nt.body if isinstance(x,ast.FunctionDef) and x.name==name)
        assert ast.get_source_segment(old,a)==ast.get_source_segment(new,b)
    rs=[json.loads(line) for line in (HERE/'evidence/raw.jsonl').read_text(encoding='ascii').splitlines()]
    assert [r['seq'] for r in rs]==list(range(len(rs)))
    tags=Counter();tasks=defaultdict(list);details={};evals=[];task=None;tx=None;source=None
    steps=0;ordinary=0;diag_writes=0;unknown=[]
    for r in rs:
        tag,p,c=r['tag'],r['payload'],r['context'];tags[tag]+=1;k=context_key(c)
        if tag=='FROZEN_IMPORTED_PARAMETERS':
            assert p['model']==frozen and p['parameter_record']==params
        elif tag=='SOURCE_SETUP':
            assert all(not x for x in stores(p['before']).values())
            d=p['descriptor_audit_only'];assert d in contract['cases'] and c['scenario_audit_only']=='prefix'+str(d['prefix'])
            assert len(p['edits'])==2*(12-d['prefix'])+2
            source={ch:{} for ch in ('D','P','X','Q')}
            for edit in p['edits']:
                ch={'q':'Q','decision':'D','process':'P'}[edit['store']]
                source[ch][address(edit['address'],ch)]=number(edit['value']) if ch=='Q' else edit['value']
        elif tag=='SOURCE_READY':
            assert source is not None and maps_equal(stores(p['stores']),source);source=None
        elif tag=='TASK_BEGIN':
            assert task is None and p['episode']['kappa']==1
            assert p['episode']['tape']=={'phase':2,'error_flag':0,'cause_rank':5}
            assert all(v is None for v in p['environment_mask_audit_only'].values())
            task={'before':p['before'],'episode':p['episode'],'epoch':p['epoch'],'key':k,
                  'diag_calls':0,'transactions':0,'writes':0}
        elif tag=='TASK_RAW':
            task['raw']=deepcopy(p);task['raw']['_episode']=task['episode']
            trace=p['trace'];st=trace['steps'];steps+=len(st)
            assert st and st[-1]['terminal'] is True and trace['outcome']==st[-1]['outcome']
            assert trace['outcome'] in ('SUCCESS','COLLISION','TRAP','TIMEOUT') and trace['option_in_force']==1
            assert p['coordinates']==[[i,0,0,(1<<64)-1] for i in range(len(st))]
            assert len(p['draws'])==len(st) and all(not d['explore'] for d in p['draws'])
            assert all(d['a_cmd']==x['a_cmd'] for d,x in zip(p['draws'],st))
            assert sum(number(x['reward']) for x in st).hex()==p['return_hex']
            cur=stores(task['before']['current']);numeric=cur if c['mode']=='dq' else stores(task['before']['learning_values'])
            at=(0,2,0,1,2);z,m=1,0
            for x in st:
                key=at+(z,m);row={a:numeric['Q'].get(key+(a,),v) for a,v in rows[key].items()}
                cmd=cur['D'][key] if c['mode']=='patch-adaptive' and key in cur['D'] else min(a for a,v in row.items() if v==max(row.values()))
                assert x['a_cmd']==cmd and x['a_realized']==cmd
                at=state(x['state']);z,m=x['control']['z'],x['control']['m']
        elif tag=='ORDINARY_UPDATE':
            expected,values,seen,policy,visited=ordinary_expected(task['before'],task['raw'],rows)
            task['visited']=visited;task['ordinary']=p['after'];ordinary+=1
            assert maps_equal(stores(p['after']['current']),expected)
            if values is None:assert p['after']['learning_values'] is None
            else:assert maps_equal(stores(p['after']['learning_values']),values)
            assert [address(x['address'],'Q') for x in p['numeric_edits']]==seen
            assert [address(x['address'],'D') for x in p['policy_edits']]==policy
            assert p['after']['immediate']==task['before']['immediate']
        elif tag=='DIAGNOSE_BEGIN':
            assert task['epoch']==0 and c['arm']!='TaskTD' and task['raw']['trace']['outcome']!='SUCCESS'
            assert p['state_before']==task['ordinary'];task['diag_calls']+=1
            assert set(p['evidence'])=={'steps','z_in_force','kappa','phi'}
            assert p['budget']=={'remaining_queries':0,'remaining_writes':12}
            visible=[]
            for key,step in zip(task['visited'],task['raw']['trace']['steps']):
                item=dict(zip(('x','y','t','kappa','phi','z','m'),key))
                item.update(a_cmd=step['a_cmd'],a_realized=step['a_realized'],reward={'binary64_hex':round(number(step['reward']),6).hex()})
                visible.append(item)
            assert p['evidence']['steps']==visible
        elif tag=='SELECTION':
            ft=[c['mode'],task['raw']['trace']['outcome'],any(s['a_cmd']!=s['a_realized'] for s in task['raw']['trace']['steps'])]
            assert p['feature']==ft
            n=len(proposal_from_visible(c['mode'],task,'clear_factual')['edits'])
            actions=['keep']+['single:'+str(i) for i in range(n)]+['clear_factual']
            costs={a:len(proposal_from_visible(c['mode'],task,a)['edits']) for a in actions}
            scores={a:number(v) for key,a,count,v,cost in frozen['table'] if key==ft and count>0 and a in actions}
            incomplete=set(scores)!=set(actions)
            expected='clear_factual' if c['arm']=='AlwaysClear' else ('keep' if incomplete else min(actions,key=lambda a:(-scores[a],costs[a],actions.index(a))))
            assert p['candidate']==expected and p['candidate_count']==len(actions)
            assert p['proposal']==proposal_from_visible(c['mode'],task,expected)
            if c['arm']=='FrozenAddress':
                assert p['decision']['feature']==ft and p['decision']['unknown']==incomplete
                assert {a:number(v) for a,v in p['decision']['scores'].items()}==scores
                if not incomplete:assert p['decision']['address_costs']==costs
                unknown.append(incomplete)
            task['selection']=p
        elif tag=='DIAGNOSTIC_TX_BEGIN':
            assert tx is None and p['before']==task['ordinary']
            assert p['edits']==task['selection']['proposal']['edits'] and 0<len(p['edits'])<=12
            target=deepcopy(stores(p['before']['current']))
            for edit in p['edits']:
                ch='Q' if edit['store']=='q' else 'D';a=address(edit['address'],ch)
                assert (a[:-1] if ch=='Q' else a) in task['visited'] and edit['value'] is None
                target[ch].pop(a,None)
            tx=(target,p['before']);task['writes']+=len(p['edits']);diag_writes+=len(p['edits'])
        elif tag=='DIAGNOSTIC_TX_END':
            assert tx is not None and maps_equal(stores(p['after']['current']),tx[0])
            assert p['after']['learning_values']==tx[1]['learning_values'] and p['after']['immediate']==tx[1]['immediate']
            task['transactions']+=1;tx=None
        elif tag=='TASK_COMPLETE':
            assert task['key']==k and p['trace']==task['raw']['trace']
            assert p['ordinary_after']==task['ordinary'] and p['after']['immediate']==task['before']['immediate']
            assert p['counters']=={'ordinary_updates':1,'diagnostic_calls':task['diag_calls'],'query_calls':0,'diagnostic_transactions':task['transactions'],'diagnostic_edit_addresses':task['writes']}
            assert p['route']['write_spend']==task['writes']
            if p['terminal']=='SUCCESS':assert task['diag_calls']==task['writes']==0
            if not task['diag_calls']:assert p['after']==task['ordinary']
            tasks[k].append(p);details[k]=task;task=None
        elif tag=='EVALUATION_ARM':
            assert len(tasks[k])==3
            factual,*future=tasks[k]
            assert p['initial_state_sha256']==digest(factual['before']['current'])
            assert p['factual_terminal']==factual['terminal'] and number(p['factual_return'])==return_value(factual)
            assert p['factual_steps']==len(factual['trace']['steps'])
            assert [number(x) for x in p['future_returns']]==[return_value(x) for x in future]
            assert p['future_outcomes']==[x['terminal'] for x in future]
            assert number(p['mean_future_return'])==sum(return_value(x) for x in future)/2
            assert p['decision']==factual['route']['decision']
            for a,b in [('diagnostic_calls','diagnostic_calls'),('diagnostic_edit_addresses','diagnostic_edit_addresses'),('diagnostic_transactions','diagnostic_transactions')]:assert p[a]==factual['counters'][b]
            selections=[x['payload'] for x in rs if x['tag']=='SELECTION' and context_key(x['context'])==k]
            assert p['selected_candidate']==(selections[0]['candidate'] if selections else None)
            assert p['actual_diagnostic_store_changed']==(factual['ordinary_after']['current']!=factual['after']['current'])
            assert all(x['counters']['diagnostic_calls']==0 for x in future)
            assert p['ordinary_updates']==3;evals.append(p)
        elif tag=='RESULT':
            assert p['frozen_selector']==frozen and p['frozen_selector_sha256']==digest(frozen)
            assert p['evaluation']==evals and p['training_updates']==0;result=p
    final=rs[-1]['payload'];assert rs[-1]['tag']=='FINAL' and final['complete'] and final['profile_restored']
    assert task is None and tx is None and source is None
    assert tags['TASK_RAW']==tags['TASK_COMPLETE']==ordinary==final['counts']['rollout']==54
    assert steps==final['counts']['step'] and final['counts']==result['counts']
    txexpected=tags['SOURCE_READY']+ordinary+sum(bool(x['payload']['policy_edits']) for x in rs if x['tag']=='ORDINARY_UPDATE')+tags['DIAGNOSTIC_TX_END']
    assert txexpected==final['counts']['transaction'] and len(evals)==18
    paired=[];aggregate=[]
    for mode in contract['modes']:
        for descriptor in contract['cases']:
            case='prefix'+str(descriptor['prefix']);a=[x for x in evals if x['mode']==mode and x['scenario_audit_only']==case]
            assert len(a)==3 and len({x['initial_state_sha256'] for x in a})==1
            assert len({(x['factual_terminal'],number(x['factual_return']).hex()) for x in a})==1
            paired.append({'mode':mode,'case':case,'factual_terminal':a[0]['factual_terminal'],'factual_steps':a[0]['factual_steps'],
                 'arms':{x['arm']:{'candidate':x['selected_candidate'],'future_returns':[number(v) for v in x['future_returns']],'future_outcomes':x['future_outcomes'],'address_edit_attempts':x['diagnostic_edit_addresses'],'diagnostic_content_changed':x['actual_diagnostic_store_changed']} for x in a}})
        arms={}
        for arm in contract['arms']:
            a=[x for x in evals if x['mode']==mode and x['arm']==arm]
            arms[arm]={'descriptive_mean_future_return_over_three_fixed_cases':sum(number(x['mean_future_return']) for x in a)/3,
                       'future_successes':sum(sum(y=='SUCCESS' for y in x['future_outcomes']) for x in a),'future_tasks':6,
                       'online_diagnostic_address_edit_attempts':sum(x['diagnostic_edit_addresses'] for x in a),
                       'online_diagnostic_transactions':sum(x['diagnostic_transactions'] for x in a)}
        aggregate.append({'mode':mode,'arms':arms})
    output={'schema':'V120_STDLIB_FROZEN_POSITION_TRANSFER_REVIEW','complete':True,'native_first_exit':0,
       'native_counts':final['counts'],'records':len(rs),'declared_input_pins':len(claim['input_binding_before']),
       'all_ordinary_full_R_L_updates_verified':ordinary,'training_updates':0,'frozen_table_unchanged':True,
       'frozen_selector_unknown_coverage_cases':sum(unknown),'frozen_selector_evaluations':len(unknown),
       'matched_TIMEOUT_twelve_step_cases':sum(x['factual_terminal']=='TIMEOUT' and x['factual_steps']==12 for x in paired),
       'online_address_edit_attempts':diag_writes,'paired_cases':paired,'descriptive_fixed_case_aggregates':aggregate,
       'raw_file':meta(HERE/'evidence/raw.jsonl'),'scientific_qualification':False,'old_checker_or_native_reruns':0,
       'notes':'Actual frozen parameter transfer, not runtime-handle restoration. Policy transfer failures are distinct from harness errors or RFL mechanism refutation. No independent-seed inference.'}
    save(HERE/'stored_audit_result.json',output)
    save(out/'exit.json',{'complete':True,'completed_at_utc':datetime.now(timezone.utc).isoformat(),'result':meta(HERE/'stored_audit_result.json')})
    print(json.dumps(output,sort_keys=True))

if __name__=='__main__':main()
