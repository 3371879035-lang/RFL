"""Stored-byte review; deliberately imports none of the native experiment modules."""
import argparse
import concurrent.futures
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import struct
import time
import traceback
import numpy as np

ROOT = Path(__file__).resolve().parents[3]


def review_case(directory):
    result = json.loads((directory/'result.json').read_text(encoding='utf-8'))
    counts = Counter()
    tracks, deep_windows = {}, set()
    payload_hash = hashlib.sha256()
    with gzip.open(directory/'steps.bin.gz', 'rb') as f:
        size = struct.unpack('<I', f.read(4))[0]
        header = json.loads(f.read(size))
        dtype = np.dtype([(x[0], x[1], tuple(x[2])) if len(x) == 3 else tuple(x)
                          for x in header['dtype']])
        for pin in header['pins']:
            b = (ROOT/pin['path']).read_bytes()
            assert len(b) == pin['bytes'] and hashlib.sha256(b).hexdigest() == pin['sha256']
        while True:
            block = f.read(dtype.itemsize*4096)
            if not block:
                break
            assert len(block) % dtype.itemsize == 0
            payload_hash.update(block)
            data = np.frombuffer(block, dtype)
            assert np.all(data['action'] < 16)
            assert np.all((data['action'] < 8) | (data['cooldown_before'] == 0))
            assert np.isfinite(data['forecast']).all()
            assert np.all((data['step'] >= 1) & (data['step'] <= 256))
            assert np.all((data['captured'] == 0) | (data['completed'] == 0))
            for row in data:
                kind, ep, checkpoint = int(row['kind']), int(row['episode']), int(row['checkpoint'])
                key = (kind, 0 if kind == 0 else checkpoint, ep)
                if key not in tracks:
                    assert row['step'] == 1
                    tracks[key] = dict(step=0, hero=row['before_hero'].copy(),
                                       monsters=row['before_monsters'].copy(), pickups=0, terminal=False)
                state = tracks[key]
                assert not state['terminal']
                assert row['step'] == state['step']+1
                assert np.array_equal(row['before_hero'], state['hero'])
                assert np.array_equal(row['before_monsters'], state['monsters'])
                displacement = np.abs(row['hero'].astype(int)-row['before_hero'].astype(int))
                assert displacement.max() <= (10 if row['action'] >= 8 else 2 if row['buff_before'] else 1)
                if row['action'] < 8:
                    direction = [(1,0),(1,-1),(0,-1),(-1,-1),(-1,0),(-1,1),(0,1),(1,1)][int(row['action'])]
                    delta = row['hero'].astype(int)-row['before_hero'].astype(int)
                    assert all(d == 0 or d*direction[i] > 0 for i,d in enumerate(delta))
                existing = row['monsters'][:, 0] >= 0
                caught = bool(np.any(np.max(np.abs(row['monsters'][existing].astype(int)-row['hero']), axis=1) <= 1))
                assert caught == bool(row['captured'])
                assert bool(row['completed']) == (row['step'] == 256 and not caught)
                state['pickups'] += int(row['pickup'])
                assert state['pickups'] <= 10
                assert float(row['score']) == 1.5*int(row['step'])+100*state['pickups']
                if kind == 0:
                    counts['train'] += 1
                    override = header['stage_override']
                    expected_stage = override if override is not None else 0 if counts['train'] <= 16384 else 1 if counts['train'] <= 65536 else 2
                    assert int(row['stage']) == expected_stage
                    if header['arm'] == 'F0':
                        assert np.isnan(row['reward'])
                    else:
                        penalty = 1 if header['arm'] in ('RL-RP','F-RP') else 0
                        expected_reward = np.float32(.015+int(row['pickup'])-penalty*int(row['captured']))
                        assert row['reward'] == expected_reward
                else:
                    counts['eval'] += 1
                    assert row['explore'] == 0 and np.isnan(row['reward'])
                if header['arm'] == 'RL-RP':
                    assert row['depth'] == 0
                else:
                    assert row['depth'] in (1,4,8)
                if row['depth'] > 1:
                    window = (*key, (int(row['step'])-1)//8)
                    assert window not in deep_windows
                    deep_windows.add(window)
                state.update(step=int(row['step']), hero=row['hero'].copy(),
                             monsters=row['monsters'].copy(), terminal=bool(row['captured'] or row['completed']))
                counts['records'] += 1
                counts['capture_ends'] += int(row['captured'])
                counts['completed_ends'] += int(row['completed'])
    assert counts['records'] == result['record_count']
    assert counts['train'] == result['training_steps']
    assert payload_hash.hexdigest() == result['record_payload_sha256']
    assert result['counters']['head_evaluations'] == 3*result['counters']['model_edges']
    if result['arm'] == 'F0':
        assert result['counters']['Q_updates'] == result['counters']['reward_packets'] == 0
    if result['arm'] == 'RL-RP':
        assert result['counters']['fact_updates'] == result['counters']['model_edges'] == 0
    episode_rows = []
    with gzip.open(directory/'episodes.jsonl.gz', 'rt', encoding='utf-8') as f:
        for line in f:
            item = json.loads(line)
            assert item['score'] == 1.5*item['steps']+100*item['treasures']
            assert bool(item['completed']) == (item['steps'] == 256 and not item['captured'])
            episode_rows.append(item)
    train = [x for x in episode_rows if x['kind'] == 'training']
    assert len(train) == result['completed_training_episodes']
    for bank in result['evaluations']:
        items = [x for x in episode_rows if x['kind'] != 'training' and x['checkpoint'] == bank['checkpoint']
                 and x.get('ablation') == bank['ablation']]
        assert len(items) == bank['episodes']
        assert sum(x['steps'] for x in items) == bank['steps']
        assert np.mean([x['score'] for x in items]) == bank['mean_score']
        assert bank['counters']['Q_updates'] == bank['counters']['fact_updates'] == bank['counters']['reward_packets'] == 0
    return dict(seed=result['seed'], arm=result['arm'], native_status=result['status'],
                counts=dict(counts), episodes=len(episode_rows),
                payload_sha256=payload_hash.hexdigest(), all_eof_crc_and_record_invariants=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory')
    parser.add_argument('--workers',type=int,default=1)
    args = parser.parse_args()
    directory = Path(args.directory)
    start, error, cases = time.perf_counter(), None, []
    try:
        paths=[p.parent for p in sorted(directory.glob('seed*/*/result.json'))]
        assert 1 <= args.workers <= 12
        if args.workers == 1:
            cases=[review_case(path) for path in paths]
        else:
            with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
                cases=list(pool.map(review_case,paths))
        assert cases, 'No case result; not silently treated as a passing empty review'
    except BaseException:
        error = traceback.format_exc()
    output = dict(schema='V09_STORED_REVIEW_V179', exit_code=0 if error is None else 1,
                  wall_seconds=time.perf_counter()-start, error=error, cases=cases,
                  native_imports_or_calls=0, experimental_RNG_draws=0,
                  limit='Byte/record and accounting review, not full neural numerical replay, reconstructed runtime identity, independent expert, or scientific gate.')
    with (directory/'stored_review_result.json').open('x', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(json.dumps(dict(exit_code=output['exit_code'],cases=len(cases),
                         wall_seconds=output['wall_seconds'],error=error)), flush=True)
    return output['exit_code']


if __name__ == '__main__':
    raise SystemExit(main())
