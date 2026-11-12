"""Stored-only audit and developmental comparison with the retained V229 results."""
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
import torch

HERE=Path(__file__).resolve().parent
CAP=HERE/'pilot_run1'
PREV=HERE.parent/'practice_feedback_v229/pilot_run1'
GROUPS=('soft-learned',)


def read(p):return json.loads(p.read_text(encoding='utf-8'))


def fingerprint(weights):
    h=hashlib.sha256()
    for k,v in weights.items():h.update(k.encode());h.update(v.cpu().numpy().tobytes())
    return h.hexdigest()


def main():
    ex=read(CAP/'exit.json');assert ex['exit_code']==0
    previous=read(PREV/'compact.json')
    all_results=dict(status='COMPLETE_STORED_DEVELOPMENT_COMPARISON',exit=ex,domains={},
        raw_training_steps=0,evaluation_steps=0,optimizer_calls=0,actual_return_labels=0,
        optimizer_calls_with_actual_return_loss=0,checkpoint_bindings=[],new_rollouts=0)
    for domain in ('pursuit','generic'):
        groups={g:dict(seeds=[],pairs=[],comparisons=[]) for g in GROUPS}
        for seed in (271,277,283):
            d=CAP/f'{domain}_{seed}';data=read(d/'result.json')
            prior=read(PREV/f'{domain}_{seed}'/'result.json')
            weights=torch.load(d/'final.pt',map_location='cpu',weights_only=False)
            for group in GROUPS:
                initial=data['evaluations']['0'][group]['0.0']['model']
                assert initial==prior['evaluations']['0']['original-F-R']['0.0']['model']
                h=fingerprint(weights[group]['network'])
                assert all(h==data['evaluations']['6'][group][e]['model'] for e in ('0.0','0.1'))
                assert weights[group]['steps']==24576 and weights[group]['updates']==1536
                all_results['checkpoint_bindings'].append(dict(domain=domain,seed=seed,group=group,initial=initial,final=h))
                event_count=0;episode_counts={};completed_labels=0;opt_count=0;return_updates=0;events=[]
                for r in range(1,7):
                    trials={};round_rows=0
                    with gzip.open(d/f'round{r:04d}_{group}.jsonl.gz','rt',encoding='utf-8') as stream:
                        for line in stream:
                            row=json.loads(line)
                            if row.get('kind')=='round_log':
                                logs=row['events'];continue
                            idx=int(row['id'].rsplit('/',1)[1]);assert idx==event_count
                            assert row['action'] in row['source']['legal']
                            view=row['memory_view'];assert 0<=view['frontier']<=idx
                            assert all(view['frontier']<=j<idx for j in view['extra'])
                            assert len(view['extra'])==len(set(view['extra']))
                            ep=row['episode'];episode_counts[ep]=episode_counts.get(ep,0)+1
                            if row['terminal']:completed_labels+=episode_counts.pop(ep)
                            if row['purpose']=='trial':
                                v=trials.setdefault(ep,dict(total=np.zeros(4,np.float32),terminal=False))
                                v['total']+=np.array(row['facts'],np.float32);v['terminal']=row['terminal']
                            event_count+=1;round_rows+=1
                    assert round_rows==4096
                    optim=[x for x in logs if x['kind']=='optimizer'];assert len(optim)==256
                    opt_count+=len(optim);return_updates+=sum('actual_return' in x['parts'] for x in optim)
                    for x in logs:
                        if x['kind']=='actual_pair':
                            delta=[];w=np.array((.96,10,0,0) if domain=='pursuit' else (0,0,1,1))
                            for rep in (0,1):
                                a=trials[f"trial/{r}/{rep}/{x['alternative']}"]
                                b=trials[f"trial/{r}/{rep}/{x['baseline']}"]
                                assert a['terminal'] and b['terminal']
                                delta.append(float(a['total']@w)-float(b['total']@w))
                            assert delta==x['differences'] and float(np.mean(delta))==x['delta']
                        if x['kind']=='full_task_gate':assert x['stage']=='student'
                    events+=logs
                assert event_count==24576 and opt_count==1536
                assert completed_labels==data['counts'][group]['actual_return_labels']
                all_results['raw_training_steps']+=event_count;all_results['optimizer_calls']+=opt_count
                all_results['actual_return_labels']+=completed_labels;all_results['optimizer_calls_with_actual_return_loss']+=return_updates
                for r in (0,3,6):
                    for e in ('0.0','0.1'):
                        ev=data['evaluations'][str(r)][group][e]
                        assert ev['successes']==sum(int(x['success']) for x in ev['rows'])
                        all_results['evaluation_steps']+=sum(x['steps'] for x in ev['rows'])
                groups[group]['seeds'].append(dict(seed=seed,curves={r:data['evaluations'][r][group] for r in ('0','3','6')},
                    counts=data['counts'][group],actual_return_labels=completed_labels,return_updates=return_updates,
                    train_seconds=data['training_seconds'][group],memory_nodes=data['memory_nodes'][group]))
                groups[group]['pairs'] += [dict(seed=seed,**x) for x in events if x['kind']=='actual_pair']
                groups[group]['comparisons'] += [dict(seed=seed,**x) for x in events if x['kind']=='full_task_gate']
        for g,s in groups.items():
            end=[x['curves']['6']['0.0'] for x in s['seeds']]
            scores=[x['mean_score'] for x in end]
            s['final']=dict(mean_score=float(np.mean(scores)),successes=sum(x['successes'] for x in end),episodes=96,
                mean_distance=float(np.mean([x['mean_distance'] for x in end])) if domain=='generic' else None,
                mean_steps=float(np.mean([x['mean_steps'] for x in end])),
                mean_pickups=float(np.mean([r['pickups'] for x in end for r in x['rows']])),
                seed_scores=scores,seed_successes=[x['successes'] for x in end])
            s['curve_summary']={r:dict(mean_score=float(np.mean([x['curves'][r]['0.0']['mean_score'] for x in s['seeds']])),
                success_rate=sum(x['curves'][r]['0.0']['successes'] for x in s['seeds'])/96) for r in ('0','3','6')}
            former='open-random' if g=='dense-random' else 'open-learned'
            s['vs_corresponding_v229']=[a-b for a,b in zip(scores,previous[domain][former]['final']['seed_scores'])]
            s['vs_original_FR']=[a-b for a,b in zip(scores,previous[domain]['original-F-R']['final']['seed_scores'])]
            s['labels_per_seed']=[x['actual_return_labels'] for x in s['seeds']]
            s['student_adoptions']=sum(x['passed'] for x in s['comparisons'])
            s['negative_or_zero_pairs']=sum(x['delta']<=0 for x in s['pairs'])
            s['mean_actual_pair_delta']=float(np.mean([x['delta'] for x in s['pairs']]))
            s['costs']={k:sum(x['counts'][k] for x in s['seeds']) for k in ('ordinary_steps','trial_steps','gate_steps','sleep_updates')}
        all_results['domains'][domain]=groups
    assert all_results['raw_training_steps']==147456 and all_results['optimizer_calls']==9216
    assert all_results['evaluation_steps']<=150912
    (CAP/'analysis.json').write_text(json.dumps(all_results,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    compact={d:{g:{k:v[k] for k in ('final','curve_summary','vs_corresponding_v229','vs_original_FR','labels_per_seed','student_adoptions','negative_or_zero_pairs','mean_actual_pair_delta','costs')} for g,v in groups.items()} for d,groups in all_results['domains'].items()}
    (CAP/'compact.json').write_text(json.dumps(compact,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=all_results['status'],seconds=ex['seconds'],training_steps=all_results['raw_training_steps'],evaluation_steps=all_results['evaluation_steps'],labels=all_results['actual_return_labels'],return_updates=all_results['optimizer_calls_with_actual_return_loss'],results=compact),ensure_ascii=False))


if __name__=='__main__':main()
