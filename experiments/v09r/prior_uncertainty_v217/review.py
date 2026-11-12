from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import csv,gzip,hashlib,json,math,random,statistics,sys
from scalar_v217 import Predictor,make_model

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
OLD=HERE.parent/'evidence_persistence_v216'
FAMILIES=['stable_novel','changed_novel','selective_change','noise','selective_return']
ARMS=['rate_mixture_v216','shared_raw_v217','local_calibrated_v217','shared_calibrated_v217']


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
    return [.5 if family=='noise' else .9 if a==desired else .1 for a in range(2)]


def measure(wire,fact,probs):
    a,y=fact['action'],fact['outcome'];p=wire['prediction'];hp=wire['fresh_prediction']
    best=max(range(2),key=lambda a:p[a][1]);fresh=max(range(2),key=lambda a:hp[a][1])
    optimal={a for a in range(2) if probs[a]==max(probs)}
    return {'log_loss':-math.log(p[a][y]),'brier':(p[a][1]-y)**2,
            'kernel_mse':statistics.mean((p[a][1]-probs[a])**2 for a in range(2)),
            'extra_wrong':int(fresh in optimal and best not in optimal),
            'current_wrong':int(fresh not in optimal),'history_weight':wire['history_share'],
            'reopening':wire['mean_reopening_rate'],
            'shrinkage':wire.get('mean_prediction_shrinkage',0.),
            'within':wire.get('within_component_variance',[[0.,0.],[0.,0.]])[a][1],
            'between':wire.get('between_component_variance',[[0.,0.],[0.,0.]])[a][1]}


def means(values):
    return {k:statistics.mean(v[k] for v in values) for k in values[0]}


def review_shard(name):
    folder=HERE/'shards'/name;native=json.loads((folder/'native_result.json').read_text(encoding='utf-8'))
    assert hashlib.sha256((folder/'raw.jsonl.gz').read_bytes()).hexdigest()==native['raw_sha256']
    h=Predictor(0.);t=Predictor(.05);imports=[];rows=[];records=events=0;maximum=0.;ended=False
    with gzip.open(folder/'raw.jsonl.gz','rt',encoding='utf-8') as stream:
        for line in stream:
            assert not ended
            r=json.loads(line);records+=1;kind=r['kind']
            assert json.dumps(r,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n'==line
            if kind=='start':
                family=r['family'];spec=r['source_spec'];seed=r['seed'];checkpoints=r['checkpoints']
                assert [spec['payload'],spec['condition'],spec['nuisance']]==random.Random(2144000+seed).sample(range(3),3)
                assert r['return_after']==(128 if family=='selective_return' else None)
                assert sorted(r['arms'])==sorted(ARMS[1:])
                src=ROOT/r['history_source'];assert hashlib.sha256(src.read_bytes()).hexdigest()==r['history_sha256']
                source={}
                with gzip.open(src,'rt',encoding='utf-8') as old:
                    for n,s in enumerate(old,1):
                        o=json.loads(s)
                        if o['kind']=='history':source[n]=o['public']
                        elif o['kind']=='history_ready':break
            elif kind=='history_import':
                d=r['public'];assert d==source[r['source_record']] and d['id']==len(imports)
                h.observe(d['context'],d['action'],d['outcome']);t.observe(d['context'],d['action'],d['outcome']);imports.append(d)
            elif kind=='arm_start':
                arm=r['arm'];mode=r['mode'];rates=r['rates'];etas=r['etas'];model=make_model(arm,h,t)
                assert r['shared']==arm.startswith('shared') and len(imports)==256
                last_id=255;train=[];ev=[];evals=[];training_metrics=[];eval_metrics={};cached={}
                seen={}
                for d in imports:seen[tuple(d['context'])]=seen.get(tuple(d['context']),0)+1
            elif kind in ['train_episode','eval_episode']:
                assert r['arm']==arm;phase='train' if kind=='train_episode' else 'eval';checkpoint=r.get('checkpoint',0)
                scene=scene_for(spec,phase,r['slot'],checkpoint);assert scene==r['scene']
                d=r['public'];x=scene['context'];wire=r['offer'];assert d['context']==x and d['id']==last_id+1 and d['policy_id']==mode
                last_id=d['id'];events+=1;key=tuple(x)
                if phase=='train' or key not in cached:cached[key]=model.predict(x)
                p,lam,hp,fp,cache=cached[key];gc=cache[1]
                for got,expected in [(wire['prediction'],p),(wire['history_prediction'],hp),(wire['fresh_prediction'],fp),
                                     (wire['within_component_variance'],gc['within']),(wire['between_component_variance'],gc['between'])]:
                    for a,b in zip(got,expected):
                        for v,w in zip(a,b):maximum=max(maximum,abs(v-w));assert abs(v-w)<1e-11
                assert all(abs(sum(row)-1)<1e-12 for row in wire['prediction']) and abs(wire['history_share']-lam)<1e-11
                for got,expected in [(wire['rate_weights'],gc['rates']),(wire['eta_weights'],gc['etas'])]:
                    for a,b in zip(got,expected):maximum=max(maximum,abs(a-b));assert abs(a-b)<1e-11
                assert rates==wire['rate_hypotheses'] and etas==wire['eta_hypotheses']
                assert abs(wire['mean_reopening_rate']-sum(a*b for a,b in zip(rates,gc['rates'])))<1e-11
                assert abs(wire['mean_prediction_shrinkage']-sum(a*b for a,b in zip(etas,gc['etas'])))<1e-11
                for a in range(2):
                    for y in range(2):
                        pp=wire['prediction'][a][y]
                        assert abs(wire['within_component_variance'][a][y]+wire['between_component_variance'][a][y]-pp*(1-pp))<1e-12
                scores=[a[1] for a in wire['prediction']];best=max(range(2),key=lambda a:scores[a]);mu=[.9 if a==best else .1 for a in range(2)]
                assert wire['decision_scores']==scores and wire['behavior']==mu and abs(wire['estimated_margin']-abs(scores[0]-scores[1]))<1e-14
                a=int(scene['action_u']<mu[1]);assert d['action']==a and abs(d['propensity']-mu[a])<1e-14
                index=r['slot'] if phase=='train' else checkpoint;pr=truth(family,spec,index,x)
                assert d['outcome']==int(scene['outcome_u']<pr[a])
                m=measure(wire,d,pr)
                if phase=='train':
                    assert r['slot']==len(train) and wire['id']==d['id'] and wire['context']==x
                    assert wire['previous_full_context_observations']==seen.get(key,0)
                    training_metrics.append(m);model.observe(x,a,d['outcome'],cache);cached={}
                    train.append(d['outcome']);seen[key]=seen.get(key,0)+1
                else:
                    assert r['slot']==len(ev);ev.append(d['outcome']);eval_metrics.setdefault(checkpoint,[]).append(m)
            elif kind=='eval_end':
                assert r['arm']==arm and r['checkpoint']==len(train) and len(ev)==128 and r['successes']==sum(ev) and r['state_unchanged']
                evals.append({k:v for k,v in r.items() if k not in ['kind','arm']});ev=[]
            elif kind=='arm_end':
                row={k:v for k,v in r.items() if k!='kind'};assert row in native['rows'] and row['evaluations']==evals
                assert len(train)==256 and row['training_successes']==sum(train) and row['first16_successes']==sum(train[:16]) and row['first64_successes']==sum(train[:64])
                assert row['second_half_successes']==sum(train[128:])
                if family=='selective_return':assert row['return_first16_successes']==sum(train[128:144])
                assert row['parameters_unchanged'] and row['history_unchanged'] and row['archive_facts']==512
                assert row['trainable_prior_scalars']==(32 if arm=='shared_raw_v217' else 96)
                rows.append({**row,'train_metrics':means(training_metrics),'eval_metrics':{str(k):means(v) for k,v in eval_metrics.items()},'data_origin':'new_V217_execution'})
            elif kind=='end':
                assert events==r['new_actual_interactions']==r['steps'] and r['history_imports']==256 and r['new_history_interactions']==0
                assert r['gradient_updates']==0 and r['input_unchanged'] and r['torch_rng_unchanged'];ended=True
            else:raise AssertionError(kind)
    assert ended and events==native['new_actual_interactions'] and records==native['records'] and len(rows)==3
    out={'rows':rows,'records':records,'interactions':events,'max_formula_error':maximum,'history_imports':len(imports)}
    with(folder/'stored_review.json').open('x',encoding='utf-8') as f:json.dump(out,f,indent=2)
    return out


def stored_references():
    old=json.loads((OLD/'stored_review.json').read_text(encoding='utf-8'));out=[]
    for row in old['rows']:
        if row['arm']!='rate_mixture_v216':continue
        folder=OLD/'shards'/f"{row['family']}_s{row['seed']:02d}"
        native=json.loads((folder/'native_result.json').read_text(encoding='utf-8'))
        assert hashlib.sha256((folder/'raw.jsonl.gz').read_bytes()).hexdigest()==native['raw_sha256']
        tm=[];em={};counts={}
        with gzip.open(folder/'raw.jsonl.gz','rt',encoding='utf-8') as f:
            for line in f:
                r=json.loads(line)
                if r['kind']=='start':spec=r['source_spec']
                if r['kind'] not in ['train_episode','eval_episode'] or r['arm']!='rate_mixture_v216':continue
                ck=r.get('checkpoint',r['slot']);pr=truth(row['family'],spec,ck,r['public']['context']);m=measure(r['offer'],r['public'],pr)
                if r['kind']=='train_episode':tm.append(m)
                else:em.setdefault(ck,[]).append(m);counts[ck]=counts.get(ck,0)+r['public']['outcome']
        assert len(tm)==256 and all(counts[e['checkpoint']]==e['successes'] for e in row['evaluations'])
        out.append({**row,'train_metrics':means(tm),'eval_metrics':{str(k):means(v) for k,v in em.items()},'data_origin':'stored_V216_no_execution'})
    assert len(out)==80
    return out


def primary(row):
    points=[144,160,192,256] if row['family']=='selective_return' else [16,64,128,256]
    return statistics.mean(e['successes']/128 for e in row['evaluations'] if e['checkpoint'] in points)


def main():
    contract=json.loads((HERE/'contract.json').read_text(encoding='utf-8'))
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in contract['input_sha256'].items())
    names=[f'{f}_s{s:02d}' for f in FAMILIES for s in range(16)]
    with ProcessPoolExecutor(max_workers=4) as pool:results=list(pool.map(review_shard,names))
    rows=[row for r in results for row in r['rows']]+stored_references();table=[];diffs=[]
    for fi,family in enumerate(FAMILIES):
        returning=family=='selective_return'
        points=[144,160,192,256] if returning else [16,64,128,256]
        for arm in ARMS:
            sub=sorted([r for r in rows if r['family']==family and r['arm']==arm],key=lambda r:r['seed']);assert len(sub)==16
            cks=[e['checkpoint'] for e in sub[0]['evaluations']]
            curve=[statistics.mean(r['evaluations'][i]['successes']/128 for r in sub) for i in range(len(cks))]
            row={'family':family,'arm':arm,'data_origin':sub[0]['data_origin'],'seeds':16,
                 'train_success_rate':statistics.mean(r['training_successes']/256 for r in sub),
                 'first64_success_rate':statistics.mean(r['first64_successes']/64 for r in sub),
                 'checkpoints':cks,'eval_curve':curve,'primary_eval_mean':statistics.mean(primary(r) for r in sub),
                 'eval_final':curve[-1],'return_first16_success_rate':statistics.mean(r['return_first16_successes']/16 for r in sub) if returning else None,
                 'late_extra_wrong_rate':statistics.mean(r['eval_metrics'][str(k)]['extra_wrong'] for r in sub for k in [64,128,256]),
                 'cpu_seconds_per_run':statistics.mean(r['cpu_seconds'] for r in sub),
                 'buffer_bytes_per_run':statistics.mean(r['buffer_bytes'] for r in sub)}
            for m in ['log_loss','brier','kernel_mse']:
                row['train_'+m]=statistics.mean(r['train_metrics'][m] for r in sub)
                row['eval_'+m]=statistics.mean(r['eval_metrics'][str(k)][m] for r in sub for k in points)
            table.append(row)
        for ai,arm in enumerate(ARMS[1:]):
            ref=sorted([r for r in rows if r['family']==family and r['arm']==ARMS[0]],key=lambda r:r['seed'])
            cur=sorted([r for r in rows if r['family']==family and r['arm']==arm],key=lambda r:r['seed'])
            values=[primary(a)-primary(b) for a,b in zip(cur,ref)]
            rng=random.Random(217900+fi*100+ai);boot=sorted(statistics.mean(rng.choices(values,k=16)) for _ in range(2000))
            diffs.append({'family':family,'arm':arm,'reference':ARMS[0],'mean_primary_difference':statistics.mean(values),
                          'paired_seed_differences':values,'exploratory_bootstrap_95':[boot[49],boot[1949]],
                          'mean_training_difference':statistics.mean((a['training_successes']-b['training_successes'])/256 for a,b in zip(cur,ref)),
                          'return_first16_difference':statistics.mean((a['return_first16_successes']-b['return_first16_successes'])/16 for a,b in zip(cur,ref)) if returning else None})
    out={'schema':'v217-independent-stored-review','new_shards':80,'new_arm_runs':240,'stored_reference_runs':80,
         'new_interactions':sum(r['interactions'] for r in results),'training_interactions':61440,'evaluation_interactions':172032,
         'recorded_history_imports':sum(r['history_imports'] for r in results),'unique_existing_history_events':16384,'arm_history_exposure':61440,
         'new_history_interactions':0,'records':sum(r['records'] for r in results),'max_formula_error':max(r['max_formula_error'] for r in results),
         'old_native_reruns':0,'new_interactions_in_review':0,'torch_imports':0,'gradient_updates':0,'table':table,'differences':diffs,'rows':rows}
    assert out['new_interactions']==233472 and out['records']==255936 and out['recorded_history_imports']==20480
    with(HERE/'stored_review.json').open('x',encoding='utf-8') as f:json.dump(out,f,indent=2)
    with(HERE/'summary.csv').open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(table[0]));w.writeheader();w.writerows(table)
    print(json.dumps({k:out[k] for k in ['new_shards','new_arm_runs','new_interactions','records','max_formula_error']}))

if __name__=='__main__':main()
