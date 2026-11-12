from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import csv,gzip,hashlib,json,math,random,statistics
from scalar_v219 import Predictor,Model

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];OLD=HERE.parent/'evidence_persistence_v216'
FAMILIES=['stable_novel','changed_novel','selective_change','noise','selective_return','mixed_reliability']
ARMS=['continuous_prior_v219']


def scene_for(spec,phase,slot,checkpoint=0):
    family=spec['family'];code=0 if family in FAMILIES[:2] else FAMILIES.index(family)
    num=((code*100+spec['seed'])*3+{'history':0,'train':1,'eval':2}[phase])*1000000+checkpoint*1000+slot
    rng=random.Random(214100000000+num);x=[rng.randrange(2) for _ in range(3)]
    if family in FAMILIES[:2]:x[spec['condition']]=0 if phase=='history' else 1
    return {'context':x,'action_u':rng.random(),'outcome_u':rng.random()}


def truth(family,spec,index,x):
    desired=x[spec['payload']]
    if family=='changed_novel':desired^=1
    elif family=='selective_change' or (family=='selective_return' and index<128):desired^=x[spec['condition']]
    if family=='mixed_reliability':
        return [(.98 if a==desired else .02) if x[spec['condition']]==0 else (.6 if a==desired else .4) for a in range(2)]
    return [.5 if family=='noise' else .9 if a==desired else .1 for a in range(2)]


def numbers(value):
    if isinstance(value,list):
        for v in value:yield from numbers(v)
    else:yield value


def close(a,b):
    aa=list(numbers(a));bb=list(numbers(b));assert len(aa)==len(bb)
    error=max(abs(v-w) for v,w in zip(aa,bb));assert error<3e-11,error
    return error


def calibration_check(w,c):
    maximum=0.
    for wk,ck in [('calibration_weights','weights'),('calibration_coefficients','coefficients'),('calibration_within_variance','within'),('calibration_between_variance','between'),('bias_conditional_mean','bias_mean'),('bias_conditional_variance','bias_variance')]:
        maximum=max(maximum,close(w[wk],c[ck]))
    for a in range(2):
        p=w['prediction'][a][1]
        assert abs(w['calibration_within_variance'][a]+w['calibration_between_variance'][a]-p*(1-p))<2e-12
    return maximum


def measure(w,d,probs):
    a,y=d['action'],d['outcome'];p=w['prediction'];b=w.get('base_prediction',p);f=w['fresh_prediction']
    best=max(range(2),key=lambda a:p[a][1]);base_best=max(range(2),key=lambda a:b[a][1]);fb=max(range(2),key=lambda a:f[a][1])
    optimal={a for a in range(2) if probs[a]==max(probs)};target=max(range(2),key=lambda a:probs[a])
    return {'log_loss':-math.log(p[a][y]),'brier':(p[a][1]-y)**2,
            'kernel_mse':statistics.mean((p[a][1]-probs[a])**2 for a in range(2)),
            'base_same_state_kernel_mse':statistics.mean((b[a][1]-probs[a])**2 for a in range(2)),
            'calibration_extra_wrong':int(base_best in optimal and best not in optimal),
            'calibration_rescue':int(base_best not in optimal and best in optimal),
            'current_correct_final_wrong':int(fb in optimal and best not in optimal),
            'delta_best_probability':p[target][1]-b[target][1],
            'best_probability':p[target][1],'best_base_probability':b[target][1],
            'bias_mass':statistics.mean(v[3] for v in w['calibration_weights']),
            'bias_variance':statistics.mean(w['bias_conditional_variance']),
            'bias_mean_abs':statistics.mean(abs(v) for v in w['bias_conditional_mean']),
            'model_variance':statistics.mean(w['calibration_between_variance'])}


def means(values):return {k:statistics.mean(v[k] for v in values) for k in values[0]}


def finish(row,train,evmetrics,conditionmetrics,origin):
    return {**row,'train_metrics':means(train),'eval_metrics':{str(k):means(v) for k,v in evmetrics.items()},
            'condition_metrics':{str(k):{str(c):means(vv) for c,vv in v.items()} for k,v in conditionmetrics.items()},'data_origin':origin}


def review_native(name):
    folder=HERE/'shards'/name;native=json.loads((folder/'native_result.json').read_text(encoding='utf-8'));path=folder/'raw.jsonl.gz'
    assert hashlib.sha256(path.read_bytes()).hexdigest()==native['raw_sha256']
    h=Predictor(0.);t=Predictor(.05);imports=[];rows=[];records=events=0;maximum=0.;ended=False
    with gzip.open(path,'rt',encoding='utf-8') as stream:
        for line in stream:
            assert not ended;r=json.loads(line);records+=1;kind=r['kind']
            assert json.dumps(r,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n'==line
            if kind=='start':
                family=r['family'];spec=r['source_spec'];seed=r['seed'];checkpoints=r['checkpoints']
                assert [spec['payload'],spec['condition'],spec['nuisance']]==random.Random(2144000+seed).sample(range(3),3)
                assert r['return_after']==(128 if family=='selective_return' else None)
                assert r['arms']==ARMS
                src=ROOT/r['history_source'];assert hashlib.sha256(src.read_bytes()).hexdigest()==r['history_sha256'];source={}
                with gzip.open(src,'rt',encoding='utf-8') as old:
                    for n,s in enumerate(old,1):
                        o=json.loads(s)
                        if o['kind']=='history':source[n]=o['public']
                        elif o['kind']=='history_ready':break
            elif kind=='history_import':
                d=r['public'];assert d==source[r['source_record']] and d['id']==len(imports)
                h.observe(d['context'],d['action'],d['outcome']);t.observe(d['context'],d['action'],d['outcome']);imports.append(d)
            elif kind=='arm_start':
                arm=r['arm'];mode=r['mode'];model=Model(arm,h,t);last_id=255;train=[];ev=[];evals=[];tm=[];em={};cm={};cached={};seen={}
                assert len(imports)==256
                for d in imports:seen[tuple(d['context'])]=seen.get(tuple(d['context']),0)+1
            elif kind in ['train_episode','eval_episode']:
                assert r['arm']==arm;phase='train' if kind=='train_episode' else 'eval';ck=r.get('checkpoint',0)
                scene=scene_for(spec,phase,r['slot'],ck);assert scene==r['scene'];d=r['public'];x=scene['context'];w=r['offer']
                assert d['context']==x and d['id']==last_id+1 and d['policy_id']==mode;last_id=d['id'];events+=1;key=tuple(x)
                if phase=='train' or key not in cached:cached[key]=model.predict(x)
                p,lam,hp,fp,cache=cached[key]
                for got,expected in [(w['prediction'],p),(w['base_prediction'],cache['base_prediction']),(w['history_prediction'],hp),(w['fresh_prediction'],fp)]:maximum=max(maximum,close(got,expected))
                maximum=max(maximum,close(w['rate_weights'],cache['base_cache'][1][-1]));assert abs(w['history_share']-lam)<3e-11
                if arm!='raw_v216':maximum=max(maximum,calibration_check(w,cache['calibration']))
                assert all(abs(sum(pp)-1)<2e-12 for pp in w['prediction'])
                scores=[v[1] for v in w['prediction']];best=max(range(2),key=lambda a:scores[a]);mu=[.9 if a==best else .1 for a in range(2)]
                assert w['decision_scores']==scores and w['behavior']==mu and abs(w['estimated_margin']-abs(scores[0]-scores[1]))<1e-14
                a=int(scene['action_u']<mu[1]);assert d['action']==a and d['propensity']==mu[a]
                probs=truth(family,spec,r['slot'] if phase=='train' else ck,x);assert d['outcome']==int(scene['outcome_u']<probs[a]);m=measure(w,d,probs)
                if phase=='train':
                    assert r['slot']==len(train) and w['id']==d['id'] and w['context']==x and w['previous_full_context_observations']==seen.get(key,0)
                    tm.append(m);model.observe(x,a,d['outcome'],cache);cached={};train.append(d['outcome']);seen[key]=seen.get(key,0)+1
                else:
                    assert r['slot']==len(ev);ev.append(d['outcome']);em.setdefault(ck,[]).append(m);cm.setdefault(ck,{}).setdefault(x[spec['condition']],[]).append(m)
            elif kind=='eval_end':
                assert r['checkpoint']==len(train) and r['successes']==sum(ev) and len(ev)==128 and r['state_unchanged']
                evals.append({k:v for k,v in r.items() if k not in ['kind','arm']});ev=[]
            elif kind=='arm_end':
                row={k:v for k,v in r.items() if k!='kind'};assert row in native['rows'] and row['evaluations']==evals
                assert len(train)==256 and row['training_successes']==sum(train) and row['first16_successes']==sum(train[:16]) and row['first64_successes']==sum(train[:64])
                assert row['second_half_successes']==sum(train[128:])
                if family=='selective_return':assert row['return_first16_successes']==sum(train[128:144])
                assert row['parameters_unchanged'] and row['history_unchanged'] and row['archive_facts']==512
                assert row['trainable_calibration_scalars']==80
                assert row['evidence_polynomial_columns']==257
                rows.append(finish(row,tm,em,cm,'new_V218_environment_execution'))
            elif kind=='end':
                assert events==r['new_actual_interactions']==r['steps'] and r['history_imports']==256 and r['new_history_interactions']==0
                assert r['gradient_updates']==0 and r['input_unchanged'] and r['torch_rng_unchanged'];ended=True
            else:raise AssertionError(kind)
    assert ended and events==native['new_actual_interactions'] and records==native['records']
    out={'rows':rows,'records':records,'interactions':events,'max_formula_error':maximum,'history_imports':len(imports)}
    with(folder/'stored_review.json').open('x',encoding='utf-8') as f:json.dump(out,f,indent=2)
    return out


def points_for(f):
    return [144,160,192,256] if f=='selective_return' else [16,64,128,256]


def primary(r):
    return statistics.mean(e['successes']/128 for e in r['evaluations'] if e['checkpoint'] in points_for(r['family']))


def main():
    contract=json.loads((HERE/'contract.json').read_text(encoding='utf-8'))
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in contract['input_sha256'].items())
    jobs=[f'{f}_s{s:02d}' for f in FAMILIES for s in range(16)]
    with ProcessPoolExecutor(max_workers=4) as pool:results=list(pool.map(review_native,jobs))
    oldfile=HERE.parent/'bidirectional_calibration_v218'/'stored_review.json'
    old=json.loads(oldfile.read_text(encoding='utf-8'))
    reference_arms=['raw_v216','conditional_temperature_v218','conditional_full_v218']
    # Frozen prior results are controls, not new executions of the old code.
    refs=[dict(r,data_origin='stored_V218_review_reference_no_rerun') for r in old['rows'] if r['arm'] in reference_arms]
    rows=[r for result in results for r in result['rows']]+refs;assert len(rows)==384
    table=[];diffs=[]
    for fi,family in enumerate(FAMILIES):
        points=points_for(family)
        for arm in reference_arms+ARMS:
            sub=sorted([r for r in rows if r['family']==family and r['arm']==arm],key=lambda r:r['seed']);assert len(sub)==16
            cks=[e['checkpoint'] for e in sub[0]['evaluations']]
            line={'family':family,'arm':arm,'data_origin':sub[0]['data_origin'],'seeds':16,
                  'train_success_rate':statistics.mean(r['training_successes']/256 for r in sub),
                  'first64_success_rate':statistics.mean(r['first64_successes']/64 for r in sub),
                  'checkpoints':cks,'eval_curve':[statistics.mean(r['evaluations'][i]['successes']/128 for r in sub) for i in range(len(cks))],
                  'primary_eval_mean':statistics.mean(primary(r) for r in sub)}
            for metric in ['log_loss','brier','kernel_mse','base_same_state_kernel_mse','calibration_extra_wrong','calibration_rescue']:
                line['train_'+metric]=statistics.mean(r['train_metrics'][metric] for r in sub)
                line['eval_'+metric]=statistics.mean(r['eval_metrics'][str(k)][metric] for r in sub for k in points)
            for metric in ['bias_mass','bias_variance','bias_mean_abs','model_variance']:
                line['eval_'+metric]=statistics.mean(r['eval_metrics'][str(k)][metric] for r in sub for k in points) if arm in ARMS else None
            line['by_condition']={str(c):{m:statistics.mean(r['condition_metrics'][str(k)][str(c)][m] for r in sub for k in points if str(c) in r['condition_metrics'][str(k)])
                                          for m in ['kernel_mse','delta_best_probability','best_probability','best_base_probability']}
                                  for c in [0,1] if any(str(c) in r['condition_metrics'][str(k)] for r in sub for k in points)}
            table.append(line)
        new=sorted([r for r in rows if r['family']==family and r['arm'] in ARMS],key=lambda r:r['seed'])
        for ai,refarm in enumerate(reference_arms):
            ref=sorted([r for r in rows if r['family']==family and r['arm']==refarm],key=lambda r:r['seed'])
            for mi,metric in enumerate(['success','log_loss','brier','kernel_mse']):
                def value(r):return primary(r) if metric=='success' else statistics.mean(r['eval_metrics'][str(k)][metric] for k in points)
                vals=[value(a)-value(b) for a,b in zip(new,ref)];rng=random.Random(219900+fi*100+ai*10+mi)
                boot=sorted(statistics.mean(rng.choices(vals,k=16)) for _ in range(2000))
                diffs.append({'family':family,'reference':refarm,'metric':metric,'new_minus_reference':statistics.mean(vals),
                              'paired_seed_values':vals,'exploratory_bootstrap_95':[boot[49],boot[1949]]})
    out={'schema':'v219-independent-stored-review','new_shards':96,'new_arm_runs':96,'stored_control_rows':288,
         'new_interactions':sum(r['interactions'] for r in results),'training_interactions':24576,'evaluation_interactions':67584,
         'new_history_interactions':0,'history_imports':24576,'unique_existing_history_events':16384,'arm_history_exposure':24576,
         'canonical_native_records':sum(r['records'] for r in results),'max_formula_error':max(r['max_formula_error'] for r in results),
         'old_native_reruns':0,'new_interactions_in_review':0,'torch_imports':0,'optimizer_steps':0,
         'reference_review_sha256':hashlib.sha256(oldfile.read_bytes()).hexdigest(),'table':table,'differences':diffs,'rows':rows}
    assert out['new_interactions']==92160 and out['canonical_native_records']==117648
    with(HERE/'stored_review.json').open('x',encoding='utf-8') as f:json.dump(out,f,indent=2)
    with(HERE/'summary.csv').open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(table[0]));w.writeheader();w.writerows(table)
    print(json.dumps({k:out[k] for k in ['new_shards','new_interactions','canonical_native_records','max_formula_error']}))


if __name__=='__main__':main()


