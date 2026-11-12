"""Read only the new closed captures; no native/learner imports or replayed episodes."""
from concurrent.futures import ProcessPoolExecutor
import gzip
import hashlib
import json
from pathlib import Path
import struct
import time
import traceback
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]


def review_case(directory):
    result=json.loads((directory/'result.json').read_text(encoding='utf-8'))
    assert result['status']=='COMPLETE' and result['training_steps']==131072
    with gzip.open(directory/'steps.bin.gz','rb') as f:
        size,=struct.unpack('<I',f.read(4));header=json.loads(f.read(size));payload=f.read()
    dtype=np.dtype([(x[0],x[1],tuple(x[2])) if len(x)==3 else tuple(x) for x in header['dtype']])
    raw=np.frombuffer(payload,dtype)
    assert len(raw)==result['record_count'] and hashlib.sha256(payload).hexdigest()==result['record_payload_sha256']
    for pin in header['pins']:
        p=ROOT/pin['path'];assert p.stat().st_size==pin['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==pin['sha256']
    train=raw['kind']==0;main=raw['kind']==1;ablation=raw['kind']==2
    assert np.all(train|main|ablation) and train.sum()==131072
    assert np.all(raw['training_q_control'][train]==1) and np.all(raw['training_q_control'][~train]==0)
    assert np.array_equal(raw['action'][train & (raw['explore']==0)],raw['q_action'][train & (raw['explore']==0)])
    assert np.array_equal(raw['action'][main],raw['full_action'][main])
    assert np.array_equal(raw['action'][ablation],raw['q_action'][ablation])
    assert result['arm'] in ['F-RP','F-R']
    assert np.all(raw['action']<16) and np.all((raw['action']<8)|(raw['cooldown_before']==0))
    assert np.isfinite(raw['forecast']).all() and np.all((raw['step']>=1)&(raw['step']<=256))
    assert np.all((raw['captured']==0)|(raw['completed']==0))
    assert np.all(raw['explore'][~train]==0) and np.isnan(raw['reward'][~train]).all()
    n=np.cumsum(train)[train];stage=np.where(n<=16384,0,np.where(n<=65536,1,2))
    assert np.array_equal(raw['stage'][train],stage)
    if result['arm']=='F0':
        assert np.isnan(raw['reward']).all() and result['counters']['Q_updates']==result['counters']['reward_packets']==0
    else:
        penalty=int(result['arm'] in ['RL-RP','F-RP'])
        reward=(.015+raw['pickup'][train].astype(np.float64)-penalty*raw['captured'][train]).astype(np.float32)
        assert np.array_equal(raw['reward'][train],reward)
        assert result['counters']['Q_updates']==1009 and result['counters']['reward_packets']==131072
    if result['arm']=='RL-RP':
        assert np.all(raw['depth']==0) and result['counters']['fact_updates']==0 and not ablation.any()
    else:
        assert np.all(np.isin(raw['depth'][~ablation],[1,4,8]))
        assert np.all(raw['depth'][ablation]==0) and result['counters']['fact_updates']==1009
        assert result['counters']['bootstrap_positions']==258304
        for j in range(3):
            assert .68<result['counters'][f'bootstrap_selected_{j}']/258304<.75
    assert result['counters']['head_evaluations']==3*result['counters']['model_edges']
    cp=np.where(train,0,raw['checkpoint'])
    order=np.lexsort((raw['step'],raw['episode'],cp,raw['kind']))
    a=raw[order];c=cp[order]
    start=np.r_[True,(a['kind'][1:]!=a['kind'][:-1])|(c[1:]!=c[:-1])|(a['episode'][1:]!=a['episode'][:-1])]
    within=~start[1:];end=np.r_[start[1:],True]
    assert np.all(a['step'][start]==1)
    assert np.all((a['step'][1:]-a['step'][:-1])[within]==1)
    assert np.array_equal(a['before_hero'][1:][within],a['hero'][:-1][within])
    assert np.array_equal(a['before_monsters'][1:][within],a['monsters'][:-1][within])
    terminal=(a['captured']!=0)|(a['completed']!=0)
    assert not terminal[~end].any()
    assert terminal[end & (a['kind']!=0)].all()
    cumulative=np.cumsum(a['pickup']);base=np.maximum.accumulate(np.where(start,cumulative-a['pickup'],0))
    pickups=cumulative-base
    assert np.all(pickups<=10) and np.array_equal(a['score'],1.5*a['step']+100*pickups)
    next_cd=np.maximum(0,np.where(a['action']>=8,32,a['cooldown_before']).astype(int)-1)
    assert np.array_equal(next_cd[:-1][within],a['cooldown_before'][1:][within])
    delta=a['hero'].astype(int)-a['before_hero'].astype(int)
    bound=np.where(a['action']>=8,10,np.where(a['buff_before']!=0,2,1))
    assert np.all(np.abs(delta).max(-1)<=bound)
    directions=np.array([(1,0),(1,-1),(0,-1),(-1,-1),(-1,0),(-1,1),(0,1),(1,1)])
    walks=a['action']<8;direction=directions[a['action']%8]
    assert np.all(((delta==0)|(delta*direction>0))[walks])
    distance=np.abs(a['monsters'].astype(int)-a['hero'][:,None,:]).max(-1)
    caught=np.any((a['monsters'][:,:,0]>=0)&(distance<=1),axis=1)
    assert np.array_equal(caught,a['captured'].astype(bool))
    assert np.array_equal(a['completed'].astype(bool),(a['step']==256)&~caught)
    deep=raw['depth']>1
    keys=np.rec.fromarrays([raw['kind'][deep],cp[deep],raw['episode'][deep],((raw['step'][deep]-1)//8)])
    assert len(np.unique(keys))==len(keys)
    with gzip.open(directory/'episodes.jsonl.gz','rt',encoding='utf-8') as f:
        episodes=[json.loads(line) for line in f]
    for e in episodes:
        assert e['score']==1.5*e['steps']+100*e['treasures']
    assert len([e for e in episodes if e['kind']=='training'])==result['completed_training_episodes']
    for bank in result['evaluations']:
        rows=[e for e in episodes if e['kind']!='training' and e['checkpoint']==bank['checkpoint'] and e.get('ablation')==bank['ablation']]
        assert len(rows)==bank['episodes'] and sum(e['steps'] for e in rows)==bank['steps']
        assert np.mean([e['score'] for e in rows])==bank['mean_score']
        assert bank['counters']['Q_updates']==bank['counters']['fact_updates']==bank['counters']['reward_packets']==0
        count=bank['prediction_audit']['successors'];sums=dict(model_mse_sum=0.,identity_mse_sum=0.,successor_Q_MAE_sum=0.)
        actual_count=0
        with gzip.open(directory/'prediction_checks.jsonl.gz','rt',encoding='utf-8') as f:
            for line in f:
                row=json.loads(line)
                if row['checkpoint']!=bank['checkpoint'] or row['kind']!=(2 if bank['ablation']=='Q_only' else 1):continue
                assert 1<=row['next_observation_step']<=255
                assert np.isfinite(row['model_mse']) and row['model_mse']>=0
                assert np.isfinite(row['identity_mse']) and row['identity_mse']>=0
                actual_count+=1;sums['model_mse_sum']+=row['model_mse'];sums['identity_mse_sum']+=row['identity_mse']
                if row['own_Q_successor_MAE'] is not None:sums['successor_Q_MAE_sum']+=row['own_Q_successor_MAE']
        assert actual_count==count
        assert all(sums[k]==bank['prediction_audit'][k] for k in sums)
        if result['arm']!='RL-RP' and bank['ablation'] is None:
            assert count==bank['steps']-bank['episodes']
    old_dir=HERE.parent/'spatial_feedback_v183/evidence_pilot'/directory.parent.name/directory.name
    old_result=json.loads((old_dir/'result.json').read_text(encoding='utf-8'))
    assert result['initial_parameter_hash']==old_result['initial_parameter_hash']
    with gzip.open(old_dir/'episodes.jsonl.gz','rt',encoding='utf-8') as f:
        old_zero=[json.loads(line) for line in f if line.strip()]
    old_zero=[e for e in old_zero if e['kind']=='evaluation' and e['checkpoint']==0]
    new_zero=[e for e in episodes if e['kind']=='evaluation' and e['checkpoint']==0]
    assert new_zero==old_zero
    assert len(result['evaluations'])==8 and sum(b['episodes'] for b in result['evaluations'])==1152
    assert result['counters']['factual_action_changes']==0
    assert result['initial_parameter_parts']['facts']!=result['final_parameter_parts']['facts']
    core_matches_RL=None; training_matches_RL=None
    if result['arm']=='F-RP':
        rl_dir=HERE.parent/'spatial_feedback_v183/evidence_pilot'/directory.parent.name/'RL-RP'
        rl_result=json.loads((rl_dir/'result.json').read_text(encoding='utf-8'))
        core_matches_RL=result['final_parameter_parts']['core']==rl_result['final_parameter_hash']
        with gzip.open(rl_dir/'steps.bin.gz','rb') as f:
            size,=struct.unpack('<I',f.read(4)); rh=json.loads(f.read(size)); rp=f.read()
        rd=np.dtype([(x[0],x[1],tuple(x[2])) if len(x)==3 else tuple(x) for x in rh['dtype']])
        rr=np.frombuffer(rp,rd);rr=rr[rr['kind']==0];nt=raw[train]
        physical=['episode','map','mode','step','before_hero','before_monsters','hero','monsters',
                  'action','stage','explore','cooldown_before','buff_before','pickup','captured','completed','score','reward']
        training_matches_RL=bool(all(np.array_equal(nt[k],rr[k]) for k in physical))
    return dict(seed=result['seed'],arm=result['arm'],train_steps=int(train.sum()),eval_steps=int((~train).sum()),
        records=len(raw),payload_sha256=result['record_payload_sha256'],full_eof_crc=True,
        reward_action_chronology_score_depth_and_prediction_aggregates=True,
        training_Q_greedy_action_verified=True, full_and_Q_frozen_readouts_verified=True,
        old_initial_parameter_hash_and_zero_full_bank_identical=True, factual_heads_parameter_content_changed=True,
        final_core_bitwise_matches_pureRL=core_matches_RL, full_training_physical_rows_match_pureRL=training_matches_RL,
        train_Q_full_disagreements=int(np.sum(train & (raw['q_action']!=raw['full_action']))),
        train_greedy_disagreements=int(np.sum(train & (raw['explore']==0) & (raw['q_action']!=raw['full_action']))))


def main():
    d=HERE/'evidence_pilot';start=time.perf_counter();cases=[];error=None
    try:
        exit_record=json.loads((d/'exit.json').read_text(encoding='utf-8'));assert exit_record['exit_code']==0
        paths=[p.parent for p in sorted(d.glob('seed*/*/result.json'))];assert len(paths)==8
        with ProcessPoolExecutor(max_workers=4) as pool:
            cases=list(pool.map(review_case,paths))
        for pin in json.loads((HERE/'control_binding.json').read_text(encoding='utf-8'))['files']:
            p=ROOT/pin['path'];assert p.stat().st_size==pin['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==pin['sha256']
        for pin in json.loads((HERE/'map_binding.json').read_text(encoding='utf-8'))['files']:
            p=ROOT/pin['path'];assert hashlib.sha256(p.read_bytes()).hexdigest()==pin['sha256']
    except BaseException:error=traceback.format_exc()
    result=dict(exit_code=int(error is not None),error=error,cases=cases,wall_seconds=time.perf_counter()-start,
        native_or_environment_calls=0,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        limit='Closed-byte and accounting checks; not full independent physics/neural replay or expert qualification. Capture-Brier uses native prequential aggregation, not independently reconstructable from raw forecasts.')
    with (d/'stored_review_result.json').open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:result[k] for k in ['exit_code','error','wall_seconds']}),flush=True)
    return result['exit_code']


if __name__=='__main__':raise SystemExit(main())
