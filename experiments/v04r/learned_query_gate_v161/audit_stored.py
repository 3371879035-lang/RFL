"""New stdlib review of actual query-value fit and heldout native consequences. No old checker/RFL execution."""
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
    return wire({'factual':factual,'planned':planned,'numeric':numeric})

def features(data,rows):
    qvalues={tuple(q):number(v) for q,v in data['numeric']}
    def row(p):return {a:qvalues.get(tuple(p[:7])+(a,),v) for a,v in rows[tuple(p[:7])].items()}
    regrets=[max(row(p).values())-row(p)[p[7]] for p in data['planned']]
    i=next(i for i,(f,p) in enumerate(zip(data['factual'],data['planned'])) if f[7]!=p[7]);f,p=data['factual'][i],data['planned'][i]
    assert f[:7]==p[:7];values=row(p)
    return max(regrets),values[f[7]]-values[p[7]]

def empirical_fit(points):
    # Independent exhaustive SSE fit from closed data only, not imported learner.
    avg=lambda ps:sum(p[1] for p in ps)/len(ps)
    sse=lambda ps:sum((p[1]-avg(ps))**2 for p in ps)
    support=[(min(p[0][j] for p in points),max(p[0][j] for p in points)) for j in range(2)];splits=[]
    for j in range(2):
        vals=sorted(set(p[0][j] for p in points))
        for a,b in zip(vals,vals[1:]):
            cut=(a+b)/2;left=[p for p in points if p[0][j]<=cut];right=[p for p in points if p[0][j]>cut]
            splits.append((sse(left)+sse(right),j,cut,left,right))
    best=min(splits,key=lambda p:p[:3]) if splits else None
    if best is not None and best[0]<sse(points):_,j,cut,left,right=best
    else:j=cut=None;left=right=points
    return wire({'support':support,'split_feature':j,'threshold':cut,'left_mean':avg(left),'right_mean':avg(right),'n':len(points),'left_n':len(left),'right_n':len(right) if j is not None else 0})

def predict(model,x):
    if any(v<number(lo) or v>number(hi) for v,(lo,hi) in zip(x,model['support'])):return None
    j=model['split_feature'];return number(model['left_mean'] if j is None or x[j]<=number(model['threshold']) else model['right_mean'])

def training_expected(c,rows):
    cfg=c['training'];assert load(ROOT/cfg['event_exit']['path'])['child_exit_code']==0 and load(ROOT/cfg['baseline_exit']['path'])['child_exit_code']==1
    assert load(ROOT/cfg['event_review']['path'])['complete'] and load(ROOT/cfg['baseline_review']['path'])['complete']
    event=[json.loads(s) for s in (ROOT/cfg['event_raw']['path']).read_text(encoding='ascii').splitlines()]
    base=[json.loads(s) for s in (ROOT/cfg['baseline_raw']['path']).read_text(encoding='ascii').splitlines()]
    mains={r['context']['main_epoch']:r['payload'] for r in event if r['tag']=='TASK_COMPLETE' and r['context'].get('phase')=='stream'}
    bases={r['context']['main_epoch']:r['payload'] for r in base if r['tag']=='TASK_COMPLETE' and r['context'].get('phase')=='stream' and r['context'].get('arm')=='TaskTD'}
    assert len(mains)==len(bases)==12
    questions=[r for r in event if r['tag']=='ARRIVAL_HYPOTHESIS_PROPOSED' and r['payload']['specification'] is not None];assert len(questions)==2
    points=[];sources=[]
    for r in questions:
        e=r['context']['main_epoch'];q=r['payload'];kk,phi=q['evidence']['kappa'],q['evidence']['phi']
        assert mains[e]['trace']==bases[e]['trace'] and mains[e]['before']['current']==bases[e]['before']['current']
        active=lambda p:[v for v in p['learning_values']['Q'] if (v['address']['state']['kappa'],v['address']['state']['phi'])==(kk,phi)]
        assert active(mains[e]['before'])==active(bases[e]['before'])
        data=projection(q);x=features(data,rows);future=[return_value(mains[j]) for j in range(e+1,e+6)];ordinary=[return_value(bases[j]) for j in range(e+1,e+6)]
        paid=sum(r2['tag']=='TASK_COMPLETE' and r2['context'].get('phase')=='private' and r2['context'].get('main_epoch')==e for r2 in event);assert paid==1
        gain=(sum(future)-sum(ordinary))/paid;points.append((x,gain));sources.append({'historical_event_seq':r['seq'],'historical_epoch':e,'feature_data':data,'x':x,'future_main_returns':future,'ordinary_future_main_returns':ordinary,'paid_private_rollouts':paid,'gain_per_paid_probe':gain})
    assert all(p[0][1]==0 for p in points)
    return {'closed_training_points':wire([{'x':x,'gain_per_paid_probe':y} for x,y in points]),'audit_only_training_sources':wire(sources),'model':empirical_fit(points),'refit_during_test':False}

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
    oldprep=[json.loads(line) for line in (ROOT/c['ordinary_checkpoint']['raw']['path']).read_text(encoding='ascii').splitlines()]
    prep=next(r['payload']['state'] for r in oldprep if r['tag']=='PREPARATION_COMPLETE')
    for cfg in c['training'].values():assert meta(ROOT/cfg['path'])=={k:cfg[k] for k in ('bytes','sha256')}
    rows={}
    for line in (ROOT/c['reference']['path']).read_text(encoding='utf-8').splitlines():
        if line.startswith('DECISION_CONTEXT='):
            q=json.loads(line.split('=',1)[1]);rows[tuple(q['context'])]={a:float.fromhex(v) for a,v in q['q_row_hex']}
    schedule=[s for s in c['schedule'] for _ in range(s['count'])];assert len(schedule)==24
    rs=[json.loads(s) for s in (HERE/'evidence/raw.jsonl').read_text(encoding='ascii').splitlines()];assert [r['seq'] for r in rs]==list(range(len(rs)))
    tasks=defaultdict(list);posts=defaultdict(list);last={};details={};registrations={};source_ids={};issued={};consumed=set();queries={};ordinals=Counter();tags=Counter();summaries=[];accepted=[];hypotheses=[];public_edges=0;decisions=[];frozen=None
    task=None;stack=[];batch=None;external=None;steps=ordinary=policyTX=ext=extpolicy=0
    def account(arm):
        return {'algorithm':arm,'trial_tasks_used':sum(len(v) for k,v in tasks.items() if k[0]=='private' and k[1]==arm),'trial_task_budget':0 if arm=='TaskTD' else c['trial_task_budget_each_feedback_arm'],'base_queries':sum(a==arm for a,e in queries),'expanded_queries':0}
    for r in rs:
        tag,p,ctx=r['tag'],r['payload'],r['context'];tags[tag]+=1;k=key(ctx);arm=ctx.get('arm');epoch=ctx.get('main_epoch')
        if tag=='REFERENCE':assert p['digest']==c['reference']['q_digest'] and p['rows']==len(rows)
        elif tag=='RECORDED_ORDINARY_MATERIALIZED':
            assert p['source_raw_sha256']==c['ordinary_checkpoint']['raw']['sha256'] and p['recorded_payload']==prep and all(p[f]==prep[f] for f in ('immediate','current','learning_values'))
            assert p['native_delta']=={'rollout':0,'step':0,'transaction':3} and p['restored_issued_identities']==0
        elif tag=='SHARED_SOURCE':
            assert p['before']==prep['current'] and p['values']==prep['learning_values'];expected=stores(prep['current'])
            expected['D'].update({(0,2,0,0,0,1,0):4,(2,2,2,1,4,1,0):3})
            assert len(p['edits'])==2 and all(x['store']=='decision' for x in p['edits']) and maps_equal(stores(p['state']),expected);source=p['state']
        elif tag=='QUERY_VALUE_MODEL_FROZEN':
            assert not tasks and frozen is None and p==training_expected(c,rows);frozen=p
        elif tag=='DIAGNOSTIC_DISPATCH':
            assert task is not None and arm!='TaskTD' and p['branch']==('event' if task['raw']['trace']['outcome']=='TRAP' else 'keep') and p['visible_mismatch'] is False
            assert p['terminal']==task['raw']['trace']['outcome'] and p['post_TD']==task['ordinary'] and p['diagnostic_account']==account(arm)
        elif tag=='QUERY_VALUE_DECISION':
            assert arm=='ValueGated' and task['spec'] is not None and p['post_TD']==task['ordinary'] and p['diagnostic_account']==account(arm)
            feature_data=projection(task['query']);x=features(feature_data,rows);pred=predict(frozen['model'],x)
            decision='unknown_probe' if pred is None else 'supported_probe' if pred>0 else 'supported_skip'
            assert p['feature_data']==feature_data and p['x']==wire(x) and p['model']==frozen['model'] and p['predicted_gain_per_paid_probe']==wire(pred) and p['decision']==decision
            task['gate']=decision;decisions.append({'arm':arm,'epoch':epoch,'stage':schedule[epoch]['label'],'x':x,'prediction':pred,'decision':decision})
        elif tag=='MAIN_INITIALIZED':
            q=p['state'];assert q['immediate']==q['current']==source and q['learning_values']==prep['learning_values'] and q['completed_episodes']==q['external_updates']==0 and q['attempted_epochs']==[]
            assert p['diagnostic_account']==account(arm) and frozen is not None
            assert p['configuration']=={'revision':'v161-empirical-query-value','event_enabled':arm!='TaskTD','trial_budget_shared':0 if arm=='TaskTD' else 6,'feedback_address_limit':0 if arm=='TaskTD' else 2,'value_gate_enabled':arm=='ValueGated','query_value_model':frozen['model'],'mro':['QueryValueGatedAgent','UnifiedFeedbackAgent','PathwiseAgent','CurrentPathProof','EventHypothesisAgent','StrictTrialDerivedAgent','StrictWitnessLoop','TrialDerivedAgent','EvidenceExperienceLoop','ObservationTaskLoop','CoordinateLearner','object']}
            last[k]=q
        elif tag=='RUNNER_CONTEXT':assert p=={'epoch':epoch,'stage_audit_only':schedule[epoch]['label'],'kappa':schedule[epoch]['kappa'],'phi':schedule[epoch]['phi']} and epoch==len(tasks[k])
        elif tag=='ARRIVAL_HYPOTHESIS_PROPOSED':
            assert task is not None and ctx['phase']=='stream' and p['evidence']==task['evidence'] and p['terminal']=='TRAP' and p['post_TD']==task['ordinary'] and all(s['a_cmd']==s['a_realized'] for s in p['evidence']['steps'])
            spec,search=planned_probe(p['evidence'],rows,c['public_transitions_per_proposal']);assert p['specification']==spec and p['public_search']==search
            public_edges+=search['public_candidate_transitions']+1;task['spec']=spec;task['query']=p
            hypotheses.append({'arm':arm,'epoch':epoch,'stage':schedule[epoch]['label'],'specification':spec,'public_search':search})
        elif tag=='OWNED_BRANCH_REGISTERED':
            assert task is not None and task.get('gate')!='supported_skip' and p['consumer']==task['ordinary'] and p['proposal']=={'action':'keep','edits':[]}
            reg=p['registration'];ordinals[arm]+=1;s=schedule[epoch]
            assert reg['ordinal']==ordinals[arm] and reg['main_epoch']==epoch and reg['origin_L']==task['ordinary']['learning_values'] and reg['kappa']==s['kappa'] and reg['phi']==s['phi'] and reg['source_I']==task['ordinary']['current'] and reg['proposal']==p['proposal']
            before=p['source_before'];assert before['immediate']==before['current']==reg['source_I'] and before['learning_values']==reg['origin_L'] and before['completed_episodes']==before['external_updates']==0
            registrations[reg['id']]={'payload':p,'key':k,'parent':task['key']};source_ids[k]=reg['id']
        elif tag=='PRIVATE_START':
            assert p['state']['immediate']==p['state']['current']==task['ordinary']['current'] and p['state']['learning_values']==task['ordinary']['learning_values'] and p['parent']==task['ordinary'] and p['n']==1 and p['arrival_specification']==task['spec']
            last[k]=p['state'];details[k]={'spec':task['spec'],'plan_episodes':p['plan_episodes']}
        elif tag=='TASK_BEGIN':
            if ctx['phase']=='private':assert task is not None and task['key'][0]=='stream';stack.append(task)
            else:assert task is None
            e=len(tasks[k]);s=schedule[epoch];assert p['epoch']==e and p['before']['attempted_epochs']==list(range(e+1)) and all(p['before'][f]==last[k][f] for f in p['before'] if f!='attempted_epochs')
            coins=[(1<<64)-1]*12;chi=[[0] for _ in range(12)]
            if ctx['phase']=='private':
                cfg=details[k];assert e==0
                for i,w in enumerate(cfg['spec']['rows']):coins[i]=0;chi[i]=[w['admissible_rank']]
            else:assert e==epoch
            ep={'epoch':e,'kappa':s['kappa'],'proposal':1,'tape':{'phase':s['phi'],'error_flag':0,'cause_rank':12},'coins':coins,'rejections':chi}
            mask={'decision':None,'controller':None,'plant':None,'trap':s['trap']};assert p['episode']==ep and p['environment_mask_audit_only']==mask
            if ctx['phase']=='private':assert details[k]['plan_episodes']==[ep]
            task={'key':k,'epoch':e,'main_epoch':epoch,'before':p['before'],'episode':ep,'mask':mask,'diag':0,**(details[k] if ctx['phase']=='private' else {})}
        elif tag=='TASK_RAW':
            tr=p['trace'];assert task is not None and task['key']==k and tr['mask']==task['mask'] and tr['option_in_force']==1
            ep=task['episode'];kk,phi=ep['kappa'],ep['tape']['phase'];at=(0,2,0,kk,phi);z,m=1,0;R=stores(task['before']['current']);N=stores(task['before']['learning_values']);calls=[]
            assert len(p['draws'])==len(tr['steps']);trap=task['mask']['trap']
            for i,(draw,x) in enumerate(zip(p['draws'],tr['steps'])):
                q=at+(z,m);vs={a:N['Q'].get(q+(a,),v) for a,v in rows[q].items()};greedy=R['D'].get(q,min(a for a,v in vs.items() if v==max(vs.values())));coin=ep['coins'][i];explore=coin==0;index=ep['rejections'][i][0]
                cmd=sorted(rows[q])[index%len(rows[q])] if explore else greedy;u=R['X'].get(at+(cmd,),cmd);real=u;calls.append([i,0,0,coin])
                if explore:calls.append([i,1,0,index])
                assert draw=={'i':i,'explore':explore,'admissible':sorted(rows[q]),'a_cmd':cmd} and x['a_cmd']==cmd and x['u']==u and x['a_realized']==real
                st,ctrl=public_move(dict(zip(('x','y','t','kappa','phi'),at)),{'z':z,'m':m},real);cell=(st['x'],st['y']);period=6 if kk==0 else 3
                outcome='COLLISION' if cell==(2,2) and st['t']%period==phi%period else 'TRAP' if list(cell)==trap['cell'] and at[2]==trap['t'] else 'SUCCESS' if cell==(4,2) else 'TIMEOUT' if st['t']>=12 else None
                reward=-.02+(1.0 if outcome=='SUCCESS' else -1.0 if outcome else 0.0)
                assert x['state']==st and x['control']==ctrl and x['terminal']==(outcome is not None) and x['outcome']==outcome and not x['illegal'] and number(x['reward']).hex()==reward.hex()
                at=state(x['state']);z,m=x['control']['z'],x['control']['m']
            assert p['coordinates']==calls and tr['steps'][-1]['terminal'] and tr['outcome']==tr['steps'][-1]['outcome'] and p['return_hex']==return_value({'trace':tr}).hex()
            task['raw']={**p,'_episode':ep};steps+=len(tr['steps'])
        elif tag=='ORDINARY_UPDATE':
            policyTX+=update(task['before'],task['raw'],p,rows,False);ordinary+=1;task['ordinary']=p['after'];task['after']=p['after']
        elif tag=='DIAGNOSE_BEGIN':
            assert ctx['phase']=='stream' and p['terminal']==task['raw']['trace']['outcome']!='SUCCESS' and p['evidence']==evidence(task['raw']['trace']) and p['state_before']==task['ordinary'];task['diag']+=1;task['evidence']=p['evidence']
        elif tag=='TRIAL_BUDGET_KEEP':assert p['main_epoch']==epoch and p['diagnostic_account']==account(arm) and account(arm)['trial_tasks_used']>=account(arm)['trial_task_budget']
        elif tag=='OUT_OF_SCOPE_FAILURE_KEEP':assert p['evidence']==task['evidence'] and (p['terminal']!='TRAP' or any(s['a_cmd']!=s['a_realized'] for s in p['evidence']['steps']))
        elif tag=='PRIVATE_COMPLETE':
            assert p['state']==last[k] and p['n']==len(tasks[k])==1 and number(p['return']).hex()==return_value(tasks[k][0]).hex() and p['hypothesis_assessment']==assess(details[k]['spec'],tasks[k][0]['trace']) and p['observation_id']==source_ids[k]
            next(h for h in hypotheses if h['epoch']==epoch and h['arm']==arm)['assessment']=p['hypothesis_assessment']
        elif tag=='SELECTED_EVENT_EXPERIENCE':
            assert p['observation_id']==source_ids['private',arm,epoch,'alternate-entry'] and p['proposal']=={'action':'keep','edits':[]}
            queries[arm,epoch]=task['query'];assert p['diagnostic_account']==account(arm)
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
            ids=[source_ids['private',arm,epoch,'alternate-entry']];assert [o['observation_id'] for o in p['observations']]==ids and p['ordinals']==[registrations[ids[0]]['payload']['registration']['ordinal']]
            for o in p['observations']:
                oid=o['observation_id'];assert issued[oid]==o and oid not in consumed and registrations[oid]['parent']==k and registrations[oid]['payload']['registration']['origin_L']==p['before']['learning_values']
            consumed.update(ids);batch={'before':p['before'],'ids':ids,'processed':[],'receipts':[]}
        elif tag=='OWNED_EXTERNAL_BEGIN':
            o=p['observation'];oid=o['observation_id'];reg=registrations[oid]
            assert task is None and external is None and batch is not None and oid==batch['ids'][len(batch['processed'])] and issued[oid]==o and oid in consumed and p['before']==last[k]
            assert not changes(reg['payload']['source_before']['immediate'],p['before']['current'],o) and p['external_update_index']==last[k]['external_updates'] and p['main_clock_advanced'] is False;external=p
        elif tag=='OWNED_EXTERNAL_END':
            o=external['observation'];oid=o['observation_id'];wanted={'applied':True,'reason':'same_mechanism_on_observed_path','observation_id':oid,'mechanism_changes':[]}
            assert p['observation_id']==oid and p['receipt']==wanted;extpolicy+=update(external['before'],{'trace':o['trace'],'_episode':o['episode']},p,rows,True);ext+=1;last[k]=p['after']
            batch['processed'].append(oid);batch['receipts'].append(wanted);accepted.append({'arm':arm,'epoch':epoch,'terminal':o['trace']['outcome'],'numeric_content_changed':external['before']['learning_values']!=p['after']['learning_values']});external=None
        elif tag=='OWNED_BATCH_END':assert batch is not None and batch['processed']==batch['ids'] and p['before']==batch['before'] and p['after']==last[k] and p['receipts']==batch['receipts'];batch=None
        elif tag=='POST_OBSERVED_TASK':assert task is None and batch is None and p['epoch']==len(tasks[k])-1==epoch and p['state']==last[k] and p['diagnostic_account']==account(arm);posts[k].append(p['state'])
        elif tag=='AGENT_FINAL':
            ts=tasks[k];vals=[return_value(t) for t in ts];assert len(ts)==len(posts[k])==p['main_tasks']==24 and p['final_state']==last[k] and p['diagnostic_account']==account(arm)
            assert [number(v) for v in p['returns']]==vals and p['outcomes']==[t['terminal'] for t in ts] and p['successes']==sum(t['terminal']=='SUCCESS' for t in ts) and number(p['mean_return']).hex()==(sum(vals)/24).hex() and p['external_updates']==last[k]['external_updates'];summaries.append(p)
        elif tag=='RESULT':assert p['complete'] and p['streams']==summaries;result=p
        elif tag=='FINAL':assert p['complete'] and p['profile_restored'];final=p
        else:raise AssertionError('unexpectedtag '+tag)
    assert task is None and external is None and batch is None and not stack and len(summaries)==3 and set(registrations)==set(issued)==consumed
    assert ordinary==sum(len(v) for v in tasks.values()) and ext==len(consumed)
    expected={'rollout':ordinary,'step':steps,'transaction':4+ordinary+policyTX+ext+extpolicy,'query_model_fit':1,'query_features':2+len(decisions)}
    if public_edges:expected['public_geometry']=public_edges
    assert final['counts']==result['counts']==expected
    phases=[];costs=[];simple=[]
    for arm in c['arms']:
        mainkey=('stream',arm,None,None);ts=tasks[mainkey];cursor=0
        assert all(x['immediate']==source and x['current']['P']==source['P'] and x['current']['X']==source['X'] for x in posts[mainkey])
        for s in c['schedule']:
            part=ts[cursor:cursor+s['count']];vals=[return_value(t) for t in part]
            phases.append({'arm':arm,'stage':s['label'],'successes':sum(t['terminal']=='SUCCESS' for t in part),'returns':vals,'mean_return':sum(vals)/len(vals),'private_tasks':sum(a==arm and cursor<=e<cursor+s['count'] for a,e in queries)});cursor+=s['count']
        allts=[t for key_,vs in tasks.items() if key_[1]==arm for t in vs];nativepol=sum(bool(r['payload']['policy_edits']) for r in rs if r['tag']=='ORDINARY_UPDATE' and r['context'].get('arm')==arm)
        epol=sum(bool(r['payload']['policy_edits']) for r in rs if r['tag']=='OWNED_EXTERNAL_END' and r['context'].get('arm')==arm);updates=sum(a['arm']==arm for a in accepted)
        cost={'arm':arm,'main_tasks':24,'private_tasks':len(allts)-24,'rollout':len(allts),'step':sum(len(t['trace']['steps']) for t in allts),'transaction':len(allts)+nativepol+updates+epol,'shared4TX_excluded':True,'additional_public_geometry_transitions':sum(h['public_search']['public_candidate_transitions']+1 for h in hypotheses if h['arm']==arm)};costs.append(cost)
        simple.append({'arm':arm,'main_successes':sum(t['terminal']=='SUCCESS' for t in ts),'main_return':sum(return_value(t) for t in ts),'all_interaction_return':sum(return_value(t) for t in allts),'all_interaction_failures':sum(t['terminal']!='SUCCESS' for t in allts),'ordinary_policy_TX':nativepol,'external_policy_TX':epol})
    assert sum(d['decision']=='supported_skip' for d in decisions)==sum(1 for d in decisions if (d['arm'],d['epoch']) not in queries)
    # A supported skip is checked against actual concurrent AlwaysUnified future,
    # not upgraded to a general claim merely because its prediction was zero.
    skip_comparisons=[]
    for d in decisions:
        if d['decision']!='supported_skip':continue
        e=d['epoch'];end=next(sum(s['count'] for s in c['schedule'][:i+1]) for i,s in enumerate(c['schedule']) if e<sum(t['count'] for t in c['schedule'][:i+1]))
        a=tasks[('stream','AlwaysUnified',None,None)];g=tasks[('stream','ValueGated',None,None)]
        skip_comparisons.append({'epoch':e,'stage':d['stage'],'first_factual_equal':a[e]['trace']==g[e]['trace'],'following_AlwaysUnified_returns':[return_value(t) for t in a[e+1:end]],'following_ValueGated_returns':[return_value(t) for t in g[e+1:end]],'Always_minus_Gated_future_sum':sum(return_value(t) for t in a[e+1:end])-sum(return_value(t) for t in g[e+1:end])})
    tree=ast.parse((HERE/'gated_agent.py').read_text());diag=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='_diagnose_visible')
    forbidden={'mask','trap','plant','truth','scene','case','evaluator','role','source_label','cost','ledger'}
    assert not (forbidden & {n.id for n in ast.walk(diag) if isinstance(n,ast.Name)})
    ftree=ast.parse((HERE/'query_value.py').read_text());classes={n.name:n for n in ftree.body if isinstance(n,ast.ClassDef)}
    assert [n.target.id for n in classes['QueryTrainingPoint'].body if isinstance(n,ast.AnnAssign)]==['x','gain_per_paid_probe']
    assert [n.target.id for n in classes['QueryFeatureData'].body if isinstance(n,ast.AnnAssign)]==['factual','planned','numeric']
    assert tags['QUERY_VALUE_MODEL_FROZEN']==1 and not any('fit_query_value' in ast.unparse(n) for n in ast.walk(tree) if isinstance(n,ast.Call))
    output={'schema':'V161_STDLIB_LEARNED_QUERY_REVIEW','complete':True,'native_counts':final['counts'],'records':len(rs),'input_pins':len(claim['input_binding_before']),'trained':frozen,'phase_results':phases,'online_costs':costs,'simple_sums_not_adopted_utility':simple,'query_decisions':decisions,'skip_comparisons':skip_comparisons,'hypotheses':hypotheses,'accepted':accepted,'native_ordinary_updates':ordinary,'ordinary_policy_TX':policyTX,'external_ordinary_updates':ext,'external_policy_TX':extpolicy,'issued_observations':len(issued),'consumed_observations':len(consumed),'success_diagnosis':0,'feedback_TX':0,'source_install_TX':1,'source_edits':2,'historical_label_interactions_reused_not_free':26,'control_native_checker_reruns':0,'new_keys_RNG_DP_calibration_collection':0,'qualification':False}
    save(HERE/'stored_audit_result.json',output);save(out/'exit.json',{'complete':True,'completed_at_utc':datetime.now(timezone.utc).isoformat(),'result':meta(HERE/'stored_audit_result.json')})
    print(json.dumps({k:output[k] for k in ('complete','native_counts','records','simple_sums_not_adopted_utility','query_decisions','skip_comparisons')},sort_keys=True))

if __name__=='__main__':main()
