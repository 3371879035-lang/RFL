"""Shared factual/imagined recurrent kernel with disjoint world and decision gradients."""
import torch
from torch import nn
from torch.nn import functional as F
from feedback_program_v220.network import joint_moments,mlp
from feedback_program_v221.network import NetworkConfig
from feedback_program_v221.memory import Schema
from feedback_program_v221.consistent_network import ConsistentEvidenceMemoryNet,consistent_comparison


class RecurrentFeedbackNet(ConsistentEvidenceMemoryNet):
    WORLD_GROUPS={'null_memory','hypothesis_embeddings','work_nodes','event_encoder','source_embedding','parent_merge','memory_blocks',
                  'query_encoder','action_encoder','reader','context_fusion','action_fusion','mixture_head','world_decoder',
                  'belief_init','belief_adapter','belief_update','terminal_head'}

    def __init__(self,schema=Schema(),config=NetworkConfig(),comparison_rank=8):
        super().__init__(schema,config,comparison_rank);d=config.width
        self.belief_init=mlp(d,d,d);self.belief_adapter=mlp(d,d,d)
        self.belief_update=nn.GRUCell(2*schema.observation+schema.action+2*schema.feedback+schema.goal,d)
        self.terminal_head=mlp(d,d,1)
        self.evidence_adapter=mlp(d,d,d)
        self.thought_init=mlp(2*d,d,d)
        self.thought_update=nn.GRUCell(2*schema.observation+schema.action+schema.feedback*2+schema.observation+2,d)
        self.thought_continue=mlp(2*d+1,d,1)
        self.thought_trial=mlp(2*d+2,d,1);self.thought_stop=mlp(2*d+2,d,1)

    def parameter_groups(self):
        world={n:p for n,p in self.named_parameters() if n.split('.')[0] in self.WORLD_GROUPS}
        policy={n:p for n,p in self.named_parameters() if n.split('.')[0] not in self.WORLD_GROUPS}
        return world,policy

    def root(self,observation,goal,memory):
        encoded,valid=self.encode_memory(memory);query=self.query_encoder(torch.cat((observation,goal),-1))
        read,_,_=self.reader(query[:,None,:],encoded,valid);context=self.context_fusion(torch.cat((query,read[:,0]),-1))
        weights=torch.softmax(self.mixture_head(context),-1)
        h=self.belief_init(context[:,None,:]+self.hypothesis_embeddings[None,:,:])
        return {'encoded':encoded,'valid':valid,'context':context,'weights':weights,'h':h}

    def kernel(self,observation,goal,actions,encoded,valid,h,hypothesis):
        query=self.query_encoder(torch.cat((observation,goal),-1))
        read,_,_=self.reader(query[:,None,:],encoded,valid)
        context=self.context_fusion(torch.cat((query,read[:,0]),-1))+self.belief_adapter(h)
        aq=query[:,None,:]+self.action_encoder(actions);ar,attention,applicability=self.reader(aq,encoded,valid)
        state=self.action_fusion(torch.cat((aq,ar,context[:,None,:].expand_as(ar)),-1))
        decoded=self.world_decoder(state+self.hypothesis_embeddings[hypothesis][:,None,:])
        o,f=self.schema.observation,self.schema.feedback
        nm,nv,fm,fv,vm,vv=torch.split(decoded,[o,o,f,f,1,1],-1)
        return {'state':state,'next_mean':nm,'next_variance':F.softplus(nv)+1e-4,'feedback_mean':fm,'feedback_variance':F.softplus(fv)+1e-4,
                'value_mean':vm.squeeze(-1),'value_variance':F.softplus(vv.squeeze(-1))+1e-4,
                'terminal_logits':self.terminal_head(state).squeeze(-1),'attention':attention,'applicability':applicability}

    def update_belief(self,h,observation,action,next_observation,feedback,mask,goal):
        return self.belief_update(torch.cat((observation,action,next_observation,feedback*mask,mask,goal),-1),h)

    def actor_logits(self,state,moments,code):
        features=torch.stack((moments['mean'],moments['model_covariance'].diagonal(dim1=-2,dim2=-1),moments['within_variance'],
                              moments['comparison_probability'].mean(-1)),-1)
        return self.actor(torch.cat((state.detach(),code[:,None,:].expand_as(state),features.detach()),-1)).squeeze(-1)

    def forward(self,observation,goal,actions,memory,code=None):
        root=self.root(observation,goal,memory);b=observation.shape[0];k=self.config.hypotheses
        repeat=lambda t:t.repeat_interleave(k,0)
        out=self.kernel(repeat(observation),repeat(goal),repeat(actions),repeat(root['encoded']),repeat(root['valid']),
                        root['h'].reshape(b*k,-1),torch.arange(k,device=observation.device).repeat(b))
        out={key:value.reshape(b,k,*value.shape[1:]) for key,value in out.items()}
        moments=joint_moments(root['weights'],out['value_mean'],out['value_variance'])
        state=torch.einsum('bk,bkad->bad',root['weights'],out['state'])
        if code is None:code=self.base_code[None,:].expand(b,-1)
        logits=self.actor_logits(state,moments,code)
        return {**out,'logits':logits,'policy':torch.softmax(logits,-1),'context':root['context'].detach(),'weights':root['weights'],
                'action_state':state,'moments':moments,'feedback_prediction':torch.einsum('bk,bkaf->baf',root['weights'],out['feedback_mean']).detach(),
                'next_prediction':torch.einsum('bk,bkao->bao',root['weights'],out['next_mean']).detach(),'_root':root,
                '_observation':observation,'_goal':goal,'_actions':actions}

    def propose(self,output):
        detached=dict(output,context=output['context'].detach(),feedback_prediction=output['feedback_prediction'].detach(),
                      moments={key:value.detach() for key,value in output['moments'].items()})
        return super().propose(detached)

    def practice_state(self,output,codes,evidence):
        p=self.null_memory;b,arms,d=codes.shape
        f=evidence['features'].to(p);sources=evidence['sources'].to(p.device);valid=evidence['valid'].to(p.device)
        count=valid.sum(-1).to(p.dtype)
        raw=(self.event_encoder(f)+self.source_embedding(sources)).detach()
        encoded=self.evidence_adapter(raw).reshape(b*arms,f.shape[2],d);valid=valid.reshape(b*arms,-1)
        encoded=torch.cat((self.evidence_null.expand(b*arms,1,d),encoded),1)
        valid=torch.cat((torch.ones(b*arms,1,dtype=torch.bool,device=p.device),valid),1)
        context=output['context'].detach()[:,None,:].expand(-1,arms,-1)
        query=self.evidence_query(torch.cat((context,codes),-1)).reshape(b*arms,1,d)
        read,_,gates=self.evidence_reader(query,encoded,valid)
        states=self.evidence_fusion(torch.cat((context,codes,read.reshape(b,arms,d),count.log1p()[:,:,None]),-1))
        potential=self.contrast_mean(states).squeeze(-1);residual=F.softplus(self.contrast_scale(states).squeeze(-1))+1e-4
        mean,variance,covariance=consistent_comparison(potential,self.comparison_factor(states),residual)
        return {'states':states,'counts':count,'contrast_mean':mean,'contrast_variance':variance,'comparison_covariance':covariance,
                'applicability':gates.reshape(b,arms,-1)}

    def trial_logits_with_thought(self,output,codes,evidence,budget,thought):
        logits,state=super().trial_logits(output,codes,evidence,budget)
        summary=thought['summary'];context=output['context'].detach();n=codes.shape[1]
        meta=torch.stack((thought['depths'].to(summary.dtype),thought['active_counts'].to(summary.dtype)),dim=-1)[None,:,:]
        arm=self.thought_trial(torch.cat((context[:,None,:].expand(-1,n,-1),summary,meta),-1)).squeeze(-1)
        stop=self.thought_stop(torch.cat((context,summary.mean(1),budget),-1))
        return logits+torch.cat((stop,arm),-1),state

    def dream(self,output,codes,tape,force_continue=False,fixed_action=None):
        from .imagination import unfold
        return unfold(self,output,codes,tape,force_continue,fixed_action)
