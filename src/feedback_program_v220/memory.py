"""Unique factual nodes and chronological training views, separate from imagination."""
from dataclasses import asdict,dataclass
import json,math
import torch


@dataclass(frozen=True)
class Schema:
    observation: int = 16
    action: int = 8
    feedback: int = 8
    goal: int = 8

    @property
    def event_features(self):
        return 2*self.observation+self.action+4*self.feedback+self.goal+7


@dataclass(frozen=True)
class Event:
    id: str
    episode: str
    step: int
    observation: tuple
    actions: tuple
    action_index: int
    next_observation: tuple
    feedback: tuple
    feedback_mask: tuple
    goal: tuple
    predicted_feedback: tuple
    predicted_mask: tuple
    propensity: float
    goal_met: bool
    terminal: bool
    cost: float
    source: str = 'environment'
    role: str = 'task'
    previous_id: str | None = None
    candidate_id: str | None = None
    model_id: str = ''

    def __post_init__(self):
        for name in ('observation','next_observation','feedback','feedback_mask','goal','predicted_feedback','predicted_mask'):
            object.__setattr__(self,name,tuple(getattr(self,name)))
        object.__setattr__(self,'actions',tuple(tuple(a) for a in self.actions))


@dataclass(frozen=True)
class ImaginedTransition:
    observation: tuple
    action: tuple
    predicted_next: tuple
    predicted_feedback: tuple
    source_ids: tuple
    model_id: str
    next_variance: tuple = ()
    feedback_variance: tuple = ()


class MemoryBank:
    SOURCES = {'environment':0,'human':1,'tool':2}

    def __init__(self,schema=Schema()):
        self.schema=schema;self.events=[];self.index={}

    def add(self,event):
        if type(event) is not Event:raise TypeError('Only observed Event nodes enter factual memory')
        if event.id in self.index:
            if self.events[self.index[event.id]]!=event:raise ValueError('Conflicting content for a factual identity')
            return False
        s=self.schema
        for values,width in [(event.observation,s.observation),(event.next_observation,s.observation),(event.feedback,s.feedback),
                             (event.feedback_mask,s.feedback),(event.predicted_feedback,s.feedback),(event.predicted_mask,s.feedback),(event.goal,s.goal)]:
            if len(values)!=width:raise ValueError('Event does not match public feature schema')
        if not event.actions or any(len(a)!=s.action for a in event.actions) or not 0<=event.action_index<len(event.actions):
            raise ValueError('Actual action must belong to the observed legal action set')
        if event.source not in self.SOURCES or event.role not in ('task','trial') or not 0<event.propensity<=1 or event.cost<0:
            raise ValueError('Invalid public event metadata')
        if event.previous_id is not None:
            if event.previous_id not in self.index:raise ValueError('Previous node must already be observed')
            previous=self.events[self.index[event.previous_id]]
            if previous.episode!=event.episode or previous.step>=event.step:raise ValueError('Broken episode chronology')
        self.index[event.id]=len(self.events);self.events.append(event)
        return True

    def view(self,stop=None):
        if stop is None:stop=len(self.events)
        if not 0<=stop<=len(self.events):raise ValueError('Memory prefix outside known history')
        rows=[];sources=[];parents=[]
        for i,e in enumerate(self.events[:stop]):
            fb=[v if observed else 0. for v,observed in zip(e.feedback,e.feedback_mask)]
            pred=[v if observed else 0. for v,observed in zip(e.predicted_feedback,e.predicted_mask)]
            meta=[math.log1p(stop-i),math.log1p(e.step),e.cost,float(e.goal_met),float(e.terminal),e.propensity,float(e.role=='trial')]
            rows.append([*e.observation,*e.actions[e.action_index],*e.next_observation,*fb,*map(float,e.feedback_mask),
                         *pred,*map(float,e.predicted_mask),*e.goal,*meta])
            sources.append(self.SOURCES[e.source]);parents.append(-1 if e.previous_id is None else self.index[e.previous_id])
        return {'features':torch.tensor(rows,dtype=torch.float32).reshape(1,stop,self.schema.event_features),
                'sources':torch.tensor(sources,dtype=torch.long).reshape(1,stop),
                'parents':torch.tensor(parents,dtype=torch.long).reshape(1,stop),
                'valid':torch.ones(1,stop,dtype=torch.bool),'ids':tuple(e.id for e in self.events[:stop])}

    def training_example(self,event_id):
        index=self.index[event_id];event=self.events[index]
        return self.view(index),event

    def replay(self,event_ids):
        if len(event_ids)!=len(set(event_ids)):raise ValueError('A replay view lists each source event once')
        return tuple(self.training_example(i) for i in event_ids)

    def to_json(self):
        return json.dumps({'schema':asdict(self.schema),'events':[asdict(e) for e in self.events]},sort_keys=True,separators=(',',':'),allow_nan=False)

    @classmethod
    def from_json(cls,text):
        d=json.loads(text);bank=cls(Schema(**d['schema']))
        for raw in d['events']:
            for key in ['observation','next_observation','feedback','feedback_mask','goal','predicted_feedback','predicted_mask']:
                raw[key]=tuple(raw[key])
            raw['actions']=tuple(tuple(a) for a in raw['actions']);bank.add(Event(**raw))
        return bank
