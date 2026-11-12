"""V0.1R arm runner — isolation enforced by construction (A59).

Arms receive *different types*, and the two leak paths found in `33857d6` are
closed here:

* ``QueryOnly`` receives :class:`QueryObservation` (response only). The runner
  keeps :class:`QueryReceipt` (with address) for its own audit, and never hands it
  over. Previously the method got ``session.history``, i.e. the full address.
* the blind policy **recomputes the menu after every response**. A50's whole point
  is that ``H`` shrinking can *grow* ``Q_safe(H)``; computing the menu once at the
  root would silently discard queries that are only unlocked later. The policy is
  still blind — it never looks at sequence content, only at frozen registry order.
"""

from __future__ import annotations

import hashlib

from .contract import (
    FactualEvidence, FactualStep, FeedbackView, MethodRunResult, Prediction,
    ProtocolError,
)
from .session import QuerySession

ARMS = ("DirectFeedback", "SequenceEvidence", "QueryOnly", "SeqThenQuery")


def make_step(row) -> FactualStep:
    """``(x, y, t, kappa, phi, z, m, a_cmd, a_realized, reward)`` -> FactualStep."""
    return FactualStep(x=row[0], y=row[1], t=row[2], kappa=row[3], phi=row[4],
                       z=row[5], m=row[6], a_cmd=row[7], a_realized=row[8],
                       reward=float(row[9]))


def make_evidence(rows, z_in_force, kappa, phi) -> FactualEvidence:
    return FactualEvidence(steps=tuple(make_step(r) for r in rows),
                           z_in_force=z_in_force, kappa=kappa, phi=phi)


def make_feedback(claim) -> FeedbackView:
    return FeedbackView(claim=tuple(claim))


def blind_drain(session: QuerySession, budget: int, order) -> None:
    """FROZEN blind policy: first not-yet-asked safe query in registry order.

    The menu is recomputed each round, so a query unlocked by a shrinking ``H``
    is still reachable. The rule reads only the menu and the already-asked set —
    never the responses — so it remains blind.
    """
    asked: set = set()
    while session.budget > 0:
        menu = session.menu()
        nxt = next((q for q in order if q in menu and q not in asked), None)
        if nxt is None:
            return
        session.submit(nxt)
        asked.add(nxt)


def _fingerprint(obj) -> str:
    return hashlib.sha256(repr(obj).encode("utf-8")).hexdigest()[:32]


def run_arm(arm: str, method, *, evidence: FactualEvidence,
            feedback: FeedbackView, probe, world, members, registry,
            budget: int) -> MethodRunResult:
    if arm not in ARMS:
        raise ProtocolError(f"unknown arm {arm!r}")

    if arm == "DirectFeedback":
        pred = method(feedback)
        return _result(arm, pred, (), world, method)

    if arm == "SequenceEvidence":
        pred = method(evidence)
        return _result(arm, pred, (), world, method)

    if arm == "QueryOnly":
        session = QuerySession(probe=probe, true_case=world, members=members,
                               registry=registry, budget=budget)
        order = [r.spec for r in registry]
        blind_drain(session, budget, order)
        # OBSERVATIONS ONLY: response payloads, no spec, no kind, no session
        pred = method(session.observations())
        return _result(arm, pred, session.receipts(), world, method)

    session = QuerySession(probe=probe, true_case=world, members=members,
                           registry=registry, budget=budget)
    pred = method(evidence, session)
    return _result(arm, pred, session.receipts(), world, method)


def _result(arm, pred, receipts, world, method) -> MethodRunResult:
    if not isinstance(pred, Prediction):
        raise ProtocolError(f"{arm} returned {type(pred).__name__}, not a Prediction")
    return MethodRunResult(
        arm=arm, prediction=pred, receipts=tuple(receipts),
        provenance={"arm": arm,
                    "method_fingerprint": _fingerprint(method),
                    "world_fingerprint": _fingerprint(_world_key(world))},
    )


def _world_key(world):
    """Opaque identity of the latent world — never its contents."""
    return (world.kappa, world.phi, world.error_flag, world.cause_rank,
            world.base_option, world.Z, world.option_fault, world.decision,
            world.controller, world.plant, world.trap)
