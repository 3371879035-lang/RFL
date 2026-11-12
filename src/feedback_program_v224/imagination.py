"""Independent policy decisions; CRN physical noise; exact forced-decision replay."""
from dataclasses import asdict,dataclass
import torch
from feedback_program_v220.network import joint_moments


@dataclass(frozen=True)
class ThoughtNode:
    arm:int
    hypothesis:int
    depth:int
    parent:int|None
    observation:tuple
    action_index:int
    next_observation:tuple
    innovation:tuple
    innovation_mask:tuple
    next_variance:tuple
    innovation_variance:tuple
    goal_met:bool
    terminal:bool
    original_weight:float


def noise_tape(seed,depth,hypotheses,observation,innovations,arms):
    g=torch.Generator().manual_seed(seed)
    return {'seed':seed,'normal':torch.randn(depth,hypotheses,observation+innovations,generator=g),
            'mask':torch.rand(depth,hypotheses,innovations,generator=g),'terminal':torch.rand(depth,hypotheses,generator=g),
            'goal':torch.rand(depth,hypotheses,generator=g),'action':torch.rand(depth,arms,generator=g),'continue':torch.rand(depth,arms,generator=g)}


def unfold(model,output,codes,tape,replay_decisions=None):
    if codes.shape[0]!=1:raise ValueError('One actual context per thought session')
    p=next(model.parameters());d=model.config.width;k=model.config.hypotheses;j=codes.shape[1];root=output['_root']
    weights=root['weights'][0].detach();context=output['context'];horizon=len(tape['action'])
    obs=output['_observation'].detach().expand(j*k,-1).clone();goal=output['_goal'].detach().expand(j*k,-1)
    actions=output['_actions'].detach().expand(j*k,-1,-1);encoded=root['encoded'].detach().expand(j*k,-1,-1)
    valid=root['valid'].expand(j*k,-1);h=root['h'][0].detach().repeat(j,1);ki=torch.arange(k,device=p.device).repeat(j)
    thought=model.thought_init(torch.cat((context[:,None,:].expand(-1,j,-1),codes),-1))[0,:,None,:].expand(-1,k,-1)
    alive=torch.ones(j,k,dtype=torch.bool,device=p.device);parent=[[-1]*k for _ in range(j)]
    count=torch.zeros(j,dtype=torch.long,device=p.device);depths=torch.zeros_like(count)
    nodes=[];decisions=[];logp=thought.sum()*0;batches=0;allocated=0
    for depth in range(horizon):
        available=alive.any(-1)
        if not available.any():break
        pooled=(thought*weights[None,:,None]).sum(1)
        continuation=model.thought_continue(torch.cat((context.expand(j,-1),pooled,p.new_full((j,1),float(horizon-depth))),-1)).squeeze(-1)
        if replay_decisions is None:
            keep=available & (tape['continue'][depth].to(p)<continuation.detach().sigmoid())
        else:
            saved=replay_decisions[depth]
            if saved['depth']!=depth or saved['available']!=available.tolist():raise ValueError('Thought topology changed')
            keep=torch.tensor(saved['continue'],dtype=torch.bool,device=p.device)
            if (keep & ~available).any():raise ValueError('Inactive candidate continued')
        logp=logp+torch.where(keep,torch.nn.functional.logsigmoid(continuation),torch.nn.functional.logsigmoid(-continuation))[available].sum()
        alive=alive&keep[:,None]
        decision={'depth':depth,'available':available.tolist(),'continue':keep.tolist(),'continue_probability':continuation.detach().sigmoid().tolist()}
        if not alive.any():decisions.append(decision);break
        with torch.no_grad():physics=model.kernel(obs,goal,actions,encoded,valid,h,ki)
        batches+=1;allocated+=j*k
        w=weights[None,:]*alive;w=w/w.sum(-1,keepdim=True).clamp_min(torch.finfo(p.dtype).tiny)
        moments=joint_moments(w,physics['value_mean'].reshape(j,k,-1),physics['value_variance'].reshape(j,k,-1))
        state=torch.einsum('jk,jkad->jad',w,physics['state'].reshape(j,k,actions.shape[1],d))
        logits=model.actor_logits(state,moments,codes[0]);policy=logits.softmax(-1)
        if replay_decisions is None:
            choice=(tape['action'][depth].to(p)[:,None]>policy.detach().cumsum(-1)).sum(-1).clamp_max(policy.shape[-1]-1)
        else:
            choice=torch.tensor(saved['action'],dtype=torch.long,device=p.device)
        logp=logp+logits.log_softmax(-1)[torch.arange(j,device=p.device),choice][keep].sum()
        row=torch.arange(j*k,device=p.device);a=choice.repeat_interleave(k);action=actions[row,a]
        with torch.no_grad():
            sample=model.sample_observed(physics['state'][row,a],tape['mask'][depth].to(p).repeat(j,1),
                                         tape['terminal'][depth].to(p).repeat(j),tape['goal'][depth].to(p).repeat(j),tape['normal'][depth].to(p).repeat(j,1))
            nxt=sample['next_observation'];u=sample['innovation'];mask=sample['mask'];gg=sample['goal_met'];dt=sample['terminal']
            new_h=model.update_observed_belief(h,obs,action,nxt,u,mask,goal,gg,dt)
        features=torch.cat((obs,action,nxt,u,mask,sample['next_variance'],sample['innovation_variance'],gg[:,None],dt[:,None],p.new_full((j*k,1),float(depth))),-1)
        updated=model.thought_update(features.detach(),thought.reshape(j*k,d)).reshape(j,k,d)
        thought=torch.where(alive[:,:,None],updated,thought);count+=alive.sum(-1)
        depths=torch.where(keep,torch.full_like(depths,depth+1),depths)
        for arm,hypothesis in alive.nonzero().tolist():
            r=arm*k+hypothesis
            node=ThoughtNode(arm,hypothesis,depth,None if parent[arm][hypothesis]<0 else parent[arm][hypothesis],tuple(obs[r].tolist()),
                             int(choice[arm]),tuple(nxt[r].tolist()),tuple(u[r].tolist()),tuple(mask[r].bool().tolist()),
                             tuple(sample['next_variance'][r].tolist()),tuple(sample['innovation_variance'][r].tolist()),
                             bool(gg[r]),bool(dt[r]),float(weights[hypothesis]))
            parent[arm][hypothesis]=len(nodes);nodes.append(node)
        decision.update(action=choice.tolist(),policy=policy.detach().tolist(),active=alive.tolist(),
                        mask=mask.reshape(j,k,-1).bool().tolist(),visibility_probability=sample['visibility_probability'].reshape(j,k,-1).tolist(),
                        terminal=dt.reshape(j,k).bool().tolist(),terminal_probability=sample['terminal_probability'].reshape(j,k).tolist(),
                        goal_met=gg.reshape(j,k).bool().tolist(),goal_probability=sample['goal_probability'].reshape(j,k).tolist())
        decisions.append(decision);h=torch.where(alive.reshape(-1,1),new_h,h);obs=torch.where(alive.reshape(-1,1),nxt,obs)
        alive=alive&~dt.reshape(j,k).bool()
    if replay_decisions is not None and len(decisions)!=len(replay_decisions):raise ValueError('Thought path length changed')
    return {'summary':(thought*weights[None,:,None]).sum(1)[None,:,:],'depths':depths,'active_counts':count,'nodes':nodes,
            'internal_log_probability':logp,'decisions':decisions,'root_weights':weights,'kernel_batches':batches,
            'allocated_particle_rows':allocated,'noise_tape':tape,'force_continue':False,'fixed_action':None}


def thought_record(thought):
    return {'nodes':[asdict(n) for n in thought['nodes']],'depths':thought['depths'].tolist(),'active_counts':thought['active_counts'].tolist(),
            'internal_log_probability':float(thought['internal_log_probability'].detach()),'decisions':thought['decisions'],
            'root_weights':thought['root_weights'].tolist(),'kernel_batches':thought['kernel_batches'],'allocated_particle_rows':thought['allocated_particle_rows'],
            'noise_tape':{key:value.tolist() if isinstance(value,torch.Tensor) else value for key,value in thought['noise_tape'].items()},
            'force_continue':thought['force_continue'],'fixed_action':thought['fixed_action']}
