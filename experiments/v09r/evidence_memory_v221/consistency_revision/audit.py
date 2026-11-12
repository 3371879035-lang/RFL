from pathlib import Path
import hashlib,json,math
HERE=Path(__file__).resolve().parent;CAP=HERE/'capture'


def main():
    runs={};checks=[];lines=0
    for row in map(json.loads,(CAP/'events.jsonl').read_text(encoding='utf-8').splitlines()):
        lines+=1;kind=row['kind']
        if kind=='check':assert row['passed'];checks.append(row);continue
        rid=row['run_id']
        if kind=='run_start':runs[rid]={'start':row,'external':[],'events':[],'decisions':[],'sessions':{}};continue
        run=runs[rid]
        if kind=='external_execution':run['external'].append(row)
        elif kind=='event':run['events'].append(row['event'])
        elif kind=='decision':run['decisions'].append(row['decision'])
        elif kind=='session':run['sessions'][row['session']['id']]=row['session']
        elif kind=='run_complete':run['complete']=row
        else:raise AssertionError(kind)
    assert len(checks)==3 and len(runs)==2
    maximum_cycle=0.;total=0;matrix_count=0
    for rid,run in runs.items():
        ids=[e['id'] for e in run['events']];events={e['id']:e for e in run['events']};index={i:j for j,i in enumerate(ids)};complete=run['complete']
        assert len(ids)==len(set(ids))==len(run['external'])==complete['actual_calls'];total+=len(ids)
        for e,x in zip(run['events'],run['external']):
            for key in ('observation','goal','actions','action_index'):assert e[key]==x[key]
            for key in ('next_observation','feedback','feedback_mask','goal_met','terminal','cost'):assert e[key]==x['result'][key]
            assert e['role']==x['role'] and e['model_id']==complete['model_before']
        decisions={};adoptions=0;chosen_trials=0
        for d in run['decisions']:
            p=d['policy'];choice=d.get('action',d.get('choice'));assert abs(sum(p)-1)<2e-6 and p[choice]==d['propensity']>0 and all(math.isfinite(v) and v>=0 for v in p)
            assert d['history_ids']==ids[:len(d['history_ids'])]
            if d['kind'] in ('task','trial'):
                assert d['history_ids']==ids[:index[d['event_id']]];decisions[d['event_id']]=d
            else:
                s=run['sessions'][d['session_id']];groups=[[] for _ in s['arms']]
                for r in s['receipts']:
                    if r['event_id'] in d['history_ids']:groups[r['arm']].append(r['event_id'])
                assert groups==d['evidence_ids'] and all(s['source_event_id'] not in g for g in groups)
                if d['kind']=='trial_choice' and choice:
                    receipt=next(r for r in s['receipts'] if r['event_id']==ids[len(d['history_ids'])]);assert receipt['arm']==choice-1;chosen_trials+=1
                if d['kind']=='adoption':
                    matrix_count+=1;m=d['contrast_mean'];v=d['contrast_variance'];assert d['counts']==list(map(len,groups))
                    for a in range(len(m)):
                        assert m[a][a]==v[a][a]==0
                        for b in range(len(m)):
                            assert m[a][b]==-m[b][a] and v[a][b]==v[b][a] and (a==b or v[a][b]>0)
                            for c in range(len(m)):maximum_cycle=max(maximum_cycle,abs(m[a][b]+m[b][c]-m[a][c]))
                    if choice:assert groups[choice];adoptions+=1
                    for j,g in enumerate(groups):
                        if j and not g:assert p[j]==0
        receipts=[r for s in run['sessions'].values() for r in s['receipts']]
        for s in run['sessions'].values():
            source=events[s['source_event_id']];assert source['terminal'] and not source['goal_met'] and len(s['receipts'])<=4
            for candidate in s['arms']:
                raw={k:v for k,v in candidate.items() if k!='digest'};assert hashlib.sha256(json.dumps(raw,sort_keys=True).encode()).hexdigest()==candidate['digest']
            for r in s['receipts']:
                e=events[r['event_id']];candidate=s['arms'][r['arm']]
                assert e['candidate_id']==r['candidate_id']==candidate['id'] and r['candidate_digest']==candidate['digest']
                assert e['role']=='trial' and e['observation']==source['observation'] and e['model_id']==r['model_id']==s['model_id']
                assert decisions[e['id']]['code']==candidate['code']
        actual={'task_steps':sum(e['role']=='task' for e in events.values()),'trial_steps':len(receipts),'baseline_trials':sum(r['arm']==0 for r in receipts),
                'candidate_trials':sum(r['arm']!=0 for r in receipts),'failure_sessions':len(run['sessions']),'adoptions':adoptions}
        assert actual==complete['counts'] and actual['task_steps']==12 and actual['trial_steps']==chosen_trials
        assert complete['model_before']==complete['model_after'] and complete['optimizer_steps']==0
        assert json.loads((CAP/f"memory_seed{complete['seed']}.json").read_text())['events']==run['events']
    assert maximum_cycle<1e-7
    result={'status':'CONSISTENT_HEAD_STORED_REVIEW_PASSED','checks':len(checks),'jsonl_records':lines,'actual_calls':total,
            'actual_adoption_matrices':matrix_count,'maximum_cycle_residual':maximum_cycle,'optimizer_steps':0,
            'scope':'Stored actual consequences, all trial records, eligibility, new comparison matrices; not trained quality or independent scientific review'}
    with (CAP/'stored_audit.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
