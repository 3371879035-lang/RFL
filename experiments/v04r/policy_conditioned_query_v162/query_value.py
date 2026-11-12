"""Explicit query DATA projection and a policy-conditioned empirical value tree."""
from dataclasses import dataclass
from rfl_rebuild.env import kernel as K

FIELDS=('x','y','t','kappa','phi')

@dataclass(frozen=True,slots=True)
class QueryFeatureData:
    factual:tuple
    planned:tuple
    numeric:tuple
    decision:tuple

    @classmethod
    def from_live(cls,evidence,spec,values,current):
        factual=tuple((s.x,s.y,s.t,s.kappa,s.phi,s.z,s.m,s.a_cmd) for s in evidence.steps)
        planned=tuple(tuple(getattr(r.state,k) for k in FIELDS)+(r.control.z,r.control.m,r.command) for r in spec.rows)
        numeric=tuple(sorted((tuple(getattr(a.state,k) for k in FIELDS)+(a.z,a.m,a.a),v) for a,v in values.q_overrides.items()))
        decision=tuple(sorted((tuple(getattr(a.state,k) for k in FIELDS)+(a.z,a.m),v) for a,v in current.decision_overrides.items()))
        return cls(factual,planned,numeric,decision)

    @classmethod
    def from_recorded(cls,payload):
        # Data only: no FactualEvidence/NativeTrace/Episode/issued source constructor.
        factual=tuple(tuple(s[k] for k in FIELDS+('z','m','a_cmd')) for s in payload['evidence']['steps'])
        planned=tuple(tuple(r['state'][k] for k in FIELDS)+(r['control']['z'],r['control']['m'],r['command']) for r in payload['specification']['rows'])
        numeric=[]
        for row in payload['post_TD']['learning_values']['Q']:
            a=row['address'];numeric.append((tuple(a['state'][k] for k in FIELDS)+(a['z'],a['m'],a['a']),float.fromhex(row['value']['binary64_hex'])))
        decision=tuple(sorted((tuple(v['address']['state'][k] for k in FIELDS)+(v['address']['z'],v['address']['m']),v['value']) for v in payload['post_TD']['current']['D']))
        return cls(factual,planned,tuple(sorted(numeric)),decision)


def query_features(data,reference):
    numeric=dict(data.numeric)
    def row(point):
        key=point[:7];base=reference.row(K.State(*key[:5]),key[5],key[6])
        return {a:numeric.get(key+(a,),v) for a,v in base.items()}
    regrets=[max(row(p).values())-row(p)[p[7]] for p in data.planned]
    j=next(i for i,(f,p) in enumerate(zip(data.factual,data.planned)) if f[7]!=p[7])
    assert data.factual[j][:7]==data.planned[j][:7]
    values=row(data.planned[j]);gap=values[data.factual[j][7]]-values[data.planned[j][7]]
    policy=dict(data.decision);policy_regrets=[]
    for p in data.planned:
        values=row(p);greedy=min(a for a,v in values.items() if v==max(values.values()))
        policy_regrets.append(max(values.values())-values[policy.get(p[:7],greedy)])
    return max(regrets),gap,max(policy_regrets)

@dataclass(frozen=True,slots=True)
class QueryTrainingPoint:
    x:tuple
    gain_per_paid_probe:float

@dataclass(frozen=True,slots=True)
class ValueNode:
    value:float
    n:int
    sse:float
    feature:int|None=None
    threshold:float|None=None
    left:object=None
    right:object=None

@dataclass(frozen=True,slots=True)
class FrozenQueryValue:
    support:tuple
    root:ValueNode
    n:int

    def predict(self,x):
        assert len(x)==len(self.support)
        if any(v<lo or v>hi for v,(lo,hi) in zip(x,self.support)):return None
        node=self.root
        while node.feature is not None:
            node=node.left if x[node.feature]<=node.threshold else node.right
        return node.value


def fit_query_value(points):
    assert type(points) is tuple and points and all(type(p) is QueryTrainingPoint for p in points)
    d=len(points[0].x);assert d in (2,3) and all(len(p.x)==d for p in points)
    mean=lambda ps:sum(p.gain_per_paid_probe for p in ps)/len(ps)
    loss=lambda ps:sum((p.gain_per_paid_probe-mean(ps))**2 for p in ps)
    def grow(ps):
        value=mean(ps);error=loss(ps);choices=[]
        for j in range(d):
            values=sorted(set(p.x[j] for p in ps))
            for a,b in zip(values,values[1:]):
                cut=(a+b)/2;left=tuple(p for p in ps if p.x[j]<=cut);right=tuple(p for p in ps if p.x[j]>cut)
                choices.append((loss(left)+loss(right),j,cut,left,right))
        best=min(choices,key=lambda v:v[:3]) if choices else None
        if best is None or best[0]>=error:return ValueNode(value,len(ps),error)
        _,j,cut,left,right=best
        return ValueNode(value,len(ps),error,j,cut,grow(left),grow(right))
    support=tuple((min(p.x[j] for p in points),max(p.x[j] for p in points)) for j in range(d))
    return FrozenQueryValue(support,grow(points),len(points))
