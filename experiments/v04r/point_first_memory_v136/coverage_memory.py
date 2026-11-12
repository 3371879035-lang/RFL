"""Point evidence can order tests before interpolation; neither is a veto."""
from adaptive_memory import AdaptiveMemory, fit_stump
from memory_candidates import without_terminal


class PointFirstMemory(AdaptiveMemory):
    def recall(self,mode,terminal,evidence,actions,costs):
        keys={a:self.key(mode,terminal,evidence,a) for a in actions}
        groups={}
        for key,values in sorted(self.samples.items()):
            groups.setdefault(key[:-2],[]).extend((key[-1],v) for v in values)
        scores={};sources={};source_keys={};models={};missing=[];coverage={}
        for action,key in keys.items():
            compatible=tuple(k for k in sorted(self.samples) if without_terminal(k)==without_terminal(key))
            if key in self.samples:
                values=self.samples[key];scores[action]=sum(values)/len(values)
                sources[action]='empirical';source_keys[action]=(key,)
            elif compatible:
                values=[v for k in compatible for v in self.samples[k]]
                scores[action]=sum(values)/len(values)
                sources[action]='terminal-backoff-empirical';source_keys[action]=compatible
            elif key[:-2] in groups:
                model=fit_stump(groups[key[:-2]]);models[action]=model
                scores[action]=model['left'] if model['cut'] is None or key[-1]<=model['cut'] else model['right']
                sources[action]='stump'
                source_keys[action]=tuple(k for k in sorted(self.samples) if k[:-2]==key[:-2])
            else:
                missing.append(action)
            coverage[action]={'exact_terminal_point_samples':len(self.samples.get(key,())),
                              'matched_other_terminal_point_samples':sum(len(self.samples[k]) for k in compatible if k!=key),
                              'same_terminal_family_samples':len(groups.get(key[:-2],()))}
        info={'keys':keys,'representation':self.kind,'supported':not missing,
              'scores':scores,'prediction_sources':sources,'source_keys':source_keys,
              'models':models,'missing':tuple(missing),'coverage':coverage,
              'provisional_actions':tuple(a for a in actions if sources.get(a)=='terminal-backoff-empirical')}
        if missing:return None,info
        selected=min(actions,key=lambda a:(-scores[a],costs[a],actions.index(a)))
        return selected,info
