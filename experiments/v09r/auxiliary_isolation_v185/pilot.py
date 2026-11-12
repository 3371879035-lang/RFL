"""One finite paired training-behavior intervention; old controls are read-only."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import platform
import sys
import time
import traceback
import psutil
import torch
import numpy as np
from experiment import ARMS, HERE, ROOT, pins, run_case, utc, write_json


def main():
    output = HERE/'evidence_pilot'
    output.mkdir(exist_ok=False)
    maps = str(HERE.parent/'spatial_feedback_v178/evidence_prepare/maps')
    input_pins = pins()
    start, results, error = time.perf_counter(), [], None
    write_json(output/'claim.json', dict(phase='auxiliary_isolation', utc=utc(), pid=__import__('os').getpid(),
        python=platform.python_version(), torch=torch.__version__, numpy=np.__version__,
        input_pins=input_pins, workers=8, argv=sys.argv), True)
    specs = [(seed, arm, 'auxiliary_isolation', str(output), maps)
             for seed in (93001,93002,93003,93004) for arm in ('F-RP','F-R')]
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=8) as pool:
            pending = {pool.submit(run_case, spec) for spec in specs}
            last_disk_check = 0.
            while pending:
                completed, pending = concurrent.futures.wait(pending, timeout=2,
                    return_when=concurrent.futures.FIRST_COMPLETED)
                processes = [psutil.Process()]+psutil.Process().children(recursive=True)
                memory = sum(p.memory_info().rss for p in processes if p.is_running())
                reason = None
                if memory > 20*1024**3:
                    reason = '20GiB RAM boundary'
                if time.perf_counter()-start > 3600:
                    reason = 'Declared pilot wall budget'
                if time.perf_counter()-last_disk_check > 30:
                    if sum(p.stat().st_size for p in output.rglob('*') if p.is_file()) > 6*1024**3:
                        reason = '6GiB artifact boundary'
                    last_disk_check = time.perf_counter()
                for future in completed:
                    result = future.result()
                    results.append(result)
                    if result['status'] != 'COMPLETE':
                        reason = 'Native case error, no automatic retry'
                if reason and not (output/'STOP.json').exists():
                    write_json(output/'STOP.json', dict(reason=reason, utc=utc()), True)
                write_json(output/'progress.json', dict(completed_cases=len(results),
                    wall_seconds=time.perf_counter()-start, aggregate_rss=memory))
        assert len(results)==8 and all(r['status']=='COMPLETE' for r in results)
        assert not (output/'STOP.json').exists()
        assert pins()==input_pins
        for pin in json.loads((HERE/'control_binding.json').read_text(encoding='utf-8'))['files']:
            p=ROOT/pin['path']
            assert p.stat().st_size==pin['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==pin['sha256']
        for pin in json.loads((HERE/'map_binding.json').read_text(encoding='utf-8'))['files']:
            p=ROOT/pin['path']
            assert p.stat().st_size==pin['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==pin['sha256']
    except BaseException:
        error=traceback.format_exc()
    record=dict(status='COMPLETE' if error is None else 'ERROR_PARTIAL_RETAINED',
        exit_code=int(error is not None), utc=utc(), error=error, cases=len(results),
        wall_seconds=time.perf_counter()-start, pins_after=pins(), inputs_unchanged=pins()==input_pins)
    write_json(output/'result.json', dict(exit=record,cases=results), True)
    write_json(output/'exit.json',record,True)
    print(json.dumps(record,ensure_ascii=False),flush=True)
    return record['exit_code']


if __name__=='__main__':
    raise SystemExit(main())
