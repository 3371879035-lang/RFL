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
from rfl_rebuild.b1.plan import dq_owner
from rfl_rebuild.learner.store import (
    DECISION,
    Q,
    DecisionAddress,
    LearnerPersistentState,
    owner_Q,
)

__all__ = [
    "DQ_SLICE",
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

    **Truthiness is refused, not merely discouraged** (§65.1's "no truthiness
    inference"). ``type(tier) is Tier`` stops another *value* posing as a tier; it does
    not stop ``if tier:`` collapsing all four members into one branch, because every
    enum member is truthy by default. Raising here turns that into a fail-stop rather
    than a silent wrong branch:

    $$\boxed{\texttt{bool(Tier.x)}\ \Longrightarrow\ \texttt{PROTOCOL\_ERROR}}$$
    """

    L0_FACTUAL = "L0_factual"
    L1_CORRECTIVE = "L1_corrective"
    L2_COUNTERFACTUAL = "L2_counterfactual"
    L3_ORACLE = "L3_oracle"

    def __bool__(self) -> bool:                      # pragma: no cover - always raises
        raise ProtocolError(
            f"Tier is opaque (A77 §65.1): {self.name} has no truth value; test identity "
            "with `is`, and dispatch on the cell, never on truthiness")


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

    **Two questions, deliberately kept apart.**

    ``cells`` answers the *semantic* one and is A77 §65.2 verbatim: what field set does
    this cell carry, or is it ill-typed? It never records build progress, so enabling a
    cell later is an implementation change rather than a rewrite of what ``fields()``
    means.

    ``implemented_tiers`` answers the *build* one: which of those cells this revision can
    actually run? A tier may be semantically real and not yet implemented — $D_Q\times L_2$
    and $D_Q\times L_3$ are exactly that today, because their content ($G_t^{CF}$; the row
    restore) is not authorised yet — and a tier may never be implemented because it is
    ill-typed ($D_Q\times L_1$).

    An earlier revision conflated the two by putting a ``DEFERRED`` sentinel *inside*
    ``cells``, which made ``fields(D_Q, L2)`` raise "not built in this revision". That
    answered a build question with a semantic table and would have forced the next step to
    redefine ``fields()`` while implementing the counterfactual — the two questions
    colliding exactly when clarity matters most.

    ``extract`` maps a declared field name to the function that reads it from the
    evaluator-side record, so delivery is a projection over *declared* names and a record
    that grows a field cannot silently widen what a law sees.

    **The descriptor validates and freezes itself.** ``@dataclass(frozen=True)`` freezes
    the *attribute binding*, not the dicts behind it, and it validates nothing, so an
    earlier version allowed both of these:

    * ``cells[L1] = {"alternative"}`` with ``extract = {}`` — accepted at construction,
      then ``deliver`` raised a bare ``KeyError: alternative`` from inside the read path
      instead of the ``PROTOCOL_ERROR`` the contract promises. The same "the error path
      crashes first" defect this project keeps finding;
    * ``PATCH_SLICE.cells[Tier.L0_FACTUAL] = frozenset({"anything"})`` — the frozen
      information contract could be edited in place at runtime, which is precisely what
      making the cell table executable was supposed to prevent.

    So construction is the contract boundary:

    $$\boxed{\operatorname{keys}(\texttt{cells}) = \texttt{Tier}}$$

    every value is either :data:`ILL_TYPED` or a ``frozenset[str]``;
    ``implemented_tiers \subseteq keys(cells)``; an implemented tier must be a real field
    set (an ill-typed cell can never be implemented); and

    $$\boxed{\bigcup_{\ell\ \text{implemented}} \text{fields}(\alpha,\ell) \subseteq
    \operatorname{keys}(\texttt{extract})}$$

    — conditioned on implementation, because a field that cannot be delivered yet does not
    need an extractor yet, while a *typo* in a delivered cell's field name still does.
    """

    name: str
    store: str
    scalar: bool
    owner: Callable[[Any], DecisionAddress]
    view: Callable[[LearnerPersistentState], dict]
    cells: Mapping[Tier, Any]
    extract: Mapping[str, Callable[[Any], Any]]
    implemented_tiers: frozenset | None = None

    def __post_init__(self) -> None:
        if self.implemented_tiers is None:
            # The default is the complete-build case: every cell that declares a field set
            # is implemented. It is a *safe* default rather than a convenient one, because
            # the extractor rule below is conditioned on implementation -- claiming a cell
            # implemented without extractors for its fields fails at construction. A
            # mid-build architecture narrows this explicitly, which is what D_Q does.
            object.__setattr__(
                self, "implemented_tiers",
                frozenset(t for t, c in self.cells.items() if c is not ILL_TYPED))
        object.__setattr__(self, "implemented_tiers", frozenset(self.implemented_tiers))
        if type(self.scalar) is not bool:
            raise ProtocolError(
                f"{self.name}: scalar={self.scalar!r} is not a bool; whether a store is "
                "scalar-valued decides the ledger's accounting domain, so it may not be "
                "coerced or inferred")
        for attr in ("owner", "view"):
            if not callable(getattr(self, attr)):
                raise ProtocolError(f"{self.name}: {attr} must be callable")
        if set(self.cells) != set(Tier):
            missing = sorted(t.name for t in set(Tier) - set(self.cells))
            extra = sorted(repr(k) for k in set(self.cells) - set(Tier))
            raise ProtocolError(
                f"{self.name}: the cell table must declare every tier; missing {missing}, "
                f"unknown {extra}. An undeclared cell would be discovered only when a "
                "law first ran in it")
        unknown = sorted(repr(t) for t in self.implemented_tiers
                         if type(t) is not Tier)
        if unknown:
            # Checked BEFORE any `.name` access: Tier is a closed opaque enum, so a
            # non-member in the build set is a malformed descriptor and must not surface
            # as an AttributeError from inside the validation that exists to catch it.
            raise ProtocolError(
                f"{self.name}: implemented_tiers contains {unknown}, which are not Tier "
                "members; the tier namespace is closed (A77 §65.1)")
        unbuilt = sorted(t.name for t in self.implemented_tiers if t not in self.cells)
        if unbuilt:
            raise ProtocolError(
                f"{self.name}: implemented tier(s) {unbuilt} have no declared cell; "
                "implementation state cannot outrun the semantics it implements")
        for tier in sorted(self.implemented_tiers, key=lambda t: t.name):
            if self.cells[tier] is ILL_TYPED:
                raise ProtocolError(
                    f"{self.name}: tier {tier.name} is marked implemented but its cell is "
                    "ill-typed; an architecture cannot implement a cell A77 says has no "
                    "substantive treatment")
        declared: set = set()
        for tier, cell in self.cells.items():
            if cell is ILL_TYPED:
                continue
            if not isinstance(cell, frozenset) or not all(
                    isinstance(f, str) for f in cell):
                raise ProtocolError(
                    f"{self.name}: cell {tier.name} is {cell!r}; a well-typed cell must "
                    "be a frozenset of field names (or ILL_TYPED)")
            if tier in self.implemented_tiers:
                declared |= set(cell)
        missing_extractors = sorted(declared - set(self.extract))
        if missing_extractors:
            raise ProtocolError(
                f"{self.name}: cell field(s) {missing_extractors} have no extractor; the "
                "failure would otherwise surface as a KeyError inside delivery, not as a "
                "protocol error at the contract boundary")
        for field_name, extractor in self.extract.items():
            if not callable(extractor):
                raise ProtocolError(
                    f"{self.name}: extractor for {field_name!r} is not callable")
        # Freeze the contents, not just the binding.
        object.__setattr__(self, "cells", MappingProxyType(dict(self.cells)))
        object.__setattr__(self, "extract", MappingProxyType(dict(self.extract)))

    def fields(self, tier: Tier) -> frozenset:
        r"""``fields(α, ℓ)``, or a ``PROTOCOL_ERROR`` for a cell a law may not use."""
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

    def require_implemented(self, tier: Tier) -> None:
        """Fail stop when a **semantically real** cell is not built in this revision.

        Kept separate from :meth:`fields` on purpose: ``fields`` answers what the cell
        *is*, this answers whether the run may use it. $D_Q\\times L_2$ is the live case —
        its field set is frozen and it has no implementation yet.
        """
        if tier not in self.implemented_tiers:
            raise ProtocolError(
                f"{self.name} at tier {tier.name} is declared by A77 §65.2 but not built "
                "in this revision; the cell is not ill-typed, it is unimplemented, and a "
                "law may not be declared in it until its fields can be delivered")

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


def _q_view(state: LearnerPersistentState) -> dict:
    return dict(state.q_overrides)


#: The $D_Q$ row of A77 §65.2's table **verbatim**, plus this revision's build state.
#:
#: ``cells`` is the frozen semantics and nothing else:
#:
#: * $L_0 = \{a_t^F, G_t^F\}$ — the factual action and its suffix return. No $a_t^+$, no
#:   $G_t^{CF}$: the cell *is* the information boundary, and widening it "because the
#:   builder could compute more" is the leak the boundary exists to prevent;
#: * $L_1$ is **ill-typed**, permanently: it supplies $a^+$ without its value, and on a
#:   scalar store every write is a value (A76 §63.5, §65.2);
#: * $L_2 = \{a_t^F, G_t^F, a_t^+, G_t^{CF}\}$ and $L_3 = \varnothing$, exactly as §65.2
#:   writes them.
#:
#: ``implemented_tiers`` is the build state: $L_0$, $L_2$ and $L_3$ all run. Enabling a cell
#: is an implementation change — flip one set and supply its extractors — rather than a
#: redefinition of what ``fields()`` means. That distinction is why the ``DEFERRED`` sentinel
#: was removed from ``cells``, and it has now paid twice: $L_2$ needed the table already
#: correct, and $L_3$ needed it correct *and* empty.
#:
#: ``owner=dq_owner`` rather than the substrate's ``owner_Q``: $L_3$'s row operation is a B1
#: object, and A78 §66.5 requires the resolver to be total over entry addresses and row
#: operations while `learner/store.py::owner_Q` keeps taking a `QAddress`.
DQ_SLICE = SliceDescriptor(
    name="D_Q",
    store=Q,
    scalar=True,
    owner=dq_owner,
    view=_q_view,
    cells={
        Tier.L0_FACTUAL: frozenset({"a_factual", "g_factual"}),
        Tier.L1_CORRECTIVE: ILL_TYPED,
        Tier.L2_COUNTERFACTUAL: frozenset({"a_factual", "g_factual", "a_plus",
                                           "g_cf"}),
        Tier.L3_ORACLE: frozenset(),
    },
    extract={
        "a_factual": lambda record: record.a_factual,
        "g_factual": lambda record: record.g_factual,
        "a_plus": lambda record: record.a_plus,
        "g_cf": lambda record: record.g_cf,
    },
    implemented_tiers=frozenset({Tier.L0_FACTUAL, Tier.L2_COUNTERFACTUAL,
                                 Tier.L3_ORACLE}),
)


def _patch_view(state: LearnerPersistentState) -> dict:
    return dict(state.decision_overrides)


#: The $D_{patch}$ row of A77 §65.2's table, and nothing else.
#:
#: $L_2$ is **ill-typed** here: every value target is ill-typed on a value-free store
#: (A76 §63.6). $L_3$ delivers $\varnothing$ because on this architecture the healthy
#: referent *is* "no override", so the restore is a deletion and needs no content.
#:
#: Every well-typed cell of this architecture is implemented, so this slice's build state
#: is complete and the two questions coincide here — which is why the separation was
#: invisible until $D_Q$ arrived.
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
    implemented_tiers=frozenset({Tier.L0_FACTUAL, Tier.L1_CORRECTIVE, Tier.L3_ORACLE}),
)
