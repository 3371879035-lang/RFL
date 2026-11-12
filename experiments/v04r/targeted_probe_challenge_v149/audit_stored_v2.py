"""New stdlib review: historical-state data, literal probes, all raw actions, TD, issued observation flow and costs."""
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
    out=HERE/'evidence_audit_v2';out.mkdir(exist_ok=False)
    def save(p,d):
        with p.open('x',encoding='utf-8',newline='\n') as f:json.dump(d,f,ensure_ascii=True,indent=2);f.write('\n')
    save(out/'claim.json',{'source':meta(Path(__file__)),'native':meta(HERE/'evidence/exit.json'),'automatic_retry':False,'started_at_utc':datetime.now(timezone.utc).isoformat()})
    c=load(HERE/'contract.json');claim=load(HERE/'evidence/claim.json');ex=load(HERE/'evidence/exit.json')
    assert ex['child_exit_code']==0 and ex['input_bytes_unchanged'] and claim['input_binding_before']==ex['input_binding_after']
    for path,pin in claim['input_binding_before'].items():assert meta(ROOT/path)==pin,path
    assert meta(HERE/'evidence/raw.jsonl')==ex['raw']
    for spec in (c['frozen_model'],c['model_code'],*tuple(c['ordinary_checkpoint'][f] for f in ('raw','exit','review'))):
        assert meta(ROOT/spec['path'])=={k:spec[k] for k in ('bytes','sha256')}
    frozen=load(ROOT/c['frozen_model']['path']);training=frozen['points'];verify_cart(frozen['tree'],training)
    oldrs=[json.loads(s) for s in (ROOT/c['ordinary_checkpoint']['raw']['path']).read_text(encoding='ascii').splitlines()]
    oldprep=[r for r in oldrs if r['tag']=='PREPARATION_COMPLETE'];assert len(oldprep)==1;prep=oldprep[0]['payload']['state']
    assert prep['completed_episodes']==1 and prep['external_updates']==0
    rows={}
    for line in (ROOT/c['reference']['path']).read_text(encoding='utf-8').splitlines():
        if line.startswith('DECISION_CONTEXT='):
            q=json.loads(line.split('=',1)[1]);rows[tuple(q['context'])]={a:float.fromhex(v) for a,v in q['q_row_hex']}
    rs=[json.loads(s) for s in (HERE/'evidence/raw.jsonl').read_text(encoding='ascii').splitlines()];assert [r['seq'] for r in rs]==list(range(len(rs)))
    tags=Counter();last={};tasks=defaultdict(list);post=defaultdict(list);details={};task=None;stack=[];sources={};registrations={};issued={};consumed=set();external=None;summaries=[];preds={};paired={};trialvals={}
    steps=0;ordinary=0;policyTX=0;ext=0;extpolicy=0;feedbackTX=0;privateTX=0;sourceTX=0;rejections=0;explorations=0;tree=None;modelseal=None;transfers=[];probed={};reused={};private_initial={};diagnostics={}
    for r in rs:
        tag,p,ctx=r['tag'],r['payload'],r['context'];tags[tag]+=1;k=key(ctx);case=ctx.get('case');arm=ctx.get('arm');ak=(case,arm)
        if tag=='REFERENCE':assert p['digest']==c['reference']['q_digest'] and p['rows']==len(rows)
        elif tag=='REUSED_FROZEN_MODEL':
            assert plain(p['model'])==frozen and p['new_fit_calls']==0
            tree=frozen['tree'];modelseal=frozen['wire_digest'];assert digest(p['model']['tree'])==modelseal
        elif tag=='RECORDED_ORDINARY_MATERIALIZED':
            assert tree is not None and p['source_seq']==oldprep[0]['seq'] and p['source_raw_sha256']==c['ordinary_checkpoint']['raw']['sha256']
            assert p['recorded_payload']==prep and all(p[f]==prep[f] for f in ('immediate','current','learning_values'))
            assert p['native_delta']=={'rollout':0,'step':0,'transaction':3} and p['restored_issued_identities']==0
        elif tag=='TASK_BEGIN':
            if ctx['phase']=='private':assert task is not None and task['key'][0]=='stream';stack.append(task)
            else:assert task is None
            e=len(tasks[k]);assert p['epoch']==e and p['before']['attempted_epochs']==list(range(e+1))
            assert all(p['before'][f]==last[k][f] for f in p['before'] if f!='attempted_epochs')
            coins=[(1<<64)-1]*12;rejection_coordinates=[[0]]*12
            if case=='delayed_damage' and e==(0 if ctx['phase']=='private' else 1):coins[0]=0
            if ctx.get('candidate') in ('probe-keep','probe-delete'):
                cmd=tasks[('stream',case,arm,None)][0]['trace']['steps'][0]['a_cmd'] if tasks[('stream',case,arm,None)] else task['raw']['trace']['steps'][0]['a_cmd']
                coins[0]=0;rejection_coordinates[0]=[[3,4].index(cmd)]
            assert p['episode']=={'epoch':e,'kappa':1,'proposal':1,'tape':{'phase':0,'error_flag':0,'cause_rank':12},'coins':coins,'rejections':rejection_coordinates}
            mask={'decision':None,'controller':None,'plant':{'t':0,'realized':3} if case=='shadowed' else None,
                  'trap':{'cell':[2,1],'t':3} if case=='delayed_damage' else {'cell':[1,2],'t':0}}
            assert p['environment_mask_audit_only']==mask
            task={'key':k,'epoch':e,'before':p['before'],'episode':p['episode'],'mask':mask,'diag':0,'tx':0,'writes':0}
        elif tag=='TASK_RAW':
            tr=p['trace'];assert task is not None and task['key']==k and tr['mask']==task['mask'] and tr['option_in_force']==1
            at=(0,2,0,1,0);z,m=1,0;cur=stores(task['before']['current']);num=stores(task['before']['learning_values']);calls=[];assert len(p['draws'])==len(tr['steps'])
            for i,(draw,x) in enumerate(zip(p['draws'],tr['steps'])):
                q=at+(z,m);vs={a:num['Q'].get(q+(a,),v) for a,v in rows[q].items()};greedy=cur['D'].get(q,min(a for a,v in vs.items() if v==max(vs.values())))
                coin=task['episode']['coins'][i];explore=coin==0;chi=task['episode']['rejections'][i][0];cmd=sorted(rows[q])[chi%len(rows[q])] if explore else greedy;u=cur['X'].get(at+(cmd,),cmd);real=3 if case=='shadowed' and at[2]==0 else u;calls.append([i,0,0,coin])
                if explore:calls.append([i,1,0,chi]);explorations+=1
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
        elif tag=='SOURCE_CASE':
            assert p['before']==prep['current'] and p['values']==prep['learning_values'];expected=stores(prep['current'])
            if case=='delayed_damage':expected['D'][(0,2,0,1,0,1,0)]=3;expected['X'][(0,2,0,1,0,3)]=4;assert len(p['edits'])==2
            else:expected['X'][(0,2,0,1,0,4)]=3;assert len(p['edits'])==1
            sourceTX+=1;assert maps_equal(stores(p['state']),expected);sources[case]=p['state']
        elif tag=='MAIN_INITIALIZED':
            q=p['state'];assert q['immediate']==q['current']==sources[case] and q['learning_values']==prep['learning_values'] and q['completed_episodes']==q['external_updates']==0 and q['attempted_epochs']==[] and q['experience_condition_revision']=='v147-consulted-own-PX-only';last[k]=q
        elif tag=='DIAGNOSE_BEGIN':
            assert ctx['phase']=='stream' and task['raw']['trace']['outcome']!='SUCCESS' and p['evidence']==evidence(task['raw']['trace']) and p['state_before']==task['ordinary'];task['diag']+=1;task['evidence']=p['evidence']
        elif tag=='FROZEN_PREDICTION':
            x=feat(task['evidence'],task['ordinary']['current']);y=predict(tree,x);prop=proposal(task['evidence']) if y>0 else {'action':'keep','edits':[]}
            assert arm=='FrozenLearned' and p['features']==x and number(p['predicted_delta']).hex()==y.hex() and p['proposal']==prop and p['frozen_digest']==modelseal;preds[case]={'features':x,'predicted_delta':y,'proposal':prop,'pattern_seen':x in [v['x'] for v in training]}
        elif tag=='DIAGNOSTIC_INPUT':
            assert task['epoch']==0 and p['evidence']==task['evidence'] and p['post_TD']==task['ordinary'] and p['features']==feat(task['evidence'],task['ordinary']['current']) and p['candidate']==proposal(task['evidence'])
            assert p['trial_horizon']==(2 if arm=='Validated' else 1);task['candidate']=p['candidate'];diagnostics[ak]=p
        elif tag=='NATIVE_OBSERVATION_REGISTERED':
            assert task is not None and task['key'][0]=='stream' and p['consumer']==task['ordinary'] and p['source_before']['completed_episodes']==0 and all(p['source_before'][f]==p['consumer'][f] for f in ('current','learning_values'))
            registrations[p['observation_id']]={'payload':p,'key':k,'parent':task['key']}
        elif tag=='PRIVATE_EDIT':
            assert (arm,ctx['candidate']) in (('Validated','controller-delete'),('TargetedProbe','probe-delete')) and p['before']==task['ordinary']['current'] and p['edits']==task['candidate']['edits']
            expected=deepcopy(p['before']);expected['X']=[x for x in expected['X'] if x['address']!=p['edits'][0]['address']];assert p['after']==expected;privateTX+=1
        elif tag=='PRIVATE_START':
            assert p['parent']==task['ordinary'];expected=deepcopy(task['ordinary']['current'])
            if ctx['candidate'] in ('controller-delete','probe-delete'):expected['X']=[x for x in expected['X'] if x['address']!=task['candidate']['edits'][0]['address']]
            assert p['state']['immediate']==p['state']['current']==expected and p['state']['learning_values']==task['ordinary']['learning_values'] and p['n']==(2 if arm=='Validated' else 1);last[k]=p['state'];private_initial[k]=p['state']
        elif tag=='NATIVE_OBSERVATION_ISSUED':
            reg=registrations[p['observation_id']];assert reg['key']==k and ctx['candidate']=='keep' and len(tasks[k])==1 and p['trace']==tasks[k][0]['trace'] and p['episode']==details[k]['episode'] and p['source_epoch']==p['main_epoch']==0 and p['observation_id'] not in issued;issued[p['observation_id']]=p
        elif tag=='PRIVATE_COMPLETE':
            assert p['state']==last[k] and p['n']==len(tasks[k])==(2 if arm=='Validated' else 1) and [number(v) for v in p['returns']]==[return_value(x) for x in tasks[k]];trialvals[case,arm,ctx['candidate']]=[number(v) for v in p['returns']]
        elif tag=='ACTUAL_PAIRED_VALUE':
            actual={n:trialvals[case,arm,n] for n in ('keep','controller-delete')};values={n:sum(v)/2 for n,v in actual.items()};q=plain(p['model'])
            assert arm=='Validated' and q['horizon']==2 and q['samples']==actual and q['values']==values and plain(p['observed'])==actual
            chosen=min(('keep','controller-delete'),key=lambda n:(-values[n],0 if n=='keep' else 1));assert p['choice']==chosen;paired[case]={'values':values,'delta':values['controller-delete']-values['keep'],'choice':chosen}
        elif tag=='LIVE_KEEP_REUSE':
            kk=('private',case,arm,'keep');assert arm=='TargetedProbe' and len(tasks[kk])==1
            expected={'episode_equal':details[kk]['episode']=={'epoch':0,'kappa':1,'proposal':1,'tape':{'phase':0,'error_flag':0,'cause_rank':12},'coins':[0]+[(1<<64)-1]*11,'rejections':[[[3,4].index(task['evidence']['steps'][0]['a_cmd'])]]+[[0]]*11},
                'parameters_equal':True,'same_reference_object':True,'mode_role_equal':True,'same_initial_R_L':all(private_initial[kk][f]==task['ordinary'][f] for f in ('current','learning_values')),'complete_one_task':True}
            assert p['proof']==expected and all(expected.values()) and p['initial']==private_initial[kk] and p['episode']==details[kk]['episode']
            assert p['actual_trace']==tasks[kk][0]['trace'] and number(p['return']).hex()==return_value(tasks[kk][0]).hex() and p['new_native_calls']==p['new_samples']==0
            reused[case]=return_value(tasks[kk][0])
        elif tag=='LIVE_KEEP_NOT_REUSABLE':
            kk=('private',case,arm,'keep');assert not all(p['proof'].values()) and p['existing_episode']==details[kk]['episode']
            command=task['evidence']['steps'][0]['a_cmd'];wanted={'epoch':0,'kappa':1,'proposal':1,'tape':{'phase':0,'error_flag':0,'cause_rank':12},'coins':[0]+[(1<<64)-1]*11,'rejections':[[[3,4].index(command)]]+[[0]]*11}
            assert p['desired_episode']==wanted and p['proof']['episode_equal']==(wanted==details[kk]['episode'])
        elif tag=='TARGETED_PROBE_VALUE':
            keep=reused[case] if case in reused else trialvals[case,arm,'probe-keep'][0];delete=trialvals[case,arm,'probe-delete'][0]
            assert p['first_command']==task['evidence']['steps'][0]['a_cmd'] and number(p['keep_return']).hex()==keep.hex() and number(p['delete_return']).hex()==delete.hex()
            assert number(p['delta']).hex()==(delete-keep).hex();wanted='controller-delete' if delete>keep else 'keep';assert p['choice']==wanted
            probed[case]={'keep_return':keep,'delete_return':delete,'delta':delete-keep,'choice':wanted,'live_keep_reused':case in reused}
        elif tag=='SELECTED_FEEDBACK':
            prop=task['candidate'];x=feat(task['evidence'],task['ordinary']['current'])
            if arm=='NoWrite':wanted={'action':'keep','edits':[]}
            elif arm=='DirectSite':wanted=prop if any(z['address']==prop['edits'][0]['address'] for z in task['ordinary']['current']['X']) else {'action':'keep','edits':[]}
            elif arm=='FrozenLearned':wanted=preds[case]['proposal']
            else:wanted=prop if (probed[case] if arm=='TargetedProbe' else paired[case])['choice']=='controller-delete' else {'action':'keep','edits':[]}
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
    assert task is None and not stack and external is None and set(registrations)==set(issued)==consumed and len(consumed)==len(c['cases'])*len(c['arms']) and len(summaries)==len(consumed)
    assert sourceTX==2 and sum(len(tasks[('stream',case,arm,None)]) for case in c['cases'] for arm in c['arms'])==60
    assert ordinary==sum(len(ts) for ts in tasks.values()) and ext+rejections==len(consumed)
    assert final['counts']==result['counts']=={'rollout':ordinary,'step':steps,'transaction':3+sourceTX+ordinary+policyTX+ext+extpolicy+feedbackTX+privateTX}
    comparisons=[]
    for case in c['cases']:
        ka=('stream',case,'FrozenLearned',None);kb=('stream',case,'Validated',None)
        comparisons.append({'case':case,'predicted_delta':preds[case]['predicted_delta'],'actual_current_paired_delta':paired[case]['delta'],
         'feature_pattern_seen_in_training':preds[case]['pattern_seen'],'decision_agrees':(preds[case]['proposal']['action']=='apply')==(paired[case]['choice']=='controller-delete'),
         'all6_main_raw_identical':[x['trace'] for x in tasks[ka]]==[x['trace'] for x in tasks[kb]],
         'all6_post_R_L_I_identical':all(all(x[f]==y[f] for f in ('current','learning_values','immediate')) for x,y in zip(post[ka],post[kb]))})
    targeted_comparisons=[];costs=[]
    for case in c['cases']:
        ka=('stream',case,'TargetedProbe',None);kb=('stream',case,'Validated',None)
        targeted_comparisons.append({'case':case,'decision_agrees':probed[case]['choice']==paired[case]['choice'],
            'all6_main_raw_identical':[x['trace'] for x in tasks[ka]]==[x['trace'] for x in tasks[kb]],
            'all6_post_R_L_I_identical':all(all(x[f]==y[f] for f in ('current','learning_values','immediate')) for x,y in zip(post[ka],post[kb]))})
        for arm in c['arms']:
            ts=[t for k,v in tasks.items() if k[1:3]==(case,arm) for t in v];trs=[x for x in transfers if (x['case'],x['arm'])==(case,arm)]
            tx=2*len(ts)+2*sum(x['applied'] for x in trs)+sum(t['counters']['diagnostic_transactions'] for t in ts)+sum(1 for r in rs if r['tag']=='PRIVATE_EDIT' and r['context'].get('case')==case and r['context'].get('arm')==arm)
            costs.append({'case':case,'arm':arm,'rollout':len(ts),'step':sum(len(t['trace']['steps']) for t in ts),'transaction':tx,'shared_checkpoint_source_TX_excluded':5})
    # Observation alias is checked against actual old data, not labels: remove only audit mask.
    def without_mask(trace):v=deepcopy(trace);v.pop('mask');return v
    old_first=next(r['payload'] for r in oldrs if r['tag']=='DIAGNOSTIC_INPUT' and r['context'].get('case')=='broken' and r['context'].get('arm')=='FrozenLearned')
    new_first=diagnostics['shadowed','FrozenLearned'];old_raw=next(r['payload']['trace'] for r in oldrs if r['tag']=='TASK_RAW' and r['context']=={'phase':'stream','case':'broken','arm':'FrozenLearned'})
    alias={'features_identical':old_first['features']==new_first['features'],'visible_evidence_identical':old_first['evidence']==new_first['evidence'],
        'own_full_post_TD_identical':all(old_first['post_TD'][f]==new_first['post_TD'][f] for f in ('immediate','current','learning_values')),
        'task_trace_except_auditmask_identical':without_mask(old_raw)==without_mask(tasks[('stream','shadowed','FrozenLearned',None)][0]['trace'])}
    compact=[{f:([number(v) for v in x[f]] if f=='returns' else number(x[f]) if f=='mean_return' else x[f]) for f in ('case','arm','successes','returns','outcomes','mean_return','external_updates')} for x in summaries]
    output={'schema':'V149_STDLIB_TARGETED_PROBE_CHALLENGE_REVIEW','complete':True,'native_counts':final['counts'],'records':len(rs),'input_pins':len(claim['input_binding_before']),
      'frozen_tree':tree,'frozen_digest':modelseal,'new_test_labels_used_to_fit_frozen_model':0,'summaries':compact,'predictions':preds,'actual_paired':paired,
      'targeted_probes':probed,'frozen_vs_validated':comparisons,'targeted_vs_validated':targeted_comparisons,'online_costs':costs,'old_new_observation_alias':alias,
      'observation_transfers':transfers,'native_ordinary_updates':ordinary,'ordinary_policy_TX':policyTX,'external_ordinary_updates':ext,'external_policy_TX':extpolicy,
      'checkpoint_TX':3,'case_source_TX':sourceTX,'private_candidate_X_TX':privateTX,'main_feedback_X_TX':feedbackTX,'actual_explore_events':explorations,
      'success_diagnosis':0,'guard_rejections':rejections,'live_keep_reuses':len(reused),'old_native_checker_bank_reruns':0,'new_keys_RNG_DP_calibration_collection':0,
      'formal_B1_or_science_qualification':False}
    save(HERE/'stored_audit_result_v2.json',output);save(out/'exit.json',{'complete':True,'completed_at_utc':datetime.now(timezone.utc).isoformat(),'result':meta(HERE/'stored_audit_result_v2.json')})
    print(json.dumps({'complete':True,'native_counts':final['counts'],'records':len(rs),'summaries':compact,'predictions':preds,'paired':paired,'probes':probed,'targeted_comparisons':targeted_comparisons,'alias':alias},sort_keys=True))

if __name__=='__main__':main()
