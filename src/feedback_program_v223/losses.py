"""Observed-data likelihood: canonical coordinates, learned visibility, correlated outcomes."""
import torch
from torch.nn import functional as F
from feedback_program_v222.memory import actual_sequence
from feedback_program_v222.losses import decision_path_loss,comparison_nll,off_policy_loss,replay_distillation_loss


def observed_gaussian_log_prob(mean,lower,value,observed):
    indices=observed.nonzero().flatten();covariance=lower@lower.transpose(-1,-2)
    marginal=covariance.index_select(-2,indices).index_select(-1,indices)
    distribution=torch.distributions.MultivariateNormal(mean.index_select(-1,indices),scale_tril=torch.linalg.cholesky(marginal))
    return distribution.log_prob(value.index_select(-1,indices))


def sequence_nll(model,bank,event_ids):
    if bank.layout!=model.layout:raise ValueError('Likelihood uses the model measurement layout')
    memory,events=actual_sequence(bank,event_ids);p=next(model.parameters());k=model.config.hypotheses
    tensor=lambda x:torch.as_tensor(x,device=p.device,dtype=p.dtype)
    root=model.root(tensor([events[0].observation]),tensor([events[0].goal]),memory);h=root['h'][0];joint=p.new_zeros(k);terms=[]
    for event in events:
        obs=tensor([event.observation]).expand(k,-1);goal=tensor([event.goal]).expand(k,-1);actions=tensor([event.actions]).expand(k,-1,-1)
        state,_,_=model.state_kernel(obs,goal,actions,root['encoded'].expand(k,-1,-1),root['valid'].expand(k,-1),h,torch.arange(k,device=p.device));state=state[:,event.action_index]
        innovation,mask=bank.layout.innovations(event);u=tensor(innovation).expand(k,-1);m=tensor(mask).expand(k,-1)
        dt=tensor(float(event.terminal)).expand(k);gg=tensor(float(event.goal_met)).expand(k)
        mask_ll=-F.binary_cross_entropy_with_logits(model.visibility_head(state),m,reduction='none').sum(-1)
        tl,gl=model.discrete(state,m,dt)
        discrete_ll=-F.binary_cross_entropy_with_logits(tl,dt,reduction='none')-F.binary_cross_entropy_with_logits(gl,gg,reduction='none')
        mean,lower=model.continuous(state,m,dt,gg)
        nxt=tensor(event.next_observation).expand(k,-1);value=torch.cat((nxt,u),-1)
        observed=torch.cat((torch.ones(model.schema.observation,dtype=torch.bool,device=p.device),m[0].bool()))
        continuous_ll=observed_gaussian_log_prob(mean,lower,value,observed)
        step=mask_ll+discrete_ll+continuous_ll;joint=joint+step
        terms.append({'mask':mask_ll,'discrete':discrete_ll,'continuous':continuous_ll,'step':step,'observed_continuous_coordinates':int(observed.sum())})
        h=model.update_observed_belief(h,obs,actions[:,event.action_index],nxt,u,m,goal,gg,dt)
    log_prior=model.mixture_head(root['context']).log_softmax(-1)[0]
    loss=-torch.logsumexp(log_prior+joint,dim=0)
    return loss,{'component_log_likelihood':joint,'log_prior':log_prior,'terms':terms,'history_ids':memory['ids'],'target_ids':tuple(event_ids)}
