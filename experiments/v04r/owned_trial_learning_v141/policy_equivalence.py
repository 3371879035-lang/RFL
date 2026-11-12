"""A unit deletion may change storage without changing the current policy.

This is NOT a claim about after-episode learning state or future trajectories.
The caller measures keep and every candidate not proved equal to keep.
"""
from dataclasses import dataclass
from rfl_rebuild.env.kernel import ControlState
from rfl_rebuild.learner.store import Q, DECISION, QAddress, DecisionAddress


@dataclass(frozen=True)
class KeepPolicyComparison:
    action: str
    supported: bool
    affected: object
    edit: object
    row_before: tuple
    row_after: tuple
    literal_before: object
    before_action: object
    after_action: object
    equivalent_to_keep: bool
    reason: str


def compare_to_keep(loop,proposal,action):
    if proposal.action!='apply' or len(proposal.edits)!=1:
        return KeepPolicyComparison(action,False,None,None,(),(),None,None,None,False,'not-unit-delete')
    edit=proposal.edits[0]
    if edit.value is not None or edit.store!=(Q if loop.mode=='dq' else DECISION):
        return KeepPolicyComparison(action,False,None,edit,(),(),None,None,None,False,'not-unit-Q-D-delete')
    address=edit.address
    owner=DecisionAddress(address.state,address.z,address.m)
    actor=loop._current.snapshot()
    numeric=loop._current if loop.mode=='dq' else loop._values
    values=numeric.snapshot().q_overrides
    reference=loop.reference.row(owner.state,owner.z,owner.m)
    row={a:values.get(QAddress(owner.state,owner.z,owner.m,a),v) for a,v in reference.items()}
    updated=dict(row)
    if edit.store==Q:
        updated[address.a]=reference[address.a]
    literal=actor.decision_overrides.get(owner) if loop.mode=='patch-adaptive' else None
    before=literal if literal is not None else min(row,key=lambda a:(-row[a],a))
    after=min(updated,key=lambda a:(-updated[a],a))
    assert before==loop._greedy()(owner.state,ControlState(owner.z,owner.m))
    equal=before==after
    return KeepPolicyComparison(action,True,owner,edit,tuple(sorted(row.items())),
                                tuple(sorted(updated.items())),literal,before,after,equal,
                                'same-at-only-modified-context' if equal else 'different-at-modified-context')
