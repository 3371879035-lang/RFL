"""New stdlib-only stored-content check; never imports/reruns RFL or old tests."""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]

def read(p): return json.loads(p.read_bytes())
def meta(p):
    data=p.read_bytes();return {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
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

def check():
    claim=read(HERE/'evidence/claim.json');receipt=read(HERE/'evidence/exit.json')
    assert receipt['child_exit_code']==0 and receipt['input_bytes_unchanged']
    assert not receipt['automatic_retry'] and claim['input_binding_before']==receipt['input_binding_after']
    for name,pin in claim['input_binding_before'].items():assert meta(ROOT/name)==pin,name
    assert meta(HERE/'evidence/raw.jsonl')==receipt['raw']
    for name in ('stdout','stderr'):assert meta(HERE/('evidence/'+name+'.log'))==receipt[name]
    c=read(HERE/'contract.json');ref=(ROOT/c['source_reference']['path']).read_bytes()
    assert hashlib.sha256(ref).hexdigest()==c['source_reference']['sha256']
    rows={}
    for line in ref.decode('utf-8').splitlines():
        if line.startswith('DECISION_CONTEXT='):
            item=json.loads(line.split('=',1)[1]);rows[tuple(item['context'])]={a:float.fromhex(v) for a,v in item['q_row_hex']}
    rs=[json.loads(line) for line in (HERE/'evidence/raw.jsonl').read_text(encoding='ascii').splitlines()]
    assert [x['seq'] for x in rs]==list(range(len(rs)))
    counts=Counter();tasks=[];partials=[];task=None;diagtx=None;numeric_changes=0;success_changes=0
    for record in rs:
        tag,p=record['tag'],record['payload'];counts[tag]+=1
        if tag=='TASK_BEGIN':
            assert task is None
            task={'before':p['before'],'episode':p['episode'],'case':record['case'],'epoch':p['epoch'],
                  'diag_calls':0,'writes':0,'transactions':0}
        elif tag=='TASK_RAW':
            assert task is not None and 'raw' not in task
            task['raw']=deepcopy(p);task['raw']['_episode']=task['episode']
            trace=p['trace'];steps=trace['steps']
            assert steps and steps[-1]['terminal'] and trace['outcome']==steps[-1]['outcome']
            assert trace['outcome'] in ('SUCCESS','COLLISION','TRAP','TIMEOUT')
            assert not any(s['terminal'] for s in steps[:-1])
            assert len(steps)==len(p['draws']) and all(not d['explore'] for d in p['draws'])
            assert p['coordinates']==[[i,0,0,(1<<64)-1] for i in range(len(steps))]
            assert float(sum(number(s['reward']) for s in steps)).hex()==p['return_hex']
        elif tag=='ORDINARY_UPDATE':
            assert task and 'ordinary' not in task
            expected,values,seen,policy,visited=ordinary_expected(task['before'],task['raw'],rows)
            task['visited']=visited;after=p['after'];task['ordinary']=after
            assert maps_equal(stores(after['current']),expected)
            if values is not None:assert maps_equal(stores(after['learning_values']),values)
            else:assert after['learning_values'] is None
            assert [address(e['address'],'Q') for e in p['numeric_edits']]==seen
            assert [address(e['address'],'D') for e in p['policy_edits']]==policy
            assert after['completed_episodes']==task['epoch']+1
            assert after['immediate']==task['before']['immediate']
            changed=not maps_equal(stores(task['before']['current']),stores(after['current']))
            numeric_changes+=int(changed)
            if task['raw']['trace']['outcome']=='SUCCESS':success_changes+=int(changed)
        elif tag=='DIAGNOSE_BEGIN':
            assert task and 'ordinary' in task and p['terminal']==task['raw']['trace']['outcome']!='SUCCESS'
            task['diag_calls']+=1;assert p['state_before']==task['ordinary']
            ev=p['evidence'];assert set(ev)=={'steps','z_in_force','kappa','phi'}
            assert p['budget']['remaining_queries']==0
            expected=[]
            for key,step in zip(task['visited'],task['raw']['trace']['steps']):
                s=dict(zip(('x','y','t','kappa','phi','z','m'),key))
                s.update(a_cmd=step['a_cmd'],a_realized=step['a_realized'],
                         reward={'binary64_hex':round(number(step['reward']),6).hex()})
                expected.append(s)
            assert ev['steps']==expected
        elif tag=='DIAGNOSE_RETURN':task['proposal']=p['proposal']
        elif tag=='DIAGNOSTIC_TX_BEGIN':
            assert diagtx is None and p['before']==task['ordinary']
            mode=task['before']['mode'];target=deepcopy(stores(p['before']['current']))
            assert len(p['edits'])<=1
            for edit in p['edits']:
                ch='Q' if edit['store']=='q' else 'D';assert ch==('Q' if mode=='dq' else 'D')
                key=address(edit['address'],ch);assert (key[:-1] if ch=='Q' else key) in task['visited']
                value=edit['value']
                if value is None:target[ch].pop(key,None)
                else:
                    v=number(value) if ch=='Q' else value
                    if ch=='Q' and v==rows[key[:-1]][key[-1]]:target[ch].pop(key,None)
                    else:target[ch][key]=v
            task['writes']+=len(p['edits']);diagtx=target
        elif tag=='DIAGNOSTIC_TX_END':
            assert diagtx is not None and maps_equal(stores(p['after']['current']),diagtx)
            assert p['after']['immediate']==task['before']['immediate']
            task['transactions']+=1;diagtx=None
        elif tag in ('TASK_COMPLETE','TASK_PARTIAL'):
            assert task and p['counters']['ordinary_updates']==1
            assert p['counters']['diagnostic_calls']==task['diag_calls']
            assert p['counters']['diagnostic_transactions']==task['transactions']
            assert p['counters']['diagnostic_edit_addresses']==task['writes']
            assert p['counters']['query_calls']==0
            if tag=='TASK_COMPLETE':
                assert p['terminal']==task['raw']['trace']['outcome']
                assert p['ordinary_after']==task['ordinary'] and p['trace']==task['raw']['trace']
                assert p['route']['write_spend']==task['writes']
                if p['terminal']=='SUCCESS':
                    assert task['diag_calls']==task['writes']==task['transactions']==0
                    assert p['route']['route']=='SUCCESS_NO_DIAGNOSTIC'
                elif p['route']['decision']=='keep':assert task['writes']==task['transactions']==0
                tasks.append({'case':task['case'],'epoch':p['epoch'],'terminal':p['terminal'],
                              'decision':p['route']['decision'],'counters':p['counters']})
            else:
                assert p['ordinary_committed'] and not p['complete_task_receipt']
                assert p['after']==task['ordinary'] and task['writes']==task['transactions']==0
                partials.append({'case':task['case'],'error':p['error_type'],
                                 'ordinary_committed':True,'no_complete_receipt':True})
            task=None
    assert task is None and diagtx is None
    final=rs[-1]['payload'];assert rs[-1]['tag']=='FINAL'
    assert final['tests']==10 and final['failures']==final['errors']==0
    assert final['unexpected_failure'] is None and final['profile_restored']
    steps=sum(len(x['payload']['trace']['steps']) for x in rs if x['tag']=='TASK_RAW')
    assert final['counts']['rollout']==counts['TASK_RAW']==10
    assert final['counts']['step']==steps==41
    expected_tx=counts['SETUP']+counts['ORDINARY_UPDATE']+counts['DIAGNOSTIC_TX_END']
    expected_tx+=sum(bool(x['payload']['policy_edits']) for x in rs if x['tag']=='ORDINARY_UPDATE')
    assert final['counts']['transaction']==expected_tx==22
    assert len(tasks)==7 and len(partials)==3 and success_changes>=1
    return {'schema':'V117_STDLIB_REAL_TASK_STORED_CHECK','complete':True,'records':len(rs),
            'tests':10,'failures':0,'errors':0,'native_counts':final['counts'],
            'completed_tasks':tasks,'planned_partial_tasks':partials,
            'ordinary_numeric_policy_state_checks':10,'successful_task_actual_learning_changed':success_changes,
            'all_declared_inputs_preserved':len(claim['input_binding_before']),
            'real_diagnostic_transactions':1,'real_diagnostic_edit_addresses':1,
            'queries_available':False,'old_checker_RFL_or_native_executed':False,
            'runtime_identity_reconstructed':False,'scientific_qualification':False,
            'scope':'Structured budgeted post-TD edit, not an original B1 pair or learned diagnosis result.'}

if __name__=='__main__':
    out=HERE/'evidence_audit';assert not out.exists(),'stored audit already attempted'
    out.mkdir();started=datetime.now(timezone.utc).isoformat()
    with (out/'claim.json').open('x',encoding='utf-8') as s:
        json.dump({'started_at_utc':started,'audit_source':meta(Path(__file__)),
                   'native_receipt':meta(HERE/'evidence/exit.json'),'automatic_retry':False},s,sort_keys=True)
    try:
        result=check()
    except BaseException as error:
        with (out/'failure.json').open('x',encoding='utf-8') as s:
            json.dump({'type':type(error).__name__,'message':str(error)},s)
        raise
    result['started_at_utc']=started;result['completed_at_utc']=datetime.now(timezone.utc).isoformat()
    with (HERE/'stored_audit_result.json').open('x',encoding='utf-8',newline='\n') as s:
        json.dump(result,s,sort_keys=True,ensure_ascii=True,indent=2);s.write('\n')
    with (out/'exit.json').open('x',encoding='utf-8') as s:
        json.dump({'audit_completed':True,'audit_result':meta(HERE/'stored_audit_result.json'),
                   'completed_at_utc':result['completed_at_utc']},s,sort_keys=True)
    print(json.dumps(result,sort_keys=True))
