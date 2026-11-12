"""Stored-record audit and analysis. Standard library only; never runs a learner/world."""
from pathlib import Path
from collections import deque, defaultdict
from itertools import combinations, product
import gzip
import hashlib
import json
import math
import random
import statistics
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = HERE/'stored_audit_result.json'
if OUT.exists():
    raise SystemExit('Existing stored audit retained; no automatic rerun')
contract = json.loads((HERE/'contract.json').read_text(encoding='utf-8'))
native = json.loads((HERE/'native_summary.json').read_text(encoding='utf-8'))
started = time.perf_counter()


def digest(table):
    return hashlib.sha256(bytes(int(v) for v in table)).hexdigest()


def bits(index):
    return [(index >> (7-j)) & 1 for j in range(8)]


def index(row):
    result = 0
    for value in row:
        result = result*2 + value
    return result


def score(policy, records):
    total = 0
    for r in records:
        row = [v for event in r['observations'] for v in event]
        num, den = r['propensity']
        total += int(int(policy['table'][index(row)]) == r['actions'][-1]) * r['outcome'] * (9*den//num)
    return total


def expected_value(policy, spec, cycle):
    correct = 0
    for i in range(256):
        row = bits(i)
        desired = spec['initial_flip']
        for j in spec['relevant']:
            desired ^= row[j]
        if spec['switch_cycle'] is not None and cycle >= spec['switch_cycle']:
            desired ^= 1
        correct += int(int(policy['table'][i]) == desired)
    # Exact uniform-context value of the same epsilon=.2 deployed policy.
    return .18 + .64*correct/256


def build_from_raw(memory, order):
    structures = [s for k in range(1, order+1) for s in combinations(range(8), k)]
    offsets, cursor = [], 0
    for s in structures:
        offsets.append(cursor)
        cursor += 2**len(s)
    counts = [[[0, 0], [0, 0]] for _ in range(cursor)]
    for record in memory:
        row = [v for e in record['observations'] for v in e]
        num, den = record['propensity']
        weight = 9*den//num
        a, y = record['actions'][-1], record['outcome']
        for s, offset in zip(structures, offsets):
            cell = offset + index([row[j] for j in s])
            counts[cell][a][y] += weight
    candidates, seen = [], set()
    for s, offset in zip(structures, offsets):
        table = []
        for i in range(256):
            row = bits(i)
            c = counts[offset + index([row[j] for j in s])]
            # Compare the two posterior means by exact integer cross multiplication.
            a0 = (c[0][1]+9)*(sum(c[1])+18)
            a1 = (c[1][1]+9)*(sum(c[0])+18)
            table.append('1' if a1 > a0 else '0')
        table = ''.join(table)
        if table not in seen:
            seen.add(table)
            candidates.append({'table': table, 'structure': list(s), 'id': digest(table)})
    return structures, counts, candidates


def bootstrap(values):
    rng = random.Random(20999001)
    n = len(values)
    means = sorted(sum(values[rng.randrange(n)] for _ in range(n))/n for _ in range(2000))
    return [means[49], means[1949]]


rows, run_results = [], {}
seen_episode_ids = 0
canonical_records = 0
totals = defaultdict(int)
current = None
with gzip.open(HERE/'evidence/raw.jsonl.gz', 'rt', encoding='utf-8') as raw:
    for line in raw:
        event = json.loads(line)
        canonical_records += 1
        kind = event['kind']
        if kind == 'start':
            assert event['contract_sha256'] == hashlib.sha256((HERE/'contract.json').read_bytes()).hexdigest()
            assert event['input_sha256'] == contract['input_sha256']
        elif kind == 'run_begin':
            current = event
            memory = deque(maxlen=contract['memory_size'])
            incumbent = {'table': '0'*256, 'structure': [], 'id': digest('0'*256)}
            observed = 0
            run_episodes = 0
            phase_records = defaultdict(list)
            run_rows = []
            assert event['run'] not in run_results
        elif kind == 'episode':
            assert event['run'] == current['run']
            r, private = event['public'], event['private']
            assert set(r) == {'id', 'observations', 'actions', 'outcome', 'propensity', 'policy_id'}
            assert r['id'] == seen_episode_ids
            seen_episode_ids += 1
            row = [v for e in r['observations'] for v in e]
            assert len(row) == 8 and all(v in (0, 1) for v in row)
            assert len(r['observations']) == 4 and all(len(e) == 2 for e in r['observations'])
            assert len(r['actions']) == 4 and r['actions'][:3] == [-1, -1, -1]
            phase = event['phase']
            policy = proposal['candidate'] if phase == 'trial' and event['role'] == 'candidate' else incumbent
            assert r['policy_id'] == policy['id']
            base = int(policy['table'][index(row)])
            p1 = .5 if phase == 'warm' else (.9 if base else .1)
            action = int(private['action_u'] < p1)
            assert r['actions'][-1] == action
            prop = [1, 2] if phase == 'warm' else ([9, 10] if action == base else [1, 10])
            assert r['propensity'] == prop
            spec = current['world_spec']
            desired = spec['initial_flip']
            for j in spec['relevant']:
                desired ^= row[j]
            if spec['switch_cycle'] is not None and event['cycle'] >= spec['switch_cycle']:
                desired ^= 1
            assert r['outcome'] == int(private['outcome_u'] < (.9 if action == desired else .1))
            assert event['learned'] == (phase != 'eval')
            if event['learned']:
                memory.append(r)
                observed += 1
                totals['state_observations'] += 1
            else:
                totals['evaluations'] += 1
            if phase == 'trial':
                totals['trials'] += 1
            phase_records[(event['cycle'], phase, event['role'])].append(event)
            totals['episodes'] += 1
            totals['steps'] += 4
            run_episodes += 1
        elif kind == 'bank':
            assert event['run'] == current['run'] and event['incumbent'] == incumbent
            assert event['diagnostics']['memory_ids'] == [r['id'] for r in memory]
            assert event['diagnostics']['seen'] == observed
            order = 1 if current['arm'] == 'unary_verified' else 2
            structures, expected_counts, candidates = build_from_raw(memory, order)
            assert [list(s) for s in structures] == event['diagnostics']['structures']
            assert expected_counts == event['diagnostics']['counts']
            assert candidates == event['candidates']
            bank = event
            totals['candidate_builds'] += 1
        elif kind == 'proposal':
            c = event['cycle']
            ranking = [x['public'] for x in phase_records[(c, 'rank', None)]]
            assert len(ranking) == contract['rank_episodes']
            candidates = bank['candidates']
            scores = [score(p, ranking) for p in candidates]
            baseline = score(incumbent, ranking)
            alternatives = [i for i, p in enumerate(candidates) if p['table'] != incumbent['table']]
            if alternatives:
                if current['arm'] == 'joint_uniform_verified':
                    chosen = random.Random(209700000+current['seed']*100+c).choice(alternatives)
                else:
                    chosen = max(alternatives, key=lambda i: scores[i])
            else:
                chosen = None
            candidate = incumbent if chosen is None else candidates[chosen]
            assert event['chosen'] == chosen and event['candidate'] == candidate
            assert event['scores'] == scores and event['baseline_score'] == baseline
            assert event['rank_delta_numerator'] == (0 if chosen is None else scores[chosen]-baseline)
            proposal = event
        elif kind == 'decision':
            c = event['cycle']
            ref = phase_records[(c, 'trial', 'reference')]
            new = phase_records[(c, 'trial', 'candidate')]
            assert len(ref) == len(new) == contract['trial_pairs']
            for r, n in zip(ref, new):
                assert r['index'] == n['index']
                assert r['public']['observations'] == n['public']['observations']
                assert r['private'] == n['private']
            delta = sum(n['public']['outcome']-r['public']['outcome'] for r, n in zip(ref, new))
            candidate = proposal['candidate']
            identical = incumbent['table'] == candidate['table']
            adopt = not identical and (proposal['rank_delta_numerator'] > 0 if current['arm'] == 'joint_rank_only' else delta > 0)
            assert event['previous'] == incumbent and event['candidate'] == candidate
            assert event['identical'] == identical and event['adopt'] == adopt
            assert event['trial_difference_sum'] == delta
            assert event['rank_delta_numerator'] == proposal['rank_delta_numerator']
            old_value = expected_value(incumbent, current['world_spec'], c)
            candidate_value = expected_value(candidate, current['world_spec'], c)
            diagnostic_delta = candidate_value-old_value
            if adopt:
                incumbent = candidate
                totals['adoptions'] += 1
            assert event['next'] == incumbent
            decision = event
        elif kind == 'cycle_end':
            c = event['cycle']
            deploy = phase_records[(c, 'deploy', None)]
            evaluation = phase_records[(c, 'eval', None)]
            assert len(deploy) == contract['deploy_episodes']
            assert len(evaluation) == contract['eval_episodes']
            assert event['deployment_success'] == sum(x['public']['outcome'] for x in deploy)
            assert event['evaluation_success'] == sum(x['public']['outcome'] for x in evaluation)
            assert event['next_policy_id'] == incumbent['id']
            row = {'run': current['run'], 'family': current['family'], 'seed': current['seed'], 'arm': current['arm'],
                   'cycle': c, 'evaluation_rate': event['evaluation_success']/contract['eval_episodes'],
                   'deployment_rate': event['deployment_success']/contract['deploy_episodes'],
                   'known_rule_expected_rate': expected_value(incumbent, current['world_spec'], c),
                   'candidate_expected_delta': diagnostic_delta,
                   'trial_observed_delta': decision['trial_difference_sum']/contract['trial_pairs'],
                   'adopt': decision['adopt'], 'harmful_adoption': bool(decision['adopt'] and diagnostic_delta < -1e-12),
                   'zero_effect_adoption': bool(decision['adopt'] and abs(diagnostic_delta) < 1e-12),
                   'missed_positive_candidate': bool(not decision['adopt'] and diagnostic_delta > 1e-12),
                   'selected_structure_covers_hidden_rule': set(current['world_spec']['relevant']) <= set(proposal['candidate']['structure'])}
            rows.append(row)
            run_rows.append(row)
        elif kind == 'run_end':
            assert event['parameter_sha256_before'] == event['parameter_sha256_after'] == current['parameters_sha256']
            assert event['episodes'] == run_episodes and event['steps'] == 4*run_episodes
            assert event['observations'] == observed
            assert len(run_rows) == contract['cycles']
            for c in range(contract['cycles']):
                assert len(phase_records[(c, 'fit', None)]) == contract['fit_episodes']
                assert len(phase_records[(c, 'rank', None)]) == contract['rank_episodes']
            assert len(phase_records[(-1, 'warm', None)]) == contract['warm_episodes']
            all_training = [x for r in phase_records.values() for x in r if x['learned']]
            run_results[current['run']] = {'family': current['family'], 'seed': current['seed'], 'arm': current['arm'],
                'evaluation_rate': statistics.mean(x['evaluation_rate'] for x in run_rows),
                'known_rule_expected_rate': statistics.mean(x['known_rule_expected_rate'] for x in run_rows),
                'all_training_success_rate': statistics.mean(x['public']['outcome'] for x in all_training),
                'adoptions': sum(x['adopt'] for x in run_rows),
                'harmful_adoptions': sum(x['harmful_adoption'] for x in run_rows),
                'zero_effect_adoptions': sum(x['zero_effect_adoption'] for x in run_rows),
                'missed_positive_candidates': sum(x['missed_positive_candidate'] for x in run_rows),
                'cycles': run_rows}
        elif kind == 'complete':
            assert dict(totals) == event['counts'] == native['counts']
            assert event['run_count'] == len(run_results)
        else:
            raise AssertionError(f'Unknown event kind {kind}')

assert kind == 'complete'
assert len(run_results) == len(contract['families'])*len(contract['seeds'])*len(contract['arms'])
assert native['status'] == 'COMPLETE'
assert {k: totals[k] for k in contract['expected_counts_except_adoptions']} == contract['expected_counts_except_adoptions']
current_pins = {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in contract['input_sha256']}
assert current_pins == contract['input_sha256']

aggregate = {}
for family in contract['families']:
    aggregate[family] = {}
    for arm in contract['arms']:
        subset = [x for x in run_results.values() if x['family'] == family and x['arm'] == arm]
        aggregate[family][arm] = {name: statistics.mean(x[name] for x in subset)
            for name in ('evaluation_rate', 'known_rule_expected_rate', 'all_training_success_rate')}
        aggregate[family][arm].update({name: sum(x[name] for x in subset)
            for name in ('adoptions', 'harmful_adoptions', 'zero_effect_adoptions', 'missed_positive_candidates')})
        aggregate[family][arm]['evaluation_by_cycle'] = [statistics.mean(x['cycles'][c]['evaluation_rate'] for x in subset)
                                                        for c in range(contract['cycles'])]
        aggregate[family][arm]['expected_by_cycle'] = [statistics.mean(x['cycles'][c]['known_rule_expected_rate'] for x in subset)
                                                      for c in range(contract['cycles'])]

contrasts = {}
for family in contract['families']:
    contrasts[family] = {}
    for baseline in ('unary_verified', 'joint_rank_only', 'joint_uniform_verified'):
        differences = []
        for seed in contract['seeds']:
            left = run_results[f'{family}/{seed}/joint_verified']['evaluation_rate']
            right = run_results[f'{family}/{seed}/{baseline}']['evaluation_rate']
            differences.append(left-right)
        contrasts[family][baseline] = {'paired_seed_mean_difference': statistics.mean(differences),
                                       'exploratory_seed_bootstrap_95': bootstrap(differences),
                                       'independent_seed_count': len(differences)}

result = {'status': 'STORED_AUDIT_PASS', 'canonical_records': canonical_records, 'counts': dict(totals),
          'run_count': len(run_results), 'wall_seconds': time.perf_counter()-started,
          'checked': ['all raw episodes and outcomes', 'all step/action/propensity records',
                      'chronological training memory with holdout exclusion', 'all weighted fact counts',
                      'all candidate tables via integer arithmetic', 'all ranking and trial decisions',
                      'paired common random inputs', 'all frozen parameter hashes', 'all input hashes'],
          'environment_runs_in_auditor': 0, 'imports_original_learner_or_world': False,
          'aggregate': aggregate, 'contrasts': contrasts,
          'note': 'Known-rule expected values are post-run analytic diagnostics, never learner inputs. Bootstrap is exploratory, not a formal family-level confirmation.'}
with OUT.open('x', encoding='utf-8', newline='\n') as out:
    json.dump(result, out, ensure_ascii=False, indent=2)
    out.write('\n')
with (HERE/'analysis_runs.json').open('x', encoding='utf-8', newline='\n') as out:
    json.dump(run_results, out, ensure_ascii=False, indent=2)
    out.write('\n')
print(json.dumps({'status': result['status'], 'canonical_records': canonical_records,
                  'runs': len(run_results), 'wall_seconds': result['wall_seconds']}, ensure_ascii=False))
for family, arms in aggregate.items():
    print(family, json.dumps({arm: {'eval': round(v['evaluation_rate'], 6), 'expected': round(v['known_rule_expected_rate'], 6),
                                    'adopt': v['adoptions'], 'harmful': v['harmful_adoptions']}
                               for arm, v in arms.items()}))
