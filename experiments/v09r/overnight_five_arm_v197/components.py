"""V197 reusable branch/learning primitives; native V196 is never invoked.

No original fixture is called. Historical Replay is read-only; newly executed
sequences are a separate factual training store, not fabricated old replay UIDs.
"""
import os
os.environ['OMP_NUM_THREADS']='1'
os.environ['MKL_NUM_THREADS']='1'
import concurrent.futures as cf
import copy, datetime, gzip, hashlib, json, sys, time, traceback
from collections import deque
from pathlib import Path
import numpy as np
import torch
from torch.nn import functional as F
from learning import Agent
from future_facts import HORIZONS, goal_scores
from world import MapBank, World, rng_for

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
torch.set_num_threads(1)
torch.set_num_interop_threads(1)

def utc(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def write(path,value):
    with Path(path).open('x',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def nh(net):
    h=hashlib.sha256()
    for p in net.state_dict().values():h.update(p.detach().numpy().tobytes())
    return h.hexdigest()
def save(path,obj):
    with gzip.open(path,'xb',compresslevel=1) as f:torch.save(obj,f)
def tiny_clone(a,trainable=False):
    b=copy.copy(a)
    for k in ('atlas','retrieval_summary','nearest'):
        setattr(b,k,getattr(a,k).copy())
    b.h=a.h.clone();b.counters=a.counters.copy()
    b.episode_rows=list(a.episode_rows)
    b.last_choice=copy.deepcopy(getattr(a,'last_choice',{}))
    b._v196_extra=None;b._selected_starts=None;b._sleep_teacher=None
    b.replay_rng=copy.deepcopy(a.replay_rng)
    if trainable:
        b.net=copy.deepcopy(a.net)
        b.target_net=copy.deepcopy(a.target_net)
        b.optimizer=torch.optim.Adam(b.net.parameters(),lr=3e-4)
        b.optimizer.load_state_dict(copy.deepcopy(a.optimizer.state_dict()))
    return b
def world_clone(w):
    b=copy.copy(w)
    for k in ('hero','treasures','treasure_alive','buffs','buff_ready','monsters'):
        setattr(b,k,getattr(w,k).copy())
    b.trajectory=[x.copy() for x in w.trajectory]
    # Map geometry and pre-generated exogenous uniforms are immutable references.
    return b
def world_hash(w):
    h=hashlib.sha256()
    for k in ('hero','treasures','treasure_alive','buffs','buff_ready','monsters','uniform'):
        h.update(getattr(w,k).tobytes())
    h.update(np.array(w.trajectory).tobytes())
    h.update(str((w.map_id,w.mode,w.t,w.cooldown,w.buff_left,w.collected,w.buff_collected,w.done)).encode())
    return h.hexdigest()
def scores(net,h,q_enabled):
    return net.q(h) if q_enabled else torch.stack([goal_scores(m(h)) for m in net.measurements]).mean(0)

def frame(a,obs,action,nxt,fact,uid,reward,teacher_scores=None):
    target=np.zeros(10,np.float32);mask=np.zeros(10,np.float32)
    target[:2]=(np.array(nxt.hero)-np.array(obs.hero))/10;mask[:2]=1
    for m in range(2):
        if obs.monster_visible[m] and nxt.monster_visible[m]:
            target[2+2*m:4+2*m]=(nxt.monster_positions[m]-obs.monster_positions[m])/2
            mask[2+2*m:4+2*m]=1
    target[6:8]=fact.pickup,fact.captured;mask[6:8]=1
    return dict(image=a.last_input[0].copy(),scalar=a.last_input[1].copy(),legal=obs.legal.copy(),
        action=int(action),reward=reward,pickup=int(fact.pickup),captured=bool(fact.captured),
        done=bool(fact.captured or fact.completed),target=target,mask=mask,
        next_image=nxt.image.copy(),next_legal=nxt.legal.copy(),uid=uid,
        teacher_scores=teacher_scores)

def rollout(agent,w,obs,cap,kind,episode,training=False,forced=None,prefix=None,shadow=None,snapshots=False):
    a=tiny_clone(agent);records=list(prefix or []);tail=[];recent=deque(maxlen=8)
    begin_t=w.t
    if shadow is not None:
        shadow=tiny_clone(shadow);shadow.reset_episode('train',episode)
    while not w.done:
        cap.check_step(kind)
        if snapshots:
            recent.append(dict(world=world_clone(w),actor=tiny_clone(a),prefix=list(records),index=len(records)))
        proposed=a.act(obs,training)
        action=int(forced) if forced is not None and w.t==begin_t else int(proposed)
        ts=None
        if shadow is not None:
            shadow.act(obs,False)
            with torch.no_grad():ts=scores(shadow.net,shadow.h,shadow.q_enabled)[0].numpy().copy()
        before=tuple(obs.hero);nxt,fact=w.step(action)
        uid,reward=cap.step(kind,episode,w,before,action,proposed,fact,a)
        r=frame(a,obs,action,nxt,fact,uid,reward,ts)
        r['stationary']=before==tuple(nxt.hero)
        a.advance_frozen(action,fact)
        if shadow is not None:shadow.advance_frozen(action,fact)
        r['next_scalar']=a._features(nxt)[0].copy()
        records.append(r);tail.append(r);obs=nxt
    trace=dict(kind=kind,episode=episode,begin_t=begin_t,records=records,
        new_ids=[r['uid'] for r in tail],prefix_reused_ids=[r['uid'] for r in records[:begin_t]],
        steps=w.t,treasures=w.collected,captured=bool(fact.captured),completed=bool(fact.completed),
        score=float(1.5*w.t+100*w.collected))
    cap.episodes+=1
    cap.event('episode',rollout=cap.episodes-1,phase=kind,episode=episode,begin_t=begin_t,steps=w.t,score=trace['score'],
        captured=trace['captured'],completed=trace['completed'],new_steps=len(tail))
    return trace,list(recent)

def new_episode(agent,bank,phase,episode):
    a=tiny_clone(agent);a.reset_episode(phase,episode)
    w=World(bank,a.seed,phase,episode)
    return a,w,w.observe()

def evaluate(agent,bank,cap,phase,start,count,kind):
    before=nh(agent.net);rows=[]
    for ep in range(start,start+count):
        a,w,o=new_episode(agent,bank,phase,ep)
        tr,_=rollout(a,w,o,cap,kind,ep)
        rows.append({k:tr[k] for k in ('episode','steps','treasures','captured','completed','score')})
    assert nh(agent.net)==before
    return dict(mean=float(np.mean([r['score'] for r in rows])),
        mean_steps=float(np.mean([r['steps'] for r in rows])),captured=sum(r['captured'] for r in rows),
        rows=rows,parameter_hash=before)

def batch(traces,rng,batch_size=8):
    im=np.zeros((batch_size,25,5,21,21),np.float32)
    sc=np.zeros((batch_size,25,184),np.float32);res=np.ones((batch_size,25),np.float32)
    selected=[];futures=[]
    for b in range(batch_size):
        tr=traces[int(rng.integers(len(traces)))];rs=tr['records'];t=int(rng.integers(len(rs)))
        seq=rs[max(0,t-23):t+1]
        start=24-len(seq)
        for j,r in enumerate(seq):im[b,start+j]=r['image'];sc[b,start+j]=r['scalar']
        im[b,24]=rs[t]['next_image'];sc[b,24]=rs[t]['next_scalar']
        res[b,start+1:]=0
        selected.append(rs[t])
        futures.append([[min(h,len(rs)-t)/h,sum(r['pickup'] for r in rs[t:t+h])] for h in HORIZONS])
    return tuple(torch.from_numpy(x) for x in (im,sc,res)),selected,torch.tensor(futures,dtype=torch.float32)

def extra_loss(agent,traces,prefs,strength,rng,shadow_kd):
    tensors,rs,future=batch(traces,rng)
    h=agent.net.unroll(*tensors);cur,nxt=h[:,-2],h[:,-1]
    actions=torch.tensor([r['action'] for r in rs],dtype=torch.long)
    done=torch.tensor([r['done'] for r in rs],dtype=torch.float32)
    legal=torch.from_numpy(np.stack([r['next_legal'] for r in rs]))
    if agent.q_enabled:
        with torch.no_grad():
            th=agent.target_net.unroll(*tensors)[:,-1]
            best=agent.net.q(nxt.detach()).masked_fill(~legal,-1e9).argmax(-1)
            y=torch.tensor([r['reward'] for r in rs],dtype=torch.float32)+.99*(1-done)*agent.target_net.q(th).gather(-1,best[:,None]).squeeze(-1)
        pred=agent.net.q(cur).gather(-1,actions[:,None]).squeeze(-1)
        ordinary=F.smooth_l1_loss(pred,y)
    else:
        ordinary=cur.sum()*0
        for m in agent.net.measurements:
            pred=m(cur).gather(1,actions[:,None,None,None].expand(-1,1,4,2)).squeeze(1)
            ordinary=ordinary+F.smooth_l1_loss(pred,future)/3
    loss=ordinary*(strength if agent.arm=='RL-RP' else 1.)
    preference=cur.sum()*0
    if prefs and agent.arm!='RL-RP':
        for p in prefs:
            images=torch.from_numpy(p['images'][None].astype(np.float32))
            scalars=torch.from_numpy(p['scalars'][None].astype(np.float32))
            resets=torch.zeros(1,images.shape[1]);resets[:,0]=1
            hidden=agent.net.unroll(images,scalars,resets)[:,-1]
            z=scores(agent.net,hidden,agent.q_enabled)[0]
            preference=preference+F.softplus(-(z[p['positive']]-z[p['negative']])/.25)/len(prefs)
        loss=loss+strength*preference
    kd=cur.sum()*0
    if shadow_kd:
        assert all(r['teacher_scores'] is not None for r in rs)
        lt=torch.from_numpy(np.stack([r['legal'] for r in rs]))
        target=torch.tensor(np.stack([r['teacher_scores'] for r in rs])).masked_fill(~lt,-1e9)
        current=scores(agent.net,cur,agent.q_enabled).masked_fill(~lt,-1e9)
        kd=F.kl_div(F.log_softmax(current/.25,-1),F.softmax(target/.25,-1),reduction='batchmean')
        loss=loss+kd
    agent._extra_stats=dict(real_loss=float(ordinary.detach()),preference_loss=float(preference.detach()),
                           behavior_kl=float(kd.detach()),preferences=len(prefs) if agent.arm!='RL-RP' else 0)
    return loss

def preference_margins(agent,prefs):
    values=[]
    with torch.no_grad():
        for p in prefs:
            im=torch.from_numpy(p['images'][None].astype(np.float32))
            sc=torch.from_numpy(p['scalars'][None].astype(np.float32))
            re=torch.zeros(1,im.shape[1]);re[:,0]=1
            z=scores(agent.net,agent.net.unroll(im,sc,re)[:,-1],agent.q_enabled)[0]
            values.append(float(z[p['positive']]-z[p['negative']]))
    return values

def fit(parent,traces,prefs,n,strength,cap,cycle,role,kd=False):
    a=tiny_clone(parent,True);before=nh(a.net);m0=preference_margins(a,prefs)
    rng=rng_for(a.seed,'v197-shared-minibatches',cycle,'sleep' if role in ('student','sleep_ordinary_reference') else 'teacher')
    for step in range(n):
        a._v196_extra=lambda obj:extra_loss(obj,traces,prefs,strength,rng,kd)
        a.learn();cap.optimizers+=1
        cap.event('optimizer',cycle=cycle,role=role,step=step,arm=a.arm,**a._extra_stats,
                  total_loss=a.last_loss)
    a._v196_extra=None
    report=dict(role=role,updates=n,parent_hash=before,child_hash=nh(a.net),
                margins_before=m0,margins_after=preference_margins(a,prefs))
    cap.event('fit',cycle=cycle,**report)
    return a,report

def dream_order(history,incumbent):
    # One previously EXECUTED candidate per historical parent; no splicing.
    available=[h for h in history if set(h['children'])=={'weak','strong'}]
    if not available:return incumbent,dict(available_trees=0,selected=incumbent)
    replay={name:float(np.mean([max(0,h['children'][name]['mean']-h['reference_mean']) for h in available]))
            for name in ('weak','strong')}
    other='strong' if incumbent=='weak' else 'weak'
    selected=other if replay[other]>replay[incumbent] else incumbent
    return selected,dict(available_trees=len(available),replay_improvement=replay,
        prior=incumbent,selected=selected,budget='one recorded candidate per parent',
        no_unseen_children=True)
