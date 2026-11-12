"""Exclusive pure-wire validation; not a retry of V96's native experiment."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]


def pin(path):
    return {'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def save(path,data):
    with path.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(data,stream,sort_keys=True,separators=(',',':'),ensure_ascii=True);stream.write('\n')


def main():
    c=json.loads((HERE/'contract.json').read_bytes())
    selected=list(p for p in HERE.iterdir() if p.is_file())
    selected += [ROOT/c[k]['path'] for k in ('preserved_failed_ruler','preserved_failed_capture')]
    selected += [p for p in (HERE.parent/'owned_whole_collateral_v96').rglob('*') if p.is_file()]
    selected=sorted(set(selected))
    before={p.relative_to(ROOT).as_posix():pin(p) for p in selected}
    for key in ('preserved_failed_ruler','preserved_failed_capture'):
        assert pin(ROOT/c[key]['path'])['sha256']==c[key]['sha256']
    out=HERE/'evidence';out.mkdir(exist_ok=False)
    started=datetime.now(timezone.utc).isoformat()
    command=[sys.executable,'-X','utf8','-B',str(HERE/'test_wire.py')]
    save(out/'claim.json',{'input_binding_before':before,'started_at_utc':started,
                         'command':command,'automatic_retry':False,'role':'PURE_WIRE_BOUNDARY_NOT_NATIVE_RULER_RETRY'})
    with (out/'stdout.log').open('xb') as stdout,(out/'stderr.log').open('xb') as stderr:
        child=subprocess.run(command,stdout=stdout,stderr=stderr,check=False,timeout=c['budget']['seconds']+10)
    after={p.relative_to(ROOT).as_posix():pin(p) for p in selected}
    receipt={'child_exit_code':child.returncode,'started_at_utc':started,
             'completed_at_utc':datetime.now(timezone.utc).isoformat(),
             'input_binding_after':after,'input_bytes_unchanged':after==before,
             'stdout':pin(out/'stdout.log'),'stderr':pin(out/'stderr.log'),
             'automatic_retry':False,'RFL_execution':False,'new_ruler_runtime_executed':False}
    save(out/'exit.json',receipt)
    print(json.dumps({k:v for k,v in receipt.items() if k!='input_binding_after'},sort_keys=True))
    return child.returncode if before==after else 2


if __name__=='__main__':raise SystemExit(main())
