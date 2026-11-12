"""Independent stdlib review of recorded continuation data; never executes old native/checkers."""
from collections import Counter
from copy import deepcopy
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]

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

def return_value(receipt):
    return float(sum(number(s['reward']) for s in receipt['trace']['steps']))


def start_values(p,rows):
    k=(0,2,0,0,3,1,0);cur=stores(p['current']);numeric=stores(p['learning_values'])
    values={a:numeric['Q'].get(k+(a,),v) for a,v in rows[k].items()}
    return {'RIGHT':{'binary64_hex':values[3].hex()},'WAIT':{'binary64_hex':values[4].hex()},
            'greedy_command':cur['D'].get(k,min(a for a,v in values.items() if v==max(values.values())))}


def main():
    out=HERE/'evidence_audit';out.mkdir(exist_ok=False)
    def save(p,x):
        with p.open('x',encoding='utf-8',newline='\n') as f:json.dump(x,f,ensure_ascii=True,indent=2);f.write('\n')
    save(out/'claim.json',{'audit_source':meta(Path(__file__)),'native_receipt':meta(HERE/'evidence/exit.json'),
        'started_at_utc':datetime.now(timezone.utc).isoformat(),'automatic_retry':False})
    c=load(HERE/'contract.json');claim=load(HERE/'evidence/claim.json');ex=load(HERE/'evidence/exit.json')
    assert ex['child_exit_code']==0 and ex['input_bytes_unchanged'] and claim['input_binding_before']==ex['input_binding_after']
    for path,pin in claim['input_binding_before'].items():assert meta(ROOT/path)==pin,path
    assert meta(HERE/'evidence/raw.jsonl')==ex['raw']
    for name in ('raw','stored_review','contract'):
        s=c['checkpoint'][name];assert meta(ROOT/s['path'])=={k:s[k] for k in ('bytes','sha256')}
    oldrs=[json.loads(x) for x in (ROOT/c['checkpoint']['raw']['path']).read_text(encoding='ascii').splitlines()]
    assert [x['seq'] for x in oldrs]==list(range(len(oldrs)))
    cp=[r['payload']['final_state'] for r in oldrs if r['tag']=='STREAM_ARM' and r['context'].get('arm')=='DriftOrdinaryExtra'];assert len(cp)==1;cp=cp[0]
    assert cp['completed_episodes']==20 and cp['external_updates']==4 and cp['mode']=='patch-adaptive'
    rows={}
    for line in (ROOT/c['reference']['path']).read_text(encoding='utf-8').splitlines():
        if line.startswith('DECISION_CONTEXT='):
            p=json.loads(line.split('=',1)[1]);rows[tuple(p['context'])]={a:float.fromhex(v) for a,v in p['q_row_hex']}
    rs=[json.loads(x) for x in (HERE/'evidence/raw.jsonl').read_text(encoding='ascii').splitlines()]
    assert [r['seq'] for r in rs]==list(range(len(rs)))
    tags=Counter();last={};task=None;tasks={};summaries=[];value_rows={};Ksteps=0;explore_count=0;policy_TX=0;numeric_TX=0
    arms={x['name']:x for x in c['arms']}
    for r in rs:
        tag,p,ctx=r['tag'],r['payload'],r['context'];tags[tag]+=1;arm=ctx.get('arm')
        if tag=='REFERENCE':assert p=={'digest':c['reference']['q_digest'],'rows':len(rows)}
        elif tag=='CHECKPOINT_BEFORE':assert p['full_payload']==cp and p['source_raw_sha256']==c['checkpoint']['raw']['sha256']
        elif tag=='CHECKPOINT_MATERIALIZED':
            assert all(p[k]==cp[k] for k in ('immediate','current','learning_values')) and p['materialization_TX']==3 and p['old_issued_identity_restored'] is False
        elif tag=='CHECKPOINT_INITIALIZED':
            assert task is None and arm in arms and arm not in last and p['checkpoint_raw_sha256']==c['checkpoint']['raw']['sha256']
            assert p['recorded_main_tasks']==20 and p['recorded_external_updates']==4 and p['fresh_clock'] is True
            assert all(p['state'][k]==cp[k] for k in ('immediate','current','learning_values','mode','reference_digest'))
            assert p['state']['completed_episodes']==p['state']['external_updates']==0 and p['state']['attempted_epochs']==[]
            last[arm]=p['state'];tasks[arm]=[];value_rows[arm]=[]
        elif tag=='TASK_BEGIN':
            assert task is None and ctx['phase']=='continuation';e=len(tasks[arm]);cfg=arms[arm];ep=p['episode']
            assert p['epoch']==ep['epoch']==e and 0<=e<12 and ep['kappa']==0 and ep['proposal']==1 and ep['tape']=={'phase':3,'error_flag':0,'cause_rank':12}
            coins=[(1<<64)-1]*12
            if e in cfg['explore_epochs']:coins[0]=0
            assert ep['coins']==coins and ep['rejections']==[[0]]*12
            expected_mask={'decision':None,'controller':None,'plant':None,'trap':{'cell':[1,2],'t':0} if cfg['trap'] else None}
            assert p['environment_mask_audit_only']==expected_mask
            assert all(p['before'][k]==last[arm][k] for k in p['before'] if k!='attempted_epochs')
            assert p['before']['attempted_epochs']==list(range(e+1))
            task={'before':p['before'],'epoch':e,'episode':ep,'mask':expected_mask,'arm':arm}
        elif tag=='TASK_RAW':
            assert task is not None and task['arm']==arm;tr=p['trace'];assert tr['mask']==task['mask'] and tr['option_in_force']==1
            assert tr['steps'][-1]['terminal'] and tr['outcome']==tr['steps'][-1]['outcome']
            at=(0,2,0,0,3);z,m=1,0;cur=stores(task['before']['current']);vals=stores(task['before']['learning_values']);calls=[]
            assert len(p['draws'])==len(tr['steps'])
            for i,(draw,step) in enumerate(zip(p['draws'],tr['steps'])):
                k=at+(z,m);admissible=sorted(rows[k]);greedy=cur['D'].get(k,min(a for a,v in rows[k].items() if vals['Q'].get(k+(a,),v)==max(vals['Q'].get(k+(b,),w) for b,w in rows[k].items())))
                coin=task['episode']['coins'][i];explore=coin==0;calls.append([i,0,0,coin])
                cmd=admissible[0] if explore else greedy
                if explore:calls.append([i,1,0,0]);explore_count+=1
                assert draw=={'i':i,'explore':explore,'admissible':admissible,'a_cmd':cmd}
                assert step['a_cmd']==step['a_realized']==cmd
                at=state(step['state']);z,m=step['control']['z'],step['control']['m']
            assert p['coordinates']==calls and p['return_hex']==sum(number(x['reward']) for x in tr['steps']).hex()
            task['raw']={**p,'_episode':task['episode']};Ksteps+=len(tr['steps'])
        elif tag=='ORDINARY_UPDATE':
            assert task is not None and task['arm']==arm
            expected,values,seen,policy,visited=ordinary_expected(task['before'],task['raw'],rows)
            assert maps_equal(stores(p['after']['current']),expected) and maps_equal(stores(p['after']['learning_values']),values)
            assert [address(x['address'],'Q') for x in p['numeric_edits']]==seen
            assert all(number(x['value']).hex()==values['Q'].get(q,rows[q[:-1]][q[-1]]).hex() for x,q in zip(p['numeric_edits'],seen))
            assert [address(x['address'],'D') for x in p['policy_edits']]==policy
            assert all(x['value']==expected['D'][q] for x,q in zip(p['policy_edits'],policy))
            assert p['after']['immediate']==cp['immediate'] and p['after']['external_updates']==0
            assert p['after']['completed_episodes']==task['epoch']+1 and p['after']['attempted_epochs']==task['before']['attempted_epochs']
            task['after']=p['after'];numeric_TX+=1;policy_TX+=bool(policy)
        elif tag=='TASK_COMPLETE':
            assert task is not None and task['arm']==arm and p['before']==task['before'] and p['after']==p['ordinary_after']==task['after'] and p['trace']==task['raw']['trace']
            assert p['terminal']==p['trace']['outcome'] and p['counters']=={'ordinary_updates':1,'diagnostic_calls':0,'query_calls':0,'diagnostic_transactions':0,'diagnostic_edit_addresses':0}
            assert p['route']=={'terminal':p['terminal'],'route':'TASK_ONLY','ordinary_learning_called':True,'diagnostic_calls':0,'query_spend':0,'write_spend':0,'decision':'none'}
            last[arm]=p['after'];tasks[arm].append(p);task=None
        elif tag=='START_VALUE_UPDATE':
            t=tasks[arm][-1];assert p['epoch']==t['epoch'] and p['before_start']==start_values(t['before'],rows) and p['after_start']==start_values(t['after'],rows)
            assert p['first_command']==t['trace']['steps'][0]['a_cmd'] and p['terminal']==t['terminal'] and p['explore_planned']==(t['epoch'] in arms[arm]['explore_epochs']) and number(p['return']).hex()==return_value(t).hex()
            value_rows[arm].append(p)
        elif tag=='STREAM_ARM':
            assert len(tasks[arm])==len(value_rows[arm])==p['tasks']==12 and p['final_state']==last[arm]
            vals=[return_value(t) for t in tasks[arm]]
            assert [number(x) for x in p['returns']]==vals and number(p['return_mean']).hex()==(sum(vals)/12).hex()
            assert p['outcomes']==[t['terminal'] for t in tasks[arm]] and p['successes']==sum(t['terminal']=='SUCCESS' for t in tasks[arm]) and p['start_values']==value_rows[arm]
            summaries.append(p)
        elif tag=='RESULT':assert p['complete'] and p['streams']==summaries;result=p
        elif tag=='FINAL':assert p['complete'] and p['profile_restored'];final=p
        else:raise AssertionError('unexpected tag '+tag)
    assert task is None and set(tasks)==set(arms) and len(summaries)==4
    assert final['counts']==result['counts']=={'rollout':48,'step':Ksteps,'transaction':3+numeric_TX+policy_TX}
    assert numeric_TX==48 and tags['CHECKPOINT_MATERIALIZED']==1 and explore_count==12
    compact=[]
    for p in summaries:
        arm=p['arm'];v=value_rows[arm]
        compact.append({'arm':arm,'successes':p['successes'],'mean_return':number(p['return_mean']),'outcomes':p['outcomes'],
             'returns':[number(x) for x in p['returns']],'start_RIGHT_values_after_each_task':[number(x['after_start']['RIGHT']) for x in v],
             'start_greedy_after_each_task':[x['after_start']['greedy_command'] for x in v],
             'first_nonexploratory_RIGHT_epoch':next((x['epoch'] for x in v if not x['explore_planned'] and x['first_command']==3),None),
             'actual_Ksteps':sum(len(t['trace']['steps']) for t in tasks[arm]),'main_diagnostics':0})
    output={'schema':'V143_STDLIB_STALE_EXPERIENCE_REVIEW','complete':True,'records':len(rs),'input_pins':len(claim['input_binding_before']),
         'native_first_exit':0,'native_counts':final['counts'],'checkpoint_full_I_R_L_exact':True,'old_prefix_native_replay':0,
         'materialization_TX':3,'native_ordinary_updates':numeric_TX,'native_policy_TX':policy_TX,'exploration_events':explore_count,'summaries':compact,
         'original_ordinary_TD_and_greedy_module_unchanged':True,'diagnostics':0,'new_RNG_keys_DP_calibration_collection':0,'scientific_qualification':False}
    save(HERE/'stored_audit_result.json',output);save(out/'exit.json',{'completed_at_utc':datetime.now(timezone.utc).isoformat(),'complete':True,'result':meta(HERE/'stored_audit_result.json')})
    print(json.dumps(output,sort_keys=True))

if __name__=='__main__':main()
