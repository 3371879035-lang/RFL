r"""B1's plan-operation layer, and the $D_Q$ owner resolver (A78 §66.5).

Put here rather than in :mod:`~rfl_rebuild.b1.laws` so that the slice descriptors can import
the owner resolver without importing the laws: `laws` imports `tier`, so a resolver living
beside the laws would make `tier` import `laws` and close a cycle. The layering is the point
— operations and the rule that owns them on the left, the laws that emit them on the right.

**The substrate is not in this layer.** `learner/store.py::owner_Q` keeps taking a
`QAddress` and must never learn `RestoreRow`; teaching the store about an update law would
trade away the separation Step 3 established. A77 §65.9's equation
$owner_Q(\texttt{RestoreRow}(x_t)) = x_t$ is discharged here, by a resolver that is total
over **both** operation kinds.
"""

from __future__ import annotations

from dataclasses import dataclass

from rfl_rebuild.b1.contract import ProtocolError
from rfl_rebuild.env.domain import is_decision_context
from rfl_rebuild.learner.store import DecisionAddress, owner_Q

__all__ = ["RestoreRow", "dq_owner"]


@dataclass(frozen=True, slots=True)
class RestoreRow:
    r"""$L_3$'s row-scoped **structural operation** (A77 §65.9, A78 §66.5).

    Symbolic, not concrete: it names the credited context whose row returns to
    $Q_D^\ast$, and the slice lowers it — against **one frozen pre-state**, before any
    commit (A78 §66.6) — into the per-entry deletions §65.9 specifies:

    $$\texttt{RestoreRow}(x_t) \longrightarrow \{Q_D^L(x_t,a) \leftarrow \bot\}_{a \in
    A_z(m,s),\ (x_t,a) \in Q_D^L}$$

    The law never sees the pre-state, so it cannot depend on when it is called.

    **The context is closed at construction:**

    $$\boxed{type(\texttt{context}) = \texttt{DecisionAddress}
    \;\land\; \texttt{context} \in \mathcal X_D^{\text{strict}}}$$

    without which the operation would reopen the Step 3 defect one layer up.
    `DecisionAddress` is a plain dataclass and inherits Python's folding, so

    $$\texttt{State}(x{=}1.0), z{=}\texttt{True}, m{=}0.0 \;\equiv\;
    \texttt{State}(x{=}1), z{=}1, m{=}0$$

    with equal hashes — and a value-equal alias inside an *exact* `RestoreRow` would pass
    the plan's context check, the owner resolver's locality check **and** the lowering's row
    match, deleting a legal credited row on behalf of a context that is not a legal context
    at all. Value equality is not typed equality, and this is the layer that has to say so:
    the predicate is Step 3's audited one, reused rather than restated.
    """

    context: DecisionAddress

    def __post_init__(self) -> None:
        if type(self.context) is not DecisionAddress:
            raise ProtocolError(
                f"RestoreRow context is {self.context!r} of type "
                f"{type(self.context).__name__}, not a DecisionAddress")
        if not is_decision_context(self.context.state, self.context.z, self.context.m):
            raise ProtocolError(
                f"RestoreRow context {self.context!r} is not a strictly typed decision "
                "context: its State fields must be true integers in their domains and z, m "
                "true integers inside theirs. Python folds 1.0, True and 1 into one key, so "
                "a value-equal alias would otherwise match a legal credited row in the plan "
                "check, the owner check AND the lowering (A78 §66.5)")


def dq_owner(op) -> DecisionAddress:
    r"""$D_Q$'s owner resolver, total over entry addresses and row operations.

    $$\boxed{owner(\texttt{RestoreRow}(x_t)) = x_t, \qquad owner(Q_D^L(x_t,a)) = x_t}$$

    One resolver for both kinds, so A77 §65.9's locality rule is checked the same way
    whichever operation a law emitted, and the substrate keeps knowing only the store.

    ``type(op) is RestoreRow`` rather than ``isinstance``: `AddressPlan` already refuses a
    subclass at the plan boundary, and the resolver matches that closure so the two cannot
    disagree about what a row operation is.
    """
    if type(op) is RestoreRow:
        return op.context
    return owner_Q(op)
