"""Owned factual source -> actual closed candidate call -> bound credit.

Seedless engineering only. No supplied method callback, evidence, proposal,
truth, model/support, query, seed or collection authorization is accepted.
This is in-process API closure, NOT a hostile-Python security sandbox or a
portable/scientific execution receipt. Old v6/v7 constructed proposals are not
retroactively authenticated by this new route.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from weakref import WeakKeyDictionary

import readiness as ready
import native_record_candidate as bridge
import credit_delivery_candidate as credit
import counterfactual_source_candidate as owned
import ordinary_methods_candidate as methods


METHODS = MappingProxyType({
    "TrajectoryCredit": (methods.trajectory_credit, "trajectory", "INHERITED_COARSE_EPISODE_RULE"),
    "ObservedExecutionCreditCandidate": (methods.observed_execution_credit, "causal", "NEW_OBSERVABLE_HEURISTIC_NOT_CAUSAL_IDENTIFICATION"),
    "AbstainCreditCandidate": (methods.abstain_credit, "causal", "NEW_EXPLICIT_ABSTENTION_BASELINE"),
})
_REGISTERED_METHODS = METHODS
_CODE_PATHS = (Path(__file__), Path(methods.__file__))
_CODE_BINDING = tuple(sha256(p.read_bytes()).hexdigest() for p in _CODE_PATHS)


class OwnedDiagnosticRun:
    __slots__ = ("__weakref__",)

    def __new__(cls):
        raise ready.ProtocolError("diagnostic handles are issued only after owned routing")


@dataclass(frozen=True, slots=True)
class _RunData:
    source: object
    method_id: str
    implementation: object
    kind: str
    rule_role: str
    prepared: object
    input_sha256: object
    proposal_units: object
    expanded_units: object
    source_binding: tuple
    route: str


_RUNS = WeakKeyDictionary()


def _code_guard():
    ready.require(METHODS is _REGISTERED_METHODS and type(METHODS) is MappingProxyType,
                  "closed method registry cannot be replaced with supplied callbacks")
    ready.require(tuple(sha256(p.read_bytes()).hexdigest() for p in _CODE_PATHS) == _CODE_BINDING,
                  "candidate invocation code changed since this module was loaded")


def _binding(data):
    return (data.fingerprint_pre, bridge.sha(data.config_payload),
        bridge.sha(data.trace_payload), bridge.sha(data.trace_metadata),
        data.audit["parent_sources_digest"], data.audit["lock_sha256"])


def run_owned_diagnostic(source, *, method_id):
    """Call exactly one declared implementation on only the owned projection.

    SUCCESS / P failure without manifestation issues a SKIPPED record with no
    input, no method call and no proposal. This differs from an actual method
    abstention. No production learner writes or native CF queries happen here.
    """
    ready.require(type(method_id) is str and method_id in METHODS,
                  "explicit closed candidate method id required; arbitrary callbacks are refused")
    _code_guard()
    implementation, kind, rule_role = METHODS[method_id]
    data = owned._checked(source)
    bound = _binding(data)
    evidence = owned.method_evidence(source)
    prepared = input_sha = units = expanded = None
    route = data.audit["route"]
    if evidence is not None:
        credit.factual_projection(evidence)
        input_sha = bridge.sha(owned._row_payload(evidence))
        try:
            proposal = implementation(evidence)  # ONLY this closed learner packet.
            prepared = credit.prepare_credit(evidence, kind=kind, proposal=proposal)
            units = tuple(sorted(proposal.units))
            expanded = prepared.expanded_units
        finally:
            _code_guard()
            ready.require(_binding(owned._checked(source)) == bound,
                          "actual diagnostic call changed its owned factual source")
        route = "ACTUAL_CANDIDATE_DIAGNOSTIC_CALL_BOUND_NOT_COLLECTION"
    handle = object.__new__(OwnedDiagnosticRun)
    _RUNS[handle] = _RunData(source, method_id, implementation, kind, rule_role,
        prepared, input_sha, units, expanded, bound, route)
    _checked_run(handle, source)
    return handle


def _checked_run(run, source):
    _code_guard()
    ready.require(type(run) is OwnedDiagnosticRun and run in _RUNS,
                  "issued diagnostic invocation required; nominal/hash records are not origin")
    d = _RUNS[run]
    ready.require(d.source is source, "diagnostic belongs to a different actual source, even if rows agree")
    source_data = owned._checked(source)
    ready.require(_binding(source_data) == d.source_binding,
                  "source changed since its actual diagnostic call")
    ready.require(type(d.method_id) is str and d.method_id in METHODS and
        METHODS[d.method_id] == (d.implementation, d.kind, d.rule_role),
        "closed method identity/permission differs from the actual call")
    evidence = owned.method_evidence(source)
    if evidence is None:
        ready.require(d.prepared is None and d.input_sha256 is None and
            d.proposal_units is None and d.expanded_units is None and
            d.route == source_data.audit["route"], "skipped route cannot carry a diagnostic prediction")
    else:
        ready.require(d.route == "ACTUAL_CANDIDATE_DIAGNOSTIC_CALL_BOUND_NOT_COLLECTION" and
            type(d.prepared) is credit.PreparedCredit and d.prepared.evidence is evidence and d.prepared.kind == d.kind,
            "actual call must retain the same owned learner packet")
        credit.validate_credit(d.prepared)
        ready.require(bridge.sha(owned._row_payload(evidence)) == d.input_sha256 and
            tuple(sorted(d.prepared.proposal.units)) == d.proposal_units and
            d.prepared.expanded_units == d.expanded_units,
            "stored proposal/input/whole expansion changed after the actual call")
    return d


def diagnostic_credit(run, source):
    """Retrieve genuine actual-call output, never authenticate supplied credit."""
    d = _checked_run(run, source)
    ready.require(d.prepared is not None, "skipped reflection is not an abstaining diagnostic call")
    return d.prepared


def diagnostic_audit(run, source):
    """Fresh evaluator-only audit. No audit/hash is accepted as a run handle."""
    d = _checked_run(run, source)
    called = d.prepared is not None
    return {"schema": "a96-owned-diagnostic-candidate-v8", "role": "SEEDLESS_ACTUAL_INVOCATION_NOT_SCIENTIFIC_RECEIPT",
        "method_id": d.method_id, "rule_role": d.rule_role, "route": d.route,
        "method_source_sha256": _CODE_BINDING[1], "invocation_source_sha256": _CODE_BINDING[0],
        "owned_source_binding": list(d.source_binding), "method_input_sha256": d.input_sha256,
        "proposal_kind": d.kind if called else None,
        "native_proposal_units": list(d.proposal_units) if called else None,
        "whole_original_eta_expansion": list(d.expanded_units) if called else None,
        "diagnostic_method_calls": int(called), "query_calls": 0,
        "actual_diagnostic_algorithm_executed": called,
        "proposal_origin_bound_to_actual_engineering_invocation": called,
        "source_handle_or_evaluator_audit_delivered_to_method": False,
        "fire_truth_Q_policy_or_tier_assistance_delivered_to_method": False,
        "complete_T_or_P_hypothesis_model_claimed": False,
        "scientific_algorithm_family_selected_or_frozen": False,
        "python_security_sandbox_claimed": False,
        "science_acquisition_origin_authenticated": False,
        "environment_seed_draws": 0, "future_training_episodes": 0,
        "collection_authorized": False, "scientific_claim_authorized": False,
        "research_complete": False}


def prepare_diagnosed_cell(run, source, arms):
    """Whole native L0/L3 credit projection. P-L1 assistance is NOT granted."""
    return credit.prepare_cell(diagnostic_credit(run, source), arms)


def prepare_diagnosed_l2_cell(run, source, arms):
    """After diagnosis, original full source-bound B1-L2 target construction.

    Extra B1 L2 content is not a method input. Every predicted decision survives
    the original architecture projection; residual predictions remain in audit.
    """
    return owned.prepare_l2_engineering_cell(source, diagnostic_credit(run, source), arms)
