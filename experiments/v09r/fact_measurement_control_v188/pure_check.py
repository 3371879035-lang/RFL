"""New pure-data and synthetic-learn check; no World instantiation or rollout."""
import ast
import hashlib
import json
from pathlib import Path
import traceback
import numpy as np
import torch
from learning import Agent
from future_facts import HORIZONS, observed_labels, goal_scores

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
checks={};error=None
try:
    for size in [1,2,3,4,5,15,16,17,63,64,65,256]:
        for terminal in [False,True]:
            rows=[(100+i,int(i%7==0),False) for i in range(size)]
            labels={}
            for n in range(1,size+1):
                for uid,k,steps,pickups in observed_labels(rows[:n],terminal and n==size):
                    assert (uid,k) not in labels
                    start=uid-100
                    assert steps==min(HORIZONS[k],size-start) if terminal and n==size else steps==HORIZONS[k]
                    assert start+steps==n
                    assert pickups==sum(row[1] for row in rows[start:n])
                    labels[uid,k]=steps,pickups,n
            for start in range(size):
                for k,horizon in enumerate(HORIZONS):
                    assert ((100+start,k) in labels)==(terminal or start+horizon<=size)
    checks['mature_window_terminal_tail_and_partial_mask_chronology']=True
    torch.set_num_threads(1)
    agent=Agent(93001,'F0')
    assert agent.net.q is None and agent.target_net is None and not agent.q_enabled
    r=agent.replay;r.n=2048;r.reset[0]=1;r.legal[:2048]=True
    r.reward[:2048]=np.nan
    r.scalar[:2048]=np.linspace(0,1,r.scalar.shape[1],dtype=np.float32)
    r.action[:2048]=np.arange(2048)%16
    r.target_mask[:2048]=1
    r.target[:2048,8:]=0.125,0.1
    r.future_mask[:2048]=1
    r.future[:2048,:,0]=np.minimum(3,np.array(HORIZONS))/np.array(HORIZONS)
    r.future[:2048,:,1]=1
    z=torch.ones(2,64)
    assert all(torch.equal(head(z),torch.zeros(2,16,4,2)) for head in agent.net.measurements)
    before=agent.parameter_hash()
    agent.learn();agent.learn()
    assert agent.parameter_hash()!=before
    assert agent.counters['Q_updates']==agent.counters['reward_packets']==0
    assert agent.counters['measurement_updates']==agent.counters['fact_updates']==2
    assert all(torch.isfinite(p).all() for p in agent.net.parameters())
    checks['actual_learn_two_synthetic_updates_no_Q_nan_reward_unread']=True
    tree=ast.parse((HERE/'learning.py').read_text(encoding='utf-8'))
    learn=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='learn')
    measurement=next(n for n in learn.body if isinstance(n,ast.If) and ast.unparse(n.test)=='not self.q_enabled')
    assert not any(isinstance(n,ast.Attribute) and n.attr in ['reward','q','score'] for n in ast.walk(measurement))
    assert 'goal_scores' not in ast.unparse(learn)
    checks['measurement_training_has_no_scalar_reward_score_Q_or_goal_scalarization']=True
    for name in ['experiment.py','pilot.py']:ast.parse((HERE/name).read_text(encoding='utf-8'))
    for pin in json.loads((HERE/'control_binding.json').read_text(encoding='utf-8'))['files']:
        p=ROOT/pin['path'];assert p.stat().st_size==pin['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==pin['sha256']
    checks['declared_old_controls_unchanged']=True
except BaseException:error=traceback.format_exc()
result=dict(exit_code=int(error is not None),error=error,checks=checks,environment_steps=0,
    declared_synthetic_agent_instances=1,declared_synthetic_optimizer_steps=2,
    actual_synthetic_optimizer_steps=locals().get('agent').counters['fact_updates'] if 'agent' in locals() else 0,
    old_native_checker_calls=0,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
with (HERE/'pure_check_result.json').open('x',encoding='utf-8',newline='\n') as f:json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps(result,ensure_ascii=False),flush=True)
raise SystemExit(result['exit_code'])
