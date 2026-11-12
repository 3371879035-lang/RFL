"""Post-hoc algebra on the sole seed with primary success regression; no rollout."""
from pathlib import Path
import gzip,hashlib,json
HERE=Path(__file__).resolve().parent


def main():
    source=HERE/'shards/changed_novel_s13/raw.jsonl.gz'
    review=json.loads((HERE/'stored_review.json').read_text(encoding='utf-8'))
    new=[r for r in review['rows'] if r['family']=='changed_novel' and r['arm']=='continuous_prior_v219']
    failures=[r['seed'] for r in new if any(r['eval_metrics'][str(k)]['calibration_extra_wrong']>0 for k in [16,64,128,256])]
    assert failures==[13]
    rows=[]
    with gzip.open(source,'rt',encoding='utf-8') as f:
        for number,line in enumerate(f,1):
            r=json.loads(line)
            if r['kind']=='start':spec=r['source_spec']
            if r['kind']!='eval_episode' or r['checkpoint'] not in [16,64,128,256]:continue
            w=r['offer'];x=r['public']['context'];target=x[spec['payload']]^1
            p=[v[1] for v in w['base_prediction']];q=[v[1] for v in w['prediction']]
            base_best=max(range(2),key=lambda a:p[a]);best=max(range(2),key=lambda a:q[a])
            if base_best!=target or best==target:continue
            temperature=[p[a]+w['calibration_coefficients'][a][0]*p[a]*(1-p[a])*(2*p[a]-1) for a in range(2)]
            rows.append({'source_line':number,'checkpoint':r['checkpoint'],'slot':r['slot'],'context':x,'target_evaluator_only':target,
                         'base':p,'calibrated':q,'same_posterior_without_bias_algebra':temperature,
                         'base_margin':p[target]-p[1-target],'calibrated_margin':q[target]-q[1-target],
                         'without_bias_correct':max(range(2),key=lambda a:temperature[a])==target,
                         'coefficients':w['calibration_coefficients'],'bias_mean':w['bias_conditional_mean'],
                         'bias_variance':w['bias_conditional_variance']})
    expected=sum(round(r['eval_metrics'][str(k)]['calibration_extra_wrong']*128) for r in new for k in [16,64,128,256]);assert len(rows)==expected
    contexts=[]
    for x in sorted({tuple(r['context']) for r in rows}):
        group=[r for r in rows if tuple(r['context'])==x]
        contexts.append({'context':x,'records':len(group),'representative':group[0]})
    out={'posthoc':True,'new_environment_interactions':0,'model_executions':0,'source':source.relative_to(HERE).as_posix(),
         'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'sole_affected_seed':13,
         'misdirected_primary_evaluations':len(rows),'without_bias_same_posterior_correct':sum(r['without_bias_correct'] for r in rows),
         'by_context':contexts,'rows':rows,'interpretation':'Algebra on this actual trajectory, not retraining or a causal branch-removal experiment.'}
    with(HERE/'ranking_diagnostic.json').open('x',encoding='utf-8') as f:json.dump(out,f,indent=2)
    print(json.dumps({k:v for k,v in out.items() if k not in ['rows','by_context']}))
    print(json.dumps(contexts))


if __name__=='__main__':main()
