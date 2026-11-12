"""Exclusive first stdlib audit, preserving the native timeout/partial evidence."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent/'owned_whole_completion_v98_stored_audit.py'


def main():
    out=HERE/'evidence_stored_audit';out.mkdir(exist_ok=False)
    b=SOURCE.read_bytes();started=datetime.now(timezone.utc).isoformat()
    with (out/'stdout.log').open('xb') as stdout,(out/'stderr.log').open('xb') as stderr:
        child=subprocess.run([sys.executable,'-X','utf8','-B',str(SOURCE)],stdout=stdout,stderr=stderr,check=False,timeout=120)
    assert SOURCE.read_bytes()==b
    receipt={'child_exit_code':child.returncode,'started_at_utc':started,
        'completed_at_utc':datetime.now(timezone.utc).isoformat(),'source_sha256':hashlib.sha256(b).hexdigest(),
        'automatic_retry':False,'old_checker_or_RFL_execution':False}
    for name in ('stdout','stderr'):
        data=(out/f'{name}.log').read_bytes();receipt[name]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    with (out/'exit.json').open('x',encoding='utf-8',newline='\n') as f:
        json.dump(receipt,f,sort_keys=True,separators=(',',':'),ensure_ascii=True);f.write('\n')
    print(json.dumps(receipt,sort_keys=True));return child.returncode


if __name__=='__main__':raise SystemExit(main())
