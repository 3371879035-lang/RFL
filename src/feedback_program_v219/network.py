"""Exact continuous bias uncertainty; trainable priors, factual evidence buffers.

Binary outcome reference network. No world/kernel input, optimizer or pseudo-facts.
"""
import torch
from torch import nn
from feedback_program_v214.network import ContextLift, log_prior
from feedback_program_v218.network import BidirectionalFeedbackNet


class ContinuousBiasHead(nn.Module):
    def __init__(self, cardinalities, actions=2, conditional=True):
        super().__init__()
        self.actions = actions
        self.lift = ContextLift((*cardinalities, actions), conditional)
        groups, cells = len(self.lift.partitions), self.lift.cells
        self.names = ('identity', 'sharpen', 'flatten', 'continuous_bias')
        self.prior_logits = nn.Parameter(torch.zeros(groups, 4, dtype=torch.float64))
        self.log_concentration = nn.Parameter(torch.zeros(groups, dtype=torch.float64))
        self.register_buffer('base_prior', torch.tensor([.5,.125,.125,.25],dtype=torch.float64).log())
        self.register_buffer('partition_prior', log_prior(self.lift.partitions,len(cardinalities)+1))
        self.register_buffer('cell_groups', torch.tensor([i for i,n in enumerate(self.lift.sizes) for _ in range(n)]))
        self.register_buffer('log_discrete', torch.zeros(cells,3,dtype=torch.float64))
        self.register_buffer('log_coefficients', torch.zeros(cells,1,dtype=torch.float64))
        self.register_buffer('visits', torch.zeros(cells,dtype=torch.int64))
        self.updates = 0

    def bias_posterior(self):
        a = self.log_concentration.exp()[self.cell_groups,None]
        n = self.visits[:,None]
        j = torch.arange(self.log_coefficients.shape[1],dtype=torch.float64)[None,:]
        remainder = (n-j).clamp_min(0)  # Unvisited polynomial coefficients stay -inf.
        left, right = a+j, a+remainder
        log_integral = (torch.lgamma(left)+torch.lgamma(right)-torch.lgamma(2*a+n)
                        -2*torch.lgamma(a)+torch.lgamma(2*a))
        joint = self.log_coefficients+log_integral
        logz = torch.logsumexp(joint,-1)
        rho = torch.softmax(joint,-1)
        total = 2*a+n
        mean_w = (rho*left/total).sum(-1)
        second_w = (rho*left*(left+1)/(total*(total+1))).sum(-1)
        mean_b = 2*mean_w-1
        second_b = 4*second_w-4*mean_w+1
        return logz,mean_b,second_b

    def posterior(self):
        bias_z,mean_b,second_b = self.bias_posterior()
        logevidence = torch.cat((self.log_discrete,bias_z[:,None]),-1)
        prior = torch.log_softmax(self.prior_logits+self.base_prior,-1)
        local_joint = prior[self.cell_groups]+logevidence
        z = torch.logsumexp(local_joint,-1)
        group_z = torch.stack([z[s:s+n].sum() for s,n in zip(self.lift.offsets,self.lift.sizes)])
        glog = self.partition_prior+group_z
        return torch.softmax(glog,0),torch.softmax(local_joint,-1),mean_b,second_b,torch.logsumexp(glog,0)

    def predict(self,rows,base):
        if base.shape!=(len(rows),self.actions,2):
            raise ValueError('Binary outcome forecasts matching public actions required')
        indices = self.lift([(*x,a) for x in rows for a in range(self.actions)]).reshape(len(rows),self.actions,-1)
        group,local,bmean,bsecond,logz = self.posterior()
        joint = group[None,None,:,None]*local[indices]
        mass = joint.sum(2)
        alpha = mass[:,:,1]-mass[:,:,2]
        beta = (joint[:,:,:,3]*bmean[indices]).sum(-1)
        p = base[...,1];u = p*(1-p);v = u*(2*p-1)
        delta = alpha*v+beta*u
        prediction = base+torch.stack((-delta,delta),-1)
        delta_second = (mass[:,:,1]+mass[:,:,2])*v.square()+(joint[:,:,:,3]*bsecond[indices]).sum(-1)*u.square()
        between = (delta_second-delta.square()).clamp_min(0)
        within = prediction[...,1]*(1-prediction[...,1])-between
        bias_mass = mass[:,:,3]
        conditional_mean = beta/bias_mass
        conditional_second = (joint[:,:,:,3]*bsecond[indices]).sum(-1)/bias_mass
        shifts = torch.stack((torch.zeros_like(p),v,-v,-u,u),-1)
        maps = base[:,:,None,:]+torch.stack((-shifts,shifts),-1)
        cache = {'indices':indices,'base':base,'maps':maps,'mass':mass,'coefficients':torch.stack((alpha,beta),-1),
                 'within':within,'between':between,'bias_mean':conditional_mean,
                 'bias_variance':(conditional_second-conditional_mean.square()).clamp_min(0),'log_evidence_ratio':logz}
        return prediction,cache

    @torch.no_grad()
    def observe(self,cache,action,outcome):
        if cache['indices'].shape[0]!=1:raise ValueError('One cached actual event per update')
        cells = cache['indices'][0,action]
        ratios = cache['maps'][0,action,:,outcome].log()-cache['base'][0,action,outcome].log()
        self.log_discrete[cells] += ratios[:3][None,:]
        width = self.log_coefficients.shape[1]
        new_width = max(width,int(self.visits[cells].max())+2)
        if new_width>width:
            self.log_coefficients = torch.cat((self.log_coefficients,torch.full((self.lift.cells,new_width-width),-torch.inf,dtype=torch.float64)),-1)
        previous = self.log_coefficients[cells].clone()
        minus = previous+ratios[3]
        plus = torch.cat((torch.full((len(cells),1),-torch.inf,dtype=torch.float64),previous[:,:-1]),-1)+ratios[4]
        self.log_coefficients[cells] = torch.logaddexp(minus,plus)
        self.visits[cells] += 1
        self.updates += 1

    def wire(self,cache,i):
        return {'calibration_names':list(self.names),'calibration_weights':cache['mass'][i].detach().tolist(),
                'calibration_coefficients':cache['coefficients'][i].detach().tolist(),
                'calibration_within_variance':cache['within'][i].detach().tolist(),
                'calibration_between_variance':cache['between'][i].detach().tolist(),
                'bias_conditional_mean':cache['bias_mean'][i].detach().tolist(),
                'bias_conditional_variance':cache['bias_variance'][i].detach().tolist(),
                'calibration_semantics':'continuous_predictive_bias_uncertainty_not_cause_probability'}


class ContinuousPriorNet(BidirectionalFeedbackNet):
    def __init__(self,historical,temporal,history,epsilon=.2,goal=(0.,1.)):
        super().__init__(historical,temporal,history,full=True,epsilon=epsilon,goal=goal)
        self.calibrator = ContinuousBiasHead(historical.cardinalities,historical.actions)
        self.mode = 'continuous_prior_v219'
        self.eval()
