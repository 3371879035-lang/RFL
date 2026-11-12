"""Learnable inducing memory and multi-trial, symmetric practice decisions."""
from dataclasses import dataclass
import torch
from torch import nn
from torch.nn import functional as F
from feedback_program_v220.memory import Schema
from feedback_program_v220.network import LearnableFeedbackNet,NetworkConfig as BaseConfig,ConditionalRead,mlp


@dataclass(frozen=True)
class NetworkConfig(BaseConfig):
    width: int = 256
    attention_heads: int = 8
    memory_layers: int = 2
    memory_slots: int = 64


class CrossBlock(nn.Module):
    def __init__(self,width,heads):
        super().__init__();self.qnorm=nn.LayerNorm(width);self.knorm=nn.LayerNorm(width)
        self.attention=nn.MultiheadAttention(width,heads,dropout=0.,batch_first=True)
        self.norm=nn.LayerNorm(width);self.ff=mlp(width,4*width,width)
    def forward(self,q,kv,valid):
        k=self.knorm(kv);q=q+self.attention(self.qnorm(q),k,k,key_padding_mask=~valid,need_weights=False)[0]
        return q+self.ff(self.norm(q))


class InducedMemoryBlock(nn.Module):
    def __init__(self,width,heads):
        super().__init__();self.read=CrossBlock(width,heads);self.work=CrossBlock(width,heads);self.write=CrossBlock(width,heads)
    def forward(self,raw,slots,valid):
        slots=self.read(slots,raw,valid)
        slot_valid=torch.ones(slots.shape[:2],device=slots.device,dtype=torch.bool)
        slots=self.work(slots,slots,slot_valid)
        raw=self.write(raw,slots,slot_valid)*valid[:,:,None]
        return raw,slots


class EvidenceMemoryNet(LearnableFeedbackNet):
    def __init__(self,schema=Schema(),config=NetworkConfig()):
        super().__init__(schema,config);d=config.width
        self.memory_blocks=nn.ModuleList([InducedMemoryBlock(d,config.attention_heads) for _ in range(config.memory_layers)])
        self.work_nodes=nn.Parameter(torch.randn(1,config.memory_slots,d)/d**.5)
        self.evidence_null=nn.Parameter(torch.zeros(1,1,d))
        self.evidence_query=mlp(2*d,d,d);self.evidence_reader=ConditionalRead(d)
        self.evidence_fusion=mlp(3*d+1,2*d,d)
        self.contrast_mean=mlp(2*d,2*d,1)
        self.contrast_mean[-1]=nn.Linear(2*d,1,bias=False)  # A shared intercept would cancel in the antisymmetric mean.
        self.contrast_scale=mlp(2*d,2*d,1)
        self.trial_score=mlp(2*d+4,2*d,1)
        self.trial_keep=mlp(2*d+2,d,1)
        self.adoption_score=mlp(2*d+2,2*d,1)
        self.adoption_score[-1]=nn.Linear(2*d,1,bias=False)
        # Every arm, including the current behavior, uses the same learned scoring rule.
        del self.adoption_keep

    def encode_memory(self,memory):
        p=self.null_memory;features=memory['features'].to(p);sources=memory['sources'].to(p.device)
        parents=memory['parents'].to(p.device);valid=memory['valid'].to(p.device)
        b,n=sources.shape;null=self.null_memory.expand(b,1,-1)
        raw=self.event_encoder(features)+self.source_embedding(sources)
        previous=torch.cat((null,raw),1).gather(1,(parents+1)[:,:,None].expand(-1,-1,self.config.width))
        raw=self.parent_merge(torch.cat((raw,previous),-1))
        raw=torch.cat((null,raw),1);valid=torch.cat((torch.ones(b,1,dtype=torch.bool,device=p.device),valid),1)
        slots=self.work_nodes.expand(b,-1,-1)
        for block in self.memory_blocks:raw,slots=block(raw,slots,valid)
        return raw,valid

    def practice_state(self,output,codes,evidence):
        p=self.null_memory;b,arms,d=codes.shape
        f=evidence['features'].to(p);sources=evidence['sources'].to(p.device);valid=evidence['valid'].to(p.device)
        count=valid.sum(-1).to(p.dtype)
        encoded=self.event_encoder(f)+self.source_embedding(sources)
        encoded=encoded.reshape(b*arms,f.shape[2],d);valid=valid.reshape(b*arms,-1)
        encoded=torch.cat((self.evidence_null.expand(b*arms,1,d),encoded),1)
        valid=torch.cat((torch.ones(b*arms,1,dtype=torch.bool,device=p.device),valid),1)
        context=output['context'][:,None,:].expand(-1,arms,-1)
        queries=self.evidence_query(torch.cat((context,codes),-1)).reshape(b*arms,1,d)
        read,_,gates=self.evidence_reader(queries,encoded,valid)
        states=self.evidence_fusion(torch.cat((context,codes,read.reshape(b,arms,d),count.log1p()[:,:,None]),-1))
        left=states[:,:,None,:].expand(-1,-1,arms,-1);right=states[:,None,:,:].expand(-1,arms,-1,-1)
        joined=torch.cat((left,right),-1)
        raw_mean=self.contrast_mean(joined).squeeze(-1);raw_scale=self.contrast_scale(joined).squeeze(-1)
        mean=(raw_mean-raw_mean.transpose(-1,-2))/2
        variance=F.softplus((raw_scale+raw_scale.transpose(-1,-2))/2)+1e-4
        return {'states':states,'counts':count,'contrast_mean':mean,'contrast_variance':variance,
                'applicability':gates.reshape(b,arms,-1)}

    def trial_logits(self,output,codes,evidence,budget):
        state=self.practice_state(output,codes,evidence);h=state['states'];n=h.shape[1]
        context=output['context'][:,None,:].expand(-1,n,-1)
        comparison=torch.stack((state['contrast_mean'][:,:,0],state['contrast_variance'][:,:,0]),-1)
        scores=self.trial_score(torch.cat((h,context,comparison,budget[:,None,:].expand(-1,n,-1)),-1)).squeeze(-1)
        stop=self.trial_keep(torch.cat((output['context'],h.mean(1),budget),-1))
        return torch.cat((stop,scores),-1),state

    def adoption_logits(self,output,codes,evidence):
        state=self.practice_state(output,codes,evidence);h=state['states'];n=h.shape[1]
        context=output['context'][:,None,:].expand(-1,n,-1)
        comparison=torch.stack((state['contrast_mean'][:,:,0],state['contrast_variance'][:,:,0]),-1)
        scores=self.adoption_score(torch.cat((h,context,comparison),-1)).squeeze(-1)
        eligible=state['counts']>0;eligible[:,0]=True
        return scores.masked_fill(~eligible,-torch.inf),state

    def attention_pair_budget(self,real_nodes,actions):
        n=real_nodes+1;s=self.config.memory_slots
        return self.config.memory_layers*(2*n*s+s*s)+(actions+1)*n
