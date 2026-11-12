"""Owned seedless B1-L2 source construction; NOT a diagnostic/collection gate.

The configuration generates its own factual episode before any credit is used.
No supplied trace, CfEpisode, replay/provider closure, target or method result is
accepted. A separate ordinary diagnostic algorithm is still unimplemented here:
matching a constructed proposal's factual bytes does NOT authenticate its origin.
All extra reference/configuration information remains B1-L2 evaluator-side.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from types import MappingProxyType
from weakref import WeakKeyDictionary

import readiness as ready
import native_record_candidate as bridge
import factual_event_candidate as factual
import credit_delivery_candidate as credit
from rfl_rebuild.b1.contract import fingerprint
from rfl_rebuild.b1.counterfactual import CfEpisode, CounterfactualTarget, build_counterfactual_envelope
from rfl_rebuild.b1.targets import resolve_credited_units
from rfl_rebuild.b1.tier import Tier
from rfl_rebuild.b2.unaffected import EvaluationScene
from rfl_rebuild.env import kernel as K
from rfl_rebuild.env.observation import learner_rows
from rfl_rebuild.learner.reference import QReferenceView, reference_view_from
from rfl_rebuild.learner.store import LearnerPersistentState
from rfl_rebuild.method.runner import make_evidence
from rfl_rebuild.solve.dp import ReferenceSolution


class OwnedL2Source:
    """Opaque in-process engineering handle, NOT transferable science authority.

    Neither a caller's dataclass/hash nor a nominal CfEpisode can issue it. This
    is API closure, not a security sandbox against arbitrary Python code. The
    method-facing projection is obtained separately and contains no handle.
    """
    __slots__ = ("__weakref__",)

    def __new__(cls):
        raise ready.ProtocolError("sources are issued only by owned factual construction")


@dataclass(frozen=True, slots=True)
class _SourceData:
    pre_state: object
    episode: object
    solution: object
    reference: object
    scene: object
    evidence: object
    fingerprint_pre: str
    config_payload: dict
    trace_payload: list
    trace_metadata: dict
    channel_handles: tuple
    audit: dict


# No serialized token is accepted. Entries live only as long as their handles.
_ISSUED = WeakKeyDictionary()


def _configuration(episode):
    return {"kappa": episode.kappa,
        "tape": [episode.tape.phase, episode.tape.error_flag, episode.tape.cause_rank],
        "base_option": episode.base_option, "reward_mode": episode.reward_mode,
        "faults": factual._mask_payload(episode.mask, episode.option_fault),
        "interventions": [repr(x) for x in episode.interventions.members],
        "snapshot_fingerprint": fingerprint(episode.snapshot_pre),
        "q_reference_sha256": episode.reference.digest()}


def _row_payload(evidence):
    rows, _, _, _, _ = credit.factual_projection(evidence)
    return [list(r[:-1]) + [float(r[-1]).hex()] for r in rows]


def _trace_metadata(trace):
    return {"outcome": trace.outcome, "base_option": trace.base_option,
        "option_in_force": trace.option_in_force,
        "faults": factual._mask_payload(trace.mask, None),
        "interventions": [repr(x) for x in trace.interventions.members]}


def _checked(source):
    ready.require(type(source) is OwnedL2Source and source in _ISSUED,
                  "issued owned L2 source required; nominal objects/hashes are not origin")
    data = _ISSUED[source]
    ep = data.episode
    ready.require(type(ep) is CfEpisode and fingerprint(data.pre_state) == data.fingerprint_pre
        and fingerprint(ep.snapshot_pre) == data.fingerprint_pre,
        "source learner changed since the owned factual episode")
    ready.require(ep.decision_read_view_pre is data.channel_handles[0]
        and ep.process_commit_provider is data.channel_handles[1]
        and ep.controller_mapping is data.channel_handles[2]
        and bridge.sha(_configuration(ep)) == bridge.sha(data.config_payload)
        and data.reference.digest() == ep.reference.digest()
        and reference_view_from(data.solution).digest() == ep.reference.digest(),
        "owned configuration/channels/shared reference differ")
    ready.require(bridge.sha(factual._trace_payload(ep.factual_trace, data.scene))
        == bridge.sha(data.trace_payload) and bridge.sha(_trace_metadata(ep.factual_trace))
        == bridge.sha(data.trace_metadata), "owned factual trace changed")
    ready.require((_row_payload(data.evidence) if data.evidence is not None else None)
        == data.audit["method_packet"], "owned learner projection changed")
    return data


def prepare_owned_l2_source(pre_state, *, scene, regime, solution, q_reference,
                            parent, reference, mask=None, option_fault=None):
    """One native config -> factual rollout; no supplied outcomes or diagnostics.

    This route is explicitly D_Q. D_patch cannot be silently driven by the
    native CfEpisode's Q-only decision channel. The native total Q view seals
    the solution's consumed .q content, not mutable .v/.policy callbacks. No DP
    solve, environment key, training, counterfactual target or B1 write occurs.
    """
    ready.validate_design(parent["lock"])
    ready.validate_reference(reference, parent)
    ready.require(type(pre_state) is LearnerPersistentState and type(scene) is EvaluationScene
        and type(solution) is ReferenceSolution and type(q_reference) is QReferenceView,
        "exact native state/scene/solution/reference required")
    scene.__post_init__()
    ready.require(type(regime) is str and regime in ("T", "P"), "separate T/P only")
    ready.require(type(solution.horizon) is int and solution.horizon == K.HORIZON,
                  "native fixed reference horizon required")
    solved_view = reference_view_from(solution)
    ready.require(solved_view.digest() == q_reference.digest() == reference["q_reference_sha256"],
                  "B1 source, alternative adapter and B2 reference must share one Q*")
    sealed_sol = ReferenceSolution(q=solved_view.rows, v=MappingProxyType({}),
        policy=MappingProxyType({}), horizon=K.HORIZON)
    mask = K.FaultMask() if mask is None else mask
    factual._strict_mask(mask, option_fault)
    before = fingerprint(pre_state)
    snapshot = pre_state.snapshot()
    ready.require(not snapshot.decision_overrides,
                  "D_Q L2 cannot substitute its Q read path for a D_patch learner")
    if regime == "T":
        ready.require(snapshot.healthy, "T needs an actual healthy learner")
    else:
        ready.require(not snapshot.healthy and mask == K.FaultMask() and option_fault is None,
                      "P needs a persistent deviation without transient/do composition")
    try:
        episode = CfEpisode(kappa=scene.kappa, tape=scene.tape, snapshot_pre=snapshot,
            reference=solved_view, mask=deepcopy(mask), option_fault=option_fault,
            base_option=scene.base_option)
    finally:
        ready.require(fingerprint(pre_state) == before, "owned factual construction mutated learner")
    trace = episode.factual_trace
    ready.require(type(trace) is K.RolloutTrace and trace.steps and
        trace.steps[-1].terminal is True and trace.steps[-1].outcome == trace.outcome
        and type(trace.outcome) is str and trace.outcome in (K.Outcome.SUCCESS,) + factual.FAILURES
        and trace.base_option == scene.base_option and trace.mask == mask
        and not trace.interventions.members and trace.option_in_force ==
            (option_fault if option_fault is not None else snapshot.process_overrides.get(
                scene.base_option, scene.base_option)), "native owned terminal episode required")
    evidence, truth = None, None
    route = "SUCCESS_NO_REFLECTION"
    if trace.outcome != K.Outcome.SUCCESS:
        truth = (factual._persistent_truth(trace, scene, solved_view) if regime == "P"
            else factual._transient_truth(trace, scene, mask, solved_view))
        if regime == "P" and not truth["Gamma_P_star"]:
            route = "P_FAILURE_WITHOUT_MANIFESTATION_NO_REFLECTION"
        else:
            route = "OWNED_FAILURE_EVIDENCE_NOT_DIAGNOSTIC_EXECUTION"
            evidence = make_evidence(learner_rows(trace, scene.kappa, scene.phase),
                trace.option_in_force, scene.kappa, scene.phase)
    config = _configuration(episode)
    raw = factual._trace_payload(trace, scene)
    audit = {"schema": "a96-b2-owned-L2-source-candidate-v1",
        "role": "SEEDLESS_B1_L2_SOURCE_NOT_DIAGNOSTIC_OR_COLLECTION_AUTHORITY",
        "regime": regime, "scene": list(scene.key), "route": route,
        "factual_outcome": trace.outcome, "configuration": config,
        "raw_factual_trace_evaluator_only": raw, "truth_evaluator_only": truth,
        "source_fingerprint_pre": before, "source_fingerprint_post": fingerprint(pre_state),
        "parent_sources_digest": parent["sources_digest"], "lock_sha256": parent["lock_sha256"],
        "healthy_reference_canonical_payload_sha256": bridge.sha(reference),
        "method_packet": _row_payload(evidence) if evidence is not None else None,
        "factual_episode_constructed_from_owned_configuration": True,
        "supplied_factual_trace_or_replay_provider_accepted": False,
        "ordinary_method_may_read_B1_L2_source": False,
        "diagnostic_algorithm_executed": False, "proposal_origin_authenticated": False,
        "science_acquisition_origin_authenticated": False, "population_membership_authenticated": False,
        "environment_seed_draws": 0, "future_training_episodes": 0,
        "B1_write_calls": 0, "collection_authorized": False,
        "scientific_claim_authorized": False, "research_complete": False}
    source = object.__new__(OwnedL2Source)
    _ISSUED[source] = _SourceData(pre_state, episode, sealed_sol, solved_view, scene, evidence,
        before, deepcopy(config), deepcopy(raw), deepcopy(_trace_metadata(trace)), (episode.decision_read_view_pre,
            episode.process_commit_provider, episode.controller_mapping), deepcopy(audit))
    _checked(source)
    return source


def method_evidence(source):
    """Closed learner fields only; no source handle/truth/targets in this packet."""
    return _checked(source).evidence


def source_audit(source):
    """Evaluator-side copy, NEVER a diagnostic method argument."""
    return deepcopy(_checked(source).audit)


@dataclass(frozen=True, slots=True)
class PreparedL2Cell:
    source: object
    prepared: object
    arms: tuple
    credited_units: tuple
    addresses: tuple
    rows: tuple
    envelope: object
    deliveries: tuple
    audit: dict
    audit_sha256: str


def _target_payload(envelope, addresses):
    if envelope is None:
        ready.require(not addresses, "nonempty L2 population lacks its complete envelope")
        return None
    ready.require(type(envelope) is MappingProxyType, "readonly L2 envelope required")
    for a in tuple(envelope) + tuple(addresses):
        bridge.SLICES["D_Q"].domain.require_credited(a)
    ready.require(set(envelope) == set(addresses), "whole L2 envelope address set differs")
    out = []
    for a in addresses:
        r = envelope[a]
        ready.require(type(r) is CounterfactualTarget, "exact native L2 target required")
        bridge.SLICES["D_Q"].domain.require_credited(r.address)
        ready.require(type(r) is CounterfactualTarget and r.address == a
            and type(r.a_factual) is int and type(r.g_factual) is float
            and ((r.a_plus is None and r.g_cf is None) or
                 (type(r.a_plus) is int and type(r.g_cf) is float)),
            "typed factual pair and jointly present/absent CF pair required")
        bridge.finite(r.g_factual, "L2 factual return")
        if r.g_cf is not None:
            bridge.finite(r.g_cf, "L2 counterfactual return")
        out.append([bridge.SLICES["D_Q"].domain.canonical(a), r.a_factual,
            r.g_factual.hex(), r.a_plus, r.g_cf.hex() if r.g_cf is not None else None])
    return out


def prepare_l2_engineering_cell(source, prepared, arms):
    """Full native L2 replay/fold for ALL D_Q credits, not a diagnostic query.

    The source owns the fact/config before prediction; it is not reconstructed
    from caller rows. Prediction bytes are checked for continuity but their
    diagnostic algorithm/origin is still unauthenticated. Whole non-D_Q credit
    is retained for later preregistered set policy, NEVER truth-pruned.
    """
    matrix = bridge.validate_pair(arms)
    ready.require(matrix["architecture"] == "D_Q" and arms[0].tier is Tier.L2_COUNTERFACTUAL,
                  "separate B1-L2 authority only; no L0/L3/diagnostic widening")
    data = _checked(source)
    ready.require(data.evidence is not None, "SUCCESS or no-manifestation has no diagnostic/credit route")
    rows, _, _, _, _ = credit.validate_credit(prepared)
    ready.require(_row_payload(prepared.evidence) == _row_payload(data.evidence),
                  "proposal packet factual bytes differ from this owned episode")
    units = tuple(u for u in prepared.expanded_units if u.startswith("Decision_"))
    addresses = (tuple(resolve_credited_units(units, data.episode.factual_trace,
        data.scene.kappa, data.scene.phase)) if units else ())
    ready.require(len(addresses) == len(units) and len(set(addresses)) == len(addresses),
                  "native rho_D must preserve every credited address exactly once")
    for a in addresses:
        bridge.SLICES["D_Q"].domain.require_credited(a)
    try:
        envelope = (build_counterfactual_envelope(rows, addresses,
            sol=data.solution, episode=data.episode) if addresses else None)
    finally:
        _checked(source)  # native errors propagate; no partial/zero/fallback envelope
    targets = _target_payload(envelope, addresses)
    delivery = bridge.SLICES["D_Q"].deliver(Tier.L2_COUNTERFACTUAL, addresses, envelope) if units else None
    audit = {"schema": "a96-b2-owned-L2-cell-candidate-v1",
        "role": "SEEDLESS_B1_L2_TARGET_PREPARATION_NOT_DIAGNOSTIC_OR_COLLECTION",
        "source_audit_sha256": bridge.sha(data.audit), "source_configuration_sha256": bridge.sha(data.config_payload),
        "source_fingerprint_pre": data.fingerprint_pre, "matrix_cell": matrix,
        "representation": prepared.kind, "native_proposal_units": sorted(prepared.proposal.units),
        "all_expanded_units": list(prepared.expanded_units), "cell_credited_units": list(units),
        "residual_predictions_retained_not_reclassified": [u for u in prepared.expanded_units if u not in units],
        "factual_rows": _row_payload(data.evidence), "complete_ordered_native_targets": targets,
        "same_tier_delivery_fields": sorted(bridge.SLICES["D_Q"].fields(Tier.L2_COUNTERFACTUAL)),
        "both_roles_share_one_projected_delivery": True,
        "no_valid_alternative_count": sum(r.a_plus is None for r in envelope.values()) if units else 0,
        "route": "L2_TARGETS_PREPARED_NOT_B1_EXECUTED" if units else "NO_DQ_CREDIT_NOT_ZERO_FILLED",
        "owned_factual_configuration_continuity_checked": True,
        "extra_B1_information_is_ordinary_diagnostic_authority": False,
        "diagnostic_algorithm_executed": False, "proposal_origin_authenticated": False,
        "native_builder_includes_its_original_full_replay_validation": True,
        "B1_write_calls": 0, "future_training_episodes": 0, "environment_seed_draws": 0,
        "collection_authorized": False, "scientific_claim_authorized": False}
    return PreparedL2Cell(source, prepared, arms, units, addresses, rows, envelope,
        (delivery, delivery), audit, bridge.sha(audit))


def _delivery_payload(delivery, addresses):
    if delivery is None:
        ready.require(not addresses, "nonempty L2 cell lacks delivery")
        return None
    ready.require(type(delivery) is MappingProxyType, "readonly L2 delivery required")
    for a in delivery:
        bridge.SLICES["D_Q"].domain.require_credited(a)
    ready.require(set(delivery) == set(addresses), "L2 delivery address population differs")
    out = []
    for a in addresses:
        r = delivery[a]
        ready.require(type(r) is MappingProxyType and set(r) ==
            bridge.SLICES["D_Q"].fields(Tier.L2_COUNTERFACTUAL), "exact declared L2 fields required")
        ready.require(type(r["a_factual"]) is int and type(r["g_factual"]) is float
            and ((r["a_plus"] is None and r["g_cf"] is None) or
                 (type(r["a_plus"]) is int and type(r["g_cf"]) is float)),
            "strict L2 delivery field types/present-absence pairs required")
        bridge.finite(r["g_factual"], "delivered factual return")
        if r["g_cf"] is not None:
            bridge.finite(r["g_cf"], "delivered counterfactual return")
        out.append([bridge.SLICES["D_Q"].domain.canonical(a), r["a_factual"],
            r["g_factual"].hex(), r["a_plus"], r["g_cf"].hex() if r["g_cf"] is not None else None])
    return out


def validate_l2_engineering_cell(cell):
    """Re-derive complete native targets before a later consumer trusts a packet.

    This performs fresh seedless replays, not cached evidence validation or a
    collection PASS. No consumer/update is executed by this function. Every
    native refusal propagates and cannot produce a partially usable envelope.
    """
    ready.require(type(cell) is PreparedL2Cell and type(cell.arms) is tuple
        and type(cell.addresses) is tuple and type(cell.credited_units) is tuple
        and all(type(u) is str for u in cell.credited_units) and type(cell.rows) is tuple
        and type(cell.deliveries) is tuple and len(cell.deliveries) == 2
        and type(cell.audit) is dict, "closed prepared L2 packet required")
    expected = prepare_l2_engineering_cell(cell.source, cell.prepared, cell.arms)
    for a in cell.addresses:
        bridge.SLICES["D_Q"].domain.require_credited(a)
    ready.require(len(cell.rows) == len(expected.rows), "L2 factual row population differs")
    for row, own in zip(cell.rows, expected.rows):
        ready.require(type(row) is tuple and len(row) == len(own)
            and all(type(v) is int for v in row[:-1]) and row[:-1] == own[:-1]
            and type(row[-1]) is type(own[-1]) and type(row[-1]) is float
            and row[-1].hex() == own[-1].hex(), "bound L2 row types/reward bytes differ")
    ready.require(cell.addresses == expected.addresses and cell.credited_units == expected.credited_units
        and _target_payload(cell.envelope, expected.addresses) == _target_payload(expected.envelope, expected.addresses)
        and cell.deliveries[0] is cell.deliveries[1]
        and _delivery_payload(cell.deliveries[0], expected.addresses) == _delivery_payload(expected.deliveries[0], expected.addresses)
        and bridge.sha(cell.audit) == cell.audit_sha256 == expected.audit_sha256,
        "prepared L2 targets/delivery/audit differ from fresh owned re-derivation")
    return expected.audit_sha256
