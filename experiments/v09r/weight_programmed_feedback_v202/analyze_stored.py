"""Stdlib reconstruction of all captured costs, evaluation and trial decisions.

No model forward pass, task execution, prior checker or new experiment occurs.
"""
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


def main():
    contract = read(HERE / 'contract.json')
    result = read(HERE / 'evidence/result.json')
    claim = read(HERE / 'evidence/claim.json')
    construction = read(HERE / 'evidence/construction.json')
    native = read(HERE / 'native_exit.json')
    assert native['exit_code'] == 0 and native['interruption'] is None
    assert sha(HERE / 'evidence/initial_written.pt') == construction['checkpoint_sha256']
    for rel, expected in claim['inputs'].items():
        assert sha(ROOT / rel) == expected
    collected, counts, gates = [], Counter(), {}
    for seed in contract['seeds']:
        source = read(HERE / 'evidence' / f'{seed}_result.json')
        source_index = 0
        expected_episode_id = 0
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
                    training_records, actual_steps, actual_episodes, adopted = 0, 0, 0, 0
                    policy_sources = {-1: 0}
                    incumbent = -1
                    evaluations = []
                    gate_counts = gates.setdefault((family, variant), Counter())

                    def episode(phase, index, cycle, policy_id, source_count):
                        nonlocal expected_episode_id, actual_steps, actual_episodes
                        row = take('episode', family, variant, cycle)
                        expected_episode_id += 1
                        assert row['episode_id'] == expected_episode_id
                        assert row['phase'] == phase and row['index'] == index and row['case'] == index % 4
                        assert row['policy_id'] == policy_id and row['policy_source_records'] == source_count
                        steps = row['transitions']
                        expected_length = (2 if index % 2 == 0 else 5) if family == 'delayed_choice' else (3 if family == 'joint_sequence' else 2)
                        assert len(steps) == expected_length
                        for j, step in enumerate(steps):
                            if j:
                                assert step['context'] == steps[j - 1]['successor']
                            assert step['terminal'] == (j == len(steps) - 1)
                            assert step['known'] == [step['terminal']] * 3
                            assert len(step['context']) == len(step['successor']) == len(step['action_descriptor']) == 6
                            assert all(math.isfinite(v) for v in step['scores'])
                            random, tie = row['action_tape'][j]
                            options = [0, 1] if phase == 'discovery' and random < .1 else [k for k, score in enumerate(step['scores']) if abs(score - max(step['scores'])) <= 1.000001e-6]
                            assert step['chosen'] == options[min(int(tie * len(options)), len(options) - 1)]
                            if not step['terminal']:
                                assert step['facts'] == [0., 0., 0.]
                        assert row['final_facts'] == steps[-1]['facts']
                        assert row['value'] == row['final_facts'][0]
                        assert row['final_facts'][0] in (0., 1.) and row['final_facts'][1] == 1. - row['value']
                        assert math.isclose(row['final_facts'][2], 1. / expected_length, abs_tol=1e-7)
                        actual_steps += len(steps)
                        actual_episodes += 1
                        counts['transitions'] += len(steps)
                        counts[phase] += 1
                        return row

                    for cycle in range(16):
                        for j in range(4):
                            row = episode('discovery', j, cycle, f'discovery-{cycle}-{j}', training_records)
                            training_records += len(row['transitions'])
                        policy_sources[cycle] = training_records
                        new, old, trial_records = [], [], 0
                        for j in range(8):
                            a = episode('candidate_trial', j, cycle, cycle, policy_sources[cycle])
                            b = episode('incumbent_trial', j, cycle, incumbent, policy_sources[incumbent])
                            assert a['outcome_uniforms'] == b['outcome_uniforms'] and a['action_tape'] == b['action_tape']
                            new.append(a['final_facts'])
                            old.append(b['final_facts'])
                            trial_records += len(a['transitions']) + len(b['transitions'])
                        decision = take('decision', family, variant, cycle)
                        assert decision['candidate_source_records'] == training_records
                        assert decision['candidate_actual'] == new and decision['incumbent_actual'] == old
                        assert decision['incumbent_before'] == incumbent
                        verdict = decision['verdict']
                        differences = [a[0] - b[0] for a, b in zip(new, old)]
                        average = statistics.mean(differences)
                        stderr = statistics.stdev(differences) / math.sqrt(8)
                        margin = average - 2. * stderr
                        if variant != 'v200_original':
                            assert verdict['paired_differences'] == differences
                            assert abs(verdict['mean_difference'] - average) < 1e-6
                            assert abs(verdict['standard_error'] - stderr) < 1e-6
                            assert abs(verdict['margin'] - margin) < 1e-6
                        if variant in ('v200_original', 'v202_no_gate'):
                            assert verdict['accept']
                        else:
                            assert verdict['accept'] == (margin > 0.)
                        gate_counts['decisions'] += 1
                        gate_counts['accepted'] += int(verdict['accept'])
                        gate_counts['positive_actual_mean_but_rejected'] += int(average > 0 and not verdict['accept'])
                        gate_counts['nonpositive_actual_mean_accepted'] += int(average <= 0 and verdict['accept'])
                        gate_counts['zero_actual_mean_rejected'] += int(average == 0 and not verdict['accept'])
                        if verdict['accept']:
                            incumbent = cycle
                            adopted += 1
                        assert decision['incumbent_after'] == incumbent
                        # This is AFTER the actual decision, never before trials.
                        training_records += trial_records
                        values = []
                        for j in range(4):
                            row = episode('evaluation', j, cycle, incumbent, policy_sources[incumbent])
                            values.append(row['value'])
                        evaluations.append(values)
                    row = take('run_end', family, variant)
                    row.pop('kind')
                    assert row == source['results'][source_index]
                    source_index += 1
                    assert row['evaluation_values'] == evaluations
                    assert row['episodes'] == actual_episodes == 384
                    assert row['environment_transitions'] == actual_steps
                    assert row['memory_records_written'] == training_records
                    assert row['adoptions'] == adopted
                    assert row['parameter_hash_before'] == row['parameter_hash_after']
                    if variant != 'v200_original':
                        assert row['parameter_hash_before'] == construction['parameter_hash']
                    for label, sample in [('first4_cycles', evaluations[:4]), ('last4_cycles', evaluations[-4:]),
                                          ('whole_evaluation', evaluations), ('after_reversal_first2', evaluations[8:10])]:
                        assert statistics.mean(v for batch in sample for v in batch) == row[label]
                    collected.append(row)
            assert stream.read() == ''
        assert source_index == 12
    assert collected == result['results']
    assert counts['episode'] == result['episodes'] == 36864
    assert counts['transitions'] == result['environment_transitions'] == 104448
    aggregates = []
    paired = []
    for family in contract['families']:
        for variant in contract['variants']:
            rows = [r for r in collected if r['family'] == family and r['variant'] == variant]
            aggregate = dict(family=family, variant=variant, seeds=len(rows),
                 first4_cycles=statistics.mean(r['first4_cycles'] for r in rows),
                 last4_cycles=statistics.mean(r['last4_cycles'] for r in rows),
                 whole_evaluation=statistics.mean(r['whole_evaluation'] for r in rows),
                 after_reversal_first2=statistics.mean(r['after_reversal_first2'] for r in rows),
                 adoptions=sum(r['adoptions'] for r in rows), seed_last4=[r['last4_cycles'] for r in rows],
                 environment_transitions=sum(r['environment_transitions'] for r in rows))
            aggregates.append(aggregate)
        for other in ['v200_original', 'v202_no_gate', 'v202_no_successor']:
            values = []
            for seed in contract['seeds']:
                a = next(r for r in collected if r['seed'] == seed and r['family'] == family and r['variant'] == 'v202_full')
                b = next(r for r in collected if r['seed'] == seed and r['family'] == family and r['variant'] == other)
                assert a['environment_transitions'] == b['environment_transitions']
                values.append(a['last4_cycles'] - b['last4_cycles'])
            paired.append(dict(family=family, comparison='v202_full minus ' + other,
                               mean=statistics.mean(values), seed_differences=values))
    assert aggregates == result['aggregates']
    review = dict(status='COMPLETE_STORED_RECONSTRUCTION', model_calls=0, environment_calls=0,
                  native_exit_code=0, counts=dict(counts), all96_parameter_hash_pairs_equal=True,
                  unchanged_input_files=len(claim['inputs']), checkpoint_sha256=construction['checkpoint_sha256'],
                  aggregates=aggregates, paired_seed_results=paired,
                  adoption_diagnostics=[dict(family=k[0], variant=k[1], **v) for k, v in gates.items()],
                  limitation='Same-team stdlib stored review, not independent expert validation or causal identifiability proof',
                  review_source_sha256=sha(Path(__file__)), finished_utc=dt.datetime.now(dt.timezone.utc).isoformat())
    with (HERE / 'evidence/stored_review.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(review, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({k: v for k, v in review.items() if k not in ('aggregates', 'paired_seed_results')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
