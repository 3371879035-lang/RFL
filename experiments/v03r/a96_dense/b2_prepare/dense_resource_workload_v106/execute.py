"""Exclusive two-child serial workload capture; no native retry."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]


def meta(path):
    h=hashlib.sha256(); size=0
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            h.update(block); size += len(block)
    return {'bytes':size,'sha256':h.hexdigest()}


def save(path,data):
    with path.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(data,stream,sort_keys=True,separators=(',', ':'),ensure_ascii=True)
        stream.write('\n')


def binding(c):
    frozen=json.loads((ROOT/c['frozen_manifest']).read_bytes())['sources']
    for name,pin in frozen.items():
        assert meta(ROOT/name)['sha256']==pin,'frozen drift '+name
    names=set(frozen)|{c['frozen_manifest'],'experiments/rebuild_status_current.json'}
    for key in ('reference_input','healthy_reference','authorization','dev_lock','preserved_core','preserved_handoff'):
        spec=c[key]; assert type(spec['path']) is str and meta(ROOT/spec['path'])['sha256']==spec['sha256']
        names.add(spec['path'])
    names |= {p.relative_to(ROOT).as_posix() for p in (ROOT/'src').rglob('*.py')}
    names |= {p.relative_to(ROOT).as_posix() for p in HERE.parent.glob('*.py')}
    for folder in ('adaptive_training_v90','owned_adaptive_handoff_v92'):
        names |= {p.relative_to(ROOT).as_posix() for p in (HERE.parent/folder).glob('*.py')}
    names |= {p.relative_to(ROOT).as_posix() for p in (HERE.parent/'complete_curve_source_gates_v105/variants/normal').glob('*.py')}
    names |= {(HERE/n).relative_to(ROOT).as_posix() for n in ('resource_meter.py','workload.py','execute.py','contract.json')}
    return {n:meta(ROOT/n) for n in sorted(names)}


def main():
    c=json.loads((HERE/'contract.json').read_bytes())
    parent=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    assert parent==c['parent_commit'],'parent changed'
    assert shutil.disk_usage(ROOT).free>=c['budget']['minimum_disk_free_bytes'],'disk reserve'
    out=HERE/'evidence'
    assert not out.exists(),'exclusive capture exists; no retry'
    before=binding(c); out.mkdir()
    started=datetime.now(timezone.utc).isoformat()
    save(out/'claim.json',{'parent_commit':parent,'started_at_utc':started,'input_binding_before':before,
                          'planned_modes':['dq','patch-adaptive'],'serial_children':True,'automatic_retry':False,
                          'role':'V106_DECLARED_FULL_SCALE_ENGINEERING_RESOURCE_WORKLOAD'})
    env=dict(os.environ); env['PYTHONDONTWRITEBYTECODE']='1'
    receipts=[]
    for mode in ('dq','patch-adaptive'):
        folder=out/mode; folder.mkdir()
        command=[sys.executable,'-X','utf8','-B',str(HERE/'workload.py'),mode]
        child_start=datetime.now(timezone.utc).isoformat()
        save(folder/'claim.json',{'mode':mode,'command':command,'started_at_utc':child_start,'automatic_retry':False})
        try:
            with (folder/'stdout.log').open('xb') as stdout,(folder/'stderr.log').open('xb') as stderr:
                child=subprocess.run(command,cwd=ROOT,env=env,stdout=stdout,stderr=stderr,check=False,
                                     timeout=c['budget']['seconds_per_child']+30)
        except subprocess.TimeoutExpired:
            save(folder/'timeout.json',{'observed_at_utc':datetime.now(timezone.utc).isoformat(),
                 'native_exit_not_fabricated':True,'automatic_retry':False,'next_child_not_started':True})
            raise
        receipt={'mode':mode,'child_exit_code':child.returncode,'started_at_utc':child_start,
                 'completed_at_utc':datetime.now(timezone.utc).isoformat(),'stdout':meta(folder/'stdout.log'),
                 'stderr':meta(folder/'stderr.log'),'automatic_retry':False}
        for name in ('raw.jsonl.gz','child_summary.json'):
            if (folder/name).exists(): receipt[name]=meta(folder/name)
        save(folder/'exit.json',receipt); receipts.append(receipt)
        print(json.dumps(receipt),flush=True)
        if child.returncode!=0: break
    after=binding(c)
    complete=len(receipts)==2 and all(r['child_exit_code']==0 for r in receipts)
    final={'started_at_utc':started,'completed_at_utc':datetime.now(timezone.utc).isoformat(),
           'completed':complete,'child_receipts':receipts,'input_binding_after':after,
           'input_bytes_unchanged':before==after,'automatic_retry':False,'scientific_qualification':False}
    save(out/'exit.json',final)
    print(json.dumps({k:v for k,v in final.items() if k!='input_binding_after'}),flush=True)
    return 0 if complete and before==after else 1


if __name__=='__main__':
    raise SystemExit(main())
