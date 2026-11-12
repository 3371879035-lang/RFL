"""New stdlib review of actual foreign-witness counterexample and strict context checks; no RFL/oldchecker execution."""
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
    c=load(HERE/'contract.json');cl=load(HERE/'evidence/claim.json');ex=load(HERE/'evidence/exit.json')
    assert ex['child_exit_code']==0 and ex['input_bytes_unchanged'] and cl['input_binding_before']==ex['input_binding_after']
    for path,pin in cl['input_binding_before'].items():assert meta(ROOT/path)==pin,path
    assert meta(HERE/'evidence/raw.jsonl')==ex['raw']
    for f in ('raw','exit','review'):
        p=c['ordinary_checkpoint'][f];assert meta(ROOT/p['path'])=={k:p[k] for k in ('bytes','sha256')}
    oldrs=[json.loads(x) for x in (ROOT/c['ordinary_checkpoint']['raw']['path']).read_text().splitlines()];preps=[r for r in oldrs if r['tag']=='PREPARATION_COMPLETE'];assert len(preps)==1;prep=preps[0]['payload']['state']
    rows={}
    for line in (ROOT/c['reference']['path']).read_text().splitlines():
        if line.startswith('DECISION_CONTEXT='):
            q=json.loads(line.split('=',1)[1]);rows[tuple(q['context'])]={a:float.fromhex(v) for a,v in q['q_row_hex']}
    rs=[json.loads(x) for x in (HERE/'evidence/raw.jsonl').read_text().splitlines()];assert [r['seq'] for r in rs]==list(range(len(rs)))
    task=None;stack=[];last={};tasks=defaultdict(list);details={};regs={};source_ids={};issued={};consumed=set();batch=None;external=None;ordinals=Counter();tags=Counter();casefinal=[];events=[];accepted=[];rejected=[]
    steps=ordinary=policyTX=privateTX=mainTX=ext=extpolicy=0
    def prop_for(name,parent):
        return {'action':'keep','edits':[]} if name=='baseline' else parent['joint'] if name=='joint' else parent['candidate']
    def edited(before,prop):
        after=deepcopy(before);after['X']=[x for x in after['X'] if all(x['address']!=e['address'] for e in prop['edits'])];return after
    for r in rs:
        tag,p,ctx=r['tag'],r['payload'],r['context'];tags[tag]+=1;k=key(ctx);arm=ctx.get('arm');name=ctx.get('candidate')
        if tag=='REFERENCE':assert p['digest']==c['reference']['q_digest'] and p['rows']==len(rows)
        elif tag=='RECORDED_ORDINARY_MATERIALIZED':
            assert p['recorded_payload']==prep and p['source_seq']==preps[0]['seq'] and p['source_raw_sha256']==c['ordinary_checkpoint']['raw']['sha256']
            assert all(p[f]==prep[f] for f in ('immediate','current','learning_values')) and p['native_delta']=={'rollout':0,'step':0,'transaction':3} and p['restored_issued_identities']==0
        elif tag=='SHARED_SOURCE':
            assert p['before']==prep['current'] and p['values']==prep['learning_values'];expected=stores(prep['current'])
            expected['X'].update({(0,2,0,1,0,4):3,(1,2,2,1,0,0):3,(0,2,0,1,3,4):3,(3,4,10,0,5,4):0});expected['D'][(0,2,0,1,3,1,0)]=4
            assert len(p['edits'])==5 and maps_equal(stores(p['state']),expected);source=p['state']
        elif tag=='MAIN_INITIALIZED':
            q=p['state'];assert q['immediate']==q['current']==source and q['learning_values']==prep['learning_values'] and q['completed_episodes']==q['external_updates']==0 and q['attempted_epochs']==[]
            assert p['implementation']==('EvidenceExperienceLoop' if arm=='LegacyForeign' else 'StrictWitnessLoop');last[k]=q
        elif tag=='DIAGNOSTIC_INPUT':
            assert p['evidence']==task['evidence'] and p['post_TD']==task['ordinary'] and p['candidate']==proposal(task['evidence']) and p['prefix']==prefix_from(task['evidence'],rows)
            task['candidate']=p['candidate'];task['prefix']=p['prefix']
        elif tag=='OWNED_BRANCH_EDIT':
            prop=prop_for(name,task);assert prop['edits'] and p['before']==task['ordinary']['current'] and p['edits']==prop['edits'] and p['after']==edited(p['before'],prop);privateTX+=1
        elif tag=='OWNED_BRANCH_REGISTERED':
            prop=prop_for(name,task);assert p['consumer']==task['ordinary'] and p['proposal']==prop;reg=p['registration'];ordinals[arm]+=1;expected=edited(task['ordinary']['current'],prop)
            assert reg['ordinal']==ordinals[arm] and reg['main_epoch']==0 and reg['origin_L']==task['ordinary']['learning_values'] and reg['kappa']==1 and reg['phi']==0 and reg['source_I']==expected and reg['proposal']==prop
            assert p['source_before']['immediate']==p['source_before']['current']==expected and p['source_before']['learning_values']==reg['origin_L'] and p['source_before']['completed_episodes']==p['source_before']['external_updates']==0
            regs[reg['id']]={'payload':p,'key':k,'parent':task['key']};source_ids[k]=reg['id']
        elif tag=='PRIVATE_START':
            prop=prop_for(name,task);assert p['parent']==task['ordinary'] and p['state']['immediate']==p['state']['current']==edited(task['ordinary']['current'],prop) and p['state']['learning_values']==task['ordinary']['learning_values'] and p['n']==1
            assert p['foreign_plan']==(name=='foreign') and p['legacy_registration']==(arm=='StrictForeign' and name=='foreign');last[k]=p['state']
        elif tag=='TASK_BEGIN':
            if ctx['phase']=='private':assert task is not None;stack.append(task)
            else:assert task is None
            assert len(tasks[k])==p['epoch']==0 and p['before']['attempted_epochs']==[0] and all(p['before'][f]==last[k][f] for f in p['before'] if f!='attempted_epochs')
            phi=3 if name=='foreign' else 0;coins=[(1<<64)-1]*12;chi=[[0]]*12
            if ctx['phase']=='private':
                view=task['trial_evidence'] if name in ('baseline','joint') else task['evidence']
                for i,s in enumerate(prefix_from(view,rows)['rows']):coins[i]=0;chi[i]=[s['admissible_rank']]
            ep={'epoch':0,'kappa':1,'proposal':1,'tape':{'phase':phi,'error_flag':0,'cause_rank':12},'coins':coins,'rejections':chi};mask={'decision':None,'controller':None,'plant':None,'trap':{'cell':[1,2],'t':0}}
            assert p['episode']==ep and p['environment_mask_audit_only']==mask;task={'key':k,'before':p['before'],'episode':ep,'mask':mask,'diag':0,'tx':0,'writes':0}
        elif tag=='TASK_RAW':
            tr=p['trace'];ep=task['episode'];phi=ep['tape']['phase'];assert task['key']==k and tr['mask']==task['mask'] and tr['option_in_force']==1 and len(p['draws'])==len(tr['steps'])
            at=(0,2,0,1,phi);z,m=1,0;cur=stores(task['before']['current']);num=stores(task['before']['learning_values']);calls=[];cells={(0,2),(4,2),(1,1),(2,1),(3,1),(1,2),(2,2),(3,2),(1,3),(3,3),(1,4),(2,4),(3,4)};delta=((0,-1),(0,1),(-1,0),(1,0),(0,0))
            for i,(draw,x) in enumerate(zip(p['draws'],tr['steps'])):
                q=at+(z,m);values={a:num['Q'].get(q+(a,),v) for a,v in rows[q].items()};greedy=cur['D'].get(q,min(a for a,v in values.items() if v==max(values.values())));explore=ep['coins'][i]==0;rank=ep['rejections'][i][0];cmd=sorted(rows[q])[rank%len(rows[q])] if explore else greedy;u=cur['X'].get(at+(cmd,),cmd);calls.append([i,0,0,ep['coins'][i]])
                if explore:calls.append([i,1,0,rank])
                assert draw=={'i':i,'explore':explore,'admissible':sorted(rows[q]),'a_cmd':cmd} and x['a_cmd']==cmd and x['u']==x['a_realized']==u
                dx,dy=delta[u];cell=(at[0]+dx,at[1]+dy);cell=cell if cell in cells else at[:2];nt=at[2]+1
                outcome='COLLISION' if cell==(2,2) and nt%3==phi%3 else 'TRAP' if cell==(1,2) and at[2]==0 else 'SUCCESS' if cell==(4,2) else 'TIMEOUT' if nt>=12 else None
                assert x['state']=={'x':cell[0],'y':cell[1],'t':nt,'kappa':1,'phi':phi} and x['control']=={'z':1,'m':1 if m or cell==(2,1) else 0} and x['terminal']==(outcome is not None) and x['outcome']==outcome and not x['illegal']
                assert number(x['reward']).hex()==(-.02+(1 if outcome=='SUCCESS' else -1 if outcome else 0)).hex();at=state(x['state']);z,m=x['control']['z'],x['control']['m']
            assert tr['steps'][-1]['terminal'] and tr['outcome']==tr['steps'][-1]['outcome'] and p['coordinates']==calls and p['return_hex']==return_value({'trace':tr}).hex();task['raw']={**p,'_episode':ep};steps+=len(tr['steps'])
        elif tag=='ORDINARY_UPDATE':policyTX+=update(task['before'],task['raw'],p,rows,False);ordinary+=1;task['ordinary']=p['after'];task['after']=p['after']
        elif tag=='DIAGNOSE_BEGIN':
            assert ctx['phase']=='stream' and p['evidence']==evidence(task['raw']['trace']) and p['state_before']==task['ordinary'];task['evidence']=p['evidence'];task['diag']+=1
        elif tag=='STRICT_FACTORY_REJECTED':
            assert arm=='StrictForeign' and p['before']==p['after']==task['ordinary'] and p['registrations_before']==p['registrations_after']==0 and p['native_delta']=={'rollout':0,'step':0,'transaction':0} and p['error_type']=='ProtocolError' and 'trialcontext' in p['error'];events.append({'case':arm,'gate':'factory','rejected':True,'native_delta':p['native_delta']})
        elif tag=='OWNED_OBSERVATION_ISSUED':
            oid=p['observation_id'];reg=regs[oid];assert reg['key']==k and p['trace']==tasks[k][0]['trace'] and p['episode']==details[k]['episode'] and p['source_epoch']==p['main_epoch']==0 and oid not in issued and p['observation_revision']=='v153-experiment-witness-origin';issued[oid]=p
        elif tag=='PRIVATE_COMPLETE':
            assert p['state']==last[k] and p['n']==len(tasks[k])==1 and [number(v) for v in p['returns']]==[return_value(tasks[k][0])] and p['observation_id']==source_ids[k]
        elif tag=='TRIAL_DERIVED_PROPOSAL':
            witness=p['witness'];reg=regs[witness['observation_id']];assert witness==issued[witness['observation_id']] and witness['trace']['outcome']!='SUCCESS' and p['parent_proposal']==task['candidate']==reg['payload']['proposal'] and p['main_post_TD']==task['ordinary']
            ev=evidence(witness['trace']);extra=proposal(ev);assert p['evidence']==ev and extra is not None and p['proposal']=={'action':'apply','edits':task['candidate']['edits']+extra['edits']};task['joint']=p['proposal'];task['trial_evidence']=ev
        elif tag=='LEGACY_FOREIGN_AUTHORIZED':
            assert arm=='LegacyForeign' and p['observation']==issued[source_ids['private',arm,0,'foreign']] and p['observation']['episode']['tape']['phase']==3 and p['proposal']==task['joint'] and p['proposal']['edits'][-1]['address']['state']['phi']==3
            assert p['before']==p['after']==task['ordinary'] and p['authority_before']==0 and p['authority_after']==1 and p['live_commit'] is False and p['native_delta']=={'rollout':0,'step':0,'transaction':0};events.append({'case':arm,'legacy_foreign_authority_admitted':True,'foreign_site':p['proposal']['edits'][-1]['address'],'live_commit':False})
        elif tag=='STRICT_WITNESS_REJECTED':
            assert arm=='StrictForeign' and p['observation']==issued[source_ids['private',arm,0,'foreign']] and p['before']==p['after']==task['ordinary'] and p['authority_before']==p['authority_after']==0 and p['live_commit'] is False and p['native_delta']=={'rollout':0,'step':0,'transaction':0}
            assert p['error_type']=='ProtocolError' and 'trialcontext' in p['error'];events.append({'case':arm,'gate':'actual_foreign_witness','rejected':True,'native_delta':p['native_delta']})
        elif tag=='STRICT_VALID_FLOW':
            assert arm=='StrictValid' and p['proposal']==task['joint'] and p['witness']==issued[source_ids['private',arm,0,'first']] and p['main_before']==p['main_after']==task['ordinary']
            base=tasks['private',arm,0,'baseline'][0];joint=tasks['private',arm,0,'joint'][0]
            assert number(p['baseline_return']).hex()==return_value(base).hex() and number(p['joint_return']).hex()==return_value(joint).hex() and p['same_literal_episode'] and p['same_parameters'] and details['private',arm,0,'baseline']['episode']==details['private',arm,0,'joint']['episode']
            task['proposal']=task['joint'] if return_value(joint)>return_value(base) else {'action':'keep','edits':[]};events.append({'case':arm,'authorized':True,'baseline_return':return_value(base),'joint_return':return_value(joint),'same_episode':True})
        elif tag=='DIAGNOSE_RETURN':assert p['proposal']==task.get('proposal',{'action':'keep','edits':[]})
        elif tag=='DIAGNOSTIC_TX_BEGIN':assert arm=='StrictValid' and p['before']==task['ordinary'] and p['edits']==task['proposal']['edits']
        elif tag=='DIAGNOSTIC_TX_END':
            expected=deepcopy(task['ordinary']);expected['current']=edited(expected['current'],task['proposal']);expected['ordinary_PX_anchor']={f:expected['current'][f] for f in ('P','X')};assert p['after']==expected;task['after']=p['after'];task['tx']=1;task['writes']=len(task['proposal']['edits']);mainTX+=1
        elif tag=='TASK_COMPLETE':
            assert p['before']==task['before'] and p['trace']==task['raw']['trace'] and p['ordinary_after']==task['ordinary'] and p['after']==task['after'] and p['terminal']==p['trace']['outcome']
            assert p['counters']=={'ordinary_updates':1,'diagnostic_calls':task['diag'],'query_calls':0,'diagnostic_transactions':task['tx'],'diagnostic_edit_addresses':task['writes']}
            if p['terminal']=='SUCCESS':assert task['diag']==task['tx']==task['writes']==0
            tasks[k].append(p);details[k]=task;last[k]=p['after'];task=stack.pop() if stack else None
        elif tag=='OWNED_BATCH_BEGIN':
            assert arm=='StrictValid' and task is None and batch is None and external is None and p['before']==last[k] and p['all_consumed_before_TD'];ids=[source_ids['private',arm,0,n] for n in ('baseline','joint')]
            assert [o['observation_id'] for o in p['observations']]==ids and p['ordinals']==[2,3]
            for o in p['observations']:
                reg=regs[o['observation_id']];assert issued[o['observation_id']]==o and o['observation_id'] not in consumed and reg['payload']['registration']['origin_L']==p['before']['learning_values'] and reg['parent']==k
            consumed.update(ids);batch={'before':p['before'],'ids':ids,'processed':[],'receipts':[]}
        elif tag=='OWNED_OBSERVATION_REJECTED':
            o=p['observation'];oid=o['observation_id'];reg=regs[oid];diff=changes(reg['payload']['source_before']['immediate'],last[k]['current'],o);receipt={'applied':False,'reason':'current_mechanism_differs_on_observed_path','observation_id':oid,'mechanism_changes':diff}
            assert batch is not None and oid==batch['ids'][len(batch['processed'])] and issued[oid]==o and diff and p['before']==p['after']==last[k] and p['receipt']==receipt;batch['processed'].append(oid);batch['receipts'].append(receipt);rejected.append(oid)
        elif tag=='OWNED_EXTERNAL_BEGIN':
            o=p['observation'];oid=o['observation_id'];reg=regs[oid];assert batch is not None and external is None and oid==batch['ids'][len(batch['processed'])] and issued[oid]==o and p['before']==last[k] and not changes(reg['payload']['source_before']['immediate'],p['before']['current'],o);external=p
        elif tag=='OWNED_EXTERNAL_END':
            o=external['observation'];oid=o['observation_id'];receipt={'applied':True,'reason':'same_mechanism_on_observed_path','observation_id':oid,'mechanism_changes':[]};assert p['observation_id']==oid and p['receipt']==receipt
            extpolicy+=update(external['before'],{'trace':o['trace'],'_episode':o['episode']},p,rows,True);ext+=1;last[k]=p['after'];batch['processed'].append(oid);batch['receipts'].append(receipt);accepted.append(oid);external=None
        elif tag=='OWNED_BATCH_END':assert batch['processed']==batch['ids'] and p['receipts']==batch['receipts'] and p['before']==batch['before'] and p['after']==last[k];batch=None
        elif tag=='CASE_FINAL':
            assert task is None and batch is None and p['case']==arm and p['main_tasks']==1 and p['receipt']==tasks[k][0] and p['final_state']==last[k] and p['final_state']['immediate']==source
            assert p['authority_records']==(0 if arm=='StrictForeign' else 1) and p['registered_sources']==(3 if arm=='StrictValid' else 1) and p['external_updates']==(1 if arm=='StrictValid' else 0)
            assert stores(last[k]['current'])['X'][(3,4,10,0,5,4)]==0
            if arm!='StrictValid':assert last[k]['current']['X']==source['X'] and p['receipt']['counters']['diagnostic_transactions']==0
            else:assert p['receipt']['counters']['diagnostic_transactions']==1 and p['receipt']['counters']['diagnostic_edit_addresses']==2
            casefinal.append({'case':arm,'authority_records':p['authority_records'],'registered_sources':p['registered_sources'],'external_updates':p['external_updates'],'main_terminal':p['receipt']['terminal'],'live_diagnostic_TX':p['receipt']['counters']['diagnostic_transactions'],'live_edit_addresses':p['receipt']['counters']['diagnostic_edit_addresses']})
        elif tag=='RESULT':assert p['complete'] and len(p['streams'])==3;result=p
        elif tag=='FINAL':assert p['complete'] and p['profile_restored'];final=p
        else:raise AssertionError('unexpectedtag '+tag)
    assert task is None and not stack and batch is None and external is None and len(casefinal)==3 and len(regs)==len(issued)==5 and len(consumed)==2
    assert final['counts']==result['counts']=={'rollout':ordinary,'step':steps,'transaction':4+ordinary+policyTX+privateTX+mainTX+ext+extpolicy}
    output={'schema':'V154_STDLIB_WITNESS_CONTEXT_REVIEW','complete':True,'native_counts':final['counts'],'records':len(rs),'input_pins':len(cl['input_binding_before']),
      'events':events,'cases':casefinal,'legacy_foreign_authority_counterexample':True,'strict_foreign_factory_zero_work_rejection':True,'strict_actual_foreign_witness_zero_work_rejection':True,'strict_samecontext_atomic_joint_path_completed':True,
      'native_ordinary_updates':ordinary,'ordinary_policy_TX':policyTX,'external_ordinary_updates':ext,'external_policy_TX':extpolicy,'private_candidate_TX':privateTX,'main_feedback_TX':mainTX,
      'issued_observations':len(issued),'consumed_observations':len(consumed),'unconsumed_observations':len(issued)-len(consumed),'accepted':accepted,'rejected':rejected,
      'future_curve_or_utility_experiment':False,'success_main_diagnosis':0,'original_v153_actual_capture_modified_or_rerun':False,'all_source_and_R_L_I_checked':True,'old_checker_bank_reruns':0,'new_keys_RNG_DP_calibration_collection':0,'full_API_or_science_qualification':False}
    save(HERE/'stored_audit_result.json',output);save(out/'exit.json',{'complete':True,'completed_at_utc':datetime.now(timezone.utc).isoformat(),'result':meta(HERE/'stored_audit_result.json')})
    print(json.dumps({'complete':True,'counts':final['counts'],'records':len(rs),'events':events,'cases':casefinal},sort_keys=True))

if __name__=='__main__':main()
