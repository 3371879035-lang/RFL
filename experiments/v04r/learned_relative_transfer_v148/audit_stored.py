"""New stdlib review of historical supervision, frozen CART and new coordinate outcomes."""
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


def evidence(trace):
    s0=trace['steps'][0]['state'];at={'x':0,'y':2,'t':0,'kappa':s0['kappa'],'phi':s0['phi']};z,m=trace['option_in_force'],0;out=[]
    for x in trace['steps']:
        out.append({**at,'z':z,'m':m,'a_cmd':x['a_cmd'],'a_realized':x['a_realized'],'reward':{'binary64_hex':float(round(number(x['reward']),6)).hex()}})
        at=x['state'];z,m=x['control']['z'],x['control']['m']
    return {'steps':out,'z_in_force':trace['option_in_force'],'kappa':s0['kappa'],'phi':s0['phi']}

def feat(ev,current):
    for i,x in enumerate(ev['steps']):
        if x['a_cmd']!=x['a_realized']:
            site={'state':{k:x[k] for k in ('x','y','t','kappa','phi')},'cmd':x['a_cmd']}
            return [len(ev['steps'])-i-1,int(any(x['address']==site for x in current['X']))]
    return None

def plain(x):
    if isinstance(x,dict):return number(x) if set(x)=={'binary64_hex'} else {k:plain(v) for k,v in x.items()}
    if isinstance(x,list):return [plain(v) for v in x]
    return x

def predict(tree,x):
    if x is None:return 0.0
    if 'mean' in tree:return tree['mean']
    return predict(tree['left'] if x[tree['feature']]<=tree['threshold'] else tree['right'],x)

def verify_cart(node,points):
    avg=sum(p['y'] for p in points)/len(points);loss=lambda ps:sum((p['y']-sum(q['y'] for q in ps)/len(ps))**2 for p in ps)
    candidates=[]
    for f in (0,1):
        xs=sorted(set(p['x'][f] for p in points))
        for a,b in zip(xs,xs[1:]):
            cut=(a+b)/2;l=[p for p in points if p['x'][f]<=cut];r=[p for p in points if p['x'][f]>cut];candidates.append((loss(l)+loss(r),f,cut,l,r))
    best=min(candidates,key=lambda x:x[:3]) if candidates else None
    if best is None or best[0]>=loss(points):assert set(node)=={'mean','n'} and node['mean'].hex()==avg.hex() and node['n']==len(points)
    else:
        score,f,cut,l,r=best;assert node['feature']==f and node['threshold']==cut;verify_cart(node['left'],l);verify_cart(node['right'],r)


def main():
    out=HERE/'evidence_audit';out.mkdir(exist_ok=False)
    def save(p,d):
        with p.open('x',encoding='utf-8',newline='\n') as f:json.dump(d,f,ensure_ascii=True,indent=2);f.write('\n')
    save(out/'claim.json',{'source':meta(Path(__file__)),'native':meta(HERE/'evidence/exit.json'),'automatic_retry':False,'started_at_utc':datetime.now(timezone.utc).isoformat()})
    c=load(HERE/'contract.json');claim=load(HERE/'evidence/claim.json');ex=load(HERE/'evidence/exit.json')
    assert ex['child_exit_code']==0 and ex['input_bytes_unchanged'] and claim['input_binding_before']==ex['input_binding_after']
    for path,pin in claim['input_binding_before'].items():assert meta(ROOT/path)==pin,path
    assert meta(HERE/'evidence/raw.jsonl')==ex['raw']
    training=[]
    for spec in c['training_sources']:
        for f in ('raw','exit','review'):assert meta(ROOT/spec[f]['path'])=={k:spec[f][k] for k in ('bytes','sha256')}
        oldrs=[json.loads(s) for s in (ROOT/spec['raw']['path']).read_text(encoding='ascii').splitlines()]
        selected=[r for r in oldrs if r['context'].get('arm')==spec['arm'] and r['context'].get('case')==spec['case']]
        d=next(r for r in selected if r['tag']=='DIAGNOSE_BEGIN');ev=d['payload']['evidence'];trial={r['context']['candidate']:[number(v) for v in r['payload']['returns']] for r in selected if r['tag']=='TRIAL_COMPLETE'}
        assert all(len(v)==2 for v in trial.values()) and set(trial)=={'keep','controller-delete'}
        delta=sum(trial['controller-delete'])/2-sum(trial['keep'])/2
        training.append({'id':spec['id'],'x':feat(ev,d['payload']['state_before']['current']),'y':delta,'paired_returns':trial,'context':[ev['kappa'],ev['phi']],
             'raw_sha256':spec['raw']['sha256'],'factual_seq':d['seq']})
    assert len(training)==3 and all(p['context']==c['training_context'] for p in training) and c['test_context']!=c['training_context']
    rows={}
    for line in (ROOT/c['reference']['path']).read_text(encoding='utf-8').splitlines():
        if line.startswith('DECISION_CONTEXT='):
            q=json.loads(line.split('=',1)[1]);rows[tuple(q['context'])]={a:float.fromhex(v) for a,v in q['q_row_hex']}
    rs=[json.loads(s) for s in (HERE/'evidence/raw.jsonl').read_text(encoding='ascii').splitlines()];assert [r['seq'] for r in rs]==list(range(len(rs)))
    tags=Counter();last={};tasks=defaultdict(list);post=defaultdict(list);details={};task=None;stack=[];sources={};registrations={};issued={};consumed=set();external=None;summaries=[];preds={};paired={};trialvals={}
    steps=0;ordinary=0;policyTX=0;ext=0;extpolicy=0;feedbackTX=0;privateTX=0;sourceTX=0;rejections=0;explorations=0;tree=None;modelseal=None;transfers=[]
    for r in rs:
        tag,p,ctx=r['tag'],r['payload'],r['context'];tags[tag]+=1;k=key(ctx);case=ctx.get('case');arm=ctx.get('arm');ak=(case,arm)
        if tag=='REFERENCE':assert p['digest']==c['reference']['q_digest'] and p['rows']==len(rows)
        elif tag=='FROZEN_RELATIVE_MODEL':
            q=plain(p);assert q==load(HERE/'frozen_model.json') and q['points']==training and q['native_work_before_fit']=={'rollout':0,'step':0,'transaction':0}
            tree=q['tree'];verify_cart(tree,training);assert p['wire_digest']==digest(p['tree']);modelseal=p['wire_digest']
        elif tag=='PREP_SEED':
            assert tree is not None;seed=p['state'];assert seed['D']==[{'address':{'state':{'x':0,'y':2,'t':0,'kappa':1,'phi':0},'z':1,'m':0},'value':3}] and seed['P']==seed['X']==seed['Q']==[]
        elif tag=='TASK_BEGIN':
            if ctx['phase']=='private':assert task is not None and task['key'][0]=='stream';stack.append(task)
            else:assert task is None
            e=len(tasks[k]);assert p['epoch']==e and p['before']['attempted_epochs']==list(range(e+1))
            if ctx['phase']=='prep':
                assert e==0 and p['before']['immediate']==p['before']['current']==seed and all(not v for v in p['before']['learning_values'].values()) and p['before']['completed_episodes']==p['before']['external_updates']==0
            else:assert all(p['before'][f]==last[k][f] for f in p['before'] if f!='attempted_epochs')
            coins=[(1<<64)-1]*12
            if case=='protective' and e==(0 if ctx['phase']=='private' else 1):coins[0]=0
            assert p['episode']=={'epoch':e,'kappa':1,'proposal':1,'tape':{'phase':0,'error_flag':0,'cause_rank':12},'coins':coins,'rejections':[[0]]*12}
            mask={'decision':None,'controller':None,'plant':{'t':0,'realized':3} if case=='plant' else None,'trap':{'cell':[1,2],'t':0}};assert p['environment_mask_audit_only']==mask
            task={'key':k,'epoch':e,'before':p['before'],'episode':p['episode'],'mask':mask,'diag':0,'tx':0,'writes':0}
        elif tag=='TASK_RAW':
            tr=p['trace'];assert task is not None and task['key']==k and tr['mask']==task['mask'] and tr['option_in_force']==1
            at=(0,2,0,1,0);z,m=1,0;cur=stores(task['before']['current']);num=stores(task['before']['learning_values']);calls=[];assert len(p['draws'])==len(tr['steps'])
            for i,(draw,x) in enumerate(zip(p['draws'],tr['steps'])):
                q=at+(z,m);vs={a:num['Q'].get(q+(a,),v) for a,v in rows[q].items()};greedy=cur['D'].get(q,min(a for a,v in vs.items() if v==max(vs.values())))
                coin=task['episode']['coins'][i];explore=coin==0;cmd=min(rows[q]) if explore else greedy;u=cur['X'].get(at+(cmd,),cmd);real=3 if case=='plant' and at[2]==0 else u;calls.append([i,0,0,coin])
                if explore:calls.append([i,1,0,0]);explorations+=1
                assert draw=={'i':i,'explore':explore,'admissible':sorted(rows[q]),'a_cmd':cmd} and x['a_cmd']==cmd and x['u']==u and x['a_realized']==real
                at=state(x['state']);z,m=x['control']['z'],x['control']['m']
            assert p['coordinates']==calls and tr['steps'][-1]['terminal'] and tr['outcome']==tr['steps'][-1]['outcome'] and p['return_hex']==return_value({'trace':tr}).hex()
            task['raw']={**p,'_episode':task['episode']};steps+=len(tr['steps'])
        elif tag=='ORDINARY_UPDATE':policyTX+=update(task['before'],task['raw'],p,rows,False);ordinary+=1;task['ordinary']=p['after'];task['after']=p['after']
        elif tag=='TASK_COMPLETE':
            assert p['trace']==task['raw']['trace'] and p['before']==task['before'] and p['ordinary_after']==task['ordinary'] and p['after']==task['after'] and p['terminal']==p['trace']['outcome']
            assert p['counters']=={'ordinary_updates':1,'diagnostic_calls':task['diag'],'query_calls':0,'diagnostic_transactions':task['tx'],'diagnostic_edit_addresses':task['writes']}
            if p['terminal']=='SUCCESS':assert task['diag']==task['tx']==task['writes']==0
            assert p['route']['write_spend']==task['writes'] and p['route']['diagnostic_calls']==task['diag'];tasks[k].append(p);details[k]=task;last[k]=p['after'];task=stack.pop() if stack else None
        elif tag=='PREPARATION_COMPLETE':assert p['receipt']==tasks[k][-1] and p['state']==last[k] and p['state']['completed_episodes']==1;prep=p['state']
        elif tag=='SOURCE_CASE':
            assert p['before']==prep['current'] and p['values']==prep['learning_values'];expected=stores(prep['current'])
            if case=='broken':expected['X'][(0,2,0,1,0,4)]=3;assert len(p['edits'])==1;sourceTX+=1
            elif case=='protective':expected['D'][(0,2,0,1,0,1,0)]=3;expected['D'][(1,2,2,1,0,1,0)]=3;expected['X'][(0,2,0,1,0,3)]=4;assert len(p['edits'])==3;sourceTX+=1
            else:assert p['edits']==[]
            assert maps_equal(stores(p['state']),expected);sources[case]=p['state']
        elif tag=='MAIN_INITIALIZED':
            q=p['state'];assert q['immediate']==q['current']==sources[case] and q['learning_values']==prep['learning_values'] and q['completed_episodes']==q['external_updates']==0 and q['attempted_epochs']==[] and q['experience_condition_revision']=='v147-consulted-own-PX-only';last[k]=q
        elif tag=='DIAGNOSE_BEGIN':
            assert ctx['phase']=='stream' and task['raw']['trace']['outcome']!='SUCCESS' and p['evidence']==evidence(task['raw']['trace']) and p['state_before']==task['ordinary'];task['diag']+=1;task['evidence']=p['evidence']
        elif tag=='FROZEN_PREDICTION':
            x=feat(task['evidence'],task['ordinary']['current']);y=predict(tree,x);prop=proposal(task['evidence']) if y>0 else {'action':'keep','edits':[]}
            assert arm=='FrozenLearned' and p['features']==x and number(p['predicted_delta']).hex()==y.hex() and p['proposal']==prop and p['frozen_digest']==modelseal;preds[case]={'features':x,'predicted_delta':y,'proposal':prop,'pattern_seen':x in [v['x'] for v in training]}
        elif tag=='DIAGNOSTIC_INPUT':
            assert task['epoch']==0 and p['evidence']==task['evidence'] and p['post_TD']==task['ordinary'] and p['features']==feat(task['evidence'],task['ordinary']['current']) and p['candidate']==proposal(task['evidence'])
            assert p['trial_horizon']==(2 if arm=='Validated' else 1);task['candidate']=p['candidate']
        elif tag=='NATIVE_OBSERVATION_REGISTERED':
            assert task is not None and task['key'][0]=='stream' and p['consumer']==task['ordinary'] and p['source_before']['completed_episodes']==0 and all(p['source_before'][f]==p['consumer'][f] for f in ('current','learning_values'))
            registrations[p['observation_id']]={'payload':p,'key':k,'parent':task['key']}
        elif tag=='PRIVATE_EDIT':
            assert arm=='Validated' and ctx['candidate']=='controller-delete' and p['before']==task['ordinary']['current'] and p['edits']==task['candidate']['edits']
            expected=deepcopy(p['before']);expected['X']=[x for x in expected['X'] if x['address']!=p['edits'][0]['address']];assert p['after']==expected;privateTX+=1
        elif tag=='PRIVATE_START':
            assert p['parent']==task['ordinary'];expected=deepcopy(task['ordinary']['current'])
            if ctx['candidate']=='controller-delete':expected['X']=[x for x in expected['X'] if x['address']!=task['candidate']['edits'][0]['address']]
            assert p['state']['immediate']==p['state']['current']==expected and p['state']['learning_values']==task['ordinary']['learning_values'] and p['n']==(2 if arm=='Validated' else 1);last[k]=p['state']
        elif tag=='NATIVE_OBSERVATION_ISSUED':
            reg=registrations[p['observation_id']];assert reg['key']==k and ctx['candidate']=='keep' and len(tasks[k])==1 and p['trace']==tasks[k][0]['trace'] and p['episode']==details[k]['episode'] and p['source_epoch']==p['main_epoch']==0 and p['observation_id'] not in issued;issued[p['observation_id']]=p
        elif tag=='PRIVATE_COMPLETE':
            assert p['state']==last[k] and p['n']==len(tasks[k])==(2 if arm=='Validated' else 1) and [number(v) for v in p['returns']]==[return_value(x) for x in tasks[k]];trialvals[case,arm,ctx['candidate']]=[number(v) for v in p['returns']]
        elif tag=='ACTUAL_PAIRED_VALUE':
            actual={n:trialvals[case,arm,n] for n in ('keep','controller-delete')};values={n:sum(v)/2 for n,v in actual.items()};q=plain(p['model'])
            assert arm=='Validated' and q['horizon']==2 and q['samples']==actual and q['values']==values and plain(p['observed'])==actual
            chosen=min(('keep','controller-delete'),key=lambda n:(-values[n],0 if n=='keep' else 1));assert p['choice']==chosen;paired[case]={'values':values,'delta':values['controller-delete']-values['keep'],'choice':chosen}
        elif tag=='SELECTED_FEEDBACK':
            prop=task['candidate'];x=feat(task['evidence'],task['ordinary']['current'])
            if arm=='NoWrite':wanted={'action':'keep','edits':[]}
            elif arm=='DirectSite':wanted=prop if any(z['address']==prop['edits'][0]['address'] for z in task['ordinary']['current']['X']) else {'action':'keep','edits':[]}
            elif arm=='FrozenLearned':wanted=preds[case]['proposal']
            else:wanted=prop if paired[case]['choice']=='controller-delete' else {'action':'keep','edits':[]}
            assert p['proposal']==wanted and p['features']==x and p['frozen_digest']==modelseal;task['proposal']=wanted
        elif tag=='DIAGNOSTIC_KEEP':assert task['epoch']>0 and p['used'] is True
        elif tag=='DIAGNOSE_RETURN':assert p['proposal']==task.get('proposal',{'action':'keep','edits':[]})
        elif tag=='DIAGNOSTIC_TX_BEGIN':assert p['before']==task['ordinary'] and p['edits']==task['proposal']['edits']
        elif tag=='DIAGNOSTIC_TX_END':
            expected=deepcopy(task['ordinary']);site=task['proposal']['edits'][0]['address'];expected['current']['X']=[x for x in expected['current']['X'] if x['address']!=site];expected['ordinary_PX_anchor']={f:expected['current'][f] for f in ('P','X')};assert p['after']==expected;task['after']=p['after'];task['tx']=task['writes']=1;feedbackTX+=1
        elif tag=='OBSERVATION_MECHANISM_REJECTED':
            obs=p['observation'];oid=obs['observation_id'];reg=registrations[oid];diff=changes(reg['payload']['source_before']['immediate'],last[k]['current'],obs)
            assert issued[oid]==obs and diff and p['before']==p['after']==last[k] and oid not in consumed and p['receipt']=={'applied':False,'reason':'learner_mechanism_changed_on_observed_path','observation_id':oid,'mechanism_changes':diff};consumed.add(oid);rejections+=1
        elif tag=='EXTERNAL_OBSERVATION_BEGIN':
            obs=p['observation'];oid=obs['observation_id'];reg=registrations[oid];assert task is None and external is None and issued[oid]==obs and oid not in consumed and reg['parent']==k and p['before']==last[k]
            assert p['before']['learning_values']==reg['payload']['consumer']['learning_values'] and changes(reg['payload']['source_before']['immediate'],p['before']['current'],obs)==[];consumed.add(oid);external=p
        elif tag=='EXTERNAL_OBSERVATION_END':
            obs=external['observation'];assert p['observation_id']==obs['observation_id'];extpolicy+=update(external['before'],{'trace':obs['trace'],'_episode':obs['episode']},p,rows,True);ext+=1;last[k]=p['after'];external=None
        elif tag=='TRANSFER_RESULT':
            oid=p['observation_id'];obs=issued[oid];reg=registrations[oid];diff=changes(reg['payload']['source_before']['immediate'],p['before']['current'],obs);accepted=not bool(diff)
            assert oid in consumed and p['after']==last[k] and p['native_delta']=={'rollout':0,'step':0,'transaction':2 if accepted else 0}
            assert p['receipt']=={'applied':accepted,'reason':'same_learner_mechanism_on_observed_path' if accepted else 'learner_mechanism_changed_on_observed_path','observation_id':oid,'mechanism_changes':diff};transfers.append({'case':case,'arm':arm,'applied':accepted})
        elif tag=='POST_MAIN_STATE':assert task is None and p['epoch']==len(tasks[k])-1 and p['state']==last[k];post[k].append(p['state'])
        elif tag=='STREAM_ARM':
            ts=tasks[k];values=[return_value(x) for x in ts];assert len(ts)==len(post[k])==p['main_tasks']==6 and p['final_state']==last[k]
            assert [number(v) for v in p['returns']]==values and p['outcomes']==[x['terminal'] for x in ts] and p['successes']==sum(x['terminal']=='SUCCESS' for x in ts) and number(p['mean_return']).hex()==(sum(values)/6).hex();summaries.append(p)
        elif tag=='MODEL_STILL_FROZEN':assert p['digest']==modelseal and p['new_value_labels_used_for_training']==0
        elif tag=='RESULT':assert p['complete'] and p['streams']==summaries;result=p
        elif tag=='FINAL':assert p['complete'] and p['profile_restored'];final=p
        else:raise AssertionError('unexpected tag '+tag)
    assert task is None and not stack and external is None and set(registrations)==set(issued)==consumed and len(consumed)==12 and len(summaries)==12
    assert ordinary==94 and ext==11 and rejections==1 and tags['PREP_SEED']==1 and sourceTX==2
    assert final['counts']==result['counts']=={'rollout':ordinary,'step':steps,'transaction':1+sourceTX+ordinary+policyTX+ext+extpolicy+feedbackTX+privateTX}
    comparisons=[]
    for case in c['cases']:
        ka=('stream',case,'FrozenLearned',None);kb=('stream',case,'Validated',None)
        comparisons.append({'case':case,'predicted_delta':preds[case]['predicted_delta'],'actual_current_paired_delta':paired[case]['delta'],
         'feature_pattern_seen_in_training':preds[case]['pattern_seen'],'decision_agrees':(preds[case]['proposal']['action']=='apply')==(paired[case]['choice']=='controller-delete'),
         'all6_main_raw_identical':[x['trace'] for x in tasks[ka]]==[x['trace'] for x in tasks[kb]],
         'all6_post_R_L_I_identical':all(all(x[f]==y[f] for f in ('current','learning_values','immediate')) for x,y in zip(post[ka],post[kb]))})
    compact=[{f:([number(v) for v in x[f]] if f=='returns' else number(x[f]) if f=='mean_return' else x[f]) for f in ('case','arm','successes','returns','outcomes','mean_return','external_updates')} for x in summaries]
    output={'schema':'V148_STDLIB_LEARNED_RELATIVE_TRANSFER_REVIEW','complete':True,'native_counts':final['counts'],'records':len(rs),'input_pins':len(claim['input_binding_before']),
      'training_examples':training,'frozen_tree':tree,'frozen_digest':modelseal,'train_context':c['training_context'],'test_context':c['test_context'],'new_test_labels_used_to_fit_frozen_model':0,
      'summaries':compact,'predictions':preds,'actual_paired':paired,'matched_main_comparisons':comparisons,'observation_transfers':transfers,
      'native_ordinary_updates':ordinary,'ordinary_policy_TX':policyTX,'external_ordinary_updates':ext,'external_policy_TX':extpolicy,'source_seed_TX':1,'case_source_TX':sourceTX,
      'private_candidate_X_TX':privateTX,'main_feedback_X_TX':feedbackTX,'actual_explore_events':explorations,'success_diagnosis':0,'guard_rejections':rejections,
      'old_native_checker_bank_reruns':0,'new_keys_RNG_DP_calibration_collection':0,'formal_B1_or_science_qualification':False}
    save(HERE/'stored_audit_result.json',output);save(out/'exit.json',{'complete':True,'completed_at_utc':datetime.now(timezone.utc).isoformat(),'result':meta(HERE/'stored_audit_result.json')})
    print(json.dumps({'complete':True,'native_counts':final['counts'],'records':len(rs),'summaries':compact,'comparisons':comparisons,'frozen_tree':tree},sort_keys=True))

if __name__=='__main__':main()
