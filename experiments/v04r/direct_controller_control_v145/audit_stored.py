"""New stdlib audit for direct-feedback and same-experience recorded comparisons."""
from collections import Counter,defaultdict
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]

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

def key(ctx):return ctx.get('phase'),ctx.get('case'),ctx.get('arm'),ctx.get('candidate')

def evidence(trace):
    at={'x':0,'y':2,'t':0,'kappa':0,'phi':3};z,m=trace['option_in_force'],0;out=[]
    for x in trace['steps']:
        out.append({**at,'z':z,'m':m,'a_cmd':x['a_cmd'],'a_realized':x['a_realized'],'reward':{'binary64_hex':float(round(number(x['reward']),6)).hex()}})
        at=x['state'];z,m=x['control']['z'],x['control']['m']
    return {'steps':out,'z_in_force':trace['option_in_force'],'kappa':0,'phi':3}

def proposal(ev):
    for x in ev['steps']:
        if x['a_cmd']!=x['a_realized']:
            return {'action':'apply','edits':[{'store':'controller','address':{'state':{k:x[k] for k in ('x','y','t','kappa','phi')},'cmd':x['a_cmd']},'value':None}]}
    return None

def update(before,raw,p,rows,external):
    expected,values,seen,policy,visited=ordinary_expected(before,raw,rows);after=p['after']
    assert maps_equal(stores(after['current']),expected) and maps_equal(stores(after['learning_values']),values)
    assert [address(x['address'],'Q') for x in p['numeric_edits']]==seen
    assert all(number(x['value']).hex()==values['Q'].get(q,rows[q[:-1]][q[-1]]).hex() for x,q in zip(p['numeric_edits'],seen))
    assert [address(x['address'],'D') for x in p['policy_edits']]==policy and all(x['value']==expected['D'][q] for x,q in zip(p['policy_edits'],policy))
    assert after['immediate']==before['immediate'] and after['ordinary_PX_anchor']==before['ordinary_PX_anchor']=={k:after['current'][k] for k in ('P','X')}
    assert after['completed_episodes']==before['completed_episodes']+(0 if external else 1) and after['external_updates']==before['external_updates']+(1 if external else 0)
    assert after['attempted_epochs']==before['attempted_epochs']
    return bool(policy)


def main():
    out=HERE/'evidence_audit';out.mkdir(exist_ok=False)
    def save(p,d):
        with p.open('x',encoding='utf-8',newline='\n') as f:json.dump(d,f,ensure_ascii=True,indent=2);f.write('\n')
    save(out/'claim.json',{'source':meta(Path(__file__)),'native':meta(HERE/'evidence/exit.json'),'started_at_utc':datetime.now(timezone.utc).isoformat(),'automatic_retry':False})
    c=load(HERE/'contract.json');claim=load(HERE/'evidence/claim.json');ex=load(HERE/'evidence/exit.json')
    assert ex['child_exit_code']==0 and ex['input_bytes_unchanged'] and claim['input_binding_before']==ex['input_binding_after']
    for path,pin in claim['input_binding_before'].items():assert meta(ROOT/path)==pin,path
    assert meta(HERE/'evidence/raw.jsonl')==ex['raw']
    oldc=load(ROOT/c['recorded_controls']['contract.json']['path']);assert all(c[k]==oldc[k] for k in ('cases','checkpoint','reference'))
    for pin in c['recorded_controls'].values():assert meta(ROOT/pin['path'])=={k:pin[k] for k in ('bytes','sha256')}
    oldclaim=load(ROOT/c['recorded_controls']['evidence/claim.json']['path']);olde=load(ROOT/c['recorded_controls']['evidence/exit.json']['path'])
    assert olde['child_exit_code']==0 and olde['input_bytes_unchanged'] and oldclaim['input_binding_before']==olde['input_binding_after']
    for path,pin in oldclaim['input_binding_before'].items():
        if path!='experiments/rebuild_status_current.json':assert meta(ROOT/path)==pin,path
    oldrs=[json.loads(x) for x in (ROOT/c['recorded_controls']['evidence/raw.jsonl']['path']).read_text(encoding='ascii').splitlines()]
    cpraw=(ROOT/c['checkpoint']['raw']['path']).read_bytes();assert hashlib.sha256(cpraw).hexdigest()==c['checkpoint']['raw']['sha256']
    cp=next(r['payload']['final_state'] for r in [json.loads(x) for x in cpraw.decode('ascii').splitlines()] if r['tag']=='STREAM_ARM' and r['context'].get('arm')=='DriftOrdinaryExtra')
    rows={}
    for line in (ROOT/c['reference']['path']).read_text(encoding='utf-8').splitlines():
        if line.startswith('DECISION_CONTEXT='):
            q=json.loads(line.split('=',1)[1]);rows[tuple(q['context'])]={a:float.fromhex(v) for a,v in q['q_row_hex']}
    rs=[json.loads(x) for x in (HERE/'evidence/raw.jsonl').read_text(encoding='ascii').splitlines()];assert [x['seq'] for x in rs]==list(range(len(rs)))
    tags=Counter();last={};starts={};tasks=defaultdict(list);details={};post=defaultdict(list);task=None;stack=[];decisions=[];registrations={};issued={};consumed=set();external=None;Ksteps=0;ordinary=0;policyTX=0;externalPolicy=0;feedbackTX=0;summaries=[]
    for r in rs:
        tag,p,ctx=r['tag'],r['payload'],r['context'];tags[tag]+=1;k=key(ctx);case=ctx.get('case');arm=ctx.get('arm')
        if tag=='REFERENCE':assert p['digest']==c['reference']['q_digest'] and p['rows']==len(rows)
        elif tag=='CHECKPOINT_BEFORE':assert p['payload']==cp and p['sha256']==c['checkpoint']['raw']['sha256']
        elif tag=='CHECKPOINT_MATERIALIZED':assert all(p[f]==cp[f] for f in ('immediate','current','learning_values'))
        elif tag=='SOURCE_X_INSTALL':
            expected=deepcopy(cp['current']);expected['X']=[{'address':{'state':{'x':0,'y':2,'t':0,'kappa':0,'phi':3},'cmd':4},'value':3}]
            assert p['before']==cp['current'] and p['after']==expected and p['edits']==[{'store':'controller',**expected['X'][0]}]
        elif tag=='SOURCE_CASE':
            expected=deepcopy(cp['current'])
            if case=='controller':expected['X']=[{'address':{'state':{'x':0,'y':2,'t':0,'kappa':0,'phi':3},'cmd':4},'value':3}]
            assert p['new_role_immediate']==expected and p['values']==cp['learning_values'];starts[case]=expected
        elif tag=='MAIN_INITIALIZED':
            assert p['state']['immediate']==p['state']['current']==starts[case] and p['state']['learning_values']==cp['learning_values']
            assert p['state']['completed_episodes']==p['state']['external_updates']==0 and p['state']['attempted_epochs']==[];last[k]=p['state']
        elif tag=='TASK_BEGIN':
            if ctx['phase']=='practice':assert task is not None and task['key'][0]=='stream';stack.append(task)
            else:assert task is None
            e=p['epoch'];assert e==len(tasks[k]) and p['before']['completed_episodes']==e and p['before']['attempted_epochs']==list(range(e+1))
            assert all(p['before'][f]==last[k][f] for f in p['before'] if f!='attempted_epochs')
            assert p['episode']=={'epoch':e,'kappa':0,'proposal':1,'tape':{'phase':3,'error_flag':0,'cause_rank':12},'coins':[(1<<64)-1]*12,'rejections':[[0]]*12}
            mask={'decision':None,'controller':None,'plant':{'t':0,'realized':3} if case=='plant' else None,'trap':{'cell':[1,2],'t':0}}
            assert p['environment_mask_audit_only']==mask;task={'key':k,'epoch':e,'before':p['before'],'episode':p['episode'],'mask':mask,'diag':0,'tx':0,'writes':0}
        elif tag=='TASK_RAW':
            assert task is not None and task['key']==k;tr=p['trace'];assert tr['mask']==task['mask'] and tr['option_in_force']==1
            at=(0,2,0,0,3);z,m=1,0;cur=stores(task['before']['current']);num=stores(task['before']['learning_values'])
            assert len(p['draws'])==len(tr['steps']) and p['coordinates']==[[i,0,0,(1<<64)-1] for i in range(len(tr['steps']))]
            for i,(d,x) in enumerate(zip(p['draws'],tr['steps'])):
                q=at+(z,m);vr={a:num['Q'].get(q+(a,),v) for a,v in rows[q].items()};cmd=cur['D'].get(q,min(a for a,v in vr.items() if v==max(vr.values())))
                u=cur['X'].get(at+(cmd,),cmd);real=3 if case=='plant' and at[2]==0 else u
                assert d=={'i':i,'explore':False,'admissible':sorted(rows[q]),'a_cmd':cmd} and x['a_cmd']==cmd and x['u']==u and x['a_realized']==real
                at=state(x['state']);z,m=x['control']['z'],x['control']['m']
            assert tr['steps'][-1]['terminal'] and tr['outcome']==tr['steps'][-1]['outcome'] and p['return_hex']==return_value({'trace':tr}).hex()
            task['raw']={**p,'_episode':task['episode']};Ksteps+=len(tr['steps'])
        elif tag=='ORDINARY_UPDATE':
            policyTX+=update(task['before'],task['raw'],p,rows,False);ordinary+=1;task['ordinary']=p['after'];task['after']=p['after']
        elif tag=='DIAGNOSE_BEGIN':
            assert ctx['phase']=='stream' and p['terminal']==task['raw']['trace']['outcome']!='SUCCESS' and p['evidence']==evidence(task['raw']['trace']) and p['state_before']==task['ordinary']
            task['diag']+=1;task['evidence']=p['evidence']
        elif tag=='DIRECT_DECISION':
            assert task['epoch']==0 and p['evidence']==task['evidence'] and p['post_TD']==task['ordinary']
            proposed=proposal(p['evidence']);assert proposed is not None
            site=proposed['edits'][0]['address'];owned=next((x['value'] for x in task['ordinary']['current']['X'] if x['address']==site),None)
            present=owned is not None;wanted=proposed if present else {'action':'keep','edits':[]}
            assert p['proposal']==wanted and p['decision']=={'has_observed_mismatch':True,'site':site,'own_store_present':present,'stored_mapping':owned}
            assert p['plus_experience']==(arm=='DirectSitePlusExperience');task['proposal']=wanted;decisions.append({'case':case,'arm':arm,'own_store_present':present,'proposal':wanted})
        elif tag=='NATIVE_OBSERVATION_REGISTERED':
            assert task['key'][0]=='stream' and arm=='DirectSitePlusExperience' and p['consumer']==task['ordinary'] and p['source_before']['completed_episodes']==0
            assert all(p['source_before'][f]==p['consumer'][f] for f in ('current','learning_values'))
            registrations[p['observation_id']]={'payload':p,'key':k,'parent':task['key']}
        elif tag=='PRACTICE_START':
            assert p['parent']==task['ordinary'] and p['state']['immediate']==p['state']['current']==task['ordinary']['current'] and p['state']['learning_values']==task['ordinary']['learning_values'];last[k]=p['state']
        elif tag=='TASK_COMPLETE':
            assert p['before']==task['before'] and p['trace']==task['raw']['trace'] and p['ordinary_after']==task['ordinary'] and p['after']==task['after'] and p['terminal']==p['trace']['outcome']
            assert p['counters']=={'ordinary_updates':1,'diagnostic_calls':task['diag'],'query_calls':0,'diagnostic_transactions':task['tx'],'diagnostic_edit_addresses':task['writes']}
            if p['terminal']=='SUCCESS':assert task['diag']==task['tx']==task['writes']==0
            assert p['route']['write_spend']==task['writes'] and p['route']['diagnostic_calls']==task['diag'];tasks[k].append(p);details[k]=task;last[k]=p['after'];task=stack.pop() if stack else None
        elif tag=='NATIVE_OBSERVATION_ISSUED':
            reg=registrations[p['observation_id']];assert reg['key']==k and len(tasks[k])==1 and p['trace']==tasks[k][0]['trace'] and p['episode']==details[k]['episode'] and p['source_epoch']==p['main_epoch']==0
            assert p['observation_id'] not in issued;issued[p['observation_id']]=p
        elif tag=='PRACTICE_COMPLETE':assert len(tasks[k])==1 and p['state']==last[k] and number(p['return']).hex()==return_value(tasks[k][0]).hex() and p['observation_id'] in issued
        elif tag=='DIAGNOSTIC_KEEP':assert task['epoch']>0 and p['used'] is True
        elif tag=='DIAGNOSE_RETURN':assert p['proposal']==task.get('proposal',{'action':'keep','edits':[]})
        elif tag=='DIAGNOSTIC_TX_BEGIN':assert p['before']==task['ordinary'] and p['edits']==task['proposal']['edits']
        elif tag=='DIAGNOSTIC_TX_END':
            expected=deepcopy(task['ordinary']);site=task['proposal']['edits'][0]['address'];expected['current']['X']=[x for x in expected['current']['X'] if x['address']!=site];expected['ordinary_PX_anchor']={f:expected['current'][f] for f in ('P','X')}
            assert p['after']==expected;task['after']=p['after'];task['tx']=task['writes']=1;feedbackTX+=1
        elif tag=='EXTERNAL_OBSERVATION_BEGIN':
            assert task is None and not stack and external is None and p['before']==last[k]
            obs=p['observation'];oid=obs['observation_id'];assert issued[oid]==obs and registrations[oid]['parent']==k and oid not in consumed
            assert p['before']['learning_values']==registrations[oid]['payload']['consumer']['learning_values'];consumed.add(oid);external=p
        elif tag=='EXTERNAL_OBSERVATION_END':
            obs=external['observation'];assert p['observation_id']==obs['observation_id'];externalPolicy+=update(external['before'],{'trace':obs['trace'],'_episode':obs['episode']},p,rows,True);last[k]=p['after'];external=None
        elif tag=='KEEP_EXPERIENCE_LEARNED':assert p['observation_id'] in consumed and p['source_completed']==1 and p['observed_epoch']==p['main_epoch']==0 and p['after']==last[k]
        elif tag=='POST_MAIN_STATE':assert task is None and p['epoch']==len(tasks[k])-1 and p['state']==last[k];post[k].append(p['state'])
        elif tag=='STREAM_ARM':
            ts=tasks[k];vals=[return_value(x) for x in ts];assert len(ts)==len(post[k])==p['main_tasks']==6 and p['final_state']==last[k]
            assert p['successes']==sum(x['terminal']=='SUCCESS' for x in ts) and p['outcomes']==[x['terminal'] for x in ts] and [number(v) for v in p['returns']]==vals and number(p['mean_return']).hex()==(sum(vals)/6).hex()
            assert p['external_updates']==int(arm=='DirectSitePlusExperience') and p['direct_events']==1;summaries.append(p)
        elif tag=='RESULT':assert p['streams']==summaries and p['complete'];result=p
        elif tag=='FINAL':assert p['complete'] and p['profile_restored'];final=p
        else:raise AssertionError('unexpected tag '+tag)
    assert task is None and external is None and not stack and len(summaries)==4 and len(consumed)==2 and set(registrations)==set(issued)==consumed
    assert ordinary==26 and tags['SOURCE_X_INSTALL']==1 and feedbackTX==2
    assert final['counts']==result['counts']=={'rollout':ordinary,'step':Ksteps,'transaction':3+1+ordinary+policyTX+len(consumed)+externalPolicy+feedbackTX}
    comparisons=[]
    for case in c['cases']:
        arm='DirectSitePlusExperience';k=('stream',case,arm,None)
        prior=[r['payload'] for r in oldrs if r['tag']=='TASK_COMPLETE' and r['context'].get('phase')=='stream' and r['context'].get('case')==case and r['context'].get('arm')=='TwoStepValue']
        priorpost=[r['payload']['state'] for r in oldrs if r['tag']=='POST_MAIN_STATE' and r['context'].get('case')==case and r['context'].get('arm')=='TwoStepValue']
        oldkeep=next(r['payload']['observation']['trace'] for r in oldrs if r['tag']=='EXTERNAL_OBSERVATION_BEGIN' and r['context'].get('case')==case and r['context'].get('arm')=='TwoStepValue')
        ownkeep=next(v['trace'] for v in issued.values() if registrations[v['observation_id']]['parent']==k)
        assert len(prior)==len(priorpost)==6 and tasks[k][0]['before']['current']==prior[0]['before']['current']
        comparisons.append({'case':case,'recorded_arm':'TwoStepValue','new_arm':arm,
            'all6_main_raw_identical':[x['trace'] for x in tasks[k]]==[x['trace'] for x in prior],
            'all6_post_experience_R_L_I_identical':all(all(x[f]==y[f] for f in ('current','learning_values','immediate')) for x,y in zip(post[k],priorpost)),
            'ingested_first_keep_trace_identical':oldkeep==ownkeep,'initial_R_L_I_identical':all(tasks[k][0]['before'][f]==prior[0]['before'][f] for f in ('current','learning_values','immediate'))})
    compact=[{f:([number(v) for v in x[f]] if f=='returns' else number(x[f]) if f=='mean_return' else x[f]) for f in ('case','arm','successes','returns','outcomes','mean_return','external_updates')} for x in summaries]
    output={'schema':'V145_STDLIB_DIRECT_CONTROL_REVIEW','complete':True,'native_counts':final['counts'],'records':len(rs),'input_pins':len(claim['input_binding_before']),
      'summaries':compact,'direct_decisions':decisions,'comparisons_to_v144':comparisons,'native_ordinary_updates':ordinary,'external_ordinary_updates':len(consumed),
      'native_policy_TX':policyTX,'external_policy_TX':externalPolicy,'main_X_feedback_TX':feedbackTX,'private_X_TX':0,'M_fit_events':0,
      'diagnostic_calls':tags['DIAGNOSE_BEGIN'],'success_diagnostic_calls':0,'old_checker_native_reruns':0,'new_keys_RNG_DP_calibration_collection':0,'formal_B1_or_science_qualification':False}
    save(HERE/'stored_audit_result.json',output);save(out/'exit.json',{'complete':True,'completed_at_utc':datetime.now(timezone.utc).isoformat(),'result':meta(HERE/'stored_audit_result.json')})
    print(json.dumps(output,sort_keys=True))

if __name__=='__main__':main()
