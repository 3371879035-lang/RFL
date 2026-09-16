"""Stateful ``QuerySession`` — budget as a resource, and A50 by ``H``.

The menu is ``Q_safe(H) = bigcap_{ell in H} Q_semantic(ell)``. Using the true
world's legality instead would still avoid returning MALFORMED, and would leak
``M`` through *which buttons appeared* — the A50(d) error.

The session hands arms :class:`QueryObservation` (response only) and keeps
:class:`QueryReceipt` (with address) for auditing. Arms other than the
sequence-informed one must never see an address.
"""

from __future__ import annotations

from dataclasses import dataclass

from .contract import (
    ProtocolError, QueryObservation, QueryReceipt, RolloutResponse,
    PlantAuditResponse, ProcessProposalResponse,
)


@dataclass(frozen=True, slots=True)
class _Registered:
    spec: tuple
    kind: str


def _wrap(kind: str, spec: tuple, response) -> object:
    """Convert a raw environment response into the closed learner-facing union."""
    if response is None:
        raise ProtocolError("illegal query reached the response boundary")
    if kind == "audit":
        _tag, u = response
        return PlantAuditResponse(t=spec[1], u=u)
    if kind == "proc_audit":
        return ProcessProposalResponse(proposal=response[1])
    # everything else is a counterfactual rollout: (rows, feedback)
    from .contract import FactualStep
    rows = response[0]
    steps = tuple(FactualStep(x=r[0], y=r[1], t=r[2], kappa=r[3], phi=r[4],
                              z=r[5], m=r[6], a_cmd=r[7], a_realized=r[8],
                              reward=float(r[9])) for r in rows)
    return RolloutResponse(steps=steps)


class QuerySession:
    def __init__(self, *, probe, true_case, members, registry, budget: int):
        if budget < 0:
            raise ProtocolError("budget must be non-negative")
        self._probe = probe
        self._true = true_case
        self._members = tuple(members)
        self._registry = tuple(registry)
        self._budget = int(budget)
        self._initial_budget = int(budget)
        self._receipts: list[QueryReceipt] = []
        self._observations: list[QueryObservation] = []
        self._fingerprint0 = probe.fingerprint(true_case)
        if true_case not in self._members:
            raise ProtocolError("the true world must be in its own information set")

    # ---- read-only, learner-safe ----------------------------------------- #
    @property
    def budget(self) -> int:
        return self._budget

    @property
    def hypothesis_size(self) -> int:
        return len(self._members)

    def observations(self) -> tuple:
        """Learner-facing evidence: responses only, no addresses."""
        return tuple(self._observations)

    def receipts(self) -> tuple:
        """Internal/audit view, WITH addresses. Never given to a method."""
        return tuple(self._receipts)

    def menu(self) -> tuple:
        """``Q_safe(H)`` — recomputed from the CURRENT ``H`` every call."""
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
                f"query budget exhausted ({self._initial_budget} spent); a "
                "protocol error, NOT a learner-facing observation"
            )
        if not all(self._probe.legal(case, spec) for case in self._members):
            raise ProtocolError(
                f"query {spec!r} is not safe on the current information set; it "
                "should not have been offered, and its refusal is not encodable "
                "as a response (A50)"
            )

        before = self._budget
        raw = self._probe.execute(self._true, spec)
        wrapped = _wrap(reg.kind, spec, raw)
        self._budget -= 1
        after = self._budget
        if before - after != 1 or after < 0:
            raise ProtocolError("budget accounting violated")

        self._members = tuple(
            c for c in self._members if self._probe.execute(c, spec) == raw
        )

        receipt = QueryReceipt(spec=spec, kind=reg.kind, cost=1, response=wrapped,
                               budget_before=before, budget_after=after)
        self._receipts.append(receipt)
        self._observations.append(QueryObservation(response=wrapped))

        if self._probe.fingerprint(self._true) != self._fingerprint0:
            raise ProtocolError("a query mutated the base world (A59)")
        return receipt

    # ---- a real independence assertion, not a tautology ------------------- #
    def independence_violated(self, qa: tuple, qb: tuple) -> bool:
        """``O(ell, q_b | q_a asked) != O(ell, q_b)`` or the world moved.

        This COMPARES the two responses. The earlier helper returned
        ``probe.execute(...) is not None``, which is always true and would have
        advertised an independence check that did not exist.
        """
        before_world = self._probe.fingerprint(self._true)
        before_resp = self._probe.execute(self._true, qb)
        shadow = QuerySession(probe=self._probe, true_case=self._true,
                              members=self._members, registry=self._registry,
                              budget=self._budget)
        shadow.submit(qa)
        after_resp = self._probe.execute(self._true, qb)
        if self._probe.fingerprint(self._true) != before_world:
            return True
        return before_resp != after_resp
