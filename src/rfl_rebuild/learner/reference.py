r"""A77 §65.4, §65.5 — the injected, frozen, read-only reference view.

$Q_D^L$ is a *sparse override* on the architecture's reference table, so every read of
$Q^{\text{eff}}$ needs $Q_D^\ast$ for the entries the store does not carry, and the
transaction boundary needs it to decide both domain membership and identity
canonicalisation. That reference enters as **one frozen object passed in by the
caller**:

$$\boxed{\texttt{QReferenceView}\text{ is injected; no store or runner code calls }
\texttt{solve\_reference()}}$$

A store that fetched its own reference would make the persistent state depend on a
global the experiment is supposed to control, and would hide which source tree produced
the numbers. This module therefore does not import the solver either: it validates a
plain mapping, and :func:`reference_view_from` accepts any object exposing ``.q``.

**Validation is at construction, and it is total.** A77 §65.5's domain is

$$\operatorname{dom}(\texttt{QReferenceView}) = \{(x,a) : x \text{ a legal decision
context},\ a \in A_z(m,s)\}$$

and the view checks exactly that for **every** row rather than trusting the solver's
shape. The check is not vacuous book-keeping: it is what lets every later read be a
plain lookup, and it is the reason an incomplete reference surfaces as a
:class:`~rfl_rebuild.learner.store.ReferenceContractError` at the boundary instead of a
``KeyError`` from inside a rollout. The measured fact that the frozen solver *is* total
(13,824 rows, 0 partial, 0 inadmissible extras) is what makes this an assertion about
this build rather than a hope about all builds — and it is re-measured by a gate, not
assumed here.

Values are stored as :class:`float` and must be finite. ``bool`` is refused: it is an
``int`` subclass, so ``True`` would otherwise pass for the value ``1.0`` and the
fingerprint would carry a type the value domain does not have.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from rfl_rebuild.env.domain import (
    decision_contexts,
    is_decision_context,
    is_strict_decision_state,
    is_true_int,
    non_integer_state_fields,
)
from rfl_rebuild.env.kernel import ControlState, State, option_actions
from rfl_rebuild.learner.store import (
    QAddress,
    ReferenceContractError,
)

__all__ = ["QReferenceView", "reference_view_from"]


def _is_finite_real(v: object) -> bool:
    """A real number that is neither ``bool`` nor non-finite."""
    return (isinstance(v, (int, float)) and not isinstance(v, bool)
            and math.isfinite(v))


@dataclass(frozen=True)
class QReferenceView:
    r"""The architecture's reference $Q_D^\ast$, frozen and total on its domain.

    Construct with a mapping ``{(State, z, m): {action: value}}``; use
    :func:`reference_view_from` for a solver object. The constructor is the contract
    boundary:

    * every key is a legal decision context, and every row's actions are **exactly**
      $A_z(m,s)$ — no partial row, no inadmissible action;
    * every value is a finite real, stored as ``float``;
    * the rows are rebound as read-only mappings, so a view cannot be edited after it
      has been handed to a store.
    """

    name: str
    rows: Mapping[Any, Mapping[int, float]]

    def __init__(self, rows: Mapping, *, name: str = "reference") -> None:
        if not isinstance(rows, Mapping):
            raise ReferenceContractError(
                f"the reference must be a mapping of (State, z, m) rows, got "
                f"{type(rows).__name__}")
        if not rows:
            raise ReferenceContractError("the reference has no rows")

        # ---- strict key typing, THEN the domain equality (A77 §65.5) ------ #
        #
        #     dom(QReferenceView) = {(x,a) : x a legal decision context, a in A_z(m,s)}
        #
        # The order below is the contract, and the parts are not interchangeable:
        #
        #     strict key typing -> strict context membership -> exact domain equality
        #       -> strict action-key typing -> row totality
        #
        # A set comparison is not a typed comparison. Python folds `True == 1`,
        # `1.0 == 1` and `False == 0` with equal hashes, and `State` is a dataclass, so
        # `State(x=1.0, ...) == State(x=1, ...)` holds. An earlier revision claimed the
        # per-key checks were "subsumed by the equality" and removed them; that reasoning
        # was wrong in exactly this way, and a probe confirmed six value-preserving
        # substitutions -- `z -> True`, `z -> 1.0`, `x -> float(x)`, `t -> float(t)`,
        # `kappa -> False`, and an action key `3 -> 3.0` -- all passed construction.
        #
        # With both sides strictly typed, the equality below *is* typed, and it is then
        # the right instrument for totality (which a cardinality check is not: it would
        # let a missing legal context and an invented one cancel).
        for key in rows:
            if not (type(key) is tuple and len(key) == 3):
                raise ReferenceContractError(
                    f"reference row key {key!r} is not a (State, z, m) triple")
            state, z, m = key
            if not is_strict_decision_state(state):
                raise ReferenceContractError(
                    f"reference row key {key!r} carries a State whose field(s) "
                    f"{non_integer_state_fields(state)} are not true ints. Python folds "
                    "1.0, True and 1 into one dict key, so this row would compare equal "
                    "to a legal context while not being one")
            if not is_decision_context(state, z, m):
                raise ReferenceContractError(
                    f"reference row key {key!r} is not a legal decision context "
                    "(type-strict membership in the frozen domain)")

        expected = decision_contexts()
        if set(rows) != expected:
            # After the typing loop every key is a legal context, so `rows` is a subset of
            # the domain and this equality is equivalent to "no legal context is
            # missing". The surplus side is therefore empty *by construction*, which is
            # why the message reports only what is missing: a branch that cannot fire is
            # not evidence, it is noise.
            missing = expected - set(rows)
            raise ReferenceContractError(
                "the reference's contexts are not exactly the frozen decision domain: "
                f"{len(missing)} of {len(expected)} legal contexts missing, e.g. "
                f"{sorted(missing, key=repr)[:2]!r}. A view that is merely row-total can "
                "be missing legal contexts, and a cardinality check would let a missing "
                "one and an invented one cancel")

        frozen: dict = {}
        for key, row in rows.items():
            state, z, m = key
            if not isinstance(row, Mapping):
                raise ReferenceContractError(
                    f"reference row {key!r} is {type(row).__name__}, not a mapping")
            for a in row:
                if not is_true_int(a):
                    raise ReferenceContractError(
                        f"reference row {key!r} is keyed by action {a!r} "
                        f"({type(a).__name__}), not a true int. The kernel's action ids "
                        "are integers, and `{3.0} == {3}` would let a float key satisfy "
                        "a value comparison while the read path returns it")
            allowed = set(option_actions(z, ControlState(z=z, m=m), state))
            keys = set(row)
            if keys != allowed:
                missing = sorted(allowed - keys)
                extra = sorted(keys - allowed)
                raise ReferenceContractError(
                    f"reference row {key!r} is not total on A_z(m,s): "
                    f"missing {missing}, inadmissible {extra}. The domain contract "
                    "dom(Q_D^L) subset of dom(QReferenceView) is only checkable while "
                    "every legal entry has a reference value (A77 §65.5)")
            values: dict = {}
            for a, v in row.items():
                if not _is_finite_real(v):
                    raise ReferenceContractError(
                        f"reference value at {key!r}, action {a!r} is {v!r}; the value "
                        "domain is the finite reals and bool is not a real")
                values[a] = float(v)
            frozen[key] = MappingProxyType(values)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "rows", MappingProxyType(frozen))

    # -- the read interface ------------------------------------------------ #
    def __len__(self) -> int:
        return len(self.rows)

    @property
    def domains(self) -> tuple:
        """The legal decision contexts, sorted for determinism."""
        return tuple(sorted(self.rows, key=lambda k: (k[0].t, k[0].kappa, k[0].phi,
                                                      k[0].x, k[0].y, k[1], k[2])))

    def has_context(self, state: State, z: int, m: int) -> bool:
        return (state, z, m) in self.rows

    def row(self, state: State, z: int, m: int) -> Mapping[int, float]:
        r"""$Q_D^\ast(x,\cdot)$. A missing row is a contract error, not a ``KeyError``."""
        try:
            return self.rows[(state, z, m)]
        except KeyError:
            raise ReferenceContractError(
                f"the reference has no row for ({state!r}, z={z!r}, m={m!r}); the view "
                "was validated as total when it was built, so this is a caller that "
                "built the context wrongly, not a missing entry") from None

    def actions(self, state: State, z: int, m: int) -> tuple:
        r"""$A_z(m,s)$ as the reference knows it, ascending."""
        return tuple(sorted(self.row(state, z, m)))

    def __contains__(self, address: object) -> bool:
        """Domain membership. Never raises: ``in`` must not fail on a foreign type."""
        if not isinstance(address, QAddress):
            return False
        row = self.rows.get((address.state, address.z, address.m))
        return row is not None and address.a in row

    def value(self, address: QAddress) -> float:
        r"""$Q_D^\ast(\texttt{address})$, or a contract error if out of domain."""
        if not isinstance(address, QAddress):
            raise ReferenceContractError(
                f"{address!r} is not a QAddress; the reference is keyed by QAddress")
        row = self.rows.get((address.state, address.z, address.m))
        if row is None:
            raise ReferenceContractError(
                f"the reference has no row for {address!r}")
        try:
            return row[address.a]
        except KeyError:
            raise ReferenceContractError(
                f"{address.a!r} is not admissible at {address!r}; the reference is total "
                "on A_z(m,s), so this address is outside the domain") from None

    def digest(self) -> str:
        r"""The canonical content digest, computed once.

        $$\boxed{\text{one referent} \iff \text{one digest}}$$

        Three places in an $L_2$ run name a reference — the episode's configuration, the
        shared $a^+$ adapter, and the transaction's canonicalisation — and they are three
        *entry points*, not three referents. Comparing content lets independently built
        views of the same $Q_D^\ast$ pass while a different referent fails stop, the same
        discipline the learner binding uses for snapshots.

        Cached because the view is immutable: ``rows`` is rebound as read-only mappings at
        construction, so the digest cannot go stale.
        """
        cached = self.__dict__.get("_digest")
        if cached is None:
            cached = hashlib.sha256(self.canonical().encode("utf-8")).hexdigest()
            object.__setattr__(self, "_digest", cached)
        return cached

    def canonical(self) -> str:
        """Deterministic digest source, so a view's identity is checkable."""
        parts = []
        for key in self.domains:
            state, z, m = key
            cells = ",".join(f"{a}={float(v).hex()}"
                             for a, v in sorted(self.rows[key].items()))
            parts.append(f"{state.x},{state.y},{state.t},{state.kappa},{state.phi},"
                         f"{z},{m}|{cells}")
        return "\n".join(parts)


def reference_view_from(solution: object, *,
                        name: str = "reference") -> QReferenceView:
    """Build a view from anything exposing a ``.q`` mapping.

    Duck-typed on purpose: this module must not import the solver, or the "no store or
    runner calls ``solve_reference()``" rule would be enforced by a comment instead of
    by the import graph.
    """
    rows = getattr(solution, "q", None)
    if rows is None:
        raise ReferenceContractError(
            f"{type(solution).__name__} has no .q mapping; a reference view is built "
            "from a solved reference, and this object is not one")
    return QReferenceView(rows, name=name)
