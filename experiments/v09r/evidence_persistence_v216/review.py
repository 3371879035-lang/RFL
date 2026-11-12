from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import csv,gzip,hashlib,json,math,random,statistics
from scalar_v216 import Predictor,make_model

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];OLD=ROOT/'experiments/v09r/decision_separation_v215'
FAMILIES=['stable_novel','changed_novel','selective_change','noise','selective_return']


def scene_for(spec,phase,slot,checkpoint=0):
    family=spec['family'];code=0 if family in FAMILIES[:2] else FAMILIES.index(family)
    num=((code*100+spec['seed'])*3+{'history':0,'train':1,'eval':2}[phase])*1000000+checkpoint*1000+slot
    rng=random.Random(214100000000+num);x=[rng.randrange(2) for _ in range(3)]
    if family in FAMILIES[:2]:x[spec['condition']]=0 if phase=='history' else 1
    return {'context':x,'action_u':rng.random(),'outcome_u':rng.random()}


def diagnostic(family,spec,checkpoint,x,wire):
    desired=x[spec['payload']]
    if family=='changed_novel':desired^=1
    elif family=='selective_change' or (family=='selective_return' and checkpoint<128):desired^=x[spec['condition']]
    truth=[.5 if family=='noise' else .9 if a==desired else .1 for a in range(2)]
    pb=max(range(2),key=lambda a:wire['prediction'][a][1]);fb=max(range(2),key=lambda a:wire['fresh_prediction'][a][1])
    optimal={a for a in range(2) if truth[a]==max(truth)}
    return {'extra_wrong':int(fb in optimal and pb not in optimal),'current_wrong':int(fb not in optimal),
            'J_policy':sum(a*b for a,b in zip(wire['behavior'],truth)),
            'J_current':sum((.9 if a==fb else .1)*truth[a] for a in range(2)),
            'history_weight':wire['history_share'],'mean_reopening_rate':wire.get('mean_reopening_rate',.02),
            'rates':wire.get('rate_weights',[1.]),'condition':x[spec['condition']]}


def reduce_diagnostics(byck):
    reduced={}
    for ck,values in byck.items():
        r={k:statistics.mean(v[k] for v in values) for k in ['extra_wrong','current_wrong','J_policy','J_current','history_weight','mean_reopening_rate']}
        r['rate_weights']=[statistics.mean(v['rates'][i] for v in values) for i in range(len(values[0]['rates']))]
        r['by_condition']={str(c):{k:statistics.mean(v[k] for v in values if v['condition']==c) for k in ['extra_wrong','history_weight','mean_reopening_rate']}
                           if any(v['condition']==c for v in values) else None for c in [0,1]}
        reduced[str(ck)]=r
    return reduced


def review_shard(name):
    folder=HERE/'shards'/name;native=json.loads((folder/'native_result.json').read_text(encoding='utf-8'))
    assert hashlib.sha256((folder/'raw.jsonl.gz').read_bytes()).hexdigest()==native['raw_sha256']
    h=Predictor(0.);t=Predictor(.05);imports=[];records=events=0;rows=[];maximum=0.
    with gzip.open(folder/'raw.jsonl.gz','rt',encoding='utf-8') as stream:
        for line in stream:
            r=json.loads(line);records+=1;kind=r['kind']
            assert json.dumps(r,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n'==line
            if kind=='start':
                family=r['family'];spec=r['source_spec'];seed=r['seed'];checkpoints=r['checkpoints']
                assert [spec['payload'],spec['condition'],spec['nuisance']]==random.Random(2144000+seed).sample(range(3),3)
                assert r['return_after']==(128 if family=='selective_return' else None)
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
                arm=r['arm'];mode=r['mode'];rates=r['rates'];model=make_model(arm,h,t);last_id=255;train=[];ev=[];evals=[];loss=[];diags={}
                assert len(imports)==256
                seen={}
                for d in imports:seen[tuple(d['context'])]=seen.get(tuple(d['context']),0)+1
            elif kind in ['train_episode','eval_episode']:
                assert r['arm']==arm;phase='train' if kind=='train_episode' else 'eval';checkpoint=r.get('checkpoint',0)
                scene=scene_for(spec,phase,r['slot'],checkpoint);assert scene==r['scene']
                d=r['public'];x=scene['context'];wire=r['offer'];assert d['context']==x and d['id']==last_id+1 and d['policy_id']==mode
                last_id=d['id'];events+=1;p,lam,hp,fp,cache=model.predict(x)
                for got,expected in [(wire['prediction'],p),(wire['history_prediction'],hp),(wire['fresh_prediction'],fp)]:
                    for a,b in zip(got,expected):
                        assert abs(sum(a)-1)<3e-12
                        for v,w in zip(a,b):maximum=max(maximum,abs(v-w));assert abs(v-w)<4e-12
                assert abs(wire['history_share']-lam)<4e-12
                rr=[1.] if arm=='fixed_v215' else cache[1][-1]
                assert rates==wire['rate_hypotheses'] and len(rr)==len(rates)
                for a,b in zip(rr,wire['rate_weights']):maximum=max(maximum,abs(a-b));assert abs(a-b)<4e-12
                assert abs(wire['mean_reopening_rate']-sum(a*b for a,b in zip(rates,rr)))<4e-12
                assert wire['rate_semantics']=='predictive_persistence_not_environment_change_probability'
                scores=[a[1] for a in wire['prediction']];best=max(range(2),key=lambda a:scores[a]);mu=[.9 if a==best else .1 for a in range(2)]
                assert wire['decision_scores']==scores and wire['behavior']==mu and abs(wire['estimated_margin']-abs(scores[0]-scores[1]))<1e-14
                a=int(scene['action_u']<mu[1]);assert d['action']==a and abs(d['propensity']-mu[a])<1e-14
                index=r['slot'] if phase=='train' else checkpoint;desired=x[spec['payload']]
                if family=='changed_novel':desired^=1
                elif family=='selective_change' or (family=='selective_return' and index<128):desired^=x[spec['condition']]
                pr=.5 if family=='noise' else .9 if a==desired else .1
                assert d['outcome']==int(scene['outcome_u']<pr)
                if phase=='train':
                    assert r['slot']==len(train) and wire['id']==d['id'] and wire['context']==x
                    assert wire['previous_full_context_observations']==seen.get(tuple(x),0)
                    loss.append(-math.log(wire['prediction'][a][d['outcome']]))
                    model.observe(x,a,d['outcome'],cache);train.append(d['outcome']);seen[tuple(x)]=seen.get(tuple(x),0)+1
                else:
                    assert r['slot']==len(ev);ev.append(d['outcome']);diags.setdefault(checkpoint,[]).append(diagnostic(family,spec,checkpoint,x,wire))
            elif kind=='eval_end':
                assert r['arm']==arm and r['checkpoint']==len(train) and len(ev)==128 and r['successes']==sum(ev) and r['state_unchanged']
                evals.append({k:v for k,v in r.items() if k not in ['kind','arm']});ev=[]
            elif kind=='arm_end':
                row={k:v for k,v in r.items() if k!='kind'};assert row in native['rows'] and row['evaluations']==evals
                assert len(train)==256 and row['training_successes']==sum(train) and row['first16_successes']==sum(train[:16]) and row['first64_successes']==sum(train[:64])
                assert row['second_half_successes']==sum(train[128:])
                if family=='selective_return':assert row['return_first16_successes']==sum(train[128:144])
                assert row['parameters_unchanged'] and row['history_unchanged'] and row['archive_facts']==512
                rows.append({**row,'train_log_loss':statistics.mean(loss),'diagnostics':reduce_diagnostics(diags),'data_origin':'new_V216_execution'})
            elif kind=='end':
                assert events==r['new_actual_interactions']==r['steps'] and r['history_imports']==256 and r['new_history_interactions']==0
                assert r['gradient_updates']==0 and r['input_unchanged'] and r['torch_rng_unchanged']
            else:raise AssertionError(kind)
    assert events==native['new_actual_interactions'] and records==native['records'] and len(rows)==(3 if family=='selective_return' else 2)
    result={'rows':rows,'records':records,'interactions':events,'max_formula_error':maximum,'history_imports':len(imports)}
    with(folder/'stored_review.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    return result


def existing_fixed_rows():
    old=json.loads((OLD/'stored_review.json').read_text(encoding='utf-8'));out=[]
    for row in old['rows']:
        family=row['family'];seed=row['seed'];diags={};counts={}
        path=OLD/'shards'/f'{family}_s{seed:02d}'/'raw.jsonl.gz'
        with gzip.open(path,'rt',encoding='utf-8') as f:
            for line in f:
                r=json.loads(line)
                if r['kind']=='start':spec=r['spec']
                elif r['kind']=='eval_episode':
                    ck=r['checkpoint'];diags.setdefault(ck,[]).append(diagnostic(family,spec,ck,r['public']['context'],r['offer']))
                    counts[ck]=counts.get(ck,0)+r['public']['outcome']
        assert all(counts[e['checkpoint']]==e['successes'] for e in row['evaluations'])
        out.append({**row,'arm':'fixed_v215','evaluation_interactions':row['eval_interactions'],
                    'return_first16_successes':None,'diagnostics':reduce_diagnostics(diags),'data_origin':'stored_V215_no_rerun'})
    return out


def row_metric(row,returning=False):
    selected=[e['successes']/128 for e in row['evaluations'] if e['checkpoint'] in ([144,160,192,256] if returning else [16,64,128,256])]
    assert len(selected)==4;return statistics.mean(selected)


def main():
    contract=json.loads((HERE/'contract.json').read_text(encoding='utf-8'))
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in contract['input_sha256'].items())
    names=[f'{f}_s{s:02d}' for f in FAMILIES for s in range(16)]
    with ProcessPoolExecutor(max_workers=4) as pool:results=list(pool.map(review_shard,names))
    rows=[row for r in results for row in r['rows']]+existing_fixed_rows();table=[];diffs=[]
    for fi,family in enumerate(FAMILIES):
        returning=family=='selective_return'
        for arm in ['fixed_v215','no_reopening_v216','rate_mixture_v216']:
            sub=[r for r in rows if r['family']==family and r['arm']==arm];assert len(sub)==16
            points=[e['checkpoint'] for e in sub[0]['evaluations']]
            curve=[statistics.mean(r['evaluations'][i]['successes']/128 for r in sub) for i in range(len(points))]
            table.append({'family':family,'arm':arm,'data_origin':sub[0]['data_origin'],'seeds':16,
                          'train_success_rate':statistics.mean(r['training_successes']/256 for r in sub),
                          'first64_success_rate':statistics.mean(r['first64_successes']/64 for r in sub),
                          'checkpoints':points,'eval_curve':curve,'primary_eval_mean':statistics.mean(row_metric(r,returning) for r in sub),
                          'eval_final':curve[-1],'return_first16_success_rate':statistics.mean(r['return_first16_successes']/16 for r in sub) if returning else None,
                          'late_extra_wrong_rate':statistics.mean(statistics.mean(r['diagnostics'][str(k)]['extra_wrong'] for k in [64,128,256]) for r in sub),
                          'train_log_loss':statistics.mean(r['train_log_loss'] for r in sub),
                          'cpu_seconds_per_run':statistics.mean(r['cpu_seconds'] for r in sub),'buffer_bytes_per_run':statistics.mean(r['buffer_bytes'] for r in sub)})
        for oi,other in enumerate(['fixed_v215','no_reopening_v216']):
            values=[];training=[];early=[]
            for seed in range(16):
                a=next(r for r in rows if (r['family'],r['seed'],r['arm'])==(family,seed,'rate_mixture_v216'))
                b=next(r for r in rows if (r['family'],r['seed'],r['arm'])==(family,seed,other))
                assert a['training_interactions']==b['training_interactions']==256 and a['evaluation_interactions']==b['evaluation_interactions']
                values.append(row_metric(a,returning)-row_metric(b,returning));training.append((a['training_successes']-b['training_successes'])/256)
                if returning:early.append((a['return_first16_successes']-b['return_first16_successes'])/16)
            rng=random.Random(216900+fi*100+oi);boot=sorted(statistics.mean(rng.choices(values,k=16)) for _ in range(2000))
            diffs.append({'family':family,'reference':other,'mean_primary_difference':statistics.mean(values),
                          'paired_seed_differences':values,'exploratory_bootstrap_95':[boot[49],boot[1949]],
                          'mean_training_difference':statistics.mean(training),'return_first16_difference':statistics.mean(early) if early else None})
    output={'schema':'v216-independent-stored-review','new_shards':80,'new_arm_runs':176,'stored_reference_runs':64,
            'new_interactions':sum(r['interactions'] for r in results),'training_interactions':45056,'evaluation_interactions':131072,
            'recorded_history_imports':sum(r['history_imports'] for r in results),'unique_prior_history_facts':16384,
            'new_history_interactions':0,'records':sum(r['records'] for r in results),'max_formula_error':max(r['max_formula_error'] for r in results),
            'old_native_reruns':0,'new_interactions_in_review':0,'torch_imports':0,'table':table,'differences':diffs,'rows':rows,
            'diagnostic_scope':'Known synthetic kernel only on evaluation side; current-correct/final-wrong is a same-state diagnostic, not an executed counterfactual or a causal attribution probability.'}
    assert output['new_interactions']==176128 and output['recorded_history_imports']==20480
    with(HERE/'stored_review.json').open('x',encoding='utf-8') as f:json.dump(output,f,indent=2)
    with(HERE/'summary.csv').open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(table[0]));w.writeheader();w.writerows(table)
    print(json.dumps({k:output[k] for k in ['new_shards','new_arm_runs','new_interactions','recorded_history_imports','records','max_formula_error']}))


if __name__=='__main__':main()
