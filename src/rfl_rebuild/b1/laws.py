r"""A76 §63.9 — the $D_{patch}$ row of the compatibility matrix.

Four registered arms, **three independent treatments**:

| arm | kind |
|---|---|
| `NoWrite` | reference |
| `DeleteFactualPatch` | independent operation ($L_0$) |
| `SetAlternative` | independent operation ($L_1$) |
| `LocalOracleRestore` | $L_3$ **alias of `DeleteFactualPatch`** |

$$\boxed{\texttt{LocalOracleRestore} \equiv \texttt{DeleteFactualPatch}
\quad\text{on } D_{patch}}$$

so it is registered as an alias and not implemented a second time: it must produce the
same transaction, the same post-state, the same per-address statuses and the same
ledger cost. If any of those differ, that is an implementation bug and the alias test
catches it.

A law plans against a **pre-update snapshot** and returns
:class:`PlannedWrite` entries. It never touches the store, never computes a status that
depends on the post-state, and never receives $T/P$, $S_{r,\pm}$, $\Gamma^\ast$,
a world id or a block id.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from rfl_rebuild.b1.contract import NO_VALID_ALTERNATIVE
from rfl_rebuild.b1.targets import TargetRecord
from rfl_rebuild.learner.store import DECISION, DecisionAddress, Edit

__all__ = [
    "LAWS",
    "DeleteFactualPatch",
    "LawPlan",
    "LocalOracleRestore",
    "NoWrite",
    "PlannedWrite",
    "SetAlternative",
    "independent_treatment_count",
    "law_metadata",
]


@dataclass(frozen=True, slots=True)
class PlannedWrite:
    """One address's planned outcome.

    Exactly one of three shapes is legal:

    | ``edit`` | ``status`` | meaning |
    |---|---|---|
    | not ``None`` | ``None`` | a normal candidate write |
    | ``None`` | ``None`` | an ordinary ``EVALUABLE_NOOP`` |
    | ``None`` | ``NO_VALID_ALTERNATIVE`` | a legitimate absence of a target |

    Anything else is a :class:`ProtocolError`. The first version of this docstring said
    "never both, never neither", which ``NoWrite`` contradicted in the very same
    commit — it legitimately plans ``edit=None, status=None``.
    """

    address: DecisionAddress
    edit: Edit | None
    status: str | None


@dataclass(frozen=True, slots=True)
class LawPlan:
    """A law's whole plan for one scene. The runner commits it in ONE transaction."""

    name: str
    writes: tuple[PlannedWrite, ...]

    @property
    def edits(self) -> tuple[Edit, ...]:
        return tuple(w.edit for w in self.writes if w.edit is not None)


class _Law:
    """Base class. Subclasses implement ``plan`` and never see the store itself.

    ``requires_alternative`` is the **information tier** (A76 §63.1). A law that does
    not set it is never handed the target envelope at all — not merely expected not to
    read it:

    $$\\boxed{L_0\\text{ law must not depend on, nor be delivered, }L_1\\text{
    corrective content}}$$

    Handing ``targets`` to ``NoWrite`` and trusting it not to look would repeat A59's
    lesson: *the method did not read the higher-tier information* does not imply *the
    runner did not first condition it on that information*. It would also let a broken
    target generator fail an $L_0$ arm that has no business needing a target.
    """

    name = "?"
    alias_of: str | None = None
    requires_alternative: bool = False

    def plan(self, addresses: Sequence[DecisionAddress],
             targets: "Mapping[DecisionAddress, TargetRecord] | None",
             snapshot) -> LawPlan:            # pragma: no cover - abstract
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"<law {self.name}>"


class NoWrite(_Law):
    r"""Propose nothing. Every credited address is ``EVALUABLE_NOOP``.

    Not ``APPLIED``: the law ran and correctly changed nothing, which is a different
    statement from a write having been committed. Requires no target.
    """

    name = "NoWrite"
    requires_alternative = False

    def plan(self, addresses, targets, snapshot) -> LawPlan:
        return LawPlan(self.name,
                       tuple(PlannedWrite(a, None, None) for a in addresses))


class DeleteFactualPatch(_Law):
    r"""$L_0$: delete the factual patch at each credited address.

    A **total** operation. Where a patch exists the transaction changes the store
    (``APPLIED``); where none exists it is a no-op (``EVALUABLE_NOOP``), never an
    evaluability failure — in regime T every address is patchless, so treating that as
    a failure would selectively exclude the whole regime.
    """

    name = "DeleteFactualPatch"
    requires_alternative = False

    def plan(self, addresses, targets, snapshot) -> LawPlan:
        return LawPlan(
            self.name,
            tuple(PlannedWrite(a, Edit(DECISION, a, None), None) for a in addresses),
        )


class SetAlternative(_Law):
    r"""$L_1$: write the verified alternative $a^+$ at each credited address.

    * a valid $a^+$ exists → plan the write; if the patch already holds exactly
      $a^+$ the transaction leaves the store unchanged and the status is
      ``EVALUABLE_NOOP``, derived from the store rather than special-cased here;
    * a **verified** absence of $a^+$ → no edit, status ``NO_VALID_ALTERNATIVE``, and
      the other addresses are unaffected;
    * a **missing** target record is not handled here at all — the runner raises
      :class:`ProtocolError` before any law runs.
    """

    name = "SetAlternative"
    requires_alternative = True

    def plan(self, addresses, targets, snapshot) -> LawPlan:
        writes = []
        for a in addresses:
            rec = targets[a]
            if rec.alternative is None:
                writes.append(PlannedWrite(a, None, NO_VALID_ALTERNATIVE))
            else:
                writes.append(PlannedWrite(a, Edit(DECISION, a, rec.alternative),
                                           None))
        return LawPlan(self.name, tuple(writes))


class LocalOracleRestore(DeleteFactualPatch):
    r"""$L_3$ on $D_{patch}$ — an **alias** of :class:`DeleteFactualPatch`.

    Implemented by *inheritance*, not by a second ``plan``: the operation exists once
    and this class only carries the alias metadata. The earlier version wrote
    ``LocalOracleRestore = DeleteFactualPatch`` and then set ``.name`` on it, which
    mutated the shared class — ``DeleteFactualPatch`` lost its own name, the registry
    contained ``LocalOracleRestore`` twice, and the independent-treatment count came
    out as 2. The alias test asserts ``plan`` is the *same function object*.
    """

    name = "LocalOracleRestore"
    alias_of = "DeleteFactualPatch"
    requires_alternative = False


#: Registration order is fixed so arm enumeration is deterministic.
LAWS = (NoWrite, DeleteFactualPatch, SetAlternative, LocalOracleRestore)


def law_metadata() -> tuple:
    """``(name, kind, alias_of)`` per registered arm.

    ``kind`` is one of ``reference`` / ``operation`` / ``alias``.
    """
    out = []
    for law in LAWS:
        if law.alias_of:
            out.append((law.name, "alias", law.alias_of))
        elif law.name == "NoWrite":
            out.append((law.name, "reference", None))
        else:
            out.append((law.name, "operation", None))
    return tuple(out)


def independent_treatment_count() -> int:
    """**Three**, not four: ``NoWrite`` + ``DeleteFactualPatch`` + ``SetAlternative``.

    ``LocalOracleRestore`` is an alias on this architecture and must not be counted,
    nor executed as a fourth arm and reported twice.
    """
    return sum(1 for _n, kind, _a in law_metadata() if kind != "alias")
