"""New stdlib audit of ordinary-extra native evidence; no old checker run."""
from collections import Counter,defaultdict
from copy import deepcopy
from datetime import datetime,timezone
import ast
import hashlib
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]

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

def check_greedy(payload,trace,kappa,rows,phi):
    cur=stores(payload['current']);numeric=cur if payload['mode']=='dq' else stores(payload['learning_values'])
    at=(0,2,0,kappa,phi);z,m=1,0
    for x in trace['steps']:
        key=at+(z,m);row={a:numeric['Q'].get(key+(a,),v) for a,v in rows[key].items()}
        cmd=cur['D'][key] if payload['mode']=='patch-adaptive' and key in cur['D'] else min(a for a,v in row.items() if v==max(row.values()))
        assert x['a_cmd']==cmd and x['a_realized']==cmd
        at=state(x['state']);z,m=x['control']['z'],x['control']['m']
    assert trace['steps'][-1]['terminal'] and trace['outcome']==trace['steps'][-1]['outcome']
    assert trace['option_in_force']==1

def planned_source_edits(mode,contract):
    edits=[]
    def add(x,y,t,k,phi,m,action,value=6.0):
        at={'state':{'x':x,'y':y,'t':t,'kappa':k,'phi':phi},'z':1,'m':m}
        if mode=='dq':
            at['a']=action;edits.append({'store':'q','address':at,'value':{'binary64_hex':value.hex()}})
        else:edits.append({'store':'decision','address':at,'value':action})
    for d in contract['sources']:
        for t in range(d['prefix'],12):
            for m in (0,1):add(*d['cell'],t,d['kappa'],d['phi'],m,4)
    d=contract['prefix_wait_source']
    for t in d['times']:
        for m in (0,1):add(*d['cell'],t,d['kappa'],d['phi'],m,4)
    d=contract['scripted_source']
    for e in d['entries']:
        for m in (0,1):add(e['x'],e['y'],e['t'],e.get('kappa',d['kappa']),e.get('phi',d['phi']),m,e['action'])
    add(1,2,1,0,4,0,3,9.0)
    edits.append({'store':'process','address':3,'value':2})
    return edits

def return_value(receipt):
    return float(sum(number(s['reward']) for s in receipt['trace']['steps']))

def ctxkey(c):
    return (c['phase'],c['arm'],c.get('main_epoch'),c.get('extra_index'))


def verify_update(before,raw,p,rows,external):
    expected,values,seen,policy,visited=ordinary_expected(before,raw,rows)
    after=p['after']
    assert maps_equal(stores(after['current']),expected) and maps_equal(stores(after['learning_values']),values)
    assert [address(e['address'],'Q') for e in p['numeric_edits']]==seen
    for edit,key in zip(p['numeric_edits'],seen):assert number(edit['value']).hex()==values['Q'].get(key,rows[key[:-1]][key[-1]]).hex()
    assert [address(e['address'],'D') for e in p['policy_edits']]==policy
    for edit,key in zip(p['policy_edits'],policy):assert edit['value']==expected['D'][key]
    assert after['immediate']==before['immediate'] and after['attempted_epochs']==before['attempted_epochs']
    assert after['completed_episodes']==before['completed_episodes']+(0 if external else 1)
    assert after['external_updates']==before['external_updates']+(1 if external else 0)
    assert after['observation_revision']==before['observation_revision']=='v142-complete-main-supplemental-observation'


def main():
    out=HERE/'evidence_audit';assert not out.exists(),'audit already attempted; no retry';out.mkdir()
    def save(path,data):
        with path.open('x',encoding='utf-8',newline='\n') as f:f.write(json.dumps(data,sort_keys=True,ensure_ascii=True,indent=2)+'\n')
    save(out/'claim.json',{'audit_source':meta(Path(__file__)),'native_receipt':meta(HERE/'evidence/exit.json'),'automatic_retry':False,'started_at_utc':datetime.now(timezone.utc).isoformat()})
    c=load(HERE/'contract.json');claim=load(HERE/'evidence/claim.json');ex=load(HERE/'evidence/exit.json')
    assert ex['child_exit_code']==0 and ex['input_bytes_unchanged'] and claim['input_binding_before']==ex['input_binding_after']
    for path,pin in claim['input_binding_before'].items():assert meta(ROOT/path)==pin,path
    assert meta(HERE/'evidence/raw.jsonl')==ex['raw']
    rows={};ref=c['reference'];assert meta(ROOT/ref['path'])['sha256']==ref['sha256']
    for line in (ROOT/ref['path']).read_text(encoding='utf-8').splitlines():
        if line.startswith('DECISION_CONTEXT='):
            p=json.loads(line.split('=',1)[1]);rows[tuple(p['context'])]={a:float.fromhex(v) for a,v in p['q_row_hex']}
    rs=[json.loads(x) for x in (HERE/'evidence/raw.jsonl').read_text(encoding='ascii').splitlines()]
    assert [r['seq'] for r in rs]==list(range(len(rs)))
    tasks=defaultdict(list);details={};last={};initial={};events=defaultdict(list);active_event=None;task=None;src=None
    registrations={};issued={};consumed=set();duplicates=set();external=None;ingestions=[];posts=defaultdict(list);summaries=[]
    tags=Counter();steps=0;ordinary=0;ordinary_policy=0;external_policy=0;main_episodes=[];extra_episodes=[]
    for r in rs:
        tag,p,ctx=r['tag'],r['payload'],r['context'];tags[tag]+=1;k=ctxkey(ctx);arm=ctx.get('arm');case=ctx.get('case')
        if tag=='REFERENCE':assert p['digest']==ref['q_digest'] and p['rows']==len(rows)
        elif tag=='SOURCE_SETUP':
            assert p['mode']=='patch-adaptive' and p['edits']==planned_source_edits('patch-adaptive',c['cases'][case]) and all(not x for x in stores(p['before']).values())
            assert len(p['edits'])==44
            src={ch:{} for ch in ('D','P','X','Q')}
            for edit in p['edits']:
                ch={'decision':'D','process':'P'}[edit['store']];src[ch][address(edit['address'],ch)]=edit['value']
        elif tag=='SOURCE_READY':
            assert src is not None and maps_equal(stores(p['stores']),src)
            initial[case]=p['stores'];src=None
        elif tag=='TASK_BEGIN':
            assert task is None
            e=p['epoch']
            if ctx['phase']=='stream':
                assert e==len(tasks[k]);item=c['schedules'][case][e]
                if e:assert all(p['before'][f]==last[k][f] for f in ('current','learning_values','immediate','external_updates','reference_digest','mode'))
                else:assert p['before']['current']==p['before']['immediate']==initial[case] and p['before']['external_updates']==0
            else:
                assert ctx['phase']=='ordinary-extra' and active_event is not None and e==0
                item=c['schedules'][case][ctx['main_epoch']]
                reg=next(v for v in registrations.values() if v['key']==k)
                assert all(p['before'][f]==reg['payload']['source_before'][f] for f in p['before'] if f!='attempted_epochs')
            assert p['episode']['epoch']==e and p['episode']['kappa']==item['kappa'] and p['episode']['tape']=={'phase':item['phi'],'error_flag':0,'cause_rank':12}
            mask={'decision':None,'controller':None,'plant':None,'trap':{'cell':[1,2],'t':0} if item['trap'] else None}
            assert p['environment_mask_audit_only']==mask and p['before']['completed_episodes']==e and p['before']['attempted_epochs']==list(range(e+1))
            task={'begin':p,'epoch':e,'key':k,'mask':mask,'episode':p['episode']}
        elif tag=='TASK_RAW':
            assert task is not None and task['key']==k
            tr=p['trace'];st=tr['steps'];assert st and st[-1]['terminal'] and tr['outcome']==st[-1]['outcome'] and tr['mask']==task['mask']
            assert p['coordinates']==[[i,0,0,(1<<64)-1] for i in range(len(st))] and len(p['draws'])==len(st) and all(not x['explore'] for x in p['draws'])
            assert p['return_hex']==sum(number(s['reward']) for s in st).hex()
            check_greedy(task['begin']['before'],tr,p['trace']['steps'][0]['state']['kappa'],rows,p['trace']['steps'][0]['state']['phi'])
            task['raw']={**p,'_episode':task['episode']};steps+=len(st)
        elif tag=='ORDINARY_UPDATE':
            assert task is not None and task['key']==k
            verify_update(task['begin']['before'],task['raw'],p,rows,False);task['ordinary']=p['after'];ordinary+=1;ordinary_policy+=bool(p['policy_edits'])
        elif tag=='TASK_COMPLETE':
            assert task is not None and task['key']==k and p['trace']==task['raw']['trace'] and p['after']==p['ordinary_after']==task['ordinary']
            assert p['counters']=={'ordinary_updates':1,'diagnostic_calls':0,'query_calls':0,'diagnostic_transactions':0,'diagnostic_edit_addresses':0}
            assert p['route']=={'terminal':p['terminal'],'route':'TASK_ONLY','ordinary_learning_called':True,'diagnostic_calls':0,'query_spend':0,'write_spend':0,'decision':'none'}
            tasks[k].append(p);details[k]=task;last[k]=p['after']
            (main_episodes if ctx['phase']=='stream' else extra_episodes).append((ctx,p))
            task=None
        elif tag=='ORDINARY_EXTRA_BEGIN':
            assert task is None and active_event is None and ctx['phase']=='stream' and tasks[k][-1]['terminal']!='SUCCESS'
            assert p['main_epoch']==len(tasks[k])-1 and p['before']==last[k] and p['max_extra_episodes']==2
            assert p['event_number']==len(events[arm])+1<=3
            active_event={'arm':arm,'main_epoch':p['main_epoch'],'episodes':[],'consumer_key':k};events[arm].append(active_event)
        elif tag=='NATIVE_OBSERVATION_REGISTERED':
            assert task is None and active_event is not None and ctx['phase']=='ordinary-extra'
            j=ctx['extra_index'];assert p['main_epoch']==ctx['main_epoch']==active_event['main_epoch'] and j==len(active_event['episodes'])<2
            if j:assert active_event['episodes'][0]['actual_terminal']!='SUCCESS'
            assert p['registration_phase']=='after-complete-main-failure'
            assert p['consumer']==last[active_event['consumer_key']] and all(p['source_before'][f]==p['consumer'][f] for f in ('current','learning_values'))
            assert p['source_before']['completed_episodes']==p['source_before']['external_updates']==0 and p['source_before']['attempted_epochs']==[]
            assert p['observation_id'] not in registrations
            registrations[p['observation_id']]={'payload':p,'key':k,'consumer_key':active_event['consumer_key']}
        elif tag=='NATIVE_OBSERVATION_ISSUED':
            assert task is None and ctx['phase']=='ordinary-extra'
            reg=registrations[p['observation_id']];assert reg['key']==k and p['observation_id'] not in issued
            assert p['trace']==tasks[k][-1]['trace'] and p['episode']==details[k]['episode'] and p['source_epoch']==0 and p['main_epoch']==reg['payload']['main_epoch']
            assert p['issuer_label']==reg['payload']['source_label'] and p['consumer_label']==reg['payload']['consumer']['source_label'] and p['reference_digest']==ref['q_digest']
            issued[p['observation_id']]=p
        elif tag=='EXTERNAL_OBSERVATION_BEGIN':
            assert task is None and external is None and ctx['phase']=='stream'
            obs=p['observation'];oid=obs['observation_id'];assert issued[oid]==obs and oid not in consumed and registrations[oid]['consumer_key']==k
            assert p['before']==last[k] and p['external_update_index']==p['before']['external_updates'] and p['main_clock_advanced'] is False
            assert p['before']['learning_values']==registrations[oid]['payload']['consumer']['learning_values']
            consumed.add(oid);external={'begin':p,'key':k}
        elif tag=='EXTERNAL_OBSERVATION_END':
            assert external is not None and external['key']==k
            before=external['begin']['before'];obs=external['begin']['observation'];assert p['observation_id']==obs['observation_id']
            verify_update(before,{'trace':obs['trace'],'_episode':obs['episode']},p,rows,True)
            last[k]=p['after'];external_policy+=bool(p['policy_edits'])
            ingestions.append({'arm':arm,'main_epoch':obs['main_epoch'],'observation_id':p['observation_id'],'source_terminal':obs['trace']['outcome'],
                 'L_Q_before':len(before['learning_values']['Q']),'L_Q_after':len(p['after']['learning_values']['Q']),'numeric_changed':before['learning_values']!=p['after']['learning_values']})
            external=None
        elif tag=='OBSERVATION_DUPLICATE_REJECTED':
            oid=p['observation_id'];assert task is None and oid in consumed and oid not in duplicates and registrations[oid]['consumer_key']==k
            assert p['native_delta']=={'rollout':0,'step':0,'transaction':0} and p['state_unchanged'] and p['error']=='native observation already consumed; no retry'
            duplicates.add(oid)
        elif tag=='ORDINARY_EXTRA_EPISODE':
            oid=p['observation_id'];reg=registrations[oid];assert oid in consumed and oid in duplicates and p['after']==last[k]
            assert active_event is not None and p['main_epoch']==active_event['main_epoch'] and p['extra_index']==len(active_event['episodes'])
            source=tasks[reg['key']][-1]
            assert p['actual_terminal']==source['terminal'] and number(p['actual_return']).hex()==return_value(source).hex()
            active_event['episodes'].append(p)
        elif tag=='ORDINARY_EXTRA_END':
            ev=active_event;assert ev is not None and p['main_epoch']==ev['main_epoch'] and p['after']==last[k]
            assert p['extra_episodes']==len(ev['episodes']) in (1,2)
            if len(ev['episodes'])==1:assert ev['episodes'][0]['actual_terminal']=='SUCCESS'
            else:assert ev['episodes'][0]['actual_terminal']!='SUCCESS'
            active_event=None
        elif tag=='POST_MAIN_LEARNING_STATE':
            assert task is None and external is None and active_event is None and p['main_epoch']==len(tasks[k])-1 and p['state']==last[k]
            n=sum(i['arm']==arm and i['main_epoch']==p['main_epoch'] for i in ingestions)
            assert n==p['observations_consumed']
            if tasks[k][-1]['terminal']!='SUCCESS' and len(events[arm])<3:assert n>0
            posts[arm].append(p['state'])
        elif tag=='STREAM_ARM':
            ts=tasks[k];assert len(ts)==len(posts[arm])==p['main_tasks']==20
            vals=[return_value(x) for x in ts]
            assert [number(x) for x in p['returns']]==vals and number(p['return_sum']).hex()==sum(vals).hex() and number(p['return_mean']).hex()==(sum(vals)/20).hex()
            assert p['outcomes']==[x['terminal'] for x in ts] and p['successes']==sum(x['terminal']=='SUCCESS' for x in ts)
            assert p['external_updates']==p['extra_episodes']==sum(x['arm']==arm for x in ingestions)
            assert p['extra_events']==len(events[arm]) and p['diagnostic_calls']==0 and p['final_state']==last[k]
            summaries.append(p)
        elif tag=='RESULT':assert p['streams']==summaries and p['complete'];result=p
        elif tag=='FINAL':assert p['complete'] and p['profile_restored'];final=p
        else:raise AssertionError('unexpected tag '+tag)
    assert task is None and external is None and active_event is None and src is None
    assert set(issued)==set(registrations)==consumed==duplicates
    assert len(main_episodes)==40 and len(extra_episodes)<=12 and ordinary==len(main_episodes)+len(extra_episodes)
    assert final['counts']==result['counts'] and final['counts']['rollout']==ordinary and final['counts']['step']==steps
    assert final['counts']['transaction']==ordinary+ordinary_policy+len(ingestions)+external_policy+tags['SOURCE_READY']
    # Check literal transport of ordinary mathematical operations; clock is explicit.
    oldloop=(ROOT/'experiments/v04r/learned_candidate_choice_v118/candidate_loop.py').read_text(encoding='utf-8');newloop=(HERE/'observation_loop.py').read_text(encoding='utf-8')
    oc=next(x for x in ast.parse(oldloop).body if isinstance(x,ast.ClassDef) and x.name=='CandidateTaskLoop');nc=next(x for x in ast.parse(newloop).body if isinstance(x,ast.ClassDef) and x.name=='ObservationTaskLoop')
    of=next(x for x in oc.body if isinstance(x,ast.FunctionDef) and x.name=='_ordinary_update_from_trace');nf=next(x for x in nc.body if isinstance(x,ast.FunctionDef) and x.name=='_update_from_observed_trace')
    normalized=[x.body[0] if isinstance(x,ast.If) and isinstance(x.test,ast.Name) and x.test.id=='advance_main' else x for x in nf.body]
    assert ast.dump(ast.Module(body=of.body,type_ignores=[]))==ast.dump(ast.Module(body=normalized,type_ignores=[]))
    controls=c['recorded_controls']
    for v in controls.values():assert meta(ROOT/v['path'])=={k:v[k] for k in ('bytes','sha256')}
    oldc=load(ROOT/controls['contract.json']['path']);olde=load(ROOT/controls['evidence/exit.json']['path']);oldclaim=load(ROOT/controls['evidence/claim.json']['path'])
    assert olde['child_exit_code']==0 and olde['input_bytes_unchanged'] and oldclaim['input_binding_before']==olde['input_binding_after']
    for path,pin in olde['input_binding_after'].items():
        if path!='experiments/rebuild_status_current.json':assert meta(ROOT/path)==pin,path
    assert all(c[k]==oldc[k] for k in ('schedules','cases','reference'))
    oldrs=[json.loads(x) for x in (ROOT/controls['evidence/raw.jsonl']['path']).read_text(encoding='ascii').splitlines()]
    comparisons=[]
    for arm in c['arms']:
        case=c['roles'][arm]['case'];prefix='Stable' if case=='stable' else 'Drift';own=tasks['stream',arm,None,None]
        for suffix in ('ExperienceNoWrite','ExperienceRepair'):
            refarm=prefix+suffix
            oldmain=[r['payload'] for r in oldrs if r['tag']=='TASK_COMPLETE' and r['context'].get('phase')=='stream' and r['context'].get('arm')==refarm]
            oldpost=[r['payload']['state'] for r in oldrs if r['tag']=='POST_MAIN_LEARNING_STATE' and r['context'].get('arm')==refarm]
            oldextra=[r['payload']['trace'] for r in oldrs if r['tag']=='TASK_RAW' and r['context'].get('phase')=='practice' and r['context'].get('arm')==refarm]
            newextra=[p['trace'] for ctx,p in extra_episodes if ctx['arm']==arm]
            assert len(oldmain)==20 and oldmain[0]['before']['current']==own[0]['before']['current']
            comparisons.append({'case':case,'new_arm':arm,'recorded_arm':refarm,
                 'all20main_raw_identical':[p['trace'] for p in own]==[p['trace'] for p in oldmain],
                 'all20post_extra_R_L_I_identical':all(all(x[f]==y[f] for f in ('current','learning_values','immediate')) for x,y in zip(posts[arm],oldpost)),
                 'all_extra_raw_in_order_identical':newextra==oldextra,
                 'old_private_rollouts':len(oldextra),'new_extra_rollouts':len(newextra),
                 'old_private_Ksteps':sum(len(x['steps']) for x in oldextra),'new_extra_Ksteps':sum(len(x['steps']) for x in newextra),
                 'old_mean_return':sum(return_value(p) for p in oldmain)/20})
    output={'schema':'V142_STDLIB_ORDINARY_EXTRA_REVIEW','complete':True,'native_first_exit':0,'native_counts':final['counts'],'records':len(rs),
        'input_pins':len(claim['input_binding_before']),'main_tasks':len(main_episodes),'extra_tasks':len(extra_episodes),'native_ordinary_updates':ordinary,
        'external_ordinary_updates':len(ingestions),'native_policy_TX':ordinary_policy,'external_policy_TX':external_policy,'issued_observations':len(issued),
        'duplicate_rejections':len(duplicates),'ingestions':ingestions,'streams':summaries,'comparisons_to_v141':comparisons,
        'diagnostic_calls':0,'feedback_main_writes':0,'candidate_proposals':0,'Mtraining':0,'original_ordinary_math_AST_exact_except_clock':True,
        'main_Ksteps':sum(len(p['trace']['steps']) for ctx,p in main_episodes),'extra_Ksteps':sum(len(p['trace']['steps']) for ctx,p in extra_episodes),
        'raw_file':meta(HERE/'evidence/raw.jsonl'),'old_checker_or_native_reruns':0,'scientific_qualification':False}
    save(HERE/'stored_audit_result.json',output);save(out/'exit.json',{'complete':True,'completed_at_utc':datetime.now(timezone.utc).isoformat(),'result':meta(HERE/'stored_audit_result.json')})
    print(json.dumps({'complete':True,'native_counts':final['counts'],'records':len(rs),'extra_tasks':len(extra_episodes),'external_updates':len(ingestions),'comparisons':comparisons,
        'summary':[{k:(number(v) if isinstance(v,dict) and 'binary64_hex' in v else v) for k,v in x.items() if k in ('arm','successes','return_mean','extra_episodes')} for x in summaries]},sort_keys=True))

if __name__=='__main__':main()
