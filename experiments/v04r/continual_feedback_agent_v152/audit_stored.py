"""New stdlib review of persistent continual agent; no oldchecker/RFL execution."""
from pathlib import Path
from collections import Counter,defaultdict
from copy import deepcopy
from datetime import datetime,timezone
import hashlib,json,ast
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

def key(ctx):return ctx.get('phase'),ctx.get('arm'),ctx.get('main_epoch') if ctx.get('phase')=='private' else None,ctx.get('candidate')

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


def prefix_from(ev,rows):
    target=next(i for i,s in enumerate(ev['steps']) if s['a_cmd']!=s['a_realized']);out=[]
    for s in ev['steps'][:target+1]:
        st={k:s[k] for k in ('x','y','t','kappa','phi')};ctrl={k:s[k] for k in ('z','m')};q=state(st)+(ctrl['z'],ctrl['m'])
        out.append({'state':st,'control':ctrl,'command':s['a_cmd'],'realized':s['a_realized'],'admissible_rank':sorted(rows[q]).index(s['a_cmd'])})
    return {'target_index':target,'rows':out}


def reach(prefix,tr):
    s0=prefix['rows'][0]['state'];at={'x':0,'y':2,'t':0,'kappa':s0['kappa'],'phi':s0['phi']};ctrl={'z':tr['option_in_force'],'m':0}
    for i,wanted in enumerate(prefix['rows']):
        if i>=len(tr['steps']):return {'reached':False,'reason':'task_ended_before_target','checked_steps':i}
        s=tr['steps'][i]
        if (at,ctrl,s['a_cmd'])!=(wanted['state'],wanted['control'],wanted['command']):
            return {'reached':False,'reason':'observed_state_control_or_command_prefix_differs','checked_steps':i}
        if i<prefix['target_index'] and s['a_realized']!=wanted['realized']:
            return {'reached':False,'reason':'preceding_observed_realization_differs','checked_steps':i}
        at=s['state'];ctrl=s['control']
    return {'reached':True,'reason':'actual_target_consulted_with_matching_observed_prefix','checked_steps':len(prefix['rows'])}


def main():
    out=HERE/'evidence_audit';out.mkdir(exist_ok=False)
    def save(p,d):
        with p.open('x',encoding='utf-8',newline='\n') as f:json.dump(d,f,ensure_ascii=True,indent=2);f.write('\n')
    save(out/'claim.json',{'source':meta(Path(__file__)),'native':meta(HERE/'evidence/exit.json'),'automatic_retry':False,'started_at_utc':datetime.now(timezone.utc).isoformat()})
    c=load(HERE/'contract.json');claim=load(HERE/'evidence/claim.json');ex=load(HERE/'evidence/exit.json')
    assert ex['child_exit_code']==0 and ex['input_bytes_unchanged'] and claim['input_binding_before']==ex['input_binding_after']
    for path,pin in claim['input_binding_before'].items():assert meta(ROOT/path)==pin,path
    assert meta(HERE/'evidence/raw.jsonl')==ex['raw']
    for f in ('raw','exit','review'):
        s=c['ordinary_checkpoint'][f];assert meta(ROOT/s['path'])=={k:s[k] for k in ('bytes','sha256')}
    oldrs=[json.loads(s) for s in (ROOT/c['ordinary_checkpoint']['raw']['path']).read_text(encoding='ascii').splitlines()]
    oldprep=[r for r in oldrs if r['tag']=='PREPARATION_COMPLETE'];assert len(oldprep)==1;prep=oldprep[0]['payload']['state']
    schedule=[s for s in c['schedule'] for _ in range(s['count'])];assert len(schedule)==32
    rows={}
    for line in (ROOT/c['reference']['path']).read_text(encoding='utf-8').splitlines():
        if line.startswith('DECISION_CONTEXT='):
            p=json.loads(line.split('=',1)[1]);rows[tuple(p['context'])]={a:float.fromhex(v) for a,v in p['q_row_hex']}
    rs=[json.loads(s) for s in (HERE/'evidence/raw.jsonl').read_text(encoding='ascii').splitlines()];assert [r['seq'] for r in rs]==list(range(len(rs)))
    tasks=defaultdict(list);post=defaultdict(list);last={};details={};registrations={};source_ids={};issued={};consumed=set();query={};accounts={};ordinals=Counter();tags=Counter();summaries=[];diagnoses=[];accepts=[];rejects=[]
    task=None;stack=[];batch=None;external=None;steps=ordinary=policyTX=ext=extpolicy=feedbackTX=privateTX=rejections=explorations=0
    def account(arm):
        q=sum(a==arm for a,e in query);return {'feedback_queries':q,'trial_tasks_used':2*q,'trial_task_budget':0 if arm=='TaskTD' else c['trial_task_budget_each_feedback_arm'],'feedback_enabled':arm!='TaskTD','learn_from_trials':arm=='PrefixRepairLearn'}
    for r in rs:
        tag,p,ctx=r['tag'],r['payload'],r['context'];tags[tag]+=1;k=key(ctx);arm=ctx.get('arm');epoch=ctx.get('main_epoch');name=ctx.get('candidate')
        if tag=='REFERENCE':assert p['digest']==c['reference']['q_digest'] and p['rows']==len(rows)
        elif tag=='RECORDED_ORDINARY_MATERIALIZED':
            assert p['source_seq']==oldprep[0]['seq'] and p['source_raw_sha256']==c['ordinary_checkpoint']['raw']['sha256'] and p['recorded_payload']==prep
            assert all(p[f]==prep[f] for f in ('immediate','current','learning_values')) and p['native_delta']=={'rollout':0,'step':0,'transaction':3} and p['restored_issued_identities']==0
        elif tag=='SHARED_SOURCE':
            assert p['before']==prep['current'] and p['values']==prep['learning_values'];expected=stores(prep['current'])
            expected['X'].update({(0,2,0,1,0,4):3,(1,2,2,1,2,0):3,(0,2,0,0,3,3):4,(3,4,10,0,5,4):0})
            expected['D'].update({(0,2,0,1,2,1,0):4,(0,2,0,0,3,1,0):3,(1,2,2,0,3,1,0):3,(0,2,0,0,4,1,0):3})
            assert len(p['edits'])==8 and maps_equal(stores(p['state']),expected);source=p['state']
        elif tag=='MAIN_INITIALIZED':
            q=p['state'];assert q['immediate']==q['current']==source and q['learning_values']==prep['learning_values'] and q['completed_episodes']==q['external_updates']==0 and q['attempted_epochs']==[] and q['experience_revision']=='v151-intervention-origin-batch'
            assert p['diagnostic_account']==account(arm);last[k]=q
        elif tag=='RUNNER_CONTEXT':
            s=schedule[epoch];assert p=={'epoch':epoch,'stage_audit_only':s['label'],'kappa':s['kappa'],'phi':s['phi']} and epoch==len(tasks[k])
        elif tag=='OWNED_BRANCH_EDIT':
            assert name=='controller-delete' and p['before']==task['ordinary']['current'] and p['edits']==task['candidate']['edits']
            expected=deepcopy(p['before']);expected['X']=[x for x in expected['X'] if x['address']!=p['edits'][0]['address']];assert p['after']==expected;privateTX+=1
        elif tag=='OWNED_BRANCH_REGISTERED':
            assert p['consumer']==task['ordinary'] and p['proposal']==({'action':'keep','edits':[]} if name=='keep' else task['candidate'])
            reg=p['registration'];ordinals[arm]+=1;expected=deepcopy(task['ordinary']['current']);s=schedule[epoch]
            if name=='controller-delete':expected['X']=[x for x in expected['X'] if x['address']!=task['candidate']['edits'][0]['address']]
            assert reg['ordinal']==ordinals[arm] and reg['main_epoch']==epoch and reg['origin_L']==task['ordinary']['learning_values'] and reg['kappa']==s['kappa'] and reg['phi']==s['phi'] and reg['source_I']==expected
            assert p['source_before']['immediate']==p['source_before']['current']==expected and p['source_before']['learning_values']==reg['origin_L'] and p['source_before']['completed_episodes']==p['source_before']['external_updates']==0
            registrations[reg['id']]={'payload':p,'key':k,'parent':task['key']};source_ids[k]=reg['id']
        elif tag=='PRIVATE_START':
            assert p['parent']==task['ordinary'];expected=deepcopy(task['ordinary']['current'])
            if name=='controller-delete':expected['X']=[x for x in expected['X'] if x['address']!=task['candidate']['edits'][0]['address']]
            assert p['state']['immediate']==p['state']['current']==expected and p['state']['learning_values']==task['ordinary']['learning_values'] and p['n']==1;last[k]=p['state']
        elif tag=='TASK_BEGIN':
            if ctx['phase']=='private':assert task is not None and task['key'][0]=='stream';stack.append(task)
            else:assert task is None
            e=len(tasks[k]);s=schedule[epoch];assert p['epoch']==e and p['before']['attempted_epochs']==list(range(e+1))
            assert all(p['before'][f]==last[k][f] for f in p['before'] if f!='attempted_epochs')
            coins=[(1<<64)-1]*12;chi=[[0]]*12
            if ctx['phase']=='private':
                assert e==0
                for i,x in enumerate(task['prefix']['rows']):coins[i]=0;chi[i]=[x['admissible_rank']]
            else:assert e==epoch
            ep={'epoch':e,'kappa':s['kappa'],'proposal':1,'tape':{'phase':s['phi'],'error_flag':0,'cause_rank':12},'coins':coins,'rejections':chi}
            mask={'decision':None,'controller':None,'plant':None,'trap':s['trap']};assert p['episode']==ep and p['environment_mask_audit_only']==mask
            task={'key':k,'epoch':e,'main_epoch':epoch,'before':p['before'],'episode':ep,'mask':mask,'diag':0,'tx':0,'writes':0}
        elif tag=='TASK_RAW':
            tr=p['trace'];assert task is not None and task['key']==k and tr['mask']==task['mask'] and tr['option_in_force']==1
            ep=task['episode'];kk,phi=ep['kappa'],ep['tape']['phase'];at=(0,2,0,kk,phi);z,m=1,0;cur=stores(task['before']['current']);num=stores(task['before']['learning_values']);calls=[]
            assert len(p['draws'])==len(tr['steps']);open_cells={(0,2),(4,2),(1,1),(2,1),(3,1),(1,2),(2,2),(3,2),(1,3),(3,3),(1,4),(2,4),(3,4)};deltas=((0,-1),(0,1),(-1,0),(1,0),(0,0));trap=task['mask']['trap']
            for i,(draw,x) in enumerate(zip(p['draws'],tr['steps'])):
                q=at+(z,m);vs={a:num['Q'].get(q+(a,),v) for a,v in rows[q].items()};greedy=cur['D'].get(q,min(a for a,v in vs.items() if v==max(vs.values())))
                coin=ep['coins'][i];explore=coin==0;index=ep['rejections'][i][0];cmd=sorted(rows[q])[index%len(rows[q])] if explore else greedy;u=cur['X'].get(at+(cmd,),cmd);real=u;calls.append([i,0,0,coin])
                if explore:calls.append([i,1,0,index]);explorations+=1
                assert draw=={'i':i,'explore':explore,'admissible':sorted(rows[q]),'a_cmd':cmd} and x['a_cmd']==cmd and x['u']==u and x['a_realized']==real
                dx,dy=deltas[real];cell=(at[0]+dx,at[1]+dy);cell=cell if cell in open_cells else at[:2];nt=at[2]+1;period=6 if kk==0 else 3
                outcome='COLLISION' if cell==(2,2) and nt%period==phi%period else 'TRAP' if list(cell)==trap['cell'] and at[2]==trap['t'] else 'SUCCESS' if cell==(4,2) else 'TIMEOUT' if nt>=12 else None
                st={'x':cell[0],'y':cell[1],'t':nt,'kappa':kk,'phi':phi};ctrl={'z':1,'m':1 if m or cell==(2,1) else 0};reward=-.02+(1.0 if outcome=='SUCCESS' else -1.0 if outcome else 0.0)
                assert x['state']==st and x['control']==ctrl and x['terminal']==(outcome is not None) and x['outcome']==outcome and not x['illegal'] and number(x['reward']).hex()==reward.hex()
                at=state(x['state']);z,m=x['control']['z'],x['control']['m']
            assert p['coordinates']==calls and tr['steps'][-1]['terminal'] and tr['outcome']==tr['steps'][-1]['outcome'] and p['return_hex']==return_value({'trace':tr}).hex()
            task['raw']={**p,'_episode':ep};steps+=len(tr['steps'])
        elif tag=='ORDINARY_UPDATE':policyTX+=update(task['before'],task['raw'],p,rows,False);ordinary+=1;task['ordinary']=p['after'];task['after']=p['after']
        elif tag=='DIAGNOSE_BEGIN':
            assert arm!='TaskTD' and ctx['phase']=='stream' and task['raw']['trace']['outcome']!='SUCCESS' and p['evidence']==evidence(task['raw']['trace']) and p['state_before']==task['ordinary'];task['diag']+=1;task['evidence']=p['evidence'];diagnoses.append({'arm':arm,'epoch':epoch,'stage':schedule[epoch]['label'],'terminal':p['terminal']})
        elif tag=='NO_VISIBLE_MISMATCH_KEEP':
            assert proposal(task['evidence']) is None and p['terminal']==task['raw']['trace']['outcome'] and p['main_epoch']==epoch and p['diagnostic_account']==account(arm);task['fast_keep']='no_visible_mismatch'
        elif tag=='TRIAL_BUDGET_KEEP':
            assert p['main_epoch']==epoch and p['diagnostic_account']==account(arm) and p['diagnostic_account']['trial_tasks_used']+2>p['diagnostic_account']['trial_task_budget'];task['fast_keep']='budget'
        elif tag=='DIAGNOSTIC_INPUT':
            assert p['evidence']==task['evidence'] and p['post_TD']==task['ordinary'] and p['candidate']==proposal(task['evidence']) and p['prefix']==prefix_from(task['evidence'],rows)
            task['candidate']=p['candidate'];task['prefix']=p['prefix']
        elif tag=='TASK_COMPLETE':
            assert p['trace']==task['raw']['trace'] and p['before']==task['before'] and p['ordinary_after']==task['ordinary'] and p['after']==task['after'] and p['terminal']==p['trace']['outcome']
            assert p['counters']=={'ordinary_updates':1,'diagnostic_calls':task['diag'],'query_calls':0,'diagnostic_transactions':task['tx'],'diagnostic_edit_addresses':task['writes']}
            if p['terminal']=='SUCCESS':assert task['diag']==task['tx']==task['writes']==0
            assert p['route']['write_spend']==task['writes'] and p['route']['diagnostic_calls']==task['diag'];tasks[k].append(p);details[k]=task;last[k]=p['after'];task=stack.pop() if stack else None
        elif tag=='OWNED_OBSERVATION_ISSUED':
            reg=registrations[p['observation_id']];assert reg['key']==k and len(tasks[k])==1 and p['trace']==tasks[k][0]['trace'] and p['episode']==details[k]['episode'] and p['source_epoch']==0 and p['main_epoch']==epoch and p['observation_id'] not in issued
            assert p['observation_revision']=='v151-native-intervention-origin' and p['issuer_label']==last[k]['source_label'] and p['consumer_label']==reg['payload']['consumer']['source_label'];issued[p['observation_id']]=p
        elif tag=='PRIVATE_COMPLETE':
            assert p['state']==last[k] and p['n']==len(tasks[k])==1 and [number(v) for v in p['returns']]==[return_value(t) for t in tasks[k]] and p['first_task_target_reach']==reach(task['prefix'],tasks[k][0]['trace'])
        elif tag=='PREFIX_DECISION':
            actual={name:[return_value(tasks[('private',arm,epoch,name)][0])] for name in ('keep','controller-delete')};means={name:sum(v) for name,v in actual.items()};rr={name:reach(task['prefix'],tasks[('private',arm,epoch,name)][0]['trace']) for name in actual};proper=all(v['reached'] for v in rr.values())
            wanted=min(actual,key=lambda name:(-means[name],0 if name=='keep' else 1)) if proper else 'keep';delta=means['controller-delete']-means['keep'] if proper else None
            assert plain(p['model'])=={'horizon':1,'samples':actual,'values':means} and plain(p['observed'])==actual and p['choice']==wanted and p['proper_target_comparison']==proper and p['target_reach']==rr
            assert p['target_delta'] is None if delta is None else number(p['target_delta']).hex()==delta.hex()
            query[arm,epoch]={'arm':arm,'epoch':epoch,'stage':schedule[epoch]['label'],'observed':actual,'choice':wanted,'target_delta':delta,'target_index':task['prefix']['target_index']};assert p['diagnostic_account']==account(arm)
        elif tag=='SELECTED_FEEDBACK':
            wanted=task['candidate'] if query[arm,epoch]['choice']=='controller-delete' else {'action':'keep','edits':[]}
            assert p['proposal']==wanted and p['target_index']==task['prefix']['target_index'];task['proposal']=wanted
        elif tag=='DIAGNOSE_RETURN':assert p['proposal']==task.get('proposal',{'action':'keep','edits':[]})
        elif tag=='DIAGNOSTIC_TX_BEGIN':assert p['before']==task['ordinary'] and p['edits']==task['proposal']['edits']
        elif tag=='DIAGNOSTIC_TX_END':
            expected=deepcopy(task['ordinary']);site=task['proposal']['edits'][0]['address'];expected['current']['X']=[x for x in expected['current']['X'] if x['address']!=site];expected['ordinary_PX_anchor']={f:expected['current'][f] for f in ('P','X')};assert p['after']==expected;task['after']=p['after'];task['tx']=task['writes']=1;feedbackTX+=1
        elif tag=='OWNED_BATCH_BEGIN':
            assert arm=='PrefixRepairLearn' and task is None and external is None and batch is None and p['before']==last[k] and p['all_consumed_before_TD'];ids=[source_ids[('private',arm,epoch,n)] for n in ('keep','controller-delete')]
            assert [o['observation_id'] for o in p['observations']]==ids and p['ordinals']==[registrations[i]['payload']['registration']['ordinal'] for i in ids]
            for o in p['observations']:
                oid=o['observation_id'];reg=registrations[oid];assert issued[oid]==o and oid not in consumed and reg['parent']==k and reg['payload']['registration']['origin_L']==p['before']['learning_values']
            consumed.update(ids);batch={'before':p['before'],'ids':ids,'processed':[],'receipts':[]}
        elif tag=='OWNED_OBSERVATION_REJECTED':
            o=p['observation'];oid=o['observation_id'];reg=registrations[oid];diff=changes(reg['payload']['source_before']['immediate'],last[k]['current'],o);wanted={'applied':False,'reason':'current_mechanism_differs_on_observed_path','observation_id':oid,'mechanism_changes':diff}
            assert batch is not None and oid==batch['ids'][len(batch['processed'])] and issued[oid]==o and diff and p['before']==p['after']==last[k] and oid in consumed and p['receipt']==wanted
            batch['processed'].append(oid);batch['receipts'].append(wanted);rejections+=1;rejects.append({'epoch':epoch,'stage':schedule[epoch]['label'],'candidate':reg['key'][3],'terminal':o['trace']['outcome'],'mechanism_changes':diff})
        elif tag=='OWNED_EXTERNAL_BEGIN':
            o=p['observation'];oid=o['observation_id'];reg=registrations[oid];assert task is None and external is None and batch is not None and oid==batch['ids'][len(batch['processed'])] and issued[oid]==o and oid in consumed and p['before']==last[k]
            assert not changes(reg['payload']['source_before']['immediate'],p['before']['current'],o) and p['external_update_index']==last[k]['external_updates'] and p['main_clock_advanced'] is False;external=p
        elif tag=='OWNED_EXTERNAL_END':
            o=external['observation'];oid=o['observation_id'];wanted={'applied':True,'reason':'same_mechanism_on_observed_path','observation_id':oid,'mechanism_changes':[]}
            assert p['observation_id']==oid and p['receipt']==wanted;extpolicy+=update(external['before'],{'trace':o['trace'],'_episode':o['episode']},p,rows,True);ext+=1;last[k]=p['after']
            batch['processed'].append(oid);batch['receipts'].append(wanted);accepts.append({'epoch':epoch,'stage':schedule[epoch]['label'],'candidate':registrations[oid]['key'][3],'terminal':o['trace']['outcome'],'numeric_content_changed':external['before']['learning_values']!=p['after']['learning_values']});external=None
        elif tag=='OWNED_BATCH_END':
            assert batch is not None and batch['processed']==batch['ids'] and p['before']==batch['before'] and p['after']==last[k] and p['receipts']==batch['receipts'];batch=None
        elif tag=='TRIAL_OBSERVATIONS_NOT_LEARNED':
            assert arm=='PrefixRepair' and p['state']==last[k] and p['observation_ids']==[source_ids[('private',arm,epoch,n)] for n in ('keep','controller-delete')] and all(i not in consumed for i in p['observation_ids'])
        elif tag=='POST_OBSERVED_TASK':
            assert task is None and batch is None and p['epoch']==len(tasks[k])-1==epoch and p['state']==last[k] and p['diagnostic_account']==account(arm);post[k].append(p['state'])
        elif tag=='AGENT_FINAL':
            ts=tasks[k];vals=[return_value(t) for t in ts];assert p['main_tasks']==len(ts)==len(post[k])==32 and p['final_state']==last[k] and p['diagnostic_account']==account(arm)
            assert [number(v) for v in p['returns']]==vals and p['outcomes']==[t['terminal'] for t in ts] and p['successes']==sum(t['terminal']=='SUCCESS' for t in ts) and number(p['mean_return']).hex()==(sum(vals)/32).hex() and p['external_updates']==last[k]['external_updates'];summaries.append(p)
        elif tag=='RESULT':assert p['complete'] and p['streams']==summaries;result=p
        elif tag=='FINAL':assert p['complete'] and p['profile_restored'];final=p
        else:raise AssertionError('unexpectedtag '+tag)
    assert task is None and external is None and batch is None and not stack and len(summaries)==3 and set(registrations)==set(issued)
    assert ordinary==sum(len(ts) for ts in tasks.values()) and ext+rejections==len(consumed)
    assert final['counts']==result['counts']=={'rollout':ordinary,'step':steps,'transaction':4+ordinary+policyTX+ext+extpolicy+feedbackTX+privateTX}
    phases=[];costs=[];preservation=[]
    for arm in c['arms']:
        k=('stream',arm,None,None);ts=tasks[k];cursor=0
        for s in c['schedule']:
            part=ts[cursor:cursor+s['count']];vals=[return_value(t) for t in part];phases.append({'arm':arm,'stage':s['label'],'start_epoch':cursor,'tasks':len(part),'successes':sum(t['terminal']=='SUCCESS' for t in part),'returns':vals,'mean_return':sum(vals)/len(vals),'query_epochs':[e for a,e in query if a==arm and cursor<=e<cursor+s['count']]});cursor+=s['count']
        native=[t for key_,v in tasks.items() if key_[1]==arm for t in v];q=sum(a==arm for a,e in query);learn_ext=sum(1 for x in accepts) if arm=='PrefixRepairLearn' else 0
        costs.append({'arm':arm,'main_tasks':32,'private_tasks':2*q,'rollout':len(native),'step':sum(len(t['trace']['steps']) for t in native),'transaction':2*len(native)+q+sum(t['counters']['diagnostic_transactions'] for t in ts)+2*learn_ext,'shared4TX_excluded':True})
        sentinel=(3,4,10,0,5,4);protective=(0,2,0,0,3,3)
        assert all(p['immediate']==source and stores(p['current'])['X'][sentinel]==0 and p['current']['P']==source['P'] for p in post[k])
        assert stores(last[k]['current'])['X'][protective]==4
        preservation.append({'arm':arm,'all32_I_preserved':True,'unread_sentinel_preserved':True,'protective_X_preserved':True,'phase_boundary_resets':0})
        assert account(arm)['trial_tasks_used']==2*q<=account(arm)['trial_task_budget']
    compact=[{f:([number(v) for v in x[f]] if f=='returns' else number(x[f]) if f=='mean_return' else x[f]) for f in ('arm','successes','returns','outcomes','mean_return','external_updates','diagnostic_account')} for x in summaries]
    policy=next(n for n in ast.parse((HERE/'continual_agent.py').read_text()).body if isinstance(n,ast.ClassDef));diag=next(n for n in policy.body if isinstance(n,ast.FunctionDef) and n.name=='_diagnose_visible');assert not ({'mask','case','stage'} & {n.id for n in ast.walk(diag) if isinstance(n,ast.Name)})
    output={'schema':'V152_STDLIB_CONTINUAL_AGENT_REVIEW','complete':True,'native_counts':final['counts'],'records':len(rs),'input_pins':len(claim['input_binding_before']),
        'summaries':compact,'phase_results':phases,'online_costs':costs,'queries':list(query.values()),'diagnoses':diagnoses,'accepted':accepts,'rejected':rejects,'preservation':preservation,
        'native_ordinary_updates':ordinary,'ordinary_policy_TX':policyTX,'external_ordinary_updates':ext,'external_policy_TX':extpolicy,'private_candidate_X_TX':privateTX,'main_feedback_X_TX':feedbackTX,
        'issued_observations':len(issued),'consumed_observations':len(consumed),'unconsumed_observations':len(issued)-len(consumed),'actual_explore_events':explorations,'success_diagnosis':0,
        'no_mismatch_keeps':tags['NO_VISIBLE_MISMATCH_KEEP'],'budget_keeps':tags['TRIAL_BUDGET_KEEP'],'old_native_checker_bank_reruns':0,'new_keys_RNG_DP_calibration_collection':0,'formal_B1_or_science_qualification':False}
    save(HERE/'stored_audit_result.json',output);save(out/'exit.json',{'complete':True,'completed_at_utc':datetime.now(timezone.utc).isoformat(),'result':meta(HERE/'stored_audit_result.json')})
    print(json.dumps({'complete':True,'native_counts':final['counts'],'records':len(rs),'summaries':compact,'phases':phases,'queries':list(query.values()),'costs':costs,'accepted':accepts,'rejected':rejects},sort_keys=True))

if __name__=='__main__':main()
