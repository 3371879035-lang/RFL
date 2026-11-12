"""Truth-blind proposal expansion and B1 cell preparation, NOT collection.

This adapter owns no diagnostic algorithm, success/failure oracle, learner,
query service, sampler, update, future or selection policy. A caller must have
already passed the owned factual failure gate. Nominal packets/digests cannot
authenticate that routing or acquisition origin. All expanded predictions are
retained; an architecture projection is recorded, never a truth-based pruning.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

import readiness as ready
import native_record_candidate as bridge
from rfl_rebuild.b1.controller import (build_controller_envelope,
    render_controller_unit, require_admissible_sites)
from rfl_rebuild.b1.factual import build_factual_envelope
from rfl_rebuild.b1.process import (AssistedInput, build_process_envelope,
    resolve_process_addresses)
from rfl_rebuild.b1.tier import Tier
from rfl_rebuild.b2.unaffected import CreditedSite
from rfl_rebuild.env import kernel as K
from rfl_rebuild.env.domain import is_decision_context
from rfl_rebuild.learner.store import DecisionAddress
from rfl_rebuild.method.contract import FactualEvidence, FactualStep
from rfl_rebuild.method import credit as native

PROPOSALS = {"module": native.ModuleProposal,
             "trajectory": native.TrajectoryProposal, "causal": native.CausalProposal}
NONWRITEABLE = ("Strategy", "ExternalPlant", "Unknown/NoWrite")


def factual_projection(evidence):
    """Only closed learner fields; strict types BEFORE Python equality folding.

    Rows are the original observation schema, with no recovered reward precision,
    terminal label, latent u, proposal, fire bit, truth or evaluator trace. This
    checks structure, not whether a nominal packet came from an actual rollout.
    Fault-privileged a_cmd is allowed in evidence; the B1 cell separately enforces
    learner admissibility and refuses it instead of dropping the credited unit.
    """
    ready.require(type(evidence) is FactualEvidence and type(evidence.steps) is tuple
        and 0 < len(evidence.steps) <= K.HORIZON, "closed nonempty factual packet required")
    for value, domain in ((evidence.kappa, K.CONTEXT_PERIODS),
            (evidence.phi, K.PHASE_DOMAIN), (evidence.z_in_force, K.option_ids())):
        ready.require(type(value) is int and value in domain, "typed outer factual context required")
    rows, decisions, controllers = [], [], []
    for i, step in enumerate(evidence.steps):
        ready.require(type(step) is FactualStep, "exact nominal factual step required")
        values = (step.x, step.y, step.t, step.kappa, step.phi, step.z, step.m,
                  step.a_cmd, step.a_realized)
        ready.require(all(type(v) is int for v in values), "true integer factual fields required")
        s = K.State(*values[:5])
        ready.require(is_decision_context(s, step.z, step.m) and step.t == i
            and step.kappa == evidence.kappa and step.phi == evidence.phi
            and step.z == evidence.z_in_force and step.a_cmd in range(len(K.ACTIONS))
            and step.a_realized in range(len(K.ACTIONS)), "factual chronology/context/action differs")
        bridge.finite(step.reward, "factual reward")
        rows.append(values + (step.reward,))
        decisions.append((f"Decision_{step.t}", DecisionAddress(s, step.z, step.m)))
        site = K.ControllerSite(s, step.a_cmd)
        controllers.append((render_controller_unit(s, step.a_cmd), site))
    # The native expander adds 'ControllerSite_' to each opaque handle. The
    # handle contains the complete A71 wire address, not only a timestep.
    shape = native.FactualShape(tuple(s.t for s in evidence.steps),
        tuple(u.removeprefix("ControllerSite_") for u, _ in controllers))
    order = native.GAMMA_STATIC + tuple(u for u, _ in decisions) + tuple(u for u, _ in controllers)
    ready.require(len(order) == len(set(order)) and set(order) == set(shape.gamma()),
                  "episode-local credit domain is not injective/complete")
    return tuple(rows), shape, order, tuple(decisions), tuple(controllers)


@dataclass(frozen=True, slots=True)
class PreparedCredit:
    evidence: FactualEvidence
    kind: str
    proposal: object
    expanded_units: tuple


def prepare_credit(evidence, *, kind, proposal):
    """Original eta_R(proposal, factual shape), NEVER Gamma*/Z_fire/locator input.

    No inferred kind, oracle adapter, generic callable or V02Input: those would
    widen the source contract. No algorithm/family is selected by this helper.
    Empty prediction stays empty; it is not relabelled Unknown/NoWrite.
    """
    _, shape, order, _, _ = factual_projection(evidence)
    ready.require(type(kind) is str and kind in PROPOSALS and
        type(proposal) is PROPOSALS[kind] and type(proposal.units) is frozenset
        and all(type(u) is str for u in proposal.units), "closed kind/native proposal required")
    # Re-run nominal alphabet validation: frozen dataclasses can still be forged
    # through low-level object access. Origin authentication is a later gate.
    proposal.__post_init__()
    expanded = native.expand(kind, proposal, shape)
    return PreparedCredit(evidence, kind, proposal, tuple(u for u in order if u in expanded))


def validate_credit(prepared):
    ready.require(type(prepared) is PreparedCredit and type(prepared.expanded_units) is tuple,
                  "exact prepared credit packet required")
    expected = prepare_credit(prepared.evidence, kind=prepared.kind, proposal=prepared.proposal)
    ready.require(all(type(u) is str for u in prepared.expanded_units)
        and prepared.expanded_units == expected.expanded_units,
        "expanded credit differs from the original truth-blind eta_R")
    return factual_projection(prepared.evidence)


@dataclass(frozen=True, slots=True)
class CellPreparation:
    prepared: PreparedCredit
    arms: tuple
    credited_units: tuple
    addresses: tuple
    b1_evidence: object
    deliveries: tuple
    audit: object
    audit_sha256: str


def _delivery_payload(delivery, addresses, descriptor, tier):
    if delivery is None:
        return None
    ready.require(type(delivery) is MappingProxyType and len(delivery) == len(addresses),
                  "closed readonly cell delivery required")
    for address in delivery:
        descriptor.domain.require_credited(address)
    ready.require(set(delivery) == set(addresses), "delivery address population differs")
    out = []
    for a in addresses:
        row = delivery[a]
        ready.require(type(row) is MappingProxyType and set(row) == descriptor.fields(tier),
                      "delivery field population differs")
        values = {}
        for key, value in row.items():
            if key.startswith("g_"):
                ready.require(type(value) is float, "native factual return must retain float type")
                bridge.finite(value, key)
                values[key] = value.hex()
            else:
                ready.require(type(value) is int, "action/proposal fields must retain true integer type")
                values[key] = value
        out.append([descriptor.domain.canonical(a), values])
    return out


def prepare_cell(prepared, arms, *, assisted=None):
    """Prepare one inherited same-tier cell, retaining its entire projection.

    D/X candidate resolution uses the *closed factual rows* at every visited
    pre-action t, not a supplied evaluator trace. Engineering tests compare it
    against original rho_D/rho_X on real seedless traces. B1's original address
    validators/builders/delivery projection remain the consumers. P resolution
    calls original rho_P and requires separately explicit AssistedInput at L1
    AND its L3 alias. No proposal is read from factual/audit/store information.
    L2 counterfactual target construction is not implemented here and fails stop.
    """
    rows, _, order, decisions, controllers = validate_credit(prepared)
    matrix = bridge.validate_pair(arms)  # Cell authority precedes assisted reads.
    architecture, tier = arms[0].architecture, arms[0].tier
    descriptor = bridge.SLICES[architecture]
    described = descriptor.fields(tier)
    allowed = {"D_Q": tuple(u for u, _ in decisions),
               "X": tuple(u for u, _ in controllers), "P": ("ProcessCommit",)}[architecture]
    units = tuple(u for u in prepared.expanded_units if u in allowed)
    if architecture != "P" or not units:
        ready.require(assisted is None, "unsanctioned or unused assisted input refused")
    if architecture == "D_Q" and tier is Tier.L2_COUNTERFACTUAL and units:
        raise ready.ProtocolError("L2 needs a separately bound counterfactual episode/adapter; no L0 fallback")
    envelope = None
    if architecture == "D_Q":
        by_unit = dict(decisions)
        addresses = tuple(by_unit[u] for u in units)
        for a in addresses:
            descriptor.domain.require_credited(a)
        if units and described:
            envelope = build_factual_envelope(rows, addresses)
        evidence = MappingProxyType({"addresses": addresses, "rows": rows})
    elif architecture == "X":
        by_unit = dict(controllers)
        addresses = tuple(by_unit[u] for u in units)
        for a in addresses:
            descriptor.domain.require_credited(a)
        require_admissible_sites(addresses, rows)  # also mandatory at L3
        if units and described:
            envelope = build_controller_envelope(rows, addresses)
        evidence = MappingProxyType({"sites": addresses, "rows": rows})
    else:
        if units:
            ready.require(type(assisted) is AssistedInput, "P requires explicit nominal assisted input")
            addresses = resolve_process_addresses(units, assisted)
            if described:
                envelope = build_process_envelope(addresses, assisted)
        else:
            addresses = ()
        evidence = MappingProxyType({"units": units, "assisted": assisted})
    ready.require(len(addresses) == len(units) and len(set(addresses)) == len(addresses),
                  "credit address count/injectivity differs; no silent deduplication")
    # Both arms in one cell receive the SAME object, not independent choices.
    delivery = descriptor.deliver(tier, addresses, envelope) if units else None
    canonical_delivery = _delivery_payload(delivery, addresses, descriptor, tier)
    audit = {"schema": "a96-b2-credit-cell-preparation-v1",
        "role": "PURE_TRUTH_BLIND_EXPANSION_AND_TIER_PREPARATION_NOT_COLLECTION",
        "representation": prepared.kind, "native_proposal_units": sorted(prepared.proposal.units),
        "factual_rows": [list(r[:-1]) + [float(r[-1]).hex()] for r in rows],
        "episode_domain_in_frozen_static_then_chronological_order": list(order),
        "all_expanded_units": list(prepared.expanded_units), "matrix_cell": matrix,
        "cell_credited_units": list(units),
        "other_writeable_channels_retained_not_reclassified": [u for u in prepared.expanded_units
            if u not in units and u not in NONWRITEABLE],
        "nonwriteable_predictions_retained": [u for u in prepared.expanded_units if u in NONWRITEABLE],
        "canonical_addresses": [descriptor.domain.canonical(a) for a in addresses],
        "same_tier_delivery": canonical_delivery,
        "delivered_to_both_roles_by_one_cell_projection": True,
        "route": "CELL_PREPARED_NOT_EXECUTED" if units else "NO_CREDIT_IN_THIS_CELL_NOT_ZERO_FILLED",
        "diagnostic_algorithm_executed": False, "actual_failure_origin_authenticated": False,
        "assisted_source_authority_authenticated": False,
        "B1_executed": False, "future_training_episodes": 0, "environment_seed_draws": 0,
        "collection_authorized": False, "scientific_claim_authorized": False}
    return CellPreparation(prepared, arms, units, addresses, evidence, (delivery, delivery),
        MappingProxyType(audit), bridge.sha(audit))


def single_credited_site(cell):
    """No silent first/min/truth-best selection for the single-site B2 instrument.

    This helper refuses *any* residual set-valued prediction, including a second
    architecture or nonwriteable unit. A full set-valued budget/aggregation/NoWrite
    policy must be separately preregistered; this code chooses none of it.
    """
    ready.require(type(cell) is CellPreparation and type(cell.b1_evidence) is MappingProxyType
        and type(cell.audit) is MappingProxyType and type(cell.addresses) is tuple
        and type(cell.credited_units) is tuple and type(cell.deliveries) is tuple
        and len(cell.deliveries) == 2, "exact prepared cell packet required")
    matrix = bridge.validate_pair(cell.arms)
    assisted = cell.b1_evidence.get("assisted") if matrix["architecture"] == "P" else None
    expected = prepare_cell(cell.prepared, cell.arms, assisted=assisted)
    descriptor = bridge.SLICES[matrix["architecture"]]
    for a in cell.addresses:
        descriptor.domain.require_credited(a)
    ready.require(type(cell.credited_units) is tuple and all(type(u) is str for u in cell.credited_units),
                  "cell credited unit types differ")
    if "rows" in expected.b1_evidence:
        rows = cell.b1_evidence.get("rows")
        ready.require(type(rows) is tuple and len(rows) == len(expected.b1_evidence["rows"]),
                      "B1 row population differs")
        for row, original in zip(rows, expected.b1_evidence["rows"]):
            ready.require(type(row) is tuple and len(row) == 10, "closed B1 row required")
            bridge.finite(row[-1], "bound B1 factual reward")
            ready.require(all(type(v) is int for v in row[:-1])
                and row[:-1] == original[:-1] and type(row[-1]) is type(original[-1])
                and float(row[-1]).hex() == float(original[-1]).hex(),
                "B1 evidence row types/reward bytes differ")
    actual_delivery = _delivery_payload(cell.deliveries[0], expected.addresses,
        descriptor, expected.arms[0].tier)
    ready.require(dict(cell.b1_evidence) == dict(expected.b1_evidence)
        and cell.addresses == expected.addresses and cell.credited_units == expected.credited_units
        and cell.deliveries[0] is cell.deliveries[1]
        and actual_delivery == expected.audit["same_tier_delivery"]
        and bridge.sha(dict(cell.audit)) == cell.audit_sha256 == expected.audit_sha256,
        "cell evidence/audit differs from recomputed preparation")
    ready.require(len(expected.addresses) == 1 and len(expected.credited_units) == 1
        and expected.prepared.expanded_units == expected.credited_units,
        "single-site B2 cannot silently discard a set-valued prediction")
    return CreditedSite(expected.arms[0].architecture, expected.addresses[0])
