"""Review each completed native case once; overlap independent shards with training."""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import time
import traceback
from stored_review import review_case


def work(pair):
    directory, destination = map(Path, pair)
    error, result = None, None
    started = time.perf_counter()
    try:
        result = review_case(directory)
    except BaseException:
        error = traceback.format_exc()
    receipt = dict(case=str(directory),exit_code=0 if error is None else 1,
                   result=result,error=error,wall_seconds=time.perf_counter()-started,
                   environment_calls=0,native_module_imports=0)
    with destination.open('x',encoding='utf-8',newline='\n') as f:
        json.dump(receipt,f,ensure_ascii=False,indent=2);f.write('\n')
    return receipt


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('directory');parser.add_argument('--workers',type=int,default=4)
    args=parser.parse_args();source=Path(args.directory).resolve()
    out=source.parent/'review_shards';out.mkdir(exist_ok=True)
    pairs=[];reused=0
    for p in sorted(source.glob('seed*/*/result.json')):
        # The native completion progress is written only after its final result closes.
        progress=p.parent/'progress.json'
        if not progress.exists() or json.loads(progress.read_text(encoding='utf-8')).get('status')!='COMPLETE':
            continue
        destination=out/(p.parent.parent.name+'__'+p.parent.name+'.json')
        if destination.exists():
            reused+=1;continue
        pairs.append((str(p.parent),str(destination)))
    assert 1<=args.workers<=12
    started=time.perf_counter()
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
        receipts=list(pool.map(work,pairs))
    summary=dict(new_shards=len(receipts),previous_receipts_reused_without_execution=reused,
                 errors=sum(x['exit_code']!=0 for x in receipts),workers=args.workers,
                 wall_seconds=time.perf_counter()-started,environment_calls=0,
                 reader_sha256=hashlib.sha256((Path(__file__).parent/'stored_review.py').read_bytes()).hexdigest())
    name=out/f'batch_{time.time_ns()}.json'
    with name.open('x',encoding='utf-8',newline='\n') as f:
        json.dump(summary,f,indent=2);f.write('\n')
    print(json.dumps(summary),flush=True)
    return int(summary['errors']>0)


if __name__=='__main__':
    raise SystemExit(main())
