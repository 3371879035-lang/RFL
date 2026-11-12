"""Exclusive first v112 integrated recovery-observability workload, two serial children, no retry."""
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
    for key in ('reference_input','healthy_reference','authorization','dev_lock','preserved_core','preserved_handoff',
                'preserved_curve','preserved_external','preserved_resource_meter','preserved_learning','preserved_td',
                'preserved_whole_ruler','preserved_whole_instrument','preserved_recorded','preserved_transfer',
                'preserved_wire_boundary','recovery_observability_document'):
        spec=c[key]; assert type(spec['path']) is str and meta(ROOT/spec['path'])['sha256']==spec['sha256']
        names.add(spec['path'])
    names |= {p.relative_to(ROOT).as_posix() for p in (ROOT/'src').rglob('*.py')}
    names |= {p.relative_to(ROOT).as_posix() for p in HERE.parent.glob('*.py')}
    for folder in ('adaptive_training_v90','owned_adaptive_handoff_v92'):
        names |= {p.relative_to(ROOT).as_posix() for p in (HERE.parent/folder).glob('*.py')}
    names |= {p.relative_to(ROOT).as_posix() for p in (HERE.parent/'complete_curve_source_gates_v105/variants/normal').glob('*.py')}
    # Only these three new files execute in the native flow. Concurrently
    # drafted new auditor/summarizer files are deliberately not native inputs.
    names |= {(HERE/n).relative_to(ROOT).as_posix() for n in ('workload.py','execute.py','contract.json')}
    bank=c['preserved_bank']
    assert meta(ROOT/bank['path'])['sha256']==bank['sha256'],'validated bank source drift'
    names.add(bank['path'])
    gate=c['predecessor_gate']
    for role in ('native','stored'):
        spec=gate[role]
        assert type(spec['sha256']) is str and len(spec['sha256'])==64,'v107 gate pin unresolved: '+role
        assert meta(ROOT/spec['path'])['sha256']==spec['sha256'],'v107 gate evidence drift: '+role
        names.add(spec['path'])
    native=json.loads((ROOT/gate['native']['path']).read_bytes())
    assert native['child_exit_code']==0 and native['input_bytes_unchanged'],'v107 native gate did not pass'
    stored=json.loads((ROOT/gate['stored']['path']).read_bytes())
    assert stored['schema']=='V107_INDEPENDENT_STDLIB_STORED_READPATH_REVIEW','v107 stored gate schema'
    assert stored['native_child_exit_preserved']==0 and stored['native_methods']==4 and stored['native_failure_error_skip']==0,'v107 stored native outcome'
    assert len(stored['eight_comparisons'])==8 and stored['eight_precall_rejections_zero_native'] is True,'v107 stored differential/guards incomplete'
    assert stored['postscene_partial_raw_returns']==1 and stored['postscene_accepted_bank_scenes']==0 and stored['partial_has_no_mean'] is True,'v107 partial gate incomplete'
    return {n:meta(ROOT/n) for n in sorted(names)}


def main():
    c=json.loads((HERE/'contract.json').read_bytes())
    assert c['modes']==['dq','patch-adaptive'],'fixed serial mode order changed'
    parent=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    assert parent==c['parent_commit'],'parent changed'
    assert shutil.disk_usage(ROOT).free>=c['budget']['minimum_disk_free_bytes'],'disk reserve'
    out=HERE/'evidence'
    assert not out.exists(),'exclusive capture exists; no retry'
    before=binding(c); out.mkdir()
    started=datetime.now(timezone.utc).isoformat()
    save(out/'claim.json',{'parent_commit':parent,'started_at_utc':started,'input_binding_before':before,
                          'planned_modes':c['modes'],'serial_children':True,'automatic_retry':False,
                          'fresh_science_or_workload_keys':0,'formal_collection_enabled':False,
                          'role':'V112_FIRST_SAME_PAIR_WHOLE_AND_RECOVERY_OBSERVABILITY_ENGINEERING_CANARY'})
    env=dict(os.environ); env['PYTHONDONTWRITEBYTECODE']='1'
    receipts=[]
    for mode in c['modes']:
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
    complete=len(receipts)==len(c['modes']) and all(r['child_exit_code']==0 for r in receipts)
    final={'started_at_utc':started,'completed_at_utc':datetime.now(timezone.utc).isoformat(),
           'completed':complete,'child_receipts':receipts,'input_binding_after':after,
           'input_bytes_unchanged':before==after,'automatic_retry':False,'scientific_qualification':False,
           'formal_collection_enabled':False,'fresh_science_or_workload_keys':0}
    save(out/'exit.json',final)
    print(json.dumps({k:v for k,v in final.items() if k!='input_binding_after'}),flush=True)
    return 0 if complete and before==after else 1


if __name__=='__main__':
    raise SystemExit(main())

