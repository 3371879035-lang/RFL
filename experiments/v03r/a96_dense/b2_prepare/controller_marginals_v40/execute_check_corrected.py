"""First-use exclusive native pure-X counting/checker captures; never retry or overwrite."""
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
import json,subprocess,sys
folder=Path(__file__).resolve().parent; root=folder.parents[4]
if sys.argv[1:]:raise ValueError('no options')
checking=True;target='check_stored_corrected.py'
output=folder/'evidence_check_corrected';output.mkdir(exist_ok=False)
command=[sys.executable,'-X','utf8','-B',str(folder/target)]
paths=[folder/n for n in ('contract.json','candidate.py','execute.py','check_stored.py','repair_contract.json','check_stored_corrected.py','execute_check_corrected.py')]
paths += [folder/d/n for d in ('evidence','evidence_check') for n in ('claim.json','exit.json','stdout.log','stderr.log')]
claim={'role':'KEYLESS_PURE_X_MARGINAL_STORED_CHECK' if checking else 'KEYLESS_PURE_X_MARGINAL_ARITHMETIC',
       'command':command,'start_utc':datetime.now(timezone.utc).isoformat(),'cwd':str(root),
       'inputs':{p.relative_to(folder).as_posix():sha256(p.read_bytes()).hexdigest() for p in paths}}
with (output/'claim.json').open('x',encoding='utf8') as f: json.dump(claim,f,indent=2)
with (output/'stdout.log').open('xb') as out,(output/'stderr.log').open('xb') as err:
    child=subprocess.Popen(command,cwd=root,stdout=out,stderr=err)
    print(json.dumps({'child_pid':child.pid,'command':command,'start_utc':claim['start_utc']}),flush=True); code=child.wait()
receipt={**claim,'finish_utc':datetime.now(timezone.utc).isoformat(),'native_child_exit_code':code,
         'files':{p.name:{'bytes':p.stat().st_size,'sha256':sha256(p.read_bytes()).hexdigest()} for p in (output/'stdout.log',output/'stderr.log')},
         'scientific_PASS':False,'collection_authorized':False}
with (output/'exit.json').open('x',encoding='utf8') as f: json.dump(receipt,f,indent=2)
print(json.dumps(receipt,sort_keys=True),flush=True); sys.exit(code)
