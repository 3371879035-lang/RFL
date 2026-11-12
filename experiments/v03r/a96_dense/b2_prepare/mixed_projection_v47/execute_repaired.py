"""First-use exclusive mixed projection/checker captures; never retry or overwrite."""
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
import json,subprocess,sys
folder=Path(__file__).resolve().parent; root=folder.parents[4]
def digest_file(p):
    h=sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
if sys.argv[1:] not in ([],['check']): raise ValueError('only explicit check mode')
checking=bool(sys.argv[1:]); target='check_stored_corrected.py' if checking else 'candidate_corrected.py'
output=folder/('evidence_check_repaired' if checking else 'evidence_repaired'); output.mkdir(exist_ok=False)
command=[sys.executable,'-X','utf8','-B',str(folder/target)]
paths=[folder/n for n in ('contract.json','candidate.py','execute.py','check_stored.py','repair_contract.json','candidate_corrected.py','execute_repaired.py','check_stored_corrected.py')]
paths += [folder/'evidence'/n for n in ('claim.json','exit.json','stdout.log','stderr.log')]
if checking: paths += [folder/'evidence_repaired'/n for n in ('claim.json','exit.json','stdout.log','stderr.log')]
claim={'role':'KEYLESS_NATIVE_MIXED_PROJECTION_STORED_CHECK' if checking else 'KEYLESS_NATIVE_MIXED_PROJECTION_ENGINEERING',
       'command':command,'start_utc':datetime.now(timezone.utc).isoformat(),'cwd':str(root),
       'inputs':{p.relative_to(folder).as_posix():digest_file(p) for p in paths}}
with (output/'claim.json').open('x',encoding='utf8') as f: json.dump(claim,f,indent=2)
with (output/'stdout.log').open('xb') as out,(output/'stderr.log').open('xb') as err:
    child=subprocess.Popen(command,cwd=root,stdout=out,stderr=err)
    print(json.dumps({'child_pid':child.pid,'command':command,'start_utc':claim['start_utc']}),flush=True); code=child.wait()
receipt={**claim,'finish_utc':datetime.now(timezone.utc).isoformat(),'native_child_exit_code':code,
         'files':{p.name:{'bytes':p.stat().st_size,'sha256':digest_file(p)} for p in (output/'stdout.log',output/'stderr.log')},
         'scientific_PASS':False,'collection_authorized':False}
with (output/'exit.json').open('x',encoding='utf8') as f: json.dump(receipt,f,indent=2)
print(json.dumps(receipt,sort_keys=True),flush=True); sys.exit(code)


