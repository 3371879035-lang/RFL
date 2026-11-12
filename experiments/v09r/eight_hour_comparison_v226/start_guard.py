"""Windows process-tree guard added after observing the venv redirector PID.

Training sources and their successful smoke remain unchanged. A timeout must
stop the owned process TREE, not merely the 5 MB venv launcher parent.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from common import HERE,write
from launch import verify_inputs

CAP=HERE/'eight_hour'

def cleanup_owned():
    # Exact experiment entry point AND exact capture directory, never every Python process.
    script="Get-CimInstance Win32_Process | Where-Object {$_.Name -like 'python*'} | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
    text=subprocess.check_output(['powershell.exe','-NoProfile','-Command',script],encoding='utf-8',errors='replace',creationflags=subprocess.CREATE_NO_WINDOW)
    rows=json.loads(text) if text.strip() else []
    if isinstance(rows,dict):rows=[rows]
    owned=[r['ProcessId'] for r in rows if str(HERE/'run.py') in (r.get('CommandLine') or '') and str(CAP) in (r.get('CommandLine') or '')]
    result=[]
    for pid in owned:
        r=subprocess.run(['taskkill.exe','/PID',str(pid),'/T','/F'],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
        result.append(dict(pid=pid,exit_code=r.returncode))
    return result

def launch():
    audit=json.loads((HERE/'smoke'/'audit.json').read_text())
    if audit['status']!='PASS_FINITE_TRAINING_WIRING':raise ValueError('Finite training wiring incomplete')
    pins=verify_inputs();CAP.mkdir(exist_ok=False)
    write(CAP/'claim.json',dict(status='CLAIMED_ONCE',start_unix=time.time(),inputs=pins,
          authority='User requested eight hours with previous RL/feedback control conditions',
          automatic_retries=0,guard_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          guard_reason='Observed Windows venv redirector parent: bound termination must cover child process trees.'))
    out=(CAP/'guard.stdout.log').open('xb');err=(CAP/'guard.stderr.log').open('xb')
    p=subprocess.Popen([sys.executable,'-X','utf8','-B',str(Path(__file__).resolve()),'--guard'],cwd=str(HERE),
                       stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
    out.close();err.close();write(CAP/'launch.json',dict(pid=p.pid,started_unix=time.time(),python=sys.executable,kind='owned_tree_guard'))
    print(json.dumps(dict(status='LAUNCHED_NOT_COMPLETED',pid=p.pid,capture=str(CAP))))

def guard():
    start=time.time()
    with (CAP/'supervisor.stdout.log').open('xb') as out,(CAP/'supervisor.stderr.log').open('xb') as err:
        p=subprocess.Popen([sys.executable,'-X','utf8','-B',str(HERE/'run.py'),'--capture',str(CAP)],cwd=str(HERE),
                           stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
        write(CAP/'guard_process.json',dict(guard_actual_pid=os.getpid(),supervisor_root_pid=p.pid,start_unix=start,
              maximum_seconds=28800,termination_grace_seconds=20))
        timeout=False
        try:code=p.wait(timeout=28820)
        except subprocess.TimeoutExpired:
            timeout=True;subprocess.run(['taskkill.exe','/PID',str(p.pid),'/T','/F'],capture_output=True,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            p.wait();code=p.returncode
    cleanup=cleanup_owned()
    write(CAP/'guard_exit.json',dict(exit_code=code,timeout=timeout,elapsed_seconds=time.time()-start,
                                    leftover_owned_processes_stopped=cleanup,automatic_retries=0))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--guard',action='store_true');a=p.parse_args()
    guard() if a.guard else launch()
