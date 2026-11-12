"""Explicit query DATA projection and a frozen two-feature empirical value stump."""
from dataclasses import dataclass
from rfl_rebuild.env import kernel as K

FIELDS=('x','y','t','kappa','phi')

@dataclass(frozen=True,slots=True)
class QueryFeatureData:
    factual:tuple
    planned:tuple
    numeric:tuple

    @classmethod
    def from_live(cls,evidence,spec,values):
        factual=tuple((s.x,s.y,s.t,s.kappa,s.phi,s.z,s.m,s.a_cmd) for s in evidence.steps)
        planned=tuple(tuple(getattr(r.state,k) for k in FIELDS)+(r.control.z,r.control.m,r.command) for r in spec.rows)
        numeric=tuple(sorted((tuple(getattr(a.state,k) for k in FIELDS)+(a.z,a.m,a.a),v) for a,v in values.q_overrides.items()))
        return cls(factual,planned,numeric)

    @classmethod
    def from_recorded(cls,payload):
        # Data only: no FactualEvidence/NativeTrace/Episode/issued source constructor.
        factual=tuple(tuple(s[k] for k in FIELDS+('z','m','a_cmd')) for s in payload['evidence']['steps'])
        planned=tuple(tuple(r['state'][k] for k in FIELDS)+(r['control']['z'],r['control']['m'],r['command']) for r in payload['specification']['rows'])
        numeric=[]
        for row in payload['post_TD']['learning_values']['Q']:
            a=row['address'];numeric.append((tuple(a['state'][k] for k in FIELDS)+(a['z'],a['m'],a['a']),float.fromhex(row['value']['binary64_hex'])))
        return cls(factual,planned,tuple(sorted(numeric)))


def query_features(data,reference):
    numeric=dict(data.numeric)
    def row(point):
        key=point[:7];base=reference.row(K.State(*key[:5]),key[5],key[6])
        return {a:numeric.get(key+(a,),v) for a,v in base.items()}
    regrets=[max(row(p).values())-row(p)[p[7]] for p in data.planned]
    j=next(i for i,(f,p) in enumerate(zip(data.factual,data.planned)) if f[7]!=p[7])
    assert data.factual[j][:7]==data.planned[j][:7]
    values=row(data.planned[j]);gap=values[data.factual[j][7]]-values[data.planned[j][7]]
    return max(regrets),gap

@dataclass(frozen=True,slots=True)
class QueryTrainingPoint:
    x:tuple
    gain_per_paid_probe:float

@dataclass(frozen=True,slots=True)
class FrozenQueryValue:
    support:tuple
    split_feature:int|None
    threshold:float|None
    left_mean:float
    right_mean:float
    n:int
    left_n:int
    right_n:int

    def predict(self,x):
        if any(v<lo or v>hi for v,(lo,hi) in zip(x,self.support)):return None
        return self.left_mean if self.split_feature is None or x[self.split_feature]<=self.threshold else self.right_mean


def fit_query_value(points):
    assert type(points) is tuple and points and all(type(p) is QueryTrainingPoint and len(p.x)==2 for p in points)
    mean=lambda ps:sum(p.gain_per_paid_probe for p in ps)/len(ps)
    loss=lambda ps:sum((p.gain_per_paid_probe-mean(ps))**2 for p in ps)
    support=tuple((min(p.x[j] for p in points),max(p.x[j] for p in points)) for j in range(2));choices=[]
    for j in range(2):
        values=sorted(set(p.x[j] for p in points))
        for a,b in zip(values,values[1:]):
            cut=(a+b)/2;left=tuple(p for p in points if p.x[j]<=cut);right=tuple(p for p in points if p.x[j]>cut)
            choices.append((loss(left)+loss(right),j,cut,left,right))
    best=min(choices,key=lambda v:v[:3]) if choices else None
    if best is None or best[0]>=loss(points):return FrozenQueryValue(support,None,None,mean(points),mean(points),len(points),len(points),0)
    _,j,cut,left,right=best
    return FrozenQueryValue(support,j,cut,mean(left),mean(right),len(points),len(left),len(right))
