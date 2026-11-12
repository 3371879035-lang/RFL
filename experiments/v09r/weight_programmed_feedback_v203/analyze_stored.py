"""Reconstruct all V203 captured decisions and results with stdlib only."""
from collections import Counter
import datetime as dt
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def wire(route):
    return dict(default=route['default'], scopes=[dict(context=list(k), policy_id=v) for k, v in sorted(route['scopes'].items())])


def main():
    contract = read(HERE / 'contract.json')
    result = read(HERE / 'evidence/result.json')
    claim = read(HERE / 'evidence/claim.json')
    construction = read(HERE / 'evidence/construction.json')
    native = read(HERE / 'native_exit.json')
    assert native['exit_code'] == 0 and native['interruption'] is None
    assert sha(HERE / 'evidence/initial_written.pt') == construction['checkpoint_sha256']
    assert claim['inputs'] == result['unchanged_inputs']
    for rel, digest in claim['inputs'].items():
        assert sha(ROOT / rel) == digest
    collected, counts, diagnosis = [], Counter(), {}
    for seed in contract['seeds']:
        stored = read(HERE / 'evidence' / f'{seed}_result.json')
        run_index, episode_id = 0, 0
        with gzip.open(HERE / 'evidence' / f'{seed}.jsonl.gz', 'rt', encoding='utf-8') as stream:
            def take(kind, family, variant, cycle=None):
                row = json.loads(next(stream))
                assert row['kind'] == kind and row['seed'] == seed
                assert row['family'] == family and row['variant'] == variant
                if cycle is not None:
                    assert row['cycle'] == cycle
                counts[kind] += 1
                return row

            for family in contract['families']:
                for variant in contract['variants']:
                    training_records, steps_count, episodes_count = 0, 0, 0
                    adopted_contexts, changed_cycles = 0, 0
                    sources = {-1: 0}
                    route = dict(default=-1, scopes={})
                    evaluation, shadow = [], []
                    diag = diagnosis.setdefault((family, variant), Counter())

                    def episode(phase, index, cycle, routing=None, fixed_id=None, discovery=False):
                        nonlocal episode_id, steps_count, episodes_count
                        row = take('episode', family, variant, cycle)
                        episode_id += 1
                        assert row['episode_id'] == episode_id
                        assert row['phase'] == phase and row['index'] == index and row['case'] == index % 4
                        if discovery:
                            expected_id, expected_source = f'discovery-{cycle}-{index}', training_records
                        else:
                            expected_id = fixed_id if fixed_id is not None else routing['scopes'].get(tuple(row['initial_context']), routing['default'])
                            expected_source = sources[expected_id]
                        assert row['policy_id'] == expected_id and row['policy_source_records'] == expected_source
                        steps = row['transitions']
                        expected_length = (2 if index % 2 == 0 else 5) if family == 'delayed_choice' else (3 if family == 'joint_sequence' else 2)
                        assert len(steps) == expected_length and steps[0]['context'] == row['initial_context']
                        for j, step in enumerate(steps):
                            if j:
                                assert step['context'] == steps[j - 1]['successor']
                            assert step['terminal'] == (j == len(steps) - 1)
                            assert step['known'] == [step['terminal']] * 3
                            assert len(step['context']) == len(step['successor']) == len(step['action_descriptor']) == 6
                            assert all(math.isfinite(v) for v in step['scores'])
                            random, tie = row['action_tape'][j]
                            choices = [0, 1] if discovery and random < .1 else [i for i, score in enumerate(step['scores']) if abs(score - max(step['scores'])) <= 1.000001e-6]
                            assert step['chosen'] == choices[min(int(tie * len(choices)), len(choices) - 1)]
                            if not step['terminal']:
                                assert step['facts'] == [0., 0., 0.]
                        assert row['final_facts'] == steps[-1]['facts']
                        assert row['value'] == row['final_facts'][0] and row['value'] in (0., 1.)
                        assert row['final_facts'][1] == 1. - row['value']
                        assert math.isclose(row['final_facts'][2], 1. / expected_length, abs_tol=1e-7)
                        steps_count += len(steps)
                        episodes_count += 1
                        counts['transitions'] += len(steps)
                        counts[phase] += 1
                        return row

                    for cycle in range(16):
                        for j in range(4):
                            row = episode('discovery', j, cycle, discovery=True)
                            training_records += len(row['transitions'])
                        sources[cycle] = training_records
                        before = dict(default=route['default'], scopes=dict(route['scopes']))
                        new, old, contexts, trial_records = [], [], [], 0
                        for j in range(8):
                            a = episode('candidate_trial', j, cycle, fixed_id=cycle)
                            b = episode('incumbent_trial', j, cycle, routing=before)
                            assert a['initial_context'] == b['initial_context']
                            assert a['outcome_uniforms'] == b['outcome_uniforms'] and a['action_tape'] == b['action_tape']
                            contexts.append(a['initial_context'])
                            new.append(a['final_facts'])
                            old.append(b['final_facts'])
                            trial_records += len(a['transitions']) + len(b['transitions'])
                        decision = take('decision', family, variant, cycle)
                        assert decision['contexts'] == contexts
                        assert decision['candidate_actual'] == new and decision['incumbent_actual'] == old
                        assert decision['candidate_source_records'] == training_records
                        assert decision['routing_before'] == wire(before)
                        verdict = decision['verdict']
                        after = dict(default=before['default'], scopes=dict(before['scopes']))
                        differences = [a[0] - b[0] for a, b in zip(new, old)]
                        scopes = sorted(set(map(tuple, contexts)))
                        if variant in ('v203_full', 'v203_global_age'):
                            assert verdict['contexts'] == [list(x) for x in scopes]
                            assert verdict['paired_differences'] == differences
                            changes = 0
                            for i, context in enumerate(scopes):
                                values = [d for c, d in zip(contexts, differences) if tuple(c) == context]
                                estimate = sum(values) / (1. + len(values))
                                stderr = statistics.stdev(values) / math.sqrt(len(values)) if len(values) > 1 else 0.
                                adopt = len(values) >= 2 and estimate > 0.
                                assert verdict['counts'][i] == len(values)
                                assert abs(verdict['raw_mean_differences'][i] - statistics.mean(values)) < 1e-6
                                assert abs(verdict['estimates'][i] - estimate) < 1e-6
                                assert abs(verdict['standard_errors'][i] - stderr) < 1e-6
                                assert verdict['adopt'][i] == adopt
                                diag['local_scope_tests'] += 1
                                diag['positive_scopes_adopted'] += int(adopt)
                                if adopt:
                                    after['scopes'][context] = cycle
                                    changes += 1
                        elif variant == 'v203_no_gate':
                            assert verdict['accept']
                            changes = len(scopes)
                            after = dict(default=cycle, scopes={})
                        else:
                            average = statistics.mean(differences)
                            stderr = statistics.stdev(differences) / math.sqrt(8.)
                            margin = average - 2. * stderr
                            assert abs(verdict['mean_difference'] - average) < 1e-6
                            assert abs(verdict['standard_error'] - stderr) < 1e-6
                            assert abs(verdict['margin'] - margin) < 1e-6
                            assert verdict['paired_differences'] == differences and verdict['accept'] == (margin > 0.)
                            changes = len(scopes) if verdict['accept'] else 0
                            diag['positive_global_mean_rejected'] += int(average > 0. and not verdict['accept'])
                            if verdict['accept']:
                                after = dict(default=cycle, scopes={})
                        assert decision['changed_contexts'] == changes
                        assert decision['routing_after'] == wire(after)
                        adopted_contexts += changes
                        changed_cycles += int(changes > 0)
                        diag['cycles'] += 1
                        diag['changed_cycles'] += int(changes > 0)
                        training_records += trial_records
                        current_values, old_values = [], []
                        for j in range(8):
                            a = episode('evaluation_after', j, cycle, routing=after)
                            b = episode('evaluation_before', j, cycle, routing=before)
                            assert a['initial_context'] == b['initial_context']
                            assert a['outcome_uniforms'] == b['outcome_uniforms'] and a['action_tape'] == b['action_tape']
                            if a['policy_id'] == b['policy_id']:
                                assert a['transitions'] == b['transitions']
                                diag['unchanged_policy_identical_eval_pairs'] += 1
                            else:
                                diag['changed_policy_eval_pairs'] += 1
                            diag['heldout_wins'] += int(a['value'] > b['value'])
                            diag['heldout_losses'] += int(a['value'] < b['value'])
                            current_values.append(a['value'])
                            old_values.append(b['value'])
                        evaluation.append(current_values)
                        shadow.append(old_values)
                        route = after
                    row = take('run_end', family, variant)
                    row.pop('kind')
                    assert row == stored['results'][run_index]
                    run_index += 1
                    assert row['episodes'] == episodes_count == 576
                    assert row['environment_transitions'] == steps_count
                    assert row['memory_records_written'] == training_records
                    assert row['changed_cycles'] == changed_cycles and row['adopted_contexts'] == adopted_contexts
                    assert row['evaluation_values'] == evaluation and row['shadow_before_values'] == shadow
                    assert row['parameter_hash_before'] == row['parameter_hash_after']
                    if variant != 'v202_original':
                        assert row['parameter_hash_before'] == construction['parameter_hash']
                    for label, sample in [('first4_cycles', evaluation[:4]), ('last4_cycles', evaluation[-4:]),
                                          ('whole_evaluation', evaluation), ('change_first2_cycles', evaluation[8:10])]:
                        assert row[label] == statistics.mean(v for batch in sample for v in batch)
                    pairs = [(a, b) for aa, bb in zip(evaluation, shadow) for a, b in zip(aa, bb)]
                    assert row['heldout_adoption_difference'] == statistics.mean(a - b for a, b in pairs)
                    assert row['heldout_adoption_wins'] == sum(a > b for a, b in pairs)
                    assert row['heldout_adoption_losses'] == sum(a < b for a, b in pairs)
                    collected.append(row)
            assert stream.read() == ''
        assert run_index == 20
    assert collected == result['results']
    assert counts['episode'] == result['episodes'] == 184320
    assert counts['transitions'] == result['environment_transitions'] == 483840
    aggregates, paired = [], []
    for family in contract['families']:
        for variant in contract['variants']:
            rows = [r for r in collected if r['family'] == family and r['variant'] == variant]
            aggregate = dict(family=family, variant=variant, seeds=len(rows))
            for key in ['first4_cycles', 'last4_cycles', 'whole_evaluation', 'change_first2_cycles', 'heldout_adoption_difference']:
                aggregate[key] = statistics.mean(r[key] for r in rows)
            for key in ['changed_cycles', 'adopted_contexts', 'environment_transitions', 'heldout_adoption_wins', 'heldout_adoption_losses']:
                aggregate[key] = sum(r[key] for r in rows)
            aggregate['seed_last4'] = [r['last4_cycles'] for r in rows]
            aggregates.append(aggregate)
        for other in contract['variants'][1:]:
            differences = []
            for seed in contract['seeds']:
                a = next(r for r in collected if r['seed'] == seed and r['family'] == family and r['variant'] == 'v203_full')
                b = next(r for r in collected if r['seed'] == seed and r['family'] == family and r['variant'] == other)
                assert a['environment_transitions'] == b['environment_transitions']
                differences.append(a['last4_cycles'] - b['last4_cycles'])
            paired.append(dict(family=family, comparison='v203_full minus ' + other,
                               mean=statistics.mean(differences), seed_differences=differences,
                               positive=sum(d > 0 for d in differences), zero=sum(d == 0 for d in differences),
                               negative=sum(d < 0 for d in differences)))
    assert aggregates == result['aggregates']
    review = dict(status='COMPLETE_STORED_RECONSTRUCTION', model_calls=0, environment_calls=0,
                  native_exit_code=0, counts=dict(counts), all320_parameter_hash_pairs_equal=True,
                  unchanged_declared_inputs=len(claim['inputs']), checkpoint_sha256=construction['checkpoint_sha256'],
                  aggregates=aggregates, paired_seed_results=paired,
                  diagnostics=[dict(family=k[0], variant=k[1], **v) for k, v in diagnosis.items()],
                  review_source_sha256=sha(Path(__file__)), finished_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                  limitation='Same-team stored reconstruction, not independent expert certification or proof of causal attribution')
    with (HERE / 'evidence/stored_review.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(review, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({k: v for k, v in review.items() if k not in ('aggregates', 'paired_seed_results', 'diagnostics')}, indent=2))


if __name__ == '__main__':
    main()
