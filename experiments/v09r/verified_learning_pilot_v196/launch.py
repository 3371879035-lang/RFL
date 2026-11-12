"""One exclusive native attempt; retain timeout/partial and never retry."""
import datetime,hashlib,json,subprocess,sys,time
from pathlib import Path
import psutil
HERE=Path(__file__).resolve().parent
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
with (HERE/'launch_claim.json').open('x',encoding='utf-8') as f:
    json.dump(dict(started_utc=utc(),command=[sys.executable,'-X','utf8','-B','experiment.py']),f)
started=time.perf_counter();peak=0;error=None
with (HERE/'native.stdout.log').open('xb') as out,(HERE/'native.stderr.log').open('xb') as err:
    p=subprocess.Popen([sys.executable,'-X','utf8','-B',str(HERE/'experiment.py')],cwd=HERE,stdout=out,stderr=err)
    while p.poll() is None:
        root=psutil.Process(p.pid)
        processes=[root]+root.children(recursive=True)
        ram=sum(x.memory_info().rss for x in processes if x.is_running())
        peak=max(peak,ram)
        if time.perf_counter()-started>1800 or ram>17179869184:
            error='WALL_OR_RAM_BUDGET'
            for child in reversed(processes[1:]):
                if child.is_running():child.kill()
            if p.poll() is None:p.kill()
            break
        time.sleep(2)
    code=p.wait()
row=dict(exit_code=code,interruption=error,wall_seconds=time.perf_counter()-started,
         peak_tree_rss=peak,finished_utc=utc())
with (HERE/'native_exit.json').open('x',encoding='utf-8') as f:json.dump(row,f,indent=2)
print(json.dumps(row),flush=True)
sys.exit(code if error is None else 1)
