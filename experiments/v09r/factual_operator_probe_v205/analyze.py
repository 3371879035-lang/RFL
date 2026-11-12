"""Stdlib-only review of actual stored evidence. Does not import/run the model."""
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
import statistics

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def lines(path):
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt', encoding='utf-8') as f:
        for line in f:
            yield json.loads(line)


def verify_episode(ep):
    family, cycle, cue = ep['family'], ep['cycle'], ep['cue']
    phase, v = 0, 2. * cue - 1. if 'history' in family else 0.
    rng = random.Random(ep['env_seed'])
    choice, expected = None, None
    for j, step in enumerate(ep['steps']):
        assert step['t'] == phase == j and step['observation'] == [float(phase), v]
        a, c, y, terminal, draw = step['action'], [0., 0.], [0., 0.], False, None
        if 'history' in family:
            last = 1 if family == 'short_history' else 5
            legal = [0] if phase < last else [0, 1, 2]
            if phase == last:
                y[0] = .25 if a == 2 else float(a == cue)
                terminal = True
            v = 0.
        else:
            legal = [0, 1, 2] if phase == 0 else [0]
            if phase == 0:
                choice = a
                if family == 'process_cost':
                    c[1], v = (.8, .1, .2)[a], float(a)
                elif family == 'branching':
                    if a == 0:
                        draw = rng.random()
                        v = -1. if draw < .5 else 1.
                    else:
                        v = .4 if a == 1 else 0.
                else:
                    expected = ((.65, .55, .45) if cycle == 0 else (.30, .75, .50))[a]
                    draw = rng.random()
                    c[0], v = float(draw < expected), 0.
            else:
                terminal = True
                if family == 'process_cost':
                    y[0] = (1., .9, .7)[choice]
                elif family == 'branching':
                    y[0] = 1. if abs(v) == 1. else (.65 if v == .4 else 0.)
        assert step['legal'] == legal and a in legal and step['draw'] == draw
        assert step['contribution'] == c and step['terminal_fact'] == y
        assert step['terminal'] == terminal and step['known'] == [True, True]
        phase += 1
        assert step['successor'] == [float(phase), v]
        expected_legal = [] if terminal else ([0, 1, 2] if ('history' in family and phase == (1 if family == 'short_history' else 5)) else [0])
        assert step['legal_next'] == expected_legal
        assert not terminal or j == len(ep['steps']) - 1
    assert ep['steps'][-1]['terminal']
    facts = [sum(s['contribution'][k] + int(s['terminal']) * s['terminal_fact'][k] for s in ep['steps']) for k in range(2)]
    assert facts == ep['facts'] and abs(facts[0] - facts[1] - ep['utility']) < 1e-12
    return ep['utility'] if expected is None else expected


def context(step, previous, window):
    result = list(step['observation'])
    for j in range(window):
        result += list(previous[-1-j]) + [1.] if j < len(previous) else [0., 0., 0.]
    return result


def main():
    cfg = json.loads((HERE / 'contract.json').read_text(encoding='utf-8'))
    native = json.loads((HERE / 'native_exit.json').read_text(encoding='utf-8'))
    assert native['exit_code'] == 0 and not native['timeout']
    assert native['inputs_before'] == native['inputs_after']
    for name, digest in native['inputs_before'].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
    count, steps, roles, train = 0, 0, Counter(), {}
    collected, expected_values = defaultdict(list), defaultdict(list)
    expected_by_id = {}
    for ep in lines(HERE / 'evidence' / 'episodes.jsonl.gz'):
        assert ep['id'] == count
        expected = verify_episode(ep)
        count += 1
        steps += len(ep['steps'])
        roles[ep['role']] += 1
        if not ep['role'].startswith('eval_'):
            train[ep['id']] = ep
        if ep['role'] != 'discovery':
            key = (ep['run'], ep['cycle'], ep['role'])
            collected[key].append(ep['utility'])
            expected_values[key].append(expected)
        if ep['role'].startswith('trial_'):
            expected_by_id[ep['id']] = expected
    assert count == cfg['maximum_actual_episodes'] and steps <= cfg['maximum_actual_steps']
    summaries = list(lines(HERE / 'evidence' / 'progress.jsonl'))
    assert len(summaries) == cfg['seeds'] * cfg['cycles'] * len(cfg['families']) * len(cfg['variants'])
    seen, group = set(), defaultdict(list)
    csv_rows = []
    for row in summaries:
        rid, cycle = row['run'], row['cycle']
        assert (rid, cycle) not in seen
        seen.add((rid, cycle))
        new, old = collected[rid, cycle, 'trial_candidate'], collected[rid, cycle, 'trial_incumbent']
        assert len(new) == len(old) == cfg['fresh_actual_trial_pairs_per_variant_cycle']
        diffs = [a - b for a, b in zip(new, old)]
        assert row['trial_differences'] == diffs
        estimate = sum(diffs) / (len(diffs) + 1.)
        assert abs(estimate - row['estimate']) < 1e-12 and row['adopted'] == (estimate > 0.)
        truth_delta = statistics.mean([a - b for a, b in zip(expected_values[rid, cycle, 'trial_candidate'], expected_values[rid, cycle, 'trial_incumbent'])])
        assert abs(truth_delta - row['analyst_expected_trial_delta']) < 1e-12
        for role in ('eval_incumbent', 'eval_deployed'):
            assert row['evaluation'][role] == collected[rid, cycle, role]
            assert len(collected[rid, cycle, role]) == cfg['heldout_actual_eval_pairs_per_variant_cycle']
            assert row['analyst_expected_eval'][role] == expected_values[rid, cycle, role]
        assert row['parameter_before'] == row['parameter_after']
        flat = dict(family=row['family'], variant=row['variant'], seed=row['seed'], cycle=cycle,
                    candidate_trial=statistics.mean(new), incumbent_trial=statistics.mean(old),
                    deployed=statistics.mean(collected[rid, cycle, 'eval_deployed']),
                    incumbent=statistics.mean(collected[rid, cycle, 'eval_incumbent']),
                    expected_deployed=statistics.mean(expected_values[rid, cycle, 'eval_deployed']),
                    expected_incumbent=statistics.mean(expected_values[rid, cycle, 'eval_incumbent']),
                    true_candidate_delta=truth_delta, adopted=int(row['adopted']),
                    harmful_adoption=int(row['adopted'] and truth_delta < -1e-12),
                    missed_beneficial_candidate=int(not row['adopted'] and truth_delta > 1e-12),
                    unknown_fallbacks=row['unknown_fallbacks'], wall_seconds=row['variant_cycle_wall_seconds'])
        csv_rows.append(flat)
        group[row['family'], row['variant'], cycle].append(flat)
    # Validate every learning target, source, ordering and loss. Recompute predictions at fixed positions only.
    memories = defaultdict(list)
    sampled, largest_error, pre_count, process_losses = 0, 0., 0, 0
    chosen_positions = {0, 1, 7, 23, 47, 63, 95, 127, 191, 255}
    for row in lines(HERE / 'evidence' / 'pre_observation.jsonl.gz'):
        rid, position = row['run'], row['rows_before']
        variant = rid.split(':')[2]
        setting = cfg['variants'][variant]
        ep = train[row['episode']]
        assert ep['role'] in ('discovery', 'trial_candidate', 'trial_incumbent')
        assert ep['cycle'] == row['cycle']
        assert ep['run'] == rid or ep['run'] == ':'.join(rid.split(':')[:2] + ['shared'])
        step = ep['steps'][row['step']]
        target = [(0. if setting['terminal_only'] else c) + step['terminal'] * y for c, y in zip(step['contribution'], step['terminal_fact'])]
        assert target == row['target'] and row['known'] == step['known']
        memory = memories[rid]
        assert len(memory) == position
        q = context(step, [s['observation'] for s in ep['steps'][:row['step']]], setting['window'])
        if position in chosen_positions:
            weights = [math.exp(-cfg['beta'] * sum((a - b) ** 2 for a, b in zip(q, k)))
                       if action == step['action'] and q[0] == k[0] else 0.
                       for k, action, _, _ in memory]
            for channel in range(2):
                mass = sum(w for w, (_, _, _, m) in zip(weights, memory) if m[channel])
                pred = (sum(w * x[channel] for w, (_, _, x, m) in zip(weights, memory) if m[channel]) / mass) if mass > 0. else None
                actual = row['prediction'][channel]
                assert (pred is None) == (actual is None)
                if pred is not None:
                    error = abs(pred - actual)
                    largest_error = max(largest_error, error)
                    assert error < 1e-10
            sampled += 1
        for predicted, actual, loss, known in zip(row['prediction'], target, row['loss'], row['known']):
            if predicted is None or not known:
                assert loss is None
            else:
                assert abs((predicted - actual) ** 2 - loss) < 1e-12
        process_losses += int(not row['terminal'] and any(x is not None for x in row['loss']))
        memory.append((q, step['action'], target, step['known']))
        pre_count += 1
    native_result = json.loads((HERE / 'native_result.json').read_text(encoding='utf-8'))
    assert count == native_result['actual_episodes'] and steps == native_result['actual_steps']
    assert pre_count == native_result['prediction_records'] and process_losses == native_result['nonterminal_prediction_loss_records']
    query_count = 0
    for query in lines(HERE / 'evidence' / 'model_queries.jsonl.gz'):
        assert query['run'].split(':')[2] in cfg['variants'] and 1 <= query['depth'] <= cfg['depth']
        assert len(query['factual']) == len(query['known']) == len(query['legal'])
        assert all(math.isfinite(v) for row in query['factual'] for v in row)
        query_count += 1
    aggregates = []
    for (family, variant, cycle), rows in group.items():
        assert len(rows) == cfg['seeds']
        output = dict(family=family, variant=variant, cycle=cycle, independent_seeds=len(rows))
        for field in ('candidate_trial', 'incumbent_trial', 'deployed', 'incumbent', 'expected_deployed', 'expected_incumbent', 'true_candidate_delta', 'wall_seconds'):
            values = [r[field] for r in rows]
            output[field + '_mean'] = statistics.mean(values)
            output[field + '_seed_se'] = statistics.stdev(values) / math.sqrt(len(values))
        for field in ('adopted', 'harmful_adoption', 'missed_beneficial_candidate', 'unknown_fallbacks'):
            output[field] = sum(r[field] for r in rows)
        aggregates.append(output)
    report = dict(status='STORED_REVIEW_MATCH', actual_episodes=count, actual_steps=steps, roles=dict(roles),
                  result_rows=len(summaries), pre_observation_records=pre_count, nonterminal_loss_records=process_losses,
                  fixed_position_prediction_checks=sampled, max_prediction_difference=largest_error,
                  stored_model_queries=query_count, native_wall_seconds=native_result['wall_seconds'],
                  interpretation='Mechanism diagnostics with fixed balanced discovery; not a trained-RL superiority test or general causal identification.',
                  limitations='Not full independent multi-step neural reconstruction; parameter equality is native hash evidence; generating-law diagnostics are analyst-only.',
                  aggregates=aggregates)
    with (HERE / 'stored_review.json').open('x', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    with (HERE / 'per_seed.csv').open('x', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(csv_rows[0]))
        writer.writeheader()
        writer.writerows(csv_rows)
    print(json.dumps({k: v for k, v in report.items() if k != 'aggregates'}))


if __name__ == '__main__':
    main()
