"""Empirical terminal backoff is a provisional test-order prior, never truth."""
from adaptive_memory import AdaptiveMemory, fit_stump
from memory_candidates import without_terminal


class HypothesisMemory(AdaptiveMemory):
    def recall(self,mode,terminal,evidence,actions,costs):
        keys={a:self.key(mode,terminal,evidence,a) for a in actions}
        groups={}
        for key,values in sorted(self.samples.items()):
            groups.setdefault(key[:-2],[]).extend((key[-1],v) for v in values)
        scores={};sources={};source_keys={};models={};missing=[]
        for action,key in keys.items():
            if key in self.samples:
                values=self.samples[key];scores[action]=sum(values)/len(values)
                sources[action]='empirical';source_keys[action]=(key,)
            elif key[:-2] in groups:
                model=fit_stump(groups[key[:-2]]);models[action]=model
                scores[action]=model['left'] if model['cut'] is None or key[-1]<=model['cut'] else model['right']
                sources[action]='stump'
                source_keys[action]=tuple(k for k in sorted(self.samples) if k[:-2]==key[:-2])
            else:
                compatible=tuple(k for k in sorted(self.samples) if without_terminal(k)==without_terminal(key))
                if self.kind=='terminal-backoff' and compatible:
                    values=[v for k in compatible for v in self.samples[k]]
                    scores[action]=sum(values)/len(values)
                    sources[action]='terminal-backoff-empirical';source_keys[action]=compatible
                else:
                    missing.append(action)
        info={'keys':keys,'representation':self.kind,'supported':not missing,
              'scores':scores,'prediction_sources':sources,'source_keys':source_keys,
              'models':models,'missing':tuple(missing),
              'provisional_actions':tuple(a for a in actions if sources.get(a)=='terminal-backoff-empirical')}
        if missing:return None,info
        selected=min(actions,key=lambda a:(-scores[a],costs[a],actions.index(a)))
        return selected,info
