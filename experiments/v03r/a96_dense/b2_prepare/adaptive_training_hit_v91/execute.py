"""One new true-hit validation child; preserve failed v90, never run its fixture."""
from datetime import datetime,timezone
import hashlib,json,os
from pathlib import Path
import subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]


def meta(path):return {'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def save(path,data):
    with path.open('x',encoding='utf-8',newline='\n') as f:
        json.dump(data,f,sort_keys=True,separators=(',',':'),ensure_ascii=True);f.write('\n')


def binding(c):
    frozen=json.loads((ROOT/c['frozen_manifest']).read_bytes())['sources']
    for n,h in frozen.items():
        if meta(ROOT/n)['sha256']!=h:raise RuntimeError('frozen source drift '+n)
    for n,h in c['preserved_v90_files'].items():
        if meta(ROOT/n)!=h:raise RuntimeError('failed v90/core bytes changed '+n)
    names=set(frozen)|set(c['preserved_v90_files'])|{c['frozen_manifest'],c['reference_input']['path']}
    names|={str(p.relative_to(ROOT)).replace('\\','/') for p in HERE.iterdir() if p.is_file()}
    return {n:meta(ROOT/n) for n in sorted(names)}


def main():
    c=json.loads((HERE/'contract.json').read_bytes())
    parent=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if parent!=c['parent_commit']:raise RuntimeError('wrong parent; no child')
    out=HERE/'evidence'
    if out.exists():raise RuntimeError('exclusive new capture exists; no retry')
    before=binding(c);out.mkdir();start=datetime.now(timezone.utc).isoformat()
    cmd=[sys.executable,'-X','utf8','-B',str(HERE/'test_actual_hits.py')]
    save(out/'claim.json',{'parent_commit':parent,'command':cmd,'started_at_utc':start,
        'input_binding_before':before,'role':'NEW_TRUE_START_HIT_INPUTS_NOT_V90_FIXTURE_RERUN','automatic_retry':False})
    env=dict(os.environ);env['PYTHONDONTWRITEBYTECODE']='1'
    with (out/'stdout.log').open('xb') as stdout,(out/'stderr.log').open('xb') as stderr:
        result=subprocess.run(cmd,cwd=ROOT,env=env,stdout=stdout,stderr=stderr,check=False)
    after=binding(c)
    receipt={'child_exit_code':result.returncode,'started_at_utc':start,
        'completed_at_utc':datetime.now(timezone.utc).isoformat(),
        'stdout':meta(out/'stdout.log'),'stderr':meta(out/'stderr.log'),
        'input_binding_after':after,'input_bytes_unchanged':before==after,
        'failed_v90_preserved':True,'automatic_retry':False,'scientific_qualification':False}
    receipt['capture_budget_met']=(receipt['stdout']['bytes']<=c['budget']['stdout_bytes'] and
                                   receipt['stderr']['bytes']<=c['budget']['stderr_bytes'])
    save(out/'exit.json',receipt)
    print(json.dumps({k:v for k,v in receipt.items() if k!='input_binding_after'}))
    return result.returncode if before==after and receipt['capture_budget_met'] else 2


if __name__=='__main__':raise SystemExit(main())
