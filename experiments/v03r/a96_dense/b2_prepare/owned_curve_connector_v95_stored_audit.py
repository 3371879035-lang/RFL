"""Independent stdlib stored-content audit. No RFL/old test/checker imports."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = ROOT/'experiments/v03r/a96_dense/b2_prepare/owned_curve_connector_v95'


def load(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def value(v):
    return float.fromhex(v['binary64_hex'])


def state(s):
    return tuple(s[k] for k in ('x', 'y', 't', 'kappa', 'phi'))


def address(a, numeric=True):
    return state(a['state'])+(a['z'], a['m'])+((a['a'],) if numeric else ())


def qtable(stores):
    return {address(x['address']): value(x['value']) for x in stores['Q']}


def dtable(stores):
    return {address(x['address'], False): x['value'] for x in stores['D']}


def numeric_eq(a, b):
    return {k:v.hex() for k,v in a.items()} == {k:v.hex() for k,v in b.items()}


def main():
    started = datetime.now(timezone.utc).isoformat()
    contract = load(HERE/'contract.json'); claim = load(HERE/'evidence/claim.json'); exit_record = load(HERE/'evidence/exit.json')
    assert claim['input_binding_before'] == exit_record['input_binding_after']
    for name, pin in claim['input_binding_before'].items():
        p = ROOT/name
        assert p.stat().st_size == pin['bytes'] and sha(p) == pin['sha256'], name
    for name in ('stdout', 'stderr'):
        p = HERE/'evidence'/f'{name}.log'
        assert p.stat().st_size == exit_record[name]['bytes'] and sha(p) == exit_record[name]['sha256']
    records = []
    for line in (HERE/'evidence/stdout.log').read_text(encoding='utf-8').splitlines():
        d = json.loads(line)
        assert json.dumps(d,sort_keys=True,separators=(',',':'),ensure_ascii=True) == line
        records.append(d)
    tagged = lambda tag:[d['payload'] for d in records if d['tag'] == tag]
    results = tagged('RESULT'); assert len(results) == 1
    result = results[0]
    rows = {}
    for line in (ROOT/contract['reference_input']['path']).read_text(encoding='utf-8').splitlines():
        if line.startswith('DECISION_CONTEXT='):
            d= json.loads(line.split('=',1)[1]); rows[tuple(d['context'])] = {a:float.fromhex(v) for a,v in d['q_row_hex']}
    assert len(rows) == 13824
    raw = tagged('RAW_ROLLOUT'); raw_steps = tagged('RAW_STEP')
    assert len(raw) == result['counts'].get('rollout',0)
    assert len(raw_steps) == result['counts'].get('step',0)
    assert sum(len(t['steps']) for t in raw) == len(raw_steps)
    pending, grouped = [], []
    for record in records:
        if record['tag'] == 'RAW_STEP': pending.append(record['payload'])
        elif record['tag'] == 'RAW_ROLLOUT':
            t=record['payload']; assert [p['result'] for p in pending] == t['steps']
            assert pending and pending[-1]['result']['terminal']
            for i,p in enumerate(pending):
                assert p['pre_state']['t'] == i and p['result']['state']['t'] == i+1
                if i: assert p['pre_state'] == pending[i-1]['result']['state'] and p['pre_control'] == pending[i-1]['result']['control']
            assert state(pending[0]['pre_state'])[:3] == (0,2,0)
            assert pending[0]['pre_control'] == {'z':t['option_in_force'],'m':0}
            grouped.append(pending); pending=[]
    assert not pending
    raw_content = [json.dumps(t,sort_keys=True,separators=(',',':')) for t in raw]
    td_count, numeric_changed, policy_changed = 0,0,0
    for receipt in tagged('CORE_EPISODE'):
        assert json.dumps(receipt['trace'],sort_keys=True,separators=(',',':')) in raw_content
        before, after = receipt['before'],receipt['after']
        assert before['immediate'] == after['immediate']
        assert before['current']['P'] == after['current']['P'] and before['current']['X'] == after['current']['X']
        assert before['completed_episodes'] == receipt['epoch'] and after['completed_episodes'] == receipt['epoch']+1
        numeric = before['current'] if before['mode']=='dq' else before['learning_values']
        frozen, work = qtable(numeric),qtable(numeric)
        d_before = dtable(before['current']); p_before = {x['address']:x['value'] for x in before['current']['P']}
        inp=receipt['episode']; s=(0,2,0,inp['kappa'],inp['tape']['phase']); z,m=receipt['trace']['option_in_force'],0
        assert z == p_before.get(inp['proposal'],inp['proposal'])
        order, expected_edits, visited = [],{},[]
        calls = []
        for i, step in enumerate(receipt['trace']['steps']):
            row=rows[s+(z,m)]; legal=sorted(row)
            coin=inp['coins'][i]; explore=coin*10 < 1*(1<<64); calls.append([i,0,0,coin])
            if explore:
                limit=(1<<64)-((1<<64)%len(legal))
                for c,draw in enumerate(inp['rejections'][i]):
                    calls.append([i,1,c,draw])
                    if draw < limit:
                        expected=legal[draw%len(legal)]; break
                else: raise AssertionError('captured completed episode exhausted coordinate draws')
            elif before['mode']=='patch-adaptive' and s+(z,m) in d_before:
                expected=d_before[s+(z,m)]
            else:
                values={a:frozen.get(s+(z,m,a),row[a]) for a in legal}; best=max(values.values())
                expected=min(a for a,v in values.items() if v==best)
            assert step['a_cmd']==expected
            assert receipt['draws'][i] == {'i':i,'explore':explore,'admissible':legal,'a_cmd':expected}
            q=s+(z,m,step['a_cmd']); current=work.get(q,row[step['a_cmd']]); target=value(step['reward'])
            ns=state(step['state']); nz,nm=step['control']['z'],step['control']['m']
            if not step['terminal']:
                nrow=rows[ns+(nz,nm)]
                target += max(work.get(ns+(nz,nm,a),v) for a,v in nrow.items())
            updated=current+0.5*(target-current); work[q]=updated; expected_edits[q]=updated
            if q not in order: order.append(q)
            visited.append(s+(z,m)); s,z,m=ns,nz,nm
        assert calls == receipt['coordinates']
        assert [address(x['address']) for x in receipt['numeric_edits']] == order
        assert numeric_eq({address(x['address']):value(x['value']) for x in receipt['numeric_edits']},expected_edits)
        sparse={q:v for q,v in work.items() if v != rows[q[:-1]][q[-1]]}
        actual=qtable(after['current'] if before['mode']=='dq' else after['learning_values'])
        assert numeric_eq(actual,sparse)
        if not numeric_eq(frozen,actual): numeric_changed+=1
        expected_policy=[]; expected_d=dict(d_before); seen=set()
        if before['mode']=='patch-adaptive':
            assert not before['current']['Q'] and not after['current']['Q']
            for context in visited:
                if context in d_before and context not in seen:
                    rr=rows[context]; vals={a:sparse.get(context+(a,),v) for a,v in rr.items()}; best=max(vals.values())
                    chosen=min(a for a,v in vals.items() if v==best)
                    expected_policy.append((context,chosen)); expected_d[context]=chosen; seen.add(context)
            assert dtable(after['current']) == expected_d
        else: assert not receipt['policy_improvement_edits'] and not after['current']['D']
        actual_policy=[(address(x['address'],False),x['value']) for x in receipt['policy_improvement_edits']]
        assert actual_policy == expected_policy
        policy_changed += sum(d_before.get(c) != v for c,v in expected_policy)
        td_count += 1
    curves=tagged('COMPLETED_ROLE_CURVE')
    summary=[]
    for item in curves:
        record=item['audit']; cps=record['checkpoints']; train=record['training']
        assert [p['epoch'] for p in cps] == [0,1,2,3] and [p['epoch'] for p in train] == [0,1,2]
        assert all(train[i]['after']['current']==train[i+1]['before']['current'] and
                   train[i]['after']['learning_values']==train[i+1]['before']['learning_values'] for i in (0,1))
        means=[]
        for point in cps:
            assert len(point['traces']) == 2
            total=0.0
            for trace in point['traces']:
                assert json.dumps(trace,sort_keys=True,separators=(',',':')) in raw_content
                total += float(sum(value(s['reward']) for s in trace['steps']))
            mean=total/2; assert mean.hex()==point['mean_hex']; means.append(mean)
        origin=record['full_pair_after']['origin']
        assert origin['engineering_plan']['engineering_bank_indices']==[16,64]
        assert origin['engineering_plan']['sample']==[[0,2,0,52,0],[1,2,0,28,0]]
        assert origin['engineering_plan']['v_pre_hex']==float(contract['shared_v_pre']).hex()
        for initial,current in zip(origin['initial_composites'],record['full_pair_after']['ordered_composites']):
            assert initial['immediate']==current['immediate']
            assert initial['current']['P']==current['current']['P'] and initial['current']['X']==current['current']['X']
        summary.append({'mode':item['mode'],'role':record['role'],'ordered_values':means,
                        'ordered_value_hex':[m.hex() for m in means],
                        'numeric_entry_counts':[len((r['after']['current'] if item['mode']=='dq' else r['after']['learning_values'])['Q']) for r in train]})
    views=tagged('EXTERNAL_CURVE_VIEW')
    assert len(views)==len(curves)
    for item, observed in zip(views,curves):
        p=item['projection']; assert set(p)=={'fields','episodes','values','pre_level','t_max'}
        assert set(p['fields'])=={'future_rewards','future_outcomes','future_trajectories','future_actions','future_observations'}
        assert p['episodes']==[0,1,2,3] and p['t_max']==3 and value(p['pre_level'])==contract['shared_v_pre']
        expected={k:[] for k in p['fields']}
        means=[]
        for cp in observed['audit']['checkpoints']:
            ts=cp['traces']; means.append({'binary64_hex':cp['mean_hex']})
            expected['future_rewards'].append([[s['reward'] for s in t['steps']] for t in ts])
            expected['future_outcomes'].append([[s['outcome'] for s in t['steps']] for t in ts])
            expected['future_trajectories'].append([[s['state'] for s in t['steps']] for t in ts])
            expected['future_actions'].append([[s['a_cmd'] for s in t['steps']] for t in ts])
            expected['future_observations'].append([[None for _s in t['steps']] for t in ts])
        assert p['fields']==expected and p['values']==means
    inventory=tagged('ACTUAL_LOADED_SOURCE_INVENTORY'); assert len(inventory)==1
    assert all(n in claim['input_binding_before'] and claim['input_binding_before'][n]['sha256']==h for n,h in inventory[0].items())
    assert result['counts'].get('forbidden',0)==0
    if exit_record['child_exit_code']==0:
        assert result['tests']==4 and result['failures']==result['errors']==result['skips']==0
        assert len(curves)==4 and td_count==12 and len(tagged('CHECKPOINT_BANK'))==16
        assert len(tagged('PARTIAL_CURVE_FAILURE'))==1 and len(tagged('PARTIAL_ONCE_AND_RESTORE'))==1
        assert len(tagged('EXTERNAL_FORGED_FEATURE_REJECTED'))==4
        assert len(raw)==47 and len(tagged('NATIVE_B1_RETURN'))==6
    out={'status':'V95_STORED_MULTI_EPOCH_AND_EXTERNAL_CONTENT_AUDITED_NOT_SCIENCE',
         'native_exit_preserved':exit_record['child_exit_code'],'inputs':len(claim['input_binding_before']),
         'records':len(records),'raw_rollouts':len(raw),'raw_steps':len(raw_steps),
         'TD_episodes_verified':td_count,'episodes_with_numeric_content_change':numeric_changed,
         'literal_policy_changes':policy_changed,'curves':summary,'tag_inventory':dict(Counter(x['tag'] for x in records)),
         'actual_loaded_sources_bound':True,'keyed_stream_executed':False,'RFL_or_old_checker_execution':False,
         'runtime_identity_reconstructed':False,'scientific_qualification':False,
         'audit_source_sha256':sha(Path(__file__)),'started_at_utc':started,
         'completed_at_utc':datetime.now(timezone.utc).isoformat()}
    with (HERE/'stored_audit_result.json').open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(out,stream,sort_keys=True,separators=(',',':'),ensure_ascii=True); stream.write('\n')
    print(json.dumps(out,sort_keys=True,ensure_ascii=True))


if __name__ == '__main__':
    main()
