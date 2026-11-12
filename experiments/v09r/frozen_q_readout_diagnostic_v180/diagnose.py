"""Post-hoc frozen own-Q intervention, not a replacement primary experiment."""
import concurrent.futures
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback

HERE=Path(__file__).resolve().parent
ORIGINAL=HERE.parent/'spatial_feedback_v179'
sys.path.insert(0,str(ORIGINAL))
import numpy as np
import psutil
import torch
from experiment import Capture,write_json
from world import MapBank,World


class QOnlyFrozenReadout:
    def __init__(self,agent):
        assert agent.arm in ('F-RP','F-R') and agent.net.q is not None
        self.agent=agent
        agent.net.eval()

    def reset(self,j):
        self.agent.reset_episode('evaluation',j)

    @torch.no_grad()
    def act(self,obs):
        a=self.agent
        scalar,_=a._features(obs)
        image=torch.from_numpy(obs.image[None].astype(np.float32))
        features=torch.from_numpy(scalar[None])
        a.h=a.net.gru(a.net.embedding(image,features),a.h)
        q=a.net.q(a.h).numpy()[0]
        q[~obs.legal]=-1e9
        action=int(q.argmax())
        self.last_choice=dict(action=action,explored=False,stage=a.stage(),depth=0,
                              forecast=float(q[action]),old_action=action)
        return action

    def advance(self,action,fact):
        self.agent.last_action,self.agent.last_pickup=action,fact.pickup
        self.agent.local_t+=1


def run_seed(seed):
    bank=MapBank(HERE.parent/'spatial_feedback_v178/evidence_prepare/maps')
    results=[]
    for arm in ('F-RP','F-R'):
        out=HERE/'evidence'/f'seed{seed}'/arm
        out.mkdir(parents=True,exist_ok=False)
        checkpoint=ORIGINAL/'evidence_matrix'/f'seed{seed}'/arm/'checkpoint_262144.pt.gz'
        with gzip.open(checkpoint,'rb') as f:
            donor=torch.load(f,map_location='cpu',weights_only=False)
        agent=donor['agent']
        del donor
        assert agent.training_steps==262144
        initial_hash=agent.parameter_hash();initial_history=agent.replay.n
        updates=(agent.counters['Q_updates'],agent.counters['fact_updates'])
        policy=QOnlyFrozenReadout(agent)
        capture=Capture(out/'steps.bin.gz',dict(schema='V09_Q_ONLY_FROZEN_DIAGNOSTIC_V180',
             seed=seed,source_arm=arm,policy_type='QOnlyFrozenReadout',training=False,
             original_checkpoint=str(checkpoint),parameter_hash=initial_hash))
        episodes=[];started=time.perf_counter();error=None
        try:
            for j in range(128):
                world=World(bank,seed,'evaluation',j);obs=world.observe();policy.reset(j)
                while not world.done:
                    before=world.audit();action=policy.act(obs)
                    obs,fact=world.step(action)
                    capture.record(4,262144,j,before,world,policy,fact,None)
                    policy.advance(action,fact)
                episodes.append(dict(episode=j,map=world.map_id,mode=world.mode,
                    heldout=world.map_id>=90109,steps=world.t,treasures=world.collected,
                    captured=bool(fact.captured),completed=bool(fact.completed),
                    score=1.5*world.t+100*world.collected))
            assert agent.parameter_hash()==initial_hash and agent.replay.n==initial_history
            assert (agent.counters['Q_updates'],agent.counters['fact_updates'])==updates
        except BaseException:
            error=traceback.format_exc()
        finally:
            capture.close()
        result=dict(seed=seed,source_arm=arm,status='COMPLETE' if error is None else 'ERROR_PARTIAL_RETAINED',
            error=error,episodes=len(episodes),steps=capture.total,training_steps_added=0,
            mean_score=float(np.mean([r['score'] for r in episodes])) if episodes else None,
            mean_survival=float(np.mean([r['steps'] for r in episodes])) if episodes else None,
            mean_treasures=float(np.mean([r['treasures'] for r in episodes])) if episodes else None,
            parameter_hash_before=initial_hash,parameter_hash_after=agent.parameter_hash(),
            persistent_history_unchanged=agent.replay.n==initial_history,
            raw_payload_sha256=capture.hash.hexdigest(),wall_seconds=time.perf_counter()-started)
        write_json(out/'episodes.json',episodes,True);write_json(out/'result.json',result,True)
        results.append(result)
        if error:break
    return results


def main():
    output=HERE/'evidence';output.mkdir(exist_ok=False)
    before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [ORIGINAL/'world.py',ORIGINAL/'learning.py',ORIGINAL/'experiment.py']}
    claim=dict(pid=__import__('os').getpid(),started_epoch=time.time(),source_hashes=before,
               diagnostic_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               contract_sha256=hashlib.sha256((HERE/'contract.json').read_bytes()).hexdigest())
    write_json(output/'claim.json',claim,True)
    main_process=psutil.Process(33964)
    workers=[p for p in main_process.children() if p.name().lower()=='python.exe']
    assert len(workers)==12
    borrowed=sorted(workers,key=lambda p:p.pid)[:4]
    suspended=[];results=[];error=None;start=time.perf_counter()
    try:
        for process in borrowed:
            process.suspend();suspended.append(process)
        write_json(output/'borrowed_worker_slots.json',dict(pids=[p.pid for p in suspended],
                    main_active_workers=8,diagnostic_workers=4),True)
        with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
            for batch in pool.map(run_seed,range(9001,9013)):
                results.extend(batch)
        assert len(results)==24 and all(r['status']=='COMPLETE' for r in results)
    except BaseException:
        error=traceback.format_exc()
    finally:
        for process in suspended:
            if process.is_running():process.resume()
        write_json(output/'worker_slots_restored.json',dict(pids=[p.pid for p in suspended],
                   restored_epoch=time.time(),pause_wall_seconds=time.perf_counter()-start),True)
    assert before=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [ORIGINAL/'world.py',ORIGINAL/'learning.py',ORIGINAL/'experiment.py']}
    summary=dict(status='COMPLETE_POSTHOC_FROZEN_DIAGNOSTIC' if error is None else 'ERROR_PARTIAL_RETAINED',
        exit_code=int(error is not None),error=error,cases=results,
        total_new_eval_episodes=sum(r['episodes'] for r in results),
        total_new_eval_steps=sum(r['steps'] for r in results),new_training_steps=0,
        wall_seconds=time.perf_counter()-start,original_native_sources_unchanged=True,
        main_workers_restored=True)
    write_json(output/'result.json',summary,True)
    print(json.dumps({k:summary[k] for k in ['status','exit_code','error','total_new_eval_episodes','total_new_eval_steps','wall_seconds','main_workers_restored']}),flush=True)
    return summary['exit_code']


if __name__=='__main__':raise SystemExit(main())
