"""Original factual identities plus arm-specific views; no synthetic summaries as facts."""
import torch
from feedback_program_v220.memory import Event,Schema,MemoryBank as FactualBank


class MemoryBank(FactualBank):
    def evidence(self,groups,stop=None):
        prefix=self.view(stop);known=set(prefix['ids'])
        flattened=[i for group in groups for i in group]
        if len(flattened)!=len(set(flattened)):
            raise ValueError('An actual trial belongs to one evidence arm, once')
        if not set(flattened)<=known:raise ValueError('Evidence is outside the observed prefix')
        count=max([len(g) for g in groups]+[0]);arms=len(groups)
        features=torch.zeros(1,arms,count,self.schema.event_features)
        sources=torch.zeros(1,arms,count,dtype=torch.long);valid=torch.zeros(1,arms,count,dtype=torch.bool)
        for arm,ids in enumerate(groups):
            if ids:
                positions=[self.index[i] for i in ids]
                features[0,arm,:len(ids)]=prefix['features'][0,positions]
                sources[0,arm,:len(ids)]=prefix['sources'][0,positions];valid[0,arm,:len(ids)]=True
        return {'features':features,'sources':sources,'valid':valid,'ids':tuple(tuple(g) for g in groups)}
