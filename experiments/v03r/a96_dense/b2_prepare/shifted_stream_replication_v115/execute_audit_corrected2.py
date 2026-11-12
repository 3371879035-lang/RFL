"""Run the second explicitly corrected stored audit without native rerun."""
from datetime import datetime, timezone
import hashlib, json, os, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]

def meta(path):
    h, size = hashlib.sha256(), 0
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block); size += len(block)
    return {'bytes': size, 'sha256': h.hexdigest()}

def save(path, payload):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(payload, stream, ensure_ascii=True, sort_keys=True, separators=(',', ':')); stream.write('\n')

def main():
    old=json.loads((HERE/'evidence/exit.json').read_bytes())
    assert old['completed'] is True and old['input_bytes_unchanged'] is True and old['automatic_retry'] is False
    capture=HERE/'evidence_stored_audit_corrected2'; assert not capture.exists(); capture.mkdir()
    started=datetime.now(timezone.utc).isoformat(); command=[sys.executable,'-X','utf8','-B',str(HERE/'audit_stored_corrected2.py')]
    save(capture/'claim.json',{'started_at_utc':started,'command':command,'first_audit_failure_preserved':True,
        'earlier_corrected_audit_failure_preserved':True,'corrections':['engineering_n_eval->evaluation_scenes','v112_motivation->v115_motivation'],
        'native_workloads_rerun':False,'old_checker_import_or_execution':False,'automatic_retry':False,'scientific_qualification':False})
    env=dict(os.environ);env['PYTHONDONTWRITEBYTECODE']='1';clock=time.monotonic()
    with (capture/'stdout.log').open('xb') as stdout,(capture/'stderr.log').open('xb') as stderr:
        child=subprocess.run(command,cwd=ROOT,env=env,stdout=stdout,stderr=stderr,check=False,timeout=900)
    result={'started_at_utc':started,'completed_at_utc':datetime.now(timezone.utc).isoformat(),'elapsed_seconds':time.monotonic()-clock,
        'corrected_audit_exit_code':child.returncode,'stdout':meta(capture/'stdout.log'),'stderr':meta(capture/'stderr.log'),
        'stored_audit_result_corrected2':meta(HERE/'stored_audit_result_corrected2.json') if (HERE/'stored_audit_result_corrected2.json').is_file() else None,
        'native_workloads_rerun':False,'old_checker_import_or_execution':False,'first_audit_failure_preserved':True,
        'earlier_corrected_audit_failure_preserved':True,'automatic_retry':False,'scientific_qualification':False}
    save(capture/'exit.json',result);print(json.dumps(result,ensure_ascii=True,sort_keys=True,separators=(',',':')),flush=True)
    return 0 if child.returncode==0 and result['stored_audit_result_corrected2'] is not None else 1

if __name__=='__main__': raise SystemExit(main())
