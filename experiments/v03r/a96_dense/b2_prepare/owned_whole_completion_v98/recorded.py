"""Recorded geometry/value data, explicitly NOT native RolloutTrace/StepResult.

No source, pair, role or persistent learner state is reconstructed here. The
owned transfer entry authenticates the artifact and exact current pre-source.
"""
from dataclasses import dataclass, fields
import math

from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.env import kernel as K


def require(ok, message):
    if not ok:
        raise ProtocolError(message)


@dataclass(frozen=True, slots=True)
class RecordedStep:
    state: K.State
    control: K.ControlState
    a_cmd: int
    u: int
    a_realized: int
    reward: float
    terminal: bool
    outcome: str | None
    illegal: bool = False


@dataclass(frozen=True, slots=True)
class RecordedTrace:
    steps: tuple
    outcome: str | None
    control: K.ControlState
    mask: K.FaultMask
    interventions: K.InterventionSet
    base_option: int
    option_in_force: int

    @property
    def return_value(self):
        return float(sum(s.reward for s in self.steps))


def _state(data):
    names=('x','y','t','kappa','phi')
    require(type(data) is dict and set(data)==set(names) and all(type(data[n]) is int for n in names),
            'exact recorded state geometry')
    return K.State(*(data[n] for n in names))


def _control(data):
    require(type(data) is dict and set(data)=={'z','m'} and all(type(v) is int for v in data.values())
            and data['z'] in K.option_ids() and data['m'] in (0,1), 'exact recorded control')
    return K.ControlState(data['z'],data['m'])


def decode(data):
    require(type(data) is dict and set(data)=={f.name for f in fields(K.RolloutTrace)}, 'closed recorded trace schema')
    require(data['mask']=={'decision':None,'controller':None,'plant':None,'trap':None}
            and data['interventions']=={'members':[]}, 'recorded bank must be ordinary/no-fault/no-do')
    require(type(data['steps']) is list and 0<len(data['steps'])<=K.HORIZON, 'complete recorded steps required')
    steps=[]
    for i,x in enumerate(data['steps']):
        require(type(x) is dict and set(x)=={f.name for f in fields(K.StepResult)}, 'closed step schema')
        require(type(x['reward']) is dict and set(x['reward'])=={'binary64_hex'}
                and type(x['reward']['binary64_hex']) is str, 'recorded binary64 reward')
        reward=float.fromhex(x['reward']['binary64_hex'])
        require(math.isfinite(reward) and reward.hex()==x['reward']['binary64_hex'], 'finite exact reward bits')
        require(all(type(x[n]) is int and x[n] in range(5) for n in ('a_cmd','u','a_realized'))
                and type(x['terminal']) is bool and type(x['illegal']) is bool and not x['illegal'],
                'exact ordinary recorded action/flags')
        state=_state(x['state']);control=_control(x['control'])
        require(state.t==i+1 and x['terminal']==(i==len(data['steps'])-1), 'complete chronological recorded path')
        require(x['outcome'] in (None,K.Outcome.SUCCESS,K.Outcome.COLLISION,K.Outcome.TRAP,K.Outcome.TIMEOUT), 'native outcome vocabulary')
        steps.append(RecordedStep(state,control,x['a_cmd'],x['u'],x['a_realized'],reward,x['terminal'],x['outcome'],x['illegal']))
    require(all(type(data[n]) is int and data[n] in K.option_ids() for n in ('base_option','option_in_force')),
            'exact recorded proposal/in-force option')
    control=_control(data['control'])
    require(control==steps[-1].control and data['outcome']==steps[-1].outcome
            and data['outcome'] is not None, 'terminal recorded metadata mismatch')
    return RecordedTrace(tuple(steps),data['outcome'],control,K.FaultMask(),K.InterventionSet(),
                         data['base_option'],data['option_in_force'])
