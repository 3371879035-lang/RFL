"""One bounded four-group pilot. No V190 fixture or completed bank is rerun."""
import concurrent.futures
import copy
import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import time
import traceback
os.environ['OMP_NUM_THREADS']='1'
os.environ['MKL_NUM_THREADS']='1'
import numpy as np
import psutil
import torch
from learning import Agent
from sleep_loop import run_sleep, state_hash
from world import MapBank,World

torch.set_num_threads(1)
torch.set_num_interop_threads(1)
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
DTYPE=np.dtype([('kind','u1'),('checkpoint','<i4'),('episode','<i4'),('step','<u2'),
    ('map','<i4'),('mode','u1'),('before_hero','u1',(2,)),('hero','u1',(2,)),
    ('monsters','<i2',(2,2)),('action','u1'),('proposed','u1'),('explore','u1'),
    ('pickup','u1'),('captured','u1'),('completed','u1'),('score','<f4'),('reward','<f4')])
LABEL_DTYPE=np.dtype([('uid','<i8'),('horizon','u1'),('observed_at','<i8'),('steps','<u2'),
    ('pickups','u1'),('terminal','u1'),('target_steps','<f4'),('target_pickups','<f4')])


def utc(): return datetime.datetime.now(datetime.timezone.utc).isoformat()


def write(path,value):
    with Path(path).open('x',encoding='utf-8',newline='\n') as f:
        json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')


def filepin(path):
    return dict(path=path.relative_to(ROOT).as_posix(),bytes=path.stat().st_size,
                sha256=hashlib.file_digest(path.open('rb'),'sha256').hexdigest())


def pins():
    return [filepin(p) for p in sorted(HERE.iterdir())
            if p.suffix=='.py' or p.name in ('contract.json','checkpoint_binding.json','map_binding.json')]


class Binary:
    def __init__(self,path,dtype,schema):
        self.f=gzip.open(path,'xb',compresslevel=1)
        data=json.dumps(dict(dtype=dtype.descr,schema=schema),separators=(',',':')).encode()
        self.f.write(struct.pack('<I',len(data))+data)
        self.buffer=np.zeros(4096,dtype);self.n=self.total=0;self.hash=hashlib.sha256()
    def add(self,row):
        self.buffer[self.n]=row;self.n+=1;self.total+=1
        if self.n==len(self.buffer):self.flush()
    def flush(self):
        b=self.buffer[:self.n].tobytes();self.hash.update(b);self.f.write(b);self.n=0
    def close(self):self.flush();self.f.close()


def record(raw,agent,kind,cp,episode,before,world,fact,reward):
    c=agent.last_choice
    raw.add((kind,cp,episode,world.t,world.map_id,world.mode,before,world.hero,world.monsters,
             c['action'],c['full_action'],c['explored'],fact.pickup,fact.captured,fact.completed,
             1.5*world.t+100*world.collected,np.nan if reward is None else reward))


def save(path,payload):
    with gzip.open(path,'xb',compresslevel=1) as f:torch.save(payload,f)


def evaluate(agent,bank,count,cp,raw,episodes):
    clone=agent.frozen()
    before=(clone.parameter_hash(),clone.replay.n,clone.training_steps,
            clone.history_policy.theta.tolist(),len(clone.history_policy.history))
    old=clone.counters.copy()
    rows=[]
    for episode in range(1024,1024+count):
        world=World(bank,clone.seed,'evaluation',episode)
        obs=world.observe();clone.reset_episode('evaluation',episode)
        stationary=streak=long_stall=0
        while not world.done:
            previous=tuple(obs.hero)
            action=clone.act(obs,False)
            nxt,fact=world.step(action)
            record(raw,clone,1,cp,episode,previous,world,fact,None)
            moved=tuple(nxt.hero)!=previous
            stationary+=int(not moved);streak=0 if moved else streak+1
            long_stall+=int(streak>=8)
            # Recurrent/local observation state only, never learning in evaluation.
            clone.last_action,clone.last_pickup=action,fact.pickup
            clone.local_t+=1;obs=nxt
        row=dict(kind='evaluation',checkpoint=cp,episode=episode,map=world.map_id,mode=world.mode,
            steps=world.t,treasures=world.collected,captured=bool(fact.captured),
            completed=bool(fact.completed),score=1.5*world.t+100*world.collected,
            stationary=stationary,long_stall=long_stall)
        rows.append(row);episodes.write(json.dumps(row,separators=(',',':'))+'\n')
    assert before==(clone.parameter_hash(),clone.replay.n,clone.training_steps,
                    clone.history_policy.theta.tolist(),len(clone.history_policy.history))
    for name in ('Q_updates','fact_updates','measurement_updates','reward_packets','v191_optimizer_updates'):
        assert clone.counters.get(name,0)==old.get(name,0)
    def summary(rs):
        return dict(episodes=len(rs),mean_score=float(np.mean([r['score'] for r in rs])),
                    mean_steps=float(np.mean([r['steps'] for r in rs])),
                    mean_treasures=float(np.mean([r['treasures'] for r in rs])))
    total=sum(r['steps'] for r in rows)
    return dict(checkpoint=cp,steps=total,**summary(rows),
        common64=summary(rows[:64]),seen=summary([r for r in rows if r['map']<90109]),
        heldout=summary([r for r in rows if r['map']>=90109]),
        stationary_rate=sum(r['stationary'] for r in rows)/total,
        long_stall_rate=sum(r['long_stall'] for r in rows)/total,
        parameter_hash=agent.parameter_hash(),frozen=True)


@torch.no_grad()
def refresh_recurrent(agent):
    # A fixed step budget can pause an unfinished task. Do not invent a terminal.
    # Re-encode its observed prefix after sleep, then resume the genuine world.
    h=torch.zeros(1,64)
    for uid,_,_ in agent.episode_rows:
        i=uid%65536
        image=torch.from_numpy(agent.replay.image[i:i+1].astype(np.float32))
        scalar=torch.from_numpy(agent.replay.scalar[i:i+1].astype(np.float32))
        h=agent.net.gru(agent.net.embedding(image,scalar),h)
    agent.h=h
    return len(agent.episode_rows)


def run_pair(spec):
    torch.use_deterministic_algorithms(True)
    seed,arm,binding=spec
    bank=MapBank(HERE.parent/'spatial_feedback_v178/evidence_prepare/maps')
    result=[];initial_evaluation=None;initial_bank_pin=None
    for variant in ('matched_replay','adaptive_sleep'):
        directory=HERE/'evidence_pilot'/f'seed{seed}'/arm/variant
        directory.mkdir(parents=True,exist_ok=False)
        start,cpu=time.perf_counter(),time.process_time()
        source=ROOT/binding['path']
        assert filepin(source)=={k:binding[k] for k in ('path','bytes','sha256')}
        with gzip.open(source,'rb') as f:loaded=torch.load(f,map_location='cpu',weights_only=False)
        agent=loaded['agent']
        assert isinstance(agent,Agent) and agent.seed==seed and agent.arm==arm
        assert agent.training_steps==agent.replay.n==147456
        old_partial=dict(episode=loaded['episode'],steps=loaded['world'].t,terminal=loaded['world'].done)
        del loaded
        agent.configure_v191(variant)
        initial_hash=agent.parameter_hash();old_counters=agent.counters.copy()
        raw=Binary(directory/'steps.bin.gz',DTYPE,'V191_REAL_STEPS')
        labels=Binary(directory/'labels.bin.gz',LABEL_DTYPE,'V191_OBSERVED_FUTURE_LABELS')
        episodes=gzip.open(directory/'episodes.jsonl.gz','xt',encoding='utf-8',compresslevel=1)
        sleep_log=gzip.open(directory/'sleep.jsonl.gz','xt',encoding='utf-8',compresslevel=1)
        evals=[];rounds=[];completed=sources=0;episode=310000;world=obs=None;error=None
        sleep_wall=0.
        try:
            if initial_evaluation is None:
                initial_evaluation=evaluate(agent,bank,128,0,raw,episodes)
                initial_bank_pin=dict(source_variant=variant,parameter_hash=initial_hash,
                                      action_implementation='inherited BaseAgent.act, no reaction layer')
            assert initial_hash==initial_bank_pin['parameter_hash']
            evals.append(dict(initial_evaluation,shared_initial_bank=initial_bank_pin))
            for cycle in range(1,4):
                cp=4096*cycle
                while agent.training_steps<147456+cp:
                    if world is None or world.done:
                        world=World(bank,seed,'train',episode)
                        agent.reset_episode('train',episode);obs=world.observe();sources+=1
                    previous=tuple(obs.hero);action=agent.act(obs,True)
                    nxt,fact=world.step(action)
                    reward=None if arm=='F0' else .015+fact.pickup-agent.penalty*fact.captured
                    record(raw,agent,0,cp,episode,previous,world,fact,reward)
                    agent.observe(nxt,fact,reward)
                    for row in agent.label_events:labels.add(row)
                    agent.label_events.clear();obs=nxt
                    if world.done:
                        completed+=1
                        row=dict(kind='training',episode=episode,steps=world.t,map=world.map_id,
                                 mode=world.mode,treasures=world.collected,captured=bool(fact.captured),
                                 completed=bool(fact.completed),score=1.5*world.t+100*world.collected)
                        episodes.write(json.dumps(row,separators=(',',':'))+'\n');episode+=1
                    if agent.training_steps%128==0 and (HERE/'evidence_pilot/STOP.json').exists():
                        raise RuntimeError('Pilot stopped; exact partial retained, no retry')
                if cycle==3:evals.append(evaluate(agent,bank,64,-cp,raw,episodes))
                begin=time.perf_counter()
                report,weights=run_sleep(agent,cycle)
                report['wall_seconds']=time.perf_counter()-begin
                sleep_wall+=report['wall_seconds']
                report['prefix_reencoded']=refresh_recurrent(agent) if not world.done else 0
                report['paused_world']=dict(episode=episode,steps=world.t,terminal=world.done)
                sleep_log.write(json.dumps(report,separators=(',',':'),allow_nan=False)+'\n');sleep_log.flush()
                save(directory/f'sleep_round{cycle}.pt.gz',weights)
                rounds.append({k:v for k,v in report.items() if k not in ('train_windows','probe_windows','features','fitting_log')})
                evals.append(evaluate(agent,bank,256 if cycle==3 else 64,cp,raw,episodes))
            save(directory/'checkpoint_final.pt.gz',dict(schema='V191_FULL_CONTINUATION',
                 agent=agent,world=world,episode=episode,observation=obs))
        except BaseException:
            error=traceback.format_exc()
            write(directory/'error.json',dict(utc=utc(),error=error,training_steps=agent.training_steps))
            save(directory/'error_boundary.pt.gz',dict(agent=agent,world=world,episode=episode,observation=obs))
        finally:
            raw.close();labels.close();episodes.close();sleep_log.close()
        delta={k:v-old_counters.get(k,0) for k,v in agent.counters.items()}
        row=dict(seed=seed,arm=arm,variant=variant,status='COMPLETE' if error is None else 'ERROR_PARTIAL_RETAINED',
            error=error,source=binding,initial_hash=initial_hash,final_hash=agent.parameter_hash(),
            old_partial_preserved=old_partial,additional_train_steps=agent.training_steps-147456,
            completed_episodes=completed,training_sources=sources,unfinished_steps=world.t if world and not world.done else 0,
            counters=delta,evaluations=evals,sleep_rounds=rounds,raw_records=raw.total,
            raw_payload_sha256=raw.hash.hexdigest(),labels=labels.total,label_payload_sha256=labels.hash.hexdigest(),
            action_rules_added=0,history_records=len(agent.history_policy.history),
            final_rehearsal_policy=agent.history_policy.theta.tolist(),
            wall_seconds=time.perf_counter()-start,cpu_seconds=time.process_time()-cpu,sleep_wall_seconds=sleep_wall)
        if error is None:
            assert row['additional_train_steps']==12288 and delta['v191_optimizer_updates']==168
            assert delta['Q_updates']==(0 if arm=='F0' else 168)
            assert delta['reward_packets']==(0 if arm=='F0' else 12288)
            assert delta['fact_updates']==(0 if arm=='RL-RP' else 168)
            assert delta['measurement_updates']==(168 if arm=='F0' else 0)
        write(directory/'result.json',row);result.append(row)
        print(json.dumps(dict(seed=seed,arm=arm,variant=variant,status=row['status'],
                             final_score=evals[-1]['mean_score'] if evals else None)),flush=True)
        if error is not None:break
        del agent
    return result


def main():
    out=HERE/'evidence_pilot';out.mkdir(exist_ok=False)
    contract=json.loads((HERE/'contract.json').read_text())
    bindings=json.loads((HERE/'checkpoint_binding.json').read_text())['files']
    inputs=pins();start=time.perf_counter();results=[];error=None;peak=0
    write(out/'claim.json',dict(utc=utc(),pid=os.getpid(),argv=sys.argv,inputs=inputs,
        cases=32,workers=4,torch=torch.__version__,python=sys.version))
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
            todo=iter(bindings)
            pending={pool.submit(run_pair,(b['seed'],b['arm'],b)) for b in [next(todo) for _ in range(4)]}
            while pending:
                finished,pending=concurrent.futures.wait(pending,timeout=5,
                    return_when=concurrent.futures.FIRST_COMPLETED)
                rss=sum(p.memory_info().rss for p in [psutil.Process(),*psutil.Process().children(recursive=True)] if p.is_running())
                peak=max(peak,rss);reason=None
                if rss>contract['budget']['ram_bytes']:reason='RAM budget'
                if time.perf_counter()-start>contract['budget']['wall_seconds']:reason='Wall-time budget'
                if sum(p.stat().st_size for p in out.rglob('*') if p.is_file())>contract['budget']['artifact_bytes']:reason='Artifact budget'
                for f in finished:
                    rows=f.result();results.extend(rows)
                    if any(r['status']!='COMPLETE' for r in rows):reason='Case error, no retry'
                if reason and not (out/'STOP.json').exists():write(out/'STOP.json',dict(reason=reason,utc=utc()))
                if not (out/'STOP.json').exists():
                    for _ in finished:
                        b=next(todo,None)
                        if b is not None:pending.add(pool.submit(run_pair,(b['seed'],b['arm'],b)))
        assert len(results)==32 and all(r['status']=='COMPLETE' for r in results)
        assert not (out/'STOP.json').exists()
        assert inputs==pins()
        for p in bindings+json.loads((HERE/'map_binding.json').read_text())['files']:
            assert filepin(ROOT/p['path'])=={k:p[k] for k in ('path','bytes','sha256')}
    except BaseException:error=traceback.format_exc()
    status=dict(exit_code=int(error is not None),error=error,utc=utc(),cases=len(results),
                wall_seconds=time.perf_counter()-start,peak_rss_bytes=peak,inputs_unchanged=inputs==pins())
    write(out/'result.json',dict(exit=status,cases=results));write(out/'exit.json',status)
    print(json.dumps(status),flush=True)
    return status['exit_code']


if __name__=='__main__':raise SystemExit(main())
