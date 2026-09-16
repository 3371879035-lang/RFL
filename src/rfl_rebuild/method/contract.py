"""V0.1R method contract — types and protocols only, no algorithms (A59).

`14-V01R-METHOD-CONTRACT.md` is the normative text. This module makes the
boundary *structural* rather than promised:

* an arm's forbidden information is **absent from its type**, not merely
  unread — the negative tests assert ``not hasattr(view, field)``;
* ``Prediction`` validates finiteness, so ``NaN`` cannot slip through Python's
  comparison semantics;
* ``s_raw`` is optional, because a method that emits legal marginals directly
  must not be forced to manufacture raw scores;
* ``OracleAdapter`` does **not** implement the ordinary method call at all, so
  a truth-capable adapter cannot be routed into a normal arm runner by someone
  reusing code.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence

N_CAUSES = 5


class ProtocolError(Exception):
    """A programmer/protocol error, never a learner-facing observation.

    Exhausting the budget, requesting an unsafe query, or naming a query that is
    not in the menu are all contract violations. They must terminate the caller,
    and they must never be turned into evidence: a "rejected" answer would be a
    function of hidden ``M`` (A50).
    """


def _finite(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


# --------------------------------------------------------------------------- #
# What each arm may see. The forbidden fields simply do not exist here.
# --------------------------------------------------------------------------- #

@dataclass(frozen=True, slots=True)
class FactualEvidence:
    """``I^factual_{0:T}``: obs plus the learner's OWN ``z_in_force`` and ``m``.

    Deliberately NOT bare ``obs``: Gate_fire counts the learner's own control
    state as legal, and A55's process diagnosis needs ``z_in_force``. Exposes no
    ``Z^pres``, ``Z^fire``, ``B``, ``M``, ``R*``, ``u`` or ``z^proposal``.
    """

    rows: tuple
    z_in_force: int
    kappa: int
    phi: int


@dataclass(frozen=True, slots=True)
class FeedbackView:
    """The learner-facing content of the feedback channel only.

    No truth-decoder internals, no ``error_flag``, no ``cause_rank``, and no
    state or trajectory: this is the whole information set of ``DirectFeedback``.
    """

    claim: tuple


@dataclass(frozen=True, slots=True)
class QueryReceipt:
    """One executed query, as the learner sees it.

    ``response`` is the learner-facing payload and MAY contain the reward and
    terminal observation a learner could read off a legal trajectory — pruning
    those to satisfy "no Outcome" would make the arm narrower than Gate_fire.
    What is forbidden here is the evaluator *tag* (``Outcome.SUCCESS``,
    ``Outcome.COLLISION``, a ground-truth cause), and that is enforced by
    construction: this type has no field that can hold one.
    """

    spec: tuple
    kind: str
    cost: int
    response: Any
    budget_before: int
    budget_after: int


@dataclass(frozen=True, slots=True)
class Prediction:
    """Five marginal probabilities, plus optional raw scores kept SEPARATE.

    ``p`` is the object AUPRC/AUROC/Brier/ECE are computed on:
    ``p_i in [0,1]``, sum unconstrained. ``s_raw`` is a diagnostic and is
    optional — merging the two would make "the probability" ambiguous exactly
    where calibration is measured.
    """

    p: tuple
    s_raw: tuple | None = None

    def __post_init__(self) -> None:
        if len(self.p) != N_CAUSES:
            raise ProtocolError(f"p must have {N_CAUSES} entries, got {len(self.p)}")
        for i, v in enumerate(self.p):
            if not _finite(v):
                raise ProtocolError(f"p[{i}] is not a finite real: {v!r}")
            if not (0.0 <= float(v) <= 1.0):
                raise ProtocolError(f"p[{i}] outside [0,1]: {v!r}")
        if self.s_raw is not None:
            if len(self.s_raw) != N_CAUSES:
                raise ProtocolError(
                    f"s_raw must have {N_CAUSES} entries, got {len(self.s_raw)}")
            for i, v in enumerate(self.s_raw):
                if not _finite(v):
                    raise ProtocolError(f"s_raw[{i}] is not a finite real: {v!r}")


@dataclass(frozen=True, slots=True)
class MethodRunResult:
    """Prediction, receipts, arm, deterministic provenance — and nothing else.

    There is deliberately **no** ``update_target``, no responsibility ``U`` and
    no write receipt: V0.1R is diagnosis only (A59).
    """

    arm: str
    prediction: Prediction
    receipts: tuple
    provenance: Mapping[str, Any] = field(default_factory=dict)


class Method(Protocol):
    """The ordinary V0.1R arm call: one arm-specific view in, one ``p`` out."""

    def __call__(self, view: Any) -> Prediction:  # pragma: no cover - protocol
        ...


# --------------------------------------------------------------------------- #
# Oracle: structurally separate, by design
# --------------------------------------------------------------------------- #

class OracleAdapter:
    """``OracleAdapter.evaluate(truth)`` — the ceiling, and NOT a method.

    It does not implement ``__call__(view)`` at all, on purpose: there is no
    code path by which a truth-capable object can be handed to a normal arm
    runner, so nobody can reuse it to peek at truth from inside an arm.
    """

    name = "Oracle"

    @staticmethod
    def evaluate(fire: Sequence[int]) -> Prediction:
        if len(fire) != N_CAUSES:
            raise ProtocolError("truth vector must have 5 entries")
        return Prediction(p=tuple(float(int(bool(x))) for x in fire))

    def __call__(self, view: Any) -> Prediction:  # pragma: no cover
        raise ProtocolError(
            "OracleAdapter is not a Method: use evaluate(truth). It must never be "
            "routed through an arm runner (A59)."
        )
