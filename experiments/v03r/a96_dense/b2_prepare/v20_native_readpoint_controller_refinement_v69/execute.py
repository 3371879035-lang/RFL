"""Exclusive source-bound stdlib stored audit launcher. Never rerun an occupied capture."""
from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
def digest(p):
    h=sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(8388608),b''):h.update(b)
    return h.hexdigest()
def save(p,o):p.write_bytes((json.dumps(o,indent=2,ensure_ascii=True,allow_nan=False)+'\n').encode())
def main():
    assert len(sys.argv)==2 and sys.argv[1] in ('candidate','check')
    checking=sys.argv[1]=='check';target='check_stored.py' if checking else 'candidate.py'
    folder=HERE/('evidence_check' if checking else 'evidence');folder.mkdir(exist_ok=False)
    names=['contract.json','candidate.py','execute.py','check_stored.py']
    if checking:names+=['evidence/'+n for n in ('claim.json','exit.json','stdout.log','stderr.log')]
    command=[sys.executable,'-X','utf8','-B',str(HERE/target)]
    claim={'role':'STDLIB_BOUND_NATIVE_READPOINT_CONTROLLER_STORED_CHECK' if checking else 'STDLIB_BOUND_NATIVE_READPOINT_CONTROLLER_STORED_REFINEMENT',
           'command':command,'start_utc':datetime.now(timezone.utc).isoformat(),'cwd':str(ROOT),
           'inputs':{n:digest(HERE/n) for n in names}}
    save(folder/'claim.json',claim)
    with (folder/'stdout.log').open('xb') as out,(folder/'stderr.log').open('xb') as err:
        child=subprocess.run(command,cwd=ROOT,stdout=out,stderr=err)
    receipt={**claim,'finish_utc':datetime.now(timezone.utc).isoformat(),'native_child_exit_code':child.returncode,
        'files':{n:{'bytes':(folder/n).stat().st_size,'sha256':digest(folder/n)} for n in ('stdout.log','stderr.log')},
        'scientific_PASS':False,'collection_authorized':False}
    save(folder/'exit.json',receipt);print(json.dumps(receipt,ensure_ascii=True));raise SystemExit(child.returncode)
if __name__=='__main__':main()



