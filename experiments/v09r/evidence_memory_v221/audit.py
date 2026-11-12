"""Stdlib inspection of the complete actual record, no model execution."""
from pathlib import Path
import hashlib,json,math
HERE=Path(__file__).resolve().parent;CAP=HERE/'capture'


def main():
    runs={};checks=[];lines=0
    with (CAP/'events.jsonl').open(encoding='utf-8') as stream:
        for row in map(json.loads,stream):
            lines+=1;kind=row['kind']
            if kind=='check':assert row['passed'];checks.append(row);continue
            rid=row['run_id']
            if kind=='run_start':runs[rid]={'start':row,'external':[],'events':[],'decisions':[],'sessions':{},'examples':[],'imagined':[]};continue
            run=runs[rid]
            if kind=='external_execution':run['external'].append(row)
            elif kind=='event':run['events'].append(row['event'])
            elif kind=='decision':run['decisions'].append(row['decision'])
            elif kind=='session':run['sessions'][row['session']['id']]=row['session']
            elif kind=='comparison_example':run['examples'].append(row)
            elif kind=='imagined':run['imagined'].append(row['transition'])
            elif kind=='run_complete':run['complete']=row
            else:raise AssertionError(kind)
    assert len(checks)==14 and len(runs)==6
    reviews=[];totals=dict(task_steps=0,trial_steps=0,baseline_trials=0,candidate_trials=0,failure_sessions=0,adoptions=0)
    for rid,run in runs.items():
        events=run['events'];external=run['external'];ids=[e['id'] for e in events];by_id={e['id']:e for e in events};positions={i:j for j,i in enumerate(ids)}
        complete=run['complete'];assert len(ids)==len(set(ids))==len(external)==complete['memory_nodes']
        for index,(event,raw) in enumerate(zip(events,external)):
            assert raw['call']==index+1 and event['role']==raw['role']
            for key in ('observation','goal','actions','action_index'):assert event[key]==raw[key]
            for key in ('next_observation','feedback','feedback_mask','goal_met','terminal','cost'):assert event[key]==raw['result'][key]
            assert event['model_id']==run['start']['model_id']
            if event['previous_id'] is not None:
                prev=by_id[event['previous_id']];assert positions[prev['id']]<index and prev['episode']==event['episode']
                assert prev['next_observation']==event['observation'] and prev['step']+1==event['step']
        task_decisions={};adoptions=0;choice_trials=0;adoption_by_session={};current_code=None;current_id=None
        for decision in run['decisions']:
            policy=decision['policy'];choice=decision.get('action',decision.get('choice'));history=decision['history_ids']
            assert all(math.isfinite(v) and v>=0 for v in policy) and abs(sum(policy)-1)<2e-6
            assert 0<=choice<len(policy) and decision['propensity']==policy[choice] and policy[choice]>0
            assert history==ids[:len(history)] and decision['model_id']==run['start']['model_id']
            if decision['kind'] in ('task','trial'):
                event=by_id[decision['event_id']];assert history==ids[:positions[event['id']]]
                assert decision['action']==event['action_index'] and decision['propensity']==event['propensity']
                task_decisions[event['id']]=decision
                if decision['kind']=='task':assert decision['code']==current_code and event['candidate_id']==current_id
            else:
                session=run['sessions'][decision['session_id']];groups=[[] for _ in session['arms']]
                for receipt in session['receipts']:
                    if receipt['event_id'] in history:groups[receipt['arm']].append(receipt['event_id'])
                assert decision['evidence_ids']==groups and all(session['source_event_id'] not in g for g in groups)
                if decision['kind']=='trial_choice':
                    assert 1<=decision['remaining_budget']<=4
                    if choice:
                        receipt=next(r for r in session['receipts'] if r['event_id']==ids[len(history)])
                        assert receipt['arm']==choice-1;choice_trials+=1
                elif decision['kind']=='adoption':
                    assert decision['counts']==list(map(len,groups));adoption_by_session[session['id']]=decision
                    for j,g in enumerate(groups):
                        if j and not g:assert policy[j]==0
                    if choice:
                        assert groups[choice];adoptions+=1;current_code=session['arms'][choice]['code'];current_id=session['arms'][choice]['id']
        assert len(task_decisions)==len(events)
        for session in run['sessions'].values():
            source=by_id[session['source_event_id']];assert source['terminal'] and not source['goal_met'] and source['role']=='task'
            assert session['model_id']==run['start']['model_id'] and session['active']
            original=task_decisions[source['id']]['code'];assert session['arms'][0]['code']==(original if original is not None else [0.]*len(session['arms'][0]['code']))
            assert len(session['receipts'])<=4 and len({r['event_id'] for r in session['receipts']})==len(session['receipts'])
            for candidate in session['arms']:
                raw={k:v for k,v in candidate.items() if k!='digest'}
                assert hashlib.sha256(json.dumps(raw,sort_keys=True).encode()).hexdigest()==candidate['digest']
                assert candidate['source_event_id']==source['id'] and candidate['history_ids']==ids[:positions[source['id']]+1]
            for receipt in session['receipts']:
                candidate=session['arms'][receipt['arm']];event=by_id[receipt['event_id']]
                assert event['role']=='trial' and event['candidate_id']==candidate['id']==receipt['candidate_id']
                assert receipt['candidate_digest']==candidate['digest'] and receipt['model_id']==event['model_id']==session['model_id']
                assert event['observation']==source['observation'] and event['goal']==source['goal'] and event['actions']==source['actions']
                assert task_decisions[event['id']]['code']==candidate['code'] and task_decisions[event['id']]['arm']==receipt['arm']
            assert session['id'] in adoption_by_session
        for example in run['examples']:
            a,b=example['target_ids'];cut=min(positions[a],positions[b]);assert example['input_history_ids']==ids[:cut]
            assert a not in example['input_history_ids'] and b not in example['input_history_ids']
            assert all(i in example['input_history_ids'] for g in example['input_evidence_ids'] for i in g)
            assert example['public_goal_difference']==float(by_id[a]['goal_met'])-float(by_id[b]['goal_met'])
        receipt_list=[r for s in run['sessions'].values() for r in s['receipts']]
        actual={'task_steps':sum(e['role']=='task' for e in events),'trial_steps':sum(e['role']=='trial' for e in events),
                'baseline_trials':sum(r['arm']==0 for r in receipt_list),'candidate_trials':sum(r['arm']!=0 for r in receipt_list),
                'failure_sessions':len(run['sessions']),'adoptions':adoptions}
        assert actual==complete['counters'] and actual['task_steps']==36 and actual['trial_steps']==choice_trials==len(receipt_list)
        assert len(run['sessions'])==sum(e['role']=='task' and e['terminal'] and not e['goal_met'] for e in events)
        assert complete['main_successes']==sum(e['role']=='task' and e['goal_met'] for e in events)
        assert complete['model_before']==complete['model_after']==run['start']['model_id'] and complete['optimizer_steps']==0
        for obj in run['imagined']:assert obj['source_ids']==ids and obj['model_id']==complete['model_after']
        path=CAP/f"memory_{complete['family']}_seed{complete['seed']}.json";raw=path.read_bytes()
        assert hashlib.sha256(raw).hexdigest()==complete['memory_sha256'] and json.loads(raw)['events']==events
        repetitions=sum(len(s['receipts'])-len(set(r['arm'] for r in s['receipts'])) for s in run['sessions'].values())
        assert complete['repeated_arm_trials']==repetitions and complete['comparison_examples']==len(run['examples'])
        for k,v in actual.items():totals[k]+=v
        reviews.append({'run_id':rid,'actual_facts':len(events),'complete_trial_receipts':len(receipt_list),'repeated_arm_trials':repetitions,
                        'comparison_examples':len(run['examples']),'review_passed':True})
    result={'status':'STORED_REVIEW_PASSED','jsonl_records':lines,'checks':len(checks),'runs':reviews,'counts':totals,
            'environment_calls':totals['task_steps']+totals['trial_steps'],'optimizer_steps':0,
            'limitations':'Stored stdlib record/identity/chronology/evidence review, not independent scientific validation or learned performance.'}
    with (CAP/'stored_audit.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps({k:v for k,v in result.items() if k!='runs'},indent=2))


if __name__=='__main__':main()
