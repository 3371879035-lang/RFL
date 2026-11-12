"""Online diagnostic consequence memory, separate from ordinary learner R+L.

Only actual failure-triggered practice outcomes train this memory. The extra
run-span representation is supplied, not claimed learned/discovered. No
context identity, absolute coordinate, ordinal position or hidden fault is in
the stored key; the table's means are learned from actual intervention returns.
"""
from evidence_selector import evidence_key


def memory_key(mode, terminal, evidence, action):
    key=evidence_key(mode,terminal,evidence,action)
    if not action.startswith('single:'):
        return key+('global',)
    i=int(action.split(':')[1]);s=evidence.steps[i]
    token=(s.x,s.y,s.a_cmd);lo=hi=i
    while lo>0 and (evidence.steps[lo-1].x,evidence.steps[lo-1].y,evidence.steps[lo-1].a_cmd)==token:lo-=1
    while hi+1<len(evidence.steps) and (evidence.steps[hi+1].x,evidence.steps[hi+1].y,evidence.steps[hi+1].a_cmd)==token:hi+=1
    return key+('repeated-run' if hi>lo else 'single-step',)


class DiagnosticMemory:
    def __init__(self):
        self.samples={}

    def snapshot(self):
        return tuple((k,len(v),sum(v)/len(v)) for k,v in sorted(self.samples.items()))

    def observe(self,key,returns):
        self.samples.setdefault(key,[]).extend(float(x) for x in returns)

    def recall(self,mode,terminal,evidence,actions,costs):
        keys={a:memory_key(mode,terminal,evidence,a) for a in actions}
        lookup={k:mean for k,n,mean in self.snapshot()}
        if any(k not in lookup for k in keys.values()):return None,{'keys':keys,'supported':False}
        scores={a:lookup[k] for a,k in keys.items()}
        selected=min(actions,key=lambda a:(-scores[a],costs[a],actions.index(a)))
        return selected,{'keys':keys,'supported':True,'scores':scores}
