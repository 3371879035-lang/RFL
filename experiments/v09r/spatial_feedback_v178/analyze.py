"""One analysis of complete V09 stored episodes. No learner or kernel imports."""
import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
import time
import numpy as np


def write_csv(path, rows):
    with path.open('x', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory')
    args = parser.parse_args()
    source = Path(args.directory)
    out = source.parent/'analysis'
    out.mkdir(exist_ok=False)
    started = time.perf_counter()
    models, curves, episodes = [], [], []
    for path in sorted(source.glob('seed*/*/result.json')):
        result = json.loads(path.read_text(encoding='utf-8'))
        assert result['status'] == 'COMPLETE' and result['phase'] == 'matrix'
        groups, training = {}, []
        with gzip.open(path.parent/'episodes.jsonl.gz', 'rt', encoding='utf-8') as f:
            for line in f:
                row = json.loads(line)
                if row['kind'] == 'training':
                    training.append(row)
                else:
                    key = (row['checkpoint'], row.get('ablation'), bool(row['heldout']), row['mode'])
                    groups.setdefault(key, []).append(row)
                    if row['checkpoint']==262144 and row.get('ablation') is None and row['episode']<128:
                        groups.setdefault((262144,'matched_full_128',bool(row['heldout']),row['mode']),[]).append(row)
        for (checkpoint, ablation, heldout, mode), bank in sorted(groups.items(), key=lambda x:str(x[0])):
            curve = dict(seed=result['seed'], arm=result['arm'], checkpoint=checkpoint,
                         ablation=ablation or '', heldout=heldout, mode=mode, episodes=len(bank),
                         mean_score=float(np.mean([r['score'] for r in bank])),
                         mean_survival=float(np.mean([r['steps'] for r in bank])),
                         mean_treasures=float(np.mean([r['treasures'] for r in bank])),
                         capture_rate=float(np.mean([r['captured'] for r in bank])))
            curves.append(curve)
        models.append(dict(seed=result['seed'], arm=result['arm'],
                           training_steps=result['training_steps'], train_episodes=len(training),
                           training_captures=sum(r['captured'] for r in training),
                           training_completions=sum(r['completed'] for r in training),
                           training_treasures=sum(r['treasures'] for r in training),
                           total_training_score=sum(r['score'] for r in training),
                           case_cpu_seconds=result['cpu_seconds'],case_wall_seconds=result['wall_seconds'],
                           changed_parameters=result['initial_parameter_hash'] != result['final_parameter_hash'],
                           **result['counters']))
    assert len(models) == 256
    assert len({(x['seed'],x['arm']) for x in models}) == 256
    arms=['RL-RP','F0','F-RP','F-R']
    checkpoints=[0,16384,65536,131072,262144]
    by_seed=[]
    for model in models:
        for heldout in [False,True]:
            for mode in [0,1]:
                bank=sorted([r for r in curves if r['seed']==model['seed'] and r['arm']==model['arm']
                             and r['heldout']==heldout and r['mode']==mode and not r['ablation']],key=lambda r:r['checkpoint'])
                assert [x['checkpoint'] for x in bank]==checkpoints
                scores=np.array([x['mean_score']/1384 for x in bank])
                values=dict(seed=model['seed'],arm=model['arm'],heldout=heldout,mode=mode,
                            AUC=float(np.trapezoid(scores,checkpoints)/262144),
                            early_AUC=float(np.trapezoid(scores[:3],checkpoints[:3])/65536),
                            final_score=bank[-1]['mean_score'],final_survival=bank[-1]['mean_survival'],
                            final_treasures=bank[-1]['mean_treasures'],final_capture=bank[-1]['capture_rate'])
                reached=[x['checkpoint'] for x in bank if x['mean_survival']>=192 and x['mean_treasures']>=3]
                values['first_observed_target']=min(reached) if reached else None
                by_seed.append(values)
    groups=[]
    for arm in arms:
        for heldout in [False,True]:
            for mode in [0,1]:
                rows=[r for r in by_seed if r['arm']==arm and r['heldout']==heldout and r['mode']==mode]
                group=dict(arm=arm,heldout=heldout,mode=mode,independent_training_seeds=len(rows))
                for name in ['AUC','early_AUC','final_score','final_survival','final_treasures','final_capture']:
                    v=np.array([r[name] for r in rows]); ordered=np.sort(v)
                    group[name]=float(v.mean());group[name+'_IQM']=float(ordered[16:48].mean())
                group['target_reached_seeds']=sum(r['first_observed_target'] is not None for r in rows)
                groups.append(group)
    seed=int.from_bytes(hashlib.blake2b(b'V09|analysis_bootstrap',digest_size=8).digest(),'little')
    resample=np.random.default_rng(seed).integers(0,64,(10000,64))
    comparisons=[]
    for left,right in [('F-RP','RL-RP'),('F0','RL-RP'),('F-RP','F-R')]:
        for heldout in [False,True]:
            for mode in [0,1]:
                for metric in ['AUC','early_AUC','final_score','final_survival','final_treasures']:
                    l={r['seed']:r[metric] for r in by_seed if r['arm']==left and r['heldout']==heldout and r['mode']==mode}
                    r={r['seed']:r[metric] for r in by_seed if r['arm']==right and r['heldout']==heldout and r['mode']==mode}
                    delta=np.array([l[s]-r[s] for s in range(9001,9065)])
                    boot=delta[resample].mean(-1)
                    comparisons.append(dict(left=left,right=right,heldout=heldout,mode=mode,metric=metric,
                         primary=not heldout and mode==1 and metric=='AUC',mean_delta=float(delta.mean()),
                         median_delta=float(np.median(delta)),low95=float(np.quantile(boot,.025)),
                         high95=float(np.quantile(boot,.975)),positive=int((delta>0).sum()),
                         zero=int((delta==0).sum()),negative=int((delta<0).sum())))
    ablations=[]
    for arm in arms[1:]:
        for ablation in ['H1_only','no_cross_episode_history_retrieval']:
            for heldout in [False,True]:
                for mode in [0,1]:
                    rows=[r for r in curves if r['arm']==arm and r['ablation']==ablation and r['heldout']==heldout and r['mode']==mode]
                    reference={r['seed']:r['mean_score'] for r in curves if r['arm']==arm and r['ablation']=='matched_full_128' and r['heldout']==heldout and r['mode']==mode}
                    delta=np.array([reference[r['seed']]-r['mean_score'] for r in sorted(rows,key=lambda x:x['seed'])])
                    boot=delta[resample].mean(-1)
                    ablations.append(dict(arm=arm,ablation=ablation,heldout=heldout,mode=mode,
                                           models=len(rows),mean_score=float(np.mean([r['mean_score'] for r in rows])),
                                           matched_full_score=float(np.mean(list(reference.values()))),
                                           full_minus_ablated_score=float(delta.mean()),
                                           low95=float(np.quantile(boot,.025)),high95=float(np.quantile(boot,.975))))
    write_csv(out/'models.csv',models)
    write_csv(out/'curves.csv',curves)
    write_csv(out/'paired_seed_metrics.csv',by_seed)
    write_csv(out/'group_summary.csv',groups)
    write_csv(out/'comparisons.csv',comparisons)
    write_csv(out/'ablations.csv',ablations)
    summary=dict(status='COMPLETE_STORED_V09_ANALYSIS',models=len(models),independent_seed_blocks=64,
                 total_training_steps=sum(x['training_steps'] for x in models),
                 completed_training_episodes=sum(x['train_episodes'] for x in models),
                 primary_comparisons=[x for x in comparisons if x['primary']],groups=groups,
                 all_comparisons=comparisons,ablations=ablations,
                 bootstrap_resamples=10000,bootstrap_random_integer_outputs=640000,
                 uncertainty='Descriptive paired training-seed intervals, not independent episode N or family PASS',
                 raw_optimal_value_available=False,normalization='1384 is dimensional upper bound, not measured attainable optimum',
                 native_calls=0,wall_seconds=time.perf_counter()-started)
    with (out/'analysis.json').open('x',encoding='utf-8') as f:
        json.dump(summary,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({k:summary[k] for k in ['status','models','total_training_steps','completed_training_episodes','primary_comparisons','wall_seconds']},ensure_ascii=False))


if __name__=='__main__':
    main()
