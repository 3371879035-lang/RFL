"""V0.1R method contract — types and protocols only, no algorithms (A59).

`14-V01R-METHOD-CONTRACT.md` is the normative text. The boundary is meant to be
*structural*, and an earlier revision only appeared to be: `FactualEvidence.rows`
was a bare tuple, `QueryReceipt.response` was `Any`, and `MethodRunResult.
provenance` held `repr(world)`, so truth could sit inside a payload while
``hasattr(receipt, "Z_fire")`` stayed False. That is not isolation.

So the payloads are now a **closed union of learner-facing types**, the internal
receipt is separated from the learner-facing observation, and provenance is an
opaque fingerprint. Nothing here can carry ``Z``, ``M``, ``B``, ``R*`` or an
evaluator ``Outcome`` tag, because no field can hold one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence

N_CAUSES = 5


class ProtocolError(Exception):
    """A programmer/protocol error, never a learner-facing observation."""


def _finite(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


# --------------------------------------------------------------------------- #
# Learner-visible step and evidence
# --------------------------------------------------------------------------- #

@dataclass(frozen=True, slots=True)
class FactualStep:
    """One learner-visible step of ``I_t = (obs_t, z_t, m_t)``.

    Every field is something the learner's own control state and sensors carry.
    ``m_t`` is explicit rather than buried in an opaque tuple — hiding it there
    would give up the structural guarantee the contract is for.
    """

    x: int
    y: int
    t: int
    kappa: int
    phi: int
    z: int          # z^in-force: the learner's own control state
    m: int          # the learner's own automaton state
    a_cmd: int
    a_realized: int
    reward: float

    def __post_init__(self) -> None:
        if not _finite(self.reward):
            raise ProtocolError("reward must be finite")


@dataclass(frozen=True, slots=True)
class FactualEvidence:
    """``I^factual_{0:T}`` — steps plus the initial in-force option.

    No ``Z^pres``, ``Z^fire``, ``B``, ``M`` (as a latent block), ``R*``, ``u`` or
    ``z^proposal``: none of those has a field here.
    """

    steps: tuple
    z_in_force: int
    kappa: int
    phi: int

    def __post_init__(self) -> None:
        for s in self.steps:
            if not isinstance(s, FactualStep):
                raise ProtocolError("FactualEvidence.steps must be FactualStep")

    @property
    def m_trajectory(self) -> tuple:
        return tuple(s.m for s in self.steps)


@dataclass(frozen=True, slots=True)
class FeedbackView:
    """The learner-facing feedback content only — no decoder internals."""

    claim: tuple


# --------------------------------------------------------------------------- #
# Closed union of learner-facing query responses
# --------------------------------------------------------------------------- #

@dataclass(frozen=True, slots=True)
class RolloutResponse:
    """A counterfactual rollout, as learner-visible steps."""

    steps: tuple

    def __post_init__(self) -> None:
        for s in self.steps:
            if not isinstance(s, FactualStep):
                raise ProtocolError("RolloutResponse.steps must be FactualStep")


@dataclass(frozen=True, slots=True)
class PlantAuditResponse:
    """``q^plant_t``: the low-level command the plant received at ``t``."""

    t: int
    u: int


@dataclass(frozen=True, slots=True)
class ProcessProposalResponse:
    """``q^proc``: the option the upstream planner proposed."""

    proposal: int


LEARNER_RESPONSES = (RolloutResponse, PlantAuditResponse, ProcessProposalResponse)


@dataclass(frozen=True, slots=True)
class QueryObservation:
    """What a learner sees for a query it did NOT address.

    Carries the response and nothing else. In particular it has **no ``spec`` and
    no ``kind``**: query addresses are partly derived from the factual trajectory
    (an execution probe needs a site, a decision replay and a plant audit need a
    timestep), so shipping them to ``QueryOnly`` would leak sequence evidence
    through the query list — the isolation A59 exists to enforce.
    """

    response: Any

    def __post_init__(self) -> None:
        if not isinstance(self.response, LEARNER_RESPONSES):
            raise ProtocolError(
                f"response must be one of {[t.__name__ for t in LEARNER_RESPONSES]}, "
                f"got {type(self.response).__name__}")


@dataclass(frozen=True, slots=True)
class QueryReceipt:
    """INTERNAL/RUNNER receipt: keeps the address, for auditing only.

    This is never handed to a method. ``QuerySession`` exposes
    :class:`QueryObservation` to arms; the address lives here so the run can be
    audited afterwards.
    """

    spec: tuple
    kind: str
    cost: int
    response: Any
    budget_before: int
    budget_after: int

    def __post_init__(self) -> None:
        if not isinstance(self.response, LEARNER_RESPONSES):
            raise ProtocolError("receipt response must be a learner-facing type")


# --------------------------------------------------------------------------- #
# Prediction and result
# --------------------------------------------------------------------------- #

@dataclass(frozen=True, slots=True)
class Prediction:
    """Five marginals, plus optional raw scores kept SEPARATE.

    ``p_i in [0,1]`` finite, sum unconstrained; ``s_raw`` optional and finite.
    Merging the two would make "the probability" ambiguous exactly where
    calibration is measured, and ``NaN`` must not slip through by Python's
    comparison semantics.
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
    """Prediction, internal receipts, arm, and an OPAQUE provenance fingerprint.

    No ``update_target``, no responsibility ``U``, no write receipt (A59), and no
    ``repr(world)``: the provenance is a hash, so it cannot carry latent world
    content into anything downstream.
    """

    arm: str
    prediction: Prediction
    receipts: tuple
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for k in ("world_fingerprint", "method_fingerprint"):
            v = self.provenance.get(k)
            if v is not None and not (isinstance(v, str) and len(v) <= 64):
                raise ProtocolError(f"provenance[{k}] must be an opaque short hash")


class Method(Protocol):
    def __call__(self, view: Any) -> Prediction:  # pragma: no cover - protocol
        ...


class OracleAdapter:
    """``OracleAdapter.evaluate(truth)`` — the ceiling, and NOT a method.

    It does not implement ``__call__(view)``, so no code path can route a
    truth-capable object into an ordinary arm runner.
    """

    name = "Oracle"

    @staticmethod
    def evaluate(fire: Sequence[int]) -> Prediction:
        if len(fire) != N_CAUSES:
            raise ProtocolError("truth vector must have 5 entries")
        return Prediction(p=tuple(float(int(bool(x))) for x in fire))

    def __call__(self, view: Any) -> Prediction:  # pragma: no cover
        raise ProtocolError(
            "OracleAdapter is not a Method: use evaluate(truth) (A59)."
        )
