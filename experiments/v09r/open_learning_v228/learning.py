"""Six matched-size learners. Actual practice precedes gated consolidation."""
import base64
import copy
import gzip
import json
import math
from collections import deque
from dataclasses import dataclass
import numpy as np
import torch
from torch.nn import functional as F
from core import (Environment,Network,GROUPS,HORIZONS,MemoryBank,packed,tensors,node,reward,
                  utility,action_scores,seed_for,fingerprint,write_json)

@dataclass
class Transition:
    source: tuple
    action: int
    next: tuple
    facts: np.ndarray
    terminal: bool
    labels: np.ndarray
    mask: np.ndarray

class State:
    def __init__(self,seed):
        torch.manual_seed(seed)
        self.net=Network()
        self.target=copy.deepcopy(self.net).eval()
        self.optimizer=torch.optim.Adam(self.net.parameters(),lr=3e-4)
        self.updates=0

    def clone(self):
        return copy.deepcopy(self)

def observation_wire(ob):
    return dict(image_bits=base64.b64encode(np.packbits(ob[0]).tobytes()).decode('ascii'),
                vector=ob[1].tolist(),legal=np.flatnonzero(ob[2]).tolist())

def aggregate_adoption(differences):
    return float(np.mean(differences)) > 0.

def signed_preference(gap, delta):
    return abs(delta) * F.softplus(-math.copysign(1., delta) * gap)

class Agent:
    def __init__(self,domain,seed,group,bank):
        self.domain=domain; self.seed=seed; self.group=group; self.bank=bank
        self.state=State(seed)
        self.replay=[]
        self.effects=[]
        self.memory_bank=MemoryBank(); self.memory=self.memory_bank.view()
        self.next_episode=0
        self.steps=0; self.updates=0; self.event_index=0
        self.env=None; self.episode_rows=[]; self.sources=[]; self.failed_sources=[]
        self.rng=np.random.default_rng(seed_for(seed,domain,'behavior'))
        self.counts=dict(real_trials=0,trial_steps=0,teacher_tests=0,teacher_pass=0,student_tests=0,
                         student_pass=0,sleep_updates=0,ordinary_updates=0,candidate_updates=0,
                         reward_packets=0,fact_labels=0,effect_pairs=0,effect_negative_or_zero=0,
                         actual_steps=0,ordinary_steps=0,gate_steps=0,actual_episodes=0)
        self.logs=[]; self.raw=None; self.round=0

    def scores(self,state,source):
        with torch.no_grad():
            b=tensors([source]); o=state.net(b)
            s=action_scores(o,self.group,b[1])[0].masked_fill(~b[2][0],-1e9)
        return s.numpy(),o

    def choose(self,state,source,epsilon,rng):
        s,_=self.scores(state,source)
        valid=np.flatnonzero(source[2])
        if rng.random()<epsilon:
            return int(rng.choice(valid))
        # Fixed, disclosed greedy tie convention; stochastic evaluation is also reported.
        return int(s.argmax())

    def append_transition(self,source,action,nxt,facts,done,episode_rows):
        tr=Transition(source,action,nxt,facts.copy(),bool(done),np.zeros((4,4),np.float32),np.zeros(4,bool))
        self.replay.append(tr); episode_rows.append(tr)
        n=len(episode_rows)
        for k,h in enumerate(HORIZONS):
            starts=[n-h] if n>=h else []
            if done: starts.extend(range(max(0,n-h+1),n))
            for start in starts:
                r=episode_rows[start]
                r.labels[k]=np.sum([x.facts for x in episode_rows[start:n]],axis=0)
                r.mask[k]=True; self.counts['fact_labels']+=1

    def actual_step(self,env,memory,state,action,purpose,episode_rows,episode_id):
        before=env.observation(); src=packed(before,memory)
        nxt,facts,done,raw=env.step(action)
        eid=f'{self.domain}/{self.seed}/{self.group}/{self.event_index}'
        self.event_index+=1; self.steps+=1; self.counts['actual_steps']+=1
        key='ordinary_steps' if purpose=='ordinary' else ('trial_steps' if purpose=='trial' else 'gate_steps')
        self.counts[key]+=1
        if self.group!='F0': self.counts['reward_packets']+=1
        nextmem=memory.extend(eid,node(before,action,nxt,facts,done))
        self.append_transition(src,action,packed(nxt,nextmem),facts,done,episode_rows)
        if done: self.counts['actual_episodes']+=1
        if self.raw:
            self.raw.write(json.dumps(dict(id=eid,episode=episode_id,purpose=purpose,source=observation_wire(before),
                memory_ids=memory.event_ids(),action=action,next=observation_wire(nxt),facts=facts.tolist(),
                terminal=done,observation_result=raw),separators=(',',':'),allow_nan=False)+'\n')
        return nextmem,facts,done

    def ordinary(self,n):
        for _ in range(n):
            self.memory=self.memory_bank.view()
            if self.env is None or self.env.done:
                self.env=Environment(self.domain,self.bank,self.seed,'train',self.next_episode)
                self.next_episode+=1; self.episode_rows=[]; self.sources=[]
            src=packed(self.env.observation(),self.memory)
            a=self.choose(self.state,src,max(.1,.5-.4*self.steps/30000),self.rng)
            if self.group!='RL-plain':
                self.sources.append(dict(env=self.env.clone(),memory=self.memory,source=src,action=a))
            self.memory,_,done=self.actual_step(self.env,self.memory,self.state,a,'ordinary',self.episode_rows,f'train/{self.next_episode-1}')
            self.memory=self.memory_bank.view()
            if done and not self.env.success:
                self.failed_sources.extend(self.sources)

    def update(self,state,indices,preference=None,teacher=None,kind='ordinary'):
        rows=[self.replay[int(i)] for i in indices]
        b=tensors([r.source for r in rows]); nb=tensors([r.next for r in rows])
        actions=torch.tensor([r.action for r in rows]); ii=torch.arange(len(rows))
        out=state.net(b); loss=torch.zeros(())
        info={}
        if self.group!='F0':
            rr=torch.tensor([reward(self.domain,r.facts,r.terminal,self.group in ('RL-plain','RL-outer','F-RP')) for r in rows],dtype=torch.float32)
            done=torch.tensor([r.terminal for r in rows],dtype=torch.float32)
            with torch.no_grad():
                online=state.net(nb)['q'].masked_fill(~nb[2],-1e9)
                target=state.target(nb)['q'][ii,online.argmax(-1)]
                y=rr+.99*(1-done)*target
            td=F.smooth_l1_loss(out['q'][ii,actions],y)
            loss=loss+td; info['td']=float(td.detach())
        if self.group not in ('RL-plain','RL-outer'):
            m=out['measurements'][ii,actions]
            labels=torch.from_numpy(np.stack([r.labels for r in rows]))
            mask=torch.from_numpy(np.stack([r.mask for r in rows]))
            # Deterministic bootstrap masks produce different factual hypotheses without imagined labels.
            boot=torch.stack([((torch.arange(len(rows))+state.updates+j*3)%5)!=j for j in range(3)],1)
            weight=(mask[:,None,:,None]&boot[:,:,None,None]).float()
            error=F.smooth_l1_loss(m,labels[:,None].expand_as(m),reduction='none')
            factual=(error*weight).sum()/(weight.sum()*4).clamp_min(1)
            loss=loss+factual; info['factual']=float(factual.detach())
        if self.group=='N228' and self.effects:
            pair=list(self.effects)[state.updates%len(self.effects)]
            po=state.net(tensors([pair['source']]))
            ep=po['effect'][0,pair['alternative']]-po['effect'][0,pair['baseline']]
            effect=F.smooth_l1_loss(ep,torch.tensor(pair['delta'],dtype=torch.float32))
            loss=loss+.1*effect; info['effect']=float(effect.detach())
        if preference is not None:
            pb=tensors([preference['source']]); po=state.net(pb)
            ps=action_scores(po,self.group,pb[1])[0]
            gap=ps[preference['alternative']]-ps[preference['baseline']]
            delta=preference['delta']
            pref=signed_preference(gap,delta)
            loss=loss+.2*pref; info['preference']=float(pref.detach())
        if teacher is not None:
            with torch.no_grad():
                to=teacher.net(b)
                ts=action_scores(to,self.group,b[1]).masked_fill(~b[2],-1e9)
                targetp=(ts/.5).softmax(-1)
            ss=action_scores(out,self.group,b[1]).masked_fill(~b[2],-1e9)
            kl=F.kl_div((ss/.5).log_softmax(-1),targetp,reduction='batchmean')*.25
            loss=loss+.5*kl; info['sleep_kl']=float(kl.detach())
        if not torch.isfinite(loss): raise RuntimeError('Nonfinite actual-data loss')
        state.optimizer.zero_grad(set_to_none=True); loss.backward()
        torch.nn.utils.clip_grad_norm_(state.net.parameters(),5.)
        state.optimizer.step(); state.updates+=1; self.updates+=1
        if state.updates%64==0: state.target.load_state_dict(state.net.state_dict())
        self.counts[{'ordinary':'ordinary_updates','candidate':'candidate_updates','sleep':'sleep_updates'}[kind]]+=1
        self.logs.append(dict(kind='optimizer',stage=kind,update=self.updates,loss=float(loss.detach()),parts=info))

    def batches(self,n,stage):
        rng=np.random.default_rng(seed_for(self.seed,self.domain,self.round,stage,'minibatches'))
        return [rng.integers(0,len(self.replay),size=32) for _ in range(n)]

    def actual_roll(self,env,state,memory,purpose,episode_id,maxsteps=None,first=None):
        episode_rows=[]; total=np.zeros(4,np.float32)
        for t in range(maxsteps or (256 if self.domain=='pursuit' else 6)):
            src=packed(env.observation(),memory)
            a=first if t==0 and first is not None else self.choose(state,src,0.,self.rng)
            memory,facts,done=self.actual_step(env,memory,state,a,purpose,episode_rows,episode_id)
            total+=facts
            if done: break
        return utility(self.domain,total),env.result()

    def full_gate(self,candidate,reference,stage):
        vals=[]; results=[]
        base_memory=self.memory_bank.view()
        for rep in range(2):
            idx=(self.round-1)*8+(0 if stage=='teacher' else 4)+rep
            env=Environment(self.domain,self.bank,self.seed,'v198-dev-v228',idx)
            key=seed_for(self.seed,self.domain,self.round,stage,rep,'paired-noise')
            u0,r0=self.actual_roll(env.clone(key),reference,base_memory,'gate',f'{stage}/{idx}/reference')
            u1,r1=self.actual_roll(env.clone(key),candidate,base_memory,'gate',f'{stage}/{idx}/candidate')
            vals.append(u1-u0); results.append(dict(reference=r0,candidate=r1))
        passed=aggregate_adoption(vals)
        self.counts[stage+'_tests']+=1
        self.counts[stage+'_pass']+=int(passed)
        self.logs.append(dict(kind='full_task_gate',stage=stage,differences=vals,passed=passed,results=results,
                              candidate=fingerprint(candidate.net),reference=fingerprint(reference.net)))
        return passed

    def investigate(self):
        if not self.failed_sources: return
        count=min(16,len(self.failed_sources))
        chosen=self.rng.choice(len(self.failed_sources),count,replace=False)
        options=[self.failed_sources[int(i)] for i in chosen]
        if self.group=='N228':
            ranks=[]
            for c in options:
                _,out=self.scores(self.state,c['source'])
                m=out['measurements'][0,c['action'],:,0]
                # Learned disagreement is a proposal heuristic, not a calibrated probability.
                ranks.append(float(m.var(0,unbiased=False).sum()))
            c=options[int(np.argmax(ranks))]
        else:
            c=options[int(self.rng.integers(len(options)))]
        scores,out=self.scores(self.state,c['source']); baseline=int(scores.argmax())
        legal=c['source'][2].copy(); legal[baseline]=False
        if self.group=='RL-outer':
            alternative=int(self.rng.choice(np.flatnonzero(legal)))
        else:
            m=out['measurements'][0,:,:,-1].clamp(0,1)
            weights=torch.from_numpy(c['source'][1][32:36])
            predicted=(m*weights).sum(-1)
            proposal=predicted.mean(-1)
            if self.group=='N228':
                proposal=proposal+.1*predicted.std(-1,unbiased=False)+out['effect'][0]
            alternative=int(proposal.masked_fill(~torch.from_numpy(legal),-1e9).argmax())
        differences=[]
        for rep in range(2):
            key=seed_for(self.seed,self.domain,self.round,'source-pair',rep)
            values=[]
            for a in (baseline,alternative):
                value,_=self.actual_roll(c['env'].clone(key),self.state,c['memory'],'trial',
                       f'trial/{self.round}/{rep}/{a}',maxsteps=16,first=a)
                self.counts['real_trials']+=1; values.append(value)
            differences.append(values[1]-values[0])
        pair=dict(source=c['source'],baseline=baseline,alternative=alternative,delta=float(np.mean(differences)))
        self.effects.append(pair); self.counts['effect_pairs']+=1
        self.counts['effect_negative_or_zero']+=int(pair['delta']<=0)
        self.logs.append(dict(kind='actual_pair',baseline=baseline,alternative=alternative,differences=differences,
                              delta=pair['delta'],source=observation_wire(c['env'].observation()),
                              memory_ids=c['memory'].event_ids(),source_policy=fingerprint(self.state.net)))
        if pair['delta']==0.: return  # Zero evidence has no signed preference target.
        teacher=self.state.clone(); reference=self.state.clone()
        for indices in self.batches(8,'teacher'):
            self.update(teacher,indices,preference=pair,kind='candidate')
            self.update(reference,indices)
        student=reference.clone(); ordinary=reference.clone()
        for indices in self.batches(8,'sleep'):
            self.update(student,indices,teacher=teacher,kind='sleep')
            self.update(ordinary,indices)
        self.state=student if self.full_gate(student,ordinary,'student') else ordinary

    def train_round(self,directory,round_index,steps=4096,updates=256):
        self.round=round_index; self.logs=[]
        start_steps=self.steps; start_updates=self.updates; before=fingerprint(self.state.net)
        path=directory/f'round{round_index:04d}_{self.group}.jsonl.gz'
        with gzip.open(path,'xt',encoding='utf-8',compresslevel=2) as output:
            self.raw=output
            self.ordinary(min(1024,steps//4))
            for indices in self.batches(min(160,updates-32),'warm'):
                self.update(self.state,indices)
            if steps>=2048 and updates>=64 and self.group!='RL-plain': self.investigate()
            remaining=steps-(self.steps-start_steps)
            if remaining<0: raise RuntimeError('Real interaction quota exceeded')
            self.ordinary(remaining)
            remaining_updates=updates-(self.updates-start_updates)
            if remaining_updates<0: raise RuntimeError('Optimizer quota exceeded')
            for indices in self.batches(remaining_updates,'finish'):
                self.update(self.state,indices)
            output.write(json.dumps(dict(kind='round_log',events=self.logs),separators=(',',':'),allow_nan=False)+'\n')
        self.raw=None
        assert self.steps-start_steps==steps and self.updates-start_updates==updates
        return dict(group=self.group,round=round_index,steps=self.steps,updates=self.updates,counts=dict(self.counts),
                    before=before,after=fingerprint(self.state.net),replay=len(self.replay),memory=len(self.memory),
                    events=len(self.logs),last_losses=[x for x in self.logs if x['kind']=='optimizer'][-5:])

    def evaluate(self,n,epsilon,phase='v198-report-v227'):
        # No replay, optimization, investigations or cross-evaluation-episode memory transfer.
        rows=[]; action_counts=np.zeros(16,np.int64)
        rng=np.random.default_rng(seed_for(self.seed,self.domain,'fixed-evaluation',epsilon))
        before=fingerprint(self.state.net)
        for index in range(n):
            env=Environment(self.domain,self.bank,self.seed,phase,index)
            evaluation_bank=MemoryBank()
            for eid,nd in zip(self.memory_bank.ids,self.memory_bank.nodes): evaluation_bank.add(eid,nd)
            memory=evaluation_bank.view()
            while not env.done:
                ob=env.observation(); src=packed(ob,memory)
                a=self.choose(self.state,src,epsilon,rng); action_counts[a]+=1
                nxt,f,done,_=env.step(a)
                memory=memory.extend(f'evaluation/{index}/{env.steps}',node(ob,a,nxt,f,done))
            rows.append(env.result())
        assert before==fingerprint(self.state.net)
        return dict(episodes=n,epsilon=epsilon,successes=sum(int(r['success']) for r in rows),
                    mean_score=float(np.mean([r['score'] for r in rows])),mean_steps=float(np.mean([r['steps'] for r in rows])),
                    mean_distance=float(np.mean([r['distance'] for r in rows])) if self.domain=='generic' else None,
                    actions=action_counts.tolist(),rows=rows,model=before,training_steps=self.steps)

    def checkpoint(self):
        return dict(group=self.group,domain=self.domain,seed=self.seed,network=self.state.net.state_dict(),
                    target=self.state.target.state_dict(),optimizer=self.state.optimizer.state_dict(),
                    memory_ids=self.memory_bank.ids,memory_nodes=self.memory_bank.nodes,steps=self.steps,updates=self.updates,counts=self.counts,
                    independent_evidence_events=self.event_index,resume_supported=False)
