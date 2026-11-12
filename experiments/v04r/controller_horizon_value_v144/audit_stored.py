"""New stdlib capture review, including delayed value and confounded negative result."""
from collections import Counter,defaultdict
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import ast,hashlib,json
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
    def save(p,x):
        with p.open('x',encoding='utf-8',newline='\n') as f:json.dump(x,f,indent=2,ensure_ascii=True);f.write('\n')
    save(out/'claim.json',{'started_at_utc':datetime.now(timezone.utc).isoformat(),'source':meta(Path(__file__)),'native':meta(HERE/'evidence/exit.json'),'automatic_retry':False})
    c=load(HERE/'contract.json');claim=load(HERE/'evidence/claim.json');ex=load(HERE/'evidence/exit.json')
    assert ex['child_exit_code']==0 and ex['input_bytes_unchanged'] and claim['input_binding_before']==ex['input_binding_after']
    for name,pin in claim['input_binding_before'].items():assert meta(ROOT/name)==pin,name
    assert meta(HERE/'evidence/raw.jsonl')==ex['raw']
    for n in ('raw','stored_review','contract'):
        pin=c['checkpoint'][n];assert meta(ROOT/pin['path'])=={k:pin[k] for k in ('bytes','sha256')}
    oldrs=[json.loads(x) for x in (ROOT/c['checkpoint']['raw']['path']).read_text(encoding='ascii').splitlines()]
    cp=next(r['payload']['final_state'] for r in oldrs if r['tag']=='STREAM_ARM' and r['context'].get('arm')=='DriftOrdinaryExtra')
    rows={}
    for line in (ROOT/c['reference']['path']).read_text(encoding='utf-8').splitlines():
        if line.startswith('DECISION_CONTEXT='):
            d=json.loads(line.split('=',1)[1]);rows[tuple(d['context'])]={a:float.fromhex(v) for a,v in d['q_row_hex']}
    rs=[json.loads(x) for x in (HERE/'evidence/raw.jsonl').read_text(encoding='ascii').splitlines()];assert [r['seq'] for r in rs]==list(range(len(rs)))
    tags=Counter();case_starts={};last={};tasks=defaultdict(list);details={};post=defaultdict(list);task=None;stack=[];trial_starts={};trial_results={};menus={};models=[];summaries=[]
    registrations={};issued={};consumed=set();external=None;Ksteps=0;ordinary=0;policyTX=0;external_policyTX=0;external_rows=[];main_feedback_TX=0;private_TX=0
    for r in rs:
        tag,p,ctx=r['tag'],r['payload'],r['context'];tags[tag]+=1;k=key(ctx);case=ctx.get('case');arm=ctx.get('arm');ak=(case,arm)
        if tag=='REFERENCE':assert p['digest']==c['reference']['q_digest'] and p['rows']==len(rows)
        elif tag=='CHECKPOINT_BEFORE':assert p['payload']==cp and p['sha256']==c['checkpoint']['raw']['sha256']
        elif tag=='CHECKPOINT_MATERIALIZED':assert all(p[f]==cp[f] for f in ('immediate','current','learning_values'))
        elif tag=='SOURCE_X_INSTALL':
            assert case=='controller' and p['before']==cp['current']
            expect=deepcopy(cp['current']);expect['X']=[{'address':{'state':{'x':0,'y':2,'t':0,'kappa':0,'phi':3},'cmd':4},'value':3}]
            assert p['after']==expect and p['edits']==[{'store':'controller',**expect['X'][0]}]
        elif tag=='SOURCE_CASE':
            expect=deepcopy(cp['current'])
            if c['cases'][case]['install_controller']:expect['X']=[{'address':{'state':{'x':0,'y':2,'t':0,'kappa':0,'phi':3},'cmd':4},'value':3}]
            assert p['new_role_immediate']==expect and p['values']==cp['learning_values'];case_starts[case]=expect
        elif tag=='MAIN_INITIALIZED':
            q=p['state'];assert q['immediate']==q['current']==case_starts[case] and q['learning_values']==cp['learning_values']
            assert q['completed_episodes']==q['external_updates']==0 and q['attempted_epochs']==[]
            assert q['ordinary_PX_anchor']=={f:q['current'][f] for f in ('P','X')};last[k]=q
        elif tag=='TASK_BEGIN':
            if ctx['phase']=='trial':assert task is not None and task['key'][0]=='stream' and task['diag']==1;stack.append(task)
            else:assert task is None
            e=p['epoch'];assert e==len(tasks[k]) and p['before']['completed_episodes']==e and p['before']['attempted_epochs']==list(range(e+1))
            assert all(p['before'][f]==last[k][f] for f in p['before'] if f!='attempted_epochs')
            ep=p['episode'];assert ep=={'epoch':e,'kappa':0,'proposal':1,'tape':{'phase':3,'error_flag':0,'cause_rank':12},'coins':[(1<<64)-1]*12,'rejections':[[0]]*12}
            mask={'decision':None,'controller':None,'plant':{'t':0,'realized':3} if case=='plant' else None,'trap':{'cell':[1,2],'t':0}}
            assert p['environment_mask_audit_only']==mask
            task={'key':k,'epoch':e,'before':p['before'],'episode':ep,'mask':mask,'diag':0,'tx':0,'writes':0}
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
            assert task is not None and task['key']==k;policyTX+=update(task['before'],task['raw'],p,rows,False);ordinary+=1;task['ordinary']=p['after'];task['after']=p['after']
        elif tag=='DIAGNOSE_BEGIN':
            assert task is not None and task['key']==k and ctx['phase']=='stream' and task['raw']['trace']['outcome']!='SUCCESS'
            assert p['evidence']==evidence(task['raw']['trace']) and p['state_before']==task['ordinary'] and p['terminal']==task['raw']['trace']['outcome'];task['diag']+=1;task['evidence']=p['evidence']
        elif tag=='TRIAL_MENU':
            assert task is not None and task['epoch']==0 and p['evidence']==task['evidence'] and p['post_TD']==task['ordinary'] and p['candidate']==proposal(task['evidence'])
            assert p['horizon']==2 and ak not in menus;menus[ak]=p
        elif tag=='PRIVATE_EDIT':
            assert task is not None and task['key'][0]=='stream' and ctx['candidate']=='controller-delete'
            assert p['before']==task['ordinary']['current'] and p['edits']==menus[ak]['candidate']['edits']
            expect=deepcopy(p['before']);expect['X']=[x for x in expect['X'] if x['address']!=p['edits'][0]['address']]
            assert p['after']==expect;private_TX+=1
        elif tag=='NATIVE_OBSERVATION_REGISTERED':
            assert task is not None and task['key'][0]=='stream' and ctx['candidate']=='keep' and p['consumer']==task['ordinary']
            assert all(p['source_before'][f]==p['consumer'][f] for f in ('current','learning_values')) and p['source_before']['completed_episodes']==p['source_before']['external_updates']==0
            assert p['observation_id'] not in registrations;registrations[p['observation_id']]={'payload':p,'key':k,'parent':task['key']}
        elif tag=='TRIAL_START':
            root=task['ordinary'];expect=deepcopy(root['current'])
            if ctx['candidate']=='controller-delete':expect['X']=[x for x in expect['X'] if x['address']!=menus[ak]['candidate']['edits'][0]['address']]
            assert p['parent']==root and p['state']['immediate']==p['state']['current']==expect and p['state']['learning_values']==root['learning_values']
            assert p['state']['ordinary_PX_anchor']=={f:expect[f] for f in ('P','X')};last[k]=p['state'];trial_starts[k]=p
        elif tag=='TASK_COMPLETE':
            assert task is not None and task['key']==k and p['before']==task['before'] and p['trace']==task['raw']['trace'] and p['ordinary_after']==task['ordinary'] and p['after']==task['after']
            assert p['terminal']==p['trace']['outcome'] and p['counters']=={'ordinary_updates':1,'diagnostic_calls':task['diag'],'query_calls':0,'diagnostic_transactions':task['tx'],'diagnostic_edit_addresses':task['writes']}
            if p['terminal']=='SUCCESS':assert task['diag']==task['tx']==task['writes']==0
            assert p['after']['immediate']==p['before']['immediate'] and p['route']['write_spend']==task['writes'] and p['route']['diagnostic_calls']==task['diag']
            tasks[k].append(p);details[k]=task;last[k]=p['after'];task=stack.pop() if stack else None
        elif tag=='NATIVE_OBSERVATION_ISSUED':
            assert ctx['candidate']=='keep' and len(tasks[k])==1 and p['trace']==tasks[k][0]['trace'] and p['episode']==details[k]['episode'] and p['source_epoch']==0 and p['main_epoch']==0
            reg=registrations[p['observation_id']];assert reg['key']==k and p['observation_id'] not in issued
            assert p['issuer_label']==reg['payload']['source_label'] and p['consumer_label']==reg['payload']['consumer']['source_label'];issued[p['observation_id']]=p
        elif tag=='TRIAL_COMPLETE':
            assert len(tasks[k])==p['source_complete_tasks']==2 and p['final_state']==last[k] and [number(x) for x in p['returns']]==[return_value(t) for t in tasks[k]]
            trial_results[k]=[number(x) for x in p['returns']]
        elif tag=='LEARNED_HORIZON_VALUE':
            assert task is not None and task['key']==k and p['main_before']==task['ordinary']
            actual={n:trial_results['trial',case,arm,n] for n in ('keep','controller-delete')};assert {n:[number(v) for v in vs] for n,vs in p['actual_trial_returns'].items()}==actual
            h=1 if arm=='OneStepValue' else 2;expected={n:sum(v[:h])/h for n,v in actual.items()};model=p['model']
            assert model['horizon']==h and {n:number(v) for n,v in model['values'].items()}==expected and {n:[number(v) for v in vs] for n,vs in model['samples'].items()}=={n:v[:h] for n,v in actual.items()}
            chosen=min(('keep','controller-delete'),key=lambda n:(-expected[n],0 if n=='keep' else 1));executed='keep' if arm=='ExperienceNoWrite' else chosen
            assert p['learned_choice']==chosen and p['executed_choice']==executed and p['force_NoWrite']==(arm=='ExperienceNoWrite');task['choice']=executed;models.append({'case':case,'arm':arm,'horizon':h,'scores':expected,'choice':chosen,'executed':executed,'returns':actual})
        elif tag=='DIAGNOSTIC_KEEP':assert task is not None and task['epoch']>0 and p['used'] is True
        elif tag=='DIAGNOSE_RETURN':
            wanted=menus[ak]['candidate'] if task.get('choice')=='controller-delete' else {'action':'keep','edits':[]}
            assert p['proposal']==wanted
        elif tag=='DIAGNOSTIC_TX_BEGIN':
            assert task is not None and task['choice']=='controller-delete' and p['before']==task['ordinary'] and p['edits']==menus[ak]['candidate']['edits'];task['edits']=p['edits']
        elif tag=='DIAGNOSTIC_TX_END':
            expect=deepcopy(task['ordinary']);expect['current']['X']=[x for x in expect['current']['X'] if x['address']!=task['edits'][0]['address']];expect['ordinary_PX_anchor']={f:expect['current'][f] for f in ('P','X')}
            assert p['after']==expect;task['after']=p['after'];task['tx']+=1;task['writes']+=1;main_feedback_TX+=1
        elif tag=='EXTERNAL_OBSERVATION_BEGIN':
            assert task is None and not stack and external is None and p['before']==last[k] and p['main_clock_advanced'] is False
            obs=p['observation'];oid=obs['observation_id'];reg=registrations[oid];assert issued[oid]==obs and reg['parent']==k and oid not in consumed and len(tasks[reg['key']])==2
            assert p['before']['learning_values']==reg['payload']['consumer']['learning_values'];consumed.add(oid);external=p
        elif tag=='EXTERNAL_OBSERVATION_END':
            assert external is not None;obs=external['observation'];assert p['observation_id']==obs['observation_id']
            external_policyTX+=update(external['before'],{'trace':obs['trace'],'_episode':obs['episode']},p,rows,True)
            last[k]=p['after'];external_rows.append({'case':case,'arm':arm,'observation_id':p['observation_id'],'source_terminal':obs['trace']['outcome'],'numeric_changed':external['before']['learning_values']!=p['after']['learning_values']});external=None
        elif tag=='KEEP_EXPERIENCE_LEARNED':assert p['observation_id'] in consumed and p['after']==last[k] and p['source_completed']==2 and p['observed_epoch']==p['main_epoch']==0
        elif tag=='POST_MAIN_STATE':assert task is None and p['epoch']==len(tasks[k])-1 and p['state']==last[k];post[k].append(p)
        elif tag=='STREAM_ARM':
            assert len(tasks[k])==len(post[k])==p['main_tasks']==6 and p['final_state']==last[k] and p['external_updates']==p['trial_events']==1
            vals=[return_value(t) for t in tasks[k]];assert [number(x) for x in p['returns']]==vals and number(p['mean_return']).hex()==(sum(vals)/6).hex()
            assert p['outcomes']==[t['terminal'] for t in tasks[k]] and p['successes']==sum(t['terminal']=='SUCCESS' for t in tasks[k]);summaries.append(p)
        elif tag=='RESULT':assert p['streams']==summaries and p['complete'];result=p
        elif tag=='FINAL':assert p['complete'] and p['profile_restored'];final=p
        else:raise AssertionError('unexpected tag '+tag)
    assert task is None and not stack and external is None and set(registrations)==set(issued)==consumed and len(consumed)==6
    assert len(summaries)==6 and ordinary==60 and tags['SOURCE_X_INSTALL']==1 and private_TX==6
    assert result['counts']==final['counts']=={'rollout':ordinary,'step':Ksteps,'transaction':3+1+ordinary+policyTX+len(consumed)+external_policyTX+private_TX+main_feedback_TX}
    # First observed task evidence is equal across mechanisms, without exposing raw u/mask as features.
    first=[evidence(tasks['stream',case,arm,None][0]['trace']) for case in c['cases'] for arm in c['arms']];assert all(x==first[0] for x in first)
    for case in c['cases']:
        for name in ('keep','controller-delete'):
            ts=[[t['trace'] for t in tasks['trial',case,arm,name]] for arm in c['arms']];assert ts[0]==ts[1]==ts[2]
    # Ordinary numerical/policy body remains exactly the executed v141 implementation.
    def method(p,cls,name):
        t=ast.parse(p.read_text(encoding='utf-8'));cl=next(x for x in t.body if isinstance(x,ast.ClassDef) and x.name==cls);return next(x for x in cl.body if isinstance(x,ast.FunctionDef) and x.name==name)
    assert ast.dump(method(HERE/'mechanism_loop.py','ObservationTaskLoop','_update_from_observed_trace'))==ast.dump(method(ROOT/'experiments/v04r/owned_trial_learning_v141/observation_loop.py','ObservationTaskLoop','_update_from_observed_trace'))
    compact=[{k:([number(v) for v in x[k]] if k=='returns' else number(x[k]) if k=='mean_return' else x[k]) for k in ('case','arm','successes','returns','outcomes','mean_return','external_updates')} for x in summaries]
    output={'schema':'V144_STDLIB_CONTROLLER_HORIZON_REVIEW','complete':True,'native_counts':final['counts'],'records':len(rs),'input_pins':len(claim['input_binding_before']),
        'summaries':compact,'models':models,'observations':external_rows,'native_ordinary_updates':ordinary,'ordinary_policy_TX':policyTX,'external_ordinary_updates':len(consumed),'external_policy_TX':external_policyTX,
        'checkpoint_TX':3,'source_install_TX':1,'private_X_TX':private_TX,'main_X_feedback_TX':main_feedback_TX,
        'main_tasks':36,'private_tasks':24,'main_diagnostic_calls':tags['DIAGNOSE_BEGIN'],'success_diagnostic_calls':0,
        'same_first_visible_evidence_across_causes':True,'same_actual_trial_data_within_case_all_arms':True,'ordinary_math_AST_exact':True,
        'old_checker_native_reruns':0,'new_keys_RNG_DP_calibration_collection':0,'formal_B1_whole_or_backend_qualification':False}
    save(HERE/'stored_audit_result.json',output);save(out/'exit.json',{'complete':True,'completed_at_utc':datetime.now(timezone.utc).isoformat(),'result':meta(HERE/'stored_audit_result.json')})
    print(json.dumps(output,sort_keys=True))

if __name__=='__main__':main()
