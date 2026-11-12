"""Trainable memory-conditioned predictor and actor; no environment imports.

Shared mixture components preserve cross-action model covariance. A candidate
changes the actor, never the predicted physical consequence of a fixed action.
"""
from dataclasses import dataclass
import math
import torch
from torch import nn
from torch.nn import functional as F
from .memory import Schema


@dataclass(frozen=True)
class NetworkConfig:
    width: int = 192
    attention_heads: int = 6
    memory_layers: int = 2
    hypotheses: int = 8
    candidates: int = 3


def mlp(inp,hidden,out):
    return nn.Sequential(nn.Linear(inp,hidden),nn.GELU(),nn.Linear(hidden,out))


def joint_moments(weights,means,variances):
    """[B,K], [B,K,A]; same latent K for every action, not independent K draws."""
    mean=torch.einsum('bk,bka->ba',weights,means)
    centered=means-mean[:,None,:]
    epistemic=torch.einsum('bk,bka,bkc->bac',weights,centered,centered)
    within=torch.einsum('bk,bka->ba',weights,variances)
    total=epistemic+torch.diag_embed(within)
    diag=total.diagonal(dim1=-2,dim2=-1)
    difference_variance=(diag[:,:,None]+diag[:,None,:]-2*total).clamp_min(0)
    gap=means[:,:,:,None]-means[:,:,None,:]
    sd=(variances[:,:,:,None]+variances[:,:,None,:]).sqrt()
    wins=torch.einsum('bk,bkac->bac',weights,.5*(1+torch.erf(gap/(sd*math.sqrt(2)))))
    return {'mean':mean,'model_covariance':epistemic,'within_variance':within,'total_covariance':total,
            'difference_variance':difference_variance,'comparison_probability':wins}


class MemoryBlock(nn.Module):
    def __init__(self,width,heads):
        super().__init__();self.norm1=nn.LayerNorm(width);self.norm2=nn.LayerNorm(width)
        self.attention=nn.MultiheadAttention(width,heads,dropout=0.,batch_first=True)
        self.ff=mlp(width,4*width,width)
    def forward(self,x,valid):
        y=self.norm1(x);x=x+self.attention(y,y,y,key_padding_mask=~valid,need_weights=False)[0]
        return (x+self.ff(self.norm2(x)))*valid[:,:,None]


class ConditionalRead(nn.Module):
    def __init__(self,width):
        super().__init__();self.width=width
        self.query=nn.Linear(width,width);self.key=nn.Linear(width,width,bias=False);self.value=nn.Linear(width,width)
        self.applicability=mlp(4*width,width,1)
    def forward(self,query,memory,valid):
        q=query[:,:,None,:].expand(-1,-1,memory.shape[1],-1)
        m=memory[:,None,:,:].expand(-1,query.shape[1],-1,-1)
        gates=torch.sigmoid(self.applicability(torch.cat((q,m,q*m,q-m),-1))).squeeze(-1)
        scores=self.query(query)@self.key(memory).transpose(-1,-2)/math.sqrt(self.width)
        weights=torch.softmax(scores.masked_fill(~valid[:,None,:],-torch.inf),-1)
        read=(weights*gates)@self.value(memory)
        return read,weights,gates


class LearnableFeedbackNet(nn.Module):
    def __init__(self,schema=Schema(),config=NetworkConfig()):
        super().__init__();self.schema=schema;self.config=config;d=config.width
        self.event_encoder=nn.Sequential(nn.Linear(schema.event_features,d),nn.GELU(),nn.Linear(d,2*d),nn.GELU(),nn.Linear(2*d,d))
        self.source_embedding=nn.Embedding(3,d)
        self.null_memory=nn.Parameter(torch.zeros(1,1,d))
        self.parent_merge=mlp(2*d,2*d,d)
        self.memory_blocks=nn.ModuleList([MemoryBlock(d,config.attention_heads) for _ in range(config.memory_layers)])
        self.query_encoder=mlp(schema.observation+schema.goal,d,d)
        self.action_encoder=mlp(schema.action,d,d)
        self.reader=ConditionalRead(d)
        self.context_fusion=mlp(2*d,2*d,d)
        self.action_fusion=mlp(3*d,2*d,d)
        self.hypothesis_embeddings=nn.Parameter(torch.randn(config.hypotheses,d)/math.sqrt(d))
        self.mixture_head=mlp(d,d,config.hypotheses)
        self.world_decoder=mlp(d,2*d,2*schema.observation+2*schema.feedback+2)
        self.base_code=nn.Parameter(torch.zeros(d))
        self.actor=mlp(2*d+4,2*d,1)
        self.actor[-1]=nn.Linear(2*d,1,bias=False)  # Shared scalar bias cancels under action softmax.
        self.proposal_keys=nn.Parameter(torch.randn(config.candidates,d)/math.sqrt(d))
        self.proposal_net=mlp(2*d+schema.feedback+1,2*d,d)
        self.trial_score=mlp(2*d+2,d,1);self.trial_keep=mlp(d+2,d,1)
        self.adoption_score=mlp(2*d+2*schema.feedback+3,d,1);self.adoption_keep=mlp(d,d,1)

    def encode_memory(self,memory):
        dtype=self.null_memory.dtype;device=self.null_memory.device
        feat=memory['features'].to(device=device,dtype=dtype);src=memory['sources'].to(device);parent=memory['parents'].to(device);valid=memory['valid'].to(device)
        b,n=src.shape;null=self.null_memory.expand(b,1,-1)
        x=self.event_encoder(feat)+self.source_embedding(src)
        pool=torch.cat((null,x),1)
        prev=pool.gather(1,(parent+1)[:,:,None].expand(-1,-1,self.config.width))
        x=self.parent_merge(torch.cat((x,prev),-1))
        x=torch.cat((null,x),1);valid=torch.cat((torch.ones(b,1,dtype=torch.bool,device=device),valid),1)
        for block in self.memory_blocks:x=block(x,valid)
        return x,valid

    def forward(self,observation,goal,actions,memory,code=None):
        encoded,valid=self.encode_memory(memory)
        query=self.query_encoder(torch.cat((observation,goal),-1))
        global_read,_,_=self.reader(query[:,None,:],encoded,valid)
        context=self.context_fusion(torch.cat((query,global_read[:,0]),-1))
        queries=query[:,None,:]+self.action_encoder(actions)
        read,attention,applicability=self.reader(queries,encoded,valid)
        state=self.action_fusion(torch.cat((queries,read,context[:,None,:].expand_as(read)),-1))
        decoded=self.world_decoder(state[:,:,None,:]+self.hypothesis_embeddings[None,None,:,:]).transpose(1,2)
        o,f=self.schema.observation,self.schema.feedback
        nm,nv,fm,fv,vm,vv=torch.split(decoded,[o,o,f,f,1,1],-1)
        weights=torch.softmax(self.mixture_head(context),-1)
        moments=joint_moments(weights,vm.squeeze(-1),F.softplus(vv.squeeze(-1))+1e-4)
        if code is None:code=self.base_code[None,:].expand(observation.shape[0],-1)
        features=torch.stack((moments['mean'],moments['model_covariance'].diagonal(dim1=-2,dim2=-1),
                              moments['within_variance'],moments['comparison_probability'].mean(-1)),-1)
        logits=self.actor(torch.cat((state,code[:,None,:].expand_as(state),features),-1)).squeeze(-1)
        return {'logits':logits,'policy':torch.softmax(logits,-1),'context':context,'action_state':state,
                'weights':weights,'next_mean':nm,'next_variance':F.softplus(nv)+1e-4,
                'feedback_mean':fm,'feedback_variance':F.softplus(fv)+1e-4,
                'value_mean':vm.squeeze(-1),'value_variance':F.softplus(vv.squeeze(-1))+1e-4,
                'feedback_prediction':torch.einsum('bk,bkaf->baf',weights,fm),
                'next_prediction':torch.einsum('bk,bkao->bao',weights,nm),
                'attention':attention,'applicability':applicability,'moments':moments}

    def propose(self,output):
        context=output['context'];b=context.shape[0];c=self.config.candidates
        extras=torch.cat((output['feedback_prediction'].mean(1),output['moments']['within_variance'].mean(-1,keepdim=True)),-1)
        return torch.tanh(self.proposal_net(torch.cat((context[:,None,:].expand(-1,c,-1),self.proposal_keys[None,:,:].expand(b,-1,-1),
                                                       extras[:,None,:].expand(-1,c,-1)),-1)))

    def trial_logits(self,output,codes,budget):
        c=codes.shape[1];context=output['context']
        keep=self.trial_keep(torch.cat((context,budget),-1))
        scores=self.trial_score(torch.cat((context[:,None,:].expand(-1,c,-1),codes,budget[:,None,:].expand(-1,c,-1)),-1)).squeeze(-1)
        return torch.cat((keep,scores),-1)

    def adoption_logits(self,output,codes,trial_summaries,eligible):
        context=output['context'];c=codes.shape[1]
        scores=self.adoption_score(torch.cat((context[:,None,:].expand(-1,c,-1),codes,trial_summaries),-1)).squeeze(-1)
        return torch.cat((self.adoption_keep(context),scores.masked_fill(~eligible,-torch.inf)),-1)
