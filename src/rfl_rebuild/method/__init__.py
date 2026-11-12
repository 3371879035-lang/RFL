"""V0.1R method layer: contract types, the stateful query session, and the
arm-isolation runner. Nothing here implements an algorithm.

See `docs/rebuild/14-V01R-METHOD-CONTRACT.md` (A59).
"""

from .contract import (  # noqa: F401
    FactualEvidence, FactualStep, FeedbackView, LEARNER_RESPONSES, Method,
    MethodRunResult, N_CAUSES, OracleAdapter, PlantAuditResponse, Prediction,
    ProcessProposalResponse, ProtocolError, QueryObservation, QueryReceipt,
    RolloutResponse,
)
from .methods import (  # noqa: F401
    DGP_MEASURE, UNIFORM_OVER_FEASIBLE_WORLDS, DirectFeedbackMethod,
    PublicSupport, QueryOnlyMethod, SeqThenQueryMethod, SequenceEvidenceMethod,
)
from .runner import (  # noqa: F401
    ARMS, blind_drain, make_evidence, make_feedback, make_step, run_arm,
)
from .session import QuerySession  # noqa: F401

__all__ = [
    "FactualEvidence", "FactualStep", "FeedbackView", "LEARNER_RESPONSES",
    "Method", "MethodRunResult", "N_CAUSES", "OracleAdapter",
    "PlantAuditResponse", "Prediction", "ProcessProposalResponse",
    "ProtocolError", "QueryObservation", "QueryReceipt", "RolloutResponse",
    "ARMS", "blind_drain", "make_evidence", "make_feedback", "make_step",
    "run_arm", "QuerySession",
    "UNIFORM_OVER_FEASIBLE_WORLDS", "DGP_MEASURE", "DirectFeedbackMethod",
    "PublicSupport", "QueryOnlyMethod", "SeqThenQueryMethod",
    "SequenceEvidenceMethod",
]
