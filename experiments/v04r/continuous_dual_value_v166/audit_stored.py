"""New stdlib review: one mixed full-state agent, shared trial budget and both genuine feedback paths; no oldchecker/RFL execution."""
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




def episode_for(ev,prefix,rows):
    coins=[(1<<64)-1]*12;chi=[[0] for _ in range(12)]
    for i,x in enumerate(prefix['rows']):coins[i]=0;chi[i]=[x['admissible_rank']]
    return {'epoch':0,'kappa':ev['kappa'],'proposal':1,'tape':{'phase':ev['phi'],'error_flag':0,'cause_rank':12},'coins':coins,'rejections':chi}


def proof_for(obs,source_initial,origin_L,desired,rows):
    R,N=stores(source_initial),stores(origin_L);at=(0,2,0,desired['kappa'],desired['tape']['phase']);z,m=obs['trace']['option_in_force'],0;out=[];ok=True
    for i,x in enumerate(obs['trace']['steps']):
        q=at+(z,m);admissible=sorted(rows[q]);coin=desired['coins'][i];explore=coin*10<(1<<64)
        coords=[[i,0,0,coin]]
        if explore:
            lim=(1<<64)-((1<<64)%len(admissible));cmd=None
            for j,value in enumerate(desired['rejections'][i]):
                coords.append([i,1,j,value])
                if value<lim:cmd=admissible[value%len(admissible)];break
            assert cmd is not None
        else:
            values={a:N['Q'].get(q+(a,),v) for a,v in rows[q].items()};cmd=R['D'].get(q,min(a for a,v in values.items() if v==max(values.values())))
        out.append({'pre_state':dict(zip(('x','y','t','kappa','phi'),at)),'pre_control':{'z':z,'m':m},'actual_command':x['a_cmd'],'desired_command':cmd,'desired_explore':explore,'desired_coordinate_DATA':coords,'command_equal':cmd==x['a_cmd']})
        if cmd!=x['a_cmd']:ok=False;break
        at=state(x['state']);z,m=x['control']['z'],x['control']['m']
    return {'equivalent':ok,'reason':'same_commands_inductively_same_deterministic_terminal_outcome' if ok else 'desired_command_differs_on_actual_consumed_path',
        'bindings':{k:True for k in ('origin_R_equal','origin_L_equal','proposal_equal','same_current_complete_observation','reference_identity_equal','mode_role_equal','plan_protocol_equal')},
        'steps':out,'native_episode_input_equal':obs['episode']==desired}


def public_move(at,ctrl,cmd):
    cells={(0,2),(4,2),(1,1),(2,1),(3,1),(1,2),(2,2),(3,2),(1,3),(3,3),(1,4),(2,4),(3,4)}
    dx,dy=((0,-1),(0,1),(-1,0),(1,0),(0,0))[cmd];cell=(at['x']+dx,at['y']+dy)
    cell=cell if cell in cells else (at['x'],at['y'])
    nxt={**at,'x':cell[0],'y':cell[1],'t':at['t']+1};control={'z':ctrl['z'],'m':1 if ctrl['m'] or cell==(2,1) else 0}
    return nxt,control


def planned_probe(ev,rows,limit):
    last=ev['steps'][-1];pre={k:last[k] for k in ('x','y','t','kappa','phi')};target,_=public_move(pre,{'z':last['z'],'m':last['m']},last['a_realized'])
    expanded=0;exhausted=False;depth=len(ev['steps'])
    def walk(at,ctrl,path):
        nonlocal expanded,exhausted
        if len(path)==depth:
            if at==target and (path[-1]['state']['x'],path[-1]['state']['y']) not in ((pre['x'],pre['y']),(target['x'],target['y'])):return path
            return None
        q=state(at)+(ctrl['z'],ctrl['m'])
        for rank,cmd in enumerate(sorted(rows[q])):
            if expanded>=limit:exhausted=True;return None
            expanded+=1;nxt,nctrl=public_move(at,ctrl,cmd);period=6 if nxt['kappa']==0 else 3
            if (nxt['x'],nxt['y'])==(4,2) or ((nxt['x'],nxt['y'])==(2,2) and nxt['t']%period==nxt['phi']%period):continue
            found=walk(nxt,nctrl,path+[{'state':at,'control':ctrl,'command':cmd,'admissible_rank':rank}])
            if found is not None:return found
            if exhausted:return None
        return None
    found=walk({'x':0,'y':2,'t':0,'kappa':ev['kappa'],'phi':ev['phi']},{'z':ev['z_in_force'],'m':0},[])
    spec={'target':target,'observed_last_pre':pre,'observed_last_command':last['a_cmd'],'rows':found} if found else None
    search={'public_candidate_transitions':expanded,'target_inference_transitions':1,'search_exhausted':exhausted,'reason':'alternate_entry_found' if found else 'finite_transition_budget_exhausted' if exhausted else 'no_legal_alternate_entry'}
    return spec,search


def assess(spec,trace):
    at={'x':0,'y':2,'t':0,'kappa':spec['target']['kappa'],'phi':spec['target']['phi']};ctrl={'z':trace['option_in_force'],'m':0}
    for i,w in enumerate(spec['rows']):
        if i>=len(trace['steps']):return {'status':'untested','reason':'terminated_before_intended_arrival','checked_steps':i}
        s=trace['steps'][i]
        if (at,ctrl,s['a_cmd'])!=(w['state'],w['control'],w['command']):return {'status':'untested','reason':'planned_prefix_not_followed','checked_steps':i}
        at=s['state'];ctrl=s['control']
    last=trace['steps'][len(spec['rows'])-1]
    if at!=spec['target']:return {'status':'untested','reason':'different_actual_arrival','checked_steps':len(spec['rows'])}
    fail=last['terminal'] and last['outcome']=='TRAP'
    return {'status':'consistent_on_tested_alternate' if fail else 'refuted_on_tested_alternate','reason':'actual_target_TRAP' if fail else 'no_TRAP_at_actual_target','checked_steps':len(spec['rows'])}



def arrival_episode(ev,spec):
    coins=[(1<<64)-1]*12;chi=[[0] for _ in range(12)]
    for i,w in enumerate(spec['rows']):coins[i]=0;chi[i]=[w['admissible_rank']]
    return {'epoch':0,'kappa':ev['kappa'],'proposal':1,'tape':{'phase':ev['phi'],'error_flag':0,'cause_rank':12},'coins':coins,'rejections':chi}


def wire(x):
    if type(x) is float:return {'binary64_hex':x.hex()}
    if isinstance(x,(list,tuple)):return [wire(v) for v in x]
    if isinstance(x,dict):return {k:wire(v) for k,v in x.items()}
    return x

def projection(q):
    fields=('x','y','t','kappa','phi')
    factual=[tuple(s[k] for k in fields+('z','m','a_cmd')) for s in q['evidence']['steps']]
    planned=[tuple(w['state'][k] for k in fields)+(w['control']['z'],w['control']['m'],w['command']) for w in q['specification']['rows']]
    numeric=sorted((address(v['address'],'Q'),number(v['value'])) for v in q['post_TD']['learning_values']['Q'])
    decision=sorted((address(v['address'],'D'),v['value']) for v in q['post_TD']['current']['D'])
    return wire({'factual':factual,'planned':planned,'numeric':numeric,'decision':decision})

def features(data,rows):
    qvalues={tuple(q):number(v) for q,v in data['numeric']}
    def row(p):return {a:qvalues.get(tuple(p[:7])+(a,),v) for a,v in rows[tuple(p[:7])].items()}
    regrets=[max(row(p).values())-row(p)[p[7]] for p in data['planned']]
    i=next(i for i,(f,p) in enumerate(zip(data['factual'],data['planned'])) if f[7]!=p[7]);f,p=data['factual'][i],data['planned'][i]
    assert f[:7]==p[:7];values=row(p)
    gap=values[f[7]]-values[p[7]];policy={tuple(q):v for q,v in data['decision']};policy_regret=[]
    for p in data['planned']:
        values=row(p);greedy=min(a for a,v in values.items() if v==max(values.values()))
        policy_regret.append(max(values.values())-values[policy.get(tuple(p[:7]),greedy)])
    return max(regrets),gap,max(policy_regret)

def predict(model,x):
    assert len(x)==len(model['support'])
    if any(v<number(lo) or v>number(hi) for v,(lo,hi) in zip(x,model['support'])):return None
    node=model['root']
    while node['feature'] is not None:
        node=node['left'] if x[node['feature']]<=number(node['threshold']) else node['right']
    return number(node['value'])


def execution_projection(ev,before,after):
    keys=('x','y','t','kappa','phi','z','m','a_cmd','a_realized')
    numeric=lambda x:sorted((address(v['address'],'Q'),number(v['value'])) for v in x['Q'])
    return wire({'factual':[tuple(s[k] for k in keys) for s in ev['steps']],'before_numeric':numeric(before),'after_numeric':numeric(after)})

def execution_numbers(data,rows):
    changed=[s for s in data['factual'] if s[7]!=s[8]];assert changed
    q=tuple(changed[0][:8]);prior=rows[q[:7]][q[7]]
    old={tuple(k):number(v) for k,v in data['before_numeric']};new={tuple(k):number(v) for k,v in data['after_numeric']}
    return new.get(q,prior)-old.get(q,prior),float(len({tuple(s[:5])+(s[7],) for s in changed}))


def main():
    out=HERE/'evidence_audit';out.mkdir(exist_ok=False)
    def save(p,d):
        with p.open('x',encoding='utf-8',newline='\n') as f:json.dump(d,f,ensure_ascii=True,indent=2);f.write('\n')
    save(out/'claim.json',{'source':meta(Path(__file__)),'native':meta(HERE/'evidence/exit.json'),'automatic_retry':False,'started_at_utc':datetime.now(timezone.utc).isoformat()})
    c=load(HERE/'contract.json');claim=load(HERE/'evidence/claim.json');ex=load(HERE/'evidence/exit.json')
    assert ex['child_exit_code']==0 and ex['input_bytes_unchanged'] and claim['input_binding_before']==ex['input_binding_after']
    for path,pin in claim['input_binding_before'].items():assert meta(ROOT/path)==pin,path
    assert meta(HERE/'evidence/raw.jsonl')==ex['raw']
    for cfg in list(c['ordinary_checkpoint'].values()):
        if isinstance(cfg,dict) and 'path' in cfg:assert meta(ROOT/cfg['path'])=={k:cfg[k] for k in ('bytes','sha256')}
    oldrs=[json.loads(s) for s in (ROOT/c['ordinary_checkpoint']['raw']['path']).read_text(encoding='ascii').splitlines()]
    oldprep=[r for r in oldrs if r['tag']=='PREPARATION_COMPLETE'];assert len(oldprep)==1;prep=oldprep[0]['payload']['state']
    schedule=[{**s,'local_epoch':j} for s in c['schedule'] for j in range(s['count'])];assert len(schedule)==34
    rows={}
    for line in (ROOT/c['reference']['path']).read_text(encoding='utf-8').splitlines():
        if line.startswith('DECISION_CONTEXT='):
            p=json.loads(line.split('=',1)[1]);rows[tuple(p['context'])]={a:float.fromhex(v) for a,v in p['q_row_hex']}
    value_decisions=[];frozen=None
    for f in ('raw','exit','review'):
        cfg=c['recorded_models'][f];assert meta(ROOT/cfg['path'])=={k:cfg[k] for k in ('bytes','sha256')}
    assert load(ROOT/c['recorded_models']['exit']['path'])['child_exit_code']==0 and load(ROOT/c['recorded_models']['review']['path'])['complete']
    saved=[json.loads(s) for s in (ROOT/c['recorded_models']['raw']['path']).read_text(encoding='ascii').splitlines()];recorded=next(r for r in saved if r['tag']=='QUERY_VALUE_MODEL_FROZEN')
    execution_decisions=[];execution_frozen=None
    for name in ('raw','exit','review'):
        cfg=c['recorded_execution_model'][name];assert meta(ROOT/cfg['path'])=={k:cfg[k] for k in ('bytes','sha256')}
    assert load(ROOT/c['recorded_execution_model']['exit']['path'])['child_exit_code']==0 and load(ROOT/c['recorded_execution_model']['review']['path'])['complete']
    exec_rows=[json.loads(line) for line in (ROOT/c['recorded_execution_model']['raw']['path']).read_text(encoding='ascii').splitlines()];execution_record=next(r for r in exec_rows if r['tag']=='EXECUTION_MODEL_FROZEN')
    path_checks=[];negative_checks=[];aliases_by_epoch={};event_queries={};hypotheses=[];dispatches=[];public_edges=0
    rs=[json.loads(s) for s in (HERE/'evidence/raw.jsonl').read_text(encoding='ascii').splitlines()];assert [r['seq'] for r in rs]==list(range(len(rs)))
    tasks=defaultdict(list);post=defaultdict(list);last={};details={};registrations={};source_ids={};issued={};consumed=set();query={};expanded={};derived=[];private_specs={};accounts={};ordinals=Counter();tags=Counter();summaries=[];diagnoses=[];accepts=[];rejects=[]
    task=None;stack=[];batch=None;external=None;steps=ordinary=policyTX=ext=extpolicy=feedbackTX=privateTX=rejections=explorations=0
    def account(arm):
        return {'algorithm':arm,'trial_tasks_used':sum(len(ts) for key_,ts in tasks.items() if key_[0]=='private' and key_[1]==arm),
                'trial_task_budget':0 if arm=='TaskTD' else c['trial_task_budget_each_feedback_arm'],
                'base_queries':sum(a==arm for a,e in query)+sum(a==arm for a,e in event_queries),'expanded_queries':sum(a==arm for a,e in expanded)}
    def prop_for(name,parent):
        if name in ('keep','deep-keep','alternate-entry'):return {'action':'keep','edits':[]}
        return parent['joint'] if name=='joint' else parent['candidate']
    def edited(original,proposal):
        result=deepcopy(original);result['X']=[x for x in result['X'] if all(x['address']!=e['address'] for e in proposal['edits'])];return result
    for r in rs:
        tag,p,ctx=r['tag'],r['payload'],r['context'];tags[tag]+=1;k=key(ctx);arm=ctx.get('arm');epoch=ctx.get('main_epoch');name=ctx.get('candidate')
        if tag=='REFERENCE':assert p['digest']==c['reference']['q_digest'] and p['rows']==len(rows)
        elif tag=='RECORDED_ORDINARY_MATERIALIZED':
            assert p['source_seq']==oldprep[0]['seq'] and p['source_raw_sha256']==c['ordinary_checkpoint']['raw']['sha256'] and p['recorded_payload']==prep
            assert all(p[f]==prep[f] for f in ('immediate','current','learning_values')) and p['native_delta']=={'rollout':0,'step':0,'transaction':3} and p['restored_issued_identities']==0
        elif tag=='SHARED_SOURCE':
            assert p['before']==prep['current'] and p['values']==prep['learning_values'];expected=stores(prep['current'])
            for item in c['source_edits']:
                ch='D' if item['store']=='decision' else 'X';expected[ch][address(item['address'],ch)]=item['value']
            assert p['edits']==c['source_edits'] and maps_equal(stores(p['state']),expected);source=p['state']
        elif tag=='CURRENT_PATH_EQUIVALENCE':
            assert arm in ('UngatedUnified','EventOnlyGate','AllQueryGate') and task['dispatch']=='execution' and 'joint' in task
            desired=episode_for(task['trial_evidence'],prefix_from(task['trial_evidence'],rows),rows)
            assert p['desired_episodes']==[desired]
            assert p['desired_protocol']=={'parameters':{'alpha':{'rational':[1,2]},'epsilon':{'rational':[1,10]}},'sample':[{'kappa':schedule[epoch]['kappa'],'phase':schedule[epoch]['phi'],'error_flag':0,'cause_rank':12,'base_option':1}],'v_pre':{'binary64_hex':(.7642000000000008).hex()},'lock_digest':'v166-current-private'}
            ids=[source_ids['private',arm,epoch,n] for n in ('keep','first')];assert p['observation_ids']==ids
            wanted=[]
            for oid in ids:
                reg=registrations[oid];w=proof_for(issued[oid],reg['payload']['source_before']['immediate'],reg['payload']['registration']['origin_L'],desired,rows)
                w['original_coordinate_calls']=details[reg['key']]['raw']['coordinates'];wanted.append(w)
            assert p['proofs']==wanted and p['reuse']==all(x['equivalent'] for x in wanted)
            aliases_by_epoch[arm,epoch]={'deep-keep':'keep','deep-first':'first'} if p['reuse'] else {}
            path_checks.append({'arm':arm,'epoch':epoch,'stage':schedule[epoch]['label'],**p})
        elif tag=='CONSUMED_COMMAND_CHANGE_REJECTED':
            assert epoch==0 and arm in ('UngatedUnified','EventOnlyGate','AllQueryGate')
            desired=episode_for(task['trial_evidence'],prefix_from(task['trial_evidence'],rows),rows);desired['rejections'][0]=[0]
            oid=source_ids['private',arm,epoch,'keep'];reg=registrations[oid]
            w=proof_for(issued[oid],reg['payload']['source_before']['immediate'],reg['payload']['registration']['origin_L'],desired,rows);w['original_coordinate_calls']=details[reg['key']]['raw']['coordinates']
            assert p['observation_id']==oid and p['desired_episodes']==[desired] and p['proof']==w and not w['equivalent']
            negative_checks.append(p)
        elif tag=='RECORDED_QUERY_MODELS':
            assert frozen is None and not tasks and p['source_seq']==recorded['seq'] and p['source_raw_sha256']==c['recorded_models']['raw']['sha256']
            assert p['frozen_parameters']==recorded['payload'] and p['materialized_models']==recorded['payload']['models'] and p['new_fit_calls']==p['restored_issued_identities']==0
            frozen=p['frozen_parameters']
        elif tag=='QUERY_VALUE_DECISION':
            assert arm in ('EventOnlyGate','AllQueryGate') and task['dispatch']=='event' and task['event_spec'] is not None
            q=task['event_query'];data=projection(q);x=features(data,rows);model=frozen['models']['policy'];pred=predict(model,x)
            decision='unknown_probe' if pred is None else 'supported_probe' if pred>0 else 'supported_skip'
            assert p['feature_data']==data and p['x']==wire(x) and p['model']==model and p['predicted_gain_per_paid_probe']==wire(pred) and p['decision']==decision
            assert p['post_TD']==task['ordinary'] and p['diagnostic_account']==account(arm)
            task['value_decision']=decision;value_decisions.append({'arm':arm,'epoch':epoch,'stage':schedule[epoch]['label'],'x':x,'prediction':pred,'decision':decision,'trial_tasks_used_before':account(arm)['trial_tasks_used']})
        elif tag=='RECORDED_EXECUTION_MODEL':
            assert execution_frozen is None and not tasks and p['source_seq']==execution_record['seq'] and p['source_raw_sha256']==c['recorded_execution_model']['raw']['sha256']
            assert p['frozen_parameters']==execution_record['payload'] and p['materialized_model']==execution_record['payload']['model'] and p['new_fit_calls']==p['restored_issued_identities']==0
            execution_frozen=p['frozen_parameters']
        elif tag=='EXECUTION_VALUE_DECISION':
            assert arm=='AllQueryGate' and task is not None and proposal(task['evidence']) is not None
            data=execution_projection(task['evidence'],task['before']['learning_values'],task['ordinary']['learning_values']);x=execution_numbers(data,rows);model=execution_frozen['model'];pred=predict(model,x)
            decision='unknown_probe' if pred is None else 'supported_probe' if pred>0 else 'supported_skip'
            assert p['feature_data']==data and p['x']==wire(x) and p['model']==model and p['predicted_gain_per_paid_probe']==wire(pred) and p['decision']==decision
            assert p['post_TD']==task['ordinary'] and p['diagnostic_account']==account(arm)
            task['execution_gate']=decision;execution_decisions.append({'arm':arm,'epoch':epoch,'stage':schedule[epoch]['label'],'x':x,'prediction':pred,'decision':decision,'trial_tasks_used_before':account(arm)['trial_tasks_used']})
        elif tag=='MAIN_INITIALIZED':
            q=p['state'];assert q['immediate']==q['current']==source and q['learning_values']==prep['learning_values'] and q['completed_episodes']==q['external_updates']==0 and q['attempted_epochs']==[] and q['experience_revision']=='v153-experimental-evidence-batch'
            assert p['diagnostic_account']==account(arm)
            assert p['configuration']=={'revision':'v165-learned-execution-query','event_enabled':arm!='TaskTD','value_gate_enabled':arm in ('EventOnlyGate','AllQueryGate'),'query_value_model':frozen['models']['policy'],'trial_budget_shared':0 if arm=='TaskTD' else 6,'feedback_address_limit':0 if arm=='TaskTD' else 2,'execution_value_model':execution_frozen['model'],'execution_gate_enabled':arm=='AllQueryGate','mro':['ExecutionQueryAgent','PolicyQueryAgent','UnifiedFeedbackAgent','PathwiseAgent','CurrentPathProof','EventHypothesisAgent','StrictTrialDerivedAgent','StrictWitnessLoop','TrialDerivedAgent','EvidenceExperienceLoop','ObservationTaskLoop','CoordinateLearner','object']}
            last[k]=q
        elif tag=='RUNNER_CONTEXT':
            s=schedule[epoch];assert p=={'epoch':epoch,'stage_audit_only':s['label'],'kappa':s['kappa'],'phi':s['phi']} and epoch==len(tasks[k])
        elif tag=='OWNED_BRANCH_EDIT':
            proposal_=prop_for(name,task);assert proposal_['edits'] and p['before']==task['ordinary']['current'] and p['edits']==proposal_['edits'] and p['after']==edited(p['before'],proposal_);privateTX+=1
        elif tag=='OWNED_BRANCH_REGISTERED':
            proposal_=prop_for(name,task);assert task.get('execution_gate')!='supported_skip' and task.get('value_decision')!='supported_skip' and p['consumer']==task['ordinary'] and p['proposal']==proposal_
            reg=p['registration'];ordinals[arm]+=1;expected=edited(task['ordinary']['current'],proposal_);stage=schedule[epoch]
            assert reg['ordinal']==ordinals[arm] and reg['main_epoch']==epoch and reg['origin_L']==task['ordinary']['learning_values'] and reg['kappa']==stage['kappa'] and reg['phi']==stage['phi'] and reg['source_I']==expected and reg['proposal']==proposal_
            assert p['source_before']['immediate']==p['source_before']['current']==expected and p['source_before']['learning_values']==reg['origin_L'] and p['source_before']['completed_episodes']==p['source_before']['external_updates']==0
            registrations[reg['id']]={'payload':p,'key':k,'parent':task['key']};source_ids[k]=reg['id']
        elif tag=='PRIVATE_START':
            proposal_=prop_for(name,task);expected=edited(task['ordinary']['current'],proposal_)
            assert p['parent']==task['ordinary'] and p['state']['immediate']==p['state']['current']==expected and p['state']['learning_values']==task['ordinary']['learning_values'] and p['n']==1
            if task['dispatch']=='execution':
                view=task['trial_evidence'] if name.startswith('deep-') or name=='joint' else task['evidence'];prefix=prefix_from(view,rows)
                assert p['probe_prefix']==prefix and not p['greedy'] and p['plan_episodes']==[episode_for(view,prefix,rows)]
                private_specs[k]={'n':1,'prefix':prefix,'greedy':False,'dispatch':'execution'}
            else:
                assert name=='alternate-entry' and p['arrival_specification']==task['event_spec'] and p['plan_episodes']==[arrival_episode(task['evidence'],task['event_spec'])]
                private_specs[k]={'n':1,'arrival_specification':task['event_spec'],'dispatch':'event'}
            last[k]=p['state']
        elif tag=='TASK_BEGIN':
            if ctx['phase']=='private':assert task is not None and task['key'][0]=='stream';stack.append(task)
            else:assert task is None
            e=len(tasks[k]);s=schedule[epoch];assert p['epoch']==e and p['before']['attempted_epochs']==list(range(e+1))
            assert all(p['before'][f]==last[k][f] for f in p['before'] if f!='attempted_epochs')
            if ctx['phase']=='private':
                cfg=private_specs[k];assert e==0
                ep=episode_for({'kappa':s['kappa'],'phi':s['phi']},cfg['prefix'],rows) if cfg['dispatch']=='execution' else arrival_episode({'kappa':s['kappa'],'phi':s['phi']},cfg['arrival_specification'])
            else:
                assert e==epoch
                coins=[(1<<64)-1]*12
                if s['force_start_right_at_local_epoch'] is not None and s['local_epoch']==s['force_start_right_at_local_epoch']:coins[0]=0
                ep={'epoch':e,'kappa':s['kappa'],'proposal':1,'tape':{'phase':s['phi'],'error_flag':0,'cause_rank':12},'coins':coins,'rejections':[[0]]*12}
            mask={'decision':None,'controller':None,'plant':None,'trap':s['trap']};assert p['episode']==ep and p['environment_mask_audit_only']==mask
            task={'key':k,'epoch':e,'main_epoch':epoch,'before':p['before'],'episode':ep,'mask':mask,'diag':0,'tx':0,'writes':0}
        elif tag=='TASK_RAW':
            tr=p['trace'];assert task is not None and task['key']==k and tr['mask']==task['mask'] and tr['option_in_force']==1
            ep=task['episode'];kk,phi=ep['kappa'],ep['tape']['phase'];at=(0,2,0,kk,phi);z,m=1,0;cur=stores(task['before']['current']);num=stores(task['before']['learning_values']);calls=[]
            assert len(p['draws'])==len(tr['steps']);open_cells={(0,2),(4,2),(1,1),(2,1),(3,1),(1,2),(2,2),(3,2),(1,3),(3,3),(1,4),(2,4),(3,4)};deltas=((0,-1),(0,1),(-1,0),(1,0),(0,0));trap=task['mask']['trap']
            for i,(draw,x) in enumerate(zip(p['draws'],tr['steps'])):
                q=at+(z,m);vs={a:num['Q'].get(q+(a,),v) for a,v in rows[q].items()};greedy=cur['D'].get(q,min(a for a,v in vs.items() if v==max(vs.values())))
                coin=ep['coins'][i];explore=coin==0;index=ep['rejections'][i][0];cmd=sorted(rows[q])[index%len(rows[q])] if explore else greedy;u=cur['X'].get(at+(cmd,),cmd);plant=task['mask']['plant'];real=plant['realized'] if plant and at[2]==plant['t'] else u;calls.append([i,0,0,coin])
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
            assert p['main_epoch']==epoch and p['diagnostic_account']==account(arm) and p['diagnostic_account']['trial_tasks_used']+(1 if task['dispatch']=='event' else 2)>p['diagnostic_account']['trial_task_budget'];task['fast_keep']='budget'
        elif tag=='DIAGNOSTIC_DISPATCH':
            mismatch=proposal(task['evidence']) is not None
            branch='execution' if mismatch else 'event' if arm!='TaskTD' and task['raw']['trace']['outcome']=='TRAP' else 'keep'
            assert p['branch']==branch and p['visible_mismatch']==mismatch and p['terminal']==task['raw']['trace']['outcome'] and p['post_TD']==task['ordinary'] and p['diagnostic_account']==account(arm)
            task['dispatch']=branch;dispatches.append({'arm':arm,'epoch':epoch,'stage':schedule[epoch]['label'],'branch':branch,'trial_tasks_used_before':account(arm)['trial_tasks_used']})
        elif tag=='ARRIVAL_HYPOTHESIS_PROPOSED':
            assert arm!='TaskTD' and task['dispatch']=='event' and p['evidence']==task['evidence'] and p['post_TD']==task['ordinary'] and p['terminal']=='TRAP'
            spec,search=planned_probe(p['evidence'],rows,c['public_transitions_per_proposal']);assert p['specification']==spec and p['public_search']==search
            task['event_spec']=spec;task['event_query']=p;public_edges+=search['public_candidate_transitions']+1
            hypotheses.append({'arm':arm,'epoch':epoch,'stage':schedule[epoch]['label'],'specification':spec,'public_search':search})
        elif tag=='SELECTED_EVENT_EXPERIENCE':
            assert task['dispatch']=='event' and p['observation_id']==source_ids['private',arm,epoch,'alternate-entry'] and p['proposal']=={'action':'keep','edits':[]}
            event_queries[arm,epoch]=task['event_query'];assert p['diagnostic_account']==account(arm)
        elif tag=='DIAGNOSTIC_INPUT':
            assert p['evidence']==task['evidence'] and p['post_TD']==task['ordinary'] and p['candidate']==proposal(task['evidence']) and p['prefix']==prefix_from(task['evidence'],rows)
            task['candidate']=p['candidate'];task['prefix']=p['prefix'];assert p['horizon']==(3 if arm=='HorizonSingle' else 1)
        elif tag=='TASK_COMPLETE':
            assert p['trace']==task['raw']['trace'] and p['before']==task['before'] and p['ordinary_after']==task['ordinary'] and p['after']==task['after'] and p['terminal']==p['trace']['outcome']
            assert p['counters']=={'ordinary_updates':1,'diagnostic_calls':task['diag'],'query_calls':0,'diagnostic_transactions':task['tx'],'diagnostic_edit_addresses':task['writes']}
            if p['terminal']=='SUCCESS':assert task['diag']==task['tx']==task['writes']==0
            assert p['route']['write_spend']==task['writes'] and p['route']['diagnostic_calls']==task['diag'];tasks[k].append(p);details[k]=task;last[k]=p['after'];task=stack.pop() if stack else None
        elif tag=='OWNED_OBSERVATION_ISSUED':
            reg=registrations[p['observation_id']];assert reg['key']==k and len(tasks[k])==1 and p['trace']==tasks[k][0]['trace'] and p['episode']==details[k]['episode'] and p['source_epoch']==0 and p['main_epoch']==epoch and p['observation_id'] not in issued
            assert p['observation_revision']=='v153-experiment-witness-origin' and p['issuer_label']==last[k]['source_label'] and p['consumer_label']==reg['payload']['consumer']['source_label'];issued[p['observation_id']]=p
        elif tag=='PRIVATE_COMPLETE':
            cfg=private_specs[k];assert p['state']==last[k] and p['n']==len(tasks[k])==cfg['n'] and p['observation_id']==source_ids[k]
            if cfg['dispatch']=='execution':assert [number(v) for v in p['returns']]==[return_value(t) for t in tasks[k]] and p['first_task_target_reach']==reach(cfg['prefix'],tasks[k][0]['trace'])
            else:
                assert number(p['return']).hex()==return_value(tasks[k][0]).hex() and p['hypothesis_assessment']==assess(cfg['arrival_specification'],tasks[k][0]['trace'])
                next(h for h in hypotheses if h['epoch']==epoch and h['arm']==arm)['assessment']=p['hypothesis_assessment']
        elif tag=='TRIAL_DERIVED_PROPOSAL':
            witness=p['witness'];oid=witness['observation_id'];reg=registrations[oid];actual=issued[oid]
            assert arm in c['arms'] and actual==witness and reg['key']==('private',arm,epoch,'first') and witness['trace']['outcome']!='SUCCESS' and p['parent_proposal']==task['candidate']==reg['payload']['proposal'] and p['main_post_TD']==task['ordinary']
            ev=evidence(witness['trace']);extra=proposal(ev);assert p['evidence']==ev and extra is not None and extra['edits'][0]['address']!=task['candidate']['edits'][0]['address']
            wanted={'action':'apply','edits':task['candidate']['edits']+extra['edits']};assert p['proposal']==wanted
            task['joint']=wanted;task['trial_evidence']=ev;derived.append({'arm':arm,'epoch':epoch,'stage':schedule[epoch]['label'],'proposal':wanted,'witness_id':oid,
                 'new_site_in_original_main':any(x['address']==extra['edits'][0]['address'] for x in (proposal(task['evidence']) or {'edits':[]})['edits'])})
        elif tag=='TRIAL_EXTENSION_UNAVAILABLE':
            oid=p['observation']['observation_id'];assert p['observation']==issued[oid] and p['reason']=='no_fresh_visible_mismatch'
            extra=proposal(evidence(p['observation']['trace']));assert extra is None or extra['edits'][0]['address'] in [e['address'] for e in task['candidate']['edits']]
        elif tag in ('BASE_MENU_VALUE','EXPANDED_MENU_VALUE'):
            isdeep=tag=='EXPANDED_MENU_VALUE';names=('deep-keep','deep-first','joint') if isdeep else ('keep','first');n=1 if isdeep or arm!='HorizonSingle' else 3
            aliases=aliases_by_epoch.get((arm,epoch),{}) if isdeep else {}
            if isdeep:assert p['live_aliases']==aliases
            menu={name:prop_for(name,task) for name in names};actual={name:[return_value(t) for t in tasks[('private',arm,epoch,aliases.get(name,name))]] for name in names};means={name:sum(v)/len(v) for name,v in actual.items()}
            wanted=min(menu,key=lambda name:(-means[name],len(menu[name]['edits']),name));assert p['menu']==menu and plain(p['observed'])==actual and plain(p['values'])==means and p['choice']==wanted and p['horizon']==n
            item={'arm':arm,'epoch':epoch,'stage':schedule[epoch]['label'],'observed':actual,'values':means,'choice':wanted,'proposal':menu[wanted],'horizon':n}
            if isdeep:
                assert (arm,epoch) in query and 'joint' in task;expanded[arm,epoch]=item
                assert all(next(x for x in path_checks if x['arm']==arm and x['epoch']==epoch)['proofs'][i]['equivalent'] for i in (0,1)) if aliases else all(details['private',arm,epoch,n]['episode']==details['private',arm,epoch,'joint']['episode'] for n in ('deep-keep','deep-first'))
            else:query[arm,epoch]=item
            assert p['diagnostic_account']==account(arm)
        elif tag=='EXPANSION_BUDGET_KEEP_BASE':
            assert p['joint_proposal']==task['joint'] and p['diagnostic_account']==account(arm) and account(arm)['trial_tasks_used']+(1 if aliases_by_epoch.get((arm,epoch)) else 3)>account(arm)['trial_task_budget']
        elif tag=='SELECTED_FEEDBACK':
            item=expanded.get((arm,epoch),query[arm,epoch]);assert p['proposal']==item['proposal'] and p['choice']==item['choice'] and p['target_index']==task['prefix']['target_index'] and p['diagnostic_account']==account(arm)
            task['proposal']=p['proposal']
        elif tag=='DIAGNOSE_RETURN':assert p['proposal']==task.get('proposal',{'action':'keep','edits':[]})
        elif tag=='DIAGNOSTIC_TX_BEGIN':assert p['before']==task['ordinary'] and p['edits']==task['proposal']['edits']
        elif tag=='DIAGNOSTIC_TX_END':
            expected=deepcopy(task['ordinary']);expected['current']=edited(expected['current'],task['proposal']);expected['ordinary_PX_anchor']={f:expected['current'][f] for f in ('P','X')}
            assert p['after']==expected;task['after']=p['after'];task['tx']=1;task['writes']=len(task['proposal']['edits']);feedbackTX+=1
        elif tag=='OWNED_BATCH_BEGIN':
            assert arm!='TaskTD' and task is None and external is None and batch is None and p['before']==last[k] and p['all_consumed_before_TD']
            wanted_names=('alternate-entry',) if (arm,epoch) in event_queries else ('deep-keep','deep-first','joint') if (arm,epoch) in expanded else ('keep','first');aliases=aliases_by_epoch.get((arm,epoch),{});ids=[source_ids['private',arm,epoch,aliases.get(n,n)] for n in wanted_names]
            assert [o['observation_id'] for o in p['observations']]==ids and p['ordinals']==[registrations[i]['payload']['registration']['ordinal'] for i in ids]
            for o in p['observations']:
                oid=o['observation_id'];reg=registrations[oid];assert issued[oid]==o and oid not in consumed and reg['parent']==k and reg['payload']['registration']['origin_L']==p['before']['learning_values']
            consumed.update(ids);batch={'before':p['before'],'ids':ids,'processed':[],'receipts':[]}
        elif tag=='OWNED_OBSERVATION_REJECTED':
            o=p['observation'];oid=o['observation_id'];reg=registrations[oid];diff=changes(reg['payload']['source_before']['immediate'],last[k]['current'],o);wanted={'applied':False,'reason':'current_mechanism_differs_on_observed_path','observation_id':oid,'mechanism_changes':diff}
            assert batch is not None and oid==batch['ids'][len(batch['processed'])] and issued[oid]==o and diff and p['before']==p['after']==last[k] and oid in consumed and p['receipt']==wanted
            batch['processed'].append(oid);batch['receipts'].append(wanted);rejections+=1;rejects.append({'arm':arm,'epoch':epoch,'stage':schedule[epoch]['label'],'candidate':reg['key'][3],'terminal':o['trace']['outcome'],'mechanism_changes':diff})
        elif tag=='OWNED_EXTERNAL_BEGIN':
            o=p['observation'];oid=o['observation_id'];reg=registrations[oid];assert task is None and external is None and batch is not None and oid==batch['ids'][len(batch['processed'])] and issued[oid]==o and oid in consumed and p['before']==last[k]
            assert not changes(reg['payload']['source_before']['immediate'],p['before']['current'],o) and p['external_update_index']==last[k]['external_updates'] and p['main_clock_advanced'] is False;external=p
        elif tag=='OWNED_EXTERNAL_END':
            o=external['observation'];oid=o['observation_id'];wanted={'applied':True,'reason':'same_mechanism_on_observed_path','observation_id':oid,'mechanism_changes':[]}
            assert p['observation_id']==oid and p['receipt']==wanted;extpolicy+=update(external['before'],{'trace':o['trace'],'_episode':o['episode']},p,rows,True);ext+=1;last[k]=p['after']
            batch['processed'].append(oid);batch['receipts'].append(wanted);accepts.append({'arm':arm,'epoch':epoch,'stage':schedule[epoch]['label'],'candidate':registrations[oid]['key'][3],'terminal':o['trace']['outcome'],'numeric_content_changed':external['before']['learning_values']!=p['after']['learning_values']});external=None
        elif tag=='OWNED_BATCH_END':
            assert batch is not None and batch['processed']==batch['ids'] and p['before']==batch['before'] and p['after']==last[k] and p['receipts']==batch['receipts'];batch=None
        elif tag=='POST_OBSERVED_TASK':
            assert task is None and batch is None and p['epoch']==len(tasks[k])-1==epoch and p['state']==last[k] and p['diagnostic_account']==account(arm);post[k].append(p['state'])
        elif tag=='AGENT_FINAL':
            ts=tasks[k];vals=[return_value(t) for t in ts];assert p['main_tasks']==len(ts)==len(post[k])==34 and p['final_state']==last[k] and p['diagnostic_account']==account(arm)
            assert [number(v) for v in p['returns']]==vals and p['outcomes']==[t['terminal'] for t in ts] and p['successes']==sum(t['terminal']=='SUCCESS' for t in ts) and number(p['mean_return']).hex()==(sum(vals)/34).hex() and p['external_updates']==last[k]['external_updates'];summaries.append(p)
        elif tag=='RESULT':assert p['complete'] and p['streams']==summaries;result=p
        elif tag=='FINAL':assert p['complete'] and p['profile_restored'];final=p
        else:raise AssertionError('unexpectedtag '+tag)
    assert task is None and external is None and batch is None and not stack and len(summaries)==4 and set(registrations)==set(issued)
    assert ordinary==sum(len(ts) for ts in tasks.values()) and ext+rejections==len(consumed)
    expected={'rollout':ordinary,'step':steps,'transaction':4+ordinary+policyTX+ext+extpolicy+feedbackTX+privateTX}
    if public_edges:expected['public_geometry']=public_edges
    if value_decisions:expected['query_features']=len(value_decisions)
    if execution_decisions:expected['execution_features']=len(execution_decisions)
    assert final['counts']==result['counts']==expected
    phases=[];costs=[];preservation=[];main_write_addresses=[]
    for arm in c['arms']:
        k=('stream',arm,None,None);ts=tasks[k];cursor=0
        for stage in c['schedule']:
            part=ts[cursor:cursor+stage['count']];vals=[return_value(t) for t in part];phases.append({'arm':arm,'stage':stage['label'],'start_epoch':cursor,'tasks':len(part),'successes':sum(t['terminal']=='SUCCESS' for t in part),'returns':vals,'mean_return':sum(vals)/len(vals),'base_query_epochs':[e for a,e in query if a==arm and cursor<=e<cursor+stage['count']],'expanded_query_epochs':[e for a,e in expanded if a==arm and cursor<=e<cursor+stage['count']]});cursor+=stage['count']
        native=[t for key_,v in tasks.items() if key_[1]==arm for t in v];accept_count=sum(x['arm']==arm for x in accepts)
        private_tx=sum(r['tag']=='OWNED_BRANCH_EDIT' and r['context'].get('arm')==arm for r in rs)
        costs.append({'arm':arm,'main_tasks':34,'private_tasks':len(native)-34,'rollout':len(native),'step':sum(len(t['trace']['steps']) for t in native),'transaction':len(native)+sum(bool(r['payload']['policy_edits']) for r in rs if r['context'].get('arm')==arm and r['tag']=='ORDINARY_UPDATE')+private_tx+sum(t['counters']['diagnostic_transactions'] for t in ts)+accept_count+sum(bool(r['payload']['policy_edits']) for r in rs if r['context'].get('arm')==arm and r['tag']=='OWNED_EXTERNAL_END'),'shared4TX_excluded':True})
        sentinel=(3,4,10,1,5,4);assert all(p['immediate']==source and stores(p['current'])['X'][sentinel]==0 and p['current']['P']==source['P'] for p in post[k])
        preservation.append({'arm':arm,'all34_I_preserved':True,'unread_sentinel_preserved':True,'phase_boundary_resets':0})
        assert account(arm)['trial_tasks_used']<=account(arm)['trial_task_budget']
        for e,t in enumerate(ts):
            if t['counters']['diagnostic_transactions']:main_write_addresses.append({'arm':arm,'epoch':e,'addresses':t['counters']['diagnostic_edit_addresses'],'atomic_TX':t['counters']['diagnostic_transactions']})
    for cost in costs:cost['public_geometry']=sum(x['public_search']['public_candidate_transitions']+1 for x in hypotheses if x['arm']==cost['arm'])
    assert len(negative_checks)==3
    assert len(value_decisions)==sum(1 for r in rs if r['tag']=='QUERY_VALUE_DECISION')
    for decision in value_decisions:
        assert ((decision['arm'],decision['epoch']) in event_queries)==(decision['decision']!='supported_skip')
    preservation=[]
    for arm in c['arms']:
        k=('stream',arm,None,None);ts=tasks[k]
        assert all(p['immediate']==source and stores(p['current'])['X'][(3,4,10,1,5,4)]==0 and stores(p['current'])['X'][(0,2,0,1,0,3)]==4 for p in post[k])
        challenge=ts[5]['trace']['steps'][0];assert challenge['a_cmd']==3 and challenge['a_realized']==4
        preservation.append({'arm':arm,'all34_I_preserved':True,'protective_X_retained':True,'unread_sentinel_retained':True,'forced_RIGHT_realized_WAIT_at_global5':True,'phase_resets':0,'single_current_state':True})
    compact=[{f:([number(v) for v in x[f]] if f=='returns' else number(x[f]) if f=='mean_return' else x[f]) for f in ('arm','successes','returns','outcomes','mean_return','external_updates','diagnostic_account')} for x in summaries]
    for d in execution_decisions:
        if d['decision']=='supported_skip':assert (d['arm'],d['epoch']) not in query
    tree=ast.parse((HERE.parent/'learned_execution_value_v165/execution_agent.py').read_text());policy=next(n for n in tree.body if isinstance(n,ast.ClassDef));diag=next(n for n in policy.body if isinstance(n,ast.FunctionDef) and n.name=='_diagnose_visible');assert not ({'mask','case','stage'} & {n.id for n in ast.walk(diag) if isinstance(n,ast.Name)})
    output={'schema':'V166_STDLIB_CONTINUOUS_DUAL_VALUE_REVIEW','complete':True,'native_counts':final['counts'],'records':len(rs),'input_pins':len(claim['input_binding_before']),
        'summaries':compact,'execution_value_decisions':execution_decisions,'execution_model_record':{'sha256':c['recorded_execution_model']['raw']['sha256'],'new_native_fits':0,'parameters_exact':True},'query_value_decisions':value_decisions,'recorded_model_pair':{'raw_sha256':c['recorded_models']['raw']['sha256'],'new_native_fits':0,'parameters_exact':True},'dispatches':dispatches,'event_hypotheses':hypotheses,'path_checks':path_checks,'negative_checks':negative_checks,'phase_results':phases,'online_costs':costs,'base_queries':list(query.values()),'expanded_queries':list(expanded.values()),'derived_hypotheses':derived,'diagnoses':diagnoses,'accepted':accepts,'rejected':rejects,'preservation':preservation,'main_write_addresses':main_write_addresses,
        'native_ordinary_updates':ordinary,'ordinary_policy_TX':policyTX,'external_ordinary_updates':ext,'external_policy_TX':extpolicy,'private_candidate_X_TX':privateTX,'main_feedback_X_TX':feedbackTX,
        'issued_observations':len(issued),'consumed_observations':len(consumed),'unconsumed_observations':len(issued)-len(consumed),'actual_explore_events':explorations,'success_diagnosis':0,
        'no_mismatch_keeps':tags['NO_VISIBLE_MISMATCH_KEEP'],'budget_keeps':tags['TRIAL_BUDGET_KEEP'],'old_native_checker_bank_reruns':0,'new_keys_RNG_DP_calibration_collection':0,'formal_B1_or_science_qualification':False}
    save(HERE/'stored_audit_result.json',output);save(out/'exit.json',{'complete':True,'completed_at_utc':datetime.now(timezone.utc).isoformat(),'result':meta(HERE/'stored_audit_result.json')})
    print(json.dumps({'complete':True,'native_counts':final['counts'],'records':len(rs),'summaries':compact,'costs':costs,'phases':phases,'main_writes':main_write_addresses,'dispatches':dispatches,'event_outcomes':[h.get('assessment') for h in hypotheses],'preservation':preservation},sort_keys=True))


if __name__=='__main__':main()
