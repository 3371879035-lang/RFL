"""Conditional diagnostic values from actual practice; supplied length feature.

Exact and learned-stump backends share the same full-length evidence keys.
No absolute coordinate, ordinal, context ID, hidden cause or future label is a
prediction feature. A stump cut and leaf means are fitted from own outcomes.
"""
from evidence_selector import evidence_key


def span_key(mode, terminal, evidence, action):
    base=evidence_key(mode,terminal,evidence,action)
    span=0
    if action.startswith('single:'):
        i=int(action.split(':')[1]);s=evidence.steps[i]
        token=(s.x,s.y,s.a_cmd);lo=hi=i
        while lo>0 and (evidence.steps[lo-1].x,evidence.steps[lo-1].y,evidence.steps[lo-1].a_cmd)==token:lo-=1
        while hi+1<len(evidence.steps) and (evidence.steps[hi+1].x,evidence.steps[hi+1].y,evidence.steps[hi+1].a_cmd)==token:hi+=1
        span=hi-lo+1
    return base+('run-span',span)


def fit_stump(points):
    mean=sum(y for x,y in points)/len(points)
    best={'cut':None,'left':mean,'right':mean,'squared_error':sum((y-mean)**2 for x,y in points),'n':len(points)}
    xs=sorted({x for x,y in points})
    for lo,hi in zip(xs,xs[1:]):
        cut=(lo+hi)/2;left=[y for x,y in points if x<=cut];right=[y for x,y in points if x>cut]
        lm,rm=sum(left)/len(left),sum(right)/len(right)
        error=sum((y-(lm if x<=cut else rm))**2 for x,y in points)
        trial={'cut':cut,'left':lm,'right':rm,'squared_error':error,'n':len(points)}
        if (error,1,cut)<(best['squared_error'],int(best['cut'] is not None),best['cut'] or 0):best=trial
    return best


class SpanMemory:
    def __init__(self,kind):
        self.kind=kind;self.samples={}

    def snapshot(self):
        return tuple((k,len(v),sum(v)/len(v)) for k,v in sorted(self.samples.items()))

    def observe(self,key,returns):
        self.samples.setdefault(key,[]).extend(float(x) for x in returns)

    def recall(self,mode,terminal,evidence,actions,costs):
        keys={a:span_key(mode,terminal,evidence,a) for a in actions}
        info={'keys':keys,'representation':self.kind}
        if self.kind=='exact-span':
            info['supported']=all(k in self.samples for k in keys.values())
            if not info['supported']:return None,info
            scores={a:sum(self.samples[k])/len(self.samples[k]) for a,k in keys.items()}
        else:
            groups={}
            for key,values in sorted(self.samples.items()):
                groups.setdefault(key[:-2],[]).extend((key[-1],y) for y in values)
            info['supported']=all(k[:-2] in groups for k in keys.values())
            if not info['supported']:return None,info
            fitted={a:fit_stump(groups[k[:-2]]) for a,k in keys.items()}
            scores={a:(m['left'] if m['cut'] is None or keys[a][-1]<=m['cut'] else m['right']) for a,m in fitted.items()}
            info['models']=fitted
        info['scores']=scores
        selected=min(actions,key=lambda a:(-scores[a],costs[a],actions.index(a)))
        return selected,info
