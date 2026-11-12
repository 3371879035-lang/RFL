"""Finite frozen policy-factorial checks, not another training matrix."""
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
import gzip
import hashlib
import json
import os
from pathlib import Path
import time
import traceback
import psutil
import torch
from evaluation_fixed import HERE, ROOT, Capture, evaluate, MapBank, utc, write_json

VARIANTS = ['H1_only', 'no_empirical_override', 'H1_no_empirical_override']


def pins():
    names = ['world.py','learning.py','repairs.py','evaluation_fixed.py','run_fixed.py','contract.json','control_binding.json','pure_check_wire_result.json']
    return [dict(path=(HERE/n).relative_to(ROOT).as_posix(), bytes=(HERE/n).stat().st_size,
                 sha256=hashlib.sha256((HERE/n).read_bytes()).hexdigest()) for n in names]


def run_model(spec):
    torch.use_deterministic_algorithms(True)
    seed, arm = spec
    start = time.perf_counter()
    source = HERE.parent/'auxiliary_isolation_v185/evidence_pilot'/f'seed{seed}'/arm
    result = json.loads((source/'result.json').read_text(encoding='utf-8'))
    with gzip.open(source/'checkpoint_131072.pt.gz','rb') as f:
        state = torch.load(f, weights_only=False, map_location='cpu')
    agent = state['agent']
    assert agent.parameter_hash() == result['final_parameter_hash'] and agent.training_steps == 131072
    bank = MapBank(str(HERE.parent/'spatial_feedback_v178/evidence_prepare/maps'))
    records = []
    for variant in VARIANTS:
        directory = HERE/'evidence'/f'seed{seed}'/arm/variant
        directory.mkdir(parents=True, exist_ok=False)
        capture = Capture(directory/'steps.bin.gz',dict(schema='V186_FROZEN_DECISION',seed=seed,arm=arm,
            variant=variant,dtype=__import__('evaluation_fixed').DTYPE.descr,pins=pins(),source_parameter_hash=agent.parameter_hash()))
        episodes = gzip.open(directory/'episodes.jsonl.gz','xt',encoding='utf-8',compresslevel=1)
        predictions = gzip.open(directory/'prediction_checks.jsonl.gz','xt',encoding='utf-8',compresslevel=1)
        error, measured = None, None
        try:
            if (HERE/'evidence/STOP.json').exists():
                raise RuntimeError('Declared resource boundary, partial retained')
            measured = evaluate(agent,bank,128,capture,episodes,predictions,131072,2,variant)
            assert agent.parameter_hash() == result['final_parameter_hash'] and agent.training_steps == 131072
            assert measured['counters']['Q_updates'] == measured['counters']['fact_updates'] == 0
        except BaseException:
            error = traceback.format_exc()
        finally:
            episodes.close(); predictions.close(); capture.close()
        record = dict(seed=seed,arm=arm,variant=variant,status='COMPLETE' if error is None else 'ERROR_PARTIAL',
            measured=measured,error=error,record_count=capture.total,record_payload_sha256=capture.hash.hexdigest(),
            source_parameter_hash=result['final_parameter_hash'],training_steps=0,optimizer_steps=0)
        write_json(directory/'result.json',record,True)
        records.append(record)
        if error is not None:
            break
    return dict(seed=seed,arm=arm,records=records,wall_seconds=time.perf_counter()-start)


def main():
    out = HERE/'evidence';out.mkdir(exist_ok=False)
    inputs = pins();start = time.perf_counter();results=[];error=None
    write_json(out/'claim.json',dict(utc=utc(),pid=os.getpid(),pins=inputs,workers=4),True)
    try:
        with ProcessPoolExecutor(max_workers=4) as pool:
            futures={pool.submit(run_model,(s,a)) for s in range(93001,93005) for a in ['F-RP','F-R']}
            while futures:
                done,futures=wait(futures,timeout=3,return_when=FIRST_COMPLETED)
                reason=None
                if time.perf_counter()-start>600:reason='600s budget'
                processes=[psutil.Process()]+psutil.Process().children(recursive=True)
                rss=sum(p.memory_info().rss for p in processes if p.is_running())
                if rss>20*1024**3:reason='20GiB budget'
                if sum(p.stat().st_size for p in out.rglob('*') if p.is_file())>2*1024**3:reason='2GiB budget'
                for future in done:
                    result=future.result();results.append(result)
                    if any(r['status']!='COMPLETE' for r in result['records']):reason='First native error'
                if reason and not (out/'STOP.json').exists():write_json(out/'STOP.json',dict(reason=reason,utc=utc()),True)
                write_json(out/'progress.json',dict(models=len(results),wall_seconds=time.perf_counter()-start,RAM_bytes=rss))
        assert len(results)==8 and sum(len(r['records']) for r in results)==24 and not (out/'STOP.json').exists()
        assert pins()==inputs
        for pin in json.loads((HERE/'control_binding.json').read_text(encoding='utf-8'))['files']:
            assert hashlib.sha256((ROOT/pin['path']).read_bytes()).hexdigest()==pin['sha256']
    except BaseException:
        error=traceback.format_exc()
    receipt=dict(exit_code=int(error is not None),error=error,utc=utc(),wall_seconds=time.perf_counter()-start,
                 models=len(results),training_steps=0,optimizer_steps=0,inputs_unchanged=pins()==inputs)
    write_json(out/'result.json',dict(exit=receipt,models=results),True)
    write_json(out/'exit.json',receipt,True)
    print(json.dumps(receipt,ensure_ascii=False),flush=True)
    return receipt['exit_code']


if __name__=='__main__':raise SystemExit(main())
