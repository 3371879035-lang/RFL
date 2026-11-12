"""Independent stdlib implementation of V6 equations, not an environment/torch import."""
from itertools import combinations
import copy
import math


def softmax(logs):
    m=max(logs); values=[math.exp(v-m) for v in logs]; total=math.fsum(values)
    return [v/total for v in values]


def normalize(logs):
    m=max(logs); z=m+math.log(math.fsum(math.exp(v-m) for v in logs))
    return [v-z for v in logs]


def groups(d, empty=False):
    return [s for k in range(0 if empty else 1,d+1) for s in combinations(range(d),k)]


def prior(structures,d):
    return normalize([-len(s)*math.log(2)-math.log(math.comb(d,len(s))) for s in structures])


class Head:
    def __init__(self,structure,hazard):
        self.structure=structure; self.hazard=hazard; self.n=0
        self.counts=[{}]; self.logs=[0.]

    def before(self):
        if self.n and self.n%32==0 and self.hazard:
            return self.counts+[{}],[x+math.log1p(-self.hazard) for x in self.logs]+[math.log(self.hazard)]
        return self.counts,self.logs

    def predict(self,x):
        counts,logs=self.before(); weights=softmax(logs); cell=tuple(x[j] for j in self.structure)
        parts=[]
        for count in counts:
            p=[]
            for a in range(2):
                row=[count.get((cell,a,y),0)+1 for y in range(2)]; total=sum(row)
                p.append([v/total for v in row])
            parts.append(p)
        mixed=[[math.fsum(w*p[a][y] for w,p in zip(weights,parts)) for y in range(2)] for a in range(2)]
        return mixed,parts

    def observe(self,x,a,y):
        _,parts=self.predict(x); counts,logs=self.before()
        self.logs=normalize([l+math.log(p[a][y]) for l,p in zip(logs,parts)])
        cell=tuple(x[j] for j in self.structure)
        self.counts=counts
        for c in self.counts: c[(cell,a,y)]=c.get((cell,a,y),0)+1
        self.n+=1


class Predictor:
    def __init__(self,hazard=.05):
        self.structures=groups(3); self.logs=prior(self.structures,3)
        self.heads=[Head(s,hazard) for s in self.structures]; self.n=0

    def predict(self,x):
        parts=[h.predict(x)[0] for h in self.heads]; w=softmax(self.logs)
        p=[[math.fsum(v*h[a][y] for v,h in zip(w,parts)) for y in range(2)] for a in range(2)]
        return p,parts

    def observe(self,x,a,y,parts=None):
        if parts is None: _,parts=self.predict(x)
        self.logs=normalize([l+math.log(p[a][y]) for l,p in zip(self.logs,parts)])
        for h in self.heads:h.observe(x,a,y)
        self.n+=1


class Gate:
    def __init__(self,conditional):
        self.structures=groups(3,True) if conditional else [()]
        self.logs=prior(self.structures,3); self.local={}

    def predict(self,x,h,f):
        keys=[(s,tuple(x[j] for j in s)) for s in self.structures]
        w=[[.98*v+.01 for v in softmax(self.local.get(k,[-math.log(2)]*2))] for k in keys]
        q=softmax(self.logs)
        parts=[[[wh*h[a][y]+wf*f[a][y] for y in range(2)] for a in range(2)] for wh,wf in w]
        lam=math.fsum(qi*wi[0] for qi,wi in zip(q,w))
        p=[[math.fsum(qi*pi[a][y] for qi,pi in zip(q,parts)) for y in range(2)] for a in range(2)]
        return p,lam,(keys,w,parts,h,f)

    def observe(self,cache,a,y):
        keys,w,parts,h,f=cache
        for key,source in zip(keys,w):
            self.local[key]=normalize([math.log(source[0])+math.log(h[a][y]),math.log(source[1])+math.log(f[a][y])])
        self.logs=normalize([l+math.log(p[a][y]) for l,p in zip(self.logs,parts)])


class Model:
    def __init__(self,mode,historical,temporal):
        self.mode=mode
        self.current=copy.deepcopy(historical if mode=='pooled_history' else temporal) if mode in ['pooled_history','temporal_v210'] else Predictor()
        self.historical=copy.deepcopy(historical) if mode.endswith('gate') else None
        self.gate=Gate(mode=='conditional_gate') if self.historical is not None else None

    def predict(self,x):
        f,parts=self.current.predict(x)
        if self.gate is None:return f,None,None,f,(parts,None)
        h=self.historical.predict(x)[0]; p,lam,gcache=self.gate.predict(x,h,f)
        return p,lam,h,f,(parts,gcache)

    def observe(self,x,a,y,cache):
        parts,gcache=cache
        if self.gate is not None:self.gate.observe(gcache,a,y)
        self.current.observe(x,a,y,parts)
