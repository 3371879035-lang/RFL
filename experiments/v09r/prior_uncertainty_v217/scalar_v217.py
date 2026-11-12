"""Independent scalar algebra; only stdlib and old scalar F/H formulas."""
from pathlib import Path
import math
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'applicability_v214'))
from scalar import groups, prior, softmax, normalize, Predictor, Model


def logsum(values):
    m=max(values)
    return m+math.log(math.fsum(math.exp(v-m) for v in values))


class Gate:
    def __init__(self,shared=True,etas=(0.,.25,.5)):
        self.groups=groups(3,True);self.shared=shared;self.etas=tuple(etas);self.rates=(0.,.002,.02,.2)
        self.hs=[(r,e) for r in self.rates for e in self.etas]
        self.logs=prior(self.groups,3);self.sources={};self.evidence={}

    def predict(self,x,h,f):
        keys=[(g,tuple(x[j] for j in g)) for g in self.groups];n=len(self.hs)
        sources=[[[[(1-eta)*p[a][y]+eta/2 for y in range(2)] for a in range(2)] for p in [h,f]] for _,eta in self.hs]
        weights=[];parts=[];evidence=[];joint=[]
        for key in keys:
            w=[[(1-rate)*p+rate/2 for p in softmax(self.sources.get((key,k),[-math.log(2)]*2))] for k,(rate,_) in enumerate(self.hs)]
            parts.append([[[math.fsum(ww*s[a][y] for ww,s in zip(wws,ss)) for y in range(2)] for a in range(2)] for wws,ss in zip(w,sources)])
            weights.append(w)
        for i,g in enumerate(self.groups):
            vals=[self.evidence[k] for k in self.evidence if k[0]==g]
            if self.shared:
                evidence.append([math.fsum(v[k] for v in vals) for k in range(n)])
            else:
                evidence.append([self.logs[i]+math.fsum(logsum(v)-math.log(n) for v in vals)])
        if self.shared:
            flat=[self.logs[i]-math.log(n)+v for i,ev in enumerate(evidence) for v in ev]
            z=softmax(flat);joint=[z[i*n:(i+1)*n] for i in range(len(keys))];logz=logsum(flat)
        else:
            q=softmax([e[0] for e in evidence]);logz=logsum([e[0] for e in evidence])
            joint=[[qg*v for v in softmax(self.evidence.get(key,[0.]*n))] for qg,key in zip(q,keys)]
        p=[[math.fsum(j[k]*pp[k][a][y] for j,pp in zip(joint,parts) for k in range(n)) for y in range(2)] for a in range(2)]
        share=math.fsum(j[k]*w[k][0] for j,w in zip(joint,weights) for k in range(n))
        rates=[math.fsum(j[k] for j in joint for k in range(n) if k//len(self.etas)==r) for r in range(4)]
        etas=[math.fsum(j[k] for j in joint for k in range(n) if k%len(self.etas)==e) for e in range(len(self.etas))]
        within=[[math.fsum(j[k]*w[k][e]*sources[k][e][a][y]*(1-sources[k][e][a][y]) for j,w in zip(joint,weights) for k in range(n) for e in range(2)) for y in range(2)] for a in range(2)]
        between=[[math.fsum(j[k]*w[k][e]*(sources[k][e][a][y]-p[a][y])**2 for j,w in zip(joint,weights) for k in range(n) for e in range(2)) for y in range(2)] for a in range(2)]
        cache={'keys':keys,'weights':weights,'sources':sources,'parts':parts,'rates':rates,'etas':etas,
               'within':within,'between':between,'log_evidence':logz}
        return p,share,cache

    def observe(self,cache,a,y):
        for key,ws,parts in zip(cache['keys'],cache['weights'],cache['parts']):
            for k,(w,ss) in enumerate(zip(ws,cache['sources'])):
                self.sources[key,k]=normalize([math.log(v)+math.log(s[a][y]) for v,s in zip(w,ss)])
            old=self.evidence.get(key,[0.]*len(self.hs))
            self.evidence[key]=[v+math.log(p[a][y]) for v,p in zip(old,parts)]


def make_model(arm,h,t):
    model=Model('conditional_gate',h,t)
    model.gate=Gate(arm.startswith('shared'),(0.,) if arm=='shared_raw_v217' else (0.,.25,.5))
    return model
