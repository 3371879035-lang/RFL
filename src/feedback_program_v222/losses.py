"""Actual-sequence world likelihood and separately routed decision objectives."""
import math
import torch
from torch.nn import functional as F
from feedback_program_v221.losses import comparison_nll,off_policy_loss,replay_distillation_loss
from .memory import actual_sequence


def gaussian_log_probability(target,mean,variance):
    return -.5*(math.log(2*math.pi)+variance.log()+(target-mean).square()/variance)


def sequence_nll(model,bank,event_ids):
    memory,events=actual_sequence(bank,event_ids);p=next(model.parameters());k=model.config.hypotheses
    tensor=lambda x:torch.as_tensor(x,device=p.device,dtype=p.dtype)
    first=events[0];root=model.root(tensor([first.observation]),tensor([first.goal]),memory)
    h=root['h'][0];joint=p.new_zeros(k);step_logs=[]
    for event in events:
        obs=tensor([event.observation]).expand(k,-1);goal=tensor([event.goal]).expand(k,-1)
        actions=tensor([event.actions]).expand(k,-1,-1);a=event.action_index
        result=model.kernel(obs,goal,actions,root['encoded'].expand(k,-1,-1),root['valid'].expand(k,-1),h,torch.arange(k,device=p.device))
        nxt=tensor(event.next_observation).expand(k,-1);feedback=tensor(event.feedback).expand(k,-1)
        mask=tensor(event.feedback_mask).expand(k,-1)
        ll=gaussian_log_probability(nxt,result['next_mean'][:,a],result['next_variance'][:,a]).sum(-1)
        ll=ll+(mask*gaussian_log_probability(feedback,result['feedback_mean'][:,a],result['feedback_variance'][:,a])).sum(-1)
        # Public goal outcome is a working scalar likelihood, not an oracle reward/Q*.
        ll=ll+gaussian_log_probability(tensor(float(event.goal_met)),result['value_mean'][:,a],result['value_variance'][:,a])
        ll=ll-F.binary_cross_entropy_with_logits(result['terminal_logits'][:,a],tensor(float(event.terminal)).expand(k),reduction='none')
        joint=joint+ll;step_logs.append(ll)
        h=model.update_belief(h,obs,actions[:,a],nxt,feedback,mask,goal)
    loss=-torch.logsumexp(root['weights'][0].log()+joint,dim=0)
    return loss,{'component_log_likelihood':joint,'step_log_likelihood':torch.stack(step_logs),
                 'root_weights':root['weights'][0],'history_ids':memory['ids'],'target_ids':tuple(event_ids)}


def decision_path_loss(internal_log_probability,external_log_probability,actual_advantage):
    advantage=torch.as_tensor(actual_advantage,device=external_log_probability.device,dtype=external_log_probability.dtype).detach()
    return -advantage*(internal_log_probability+external_log_probability)
