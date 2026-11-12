"""Direct-feedback control: observed mismatch plus own stored state, never evaluator truth."""
from rfl_rebuild.env.kernel import ControllerSite,State
from rfl_rebuild.learner.store import CONTROLLER,Edit
from candidate_loop import Proposal

def candidate(evidence):
    for step in evidence.steps:
        if step.a_cmd!=step.a_realized:
            site=ControllerSite(State(step.x,step.y,step.t,step.kappa,step.phi),step.a_cmd)
            return Proposal('apply',(Edit(CONTROLLER,site,None),))
    return None


def choose(evidence,own_controller):
    proposed=candidate(evidence)
    if proposed is None:return Proposal(),{'has_observed_mismatch':False,'own_store_present':False}
    site=proposed.edits[0].address
    present=site in own_controller
    return (proposed if present else Proposal()),{'has_observed_mismatch':True,'site':site,'own_store_present':present,
            'stored_mapping':own_controller[site] if present else None}
