from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,os,subprocess,sys,time
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(path,value):
    with path.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False)


def main():
    cap=HERE/'capture';cap.mkdir(exist_ok=False);contract=json.loads((HERE/'contract.json').read_text())
    previous=json.loads((HERE.parent/'capture/claim.json').read_text())['input_sha256'];pins={}
    for name,digest in previous.items():
        assert sha(ROOT/name)==digest,name;pins[name]=digest
    for directory in (HERE,ROOT/'src/feedback_program_v221',ROOT/'docs/feedback_math/evidence_memory_v221'):
        for p in directory.iterdir():
            if p.is_file():pins[p.relative_to(ROOT).as_posix()]=sha(p)
    for name in ('events.jsonl','probe_summary.json','stored_audit.json','exit.json'):
        p=HERE.parent/'capture'/name;pins[p.relative_to(ROOT).as_posix()]=sha(p)
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    save(cap/'claim.json',{'utc':datetime.now(timezone.utc).isoformat(),'head':head,'input_sha256':pins,'previous_inputs':len(previous),'automatic_retries':0})
    start=time.perf_counter();status={'first_run_exit':None,'audit_exit':None,'timeout':False,'automatic_retries':0}
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONUTF8':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
    try:
        with (cap/'stdout.txt').open('x',encoding='utf-8') as out,(cap/'stderr.txt').open('x',encoding='utf-8') as err:
            r=subprocess.run([sys.executable,'-X','utf8','-B',str(HERE/'probe.py')],cwd=ROOT,env=env,stdout=out,stderr=err,timeout=contract['wall_budget_seconds']);status['first_run_exit']=r.returncode
        if status['first_run_exit']==0:
            with (cap/'audit_stdout.txt').open('x',encoding='utf-8') as out,(cap/'audit_stderr.txt').open('x',encoding='utf-8') as err:
                r=subprocess.run([sys.executable,'-X','utf8','-B',str(HERE/'audit.py')],cwd=ROOT,env=env,stdout=out,stderr=err,timeout=30);status['audit_exit']=r.returncode
    except subprocess.TimeoutExpired:status['timeout']=True
    finally:
        status.update(wall_seconds=time.perf_counter()-start,input_count=len(pins),changed_inputs=[n for n,d in pins.items() if sha(ROOT/n)!=d],utc=datetime.now(timezone.utc).isoformat())
        save(cap/'exit.json',status);print(json.dumps(status,indent=2))
    return 0 if status['first_run_exit']==status['audit_exit']==0 and not status['timeout'] and not status['changed_inputs'] else 1


if __name__=='__main__':sys.exit(main())
