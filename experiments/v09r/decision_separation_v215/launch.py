from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
import hashlib
import json
import os
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]


def main():
    contract=json.loads((HERE/'contract.json').read_text(encoding='utf-8'))
    started=time.monotonic();deadline=started+contract['wall_budget_seconds']
    capture=HERE/'capture';capture.mkdir(exist_ok=True)
    with(capture/'claim.json').open('x',encoding='utf-8') as f:
        json.dump({'utc':datetime.now(timezone.utc).isoformat(),'pid':os.getpid(),
                   'contract_sha256':hashlib.sha256((HERE/'contract.json').read_bytes()).hexdigest()},f,indent=2)
    pins=lambda:{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in contract['input_sha256']}
    before=pins();assert before==contract['input_sha256']
    env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1')
    def child(name,script,args,limit):
        row={'name':name,'command':[sys.executable,'-X','utf8','-B',str(HERE/script),*args],
             'started_utc':datetime.now(timezone.utc).isoformat()};t=time.monotonic();remaining=deadline-t
        if remaining<=0:row.update(exit_code=None,timed_out=False,not_started='overall_budget_exhausted')
        else:
            with(capture/f'{name}.stdout.txt').open('xb') as out,(capture/f'{name}.stderr.txt').open('xb') as err:
                try:
                    result=subprocess.run(row['command'],cwd=str(ROOT),env=env,stdout=out,stderr=err,
                                          timeout=min(limit,remaining),check=False)
                    row.update(exit_code=result.returncode,timed_out=False)
                except subprocess.TimeoutExpired:row.update(exit_code=None,timed_out=True)
        row['wall_seconds']=time.monotonic()-t
        with(capture/f'{name}.exit.json').open('x',encoding='utf-8') as f:json.dump(row,f,indent=2)
        print(json.dumps({k:row[k] for k in ['name','exit_code','timed_out','wall_seconds']}),flush=True)
        return row
    results=[child('formula_checks','check_model.py',[],contract['check_budget_seconds'])]
    if results[0]['exit_code']==0:
        with ThreadPoolExecutor(max_workers=contract['parallel_shards']) as pool:
            jobs=[pool.submit(child,f'{family}_s{seed:02d}','run_shard.py',[family,str(seed)],contract['shard_budget_seconds'])
                  for family in contract['families'] for seed in contract['seeds']]
            for job in as_completed(jobs):results.append(job.result())
        if all(r['exit_code']==0 for r in results):results.append(child('stored_review','review.py',[],contract['review_budget_seconds']))
    after=pins();complete=len(results)==66 and all(r['exit_code']==0 for r in results) and before==after
    final={'utc':datetime.now(timezone.utc).isoformat(),'complete':complete,'exit_code':0 if complete else 1,
           'wall_seconds':time.monotonic()-started,'children':results,'inputs_before':before,'inputs_after':after,
           'inputs_unchanged':before==after,'automatic_retries':0}
    with(capture/'exit.json').open('x',encoding='utf-8') as f:json.dump(final,f,indent=2)
    return final['exit_code']


if __name__=='__main__':sys.exit(main())
