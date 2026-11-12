"""Declared measurement provenance, not equality-based semantic inference."""
from dataclasses import asdict,dataclass
import math
import torch


@dataclass(frozen=True)
class View:
    terms:tuple=()
    constant:float=0.
    def __post_init__(self):object.__setattr__(self,'terms',tuple(tuple(t) for t in self.terms))


@dataclass(frozen=True)
class FeedbackLayout:
    primitive_ids:tuple
    views:tuple
    def __post_init__(self):
        object.__setattr__(self,'primitive_ids',tuple(self.primitive_ids));object.__setattr__(self,'views',tuple(self.views))
        if len(set(self.primitive_ids))!=len(self.primitive_ids):raise ValueError('Primitive identities must be distinct')
        for i in range(len(self.primitive_ids)):
            if not self.direct_fields(i):raise ValueError('Each novel primitive requires a directly observed field')
    def direct_fields(self,i):return [j for j,v in enumerate(self.views) if v.constant==0 and v.terms==(('innovation',i,1.),)]
    def to_dict(self):return asdict(self)
    @classmethod
    def from_dict(cls,d):return cls(tuple(d['primitive_ids']),tuple(View(**v) for v in d['views']))
    def validate_schema(self,schema):
        if len(self.views)!=schema.feedback:raise ValueError('Feedback layout differs from public schema')
        sizes={'next':schema.observation,'observation':schema.observation,'action':schema.action,
               'innovation':len(self.primitive_ids),'goal_met':1,'terminal':1,'action_index':1}
        for view in self.views:
            for kind,i,coefficient in view.terms:
                if kind not in sizes or not 0<=i<sizes[kind] or not math.isfinite(coefficient):raise ValueError('Unknown public view coordinate')

    def innovations(self,event,predicted=False):
        values=event.predicted_feedback if predicted else event.feedback
        masks=event.predicted_mask if predicted else event.feedback_mask
        out=[];valid=[]
        for i in range(len(self.primitive_ids)):
            seen=[values[j] for j in self.direct_fields(i) if masks[j]]
            if seen and any(v!=seen[0] for v in seen):raise ValueError('Conflicting copies of one primitive measurement')
            out.append(seen[0] if seen else 0.);valid.append(bool(seen))
        return tuple(out),tuple(valid)

    def render(self,next_observation,innovations,goal_met,terminal,observation,action,action_index):
        source={'next':next_observation,'innovation':innovations,'goal_met':(goal_met,),'terminal':(terminal,),
                'observation':observation,'action':action,'action_index':(action_index,)}
        return tuple(v.constant+sum(coef*source[kind][i] for kind,i,coef in v.terms) for v in self.views)

    def visible_views(self,innovation_mask):
        return tuple(all(innovation_mask[i] for kind,i,c in v.terms if kind=='innovation' and c!=0) for v in self.views)

    def validate_event(self,event):
        u,m=self.innovations(event)
        values=self.render(event.next_observation,u,float(event.goal_met),float(event.terminal),event.observation,event.actions[event.action_index],event.action_index)
        available=self.visible_views(m)
        for j,visible in enumerate(event.feedback_mask):
            if visible and not available[j]:raise ValueError('A derived observed field lacks its declared primitive observation')
            if visible and not math.isclose(values[j],event.feedback[j],rel_tol=1e-6,abs_tol=1e-8):
                raise ValueError('Observed feedback contradicts declared measurement provenance')

    def projection(self,observation,actions):
        """Root vector is [next observation, innovations, goal_met, terminal]."""
        o=observation.shape[-1];p=len(self.primitive_ids);q=o+p+2
        matrix=observation.new_zeros(len(self.views),q);offset=observation.new_zeros(*actions.shape[:-1],len(self.views))
        for j,view in enumerate(self.views):
            offset[...,j]=view.constant
            for kind,i,c in view.terms:
                if kind in ('next','innovation','goal_met','terminal'):
                    index=i if kind=='next' else o+i if kind=='innovation' else o+p if kind=='goal_met' else o+p+1
                    matrix[j,index]+=c
                elif kind=='observation':offset[...,j]+=c*observation[...,i,None]
                elif kind=='action':offset[...,j]+=c*actions[...,i]
                else:offset[...,j]+=c*torch.arange(actions.shape[-2],device=actions.device,dtype=actions.dtype)
        return matrix,offset
