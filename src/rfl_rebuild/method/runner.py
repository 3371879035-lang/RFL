"""V0.1R arm runner — isolation enforced by construction (A59).

Each arm is handed a *different type*. No arm is asked to promise it will not
read something: the something is not there.

    DirectFeedback   FeedbackView only            -- no state, no trajectory, no query()
    SequenceEvidence FactualEvidence only         -- B_Q = 0, no QuerySession
    QueryOnly        receipts only                -- runner picks; no menu handles
    SeqThenQuery     FactualEvidence + QuerySession -- selects its own queries

``QueryOnly`` is the subtle one. Several query *addresses* are derived from the
factual trajectory (an execution probe needs a ``(state, a_cmd)`` site, a
decision replay and a plant audit need a timestep), so showing an arm the menu
would leak sequence evidence through the query list. The runner therefore drains
the arm's safe family with a frozen blind policy and passes only the responses.
"""

from __future__ import annotations

from .contract import (
    FactualEvidence, FeedbackView, MethodRunResult, Prediction, ProtocolError,
)
from .session import QuerySession

ARMS = ("DirectFeedback", "SequenceEvidence", "QueryOnly", "SeqThenQuery")


def make_evidence(rows, z_in_force, kappa, phi) -> FactualEvidence:
    return FactualEvidence(rows=tuple(rows), z_in_force=z_in_force,
                           kappa=kappa, phi=phi)


def make_feedback(claim) -> FeedbackView:
    return FeedbackView(claim=tuple(claim))


def _blind_policy(menu, budget):
    """FROZEN blind selection: registry order, first `budget` safe queries."""
    return list(menu[:budget])


def run_arm(arm: str, method, *, evidence: FactualEvidence,
            feedback: FeedbackView, probe, world, members, registry,
            budget: int) -> MethodRunResult:
    if arm not in ARMS:
        raise ProtocolError(f"unknown arm {arm!r}")

    if arm == "DirectFeedback":
        # view is FeedbackView; there is no evidence object in scope for the method
        pred = method(feedback)
        return _result(arm, pred, (), world, feedback, evidence)

    if arm == "SequenceEvidence":
        pred = method(evidence)
        return _result(arm, pred, (), world, feedback, evidence)

    if arm == "QueryOnly":
        session = QuerySession(probe=probe, true_case=world, members=members,
                               registry=registry, budget=budget)
        for spec in _blind_policy(session.menu(), budget):
            session.submit(spec)
        # the method sees RECEIPTS ONLY -- no menu, no session, no evidence
        pred = method(session.history)
        return _result(arm, pred, session.history, world, feedback, evidence)

    # SeqThenQuery: evidence plus a live session it steers itself
    session = QuerySession(probe=probe, true_case=world, members=members,
                           registry=registry, budget=budget)
    pred = method(evidence, session)
    return _result(arm, pred, session.history, world, feedback, evidence)


def _result(arm, pred, receipts, world, feedback, evidence) -> MethodRunResult:
    if not isinstance(pred, Prediction):
        raise ProtocolError(f"{arm} returned {type(pred).__name__}, not a Prediction")
    return MethodRunResult(
        arm=arm, prediction=pred, receipts=tuple(receipts),
        provenance={"world_fingerprint": repr(world), "arm": arm},
    )
