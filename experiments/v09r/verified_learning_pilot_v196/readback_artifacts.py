"""Read genuine saved tensors only; never call a policy, optimizer or world step."""
import datetime
import gc
import gzip
import hashlib
import json
import traceback
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))


def load(p):
    with gzip.open(p, 'rb') as f:
        return torch.load(f, map_location='cpu', weights_only=False)


def network_hash(state):
    h = hashlib.sha256()
    for p in state.values():
        h.update(p.detach().numpy().tobytes())
    return h.hexdigest()


def replay_hash(r):
    h = hashlib.sha256()
    for k, v in sorted(vars(r).items()):
        h.update(k.encode())
        if isinstance(v, np.ndarray):
            h.update(str((v.dtype.str, v.shape)).encode())
            h.update(v.tobytes())
        else:
            h.update(repr(v).encode())
    return h.hexdigest()


def main():
    claim = HERE/'analysis/readback_claim.json'
    with claim.open('x', encoding='utf-8') as f:
        json.dump(dict(started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                       source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                       scope='Deserialize saved arrays; zero environment/optimizer/policy calls'), f)
    try:
        jobs = read(HERE/'evidence/summary.json')['results']
        reviewed = []
        for job in sorted(jobs, key=lambda j: (j['seed'], j['arm'])):
            d = HERE/'evidence'/f"seed{job['seed']}"/job['arm']
            old = load(ROOT/job['source']['path'])
            source_hash = network_hash(old['agent'].net.state_dict())
            old_replay = replay_hash(old['agent'].replay)
            assert source_hash == job['source_parameter_hash']
            del old
            for cycle, row in enumerate(job['cycles']):
                obj = load(d/f'checkpoint_cycle{cycle}.pt.gz')
                a = obj['agent']
                assert a.seed == job['seed'] and a.arm == job['arm']
                assert a.q_enabled == (a.arm != 'F0') and a.factual == (a.arm != 'RL-RP')
                assert (a.net.q is None) == (a.arm == 'F0')
                assert (a.net.heads is None) == (a.arm == 'RL-RP')
                assert network_hash(a.net.state_dict()) == row['deployed_report']['parameter_hash']
                assert a._v196_extra is None and a._sleep_teacher is None
                assert replay_hash(a.replay) == old_replay
                assert len(obj['history']) == cycle+1
                for i in range(cycle+1):
                    cr = job['cycles'][i]
                    assert obj['history'][i]['parent_hash'] == cr['parent_hash']
                    for name, child in cr['teachers'].items():
                        assert network_hash(obj['networks'][f'cycle{i}_{name}']) == child['fit']['child_hash']
                    if cr['sleep'] is not None:
                        assert network_hash(obj['networks'][f'cycle{i}_student']) == cr['sleep']['child_hash']
                del a, obj
            with gzip.open(d/'raw.jsonl.gz', 'rt', encoding='utf-8') as f:
                raw = {r['id']: r for r in map(json.loads, f)}
            data = load(d/'data.pt.gz')
            sources = {t['episode']: t for t in data if t['kind'] == 'source'}
            actual_ids = []
            frame_count = reused = 0
            for tr in data:
                rs, prefix = tr['records'], tr['begin_t']
                assert len(rs) == tr['steps'] and rs[-1]['done']
                assert not any(r['done'] for r in rs[:-1])
                assert tr['new_ids'] == [r['uid'] for r in rs[prefix:]]
                assert tr['prefix_reused_ids'] == [r['uid'] for r in rs[:prefix]]
                if tr['kind'] == 'trial':
                    assert tr['prefix_reused_ids'] == [r['uid'] for r in sources[tr['episode']]['records'][:prefix]]
                else:
                    assert prefix == 0
                actual_ids.extend(tr['new_ids'])
                reused += prefix
                for i, r in enumerate(rs):
                    x = raw[r['uid']]
                    assert r['action'] == x['action'] and r['reward'] == x['reward']
                    assert r['pickup'] == x['pickup'] and r['captured'] == x['captured']
                    assert r['done'] == (x['captured'] or x['completed'])
                    assert r['image'].shape == r['next_image'].shape == (5, 21, 21)
                    assert r['scalar'].shape == r['next_scalar'].shape == (184,)
                    assert r['legal'].shape == r['next_legal'].shape == (16,)
                    assert r['legal'][r['action']]
                    if i+1 < len(rs):
                        assert np.array_equal(r['next_image'], rs[i+1]['image'])
                        assert np.array_equal(r['next_scalar'], rs[i+1]['scalar'])
                    if i >= prefix:
                        assert x['kind'] == tr['kind'] and x['episode'] == tr['episode']
                    if tr['kind'] == 'student_wake':
                        assert r['teacher_scores'].shape == (16,)
                        assert np.isfinite(r['teacher_scores']).all()
                    else:
                        assert r['teacher_scores'] is None
                    frame_count += 1
                assert tr['score'] == 1.5*len(rs)+100*sum(r['pickup'] for r in rs)
            assert len(actual_ids) == len(set(actual_ids))
            assert set(actual_ids) == {uid for uid, r in raw.items() if r['kind'] in ('source', 'trial', 'student_wake')}
            reviewed.append(dict(seed=job['seed'], arm=job['arm'], checkpoints=2,
                                 original_replay_preserved=True, replay_sha256=old_replay,
                                 actual_new_data_steps=len(actual_ids), stored_frames=frame_count,
                                 reused_prefix_frames=reused, complete_training_traces=len(data)))
            del data, raw, sources
            gc.collect()
        result = dict(status='PASS_SAVED_TENSOR_READBACK', jobs=reviewed, checkpoints=32,
                      real_new_data_steps=sum(r['actual_new_data_steps'] for r in reviewed),
                      reused_prefix_frames=sum(r['reused_prefix_frames'] for r in reviewed),
                      environment_calls=0, policy_calls=0, optimizer_calls=0)
    except BaseException:
        result = dict(status='ERROR_READBACK', error=traceback.format_exc())
    with (HERE/'analysis/readback_result.json').open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'jobs'}))
    return 0 if result['status'] == 'PASS_SAVED_TENSOR_READBACK' else 1


if __name__ == '__main__':
    raise SystemExit(main())
