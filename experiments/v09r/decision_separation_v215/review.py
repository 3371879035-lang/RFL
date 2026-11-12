"""Independent stored arithmetic; no torch, network, or environment execution."""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import csv
import gzip
import hashlib
import json
import math
import random
import statistics
import sys

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
PREVIOUS=ROOT/'experiments/v09r/applicability_v214'
sys.path.insert(0,str(PREVIOUS))
from scalar import Predictor,Model

FAMILIES=['stable_novel','changed_novel','selective_change','noise']
MODE='decision_separated_v215'


def scene_for(spec,phase,slot,checkpoint=0):
    code=0 if spec['family'] in FAMILIES[:2] else FAMILIES.index(spec['family'])
    number=((code*100+spec['seed'])*3+{'history':0,'train':1,'eval':2}[phase])*1000000+checkpoint*1000+slot
    rng=random.Random(214100000000+number);x=[rng.randrange(2) for _ in range(3)]
    if spec['family'] in FAMILIES[:2]:x[spec['condition']]=0 if phase=='history' else 1
    return {'context':x,'action_u':rng.random(),'outcome_u':rng.random()}


def epsilon_policy(p):
    best=max(range(2),key=lambda a:p[a][1])
    return [.9 if a==best else .1 for a in range(2)]


def review_shard(name):
    folder=HERE/'shards'/name;native=json.loads((folder/'native_result.json').read_text(encoding='utf-8'))
    assert hashlib.sha256((folder/'raw.jsonl.gz').read_bytes()).hexdigest()==native['raw_sha256']
    h=Predictor(0.);t=Predictor(.05);imported=[];record_count=events=0
    train=[];eval_values=[];evals=[];losses=[];maximum=0.;diagnostics={};initial=[];last_id=255
    seen={};model=None;minimum_predicted_gain=0.
    with gzip.open(folder/'raw.jsonl.gz','rt',encoding='utf-8') as stream:
        for line in stream:
            r=json.loads(line);record_count+=1;kind=r['kind']
            assert json.dumps(r,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n'==line
            if kind=='start':
                spec=r['spec'];assert r['mode']==MODE
                assert [spec['payload'],spec['condition'],spec['nuisance']]==random.Random(2144000+spec['seed']).sample(range(3),3)
                source=ROOT/r['history_source'];assert hashlib.sha256(source.read_bytes()).hexdigest()==r['history_sha256']
                source_facts={}
                with gzip.open(source,'rt',encoding='utf-8') as old:
                    for i,oldline in enumerate(old,1):
                        record=json.loads(oldline)
                        if record['kind']=='history':source_facts[i]=record['public']
                        elif record['kind']=='history_ready':break
                assert len(source_facts)==256
            elif kind=='history_import':
                d=r['public'];assert d==source_facts[r['source_record']] and d['id']==r['source_slot']==len(imported)
                x=d['context'];h.observe(x,d['action'],d['outcome']);t.observe(x,d['action'],d['outcome'])
                imported.append(d);seen[tuple(x)]=seen.get(tuple(x),0)+1
            elif kind in ['train_episode','eval_episode']:
                if model is None:
                    assert len(imported)==256;model=Model('conditional_gate',h,t)
                phase='train' if kind=='train_episode' else 'eval';checkpoint=r.get('checkpoint',0)
                scene=scene_for(spec,phase,r['slot'],checkpoint);assert scene==r['scene']
                d=r['public'];x=scene['context'];assert d['context']==x and d['id']==last_id+1 and d['policy_id']==MODE
                last_id=d['id'];events+=1;wire=r['offer'];p,lam,hp,fp,cache=model.predict(x)
                for got,expected in [(wire['prediction'],p),(wire['history_prediction'],hp),(wire['fresh_prediction'],fp)]:
                    for a,b in zip(got,expected):
                        assert abs(sum(a)-1)<2e-12
                        for v,w in zip(a,b):maximum=max(maximum,abs(v-w));assert abs(v-w)<3e-12
                assert abs(wire['history_share']-lam)<3e-12
                maximum=max(maximum,abs(wire['history_share']-lam))
                assert wire['history_share_semantics']=='predictive_weight_not_execution_fraction'
                scores=[a[1] for a in wire['prediction']];assert wire['decision_scores']==scores
                assert abs(wire['estimated_margin']-abs(scores[0]-scores[1]))<1e-14
                mu=epsilon_policy(wire['prediction']);assert wire['behavior']==mu
                ph=epsilon_policy(wire['history_prediction']);pf=epsilon_policy(wire['fresh_prediction'])
                old=[wire['history_share']*a+(1-wire['history_share'])*b for a,b in zip(ph,pf)]
                for a,b in zip(old,wire['source_mixture_behavior_not_executed']):assert abs(a-b)<1e-14
                predicted_gain=sum((a-b)*q for a,b,q in zip(mu,old,scores))
                assert predicted_gain>=-1e-14;minimum_predicted_gain=min(minimum_predicted_gain,predicted_gain)
                a=int(scene['action_u']<mu[1]);assert a==d['action'] and abs(d['propensity']-mu[a])<1e-14
                desired=x[spec['payload']]
                if spec['family']=='changed_novel':desired^=1
                elif spec['family']=='selective_change':desired^=x[spec['condition']]
                truth=[.5 if spec['family']=='noise' else .9 if j==desired else .1 for j in range(2)]
                assert d['outcome']==int(scene['outcome_u']<truth[a])
                if phase=='train':
                    assert r['slot']==len(train) and wire['id']==d['id'] and wire['context']==x
                    assert wire['previous_full_context_observations']==seen.get(tuple(x),0)
                    losses.append(-math.log(wire['prediction'][a][d['outcome']]))
                    model.observe(x,a,d['outcome'],cache);train.append(d['outcome']);seen[tuple(x)]=seen.get(tuple(x),0)+1
                else:
                    assert r['slot']==len(eval_values);eval_values.append(d['outcome'])
                    jf=sum(a*b for a,b in zip(pf,truth));jn=sum(a*b for a,b in zip(mu,truth));jo=sum(a*b for a,b in zip(old,truth))
                    diagnostics.setdefault(checkpoint,[]).append({'condition':x[spec['condition']],
                        'history_predictive_weight':lam,'J_new':jn,'J_current_branch':jf,'J_old_mixture_same_state':jo,
                        'current_minus_new':jf-jn,'new_minus_old_mixture_same_state':jn-jo})
                    if checkpoint==0:initial.append({'context':x,'prediction':wire['prediction'],'behavior':mu,'history_share':wire['history_share']})
            elif kind=='eval_end':
                assert r['checkpoint']==len(train) and r['successes']==sum(eval_values) and len(eval_values)==128
                assert r['state_unchanged'] is True;evals.append({k:v for k,v in r.items() if k!='kind'});eval_values=[]
            elif kind=='arm_end':
                row={k:v for k,v in r.items() if k!='kind'};assert row==native['row']
                assert row['training_successes']==sum(train) and row['first16_successes']==sum(train[:16]) and row['first64_successes']==sum(train[:64])
                assert row['evaluations']==evals and row['archive_facts']==512 and row['new_history_interactions']==0
            elif kind=='end':
                assert r['new_actual_interactions']==r['steps']==896 and r['recorded_history_facts_imported']==256
                assert r['gradient_updates']==0 and r['input_unchanged'] and r['torch_rng_unchanged']
            else:raise AssertionError(kind)
    assert record_count==native['records'] and events==native['new_actual_interactions']==896 and len(train)==256 and len(evals)==5
    reduced={}
    for ck,values in diagnostics.items():
        reduced[str(ck)]={k:statistics.mean(v[k] for v in values) for k in values[0] if k!='condition'}
        reduced[str(ck)]['history_weight_by_condition']={str(c):statistics.mean(v['history_predictive_weight'] for v in values if v['condition']==c)
                                                       if any(v['condition']==c for v in values) else None for c in [0,1]}
    result={'row':{**row,'train_log_loss':statistics.mean(losses),'diagnostics':reduced},
            'records':record_count,'new_actual_interactions':events,'recorded_history_imports':len(imported),
            'max_formula_error':maximum,'minimum_predicted_value_gain':minimum_predicted_gain,
            'initial_visible_predictions':initial,'raw_sha256':native['raw_sha256']}
    with(folder/'stored_review.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    return result


def main():
    contract=json.loads((HERE/'contract.json').read_text(encoding='utf-8'))
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==v for p,v in contract['input_sha256'].items())
    names=[f'{family}_s{seed:02d}' for family in FAMILIES for seed in range(16)]
    with ProcessPoolExecutor(max_workers=4) as pool:reviews=list(pool.map(review_shard,names))
    keyed={(r['row']['family'],r['row']['seed']):r for r in reviews}
    for seed in range(16):assert keyed[('stable_novel',seed)]['initial_visible_predictions']==keyed[('changed_novel',seed)]['initial_visible_predictions']
    rows=[r['row'] for r in reviews];old=json.loads((PREVIOUS/'stored_review.json').read_text(encoding='utf-8'))
    table=[];differences=[]
    for fi,family in enumerate(FAMILIES):
        sub=[r for r in rows if r['family']==family]
        for r in old['table']:
            if r['family']==family:table.append({**r,'data_origin':'stored_V214_no_rerun'})
        means=[statistics.mean(r['evaluations'][i]['successes']/128 for r in sub) for i in range(5)]
        table.append({'family':family,'arm':MODE,'seeds':16,'training_success_rate':statistics.mean(r['training_successes']/256 for r in sub),
                      'first64_success_rate':statistics.mean(r['first64_successes']/64 for r in sub),
                      'eval_mean_after_learning':statistics.mean(means[1:]),'eval_final':means[-1],'eval_curve':means,
                      'train_log_loss':statistics.mean(r['train_log_loss'] for r in sub),
                      'cpu_seconds_per_run':statistics.mean(r['cpu_seconds'] for r in sub),
                      'buffer_bytes_per_run':statistics.mean(r['buffer_bytes'] for r in sub),'data_origin':'new_V215_execution'})
        for ai,arm in enumerate(['conditional_gate','global_gate','temporal_v210','fresh_only','pooled_history']):
            vals=[];trainvals=[]
            for seed in range(16):
                a=keyed[(family,seed)]['row'];b=next(r for r in old['rows'] if (r['family'],r['seed'],r['arm'])==(family,seed,arm))
                assert a['training_interactions']==b['training_interactions']==256 and a['eval_interactions']==b['eval_interactions']==640
                vals.append(statistics.mean((aa['successes']-bb['successes'])/128 for aa,bb in zip(a['evaluations'][1:],b['evaluations'][1:])))
                trainvals.append((a['training_successes']-b['training_successes'])/256)
            rng=random.Random(215900+fi*100+ai);boot=sorted(statistics.mean(rng.choices(vals,k=16)) for _ in range(2000))
            differences.append({'family':family,'reference':arm,'mean_eval_difference':statistics.mean(vals),
                                'paired_seed_differences':vals,'exploratory_bootstrap_95':[boot[49],boot[1949]],
                                'mean_training_difference':statistics.mean(trainvals)})
    result={'schema':'v215-independent-stored-review','new_shards':64,'new_actual_interactions':sum(r['new_actual_interactions'] for r in reviews),
            'recorded_history_imports':sum(r['recorded_history_imports'] for r in reviews),'new_history_interactions':0,
            'training_interactions':16384,'evaluation_interactions':40960,'steps':57344,
            'records':sum(r['records'] for r in reviews),'max_formula_error':max(r['max_formula_error'] for r in reviews),
            'indistinguishable_pairs_checked':16,'old_native_reruns':0,'new_environment_runs_in_review':0,'torch_imports':0,
            'diagnostic_scope':'Known synthetic kernel, evaluation-only arithmetic. Own current branch and old-policy-on-new-state are hypothetical distributions, not additional executed counterfactual rollouts.',
            'table':table,'differences':differences,'rows':rows}
    with(HERE/'stored_review.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    with(HERE/'summary.csv').open('x',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(table[0]));writer.writeheader();writer.writerows(table)
    print(json.dumps({k:result[k] for k in ['new_shards','new_actual_interactions','recorded_history_imports','records','max_formula_error']}))


if __name__=='__main__':main()
