"""V8 conditional mixtures of evidence persistence, not causal change probabilities."""
import math
import torch
from torch import nn
from feedback_program_v214.network import ContextLift, log_prior
from feedback_program_v215 import DecisionSeparatedNet


class PersistenceGate(nn.Module):
    def __init__(self, cardinalities, rates=(0., .002, .02, .2), conditional=True):
        super().__init__()
        if not rates or len(set(rates))!=len(rates) or any(not 0<=r<1 for r in rates):
            raise ValueError('Declare distinct reopening hypotheses in [0,1)')
        self.lift=ContextLift(cardinalities,conditional)
        self.rate_values=tuple(rates)
        c=self.lift.cells;r=len(rates)
        self.register_buffer('rates',torch.tensor(rates,dtype=torch.float64))
        self.register_buffer('log_sources',torch.full((c,r,2),-math.log(2),dtype=torch.float64))
        self.register_buffer('log_rates',torch.full((c,r),-math.log(r),dtype=torch.float64))
        self.register_buffer('log_partitions',log_prior(self.lift.partitions,len(cardinalities)))
        self.register_buffer('visits',torch.zeros(c,dtype=torch.int64))
        self.updates=0
        self.eval().requires_grad_(False)

    def predict(self, rows, historical, current):
        indices=self.lift(rows)
        w=(1-self.rates)[None,None,:,None]*torch.softmax(self.log_sources[indices],-1)+self.rates[None,None,:,None]/2
        rho=torch.softmax(self.log_rates[indices],-1)
        q=torch.softmax(self.log_partitions,0)
        sources=torch.stack((historical,current),dim=1)
        per_rate=torch.einsum('bgre,beao->bgrao',w,sources)
        per_group=torch.einsum('bgr,bgrao->bgao',rho,per_rate)
        prediction=torch.einsum('g,bgao->bao',q,per_group)
        share=torch.einsum('g,bgr,bgr->b',q,rho,w[:,:,:,0])
        rate_marginal=torch.einsum('g,bgr->br',q,rho)
        return prediction,share,{'indices':indices,'weights':w,'rate_weights':rho,'rate_predictions':per_rate,
                                'group_predictions':per_group,'sources':sources,'partition_weights':q,
                                'rate_marginal':rate_marginal}

    @torch.no_grad()
    def observe(self, cache, action, outcome):
        if cache['indices'].shape[0]!=1:raise ValueError('One actual observation per update')
        cells=cache['indices'][0]
        likelihood=cache['sources'][0,:,action,outcome]
        source_joint=cache['weights'][0].log()+likelihood.log()[None,None,:]
        self.log_sources[cells]=source_joint-torch.logsumexp(source_joint,-1,keepdim=True)
        rate_joint=cache['rate_weights'][0].log()+cache['rate_predictions'][0,:,:,action,outcome].log()
        self.log_rates[cells]=rate_joint-torch.logsumexp(rate_joint,-1,keepdim=True)
        self.log_partitions+=cache['group_predictions'][0,:,action,outcome].log()
        self.log_partitions-=torch.logsumexp(self.log_partitions,0)
        self.visits[cells]+=1;self.updates+=1


class PersistenceFeedbackNet(DecisionSeparatedNet):
    def __init__(self, historical, temporal, history, rates=(0.,.002,.02,.2), epsilon=.2, goal=(0.,1.)):
        super().__init__(historical,temporal,history,epsilon,goal)
        self.gate=PersistenceGate(historical.cardinalities,rates)
        self.mode='rate_mixture_v216' if len(rates)>1 else 'no_reopening_v216'
        self.eval().requires_grad_(False)

    def predict(self, rows):
        p,mu,share,cache=super().predict(rows)
        cache['rate_marginal']=cache['gate']['rate_marginal']
        return p,mu,share,cache

    @torch.no_grad()
    def offer(self, context, observation_id):
        wire=super().offer(context,observation_id);cache=self.pending[1]
        marginal=cache['rate_marginal'][0]
        wire.update(rate_hypotheses=list(self.gate.rate_values),rate_weights=marginal.tolist(),
                    mean_reopening_rate=float((marginal*self.gate.rates).sum()),
                    rate_semantics='predictive_persistence_not_environment_change_probability')
        return wire
