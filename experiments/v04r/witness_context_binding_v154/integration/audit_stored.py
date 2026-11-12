"""New stdlib review of actual foreign-witness counterexample and strict context checks; no RFL/oldchecker execution."""
from pathlib import Path
from collections import Counter,defaultdict
from copy import deepcopy
from datetime import datetime,timezone
import hashlib,json,ast
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]

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
    def save(p,x):
        with p.open('x',encoding='utf-8',newline='\n') as f:json.dump(x,f,ensure_ascii=True,indent=2);f.write('\n')
    save(out/'claim.json',{'source':meta(Path(__file__)),'native':meta(HERE/'evidence/exit.json'),'automatic_retry':False,'started_at_utc':datetime.now(timezone.utc).isoformat()})
    c=load(HERE/'contract.json');claim=load(HERE/'evidence/claim.json');ex=load(HERE/'evidence/exit.json')
    assert ex['child_exit_code']==0 and ex['input_bytes_unchanged'] and claim['input_binding_before']==ex['input_binding_after']
    for path,pin in claim['input_binding_before'].items():assert meta(ROOT/path)==pin,path
    assert meta(HERE/'evidence/raw.jsonl')==ex['raw']
    rs=[json.loads(s) for s in (HERE/'evidence/raw.jsonl').read_text().splitlines()];assert [r['seq'] for r in rs]==list(range(len(rs)))
    def tagged(tag,arm=None):return [r for r in rs if r['tag']==tag and (arm is None or r['context'].get('arm')==arm)]
    def one(tag,arm=None):
        items=tagged(tag,arm);assert len(items)==1,(tag,arm,len(items));return items[0]
    prep=one('RECORDED_ORDINARY_MATERIALIZED')['payload'];assert prep['materialization_TX']==3 and all(prep[f]==prep['recorded_payload'][f] for f in ('immediate','current','learning_values'))
    src=one('SHARED_SOURCE')['payload'];expected=stores(prep['current']);expected['D'][(0,2,0,1,3,1,0)]=4;expected['X'][(0,2,0,1,3,4)]=3;expected['X'][(1,2,2,1,3,0)]=3
    assert src['before']==prep['current'] and maps_equal(stores(src['state']),expected) and src['values']==prep['learning_values'] and len(src['edits'])==3
    rows={}
    for line in (ROOT/c['reference']['path']).read_text().splitlines():
        if line.startswith('DECISION_CONTEXT='):
            q=json.loads(line.split('=',1)[1]);rows[tuple(q['context'])]={a:float.fromhex(v) for a,v in q['q_row_hex']}
    groups=defaultdict(list)
    for r in rs:
        if r['tag'] in ('TASK_BEGIN','TASK_RAW','ORDINARY_UPDATE','TASK_COMPLETE','TASK_PARTIAL'):groups[key(r['context'])].append(r)
    assert len(groups)==7;native_step=0;policyTX=0;info={}
    initial={r['context']['arm']:r['payload'] for r in tagged('MAIN_INITIALIZED')}
    assert set(initial)==set(c['cases'])
    for arm,p in initial.items():
        assert p['state']['immediate']==p['state']['current']==src['state'] and p['state']['learning_values']==src['values'] and p['state']['completed_episodes']==p['state']['external_updates']==0
        assert p['MRO'][:4]==['StrictTrialDerivedAgent','StrictWitnessLoop','TrialDerivedAgent','EvidenceExperienceLoop']
    for k,events in groups.items():
        phase,arm,epoch,name=k;tags=[r['tag'] for r in events];assert tags[:3]==['TASK_BEGIN','TASK_RAW','ORDINARY_UPDATE'] and len(events)==4
        b,raw,upd,end=(r['payload'] for r in events);ep=b['episode'];tr=raw['trace'];assert ep['epoch']==0 and ep['kappa']==1 and ep['proposal']==1 and ep['tape']=={'phase':3,'error_flag':0,'cause_rank':12} and b['before']['attempted_epochs']==[0]
        coins=[(1<<64)-1]*12;chi=[[0]]*12
        if phase=='private':
            view=one('TRIAL_DERIVED_PROPOSAL',arm)['payload']['evidence'] if name in ('deep-keep','deep-first','joint') else one('DIAGNOSTIC_INPUT',arm)['payload']['evidence']
            for i,s in enumerate(prefix_from(view,rows)['rows']):coins[i]=0;chi[i]=[s['admissible_rank']]
        else:assert all(b['before'][f]==initial[arm]['state'][f] for f in b['before'] if f!='attempted_epochs')
        assert ep['coins']==coins and ep['rejections']==chi
        assert b['environment_mask_audit_only']==tr['mask']=={'decision':None,'controller':None,'plant':None,'trap':{'cell':[1,2],'t':0}} and tr['option_in_force']==1
        at=(0,2,0,1,3);z,m=1,0;cur=stores(b['before']['current']);num=stores(b['before']['learning_values']);calls=[];cells={(0,2),(4,2),(1,1),(2,1),(3,1),(1,2),(2,2),(3,2),(1,3),(3,3),(1,4),(2,4),(3,4)};delta=((0,-1),(0,1),(-1,0),(1,0),(0,0));assert len(raw['draws'])==len(tr['steps'])
        for i,(draw,s) in enumerate(zip(raw['draws'],tr['steps'])):
            q=at+(z,m);vals={a:num['Q'].get(q+(a,),v) for a,v in rows[q].items()};greedy=cur['D'].get(q,min(a for a,v in vals.items() if v==max(vals.values())));explore=coins[i]==0;rank=chi[i][0];cmd=sorted(rows[q])[rank%len(rows[q])] if explore else greedy;u=cur['X'].get(at+(cmd,),cmd)
            calls.append([i,0,0,coins[i]])
            if explore:calls.append([i,1,0,rank])
            assert draw=={'i':i,'explore':explore,'admissible':sorted(rows[q]),'a_cmd':cmd} and s['a_cmd']==cmd and s['u']==s['a_realized']==u
            dx,dy=delta[u];cell=(at[0]+dx,at[1]+dy);cell=cell if cell in cells else at[:2];nt=at[2]+1;outcome='COLLISION' if cell==(2,2) and nt%3==0 else 'TRAP' if cell==(1,2) and at[2]==0 else 'SUCCESS' if cell==(4,2) else 'TIMEOUT' if nt>=12 else None
            assert s['state']=={'x':cell[0],'y':cell[1],'t':nt,'kappa':1,'phi':3} and s['control']=={'z':1,'m':1 if m or cell==(2,1) else 0} and s['terminal']==(outcome is not None) and s['outcome']==outcome and not s['illegal'] and number(s['reward']).hex()==(-.02+(1 if outcome=='SUCCESS' else -1 if outcome else 0)).hex()
            at=state(s['state']);z,m=s['control']['z'],s['control']['m']
        assert tr['steps'][-1]['terminal'] and tr['outcome']==tr['steps'][-1]['outcome'] and raw['coordinates']==calls and raw['return_hex']==return_value({'trace':tr}).hex();native_step+=len(tr['steps']);policyTX+=update(b['before'],{**raw,'_episode':ep},upd,rows,False)
        if tags[-1]=='TASK_PARTIAL':
            assert arm=='ForeignPlanAgent' and phase=='stream' and end['ordinary_committed'] and end['complete_task_receipt'] is False and end['error_type']=='ProtocolError' and 'trialcontext' in end['error'] and end['after']==upd['after'] and end['counters']=={'ordinary_updates':1,'diagnostic_calls':1,'query_calls':0,'diagnostic_transactions':0,'diagnostic_edit_addresses':0}
        else:
            assert tags[-1]=='TASK_COMPLETE' and end['before']==b['before'] and end['ordinary_after']==upd['after'] and end['trace']==tr and end['terminal']==tr['outcome']
            if phase=='private':assert end['after']==upd['after'] and end['counters']=={'ordinary_updates':1,'diagnostic_calls':0,'query_calls':0,'diagnostic_transactions':0,'diagnostic_edit_addresses':0}
            else:assert end['counters']=={'ordinary_updates':1,'diagnostic_calls':1,'query_calls':0,'diagnostic_transactions':1,'diagnostic_edit_addresses':2}
        info[k]={'before':b,'raw':raw,'ordinary':upd,'end':end}
    parent=info['stream','ValidAgentPhase3',None,None]['ordinary']['after'];derived=one('TRIAL_DERIVED_PROPOSAL')['payload'];first=proposal(one('DIAGNOSTIC_INPUT','ValidAgentPhase3')['payload']['evidence'])
    issued={r['payload']['observation_id']:r['payload'] for r in tagged('OWNED_OBSERVATION_ISSUED')};assert len(issued)==5 and derived['witness']==issued[derived['witness']['observation_id']] and derived['evidence']==evidence(derived['witness']['trace'])
    joint={'action':'apply','edits':first['edits']+proposal(derived['evidence'])['edits']};assert derived['proposal']==joint and derived['parent_proposal']==first and derived['main_post_TD']==parent
    for r in tagged('OWNED_BRANCH_REGISTERED'):
        p=r['payload'];name=r['context']['candidate'];prop={'action':'keep','edits':[]} if name in ('keep','deep-keep') else joint if name=='joint' else first
        assert p['proposal']==prop and p['consumer']==parent and p['registration']['origin_L']==parent['learning_values'] and p['registration']['kappa']==1 and p['registration']['phi']==3
        expected=deepcopy(parent['current']);expected['X']=[x for x in expected['X'] if all(x['address']!=e['address'] for e in prop['edits'])]
        assert p['source_before']['immediate']==p['source_before']['current']==expected and p['source_before']['learning_values']==parent['learning_values']
    for tag,names in (('BASE_MENU_VALUE',('keep','first')),('EXPANDED_MENU_VALUE',('deep-keep','deep-first','joint'))):
        p=one(tag)['payload'];actual={n:[return_value({'trace':info['private','ValidAgentPhase3',0,n]['raw']['trace']})] for n in names};vals={n:v[0] for n,v in actual.items()}
        assert plain(p['observed'])==actual and plain(p['values'])==vals and p['choice']==('keep' if tag=='BASE_MENU_VALUE' else 'joint')
    txb=one('DIAGNOSTIC_TX_BEGIN')['payload'];txe=one('DIAGNOSTIC_TX_END')['payload'];expected=deepcopy(parent);expected['current']['X']=[x for x in expected['current']['X'] if all(x['address']!=e['address'] for e in joint['edits'])];expected['ordinary_PX_anchor']={f:expected['current'][f] for f in ('P','X')}
    assert txb['before']==parent and txb['edits']==joint['edits'] and txe['after']==expected
    accepted=one('OWNED_EXTERNAL_BEGIN')['payload'];finished=one('OWNED_EXTERNAL_END')['payload'];assert accepted['observation']==issued[accepted['observation']['observation_id']] and not changes(next(r['payload']['source_before']['immediate'] for r in tagged('OWNED_BRANCH_REGISTERED') if r['payload']['registration']['id']==accepted['observation']['observation_id']),accepted['before']['current'],accepted['observation'])
    extpolicy=update(accepted['before'],{'trace':accepted['observation']['trace'],'_episode':accepted['observation']['episode']},finished,rows,True);assert len(tagged('OWNED_OBSERVATION_REJECTED'))==2
    valid=one('VALID_BOUND_AGENT')['payload'];bad=one('EXPECTED_PARTIAL_AGENT')['payload']
    assert valid['case']=='ValidAgentPhase3' and valid['main_complete'] and not valid['closed'] and valid['state']==finished['after'] and valid['complete_receipts']==1 and valid['registered_sources']==5 and valid['authority_records']==1 and valid['diagnostic_account']=={'algorithm':'TrialExpanded','trial_tasks_used':5,'trial_task_budget':5,'base_queries':1,'expanded_queries':1}
    assert bad['case']=='ForeignPlanAgent' and not bad['main_complete'] and bad['expected_protocol_rejection'] and bad['closed'] and bad['complete_receipts']==bad['registered_sources']==bad['authority_records']==0 and bad['diagnostic_account']['trial_tasks_used']==0 and bad['native_delta']=={'rollout':1,'step':1,'transaction':2}
    assert bad['state']==info['stream','ForeignPlanAgent',None,None]['ordinary']['after']
    final=one('FINAL')['payload'];assert final['complete'] and final['profile_restored'] and final['counts']=={'rollout':7,'step':native_step,'transaction':4+len(groups)+policyTX+3+1+1+extpolicy}
    assert all(x['state']['immediate']==src['state'] for x in (valid,bad))
    output={'schema':'V154_BOUND_AGENT_INTEGRATION_REVIEW','complete':True,'native_counts':final['counts'],'records':len(rs),'input_pins':len(claim['input_binding_before']),
      'positive_full_agent':{'main_complete':True,'joint_live_addresses':2,'atomic_live_TX':1,'private_tasks':5,'context':[1,3],'external_updates':1},
      'negative_full_agent':{'main_complete':False,'expected_protocol_rejection':True,'closed':True,'ordinary_committed':True,'registered_sources':0,'private_tasks':0,'extra_work_after_main_ordinary':{'rollout':0,'step':0,'transaction':0},'no_retry':True},
      'all7_raw_TD_R_L_I_checked':True,'future_or_utility_inference':False,'old_native_checker_bank_reruns':0,'keys_RNG_DP_calibration_formal_collection':0,'full_protocol_qualification':False}
    save(HERE/'stored_audit_result.json',output);save(out/'exit.json',{'complete':True,'result':meta(HERE/'stored_audit_result.json'),'completed_at_utc':datetime.now(timezone.utc).isoformat()});print(json.dumps(output,sort_keys=True))

if __name__=='__main__':main()
