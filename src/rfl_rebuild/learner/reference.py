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

import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from rfl_rebuild.env.domain import decision_contexts
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

        # ---- domain totality, as an EQUALITY (A77 §65.5) ------------------ #
        #
        #     dom(QReferenceView) = {(x,a) : x a legal decision context, a in A_z(m,s)}
        #
        # The first version checked only that each row the caller handed over had its
        # actions exactly equal to A_z(m,s). A single complete row therefore made a legal
        # view: row totality says nothing about *which* contexts exist, so a reference
        # missing 13,823 of them -- or one carrying a context outside the frozen domain --
        # was accepted. The enumerator is `env.domain`, shared with the solver, so this is
        # a comparison against the environment's own list rather than a second opinion;
        # a cardinality check would have let a missing context and an invented one cancel.
        #
        # The per-key shape checks the first version carried are subsumed by this
        # equality and were removed rather than left in place: a malformed key is by
        # definition not a member of the domain, so a separate check could never fire.
        expected = decision_contexts()
        if set(rows) != expected:
            missing = expected - set(rows)
            extra = set(rows) - expected
            raise ReferenceContractError(
                "the reference's contexts are not exactly the frozen decision domain: "
                f"{len(missing)} of {len(expected)} legal contexts missing, "
                f"{len(extra)} context(s) outside the domain. Examples: missing "
                f"{sorted(missing, key=repr)[:2]!r}, unexpected "
                f"{sorted(extra, key=repr)[:2]!r}")

        frozen: dict = {}
        for key, row in rows.items():
            state, z, m = key
            if not isinstance(row, Mapping):
                raise ReferenceContractError(
                    f"reference row {key!r} is {type(row).__name__}, not a mapping")
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
