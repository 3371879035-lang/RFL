"""Read the stored run; no learner, environment rollout, or optimizer execution."""
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
import torch

HERE=Path(__file__).resolve().parent
CAP=HERE/'pilot_run1'
GROUPS=('original-F-R','open-random','open-learned')


def read(p):return json.loads(p.read_text(encoding='utf-8'))


def weight_hash(weights):
    h=hashlib.sha256()
    for k,v in weights.items():h.update(k.encode());h.update(v.cpu().numpy().tobytes())
    return h.hexdigest()


def main():
    final=read(CAP/'exit.json');assert final['exit_code']==0
    result=dict(status='COMPLETE_STORED_RESULT_REVIEW',exit=final,domains={},
                independent_training_seeds=[271,277,283],raw_training_steps=0,
                raw_evaluation_steps=0,optimizer_calls=0,checkpoint_bindings=[],
                new_environment_or_optimizer_calls=0)
    for domain in ('pursuit','generic'):
        combined={g:dict(seed_results=[],pairs=[],comparisons=[],curves={str(r):[] for r in (0,3,6)}) for g in GROUPS}
        for seed in (271,277,283):
            d=CAP/f'{domain}_{seed}';data=read(d/'result.json');assert read(d/'exit.json')['exit_code']==0
            weights=torch.load(d/'final.pt',map_location='cpu',weights_only=False)
            for group in GROUPS:
                model=weight_hash(weights[group]['network'])
                for e in ('0.0','0.1'):assert model==data['evaluations']['6'][group][e]['model']
                assert weights[group]['steps']==24576 and weights[group]['updates']==1536
                result['checkpoint_bindings'].append(dict(domain=domain,seed=seed,group=group,model=model))
                logs=[];count=0;optim=0
                wiregroup='F-R' if group=='original-F-R' else group
                for r in range(1,7):
                    trial={}
                    with gzip.open(d/f'round{r:04d}_{wiregroup}.jsonl.gz','rt',encoding='utf-8') as f:
                        rows=0
                        for line in f:
                            row=json.loads(line)
                            if row.get('kind')=='round_log':
                                events=row['events'];continue
                            idx=int(row['id'].rsplit('/',1)[1]);assert idx==count
                            assert row['action'] in row['source']['legal']
                            if 'memory_view' in row:
                                view=row['memory_view'];assert 0<=view['frontier']<=idx
                                assert len(view['extra'])==len(set(view['extra']))
                                assert all(view['frontier']<=j<idx for j in view['extra'])
                            else:assert all(int(e.rsplit('/',1)[1])<idx for e in row['memory_ids'])
                            if row['purpose']=='trial':
                                value=trial.setdefault(row['episode'],dict(total=np.zeros(4,np.float32),terminal=False,steps=0))
                                value['total']+=np.array(row['facts'],np.float32)
                                value['terminal']=row['terminal'];value['steps']+=1
                            rows+=1;count+=1
                    assert rows==4096
                    n=sum(e['kind']=='optimizer' for e in events);assert n==256;optim+=n
                    for event in events:
                        if event['kind']=='actual_pair':
                            differences=[]
                            for rep in (0,1):
                                b=trial[f"trial/{r}/{rep}/{event['baseline']}"]
                                a=trial[f"trial/{r}/{rep}/{event['alternative']}"]
                                w=np.array((.96,10,0,0) if domain=='pursuit' else (0,0,1,1))
                                differences.append(float(a['total']@w)-float(b['total']@w))
                                if group!='original-F-R':assert a['terminal'] and b['terminal']
                            assert differences==event['differences']
                            assert float(np.mean(differences))==event['delta']
                        if group!='original-F-R' and event['kind']=='full_task_gate':assert event['stage']=='student'
                    logs+=events
                assert count==24576 and optim==1536
                result['raw_training_steps']+=count;result['optimizer_calls']+=optim
                s=combined[group]
                for r in (0,3,6):
                    ev=data['evaluations'][str(r)][group]
                    for e in ('0.0','0.1'):
                        assert ev[e]['episodes']==32
                        assert ev[e]['successes']==sum(int(x['success']) for x in ev[e]['rows'])
                        result['raw_evaluation_steps']+=sum(x['steps'] for x in ev[e]['rows'])
                    s['curves'][str(r)].append(ev['0.0'])
                s['seed_results'].append(dict(seed=seed,greedy=data['evaluations']['6'][group]['0.0'],
                    exploratory=data['evaluations']['6'][group]['0.1'],counts=data['counts'][group],
                    training_seconds=data['training_seconds'][group],memory_nodes=data['memory_nodes'][group],
                    eligible_failed_states=data['complete_failed_states'][group]))
                s['pairs'] += [dict(seed=seed,**x) for x in logs if x['kind']=='actual_pair']
                s['comparisons'] += [dict(seed=seed,**x) for x in logs if x['kind']=='full_task_gate']
        for g,s in combined.items():
            rows=[v['greedy'] for v in s['seed_results']]
            s['final']=dict(mean_score=float(np.mean([r['mean_score'] for r in rows])),
                successes=sum(r['successes'] for r in rows),episodes=96,
                mean_steps=float(np.mean([r['mean_steps'] for r in rows])),
                mean_pickups=float(np.mean([v['pickups'] for r in rows for v in r['rows']])),
                mean_distance=float(np.mean([r['mean_distance'] for r in rows])) if domain=='generic' else None,
                seed_scores=[r['mean_score'] for r in rows],seed_successes=[r['successes'] for r in rows])
            s['curve_summary']={r:dict(mean_score=float(np.mean([x['mean_score'] for x in rr])),
                success_rate=sum(x['successes'] for x in rr)/96) for r,rr in s['curves'].items()}
            s['negative_or_zero_pairs']=sum(p['delta']<=0 for p in s['pairs'])
            s['mean_actual_pair_delta']=float(np.mean([p['delta'] for p in s['pairs']]))
            s['student_adoptions']=sum(x['passed'] for x in s['comparisons'] if x['stage']=='student')
            s['actual_steps_by_purpose']={k:sum(x['counts'][k] for x in s['seed_results']) for k in ('ordinary_steps','trial_steps','gate_steps')}
        base=combined['original-F-R'];random=combined['open-random']
        for g,s in combined.items():
            s['paired_score_vs_original']=[a['greedy']['mean_score']-b['greedy']['mean_score'] for a,b in zip(s['seed_results'],base['seed_results'])]
            s['paired_score_vs_random']=[a['greedy']['mean_score']-b['greedy']['mean_score'] for a,b in zip(s['seed_results'],random['seed_results'])]
        result['domains'][domain]=combined
    assert result['raw_training_steps']==442368
    assert result['raw_evaluation_steps']<=452736
    assert result['optimizer_calls']==27648
    (CAP/'analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    compact={d:{g:{k:s[k] for k in ('final','curve_summary','negative_or_zero_pairs','mean_actual_pair_delta','student_adoptions','actual_steps_by_purpose','paired_score_vs_original','paired_score_vs_random')} for g,s in groups.items()} for d,groups in result['domains'].items()}
    (CAP/'compact.json').write_text(json.dumps(compact,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=result['status'],wall_seconds=final['seconds'],raw_training_steps=result['raw_training_steps'],raw_evaluation_steps=result['raw_evaluation_steps'],optimizer_calls=result['optimizer_calls'],results=compact),ensure_ascii=False))


if __name__=='__main__':main()
