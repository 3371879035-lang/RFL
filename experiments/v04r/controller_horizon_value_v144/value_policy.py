"""Only visible mismatch proposals and fitted raw-return value; no state/truth access."""
from dataclasses import dataclass
from rfl_rebuild.env.kernel import ControllerSite,State
from rfl_rebuild.learner.store import CONTROLLER,Edit
from candidate_loop import Proposal


def candidate(evidence):
    for step in evidence.steps:
        if step.a_cmd!=step.a_realized:
            site=ControllerSite(State(step.x,step.y,step.t,step.kappa,step.phi),step.a_cmd)
            return Proposal('apply',(Edit(CONTROLLER,site,None),))
    return None

@dataclass
class EmpiricalHorizonValue:
    horizon:int
    values:dict=None
    samples:dict=None
    def fit(self,observations):
        self.samples={k:tuple(v[:self.horizon]) for k,v in observations.items()}
        assert all(len(v)==self.horizon for v in self.samples.values())
        self.values={k:sum(v)/len(v) for k,v in self.samples.items()}
    def choose(self):
        return min(('keep','controller-delete'),key=lambda k:(-self.values[k],0 if k=='keep' else 1))
