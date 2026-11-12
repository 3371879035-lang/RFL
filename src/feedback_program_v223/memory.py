"""Raw receipts retained; neural memory reads only canonical primitive feedback."""
from dataclasses import asdict,replace
import json
import torch
from feedback_program_v221.memory import MemoryBank as PreviousBank,Event,Schema
from .layout import FeedbackLayout


class MemoryBank(PreviousBank):
    def __init__(self,schema,layout):
        super().__init__(schema);layout.validate_schema(schema);self.layout=layout
        self.canonical_schema=replace(schema,feedback=len(layout.primitive_ids))
    def add(self,event):
        if type(event) is not Event:raise TypeError('Only actual Event receipts enter factual memory')
        self.layout.validate_event(event)
        return super().add(event)
    def view(self,stop=None):
        if stop is None:stop=len(self.events)
        if not 0<=stop<=len(self.events):raise ValueError('Invalid historical prefix')
        canonical=PreviousBank(self.canonical_schema)
        for e in self.events[:stop]:
            u,m=self.layout.innovations(e);pred,pm=self.layout.innovations(e,True)
            canonical.add(replace(e,feedback=u,feedback_mask=m,predicted_feedback=pred,predicted_mask=pm))
        return canonical.view()
    def evidence(self,groups,stop=None):
        prefix=self.view(stop);flat=[i for group in groups for i in group]
        if len(flat)!=len(set(flat)) or not set(flat)<=set(prefix['ids']):raise ValueError('Evidence identity or prefix mismatch')
        n=max([len(g) for g in groups]+[0]);a=len(groups)
        features=prefix['features'].new_zeros(1,a,n,self.canonical_schema.event_features)
        sources=torch.zeros(1,a,n,dtype=torch.long);valid=torch.zeros(1,a,n,dtype=torch.bool)
        for arm,ids in enumerate(groups):
            if ids:
                positions=[self.index[i] for i in ids];features[0,arm,:len(ids)]=prefix['features'][0,positions]
                sources[0,arm,:len(ids)]=prefix['sources'][0,positions];valid[0,arm,:len(ids)]=True
        return {'features':features,'sources':sources,'valid':valid,'ids':tuple(tuple(g) for g in groups)}
    def to_json(self):
        return json.dumps({'schema':asdict(self.schema),'layout':self.layout.to_dict(),'events':[asdict(e) for e in self.events]},sort_keys=True,separators=(',',':'),allow_nan=False)
    @classmethod
    def from_json(cls,text):
        d=json.loads(text);bank=cls(Schema(**d['schema']),FeedbackLayout.from_dict(d['layout']))
        for event in d['events']:bank.add(Event(**event))
        return bank
