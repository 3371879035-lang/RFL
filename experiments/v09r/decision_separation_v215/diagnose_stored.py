"""Post-result recorded diagnosis, no learner imports, updates, or new trials."""
from pathlib import Path
from collections import Counter
import gzip
import hashlib
import json
import statistics

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]


def main():
    contract=json.loads((HERE/'contract.json').read_text(encoding='utf-8'))
    review=json.loads((HERE/'stored_review.json').read_text(encoding='utf-8'))
    execution=json.loads((HERE/'capture/exit.json').read_text(encoding='utf-8'))
    checks=json.loads((HERE/'check_result.json').read_text(encoding='utf-8'))
    assert execution['complete'] and checks['passed']==8 and checks['failed']==0
    bad=[];recent={}
    for folder in sorted((HERE/'shards').glob('selective_change_*')):
        with gzip.open(folder/'raw.jsonl.gz','rt',encoding='utf-8') as f:
            for line in f:
                r=json.loads(line)
                if r['kind']=='start':spec=r['spec']
                if r['kind'] not in ['train_episode','eval_episode']:continue
                wire=r['offer'];x=r['public']['context'];truth=x[spec['payload']]^x[spec['condition']]
                if r['kind']=='train_episode' and r['slot']<128 and x[spec['condition']]==1:
                    a=r['public']['action'];y=r['public']['outcome'];lh=wire['history_prediction'][a][y];lf=wire['fresh_prediction'][a][y]
                    recent.setdefault(spec['seed'],[]).append({'task':r['slot']+1,'context':x,'action':a,'outcome':y,
                        'true_best_action':truth,'history_weight_before':wire['history_share'],
                        'H_likelihood':lh,'F_likelihood':lf,'likelihood_ratio_H_over_F':lh/lf})
                if r['kind']!='eval_episode' or r['checkpoint']!=128:continue
                fb=max(range(2),key=lambda a:wire['fresh_prediction'][a][1]);nb=max(range(2),key=lambda a:wire['prediction'][a][1])
                if fb==truth and nb!=truth:
                    df=wire['fresh_prediction'][truth][1]-wire['fresh_prediction'][1-truth][1]
                    dh=wire['history_prediction'][truth][1]-wire['history_prediction'][1-truth][1]
                    bad.append({'seed':spec['seed'],'context':x,'condition':x[spec['condition']],
                                'history_weight':wire['history_share'],'decision_switch_threshold':df/(df-dh),
                                'fresh_advantage':df,'historical_advantage':dh,'mixed_scores':wire['decision_scores']})
    counts=Counter((v['seed'],tuple(v['context'])) for v in bad)
    details=[{'seed':seed,'context':list(x),'eval_occurrences':n,
              'example':next(v for v in bad if v['seed']==seed and tuple(v['context'])==x)} for (seed,x),n in counts.items()]
    aggregate=[]
    for family in contract['families']:
        rows=[r for r in review['rows'] if r['family']==family]
        for ck in ['0','16','64','128','256']:
            row={'family':family,'checkpoint':int(ck)}
            row.update({k:statistics.mean(r['diagnostics'][ck][k] for r in rows)
                        for k in rows[0]['diagnostics'][ck] if k!='history_weight_by_condition'})
            row['history_weight_by_condition']={}
            for c in ['0','1']:
                values=[r['diagnostics'][ck]['history_weight_by_condition'][c] for r in rows
                        if r['diagnostics'][ck]['history_weight_by_condition'][c] is not None]
                row['history_weight_by_condition'][c]=statistics.mean(values) if values else None
            aggregate.append(row)
    diagnosis={'schema':'v215-post-result-recorded-diagnosis','new_interactions':0,'model_replays':0,'parameter_updates':0,
               'selective_checkpoint128_current_correct_mixed_wrong_records':len(bad),'grouped_records':details,
               'preceding_actual_condition1_observations':{str(seed):recent[seed][-12:] for seed in sorted({x['seed'] for x in bad})},
               'aggregate_expected_values':aggregate,'known_kernel_used_only_for_posthoc_evaluation':True,
               'claim_boundary':'Observed predictive weighting resurgence; no hazard/noise-calibration ablation, so do not attribute all error to gamma or treat the posthoc sequence probability as a significance test.'}
    with(HERE/'posthoc_diagnostic.json').open('x',encoding='utf-8') as f:json.dump(diagnosis,f,indent=2)
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in contract['input_sha256'].items())
    summary={'schema':'v215-result-summary','status':'DECISION_QUOTA_DEFECT_REMOVED_IN_FINITE_TEST_PREDICTIVE_APPLICABILITY_REMAINS_PARTIAL',
             'formula_checks_passed':8,'formula_checks_failed':0,'new_native_shards':64,'new_native_errors':0,
             'stored_review_exit':0,'wall_seconds':execution['wall_seconds'],'old_native_reruns':0,'automatic_retries':0,
             'new_actual_interactions':57344,'training_interactions':16384,'evaluation_interactions':40960,
             'recorded_history_imports':16384,'new_history_interactions':0,'raw_records':review['records'],
             'max_formula_error':review['max_formula_error'],'gradient_updates':0,'SLEEP_consolidations':0,
             'input_files':len(contract['input_sha256']),'input_sha256_unchanged':True,
             'table':review['table'],'paired_differences':review['differences'],'posthoc_diagnostic':'posthoc_diagnostic.json',
             'supported':['Prediction source weights no longer force execution fractions.',
                          'Given the same supplied facts, predictive learning is unchanged; only decision readout differs.',
                          'New finite runs improve changed-world postlearning success vs V214; selective mean improves but paired interval crosses zero.',
                          'All learned-world final checkpoints match the corresponding fresh and temporal stored evaluations; no universal superiority claim.'],
             'retained_adverse':['Changed-world initial success decreases; first16 training also decreases vs V214.',
                                 'Changed-world postlearning mean still below the old temporal control.',
                                 'Selective seed8 checkpoint128 overweights invalid history after misleading stochastic outcomes.',
                                 'Finite categorical known-boundary developer benchmark, not general causal discovery or calibrated confidence.']}
    with(HERE/'result_summary.json').open('x',encoding='utf-8') as f:json.dump(summary,f,indent=2)
    print(json.dumps({'new_native_shards':64,'posthoc_wrong_records':len(bad),'affected_seeds':sorted({r['seed'] for r in bad}),
                      'input_pins_unchanged':True,'new_interactions_in_diagnosis':0}))


if __name__=='__main__':main()
