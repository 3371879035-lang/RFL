"""Independent scalar calibration arithmetic; no torch or native learner import."""
from pathlib import Path
import math,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'evidence_persistence_v216'))
from scalar_v216 import Predictor,make_model as base_model,groups,prior,softmax


def logsum(values):
    m=max(values);return m+math.log(math.fsum(math.exp(v-m) for v in values))


class Calibrator:
    def __init__(self,conditional=True,full=True):
        self.full=full;self.groups=groups(4,True) if conditional else [()]
        self.group_prior=prior(self.groups,4)
        self.pi=[.5,.125,.125,.125,.125] if full else [.5,.25,.25]
        self.logs={};self.updates=0

    def predict(self,x,base):
        k=len(self.pi);glog=[]
        for i,g in enumerate(self.groups):
            zz=[logsum([math.log(p)+v for p,v in zip(self.pi,vs)]) for key,vs in self.logs.items() if key[0]==g]
            glog.append(self.group_prior[i]+math.fsum(zz))
        q=softmax(glog);ps=[];keys=[];maps=[];weights=[];coefs=[];within=[];between=[]
        for a in range(2):
            z=(*x,a);kk=[(g,tuple(z[j] for j in g)) for g in self.groups]
            ww=[softmax([math.log(p)+v for p,v in zip(self.pi,self.logs.get(key,[0.]*k))]) for key in kk]
            mass=[math.fsum(gg*w[i] for gg,w in zip(q,ww)) for i in range(k)]
            p=base[a][1];u=p*(1-p);v=u*(2*p-1)
            shifts=[0.,v,-v,u,-u] if self.full else [0.,v,-v]
            mm=[[base[a][0]-d,base[a][1]+d] for d in shifts]
            alpha=mass[1]-mass[2];beta=mass[3]-mass[4] if self.full else 0.;d=alpha*v+beta*u
            pred=[base[a][0]-d,base[a][1]+d]
            ps.append(pred);keys.append(kk);maps.append(mm);weights.append(mass);coefs.append([alpha,beta])
            within.append(math.fsum(w*m[1]*(1-m[1]) for w,m in zip(mass,mm)))
            between.append(math.fsum(w*(m[1]-pred[1])**2 for w,m in zip(mass,mm)))
        return ps,{'keys':keys,'maps':maps,'base':base,'weights':weights,'coefficients':coefs,
                   'within':within,'between':between,'log_evidence_ratio':logsum(glog)}

    def observe(self,cache,a,y):
        delta=[math.log(m[y])-math.log(cache['base'][a][y]) for m in cache['maps'][a]]
        for key in cache['keys'][a]:
            self.logs[key]=[v+d for v,d in zip(self.logs.get(key,[0.]*len(self.pi)),delta)]
        self.updates+=1


class Model:
    def __init__(self,arm,h,t):
        self.base=base_model('rate_mixture_v216',h,t)
        self.calibrator=None if arm=='raw_v216' else Calibrator(True,arm=='conditional_full_v218')

    def predict(self,x):
        base,lam,h,f,cache=self.base.predict(x)
        p,c=(base,None) if self.calibrator is None else self.calibrator.predict(x,base)
        return p,lam,h,f,{'base_cache':cache,'base_prediction':base,'calibration':c}

    def observe(self,x,a,y,cache):
        self.base.observe(x,a,y,cache['base_cache'])
        if self.calibrator is not None:self.calibrator.observe(cache['calibration'],a,y)
