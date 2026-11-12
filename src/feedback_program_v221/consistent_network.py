"""Preferred V221 comparison head: one value potential and one PSD joint covariance."""
import torch
from torch import nn
from torch.nn import functional as F
from .network import EvidenceMemoryNet,NetworkConfig,mlp
from .memory import Schema


def consistent_comparison(potential,factors,residual):
    covariance=factors@factors.transpose(-1,-2)+torch.diag_embed(residual)
    means=potential[:,:,None]-potential[:,None,:]
    delta=factors[:,:,None,:]-factors[:,None,:,:]
    variance=delta.square().sum(-1)+residual[:,:,None]+residual[:,None,:]
    off_diagonal=~torch.eye(potential.shape[1],dtype=torch.bool,device=potential.device)
    return means,variance*off_diagonal,covariance


class ConsistentEvidenceMemoryNet(EvidenceMemoryNet):
    def __init__(self,schema=Schema(),config=NetworkConfig(),comparison_rank=8):
        super().__init__(schema,config);d=config.width;self.comparison_rank=comparison_rank
        self.contrast_mean=mlp(d,2*d,1);self.contrast_mean[-1]=nn.Linear(2*d,1,bias=False)
        self.contrast_scale=mlp(d,2*d,1)
        self.comparison_factor=mlp(d,2*d,comparison_rank)
        self.comparison_factor[-1]=nn.Linear(2*d,comparison_rank,bias=False)

    def practice_state(self,output,codes,evidence):
        p=self.null_memory;b,arms,d=codes.shape
        features=evidence['features'].to(p);sources=evidence['sources'].to(p.device);valid=evidence['valid'].to(p.device)
        count=valid.sum(-1).to(p.dtype)
        encoded=(self.event_encoder(features)+self.source_embedding(sources)).reshape(b*arms,features.shape[2],d)
        valid=valid.reshape(b*arms,-1)
        encoded=torch.cat((self.evidence_null.expand(b*arms,1,d),encoded),1)
        valid=torch.cat((torch.ones(b*arms,1,dtype=torch.bool,device=p.device),valid),1)
        context=output['context'][:,None,:].expand(-1,arms,-1)
        queries=self.evidence_query(torch.cat((context,codes),-1)).reshape(b*arms,1,d)
        read,_,gates=self.evidence_reader(queries,encoded,valid)
        states=self.evidence_fusion(torch.cat((context,codes,read.reshape(b,arms,d),count.log1p()[:,:,None]),-1))
        potential=self.contrast_mean(states).squeeze(-1)
        residual=F.softplus(self.contrast_scale(states).squeeze(-1))+1e-4
        factors=self.comparison_factor(states)
        means,variance,covariance=consistent_comparison(potential,factors,residual)
        return {'states':states,'counts':count,'contrast_mean':means,'contrast_variance':variance,
                'comparison_covariance':covariance,'comparison_potential':potential,'comparison_residual':residual,
                'applicability':gates.reshape(b,arms,-1)}
