"""The single learner-visible observation model.

`walk_transition` and the row tuple used to live inside ``scripts/gate_stage2.py``,
which is evaluator-side code. The method side needs the *same* timeline and the
*same* rows -- ``PublicSCMView`` must forward-simulate a hypothetical world and
report what a learner would have seen -- and copying them would have created a
second implementation of the observation model, precisely the defect route C
removed for the fault grammar.

The row tuple **is** the definition of the learner-visible factual evidence
``X^loc``, so it belongs in ``src``, with ``gate_stage2`` importing it rather than
owning it.

Public: A72 §8.2 explicitly allows the public kernel transition and event order.

What this module does NOT do: it reads no tape nuisance, no DGP weight, no support
identity and no truth. It turns a rollout into observations.
"""

from __future__ import annotations

from typing import Any, Iterator

from rfl_rebuild.env import kernel as K
from rfl_rebuild.env.kernel import State

__all__ = ["ROW_SCHEMA", "learner_rows", "walk_transition"]

#: The learner-visible row, in order. Frozen: it defines ``X^loc``.
ROW_SCHEMA: tuple[str, ...] = (
    "x", "y", "t", "kappa", "phi", "z", "m", "a_cmd", "a_realized", "reward",
)


def walk_transition(trace: Any, kappa: int, phi: int, z_in_force: int) -> Iterator[tuple]:
    """Yield ``(s_pre, z, m, a_cmd, a_realized, reward)`` per step.

    ``StepResult.state`` is the state *after* the move, so pairing it with the
    pre-action control state produced a mixed timeline (the A45–A49 correction).
    One helper, used by both the signature and the query family, is the only way to
    keep them aligned.
    """
    state = State(x=K.START[0], y=K.START[1], t=0, kappa=kappa, phi=phi)
    ctrl = K.initial_control(z_in_force)
    for res in trace.steps:
        yield state, ctrl.z, ctrl.m, res.a_cmd, res.a_realized, res.reward
        state, ctrl = res.state, res.control


def learner_rows(trace: Any, kappa: int, phi: int) -> tuple:
    """``I^factual``'s first half: what the learner sees, per step.

    ``z`` here is ``z^in-force``, not the proposal -- the process/commit layer is
    part of the mechanism (A55), so the proposal is latent and must be enumerated
    rather than read off the evidence.
    """
    z_in_force = trace.option_in_force
    return tuple(
        (s.x, s.y, s.t, s.kappa, s.phi, z, m, a_cmd, a_realized, round(r, 6))
        for (s, z, m, a_cmd, a_realized, r)
        in walk_transition(trace, kappa, phi, z_in_force)
    )
