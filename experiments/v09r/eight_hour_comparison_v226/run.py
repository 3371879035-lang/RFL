"""Eight-hour local training; immutable round receipts, explicit partials, no retry."""
import argparse
import ctypes
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
from common import ROOT,HERE,write,archive,metrics,digest
import torch
from references import Reference,GROUPS
from neural import Neural

def factory(seed,group):return Neural(seed) if group=='N226' else Reference(seed,group)

def save_pt(path,data,exclusive=True):
    path=Path(path)
    if exclusive:
        with path.open('xb') as f:torch.save(data,f)
    else:
        tmp=path.with_name(path.name+'.tmp')
        with tmp.open('wb') as f:torch.save(data,f)
        os.replace(tmp,path)

def restore(seed,group,c):
    model=factory(seed,group);model.net.load_state_dict(c['model'])
    model.optimizer.load_state_dict(c['optimizer']);model.rng.setstate(c['rng'])
    model.total_steps=c['total_steps'];model.total_updates=c['total_updates'];model.next_episode=c['next_episode'];model.counters=c['counters']
    if group=='N226':
        from feedback_program_v225 import MemoryBank
        model.bank=MemoryBank.from_json(json.dumps(c['memory']))
    else:
        from collections import deque
        model.target.load_state_dict(c['target']);model.history=deque(c['history'],maxlen=96);model.replay=deque(c['replay'],maxlen=8192)
    return model

def evaluate_all(models,directory,tag,n):
    scores={}
    for group,model in models.items():
        before=digest(model.net);start=time.monotonic();raw=model.evaluate(tag,n)
        assert before==digest(model.net)
        scores[group]=dict(metrics(raw['rows']),actual_steps=raw['actual_steps'],wall_seconds=time.monotonic()-start,
                           model_sha256=before,train_steps=model.total_steps,train_updates=model.total_updates,
                           rows=raw['rows'],family={str(f):metrics([r for r in raw['rows'] if r['family']==f]) for f in range(4)})
        archive(directory/f'eval_{tag}_{group}.json.gz',raw)
    write(directory/f'eval_{tag}.json',scores)
    return scores

def worker(args):
    torch.set_num_threads(1);torch.set_num_interop_threads(1)
    cap=Path(args.capture);directory=cap/f'seed{args.seed}';directory.mkdir(exist_ok=False)
    contract=json.loads((HERE/'contract.json').read_text(encoding='utf-8'));start=time.monotonic()
    models={group:factory(args.seed,group) for group in GROUPS}
    write(directory/'initial.json',{g:dict(parameters=sum(p.numel() for p in m.net.parameters()),sha256=digest(m.net)) for g,m in models.items()})
    eval_n=4 if args.smoke else contract['evaluation']['interim_episodes']
    evaluate_all(models,directory,'initial',eval_n)
    block=0
    try:
        while args.smoke and block<2 or not args.smoke and time.time()<args.training_deadline:
            if (cap/'STOP').exists():break
            block+=1;round_start=time.monotonic();receipts={}
            for offset in range(len(GROUPS)):
                group=GROUPS[(offset+block-1)%len(GROUPS)];m=models[group]
                write(directory/'live.json',dict(status='TRAINING',block=block,group=group,total_steps=m.total_steps,
                                                last_complete=block-1,updated_unix=time.time()),False)
                t=time.monotonic();result=m.collect(block,contract['charged_steps_per_group_seed_round'])
                result['wall_seconds']=time.monotonic()-t
                archive(directory/f'block{block:05}_{group}.json.gz',result)
                receipts[group]={k:v for k,v in result.items() if k not in ('trace','external','records')}
                if result['before']==result['after']:raise AssertionError(f'{group} did not update actual weights')
                print(json.dumps(dict(seed=args.seed,block=block,group=group,steps=result['total_steps'],
                                      updates=result['total_updates'],losses=result['losses'],seconds=result['wall_seconds'])),flush=True)
            write(directory/f'round{block:05}.json',dict(block=block,seed=args.seed,groups=receipts,wall_seconds=time.monotonic()-round_start))
            write(directory/'progress.json',dict(status='TRAINING',last_complete=block,train_steps_per_group=block*64,
                                                elapsed_seconds=time.monotonic()-start,updated_unix=time.time()),False)
            save_pt(directory/'latest.pt',{g:m.checkpoint() for g,m in models.items()},False)
            if args.smoke or block in contract['evaluation']['rungs']:
                save_pt(directory/f'rung{block:05}.pt',{g:m.checkpoint() for g,m in models.items()})
                evaluate_all(models,directory,f'rung{block:05}',eval_n)
            if args.smoke and block==2:break
        write(directory/'worker_exit.json',dict(status='TRAINING_FINISHED',last_complete=block,
                                               elapsed_seconds=time.monotonic()-start,exit_code=0))
        return 0
    except BaseException as error:
        write(directory/'failure.json',dict(type=type(error).__name__,message=str(error),traceback=traceback.format_exc(),
                  block=block,last_complete=max(0,block-1),elapsed_seconds=time.monotonic()-start))
        raise

def final_worker(args):
    torch.set_num_threads(1);torch.set_num_interop_threads(1)
    directory=Path(args.capture)/f'seed{args.seed}'
    checkpoints=torch.load(directory/f'rung{args.final_block:05}.pt',map_location='cpu',weights_only=False)
    models={g:restore(args.seed,g,c) for g,c in checkpoints.items()}
    evaluate_all(models,directory,'final_common',64)
    write(directory/'final_exit.json',dict(exit_code=0,block=args.final_block,steps_per_group=args.final_block*64))

def summarize(cap,seeds,status,common):
    rows=[]
    for seed in seeds:
        d=cap/f'seed{seed}'
        if not (d/'eval_final_common.json').exists():continue
        initial=json.loads((d/'eval_initial.json').read_text());final=json.loads((d/'eval_final_common.json').read_text())
        for g in GROUPS:
            rows.append(dict(seed=seed,group=g,initial=initial[g],final=final[g]))
    aggregate={}
    for g in GROUPS:
        sub=[r for r in rows if r['group']==g]
        if sub:aggregate[g]=dict(seeds=len(sub),success_rate=sum(r['final']['success_rate'] for r in sub)/len(sub),
             mean_final_distance=sum(r['final']['mean_final_distance'] for r in sub)/len(sub),
             paired_distance_change=sum(sum(f['distance']-i['distance'] for f,i in zip(r['final']['rows'],r['initial']['rows']))/len(r['initial']['rows']) for r in sub)/len(sub))
    write(cap/'result_summary.json',dict(status=status,last_common_rung=common,actual_rows=rows,aggregate=aggregate,
          claim='New portable common-task package comparison; not direct legacy game score comparison. Three independent seeds, not thousands of independent models.'))
    lines=['# V226 八小时训练结果',f'状态：{status}。最后共同预算档：{common}。',
           '旧五组保留的是学习条件，本轮是通用任务上的新实现；不能直接与旧地图分数横比。',
           '|组别|独立种子|成功率|终点距离（越小越好）|相对初始距离变化|','|---|---:|---:|---:|---:|']
    for g,a in aggregate.items():lines.append(f"|{g}|{a['seeds']}|{a['success_rate']:.4f}|{a['mean_final_distance']:.4f}|{a['paired_distance_change']:+.4f}|")
    lines+=['','预算按所有实际环境调用匹配，包括试验、教师/学生采用测试；不是相同 FLOPs。',
             '完整任务结果、梯度、机制计数、失败和部分运行保留在各 seed 目录。',
             'N226 是事实学习加目标回报的混合训练，不称纯反馈；F0 不接显式奖励/处罚或 Q。',
             'SLEEP 是本地条件化行为蒸馏实现，不等于论文全复现。当前评估区分实际重复评估和独立训练种子。']
    with (cap/'REPORT.md').open('x',encoding='utf-8') as f:f.write('\n'.join(lines)+'\n')

def supervisor(args):
    contract=json.loads((HERE/'contract.json').read_text());cap=Path(args.capture)
    start=time.time();budget=contract['wall_seconds'];deadline=start+budget
    reserve=contract['final_reserve_seconds'];seeds=contract['training_seeds']
    awake=ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
    write(cap/'run_clock.json',dict(start_unix=start,deadline_unix=deadline,training_deadline_unix=deadline-reserve,
                                  process_id=os.getpid(),wall_budget_seconds=budget,system_awake_request_succeeded=bool(awake)))
    processes=[];logs=[];status='COMPLETED_WALL_BUDGET';common=0
    try:
        for seed in seeds:
            out=(cap/f'seed{seed}.stdout.log').open('xb');err=(cap/f'seed{seed}.stderr.log').open('xb');logs.extend((out,err))
            p=subprocess.Popen([sys.executable,'-X','utf8','-B',str(HERE/'run.py'),'--worker','--capture',str(cap),
                  '--seed',str(seed),'--training-deadline',str(deadline-reserve)],cwd=str(HERE),stdout=out,stderr=err,
                  creationflags=subprocess.CREATE_NO_WINDOW)
            processes.append(p)
        write(cap/'workers.json',[dict(seed=s,pid=p.pid) for s,p in zip(seeds,processes)])
        while any(p.poll() is None for p in processes):
            failed=[p for p in processes if p.poll() not in (None,0)]
            if failed:
                status='PARTIAL_WORKER_FAILURE';(cap/'STOP').touch(exist_ok=True)
                # A failed shard is never retried; preserve other completed rounds.
                for p in processes:
                    if p.poll() is None:p.terminate()
                break
            if time.time()>deadline-reserve/2:
                status='PARTIAL_TRAINING_OVERRUN'
                for p in processes:
                    if p.poll() is None:p.terminate()
                break
            size=sum(p.stat().st_size for p in cap.rglob('*') if p.is_file())
            if size>contract['artifact_bytes_max'] or __import__('shutil').disk_usage(HERE).free<12*1024**3:
                status='RESOURCE_STOP';(cap/'STOP').touch(exist_ok=True)
            snapshot={}
            for seed in seeds:
                path=cap/f'seed{seed}'/'progress.json'
                if path.exists():snapshot[str(seed)]=json.loads(path.read_text())
            write(cap/'progress.json',dict(status=status if status!='COMPLETED_WALL_BUDGET' else 'RUNNING',
                    elapsed_seconds=time.time()-start,seeds=snapshot,artifact_bytes=size),False)
            time.sleep(30)
        for p in processes:p.wait()
        if any(p.returncode!=0 for p in processes) and status=='COMPLETED_WALL_BUDGET':status='PARTIAL_WORKER_FAILURE'
        available=[]
        for seed in seeds:
            available.append({int(p.stem[4:]) for p in (cap/f'seed{seed}').glob('rung*.pt')})
        shared=set.intersection(*available) if available else set();common=max(shared,default=0)
        if common and status=='COMPLETED_WALL_BUDGET':
            finals=[]
            for seed in seeds:
                out=(cap/f'final{seed}.stdout.log').open('xb');err=(cap/f'final{seed}.stderr.log').open('xb');logs.extend((out,err))
                finals.append(subprocess.Popen([sys.executable,'-X','utf8','-B',str(HERE/'run.py'),'--final',
                      '--capture',str(cap),'--seed',str(seed),'--final-block',str(common)],cwd=str(HERE),
                      stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW))
            for p in finals:
                try:p.wait(timeout=max(1,deadline-time.time()))
                except subprocess.TimeoutExpired:
                    p.terminate();p.wait();status='PARTIAL_FINAL_TIMEOUT'
                if p.returncode:status='PARTIAL_FINAL_FAILURE' if status=='COMPLETED_WALL_BUDGET' else status
        elif not common:status='NO_COMMON_COMPLETED_RUNG'
        summarize(cap,seeds,status,common)
        from launch import verify_inputs
        preservation=verify_inputs()
        write(cap/'exit.json',dict(status=status,worker_exit_codes=[p.returncode for p in processes],
              wall_seconds=time.time()-start,last_common_rung=common,old_and_new_inputs_unchanged=preservation,
              automatic_retries=0))
    finally:
        for f in logs:f.close()
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)

def main():
    p=argparse.ArgumentParser();p.add_argument('--worker',action='store_true');p.add_argument('--final',action='store_true')
    p.add_argument('--smoke',action='store_true');p.add_argument('--seed',type=int,default=179)
    p.add_argument('--capture',required=True);p.add_argument('--training-deadline',type=float,default=0.)
    p.add_argument('--final-block',type=int,default=0);args=p.parse_args()
    if args.final:final_worker(args)
    elif args.worker:worker(args)
    else:supervisor(args)
if __name__=='__main__':main()
