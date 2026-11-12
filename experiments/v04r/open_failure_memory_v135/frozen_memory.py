"""Frozen recorded diagnostic values, not restored native learner identity."""
from dataclasses import dataclass
from diagnostic_memory import memory_key


def span_key(mode,terminal,evidence,action):
    from evidence_selector import evidence_key
    base=evidence_key(mode,terminal,evidence,action);span=0
    if action.startswith('single:'):
        i=int(action.split(':')[1]);s=evidence.steps[i];token=(s.x,s.y,s.a_cmd);lo=hi=i
        while lo>0 and (evidence.steps[lo-1].x,evidence.steps[lo-1].y,evidence.steps[lo-1].a_cmd)==token:lo-=1
        while hi+1<len(evidence.steps) and (evidence.steps[hi+1].x,evidence.steps[hi+1].y,evidence.steps[hi+1].a_cmd)==token:hi+=1
        span=hi-lo+1
    return base+('run-span',span)


def decoded(x):return float.fromhex(x['binary64_hex']) if isinstance(x,dict) and set(x)=={'binary64_hex'} else x


@dataclass(frozen=True)
class FrozenMemory:
    kind: str
    table: tuple
    models: tuple

    @classmethod
    def from_record(cls,kind,record):
        rows=[] if kind=='none' else record['coarse_table' if kind=='coarse' else 'exact_table']
        table=tuple((tuple(k),n,decoded(v)) for k,n,v in rows)
        models=tuple((tuple(m['base_key']),tuple((k,decoded(v)) for k,v in sorted(m['model'].items()))) for m in record['models']) if kind=='learned-stump' else ()
        return cls(kind,table,models)

    def snapshot(self):return self.table

    def weight_snapshot(self):return self.table,self.models

    def key(self,mode,terminal,evidence,action):
        return (memory_key if self.kind=='coarse' else span_key)(mode,terminal,evidence,action)

    def recall(self,mode,terminal,evidence,actions,costs):
        keys={a:self.key(mode,terminal,evidence,a) for a in actions}
        info={'keys':keys,'representation':self.kind};means={k:v for k,n,v in self.table}
        if self.kind=='learned-stump':
            models={k:dict(v) for k,v in self.models};info['supported']=all(k[:-2] in models for k in keys.values())
            if not info['supported']:return None,info
            fitted={a:models[k[:-2]] for a,k in keys.items()};info['models']=fitted
            scores={a:(m['left'] if m['cut'] is None or keys[a][-1]<=m['cut'] else m['right']) for a,m in fitted.items()}
        else:
            info['supported']=all(k in means for k in keys.values())
            if not info['supported']:return None,info
            scores={a:means[k] for a,k in keys.items()}
        info['scores']=scores
        selected=min(actions,key=lambda a:(-scores[a],costs[a],actions.index(a)))
        return selected,info
