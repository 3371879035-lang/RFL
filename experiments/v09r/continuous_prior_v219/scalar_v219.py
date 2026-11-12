"""Independent scalar Beta mixture arithmetic; no torch/native learner import."""
from pathlib import Path
import math,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'evidence_persistence_v216'))
from scalar_v216 import Predictor,make_model as base_model,groups,prior,softmax


def logsum(vs):
    m=max(vs)
    if m==-math.inf:return m
    return m+math.log(math.fsum(math.exp(v-m) for v in vs))


class Calibrator:
    def __init__(self,conditional=True,concentration=1.):
        self.groups=groups(4,True) if conditional else [()]
        self.group_prior=prior(self.groups,4);self.pi=[.5,.125,.125,.25]
        self.a=concentration;self.logs={};self.coeffs={};self.updates=0

    def cell(self,key):
        coeffs=self.coeffs.get(key,[0.]);n=len(coeffs)-1;a=self.a
        joint=[c+math.lgamma(a+j)+math.lgamma(a+n-j)-math.lgamma(2*a+n)-2*math.lgamma(a)+math.lgamma(2*a) for j,c in enumerate(coeffs)]
        z=logsum(joint);rho=softmax(joint);den=2*a+n
        mean=math.fsum(w*(a+j)/den for j,w in enumerate(rho))
        second=math.fsum(w*(a+j)*(a+j+1)/(den*(den+1)) for j,w in enumerate(rho))
        local=[math.log(p)+v for p,v in zip(self.pi,self.logs.get(key,[0.]*3)+[z])]
        return logsum(local),softmax(local),2*mean-1,4*second-4*mean+1

    def predict(self,x,base):
        cells={key:self.cell(key) for key in self.coeffs}
        glog=[self.group_prior[i]+math.fsum(c[0] for key,c in cells.items() if key[0]==g) for i,g in enumerate(self.groups)]
        q=softmax(glog);ps=[];keys=[];maps=[];weights=[];coefs=[];within=[];between=[];bm=[];bv=[]
        for action in range(2):
            z=(*x,action);kk=[(g,tuple(z[j] for j in g)) for g in self.groups]
            cc=[cells[key] if key in cells else self.cell(key) for key in kk]
            joint=[[gg*w for w in c[1]] for gg,c in zip(q,cc)]
            mass=[math.fsum(w[k] for w in joint) for k in range(4)]
            alpha=mass[1]-mass[2];beta=math.fsum(w[3]*c[2] for w,c in zip(joint,cc))
            bs=math.fsum(w[3]*c[3] for w,c in zip(joint,cc));bmean=beta/mass[3]
            p=base[action][1];u=p*(1-p);v=u*(2*p-1);delta=alpha*v+beta*u
            pred=[base[action][0]-delta,p+delta];variance=max(0.,(mass[1]+mass[2])*v*v+bs*u*u-delta*delta)
            ps.append(pred);keys.append(kk);coefs.append([alpha,beta]);weights.append(mass)
            maps.append([[base[action][0]-d,p+d] for d in [0.,v,-v,-u,u]])
            between.append(variance);within.append(pred[1]*(1-pred[1])-variance);bm.append(bmean);bv.append(max(0.,bs/mass[3]-bmean*bmean))
        return ps,{'keys':keys,'base':base,'maps':maps,'weights':weights,'coefficients':coefs,'within':within,'between':between,
                   'bias_mean':bm,'bias_variance':bv,'log_evidence_ratio':logsum(glog)}

    def observe(self,cache,a,y):
        ratio=[math.log(m[y])-math.log(cache['base'][a][y]) for m in cache['maps'][a]]
        for key in cache['keys'][a]:
            self.logs[key]=[l+r for l,r in zip(self.logs.get(key,[0.]*3),ratio[:3])]
            old=self.coeffs.get(key,[0.]);new=[]
            for j in range(len(old)+1):
                terms=[]
                if j<len(old):terms.append(old[j]+ratio[3])
                if j>0:terms.append(old[j-1]+ratio[4])
                new.append(logsum(terms))
            self.coeffs[key]=new
        self.updates+=1


class Model:
    def __init__(self,arm,h,t):
        self.base=base_model('rate_mixture_v216',h,t);self.calibrator=Calibrator()
    def predict(self,x):
        base,lam,h,f,c=self.base.predict(x);p,cal=self.calibrator.predict(x,base)
        return p,lam,h,f,{'base_cache':c,'base_prediction':base,'calibration':cal}
    def observe(self,x,a,y,cache):
        self.base.observe(x,a,y,cache['base_cache']);self.calibrator.observe(cache['calibration'],a,y)
