"""New stdlib review of failure-only action trials; no old checker or RFL execution."""
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


def trial_spec(ev,alternative,rows):
    out=[]
    for i,x in enumerate(ev['steps']):
        st={k:x[k] for k in ('x','y','t','kappa','phi')};ctrl={k:x[k] for k in ('z','m')};cmd=alternative if i==len(ev['steps'])-1 else x['a_cmd'];q=state(st)+(ctrl['z'],ctrl['m'])
        out.append({'state':st,'control':ctrl,'command':cmd,'previously_realized':x['a_realized'],'admissible_rank':sorted(rows[q]).index(cmd)})
    return {'target_index':len(out)-1,'observed_failed_command':ev['steps'][-1]['a_cmd'],'alternative_command':alternative,'rows':out}


def actual_reach(spec,trace):
    row=spec['rows'][0];at={'x':0,'y':2,'t':0,'kappa':row['state']['kappa'],'phi':row['state']['phi']};ctrl={'z':trace['option_in_force'],'m':0}
    for i,w in enumerate(spec['rows']):
        if i>=len(trace['steps']):return {'reached':False,'reason':'ended_before_target','steps':i}
        s=trace['steps'][i]
        if (at,ctrl,s['a_cmd'])!=(w['state'],w['control'],w['command']):return {'reached':False,'reason':'planned_prefix_not_followed','steps':i}
        if i<spec['target_index'] and s['a_realized']!=w['previously_realized']:return {'reached':False,'reason':'earlier_realization_differs','steps':i}
        at=s['state'];ctrl=s['control']
    return {'reached':True,'reason':'actual_alternate_command_at_failed_context','steps':len(spec['rows'])}


def main():
    out=HERE/'evidence_audit';out.mkdir(exist_ok=False)
    def save(path,data):
        with path.open('x',encoding='utf-8',newline='\n') as f:json.dump(data,f,ensure_ascii=True,indent=2);f.write('\n')
    save(out/'claim.json',{'source':meta(Path(__file__)),'native':meta(HERE/'evidence/exit.json'),'automatic_retry':False,'started_at_utc':datetime.now(timezone.utc).isoformat()})
    c=load(HERE/'contract.json');claim=load(HERE/'evidence/claim.json');ex=load(HERE/'evidence/exit.json')
    assert ex['child_exit_code']==0 and ex['input_bytes_unchanged'] and claim['input_binding_before']==ex['input_binding_after']
    for path,pin in claim['input_binding_before'].items():assert meta(ROOT/path)==pin,path
    assert meta(HERE/'evidence/raw.jsonl')==ex['raw']
    for f in ('raw','exit','review'):
        cfg=c['ordinary_checkpoint'][f];assert meta(ROOT/cfg['path'])=={k:cfg[k] for k in ('bytes','sha256')}
    oldrs=[json.loads(s) for s in (ROOT/c['ordinary_checkpoint']['raw']['path']).read_text(encoding='ascii').splitlines()]
    oldprep=[r for r in oldrs if r['tag']=='PREPARATION_COMPLETE'];assert len(oldprep)==1;prep=oldprep[0]['payload']['state']
    for cfg in c['baseline_data'].values():assert meta(ROOT/cfg['path'])=={k:cfg[k] for k in ('bytes','sha256')}
    oldex=load(ROOT/c['baseline_data']['exit']['path']);oldcontract=load(ROOT/c['baseline_data']['contract']['path']);oldreport=load(ROOT/c['baseline_data']['result']['path'])
    assert oldex['child_exit_code']==1 and oldex['input_bytes_unchanged'] and oldreport['actual']['complete_main_receipts']==12 and not oldreport['actual']['investigating_roles_started']
    assert c['schedule']==oldcontract['schedule'][:2] and c['reference']==oldcontract['reference'] and c['ordinary_checkpoint']==oldcontract['ordinary_checkpoint']
    common=[name for name in claim['input_binding_before'] if name.startswith('src/') or name.endswith(('/learning.py','/td.py','/adaptive_training.py','/evidence_loop.py','/trial_agent.py','/strict_witness.py','/bound_agent.py','/checkpoint.py','/action_query.py','/probe_agent.py'))]
    for name in common:assert oldex['input_binding_after'][name]==claim['input_binding_before'][name],name
    rows={}
    for line in (ROOT/c['reference']['path']).read_text(encoding='utf-8').splitlines():
        if line.startswith('DECISION_CONTEXT='):
            q=json.loads(line.split('=',1)[1]);rows[tuple(q['context'])]={a:float.fromhex(v) for a,v in q['q_row_hex']}
    schedule=[s for s in c['schedule'] for _ in range(s['count'])];assert len(schedule)==12
    oldrs=[json.loads(line) for line in (ROOT/c['baseline_data']['raw']['path']).read_text(encoding='ascii').splitlines()]
    rs=[json.loads(line) for line in (HERE/'evidence/raw.jsonl').read_text(encoding='ascii').splitlines()]
    assert [r['seq'] for r in oldrs]==list(range(len(oldrs))) and [r['seq'] for r in rs]==list(range(len(rs)))
    combined=[('recorded_baseline',r) for r in oldrs]+[('new',r) for r in rs]
    tasks=defaultdict(list);posts=defaultdict(list);last={};details={};registrations={};source_ids={};issued={};consumed=set();queries={};ordinals=Counter();tags=Counter();summaries=[];accepted=[];query_reports=[]
    task=None;stack=[];batch=None;external=None;steps=ordinary=policyTX=ext=extpolicy=0;policy_by_arm=Counter();extpolicy_by_arm=Counter()
    def account(arm):
        return {'algorithm':arm,'trial_tasks_used':sum(len(v) for k,v in tasks.items() if k[0]=='private' and k[1]==arm),'trial_task_budget':0 if arm=='TaskTD' else c['trial_task_budget_each'],
            'base_queries':sum(a==arm for a,e in queries),'expanded_queries':0}
    for capture,r in combined:
        tag,p,ctx=r['tag'],r['payload'],r['context'];tags[tag]+=1;k=key(ctx);arm=ctx.get('arm');epoch=ctx.get('main_epoch')
        if tag=='REFERENCE':assert p['digest']==c['reference']['q_digest'] and p['rows']==len(rows)
        elif tag=='RECORDED_ORDINARY_MATERIALIZED':
            assert p['source_seq']==oldprep[0]['seq'] and p['source_raw_sha256']==c['ordinary_checkpoint']['raw']['sha256'] and p['recorded_payload']==prep
            assert all(p[f]==prep[f] for f in ('immediate','current','learning_values')) and p['native_delta']=={'rollout':0,'step':0,'transaction':3} and p['restored_issued_identities']==0
        elif tag=='SHARED_UNEDITED_SOURCE':assert p['state']==prep['current'] and p['values']==prep['learning_values'] and p['source_install_TX']==0;source=p['state']
        elif tag=='MAIN_INITIALIZED':
            q=p['state'];assert q['immediate']==q['current']==source and q['learning_values']==prep['learning_values'] and q['completed_episodes']==q['external_updates']==0 and q['attempted_epochs']==[]
            assert p['diagnostic_account']==account(arm);last[k]=q
        elif tag=='RUNNER_CONTEXT':assert p=={'epoch':epoch,'stage_audit_only':schedule[epoch]['label'],'kappa':schedule[epoch]['kappa'],'phi':schedule[epoch]['phi']} and epoch==len(tasks[k])
        elif tag=='FAILURE_QUERY_PLANNED':
            assert task is not None and ctx['phase']=='stream' and arm!='TaskTD' and p['evidence']==task['evidence'] and p['terminal']==task['raw']['trace']['outcome'] and p['post_TD']==task['ordinary']
            assert all(s['a_cmd']==s['a_realized'] for s in p['evidence']['steps'])
            t=p['evidence']['steps'][-1];q=tuple(t[f] for f in ('x','y','t','kappa','phi','z','m'));num=stores(task['ordinary']['learning_values']);R=stores(task['ordinary']['current'])
            vs={a:num['Q'].get(q+(a,),v) for a,v in rows[q].items()};alts=[a for a in vs if a!=t['a_cmd']];alternative=min(alts,key=lambda a:(-vs[a],a));spec=trial_spec(p['evidence'],alternative,rows)
            assert p['specification']==spec and p['greedy']==(arm=='GreedyPractice') and [(a,number(v)) for a,v in p['row_after_main_TD']]==list(vs.items())
            assert p['ordinary_selector_at_target']==R['D'].get(q,min(a for a,v in vs.items() if v==max(vs.values())))
            task['spec']=spec;task['query']=p
        elif tag=='OWNED_BRANCH_REGISTERED':
            assert task is not None and p['consumer']==task['ordinary'] and p['proposal']=={'action':'keep','edits':[]}
            reg=p['registration'];ordinals[arm]+=1;s=schedule[epoch]
            assert reg['ordinal']==ordinals[arm] and reg['main_epoch']==epoch and reg['origin_L']==task['ordinary']['learning_values'] and reg['kappa']==s['kappa'] and reg['phi']==s['phi'] and reg['source_I']==task['ordinary']['current'] and reg['proposal']==p['proposal']
            before=p['source_before'];assert before['immediate']==before['current']==reg['source_I'] and before['learning_values']==reg['origin_L'] and before['completed_episodes']==before['external_updates']==0
            registrations[reg['id']]={'payload':p,'key':k,'parent':task['key']};source_ids[k]=reg['id']
        elif tag=='PRIVATE_START':
            assert p['state']['immediate']==p['state']['current']==task['ordinary']['current'] and p['state']['learning_values']==task['ordinary']['learning_values'] and p['parent']==task['ordinary'] and p['n']==1 and p['action_trial_specification']==task['spec'] and p['greedy']==(arm=='GreedyPractice')
            last[k]=p['state'];details[k]={'spec':task['spec'],'greedy':p['greedy'],'plan_episodes':p['plan_episodes']}
        elif tag=='TASK_BEGIN':
            if ctx['phase']=='private':assert task is not None and task['key'][0]=='stream';stack.append(task)
            else:assert task is None
            e=len(tasks[k]);s=schedule[epoch];assert p['epoch']==e and p['before']['attempted_epochs']==list(range(e+1)) and all(p['before'][f]==last[k][f] for f in p['before'] if f!='attempted_epochs')
            coins=[(1<<64)-1]*12;chi=[[0] for _ in range(12)]
            if ctx['phase']=='private':
                cfg=details[k];assert e==0
                if not cfg['greedy']:
                    for i,w in enumerate(cfg['spec']['rows']):coins[i]=0;chi[i]=[w['admissible_rank']]
            else:assert e==epoch
            ep={'epoch':e,'kappa':s['kappa'],'proposal':1,'tape':{'phase':s['phi'],'error_flag':0,'cause_rank':12},'coins':coins,'rejections':chi}
            mask={'decision':None,'controller':None,'plant':None,'trap':s['trap']};assert p['episode']==ep and p['environment_mask_audit_only']==mask
            if ctx['phase']=='private':assert details[k]['plan_episodes']==[ep]
            task={'key':k,'epoch':e,'main_epoch':epoch,'before':p['before'],'episode':ep,'mask':mask,'diag':0,'tx':0,'writes':0,**(details[k] if ctx['phase']=='private' else {})}
        elif tag=='TASK_RAW':
            tr=p['trace'];assert task is not None and task['key']==k and tr['mask']==task['mask'] and tr['option_in_force']==1
            ep=task['episode'];kk,phi=ep['kappa'],ep['tape']['phase'];at=(0,2,0,kk,phi);z,m=1,0;R=stores(task['before']['current']);N=stores(task['before']['learning_values']);calls=[]
            assert len(p['draws'])==len(tr['steps']);open_cells={(0,2),(4,2),(1,1),(2,1),(3,1),(1,2),(2,2),(3,2),(1,3),(3,3),(1,4),(2,4),(3,4)};delta=((0,-1),(0,1),(-1,0),(1,0),(0,0));trap=task['mask']['trap']
            for i,(draw,x) in enumerate(zip(p['draws'],tr['steps'])):
                q=at+(z,m);vs={a:N['Q'].get(q+(a,),v) for a,v in rows[q].items()};greedy=R['D'].get(q,min(a for a,v in vs.items() if v==max(vs.values())));coin=ep['coins'][i];explore=coin==0;index=ep['rejections'][i][0]
                cmd=sorted(rows[q])[index%len(rows[q])] if explore else greedy;u=R['X'].get(at+(cmd,),cmd);real=u;calls.append([i,0,0,coin])
                if explore:calls.append([i,1,0,index])
                assert draw=={'i':i,'explore':explore,'admissible':sorted(rows[q]),'a_cmd':cmd} and x['a_cmd']==cmd and x['u']==u and x['a_realized']==real
                dx,dy=delta[real];cell=(at[0]+dx,at[1]+dy);cell=cell if cell in open_cells else at[:2];nt=at[2]+1;period=6 if kk==0 else 3
                outcome='COLLISION' if cell==(2,2) and nt%period==phi%period else 'TRAP' if list(cell)==trap['cell'] and at[2]==trap['t'] else 'SUCCESS' if cell==(4,2) else 'TIMEOUT' if nt>=12 else None
                st={'x':cell[0],'y':cell[1],'t':nt,'kappa':kk,'phi':phi};ctrl={'z':1,'m':1 if m or cell==(2,1) else 0};reward=-.02+(1.0 if outcome=='SUCCESS' else -1.0 if outcome else 0.0)
                assert x['state']==st and x['control']==ctrl and x['terminal']==(outcome is not None) and x['outcome']==outcome and not x['illegal'] and number(x['reward']).hex()==reward.hex()
                at=state(x['state']);z,m=x['control']['z'],x['control']['m']
            assert p['coordinates']==calls and tr['steps'][-1]['terminal'] and tr['outcome']==tr['steps'][-1]['outcome'] and p['return_hex']==return_value({'trace':tr}).hex()
            task['raw']={**p,'_episode':ep};steps+=len(tr['steps'])
        elif tag=='ORDINARY_UPDATE':
            pol=update(task['before'],task['raw'],p,rows,False);policyTX+=pol;policy_by_arm[arm]+=pol;ordinary+=1;task['ordinary']=p['after'];task['after']=p['after']
        elif tag=='DIAGNOSE_BEGIN':
            assert ctx['phase']=='stream' and arm!='TaskTD' and p['terminal']==task['raw']['trace']['outcome']!='SUCCESS' and p['evidence']==evidence(task['raw']['trace']) and p['state_before']==task['ordinary'];task['diag']+=1;task['evidence']=p['evidence']
        elif tag=='TRIAL_BUDGET_KEEP':assert p['main_epoch']==epoch and p['diagnostic_account']==account(arm) and account(arm)['trial_tasks_used']>=account(arm)['trial_task_budget']
        elif tag=='NO_ADMISSIBLE_ALTERNATIVE_KEEP':assert p['evidence']==task['evidence'] and len(rows[tuple(task['evidence']['steps'][-1][f] for f in ('x','y','t','kappa','phi','z','m'))])==1
        elif tag=='OUT_OF_SCOPE_MISMATCH_KEEP':assert p['evidence']==task['evidence'] and any(s['a_cmd']!=s['a_realized'] for s in p['evidence']['steps'])
        elif tag=='PRIVATE_COMPLETE':
            assert p['state']==last[k] and p['n']==len(tasks[k])==1 and number(p['return']).hex()==return_value(tasks[k][0]).hex() and p['actual_target_reach']==actual_reach(details[k]['spec'],tasks[k][0]['trace']) and p['observation_id']==source_ids[k]
        elif tag=='SELECTED_FAILURE_EXPERIENCE':
            assert p['observation_id']==source_ids['private',arm,epoch,'practice'] and p['proposal']=={'action':'keep','edits':[]}
            queries[arm,epoch]=task['query'];assert p['diagnostic_account']==account(arm)
            q=task['query'];query_reports.append({'arm':arm,'epoch':epoch,'stage':schedule[epoch]['label'],'target_index':q['specification']['target_index'],'failed_command':q['specification']['observed_failed_command'],'proposed_alternative':q['specification']['alternative_command'],'post_main_TD_selector':q['ordinary_selector_at_target'],'post_main_TD_already_avoids_failed_command':q['ordinary_selector_at_target']!=q['specification']['observed_failed_command']})
        elif tag=='DIAGNOSE_RETURN':assert p['proposal']=={'action':'keep','edits':[]}
        elif tag=='TASK_COMPLETE':
            assert p['trace']==task['raw']['trace'] and p['before']==task['before'] and p['ordinary_after']==task['ordinary'] and p['after']==task['after'] and p['terminal']==p['trace']['outcome']
            assert p['counters']=={'ordinary_updates':1,'diagnostic_calls':task['diag'],'query_calls':0,'diagnostic_transactions':0,'diagnostic_edit_addresses':0}
            if p['terminal']=='SUCCESS':assert task['diag']==0
            assert p['route']['write_spend']==0 and p['route']['diagnostic_calls']==task['diag'];tasks[k].append(p);details[k]=task;last[k]=p['after'];task=stack.pop() if stack else None
        elif tag=='OWNED_OBSERVATION_ISSUED':
            oid=p['observation_id'];reg=registrations[oid];assert reg['key']==k and len(tasks[k])==1 and p['trace']==tasks[k][0]['trace'] and p['episode']==details[k]['episode'] and p['source_epoch']==0 and p['main_epoch']==epoch and oid not in issued
            assert p['observation_revision']=='v153-experiment-witness-origin' and p['issuer_label']==last[k]['source_label'] and p['consumer_label']==reg['payload']['consumer']['source_label'];issued[oid]=p
        elif tag=='OWNED_BATCH_BEGIN':
            assert task is None and batch is None and external is None and p['before']==last[k] and p['all_consumed_before_TD']
            ids=[source_ids['private',arm,epoch,'practice']];assert [o['observation_id'] for o in p['observations']]==ids and p['ordinals']==[registrations[ids[0]]['payload']['registration']['ordinal']]
            for o in p['observations']:
                oid=o['observation_id'];assert issued[oid]==o and oid not in consumed and registrations[oid]['parent']==k and registrations[oid]['payload']['registration']['origin_L']==p['before']['learning_values']
            consumed.update(ids);batch={'before':p['before'],'ids':ids,'processed':[],'receipts':[]}
        elif tag=='OWNED_EXTERNAL_BEGIN':
            o=p['observation'];oid=o['observation_id'];reg=registrations[oid]
            assert task is None and external is None and batch is not None and oid==batch['ids'][len(batch['processed'])] and issued[oid]==o and oid in consumed and p['before']==last[k]
            assert not changes(reg['payload']['source_before']['immediate'],p['before']['current'],o) and p['external_update_index']==last[k]['external_updates'] and p['main_clock_advanced'] is False;external=p
        elif tag=='OWNED_EXTERNAL_END':
            o=external['observation'];oid=o['observation_id'];wanted={'applied':True,'reason':'same_mechanism_on_observed_path','observation_id':oid,'mechanism_changes':[]}
            assert p['observation_id']==oid and p['receipt']==wanted;pol=update(external['before'],{'trace':o['trace'],'_episode':o['episode']},p,rows,True);extpolicy+=pol;extpolicy_by_arm[arm]+=pol;ext+=1;last[k]=p['after']
            batch['processed'].append(oid);batch['receipts'].append(wanted);accepted.append({'arm':arm,'epoch':epoch,'terminal':o['trace']['outcome'],'numeric_content_changed':external['before']['learning_values']!=p['after']['learning_values']});external=None
        elif tag=='OWNED_BATCH_END':assert batch is not None and batch['processed']==batch['ids'] and p['before']==batch['before'] and p['after']==last[k] and p['receipts']==batch['receipts'];batch=None
        elif tag=='POST_OBSERVED_TASK':assert task is None and batch is None and p['epoch']==len(tasks[k])-1==epoch and p['state']==last[k] and p['diagnostic_account']==account(arm);posts[k].append(p['state'])
        elif tag=='AGENT_FINAL':
            ts=tasks[k];vals=[return_value(t) for t in ts];assert len(ts)==len(posts[k])==p['main_tasks']==12 and p['final_state']==last[k] and p['diagnostic_account']==account(arm)
            assert [number(v) for v in p['returns']]==vals and p['outcomes']==[t['terminal'] for t in ts] and p['successes']==sum(t['terminal']=='SUCCESS' for t in ts) and number(p['mean_return']).hex()==(sum(vals)/12).hex() and p['external_updates']==last[k]['external_updates'];summaries.append(p)
        elif tag=='FAILURE':
            assert capture=='recorded_baseline' and task is None and not stack and p['type']=='ValueError' and p['error']=='trap cell may not be START or GOAL (11 §6.6)' and p['counts']=={'rollout':12,'step':73,'transaction':15}
            assert len(tasks['stream','TaskTD',None,None])==12 and not any(k[0]=='private' for k in tasks)
            preserved_failure=p
        elif tag=='RESULT':assert capture=='new' and p['complete'] and p['streams']==summaries;result=p
        elif tag=='FINAL':
            assert p['profile_restored']
            if capture=='recorded_baseline':assert not p['complete'] and p['counts']==preserved_failure['counts'];oldfinal=p
            else:assert p['complete'];final=p
        else:raise AssertionError('unexpectedtag '+tag)
    assert task is None and external is None and batch is None and not stack and len(summaries)==2 and set(registrations)==set(issued)==consumed
    assert ordinary==sum(len(v) for v in tasks.values()) and ext==len(consumed)
    combined_counts={'rollout':ordinary,'step':steps,'transaction':6+ordinary+policyTX+ext+extpolicy}
    assert final['counts']==result['counts']=={k:combined_counts[k]-oldfinal['counts'][k] for k in combined_counts}
    phases=[];costs=[]
    for arm in ['TaskTD']+c['arms']:
        k=('stream',arm,None,None);ts=tasks[k];cursor=0
        assert all(x['immediate']==source and x['current']['P']==source['P'] and x['current']['X']==source['X'] for x in posts[k])
        for stage in c['schedule']:
            part=ts[cursor:cursor+stage['count']];vals=[return_value(t) for t in part];phases.append({'arm':arm,'stage':stage['label'],'successes':sum(t['terminal']=='SUCCESS' for t in part),'returns':vals,'mean_return':sum(vals)/len(vals),'private_tasks':sum(a==arm and cursor<=e<cursor+stage['count'] for a,e in queries)});cursor+=stage['count']
        native=[t for k_,v in tasks.items() if k_[1]==arm for t in v];extra=sum(x['arm']==arm for x in accepted)
        costs.append({'arm':arm,'main_tasks':12,'private_tasks':len(native)-12,'rollout':len(native),'step':sum(len(t['trace']['steps']) for t in native),'transaction':len(native)+policy_by_arm[arm]+extra+extpolicy_by_arm[arm],'shared3TX_excluded':True})
    equality=[]
    for e in range(12):
        raw=[tasks['stream',arm,None,None][e]['trace'] for arm in ['TaskTD']+c['arms']]
        fields=('immediate','current','learning_values','ordinary_PX_anchor')
        equality.append({'epoch':e,'all3_main_raw_equal':raw[0]==raw[1]==raw[2],'greedy_vs_targeted_post_RLI_equal':all(posts['stream','GreedyPractice',None,None][e][f]==posts['stream','TargetedPractice',None,None][e][f] for f in fields),'TaskTD_vs_greedy_post_RLI_equal':all(posts['stream','TaskTD',None,None][e][f]==posts['stream','GreedyPractice',None,None][e][f] for f in fields)})
    base=tasks['stream','TaskTD',None,None];baseline={'arm':'TaskTD','source':'v157 actual complete12 prefix; capture exit1/full18 notcomplete','successes':sum(t['terminal']=='SUCCESS' for t in base),'returns':[return_value(t) for t in base],'outcomes':[t['terminal'] for t in base],'mean_return':sum(return_value(t) for t in base)/12,'external_updates':0,'diagnostic_account':account('TaskTD')}
    compact=[{f:([number(v) for v in x[f]] if f=='returns' else number(x[f]) if f=='mean_return' else x[f]) for f in ('arm','successes','returns','outcomes','mean_return','external_updates','diagnostic_account')} for x in summaries]
    compact=[baseline]+compact
    tree=ast.parse((HERE.parent/'no_mismatch_failure_probe_v157/probe_agent.py').read_text());diag=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='_diagnose_visible')
    assert not ({'mask','case','stage','trap','plant','truth'} & {n.id for n in ast.walk(diag) if isinstance(n,ast.Name)})
    output={'schema':'V158_STDLIB_LEGAL_FAILURE_PROBE_COMPLETION_REVIEW','complete':True,'native_counts':final['counts'],'records':len(rs),'recorded_baseline_records':len(oldrs),'recorded_baseline_native_exit':1,'preserved_failure':preserved_failure,'combined_counts':combined_counts,'matched_common_source_pins':len(common),'input_pins':len(claim['input_binding_before']),
        'summaries':compact,'phase_results':phases,'online_costs':costs,'queries':query_reports,'accepted':accepted,'main_equality':equality,
        'combined_native_ordinary_updates':ordinary,'new_native_ordinary_updates':ordinary-12,'ordinary_policy_TX':policyTX,'external_ordinary_updates':ext,'external_policy_TX':extpolicy,'issued_observations':len(issued),'consumed_observations':len(consumed),
        'no_alternative_keeps':tags['NO_ADMISSIBLE_ALTERNATIVE_KEEP'],'budget_keeps':tags['TRIAL_BUDGET_KEEP'],'out_of_scope_keeps':tags['OUT_OF_SCOPE_MISMATCH_KEEP'],
        'feedback_TX':0,'source_install_TX':0,'success_diagnosis':0,'old_native_checker_bank_reruns':0,'new_keys_RNG_DP_calibration_collection':0,'formal_B1_or_science_qualification':False}
    save(HERE/'stored_audit_result.json',output);save(out/'exit.json',{'complete':True,'completed_at_utc':datetime.now(timezone.utc).isoformat(),'result':meta(HERE/'stored_audit_result.json')})
    print(json.dumps({'complete':True,'native_counts':final['counts'],'records':len(rs),'summaries':compact,'phases':phases,'costs':costs,'all_main_raw_equal':all(x['all3_main_raw_equal'] for x in equality)},sort_keys=True))

if __name__=='__main__':main()
