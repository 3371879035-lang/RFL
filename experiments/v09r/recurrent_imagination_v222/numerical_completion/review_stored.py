"""Review the already-completed V222 real flow and completed directed checks; no neural execution."""
from pathlib import Path
import hashlib,json,math
HERE=Path(__file__).resolve().parent;CAP=HERE.parent/'capture';OUT=HERE/'capture'


def review_thought(t,source):
    assert not t['force_continue'] and t['fixed_action'] is None
    weights=t['root_weights'];k=len(weights);arms=len(t['depths']);nodes=t['nodes']
    assert all(v>=0 and math.isfinite(v) for v in weights) and abs(sum(weights)-1)<2e-6
    keys={(n['arm'],n['hypothesis'],n['depth']):n for n in nodes};assert len(keys)==len(nodes)
    by_index={id(n):i for i,n in enumerate(nodes)};count=[0]*arms;depths=[0]*arms
    alive=[[True]*k for _ in range(arms)];logp=0.;batches=0
    for dec in t['decisions']:
        depth=dec['depth'];available=[any(row) for row in alive];assert available==dec['available']
        keep=[available[a] and t['noise_tape']['continue'][depth]<dec['continue_probability'][a] for a in range(arms)]
        assert keep==dec['continue']
        for a in range(arms):
            if available[a]:logp+=math.log(dec['continue_probability'][a] if keep[a] else 1-dec['continue_probability'][a])
        active=[[v and keep[a] for v in row] for a,row in enumerate(alive)]
        if not any(any(row) for row in active):assert 'action' not in dec;break
        batches+=1;assert dec['active']==active
        for a in range(arms):
            if not keep[a]:continue
            policy=dec['action_policy'][a];assert abs(sum(policy)-1)<2e-6 and all(v>=0 for v in policy)
            u=t['noise_tape']['action'][depth];cdf=0;choice=len(policy)-1
            for i,prob in enumerate(policy):
                cdf+=prob
                if u<=cdf:choice=i;break
            assert choice==dec['action'][a];logp+=math.log(policy[choice]);depths[a]=depth+1
            for ki in range(k):
                if not active[a][ki]:continue
                n=keys[a,ki,depth];count[a]+=1
                assert n['action_index']==choice and n['original_weight']==weights[ki]
                terminal=t['noise_tape']['terminal'][depth][ki]<dec['terminal_probability'][a][ki]
                assert n['predicted_terminal']==terminal==dec['terminal'][a][ki]
                assert all(v>0 and math.isfinite(v) for v in n['next_variance']+n['feedback_variance'])
                assert all(math.isfinite(v) for v in n['observation']+n['next_observation']+n['feedback'])
                if depth==0:assert n['parent'] is None and n['observation']==source['observation']
                else:
                    assert 0<=n['parent']<by_index[id(n)];prior=nodes[n['parent']]
                    assert (prior['arm'],prior['hypothesis'],prior['depth']+1)==(a,ki,depth)
                    assert not prior['predicted_terminal'] and prior['next_observation']==n['observation']
        alive=[[active[a][ki] and not dec['terminal'][a][ki] for ki in range(k)] for a in range(arms)]
    assert count==t['active_counts'] and depths==t['depths'] and sum(count)==len(nodes)
    assert t['kernel_batches']==batches and t['allocated_particle_rows']==batches*k*arms
    assert abs(logp-t['internal_log_probability'])<1e-4*max(1,abs(logp))


def main():
    rows=[json.loads(line) for line in (CAP/'events.jsonl').read_text(encoding='utf-8').splitlines()]
    runs={};checks=[]
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
    assert len(runs)==4 and len(checks)==1
    totals=dict(task_steps=0,trial_steps=0,baseline_trials=0,candidate_trials=0,failure_sessions=0,adoptions=0)
    reviews=[];refreshed=0
    for rid,run in runs.items():
        events=run['events'];ids=[e['id'] for e in events];by_id={e['id']:e for e in events};positions={i:j for j,i in enumerate(ids)}
        assert len(ids)==len(set(ids))==len(run['external']);done=run['complete']
        version=run['start']['model_id'];task_decisions={};chosen_trials=0;adoptions=0;current=None;current_id=None
        for index,(e,raw) in enumerate(zip(events,run['external'])):
            assert raw['call']==index+1 and e['role']==raw['role'] and e['model_id']==version
            for key in ('observation','goal','actions','action_index'):assert e[key]==raw[key]
            for key in ('next_observation','feedback','feedback_mask','goal_met','terminal','cost'):assert e[key]==raw['result'][key]
            if e['previous_id'] is not None:
                prev=by_id[e['previous_id']];assert positions[prev['id']]<index and prev['episode']==e['episode']
                assert prev['step']+1==e['step'] and prev['next_observation']==e['observation'] and not prev['terminal']
        for dec in run['decisions']:
            policy=dec['policy'];choice=dec.get('action',dec.get('choice'));history=dec['history_ids']
            assert history==ids[:len(history)] and dec['model_id']==version
            assert all(math.isfinite(v) and v>=0 for v in policy) and abs(sum(policy)-1)<2e-6
            assert dec['propensity']==policy[choice]>0
            if dec['kind'] in ('task','trial'):
                e=by_id[dec['event_id']];assert history==ids[:positions[e['id']]] and dec['action']==e['action_index']
                assert dec['propensity']==e['propensity'];task_decisions[e['id']]=dec
                if dec['kind']=='task':assert dec['code']==current and e['candidate_id']==current_id
                continue
            session=run['sessions'][dec['session_id']];groups=[[] for _ in session['arms']]
            for receipt in session['receipts']:
                if receipt['event_id'] in history:groups[receipt['arm']].append(receipt['event_id'])
            assert dec['evidence_ids']==groups and all(session['source_event_id'] not in g for g in groups)
            if dec['kind']=='trial_choice':
                t=run['thoughts'][dec['thought_id']]
                assert t['history_ids']==history and t['evidence_ids']==groups and t['model_id']==version and t['session_id']==session['id']
                assert 1<=dec['remaining_budget']<=2
                if choice:
                    r=next(r for r in session['receipts'] if r['event_id']==ids[len(history)])
                    assert r['arm']==choice-1;chosen_trials+=1
            elif dec['kind']=='adoption':
                assert dec['counts']==list(map(len,groups))
                for j,g in enumerate(groups):
                    if j and not g:assert policy[j]==0
                if choice:
                    assert groups[choice];adoptions+=1;current=session['arms'][choice]['code'];current_id=session['arms'][choice]['id']
            else:raise AssertionError(dec['kind'])
        assert len(task_decisions)==len(events)
        for s in run['sessions'].values():
            source=by_id[s['source_event_id']];assert source['role']=='task' and source['terminal'] and not source['goal_met']
            assert s['model_id']==version and len(s['receipts'])<=2 and s['active']
            for candidate in s['arms']:
                raw={key:value for key,value in candidate.items() if key!='digest'}
                assert hashlib.sha256(json.dumps(raw,sort_keys=True).encode()).hexdigest()==candidate['digest']
                assert candidate['source_event_id']==source['id'] and candidate['history_ids']==ids[:positions[source['id']]+1]
            for receipt in s['receipts']:
                c=s['arms'][receipt['arm']];e=by_id[receipt['event_id']]
                assert receipt['candidate_digest']==c['digest'] and e['candidate_id']==c['id']==receipt['candidate_id']
                assert receipt['model_id']==version and e['role']=='trial' and task_decisions[e['id']]['code']==c['code']
                assert (e['observation'],e['goal'],e['actions'])==(source['observation'],source['goal'],source['actions'])
            ts=[t for t in run['thoughts'].values() if t['session_id']==s['id']]
            assert len(ts) in (1,2)
            if len(ts)==2:
                a,b=ts;added=set(b['history_ids'])-set(a['history_ids']);assert len(added)==1
                assert by_id[next(iter(added))]['role']=='trial';refreshed+=1
            for t in ts:review_thought(t,source)
        receipts=[r for s in run['sessions'].values() for r in s['receipts']]
        actual={'task_steps':sum(e['role']=='task' for e in events),'trial_steps':sum(e['role']=='trial' for e in events),
                'baseline_trials':sum(r['arm']==0 for r in receipts),'candidate_trials':sum(r['arm']!=0 for r in receipts),
                'failure_sessions':len(run['sessions']),'adoptions':adoptions}
        assert actual==done['counters'] and actual['task_steps']==12 and actual['trial_steps']==chosen_trials==len(receipts)
        assert len(run['sessions'])==sum(e['role']=='task' and e['terminal'] and not e['goal_met'] for e in events)
        assert done['main_successes']==sum(e['role']=='task' and e['goal_met'] for e in events)
        assert done['model_before']==done['model_after']==version and done['optimizer_steps']==0
        assert done['imagined_nodes']==sum(len(t['nodes']) for t in run['thoughts'].values())
        assert done['allocated_particle_rows']==sum(t['allocated_particle_rows'] for t in run['thoughts'].values())
        data=(CAP/f"memory_{done['family']}_seed{done['seed']}.json").read_bytes()
        assert hashlib.sha256(data).hexdigest()==done['memory_sha256'] and json.loads(data)['events']==events
        for key,value in actual.items():totals[key]+=value
        reviews.append({'run_id':rid,'actual_facts':len(events),'imagined_nodes':done['imagined_nodes'],'thought_sessions':len(run['thoughts'])})
    directed=json.loads((OUT/'summary.json').read_text());assert len(directed['checks'])==7
    summary={'actual_environment_calls':sum(r['complete']['actual_environment_calls'] for r in runs.values()),
             'imagined_nodes':sum(r['complete']['imagined_nodes'] for r in runs.values())}
    assert totals['task_steps']+totals['trial_steps']==summary['actual_environment_calls']<=80
    assert sum(r['imagined_nodes'] for r in reviews)==summary['imagined_nodes']
    result={'status':'STORED_REVIEW_PASSED','jsonl_records':len(rows),'first_run_passed_checks':len(checks),'directed_checks':len(directed['checks']),'runs':reviews,'counts':totals,
            'actual_environment_calls':summary['actual_environment_calls'],'imagined_nodes':summary['imagined_nodes'],
            'updated_actual_prefixes':refreshed,'optimizer_steps':0,
            'limits':'Stored provenance/chronology/choice/topology audit, not independent validation of imagined predictions or learned performance.'}
    with (OUT/'stored_audit.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
