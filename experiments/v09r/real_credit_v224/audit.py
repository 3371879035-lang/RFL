"""Stored-data audit only: stdlib, no RFL import, model execution or environment calls."""
from pathlib import Path
import hashlib
import json
import math

HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[2]; CAP = HERE/'capture'


def close(a, b, tol=1e-6):
    assert math.isclose(a, b, rel_tol=tol, abs_tol=tol), (a, b)


def main():
    claim = json.loads((CAP/'claim.json').read_text())
    for name, digest in claim['input_sha256'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == digest, name
    rows = []
    with (CAP/'events.jsonl').open(encoding='utf-8') as stream:
        for line in stream:
            assert line.endswith('\n')
            rows.append(json.loads(line))
    summary = json.loads((CAP/'summary.json').read_text()); contract = json.loads((HERE/'contract.json').read_text())
    totals = dict(actual_events=0, main_steps=0, trials=0, successes=0, imagined_nodes=0, particle_rows=0, decisions=0)
    for run in summary['runs']:
        seed = run['seed']; rid = f'v224/seed{seed}'
        trace = json.loads((CAP/f'trace_seed{seed}.json').read_text())
        credit = json.loads((CAP/f'credit_seed{seed}.json').read_text())
        captured = [r for r in rows if r['run_id'] == rid]
        actual = [r for r in captured if r['kind'] == 'external_execution']
        events = trace['memory']['events']; ids = [e['id'] for e in events]; by_id = dict(zip(ids, events))
        assert len(actual) == len(events) == run['actual_calls'] == len(set(ids))
        assert [r['event'] for r in captured if r['kind'] == 'actual_event'] == events
        assert [r['decision'] for r in captured if r['kind'] == 'decision'] == trace['decisions']
        assert [r['thought'] for r in captured if r['kind'] == 'thought'] == trace['thoughts']
        assert run['model_before'] == run['model_after'] == trace['model_id']
        for i, (r, e) in enumerate(zip(actual, events)):
            assert r['call'] == i+1 and r['action_index'] == e['action_index']
            for key in ('observation', 'actions', 'goal'): assert r[key] == e[key]
            for key, value in r['result'].items(): assert value == e[key], key
            x = r['observation']; a = r['actions'][r['action_index']]; nxt = r['result']['next_observation']
            for j in range(16): close(nxt[j], .6*x[j]+.15*a[j % 8]+r['noise'][j], 1e-12)
            assert all(-.01 <= n <= .01 for n in r['noise'])
            assert e['terminal'] == (r['step'] == 2)
            assert e['goal_met'] == (e['terminal'] and nxt[0] > .15)
            fb = e['feedback']; mask = e['feedback_mask']
            assert mask[:6] == [True]*6
            for got, expected in zip(fb[:6], [float(e['goal_met']), nxt[0], nxt[0]-x[0], 1., e['action_index'], float(e['terminal'])]):
                close(got, expected, 1e-12)
            for j in (6, 7):
                if not mask[j]: assert fb[j] == 0.
            if mask[6]: assert abs(fb[6]-nxt[0]) <= .1+1e-12
            if mask[7]: assert abs(fb[7]-(nxt[1]-x[1])) <= .1+1e-12
            assert e['cost'] == 1. and e['source'] == 'environment'
            if e['previous_id']:
                prev = by_id[e['previous_id']]
                assert ids.index(prev['id']) < i and prev['next_observation'] == e['observation']
                assert prev['episode'] == e['episode'] and prev['step']+1 == e['step']
        post_ends = []
        covered_task_ids = []
        for episode in trace['episodes']:
            source = [by_id[i] for i in episode['source_ids']]
            assert len(source) == 3 and source[0]['observation'][0] == -2.
            assert source[-1]['terminal'] and not source[-1]['goal_met']
            covered_task_ids.extend(episode['source_ids'])
            assert len(episode['post_task_ids']) == 2
            for j, seq in enumerate(episode['post_task_ids']):
                assert len(seq) == 3 and by_id[seq[0]]['observation'][0] == contract['post_choice_initial_x0'][j]
                assert by_id[seq[-1]]['terminal']
                post_ends.append(seq[-1]); covered_task_ids.extend(seq)
        assert len(set(covered_task_ids)) == 27 and set(covered_task_ids) == {e['id'] for e in events if e['role'] == 'task'}
        thoughts = {t['id']: t for t in trace['thoughts']}; internal = {}
        for t in thoughts.values():
            lp = 0.; rows_allocated = 0
            assert len(t['noise_tape']['action']) == 3
            assert all(len(x) == 4 for x in t['noise_tape']['action'])
            for d in t['decisions']:
                for available, keep, prob in zip(d['available'], d['continue'], d['continue_probability']):
                    if available: lp += math.log(prob if keep else 1-prob)
                    else: assert not keep
                if 'action' in d:
                    rows_allocated += 4*8
                    for keep, a, policy in zip(d['continue'], d['action'], d['policy']):
                        close(sum(policy), 1.)
                        if keep: lp += math.log(policy[a])
            close(lp, t['internal_log_probability'], 1e-5); internal[t['id']] = lp
            assert rows_allocated == t['allocated_particle_rows']
            for index, node in enumerate(t['nodes']):
                if node['parent'] is not None:
                    parent = t['nodes'][node['parent']]
                    assert node['parent'] < index and parent['arm'] == node['arm'] and parent['hypothesis'] == node['hypothesis']
                    assert parent['next_observation'] == node['observation'] and not parent['terminal']
                for value, mask in zip(node['innovation'], node['innovation_mask']):
                    if not mask: assert value == 0.
        seen = []; reward = []; log_steps = []; trial_ids = []; used_thoughts = []
        for d in trace['decisions']:
            assert d['history_ids'] == seen and d['model_id'] == trace['model_id']
            r = [0., 0., 0.]; kind = d['kind']; lp = math.log(d['propensity'])
            choice = d['action'] if kind in ('task', 'trial') else d['choice']
            close(sum(d['policy']), 1.); assert d['propensity'] == d['policy'][choice] > 0.
            if kind in ('task', 'trial'):
                e = events[len(seen)]; assert e['id'] == d['event_id'] and e['propensity'] == d['propensity']
                r[1] = -e['cost']
                if e['id'] in post_ends:
                    assert d['purpose'] == 'post_choice'; r[0] = float(e['goal_met'])/len(post_ends)
                seen.append(e['id'])
                if kind == 'trial': trial_ids.append(e['id'])
            if kind == 'trial_choice':
                t = thoughts[d['thought_id']]; used_thoughts.append(t['id']); assert t['history_ids'] == seen
                r[2] = -t['allocated_particle_rows']; lp += internal[t['id']]
            reward.append(r); log_steps.append(lp)
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
                arm = s['arms'][r['arm']]; e = by_id[r['event_id']]
                assert r['candidate_digest'] == arm['digest'] and e['candidate_id'] == arm['id']
        returns = []; cumulative = [0., 0., 0.]
        for r in reversed(reward):
            cumulative = [x+y for x, y in zip(cumulative, r)]; returns.append(cumulative)
        returns.reverse()
        for measured, expected in zip(credit['reward'], reward):
            for x, y in zip(measured, expected): close(x, y)
        for measured, expected in zip(credit['returns'], returns):
            for x, y in zip(measured, expected): close(x, y)
        for x, y in zip(credit['log_steps'], log_steps): close(x, y, 1e-5)
        for j in range(3):
            actor = -sum((g[j]-v[j])*l for g, v, l in zip(returns, credit['values'], log_steps))
            critic = sum((g[j]-v[j])**2 for g, v in zip(returns, credit['values']))/len(returns)
            zero = -sum(g[j]*l for g, l in zip(returns, log_steps))
            for x, y in [(credit['policy_losses'][j], actor), (credit['critic_losses'][j], critic), (credit['zero_baseline_losses'][j], zero)]:
                close(x, y, 2e-5)
        assert len(events) == 27+len(trial_ids) and len(trial_ids) <= 6
        assert run['return_vector'][1] == -len(events)
        totals['actual_events'] += len(events); totals['main_steps'] += 27; totals['trials'] += len(trial_ids)
        totals['successes'] += sum(by_id[i]['goal_met'] for i in post_ends)
        totals['imagined_nodes'] += sum(len(t['nodes']) for t in thoughts.values())
        totals['particle_rows'] += sum(t['allocated_particle_rows'] for t in thoughts.values())
        totals['decisions'] += len(trace['decisions'])
    assert totals['actual_events'] == summary['actual_calls'] <= 66 and totals['main_steps'] == 54
    result = dict(status='STORED_DATA_CHECKED', input_pins=len(claim['input_sha256']), jsonl_complete_records=len(rows),
        totals=totals, policy_return_objective_recomputed=True, internal_independent_log_density_recomputed=True,
        actual_transition_equations_checked=True, actual_environment_calls=0, optimizer_steps=0,
        limits='Stdlib source-data audit, not an independent scientific replication or runtime identity reconstruction')
    with (CAP/'stored_audit.json').open('x', encoding='utf-8') as f: json.dump(result, f, indent=2)
    print(json.dumps(result, indent=2))


if __name__ == '__main__': main()
