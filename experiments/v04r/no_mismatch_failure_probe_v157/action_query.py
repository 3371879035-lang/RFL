"""A planned action experiment is DATA, not fabricated observed evidence."""
from dataclasses import dataclass
from rfl_rebuild.env import kernel as K

@dataclass(frozen=True,slots=True)
class PlannedActionRow:
    state:K.State
    control:K.ControlState
    command:int
    previously_realized:int
    admissible_rank:int

@dataclass(frozen=True,slots=True)
class ActionTrialSpecification:
    target_index:int
    observed_failed_command:int
    alternative_command:int
    rows:tuple

    @classmethod
    def from_visible_failure(cls,evidence,alternative):
        out=[]
        for i,s in enumerate(evidence.steps):
            at=K.State(s.x,s.y,s.t,s.kappa,s.phi);ctrl=K.ControlState(s.z,s.m)
            cmd=alternative if i==len(evidence.steps)-1 else s.a_cmd
            admissible=tuple(K.option_actions(ctrl.z,ctrl,at))
            out.append(PlannedActionRow(at,ctrl,cmd,s.a_realized,admissible.index(cmd)))
        return cls(len(out)-1,evidence.steps[-1].a_cmd,alternative,tuple(out))

    def literal_coordinates(self):
        coins=[(1<<64)-1]*12;rejections=[(0,)]*12
        for i,row in enumerate(self.rows):coins[i]=0;rejections[i]=(row.admissible_rank,)
        return tuple(coins),tuple(rejections)

    def actual_reach(self,trace):
        at=K.State(0,2,0,self.rows[0].state.kappa,self.rows[0].state.phi);ctrl=K.ControlState(trace['option_in_force'],0)
        for i,wanted in enumerate(self.rows):
            if i>=len(trace['steps']):return {'reached':False,'reason':'ended_before_target','steps':i}
            actual=trace['steps'][i]
            if (at,ctrl,actual['a_cmd'])!=(wanted.state,wanted.control,wanted.command):return {'reached':False,'reason':'planned_prefix_not_followed','steps':i}
            if i<self.target_index and actual['a_realized']!=wanted.previously_realized:return {'reached':False,'reason':'earlier_realization_differs','steps':i}
            at=K.State(**actual['state']);ctrl=K.ControlState(**actual['control'])
        return {'reached':True,'reason':'actual_alternate_command_at_failed_context','steps':len(self.rows)}
