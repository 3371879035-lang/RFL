"""Independent scalar V8 probability algebra; no torch or learner imports."""
from pathlib import Path
import math
import sys

OLD=Path(__file__).resolve().parents[1]/'applicability_v214'
sys.path.insert(0,str(OLD))
from scalar import groups,prior,softmax,normalize,Predictor,Model


class Gate:
    def __init__(self,rates=(0.,.002,.02,.2),conditional=True):
        self.rates=tuple(rates);self.groups=groups(3,True) if conditional else [()]
        self.logs=prior(self.groups,3);self.sources={};self.rate_logs={}

    def predict(self,x,h,f):
        keys=[(g,tuple(x[j] for j in g)) for g in self.groups];q=softmax(self.logs)
        all_w=[];all_rho=[];per_rate=[];per_group=[]
        for key in keys:
            old=self.sources.get(key,[[-math.log(2)]*2 for _ in self.rates])
            w=[[(1-rate)*v+rate/2 for v in softmax(logs)] for rate,logs in zip(self.rates,old)]
            rho=softmax(self.rate_logs.get(key,[-math.log(len(self.rates))]*len(self.rates)))
            pr=[[[wh*h[a][y]+wf*f[a][y] for y in range(2)] for a in range(2)] for wh,wf in w]
            pg=[[math.fsum(z*pp[a][y] for z,pp in zip(rho,pr)) for y in range(2)] for a in range(2)]
            all_w.append(w);all_rho.append(rho);per_rate.append(pr);per_group.append(pg)
        p=[[math.fsum(z*pg[a][y] for z,pg in zip(q,per_group)) for y in range(2)] for a in range(2)]
        share=math.fsum(qg*math.fsum(z*w[0] for z,w in zip(rho,ws)) for qg,rho,ws in zip(q,all_rho,all_w))
        rates=[math.fsum(qg*rho[r] for qg,rho in zip(q,all_rho)) for r in range(len(self.rates))]
        cache=(keys,all_w,all_rho,per_rate,per_group,h,f,rates)
        return p,share,cache

    def observe(self,cache,a,y):
        keys,ws,rhos,prs,pgs,h,f,_=cache
        for key,w,rho,pr in zip(keys,ws,rhos,prs):
            self.sources[key]=[normalize([math.log(v[0])+math.log(h[a][y]),math.log(v[1])+math.log(f[a][y])]) for v in w]
            self.rate_logs[key]=normalize([math.log(z)+math.log(p[a][y]) for z,p in zip(rho,pr)])
        self.logs=normalize([v+math.log(p[a][y]) for v,p in zip(self.logs,pgs)])


def make_model(arm,h,t):
    model=Model('conditional_gate',h,t)
    if arm!='fixed_v215':model.gate=Gate((0.,) if arm=='no_reopening_v216' else (0.,.002,.02,.2))
    return model
