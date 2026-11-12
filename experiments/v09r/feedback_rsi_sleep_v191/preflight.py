"""New decoder, feedback isolation and learned-policy checks; zero environment steps."""
import copy
import gzip
import json
from pathlib import Path
import sys
import time
import traceback
import numpy as np
import torch
from learning import Agent, BaseAgent
from sleep_loop import HistoryPolicy, make_pools, proxy, arrays, distillation

torch.set_num_threads(1)
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]


def main():
    path=HERE/'preflight_result.json'
    assert not path.exists()
    rows=[];error=None;start=time.perf_counter()
    try:
        assert Agent.act is BaseAgent.act
        bindings=json.loads((HERE/'checkpoint_binding.json').read_text())['files']
        for binding in bindings[:4]:
            with gzip.open(ROOT/binding['path'],'rb') as f:
                saved=torch.load(f,map_location='cpu',weights_only=False)
            agent=saved['agent'];agent.configure_v191('adaptive_sleep')
            assert agent.training_steps==agent.replay.n==147456
            assert agent.replay.future.shape==(65536,4,2)
            initial=agent.parameter_hash()
            train,probe_starts=make_pools(agent,1)
            before=proxy(agent,probe_starts[:16],agent.net,agent.target_net)
            assert np.isfinite(before).all()
            if agent.arm=='F0':
                agent.replay.reward[:]=np.nan
                after=proxy(agent,probe_starts[:16],agent.net,agent.target_net)
                assert np.array_equal(before,after) and agent.net.q is None
            indices,images,scalars,resets=arrays(agent,train[:16])
            h=agent.net.unroll(images,scalars,resets)
            ii=indices[:,8:24]
            actions=torch.from_numpy(agent.replay.action[ii].astype(np.int64))
            agent._sleep_teacher=copy.deepcopy(agent.net)
            d=distillation(agent,h,images,scalars,resets,ii,actions)
            assert float(d.detach())==0.
            assert initial==agent.parameter_hash() and agent.counters['v191_optimizer_updates']==0
            rows.append(dict(arm=agent.arm,checkpoint=binding['path'],parameter_hash=initial,
                             probe_mean=float(before.mean()),same_teacher_distillation=float(d.detach())))
            del saved,agent,h,d
        policy=HistoryPolicy();rng=np.random.default_rng(191)
        choices,_=policy.proposals(rng)
        records=[dict(cycle=0,branch=i,theta=t.tolist(),relative_gain=float(i),probe_loss=4.-i)
                 for i,t in enumerate(choices)]
        policy.observe(records,1)
        assert np.array_equal(policy.theta,choices[1]) and len(policy.history)==4
        future,beta=policy.proposals(rng)
        assert len(future)==4 and np.linalg.norm(beta)>0
    except BaseException:error=traceback.format_exc()
    result=dict(exit_code=int(error is not None),error=error,checks=rows,
                environment_steps=0,optimizer_updates=0,wall_seconds=time.perf_counter()-start)
    with path.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(result))
    return result['exit_code']


if __name__=='__main__':raise SystemExit(main())
