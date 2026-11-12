"""Posthoc arithmetic only: compare shrinkage at the identical stored H/F weights.

No learner/torch/world execution. Kernel belongs only to this diagnostic side.
"""
from pathlib import Path
import gzip,hashlib,json,statistics

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
FAMILIES=['stable_novel','changed_novel','selective_change','noise','selective_return']
ARMS=['rate_mixture_v216','shared_raw_v217','local_calibrated_v217','shared_calibrated_v217']


def main():
    contract=json.loads((HERE/'contract.json').read_text(encoding='utf-8'))
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in contract['input_sha256'].items())
    buckets={};files={};records=0
    for family in FAMILIES:
        points=[144,160,192,256] if family=='selective_return' else [16,64,128,256]
        for seed in range(16):
            for root,allowed in [(HERE.parent/'evidence_persistence_v216',[ARMS[0]]),(HERE,ARMS[1:])]:
                folder=root/'shards'/f'{family}_s{seed:02d}';path=folder/'raw.jsonl.gz'
                native=json.loads((folder/'native_result.json').read_text(encoding='utf-8'));digest=hashlib.sha256(path.read_bytes()).hexdigest()
                assert digest==native['raw_sha256'];files[path.relative_to(ROOT).as_posix()]=digest
                with gzip.open(path,'rt',encoding='utf-8') as f:
                    for line in f:
                        r=json.loads(line)
                        if r['kind']=='start':spec=r['source_spec']
                        if r['kind']!='eval_episode' or r['arm'] not in allowed or r['checkpoint'] not in points:continue
                        records+=1;x=r['public']['context'];w=r['offer'];desired=x[spec['payload']]
                        if family=='changed_novel':desired^=1
                        elif family=='selective_change':desired^=x[spec['condition']]
                        q=[.5 if family=='noise' else .9 if a==desired else .1 for a in range(2)]
                        predicted=[p[1] for p in w['prediction']];share=w['history_share']
                        unshrunk=[share*h[1]+(1-share)*f[1] for h,f in zip(w['history_prediction'],w['fresh_prediction'])]
                        mse=statistics.mean((p-t)**2 for p,t in zip(predicted,q));raw=statistics.mean((p-t)**2 for p,t in zip(unshrunk,q))
                        key=(family,r['arm'],seed)
                        buckets.setdefault(key,[]).append({'kernel_mse':mse,'same_state_unshrunk_mse':raw,'immediate_shrinkage_mse_difference':mse-raw,
                            'probability_on_true_best':predicted[desired] if family!='noise' else None,
                            'unshrunk_probability_on_true_best':unshrunk[desired] if family!='noise' else None,
                            'prediction_toward_chance':statistics.mean((1 if t>.5 else -1)*(p-t) for p,t in zip(predicted,q)) if family!='noise' else None,
                            'hypothesis_shrinkage':w.get('mean_prediction_shrinkage',0.),
                            'action_disagreement_if_shrinkage_omitted':int(max(range(2),key=lambda a:predicted[a])!=max(range(2),key=lambda a:unshrunk[a]))})
    table=[]
    for family in FAMILIES:
        for arm in ARMS:
            sub=[buckets[family,arm,s] for s in range(16)];assert all(len(v)==512 for v in sub)
            metrics={k:statistics.mean(statistics.mean(v[k] for v in seed) for seed in sub) if sub[0][0][k] is not None else None for k in sub[0][0]}
            table.append({'family':family,'arm':arm,**metrics})
    out={'schema':'v217-posthoc-stored-probability-diagnosis','source_files':files,'evaluated_stored_records':records,'new_environment_interactions':0,
         'new_neural_execution':0,'parameter_updates':0,'table':table,
         'interpretation':'Same-state algebra separates direct probability shrinkage only. It is not an executed alternative policy, not a trajectory effect, and kernel truth is unavailable to the learner.'}
    with(HERE/'posthoc_diagnostic.json').open('x',encoding='utf-8') as f:json.dump(out,f,indent=2)
    print(json.dumps({'evaluated_stored_records':records,'new_environment_interactions':0,'table':table},ensure_ascii=False))

if __name__=='__main__':main()
