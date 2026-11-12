"""One fixed, bounded fresh comparison. No retry or outcome-dependent extension."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
GROUPS=('soft-learned',)


def write(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def verify():
    pins=json.loads((HERE/'input_pins.json').read_text(encoding='utf-8'))
    changed=[p for p,h in pins.items() if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h]
    if changed: raise RuntimeError(repr(changed))
    return len(pins)


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m)
    return m


def worker(cap,domain,seed):
    import torch
    torch.set_num_threads(1);torch.set_num_interop_threads(1)
    d=cap/f'{domain}_{seed}';d.mkdir(exist_ok=False)
    start=time.time()
    try:
        core=load('core',HERE/'core.py')
        learn=load('learning',HERE/'learning.py')
        bank=core.P.MapBank(ROOT/'experiments/v09r/spatial_feedback_v178/evidence_prepare/maps') if domain=='pursuit' else None
        agents={g:learn.Agent(domain,seed,g,bank) for g in GROUPS}
        assert len(set(core.fingerprint(a.state.net) for a in agents.values()))==1
        write(d/'process.json',dict(pid=os.getpid(),domain=domain,seed=seed,start=start,
              parameters=core.count_parameters(agents['soft-learned'].state.net),initial_weights_identical=True))
        evaluations={};costs={g:0. for g in GROUPS}
        for r in range(7):
            if r:
                receipts={}
                order=GROUPS
                for g in order:
                    t=time.perf_counter(); receipts[g]=agents[g].train_round(d,r)
                    costs[g]+=time.perf_counter()-t
                write(d/f'round{r:04d}.json',dict(round=r,groups=receipts,training_seconds=costs))
            if r in (0,3,6):
                result={g:{str(e):a.evaluate(32,e,phase='v198-report-v229') for e in (0.,.1)} for g,a in agents.items()}
                evaluations[str(r)]=result
                write(d/f'evaluation{r:04d}.json',dict(round=r,results=result))
        torch.save({g:a.checkpoint() for g,a in agents.items()},d/'final.pt')
        write(d/'result.json',dict(domain=domain,seed=seed,evaluations=evaluations,training_seconds=costs,
              counts={g:a.counts for g,a in agents.items()},memory_nodes={g:len(a.memory_bank.nodes) if hasattr(a,'memory_bank') else len(a.memory) for g,a in agents.items()},
              complete_failed_states={g:len(a.failed_sources) for g,a in agents.items()},seconds=time.time()-start))
        write(d/'exit.json',dict(exit_code=0,input_count=verify(),seconds=time.time()-start,retry=0))
    except BaseException:
        write(d/'failure.json',dict(error=traceback.format_exc(),seconds=time.time()-start,retry=0));raise


def main():
    cap=HERE/'pilot_run1';cap.mkdir(exist_ok=False)
    start=time.time();count=verify()
    contract=json.loads((HERE/'contract.json').read_text(encoding='utf-8'))
    write(cap/'claim.json',dict(start=start,contract=contract,input_count=count))
    children=[];handles=[]
    try:
        for domain in ('generic','pursuit'):
            for seed in (271,277,283):
                out=(cap/f'{domain}_{seed}.stdout.log').open('xb');err=(cap/f'{domain}_{seed}.stderr.log').open('xb')
                handles.extend((out,err))
                p=subprocess.Popen([sys.executable,'-X','utf8','-B',str(HERE/'run.py'),'--worker',domain,'--seed',str(seed)],cwd=ROOT,
                    stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
                children.append(p)
        write(cap/'processes.json',dict(supervisor=os.getpid(),pids=[p.pid for p in children]))
        while any(p.poll() is None for p in children):
            if any(p.poll() not in (None,0) for p in children): raise RuntimeError('A worker failed; partial evidence retained')
            if time.time()-start>900: raise TimeoutError('Fixed wall budget reached; no retry')
            time.sleep(5)
        write(cap/'exit.json',dict(exit_code=0,seconds=time.time()-start,input_count=verify(),rounds=6,retries=0))
    except BaseException:
        write(cap/'failure.json',dict(error=traceback.format_exc(),seconds=time.time()-start,retries=0));raise
    finally:
        for p in children:
            if p.poll() is None:
                subprocess.run(['taskkill.exe','/PID',str(p.pid),'/T','/F'],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
        for h in handles:h.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--worker');parser.add_argument('--seed',type=int)
    args=parser.parse_args()
    if args.worker:worker(HERE/'pilot_run1',args.worker,args.seed)
    else:main()
