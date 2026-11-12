"""Independent seed workers; round barriers and an owned Windows process-tree budget."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]

def write(path,value):
    p=Path(path); t=p.with_suffix(p.suffix+'.tmp')
    t.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8');t.replace(p)

def pins():
    expected=json.loads((HERE/'input_pins.json').read_text(encoding='utf-8'))
    changed=[p for p,h in expected.items() if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h]
    if changed: raise RuntimeError('Input changes: '+repr(changed))
    return len(expected)

def worker(args):
    import torch
    torch.set_num_threads(1);torch.set_num_interop_threads(1)
    from core import P,GROUPS,Network,count_parameters,fingerprint
    from learning import Agent
    cap=Path(args.capture); d=cap/f'{args.domain}_seed{args.seed}';d.mkdir(exist_ok=False)
    write(d/'process.json',dict(pid=os.getpid(),start=time.time(),domain=args.domain,seed=args.seed))
    try:
        bank=P.MapBank(ROOT/'experiments/v09r/spatial_feedback_v178/evidence_prepare/maps') if args.domain=='pursuit' else None
        agents={g:Agent(args.domain,args.seed,g,bank) for g in GROUPS}
        assert len(set(fingerprint(a.state.net) for a in agents.values()))==1
        write(d/'parameters.json',count_parameters(agents[GROUPS[0]].state.net))
        initial={g:{str(e):a.evaluate(args.eval_n,e) for e in (0.,.1)} for g,a in agents.items()}
        write(d/'initial.json',dict(round=0,results=initial,finished=time.time()))
        last=0
        while True:
            command=cap/f'command{last+1:04d}.json'
            if not command.exists():
                if (cap/'finalize.json').exists(): break
                time.sleep(1);continue
            cfg=json.loads(command.read_text())
            if cfg['round']!=last+1: raise RuntimeError('Chronology mismatch')
            start=time.time(); results=[]
            # Rotate execution order without changing per-seed temporal order.
            ordered=GROUPS[last%len(GROUPS):]+GROUPS[:last%len(GROUPS)]
            for g in ordered:
                results.append(agents[g].train_round(d,last+1))
            last+=1
            ck={g:dict(network=a.state.net.state_dict(),memory=a.memory,steps=a.steps,counts=a.counts) for g,a in agents.items()}
            torch.save(ck,d/f'round{last:04d}.pt')
            write(d/f'round{last:04d}.json',dict(round=last,seconds=time.time()-start,results=results,finished=time.time()))
        final={g:{str(e):a.evaluate(args.eval_n,e) for e in (0.,.1)} for g,a in agents.items()}
        torch.save({g:a.checkpoint() for g,a in agents.items()},d/'final.pt')
        write(d/'final.json',dict(round=last,results=final,finished=time.time(),steps_per_group=next(iter(agents.values())).steps))
        write(d/'exit.json',dict(exit_code=0,round=last,input_count=pins(),retry=0))
    except BaseException:
        write(d/'failure.json',dict(error=traceback.format_exc(),time=time.time(),retry=0))
        raise

def kill_owned(process):
    if process.poll() is None:
        r=subprocess.run(['taskkill.exe','/PID',str(process.pid),'/T','/F'],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
        return dict(pid=process.pid,taskkill=r.returncode)
    return None

def supervisor(args):
    cap=Path(args.capture); start=time.time(); children=[]; handles=[]
    duration=1800 if args.smoke else 10800
    seeds=[191] if args.smoke else [137,149,163]
    eval_n=4 if args.smoke else 32
    tasks=[(domain,seed) for domain in ('generic','pursuit') for seed in seeds]
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
    try:
        for domain,seed in tasks:
            out=(cap/f'{domain}_{seed}.stdout.log').open('xb');err=(cap/f'{domain}_{seed}.stderr.log').open('xb')
            handles.extend([out,err])
            cmd=[sys.executable,'-X','utf8','-B',str(HERE/'runtime.py'),'worker','--capture',str(cap),'--domain',domain,'--seed',str(seed),'--eval-n',str(eval_n)]
            p=subprocess.Popen(cmd,cwd=str(ROOT),stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
            children.append(p)
        write(cap/'processes.json',dict(supervisor_pid=os.getpid(),workers=[dict(domain=d,seed=s,pid=p.pid) for (d,s),p in zip(tasks,children)]))
        folders=[cap/f'{d}_seed{s}' for d,s in tasks]
        def barrier(name):
            while not all((f/name).exists() for f in folders):
                for p in children:
                    if p.poll() is not None: raise RuntimeError(f'Worker exited before {name}: PID {p.pid}, code {p.returncode}')
                if time.time()-start>duration: raise TimeoutError('Shared wall budget reached with a partial phase')
                time.sleep(3)
        barrier('initial.json'); initial_seconds=time.time()-start
        longest=0.; round_index=0
        while True:
            remaining=duration-(time.time()-start)
            reserve=max(600.,initial_seconds*1.6+60.) if not args.smoke else max(90.,initial_seconds*1.5)
            if round_index and (args.smoke or remaining < reserve+longest*1.35): break
            round_index+=1
            write(cap/f'command{round_index:04d}.json',dict(round=round_index,issued=time.time(),steps_per_group=4096,optimizer_calls_per_group=256))
            barrier(f'round{round_index:04d}.json')
            receipts=[json.loads((f/f'round{round_index:04d}.json').read_text()) for f in folders]
            longest=max(longest,max(r['seconds'] for r in receipts))
            write(cap/'progress.json',dict(common_round=round_index,elapsed_seconds=time.time()-start,longest_worker_round=longest,
                                          steps_per_model=round_index*4096,models=len(tasks)*6))
        write(cap/'finalize.json',dict(common_round=round_index,time=time.time()))
        # Final phase has a distinct completion marker; a worker may finish while others evaluate.
        while not all((f/'exit.json').exists() for f in folders):
            for p,f in zip(children,folders):
                if p.poll() is not None and not (f/'exit.json').exists(): raise RuntimeError(f'Worker failure at final: {p.pid}, {p.returncode}')
            if time.time()-start>duration: raise TimeoutError('Final phase exceeded shared budget')
            time.sleep(3)
        for p in children:
            if p.wait(timeout=20)!=0: raise RuntimeError('Nonzero final child')
        write(cap/'exit.json',dict(status='COMPLETED_PREDECLARED_WALL_BUDGET',exit_code=0,common_round=round_index,
                                  elapsed_seconds=time.time()-start,wall_cap_seconds=duration,input_count=pins(),automatic_retries=0,
                                  note='Stopped launching whole rounds early enough to perform final evaluation inside cap.'))
    except BaseException:
        write(cap/'failure.json',dict(error=traceback.format_exc(),elapsed_seconds=time.time()-start,automatic_retries=0))
        raise
    finally:
        cleanup=[r for p in children if (r:=kill_owned(p)) is not None]
        write(cap/'cleanup.json',dict(stopped_owned_trees=cleanup,time=time.time()))
        for h in handles:h.close()
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)

def launch(args):
    pins()
    if not args.smoke:
        smoke=json.loads((HERE/'smoke/exit.json').read_text())
        diagnostics=json.loads((HERE/'diagnostic/result.json').read_text())
        if smoke['exit_code']!=0 or diagnostics['status']!='PASS_BOUNDED_IMPLEMENTATION': raise RuntimeError('Short validation not complete')
    cap=HERE/('smoke' if args.smoke else 'three_hour')
    cap.mkdir(exist_ok=False)
    write(cap/'claim.json',dict(time=time.time(),wall_seconds=1800 if args.smoke else 10800,domains=['pursuit','generic'],
          authority='Latest direct user: repair math and neural model, then train both domains concurrently for three hours.',
          groups=['RL-plain','RL-outer','F0','F-RP','F-R','N227'],automatic_retries=0,input_count=pins()))
    with (cap/'guard.stdout.log').open('xb') as out,(cap/'guard.stderr.log').open('xb') as err:
        cmd=[sys.executable,'-X','utf8','-B',str(HERE/'runtime.py'),'guard','--capture',str(cap)] + (['--smoke'] if args.smoke else [])
        p=subprocess.Popen(cmd,cwd=str(ROOT),stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
    write(cap/'launch.json',dict(pid=p.pid,time=time.time(),python=sys.executable))
    print(json.dumps(dict(status='LAUNCHED_NOT_COMPLETED',pid=p.pid,capture=str(cap))))

def guard(args):
    cap=Path(args.capture);start=time.time();timeout=False
    with (cap/'supervisor.stdout.log').open('xb') as out,(cap/'supervisor.stderr.log').open('xb') as err:
        cmd=[sys.executable,'-X','utf8','-B',str(HERE/'runtime.py'),'supervisor','--capture',str(cap)]+(['--smoke'] if args.smoke else [])
        p=subprocess.Popen(cmd,cwd=str(ROOT),stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
        try: code=p.wait(timeout=(1800 if args.smoke else 10800)+30)
        except subprocess.TimeoutExpired:
            timeout=True;kill_owned(p);code=p.wait()
    write(cap/'guard_exit.json',dict(exit_code=code,timeout=timeout,seconds=time.time()-start,automatic_retries=0))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['worker','supervisor','launch','guard'])
    parser.add_argument('--capture');parser.add_argument('--domain');parser.add_argument('--seed',type=int)
    parser.add_argument('--eval-n',type=int,default=32);parser.add_argument('--smoke',action='store_true')
    args=parser.parse_args();globals()[args.mode](args)
