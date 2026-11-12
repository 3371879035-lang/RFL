"""Learn from actual verified interventions; exact empirical anchors are not truth."""
from frozen_memory import span_key, decoded


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


class AdaptiveMemory:
    def __init__(self,kind,record):
        self.kind=kind;self.samples={}
        for example in record['recorded_practice_examples']:
            self.observe(tuple(example['key']),tuple(decoded(v) for v in example['returns']))

    def snapshot(self):return tuple((k,len(v),sum(v)/len(v)) for k,v in sorted(self.samples.items()))

    def observe(self,key,returns):self.samples.setdefault(key,[]).extend(float(v) for v in returns)

    def key(self,mode,terminal,evidence,action):return span_key(mode,terminal,evidence,action)

    def recall(self,mode,terminal,evidence,actions,costs):
        keys={a:self.key(mode,terminal,evidence,a) for a in actions};groups={}
        for key,vals in sorted(self.samples.items()):groups.setdefault(key[:-2],[]).extend((key[-1],v) for v in vals)
        info={'keys':keys,'representation':self.kind,'supported':all(k[:-2] in groups for k in keys.values())}
        if not info['supported']:return None,info
        models={a:fit_stump(groups[k[:-2]]) for a,k in keys.items()};scores={};sources={}
        for a,key in keys.items():
            m=models[a]
            if self.kind=='empirical-anchor' and key in self.samples:
                scores[a]=sum(self.samples[key])/len(self.samples[key]);sources[a]='empirical'
            else:
                scores[a]=m['left'] if m['cut'] is None or key[-1]<=m['cut'] else m['right'];sources[a]='stump'
        info.update(models=models,scores=scores,prediction_sources=sources)
        selected=min(actions,key=lambda a:(-scores[a],costs[a],actions.index(a)))
        return selected,info
