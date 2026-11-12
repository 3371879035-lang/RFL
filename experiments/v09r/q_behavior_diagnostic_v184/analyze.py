"""One closed-data comparison of training controller and frozen action readout."""
import gzip
import json
from pathlib import Path
import statistics
import struct
import numpy as np

HERE = Path(__file__).resolve().parent
OLD = HERE.parent/'spatial_feedback_v183'
SEEDS = [93001, 93002, 93003, 93004]
ARMS = ['RL-RP', 'F0', 'F-RP', 'F-R']
HYBRIDS = ['F-RP', 'F-R']
CHECKPOINTS = [0, 16384, 65536, 131072]


def mean(values):
    return float(statistics.mean(values))


def describe(values):
    return dict(mean=mean(values), minimum=float(min(values)), maximum=float(max(values)),
                positive_seeds=sum(v > 0 for v in values), per_seed=list(values))


def load_case(root, seed, arm, controller):
    directory = root/'evidence_pilot'/f'seed{seed}'/arm
    result = json.loads((directory/'result.json').read_text(encoding='utf-8'))
    assert result['status'] == 'COMPLETE' and result['training_steps'] == 131072
    with gzip.open(directory/'episodes.jsonl.gz', 'rt', encoding='utf-8') as f:
        episodes = [json.loads(line) for line in f]
    with gzip.open(directory/'steps.bin.gz', 'rb') as f:
        size, = struct.unpack('<I', f.read(4))
        header = json.loads(f.read(size))
        dtype = np.dtype([(x[0], x[1], tuple(x[2])) if len(x) == 3 else tuple(x) for x in header['dtype']])
        raw = np.frombuffer(f.read(), dtype)
    training = raw[raw['kind'] == 0]
    assert len(training) == 131072
    row = dict(seed=seed, arm=arm, training_controller=controller,
        initial_parameter_hash=result['initial_parameter_hash'], cells={}, curves={}, train_windows={})
    for readout, kind in [('full', 'evaluation'), ('Q', 'ablation')]:
        curve = []
        for cp in CHECKPOINTS:
            selected = [e for e in episodes if e['kind'] == kind and e['checkpoint'] == cp and e['episode'] < 128]
            if not selected:
                continue
            assert len(selected) == 128
            curve.append(dict(checkpoint=cp, score=mean(e['score'] for e in selected),
                              survival=mean(e['steps'] for e in selected), treasures=mean(e['treasures'] for e in selected)))
            if cp == 131072:
                splits = {}
                for heldout in [False, True]:
                    for mode in [0, 1]:
                        xs = [e for e in selected if e['heldout'] == heldout and e['mode'] == mode]
                        assert len(xs) == 32
                        splits[('heldout' if heldout else 'seen')+('_duo' if mode else '_solo')] = mean(e['score'] for e in xs)
                row['cells'][readout] = dict(curve[-1], episodes=128, splits=splits)
        row['curves'][readout] = curve
    full256 = [e for e in episodes if e['kind'] == 'evaluation' and e['checkpoint'] == 131072]
    assert len(full256) == 256
    row['full256'] = dict(score=mean(e['score'] for e in full256), survival=mean(e['steps'] for e in full256),
                         treasures=mean(e['treasures'] for e in full256))
    for name, train, lower in [('all', training, 0), ('last32768steps', training[-32768:], 98304)]:
        ended = [e for e in episodes if e['kind'] == 'training' and e['global_step'] > lower]
        row['train_windows'][name] = dict(real_steps=len(train), complete_episodes=len(ended),
            mean_length_of_episodes_ending_in_window=mean(e['steps'] for e in ended),
            immobile_fraction=float(np.mean(np.all(train['hero'] == train['before_hero'], axis=1))),
            at_or_beyond_step32_fraction=float(np.mean(train['step'] >= 32)),
            at_or_beyond_step64_fraction=float(np.mean(train['step'] >= 64)),
            pickups_per1000steps=float(train['pickup'].sum()/len(train)*1000),
            captures_per1000steps=float(train['captured'].sum()/len(train)*1000),
            visited_hero_cells=int(len(np.unique(train['hero'], axis=0))))
        if controller == 'Q':
            greedy = train['explore'] == 0
            row['train_windows'][name]['Q_full_disagreement_fraction'] = float(np.mean(train['q_action'] != train['full_action']))
            row['train_windows'][name]['greedy_planner_override_fraction'] = float(np.mean(train['q_action'][greedy] != train['full_action'][greedy]))
    row['learning_counts'] = {k: result['counters'][k] for k in ['Q_updates', 'fact_updates', 'retrieval', 'retrieved_records', 'model_edges']}
    fullbank = next(b for b in result['evaluations'] if b['checkpoint'] == 131072 and b['ablation'] is None)
    audit = fullbank['prediction_audit']
    n = audit['successors']
    row['prediction_on_full_policy_paths'] = dict(positions=n,
        model_MSE=audit['model_mse_sum']/n if n else None,
        identity_MSE=audit['identity_mse_sum']/n if n else None,
        own_Q_successor_MAE=audit['successor_Q_MAE_sum']/n if n and arm != 'F0' else None)
    return row, result


def main():
    native = json.loads((HERE/'evidence_pilot/exit.json').read_text(encoding='utf-8'))
    review = json.loads((HERE/'evidence_pilot/stored_review_result.json').read_text(encoding='utf-8'))
    assert native['exit_code'] == review['exit_code'] == 0
    rows, new_native = [], []
    for seed in SEEDS:
        for arm in ARMS:
            row, _ = load_case(OLD, seed, arm, 'old')
            rows.append(row)
        for arm in HYBRIDS:
            row, receipt = load_case(HERE, seed, arm, 'Q')
            rows.append(row)
            new_native.append(receipt)
    lookup = {(r['seed'], r['arm'], r['training_controller']): r for r in rows}
    for seed in SEEDS:
        for arm in HYBRIDS:
            assert lookup[seed, arm, 'old']['initial_parameter_hash'] == lookup[seed, arm, 'Q']['initial_parameter_hash']
            assert lookup[seed, arm, 'old']['curves']['full'][0] == lookup[seed, arm, 'Q']['curves']['full'][0]
    tables = []
    for controller, arms in [('old', ARMS), ('Q', HYBRIDS)]:
        for arm in arms:
            selected = [lookup[seed, arm, controller] for seed in SEEDS]
            for readout in ['full', 'Q']:
                if readout not in selected[0]['cells']:
                    continue
                cell = dict(arm=arm, training_controller=controller, readout=readout, trained_seeds=4,
                    eval_episodes_each=128, score=describe([r['cells'][readout]['score'] for r in selected]),
                    survival=describe([r['cells'][readout]['survival'] for r in selected]),
                    treasures=describe([r['cells'][readout]['treasures'] for r in selected]),
                    splits={name: mean(r['cells'][readout]['splits'][name] for r in selected)
                            for name in selected[0]['cells'][readout]['splits']})
                if len(selected[0]['curves'][readout]) == 4:
                    cell['curve_scores'] = [mean(r['curves'][readout][j]['score'] for r in selected) for j in range(4)]
                    cell['normalized_AUC'] = mean(float(np.trapezoid([p['score']/1384 for p in r['curves'][readout]], CHECKPOINTS)/131072) for r in selected)
                tables.append(cell)
    effects = []
    for arm in HYBRIDS:
        old = [lookup[seed, arm, 'old'] for seed in SEEDS]
        new = [lookup[seed, arm, 'Q'] for seed in SEEDS]
        rl = [lookup[seed, 'RL-RP', 'old'] for seed in SEEDS]
        effect = dict(arm=arm,
            training_controller_effect_fixed_full=describe([b['cells']['full']['score']-a['cells']['full']['score'] for a, b in zip(old, new)]),
            training_controller_effect_fixed_Q=describe([b['cells']['Q']['score']-a['cells']['Q']['score'] for a, b in zip(old, new)]),
            new_full_minus_own_Q=describe([b['cells']['full']['score']-b['cells']['Q']['score'] for b in new]),
            new_own_Q_minus_pure_RL=describe([b['cells']['Q']['score']-a['cells']['full']['score'] for a, b in zip(rl, new)]),
            old_own_Q_minus_pure_RL=describe([b['cells']['Q']['score']-a['cells']['full']['score'] for a, b in zip(rl, old)]),
            late_training={controller: {key: mean(r['train_windows']['last32768steps'][key] for r in data)
                             for key in ['mean_length_of_episodes_ending_in_window', 'immobile_fraction', 'at_or_beyond_step64_fraction', 'pickups_per1000steps']}
                           for controller, data in [('old', old), ('Q', new)]})
        effects.append(effect)
    actual = dict(training_steps=sum(r['training_steps'] for r in new_native),
        evaluation_episodes=sum(b['episodes'] for r in new_native for b in r['evaluations']),
        evaluation_steps=sum(b['steps'] for r in new_native for b in r['evaluations']),
        all_environment_steps=sum(r['record_count'] for r in new_native),
        completed_training_episodes=sum(r['completed_training_episodes'] for r in new_native),
        source_instances=sum(r['source_instances'] for r in new_native),
        optimizer_steps=sum(r['counters']['Q_updates'] for r in new_native),
        factual_update_steps=sum(r['counters']['fact_updates'] for r in new_native),
        wall_seconds=native['wall_seconds'], old_native_or_checker_calls=0)
    assert actual['training_steps'] == 1048576 and actual['evaluation_episodes'] == 9216
    assert actual['all_environment_steps'] <= 3407872
    assert actual['optimizer_steps'] == actual['factual_update_steps'] == 8072
    report = dict(status='COMPLETE_SMALL_Q_BEHAVIOR_DIAGNOSTIC_NOT_FULL_V09', native_exit=0, stored_review_exit=0,
        inference_unit='Four paired trained seeds. 128 final evaluation scenes perseed/readout, not independent trainingN.',
        matched128_cells=tables, paired_effects=effects, per_case=rows, actual=actual,
        limits=['Old controls are read-only V183 same seeds, initialization and budget; not fresh randomized confirmation.',
                'Training-controller effect includes the changed encountered data/history/targets, not a mediation-isolated distribution effect.',
                'F-R vs pureRL also differs in punishment; F-RP is the closest reward-matched hybrid comparison.',
                'Auxiliary-gradient/representation interference is not identified solely by a remaining pureRL gap.',
                'F0 is unchanged; hybridQ intervention does not repair pure-feedback planning.',
                'Planner still computes during training; no claim of compute savings or final algorithm adoption.',
                'Factual and Q updates use one shared optimizer step, not two independent update costs.'])
    out = HERE/'analysis'
    out.mkdir(exist_ok=False)
    (out/'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    lines = ['# V184：训练行为控制器小规模定位', '',
        '8个新模型；旧四组结果只读复用。下表全部为相同末点j0..127场景，4个配对种子均值。', '',
        '|组|训练行为|冻结读出|分数|存活步数|宝箱|', '|---|---|---|---:|---:|---:|']
    for row in tables:
        controller = '旧原配置' if row['training_controller'] == 'old' else '新：自己的Q'
        lines.append(f"|{row['arm']}|{controller}|{row['readout']}|{row['score']['mean']:.3f}|{row['survival']['mean']:.3f}|{row['treasures']['mean']:.3f}|")
    lines += ['', '## 同seed配对分数差', '', '|组|改变训练行为：固定完整读出|改变训练行为：固定Q读出|新模型完整−Q|新模型Q−纯RL|', '|---|---:|---:|---:|---:|']
    for e in effects:
        keys = ['training_controller_effect_fixed_full', 'training_controller_effect_fixed_Q', 'new_full_minus_own_Q', 'new_own_Q_minus_pure_RL']
        lines.append('|'+e['arm']+'|'+'|'.join(f"{e[k]['mean']:+.3f}" for k in keys)+'|')
    lines += ['', '逐种子差值（93001、93002、93003、93004）：', '']
    for e in effects:
        for key in keys:
            lines.append(f"- {e['arm']} {key}: {e[key]['per_seed']}")
    lines += ['', '## 实际新增工作', '', '```json', json.dumps(actual, ensure_ascii=False, indent=2), '```', '',
        'Q训练更好若成立，支持训练控制器及其带来的经历变化有害；不把残余差距直接归因于梯度冲突。F0未变，不偷接Q。四种子是机制定位，不是总体确认；整个V0.9未完成。']
    (out/'result.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(json.dumps(dict(status=report['status'], actual=actual, cells=[{k:r[k] for k in ['arm','training_controller','readout','score']} for r in tables], effects=effects), ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
