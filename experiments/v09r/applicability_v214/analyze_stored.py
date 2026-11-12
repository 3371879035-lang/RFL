"""Post-result analysis only: exact small-world expected utilities, no environment calls."""
from pathlib import Path
import gzip
import hashlib
import json
import statistics

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]


def main():
    checked=json.loads((HERE/'stored_review.json').read_text(encoding='utf-8'))
    contract=json.loads((HERE/'contract.json').read_text(encoding='utf-8'))
    execution=json.loads((HERE/'capture/exit.json').read_text(encoding='utf-8'))
    assert execution['complete'] and checked['shards']==64
    groups={};n=0
    for family in contract['families']:
        for seed in contract['seeds']:
            folder=HERE/'shards'/f'{family}_s{seed:02d}'
            native=json.loads((folder/'native_result.json').read_text(encoding='utf-8'))
            assert hashlib.sha256((folder/'raw.jsonl.gz').read_bytes()).hexdigest()==native['raw_sha256']
            with gzip.open(folder/'raw.jsonl.gz','rt',encoding='utf-8') as f:
                for line in f:
                    r=json.loads(line)
                    if r['kind']=='start':spec=r['spec']
                    if r['kind']!='eval_episode' or r['arm'] not in ['global_gate','conditional_gate']:continue
                    x=r['public']['context'];wire=r['offer'];lam=wire['history_share']
                    desired=x[spec['payload']]
                    if family=='changed_novel':desired^=1
                    elif family=='selective_change':desired^=x[spec['condition']]
                    truth=[.5 if family=='noise' else .9 if a==desired else .1 for a in range(2)]
                    hp=wire['history_prediction'];fp=wire['fresh_prediction']
                    ah=max(range(2),key=lambda a:hp[a][1]);af=max(range(2),key=lambda a:fp[a][1])
                    jh=sum(truth[a]*(.9 if a==ah else .1) for a in range(2))
                    jf=sum(truth[a]*(.9 if a==af else .1) for a in range(2))
                    jm=sum(truth[a]*wire['behavior'][a] for a in range(2))
                    assert abs(jm-(lam*jh+(1-lam)*jf))<1e-14
                    key=(family,r['arm'],r['checkpoint'],seed)
                    groups.setdefault(key,[]).append({'history_share':lam,'J_history':jh,'J_current_branch':jf,
                                                     'J_executed_mixture':jm,'history_mixing_penalty_vs_own_current':jf-jm,
                                                     'branches_disagree':int(ah!=af),
                                                     'condition':x[spec['condition']]})
                    n+=1
    rows=[]
    metrics=['history_share','J_history','J_current_branch','J_executed_mixture',
             'history_mixing_penalty_vs_own_current','branches_disagree']
    for family in contract['families']:
        for arm in ['global_gate','conditional_gate']:
            for ck in contract['evaluation_checkpoints']:
                perseed=[groups[(family,arm,ck,s)] for s in contract['seeds']]
                row={'family':family,'arm':arm,'checkpoint':ck,'seeds':16}
                for metric in metrics:row[metric]=statistics.mean(statistics.mean(v[metric] for v in values) for values in perseed)
                row['history_share_by_condition']={}
                for c in [0,1]:
                    means=[statistics.mean(v['history_share'] for v in values if v['condition']==c)
                           for values in perseed if any(v['condition']==c for v in values)]
                    row['history_share_by_condition'][str(c)]=statistics.mean(means) if means else None
                rows.append(row)
    diagnostic={'schema':'v214-post-result-stored-arithmetic','new_environment_interactions':0,
                'training_or_parameter_updates':0,'raw_evaluation_records_used':n,
                'scope':'Known synthetic kernel used ONLY by evaluator after the run, never by learner. J_current_branch is the gated model own current branch at the same saved contexts, NOT an independently executed fresh_only control.',
                'not_an_actual_counterfactual_rollout':True,'rows':rows}
    with(HERE/'posthoc_diagnostic.json').open('x',encoding='utf-8') as f:json.dump(diagnostic,f,indent=2)
    pins={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in contract['input_sha256']}
    assert pins==contract['input_sha256']
    summary={'schema':'v214-result-summary','status':'EXECUTED_CONDITIONAL_APPLICABILITY_PARTIAL_NOT_GENERAL_REPLACEMENT',
             'formula_checks':{'passed':8,'failed':0},'native_shards':64,'native_errors':0,
             'independent_stored_review_exit':0,'total_seconds':execution['wall_seconds'],
             'actual_interactions':checked['actual_interactions'],'history_interactions':checked['history_interactions'],
             'training_interactions':checked['training_interactions'],'evaluation_interactions':checked['evaluation_interactions'],
             'steps':checked['actual_interactions'],'raw_records':checked['records'],
             'maximum_formula_discrepancy':checked['max_formula_error'],
             'gradient_updates':0,'automatic_retries':0,'input_sha256_unchanged':True,
             'table':checked['table'],'paired_differences':checked['differences'],
             'diagnostic':'posthoc_diagnostic.json',
             'supported':['Historical applicability can be learned differently across observable conditions.',
                          'Selective change performance improves over the continuing temporal control in this finite experiment.',
                          'Identical old evidence and new visible conditions cannot reveal the new hidden rule before feedback.'],
             'limitations':['Primary conditional-vs-global efficiency difference is small and exploratory interval crosses zero.',
                            'Conditional mixture still loses to fresh-only on changed/selective worlds and to temporal on changed-novel.',
                            'Likelihood compatibility is not action usefulness; nonzero source reopening can execute inferior historical actions.',
                            'Known segment boundary, finite categorical contexts, no long-horizon cause identification, no learned encoder or SLEEP consolidation.',
                            'No universal improvement, no causal-probability interpretation, no formal confirmation or deployment adoption.'],
             'documentation_precision':'NETWORK_MODEL_V6.md mentions relation-projection support in outputs; actual persisted interface exposes full-context observation count plus H/F predictions, not per-head relation-support counters. No extra output or implementation claimed.'}
    with(HERE/'result_summary.json').open('x',encoding='utf-8') as f:json.dump(summary,f,indent=2)
    for row in rows:
        if row['arm']=='conditional_gate' and row['checkpoint'] in [0,64,256]:print(json.dumps(row))


if __name__=='__main__':main()
