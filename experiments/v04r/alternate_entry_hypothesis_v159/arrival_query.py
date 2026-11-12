"""A finite question generator using public geometry, NOT a native rollout oracle."""
from dataclasses import dataclass
from rfl_rebuild.env import kernel as K


def public_advance(state,control,command):
    x,y=K._enter(command,state)
    nxt=K.State(x,y,state.t+1,state.kappa,state.phi)
    return nxt,K.automaton_transition(control.z,control,state,command,nxt)

@dataclass(frozen=True,slots=True)
class PlannedArrivalRow:
    state:K.State
    control:K.ControlState
    command:int
    admissible_rank:int

@dataclass(frozen=True,slots=True)
class PlannedArrivalProbe:
    target:K.State
    observed_last_pre:K.State
    observed_last_command:int
    rows:tuple

    def literal_coordinates(self):
        coins=[(1<<64)-1]*12;chi=[(0,)]*12
        for i,row in enumerate(self.rows):coins[i]=0;chi[i]=(row.admissible_rank,)
        return tuple(coins),tuple(chi)

    def assess(self,trace):
        at=K.State(0,2,0,self.target.kappa,self.target.phi);ctrl=K.initial_control(trace['option_in_force'])
        for i,wanted in enumerate(self.rows):
            if i>=len(trace['steps']):return {'status':'untested','reason':'terminated_before_intended_arrival','checked_steps':i}
            actual=trace['steps'][i]
            if (at,ctrl,actual['a_cmd'])!=(wanted.state,wanted.control,wanted.command):return {'status':'untested','reason':'planned_prefix_not_followed','checked_steps':i}
            at=K.State(**actual['state']);ctrl=K.ControlState(**actual['control'])
        last=trace['steps'][len(self.rows)-1]
        if at!=self.target:return {'status':'untested','reason':'different_actual_arrival','checked_steps':len(self.rows)}
        # Only the event at that transition matters, not a later episode failure.
        same_failure=last['terminal'] and last['outcome']=='TRAP'
        return {'status':'consistent_on_tested_alternate' if same_failure else 'refuted_on_tested_alternate',
            'reason':'actual_target_TRAP' if same_failure else 'no_TRAP_at_actual_target', 'checked_steps':len(self.rows)}


def propose_alternate(evidence,transition_budget):
    last=evidence.steps[-1];pre=K.State(last.x,last.y,last.t,last.kappa,last.phi);control=K.ControlState(last.z,last.m)
    target,_=public_advance(pre,control,last.a_realized)
    expanded=0;exhausted=False
    start=K.State(0,2,0,evidence.kappa,evidence.phi);initial=K.initial_control(evidence.z_in_force)
    def visit(at,ctrl,path):
        nonlocal expanded,exhausted
        if len(path)==len(evidence.steps):
            if at==target and path[-1].state.cell not in (pre.cell,target.cell):return path
            return None
        for rank,cmd in enumerate(K.option_actions(ctrl.z,ctrl,at)):
            if expanded>=transition_budget:exhausted=True;return None
            expanded+=1;nxt,nctrl=public_advance(at,ctrl,cmd)
            # Known public event order only; no unknown trap or other mask input.
            if nxt.cell==K.GOAL or (nxt.cell==K.CONTESTED and K.hazard_at(nxt.t,nxt.kappa,nxt.phi)):continue
            row=PlannedArrivalRow(at,ctrl,cmd,rank)
            found=visit(nxt,nctrl,path+(row,))
            if found is not None:return found
            if exhausted:return None
        return None
    found=visit(start,initial,())
    proof={'public_candidate_transitions':expanded,'target_inference_transitions':1,'search_exhausted':exhausted,
        'reason':'alternate_entry_found' if found else 'finite_transition_budget_exhausted' if exhausted else 'no_legal_alternate_entry'}
    return (PlannedArrivalProbe(target,pre,last.a_cmd,found) if found else None),proof
