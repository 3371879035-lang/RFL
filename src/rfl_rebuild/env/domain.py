r"""The frozen decision-context domain $\mathcal X_D$ — enumerated **once**, shared.

$$\boxed{\mathcal X_D = \{(s,z,m) : s \in S_{\text{decision}},\ z \in Z,\ m \in \{0,1\}\}}$$

This module exists because A77 §65.5 states the reference domain as an **equality**, not
as a property of whichever rows a caller happened to supply:

$$\operatorname{dom}(\texttt{QReferenceView}) = \{(x,a) : x \text{ a legal decision
context},\ a \in A_z(m,s)\}$$

Proving that needs an *independent* enumerator of the legal contexts. Before this module
the only enumerator was ``solve/dp.py``'s, so the reference's domain check would have had
to import the solver — and a contract validated by the same code that produces the object
being validated is not validated. It is also why the learner package must not reach for
``solve_reference()``: the domain of a legal context is a property of the **environment**,
not of a particular solve.

So the enumeration lives here, in ``env/``, and both sides use it:

* ``solve/dp.py`` iterates these states to run backward induction;
* ``learner/reference.py`` compares the reference's keys against them.

They are the same list by construction, which is the point: a mismatch would otherwise be
a silent disagreement about which contexts exist, discoverable only as a missing
``KeyError`` deep in a rollout.
"""

from __future__ import annotations

from typing import Iterator

from rfl_rebuild.env import kernel as K
from rfl_rebuild.env.kernel import State

__all__ = [
    "M_DOMAIN",
    "decision_contexts",
    "decision_states",
    "is_decision_context",
    "n_decision_contexts",
]

#: The automaton-state domain. Both lanes exist and both are reachable.
M_DOMAIN: tuple[int, ...] = (0, 1)

#: The option domain, as the kernel defines it.
Z_DOMAIN: tuple[int, ...] = tuple(K.option_ids())

#: $\kappa$'s domain: the keys of the kernel's frozen hazard schedule.
KAPPA_DOMAIN: tuple[int, ...] = tuple(sorted(K.CONTEXT_PERIODS))


def decision_states() -> Iterator[State]:
    """Every reachable **decision** state: open cell, ``t in [0, H)``, both lanes, every phase.

    ``GOAL`` is excluded: arriving there is terminal, so it is never a decision point, and
    $A_{z_1}$ would be empty there (no action strictly decreases a distance of zero).
    """
    for x in range(K.N_COLS):
        for y in range(K.N_ROWS):
            if (x, y) not in K.OPEN_CELLS or (x, y) == K.GOAL:
                continue
            for t in range(K.HORIZON):
                for kappa in KAPPA_DOMAIN:
                    for phi in K.PHASE_DOMAIN:
                        yield State(x=x, y=y, t=t, kappa=kappa, phi=phi)


def decision_contexts() -> frozenset:
    r"""$\mathcal X_D$ as a set of ``(State, z, m)`` keys, in the reference's own key shape."""
    return frozenset(
        (state, z, m)
        for state in decision_states()
        for z in Z_DOMAIN
        for m in M_DOMAIN
    )


def n_decision_contexts() -> int:
    return len(decision_contexts())


def is_decision_context(state: State, z: object, m: object) -> bool:
    """Membership without materialising the set, for a single hostile lookup."""
    if not isinstance(state, State):
        return False
    if z not in Z_DOMAIN or m not in M_DOMAIN:
        return False
    if (state.x, state.y) not in K.OPEN_CELLS or (state.x, state.y) == K.GOAL:
        return False
    if not (0 <= state.t < K.HORIZON):
        return False
    if state.kappa not in KAPPA_DOMAIN:
        return False
    return state.phi in K.PHASE_DOMAIN
