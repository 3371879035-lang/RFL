"""Stored-record review using stdlib only. Not an independent scientific review."""
from pathlib import Path
import hashlib,json,math
HERE=Path(__file__).resolve().parent


def main():
    capture=HERE/'capture';runs={};checks=[];lines=0
    with (capture/'events.jsonl').open(encoding='utf-8') as stream:
        for line in stream:
            lines+=1;row=json.loads(line);kind=row['kind']
            if kind=='check':assert row['passed'];checks.append(row);continue
            rid=row['run_id']
            if kind=='run_start':runs[rid]={'start':row,'external':[],'events':[],'decisions':[],'candidates':{},'receipts':{},'imagined':[]};continue
            run=runs[rid]
            if kind=='external_execution':run['external'].append(row)
            elif kind=='event':run['events'].append(row['event'])
            elif kind=='decision':run['decisions'].append(row['decision'])
            elif kind=='candidate':run['candidates'][row['candidate']['id']]=row
            elif kind=='receipt':run['receipts'][row['receipt']['candidate_id']]=row['receipt']
            elif kind=='imagined':run['imagined'].append(row['transition'])
            elif kind=='run_complete':run['complete']=row
            else:raise AssertionError(kind)
    assert len(checks)==14 and len(runs)==12
    counts={'tasks':0,'trials':0,'reflections':0,'adoptions':0,'imagined':0};reviews=[]
    for rid,run in runs.items():
        events=run['events'];external=run['external'];complete=run['complete'];event_ids=[e['id'] for e in events];by_id={e['id']:e for e in events}
        assert len(event_ids)==len(set(event_ids))==len(external)==complete['memory_nodes']
        for index,(event,raw) in enumerate(zip(events,external)):
            assert raw['call']==index+1
            for key in ('observation','goal','actions','action_index'):assert event[key]==raw[key]
            for key in ('next_observation','feedback','feedback_mask','goal_met','terminal','cost'):assert event[key]==raw['result'][key]
            assert event['model_id']==run['start']['model_id']
        task_decisions={};trial_choice_count=0;adoptions=0;trial_choices=[]
        for decision in run['decisions']:
            p=decision['policy'];choice=decision.get('action',decision.get('choice'))
            assert all(math.isfinite(v) and v>=0 for v in p) and abs(sum(p)-1)<2e-6
            assert 0<=choice<len(p) and decision['propensity']==p[choice] and p[choice]>0
            history=decision['history_ids'];assert history==event_ids[:len(history)]
            if decision['kind'] in ('task','trial'):
                event=by_id[decision['event_id']];idx=event_ids.index(event['id']);assert history==event_ids[:idx]
                assert decision['action']==event['action_index'] and decision['propensity']==event['propensity']
                task_decisions[event['id']]=decision
            elif decision['kind']=='trial_choice':
                trial_choice_count+=1;assert not by_id[decision['source_event_id']]['goal_met'];trial_choices.append(decision)
            elif decision['kind']=='adoption':
                for j,ok in enumerate(decision['eligible']):
                    cid=decision['candidate_ids'][j]
                    if ok:assert cid in run['receipts'] and run['receipts'][cid]['event_id'] in history
                    else:assert p[j+1]==0
                if choice:assert decision['eligible'][choice-1];adoptions+=1
        assert len(task_decisions)==len(events)
        for cid,receipt in run['receipts'].items():
            candidate=run['candidates'][cid];raw_candidate=candidate['candidate']
            digest=hashlib.sha256(json.dumps(raw_candidate,sort_keys=True).encode()).hexdigest()
            assert digest==candidate['digest']==receipt['candidate_digest']
            event=by_id[receipt['event_id']];assert event['role']=='trial' and event['candidate_id']==cid
            assert receipt['model_id']==event['model_id']==raw_candidate['model_id']==run['start']['model_id']
            assert task_decisions[event['id']]['code']==raw_candidate['code']
            assert not by_id[raw_candidate['source_event_id']]['goal_met']
            assert raw_candidate['history_ids']==event_ids[:len(raw_candidate['history_ids'])]
        for decision in trial_choices:
            assert len(decision['candidate_ids'])==3
            for cid in decision['candidate_ids']:
                c=run['candidates'][cid]['candidate'];assert c['source_event_id']==decision['source_event_id'] and c['history_ids']==decision['history_ids']
            if decision['choice']:assert decision['candidate_ids'][decision['choice']-1] in run['receipts']
        actual={'tasks':sum(e['role']=='task' for e in events),'trials':sum(e['role']=='trial' for e in events),
                'reflections':trial_choice_count,'adoptions':adoptions,'imagined':len(run['imagined'])}
        assert actual==complete['counters'] and actual['tasks']==16 and actual['trials']<=16
        assert actual['reflections']==sum(e['role']=='task' and not e['goal_met'] for e in events)
        assert complete['main_successes']==sum(e['role']=='task' and e['goal_met'] for e in events)
        assert complete['trial_successes']==sum(e['role']=='trial' and e['goal_met'] for e in events)
        assert complete['model_before']==complete['model_after']==run['start']['model_id'] and complete['optimizer_steps']==0
        for imagined in run['imagined']:
            assert imagined['source_ids']==event_ids and imagined['model_id']==complete['model_after']
            assert all(v>0 and math.isfinite(v) for v in imagined['next_variance']+imagined['feedback_variance'])
        bank_path=capture/f"memory_{complete['family']}_seed{complete['seed']}.json"
        bank_bytes=bank_path.read_bytes();bank=json.loads(bank_bytes)
        assert hashlib.sha256(bank_bytes).hexdigest()==complete['memory_sha256'] and bank['events']==events
        for k,v in actual.items():counts[k]+=v
        reviews.append({'run_id':rid,'factual_nodes':len(events),'candidate_receipts':len(run['receipts']),'all_checks':True})
    result={'status':'STORED_RECORD_REVIEW_PASSED','canonical_jsonl_lines':lines,'formula_interface_checks':len(checks),'runs':reviews,
            'counts':counts,'factual_nodes':counts['tasks']+counts['trials'],'optimizer_steps':0,
            'limits':'stdlib stored identity/count/chronology review; not independent scientist, policy quality, calibration, or full counterfactual validation'}
    with (capture/'stored_audit.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps({k:v for k,v in result.items() if k!='runs'},indent=2))


if __name__=='__main__':main()
