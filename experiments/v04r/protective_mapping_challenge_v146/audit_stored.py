"""New stdlib review of the protective-mapping challenge, not an old native/checker run."""
from pathlib import Path
from collections import Counter,defaultdict
from copy import deepcopy
from datetime import datetime,timezone
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
        with p.open('x',encoding='utf-8',newline='\n') as f:json.dump(d,f,indent=2,ensure_ascii=True);f.write('\n')
    save(out/'claim.json',{'source':meta(Path(__file__)),'native':meta(HERE/'evidence/exit.json'),'automatic_retry':False,'started_at_utc':datetime.now(timezone.utc).isoformat()})
    c=load(HERE/'contract.json');claim=load(HERE/'evidence/claim.json');ex=load(HERE/'evidence/exit.json')
    assert ex['child_exit_code']==0 and ex['input_bytes_unchanged'] and claim['input_binding_before']==ex['input_binding_after']
    for path,pin in claim['input_binding_before'].items():assert meta(ROOT/path)==pin,path
    assert meta(HERE/'evidence/raw.jsonl')==ex['raw']
    pin=c['checkpoint']['raw'];raw=(ROOT/pin['path']).read_bytes();assert meta(ROOT/pin['path'])=={k:pin[k] for k in ('bytes','sha256')}
    cp=next(x['payload']['final_state'] for x in [json.loads(s) for s in raw.decode('ascii').splitlines()] if x['tag']=='STREAM_ARM' and x['context'].get('arm')=='DriftOrdinaryExtra')
    for pin in c['recorded_contrast'].values():assert meta(ROOT/pin['path'])=={k:pin[k] for k in ('bytes','sha256')}
    rows={}
    for line in (ROOT/c['reference']['path']).read_text(encoding='utf-8').splitlines():
        if line.startswith('DECISION_CONTEXT='):
            d=json.loads(line.split('=',1)[1]);rows[tuple(d['context'])]={a:float.fromhex(v) for a,v in d['q_row_hex']}
    rs=[json.loads(s) for s in (HERE/'evidence/raw.jsonl').read_text(encoding='ascii').splitlines()];assert [x['seq'] for x in rs]==list(range(len(rs)))
    tags=Counter();last={};tasks=defaultdict(list);details={};post=defaultdict(list);hypotheses={};trial_results={};stack=[];task=None;source=None;summaries=[];model=None
    steps=0;ordinary=0;policyTX=0;feedbackTX=0;privateTX=0;explorations=0
    for r in rs:
        tag,p,ctx=r['tag'],r['payload'],r['context'];tags[tag]+=1;k=key(ctx);arm=ctx.get('arm')
        if tag=='REFERENCE':assert p['digest']==c['reference']['q_digest'] and p['rows']==len(rows)
        elif tag=='CHECKPOINT_BEFORE':assert p['payload']==cp and p['sha256']==c['checkpoint']['raw']['sha256']
        elif tag=='CHECKPOINT_MATERIALIZED':assert all(p[f]==cp[f] for f in ('immediate','current','learning_values'))
        elif tag=='SOURCE_INSTALL':
            assert p['before']==cp['current'] and p['values']==cp['learning_values']
            expected=stores(cp['current']);expected['D'][(0,2,0,0,3,1,0)]=3;expected['D'][(1,2,2,0,3,1,0)]=3;expected['X'][(0,2,0,0,3,3)]=4
            assert maps_equal(stores(p['after']),expected)
            assert p['edits']==[{'store':'decision','address':{'state':{'x':0,'y':2,'t':0,'kappa':0,'phi':3},'z':1,'m':0},'value':3},
                {'store':'controller','address':{'state':{'x':0,'y':2,'t':0,'kappa':0,'phi':3},'cmd':3},'value':4},
                {'store':'decision','address':{'state':{'x':1,'y':2,'t':2,'kappa':0,'phi':3},'z':1,'m':0},'value':3}];source=p['after']
        elif tag=='MAIN_INITIALIZED':
            q=p['state'];assert q['immediate']==q['current']==source and q['learning_values']==cp['learning_values'] and q['completed_episodes']==q['external_updates']==0 and q['attempted_epochs']==[];last[k]=q
        elif tag=='TASK_BEGIN':
            if ctx['phase']=='trial':assert task is not None and task['key'][0]=='stream';stack.append(task)
            else:assert task is None
            e=len(tasks[k]);assert p['epoch']==e and p['before']['attempted_epochs']==list(range(e+1)) and all(p['before'][f]==last[k][f] for f in p['before'] if f!='attempted_epochs')
            coins=[(1<<64)-1]*12
            if e in c['coordinates']['private_explore_epochs' if ctx['phase']=='trial' else 'main_explore_epochs']:coins[0]=0
            assert p['episode']=={'epoch':e,'kappa':0,'proposal':1,'tape':{'phase':3,'error_flag':0,'cause_rank':12},'coins':coins,'rejections':[[0]]*12}
            mask={'decision':None,'controller':None,'plant':None,'trap':{'cell':[1,2],'t':0}}
            assert p['environment_mask_audit_only']==mask;task={'key':k,'epoch':e,'before':p['before'],'episode':p['episode'],'mask':mask,'diag':0,'tx':0,'writes':0}
        elif tag=='TASK_RAW':
            assert task is not None and task['key']==k;tr=p['trace'];assert tr['mask']==task['mask'] and tr['option_in_force']==1
            at=(0,2,0,0,3);z,m=1,0;cur=stores(task['before']['current']);num=stores(task['before']['learning_values']);calls=[]
            assert len(p['draws'])==len(tr['steps'])
            for i,(draw,x) in enumerate(zip(p['draws'],tr['steps'])):
                q=at+(z,m);vr={a:num['Q'].get(q+(a,),v) for a,v in rows[q].items()};greedy=cur['D'].get(q,min(a for a,v in vr.items() if v==max(vr.values())))
                coin=task['episode']['coins'][i];explore=coin==0;cmd=min(rows[q]) if explore else greedy;u=cur['X'].get(at+(cmd,),cmd);calls.append([i,0,0,coin])
                if explore:calls.append([i,1,0,0]);explorations+=1
                assert draw=={'i':i,'explore':explore,'admissible':sorted(rows[q]),'a_cmd':cmd} and x['a_cmd']==cmd and x['u']==x['a_realized']==u
                at=state(x['state']);z,m=x['control']['z'],x['control']['m']
            assert p['coordinates']==calls and tr['steps'][-1]['terminal'] and tr['outcome']==tr['steps'][-1]['outcome'] and p['return_hex']==return_value({'trace':tr}).hex()
            task['raw']={**p,'_episode':task['episode']};steps+=len(tr['steps'])
        elif tag=='ORDINARY_UPDATE':policyTX+=update(task['before'],task['raw'],p,rows,False);ordinary+=1;task['ordinary']=p['after'];task['after']=p['after']
        elif tag=='DIAGNOSE_BEGIN':
            assert task['raw']['trace']['outcome']!='SUCCESS' and p['evidence']==evidence(task['raw']['trace']) and p['state_before']==task['ordinary'];task['evidence']=p['evidence'];task['diag']+=1
        elif tag=='FORCED_KEEP':assert arm=='NoWrite' and task['epoch']==0 and p['evidence']==task['evidence']
        elif tag=='DIRECT_HYPOTHESIS':
            prop=proposal(task['evidence']);site=prop['edits'][0]['address'];owned=next(x['value'] for x in task['ordinary']['current']['X'] if x['address']==site)
            assert p['evidence']==task['evidence'] and p['proposal']==prop and p['post_TD']==task['ordinary']
            assert p['decision']=={'has_observed_mismatch':True,'site':site,'own_store_present':True,'stored_mapping':owned}
            hypotheses[arm]=prop
            if arm=='DirectSite':task['proposal']=prop
        elif tag=='PRIVATE_EDIT':
            assert ctx['candidate']=='controller-delete' and p['before']==task['ordinary']['current'] and p['edits']==hypotheses[arm]['edits']
            expected=deepcopy(p['before']);expected['X']=[x for x in expected['X'] if x['address']!=p['edits'][0]['address']];assert p['after']==expected;privateTX+=1
        elif tag=='TRIAL_START':
            assert task['key'][0]=='stream' and p['parent']==task['ordinary'];expected=deepcopy(task['ordinary']['current'])
            if ctx['candidate']=='controller-delete':expected['X']=[x for x in expected['X'] if x['address']!=hypotheses[arm]['edits'][0]['address']]
            assert p['state']['current']==p['state']['immediate']==expected and p['state']['learning_values']==task['ordinary']['learning_values'];last[k]=p['state']
        elif tag=='TASK_COMPLETE':
            assert p['trace']==task['raw']['trace'] and p['before']==task['before'] and p['ordinary_after']==task['ordinary'] and p['after']==task['after'] and p['terminal']==p['trace']['outcome']
            assert p['counters']=={'ordinary_updates':1,'diagnostic_calls':task['diag'],'query_calls':0,'diagnostic_transactions':task['tx'],'diagnostic_edit_addresses':task['writes']}
            if p['terminal']=='SUCCESS':assert task['diag']==task['tx']==task['writes']==0
            assert p['route']['diagnostic_calls']==task['diag'] and p['route']['write_spend']==task['writes'];tasks[k].append(p);details[k]=task;last[k]=p['after'];task=stack.pop() if stack else None
        elif tag=='TRIAL_COMPLETE':assert len(tasks[k])==2 and p['state']==last[k] and [number(x) for x in p['returns']]==[return_value(x) for x in tasks[k]];trial_results[ctx['candidate']]=[number(x) for x in p['returns']]
        elif tag=='PAIRED_VALUE':
            actual=trial_results;assert {n:[number(x) for x in v] for n,v in p['observed'].items()}==actual and p['parent_unchanged'] is True
            expected={n:sum(v)/2 for n,v in actual.items()};q=p['model'];assert q['horizon']==2 and {n:number(v) for n,v in q['values'].items()}==expected and {n:[number(x) for x in v] for n,v in q['samples'].items()}==actual
            chosen=min(('keep','controller-delete'),key=lambda n:(-expected[n],0 if n=='keep' else 1));assert p['choice']==chosen;task['proposal']=hypotheses[arm] if chosen=='controller-delete' else {'action':'keep','edits':[]};model={'samples':actual,'values':expected,'choice':chosen}
        elif tag=='DIAGNOSTIC_KEEP':assert task['epoch']>0 and p['used'] is True
        elif tag=='DIAGNOSE_RETURN':assert p['proposal']==task.get('proposal',{'action':'keep','edits':[]})
        elif tag=='DIAGNOSTIC_TX_BEGIN':assert p['before']==task['ordinary'] and p['edits']==task['proposal']['edits']
        elif tag=='DIAGNOSTIC_TX_END':
            expected=deepcopy(task['ordinary']);site=task['proposal']['edits'][0]['address'];expected['current']['X']=[x for x in expected['current']['X'] if x['address']!=site];expected['ordinary_PX_anchor']={f:expected['current'][f] for f in ('P','X')}
            assert p['after']==expected;task['after']=p['after'];task['tx']=task['writes']=1;feedbackTX+=1
        elif tag=='POST_MAIN_STATE':assert task is None and p['epoch']==len(tasks[k])-1 and p['state']==last[k];post[k].append(p['state'])
        elif tag=='STREAM_ARM':
            ts=tasks[k];vals=[return_value(x) for x in ts];assert len(ts)==len(post[k])==p['tasks']==6 and p['final_state']==last[k] and p['external_updates']==0
            assert [number(x) for x in p['returns']]==vals and p['outcomes']==[x['terminal'] for x in ts] and p['successes']==sum(x['terminal']=='SUCCESS' for x in ts) and number(p['mean_return']).hex()==(sum(vals)/6).hex();summaries.append(p)
        elif tag=='RESULT':assert p['complete'] and p['streams']==summaries;result=p
        elif tag=='FINAL':assert p['complete'] and p['profile_restored'];final=p
        else:raise AssertionError('unexpected tag '+tag)
    assert task is None and not stack and len(summaries)==3 and ordinary==22
    assert result['counts']==final['counts']=={'rollout':ordinary,'step':steps,'transaction':3+1+ordinary+policyTX+privateTX+feedbackTX}
    old=load(ROOT/c['recorded_contrast']['stored_audit_result.json']['path']);bad=next(x for x in old['models'] if x['case']=='controller' and x['arm']=='TwoStepValue')
    context_comparison={'old_broken_controller_values':bad['scores'],'new_protective_values':model['values'],
        'same_delete_absolute_value':bad['scores']['controller-delete']==model['values']['controller-delete'],
        'old_choice':bad['choice'],'new_choice':model['choice']}
    a=('stream',None,'NoWrite',None);b=('stream',None,'PairedValue',None)
    equivalence={'all6main_raw_identical':[x['trace'] for x in tasks[a]]==[x['trace'] for x in tasks[b]],
      'all6post_R_L_I_identical':all(all(x[f]==y[f] for f in ('current','learning_values','immediate')) for x,y in zip(post[a],post[b]))}
    compact=[{f:([number(v) for v in x[f]] if f=='returns' else number(x[f]) if f=='mean_return' else x[f]) for f in ('arm','successes','outcomes','returns','mean_return')} for x in summaries]
    first=[tasks['stream',None,arm,None][0]['trace'] for arm in c['arms']];assert first[0]==first[1]==first[2]
    dkey=(1,2,2,0,3,1,0);first_after=stores(tasks[a][0]['ordinary_after']['current']);assert first_after['D'][dkey]==0
    output={'schema':'V146_STDLIB_PROTECTIVE_MAPPING_REVIEW','complete':True,'native_counts':final['counts'],'records':len(rs),'input_pins':len(claim['input_binding_before']),
        'summaries':compact,'paired_value_model':model,'historical_value_contrast':context_comparison,'NoWrite_PairedValue_equivalence':equivalence,
        'first_factual_fullraw_equal_all_arms':True,'ordinary_TD_already_restores_actual_bad_D_to_UP':True,'native_ordinary_updates':ordinary,'ordinary_policy_TX':policyTX,
        'source_checkpoint_TX':3,'source_install_TX':1,'source_install_edits':3,'private_X_TX':privateTX,'main_X_TX':feedbackTX,
        'actual_exploration_events':explorations,'main_diagnostic_calls':tags['DIAGNOSE_BEGIN'],'success_diagnostic_calls':0,
        'external_observation_ingestions':0,'model_fits':tags['PAIRED_VALUE'],'old_native_checker_reruns':0,'new_keys_RNG_DP_calibration_collection':0,'formal_B1_or_science_qualification':False}
    save(HERE/'stored_audit_result.json',output);save(out/'exit.json',{'complete':True,'completed_at_utc':datetime.now(timezone.utc).isoformat(),'result':meta(HERE/'stored_audit_result.json')})
    print(json.dumps(output,sort_keys=True))

if __name__=='__main__':main()
