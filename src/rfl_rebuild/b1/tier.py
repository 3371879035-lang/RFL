r"""A77 §65.1–§65.2 — the information contract: tiers, cells and exact delivery.

This module is the **structure** A77 froze, introduced here for the architecture that
already exists. It contains no $D_Q$ object: no ``QAddress``, no store, no target value.
The $D_Q$ row is added in a later step, as A77 §65.12 requires.

Three things live here and nowhere else.

**The tier is a closed opaque enum** (§65.1). Declared exactly once per law, with ``None``
as the NOT-DECLARED sentinel and an identity test, so an ``int`` or a ``bool`` cannot pass
for a tier:

$$\boxed{\texttt{type(tier) is Tier}}$$

**Delivery is a property of the cell** ``(architecture, tier)``, not of the law (§65.2):

$$\boxed{\text{fields}(\alpha,\ell) = \text{the complete field set handed to every law in
that cell}}$$

and a cell may be **ill-typed**, meaning no substantive treatment exists in it. Declaring
such a cell is a ``PROTOCOL_ERROR``, which is how §65.2's table becomes executable rather
than advisory: on a value-free architecture $L_2$ is ill-typed, and on a scalar one $L_1$
is — the second is the rule that keeps `PositiveAlternative` retired.

**The delivered object is derived from the declared field set, never from the record.**
A law therefore cannot receive a field its cell excludes, and a cell with
$\text{fields} = \varnothing$ delivers **no object at all** rather than an empty one. The
projection is deliberately narrower than the evaluator-side record: `TargetRecord` also
carries ``factual_command``, which exists for validation and is not delivered content
($a^+\neq a^F$ is the validator's question, not the law's).

That last point is the honest statement of what "exact delivery" means here. Equality
between the delivered keys and ``fields(α,ℓ)`` holds **by construction**, because the
projection is built *from* the declared set; asserting it at runtime would be a check that
cannot fail. What is therefore gated instead is what can fail: that the projection does
not leak an undeclared field, that an empty cell delivers nothing, and that an ill-typed
cell is rejected before a law runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Callable, Mapping

from rfl_rebuild.b1.contract import ProtocolError
from rfl_rebuild.learner.store import DECISION, DecisionAddress, LearnerPersistentState

__all__ = [
    "ILL_TYPED",
    "PATCH_SLICE",
    "SliceDescriptor",
    "Tier",
]


class Tier(Enum):
    r"""The four information tiers of A76 §63.1, opaque and unordered.

    An ``Enum`` and deliberately not an ``IntEnum``: nothing in the design compares
    tiers numerically, and an integer-valued member would let ``0``, ``True`` and ``1``
    all pass for $L_0$ — the same class of accident the boolean flag produced.
    """

    L0_FACTUAL = "L0_factual"
    L1_CORRECTIVE = "L1_corrective"
    L2_COUNTERFACTUAL = "L2_counterfactual"
    L3_ORACLE = "L3_oracle"


class _IllTyped:
    """A cell with no substantive compatible treatment. Not a field set."""

    __slots__ = ()

    def __repr__(self) -> str:                       # pragma: no cover - diagnostics
        return "<ill-typed cell>"


#: Declaring a law in an ill-typed cell is a protocol error (§65.2, §65.3).
ILL_TYPED = _IllTyped()


@dataclass(frozen=True)
class SliceDescriptor:
    r"""One architecture's store slice: what it writes, and what each cell delivers.

    ``cells`` maps a tier to either a field set or :data:`ILL_TYPED`. ``extract`` maps a
    declared field name to the function that reads it from the evaluator-side record, so
    the delivery is a projection over *declared* names and a record that grows a field
    cannot silently widen what a law sees.
    """

    name: str
    store: str
    scalar: bool
    owner: Callable[[Any], DecisionAddress]
    view: Callable[[LearnerPersistentState], dict]
    cells: Mapping[Tier, Any]
    extract: Mapping[str, Callable[[Any], Any]]

    def fields(self, tier: Tier) -> frozenset:
        r"""``fields(α, ℓ)``, or a ``PROTOCOL_ERROR`` for an ill-typed cell."""
        cell = self.cells.get(tier)
        if cell is None:
            raise ProtocolError(
                f"{self.name} declares no cell for tier {tier!r}; every tier the "
                "architecture supports must be declared, ill-typed included")
        if cell is ILL_TYPED:
            raise ProtocolError(
                f"{self.name} has no substantive treatment at tier {tier!r}: the cell is "
                "ill-typed, so a law may not be declared in it (A77 §65.2)")
        return cell

    def deliver(self, tier: Tier, addresses, envelope):
        r"""Project the envelope onto exactly ``fields(α, ℓ)``.

        An empty cell returns ``None``: a law that needs nothing is handed nothing, not
        an empty container. A cell that declares fields and is handed no envelope is a
        ``PROTOCOL_ERROR`` — the caller was supposed to build one.
        """
        declared = self.fields(tier)
        if not declared:
            return None
        if envelope is None:
            raise ProtocolError(
                f"{self.name} at tier {tier!r} declares fields {sorted(declared)} but no "
                "envelope was supplied; the runner must build the cell's fields before "
                "any law in it runs")
        rows = {}
        for a in addresses:
            rows[a] = MappingProxyType({f: self.extract[f](envelope[a])
                                        for f in sorted(declared)})
        return MappingProxyType(rows)


def _patch_view(state: LearnerPersistentState) -> dict:
    return dict(state.decision_overrides)


#: The $D_{patch}$ row of A77 §65.2's table, and nothing else.
#:
#: $L_2$ is **ill-typed** here: every value target is ill-typed on a value-free store
#: (A76 §63.6). $L_3$ delivers $\varnothing$ because on this architecture the healthy
#: referent *is* "no override", so the restore is a deletion and needs no content.
PATCH_SLICE = SliceDescriptor(
    name="D_patch",
    store=DECISION,
    scalar=False,
    owner=lambda address: address,                 # owner_patch = identity
    view=_patch_view,
    cells={
        Tier.L0_FACTUAL: frozenset(),
        Tier.L1_CORRECTIVE: frozenset({"alternative"}),
        Tier.L2_COUNTERFACTUAL: ILL_TYPED,
        Tier.L3_ORACLE: frozenset(),
    },
    extract={"alternative": lambda record: record.alternative},
)
