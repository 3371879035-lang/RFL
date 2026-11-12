"""Exclusive complete Git formatting diagnostic; no experiment/source mutation."""
from pathlib import Path
from datetime import datetime,timezone
from hashlib import sha256
import json,subprocess,sys
p=Path(__file__).resolve().parent;r=p.parents[4];d=p/'evidence_git_format';d.mkdir(exist_ok=False)
cmd=['git','-c','core.autocrlf=false','diff','--cached','--check']
index=subprocess.check_output(['git','ls-files','--stage','-z'],cwd=r)
names=subprocess.check_output(['git','diff','--cached','--name-only','-z'],cwd=r)
cl={'role':'TOOL_FORMAT_DIAGNOSTIC_NOT_NATIVE_MECHANISM_OR_SCIENTIFIC_GATE','start_utc':datetime.now(timezone.utc).isoformat(),'command':cmd,'HEAD':subprocess.check_output(['git','rev-parse','HEAD'],cwd=r).decode().strip(),'staged_names':sorted(n.decode() for n in names.split(b'\0') if n),'full_index_sha256':sha256(index).hexdigest(),'helper_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),'no_experiment_reexecution':True}
with (d/'claim.json').open('x',encoding='utf8') as f:json.dump(cl,f,indent=2)
with (d/'stdout.log').open('xb') as out,(d/'stderr.log').open('xb') as err:code=subprocess.run(cmd,cwd=r,stdout=out,stderr=err).returncode
def dig(f):
 h=sha256()
 with f.open('rb') as q:
  for b in iter(lambda:q.read(1048576),b''):h.update(b)
 return {'bytes':f.stat().st_size,'sha256':h.hexdigest()}
ex={**cl,'finish_utc':datetime.now(timezone.utc).isoformat(),'native_git_exit_code':code,'files':{n:dig(d/n) for n in ('stdout.log','stderr.log')},'same_index_after':subprocess.check_output(['git','ls-files','--stage','-z'],cwd=r)==index,'scientific_PASS':False}
with (d/'exit.json').open('x',encoding='utf8') as f:json.dump(ex,f,indent=2)
assert code==1 and ex['same_index_after']
print(json.dumps(ex,sort_keys=True))
