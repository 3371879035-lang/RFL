"""Temporary open-loop particle thoughts. No environment call or factual-bank write."""
from dataclasses import asdict
import torch
from feedback_program_v220.network import joint_moments
from .memory import ThoughtNode


def noise_tape(seed,depth,hypotheses,observation,feedback):
    g=torch.Generator(device='cpu').manual_seed(seed)
    return {'seed':seed,'normal':torch.randn(depth,hypotheses,observation+feedback,generator=g),
            'action':torch.rand(depth,generator=g),'terminal':torch.rand(depth,hypotheses,generator=g),
            'continue':torch.rand(depth,generator=g)}


def categorical(probabilities,uniform):
    return (uniform>probabilities.detach().cumsum(-1)).sum(-1).clamp_max(probabilities.shape[-1]-1)


def unfold(model,output,codes,tape,force_continue=False,fixed_action=None):
    if codes.shape[0]!=1:raise ValueError('One actual decision context per thought session')
    p=next(model.parameters());d=model.config.width;k=model.config.hypotheses;j=codes.shape[1]
    o,f=model.schema.observation,model.schema.feedback;horizon=tape['action'].numel()
    root=output['_root'];weights=root['weights'][0].detach();context=output['context'].detach()
    obs=output['_observation'].detach().expand(j*k,-1).clone()
    goal=output['_goal'].detach().expand(j*k,-1)
    actions=output['_actions'].detach().expand(j*k,-1,-1)
    encoded=root['encoded'].detach().expand(j*k,-1,-1);valid=root['valid'].expand(j*k,-1)
    h=root['h'][0].detach().repeat(j,1);hypothesis=torch.arange(k,device=p.device).repeat(j)
    thought=model.thought_init(torch.cat((context[:,None,:].expand(-1,j,-1),codes),-1))[0,:,None,:].expand(-1,k,-1)
    alive=torch.ones(j,k,dtype=torch.bool,device=p.device);parent=[[-1]*k for _ in range(j)]
    active_counts=torch.zeros(j,dtype=torch.long,device=p.device);depths=torch.zeros_like(active_counts)
    nodes=[];decisions=[];log_probability=thought.sum()*0;kernel_batches=0;allocated_rows=0
    for depth in range(horizon):
        available=alive.any(-1)
        if not available.any():break
        pooled=(thought*weights[None,:,None]).sum(1)
        rem=p.new_full((j,1),float(horizon-depth))
        continue_logits=model.thought_continue(torch.cat((context.expand(j,-1),pooled,rem),-1)).squeeze(-1)
        continue_probability=continue_logits.sigmoid()
        keep=torch.ones_like(available) if force_continue else tape['continue'][depth].to(p)<continue_probability.detach()
        keep=keep&available
        selected=torch.where(keep,torch.nn.functional.logsigmoid(continue_logits),torch.nn.functional.logsigmoid(-continue_logits))
        if not force_continue:log_probability=log_probability+selected[available].sum()
        alive=alive&keep[:,None]
        record={'depth':depth,'available':available.tolist(),'continue_probability':continue_probability.detach().tolist(),
                'continue':keep.tolist(),'forced_continue':bool(force_continue)}
        if not alive.any():decisions.append(record);break
        with torch.no_grad():
            physics=model.kernel(obs,goal,actions,encoded,valid,h,hypothesis)
        kernel_batches+=1;allocated_rows+=j*k
        value_mean=physics['value_mean'].reshape(j,k,-1);value_var=physics['value_variance'].reshape(j,k,-1)
        # Survivorship normalization is only a planner summary, never a new factual posterior.
        planner_weight=weights[None,:]*alive
        planner_weight=planner_weight/planner_weight.sum(-1,keepdim=True).clamp_min(torch.finfo(p.dtype).tiny)
        moments=joint_moments(planner_weight,value_mean,value_var)
        state=torch.einsum('jk,jkad->jad',planner_weight,physics['state'].reshape(j,k,actions.shape[1],d))
        logits=model.actor_logits(state,moments,codes[0]);policy=logits.softmax(-1)
        choice=categorical(policy,tape['action'][depth].to(p)) if fixed_action is None else torch.full((j,),fixed_action,device=p.device,dtype=torch.long)
        if fixed_action is None:log_probability=log_probability+logits.log_softmax(-1)[torch.arange(j,device=p.device),choice][keep].sum()
        selected_action=choice.repeat_interleave(k);row=torch.arange(j*k,device=p.device)
        with torch.no_grad():
            nm=physics['next_mean'][row,selected_action];nv=physics['next_variance'][row,selected_action]
            fm=physics['feedback_mean'][row,selected_action];fv=physics['feedback_variance'][row,selected_action]
            eps=tape['normal'][depth].to(p).repeat(j,1)
            next_obs=nm+nv.sqrt()*eps[:,:o];feedback=fm+fv.sqrt()*eps[:,o:]
            terminal_probability=physics['terminal_logits'][row,selected_action].sigmoid()
            terminal=tape['terminal'][depth].to(p).repeat(j)<terminal_probability
            actual_action=actions[row,selected_action]
            new_h=model.update_belief(h,obs,actual_action,next_obs,feedback,torch.ones_like(feedback),goal)
        thought_input=torch.cat((obs,actual_action,next_obs,feedback,nv,fv,terminal.to(p.dtype)[:,None],p.new_full((j*k,1),float(depth))),-1)
        new_thought=model.thought_update(thought_input.detach(),thought.reshape(j*k,d)).reshape(j,k,d)
        thought=torch.where(alive[:,:,None],new_thought,thought)
        depths=torch.where(keep,torch.full_like(depths,depth+1),depths);active_counts+=alive.sum(-1)
        for arm,ki in alive.nonzero().tolist():
            r=arm*k+ki
            node=ThoughtNode(arm,ki,depth,None if parent[arm][ki]<0 else parent[arm][ki],tuple(obs[r].tolist()),
                             int(choice[arm]),tuple(next_obs[r].tolist()),tuple(feedback[r].tolist()),
                             tuple(nv[r].tolist()),tuple(fv[r].tolist()),bool(terminal[r]),float(weights[ki]))
            parent[arm][ki]=len(nodes);nodes.append(node)
        record.update(action=choice.tolist(),action_policy=policy.detach().tolist(),forced_action=fixed_action,
                      active=alive.tolist(),terminal_probability=terminal_probability.reshape(j,k).tolist(),
                      terminal=terminal.reshape(j,k).tolist())
        decisions.append(record)
        h=torch.where(alive.reshape(-1,1),new_h,h);obs=torch.where(alive.reshape(-1,1),next_obs,obs)
        alive=alive&~terminal.reshape(j,k)
    return {'summary':(thought*weights[None,:,None]).sum(1)[None,:,:],'depths':depths,'active_counts':active_counts,
            'nodes':nodes,'internal_log_probability':log_probability,'decisions':decisions,'root_weights':weights,
            'kernel_batches':kernel_batches,'allocated_particle_rows':allocated_rows,'noise_tape':tape,
            'force_continue':bool(force_continue),'fixed_action':fixed_action}


def thought_record(thought):
    return {'nodes':[asdict(n) for n in thought['nodes']],'depths':thought['depths'].tolist(),
            'active_counts':thought['active_counts'].tolist(),'root_weights':thought['root_weights'].tolist(),
            'internal_log_probability':float(thought['internal_log_probability'].detach()),'decisions':thought['decisions'],
            'summary':thought['summary'].detach().tolist(),'kernel_batches':thought['kernel_batches'],
            'allocated_particle_rows':thought['allocated_particle_rows'],
            'noise_tape':{key:value.tolist() if isinstance(value,torch.Tensor) else value for key,value in thought['noise_tape'].items()},
            'force_continue':thought['force_continue'],'fixed_action':thought['fixed_action']}
