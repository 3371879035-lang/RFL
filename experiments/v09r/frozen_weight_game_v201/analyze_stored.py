"""One read-only, stdlib review of V201 records; no model or world execution."""
from collections import Counter, deque
import datetime as dt
import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def mean(rows, key):
    return sum(r[key] for r in rows) / len(rows)


def main():
    contract = read(HERE / 'contract.json')
    result = read(HERE / 'evidence/result.json')
    claim = read(HERE / 'evidence/claim.json')
    native = read(HERE / 'native_exit.json')
    assert native['exit_code'] == 0 and native['interruption'] is None
    assert result['input_pins_after'] == claim['input_pins']
    for rel, pin in claim['input_pins'].items():
        assert sha(ROOT / rel) == pin['sha256']
        assert (ROOT / rel).stat().st_size == pin['bytes']
    counts = Counter()
    summaries, all_rows, diagnostics = {}, [], {}
    for variant in contract['variants']:
        group_rows = []
        diag = Counter()
        seed_differences = []
        for seed in contract['seeds']:
            prefix = f'{seed}_{variant}'
            stored = read(HERE / 'evidence' / f'{prefix}.json')
            assert stored['parameter_hash_before'] == stored['parameter_hash_after'] == contract['parameter_hash']
            episode_index, memory_count, rows = 0, 0, []
            current = None
            with gzip.open(HERE / 'evidence' / f'{prefix}.jsonl.gz', 'rt', encoding='utf-8') as stream:
                for line in stream:
                    row = json.loads(line)
                    kind = row['kind']
                    counts[kind] += 1
                    if kind == 'start':
                        assert current is None
                        assert row['episode'] == contract['episodes'][episode_index]
                        assert row['seed'] == seed and row['variant'] == variant
                        assert row['parameter_hash'] == contract['parameter_hash']
                        assert row['memory_count'] == memory_count
                        current = dict(episode=row['episode'], facts=[], pickups=[0], buffs=0,
                                       pending=deque(), memory_before=memory_count,
                                       no_movement=0, exploration=0, writes=0)
                        continue
                    assert current is not None and row['episode'] == current['episode']
                    t = len(current['facts'])
                    if kind == 'step':
                        assert row['t'] == t + 1 and row['memory_count'] == memory_count
                        assert row['chosen_action'] in row['legal']
                        assert len(row['scores']) == len(row['legal']) == len(row['candidates'])
                        chosen = row['legal'].index(row['chosen_action'])
                        if not row['explore']:
                            assert row['scores'][chosen] == max(row['scores'])
                        assert row['fact']['steps'] == 1
                        if t:
                            assert not current['facts'][-1]['captured'] and not current['facts'][-1]['completed']
                        current['facts'].append(row['fact'])
                        current['pickups'].append(current['pickups'][-1] + row['fact']['pickup'])
                        current['buffs'] += row['fact']['buff_pickup']
                        current['pending'].append(t + 1)
                        current['no_movement'] += row['no_movement']
                        current['exploration'] += row['explore']
                        diag['actions'] += 1
                        diag['chosen_support_sum'] += sum(row['support']) / 3
                        diag['chosen_support_below_half'] += int(sum(row['support']) / 3 < .5)
                        diag['no_movement_actions'] += row['no_movement']
                        diag['blink_actions'] += int(row['chosen_action'] >= 8)
                        diag['exploration_actions'] += row['explore']
                        continue
                    if kind == 'feedback':
                        assert row['at_step'] == t
                        start = current['pending'].popleft()
                        assert row['source_step'] == start
                        terminal = current['facts'][-1]['captured'] or current['facts'][-1]['completed']
                        duration = t - start + 1
                        assert duration == contract['fact_horizon'] or (terminal and duration < contract['fact_horizon'])
                        expected = [duration / contract['fact_horizon'],
                                    (current['pickups'][-1] - current['pickups'][start - 1]) / 10.,
                                    float(current['facts'][-1]['captured'])]
                        assert row['facts'] == expected
                        assert row['written'] == (variant == 'frozen_memory')
                        memory_count += int(row['written'])
                        current['writes'] += int(row['written'])
                        diag['factual_windows'] += 1
                        diag['windows_available_only_at_terminal'] += int(terminal)
                        diag['short_terminal_windows'] += int(duration < contract['fact_horizon'])
                        continue
                    assert kind == 'episode'
                    assert not current['pending']
                    final = current['facts'][-1]
                    assert final['captured'] or final['completed']
                    assert row['steps'] == t and row['treasures'] == current['pickups'][-1]
                    assert row['buffs'] == current['buffs']
                    assert row['score'] == 1.5 * t + 100 * current['pickups'][-1]
                    assert row['captured'] == final['captured'] and row['completed'] == final['completed']
                    assert row['memory_before'] == current['memory_before']
                    assert row['memory_after'] == memory_count
                    assert row['memory_writes'] == current['writes']
                    assert row['no_movement_actions'] == current['no_movement']
                    assert row['exploration_actions'] == current['exploration']
                    assert row['parameter_hash_after'] == contract['parameter_hash']
                    row.pop('kind')
                    assert row == stored['rows'][episode_index]
                    rows.append(row)
                    episode_index += 1
                    current = None
            assert current is None and episode_index == 512
            assert mean(rows, 'score') == stored['summary']['mean_score']
            assert mean(rows[:128], 'score') == stored['first128']['mean_score']
            assert mean(rows[-128:], 'score') == stored['last128']['mean_score']
            group_rows.extend(rows)
        summaries[variant] = dict(episodes=len(group_rows), mean_score=mean(group_rows, 'score'),
                                 mean_steps=mean(group_rows, 'steps'), mean_treasures=mean(group_rows, 'treasures'),
                                 captured=sum(r['captured'] for r in group_rows),
                                 completed=sum(r['completed'] for r in group_rows))
        assert summaries[variant] == result['summaries'][variant]
        diag['mean_chosen_support'] = diag['chosen_support_sum'] / diag['actions']
        diag['prior_dominated_fraction'] = diag['chosen_support_below_half'] / diag['actions']
        diag['no_movement_fraction'] = diag['no_movement_actions'] / diag['actions']
        diag['terminal_feedback_fraction'] = diag['windows_available_only_at_terminal'] / diag['factual_windows']
        diagnostics[variant] = dict(diag)
        all_rows.extend(group_rows)
    assert counts['episode'] == result['episodes'] == 4096
    assert counts['step'] == counts['feedback'] == result['environment_steps']
    assert sum(row['memory_writes'] for row in all_rows) == result['memory_writes']
    per_seed = []
    for seed in contract['seeds']:
        means = {v: mean([r for r in all_rows if r['seed'] == seed and r['variant'] == v], 'score')
                 for v in contract['variants']}
        per_seed.append(dict(seed=seed, **means, difference=means['frozen_memory'] - means['frozen_no_memory']))
    windows = {}
    for label, start, end in [('first128', 0, 128), ('last128', 384, 512)]:
        ids = set(contract['episodes'][start:end])
        windows[label] = {v: mean([r for r in all_rows if r['variant'] == v and r['episode'] in ids], 'score')
                          for v in contract['variants']}
    summary = dict(status='COMPLETE', stdlib_only=True, new_world_or_model_calls=0,
                   native_exit_code=native['exit_code'], raw_records=dict(counts),
                   all_input_pins_current_unchanged=len(claim['input_pins']),
                   parameter_hash=contract['parameter_hash'], all4096_episode_parameter_hashes_equal=True,
                   score_summaries=summaries, paired_seed_means=per_seed, windows=windows,
                   diagnostics=diagnostics, review_source_sha256=sha(Path(__file__)),
                   finished_utc=dt.datetime.now(dt.timezone.utc).isoformat())
    with (HERE / 'evidence/stored_review.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(summary, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
