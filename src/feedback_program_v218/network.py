"""Identity-initialized, evidence-conditioned bidirectional binary calibration.

Analytic basis maps; differentiable prior parameters; no optimizer or hidden kernel.
"""
import torch
from torch import nn
from feedback_program_v214.network import ContextLift,log_prior
from feedback_program_v216 import PersistenceFeedbackNet
from feedback_program_v217.network import unique_facts


class IdentityCalibrationHead(nn.Module):
    def __init__(self,cardinalities,actions=2,conditional=True,full=True):
        super().__init__()
        self.actions,self.conditional,self.full=actions,conditional,full
        self.lift=ContextLift((*cardinalities,actions),conditional)
        self.names=('identity','sharpen','flatten','raise_success','lower_success') if full else ('identity','sharpen','flatten')
        base=[.5,.125,.125,.125,.125] if full else [.5,.25,.25]
        self.register_buffer('base_prior',torch.tensor(base,dtype=torch.float64).log())
        self.prior_logits=nn.Parameter(torch.zeros(len(self.lift.partitions),len(base),dtype=torch.float64))
        self.register_buffer('log_ratio',torch.zeros(self.lift.cells,len(base),dtype=torch.float64))
        self.register_buffer('partition_prior',log_prior(self.lift.partitions,len(cardinalities)+1))
        self.register_buffer('cell_groups',torch.tensor([i for i,n in enumerate(self.lift.sizes) for _ in range(n)]))
        self.register_buffer('visits',torch.zeros(self.lift.cells,dtype=torch.int64))
        self.updates=0

    def log_priors(self):
        return torch.log_softmax(self.prior_logits+self.base_prior,-1)

    def posterior(self):
        joint=self.log_priors()[self.cell_groups]+self.log_ratio
        z=torch.logsumexp(joint,-1)
        group_z=torch.stack([z[s:s+n].sum() for s,n in zip(self.lift.offsets,self.lift.sizes)])
        groups=self.partition_prior+group_z
        return torch.softmax(groups,0),torch.softmax(joint,-1),torch.logsumexp(groups,0)

    def maps(self,base):
        p=base[...,1];u=p*(1-p);v=u*(2*p-1)
        shifts=torch.stack([torch.zeros_like(p),v,-v,u,-u] if self.full else [torch.zeros_like(p),v,-v],-1)
        return base[:,:,None,:]+torch.stack((-shifts,shifts),-1),u,v

    def predict(self,rows,base):
        if base.shape!=(len(rows),self.actions,2):raise ValueError('Binary outcome forecasts matching the public action schema required')
        indices=self.lift([(*x,a) for x in rows for a in range(self.actions)]).reshape(len(rows),self.actions,-1)
        group,local,logz=self.posterior()
        joint=group[None,None,:,None]*local[indices]
        mass=joint.sum(2)
        maps,u,v=self.maps(base)
        alpha=mass[:,:,1]-mass[:,:,2]
        beta=mass[:,:,3]-mass[:,:,4] if self.full else torch.zeros_like(alpha)
        delta=alpha*v+beta*u
        prediction=base+torch.stack((-delta,delta),-1)
        between=(mass*(maps[:,:,:,1]-prediction[:,:,None,1]).square()).sum(-1)
        within=(mass*maps[:,:,:,1]*(1-maps[:,:,:,1])).sum(-1)
        cache={'indices':indices,'maps':maps,'base':base,'mass':mass,
               'coefficients':torch.stack((alpha,beta),-1),'within':within,'between':between,'log_evidence_ratio':logz}
        return prediction,cache

    @torch.no_grad()
    def observe(self,cache,action,outcome):
        if cache['indices'].shape[0]!=1:raise ValueError('One observed action/result at a time')
        cells=cache['indices'][0,action]
        ratio=cache['maps'][0,action,:,outcome].log()-cache['base'][0,action,outcome].log()
        self.log_ratio[cells]+=ratio[None,:]
        self.visits[cells]+=1
        self.updates+=1

    def wire(self,cache,i):
        return {'calibration_names':list(self.names),'calibration_weights':cache['mass'][i].detach().tolist(),
                'calibration_coefficients':cache['coefficients'][i].detach().tolist(),
                'calibration_within_variance':cache['within'][i].detach().tolist(),
                'calibration_between_variance':cache['between'][i].detach().tolist(),
                'calibration_semantics':'conditional_predictive_maps_not_cause_probabilities'}


class BidirectionalFeedbackNet(PersistenceFeedbackNet):
    def __init__(self,historical,temporal,history,full=True,epsilon=.2,goal=(0.,1.)):
        if historical.outcomes!=2:raise ValueError('This finite calibration prototype uses binary outcomes')
        archive=unique_facts(history)
        super().__init__(historical,temporal,archive,epsilon=epsilon,goal=goal)
        self.calibrator=IdentityCalibrationHead(historical.cardinalities,historical.actions,True,full)
        self.mode='conditional_full_v218' if full else 'conditional_temperature_v218'
        self._facts={f.id:f for f in archive}
        self.eval()

    def predict(self,rows):
        base,_,share,cache=super().predict(rows)
        prediction,calibration=self.calibrator.predict(rows,base)
        behavior,scores,margin=self.readout(prediction)
        cache.update(base_prediction=base,calibration=calibration,decision_scores=scores,estimated_margin=margin)
        return prediction,behavior,share,cache

    @torch.no_grad()
    def offer(self,context,observation_id):
        wire=super().offer(context,observation_id);cache=self.pending[1]
        wire.update(base_prediction=cache['base_prediction'][0].tolist(),**self.calibrator.wire(cache['calibration'],0))
        return wire

    @torch.no_grad()
    def observe(self,offer,fact):
        if fact.id in self._facts:raise ValueError('Already recorded: replay is not a new observation')
        cache=self.pending[1]['calibration'] if self.pending is not None else None
        # The original API validates and consumes the event. Calibration uses the
        # saved BEFORE-result forecasts, never the freshly updated base predictor.
        super().observe(offer,fact)
        self.calibrator.observe(cache,fact.action,fact.outcome)
        self._facts[fact.id]=fact

    def replay_fact(self,fact):
        if fact.id not in self._facts or self._facts[fact.id]!=fact:raise ValueError('Replay needs an unchanged known event')
        return self._facts[fact.id]

    def predictive_loss(self,rows,actions,outcomes):
        p=self(rows)
        return -p[torch.arange(len(rows)),actions,outcomes].log().mean()
