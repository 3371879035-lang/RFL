"""Independent stored arithmetic review; no learner/task modules imported."""
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import datetime as dt
import gzip
import hashlib
import json
from pathlib import Path
import time
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def close(a, b, tol=5e-5):
    assert np.allclose(a, b, atol=tol, rtol=0.), (a, b)


def kernel(q, memory, minimum, scale):
    distance = (((np.array(memory) - minimum) / scale - (np.array(q) - minimum) / scale) ** 2).sum(-1)
    return np.exp(np.clip(-20. * distance, -80., 0.))


def review_seed(seed):
    counts, maximum_loss_error = Counter(), 0.
    comparisons, finished, ingested_ids = {}, [], set()
    context_sets, pending_trials, nodes, policy_counts = set(), {}, [], {-1: 0}
    memory, writes = [], 0
    active = None
    outcomes = {'evaluation_after': [], 'evaluation_before': []}
    adopted, unseen_adopted, exact_eval_matches = 0, 0, 0
    episode_by_id = {}
    np_rng = np.random.default_rng(seed)
    labels, small = np_rng.permutation(64), np_rng.permutation(16)
    columns, actions = np_rng.permutation(6), np.eye(6, dtype=np.float32)[np_rng.permutation(2)]
    good = np_rng.integers(0, 2, 4)
    thresholds, signs = np_rng.uniform(-.35, .35, 3), np_rng.integers(0, 2, 3)

    def geometry():
        if not memory:
            return np.empty((0, 12)), np.zeros(12), np.ones(12)
        features = np.array([x['feature'] for x in memory])
        minimum = features.min(0)
        span = features.max(0) - minimum
        return features, minimum, np.where(span > 0, span, 1.)

    def select(initial, route, stored_checks):
        checks = []
        for node in reversed(route):
            if node['kind'] == 'all':
                check = dict(adopt=True)
            elif node['kind'] == 'exact':
                check = dict(adopt=tuple(initial) in node['scopes'])
            else:
                weights = kernel(initial, node['contexts'], node['minimum'], node['scale'])
                mass = weights.sum()
                estimate = weights @ node['differences'] / (1. + mass)
                recorded = stored_checks[len(checks)]
                close(mass, recorded['mass'], 5e-4)
                close(estimate, recorded['estimate'])
                close(weights, recorded['actual_trial_weights'])
                # Dot-product distance in binary32 can round the sign of a
                # mathematically near-zero margin. Check arithmetic against
                # independent real-distance RBF, but classify using the actual
                # stored binary32 margin/mass, not a different precision's bit.
                check = dict(adopt=bool(recorded['mass'] >= 2. and recorded['estimate'] > 0.),
                             mass=float(mass), estimate=float(estimate), actual_trial_weights=weights.tolist())
            checks.append(dict(policy_id=node['policy_id'], **check))
            if check['adopt']:
                return node['policy_id'], checks
        return -1, checks

    with gzip.open(HERE / 'evidence' / f'{seed}.jsonl.gz', 'rt', encoding='utf-8') as stream:
        for line in stream:
            r = json.loads(line)
            counts[r['kind']] += 1
            key = (r['family'], r['variant'])
            if active is None:
                active = key
            assert key == active
            family, variant = key
            is_old = variant == 'v203_original'
            if r['kind'] == 'episode':
                ep_id, cycle, phase, index = r['episode_id'], r['cycle'], r['phase'], r['index']
                assert ep_id not in episode_by_id
                episode_by_id[ep_id] = r
                context_sets.add(tuple(r['initial_context']))
                counts[phase] += 1
                group = ('trial' if phase.endswith('_trial') else 'evaluation' if phase.startswith('evaluation_') else phase)
                def tape(role, tag, shape):
                    digest = hashlib.sha256(('v204|' + '|'.join(map(str, [seed, family, cycle, role, index, tag]))).encode()).digest()
                    return np.random.default_rng(int.from_bytes(digest[:8], 'little')).random(shape)
                close(r['initial_uniforms'], tape(group, 'initial', 2), 0.)
                close(r['action_tape'], tape(group, 'tie', (5, 2)), 0.)
                close(r['outcome_uniforms'], tape(phase if phase.endswith('_trial') else group, 'outcome', 5), 0.)
                x = 2. * r['initial_uniforms'][0] - 1.
                continuous = family.startswith('continuous_')
                depth = 5 if family == 'continuous_delayed' else 3 if continuous else 2
                prefix = []
                def observation():
                    t = len(prefix)
                    node = (2 ** t - 1 + sum(bit * 2 ** (t - j - 1) for j, bit in enumerate(prefix))
                            if family == 'continuous_joint' else 0 if t == 0 else 1 + prefix[0] * 5 + t - 1)
                    if continuous:
                        code = int(small[node])
                        out = np.array([*[(code >> j) & 1 for j in range(4)], (x + 1.) / 2., x ** 2], np.float32)
                    else:
                        code = int(labels[r['case'] * 11 + node])
                        out = np.array([(code >> j) & 1 for j in range(6)], np.float32)
                    return out[columns]
                close(r['initial_context'], observation(), 0.)
                if phase == 'candidate_trial':
                    policy_counts.setdefault(cycle, writes)
                    assert policy_counts[cycle] == writes and r['policy_id'] == cycle
                elif phase == 'discovery':
                    assert r['policy_id'] == f'discovery-{cycle}-{index}' and r['policy_source_records'] == writes
                else:
                    route = nodes[:-1] if phase == 'evaluation_before' else nodes
                    expected_id, expected_checks = select(r['initial_context'], route, r['route_checks'])
                    assert expected_id == r['policy_id']
                    assert len(expected_checks) == len(r['route_checks'])
                    for a, b in zip(expected_checks, r['route_checks']):
                        assert a['policy_id'] == b['policy_id'] and a['adopt'] == b['adopt']
                        if 'mass' in a:
                            close(a['mass'], b['mass'], 5e-4)
                            close(a['estimate'], b['estimate'])
                            close(a['actual_trial_weights'], b['actual_trial_weights'])
                if phase != 'discovery':
                    assert r['policy_source_records'] == policy_counts[r['policy_id']]
                assert len(r['transitions']) == depth
                for t, row in enumerate(r['transitions']):
                    counts['transitions'] += 1
                    close(row['context'], observation(), 0.)
                    scores = np.array(row['scores'])
                    assert np.isfinite(scores).all()
                    tape_values = r['action_tape'][t]
                    options = np.arange(2) if phase == 'discovery' and tape_values[0] < .1 else np.flatnonzero(np.isclose(scores, scores.max(), atol=1e-6, rtol=0.))
                    chosen = int(options[min(int(tape_values[1] * len(options)), len(options) - 1)])
                    assert chosen == row['chosen']
                    close(row['action_descriptor'], actions[chosen], 0.)
                    prefix.append(chosen)
                    close(row['successor'], observation(), 0.)
                    assert row['terminal'] == (t == depth - 1)
                    if not is_old:
                        probabilities = np.array(row['expert_probabilities'])
                        close(probabilities.sum(-1), np.ones(2), 2e-6)
                        assert (probabilities >= 0).all()
                    if t != depth - 1:
                        assert row['known'] == [False] * 3 and row['facts'] == [0.] * 3
                if family == 'continuous_joint':
                    desired = (x > thresholds).astype(int) ^ signs
                    success = float(np.array_equal(prefix, desired))
                else:
                    desired = int(x > thresholds[0]) ^ int(signs[0]) if continuous else int(good[r['case']])
                    if family in ('abrupt_change', 'continuous_abrupt') and cycle >= 8:
                        desired = 1 - desired
                    correct = prefix[0] == desired
                    success = float(correct) if family == 'continuous_delayed' else float(r['outcome_uniforms'][-1] < (.8 if correct else .2))
                close(r['final_facts'], np.array([success, 1. - success, 1. / depth], np.float32), 0.)
                assert r['transitions'][-1]['known'] == [True] * 3 and r['value'] == success
                assert r['transitions'][-1]['facts'] == r['final_facts']
                if phase.endswith('_trial'):
                    if phase == 'candidate_trial':
                        pending_trials[index] = r
                    else:
                        a = pending_trials[index]
                        assert a['initial_context'] == r['initial_context'] and a['action_tape'] == r['action_tape']
                        assert a['outcome_uniforms'] != r['outcome_uniforms']
                if phase.startswith('evaluation_'):
                    outcomes[phase].append(r['value'])
                    if phase == 'evaluation_after':
                        comparisons[index] = r
                        if r['policy_id'] == cycle:
                            adopted += 1
                            unseen_adopted += int(tuple(r['initial_context']) not in trial_scope)
                        exact_eval_matches += int(tuple(r['initial_context']) in trial_scope)
                    else:
                        a = comparisons[index]
                        assert a['initial_context'] == r['initial_context'] and a['outcome_uniforms'] == r['outcome_uniforms'] and a['action_tape'] == r['action_tape']
            elif r['kind'] == 'ingest':
                for entry in r['records']:
                    ep_id = entry['episode_id']
                    assert ep_id not in ingested_ids
                    ingested_ids.add(ep_id)
                    ep = episode_by_id[ep_id]
                    assert ep['phase'] in ('discovery', 'candidate_trial', 'incumbent_trial')
                    assert entry['source_records_before'] == writes
                    for row in ep['transitions']:
                        if not is_old and row['terminal']:
                            features, minimum, scale = geometry()
                            similarity = kernel(np.r_[row['context'], row['action_descriptor']], features, minimum, scale)
                            if memory:
                                order = np.argsort([-v['timestamp'] for v in memory])[::-1]
                                ordered = similarity[order]
                                newer = np.empty_like(similarity)
                                newer[order] = np.cumsum(ordered[::-1])[::-1] - ordered
                                weight = similarity[None, :] * np.exp(-np.log(2.) * np.array([1., 1. / 32.])[:, None] * newer[None, :])
                                valid = np.array([v['known'] for v in memory]) * np.array([v['terminal'] for v in memory])[:, None]
                                values = np.array([v['facts'] for v in memory])
                                prediction = (weight @ (valid * values) + .5) / (1. + weight @ valid)
                            else:
                                prediction = np.full((2, 3), .5)
                            losses = (prediction - np.array(row['facts'])[None, :]) ** 2
                            receipt = entry['terminal_prediction_receipt']
                            maximum_loss_error = max(maximum_loss_error, float(np.abs(losses - np.array(receipt['pre_observation_losses'])).max()))
                            close(losses, receipt['pre_observation_losses'])
                            assert receipt['source_records_before'] == writes and receipt['loss_known'] and receipt['observed_factual_channels'] == 3
                            counts['pre_observation_loss_receipts'] += 1
                        item = dict(feature=list(row['context']) + list(row['action_descriptor']), facts=row['facts'], known=row['known'], terminal=row['terminal'], timestamp=writes)
                        if len(memory) < 384:
                            memory.append(item)
                        else:
                            memory[writes % 384] = item
                        writes += 1
                    assert entry['source_records_after'] == writes
                assert r['source_records_after'] == writes
            elif r['kind'] == 'decision':
                assert r['source_records'] == writes and policy_counts[r['cycle']] == writes
                contexts, new, old = np.array(r['contexts']), np.array(r['candidate_actual']), np.array(r['incumbent_actual'])
                for j in range(16):
                    assert r['contexts'][j] == pending_trials[j]['initial_context']
                trial_scope = set(map(tuple, r['contexts']))
                difference = new[:, 0] - old[:, 0]
                v = r['verdict']
                if variant in ('v204_full', 'v204_fixed_age'):
                    _, minimum, scale = geometry()
                    close(v['minimum'], minimum[:6])
                    close(v['scale'], scale[:6])
                    close(v['differences'], difference)
                    nodes.append(dict(kind='kernel', policy_id=r['cycle'], contexts=contexts,
                                      differences=difference, minimum=np.array(v['minimum']), scale=np.array(v['scale'])))
                elif variant == 'v204_no_gate':
                    nodes.append(dict(kind='all', policy_id=r['cycle']))
                else:
                    scopes = np.unique(contexts, axis=0)
                    match = (scopes[:, None, :] == contexts[None, :, :]).all(-1)
                    n = match.sum(-1)
                    estimates = match @ difference / (1. + n)
                    accept = (n >= 2) & (estimates > 0.)
                    close(v['contexts'], scopes)
                    assert v['adopt'] == accept.tolist()
                    nodes.append(dict(kind='exact', policy_id=r['cycle'], scopes={tuple(c) for c, a in zip(scopes, accept) if a}))
            elif r['kind'] == 'run_end':
                after = np.array(outcomes['evaluation_after']).reshape(16, 8)
                before = np.array(outcomes['evaluation_before']).reshape(16, 8)
                assert r['evaluation_values'] == after.tolist() and r['shadow_before_values'] == before.tolist()
                for k, value in [('first4_cycles', after[:4].mean()), ('last4_cycles', after[-4:].mean()),
                                 ('change_first2_cycles', after[8:10].mean()), ('whole_evaluation', after.mean()),
                                 ('heldout_adoption_difference', after.mean() - before.mean())]:
                    close(r[k], value, 0.)
                assert r['heldout_adoption_wins'] == int((after > before).sum()) and r['heldout_adoption_losses'] == int((after < before).sum())
                assert r['memory_records_written'] == writes
                assert r['adopted_queries'] == adopted and r['adoption_queries'] == 128
                assert r['unique_initial_contexts'] == len(context_sets) and r['initial_context_records'] == 832
                assert r['parameter_hash_before'] == r['parameter_hash_after']
                assert r['episodes'] == 832
                assert r['environment_transitions'] == sum(len(e['transitions']) for e in episode_by_id.values())
                assert all((e['phase'] in ('discovery', 'candidate_trial', 'incumbent_trial')) == (i in ingested_ids)
                           for i, e in episode_by_id.items())
                finished.append(dict(result={k: v for k, v in r.items() if k != 'kind'},
                                     unseen_initial_adoptions=unseen_adopted, exact_trial_matches_in_evaluation=exact_eval_matches))
                active = None
                memory, writes, nodes, policy_counts = [], 0, [], {-1: 0}
                outcomes = {'evaluation_after': [], 'evaluation_before': []}
                adopted, unseen_adopted, exact_eval_matches = 0, 0, 0
                context_sets = set()
                episode_by_id = {}
            else:
                raise AssertionError(r['kind'])
    assert len(finished) == 25 and counts['episode'] == 20800
    stored = json.loads((HERE / 'evidence' / f'{seed}_result.json').read_text(encoding='utf-8'))
    assert stored['results'] == [x['result'] for x in finished]
    return dict(seed=seed, counts=dict(counts), maximum_loss_error=maximum_loss_error, runs=finished)


def main():
    import torch
    torch.set_num_threads(1)
    started = time.perf_counter()
    claim = json.loads((HERE / 'evidence/claim.json').read_text(encoding='utf-8'))
    native = json.loads((HERE / 'native_exit.json').read_text(encoding='utf-8'))
    assert native['exit_code'] == 0
    for p, h in claim['inputs'].items():
        assert sha(ROOT / p) == h, p
    checkpoint = HERE / 'evidence/initial_written.pt'
    payload = torch.load(checkpoint, map_location='cpu', weights_only=True)
    def phash(state):
        h = hashlib.sha256()
        for k, v in state.items():
            h.update(k.encode()); h.update(v.numpy().tobytes())
        return h.hexdigest()
    current_hash = phash(payload['state_dict'])
    old_hash = phash(torch.load(ROOT / claim['contract']['old_checkpoint'], map_location='cpu', weights_only=True)['state_dict'])
    with ProcessPoolExecutor(max_workers=4) as pool:
        batches = list(pool.map(review_seed, claim['contract']['seeds']))
    native_result = json.loads((HERE / 'evidence/result.json').read_text(encoding='utf-8'))
    rows = [x['result'] for b in batches for x in b['runs']]
    assert rows == native_result['results']
    for r in rows:
        assert r['parameter_hash_before'] == (old_hash if r['variant'] == 'v203_original' else current_hash)
    for a in native_result['aggregates']:
        selected = [r for r in rows if r['family'] == a['family'] and r['variant'] == a['variant']]
        assert a['seeds'] == len(selected) == 16
        for k in ['first4_cycles', 'last4_cycles', 'change_first2_cycles', 'whole_evaluation', 'heldout_adoption_difference']:
            close(a[k], sum(r[k] for r in selected) / len(selected), 0.)
        for k in ['environment_transitions', 'heldout_adoption_wins', 'heldout_adoption_losses', 'adopted_queries', 'adoption_queries']:
            assert a[k] == sum(r[k] for r in selected)
        assert a['seed_last4'] == [r['last4_cycles'] for r in selected]
        assert a['seed_change_first2'] == [r['change_first2_cycles'] for r in selected]
    counts = sum((Counter(b['counts']) for b in batches), Counter())
    assert counts['episode'] == 332800 and counts['transitions'] == native_result['environment_transitions']
    report = dict(status='COMPLETE_STORED_ARITHMETIC_REVIEW', native_exit_code=native['exit_code'],
                  new_learner_or_environment_calls=0, counts=dict(counts), reviewed_runs=400,
                  pre_observation_loss_maximum_absolute_error=max(b['maximum_loss_error'] for b in batches),
                  parameter_hash_pairs_unchanged=400, parameter_count=sum(v.numel() for v in payload['state_dict'].values()),
                  unchanged_input_pins=len(claim['inputs']), checkpoint_sha256=sha(checkpoint),
                  continuous_scope=[dict(seed=b['seed'], family=x['result']['family'], variant=x['result']['variant'],
                      unseen_initial_adoptions=x['unseen_initial_adoptions'], exact_trial_matches=x['exact_trial_matches_in_evaluation'],
                      unique_initial_contexts=x['result']['unique_initial_contexts']) for b in batches for x in b['runs'] if x['result']['family'].startswith('continuous_')],
                  aggregates=native_result['aggregates'], review_source_sha256=sha(__file__),
                  wall_seconds=time.perf_counter() - started, finished_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                  limitations='Stored arithmetic checks all worlds, choices from logged scores, pre-observation losses, routing, chronology and costs. Does not independently reconstruct every multi-step neural forward; not independent expert certification.')
    with (HERE / 'evidence/stored_review.json').open('x', encoding='utf-8', newline='\n') as f:
        json.dump(report, f, ensure_ascii=False, indent=2, allow_nan=False); f.write('\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('aggregates', 'continuous_scope')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
