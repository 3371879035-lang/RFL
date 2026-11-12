"""Actual V225 network training, with conditional blocks and bounded real memory.

No optimizer sees imagined outcomes as physical labels. All policy replay and
world gradients are computed before the behavior snapshot changes.
"""
import copy
import json
import random
from dataclasses import asdict
import torch
from torch.nn import functional as F
from common import digest
from task import Task, ACTIONS, distance, layout, seed_for
from feedback_program_v225 import FilteredFeedbackNet, PracticeAgent, MemoryBank
from feedback_program_v225.identity import model_identity
from feedback_program_v225.losses import sequence_nll
from credit import evaluate_trace

class EvaluationAgent(PracticeAgent):
    def choose(self,logits):
        a=int(logits[0].argmax());p=[0.]*logits.shape[-1];p[a]=1.
        return a,1.,p

class Neural:
    group='N226'
    def __init__(self,seed):
        self.seed=seed;torch.manual_seed(seed)
        self.net=FilteredFeedbackNet(layout()).eval()
        world,policy=self.net.parameter_groups()
        critic={n:p for n,p in policy.items() if n.startswith('critic')}
        policy={n:p for n,p in policy.items() if not n.startswith('critic')}
        self.parts=(world,policy,critic)
        self.optimizer=torch.optim.Adam([dict(params=list(world.values()),lr=1e-4),
                    dict(params=list(policy.values()),lr=2e-4),dict(params=list(critic.values()),lr=2e-4)])
        self.bank=MemoryBank(self.net.schema,self.net.layout)
        self.rng=random.Random(seed_for(seed,'N226','behavior'))
        self.total_steps=0;self.total_updates=0;self.next_episode=0
        self.counters=dict(actual_trials=0,history_references=0,candidate_trials=0,teacher_gates=0,
                           teacher_pass=0,sleep_updates=0,student_gates=0,adoptions=0,ordinary_updates=0,
                           reward_packets=0,fact_targets=0,imagined_nodes=0,thoughts=0,filter_updates=0)
    def window(self, bank):
        # Keep complete real episodes; the full immutable raw trace remains archived.
        start=max(0,len(bank.events)-96)
        while start<len(bank.events) and bank.events[start].previous_id is not None:start+=1
        new=MemoryBank(bank.schema,bank.layout)
        for event in bank.events[start:]:new.add(event)
        return new
    def collect(self,block,budget=64):
        before=digest(self.net);initial_nodes=len(self.bank.events)
        agent=PracticeAgent(self.net,f'v226/{self.seed}/block{block}',self.rng,self.bank,thought_depth=2)
        begin=len(agent.bank.events);episodes=[];scores=[];external=[]
        def task(horizon,purpose):
            index=self.next_episode;self.next_episode+=1
            env=Task(self.seed,'train',index,horizon);episode=f'train/{index}/block{block}'
            prev=None;ids=[];last_state=None
            for step in range(horizon):
                obs=env.observation();last_state=copy.deepcopy(env)
                def execute(a):
                    result=env.execute(a);external.append(dict(episode=episode,step=step,observation=obs,goal=env.goal,
                                        action=a,result=result,kind='main'));return result
                event=agent.execute(obs,env.goal,ACTIONS,execute,episode,step,prev,purpose=purpose)
                ids.append(event.id);prev=event.id
            scores.append(dict(success=event.goal_met,distance=distance(event.next_observation),family=env.family,steps=horizon))
            episodes.append(dict(ids=ids,purpose=purpose))
            return event,last_state
        for _ in range(2):
            source,state=task(6,'source');trial_calls=[0]
            def trial(action):
                branch=copy.deepcopy(state);result=branch.execute(action,branch=200+trial_calls[0]);trial_calls[0]+=1
                external.append(dict(episode=source.episode,step=source.step,observation=source.observation,
                                     goal=source.goal,action=action,result=result,kind='trial'))
                return result
            agent.reflect(source,trial,budget=4)
        while len(agent.bank.events)-begin<budget:
            task(min(6,budget-(len(agent.bank.events)-begin)),'post_choice')
        trace=agent.export_trace(episodes)
        assert len(external)==len(agent.bank.events)-begin==budget
        replay=evaluate_trace(self.net,trace)
        # Goal-progress return only; actual compute/interaction costs are reported, not scalarized into it.
        policy_loss=replay['policy_losses'][0]
        critic_loss=replay['critic_losses'][0]
        self.optimizer.zero_grad(set_to_none=True)
        (policy_loss+.5*critic_loss).backward()
        policy_value=float(policy_loss.detach());critic_value=float(critic_loss.detach())
        replay_errors=replay['errors'];del replay
        # Uniformly sample complete current episodes, plus one complete historical episode.
        current=[ep['ids'] for ep in episodes]
        chosen=self.rng.sample(current,min(3,len(current)))
        old=[];chain=[]
        for e in agent.bank.events[:begin]:
            if e.previous_id is None:chain=[]
            chain.append(e.id)
            if e.terminal:old.append(list(chain));chain=[]
        if old:chosen.append(self.rng.choice(old))
        normalizer=sum(map(len,chosen));world_value=0.
        for ids in chosen:
            loss,detail=sequence_nll(self.net,agent.bank,ids)
            world_value+=float(loss.detach())/normalizer
            (loss/normalizer).backward();del loss,detail
        grads={}
        for name,part in zip(('world','policy','critic'),self.parts):
            parameters=list(part.values())
            norm=torch.nn.utils.clip_grad_norm_(parameters,5.)
            if not torch.isfinite(norm):raise FloatingPointError(f'Nonfinite {name} gradient')
            grads[name]=dict(norm=float(norm),tensors=sum(p.grad is not None for p in parameters))
        assert model_identity(self.net)==trace['model_id'], 'Behavior snapshot changed before gradients were complete'
        self.optimizer.step();self.total_updates+=1
        sleep_rows=[]
        # Conservative factual eligibility, not success-forcing: a tried candidate
        # beat a tried baseline at the same source and succeeded in a real later task.
        sessions={s['id']:s for s in trace['sessions']};eligible=set()
        for sid,s in sessions.items():
            groups={i:[] for i in range(len(s['arms']))}
            for r in s['receipts']:
                e=agent.bank.events[agent.bank.index[r['event_id']]];groups[r['arm']].append(distance(e.next_observation))
            if groups[0]:
                for arm,vals in groups.items():
                    if arm and vals and sum(vals)/len(vals)<sum(groups[0])/len(groups[0]):eligible.add((sid,arm))
        success_episodes={e.episode for e in agent.bank.events[begin:] if e.terminal and e.goal_met and e.role=='task'}
        for d in trace['decisions']:
            if d['kind']!='task':continue
            origin=d['code_origin'];e=agent.bank.events[agent.bank.index[d['event_id']]]
            if origin['kind']=='proposal' and (origin['session_id'],origin['arm']) in eligible and e.episode in success_episodes:
                sleep_rows.append(d)
        # Sleep is a separate conditional behavior-consolidation update. Stored
        # teacher probabilities are from ACTUAL behavior, not invented success.
        sleep_loss=None
        if sleep_rows:
            self.optimizer.zero_grad(set_to_none=True)
            sleep_rows=self.rng.sample(sleep_rows,min(8,len(sleep_rows)));total=0.
            for d in sleep_rows:
                e=agent.bank.events[agent.bank.index[d['event_id']]];stop=agent.bank.index[e.id]
                out=self.net(torch.tensor([e.observation]),torch.tensor([e.goal]),torch.tensor([e.actions]),
                             agent.bank.forecast_view(e.previous_id,stop))
                loss=F.kl_div(out['logits'].log_softmax(-1),torch.tensor([d['policy']]),reduction='batchmean')
                (loss/len(sleep_rows)).backward();total+=float(loss.detach())/len(sleep_rows)
            norm=torch.nn.utils.clip_grad_norm_(list(self.parts[1].values()),5.)
            if not torch.isfinite(norm):raise FloatingPointError('Nonfinite sleep gradient')
            self.optimizer.step();self.total_updates+=1;self.counters['sleep_updates']+=1;sleep_loss=total
        self.bank=self.window(agent.bank);self.total_steps+=budget
        self.counters['actual_trials']+=agent.counters['trial_steps']
        self.counters['candidate_trials']+=agent.counters['candidate_trials']
        self.counters['adoptions']+=agent.counters['adoptions']
        self.counters['history_references']+=budget if initial_nodes else budget-1
        self.counters['ordinary_updates']+=1;self.counters['fact_targets']+=normalizer
        self.counters['reward_packets']+=agent.counters['task_steps']
        self.counters['imagined_nodes']+=sum(len(t['nodes']) for t in agent.thoughts)
        self.counters['thoughts']+=len(agent.thoughts);self.counters['filter_updates']+=len(agent.filter_receipts)
        after=digest(self.net)
        if before==after:raise AssertionError('Training produced no actual parameter update')
        return dict(group=self.group,seed=self.seed,block=block,charged_steps=budget,total_steps=self.total_steps,
                    updates=1+int(sleep_loss is not None),total_updates=self.total_updates,
                    before=before,after=after,losses=dict(world_nll_per_event=world_value,policy=policy_value,
                    critic=critic_value,sleep=sleep_loss),gradients=grads,counters=dict(self.counters),
                    main_tasks=scores,history_nodes=len(self.bank.events),initial_history_nodes=initial_nodes,
                    credit_replay_errors=replay_errors,trace=trace,external=external,
                    world_training_ids=chosen,sleep_event_ids=[d['event_id'] for d in sleep_rows])
    @torch.no_grad()
    def evaluate(self,index,episodes):
        bank=MemoryBank.from_json(self.bank.to_json())
        agent=EvaluationAgent(self.net,f'v226-report/{self.seed}/{index}',random.Random(seed_for(self.seed,'report-policy')),bank,thought_depth=2)
        # The actual deterministic behavior has propensity one, not the softmax probability.
        rows=[];raw=[];before=digest(self.net)
        for e in range(episodes):
            task=Task(self.seed,'report',e);prev=None
            for step in range(6):
                obs=task.observation()
                def execute(a):
                    result=task.execute(a);raw.append(dict(observation=obs,goal=task.goal,action=a,result=result));return result
                event=agent.execute(obs,task.goal,ACTIONS,execute,f'report/{index}/{e}',step,prev,purpose='post_choice');prev=event.id
            rows.append(dict(success=event.goal_met,distance=distance(event.next_observation),family=task.family,steps=6))
        assert before==digest(self.net)
        return dict(rows=rows,actual_steps=len(raw),raw=raw,optimizer_steps=0)
    def checkpoint(self):
        return dict(kind='trained_V225_network_conditional_V226',seed=self.seed,model=self.net.state_dict(),
                    optimizer=self.optimizer.state_dict(),schema=asdict(self.net.schema),config=asdict(self.net.config),
                    layout=self.net.layout.to_dict(),memory=json.loads(self.bank.to_json()),rng=self.rng.getstate(),
                    total_steps=self.total_steps,total_updates=self.total_updates,next_episode=self.next_episode,
                    counters=self.counters,model_id=model_identity(self.net))
