"""Stateful ``QuerySession`` — budget as an unbypassable resource, and A50 by H.

Three things this module must not get wrong, all of them easy shortcuts:

1. **The menu comes from the information set, not from the truth.**
   ``Q_safe(H) = bigcap_{ell in H} Q_semantic(ell)``. Using the true latent
   world's legality instead would still avoid returning MALFORMED -- and would
   leak ``M`` through *which buttons appeared*, which is exactly the A50(d) error.
2. **Budget is consumed, never merely reported.** A successful query satisfies
   ``budget_before - budget_after == cost == 1`` and ``budget_after >= 0``. The
   fifth request raises ``ProtocolError``; it does not return a "budget exceeded"
   learner observation, because a refusal must not become evidence.
3. **Every query is an independent probe of the same world.** The world
   fingerprint is unchanged across queries, and the response to ``q_b`` does not
   depend on whether ``q_a`` was asked first.

The session drives the world through an injected ``probe`` so that this layer
carries no dependency on the environment scripts:

    probe.legal(case, q) -> bool          # response is not None
    probe.execute(case, q) -> response    # learner-facing payload
    probe.fingerprint(case) -> hashable   # world identity, for immutability
"""

from __future__ import annotations

from dataclasses import dataclass

from .contract import ProtocolError, QueryReceipt


@dataclass(frozen=True, slots=True)
class _Registered:
    spec: tuple
    kind: str


class QuerySession:
    """Holds the information set ``H``, the remaining budget and the history."""

    def __init__(self, *, probe, true_case, members, registry, budget: int):
        if budget < 0:
            raise ProtocolError("budget must be non-negative")
        self._probe = probe
        self._true = true_case
        self._members = tuple(members)
        self._registry = tuple(registry)
        self._budget = int(budget)
        self._initial_budget = int(budget)
        self._history: list[QueryReceipt] = []
        self._fingerprint0 = probe.fingerprint(true_case)
        if true_case not in self._members:
            raise ProtocolError("the true world must be in its own information set")

    # ---- read-only views the method may use ------------------------------- #
    @property
    def budget(self) -> int:
        return self._budget

    @property
    def history(self) -> tuple[QueryReceipt, ...]:
        return tuple(self._history)

    @property
    def hypothesis_size(self) -> int:
        """How many latent worlds are still consistent. Safe to expose."""
        return len(self._members)

    def menu(self) -> tuple[tuple, ...]:
        """``Q_safe(H)``: queries well-formed in EVERY still-possible world."""
        return tuple(
            reg.spec for reg in self._registry
            if all(self._probe.legal(case, reg.spec) for case in self._members)
        )

    # ---- the only way to spend ------------------------------------------- #
    def submit(self, spec: tuple) -> QueryReceipt:
        reg = next((r for r in self._registry if r.spec == spec), None)
        if reg is None:
            raise ProtocolError(f"query {spec!r} is not in the candidate registry")
        if self._budget < 1:
            raise ProtocolError(
                f"query budget exhausted ({self._initial_budget} spent); this is a "
                "protocol error, NOT a learner-facing observation"
            )
        safe = all(self._probe.legal(case, spec) for case in self._members)
        if not safe:
            raise ProtocolError(
                f"query {spec!r} is not safe on the current information set; it "
                "should not have been offered, and its refusal is not encodable "
                "as a response (A50)"
            )

        before = self._budget
        response = self._probe.execute(self._true, spec)
        self._budget -= 1
        after = self._budget
        if before - after != 1 or after < 0:
            raise ProtocolError("budget accounting violated")

        # belief update: keep exactly the worlds that would have answered alike
        self._members = tuple(
            c for c in self._members
            if self._probe.execute(c, spec) == response
        )

        receipt = QueryReceipt(spec=spec, kind=reg.kind, cost=1,
                               response=response,
                               budget_before=before, budget_after=after)
        self._history.append(receipt)

        if self._probe.fingerprint(self._true) != self._fingerprint0:
            raise ProtocolError("a query mutated the base world (A59)")
        return receipt

    def audit_independence(self, spec: tuple) -> bool:
        """``O(ell, q_b | q_a asked) == O(ell, q_b)`` for an earlier query."""
        if not self._history:
            raise ProtocolError("no earlier query to test independence against")
        return self._probe.execute(self._true, spec) is not None
