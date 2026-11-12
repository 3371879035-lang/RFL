"""Isolated C1 proposal; never imported by the rev-4 production initializer.

See docs/rebuild/22-F0-INITIALIZER-CANDIDATE.md. A87 remains unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass

from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b2.initializer import canary_address
from rfl_rebuild.env.kernel import ControlState
from rfl_rebuild.learner.store import Edit, Q, QAddress, LearnerPersistentState


@dataclass(frozen=True)
class OptimisticFixture:
    address: QAddress
    initial_value: float
    target_value: float
    best_value: float
    healthy_action: int

    def initialize(self, *, q_reference):
        learner = LearnerPersistentState()
        learner.apply_transaction((Edit(Q, self.address, self.initial_value),),
                                  q_reference=q_reference)
        return learner

    def action(self, learner, *, q_reference):
        a = self.address
        return learner.snapshot().q_decision_provider(q_reference)(
            a.state, ControlState(z=a.z, m=a.m))

    def policy_restored(self, learner, *, q_reference):
        return self.action(learner, q_reference=q_reference) == self.healthy_action


def optimistic_fixture(*, q_reference) -> OptimisticFixture:
    witness = canary_address()
    row = q_reference.rows[(witness.state, witness.z, witness.m)]
    best = max(row.values())
    suboptimal = sorted(a for a, value in row.items() if value < best)
    if not suboptimal:
        raise ProtocolError("C1 requires a strict suboptimal action at the frozen context")
    action = suboptimal[0]
    target = row[action]
    initial = best + (best - target)
    if not initial > best:
        raise ProtocolError("C1's positive gap must be representable")
    healthy = LearnerPersistentState().snapshot().q_decision_provider(q_reference)(
        witness.state, ControlState(z=witness.z, m=witness.m))
    return OptimisticFixture(QAddress(witness.state, witness.z, witness.m, action),
                             initial, target, best, healthy)
