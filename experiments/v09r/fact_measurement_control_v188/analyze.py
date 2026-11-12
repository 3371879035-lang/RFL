"""Closed-data comparison of direct future factual control, with preserved earlier controls."""
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


def curve_auc(row):
    values=row['curves']['full']
    assert len(values)==4
    return sum((b['checkpoint']-a['checkpoint'])*(a['score']+b['score'])/2 for a,b in zip(values,values[1:]))/131072


def main():
    native=json.loads((HERE/'evidence_pilot/exit.json').read_text(encoding='utf-8'))
    review=json.loads((HERE/'evidence_pilot/stored_review_result.json').read_text(encoding='utf-8'))
    assert native['exit_code']==review['exit_code']==0
    rows=[];fresh=[]
    for seed in SEEDS:
        for label,root,arms in [('V183',OLD,['RL-RP','F0']),('V187',HERE.parent/'grounded_feedback_readout_v187',['F-RP','F-R']),('V188',HERE,['F0'])]:
            for arm in arms:
                row,receipt=load_case(root,seed,arm,'fact' if arm=='F0' else 'old')
                row['dataset']=label;row['common_step_trapezoid_mean_score']=curve_auc(row)
                rows.append(row)
                if label=='V188':fresh.append(receipt)
    lookup={(r['dataset'],r['seed'],r['arm']):r for r in rows}
    cells=[]
    for label,arms in [('V183',['RL-RP','F0']),('V187',['F-RP','F-R']),('V188',['F0'])]:
        for arm in arms:
            rs=[lookup[label,seed,arm] for seed in SEEDS]
            cells.append(dict(dataset=label,arm=arm,score=describe([r['cells']['full']['score'] for r in rs]),
                survival=describe([r['cells']['full']['survival'] for r in rs]),treasures=describe([r['cells']['full']['treasures'] for r in rs]),
                curve_scores=[mean(r['curves']['full'][j]['score'] for r in rs) for j in range(4)],
                common_step_trapezoid_mean_score=describe([r['common_step_trapezoid_mean_score'] for r in rs]),
                full256=describe([r['full256']['score'] for r in rs]),
                splits={key:describe([r['cells']['full']['splits'][key] for r in rs]) for key in rs[0]['cells']['full']['splits']}))
    old=[lookup['V183',seed,'F0'] for seed in SEEDS];new=[lookup['V188',seed,'F0'] for seed in SEEDS]
    contrasts=dict(final128_new_minus_old=describe([b['cells']['full']['score']-a['cells']['full']['score'] for a,b in zip(old,new)]),
        AUC_new_minus_old=describe([b['common_step_trapezoid_mean_score']-a['common_step_trapezoid_mean_score'] for a,b in zip(old,new)]),
        checkpoint_new_minus_old=[describe([b['curves']['full'][j]['score']-a['curves']['full'][j]['score'] for a,b in zip(old,new)]) for j in range(4)],
        late_training={label:{k:mean(r['train_windows']['last32768steps'][k] for r in rs) for k in ['mean_length_of_episodes_ending_in_window','immobile_fraction','pickups_per1000steps','at_or_beyond_step64_fraction']} for label,rs in [('old',old),('new',new)]})
    actual=dict(training_steps=sum(r['training_steps'] for r in fresh),evaluation_episodes=sum(b['episodes'] for r in fresh for b in r['evaluations']),
        evaluation_steps=sum(b['steps'] for r in fresh for b in r['evaluations']),all_environment_steps=sum(r['record_count'] for r in fresh),
        completed_training_episodes=sum(r['completed_training_episodes'] for r in fresh),source_instances=sum(r['source_instances'] for r in fresh),
        optimizer_steps=sum(r['counters']['fact_updates'] for r in fresh),measurement_update_markers=sum(r['counters']['measurement_updates'] for r in fresh),
        Q_updates=sum(r['counters']['Q_updates'] for r in fresh),reward_packets=sum(r['counters']['reward_packets'] for r in fresh),
        factual_labels=sum(r['future_labels']['records'] for r in fresh),measurement_eval_rows=sum(r['measurement_evaluation']['records'] for r in fresh),
        parameters_each=[r['parameters'] for r in fresh],added_parameters_each=26520,wall_seconds=native['wall_seconds'],synthetic_preflight_optimizer_steps=2)
    assert actual['training_steps']==524288 and actual['evaluation_episodes']==2560 and actual['all_environment_steps']<=1179648
    assert actual['optimizer_steps']==actual['measurement_update_markers']==4036 and actual['Q_updates']==actual['reward_packets']==0
    result=dict(status='COMPLETE_FINITE_F0_MEASUREMENT_CONTROL_NOT_FULL_V09',native_exit=0,stored_review_exit=0,
        matched128_cells=cells,paired_F0_contrasts=contrasts,actual=actual,per_case=rows,
        measurement_calibration_on_own_chosen_paths=[dict(seed=c['seed'],curves=c['calibration_on_own_paths']) for c in review['cases']],
        limits=['4known paired development seeds, not fresh confirmation.',
                'Other3arms and oldF0 are reused closed controls, not newly trained.',
                'Composite method repair changes predictor/loss routing/horizon/readout; not individual contribution identification.',
                'No external scalarreward/Q/TD does not mean no goals or numeric prediction loss.',
                '64step planning objective is finite horizon, not all possible delayed task consequences.',
                'On-policy observed targets are not oracle counterfactuals; chosen-path calibration can change with policy.',
                'Mean trapezoid score is a four-checkpoint proxy, not densely observed time-to-threshold or wall-clock superiority.',
                'Added measurement parameters/compute are disclosed; no equal-compute or general-taste claim.'])
    out=HERE/'analysis';out.mkdir(exist_ok=False)
    with (out/'result.json').open('x',encoding='utf-8',newline='\n') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    lines=['# V188：纯反馈直接未来事实控制实测','','全部主比较使用4个训练种子、相同末点j0..127场景；旧三组与旧F0只读复用。','',
        '|版本|组|得分|存活步数|宝箱|共同步数曲线平均分（梯形）|','|---|---|---:|---:|---:|---:|']
    for c in cells:lines.append(f"|{c['dataset']}|{c['arm']}|{c['score']['mean']:.6f}|{c['survival']['mean']:.6f}|{c['treasures']['mean']:.6f}|{c['common_step_trapezoid_mean_score']['mean']:.6f}|")
    lines+=['','## 新旧纯反馈曲线','','|训练步|旧F0|新F0|新−旧（各seed）|','|---|---:|---:|---|']
    for j,cp in enumerate(CHECKPOINTS):
        lines.append(f"|{cp}|{mean(r['curves']['full'][j]['score'] for r in old):.6f}|{mean(r['curves']['full'][j]['score'] for r in new):.6f}|{contrasts['checkpoint_new_minus_old'][j]['per_seed']}|")
    lines+=['','## 实际新增工作','','```json',json.dumps(actual,ensure_ascii=False,indent=2),'```','',
        '目标只是行动阶段的公开偏好，事实损失没有接奖励/Q/TD。未来标签全由真实已经观察的窗口/终止尾部构造；未完成尾部不补答案。',
        '接受所有正/零/负结果，不据此临时加seed或追收益调权。整个V0.9未宣称完成。']
    with (out/'result.md').open('x',encoding='utf-8',newline='\n') as f:f.write('\n'.join(lines)+'\n')
    print(json.dumps(dict(status=result['status'],cells=cells,contrasts=contrasts,actual=actual),ensure_ascii=False),flush=True)

if __name__=='__main__':main()
