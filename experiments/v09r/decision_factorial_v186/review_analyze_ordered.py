"""Read closed frozen captures once, then contrast with the stored V185 banks."""
import gzip
import hashlib
import json
from pathlib import Path
import statistics
import struct
import time
import traceback
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
SEEDS=range(93001,93005)
ARMS=['F-RP','F-R']
VARIANTS=['H1_only','no_empirical_override','H1_no_empirical_override']


def mean(xs):return float(statistics.mean(xs))


def ordered_sum(xs):
    total=0.
    for x in xs:total+=x
    return total


def main():
    start=time.perf_counter();error=None;cases=[];output=None
    try:
        native=json.loads((HERE/'evidence/exit.json').read_text(encoding='utf-8'))
        assert native['exit_code']==0
        for seed in SEEDS:
            for arm in ARMS:
                original=HERE.parent/'auxiliary_isolation_v185/evidence_pilot'/f'seed{seed}'/arm
                rr=json.loads((original/'result.json').read_text(encoding='utf-8'))
                with gzip.open(original/'episodes.jsonl.gz','rt',encoding='utf-8') as f:
                    old=[json.loads(x) for x in f]
                base={key:[x for x in old if x.get('checkpoint')==131072 and x['episode']<128 and x.get('ablation')==ablation]
                      for key,ablation in [('full',None),('Q','Q_only')]}
                for key in base:assert len(base[key])==128
                row=dict(seed=seed,arm=arm,scores={k:mean(x['score'] for x in xs) for k,xs in base.items()},variants={})
                for variant in VARIANTS:
                    d=HERE/'evidence'/f'seed{seed}'/arm/variant
                    result=json.loads((d/'result.json').read_text(encoding='utf-8'));assert result['status']=='COMPLETE'
                    with gzip.open(d/'steps.bin.gz','rb') as f:
                        size,=struct.unpack('<I',f.read(4));header=json.loads(f.read(size));payload=f.read()
                    dtype=np.dtype([(x[0],x[1],tuple(x[2])) if len(x)==3 else tuple(x) for x in header['dtype']])
                    raw=np.frombuffer(payload,dtype)
                    assert len(raw)==result['record_count'] and hashlib.sha256(payload).hexdigest()==result['record_payload_sha256']
                    assert result['source_parameter_hash']==result['measured']['parameter_hash']==rr['final_parameter_hash']
                    for pin in header['pins']:
                        assert hashlib.sha256((ROOT/pin['path']).read_bytes()).hexdigest()==pin['sha256']
                    assert np.all(raw['kind']==2) and np.all(raw['checkpoint']==131072)
                    assert np.all(raw['training_q_control']==0) and np.all(raw['explore']==0) and np.isnan(raw['reward']).all()
                    assert np.array_equal(raw['action'],raw['full_action'])
                    assert np.all((raw['action']<8)|(raw['cooldown_before']==0))
                    assert np.all(raw['depth']==1) if variant.startswith('H1') else np.all(np.isin(raw['depth'],[1,4,8]))
                    assert result['measured']['counters']['Q_updates']==result['measured']['counters']['fact_updates']==0
                    with gzip.open(d/'episodes.jsonl.gz','rt',encoding='utf-8') as f:episodes=[json.loads(x) for x in f]
                    assert len(episodes)==128 and sum(x['steps'] for x in episodes)==len(raw)
                    for j,e in enumerate(episodes):
                        assert e['episode']==j and e['ablation']==variant
                        assert e['map']==base['full'][j]['map'] and e['mode']==base['full'][j]['mode']
                        a=raw[raw['episode']==j]
                        assert np.array_equal(a['step'],np.arange(1,e['steps']+1))
                        assert np.array_equal(a['before_hero'][1:],a['hero'][:-1])
                        assert np.array_equal(a['before_monsters'][1:],a['monsters'][:-1])
                        assert np.array_equal(a['score'],1.5*a['step']+100*np.cumsum(a['pickup']))
                        assert not ((a['captured']|a['completed'])[:-1]).any() and (a['captured'][-1]|a['completed'][-1])
                        assert e['score']==float(a['score'][-1]) and e['treasures']==int(a['pickup'].sum())
                    measured=result['measured'];assert mean(x['score'] for x in episodes)==measured['mean_score']
                    with gzip.open(d/'prediction_checks.jsonl.gz','rt',encoding='utf-8') as f:preds=[json.loads(x) for x in f]
                    assert len(preds)==len(raw)-128==measured['prediction_audit']['successors']
                    for field,aggregate in [('model_mse','model_mse_sum'),('identity_mse','identity_mse_sum'),('own_Q_successor_MAE','successor_Q_MAE_sum')]:
                        assert ordered_sum(x[field] for x in preds)==measured['prediction_audit'][aggregate]
                    row['scores'][variant]=mean(x['score'] for x in episodes)
                    row['variants'][variant]=dict(episodes=128,steps=len(raw),survival=mean(x['steps'] for x in episodes),
                        treasures=mean(x['treasures'] for x in episodes),parameter_hash=measured['parameter_hash'])
                cases.append(row)
        summaries=[]
        for arm in ARMS:
            rs=[x for x in cases if x['arm']==arm]
            summary=dict(arm=arm,means={k:mean(x['scores'][k] for x in rs) for k in ['full','Q']+VARIANTS},differences_vs_full={})
            for variant in VARIANTS:
                ds=[x['scores'][variant]-x['scores']['full'] for x in rs]
                summary['differences_vs_full'][variant]=dict(mean=mean(ds),positive_seeds=sum(x>0 for x in ds),per_seed=ds)
            summaries.append(summary)
        actual=dict(training_steps=0,optimizer_steps=0,evaluation_episodes=3072,
            environment_steps=sum(v['steps'] for r in cases for v in r['variants'].values()),wall_seconds=native['wall_seconds'])
        assert actual['environment_steps']<=786432
        output=dict(status='COMPLETE_FROZEN_DECISION_FACTORIAL',summaries=summaries,per_case=cases,actual=actual,
            limitations=['Four fixed trained seeds; evaluationepisodes are not independent trainingseeds.',
                         'Frozenreadout effects only; no retraining, no automatic adoption of best variant.',
                         'Noempiricaloverride retains historicalfeatures; this is not deleting all memory.',
                         'OriginalfullandQscores are read-onlyV185matched128banks.'])
    except BaseException:error=traceback.format_exc()
    receipt=dict(exit_code=int(error is not None),error=error,cases=len(cases),wall_seconds=time.perf_counter()-start,
                 native_or_environment_calls=0,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    with (HERE/'evidence/stored_review_ordered_result.json').open('x',encoding='utf-8',newline='\n') as f:json.dump(receipt,f,ensure_ascii=False,indent=2)
    if output is not None and error is None:
        out=HERE/'analysis';out.mkdir(exist_ok=False)
        with (out/'result.json').open('x',encoding='utf-8',newline='\n') as f:json.dump(output,f,ensure_ascii=False,indent=2)
        lines=['# V186：冻结决策层两因素结果','','全部同j0..127场景，4配对训练种子。','','|组|原完整|自己Q|仅一步H1|仅去经验评分修正|H1且去经验评分修正|','|---|---:|---:|---:|---:|---:|']
        for row in output['summaries']:
            lines.append('|'+row['arm']+'|'+'|'.join(f"{row['means'][k]:.3f}" for k in ['full','Q']+VARIANTS)+'|')
        lines+=['','新增0训练，3072评估回合；所有负/零/正结果保留。不把冻结对照当新训练效果。','',json.dumps(output['actual'],ensure_ascii=False)]
        with (out/'result.md').open('x',encoding='utf-8',newline='\n') as f:f.write('\n'.join(lines)+'\n')
    print(json.dumps(dict(review=receipt,result=None if output is None else dict(summaries=output['summaries'],actual=output['actual'])),ensure_ascii=False),flush=True)
    return receipt['exit_code']


if __name__=='__main__':raise SystemExit(main())
