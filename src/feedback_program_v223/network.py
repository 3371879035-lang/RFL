"""Canonical feedback and pattern-conditioned correlated outcomes."""
from dataclasses import dataclass,replace
import torch
from torch import nn
from torch.nn import functional as F
from feedback_program_v220.network import mlp,joint_moments
from feedback_program_v221.network import NetworkConfig as PreviousConfig
from feedback_program_v222.network import RecurrentFeedbackNet
from .memory import Schema


@dataclass(frozen=True)
class NetworkConfig(PreviousConfig):
    width:int=320
    memory_slots:int=96
    forecast_samples:int=4


class ObservableFeedbackNet(RecurrentFeedbackNet):
    WORLD_GROUPS=(RecurrentFeedbackNet.WORLD_GROUPS-{'world_decoder','terminal_head'})|{'visibility_head','terminal_conditional','goal_conditional','joint_decoder'}
    def __init__(self,layout,schema=Schema(),config=NetworkConfig(),comparison_rank=8):
        layout.validate_schema(schema)
        super().__init__(schema,config,comparison_rank);self.layout=layout;self.innovations=len(layout.primitive_ids)
        d=config.width;o=schema.observation;p=self.innovations;self.continuous_width=o+p
        canonical=replace(schema,feedback=p)
        self.event_encoder=nn.Sequential(nn.Linear(canonical.event_features,d),nn.GELU(),nn.Linear(d,2*d),nn.GELU(),nn.Linear(2*d,d))
        del self.world_decoder;del self.terminal_head
        self.visibility_head=mlp(d,d,p);self.terminal_conditional=mlp(d+p,d,1);self.goal_conditional=mlp(d+p+1,d,1)
        y=self.continuous_width
        self.joint_decoder=mlp(d+p+2,2*d,y+y*(y+1)//2)
        self.belief_update=nn.GRUCell(2*o+schema.action+2*p+schema.goal+2,d)
        self.thought_update=nn.GRUCell(3*o+schema.action+3*p+3,d)
        self.proposal_net=mlp(2*d+p+1,2*d,d)
        self.register_buffer('forecast_uniforms',torch.rand(config.forecast_samples,p,generator=torch.Generator().manual_seed(223)))

    def state_kernel(self,observation,goal,actions,encoded,valid,h,hypothesis):
        query=self.query_encoder(torch.cat((observation,goal),-1));read,_,_=self.reader(query[:,None,:],encoded,valid)
        context=self.context_fusion(torch.cat((query,read[:,0]),-1))+self.belief_adapter(h)
        aq=query[:,None,:]+self.action_encoder(actions);ar,attention,gates=self.reader(aq,encoded,valid)
        state=self.action_fusion(torch.cat((aq,ar,context[:,None,:].expand_as(ar)),-1))
        return state+self.hypothesis_embeddings[hypothesis][:,None,:],attention,gates

    def discrete(self,state,mask,terminal=None):
        condition=torch.cat((state,mask),-1);terminal_logits=self.terminal_conditional(condition).squeeze(-1)
        goal_logits=None if terminal is None else self.goal_conditional(torch.cat((condition,terminal[...,None]),-1)).squeeze(-1)
        return terminal_logits,goal_logits

    def continuous(self,state,mask,terminal,goal_met):
        output=self.joint_decoder(torch.cat((state,mask,terminal[...,None],goal_met[...,None]),-1));n=self.continuous_width
        mean=output[...,:n];raw=output[...,n:];lower=raw.new_zeros(*raw.shape[:-1],n,n)
        i,j=torch.tril_indices(n,n,device=raw.device);lower[...,i,j]=raw
        diag=lower.diagonal(dim1=-2,dim2=-1)
        lower=lower-torch.diag_embed(diag)+torch.diag_embed(F.softplus(diag)+1e-3)
        return mean,lower

    @torch.no_grad()
    def forecast(self,state):
        """Finite fixed-node marginal approximation; no fabricated observations."""
        shape=state.shape[:-1];flat=state.reshape(-1,state.shape[-1]);n=flat.shape[0];s=self.config.forecast_samples;p=self.innovations
        probabilities=self.visibility_head(flat).sigmoid()
        mask=(self.forecast_uniforms[:,None,:]<probabilities[None,:,:]).to(flat.dtype).reshape(s*n,p)
        repeated=flat.repeat(s,1);terminal_logits,_=self.discrete(repeated,mask);pt=terminal_logits.sigmoid()
        q=self.continuous_width+2;mean=flat.new_zeros(n,q);second=flat.new_zeros(n,q,q)
        for terminal in (0.,1.):
            dt=pt.new_full(pt.shape,terminal);_,gl=self.discrete(repeated,mask,dt);pg=gl.sigmoid()
            for goal_met in (0.,1.):
                gg=pt.new_full(pt.shape,goal_met);mu,lower=self.continuous(repeated,mask,dt,gg)
                roots=torch.cat((mu,gg[:,None],dt[:,None]),-1)
                covariance=roots.new_zeros(s*n,q,q);covariance[:,:self.continuous_width,:self.continuous_width]=lower@lower.transpose(-1,-2)
                w=(pt if terminal else 1-pt)*(pg if goal_met else 1-pg)/s
                mean+=(w[:,None]*roots).reshape(s,n,q).sum(0)
                second+=(w[:,None,None]*(covariance+roots[:,:,None]*roots[:,None,:])).reshape(s,n,q,q).sum(0)
        covariance=second-mean[:,:,None]*mean[:,None,:]
        return mean.reshape(*shape,q),covariance.reshape(*shape,q,q),probabilities.reshape(*shape,p)

    def kernel(self,observation,goal,actions,encoded,valid,h,hypothesis):
        state,attention,gates=self.state_kernel(observation,goal,actions,encoded,valid,h,hypothesis)
        roots,covariance,visible=self.forecast(state);o=self.schema.observation;n=self.continuous_width
        matrix,offset=self.layout.projection(observation,actions)
        fb=roots@matrix.T+offset;fbvar=torch.einsum('fq,...qr,fr->...f',matrix,covariance,matrix).clamp_min(0)
        diagonal=covariance.diagonal(dim1=-2,dim2=-1).clamp_min(0)
        return {'state':state,'next_mean':roots[...,:o],'next_variance':diagonal[...,:o],
                'feedback_mean':fb,'feedback_variance':fbvar,'innovation_mean':roots[...,o:n],
                'innovation_variance':diagonal[...,o:n],'visibility_probability':visible,
                'value_mean':roots[...,n],'value_variance':diagonal[...,n].clamp_min(1e-6),
                'root_mean':roots,'root_covariance':covariance,'attention':attention,'applicability':gates}

    def forward(self,observation,goal,actions,memory,code=None):
        root=self.root(observation,goal,memory);b=observation.shape[0];k=self.config.hypotheses;rep=lambda t:t.repeat_interleave(k,0)
        out=self.kernel(rep(observation),rep(goal),rep(actions),rep(root['encoded']),rep(root['valid']),root['h'].reshape(b*k,-1),torch.arange(k,device=observation.device).repeat(b))
        out={key:value.reshape(b,k,*value.shape[1:]) for key,value in out.items()}
        moments=joint_moments(root['weights'],out['value_mean'],out['value_variance']);state=torch.einsum('bk,bkad->bad',root['weights'],out['state'])
        if code is None:code=self.base_code[None,:].expand(b,-1)
        logits=self.actor_logits(state,moments,code)
        return {**out,'logits':logits,'policy':logits.softmax(-1),'context':root['context'].detach(),'weights':root['weights'],
                'action_state':state,'moments':moments,'feedback_prediction':torch.einsum('bk,bkaf->baf',root['weights'],out['feedback_mean']).detach(),
                'innovation_prediction':torch.einsum('bk,bkap->bap',root['weights'],out['innovation_mean']).detach(),
                'next_prediction':torch.einsum('bk,bkao->bao',root['weights'],out['next_mean']).detach(),
                '_root':root,'_observation':observation,'_goal':goal,'_actions':actions}

    def propose(self,output):return super().propose(dict(output,feedback_prediction=output['innovation_prediction']))

    def update_observed_belief(self,h,observation,action,next_observation,innovation,mask,goal,goal_met,terminal):
        observed=torch.where(mask.bool(),innovation,torch.zeros_like(innovation))
        return self.belief_update(torch.cat((observation,action,next_observation,observed,mask,goal,goal_met[:,None],terminal[:,None]),-1),h)

    @torch.no_grad()
    def sample_observed(self,state,mask_uniform,terminal_uniform,goal_uniform,noise):
        probability=self.visibility_head(state).sigmoid();mask=(mask_uniform<probability).to(state.dtype)
        tl,_=self.discrete(state,mask);terminal=(terminal_uniform<tl.sigmoid()).to(state.dtype)
        _,gl=self.discrete(state,mask,terminal);goal_met=(goal_uniform<gl.sigmoid()).to(state.dtype)
        mean,lower=self.continuous(state,mask,terminal,goal_met);y=mean+(lower@noise[...,None]).squeeze(-1)
        o=self.schema.observation;observed=torch.where(mask.bool(),y[:,o:],torch.zeros_like(y[:,o:]))
        variance=lower.square().sum(-1)
        return {'next_observation':y[:,:o],'innovation':observed,'mask':mask,'goal_met':goal_met,'terminal':terminal,
                'next_variance':variance[:,:o],'innovation_variance':variance[:,o:],
                'visibility_probability':probability,'terminal_probability':tl.sigmoid(),'goal_probability':gl.sigmoid()}

    def dream(self,output,codes,tape,force_continue=False,fixed_action=None):
        from .imagination import unfold
        return unfold(self,output,codes,tape,force_continue,fixed_action)
