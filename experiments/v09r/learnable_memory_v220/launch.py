"""One bounded invocation; preserve failures and all original bytes."""
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,os,subprocess,sys,time
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):
    with path.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False)


def main():
    contract=json.loads((HERE/'contract.json').read_text());capture=HERE/'capture';capture.mkdir(exist_ok=False)
    previous=ROOT/'experiments/v09r/continuous_prior_v219/contract.json'
    old=json.loads(previous.read_text())['input_sha256']
    inputs={}
    for name,digest in old.items():
        path=ROOT/name;actual=sha(path)
        if actual!=digest:raise ValueError(f'Prior declared source changed: {name}')
        inputs[name]=actual
    for directory in (ROOT/'src/feedback_program_v220',ROOT/'docs/feedback_math/learnable_memory_v220',HERE):
        for path in directory.iterdir():
            if path.is_file():inputs[path.relative_to(ROOT).as_posix()]=sha(path)
    for name in ('contract.json','result_summary.json','RESULTS.md','stored_review.json','ranking_diagnostic.json'):
        path=previous.parent/name;inputs[path.relative_to(ROOT).as_posix()]=sha(path)
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    write(capture/'claim.json',{'utc':datetime.now(timezone.utc).isoformat(),'head':head,'python':sys.executable,
                              'input_sha256':inputs,'previous_declared_input_count':len(old),'automatic_retries':0,'contract_sha256':sha(HERE/'contract.json')})
    start=time.perf_counter();status={'first_run_exit':None,'audit_exit':None,'timeout':False}
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONUTF8':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
    try:
        with (capture/'stdout.txt').open('x',encoding='utf-8') as out,(capture/'stderr.txt').open('x',encoding='utf-8') as err:
            result=subprocess.run([sys.executable,'-X','utf8','-B',str(HERE/'run.py')],cwd=ROOT,env=env,
                                  stdout=out,stderr=err,timeout=contract['wall_budget_seconds'])
            status['first_run_exit']=result.returncode
        if status['first_run_exit']==0:
            with (capture/'audit_stdout.txt').open('x',encoding='utf-8') as out,(capture/'audit_stderr.txt').open('x',encoding='utf-8') as err:
                audit=subprocess.run([sys.executable,'-X','utf8','-B',str(HERE/'audit.py')],cwd=ROOT,env=env,stdout=out,stderr=err,timeout=30)
                status['audit_exit']=audit.returncode
    except subprocess.TimeoutExpired:
        status['timeout']=True
    finally:
        status['wall_seconds']=time.perf_counter()-start
        changed=[name for name,digest in inputs.items() if sha(ROOT/name)!=digest]
        status.update(input_count=len(inputs),changed_inputs=changed,utc=datetime.now(timezone.utc).isoformat(),automatic_retries=0)
        write(capture/'exit.json',status);print(json.dumps(status,indent=2))
    return 0 if status['first_run_exit']==0 and status['audit_exit']==0 and not changed and not status['timeout'] else 1


if __name__=='__main__':sys.exit(main())
