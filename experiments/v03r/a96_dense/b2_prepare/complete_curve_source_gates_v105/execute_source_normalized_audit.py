"""Exclusive first stored-content audit capture; never reruns native RFL."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent

def meta(path):
    return {'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}

def save(path, data):
    with path.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(data,stream,sort_keys=True,separators=(',',':'),ensure_ascii=True)
        stream.write('\n')

def main():
    out=HERE/'evidence_stored_audit_source_normalized'
    if out.exists():
        raise RuntimeError('audit already captured; no retry')
    out.mkdir()
    command=[sys.executable,'-X','utf8','-B',str(HERE/'audit_source_normalized.py')]
    start=datetime.now(timezone.utc).isoformat()
    save(out/'claim.json',{'command':command,'started_at_utc':start,'audit_source':meta(HERE/'audit_source_normalized.py'),'automatic_retry':False})
    with (out/'stdout.log').open('xb') as stdout,(out/'stderr.log').open('xb') as stderr:
        run=subprocess.run(command,cwd=HERE,stdout=stdout,stderr=stderr,check=False,timeout=180)
    data={'child_exit_code':run.returncode,'started_at_utc':start,'completed_at_utc':datetime.now(timezone.utc).isoformat(),
          'stdout':meta(out/'stdout.log'),'stderr':meta(out/'stderr.log'),'automatic_retry':False}
    save(out/'exit.json',data)
    print(json.dumps(data))
    return run.returncode

if __name__=='__main__':
    raise SystemExit(main())


