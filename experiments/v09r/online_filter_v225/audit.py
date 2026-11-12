"""Independent stdlib recurrence/count audit; no neural model or environment execution."""
from pathlib import Path
import hashlib
import json
import math
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[2]; CAP = HERE/'capture'


def close(a, b, tol=1e-6):
    assert math.isclose(a, b, rel_tol=tol, abs_tol=tol), (a, b)


def logsumexp(x):
    m = max(x)
    return m+math.log(sum(math.exp(v-m) for v in x))


def internal_probability(thought):
    value = 0.; allocated = 0
    assert all(len(row) == 4 for row in thought['noise_tape']['action'])
    for decision in thought['decisions']:
        for available, keep, probability in zip(decision['available'], decision['continue'], decision['continue_probability']):
            if available: value += math.log(probability if keep else 1-probability)
            else: assert not keep
        if 'action' in decision:
            allocated += 32
            for keep, action, policy in zip(decision['continue'], decision['action'], decision['policy']):
                close(sum(policy), 1.)
                if keep: value += math.log(policy[action])
    close(value, thought['internal_log_probability'], 1e-5)
    assert allocated == thought['allocated_particle_rows']
    for i, node in enumerate(thought['nodes']):
        if node['parent'] is not None:
            parent = thought['nodes'][node['parent']]
            assert node['parent'] < i and parent['next_observation'] == node['observation'] and not parent['terminal']
            assert parent['arm'] == node['arm'] and parent['hypothesis'] == node['hypothesis']
        for v, mask in zip(node['innovation'], node['innovation_mask']):
            if not mask: assert v == 0.
    return value


def main():
    claim = json.loads((CAP/'claim.json').read_text())
    for name, digest in claim['input_sha256'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == digest, name
    rows = []
    with (CAP/'events.jsonl').open(encoding='utf-8') as stream:
        for line in stream:
            assert line.endswith('\n'); rows.append(json.loads(line))
    summary = json.loads((CAP/'summary.json').read_text()); contract = json.loads((HERE/'contract.json').read_text())
    totals = dict(actual_events=0, actual_filter_updates=0, main_steps=0, trials=0, post_successes=0,
                  imagined_nodes=0, particle_rows=0, diagnostic_imagined_nodes=0, diagnostic_particle_rows=0, decisions=0)
    max_recurrence_error = 0.
    for run in summary['runs']:
        seed = run['seed']; rid = f'v225/seed{seed}'
        trace = json.loads((CAP/f'trace_seed{seed}.json').read_text())
        credit = json.loads((CAP/f'credit_seed{seed}.json').read_text())
        diag = json.loads((CAP/f'diagnostic_seed{seed}.json').read_text())
        captured = [r for r in rows if r['run_id'] == rid]
        actual = [r for r in captured if r['kind'] == 'external_execution']
        events = trace['memory']['events']; ids = [e['id'] for e in events]; by_id = dict(zip(ids, events))
        assert len(actual) == len(events) == run['actual_calls'] == len(set(ids))
        assert [r['event'] for r in captured if r['kind'] == 'actual_event'] == events
        assert [r['decision'] for r in captured if r['kind'] == 'decision'] == trace['decisions']
        assert [r['thought'] for r in captured if r['kind'] == 'thought'] == trace['thoughts']
        assert [r['receipt'] for r in captured if r['kind'] == 'filter_receipt'] == trace['filter_receipts']
        assert run['model_before'] == run['model_after'] == trace['model_id']
        fr = {r['event_id']: r for r in trace['filter_receipts']}
        assert len(fr) == len(events) == run['actual_filter_updates']
        for i, (external, event) in enumerate(zip(actual, events)):
            assert external['call'] == i+1 and external['action_index'] == event['action_index']
            for key in ('observation', 'actions', 'goal'): assert external[key] == event[key]
            for key, value in external['result'].items(): assert value == event[key]
            x = event['observation']; a = event['actions'][event['action_index']]; nxt = event['next_observation']
            for j in range(16): close(nxt[j], .8*x[j]+.08*a[j % 8]+external['noise'][j], 1e-12)
            assert all(-.01 <= n <= .01 for n in external['noise'])
            assert event['terminal'] == (external['step'] == external['horizon']-1)
            assert event['goal_met'] == (event['terminal'] and nxt[0] > .15)
            fb = event['feedback']; mask = event['feedback_mask']; assert mask[:6] == [True]*6
            for got, expected in zip(fb[:6], [float(event['goal_met']), nxt[0], nxt[0]-x[0], 1., event['action_index'], float(event['terminal'])]):
                close(got, expected, 1e-12)
            for j in (6, 7):
                if not mask[j]: assert fb[j] == 0.
            if mask[6]: assert abs(fb[6]-nxt[0]) <= .1+1e-12
            if mask[7]: assert abs(fb[7]-(nxt[1]-x[1])) <= .1+1e-12
            assert event['cost'] == 1. and event['source'] == 'environment'
            receipt = fr[event['id']]; before = receipt['before']; after = receipt['after']
            assert before['anchor_ids']+before['used_ids'] == ids[:i]
            assert not (set(before['anchor_ids']) & set(before['used_ids']))
            assert after['anchor_ids'] == before['anchor_ids'] and after['used_ids'] == before['used_ids']+[event['id']]
            assert before['world_id'] == after['world_id'] == trace['world_id']
            assert before['terminal'] is False and after['terminal'] == event['terminal']
            if event['previous_id'] is None:
                assert before['used_ids'] == [] and before['anchor_ids'] == ids[:i] and before['log_evidence'] == 0.
            else:
                assert event['previous_id'] == ids[i-1]
                previous = by_id[event['previous_id']]; old_state = fr[event['previous_id']]['after']
                assert previous['next_observation'] == event['observation'] and not previous['terminal']
                assert previous['episode'] == event['episode'] and previous['step']+1 == event['step']
                assert before == old_state
            assert receipt['observed_continuous_coordinates'] == 16+sum(mask[6:])
            close(logsumexp(before['log_weights']), 0., 1e-9)
            component = receipt['component_log_likelihood']
            for j in range(8):
                close(component[j], receipt['mask_log_likelihood'][j]+receipt['discrete_log_likelihood'][j]+receipt['continuous_log_likelihood'][j], 1e-5)
            joint = [w+ll for w, ll in zip(before['log_weights'], component)]; logz = logsumexp(joint)
            max_recurrence_error = max(max_recurrence_error, abs(logz-receipt['log_predictive']))
            close(logz, receipt['log_predictive'], 1e-9)
            for got, expected in zip(after['log_weights'], [x-logz for x in joint]): close(got, expected, 1e-9)
            close(after['log_evidence'], before['log_evidence']+logz, 1e-9)
        post_ends = []; task_ids = []
        for episode, horizon in zip(trace['episodes'], contract['source_lengths']):
            source_ids = episode['source_ids']; assert len(source_ids) == horizon
            assert by_id[source_ids[0]]['observation'][0] == -3. and not by_id[source_ids[-1]]['goal_met']
            task_ids.extend(source_ids)
            for j, seq in enumerate(episode['post_task_ids']):
                assert len(seq) == horizon and by_id[seq[0]]['observation'][0] == contract['post_initial_x0'][j]
                assert by_id[seq[-1]]['terminal']; post_ends.append(seq[-1]); task_ids.extend(seq)
            for seq in [source_ids, *episode['post_task_ids']]:
                for step, eid in enumerate(seq): assert len(by_id[eid]['actions']) == contract['action_counts_by_step_cycle'][step % 3]
        assert len(task_ids) == len(set(task_ids)) == 36 and set(task_ids) == {e['id'] for e in events if e['role'] == 'task'}
        thoughts = {t['id']: t for t in trace['thoughts']}
        internal = {key: internal_probability(t) for key, t in thoughts.items()}
        seen = []; reward = []; trial_ids = []; used_thoughts = []
        for index, d in enumerate(trace['decisions']):
            assert d['history_ids'] == seen and d['model_id'] == trace['model_id']
            r = [0., 0., 0.]; kind = d['kind']; lp = math.log(d['propensity'])
            choice = d['action'] if kind in ('task', 'trial') else d['choice']
            close(sum(d['policy']), 1.); assert d['propensity'] == d['policy'][choice] > 0.
            if kind in ('task', 'trial'):
                event = events[len(seen)]; assert event['id'] == d['event_id'] and event['propensity'] == d['propensity']
                assert d['conditioning'] == fr[event['id']]['before']
                r[1] = -event['cost']
                if event['id'] in post_ends:
                    assert d['purpose'] == 'post_choice'; r[0] = float(event['goal_met'])/len(post_ends)
                seen.append(event['id'])
                if kind == 'trial': trial_ids.append(event['id'])
            if kind == 'trial_choice':
                t = thoughts[d['thought_id']]; assert t['history_ids'] == seen
                used_thoughts.append(t['id']); r[2] = -t['allocated_particle_rows']; lp += internal[t['id']]
            reward.append(r); close(credit['log_steps'][index], lp, 1e-5)
        assert seen == ids and set(used_thoughts) == set(thoughts) and len(used_thoughts) == len(thoughts)
        receipts = [r for s in trace['sessions'] for r in s['receipts']]
        assert sorted(r['event_id'] for r in receipts) == sorted(trial_ids)
        for s in trace['sessions']:
            generation = trace['generations'][s['id']]
            assert generation['history_ids'] == ids[:ids.index(s['source_event_id'])+1]
            for arm in s['arms']:
                raw = {k: v for k, v in arm.items() if k != 'digest'}
                assert hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest() == arm['digest']
            for r in s['receipts']:
                arm = s['arms'][r['arm']]
                assert r['candidate_digest'] == arm['digest'] and by_id[r['event_id']]['candidate_id'] == arm['id']
        returns = []; cumulative = [0., 0., 0.]
        for r in reversed(reward):
            cumulative = [x+y for x, y in zip(cumulative, r)]; returns.append(cumulative)
        returns.reverse()
        for actual_row, expected_row in zip(credit['reward'], reward):
            for a, b in zip(actual_row, expected_row): close(a, b)
        for actual_row, expected_row in zip(credit['returns'], returns):
            for a, b in zip(actual_row, expected_row): close(a, b)
        assert len(events) == 36+len(trial_ids) and len(trial_ids) <= 4
        internal_probability(diag['thought'])
        state = diag['actual_conditioning']; assert state == fr[diag['source_event_id']]['before']
        for a, b in zip(diag['thought']['root_weights'], state['log_weights']): close(a, math.exp(b), 1e-6)
        assert diag['particle_rows'] == diag['thought']['allocated_particle_rows']
        totals['actual_events'] += len(events); totals['actual_filter_updates'] += len(fr); totals['main_steps'] += 36
        totals['trials'] += len(trial_ids); totals['post_successes'] += sum(by_id[i]['goal_met'] for i in post_ends)
        totals['imagined_nodes'] += sum(len(t['nodes']) for t in thoughts.values())
        totals['particle_rows'] += sum(t['allocated_particle_rows'] for t in thoughts.values())
        totals['diagnostic_imagined_nodes'] += len(diag['thought']['nodes']); totals['diagnostic_particle_rows'] += diag['particle_rows']
        totals['decisions'] += len(trace['decisions'])
    assert totals['actual_events'] == summary['actual_calls'] <= 80 and totals['main_steps'] == 72
    assert totals['actual_events'] == totals['actual_filter_updates'] and totals['diagnostic_particle_rows'] <= 128
    result = dict(status='STORED_DATA_CHECKED', input_pins=len(claim['input_sha256']), jsonl_complete_records=len(rows), totals=totals,
        posterior_recurrence_max_error=max_recurrence_error, future_target_in_prediction_prefix=0, actual_environment_calls=0,
        limits='Stdlib data and recurrence audit; neural likelihood components are logged, not independently re-executed. Not an independent scientific replication.')
    with (CAP/'stored_audit.json').open('x', encoding='utf-8') as f: json.dump(result, f, indent=2)
    print(json.dumps(result, indent=2))


if __name__ == '__main__': main()
