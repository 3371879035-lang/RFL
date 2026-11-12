"""Independent stored review: authentic source transfer, consulted mechanisms, TD and continuation."""
from pathlib import Path
from collections import Counter,defaultdict
from copy import deepcopy
from datetime import datetime,timezone
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


def changes(origin,current,obs):
    old,now=stores(origin),stores(current);out=[];base=obs['trace']['base_option']
    a,b=old['P'].get(base,base),now['P'].get(base,base)
    if a!=b:out.append({'channel':'P','address':base,'origin':a,'current':b})
    at={'x':0,'y':2,'t':0,'kappa':obs['episode']['kappa'],'phi':obs['episode']['tape']['phase']}
    for x in obs['trace']['steps']:
        cmd=x['a_cmd'];q=state(at)+(cmd,);a,b=old['X'].get(q,cmd),now['X'].get(q,cmd)
        if a!=b:out.append({'channel':'X','address':{'state':at,'cmd':cmd},'origin':a,'current':b})
        at=x['state']
    return out


def right_value(p,rows):return stores(p['learning_values'])['Q'].get((0,2,0,0,3,1,0,3),rows[0,2,0,0,3,1,0][3])


def main():
    out=HERE/'evidence_audit';out.mkdir(exist_ok=False)
    def save(p,x):
        with p.open('x',encoding='utf-8',newline='\n') as f:json.dump(x,f,indent=2,ensure_ascii=True);f.write('\n')
    save(out/'claim.json',{'source':meta(Path(__file__)),'native':meta(HERE/'evidence/exit.json'),'automatic_retry':False,'started_at_utc':datetime.now(timezone.utc).isoformat()})
    c=load(HERE/'contract.json');claim=load(HERE/'evidence/claim.json');ex=load(HERE/'evidence/exit.json')
    assert ex['child_exit_code']==0 and ex['input_bytes_unchanged'] and claim['input_binding_before']==ex['input_binding_after']
    for path,q in claim['input_binding_before'].items():assert meta(ROOT/path)==q,path
    assert meta(HERE/'evidence/raw.jsonl')==ex['raw']
    pin=c['checkpoint']['raw'];data=(ROOT/pin['path']).read_bytes();assert meta(ROOT/pin['path'])=={k:pin[k] for k in ('bytes','sha256')}
    cp=next(x['payload']['final_state'] for x in [json.loads(s) for s in data.decode('ascii').splitlines()] if x['tag']=='STREAM_ARM' and x['context'].get('arm')=='DriftOrdinaryExtra')
    rows={}
    for line in (ROOT/c['reference']['path']).read_text(encoding='utf-8').splitlines():
        if line.startswith('DECISION_CONTEXT='):
            q=json.loads(line.split('=',1)[1]);rows[tuple(q['context'])]={a:float.fromhex(v) for a,v in q['q_row_hex']}
    rs=[json.loads(s) for s in (HERE/'evidence/raw.jsonl').read_text(encoding='ascii').splitlines()];assert [x['seq'] for x in rs]==list(range(len(rs)))
    tags=Counter();starts={};last={};tasks=defaultdict(list);details={};post=defaultdict(list);stack=[];task=None;registrations={};issued={};consumed=set();external=None;transfers=[];duplicates=set();summaries=[]
    steps=0;ordinary=0;policyTX=0;extTX=0;extPolicy=0;feedbackTX=0;explorations=0
    for r in rs:
        tag,p,ctx=r['tag'],r['payload'],r['context'];tags[tag]+=1;k=key(ctx);case=ctx.get('case');arm=ctx.get('arm')
        if tag=='REFERENCE':assert p['digest']==c['reference']['q_digest'] and p['rows']==len(rows)
        elif tag=='CHECKPOINT_BEFORE':assert p['payload']==cp and p['sha256']==c['checkpoint']['raw']['sha256']
        elif tag=='CHECKPOINT_MATERIALIZED':assert all(p[f]==cp[f] for f in ('immediate','current','learning_values'))
        elif tag=='SOURCE_INSTALL':
            assert p['before']==cp['current'] and p['values']==cp['learning_values'];expected=stores(cp['current'])
            if case=='affected':expected['D'][(0,2,0,0,3,1,0)]=3;expected['D'][(1,2,2,0,3,1,0)]=3;expected['X'][(0,2,0,0,3,3)]=4;assert len(p['edits'])==3
            else:expected['X'][(0,2,0,0,3,4)]=3;assert len(p['edits'])==1
            assert maps_equal(stores(p['after']),expected);starts[case]=p['after']
        elif tag=='MAIN_INITIALIZED':
            q=p['state'];assert q['immediate']==q['current']==starts[case] and q['learning_values']==cp['learning_values'] and q['completed_episodes']==q['external_updates']==0 and q['attempted_epochs']==[]
            assert ('experience_condition_revision' in q)==(arm=='Conditioned');last[k]=q
        elif tag=='TASK_BEGIN':
            if ctx['phase']=='private':assert task is not None and task['key'][0]=='stream';stack.append(task)
            else:assert task is None
            e=len(tasks[k]);assert p['epoch']==e and p['before']['attempted_epochs']==list(range(e+1)) and all(p['before'][f]==last[k][f] for f in p['before'] if f!='attempted_epochs')
            coins=[(1<<64)-1]*12
            if case=='affected' and e==(0 if ctx['phase']=='private' else 1):coins[0]=0
            assert p['episode']=={'epoch':e,'kappa':0,'proposal':1,'tape':{'phase':3,'error_flag':0,'cause_rank':12},'coins':coins,'rejections':[[0]]*12}
            mask={'decision':None,'controller':None,'plant':None,'trap':{'cell':[1,2],'t':0}};assert p['environment_mask_audit_only']==mask
            task={'key':k,'epoch':e,'before':p['before'],'episode':p['episode'],'mask':mask,'diag':0,'tx':0,'writes':0}
        elif tag=='TASK_RAW':
            tr=p['trace'];assert task is not None and task['key']==k and tr['mask']==task['mask'] and tr['option_in_force']==1
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
            assert task['raw']['trace']['outcome']!='SUCCESS' and p['evidence']==evidence(task['raw']['trace']) and p['state_before']==task['ordinary'];task['diag']+=1;task['evidence']=p['evidence']
        elif tag=='OBSERVATION_SOURCE_BEGIN':
            expected=proposal(task['evidence']);site=expected['edits'][0]['address'];val=next(x['value'] for x in task['ordinary']['current']['X'] if x['address']==site)
            assert task['epoch']==0 and p['evidence']==task['evidence'] and p['proposal']==expected and p['post_TD']==task['ordinary']
            assert p['direct_decision']=={'has_observed_mismatch':True,'site':site,'own_store_present':True,'stored_mapping':val};task['proposal']=expected
        elif tag=='NATIVE_OBSERVATION_REGISTERED':
            assert task is not None and task['key'][0]=='stream' and p['consumer']==task['ordinary'] and p['source_before']['completed_episodes']==0
            assert all(p['source_before'][f]==p['consumer'][f] for f in ('current','learning_values'));registrations[p['observation_id']]={'payload':p,'key':k,'parent':task['key']}
        elif tag=='SOURCE_READY':assert p['parent']==task['ordinary'] and p['state']['immediate']==p['state']['current']==task['ordinary']['current'] and p['state']['learning_values']==task['ordinary']['learning_values'];last[k]=p['state']
        elif tag=='TASK_COMPLETE':
            assert p['before']==task['before'] and p['trace']==task['raw']['trace'] and p['ordinary_after']==task['ordinary'] and p['after']==task['after'] and p['terminal']==p['trace']['outcome']
            assert p['counters']=={'ordinary_updates':1,'diagnostic_calls':task['diag'],'query_calls':0,'diagnostic_transactions':task['tx'],'diagnostic_edit_addresses':task['writes']}
            if p['terminal']=='SUCCESS':assert task['diag']==task['tx']==task['writes']==0
            assert p['route']['diagnostic_calls']==task['diag'] and p['route']['write_spend']==task['writes'];tasks[k].append(p);details[k]=task;last[k]=p['after'];task=stack.pop() if stack else None
        elif tag=='NATIVE_OBSERVATION_ISSUED':
            reg=registrations[p['observation_id']];assert reg['key']==k and len(tasks[k])==1 and p['trace']==tasks[k][0]['trace'] and p['episode']==details[k]['episode'] and p['source_epoch']==p['main_epoch']==0
            assert p['observation_id'] not in issued;issued[p['observation_id']]=p
        elif tag=='SOURCE_COMPLETE':assert len(tasks[k])==1 and p['state']==last[k] and number(p['return']).hex()==return_value(tasks[k][0]).hex() and p['observation_id'] in issued
        elif tag=='DIAGNOSTIC_KEEP':assert task['epoch']>0 and p['used'] is True
        elif tag=='DIAGNOSE_RETURN':assert p['proposal']==task.get('proposal',{'action':'keep','edits':[]})
        elif tag=='DIAGNOSTIC_TX_BEGIN':assert p['before']==task['ordinary'] and p['edits']==task['proposal']['edits']
        elif tag=='DIAGNOSTIC_TX_END':
            expected=deepcopy(task['ordinary']);site=task['proposal']['edits'][0]['address'];expected['current']['X']=[x for x in expected['current']['X'] if x['address']!=site];expected['ordinary_PX_anchor']={f:expected['current'][f] for f in ('P','X')}
            assert p['after']==expected;task['after']=p['after'];task['tx']=task['writes']=1;feedbackTX+=1
        elif tag=='OBSERVATION_MECHANISM_REJECTED':
            obs=p['observation'];oid=obs['observation_id'];reg=registrations[oid];diff=changes(reg['payload']['source_before']['immediate'],last[k]['current'],obs)
            assert task is None and arm=='Conditioned' and case=='affected' and issued[oid]==obs and diff and oid not in consumed and reg['parent']==k
            assert p['before']==p['after']==last[k] and p['consumed_once'] and p['ordinary_update_executed'] is False
            assert p['receipt']=={'applied':False,'reason':'learner_mechanism_changed_on_observed_path','observation_id':oid,'mechanism_changes':diff};consumed.add(oid)
        elif tag=='EXTERNAL_OBSERVATION_BEGIN':
            obs=p['observation'];oid=obs['observation_id'];reg=registrations[oid];assert task is None and external is None and issued[oid]==obs and oid not in consumed and reg['parent']==k and p['before']==last[k]
            assert p['before']['learning_values']==reg['payload']['consumer']['learning_values'] and p['main_clock_advanced'] is False
            if arm=='Conditioned':assert changes(reg['payload']['source_before']['immediate'],p['before']['current'],obs)==[]
            consumed.add(oid);external=p
        elif tag=='EXTERNAL_OBSERVATION_END':
            obs=external['observation'];assert p['observation_id']==obs['observation_id'];extPolicy+=update(external['before'],{'trace':obs['trace'],'_episode':obs['episode']},p,rows,True);extTX+=1;last[k]=p['after'];external=None
        elif tag=='TRANSFER_RESULT':
            oid=p['observation_id'];obs=issued[oid];reg=registrations[oid];diff=changes(reg['payload']['source_before']['immediate'],p['before']['current'],obs)
            assert oid in consumed and p['after']==last[k] and not p['main_closed'] and p['native_delta']=={'rollout':0,'step':0,'transaction':2 if p['applied'] else 0}
            assert p['applied']==(arm=='Legacy' or not diff) and p['after']['external_updates']-p['before']['external_updates']==int(p['applied'])
            if arm=='Legacy':assert p['legacy_return_none'] is True and p['typed_receipt'] is None
            else:
                assert not p['legacy_return_none'];wanted={'applied':p['applied'],'reason':'same_learner_mechanism_on_observed_path' if p['applied'] else 'learner_mechanism_changed_on_observed_path','observation_id':oid,'mechanism_changes':diff};assert p['typed_receipt']==wanted
            if not p['applied']:assert p['before']==p['after']
            transfers.append({'case':case,'arm':arm,'applied':p['applied'],'mechanism_changes':diff,'source_terminal':obs['trace']['outcome'],
                'RIGHT_before':right_value(p['before'],rows),'RIGHT_after':right_value(p['after'],rows),'numeric_changed':p['before']['learning_values']!=p['after']['learning_values'],
                'native_delta':p['native_delta'],'main_closed':p['main_closed']})
        elif tag=='DUPLICATE_REJECTED':
            oid=p['observation_id'];assert oid in consumed and oid not in duplicates and p['native_delta']=={'rollout':0,'step':0,'transaction':0} and p['state_unchanged'] and p['message']=='native observation already consumed; no retry';duplicates.add(oid)
        elif tag=='POST_MAIN_STATE':assert task is None and p['epoch']==len(tasks[k])-1 and p['state']==last[k];post[k].append(p['state'])
        elif tag=='STREAM_ARM':
            ts=tasks[k];vs=[return_value(x) for x in ts];assert len(ts)==len(post[k])==p['main_tasks']==3 and p['final_state']==last[k] and p['main_closed'] is False
            assert [number(x) for x in p['returns']]==vs and p['outcomes']==[x['terminal'] for x in ts] and p['successes']==sum(x['terminal']=='SUCCESS' for x in ts) and number(p['mean_return']).hex()==(sum(vs)/3).hex()
            assert p['observation_applied']==bool(p['external_updates']) and p['external_updates']==int(arm=='Legacy' or case=='unaffected');summaries.append(p)
        elif tag=='RESULT':assert p['complete'] and p['streams']==summaries;result=p
        elif tag=='FINAL':assert p['complete'] and p['profile_restored'];final=p
        else:raise AssertionError('unexpected tag '+tag)
    assert task is None and not stack and external is None and set(registrations)==set(issued)==consumed==duplicates and len(consumed)==4
    assert ordinary==16 and extTX==3 and tags['SOURCE_INSTALL']==2 and feedbackTX==4 and tags['OBSERVATION_MECHANISM_REJECTED']==1
    assert final['counts']==result['counts']=={'rollout':ordinary,'step':steps,'transaction':3+2+ordinary+policyTX+extTX+extPolicy+feedbackTX}
    def method(p,name,cls):
        t=ast.parse(p.read_text(encoding='utf-8'));c=next(x for x in t.body if isinstance(x,ast.ClassDef) and x.name==cls);return next(x for x in c.body if isinstance(x,ast.FunctionDef) and x.name==name)
    base=method(ROOT/'experiments/v04r/controller_horizon_value_v144/mechanism_loop.py','consume_trial_observation','ObservationTaskLoop')
    new=method(HERE/'conditioned_experience.py','consume_trial_observation','ConditionedObservationLoop')
    n=next(i for i,x in enumerate(new.body) if isinstance(x,ast.Expr) and isinstance(x.value,ast.Call) and isinstance(x.value.func,ast.Attribute) and x.value.func.attr=='_check')
    dump=lambda xs:ast.dump(ast.Module(body=xs,type_ignores=[]))
    assert dump(new.body[:n])==dump(base.body[:n]) and dump(new.body[n+3:-1])==dump(base.body[n:])
    comparison=[]
    for case in c['cases']:
        ka=('stream',case,'Legacy',None);kb=('stream',case,'Conditioned',None)
        comparison.append({'case':case,'all3_main_raw_identical':[x['trace'] for x in tasks[ka]]==[x['trace'] for x in tasks[kb]],
           'all3_post_R_L_I_identical':all(all(x[f]==y[f] for f in ('current','learning_values','immediate')) for x,y in zip(post[ka],post[kb]))})
    compact=[{f:([number(v) for v in x[f]] if f=='returns' else number(x[f]) if f=='mean_return' else x[f]) for f in ('case','arm','successes','returns','outcomes','mean_return','observation_applied','external_updates','main_closed')} for x in summaries]
    output={'schema':'V147_STDLIB_MECHANISM_CONDITIONED_REVIEW','complete':True,'native_counts':final['counts'],'records':len(rs),'input_pins':len(claim['input_binding_before']),
      'summaries':compact,'transfers':transfers,'main_comparisons':comparison,'authentic_observations_issued':4,'once_consumed_including_rejection':4,'duplicate_rejections':4,
      'guard_rejections':1,'guard_acceptances':1,'legacy_acceptances':2,'native_ordinary_updates':ordinary,'ordinary_policy_TX':policyTX,'external_ordinary_updates':extTX,'external_policy_TX':extPolicy,
      'prefix_and_accepted_ordinary_apply_AST_exact':True,'actual_P_difference_tested':False,'actual_X_consulted_and_unconsulted_difference_tested':True,
      'new_draws_or_K_on_transfer':0,'success_diagnosis':0,'old_native_checker_reruns':0,'new_keys_RNG_DP_calibration_collection':0,'formal_B1_or_dynamics_totality_qualification':False}
    save(HERE/'stored_audit_result.json',output);save(out/'exit.json',{'complete':True,'completed_at_utc':datetime.now(timezone.utc).isoformat(),'result':meta(HERE/'stored_audit_result.json')})
    print(json.dumps(output,sort_keys=True))

if __name__=='__main__':main()
