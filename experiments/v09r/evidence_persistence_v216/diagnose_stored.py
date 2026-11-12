"""Post-result same-record gate analysis; no new environment or learner execution."""
from pathlib import Path
import gzip,hashlib,json,statistics
from scalar_v216 import Gate

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]


def main():
    review=json.loads((HERE/'stored_review.json').read_text(encoding='utf-8'))
    contract=json.loads((HERE/'contract.json').read_text(encoding='utf-8'))
    execution=json.loads((HERE/'capture/exit.json').read_text(encoding='utf-8'))
    checks=json.loads((HERE/'check_result.json').read_text(encoding='utf-8'))
    assert execution['complete'] and checks['passed']==8 and checks['failed']==0
    source=ROOT/'experiments/v09r/decision_separation_v215/shards/selective_change_s08/raw.jsonl.gz'
    gates={'no_reopening':Gate((0.,)),'rate_mixture':Gate()};comparisons=[];updates=0
    with gzip.open(source,'rt',encoding='utf-8') as f:
        for line in f:
            r=json.loads(line)
            if r['kind']=='start':spec=r['spec']
            if r['kind']=='train_episode' and r['slot']<128:
                wire=r['offer'];d=r['public'];x=d['context']
                for gate in gates.values():
                    _,_,cache=gate.predict(x,wire['history_prediction'],wire['fresh_prediction']);gate.observe(cache,d['action'],d['outcome'])
                updates+=1
            elif r['kind']=='eval_episode' and r['checkpoint']==128:
                wire=r['offer'];x=r['public']['context'];correct=x[spec['payload']]^x[spec['condition']]
                old=max(range(2),key=lambda a:wire['prediction'][a][1]);row={'context':x,'old_correct':old==correct,'old_history_weight':wire['history_share']}
                for name,gate in gates.items():
                    p,lam,cache=gate.predict(x,wire['history_prediction'],wire['fresh_prediction'])
                    row[name]={'correct':max(range(2),key=lambda a:p[a][1])==correct,'history_weight':lam,'rate_weights':cache[-1]}
                comparisons.append(row)
            elif r['kind']=='train_episode' and r['slot']>=128:break
    assert updates==128 and len(comparisons)==128
    record={'old_wrong_greedy':sum(not x['old_correct'] for x in comparisons),
            **{name+'_wrong_greedy':sum(not x[name]['correct'] for x in comparisons) for name in gates}}
    condition_one=[x for x in comparisons if x['context'][spec['condition']]==1]
    record['condition1_mean_history_weights']={'old':statistics.mean(x['old_history_weight'] for x in condition_one),
                                               **{name:statistics.mean(x[name]['history_weight'] for x in condition_one) for name in gates}}
    aggregate=[]
    for family in contract['families']:
        for arm in ['fixed_v215','no_reopening_v216','rate_mixture_v216']:
            rows=[x for x in review['rows'] if x['family']==family and x['arm']==arm]
            for ck in rows[0]['diagnostics']:
                a={'family':family,'arm':arm,'checkpoint':int(ck)}
                a.update({k:statistics.mean(x['diagnostics'][ck][k] for x in rows) for k in ['extra_wrong','J_policy','J_current','history_weight','mean_reopening_rate']})
                n=len(rows[0]['diagnostics'][ck]['rate_weights'])
                a['rate_weights']=[statistics.mean(x['diagnostics'][ck]['rate_weights'][i] for x in rows) for i in range(n)]
                aggregate.append(a)
    diagnostic={'schema':'v216-post-result-recorded-diagnosis','new_interactions':0,'new_neural_runs':0,
                'same_record_seed8_gate_updates_per_candidate':128,'same_record_summary':record,'same_record_details':comparisons,
                'scope':'Two new scalar gates receive identical recorded V215 pre-action H/F predictions, contexts, actual actions/outcomes. Only gate changes. Hypothetical decisions at stored eval inputs are not fresh policy rollouts; primary outcomes come from new native experiments.',
                'aggregate_diagnostics':aggregate}
    with(HERE/'posthoc_diagnostic.json').open('x',encoding='utf-8') as f:json.dump(diagnostic,f,indent=2)
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==v for p,v in contract['input_sha256'].items())
    summary={'schema':'v216-result-summary','status':'REDUCED_OBSERVED_REACTIVATION_WITH_RESPONSIVENESS_TRADEOFF_NOT_GENERAL_GAIN',
             'formula_checks_passed':8,'formula_checks_failed':0,'new_shards':80,'new_arm_runs':176,'new_native_errors':0,
             'stored_review_exit':0,'wall_seconds':execution['wall_seconds'],'new_interactions':176128,
             'training_interactions':45056,'evaluation_interactions':131072,'recorded_history_import_operations':20480,
             'unique_existing_source_events':16384,'arm_history_exposure':45056,'new_history_interactions':0,
             'canonical_records':review['records'],'max_formula_error':review['max_formula_error'],
             'old_native_reruns':0,'automatic_retries':0,'gradient_updates':0,'SLEEP_consolidations':0,
             'input_files':len(contract['input_sha256']),'input_sha256_unchanged':True,
             'table':review['table'],'paired_differences':review['differences'],'same_record_seed8':record,
             'supported':['Conditional source persistence can be learned by comparing prequential hypotheses.',
                          'The previously observed late invalid-history revival is absent at tested late static checkpoints.',
                          'Fixed zero reopening is slower after the new genuine restoration; mixture recovers more quickly than this ablation.'],
             'limitations':['Overall static task-success gains are near zero; early learning loss offsets late correction.',
                            'Restoration first16 training remains below the original fixed .02 method.',
                            'Rate grid and uniform prior are engineering choices, not a discovered true environment hazard.',
                            'Noise calibration, high-dimensional context, hidden causes, and general causal attribution remain unresolved.']}
    with(HERE/'result_summary.json').open('x',encoding='utf-8') as f:json.dump(summary,f,indent=2)
    print(json.dumps(record))


if __name__=='__main__':main()
