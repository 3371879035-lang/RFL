"""Learned query DATA, never an observed-prefix or write-authorization object."""
from dataclasses import dataclass
from rfl_rebuild.env import kernel as K

@dataclass(frozen=True,slots=True)
class PlannedCommand:
    x:int
    y:int
    t:int
    z:int
    m:int
    command:int

@dataclass(frozen=True,slots=True)
class PlannedProbeProgram:
    rows:tuple

    @classmethod
    def from_evidence(cls,evidence):
        target=next(i for i,s in enumerate(evidence.steps) if s.a_cmd!=s.a_realized)
        return cls(tuple(PlannedCommand(s.x,s.y,s.t,s.z,s.m,s.a_cmd) for s in evidence.steps[:target+1]))

    @classmethod
    def from_recorded_evidence(cls,evidence):
        target=next(i for i,s in enumerate(evidence['steps']) if s['a_cmd']!=s['a_realized'])
        return cls(tuple(PlannedCommand(*(s[k] for k in ('x','y','t','z','m','a_cmd'))) for s in evidence['steps'][:target+1]))

    def matches_first(self,evidence):
        s=evidence.steps[0]
        return self.rows[0]==PlannedCommand(s.x,s.y,s.t,s.z,s.m,s.a_cmd)

    def coordinates(self,evidence):
        # A hypothesis recontextualized using CURRENT public action domains.
        # These are not actual current observed states or responsibility evidence.
        coins=[(1<<64)-1]*12;rejections=[(0,)]*12
        for i,s in enumerate(self.rows):
            at=K.State(s.x,s.y,s.t,evidence.kappa,evidence.phi);ctrl=K.ControlState(s.z,s.m)
            admissible=tuple(sorted(K.option_actions(ctrl.z,ctrl,at)))
            coins[i]=0;rejections[i]=(admissible.index(s.command),)
        return tuple(coins),tuple(rejections)
