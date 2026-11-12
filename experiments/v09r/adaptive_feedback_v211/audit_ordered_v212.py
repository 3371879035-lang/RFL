# V212 targeted stored-review revision. Original V211 reviewer/capture remain unchanged.
"""New stored-data review. Standard library only, no learner/world/RFL imports."""
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from itertools import combinations, product
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
import random
import statistics
import struct
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FAMILIES = ('single', 'triple', 'switch_pair', 'noise')
ARMS = ('full', 'fixed_order', 'pooled_history', 'mean_eight')
ROWS = list(product((0, 1), repeat=4))
STRUCTURES = [s for k in range(1, 5) for s in combinations(range(4), k)]
STATE_ORDER = ('_goal', '_head.counts', '_head.log_weights', '_head.lift.weight', '_head.lift.bias')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def softmax(logs):
    top = max(logs)
    values = [math.exp(x-top) for x in logs]
    total = sum(values)
    return [x/total for x in values]


def context_index(row):
    return sum(int(v)*(2**(3-j)) for j, v in enumerate(row))


class ScalarTemporalModel:
    def __init__(self, structure, hazard):
        self.structure, self.hazard = tuple(structure), hazard
        self.cells = 2**len(structure)
        self.counts = [[0]*(self.cells*4)]
        self.logs, self.starts, self.n = [0.], [0], 0

    def cell(self, row):
        result = 0
        for j in self.structure:
            result = 2*result+row[j]
        return result

    def catch_up(self, history, n):
        while self.n < n:
            fact = history[self.n]
            if self.n and self.n % 32 == 0 and self.hazard:
                self.logs = [w+math.log1p(-self.hazard) for w in self.logs]+[math.log(self.hazard)]
                self.counts.append([0]*(self.cells*4))
                self.starts.append(self.n)
            index = 4*self.cell(fact['context'])+2*fact['action']
            joint = [w+math.log((c[index+fact['outcome']]+1)/(c[index]+c[index+1]+2))
                     for w, c in zip(self.logs, self.counts)]
            peak = max(joint)
            normalizer = peak+math.log(sum(math.exp(w-peak) for w in joint))
            self.logs = [w-normalizer for w in joint]
            for c in self.counts:
                c[index+fact['outcome']] += 1
            self.n += 1


def head_weights(structure):
    result = []
    for values in product((0, 1), repeat=len(structure)):
        row = [0.]*8
        for j, v in zip(structure, values):
            row[2*j+v] = 1.
        result.extend(row)
    return result, [float(1-len(structure))]*(2**len(structure))


def verify_policy(wire, history, models, known, diagnostic):
    if wire['id'] in known:
        assert known[wire['id']] == wire
        return
    cards, structure, actions, outcomes, block, hazard, starts, n, goal = wire['meta']
    assert cards == [2]*4 and actions == outcomes == 2 and block == 32 and goal == [0., 1.]
    key = tuple(structure)
    assert key in STRUCTURES and n <= len(history)
    model = models.setdefault(key, ScalarTemporalModel(key, hazard))
    assert model.n <= n and model.hazard == hazard
    model.catch_up(history, n)
    assert model.starts == starts
    state = wire['state']
    assert set(state) == set(STATE_ORDER)
    assert state['_goal'] == {'shape': [2], 'values': [0., 1.]}
    assert state['_head.counts']['shape'] == [len(starts), model.cells, 2, 2]
    expected_counts = [v for branch in model.counts for v in branch]
    assert expected_counts == state['_head.counts']['values']
    logs = state['_head.log_weights']['values']
    assert state['_head.log_weights']['shape'] == [len(starts)]
    log_error = max(abs(a-b) for a, b in zip(logs, model.logs))
    diagnostic['max_log_weight_error'] = max(diagnostic['max_log_weight_error'], log_error)
    assert log_error < 2e-9
    weights, biases = head_weights(key)
    assert state['_head.lift.weight'] == {'shape': [model.cells, 8], 'values': weights}
    assert state['_head.lift.bias'] == {'shape': [model.cells], 'values': biases}
    digest = hashlib.sha256(json.dumps(wire['meta']).encode())
    for name in STATE_ORDER:
        values = state[name]['values']
        digest.update(name.encode())
        digest.update(struct.pack('<'+'d'*len(values), *values))
    assert digest.hexdigest() == wire['id']
    branches = list(model.counts)
    forecast_logs = list(logs)
    if n and n % 32 == 0 and hazard:
        forecast_logs = [w+math.log1p(-hazard) for w in forecast_logs]+[math.log(hazard)]
        branches.append([0]*(model.cells*4))
    mixing = softmax(forecast_logs)
    for row, actual, chosen in zip(ROWS, wire['values'], wire['actions']):
        values = []
        cell = model.cell(row)
        for action in (0, 1):
            k = 4*cell+2*action
            values.append(sum(w*(c[k+1]+1)/(c[k]+c[k+1]+2) for w, c in zip(mixing, branches)))
        error = max(abs(a-b) for a, b in zip(actual, values))
        diagnostic['max_predictive_error'] = max(diagnostic['max_predictive_error'], error)
        assert error < 2e-12
        assert chosen == max(range(2), key=lambda a: actual[a])
        if chosen != max(range(2), key=lambda a: values[a]):
            assert abs(values[0]-values[1]) < 2e-12
            diagnostic['floating_tie_action_differences'] += 1
    assert wire['last_fact_id'] == (history[n-1]['id'] if n else -1)
    known[wire['id']] = wire
    diagnostic['policies_verified'] += 1


def expected_numerator(policy, spec, cycle):
    if spec['family'] == 'noise':
        return 25  # Denominator 50.
    matches = 0
    for row, action in zip(ROWS, policy['actions']):
        target = spec['flip']
        for j in spec['relevant']:
            target ^= row[j]
        if spec['switch_cycle'] is not None and cycle >= spec['switch_cycle']:
            target ^= 1
        matches += int(action == target)
    return 9+2*matches  # .18 + .64 * matches / 16.


def audit_episode(record, spec, seed, known, expected_frame, event):
    f, private = record['public'], record['private']
    cycle, phase, slot = record['cycle'], record['phase'], record['slot']
    assert (phase, cycle, slot) == expected_frame and f['id'] == event
    assert set(f) == {'id', 'context', 'action', 'outcome', 'propensity', 'policy_id'}
    prefix = ((FAMILIES.index(spec['family'])*100+seed)*20+cycle+2)*10+{'warm': 0, 'train': 1, 'eval': 2}[phase]
    context_slot = 64+(slot-64)//2 if phase == 'train' and slot >= 64 else slot
    context_rng = random.Random(211000000000+10000*prefix+context_slot)
    noise_rng = random.Random(211900000000+10000*prefix+slot)
    row = [context_rng.randrange(2) for _ in range(4)]
    action_u, outcome_u = noise_rng.random(), noise_rng.random()
    assert f['context'] == row and private['action_u'] == action_u and private['outcome_u'] == outcome_u
    base = known[f['policy_id']]['actions'][context_index(row)]
    epsilon = 1. if phase == 'warm' else .2
    assert record['epsilon'] == epsilon and private['base_action'] == base
    action = int(action_u < (1-epsilon)*base+epsilon/2)
    assert f['action'] == action and private['actions'] == [-1, -1, -1, action]
    assert abs(f['propensity']-((1-epsilon)*int(action == base)+epsilon/2)) < 1e-15
    target = spec['flip']
    for j in spec['relevant']:
        target ^= row[j]
    if spec['switch_cycle'] is not None and cycle >= spec['switch_cycle']:
        target ^= 1
    probability = .5 if spec['family'] == 'noise' else .9 if action == target else .1
    assert f['outcome'] == int(outcome_u < probability)
    assert private['terminal'] == ('SUCCESS' if f['outcome'] else 'FAIL')
    assert record['learn'] == (phase != 'eval')


def trial_expected(pairs, index, mean_arm, same_snapshot):
    if same_snapshot:
        assert not pairs
        return 'same_snapshot', 0., 0.
    plus, minus = [0.]*4, [0.]*4
    threshold = -math.log(.05/(index*(index+1)))
    def log_mean(values):
        peak = max(values)
        return peak+math.log(sum(math.exp(v-peak) for v in values)/4)
    status = 'continue'
    for t, (old, new) in enumerate(pairs, 1):
        assert status == 'continue'
        difference = new['public']['outcome']-old['public']['outcome']
        assert old['public']['context'] == new['public']['context']
        assert old['private']['outcome_u'] != new['private']['outcome_u']
        for j, q in enumerate((.25, .5, .75, 1.)):
            p, m = 1+q*difference, 1-q*difference
            plus[j] += math.log(p) if p else -math.inf
            minus[j] += math.log(m) if m else -math.inf
        if mean_arm:
            if t == 8:
                status = 'adopt' if sum(b['public']['outcome']-a['public']['outcome'] for a, b in pairs) > 0 else 'unresolved_keep'
        elif log_mean(plus) >= threshold:
            status = 'adopt'
        elif log_mean(minus) >= threshold:
            status = 'not_worth_cost'
        elif t == 128:
            status = 'unresolved_keep'
    assert status != 'continue'
    return status, log_mean(plus), log_mean(minus)


def audit_shard(job):
    family, seed = job
    folder = HERE/'shards'/f'{family}_s{seed:02d}'
    exit_record = json.loads((folder/'exit.json').read_text())
    assert exit_record['exit_code'] == 0 and not exit_record['timed_out']
    native = json.loads((folder/'native_summary.json').read_text())
    assert sha(folder/'raw.jsonl.gz') == native['raw_sha256']
    diagnostic = {'max_log_weight_error': 0., 'max_predictive_error': 0.,
                  'floating_tie_action_differences': 0, 'policies_verified': 0}
    frames = [('eval', -1, i) for i in range(128)]+[('warm', -1, i) for i in range(64)]
    for cycle in range(6):
        frames += [('train', cycle, i) for i in range(320)]+[('eval', cycle, i) for i in range(128)]
    results, record_count, ended = [], 0, False
    with gzip.open(folder/'raw.jsonl.gz', 'rt', encoding='utf-8') as stream:
        for line in stream:
            record_count += 1
            record = json.loads(line)
            assert json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n' == line
            kind = record['kind']
            if kind == 'shard_start':
                assert record['family'] == family and record['seed'] == seed
            elif kind == 'run_begin':
                arm, spec = record['arm'], record['spec']
                generator = random.Random(21141000+101*seed+FAMILIES.index(family))
                order = {'single': 1, 'triple': 3, 'switch_pair': 2, 'noise': 0}[family]
                assert spec == {'family': family, 'relevant': sorted(generator.sample(range(4), order)),
                                'flip': generator.randrange(2), 'switch_cycle': 3 if family == 'switch_pair' else None}
                history, known, models = [], {}, {}
                event = learned = training_success = warm_success = 0
                phase_success, phase_counts = Counter(), Counter()
                structure_count, replay_reads = 10, 0
                decisions, evals, nominations = [], [], []
                pair_records, ranking = [], []
                selected = bank = None
                verify_policy(record['initial'], history, models, known, diagnostic)
                active = record['initial']['id']
            elif kind == 'episode':
                assert record['arm'] == arm
                audit_episode(record, spec, seed, known, frames[event], event)
                f = record['public']
                event += 1
                phase, cycle, slot = record['phase'], record['cycle'], record['slot']
                phase_success[phase, cycle] += f['outcome']
                phase_counts[phase, cycle] += 1
                if record['paired']:
                    expected_policy = active if record['role'] == 'reference' else selected
                    assert f['policy_id'] == expected_policy and phase == 'train' and slot >= 64
                    assert record['role'] == ('reference' if len(pair_records) % 2 == 0 else 'candidate')
                    pair_records.append(record)
                else:
                    assert f['policy_id'] == active
                if record['learn']:
                    history.append(f)
                    learned += 1
                    if phase == 'train':
                        training_success += f['outcome']
                    else:
                        warm_success += f['outcome']
                if phase == 'train' and 32 <= slot < 64:
                    ranking.append(f)
            elif kind == 'bank':
                assert record['memory_ids'] == [f['id'] for f in history]
                assert record['incumbent']['id'] == active
                verify_policy(record['incumbent'], history, models, known, diagnostic)
                bank = record['candidates']
                assert [tuple(p['meta'][1]) for p in bank] == STRUCTURES[:structure_count]
                for policy in bank:
                    assert policy['meta'][5] == (0. if arm == 'pooled_history' else .05)
                    verify_policy(policy, history, models, known, diagnostic)
                ranking, pair_records = [], []
            elif kind == 'nomination':
                def score(policy):
                    # Exact native ordered accumulation, not builtin float sum.
                    total = 0.
                    for f in ranking:
                        total += ((.8*int(f['action'] == policy['actions'][context_index(f['context'])])+.1)
                                  *f['outcome']/f['propensity'])
                    return total/len(ranking)
                assert len(ranking) == 32 and record['ranking_ids'] == [f['id'] for f in ranking]
                scores = [score(p) for p in bank]
                assert max(abs(a-b) for a, b in zip(scores, record['candidate_scores'])) < 1e-12
                assert abs(score(known[active])-record['reference_score']) < 1e-12
                eligible = [i for i, p in enumerate(bank) if p['id'] != active]
                chosen = max(eligible, key=lambda i: scores[i]) if eligible else None
                assert chosen == record['chosen']
                selected = active if chosen is None else bank[chosen]['id']
                assert record['candidate'] == selected and record['selection_cutoff'] == ranking[-1]['id']
                nominations.append(record)
            elif kind == 'decision':
                cycle = record['cycle']
                assert record['reference'] == active and record['candidate'] == selected
                assert record['trial_index'] == cycle+1 and record['horizon'] == 256
                assert record['switch_cost'] == record['effect_cost_threshold'] == record['pair_cost_spent'] == 0
                assert len(pair_records) % 2 == 0
                pairs = list(zip(pair_records[::2], pair_records[1::2]))
                status, lp, lm = trial_expected(pairs, cycle+1, arm == 'mean_eight', selected == active)
                assert record['status'] == status and record['pairs'] == len(pairs)
                assert record['max_pairs'] == (8 if arm == 'mean_eight' else 128)
                assert record['alpha_spent'] == (None if arm == 'mean_eight' else .05/((cycle+1)*(cycle+2)))
                for actual, expected in ((record['log_e_plus'], lp), (record['log_e_minus'], lm)):
                    assert actual == '-inf' if expected == -math.inf else abs(actual-expected) < 1e-12
                ref_n = expected_numerator(known[active], spec, cycle)
                new_n = expected_numerator(known[selected], spec, cycle)
                same = known[active]['actions'] == known[selected]['actions']
                adopt = status == 'adopt'
                diagnostics = {'cycle': cycle, 'status': status, 'pairs': len(pairs),
                               'effect': (new_n-ref_n)/50, 'same_behavior': same,
                               'reference_expected': ref_n/50, 'candidate_expected': new_n/50,
                               'adopt': adopt, 'positive_missed': new_n > ref_n and not adopt}
                if adopt:
                    active = selected
                    assert record['growth'] is None
                else:
                    budget = 0 if arm == 'fixed_order' else 16
                    added, spent = [], 0
                    while structure_count < len(STRUCTURES):
                        candidate_structure = STRUCTURES[structure_count]
                        cells = 2**len(candidate_structure)
                        if spent+cells > budget:
                            break
                        added.append(list(candidate_structure))
                        structure_count += 1
                        spent += cells
                    assert record['growth']['added'] == added and record['growth']['cells_spent'] == spent
                    replay_reads += len(added)*len(history)
                assert record['active_identity'] == active
                decisions.append(diagnostics)
            elif kind == 'cycle_end':
                assert record['memory_facts'] == len(history) == 64+320*(record['cycle']+1)
                assert record['training_successes'] == phase_success['train', record['cycle']]
                assert record['structures'] == structure_count and record['replay_reads'] == replay_reads
                assert record['ordinary_after_trial'] == 256-2*decisions[-1]['pairs']
            elif kind == 'evaluation':
                cycle = record['cycle']
                assert record['policy_id'] == active and record['episodes'] == phase_counts['eval', cycle] == 128
                assert record['successes'] == phase_success['eval', cycle]
                assert record['learned_facts'] == len(history)
                evals.append({'checkpoint': record['checkpoint'], 'success': record['successes']/128,
                              'expected': expected_numerator(known[active], spec, cycle)/50})
            elif kind == 'run_end':
                assert event == 2880 and learned == len(history) == 1984 and len(evals) == 7
                assert record['episodes'] == event and record['steps'] == 4*event
                assert record['trial_episodes'] == 2*sum(d['pairs'] for d in decisions)
                assert record['adoptions'] == sum(d['adopt'] for d in decisions)
                assert record['original_parameters_unchanged'] and record['replay_reads'] == replay_reads
                results.append({'family': family, 'seed': seed, 'arm': arm,
                                'evaluation_mean': statistics.mean(e['success'] for e in evals[1:]),
                                'expected_mean': statistics.mean(e['expected'] for e in evals[1:]),
                                'evaluation_final': evals[-1]['success'], 'expected_final': evals[-1]['expected'],
                                'learning_success_rate': (training_success+warm_success)/1984,
                                'learning_failures': 1984-training_success-warm_success,
                                'cycle_training_success': [phase_success['train', c]/320 for c in range(6)],
                                'checkpoints': evals, 'decisions': decisions,
                                'trial_pairs': sum(d['pairs'] for d in decisions),
                                'same_behavior_pairs': sum(d['pairs'] for d in decisions if d['same_behavior']),
                                'positive_adoptions': sum(d['adopt'] and d['effect'] > 0 for d in decisions),
                                'zero_adoptions': sum(d['adopt'] and d['effect'] == 0 for d in decisions),
                                'negative_adoptions': sum(d['adopt'] and d['effect'] < 0 for d in decisions),
                                'positive_candidates_missed': sum(d['positive_missed'] for d in decisions),
                                'replay_reads': replay_reads, 'cpu_seconds': record['cpu_seconds'],
                                'wall_seconds': record['wall_seconds'], 'timings': record['timings'],
                                'final_structures': len(record['final_structures']),
                                'buffer_bytes': record['buffer_bytes']})
            elif kind == 'shard_end':
                assert record['input_unchanged'] and record['torch_rng_unchanged'] and record['runs'] == 4
                ended = True
            else:
                raise AssertionError(f'Unexpected raw record {kind}')
    assert ended and record_count == native['records'] and len(results) == 4
    result = {'family': family, 'seed': seed, 'records': record_count, 'runs': results, 'diagnostic': diagnostic,
              'raw_sha256': native['raw_sha256'], 'full_eof': True}
    with (folder/'stored_review_v212.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    return result


def main():
    started = time.perf_counter()
    contract = json.loads((HERE/'contract.json').read_text(encoding='utf-8'))
    before = {path: sha(ROOT/path) for path in contract['input_sha256']}
    assert before == contract['input_sha256']
    native_exit = json.loads((HERE/'native_exit.json').read_text())
    assert native_exit['completed'] == 24 and native_exit['failed_or_timed_out'] == 0
    with (HERE/'audit_claim_v212.json').open('x', encoding='utf-8') as stream:
        json.dump({'utc': datetime.now(timezone.utc).isoformat(), 'auditor_sha256': sha(Path(__file__)),
                   'native_exit_sha256': sha(HERE/'native_exit.json'), 'workers': 4}, stream, indent=2)
    jobs = [(family, seed) for family in FAMILIES for seed in range(6)]
    revision = json.loads((HERE/'review_revision_contract.json').read_text(encoding='utf-8'))
    assert sha(Path(__file__)) == revision['new_reviewer_sha256']
    assert sha(HERE/'audit_and_analyze.py') == revision['original_reviewer_sha256']
    shards, pending = [], []
    for family, seed in jobs:
        key = f'{family}_s{seed:02d}'
        folder = HERE/'shards'/key
        if key in revision['completed_stored_reviews']:
            binding = revision['completed_stored_reviews'][key]
            assert sha(folder/'stored_review.json') == binding['review_sha256']
            assert sha(folder/'raw.jsonl.gz') == binding['raw_sha256']
            result = json.loads((folder/'stored_review.json').read_text())
            assert result['full_eof'] and result['raw_sha256'] == binding['raw_sha256']
            shards.append(result)
        else:
            assert key in revision['remaining_shards']
            pending.append((family, seed))
    with ProcessPoolExecutor(max_workers=4) as pool:
        shards.extend(pool.map(audit_shard, pending))
    runs = [run for shard in shards for run in shard['runs']]
    tables = []
    for family in FAMILIES:
        for arm in ARMS:
            selected = [r for r in runs if r['family'] == family and r['arm'] == arm]
            mean_fields = ('evaluation_mean', 'expected_mean', 'evaluation_final', 'expected_final',
                           'learning_success_rate', 'learning_failures', 'cpu_seconds', 'wall_seconds', 'buffer_bytes')
            sum_fields = ('trial_pairs', 'same_behavior_pairs', 'positive_adoptions', 'zero_adoptions',
                          'negative_adoptions', 'positive_candidates_missed', 'replay_reads')
            tables.append({'family': family, 'arm': arm, 'seeds': 6,
                           **{k: statistics.mean(r[k] for r in selected) for k in mean_fields},
                           **{k: sum(r[k] for r in selected) for k in sum_fields},
                           'expected_curve': [statistics.mean(r['checkpoints'][i]['expected'] for r in selected) for i in range(7)],
                           'measured_curve': [statistics.mean(r['checkpoints'][i]['success'] for r in selected) for i in range(7)]})
    contrasts = []
    rng = random.Random(21199001)
    for family in FAMILIES:
        full = {r['seed']: r for r in runs if r['family'] == family and r['arm'] == 'full'}
        for arm in ARMS[1:]:
            other = {r['seed']: r for r in runs if r['family'] == family and r['arm'] == arm}
            for metric in ('evaluation_mean', 'learning_success_rate'):
                differences = [full[s][metric]-other[s][metric] for s in range(6)]
                bootstrap = sorted(statistics.mean(differences[rng.randrange(6)] for _ in range(6)) for _ in range(2000))
                contrasts.append({'family': family, 'full_minus': arm, 'metric': metric,
                                  'paired_seed_differences': differences, 'mean': statistics.mean(differences),
                                  'exploratory_95pct_interval': [bootstrap[49], bootstrap[1949]],
                                  'not_confirmatory_family_inference': True})
    after = {path: sha(ROOT/path) for path in before}
    assert after == before
    output = {'schema': 'v211-first-independent-stored-review', 'runs': runs, 'tables': tables,
              'contrasts': contrasts, 'shards': len(shards), 'canonical_records': sum(s['records'] for s in shards),
              'episodes': 2880*len(runs), 'steps': 11520*len(runs), 'learned_facts': 1984*len(runs),
              'evaluations': 896*len(runs), 'input_files_unchanged': len(before),
              'max_log_weight_error': max(s['diagnostic']['max_log_weight_error'] for s in shards),
              'max_predictive_error': max(s['diagnostic']['max_predictive_error'] for s in shards),
              'floating_tie_action_differences': sum(s['diagnostic']['floating_tie_action_differences'] for s in shards),
              'policy_states_verified': sum(s['diagnostic']['policies_verified'] for s in shards),
              'review_environment_runs': 0, 'review_neural_imports': 0, 'cached_completed_shards': len(revision['completed_stored_reviews']), 'newly_reviewed_shards': len(pending), 'original_review_exit_preserved': 1, 'wall_seconds': time.perf_counter()-started}
    with (HERE/'stored_review_result_v212.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(output, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({k: v for k, v in output.items() if k not in ('runs', 'tables', 'contrasts')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
