"""New stdlib review of intervention-origin native observations and ordinary TD batches; no oldchecker/RFL execution."""
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


def prefix_from(ev,rows):
    target=next(i for i,s in enumerate(ev['steps']) if s['a_cmd']!=s['a_realized']);out=[]
    for s in ev['steps'][:target+1]:
        st={k:s[k] for k in ('x','y','t','kappa','phi')};ctrl={k:s[k] for k in ('z','m')};q=state(st)+(ctrl['z'],ctrl['m'])
        out.append({'state':st,'control':ctrl,'command':s['a_cmd'],'realized':s['a_realized'],'admissible_rank':sorted(rows[q]).index(s['a_cmd'])})
    return {'target_index':target,'rows':out}


def reach(prefix,tr):
    at={'x':0,'y':2,'t':0,'kappa':1,'phi':0};ctrl={'z':tr['option_in_force'],'m':0}
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
        spec=c['ordinary_checkpoint'][f];assert meta(ROOT/spec['path'])=={k:spec[k] for k in ('bytes','sha256')}
    oldrs=[json.loads(s) for s in (ROOT/c['ordinary_checkpoint']['raw']['path']).read_text(encoding='ascii').splitlines()]
    oldprep=[r for r in oldrs if r['tag']=='PREPARATION_COMPLETE'];assert len(oldprep)==1;prep=oldprep[0]['payload']['state']
    rows={}
    for line in (ROOT/c['reference']['path']).read_text(encoding='utf-8').splitlines():
        if line.startswith('DECISION_CONTEXT='):
            q=json.loads(line.split('=',1)[1]);rows[tuple(q['context'])]={a:float.fromhex(v) for a,v in q['q_row_hex']}
    rs=[json.loads(s) for s in (HERE/'evidence/raw.jsonl').read_text(encoding='ascii').splitlines()];assert [r['seq'] for r in rs]==list(range(len(rs)))
    tags=Counter();last={};tasks=defaultdict(list);post=defaultdict(list);details={};task=None;stack=[];registrations={};issued={};consumed=set();external=None;summaries=[];trialvals={};trialreach={};diagnostics={};query={};transfers=[]
    steps=ordinary=policyTX=ext=extpolicy=feedbackTX=privateTX=rejections=explorations=0
    sources={};batch=None;accepted=[];rejected=[];duplicates=0;source_registrations={}
    for r in rs:
        tag,p,ctx=r['tag'],r['payload'],r['context'];tags[tag]+=1;k=key(ctx);case=ctx.get('case');arm=ctx.get('arm');ak=(case,arm);name=ctx.get('candidate')
        if tag=='REFERENCE':assert p['digest']==c['reference']['q_digest'] and p['rows']==len(rows)
        elif tag=='RECORDED_ORDINARY_MATERIALIZED':
            assert p['source_seq']==oldprep[0]['seq'] and p['source_raw_sha256']==c['ordinary_checkpoint']['raw']['sha256'] and p['recorded_payload']==prep
            assert all(p[f]==prep[f] for f in ('immediate','current','learning_values')) and p['native_delta']=={'rollout':0,'step':0,'transaction':3} and p['restored_issued_identities']==0
        elif tag=='SOURCE_CASE':
            assert p['before']==prep['current'] and p['values']==prep['learning_values'];expected=stores(prep['current'])
            site=(0,2,0,1,0,4) if case=='first_failure_then_gain' else (1,2,2,1,0,0)
            expected['X'][site]=3;assert maps_equal(stores(p['state']),expected) and len(p['edits'])==1
            assert address(p['edits'][0]['address'],'X')==site and p['edits'][0]['store']=='controller' and p['edits'][0]['value']==3;sources[case]=p['state']
        elif tag=='MAIN_INITIALIZED':
            q=p['state'];assert q['immediate']==q['current']==sources[case] and q['learning_values']==prep['learning_values'] and q['completed_episodes']==q['external_updates']==0 and q['attempted_epochs']==[]
            assert q['experience_revision']=='v151-intervention-origin-batch';last[k]=q
        elif tag=='OWNED_BRANCH_EDIT':
            assert name=='controller-delete' and p['before']==task['ordinary']['current'] and p['edits']==task['candidate']['edits']
            expected=deepcopy(p['before']);expected['X']=[x for x in expected['X'] if x['address']!=p['edits'][0]['address']];assert p['after']==expected;privateTX+=1
        elif tag=='PRIVATE_START':
            assert p['parent']==task['ordinary'];expected=deepcopy(task['ordinary']['current'])
            if name=='controller-delete':expected['X']=[x for x in expected['X'] if x['address']!=task['candidate']['edits'][0]['address']]
            n=2 if case=='first_failure_then_gain' else 1
            assert p['state']['immediate']==p['state']['current']==expected and p['state']['learning_values']==task['ordinary']['learning_values'] and p['n']==n;last[k]=p['state']
        elif tag=='TASK_BEGIN':
            if ctx['phase']=='private':assert task is not None and task['key'][0]=='stream';stack.append(task)
            else:assert task is None
            e=len(tasks[k]);assert p['epoch']==e and p['before']['attempted_epochs']==list(range(e+1))
            assert all(p['before'][f]==last[k][f] for f in p['before'] if f!='attempted_epochs')
            coins=[(1<<64)-1]*12;chi=[[0]]*12
            if ctx['phase']=='stream' and case=='late_repair' and e==1:coins[:3]=[0]*3;chi[:3]=[[1],[0],[0]]
            if ctx['phase']=='private' and case=='late_repair':
                for i,part in enumerate(task['prefix']['rows']):coins[i]=0;chi[i]=[part['admissible_rank']]
            ep={'epoch':e,'kappa':1,'proposal':1,'tape':{'phase':0,'error_flag':0,'cause_rank':12},'coins':coins,'rejections':chi};assert p['episode']==ep
            mask={'decision':None,'controller':None,'plant':None,'trap':{'cell':[1,2],'t':0} if case=='first_failure_then_gain' else None};assert p['environment_mask_audit_only']==mask
            task={'key':k,'epoch':e,'before':p['before'],'episode':ep,'mask':mask,'diag':0,'tx':0,'writes':0}
        elif tag=='TASK_RAW':
            tr=p['trace'];assert task is not None and task['key']==k and tr['mask']==task['mask'] and tr['option_in_force']==1
            at=(0,2,0,1,0);z,m=1,0;cur=stores(task['before']['current']);num=stores(task['before']['learning_values']);calls=[];assert len(p['draws'])==len(tr['steps'])
            open_cells={(0,2),(4,2),(1,1),(2,1),(3,1),(1,2),(2,2),(3,2),(1,3),(3,3),(1,4),(2,4),(3,4)};deltas=((0,-1),(0,1),(-1,0),(1,0),(0,0))
            for i,(draw,x) in enumerate(zip(p['draws'],tr['steps'])):
                q=at+(z,m);vs={a:num['Q'].get(q+(a,),v) for a,v in rows[q].items()};greedy=cur['D'].get(q,min(a for a,v in vs.items() if v==max(vs.values())))
                coin=task['episode']['coins'][i];explore=coin==0;index=task['episode']['rejections'][i][0];cmd=sorted(rows[q])[index%len(rows[q])] if explore else greedy
                u=cur['X'].get(at+(cmd,),cmd);real=u;calls.append([i,0,0,coin])
                if explore:calls.append([i,1,0,index]);explorations+=1
                assert draw=={'i':i,'explore':explore,'admissible':sorted(rows[q]),'a_cmd':cmd} and x['a_cmd']==cmd and x['u']==u and x['a_realized']==real
                dx,dy=deltas[real];cell=(at[0]+dx,at[1]+dy);cell=cell if cell in open_cells else at[:2];nt=at[2]+1
                outcome='COLLISION' if cell==(2,2) and nt%3==0 else 'TRAP' if case=='first_failure_then_gain' and cell==(1,2) and at[2]==0 else 'SUCCESS' if cell==(4,2) else 'TIMEOUT' if nt>=12 else None
                expectedstate={'x':cell[0],'y':cell[1],'t':nt,'kappa':1,'phi':0};ctrl={'z':1,'m':1 if m or cell==(2,1) else 0};reward=-.02+(1.0 if outcome=='SUCCESS' else -1.0 if outcome else 0.0)
                assert x['state']==expectedstate and x['control']==ctrl and x['terminal']==(outcome is not None) and x['outcome']==outcome and not x['illegal'] and number(x['reward']).hex()==reward.hex()
                at=state(x['state']);z,m=x['control']['z'],x['control']['m']
            assert p['coordinates']==calls and tr['steps'][-1]['terminal'] and tr['outcome']==tr['steps'][-1]['outcome'] and p['return_hex']==return_value({'trace':tr}).hex()
            task['raw']={**p,'_episode':task['episode']};steps+=len(tr['steps'])
        elif tag=='ORDINARY_UPDATE':policyTX+=update(task['before'],task['raw'],p,rows,False);ordinary+=1;task['ordinary']=p['after'];task['after']=p['after']
        elif tag=='DIAGNOSE_BEGIN':
            assert ctx['phase']=='stream' and task['raw']['trace']['outcome']!='SUCCESS' and p['evidence']==evidence(task['raw']['trace']) and p['state_before']==task['ordinary'];task['diag']+=1;task['evidence']=p['evidence']
        elif tag=='DIAGNOSTIC_INPUT':
            assert task['epoch']==0 and p['evidence']==task['evidence'] and p['post_TD']==task['ordinary'] and p['candidate']==proposal(task['evidence']) and p['prefix']==prefix_from(task['evidence'],rows)
            task['candidate']=p['candidate'];task['prefix']=p['prefix'];diagnostics[ak]=p
        elif tag=='OWNED_BRANCH_REGISTERED':
            assert p['consumer']==task['ordinary'] and p['proposal']==({'action':'keep','edits':[]} if name=='keep' else task['candidate'])
            reg=p['registration'];ordinal=1 if name=='keep' else 2;expected=deepcopy(task['ordinary']['current'])
            if name=='controller-delete':expected['X']=[x for x in expected['X'] if x['address']!=task['candidate']['edits'][0]['address']]
            assert reg['ordinal']==ordinal and reg['main_epoch']==0 and reg['origin_L']==task['ordinary']['learning_values'] and reg['kappa']==1 and reg['phi']==0 and reg['source_I']==expected
            assert p['source_before']['immediate']==p['source_before']['current']==expected and p['source_before']['learning_values']==reg['origin_L'] and p['source_before']['completed_episodes']==p['source_before']['external_updates']==0
            registrations[reg['id']]={'payload':p,'key':k,'parent':task['key']};source_registrations[k]=reg['id']
        elif tag=='TASK_COMPLETE':
            assert p['trace']==task['raw']['trace'] and p['before']==task['before'] and p['ordinary_after']==task['ordinary'] and p['after']==task['after'] and p['terminal']==p['trace']['outcome']
            assert p['counters']=={'ordinary_updates':1,'diagnostic_calls':task['diag'],'query_calls':0,'diagnostic_transactions':task['tx'],'diagnostic_edit_addresses':task['writes']}
            if p['terminal']=='SUCCESS':assert task['diag']==task['tx']==task['writes']==0
            assert p['route']['write_spend']==task['writes'] and p['route']['diagnostic_calls']==task['diag'];tasks[k].append(p);details[k]=task;last[k]=p['after'];task=stack.pop() if stack else None
        elif tag=='OWNED_OBSERVATION_ISSUED':
            reg=registrations[p['observation_id']];assert reg['key']==k and len(tasks[k])==1 and p['trace']==tasks[k][0]['trace'] and p['episode']==details[k]['episode'] and p['source_epoch']==p['main_epoch']==0 and p['observation_id'] not in issued
            assert p['observation_revision']=='v151-native-intervention-origin' and p['issuer_label']==last[k]['source_label'] and p['consumer_label']==reg['payload']['consumer']['source_label'];issued[p['observation_id']]=p
        elif tag=='PRIVATE_COMPLETE':
            n=2 if case=='first_failure_then_gain' else 1
            assert p['state']==last[k] and p['n']==len(tasks[k])==n and [number(v) for v in p['returns']]==[return_value(x) for x in tasks[k]]
            rr=reach(task['prefix'],tasks[k][0]['trace']);assert p['first_task_target_reach']==rr;trialvals[case,arm,name]=[number(v) for v in p['returns']];trialreach[case,arm,name]=rr
        elif tag=='ACTUAL_QUERY_VALUE':
            actual={name:trialvals[case,arm,name] for name in ('keep','controller-delete')};n=2 if case=='first_failure_then_gain' else 1
            means={name:sum(v)/n for name,v in actual.items()};wanted=min(actual,key=lambda name:(-means[name],0 if name=='keep' else 1))
            assert p['choice']==wanted and p['horizon']==n and plain(p['model'])=={'horizon':n,'samples':actual,'values':means} and plain(p['observed'])==actual
            query[ak]={'observed':actual,'means':means,'query_delta':means['controller-delete']-means['keep'],'choice':wanted,'horizon':n}
        elif tag=='SELECTED_FEEDBACK':
            wanted=task['candidate'] if query[ak]['choice']=='controller-delete' else {'action':'keep','edits':[]}
            assert p['proposal']==wanted and p['target_index']==task['prefix']['target_index'];task['proposal']=wanted
        elif tag=='DIAGNOSTIC_KEEP':assert task['epoch']>0 and p['used'] is True
        elif tag=='DIAGNOSE_RETURN':assert p['proposal']==task.get('proposal',{'action':'keep','edits':[]})
        elif tag=='DIAGNOSTIC_TX_BEGIN':assert p['before']==task['ordinary'] and p['edits']==task['proposal']['edits']
        elif tag=='DIAGNOSTIC_TX_END':
            expected=deepcopy(task['ordinary']);site=task['proposal']['edits'][0]['address'];expected['current']['X']=[x for x in expected['current']['X'] if x['address']!=site];expected['ordinary_PX_anchor']={f:expected['current'][f] for f in ('P','X')};assert p['after']==expected;task['after']=p['after'];task['tx']=task['writes']=1;feedbackTX+=1
        elif tag=='OWNED_BATCH_BEGIN':
            assert task is None and external is None and batch is None and p['before']==last[k] and p['all_consumed_before_TD']
            wanted_names=('keep',) if arm=='KeepOnly' else ('controller-delete',) if arm=='CandidateOnly' else ('keep','controller-delete');wanted_ids=[source_registrations[('private',case,arm,n)] for n in wanted_names]
            assert [o['observation_id'] for o in p['observations']]==wanted_ids and p['ordinals']==[1 if n=='keep' else 2 for n in wanted_names]
            for obs in p['observations']:
                oid=obs['observation_id'];reg=registrations[oid];assert issued[oid]==obs and oid not in consumed and reg['parent']==k and reg['payload']['registration']['origin_L']==p['before']['learning_values']
            consumed.update(wanted_ids);batch={'before':p['before'],'ids':wanted_ids,'receipts':[],'processed':[],'accept_count':0}
        elif tag=='OWNED_OBSERVATION_REJECTED':
            obs=p['observation'];oid=obs['observation_id'];reg=registrations[oid];diff=changes(reg['payload']['source_before']['immediate'],last[k]['current'],obs)
            receipt={'applied':False,'reason':'current_mechanism_differs_on_observed_path','observation_id':oid,'mechanism_changes':diff}
            assert batch is not None and oid==batch['ids'][len(batch['processed'])] and issued[oid]==obs and diff and p['before']==p['after']==last[k] and oid in consumed and p['receipt']==receipt
            batch['processed'].append(oid);batch['receipts'].append(receipt);rejections+=1;rejected.append({'case':case,'arm':arm,'candidate':reg['key'][3],'terminal':obs['trace']['outcome'],'mechanism_changes':diff})
        elif tag=='OWNED_EXTERNAL_BEGIN':
            obs=p['observation'];oid=obs['observation_id'];reg=registrations[oid];assert task is None and external is None and batch is not None and oid==batch['ids'][len(batch['processed'])] and issued[oid]==obs and oid in consumed and p['before']==last[k]
            assert changes(reg['payload']['source_before']['immediate'],p['before']['current'],obs)==[] and p['external_update_index']==last[k]['external_updates'] and p['main_clock_advanced'] is False;external=p
        elif tag=='OWNED_EXTERNAL_END':
            obs=external['observation'];oid=obs['observation_id'];reg=registrations[oid];receipt={'applied':True,'reason':'same_mechanism_on_observed_path','observation_id':oid,'mechanism_changes':[]}
            assert p['observation_id']==oid and p['receipt']==receipt;extpolicy+=update(external['before'],{'trace':obs['trace'],'_episode':obs['episode']},p,rows,True);ext+=1;last[k]=p['after']
            batch['processed'].append(oid);batch['receipts'].append(receipt);batch['accept_count']+=1
            accepted.append({'case':case,'arm':arm,'candidate':reg['key'][3],'terminal':obs['trace']['outcome'],'numeric_content_changed':external['before']['learning_values']!=p['after']['learning_values'],
                'before_numeric':external['before']['learning_values'],'after_numeric':p['after']['learning_values'],'observed_trace':obs['trace']});external=None
        elif tag=='OWNED_BATCH_END':
            assert batch is not None and batch['processed']==batch['ids'] and p['before']==batch['before'] and p['after']==last[k] and p['receipts']==batch['receipts'];batch['ended']=True
        elif tag=='BATCH_TRANSFER_RESULT':
            assert batch is not None and batch.get('ended') and p['observation_ids']==batch['ids'] and p['before']==batch['before'] and p['after']==last[k] and p['receipts']==batch['receipts']
            assert p['native_delta']=={'rollout':0,'step':0,'transaction':2*batch['accept_count']};transfers.extend({'case':case,'arm':arm,**q} for q in batch['receipts']);batch=None
        elif tag=='OWNED_DUPLICATE_REJECTED':
            assert p['state_unchanged'] and p['error_type']=='ProtocolError' and 'already consumed' in p['error'] and all(x in consumed for x in p['observation_ids']) and p['native_delta']=={'rollout':0,'step':0,'transaction':0};duplicates+=1
        elif tag=='NO_TRIAL_INGESTION':
            assert arm=='NoTrialLearning' and p['before']==p['after']==last[k] and p['native_delta']=={'rollout':0,'step':0,'transaction':0}
            assert p['observation_ids']==[source_registrations[('private',case,arm,n)] for n in ('keep','controller-delete')] and all(x not in consumed for x in p['observation_ids'])
        elif tag=='POST_MAIN_STATE':assert task is None and p['epoch']==len(tasks[k])-1 and p['state']==last[k];post[k].append(p['state'])
        elif tag=='STREAM_ARM':
            ts=tasks[k];values=[return_value(x) for x in ts];assert len(ts)==len(post[k])==p['main_tasks']==6 and p['final_state']==last[k]
            assert [number(v) for v in p['returns']]==values and p['outcomes']==[x['terminal'] for x in ts] and p['successes']==sum(x['terminal']=='SUCCESS' for x in ts) and number(p['mean_return']).hex()==(sum(values)/6).hex();summaries.append(p)
        elif tag=='RESULT':assert p['complete'] and p['streams']==summaries;result=p
        elif tag=='FINAL':assert p['complete'] and p['profile_restored'];final=p
        else:raise AssertionError('unexpected tag '+tag)
    assert task is None and not stack and external is None and batch is None and set(registrations)==set(issued) and len(summaries)==len(c['cases'])*len(c['arms'])
    assert len(sources)==2 and ordinary==sum(len(ts) for ts in tasks.values()) and ext+rejections==len(consumed) and duplicates==6
    assert final['counts']==result['counts']=={'rollout':ordinary,'step':steps,'transaction':5+ordinary+policyTX+ext+extpolicy+feedbackTX+privateTX}
    # The new source executes the old native body literally except its nominal issue block.
    def run_body(path,classname):
        tree=ast.parse(path.read_text(encoding='utf-8'));cl=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==classname);f=next(n for n in cl.body if isinstance(n,ast.FunctionDef) and n.name=='run_task');tr=next(n for n in f.body if isinstance(n,ast.Try));assert isinstance(tr.body[-2],ast.If);tr.body[-2]=ast.Pass();return ast.dump(f,include_attributes=False)
    assert run_body(HERE/'intervention_experience.py','OwnedInterventionSource')==run_body(HERE.parent/'controller_horizon_value_v144/mechanism_loop.py','ObservationTaskLoop')
    compact=[{f:([number(v) for v in x[f]] if f=='returns' else number(x[f]) if f=='mean_return' else x[f]) for f in ('case','arm','successes','returns','outcomes','mean_return','external_updates')} for x in summaries]
    costs=[];comparisons=[];duplicate_trace=[]
    for case in c['cases']:
        for arm in c['arms']:
            ts=[t for k,v in tasks.items() if k[1:3]==(case,arm) for t in v];trs=[x for x in transfers if (x['case'],x['arm'])==(case,arm)]
            costs.append({'case':case,'arm':arm,'rollout':len(ts),'step':sum(len(t['trace']['steps']) for t in ts),'transaction':2*len(ts)+2*sum(x['applied'] for x in trs)+sum(t['counters']['diagnostic_transactions'] for t in ts)+1,'shared5TX_excluded':True})
            akey=('private',case,arm,'keep');bkey=('private',case,arm,'controller-delete')
            duplicate_trace.append({'case':case,'arm':arm,'first_keep_candidate_raw_identical':tasks[akey][0]['trace']==tasks[bkey][0]['trace']})
        for arm in ('KeepOnly','CandidateOnly','CompatibleBatch'):
            ka=('stream',case,arm,None);kb=('stream',case,'NoTrialLearning',None)
            comparisons.append({'case':case,'arm':arm,'vs':'NoTrialLearning','all6_raw_identical':[t['trace'] for t in tasks[ka]]==[t['trace'] for t in tasks[kb]],
                'all6_post_R_L_I_identical':all(all(x[f]==y[f] for f in ('current','learning_values','immediate')) for x,y in zip(post[ka],post[kb]))})
    all_queries=[{'case':case,'arm':arm,**v} for (case,arm),v in query.items()]
    # Source strategy equality is checked per same-case arm before any ingestion; no laterstate equality claim.
    source_roots_equal=all(all(diagnostics[case,arm]['post_TD']=={**diagnostics[case,'NoTrialLearning']['post_TD'],'source_label':diagnostics[case,arm]['post_TD']['source_label']} for arm in c['arms']) for case in c['cases'])
    output={'schema':'V151_STDLIB_INTERVENTION_TRIAL_LEARNING_REVIEW','complete':True,'native_counts':final['counts'],'records':len(rs),'input_pins':len(claim['input_binding_before']),
      'summaries':compact,'queries':all_queries,'online_costs':costs,'comparisons':comparisons,'accepted':accepted,'rejected':rejected,'observation_transfers':transfers,
      'pre_ingestion_postTD_roots_equal_except_labels':source_roots_equal,'keep_candidate_first_trace_comparisons':duplicate_trace,
      'native_ordinary_updates':ordinary,'ordinary_policy_TX':policyTX,'external_ordinary_updates':ext,'external_policy_TX':extpolicy,'checkpoint_TX':3,'source_TX':2,
      'private_candidate_X_TX':privateTX,'main_feedback_X_TX':feedbackTX,'actual_explore_events':explorations,'success_diagnosis':0,'mechanism_rejections':rejections,'duplicate_batch_rejections':duplicates,
      'issued_new_observations':len(issued),'consumed_new_observations':len(consumed),'unconsumed_new_observations':len(issued)-len(consumed),'native_source_AST_only_issue_block_changed':True,
      'old_native_checker_bank_reruns':0,'new_keys_RNG_DP_calibration_collection':0,'formal_B1_or_science_qualification':False}
    save(HERE/'stored_audit_result.json',output);save(out/'exit.json',{'complete':True,'completed_at_utc':datetime.now(timezone.utc).isoformat(),'result':meta(HERE/'stored_audit_result.json')})
    print(json.dumps({'complete':True,'native_counts':final['counts'],'records':len(rs),'summaries':compact,'accepted':[{k:v for k,v in x.items() if k not in ('before_numeric','after_numeric','observed_trace')} for x in accepted],'rejected':rejected,'queries':all_queries,'comparisons':comparisons,'pre_roots_equal':source_roots_equal},sort_keys=True))

if __name__=='__main__':main()
