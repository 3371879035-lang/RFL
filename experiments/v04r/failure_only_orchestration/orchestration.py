"""Failure-only outer orchestration for the revised local V0.4 study.

This module is a frozen-list-free engineering seam. It does not alter the V0.3
kernel, learner stores, B1 laws or registries, and it does not claim an
end-to-end learned RFL result. A task-visible terminal observation is the only
route selector: success keeps ordinary learning but never invokes diagnosis;
the three known failure terminals may be diagnosed within an explicit budget,
or may return keep. Unknown, missing and non-terminal observations are protocol
errors. Evaluator truth is retained as audit-only data and is never consulted
for routing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional


class ProtocolError(ValueError):
    """The task did not provide a legal terminal observation or decision."""


SUCCESS = "SUCCESS"
FAILURES = frozenset(("COLLISION", "TRAP", "TIMEOUT"))
TERMINALS = frozenset((SUCCESS, *FAILURES))


@dataclass(frozen=True, slots=True)
class TaskObservation:
    """Task-visible result plus learner-visible evidence.

    ``evaluator_metadata`` is intentionally carried only for audit. The
    orchestrator never reads it to choose a route and does not pass it to the
    diagnostic callback.
    """

    terminal: Any
    learner_evidence: Any = None
    evaluator_metadata: Any = None


@dataclass(frozen=True, slots=True)
class LearnerObservation:
    """Only task-visible terminal and learner evidence enter ordinary learning."""

    terminal: str
    learner_evidence: Any = None


@dataclass(frozen=True, slots=True)
class BudgetView:
    """Immutable budget view exposed to diagnosis; spending stays in the runner."""

    remaining_queries: int
    remaining_writes: int


@dataclass(frozen=True, slots=True)
class DiagnosticResult:
    """A failure diagnosis may keep the learner unchanged or request a write."""

    action: str
    query_cost: int = 0
    write_cost: int = 0
    payload: Any = None

    def __post_init__(self) -> None:
        if self.action not in ("keep", "apply"):
            raise ProtocolError("diagnostic action must be keep or apply")
        if type(self.query_cost) is not int or self.query_cost < 0:
            raise ProtocolError("query_cost must be a non-negative integer")
        if type(self.write_cost) is not int or self.write_cost < 0:
            raise ProtocolError("write_cost must be a non-negative integer")
        if self.action == "keep" and self.write_cost:
            raise ProtocolError("keep cannot carry diagnostic writes")


@dataclass(slots=True)
class DiagnosticBudget:
    """Mutable per-task diagnostic budget; no hidden retry or overspend."""

    max_queries: int
    max_writes: int
    queries: int = 0
    writes: int = 0

    def __post_init__(self) -> None:
        if type(self.max_queries) is not int or self.max_queries < 0:
            raise ProtocolError("max_queries must be non-negative")
        if type(self.max_writes) is not int or self.max_writes < 0:
            raise ProtocolError("max_writes must be non-negative")

    def spend(self, *, queries: int = 0, writes: int = 0) -> None:
        if type(queries) is not int or type(writes) is not int or queries < 0 or writes < 0:
            raise ProtocolError("diagnostic spend must be non-negative integers")
        if self.queries + queries > self.max_queries:
            raise ProtocolError("diagnostic query budget exceeded")
        if self.writes + writes > self.max_writes:
            raise ProtocolError("diagnostic write budget exceeded")
        self.queries += queries
        self.writes += writes


@dataclass(frozen=True, slots=True)
class RouteRecord:
    terminal: str
    route: str
    ordinary_learning_called: bool
    diagnostic_calls: int
    query_spend: int
    write_spend: int
    decision: str


@dataclass(slots=True)
class FailureOnlyOrchestrator:
    """Connect one real task result, ordinary learning and optional diagnosis."""

    ordinary_update: Callable[[LearnerObservation], None]
    diagnose: Callable[[str, Any, BudgetView], DiagnosticResult]
    apply_diagnostic: Callable[[DiagnosticResult], None]
    max_queries: int = 0
    max_writes: int = 0
    history: list[RouteRecord] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not callable(self.ordinary_update) or not callable(self.diagnose):
            raise ProtocolError("ordinary_update and diagnose must be callable")
        if not callable(self.apply_diagnostic):
            raise ProtocolError("apply_diagnostic must be callable")
        if type(self.max_queries) is not int or self.max_queries < 0:
            raise ProtocolError("max_queries must be non-negative")
        if type(self.max_writes) is not int or self.max_writes < 0:
            raise ProtocolError("max_writes must be non-negative")

    @staticmethod
    def _terminal(observation: TaskObservation) -> str:
        terminal = observation.terminal
        if type(terminal) is not str or terminal not in TERMINALS:
            raise ProtocolError("missing, non-terminal or unknown task result")
        return terminal

    def run(self, observation: TaskObservation) -> RouteRecord:
        if not isinstance(observation, TaskObservation):
            raise ProtocolError("a typed TaskObservation is required")
        terminal = self._terminal(observation)
        budget = DiagnosticBudget(self.max_queries, self.max_writes)

        # Ordinary task learning is retained for every legal terminal outcome.
        self.ordinary_update(LearnerObservation(terminal, observation.learner_evidence))

        if terminal == SUCCESS:
            # No diagnostic callback is reachable on success. The callback gets
            # learner evidence only on failures, so evaluator metadata cannot
            # silently influence the route.
            record = RouteRecord(SUCCESS, "SUCCESS_NO_DIAGNOSTIC", True, 0, 0, 0, "none")
            self.history.append(record)
            return record

        result = self.diagnose(terminal, observation.learner_evidence,
                               BudgetView(budget.max_queries - budget.queries,
                                          budget.max_writes - budget.writes))
        if not isinstance(result, DiagnosticResult):
            raise ProtocolError("diagnose must return DiagnosticResult")
        budget.spend(queries=result.query_cost, writes=result.write_cost)
        if result.action == "apply":
            self.apply_diagnostic(result)
            route = "FAILURE_DIAGNOSTIC_APPLIED"
        else:
            route = "FAILURE_DIAGNOSTIC_KEEP"
        record = RouteRecord(terminal, route, True, 1, budget.queries, budget.writes, result.action)
        self.history.append(record)
        return record

