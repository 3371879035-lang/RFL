"""V196: real interventions, real behavioral teachers, verified student adoption.

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

class Capture:
    def __init__(self,d):
        self.raw=gzip.open(d/'raw.jsonl.gz','xt',encoding='utf-8',compresslevel=1)
        self.events=gzip.open(d/'events.jsonl.gz','xt',encoding='utf-8',compresslevel=1)
        self.counts={};self.steps=0;self.episodes=0;self.optimizers=0
        self.data=[];self.started=time.perf_counter()
    def event(self,kind,**kw):
        self.events.write(json.dumps(dict(kind=kind,**kw),separators=(',',':'),allow_nan=False)+'\n')
    def step(self,kind,episode,w,before,action,proposed,fact,a):
        self.steps+=1;self.counts[kind]=self.counts.get(kind,0)+1
        reward=None if a.arm=='F0' else .015+fact.pickup-a.penalty*fact.captured
        row=dict(id=self.steps,rollout=self.episodes,kind=kind,episode=episode,map=w.map_id,mode=w.mode,t=w.t,
            before=list(before),hero=w.hero.tolist(),monsters=w.monsters.tolist(),action=int(action),
            proposed=int(proposed),pickup=int(fact.pickup),captured=bool(fact.captured),
            completed=bool(fact.completed),collected=w.collected,score=1.5*w.t+100*w.collected,
            reward=reward)
        self.raw.write(json.dumps(row,separators=(',',':'))+'\n')
        return self.steps,reward
    def close(self):self.raw.close();self.events.close()

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
        if cap.steps>=93750:raise RuntimeError('Per-job share of declared environment budget exhausted')
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

def collect(agent,bank,cap,cycle):
    traces=[];cases=[];prefs=[];source_rows=[]
    for i in range(8):
        ep=1960000+cycle*100+i
        a,w,o=new_episode(agent,bank,'train',ep)
        tr,snaps=rollout(a,w,o,cap,'source',ep,True,snapshots=True)
        traces.append(tr);source_rows.append(tr)
        eligible=[s for s in snaps if tr['records'][s['index']]['stationary']]
        if len(cases)<2 and tr['captured'] and tr['steps']<=96 and eligible:
            s=eligible[0];s['source']=tr;cases.append(s)
    for ci,s in enumerate(cases):
        root=s['world'];root_pin=world_hash(root)
        original=s['source']['records'][s['index']]['action']
        legal=root.observe().legal
        acts=list(dict.fromkeys([original,(original%8+2)%8,(original%8-2)%8]))
        acts=[x for x in acts if legal[x]]
        out=[]
        for act in acts:
            w=world_clone(root)
            tr,_=rollout(s['actor'],w,w.observe(),cap,'trial',s['source']['episode'],True,act,s['prefix'])
            traces.append(tr);out.append(tr)
            if act==original:
                orig=s['source']['records'][s['index']:]
                rep=tr['records'][s['index']:]
                assert len(orig)==len(rep)
                assert all(x['action']==y['action'] and x['pickup']==y['pickup'] and
                    x['captured']==y['captured'] and np.array_equal(x['next_image'],y['next_image'])
                    for x,y in zip(orig,rep)), 'Real source continuation did not reproduce under exact branch restoration'
            assert world_hash(root)==root_pin,'Trial mutated its parent world'
        root_record=out[0]['records'][s['index']]
        ims=np.stack([r['image'] for r in out[0]['records'][:s['index']+1]])
        scs=np.stack([r['scalar'] for r in out[0]['records'][:s['index']+1]])
        vals=[t['score'] for t in out]
        if agent.arm!='RL-RP':
            for j in range(1,len(acts)):
                if vals[j]!=vals[0]:
                    better,worse=(acts[j],acts[0]) if vals[j]>vals[0] else (acts[0],acts[j])
                    prefs.append(dict(images=ims,scalars=scs,positive=better,negative=worse,
                        case=ci,difference=vals[j]-vals[0]))
        cap.event('intervention',cycle=cycle,case=ci,source_episode=s['source']['episode'],
            root_t=root.t,root_hash=root_pin,actions=acts,actual_scores=vals,
            prefix_records_reused=len(s['prefix']),root_preserved=True,original_reproduced=True,
            preference_channel=agent.arm!='RL-RP')
    cap.data.extend(traces)
    return traces,prefs,dict(cases=len(cases),preferences=len(prefs),sources=len(source_rows),
                            source_scores=[x['score'] for x in source_rows])

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
    rng=rng_for(a.seed,'v196-optimizer',cycle,role)
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

def run_job(binding):
    seed,arm=binding['seed'],binding['arm'];d=HERE/'evidence'/f'seed{seed}'/arm
    d.mkdir(parents=True,exist_ok=False);cap=Capture(d);start=time.perf_counter()
    result=dict(seed=seed,arm=arm,cycles=[],source=binding,status='RUNNING')
    checkpoints={};history=[];order='weak'
    try:
        source=ROOT/binding['path'];assert sha(source)==binding['sha256']
        with gzip.open(source,'rb') as f:loaded=torch.load(f,map_location='cpu',weights_only=False)
        live=loaded['agent'];assert isinstance(live,Agent) and live.training_steps==147456
        live.configure_v196('v196');live.label_events=[];live._v196_extra=None
        result['source_parameter_hash']=nh(live.net)
        result['old_partial_preserved']=dict(episode=loaded['episode'],world_t=loaded['world'].t,done=loaded['world'].done)
        del loaded
        bank=MapBank(ROOT/'experiments/v09r/spatial_feedback_v178/evidence_prepare/maps')
        all_data=[]
        for cycle in range(2):
            cycle_before=cap.steps;parent_hash=nh(live.net)
            traces,prefs,case_report=collect(live,bank,cap,cycle);all_data.extend(traces)
            # Ordinary reference really learns, including all new trial outcomes.
            ref,ref_fit=fit(live,all_data,[],32,1.,cap,cycle,'ordinary')
            probe_start=1961000+cycle*100
            ref_probe=evaluate(ref,bank,cap,'train',probe_start,16,'reference_probe')
            recipe,meta=dream_order(history,order);order=recipe
            cap.event('dream',cycle=cycle,parent_hash=parent_hash,**meta)
            recipes=['weak','strong'] if cycle==0 else [recipe,'strong' if recipe=='weak' else 'weak']
            children={};teachers={};fit_reports={};selected=None
            for name in recipes:
                teacher,fr=fit(live,all_data,prefs,16,{'weak':.25,'strong':1.}[name],cap,cycle,name)
                val=evaluate(teacher,bank,cap,'train',probe_start,16,'teacher_probe')
                children[name]=val;teachers[name]=teacher;fit_reports[name]=fr
                checkpoints[f'cycle{cycle}_{name}']=copy.deepcopy(teacher.net.state_dict())
                if val['mean']>ref_probe['mean'] and (selected is None or val['mean']>children[selected]['mean']):selected=name
                if cycle==1 and selected is not None:break
            history.append(dict(parent_hash=parent_hash,reference_mean=ref_probe['mean'],
                children={k:dict(mean=v['mean'],hash=v['parameter_hash'],fit=fit_reports[k]) for k,v in children.items()}))
            student=student_gate=ref_gate=None;sleep_report=None;matched_sleep_reference=None;adopted=False
            if selected is not None:
                teacher=teachers[selected];wake=[]
                for j in range(8):
                    ep=1963000+cycle*100+j
                    a,w,o=new_episode(ref,bank,'train',ep)
                    tr,_=rollout(a,w,o,cap,'student_wake',ep,True,shadow=teacher)
                    wake.append(tr)
                cap.data.extend(wake);all_data.extend(wake)
                student,sleep_report=fit(ref,wake,[],16,1.,cap,cycle,'student',kd=True)
                ref,matched_sleep_reference=fit(ref,wake,[],16,1.,cap,cycle,'sleep_ordinary_reference')
                checkpoints[f'cycle{cycle}_student']=copy.deepcopy(student.net.state_dict())
                ref_gate=evaluate(ref,bank,cap,'train',1962000+cycle*100,16,'reference_gate')
                student_gate=evaluate(student,bank,cap,'train',1962000+cycle*100,16,'student_gate')
                adopted=student_gate['mean']>ref_gate['mean'] and student_gate['captured']<=ref_gate['captured']
            before_adopt=nh(live.net)
            assert before_adopt==parent_hash,'Candidate training mutated deployed parent'
            live=student if adopted else ref
            cap.event('adopt',cycle=cycle,parent_hash=parent_hash,teacher=selected,adopted=adopted,
                reference_hash=nh(ref.net),student_hash=None if student is None else nh(student.net),
                deployed_hash=nh(live.net),student_gate=student_gate,reference_gate=ref_gate)
            # Report bank is only read after the adoption decision is fixed.
            final_ref=evaluate(ref,bank,cap,'v196-report',4096+cycle*64,64,'reference_report')
            final_teacher=evaluate(teachers[selected],bank,cap,'v196-report',4096+cycle*64,64,'teacher_report') if selected is not None else None
            final_live=evaluate(live,bank,cap,'v196-report',4096+cycle*64,64,'deployed_report') if adopted else dict(final_ref,shared_exact_reference=True)
            if student is not None and not adopted:
                final_student=evaluate(student,bank,cap,'v196-report',4096+cycle*64,64,'rejected_student_report')
            elif adopted:final_student=final_live
            else:final_student=None
            row=dict(cycle=cycle,cases=case_report,parent_hash=parent_hash,reference_fit=ref_fit,
                dream=meta,teachers={k:dict(probe=v,fit=fit_reports[k]) for k,v in children.items()},
                teacher_selected=selected,sleep=sleep_report,student_adopted=adopted,
                matched_sleep_reference=matched_sleep_reference,teacher_report=final_teacher,
                reference_gate=ref_gate,student_gate=student_gate,
                reference_report=final_ref,deployed_report=final_live,student_report=final_student,
                environment_steps=cap.steps-cycle_before)
            result['cycles'].append(row)
            save(d/f'checkpoint_cycle{cycle}.pt.gz',dict(agent=live,history=history,networks=checkpoints))
            cap.event('cycle_complete',cycle=cycle,teacher=selected,adopted=adopted,
                reference=final_ref['mean'],deployed=final_live['mean'])
            cap.raw.flush();cap.events.flush()
            print(json.dumps(dict(seed=seed,arm=arm,cycle=cycle,teacher=selected,adopted=adopted,
                reference=final_ref['mean'],deployed=final_live['mean'])),flush=True)
        result['status']='COMPLETE'
    except BaseException:
        result['status']='ERROR_PARTIAL';result['error']=traceback.format_exc()
        print(result['error'],flush=True)
    finally:
        result.update(environment_steps=cap.steps,actual_rollouts=cap.episodes,optimizer_updates=cap.optimizers,
            step_counts=cap.counts,wall_seconds=time.perf_counter()-start)
        cap.close();save(d/'data.pt.gz',cap.data)
        write(d/'result.json',result)
    return result

def main():
    out=HERE/'evidence';out.mkdir(exist_ok=False)
    contract=json.loads((HERE/'contract.json').read_text(encoding='utf-8'))
    inputs=[p for p in HERE.iterdir() if p.suffix in ('.py','.json')]
    binding=json.loads((HERE/'checkpoint_binding.json').read_text())['files']
    maps=json.loads((HERE/'map_binding.json').read_text())['files']
    pins={p.relative_to(ROOT).as_posix():sha(p) for p in inputs}
    for item in binding+maps:
        assert sha(ROOT/item['path'])==item['sha256'],item['path']
        pins[item['path']]=item['sha256']
    write(out/'claim.json',dict(started_utc=utc(),parent_git=contract['parent_git'],inputs=pins))
    start=time.perf_counter()
    results=[];aborted=False;remaining=iter(binding)
    with cf.ProcessPoolExecutor(max_workers=4) as pool:
        active={pool.submit(run_job,next(remaining)) for _ in range(4)}
        while active:
            done,active=cf.wait(active,return_when=cf.FIRST_COMPLETED)
            for f in done:
                row=f.result();results.append(row)
                if row['status']!='COMPLETE':aborted=True
            if not aborted:
                for _ in done:
                    item=next(remaining,None)
                    if item is not None:active.add(pool.submit(run_job,item))
    changed=[p for p,h in pins.items() if sha(ROOT/p)!=h]
    summary=dict(status='COMPLETE' if not changed and len(results)==16 and all(r['status']=='COMPLETE' for r in results) else 'PARTIAL_OR_ERROR',
        started_elapsed_seconds=time.perf_counter()-start,changed_inputs=changed,jobs=len(results),
        environment_steps=sum(r['environment_steps'] for r in results),
        actual_rollouts=sum(r['actual_rollouts'] for r in results),
        optimizer_updates=sum(r['optimizer_updates'] for r in results),results=results,finished_utc=utc())
    write(out/'summary.json',summary)
    if summary['environment_steps']>contract['budget']['max_environment_steps']:raise RuntimeError('Declared environment budget exceeded')
    return 0 if summary['status']=='COMPLETE' else 1

if __name__=='__main__':sys.exit(main())
