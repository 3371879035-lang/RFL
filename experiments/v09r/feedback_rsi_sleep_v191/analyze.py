"""Prewritten descriptive analysis: paired development seeds, no significance gate."""
import json
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent


def main():
    data=json.loads((HERE/'evidence_pilot/result.json').read_text())
    assert data['exit']['exit_code']==0
    cases=data['cases'];groups={}
    for arm in ('RL-RP','F0','F-RP','F-R'):
        variants={}
        for variant in ('matched_replay','adaptive_sleep'):
            rows=sorted([r for r in cases if r['arm']==arm and r['variant']==variant],key=lambda r:r['seed'])
            assert len(rows)==4
            def point(r,cp):return next(x for x in r['evaluations'] if x['checkpoint']==cp)
            per_seed=[]
            for r in rows:
                final=point(r,12288)
                curve=[point(r,cp)['common64']['mean_score'] for cp in (0,4096,8192,12288)]
                per_seed.append(dict(seed=r['seed'],final_score=final['mean_score'],
                    mean_steps=final['mean_steps'],mean_treasures=final['mean_treasures'],
                    seen=final['seen']['mean_score'],heldout=final['heldout']['mean_score'],
                    stationary_rate=final['stationary_rate'],common64_curve=curve,
                    normalized_auc=(curve[0]/2+curve[1]+curve[2]+curve[3]/2)/3,
                    last_sleep_score_delta=point(r,12288)['common64']['mean_score']-point(r,-12288)['common64']['mean_score'],
                    final_policy=r['final_rehearsal_policy'],
                    final_probe_change=r['sleep_rounds'][-1]['before_probe']-r['sleep_rounds'][-1]['after_probe'],
                    theta_changes=sum(s['previous_theta']!=s['next_theta'] for s in r['sleep_rounds']),
                    kept_parent_teacher=sum(s['selected'] is None for s in r['sleep_rounds']) if variant=='adaptive_sleep' else None,
                    wall_seconds=r['wall_seconds'],sleep_wall_seconds=r['sleep_wall_seconds']))
            keys=('final_score','mean_steps','mean_treasures','seen','heldout','stationary_rate',
                  'normalized_auc','last_sleep_score_delta','wall_seconds','sleep_wall_seconds')
            variants[variant]=dict(per_seed=per_seed,mean={k:float(np.mean([r[k] for r in per_seed])) for k in keys},
                mean_common64_curve=np.mean([r['common64_curve'] for r in per_seed],axis=0).tolist())
        control=variants['matched_replay']['per_seed'];adaptive=variants['adaptive_sleep']['per_seed']
        differences=[dict(seed=a['seed'],score=a['final_score']-b['final_score'],
                          auc=a['normalized_auc']-b['normalized_auc'],heldout=a['heldout']-b['heldout'])
                     for a,b in zip(adaptive,control)]
        groups[arm]=dict(variants=variants,paired=differences,
                        mean_difference=float(np.mean([r['score'] for r in differences])),
                        positive_seeds=sum(r['score']>0 for r in differences))
    result=dict(scope='One preregistered bounded development pilot, four existing seeds, no population superiority claim.',
                groups=groups,execution=data['exit'],
                totals=dict(wake_steps=sum(r['additional_train_steps'] for r in cases),
                optimizer_updates=sum(r['counters']['v191_optimizer_updates'] for r in cases),
                actual_records=sum(r['raw_records'] for r in cases),
                candidate_branches=sum(len(s['candidates']) for r in cases for s in r['sleep_rounds']),
                learned_policy_changes=sum(s['previous_theta']!=s['next_theta'] for r in cases for s in r['sleep_rounds'])))
    out=HERE/'analysis';out.mkdir(exist_ok=False)
    with (out/'result.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({arm:dict(control=g['variants']['matched_replay']['mean']['final_score'],
                adaptive=g['variants']['adaptive_sleep']['mean']['final_score'],
                difference=g['mean_difference'],positive_seeds=g['positive_seeds']) for arm,g in groups.items()}))
    return 0


if __name__=='__main__':raise SystemExit(main())
