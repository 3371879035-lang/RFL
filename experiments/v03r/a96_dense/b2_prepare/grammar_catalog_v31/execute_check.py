"""One exclusive stored checker capture, no catalog/experiment reacquisition."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

folder=Path(__file__).resolve().parent
root=folder.parents[4]
output=folder/'evidence_check'
output.mkdir(exist_ok=False)
command=[sys.executable,'-X','utf8','-B',str(folder/'check_stored.py')]
claim={'role':'STDLIB_FULL_STORED_CATALOG_CHECK_NOT_SCIENCE','command':command,
       'start_utc':datetime.now(timezone.utc).isoformat(),'cwd':str(root),
       'inputs':{p.relative_to(folder).as_posix():sha256(p.read_bytes()).hexdigest() for p in
           [folder/'check_stored.py',Path(__file__)]+[folder/'evidence'/n for n in ('claim.json','exit.json','stdout.log','stderr.log')]}}
with (output/'claim.json').open('x',encoding='utf8') as stream:json.dump(claim,stream,indent=2)
with (output/'stdout.log').open('xb') as stdout,(output/'stderr.log').open('xb') as stderr:
    process=subprocess.Popen(command,cwd=root,stdout=stdout,stderr=stderr)
    code=process.wait()
receipt={**claim,'finish_utc':datetime.now(timezone.utc).isoformat(),'native_child_exit_code':code,
         'files':{p.name:{'bytes':p.stat().st_size,'sha256':sha256(p.read_bytes()).hexdigest()} for p in
                   (output/'stdout.log',output/'stderr.log')}}
with (output/'exit.json').open('x',encoding='utf8') as stream:json.dump(receipt,stream,indent=2)
print(json.dumps(receipt,sort_keys=True),flush=True)
sys.exit(code)
