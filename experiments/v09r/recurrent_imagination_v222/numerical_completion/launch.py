from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,os,subprocess,sys,time
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];OLD=HERE.parent/'capture'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(path,value):
    with path.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False)
def main():
    cap=HERE/'capture';cap.mkdir(exist_ok=False);contract=json.loads((HERE/'contract.json').read_text())
    pins=json.loads((OLD/'claim.json').read_text())['input_sha256']
    for name,digest in pins.items():assert sha(ROOT/name)==digest,name
    for directory in (HERE,OLD):
        for p in directory.iterdir():
            if p.is_file():pins[p.relative_to(ROOT).as_posix()]=sha(p)
    save(cap/'claim.json',{'utc':datetime.now(timezone.utc).isoformat(),'input_sha256':pins,'first_failure_exit':json.loads((OLD/'exit.json').read_text()),'environment_calls_allowed':0})
    status={'first_run_exit':None,'stored_review_exit':None,'timeout':False,'automatic_retries':0};start=time.perf_counter()
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONUTF8':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
    try:
        for file,key in [('probe.py','first_run_exit'),('review_stored.py','stored_review_exit')]:
            with (cap/(file+'.stdout.txt')).open('x',encoding='utf-8') as out,(cap/(file+'.stderr.txt')).open('x',encoding='utf-8') as err:
                r=subprocess.run([sys.executable,'-X','utf8','-B',str(HERE/file)],cwd=ROOT,env=env,stdout=out,stderr=err,timeout=contract['wall_budget_seconds'])
            status[key]=r.returncode
            if r.returncode:break
    except subprocess.TimeoutExpired:status['timeout']=True
    finally:
        status.update(wall_seconds=time.perf_counter()-start,input_count=len(pins),changed_inputs=[n for n,d in pins.items() if sha(ROOT/n)!=d],utc=datetime.now(timezone.utc).isoformat())
        save(cap/'exit.json',status);print(json.dumps(status,indent=2))
    return 0 if status['first_run_exit']==status['stored_review_exit']==0 and not status['timeout'] and not status['changed_inputs'] else 1
if __name__=='__main__':sys.exit(main())
