"""Read-only audit of this new pilot; no environment or training execution."""
import gzip
import hashlib
import json
from pathlib import Path
import struct
import time
import traceback
import numpy as np
import torch

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]


def load_binary(path):
    with gzip.open(path,'rb') as f:
        n=struct.unpack('<I',f.read(4))[0];header=json.loads(f.read(n));data=f.read()
    descr=[tuple([x[0],x[1],tuple(x[2])]) if len(x)==3 else tuple(x) for x in header['dtype']]
    dtype=np.dtype(descr)
    assert len(data)%dtype.itemsize==0
    return np.frombuffer(data,dtype),hashlib.sha256(data).hexdigest()


def weight_hash(state):
    h=hashlib.sha256()
    for v in state.values():h.update(v.detach().numpy().tobytes())
    return h.hexdigest()


def main():
    output=HERE/'stored_review.json';assert not output.exists()
    start=time.perf_counter();error=None;rows=[]
    totals=dict(train_steps=0,eval_steps=0,eval_episodes=0,labels=0,optimizer_updates=0,
                candidate_branches=0,changed_policies=0,student_weight_changes=0)
    try:
        main_result=json.loads((HERE/'evidence_pilot/result.json').read_text())
        assert main_result['exit']['exit_code']==0 and len(main_result['cases'])==32
        claim=json.loads((HERE/'evidence_pilot/claim.json').read_text())
        bindings=json.loads((HERE/'checkpoint_binding.json').read_text())['files']
        map_pins=json.loads((HERE/'map_binding.json').read_text())['files']
        for pin in claim['inputs']+bindings+map_pins:
            p=ROOT/pin['path']
            assert p.stat().st_size==pin['bytes']
            assert hashlib.file_digest(p.open('rb'),'sha256').hexdigest()==pin['sha256']
        for result in main_result['cases']:
            d=HERE/'evidence_pilot'/f"seed{result['seed']}"/result['arm']/result['variant']
            stored=json.loads((d/'result.json').read_text());assert stored==result
            data,digest=load_binary(d/'steps.bin.gz')
            assert len(data)==result['raw_records'] and digest==result['raw_payload_sha256']
            train=data[data['kind']==0];evaluation=data[data['kind']==1]
            assert len(train)==12288 and np.isin(data['action'],np.arange(16)).all()
            if result['arm']=='F0':assert np.isnan(data['reward']).all()
            else:
                penalty=1 if result['arm'] in ('RL-RP','F-RP') else 0
                expected=(.015+train['pickup'].astype(float)-penalty*train['captured']).astype(np.float32)
                assert np.array_equal(train['reward'],expected)
                assert np.isnan(evaluation['reward']).all()
            with gzip.open(d/'episodes.jsonl.gz','rt',encoding='utf-8') as f:
                episodes=[json.loads(l) for l in f]
            for cp in np.unique(evaluation['checkpoint']):
                a=evaluation[evaluation['checkpoint']==cp]
                eps=[r for r in episodes if r['kind']=='evaluation' and r['checkpoint']==int(cp)]
                ev=next(e for e in result['evaluations'] if e['checkpoint']==int(cp))
                assert len(eps)==ev['episodes'] and sum(r['steps'] for r in eps)==len(a)==ev['steps']
                assert float(np.mean([r['score'] for r in eps]))==ev['mean_score']
                for row in eps:
                    b=a[a['episode']==row['episode']]
                    assert len(b)==row['steps'] and np.array_equal(b['step'],np.arange(1,len(b)+1))
                    assert np.all(b['score']==1.5*b['step']+100*np.cumsum(b['pickup']))
                    assert row['score']==float(b['score'][-1])
                    assert bool(b['captured'][-1] or b['completed'][-1])
                    assert not np.any(b['captured'][:-1]|b['completed'][:-1])
                totals['eval_episodes']+=len(eps)
            if result['variant']=='adaptive_sleep':
                peer=json.loads((d.parent/'matched_replay/result.json').read_text())
                assert result['initial_hash']==peer['initial_hash']
                assert result['evaluations'][0]==peer['evaluations'][0]
                assert not np.any(evaluation['checkpoint']==0)
            labels,label_digest=load_binary(d/'labels.bin.gz')
            assert len(labels)==result['labels'] and label_digest==result['label_payload_sha256']
            if result['arm']=='F0':
                assert ((labels['uid']>=147456)&(labels['observed_at']<159744)).all()
                assert ((labels['observed_at']-labels['uid']+1)==labels['steps']).all()
                horizons=np.array([1,4,16,64])[labels['horizon']]
                assert np.array_equal(labels['target_steps'],(labels['steps']/horizons).astype(np.float32))
                assert np.array_equal(labels['target_pickups'],labels['pickups'].astype(np.float32))
                assert ((labels['steps']==horizons)|(labels['terminal']==1)).all()
                # Labels must be realized pickups inside that same recorded trajectory.
                prefix=np.r_[0,np.cumsum(train['pickup'],dtype=np.int64)]
                a=labels['uid']-147456;b=labels['observed_at']-147456+1
                assert np.array_equal(prefix[b]-prefix[a],labels['pickups'])
                assert np.all(train['episode'][a]==train['episode'][b-1])
            else:assert len(labels)==0
            with gzip.open(d/'sleep.jsonl.gz','rt',encoding='utf-8') as f:
                sleeps=[json.loads(l) for l in f]
            assert len(sleeps)==3
            previous=np.zeros(3)
            for report in sleeps:
                cycle=report['cycle'];features=np.array(report['features']);pool=np.array(report['train_windows'])
                probe=np.array(report['probe_windows'])
                assert not np.intersect1d((pool[:,None]+np.arange(25)).ravel(),(probe[:,None]+np.arange(25)).ravel()).size
                assert np.array_equal(previous,report['previous_theta']) and report['updates']==24
                assert len(report['fitting_log'])==24
                with gzip.open(d/f'sleep_round{cycle}.pt.gz','rb') as f:
                    weights=torch.load(f,map_location='cpu',weights_only=True)
                assert weight_hash(weights['parent'])==report['parent_hash']
                assert weight_hash(weights['student'])==report['student_hash']!=report['parent_hash']
                if result['variant']=='adaptive_sleep':
                    candidates=report['candidates'];assert len(candidates)==len(weights['teachers'])==4
                    best=min(range(4),key=lambda i:candidates[i]['probe_loss'])
                    expected=best if candidates[best]['probe_loss']<report['before_probe'] else None
                    assert report['selected']==expected
                    theta=previous if expected is None else np.array(candidates[expected]['theta'])
                    assert np.array_equal(theta,report['next_theta'])
                    for i,c in enumerate(candidates):
                        assert weight_hash(weights['teachers'][i])==c['teacher_hash']
                        assert abs(c['relative_gain']-(report['before_probe']-c['probe_loss'])/max(report['before_probe'],1e-12))<1e-12
                    assert report['history_records']==4*cycle
                    totals['candidate_branches']+=4
                    totals['changed_policies']+=int(not np.array_equal(previous,theta))
                    totals['student_weight_changes']+=1
                for entry in report['fitting_log']:
                    branch=entry['branch']
                    theta=(np.zeros(3) if branch=='direct' else np.array(report['next_theta']) if branch=='student'
                           else np.array(report['candidates'][branch]['theta']))
                    logits=features@theta;prob=np.exp(logits-logits.max());prob/=prob.sum();prob=.1/len(prob)+.9*prob
                    indices=[int(np.flatnonzero(pool==v)[0]) for v in entry['starts']]
                    assert np.allclose(prob[indices],entry['probabilities'],rtol=0,atol=1e-14)
                    assert np.isfinite(entry['loss']) and np.isfinite(entry['distillation'])
                    if branch!='student':assert entry['distillation']==0
                previous=np.array(report['next_theta'])
            assert np.array_equal(previous,result['final_rehearsal_policy'])
            assert result['final_hash']==sleeps[-1]['student_hash']
            counters=result['counters'];assert counters['v191_optimizer_updates']==168
            assert counters['Q_updates']==(0 if result['arm']=='F0' else 168)
            assert counters['fact_updates']==(0 if result['arm']=='RL-RP' else 168)
            assert counters['reward_packets']==(0 if result['arm']=='F0' else 12288)
            totals['train_steps']+=len(train);totals['eval_steps']+=len(evaluation)
            totals['labels']+=len(labels);totals['optimizer_updates']+=168
            rows.append(dict(seed=result['seed'],arm=result['arm'],variant=result['variant'],verified=True))
        assert totals['train_steps']==393216 and totals['eval_episodes']==16384
        assert totals['optimizer_updates']==5376 and totals['candidate_branches']==192
    except BaseException:error=traceback.format_exc()
    result=dict(exit_code=int(error is not None),error=error,cases=rows,totals=totals,
                source_pins_verified=len(claim['inputs']+bindings+map_pins) if 'claim' in locals() else 0,
                wall_seconds=time.perf_counter()-start,environment_executions=0,optimizer_updates=0,
                scope='Stored evidence arithmetic/selection/probabilities/weight-content/feedback isolation; not independent expert or neural-gradient replay.')
    with output.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(result));return result['exit_code']


if __name__=='__main__':raise SystemExit(main())
