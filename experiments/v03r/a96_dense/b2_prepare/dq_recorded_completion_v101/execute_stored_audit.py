"""Exclusive first independent v101 stdlib stored-content review, no retry."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent/'dq_recorded_completion_v101_stored_audit.py'


def main():
    out=HERE/'evidence_stored_audit';out.mkdir(exist_ok=False)
    before=SOURCE.read_bytes();started=datetime.now(timezone.utc).isoformat()
    with (out/'stdout.log').open('xb') as stdout,(out/'stderr.log').open('xb') as stderr:
        child=subprocess.run([sys.executable,'-X','utf8','-B',str(SOURCE)],stdout=stdout,stderr=stderr,check=False,timeout=120)
    assert SOURCE.read_bytes()==before
    receipt={'child_exit_code':child.returncode,'started_at_utc':started,'completed_at_utc':datetime.now(timezone.utc).isoformat(),
        'source_sha256':hashlib.sha256(before).hexdigest(),'automatic_retry':False,'old_checker_RFL_execution':False}
    for name in ('stdout','stderr'):
        data=(out/f'{name}.log').read_bytes();receipt[name]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    with (out/'exit.json').open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(receipt,stream,sort_keys=True,separators=(',',':'),ensure_ascii=True);stream.write('\n')
    print(json.dumps(receipt,sort_keys=True));return child.returncode


if __name__=='__main__':raise SystemExit(main())
