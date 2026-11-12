"""Closed-data comparison of grounded residual readout, with preserved earlier controls."""
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
    rows, fresh = [], []
    for seed in SEEDS:
        for label, root, arms in [('V183', OLD, ARMS),
                ('V184', HERE.parent/'q_behavior_diagnostic_v184', HYBRIDS), ('V185', HERE.parent/'auxiliary_isolation_v185', HYBRIDS), ('V187', HERE, HYBRIDS)]:
            for arm in arms:
                row, receipt = load_case(root, seed, arm, 'old' if label == 'V183' else 'Q')
                row['dataset'] = label
                rows.append(row)
                if label == 'V187':
                    fresh.append(receipt)
    lookup = {(r['dataset'], r['seed'], r['arm']): r for r in rows}
    cells = []
    for label, arms in [('V183', ARMS), ('V184', HYBRIDS), ('V185', HYBRIDS), ('V187', HYBRIDS)]:
        for arm in arms:
            rs = [lookup[label, seed, arm] for seed in SEEDS]
            for readout in ['full', 'Q']:
                if readout not in rs[0]['cells']:
                    continue
                cell = dict(dataset=label, arm=arm, readout=readout, eval_scenes_each=128,
                    score=describe([r['cells'][readout]['score'] for r in rs]),
                    survival=describe([r['cells'][readout]['survival'] for r in rs]),
                    treasures=describe([r['cells'][readout]['treasures'] for r in rs]))
                if len(rs[0]['curves'][readout]) == 4:
                    cell['curve_scores'] = [mean(r['curves'][readout][j]['score'] for r in rs) for j in range(4)]
                cells.append(cell)
    effects = []
    for arm in HYBRIDS:
        old = [lookup['V185', seed, arm] for seed in SEEDS]
        new = [lookup['V187', seed, arm] for seed in SEEDS]
        rl = [lookup['V183', seed, 'RL-RP'] for seed in SEEDS]
        effect = dict(arm=arm,
            readout_revision_effect_fixed_Q=describe([b['cells']['Q']['score']-a['cells']['Q']['score'] for a,b in zip(old,new)]),
            readout_revision_effect_fixed_full=describe([b['cells']['full']['score']-a['cells']['full']['score'] for a,b in zip(old,new)]),
            grounded_full_minus_ownQ=describe([b['cells']['full']['score']-b['cells']['Q']['score'] for b in new]),
            protected_Q_minus_pureRL=describe([b['cells']['Q']['score']-a['cells']['full']['score'] for a,b in zip(rl,new)]),
            late_training={label: {k: mean(r['train_windows']['last32768steps'][k] for r in rs)
                for k in ['mean_length_of_episodes_ending_in_window','immobile_fraction','pickups_per1000steps','at_or_beyond_step64_fraction']}
                for label,rs in [('V185',old),('V187',new)]})
        effects.append(effect)
    actual = dict(training_steps=sum(r['training_steps'] for r in fresh),
        evaluation_episodes=sum(b['episodes'] for r in fresh for b in r['evaluations']),
        evaluation_steps=sum(b['steps'] for r in fresh for b in r['evaluations']),
        all_environment_steps=sum(r['record_count'] for r in fresh),
        completed_training_episodes=sum(r['completed_training_episodes'] for r in fresh),
        source_instances=sum(r['source_instances'] for r in fresh),
        optimizer_steps=sum(r['counters']['Q_updates'] for r in fresh),
        factual_updates=sum(r['counters']['fact_updates'] for r in fresh), wall_seconds=native['wall_seconds'])
    assert actual['training_steps'] == 1048576 and actual['evaluation_episodes'] == 9216
    assert actual['all_environment_steps'] <= 3407872 and actual['optimizer_steps'] == actual['factual_updates'] == 8072
    exact = [{k: c[k] for k in ['seed','arm','factual_heads_parameter_content_changed',
        'final_core_bitwise_matches_pureRL','full_training_physical_rows_match_pureRL',
        'final_core_matches_V185','full_training_physical_rows_match_V185']} for c in review['cases']]
    result = dict(status='COMPLETE_GROUNDED_RESIDUAL_PILOT_NOT_FULL_V09', native_exit=0, stored_review_exit=0,
        matched128_cells=cells, paired_effects=effects, core_and_trajectory_comparison=exact,
        per_case=rows, actual=actual,
        limits=['Known four paired seeds; previous controls reused without re-execution.',
                'A reward-using local residual critic, not a purefeedback repair or a proof of independent attribution benefit.',
                'Restoring pureRL does not establish useful feedback action improvement.',
                'F0 not modified or rerun; no Q or reward introduced into F0.',
                'F-R vs RL-RP also changes punishment; within-arm V185/V187 comparison holds punishment fixed.',
                'One declaredreadoutcandidate; training behavior remainsQ, so no closed-loopfeedbacktrainingclaim.'])
    out = HERE/'analysis'
    out.mkdir(exist_ok=False)
    with (out/'result.json').open('x',encoding='utf-8',newline='\n') as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
    lines = ['# V187：真实转移残差反馈实测', '', '4个配对训练种子，全部表格使用同末点j0..127场景。', '',
        '|版本|组|冻结读出|平均分|存活步数|宝箱|', '|---|---|---|---:|---:|---:|']
    for c in cells:
        lines.append(f"|{c['dataset']}|{c['arm']}|{c['readout']}|{c['score']['mean']:.3f}|{c['survival']['mean']:.3f}|{c['treasures']['mean']:.3f}|")
    lines += ['', '## 固定读出的配对差', '', '|组|读出修订后−前，Q读出|读出修订后−前，完整读出|新反馈−Q|保留Q−纯RL|', '|---|---:|---:|---:|---:|']
    keys = ['readout_revision_effect_fixed_Q','readout_revision_effect_fixed_full','grounded_full_minus_ownQ','protected_Q_minus_pureRL']
    for e in effects:
        lines.append('|'+e['arm']+'|'+'|'.join(f"{e[k]['mean']:+.3f}" for k in keys)+'|')
    lines += ['', '逐seed差值：']
    for e in effects:
        for k in keys:
            lines.append(f"- {e['arm']} {k}: {e[k]['per_seed']}")
    lines += ['', '## 核心参数/完整训练轨迹与纯RL的精确比较', '', '```json', json.dumps(exact,ensure_ascii=False,indent=2),'```',
        '', '## 实际新增工作', '', '```json',json.dumps(actual,ensure_ascii=False,indent=2),'```', '',
        '恢复基线不是反馈增量。四种子固定候选，不按效果调参；训练Q控制不等于已证明反馈接管训练的效果。']
    with (out/'result.md').open('x',encoding='utf-8',newline='\n') as f:
        f.write('\n'.join(lines)+'\n')
    print(json.dumps(dict(status=result['status'],actual=actual,
        cells=[{k:c[k] for k in ['dataset','arm','readout','score']} for c in cells],
        effects=effects,exact=exact),ensure_ascii=False),flush=True)


if __name__ == '__main__':
    main()


