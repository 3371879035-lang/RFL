"""Actual owned diagnostic -> whole native B1 pair, SEEDLESS engineering only.

No supplied state/credit/cell/ledger/receipt/reference/callback/seed is accepted.
This closes an in-process component lineage, not a portable SCI execution proof,
hostile-Python sandbox, whole-set U2 policy, future collector or collection gate.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from weakref import WeakKeyDictionary

import readiness as ready
import native_record_candidate as bridge
import credit_delivery_candidate as credit
import counterfactual_source_candidate as owned
import diagnostic_source_candidate as diagnostic
from rfl_rebuild.b1.contract import (APPLIED, EVALUABLE_NOOP, NO_VALID_ALTERNATIVE,
    DecisionWriteReceipt, UpdateLedger, fingerprint)
from rfl_rebuild.b1.laws import AddressPlan, LawPlan
from rfl_rebuild.b1.runner import B1Result, _scalar_accounting
from rfl_rebuild.b1.tier import Tier
from rfl_rebuild.b2.runner import PairedRunner
from rfl_rebuild.learner.store import Edit, LearnerPersistentState


_CODE_PATHS = tuple(Path(m.__file__) for m in (ready, bridge, credit, owned, diagnostic)) + (Path(__file__),)
_CODE_BINDING = tuple(sha256(p.read_bytes()).hexdigest() for p in _CODE_PATHS)
_PARENT_SOURCES = ready.load_parent()["sources"]
_VIEWS = ("decision_overrides", "process_overrides", "controller_overrides", "q_overrides")
_STORE_VIEW = {"D_Q": "q_overrides", "X": "controller_overrides", "P": "process_overrides"}


class OwnedB1Pair:
    __slots__ = ("__weakref__",)

    def __new__(cls):
        raise ready.ProtocolError("pair handles require the actual owned diagnostic and native B1 route")


@dataclass(frozen=True, slots=True)
class _PairData:
    source: object
    diagnostic_run: object
    diagnostic_sha: str
    cell: object
    cell_payload: object
    clones: tuple
    results: tuple
    result_payload: tuple
    route: str
    source_route: str


_PAIRS = WeakKeyDictionary()


def _code_guard():
    ready.require(tuple(sha256(p.read_bytes()).hexdigest() for p in _CODE_PATHS) == _CODE_BINDING,
                  "pair/dependency code changed since module loading")
    ready.require(all(ready.file_hash(ready.ROOT / n) == h for n, h in _PARENT_SOURCES.items()),
                  "frozen parent source bytes changed")


def _cell_payload(cell, run, source):
    ready.require(type(cell) in (credit.CellPreparation, owned.PreparedL2Cell) and
        type(cell.deliveries) is tuple and len(cell.deliveries) == 2,
        "closed original cell and two delivery roles required")
    prepared = diagnostic.diagnostic_credit(run, source)
    ready.require(cell.prepared is prepared, "cell lost the actual diagnostic output identity")
    matrix = bridge.validate_pair(cell.arms)
    if matrix["architecture"] == "D_Q" and cell.arms[0].tier is Tier.L2_COUNTERFACTUAL:
        ready.require(type(cell) is owned.PreparedL2Cell and cell.source is source,
                      "L2 cell must belong to this exact owned source")
        owned.validate_l2_engineering_cell(cell)  # fresh full native targets, never a cached PASS
    else:
        ready.require(type(cell) is credit.CellPreparation, "exact native-credit cell preparation required")
        expected = diagnostic.prepare_diagnosed_cell(run, source, cell.arms)
        ready.require(type(cell.b1_evidence) is MappingProxyType and
            set(cell.b1_evidence) == set(expected.b1_evidence) and
            cell.addresses == expected.addresses and cell.credited_units == expected.credited_units and
            dict(cell.b1_evidence) == dict(expected.b1_evidence), "whole cell/evidence differs from original projection")
        if "rows" in cell.b1_evidence:
            rows = cell.b1_evidence["rows"]
            ready.require(type(rows) is tuple and len(rows) == len(expected.b1_evidence["rows"]),
                          "full original factual rows required")
            for row, original in zip(rows, expected.b1_evidence["rows"]):
                ready.require(type(row) is tuple and all(type(v) is int for v in row[:-1]) and
                    row[:-1] == original[:-1] and type(row[-1]) is float and
                    row[-1].hex() == original[-1].hex(), "factual row types/return bytes differ")
        ready.require(credit._delivery_payload(cell.deliveries[0], cell.addresses,
            bridge.SLICES[matrix["architecture"]], cell.arms[0].tier) == expected.audit["same_tier_delivery"] and
            cell.audit_sha256 == expected.audit_sha256, "same-tier delivery/audit differs")
    ready.require(type(cell.addresses) is tuple and type(cell.credited_units) is tuple and
        len(cell.addresses) == len(cell.credited_units) and len(set(cell.addresses)) == len(cell.addresses) and
        type(cell.deliveries) is tuple and len(cell.deliveries) == 2 and
        cell.deliveries[0] is cell.deliveries[1] and bridge.sha(dict(cell.audit)) == cell.audit_sha256,
        "complete injective cell and one shared delivery required")
    return {"matrix_cell": matrix, "cell_audit_sha256": cell.audit_sha256,
        "all_expanded_units": list(prepared.expanded_units),
        "cell_credited_units": list(cell.credited_units),
        "residual_predictions": [u for u in prepared.expanded_units if u not in cell.credited_units],
        "ordered_addresses": [bridge.SLICES[matrix["architecture"]].domain.canonical(a) for a in cell.addresses]}


def _ledger_payload(result, clone, source_data, cell, *, reference):
    ready.require(type(result) is B1Result and result.post_state is clone and
        type(clone) is LearnerPersistentState, "native B1 result must retain its own clone")
    ledger = result.ledger
    architecture = cell.arms[0].architecture
    spec = bridge.SLICES[architecture]
    ready.require(type(ledger) is UpdateLedger and type(ledger.receipts) is tuple and
        len(ledger.receipts) == len(cell.addresses) and
        type(ledger.scalar_metrics_applicable) is bool and ledger.scalar_metrics_applicable == spec.scalar and
        type(ledger.n_scalar) is int and ledger.n_scalar >= 0 and
        ledger.fingerprint_pre == source_data.fingerprint_pre and ledger.fingerprint_post == fingerprint(clone),
        "whole native ledger types/count/pre/post binding differs")
    before, after = spec.view(source_data.pre_state), spec.view(clone)
    # No edits may escape the declared architecture or credited owners.
    for view in _VIEWS:
        if view != _STORE_VIEW[architecture]:
            ready.require(dict(getattr(source_data.pre_state, view)) == dict(getattr(clone, view)),
                          "native result changed another architecture's store")
    changed = [e for e in set(before) | set(after) if before.get(e) != after.get(e)]
    for entry in changed:
        spec.domain.require_store(entry)
        ready.require(spec.domain.owner(entry) in cell.addresses, "post-state changed an uncredited owner")
    for receipt, address in zip(ledger.receipts, cell.addresses):
        spec.domain.require_credited(address)
        ready.require(type(receipt) is DecisionWriteReceipt and type(receipt.address) is type(address) and
            receipt.address == address and type(receipt.status) is str and
            receipt.status in (APPLIED, EVALUABLE_NOOP, NO_VALID_ALTERNATIVE) and
            type(receipt.store_changed) is bool and type(receipt.canonical_form) is str and
            receipt.canonical_form == spec.domain.canonical(address) and
            receipt.store_changed == any(spec.domain.owner(e) == address for e in changed),
            "every chronological native receipt must describe exactly its credited owner")
    for field in ("sum_abs_delta", "max_abs_delta"):
        ready.require(type(getattr(ledger, field)) is float and bridge.finite(getattr(ledger, field), field) >= 0,
                      "finite native float scalar accounting required")
    ledger.check_fingerprint_invariants()
    if spec.scalar:
        # Recheck actual state deltas using the ORIGINAL created/deleted accounting,
        # sorting and math.fsum, not a newly reconstructed floating moment/formula.
        plans = tuple(AddressPlan(a, tuple(Edit(spec.store, e, after.get(e)) for e in changed
            if spec.domain.owner(e) == a)) for a in cell.addresses)
        n, total, largest = _scalar_accounting(LawPlan("ACTUAL_STATE_DELTA_RECHECK", plans),
            before, after, source_data.reference)
        ready.require(ledger.n_scalar == n and ledger.sum_abs_delta.hex() == total.hex() and
            ledger.max_abs_delta.hex() == largest.hex(), "ledger scalar accounting differs from original actual state deltas")
    else:
        ready.require(ledger.n_scalar == 0 and ledger.sum_abs_delta.hex() == (0.).hex() and
            ledger.max_abs_delta.hex() == (0.).hex(), "non-scalar native slice must not invent scalar cost")
    if reference:
        ready.require(fingerprint(clone) == source_data.fingerprint_pre and
            all(r.status == EVALUABLE_NOOP and not r.store_changed for r in ledger.receipts),
            "registered NoWrite reference must preserve the full learner state")
    return {"native_canonical_ledger": ledger.canonical(),
        "ordered_receipts": [[r.canonical_form, r.status, r.store_changed] for r in ledger.receipts],
        "fingerprint_pre": ledger.fingerprint_pre, "fingerprint_post": ledger.fingerprint_post,
        "n_addressed": ledger.n_addressed, "n_changed_addresses": ledger.n_changed_addresses,
        "scalar_metrics_applicable": ledger.scalar_metrics_applicable, "n_scalar": ledger.n_scalar,
        "sum_abs_delta_hex": ledger.sum_abs_delta.hex(), "max_abs_delta_hex": ledger.max_abs_delta.hex()}


def run_owned_b1_pair(run, source, arms):
    """No scientific sampling/future; apply one complete original B1 pair.

    Skipped reflection reads no arm; actual empty cell gets no ledger or clone.
    The entire projected set is passed to each original B1 entry point once.
    Native errors propagate; no usable partial pair or automatic retry is issued.
    """
    _code_guard()
    d = diagnostic._checked_run(run, source)
    diagnostic_sha = bridge.sha(diagnostic.diagnostic_audit(run, source))
    cell = payload = None; clones = results = result_payload = ()
    route = "SKIPPED_REFLECTION_NO_B1"
    if d.prepared is not None:
        matrix = bridge.validate_pair(arms)
        cell = (diagnostic.prepare_diagnosed_l2_cell(run, source, arms)
            if matrix["architecture"] == "D_Q" and arms[0].tier is Tier.L2_COUNTERFACTUAL
            else diagnostic.prepare_diagnosed_cell(run, source, arms))
        payload = _cell_payload(cell, run, source)
        route = "NO_CREDIT_IN_CELL_NO_B1_NOT_SCIENTIFIC_ZERO"
        if cell.addresses:
            data = owned._checked(source)
            clones = tuple(data.pre_state.clone() for _ in arms)
            ready.require(clones[0] is not clones[1] and all(c is not data.pre_state and
                fingerprint(c) == data.fingerprint_pre for c in clones), "two independent same-pre-state clones required")
            if type(cell) is owned.PreparedL2Cell:
                evidence = MappingProxyType({"addresses": cell.addresses, "rows": cell.rows,
                    "sol": data.solution, "episode": data.episode})
            else:
                evidence = cell.b1_evidence
            collected = []
            try:
                for arm, clone in zip(arms, clones):
                    _cell_payload(cell, run, source)
                    collected.append(PairedRunner._apply(arm, clone, evidence, data.reference))
                results = tuple(collected)
                result_payload = tuple(_ledger_payload(r, c, data, cell, reference=i == 0)
                    for i, (r, c) in enumerate(zip(results, clones)))
            finally:
                _code_guard()
                diagnostic._checked_run(run, source)
                ready.require(bridge.sha(diagnostic.diagnostic_audit(run, source)) == diagnostic_sha,
                              "native B1 changed its actual diagnostic/source binding")
            route = "WHOLE_NATIVE_B1_PAIR_EXECUTED_NOT_B2_COLLECTION"
    handle = object.__new__(OwnedB1Pair)
    _PAIRS[handle] = _PairData(source, run, diagnostic_sha, cell, payload,
        clones, results, result_payload, route, d.route)
    _checked_pair(handle, run, source)
    return handle


def _checked_pair(pair, run, source):
    _code_guard()
    ready.require(type(pair) is OwnedB1Pair and pair in _PAIRS, "issued actual B1 pair required, not a cell/audit/hash")
    d = _PAIRS[pair]
    ready.require(d.source is source and d.diagnostic_run is run, "pair belongs to another actual source/diagnostic call")
    diagnostic._checked_run(run, source)
    ready.require(bridge.sha(diagnostic.diagnostic_audit(run, source)) == d.diagnostic_sha,
                  "actual diagnostic continuity changed after B1")
    if d.cell is None:
        ready.require(d.route == "SKIPPED_REFLECTION_NO_B1" and d.cell_payload is None and
            not d.clones and not d.results and not d.result_payload, "skipped reflection cannot carry B1 results")
    else:
        ready.require(_cell_payload(d.cell, run, source) == d.cell_payload, "cell changed after native B1")
        if not d.cell.addresses:
            ready.require(d.route == "NO_CREDIT_IN_CELL_NO_B1_NOT_SCIENTIFIC_ZERO" and
                not d.clones and not d.results and not d.result_payload, "empty cell cannot fabricate zero ledgers")
        else:
            data = owned._checked(source)
            ready.require(d.route == "WHOLE_NATIVE_B1_PAIR_EXECUTED_NOT_B2_COLLECTION" and
                len(d.clones) == len(d.results) == len(d.result_payload) == 2 and
                d.clones[0] is not d.clones[1] and all(c is not data.pre_state for c in d.clones),
                "complete independent two-arm execution required")
            for i, (r, c, payload) in enumerate(zip(d.results, d.clones, d.result_payload)):
                ready.require(_ledger_payload(r, c, data, d.cell, reference=i == 0) == payload,
                              "native ledger or immediate post-state changed after B1")
    return d


def pair_audit(pair, run, source):
    """Evaluator-only fresh audit; detached JSON cannot issue or transfer a pair."""
    d = _checked_pair(pair, run, source)
    # New lists/dicts; caller cannot mutate the pinned record via audit output.
    payload = {"schema": "a96-owned-whole-B1-pair-candidate-v9", "route": d.route,
        "role": "SEEDLESS_IN_PROCESS_NATIVE_B1_LINEAGE_NOT_SCIENTIFIC_RECEIPT",
        "source_route": d.source_route, "diagnostic_audit_sha256": d.diagnostic_sha,
        "cell": d.cell_payload, "ordered_arm_ledgers": list(d.result_payload),
        "B1_arm_calls": len(d.results), "immediate_post_clones": len(d.clones),
        "source_or_actual_diagnostic_origin_replaced_by_detached_cell": False,
        "old_cell_audit_relabelled_as_scientific_execution": False,
        "whole_set_U2_or_NoWrite_science_policy_selected": False,
        "query_calls_by_diagnostic": 0, "environment_seed_draws": 0, "future_training_episodes": 0,
        "collection_authorized": False, "scientific_claim_authorized": False,
        "science_acquisition_origin_authenticated": False, "research_complete": False}
    return deepcopy(payload)


def clone_immediate_post(pair, run, source, *, role):
    """Export only a fresh clone; never mutate the pinned immediate post-state."""
    ready.require(type(role) is str and role in ("reference", "treatment"), "explicit paired arm role required")
    d = _checked_pair(pair, run, source)
    ready.require(len(d.clones) == 2, "skipped/empty cell has no post-state or zero-filled future")
    pinned = d.clones[("reference", "treatment").index(role)]
    exported = pinned.clone()
    data = owned._checked(source)
    ready.require(type(exported) is LearnerPersistentState and
        all(exported is not c for c in d.clones) and exported is not data.pre_state and
        fingerprint(exported) == fingerprint(pinned),
        "export must be an independent exact-state clone of the requested arm")
    return exported
