"""Summarize this fixed repair pilot once; four trained seeds are the inference unit."""
import gzip
import hashlib
import json
from pathlib import Path
import statistics
import numpy as np

HERE=Path(__file__).resolve().parent
ARMS=['RL-RP','F0','F-RP','F-R']
SEEDS=[93001,93002,93003,93004]
CHECKPOINTS=[0,16384,65536,131072]


def mean(xs):return float(statistics.mean(xs))


def describe(values):
    return dict(mean=mean(values),minimum=float(min(values)),maximum=float(max(values)),per_seed=values)


def main():
    d=HERE/'evidence_pilot'
    native=json.loads((d/'exit.json').read_text(encoding='utf-8'))
    review=json.loads((d/'stored_review_result.json').read_text(encoding='utf-8'))
    assert native['exit_code']==review['exit_code']==0
    per_case=[];all_results=[]
    for seed in SEEDS:
        for arm in ARMS:
            path=d/f'seed{seed}'/arm
            r=json.loads((path/'result.json').read_text(encoding='utf-8'));all_results.append(r)
            with gzip.open(path/'episodes.jsonl.gz','rt',encoding='utf-8') as f:
                episodes=[json.loads(line) for line in f]
            main_rows=[e for e in episodes if e['kind']=='evaluation']
            curves=[]
            for cp in CHECKPOINTS:
                es=[e for e in main_rows if e['checkpoint']==cp]
                assert len(es)==(256 if cp==131072 else 128)
                seen_duo=[e for e in es if not e['heldout'] and e['mode']==1]
                curves.append(dict(checkpoint=cp,mixed_score=mean(e['score'] for e in es),
                    seen_duo_score=mean(e['score'] for e in seen_duo)))
            final=[e for e in main_rows if e['checkpoint']==131072]
            bank=next(b for b in r['evaluations'] if b['checkpoint']==131072 and b['ablation'] is None)
            audit=bank['prediction_audit'];n=audit['successors']
            row=dict(seed=seed,arm=arm,final_score=mean(e['score'] for e in final),
                final_survival=mean(e['steps'] for e in final),final_treasures=mean(e['treasures'] for e in final),
                capture_rate=mean(int(e['captured']) for e in final),curves=curves,
                mixed_AUC=float(np.trapezoid([v['mixed_score']/1384 for v in curves],CHECKPOINTS)/131072),
                seen_duo_AUC=float(np.trapezoid([v['seen_duo_score']/1384 for v in curves],CHECKPOINTS)/131072),
                early_mixed_AUC=float(np.trapezoid([v['mixed_score']/1384 for v in curves[:3]],CHECKPOINTS[:3])/65536),
                prediction_model_MSE=audit['model_mse_sum']/n if n else None,
                prediction_identity_MSE=audit['identity_mse_sum']/n if n else None,
                own_Q_successor_MAE=audit['successor_Q_MAE_sum']/n if n and arm!='F0' else None,
                prediction_positions=n,split={})
            for heldout in [False,True]:
                for mode in [0,1]:
                    es=[e for e in final if e['heldout']==heldout and e['mode']==mode];assert len(es)==64
                    row['split'][('heldout' if heldout else 'seen')+('_duo' if mode else '_solo')]=dict(score=mean(e['score'] for e in es),survival=mean(e['steps'] for e in es))
            if arm!='RL-RP':
                denominator=r['counters']['bootstrap_positions']
                row['bootstrap_inclusion']=[r['counters'][f'bootstrap_selected_{j}']/denominator for j in range(3)]
            if arm in ['F-RP','F-R']:
                q=[e for e in episodes if e.get('ablation')=='Q_only'];assert len(q)==128
                matched=[e for e in final if e['episode']<128]
                row['frozen_Q_only']=dict(episodes=128,full_score=mean(e['score'] for e in matched),
                    Q_only_score=mean(e['score'] for e in q),Q_only_survival=mean(e['steps'] for e in q),
                    full_minus_Q=mean(e['score'] for e in matched)-mean(e['score'] for e in q))
            per_case.append(row)
    summaries=[]
    for arm in ARMS:
        rows=[r for r in per_case if r['arm']==arm]
        s=dict(arm=arm,trained_models=4,final_episodes_each=256)
        for key in ['final_score','final_survival','final_treasures','capture_rate','mixed_AUC','seen_duo_AUC','early_mixed_AUC']:
            s[key]=describe([r[key] for r in rows])
        s['curves']=[dict(checkpoint=cp,mixed_score=mean(r['curves'][j]['mixed_score'] for r in rows),seen_duo_score=mean(r['curves'][j]['seen_duo_score'] for r in rows)) for j,cp in enumerate(CHECKPOINTS)]
        s['splits']={key:dict(score=mean(r['split'][key]['score'] for r in rows),survival=mean(r['split'][key]['survival'] for r in rows)) for key in rows[0]['split']}
        if arm!='RL-RP':
            s['frozen_prediction']=dict(model_MSE=mean(r['prediction_model_MSE'] for r in rows),identity_MSE=mean(r['prediction_identity_MSE'] for r in rows),
                model_better_than_identity_seeds=sum(r['prediction_model_MSE']<r['prediction_identity_MSE'] for r in rows),
                actual_bootstrap_inclusion=[mean(r['bootstrap_inclusion'][j] for r in rows) for j in range(3)])
        if arm in ['F-RP','F-R']:
            s['frozen_readout']=dict(full_score=mean(r['frozen_Q_only']['full_score'] for r in rows),
                Q_only_score=mean(r['frozen_Q_only']['Q_only_score'] for r in rows),
                full_minus_Q=describe([r['frozen_Q_only']['full_minus_Q'] for r in rows]),
                full_better_seeds=sum(r['frozen_Q_only']['full_minus_Q']>0 for r in rows))
        summaries.append(s)
    pairs=[]
    for treatment,reference in [('F-RP','RL-RP'),('F0','RL-RP'),('F-RP','F-R')]:
        ta=[r for r in per_case if r['arm']==treatment];re=[r for r in per_case if r['arm']==reference]
        pairs.append(dict(treatment=treatment,reference=reference,final_score_difference=describe([a['final_score']-b['final_score'] for a,b in zip(ta,re)]),
            seen_duo_AUC_difference=describe([a['seen_duo_AUC']-b['seen_duo_AUC'] for a,b in zip(ta,re)])))
    result=dict(status='COMPLETE_SMALL_REPAIR_PILOT_NOT_FULL_V09',native_exit=0,stored_review_exit=0,
        summaries=summaries,paired_seed_differences=pairs,per_case=per_case,
        actual=dict(training_steps=sum(r['training_steps'] for r in all_results),
            evaluation_episodes=sum(b['episodes'] for r in all_results for b in r['evaluations']),
            evaluation_steps=sum(b['steps'] for r in all_results for b in r['evaluations']),
            all_environment_steps=sum(r['record_count'] for r in all_results),
            completed_training_episodes=sum(r['completed_training_episodes'] for r in all_results),
            optimizer_steps=16*1009,wall_seconds=native['wall_seconds']),
        inference_unit='4independent paired training seeds, not11264independent training samples.',
        limits=['Combined repair, not component-isolated causal attribution.','No task-score guarantee from improved prediction.','No automatic64seed expansion or claimV09complete.','Equal real training steps, not equal auxiliary compute.','PureRL also learns from experience; F0meansnoexternalrewardpacket/Qhead, not no objective.'])
    assert result['actual']['training_steps']==2097152 and result['actual']['evaluation_episodes']==11264
    assert result['actual']['all_environment_steps']<=4980736
    out=HERE/'analysis';out.mkdir(exist_ok=False)
    (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# V183 修复小试实测数据','','4个独立训练种子；每模型131072训练步，末点256评估。旧64种子批次未重启。',
        '','|组|最终均分|存活步数|宝箱|混合AUC|已见duo AUC|四种子分数范围|','|---|---:|---:|---:|---:|---:|---:|']
    for s in summaries:
        lines.append(f"|{s['arm']}|{s['final_score']['mean']:.3f}|{s['final_survival']['mean']:.3f}|{s['final_treasures']['mean']:.3f}|{s['mixed_AUC']['mean']:.6f}|{s['seen_duo_AUC']['mean']:.6f}|{s['final_score']['minimum']:.2f}–{s['final_score']['maximum']:.2f}|")
    lines+=['','## 冻结下一观察预测','','|组|模型后继MSE|不变基线MSE|模型更好的种子|','|---|---:|---:|---:|']
    for s in summaries:
        if 'frozen_prediction' in s:
            p=s['frozen_prediction'];lines.append(f"|{s['arm']}|{p['model_MSE']:.6f}|{p['identity_MSE']:.6f}|{p['model_better_than_identity_seeds']}/4|")
    lines+=['','## 同场景冻结读出对照','','|混合组|完整反馈读出|自己Q-only|完整读出更好的种子|','|---|---:|---:|---:|']
    for s in summaries:
        if 'frozen_readout' in s:
            p=s['frozen_readout'];lines.append(f"|{s['arm']}|{p['full_score']:.3f}|{p['Q_only_score']:.3f}|{p['full_better_seeds']}/4|")
    lines+=['','这是小规模组合修复验证，不等原64种子确认；不以评估回合数充当独立训练N。预测误差仅比较同模型实际选中动作、冻结评估路径上的后继表示。','',
        '新源码与实际执行结果保留；没有根据结果改参数、换seed、延长训练或启动下一轮。']
    (out/'result.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'status':result['status'],'actual':result['actual'],'four_groups':[{k:s[k]['mean'] for k in ['final_score','final_survival','final_treasures']}|{'arm':s['arm']} for s in summaries]},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
