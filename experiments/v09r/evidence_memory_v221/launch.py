from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,os,subprocess,sys,time
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,value):
    with path.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False)


def main():
    contract=json.loads((HERE/'contract.json').read_text());cap=HERE/'capture';cap.mkdir(exist_ok=False)
    old_path=ROOT/'experiments/v09r/learnable_memory_v220/capture/claim.json';old=json.loads(old_path.read_text())['input_sha256']
    inputs={}
    for name,digest in old.items():
        actual=sha(ROOT/name)
        if actual!=digest:raise ValueError(f'Previous declared bytes changed: {name}')
        inputs[name]=actual
    for directory in (ROOT/'src/feedback_program_v221',ROOT/'docs/feedback_math/evidence_memory_v221',HERE):
        for path in directory.iterdir():
            if path.is_file():inputs[path.relative_to(ROOT).as_posix()]=sha(path)
    for name in ('RESULTS.md','USAGE.md','result_summary.json','summarize_stored.py','capture/exit.json','capture/stored_audit.json','capture/probe_summary.json'):
        path=old_path.parent.parent/name;inputs[path.relative_to(ROOT).as_posix()]=sha(path)
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    save(cap/'claim.json',{'utc':datetime.now(timezone.utc).isoformat(),'head':head,'input_sha256':inputs,'previous_declared_inputs':len(old),
                           'python':sys.executable,'contract_sha256':sha(HERE/'contract.json'),'automatic_retries':0})
    start=time.perf_counter();status={'first_run_exit':None,'audit_exit':None,'timeout':False,'automatic_retries':0}
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONUTF8':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
    try:
        with (cap/'stdout.txt').open('x',encoding='utf-8') as out,(cap/'stderr.txt').open('x',encoding='utf-8') as err:
            result=subprocess.run([sys.executable,'-X','utf8','-B',str(HERE/'run.py')],cwd=ROOT,env=env,stdout=out,stderr=err,timeout=contract['wall_budget_seconds'])
            status['first_run_exit']=result.returncode
        if status['first_run_exit']==0:
            with (cap/'audit_stdout.txt').open('x',encoding='utf-8') as out,(cap/'audit_stderr.txt').open('x',encoding='utf-8') as err:
                result=subprocess.run([sys.executable,'-X','utf8','-B',str(HERE/'audit.py')],cwd=ROOT,env=env,stdout=out,stderr=err,timeout=30)
                status['audit_exit']=result.returncode
    except subprocess.TimeoutExpired:status['timeout']=True
    finally:
        status.update(wall_seconds=time.perf_counter()-start,input_count=len(inputs),changed_inputs=[name for name,digest in inputs.items() if sha(ROOT/name)!=digest],
                      utc=datetime.now(timezone.utc).isoformat())
        save(cap/'exit.json',status);print(json.dumps(status,indent=2))
    return 0 if status['first_run_exit']==0 and status['audit_exit']==0 and not status['timeout'] and not status['changed_inputs'] else 1


if __name__=='__main__':sys.exit(main())
