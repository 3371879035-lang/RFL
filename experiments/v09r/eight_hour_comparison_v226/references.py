"""Portable reference implementations, NOT resumed V198/V199 game agents.

Five previous experimental conditions are retained. Actual branch tests precede
preference learning; temporary teacher/student policies must pass real paired
tasks. A failed gate keeps ordinary learning, not a frozen weak control.
"""
import copy
import random
from collections import deque
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
from common import digest
from task import ACTIONS, Task, distance, reward, seed_for

GROUPS=('RL-plain','RL-outer','F0','F-RP','F-R','N226')

class Core(nn.Module):
    def __init__(self, seed, factual, q_enabled):
        super().__init__(); torch.manual_seed(seed)
        self.q=nn.Sequential(nn.Linear(64,128),nn.Tanh(),nn.Linear(128,128),nn.Tanh(),nn.Linear(128,5)) if q_enabled else None
        torch.manual_seed(seed+1)
        self.fact=nn.Sequential(nn.Linear(72,128),nn.Tanh(),nn.Linear(128,128),nn.Tanh(),nn.Linear(128,18)) if factual else None
    def facts(self,x):
        n=len(x); acts=torch.tensor(ACTIONS,dtype=x.dtype,device=x.device)
        inp=torch.cat((x[:,None].expand(n,5,64),acts[None].expand(n,5,8)),-1)
        return self.fact(inp)
    def scores(self,x):
        if self.q is not None:return self.q(x)
        # Pure factual prediction of the realized episode endpoint, no Q/reward target.
        end=self.facts(x)[...,-2:]; target=x[:,None,2:4]
        return -(end-target).square().sum(-1)

class Reference:
    def __init__(self, seed, group):
        self.seed=seed;self.group=group
        self.factual=group in ('F0','F-RP','F-R');self.q_enabled=group!='F0'
        self.net=Core(seed,self.factual,self.q_enabled).eval()
        self.target=copy.deepcopy(self.net).requires_grad_(False)
        self.optimizer=torch.optim.Adam(self.net.parameters(),lr=3e-4)
        self.history=deque(maxlen=96);self.replay=deque(maxlen=8192)
        self.rng=random.Random(seed_for(seed,group,'behavior'))
        self.total_steps=0;self.total_updates=0;self.next_episode=0
        self.counters=dict(actual_trials=0,history_references=0,candidate_trials=0,teacher_gates=0,
                           teacher_pass=0,sleep_updates=0,student_gates=0,adoptions=0,
                           ordinary_updates=0,reward_packets=0,fact_targets=0,imagined_nodes=0)
    def feature(self, observation, goal):
        h=np.mean(np.array(self.history,dtype=np.float32),axis=0) if self.history else np.zeros(40,np.float32)
        return np.array((*observation,*goal,*h),np.float32)
    def action(self, x, model=None, training=True):
        model=self.net if model is None else model
        with torch.no_grad(): scores=model.scores(torch.tensor(x[None]))[0].numpy()
        eps=max(.05,.25/(1+self.total_steps/4096)) if training else 0.
        a=self.rng.randrange(5) if self.rng.random()<eps else int(scores.argmax())
        return a
    def record(self, obs, goal, action, result, x, episode, step, role, records):
        self.history.append(tuple(obs)+ACTIONS[action]+tuple(result['next_observation']))
        nx=self.feature(result['next_observation'],goal)
        r=reward(obs,result,self.group in ('RL-plain','RL-outer','F-RP')) if self.q_enabled else None
        row=dict(id=f'{self.group}/{self.seed}/{self.total_steps}',episode=episode,step=step,role=role,
                 observation=obs,goal=goal,action=action,result=result,x=x.tolist(),nx=nx.tolist(),reward=r)
        records.append(row);self.total_steps+=1
        self.counters['reward_packets']+=int(r is not None)
        self.counters['history_references']+=int(bool(self.history))
        if role=='trial':self.counters['actual_trials']+=1
        return row
    def episode(self, task, records, model=None, training=True, role='task'):
        episode=f'{task.split}/{task.index}/{role}/{self.total_steps}'; rows=[]; last_state=None
        for step in range(task.horizon):
            obs=task.observation();x=self.feature(obs,task.goal)
            action=self.action(x,model,training);last_state=copy.deepcopy(task)
            result=task.execute(action)
            rows.append(self.record(obs,task.goal,action,result,x,episode,step,role,records))
        for row in rows:
            row['endpoint']=result['next_observation'][:2]
            self.replay.append(row)
        return dict(success=result['goal_met'],distance=distance(result['next_observation']),
                    family=task.family,steps=task.horizon),last_state,rows[-1]
    def ordinary_loss(self, net, rows):
        x=torch.tensor([r['x'] for r in rows]);nx=torch.tensor([r['nx'] for r in rows])
        act=torch.tensor([r['action'] for r in rows]);loss=x.sum()*0
        details={}
        if net.q is not None:
            with torch.no_grad():
                best=net.q(nx).argmax(-1)
                boot=self.target.q(nx).gather(1,best[:,None])[:,0]
                r=torch.tensor([r['reward'] for r in rows]);done=torch.tensor([r['result']['terminal'] for r in rows],dtype=x.dtype)
                y=r+.97*(1-done)*boot
            q=net.q(x).gather(1,act[:,None])[:,0];ql=F.smooth_l1_loss(q,y)
            loss=loss+ql;details['td']=float(ql.detach())
        if net.fact is not None:
            pred=net.facts(x)[torch.arange(len(rows)),act]
            target=torch.tensor([(*r['result']['next_observation'],*r['endpoint']) for r in rows])
            fl=F.mse_loss(pred,target);loss=loss+fl;details['facts']=float(fl.detach())
        return loss,details
    def step(self,model,opt,loss):
        if not torch.isfinite(loss):raise FloatingPointError('Reference nonfinite loss')
        opt.zero_grad(set_to_none=True);loss.backward();norm=nn.utils.clip_grad_norm_(model.parameters(),5.)
        if not torch.isfinite(norm):raise FloatingPointError('Reference nonfinite gradient')
        opt.step();self.total_updates+=1
    def collect(self, block, budget=64):
        before=digest(self.net);begin=self.total_steps;updates_before=self.total_updates
        records=[];scores=[];preferences=[];outer=self.group!='RL-plain'
        for _ in range(2):
            task=Task(self.seed,'train',self.next_episode);self.next_episode+=1
            score,state,last=self.episode(task,records);scores.append(score)
            if not outer or score['success']:continue
            # History proposes a different action; paired real futures decide.
            x=np.array(last['x'],np.float32);base=last['action']
            with torch.no_grad(): values=self.net.scores(torch.tensor(x[None]))[0].tolist()
            proposal=max((a for a in range(5) if a!=base),key=lambda a:values[a])
            effects=[]
            for replicate in range(2):
                out=[]
                for action in (base,proposal):
                    branch=copy.deepcopy(state);obs=branch.observation()
                    result=branch.execute(action,branch=100+replicate)
                    # Each actual branch is logged, charged and retained, including adverse ones.
                    row=self.record(obs,branch.goal,action,result,x,
                                    f'trial/{block}/{state.index}/{replicate}/{action}',0,'trial',records)
                    row['endpoint']=result['next_observation'][:2];self.replay.append(row)
                    utility=-distance(result['next_observation']) if not self.q_enabled else row['reward']
                    out.append(utility)
                effects.append(out[1]-out[0])
            if all(e>0 for e in effects):preferences.append(dict(x=x.tolist(),better=proposal,worse=base,effects=effects))
        gate=[]
        if preferences:
            # One teacher, then one distilled student; no automatic retry or candidate sweep.
            teacher=copy.deepcopy(self.net);opt=torch.optim.Adam(teacher.parameters(),lr=3e-4)
            xx=torch.tensor([p['x'] for p in preferences]);ss=teacher.scores(xx)
            pref=torch.stack([F.softplus(ss[j,p['worse']]-ss[j,p['better']]) for j,p in enumerate(preferences)]).mean()
            self.step(teacher,opt,pref);self.counters['candidate_trials']+=1
            def paired(candidate,label):
                results=[];snap=list(self.history)
                for rep in range(2):
                    pair=[]
                    for model in (self.net,candidate):
                        self.history=deque(snap,maxlen=96)
                        # Separate actual executions, same initial state and exogenous noise.
                        task=Task(self.seed,f'dev-{block}-{label}',rep+4*(block%4),horizon=3)
                        score,_,_=self.episode(task,records,model,False,role=label);pair.append(score)
                    results.append(pair)
                # Both policies' actual facts remain in replay; restore unselected branch-local context.
                self.history=deque(snap,maxlen=96)
                passed=all(p[1]['distance']<p[0]['distance'] for p in results) and sum(p[1]['success'] for p in results)>=sum(p[0]['success'] for p in results)
                gate.append(dict(kind=label,pairs=results,passed=passed));return passed
            self.counters['teacher_gates']+=1
            if paired(teacher,'teacher_gate'):
                self.counters['teacher_pass']+=1
                student=copy.deepcopy(self.net);so=torch.optim.Adam(student.parameters(),lr=3e-4)
                real=torch.tensor([r['x'] for r in records])
                with torch.no_grad():probs=teacher.scores(real).softmax(-1)
                sl=F.kl_div(student.scores(real).log_softmax(-1),probs,reduction='batchmean')
                self.step(student,so,sl);self.counters['sleep_updates']+=1;self.counters['student_gates']+=1
                if paired(student,'student_gate'):
                    self.net.load_state_dict(student.state_dict());self.counters['adoptions']+=1
                    # New student has no inherited Adam moments from the rejected/teacher path.
                    self.optimizer=torch.optim.Adam(self.net.parameters(),lr=3e-4)
        while self.total_steps-begin<budget:
            remaining=budget-(self.total_steps-begin)
            task=Task(self.seed,'train',self.next_episode,horizon=min(6,remaining));self.next_episode+=1
            score,_,_=self.episode(task,records);scores.append(score)
        assert self.total_steps-begin==budget
        rows=self.rng.sample(list(self.replay),min(128,len(self.replay)))
        loss,detail=self.ordinary_loss(self.net,rows);self.step(self.net,self.optimizer,loss)
        self.counters['ordinary_updates']+=1;self.counters['fact_targets']+=len(rows) if self.factual else 0
        with torch.no_grad():
            for target,current in zip(self.target.parameters(),self.net.parameters()):target.lerp_(current,.05)
        return dict(group=self.group,seed=self.seed,block=block,charged_steps=budget,total_steps=self.total_steps,
                    updates=self.total_updates-updates_before,total_updates=self.total_updates,
                    losses=detail,counters=dict(self.counters),before=before,after=digest(self.net),
                    main_tasks=scores,preferences=preferences,gates=gate,records=records,
                    history_nodes=len(self.history),replay_nodes=len(self.replay))
    def evaluate(self,index,episodes):
        clone=copy.deepcopy(self);start=clone.total_steps;rows=[];raw=[]
        for e in range(episodes):
            task=Task(self.seed,'report',e,horizon=6)
            score,_,_=clone.episode(task,raw,training=False);rows.append(score)
        return dict(rows=rows,actual_steps=clone.total_steps-start,raw=raw,optimizer_steps=0)
    def checkpoint(self):
        return dict(kind='portable_reference_not_legacy_game_checkpoint',group=self.group,seed=self.seed,
                    model=self.net.state_dict(),target=self.target.state_dict(),optimizer=self.optimizer.state_dict(),
                    history=list(self.history),replay=list(self.replay),rng=self.rng.getstate(),
                    total_steps=self.total_steps,total_updates=self.total_updates,next_episode=self.next_episode,
                    counters=self.counters)
