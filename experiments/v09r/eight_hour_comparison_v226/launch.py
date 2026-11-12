"""Exclusive finite smoke / detached eight-hour launch. Never automatic retry."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from common import HERE,ROOT,write

def verify_inputs():
    binding=json.loads((HERE/'input_pins.json').read_text(encoding='utf-8'))
    changed=[name for name,value in binding.items() if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=value]
    if changed:raise ValueError(f'Pinned input changed: {changed}')
    return dict(files=len(binding),matched=True)

def smoke():
    cap=HERE/'smoke';cap.mkdir(exist_ok=False);preserved=verify_inputs();start=time.time()
    write(cap/'claim.json',dict(status='CLAIMED_ONCE',start_unix=start,inputs=preserved,automatic_retries=0,
          budget=dict(maximum_seconds=1800,training_steps=768,evaluation_steps=432,independent_seed=179)))
    with (cap/'stdout.log').open('xb') as out,(cap/'stderr.log').open('xb') as err:
        p=subprocess.Popen([sys.executable,'-X','utf8','-B',str(HERE/'run.py'),'--worker','--smoke',
                 '--capture',str(cap),'--seed','179'],cwd=str(HERE),stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
        write(cap/'process.json',dict(pid=p.pid))
        try:code=p.wait(timeout=1800)
        except subprocess.TimeoutExpired:p.terminate();p.wait();code=None
    inputs=verify_inputs()
    write(cap/'exit.json',dict(exit_code=code,wall_seconds=time.time()-start,inputs=inputs,timeout=code is None))
    if code!=0:return 1
    audit_smoke(cap)
    return 0

def audit_smoke(cap):
    import gzip
    d=cap/'seed179';rows=[]
    for block in (1,2):
        receipt=json.loads((d/f'round{block:05}.json').read_text())
        for group,r in receipt['groups'].items():
            assert r['charged_steps']==64 and r['total_steps']==64*block
            assert r['before']!=r['after'] and 1<=r['updates']<=3
            with gzip.open(d/f'block{block:05}_{group}.json.gz','rt',encoding='utf-8') as f:full=json.load(f)
            if group=='N226':
                trace=full['trace'];old=len(trace['initial_history_ids']);events=trace['memory']['events']
                assert len(events)-old==64 and len(full['external'])==64
                assert trace['actual_filter_updates']==64
                assert len({e['id'] for e in events})==len(events)
                assert len(trace['initial_history_ids'])>0 if block==2 else not trace['initial_history_ids']
                assert all(g['tensors']>0 for g in full['gradients'].values())
                observed={e['id'] for e in events}
                assert all(set(ids)<=observed for ids in full['world_training_ids'])
                assert all(e['source']=='environment' for e in events)
            else:
                assert len(full['records'])==64
                if group=='F0':assert all(r['reward'] is None for r in full['records'])
                if group=='RL-plain':assert not full['gates'] and not full['preferences'] and full['counters']['sleep_updates']==0
            rows.append(dict(block=block,group=group,steps=64,weight_changed=True))
    # Checkpoint round trip is exercised on the actual produced file, not by rerunning environment banks.
    import torch
    sys.path.insert(0,str(HERE));from run import restore
    from common import digest
    checkpoints=torch.load(d/'rung00002.pt',map_location='cpu',weights_only=False)
    last=json.loads((d/'round00002.json').read_text())
    for group,c in checkpoints.items():
        model=restore(179,group,c)
        assert digest(model.net)==last['groups'][group]['after']
        del model
    write(cap/'audit.json',dict(status='PASS_FINITE_TRAINING_WIRING',training_steps=768,rows=rows,
          checkpoint_roundtrip_groups=6,old_native_reruns=0,independent_training_efficacy_claim=False,
          limitations='Two blocks at one separate seed verify wiring/updates, not convergence or superiority.'))

def long_run():
    audit=json.loads((HERE/'smoke'/'audit.json').read_text())
    if audit['status']!='PASS_FINITE_TRAINING_WIRING':raise ValueError('New finite training wiring is not complete')
    inputs=verify_inputs();cap=HERE/'eight_hour';cap.mkdir(exist_ok=False)
    write(cap/'claim.json',dict(status='CLAIMED_ONCE',start_unix=time.time(),inputs=inputs,
                              explicit_user_budget_hours=8,automatic_retries=0))
    out=(cap/'supervisor.stdout.log').open('xb');err=(cap/'supervisor.stderr.log').open('xb')
    p=subprocess.Popen([sys.executable,'-X','utf8','-B',str(HERE/'run.py'),'--capture',str(cap)],
         cwd=str(HERE),stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
    out.close();err.close();write(cap/'launch.json',dict(pid=p.pid,started_unix=time.time(),python=sys.executable))
    print(json.dumps(dict(status='LAUNCHED_NOT_COMPLETED',pid=p.pid,capture=str(cap))))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=('smoke','long'));args=parser.parse_args()
    if args.mode=='smoke':sys.exit(smoke())
    long_run()
