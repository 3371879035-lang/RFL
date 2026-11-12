"""Summarize already closed raw captures, without running an agent or world."""
import ast
import datetime
import gzip
import hashlib
import json
from pathlib import Path
import struct
import time
import numpy as np

HERE = Path(__file__).resolve().parent
ORIGINAL = HERE.parent/'spatial_feedback_v179'


def profile(raw):
    ready = raw['cooldown_before'] == 0
    flash = raw['action'] >= 8
    duo = raw['mode'] == 1
    return dict(steps=len(raw), flash_steps=int(flash.sum()), flash_available_steps=int(ready.sum()),
        unmoved_steps=int(np.all(raw['hero'] == raw['before_hero'], axis=1).sum()),
        duo_steps=int(duo.sum()), duo_after_spawn_steps=int((duo & (raw['step'] >= 97)).sum()),
        duo_speedup_steps=int((duo & (raw['step'] >= 161)).sum()),
        action_counts=np.bincount(raw['action'], minlength=16).tolist())


def main():
    started = time.perf_counter()
    tree = ast.parse((ORIGINAL/'experiment.py').read_text(encoding='utf-8'))
    definition = next(n.value.args[0] for n in tree.body if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == 'DTYPE' for t in n.targets))
    dtype = np.dtype(ast.literal_eval(definition))
    contract = json.loads((HERE/'trajectory_contract.json').read_text(encoding='utf-8'))
    rows = []
    for pin in contract['sources']:
        path = Path(pin['path'])
        assert hashlib.sha256(path.read_bytes()).hexdigest() == pin['sha256']
        with gzip.open(path, 'rb') as f:
            n, = struct.unpack('<I', f.read(4))
            header = json.loads(f.read(n))
            payload = f.read()
        raw = np.frombuffer(payload, dtype)
        q_only = header['schema'] == 'V09_Q_ONLY_FROZEN_DIAGNOSTIC_V180'
        row = dict(seed=header['seed'], arm=header['source_arm'] if q_only else header['arm'],
                   readout='own_Q_only' if q_only else 'full', raw_records=len(raw))
        selected = raw if q_only else raw[(raw['kind'] == 1) & (raw['checkpoint'] == 262144) & (raw['episode'] < 128)]
        row['matched_final128'] = profile(selected)
        if not q_only:
            training = raw[raw['kind'] == 0]
            row['all_training'] = profile(training)
            row['training_stages'] = {str(s):profile(training[training['stage'] == s]) for s in range(3)}
            assert len(training) == 262144
        rows.append(row)
    groups = []
    for readout, arms in [('full', ['RL-RP', 'F0', 'F-RP', 'F-R']), ('own_Q_only', ['F-RP', 'F-R'])]:
        for arm in arms:
            selected = [r for r in rows if r['readout'] == readout and r['arm'] == arm]
            assert len(selected) == 12
            group = dict(arm=arm, readout=readout, trained_models=12)
            for scope in ['matched_final128'] + (['all_training'] if readout == 'full' else []):
                totals = {key:sum(r[scope][key] for r in selected) for key in selected[0][scope] if key != 'action_counts'}
                totals.update(flash_fraction=totals['flash_steps']/totals['steps'],
                    flash_use_when_available=totals['flash_steps']/totals['flash_available_steps'],
                    unmoved_fraction=totals['unmoved_steps']/totals['steps'],
                    late_duo_fraction_of_duo_steps=totals['duo_speedup_steps']/totals['duo_steps'])
                group[scope] = totals
            groups.append(group)
    assert time.perf_counter()-started <= 180
    result = dict(status='COMPLETE_STORED_TRAJECTORY_PROFILE', utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        wall_seconds=time.perf_counter()-started, cases=rows, groups=groups,
        new_training_steps=0, new_environment_steps=0,
        limit='Exposure imbalance is observed; its independent causal contribution is not established.')
    with (HERE/'trajectory_result.json').open('x',encoding='utf-8') as f:
        json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False)
    print(json.dumps({'status':result['status'],'wall_seconds':result['wall_seconds'],'groups':groups}))


if __name__ == '__main__':
    main()
