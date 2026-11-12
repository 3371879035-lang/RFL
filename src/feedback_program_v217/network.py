"""Predictive evidence sharing, reliability uncertainty and trainable prior logits.

No truth/kernel import. Analytic initialization, no optimizer, no synthetic facts.
"""
import math
import torch
from torch import nn
from feedback_program_v210.network import Fact
from feedback_program_v214.network import ContextLift, log_prior
from feedback_program_v215 import DecisionSeparatedNet


def unique_facts(records):
    """Stable event id, not equal content, defines a repeated observation."""
    found = {}
    for fact in records:
        if type(fact) is not Fact:
            raise ValueError('Use factual records with stable event identities')
        if fact.id in found and found[fact.id] != fact:
            raise ValueError('Conflicting content for one factual identity')
        found[fact.id] = fact
    return list(found.values())


class NeuralPrior(nn.Module):
    def __init__(self, groups, rates, reliabilities):
        super().__init__()
        self.logits = nn.Parameter(torch.zeros(groups, rates, reliabilities, dtype=torch.float64))

    def forward(self):
        return torch.log_softmax(self.logits.flatten(1), -1).reshape_as(self.logits)


class SharedEvidenceGate(nn.Module):
    def __init__(self, cardinalities, shared=True, etas=(0., .25, .5), rates=(0., .002, .02, .2)):
        super().__init__()
        if not etas or not rates or any(not 0 <= x < 1 for x in (*etas, *rates)):
            raise ValueError('Declare nonempty rate/reliability grids in [0,1)')
        self.lift = ContextLift(cardinalities)
        self.shared = bool(shared)
        self.rate_values, self.eta_values = tuple(rates), tuple(etas)
        c, g, r, b = self.lift.cells, len(self.lift.partitions), len(rates), len(etas)
        self.prior = NeuralPrior(g, r, b)
        self.register_buffer('rates', torch.tensor(rates, dtype=torch.float64))
        self.register_buffer('etas', torch.tensor(etas, dtype=torch.float64))
        self.register_buffer('log_sources', torch.full((c,r,b,2), -math.log(2), dtype=torch.float64))
        self.register_buffer('log_likelihood', torch.zeros(c,r,b, dtype=torch.float64))
        self.register_buffer('partition_prior', log_prior(self.lift.partitions, len(cardinalities)))
        self.register_buffer('visits', torch.zeros(c, dtype=torch.int64))
        self.register_buffer('cell_groups', torch.tensor([i for i,n in enumerate(self.lift.sizes) for _ in range(n)]))
        self.updates = 0

    def hyper_posterior(self):
        lp = self.prior()
        if self.shared:
            evidence = torch.stack([self.log_likelihood[s:s+n].sum(0)
                                    for s,n in zip(self.lift.offsets,self.lift.sizes)])
            joint = self.partition_prior[:,None,None]+lp+evidence
            logz = torch.logsumexp(joint.flatten(), 0)
            return torch.exp(joint-logz), logz
        local_joint = lp[self.cell_groups]+self.log_likelihood
        local_z = torch.logsumexp(local_joint.flatten(1), -1)
        group_z = torch.stack([local_z[s:s+n].sum() for s,n in zip(self.lift.offsets,self.lift.sizes)])
        log_group = self.partition_prior+group_z
        logz = torch.logsumexp(log_group, 0)
        q = torch.softmax(log_group, 0)
        conditional = torch.softmax(local_joint.flatten(1), -1).reshape_as(local_joint)
        return (q, conditional), logz

    def predict(self, rows, historical, current):
        indices = self.lift(rows)
        v = ((1-self.rates)[None,None,:,None,None]*torch.softmax(self.log_sources[indices], -1)
             + self.rates[None,None,:,None,None]/2)
        raw = torch.stack((historical,current), dim=1)
        source = ((1-self.etas)[None,:,None,None,None]*raw[:,None]
                  + self.etas[None,:,None,None,None]/raw.shape[-1])
        per_hypothesis = torch.einsum('ngrke,nkeao->ngrkao', v, source)
        posterior, logz = self.hyper_posterior()
        if self.shared:
            joint = posterior[None].expand(len(rows),-1,-1,-1)
        else:
            q, conditional = posterior
            joint = q[None,:,None,None]*conditional[indices]
        prediction = torch.einsum('ngrk,ngrkao->nao', joint, per_hypothesis)
        omega = joint[:,:,:,:,None]*v
        within = torch.einsum('ngrke,nkeao->nao', omega, source*(1-source))
        second = torch.einsum('ngrke,nkeao->nao', omega, source.square())
        between = second-prediction.square()
        share = omega[:,:,:,:,0].sum((1,2,3))
        cache = {'indices':indices,'weights':v,'sources':source,'hypotheses':per_hypothesis,
                 'joint':joint,'rate_marginal':joint.sum((1,3)), 'eta_marginal':joint.sum((1,2)),
                 'within':within,'between':between,'log_evidence':logz}
        return prediction,share,cache

    @torch.no_grad()
    def observe(self, cache, action, outcome):
        if cache['indices'].shape[0] != 1:
            raise ValueError('One real result per cached prediction')
        cells = cache['indices'][0]
        likelihood = cache['sources'][0,:,:,action,outcome]
        joint = cache['weights'][0].log()+likelihood.log()[None,None,:,:]
        self.log_sources[cells] = joint-torch.logsumexp(joint, -1, keepdim=True)
        self.log_likelihood[cells] += cache['hypotheses'][0,:,:, :,action,outcome].log()
        self.visits[cells] += 1
        self.updates += 1


class PriorUncertaintyNet(DecisionSeparatedNet):
    def __init__(self, historical, temporal, history, shared=True, etas=(0.,.25,.5), epsilon=.2, goal=(0.,1.)):
        archive = unique_facts(history)
        super().__init__(historical, temporal, archive, epsilon, goal)
        self.gate = SharedEvidenceGate(historical.cardinalities, shared, etas)
        self.mode = ('shared_' if shared else 'local_')+('raw' if len(etas)==1 else 'calibrated')+'_v217'
        self._facts = {f.id:f for f in archive}
        self.eval()  # Prior parameters remain trainable; this run does not optimize them.

    def predict(self, rows):
        fresh, parts = self.current.predict(rows)
        historical = self.historical(rows)
        prediction, share, gate = self.gate.predict(rows,historical,fresh)
        behavior, scores, margin = self.readout(prediction)
        cache = {'parts':parts,'gate':gate,'history':historical,'fresh':fresh,
                 'decision_scores':scores,'estimated_margin':margin,
                 'source_mixture_behavior':share[:,None]*self._policy(historical)+(1-share[:,None])*self._policy(fresh)}
        return prediction,behavior,share,cache

    def predictive_loss(self, rows, actions, outcomes):
        """Differentiable query loss. Does not add evidence or mutate a parameter.

        Callers must establish disjoint support/query chronology for training.
        """
        p = self(rows)
        index = torch.arange(len(rows))
        return -p[index,actions,outcomes].log().mean()

    @torch.no_grad()
    def offer(self, context, observation_id):
        wire = super().offer(context,observation_id)
        cache = self.pending[1]['gate']
        wire.update(self.uncertainty_wire(cache,0))
        return wire

    def uncertainty_wire(self, cache, i):
        rates = cache['rate_marginal'][i]
        etas = cache['eta_marginal'][i]
        return {'rate_hypotheses':list(self.gate.rate_values),'rate_weights':rates.detach().tolist(),
                'mean_reopening_rate':float((rates*self.gate.rates).sum().detach()),
                'eta_hypotheses':list(self.gate.eta_values),'eta_weights':etas.detach().tolist(),
                'mean_prediction_shrinkage':float((etas*self.gate.etas).sum().detach()),
                'within_component_variance':cache['within'][i].detach().tolist(),
                'between_component_variance':cache['between'][i].detach().tolist(),
                'rate_semantics':'predictive_persistence_not_environment_change_probability',
                'uncertainty_semantics':'model_mixture_decomposition_not_identified_physical_noise'}

    @torch.no_grad()
    def observe(self, offer, fact):
        if fact.id in self._facts:
            raise ValueError('Already recorded: replay must not add evidence')
        super().observe(offer,fact)
        self._facts[fact.id] = fact

    def replay_fact(self, fact):
        """Read the known event for future replay, without claiming a new sample."""
        if fact.id not in self._facts or self._facts[fact.id] != fact:
            raise ValueError('Replay must reference an unchanged, already observed event')
        return self._facts[fact.id]
