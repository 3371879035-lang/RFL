"""Independent stdlib replay of stored arithmetic, actions, noise, and all costs.

Does not import the learner, torch, environment, or execute new environment steps.
"""
from pathlib import Path
from fractions import Fraction
import csv
import gzip
import hashlib
import itertools
import json
import math
import random
import statistics

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FAMILIES = ['single', 'triple', 'small_gap', 'noise']


def close(a, b, tolerance=3e-13):
    assert abs(a-b) <= tolerance, (a, b)


def softmax(logs):
    mx = max(logs)
    e = [math.exp(x-mx) for x in logs]
    total = math.fsum(e)
    return [x/total for x in e]


def main():
    contract = json.loads((HERE/'contract.json').read_text(encoding='utf-8'))
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest() == v
               for p, v in contract['input_sha256'].items())
    native = json.loads((HERE/'native_result.json').read_text(encoding='utf-8'))
    assert hashlib.sha256((HERE/'raw.jsonl.gz').read_bytes()).hexdigest() == native['raw_sha256']
    contexts = list(itertools.product((0, 1), repeat=4))
    nrecords = nepisodes = 0
    observed = []
    runs = {}
    max_weight_error = 0.
    with gzip.open(HERE/'raw.jsonl.gz', 'rt', encoding='utf-8') as stream:
        for line in stream:
            r = json.loads(line)
            assert json.dumps(r, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n' == line
            nrecords += 1
            kind = r['kind']
            if kind == 'setup':
                bank = r['bank']
                reps = bank['representatives']
                signatures = bank['signatures']
                assert len(signatures) == 9
                expected_signatures = sorted([[sum(x[j] for j in s) % 2 for x in contexts]
                                              for s in r['definitions']])
                assert signatures == expected_signatures
                ref_id = r['reference']
                mapping = dict(zip(reps, signatures))
                assert mapping[ref_id] == [0]*16
                epsilon, rho, horizon = .2, .5, 128
                eta = math.sqrt(2*rho*math.log(9)/(horizon*2))
                def probabilities(policy_id, x):
                    a = mapping[policy_id][contexts.index(tuple(x))]
                    return [.9 if k == a else .1 for k in range(2)]
            elif kind == 'episode':
                nepisodes += 1
                key = r['family'], r['seed'], r['arm']
                state = runs.setdefault(key, {'counts': [0,0,0], 'sums': [0,0,0], 'ranking': [],
                                              'logs': [-math.log(9)]*9, 'tv': 0., 'last_id': 63})
                family, seed, arm = key
                phase, slot = r['phase'], r['slot']
                assert slot == state['counts'][phase]
                number = (((FAMILIES.index(family)*100+seed)*3+phase)*1000+slot)
                generator = random.Random(213000000000+number)
                x = tuple(generator.randrange(2) for _ in range(4))
                au, ou = generator.random(), generator.random()
                assert au == r['action_u'] and ou == r['outcome_u']
                fact = r['public']
                assert tuple(fact['context']) == x and fact['id'] == state['last_id']+1
                experts = [probabilities(pid, x) for pid in reps]
                base = probabilities(ref_id, x)
                if phase == 0:
                    mu = base
                    assert fact['policy_id'] == ref_id
                    state['ranking'].append(fact)
                elif phase == 1:
                    if arm == 'feedback_mix':
                        w = softmax(state['logs'])
                        for v, expected in zip(r['before_weights'], w):
                            max_weight_error = max(max_weight_error, abs(v-expected))
                            close(v, expected)
                        q = [math.fsum(wj*p[a] for wj, p in zip(w, experts)) for a in range(2)]
                        receipt = r['receipt']
                        assert receipt['observation_id'] == fact['id'] and receipt['ordinal'] == slot
                        assert receipt['context'] == list(x) and receipt['lease_id'] == state['lease_id']
                        for got, expected in zip(receipt['expert_probabilities'], experts):
                            for ga, ea in zip(got, expected): close(ga, ea)
                        assert fact['policy_id'] == state['lease_id']
                    elif arm == 'locked_ips':
                        q = experts[state['chosen']]
                    else:
                        q = [math.fsum(p[a] for p in experts)/9 for a in range(2)]
                    mu = [(b+qa)/2 for b, qa in zip(base, q)]
                    tv = math.fsum(abs(p-b) for p, b in zip(mu, base))/2
                    state['tv'] += tv
                    if arm == 'feedback_mix': close(receipt['total_variation'], tv)
                else:
                    assert phase == 2 and fact['policy_id'] == state['proposed']
                    mu = probabilities(state['proposed'], x)
                for value, expected in zip(r['probabilities'], mu): close(value, expected)
                action = int(au < mu[1])
                assert action == fact['action']
                close(fact['propensity'], mu[action])
                desired = x[seed % 4] if family == 'single' else x[0]^x[1]^x[2]
                correct = .58 if family == 'small_gap' else .9
                success_p = .5 if family == 'noise' else correct if action == desired else 1-correct
                assert fact['outcome'] == int(ou < success_p)
                state['counts'][phase] += 1
                state['sums'][phase] += fact['outcome']
                state['last_id'] = fact['id']
                if phase == 1 and arm == 'feedback_mix':
                    estimates = [p[action]*(1-fact['outcome'])/mu[action] for p in experts]
                    state['logs'] = [l-eta*el for l, el in zip(state['logs'], estimates)]
                    normalizer = max(state['logs'])+math.log(math.fsum(math.exp(x-max(state['logs'])) for x in state['logs']))
                    state['logs'] = [l-normalizer for l in state['logs']]
                    state['estimates'] = estimates
            elif kind == 'begin_trial':
                key = r['family'], r['seed'], r['arm']
                state = runs[key]
                assert state['counts'] == [32,0,0]
                scores = []
                for pid in reps:
                    score = sum((Fraction(probabilities(pid, f['context'])[f['action']]).limit_denominator(10)
                                 *f['outcome']/Fraction(f['propensity']).limit_denominator(10)
                                 for f in state['ranking']), Fraction())/32
                    scores.append(score)
                assert r['ranking_scores'] == [str(s) for s in scores]
                state['chosen'] = max(range(9), key=lambda i: scores[i])
                assert state['chosen'] == r['selected_index']
                state['lease_id'] = r['lease_id']
                if key[2] == 'feedback_mix':
                    meta = [1, ref_id, reps, 128, .5, 95, .2, [0.,1.]]
                    assert hashlib.sha256(json.dumps(meta).encode()).hexdigest() == r['lease_id']
            elif kind == 'update':
                state = runs[(r['family'], r['seed'], r['arm'])]
                assert r['slot'] == state['counts'][1]-1
                for a, b in zip(r['estimated_losses'], state['estimates']): close(a, b)
                for a, b in zip(r['after_weights'], softmax(state['logs'])): close(a, b)
            elif kind == 'nomination':
                key = r['family'], r['seed'], r['arm']; state = runs[key]
                assert state['counts'] == [32,128,0]
                if key[2] == 'feedback_mix':
                    native_logs = r['lease']['log_weights']
                    for a, b in zip(native_logs, state['logs']): close(a, b)
                    index = max(range(9), key=lambda i: native_logs[i])
                elif key[2] == 'locked_ips': index = state['chosen']
                else: index = 0
                assert r['proposed'] == reps[index]
                state['proposed'] = r['proposed']
                close(r['tv_spent'], state['tv'], 2e-11)
                assert state['tv'] <= 51.2+1e-10 and r['permanent_adoption'] is False
            elif kind == 'run_end':
                key = r['family'], r['seed'], r['arm']; state = runs[key]
                assert state['counts'] == [32,128,128] and state['last_id'] == 351
                assert state['sums'] == [r['warm_successes'], r['trial_successes'], r['proposal_eval_successes']]
                family, seed, _ = key
                values = []
                for x in contexts:
                    desired = x[seed % 4] if family == 'single' else x[0]^x[1]^x[2]
                    correct = .58 if family == 'small_gap' else .9
                    for a, p in enumerate(probabilities(r['proposed'], x)):
                        success_p = .5 if family == 'noise' else correct if a == desired else 1-correct
                        values.append(p*success_p/16)
                close(r['proposal_expected_value_posthoc'], math.fsum(values))
                observed.append({k:v for k,v in r.items() if k != 'kind'})
            elif kind == 'end':
                assert r['runs'] == 192 and r['episodes'] == 55296 and r['steps'] == 221184
            else: raise AssertionError(kind)
    assert nrecords == native['records'] and nepisodes == native['episodes'] == 55296
    assert observed == native['runs'] and len(runs) == len(observed) == 192
    table = []
    for family in FAMILIES:
        for arm in ['locked_ips', 'uniform_mix', 'feedback_mix']:
            group = [r for r in observed if (r['family'],r['arm']) == (family,arm)]
            table.append({'family': family, 'arm': arm, 'independent_seeds': len(group),
                          'trial_success_rate': statistics.mean(r['trial_successes']/128 for r in group),
                          'proposal_evaluation_success_rate': statistics.mean(r['proposal_eval_successes']/128 for r in group),
                          'proposal_expected_posthoc': statistics.mean(r['proposal_expected_value_posthoc'] for r in group),
                          'mean_tv_spent': statistics.mean(r['tv_spent'] for r in group),
                          'mean_cpu_seconds': statistics.mean(r['cpu_seconds'] for r in group)})
    differences = []
    for family in FAMILIES:
        for metric in ['trial_successes', 'proposal_eval_successes']:
            pairs = []
            for seed in range(16):
                a = next(r for r in observed if (r['family'],r['seed'],r['arm']) == (family,seed,'feedback_mix'))
                b = next(r for r in observed if (r['family'],r['seed'],r['arm']) == (family,seed,'locked_ips'))
                pairs.append((a[metric]-b[metric])/128)
            differences.append({'family': family, 'metric': metric, 'paired_seed_differences': pairs,
                                'mean': statistics.mean(pairs), 'sample_sd': statistics.stdev(pairs)})
    result = {'schema': 'v213-independent-stored-review', 'records': nrecords,
              'actual_episodes': nepisodes, 'steps': nepisodes*4, 'runs': len(runs),
              'max_weight_error': max_weight_error, 'table': table, 'differences': differences,
              'new_environment_runs': 0, 'neural_imports': 0, 'all_input_pins_match': True}
    with (HERE/'stored_review.json').open('x', encoding='utf-8') as f:
        json.dump(result, f, indent=2, allow_nan=False)
    with (HERE/'summary.csv').open('x', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(table[0])); writer.writeheader(); writer.writerows(table)
    print(json.dumps({'records': nrecords, 'episodes': nepisodes, 'max_weight_error': max_weight_error}))


if __name__ == '__main__': main()
