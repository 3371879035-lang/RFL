"""Observed command-prefix experiments. No mask, causal label, evaluator or reference Q input."""
from dataclasses import dataclass
from rfl_rebuild.env import kernel as K

@dataclass(frozen=True,slots=True)
class ObservedCommand:
    state: K.State
    control: K.ControlState
    command: int
    realized: int
    admissible_rank: int

@dataclass(frozen=True,slots=True)
class PrefixSpecification:
    target_index: int
    rows: tuple

@dataclass(frozen=True,slots=True)
class ReachResult:
    reached: bool
    reason: str
    checked_steps: int


def compile_observed_prefix(evidence):
    target=next(i for i,s in enumerate(evidence.steps) if s.a_cmd!=s.a_realized)
    rows=[]
    for s in evidence.steps[:target+1]:
        at=K.State(s.x,s.y,s.t,s.kappa,s.phi);ctrl=K.ControlState(s.z,s.m)
        admissible=tuple(sorted(K.option_actions(ctrl.z,ctrl,at)))
        rows.append(ObservedCommand(at,ctrl,s.a_cmd,s.a_realized,admissible.index(s.a_cmd)))
    return PrefixSpecification(target,tuple(rows))


def literal_coordinates(spec,*,first_command_only=False):
    coins=[(1<<64)-1]*12;rejections=[(0,)]*12
    used=spec.rows[:1] if first_command_only else spec.rows
    for i,s in enumerate(used):coins[i]=0;rejections[i]=(s.admissible_rank,)
    return tuple(coins),tuple(rejections)


def assess_actual_reach(spec,trace):
    # This receives the newly executed task's actual trace DATA, never creates
    # a source/receipt/issued observation from it. The target realization may
    # change under repair; the observed prefix before that target must agree.
    first=spec.rows[0];at=K.State(0,2,0,first.state.kappa,first.state.phi)
    ctrl=K.ControlState(trace['option_in_force'],0)
    for i,wanted in enumerate(spec.rows):
        if i>=len(trace['steps']):return ReachResult(False,'task_ended_before_target',i)
        actual=trace['steps'][i]
        if (at,ctrl,actual['a_cmd'])!=(wanted.state,wanted.control,wanted.command):
            return ReachResult(False,'observed_state_control_or_command_prefix_differs',i)
        if i<spec.target_index and actual['a_realized']!=wanted.realized:
            return ReachResult(False,'preceding_observed_realization_differs',i)
        at=K.State(**actual['state']);ctrl=K.ControlState(**actual['control'])
    return ReachResult(True,'actual_target_consulted_with_matching_observed_prefix',len(spec.rows))
