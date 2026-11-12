"""A failed actual trial can suggest replaying a witnessed factual command.

No claim is made that the earlier command is safe or better: it must be tested.
"""
from dataclasses import dataclass
from candidate_loop import Proposal
from rfl_rebuild.env.kernel import State
from rfl_rebuild.learner.store import DECISION, DecisionAddress, Edit


def owner(step):
    return DecisionAddress(State(step.x,step.y,step.t,step.kappa,step.phi),step.z,step.m)


@dataclass(frozen=True)
class LiteralReplayCandidate:
    action: str
    factual_index: int
    trial_index: int
    affected: DecisionAddress
    witnessed_command: int
    failed_trial_command: int
    proposal: Proposal


def build_replay(mode,factual,failed_probe):
    if mode!='patch-adaptive' or not failed_probe.steps:
        return None
    last=failed_probe.steps[-1];target=owner(last)
    for i,step in enumerate(factual.steps):
        if owner(step)==target and step.a_cmd!=last.a_cmd:
            action='replay:'+str(i)+':'+str(len(failed_probe.steps)-1)
            return LiteralReplayCandidate(action,i,len(failed_probe.steps)-1,target,step.a_cmd,last.a_cmd,
                        Proposal('apply',(Edit(DECISION,target,step.a_cmd),)))
    return None


def replay_memory_key(mode,terminal,factual,candidate):
    mismatch=any(s.a_cmd!=s.a_realized for s in factual.steps)
    return (mode,terminal,mismatch,'trial-literal-replay-v1',candidate.witnessed_command,
            candidate.failed_trial_command)
