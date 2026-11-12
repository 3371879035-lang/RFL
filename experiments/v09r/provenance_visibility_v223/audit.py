"""Stdlib receipt and observed/imagination separation review, not model performance review."""
from pathlib import Path
import hashlib,json,math,struct
HERE=Path(__file__).resolve().parent;CAP=HERE/'capture'


def innovations(event,layout):
    values=[];mask=[]
    for i in range(len(layout['primitive_ids'])):
        fields=[j for j,v in enumerate(layout['views']) if v['terms']==[['innovation',i,1.]] and v['constant']==0]
        observed=[event['feedback'][j] for j in fields if event['feedback_mask'][j]]
        assert not observed or all(v==observed[0] for v in observed)
        values.append(observed[0] if observed else 0.);mask.append(bool(observed))
    return values,mask


def review_thought(t,source):
    assert not t['force_continue'] and t['fixed_action'] is None
    weights=t['root_weights'];k=len(weights);arms=len(t['depths']);nodes=t['nodes'];np=len(t['noise_tape']['mask'][0][0])
    assert abs(sum(weights)-1)<2e-6 and all(v>=0 for v in weights)
    keys={(n['arm'],n['hypothesis'],n['depth']):i for i,n in enumerate(nodes)};assert len(keys)==len(nodes)
    alive=[[True]*k for _ in range(arms)];counts=[0]*arms;depths=[0]*arms;batches=0;logp=0.
    for dec in t['decisions']:
        depth=dec['depth'];available=[any(row) for row in alive];assert dec['available']==available
        keep=[available[a] and t['noise_tape']['continue'][depth]<dec['continue_probability'][a] for a in range(arms)];assert keep==dec['continue']
        for a in range(arms):
            if available[a]:logp+=math.log(dec['continue_probability'][a] if keep[a] else 1-dec['continue_probability'][a])
        active=[[v and keep[a] for v in row] for a,row in enumerate(alive)]
        if not any(any(row) for row in active):assert 'action' not in dec;break
        assert dec['active']==active;batches+=1
        for a in range(arms):
            if not keep[a]:continue
            policy=dec['policy'][a];assert abs(sum(policy)-1)<2e-6 and all(v>=0 for v in policy)
            cdf=0.;choice=len(policy)-1
            for i,v in enumerate(policy):
                cdf+=v
                if t['noise_tape']['action'][depth]<=cdf:choice=i;break
            assert choice==dec['action'][a];logp+=math.log(policy[choice]);depths[a]=depth+1
            for ki in range(k):
                if not active[a][ki]:continue
                index=keys[a,ki,depth];node=nodes[index];counts[a]+=1
                mask=[t['noise_tape']['mask'][depth][ki][j]<dec['visibility_probability'][a][ki][j] for j in range(np)]
                terminal=t['noise_tape']['terminal'][depth][ki]<dec['terminal_probability'][a][ki]
                met=t['noise_tape']['goal'][depth][ki]<dec['goal_probability'][a][ki]
                assert node['innovation_mask']==mask==dec['mask'][a][ki]
                assert all(v==0 for v,m in zip(node['innovation'],mask) if not m)
                assert node['terminal']==terminal==dec['terminal'][a][ki] and node['goal_met']==met==dec['goal_met'][a][ki]
                assert node['action_index']==choice and node['original_weight']==weights[ki]
                assert all(math.isfinite(v) and v>0 for v in node['next_variance']+node['innovation_variance'])
                if depth==0:
                    assert node['parent'] is None
                    assert node['observation']==[struct.unpack('f',struct.pack('f',v))[0] for v in source['observation']]
                else:
                    assert 0<=node['parent']<index;parent=nodes[node['parent']]
                    assert (parent['arm'],parent['hypothesis'],parent['depth']+1)==(a,ki,depth)
                    assert parent['next_observation']==node['observation'] and not parent['terminal']
        alive=[[active[a][i] and not dec['terminal'][a][i] for i in range(k)] for a in range(arms)]
    assert counts==t['active_counts'] and depths==t['depths'] and sum(counts)==len(nodes)
    assert batches==t['kernel_batches'] and batches*k*arms==t['allocated_particle_rows']
    assert abs(logp-t['internal_log_probability'])<1e-4*max(1,abs(logp))


def main():
    rows=[json.loads(line) for line in (CAP/'events.jsonl').read_text(encoding='utf-8').splitlines()];runs={};checks=[]
    for row in rows:
        kind=row['kind']
        if kind=='check':assert row['passed'];checks.append(row);continue
        rid=row['run_id']
        if kind=='run_start':runs[rid]={'start':row,'external':[],'events':[],'decisions':[],'sessions':{},'thoughts':{}};continue
        run=runs[rid]
        if kind=='external_execution':run['external'].append(row)
        elif kind=='event':run['events'].append(row['event'])
        elif kind=='decision':run['decisions'].append(row['decision'])
        elif kind=='session':run['sessions'][row['session']['id']]=row['session']
        elif kind=='thought':run['thoughts'][row['thought']['id']]=row['thought']
        elif kind=='run_complete':run['complete']=row
        else:raise AssertionError(kind)
    assert len(runs)==4 and len(checks)==8
    totals=dict(task_steps=0,trial_steps=0,baseline_trials=0,candidate_trials=0,failure_sessions=0,adoptions=0)
    reports=[];updates=0
    for rid,run in runs.items():
        events=run['events'];ids=[e['id'] for e in events];by_id={e['id']:e for e in events};positions={i:j for j,i in enumerate(ids)}
        complete=run['complete'];version=run['start']['model_id'];layout=run['start']['layout'];real_hidden=0
        assert len(ids)==len(set(ids))==len(run['external'])==complete['memory_nodes']
        for index,(e,raw) in enumerate(zip(events,run['external'])):
            assert raw['call']==index+1 and e['role']==raw['role'] and e['model_id']==version
            for key in ('observation','goal','actions','action_index'):assert e[key]==raw[key]
            for key in ('next_observation','feedback','feedback_mask','goal_met','terminal','cost'):assert e[key]==raw['result'][key]
            if e['previous_id'] is not None:
                prev=by_id[e['previous_id']];assert positions[prev['id']]<index and prev['episode']==e['episode']
                assert prev['step']+1==e['step'] and prev['next_observation']==e['observation'] and not prev['terminal']
            u,m=innovations(e,layout);real_hidden+=sum(not v for v in m)
            sources={'next':e['next_observation'],'innovation':u,'goal_met':[float(e['goal_met'])],'terminal':[float(e['terminal'])],
                     'observation':e['observation'],'action':e['actions'][e['action_index']],'action_index':[e['action_index']]}
            for j,view in enumerate(layout['views']):
                if e['feedback_mask'][j]:
                    expected=view['constant']+sum(c*sources[key][i] for key,i,c in view['terms'])
                    assert math.isclose(expected,e['feedback'][j],rel_tol=1e-6,abs_tol=1e-8)
        decisions={};current=None;current_id=None;chosen_trials=0;adoptions=0
        for dec in run['decisions']:
            history=dec['history_ids'];policy=dec['policy'];choice=dec.get('action',dec.get('choice'))
            assert history==ids[:len(history)] and dec['model_id']==version
            assert abs(sum(policy)-1)<2e-6 and all(math.isfinite(v) and v>=0 for v in policy) and dec['propensity']==policy[choice]>0
            if dec['kind'] in ('task','trial'):
                e=by_id[dec['event_id']];assert history==ids[:positions[e['id']]] and dec['action']==e['action_index'] and dec['propensity']==e['propensity']
                decisions[e['id']]=dec
                if dec['kind']=='task':assert dec['code']==current and e['candidate_id']==current_id
                continue
            session=run['sessions'][dec['session_id']];groups=[[] for _ in session['arms']]
            for receipt in session['receipts']:
                if receipt['event_id'] in history:groups[receipt['arm']].append(receipt['event_id'])
            assert groups==dec['evidence_ids'] and all(session['source_event_id'] not in group for group in groups)
            if dec['kind']=='trial_choice':
                thought=run['thoughts'][dec['thought_id']];assert thought['history_ids']==history and thought['evidence_ids']==groups
                assert thought['model_id']==version and thought['session_id']==session['id'] and 1<=dec['remaining_budget']<=2
                if choice:
                    receipt=next(r for r in session['receipts'] if r['event_id']==ids[len(history)]);assert receipt['arm']==choice-1;chosen_trials+=1
            elif dec['kind']=='adoption':
                assert dec['counts']==list(map(len,groups))
                for j,g in enumerate(groups):
                    if j and not g:assert policy[j]==0
                if choice:assert groups[choice];adoptions+=1;current=session['arms'][choice]['code'];current_id=session['arms'][choice]['id']
            else:raise AssertionError(dec['kind'])
        assert len(decisions)==len(events)
        for s in run['sessions'].values():
            source=by_id[s['source_event_id']];assert source['role']=='task' and source['terminal'] and not source['goal_met']
            assert s['model_id']==version and s['active'] and len(s['receipts'])<=2
            for candidate in s['arms']:
                unsigned={key:value for key,value in candidate.items() if key!='digest'}
                assert hashlib.sha256(json.dumps(unsigned,sort_keys=True).encode()).hexdigest()==candidate['digest']
                assert candidate['history_ids']==ids[:positions[source['id']]+1] and candidate['source_event_id']==source['id']
            for receipt in s['receipts']:
                c=s['arms'][receipt['arm']];e=by_id[receipt['event_id']]
                assert receipt['candidate_digest']==c['digest'] and receipt['candidate_id']==c['id']==e['candidate_id']
                assert receipt['model_id']==version and e['role']=='trial' and decisions[e['id']]['code']==c['code']
                assert (e['observation'],e['goal'],e['actions'])==(source['observation'],source['goal'],source['actions'])
            thoughts=[t for t in run['thoughts'].values() if t['session_id']==s['id']]
            assert len(thoughts) in (1,2)
            if len(thoughts)==2:
                added=set(thoughts[1]['history_ids'])-set(thoughts[0]['history_ids']);assert len(added)==1
                assert by_id[next(iter(added))]['role']=='trial';updates+=1
            for t in thoughts:review_thought(t,source)
        receipt_list=[r for s in run['sessions'].values() for r in s['receipts']]
        actual={'task_steps':sum(e['role']=='task' for e in events),'trial_steps':sum(e['role']=='trial' for e in events),
                'baseline_trials':sum(r['arm']==0 for r in receipt_list),'candidate_trials':sum(r['arm']!=0 for r in receipt_list),'failure_sessions':len(run['sessions']),'adoptions':adoptions}
        assert actual==complete['counters'] and actual['task_steps']==9 and actual['trial_steps']==chosen_trials==len(receipt_list)
        assert actual['failure_sessions']==sum(e['role']=='task' and e['terminal'] and not e['goal_met'] for e in events)
        assert complete['model_before']==complete['model_after']==version and complete['optimizer_steps']==0
        nodes=[n for t in run['thoughts'].values() for n in t['nodes']];hidden=sum(not v for n in nodes for v in n['innovation_mask'])
        assert len(nodes)==complete['imagined_nodes'] and hidden==complete['imagined_hidden_innovation_slots'] and real_hidden==complete['real_hidden_innovation_slots']
        assert sum(t['allocated_particle_rows'] for t in run['thoughts'].values())==complete['allocated_particle_rows']
        raw=(CAP/f"memory_{complete['condition']}_seed{complete['seed']}.json").read_bytes();stored=json.loads(raw)
        assert hashlib.sha256(raw).hexdigest()==complete['memory_sha256'] and stored['events']==events and stored['layout']==layout
        for key,value in actual.items():totals[key]+=value
        reports.append({'run_id':rid,'actual_facts':len(events),'imagined_nodes':len(nodes),'hidden_imagined_slots':hidden,'hidden_real_slots':real_hidden})
    summary=json.loads((CAP/'summary.json').read_text());assert summary['counts']==totals and summary['checks_all_passed']
    assert sum(r['actual_facts'] for r in reports)==summary['actual_environment_calls']<=60
    result={'status':'STORED_REVIEW_PASSED','jsonl_records':len(rows),'checks':len(checks),'runs':reports,'counts':totals,'actual_prefix_refreshes':updates,
            'actual_environment_calls':summary['actual_environment_calls'],'optimizer_steps':0,'limits':'Stored identity, provenance and observed-only rollout audit; not independent scientific or calibrated performance evidence.'}
    with (CAP/'stored_audit.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
