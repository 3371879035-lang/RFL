"""V0.1R method layer: contract types, the stateful query session, and the
arm-isolation runner.

Nothing in this package implements an algorithm. It exists so that the
semantic gate can assert on the *pipe* — that it does not cheat, does not
overstep, and has no side effects — before any method is judged on quality.

See `docs/rebuild/14-V01R-METHOD-CONTRACT.md` (A59).
"""

from .contract import (  # noqa: F401
    Method, MethodRunResult, N_CAUSES, OracleAdapter, Prediction, ProtocolError,
    QueryReceipt, FactualEvidence, FeedbackView,
)
from .runner import ARMS, make_evidence, make_feedback, run_arm  # noqa: F401
from .session import QuerySession  # noqa: F401

__all__ = [
    "Method", "MethodRunResult", "N_CAUSES", "OracleAdapter", "Prediction",
    "ProtocolError", "QueryReceipt", "FactualEvidence", "FeedbackView",
    "QuerySession", "ARMS", "make_evidence", "make_feedback", "run_arm",
]
