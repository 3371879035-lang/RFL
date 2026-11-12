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
    "STATE_FIELDS",
    "decision_contexts",
    "decision_states",
    "is_decision_context",
    "is_strict_decision_state",
    "is_true_int",
    "n_decision_contexts",
]

#: The automaton-state domain. Both lanes exist and both are reachable.
M_DOMAIN: tuple[int, ...] = (0, 1)

#: The option domain, as the kernel defines it.
Z_DOMAIN: tuple[int, ...] = tuple(K.option_ids())

#: $\kappa$'s domain: the keys of the kernel's frozen hazard schedule.
KAPPA_DOMAIN: tuple[int, ...] = tuple(sorted(K.CONTEXT_PERIODS))

#: The fields of ``State``, in order, all of which are integer-valued.
STATE_FIELDS: tuple[str, ...] = ("x", "y", "t", "kappa", "phi")


def is_true_int(v: object) -> bool:
    r"""$\texttt{type}(v) = \texttt{int}$ — an identity test, not a subclass test.

    ``bool`` is an ``int`` subclass and ``IntEnum`` members are ints, so ``isinstance``
    admits values whose *type* the domain does not have. Worse, Python's numeric equality
    folds them: ``True == 1``, ``1.0 == 1`` and ``False == 0``, with equal hashes, so a
    ``set`` or ``dict`` keyed by the wrong type silently *is* the key it resembles.

    $$\boxed{\text{a set comparison is not a typed comparison}}$$

    This distinction is not pedantry: the whole point of the domain equality in
    :func:`~rfl_rebuild.learner.reference.QReferenceView` is that the reference carries
    exactly the legal contexts, and a folding comparison cannot say that.
    """
    return type(v) is int


def is_strict_decision_state(state: object) -> bool:
    """A ``State`` whose five fields are all true ints.

    ``State`` is a frozen dataclass, so its ``__eq__``/``__hash__`` inherit the numeric
    folding above: ``State(x=1, ...) == State(x=1.0, ...)`` is ``True`` and the hashes
    agree. A float-typed state therefore satisfies a membership test against a legal
    context while not *being* one.
    """
    if type(state) is not State:
        return False
    return all(type(getattr(state, f)) is int for f in STATE_FIELDS)


def non_integer_state_fields(state: object) -> tuple:
    """Which of the five fields are not true ints. For messages, not for control flow."""
    return tuple(f for f in STATE_FIELDS if type(getattr(state, f, None)) is not int)


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
    r"""$\mathcal X_D$ as a set of ``(State, z, m)`` keys, in the reference's own key shape.

    Every member is **strictly typed** — true ``int`` fields and a true ``int`` ``z``/``m``
    — so an equality test against this set is a typed comparison once the other side has
    been typed too.
    """
    return frozenset(
        (state, z, m)
        for state in decision_states()
        for z in Z_DOMAIN
        for m in M_DOMAIN
    )


def n_decision_contexts() -> int:
    return len(decision_contexts())


def is_decision_context(state: object, z: object, m: object) -> bool:
    r"""Strict membership in $\mathcal X_D$: **types first**, then values.

    The order matters and is deliberate. Checking ``z in Z_DOMAIN`` first would accept
    ``True`` and ``1.0``, because the containment test is a value test; requiring
    ``type(z) is int`` first makes the value test mean what it appears to mean.
    """
    if not is_strict_decision_state(state):
        return False
    if not is_true_int(z) or not is_true_int(m):
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
