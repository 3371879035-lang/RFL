"""One exclusive first integration run, immutable inputs, no automatic retry."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
PREP=ROOT/'experiments/v03r/a96_dense/b2_prepare'

def meta(p):
    data=p.read_bytes()
    return {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}

def save(p,x):
    with p.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(x,stream,sort_keys=True,ensure_ascii=True,separators=(',',':'));stream.write('\n')

def inputs():
    manifest=json.loads((ROOT/'experiments/v03r/a96_dense/pipeline/frozen_inputs.json').read_bytes())
    for name,sha in manifest['sources'].items():
        assert meta(ROOT/name)['sha256']==sha,'frozen source drift '+name
    files={ROOT/name for name in manifest['sources']}
    files.update((ROOT/'src').rglob('*.py'))
    files.update(HERE/n for n in ('contract.json','execute.py','workload.py','evidence_selector.py','audit_stored.py'))
    files.update({ROOT/'experiments/rebuild_status_current.json',
                  ROOT/'experiments/v03r/a96_dense/pipeline/frozen_inputs.json',
                  HERE.parent/'failure_only_orchestration/orchestration.py',
                  HERE.parent/'observed_task_loop_v117/task_loop.py',
                  HERE.parent/'learned_candidate_choice_v118/candidate_loop.py',
                  HERE.parent/'factual_address_choice_v119/selector.py',
                  HERE.parent/'factual_address_choice_v119/evidence/raw.jsonl',
                  HERE.parent/'position_transfer_v120/frozen_parameters.json',
                  PREP/'adaptive_training_v90/adaptive_training.py',
                  PREP/'complete_curve_source_gates_v105/variants/normal/td.py',
                  PREP/'complete_curve_source_gates_v105/variants/normal/learning.py',
                  PREP/'grammar_catalog_v31/evidence/stdout.log'})
    return {p.relative_to(ROOT).as_posix():meta(p) for p in sorted(files)}

def main():
    c=json.loads((HERE/'contract.json').read_bytes())
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    assert head==c['parent_commit'],'parent moved before exclusive run'
    out=HERE/'evidence';assert not out.exists(),'capture exists, no retry'
    before=inputs();out.mkdir()
    started=datetime.now(timezone.utc).isoformat();clock=time.monotonic()
    command=[sys.executable,'-X','utf8','-B',str(HERE/'workload.py')]
    save(out/'claim.json',{'started_at_utc':started,'command':command,'parent_commit':head,
         'input_binding_before':before,'automatic_retry':False,'new_keys':0,'formal_collection':False})
    env=dict(os.environ);env['PYTHONDONTWRITEBYTECODE']='1'
    try:
        with (out/'stdout.log').open('xb') as stdout,(out/'stderr.log').open('xb') as stderr:
            child=subprocess.run(command,cwd=ROOT,env=env,stdout=stdout,stderr=stderr,
                                 check=False,timeout=c['budget']['seconds']+15)
    except subprocess.TimeoutExpired:
        save(out/'timeout.json',{'observed_at_utc':datetime.now(timezone.utc).isoformat(),
             'native_exit_not_fabricated':True,'automatic_retry':False})
        raise
    after=inputs()
    result={'started_at_utc':started,'completed_at_utc':datetime.now(timezone.utc).isoformat(),
            'wall_seconds':time.monotonic()-clock,'child_exit_code':child.returncode,
            'input_binding_after':after,'input_bytes_unchanged':before==after,
            'stdout':meta(out/'stdout.log'),'stderr':meta(out/'stderr.log'),
            'raw':meta(out/'raw.jsonl') if (out/'raw.jsonl').exists() else None,
            'automatic_retry':False,'scientific_qualification':False,'new_keys':0,'formal_collection':False}
    save(out/'exit.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='input_binding_after'},sort_keys=True),flush=True)
    return 0 if child.returncode==0 and before==after else 1

if __name__=='__main__':raise SystemExit(main())
