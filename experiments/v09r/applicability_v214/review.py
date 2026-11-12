"""Stdlib stored review: independent formula replay and real observation accounting."""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import csv
import gzip
import hashlib
import itertools
import json
import math
import random
import statistics

from scalar import Model,Predictor

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
FAMILIES=('stable_novel','changed_novel','selective_change','noise')
ARMS=('pooled_history','fresh_only','temporal_v210','global_gate','conditional_gate')


def expected_scene(spec,phase,slot,checkpoint):
    family=spec['family'];code=0 if family in FAMILIES[:2] else FAMILIES.index(family)
    ph={'history':0,'train':1,'eval':2}[phase]
    number=((code*100+spec['seed'])*3+ph)*1000000+checkpoint*1000+slot
    rng=random.Random(214100000000+number);x=[rng.randrange(2) for _ in range(3)]
    if family in FAMILIES[:2]:x[spec['condition']]=0 if phase=='history' else 1
    return x,rng.random(),rng.random()


def action_probs(prediction):
    a=max(range(2),key=lambda j:prediction[j][1])
    return [.9 if i==a else .1 for i in range(2)]


def review_shard(name):
    folder=HERE/'shards'/name
    native=json.loads((folder/'native_result.json').read_text())
    assert hashlib.sha256((folder/'raw.jsonl.gz').read_bytes()).hexdigest()==native['raw_sha256']
    historical=Predictor(0.);temporal=Predictor(.05);nrecords=events=0;history=[]
    rows=[];first={};max_error=0.;source_ties=0
    with gzip.open(folder/'raw.jsonl.gz','rt',encoding='utf-8') as stream:
        for line in stream:
            r=json.loads(line);nrecords+=1
            assert json.dumps(r,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n'==line
            kind=r['kind']
            if kind=='start':
                spec=r['spec'];perm=random.Random(2144000+spec['seed']).sample(range(3),3)
                assert [spec['payload'],spec['condition'],spec['nuisance']]==perm
                assert r['history_is_real'] is True
            elif kind=='history_ready':
                assert len(history)==historical.n==temporal.n==256 and r['actual_source_interactions']==256
            elif kind=='arm_start':
                arm=r['arm'];model=Model(arm,historical,temporal);last_id=255;train=[];evals=[]
                active_eval=None;eval_values=[];seen={}
                for f in history:seen[tuple(f['context'])]=seen.get(tuple(f['context']),0)+1
                losses=[];briers=[];shares={0:[],1:[]}
                eval_losses={};eval_shares={};first[arm]=[]
                assert r['archive_facts']==256
            elif kind in ('history','train_episode','eval_episode'):
                events+=1
                phase='history' if kind=='history' else 'train' if kind=='train_episode' else 'eval'
                checkpoint=r.get('checkpoint',0)
                x,au,ou=expected_scene(spec,phase,r['slot'],checkpoint)
                assert r['scene']=={'context':x,'action_u':au,'outcome_u':ou}
                f=r['public'];assert f['context']==x
                if phase=='history':
                    assert f['id']==len(history) and f['policy_id']=='history-uniform';behavior=[.5,.5]
                else:
                    assert r['arm']==arm and f['id']==last_id+1 and f['policy_id']==arm
                    last_id=f['id'];wire=r['offer'];pred,lam,hp,fp,cache=model.predict(x)
                    for name_,got,expected in [('prediction',wire['prediction'],pred),('fresh',wire['fresh_prediction'],fp)]:
                        for ga,ea in zip(got,expected):
                            assert abs(sum(ga)-1)<2e-12
                            for gv,ev in zip(ga,ea):max_error=max(max_error,abs(gv-ev));assert abs(gv-ev)<3e-12,(name_,gv,ev)
                    if lam is None:
                        assert wire['history_share'] is None and wire['history_prediction'] is None
                        behavior=action_probs(wire['prediction'])
                    else:
                        assert abs(wire['history_share']-lam)<3e-12
                        max_error=max(max_error,abs(wire['history_share']-lam))
                        for ga,ea in zip(wire['history_prediction'],hp):
                            for gv,ev in zip(ga,ea):assert abs(gv-ev)<3e-12
                        ph=action_probs(wire['history_prediction']);pf=action_probs(wire['fresh_prediction'])
                        behavior=[wire['history_share']*a+(1-wire['history_share'])*b for a,b in zip(ph,pf)]
                        source_ties+=int(abs(wire['fresh_prediction'][0][1]-wire['fresh_prediction'][1][1])<1e-12)
                    for a,b in zip(wire['behavior'],behavior):assert abs(a-b)<1e-14
                    if phase=='train':
                        assert wire['id']==f['id'] and wire['context']==x
                        assert wire['previous_full_context_observations']==seen.get(tuple(x),0)
                    elif checkpoint==0:
                        first[arm].append({'context':x,'prediction':wire['prediction'],'behavior':wire['behavior'],
                                           'history_share':wire['history_share']})
                action=int(au<behavior[1]);assert f['action']==action and abs(f['propensity']-behavior[action])<1e-14
                desired=x[spec['payload']]
                if phase!='history':
                    if spec['family']=='changed_novel':desired^=1
                    elif spec['family']=='selective_change':desired^=x[spec['condition']]
                p=.5 if spec['family']=='noise' else .9 if action==desired else .1
                assert f['outcome']==int(ou<p)
                if phase=='history':
                    historical.observe(x,action,f['outcome']);temporal.observe(x,action,f['outcome']);history.append(f)
                elif phase=='train':
                    assert r['slot']==len(train)
                    losses.append(-math.log(wire['prediction'][action][f['outcome']]))
                    briers.append((wire['prediction'][action][1]-f['outcome'])**2)
                    model.observe(x,action,f['outcome'],cache);train.append(f['outcome'])
                    seen[tuple(x)]=seen.get(tuple(x),0)+1
                else:
                    eval_losses.setdefault(checkpoint,[]).append(-math.log(wire['prediction'][action][f['outcome']]))
                    eval_shares.setdefault(checkpoint,{0:[],1:[]})
                    if lam is not None:eval_shares[checkpoint][x[spec['condition']]].append(wire['history_share'])
                    assert r['slot']==len(eval_values)
                    eval_values.append(f['outcome'])
            elif kind=='eval_end':
                assert r['checkpoint']==len(train) and len(eval_values)==128
                assert r['successes']==sum(eval_values) and r['state_unchanged'] is True
                evals.append({k:v for k,v in r.items() if k not in ['kind','arm']});eval_values=[]
            elif kind=='arm_end':
                assert len(train)==256 and r['training_successes']==sum(train)
                assert r['first16_successes']==sum(train[:16]) and r['first64_successes']==sum(train[:64])
                assert r['evaluations']==evals and r['archive_facts']==512
                rawrow={k:v for k,v in r.items() if k!='kind'}
                assert rawrow in native['rows']
                row={**rawrow,'family':spec['family'],'seed':spec['seed'],
                     'train_log_loss':statistics.mean(losses),'train_brier':statistics.mean(briers),
                     'eval_log_loss':{str(k):statistics.mean(v) for k,v in eval_losses.items()},
                     'history_share_by_checkpoint_condition':{str(k):{str(c):statistics.mean(v) if v else None for c,v in vv.items()} for k,vv in eval_shares.items()}}
                rows.append(row)
            elif kind=='end':
                assert r['interactions']==r['steps']==4736 and r['training_interactions']==1280 and r['evaluation_interactions']==3200
            else:raise AssertionError(kind)
    assert events==native['actual_interactions']==4736 and nrecords==native['records'] and len(rows)==5
    result={'family':spec['family'],'seed':spec['seed'],'records':nrecords,'interactions':events,
            'max_formula_error':max_error,'near_tied_fresh_predictions':source_ties,'rows':rows,
            'first_visible_predictions':first,'raw_sha256':native['raw_sha256']}
    with(folder/'stored_review.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    return result


def main():
    contract=json.loads((HERE/'contract.json').read_text(encoding='utf-8'))
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==v for p,v in contract['input_sha256'].items())
    names=[f'{family}_s{seed:02d}' for family in FAMILIES for seed in range(16)]
    with ProcessPoolExecutor(max_workers=4) as pool:results=list(pool.map(review_shard,names))
    keyed={(r['family'],r['seed']):r for r in results}
    for seed in range(16):
        assert keyed[('stable_novel',seed)]['first_visible_predictions']==keyed[('changed_novel',seed)]['first_visible_predictions']
    rows=[row for r in results for row in r['rows']]
    table=[]
    for family in FAMILIES:
        for arm in ARMS:
            subset=[r for r in rows if (r['family'],r['arm'])==(family,arm)]
            means=[statistics.mean(r['evaluations'][i]['successes']/128 for r in subset) for i in range(5)]
            table.append({'family':family,'arm':arm,'seeds':16,
                          'training_success_rate':statistics.mean(r['training_successes']/256 for r in subset),
                          'first64_success_rate':statistics.mean(r['first64_successes']/64 for r in subset),
                          'eval_mean_after_learning':statistics.mean(means[1:]),'eval_final':means[-1],
                          'eval_curve':means,'train_log_loss':statistics.mean(r['train_log_loss'] for r in subset),
                          'cpu_seconds_per_run':statistics.mean(r['cpu_seconds'] for r in subset),
                          'buffer_bytes_per_run':statistics.mean(r['buffer_bytes'] for r in subset)})
    differences=[]
    for fi,family in enumerate(FAMILIES):
        for other in ['global_gate','temporal_v210','fresh_only','pooled_history']:
            vals=[];trainvals=[]
            for seed in range(16):
                a=next(r for r in rows if (r['family'],r['seed'],r['arm'])==(family,seed,'conditional_gate'))
                b=next(r for r in rows if (r['family'],r['seed'],r['arm'])==(family,seed,other))
                vals.append(sum(x['successes']-y['successes'] for x,y in zip(a['evaluations'][1:],b['evaluations'][1:]))/(4*128))
                trainvals.append((a['training_successes']-b['training_successes'])/256)
            rng=random.Random(214900+fi*100+ARMS.index(other));boot=sorted(statistics.mean(rng.choices(vals,k=16)) for _ in range(2000))
            differences.append({'family':family,'reference':other,'mean_eval_difference':statistics.mean(vals),
                                'paired_seed_differences':vals,'exploratory_bootstrap_95':[boot[49],boot[1949]],
                                'mean_training_difference':statistics.mean(trainvals)})
    result={'schema':'v214-independent-stored-review','shards':64,'runs':len(rows),
            'actual_interactions':sum(r['interactions'] for r in results),'history_interactions':16384,
            'training_interactions':81920,'evaluation_interactions':204800,'records':sum(r['records'] for r in results),
            'max_formula_error':max(r['max_formula_error'] for r in results),'indistinguishable_pairs_checked':16,
            'steps_are_single_action_transitions':True,'table':table,'differences':differences,'rows':rows,
            'new_environment_runs':0,'neural_imports':0,'input_pins_match':True}
    with(HERE/'stored_review.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    with(HERE/'summary.csv').open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(table[0]));w.writeheader();w.writerows(table)
    print(json.dumps({k:result[k] for k in ['shards','runs','actual_interactions','records','max_formula_error','indistinguishable_pairs_checked']}))


if __name__=='__main__':main()
