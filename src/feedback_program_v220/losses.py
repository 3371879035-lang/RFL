"""Differentiable training interfaces; callers supply factual targets and provenance."""
import math
import torch
from torch.nn import functional as F


def factual_nll(output,actions,next_observation,feedback,feedback_mask,value=None):
    b=torch.arange(actions.shape[0],device=actions.device)
    def logpdf(mean,variance,target):
        return -.5*(math.log(2*math.pi)+variance.log()+(target[:,None,:]-mean).square()/variance)
    nm=output['next_mean'][b,:,actions,:];nv=output['next_variance'][b,:,actions,:]
    fm=output['feedback_mean'][b,:,actions,:];fv=output['feedback_variance'][b,:,actions,:]
    joint=logpdf(nm,nv,next_observation).sum(-1)+(logpdf(fm,fv,feedback)*feedback_mask[:,None,:]).sum(-1)
    if value is not None:
        vm=output['value_mean'][b,:,actions];vv=output['value_variance'][b,:,actions]
        joint+=-.5*(math.log(2*math.pi)+vv.log()+(value[:,None]-vm).square()/vv)
    return -torch.logsumexp(output['weights'].log()+joint,-1).mean()


def off_policy_loss(logits,actions,behavior_probability,advantage):
    if bool((behavior_probability<=0).any()):raise ValueError('Recorded behavior support is required')
    current=torch.softmax(logits,-1).gather(-1,actions[:,None]).squeeze(-1)
    return -(current/behavior_probability.detach()*advantage.detach()).mean()


def replay_distillation_loss(logits,teacher_probability):
    return F.kl_div(F.log_softmax(logits,-1),teacher_probability.detach(),reduction='batchmean')
