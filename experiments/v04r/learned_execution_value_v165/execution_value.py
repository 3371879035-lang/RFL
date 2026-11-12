"""Own ordinary-learning consequence DATA, not evaluator/source truth."""
from dataclasses import dataclass
from rfl_rebuild.env import kernel as K
FIELDS=('x','y','t','kappa','phi')

def numeric_data(values):
    return tuple(sorted((tuple(getattr(a.state,k) for k in FIELDS)+(a.z,a.m,a.a),v) for a,v in values.q_overrides.items()))

def recorded_numeric(store):
    return tuple(sorted((tuple(v['address']['state'][k] for k in FIELDS)+(v['address']['z'],v['address']['m'],v['address']['a']),float.fromhex(v['value']['binary64_hex'])) for v in store['Q']))

@dataclass(frozen=True,slots=True)
class ExecutionFeatureData:
    factual:tuple
    before_numeric:tuple
    after_numeric:tuple

    @classmethod
    def from_live(cls,evidence,before,after):
        return cls(tuple(tuple(getattr(s,k) for k in FIELDS)+tuple(getattr(s,k) for k in ('z','m','a_cmd','a_realized')) for s in evidence.steps),before,numeric_data(after))

    @classmethod
    def from_recorded(cls,evidence,before,after):
        return cls(tuple(tuple(s[k] for k in FIELDS+('z','m','a_cmd','a_realized')) for s in evidence['steps']),recorded_numeric(before),recorded_numeric(after))

def execution_features(data,reference):
    mismatch=[s for s in data.factual if s[7]!=s[8]];assert mismatch
    first=mismatch[0];key=first[:8];prior=reference.row(K.State(*key[:5]),key[5],key[6])[key[7]]
    before=dict(data.before_numeric).get(key,prior);after=dict(data.after_numeric).get(key,prior)
    return after-before,float(len(set(s[:5]+(s[7],) for s in mismatch)))
