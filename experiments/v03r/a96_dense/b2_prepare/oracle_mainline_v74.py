"""Direct Oracle -> whole native B1 -> protected future-start preparation.

Independent addon, not a selected scientific family or a collection entry point.
No ordinary diagnosis, new law, joint Collateral formula, seed, RNG or trainer.
v74 extends the preserved v73 source in a separate namespace: original L2 replay,
patch L1/L3 and independent full-store scalar accounting. No calibration gate waiver.
Opaque handles authenticate this module's in-process ownership, not hostile Python.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
import json
import math
from pathlib import Path
from types import MappingProxyType
from weakref import WeakKeyDictionary

import readiness as ready
import factual_event_candidate as factual
import credit_delivery_candidate as projection
from rfl_rebuild.b1 import laws
from rfl_rebuild.b1 import counterfactual as native_cf
from rfl_rebuild.b1 import runner as native_b1
from rfl_rebuild.b1.contract import (
    APPLIED, EVALUABLE_NOOP, NO_VALID_ALTERNATIVE, DecisionWriteReceipt,
    UpdateLedger, fingerprint)
from rfl_rebuild.b1.controller import resolve_controller_sites
from rfl_rebuild.b1.process import AssistedInput, resolve_process_addresses
from rfl_rebuild.b1.targets import resolve_credited_units
from rfl_rebuild.b1.tier import DQ_SLICE, PATCH_SLICE, P_SLICE, X_SLICE, Tier
from rfl_rebuild.b2.environment import learner_channels
from rfl_rebuild.b2.evalorder import prefix, prefix_digest
from rfl_rebuild.b2.unaffected import EvaluationScene
from rfl_rebuild.env import kernel as K
from rfl_rebuild.env.observation import learner_rows
from rfl_rebuild.learner.reference import QReferenceView
from rfl_rebuild.learner.store import LearnerPersistentState, LearnerSnapshot
from rfl_rebuild.method.credit import OracleCreditAdapter
from rfl_rebuild.method.runner import make_evidence
from rfl_rebuild.solve.dp import ReferenceSolution

SLICES = MappingProxyType({"D_Q": DQ_SLICE, "D_patch": PATCH_SLICE,
                         "X": X_SLICE, "P": P_SLICE})
_VIEWS = ("decision_overrides", "process_overrides", "controller_overrides", "q_overrides")
_VIEW = {"D_Q": "q_overrides", "D_patch": "decision_overrides",
         "X": "controller_overrides", "P": "process_overrides"}
_ROLES = ("reference", "treatment")
_PATHS = tuple(Path(m.__file__) for m in (ready, factual, projection, native_b1, laws, native_cf)) + (Path(__file__),)
_BINDING = tuple(sha256(p.read_bytes()).hexdigest() for p in _PATHS)


def _sha(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode("utf-8")).hexdigest()


def _stores(state):
    # Full actual entries, not a fingerprint-only equality test.
    return tuple(dict(getattr(state, n)) for n in _VIEWS)


def _store_wire(state):
    ready.require(type(state) in (LearnerPersistentState, LearnerSnapshot), "exact full-store representation required")
    snap = state.snapshot() if type(state) is LearnerPersistentState else state
    def address(a):
        s = a.state
        base = [s.x, s.y, s.t, s.kappa, s.phi]
        if hasattr(a, "z"):
            return base + [a.z, a.m] + ([a.a] if hasattr(a, "a") else [])
        return base + [a.cmd]
    return {
        "D": sorted([[address(a), v] for a, v in snap.decision_overrides.items()]),
        "P": sorted([[a, v] for a, v in snap.process_overrides.items()]),
        "X": sorted([[address(a), v] for a, v in snap.controller_overrides.items()]),
        "Q": sorted([[address(a), float(v).hex()] for a, v in snap.q_overrides.items()])}


def _guard(parent=None):
    ready.require(tuple(sha256(p.read_bytes()).hexdigest() for p in _PATHS) == _BINDING,
                  "addon/dependency bytes changed since loading")
    if parent is not None:
        ready.require(all(ready.file_hash(ready.ROOT / n) == h
                          for n, h in parent["sources"].items()), "frozen parent source drift")


class OwnedOracleSource:
    __slots__ = ("__weakref__",)
    def __new__(cls):
        raise ready.ProtocolError("source requires its actual owned factual construction")


class OwnedOraclePair:
    __slots__ = ("__weakref__",)
    def __new__(cls):
        raise ready.ProtocolError("pair requires this source's complete native B1 execution")


class OwnedOracleFutureInputs:
    __slots__ = ("__weakref__",)
    def __new__(cls):
        raise ready.ProtocolError("future inputs require this owned immediate pair")


@dataclass(frozen=True, slots=True)
class _Source:
    pre: object
    scene: object
    regime: str
    reference: object
    parent: object
    healthy: object
    trace: object
    evidence: object
    truth: object
    payload: object
    seal: str
    episode: object
    solution: object


@dataclass(frozen=True, slots=True)
class _Projection:
    whole_units: tuple
    cell_units: tuple
    addresses: tuple
    residual_units: tuple


@dataclass(frozen=True, slots=True)
class _Pair:
    source: object
    architecture: str
    tier: object
    law_name: str
    projected: object
    assisted: object
    clones: tuple
    results: tuple
    payload: object
    seal: str


@dataclass(frozen=True, slots=True)
class _Future:
    pair: object
    source: object
    template: object
    starts: tuple
    payload: object
    seal: str


_SOURCES = WeakKeyDictionary()
_PAIRS = WeakKeyDictionary()
_FUTURES = WeakKeyDictionary()
_CONSUMED = WeakKeyDictionary()


def _ordered_oracle(evidence, gamma):
    """Pure evaluator projection; never turn Oracle truth into CausalProposal."""
    _, _, order, _, _ = projection.factual_projection(evidence)
    ready.require(type(gamma) is tuple and gamma and all(type(u) is str for u in gamma)
                  and len(gamma) == len(set(gamma)), "complete typed unique nonempty truth required")
    ready.require(set(gamma) <= set(order), "truth names a unit outside this actual episode")
    oracle = OracleCreditAdapter.evaluate(gamma)
    ready.require(oracle == frozenset(gamma), "Oracle changed the given truth population")
    return tuple(u for u in order if u in oracle)


def _project(evidence, gamma, architecture, assisted=None):
    ready.require(type(architecture) is str and architecture in SLICES, "closed architecture required")
    _, _, _, decisions, controllers = projection.factual_projection(evidence)
    whole = _ordered_oracle(evidence, gamma)
    if architecture in ("D_Q", "D_patch"):
        by_unit = dict(decisions)
    elif architecture == "X":
        by_unit = dict(controllers)
    else:
        by_unit = {"ProcessCommit": None}
    units = tuple(u for u in whole if u in by_unit)
    if architecture == "P" and units:
        addresses = tuple(resolve_process_addresses(units, assisted))
    else:
        ready.require(assisted is None, "unused/foreign assistance is refused")
        addresses = tuple(by_unit[u] for u in units)
    ready.require(len(addresses) == len(units) == len(set(addresses)),
                  "every projected real owner must survive exactly once")
    for a in addresses:
        SLICES[architecture].domain.require_credited(a)
    return _Projection(whole, units, addresses, tuple(u for u in whole if u not in units))


def _registered(architecture, tier, law_name):
    ready.require(type(architecture) is str and architecture in SLICES
                  and type(tier) is Tier and type(law_name) is str, "typed registered cell required")
    SLICES[architecture].require_implemented(tier)
    if architecture == "D_patch":
        # Original patch registry carries one L0 NoWrite class. The original
        # tier-valued reference is used at L1/L3, without changing any registry.
        registry = laws.LAWS + ((laws.NoWriteRef(tier),) if tier is not Tier.L0_FACTUAL else ())
    else:
        registry = {"D_Q": laws.DQ_LAWS, "X": laws.X_LAWS, "P": laws.P_LAWS}[architecture]
    treatments = [x for x, m in zip(registry, laws.law_metadata(registry))
                  if x.name == law_name and x.tier is tier and m[1] != "reference"]
    refs = [x for x, m in zip(registry, laws.law_metadata(registry))
            if x.tier is tier and m[1] == "reference"]
    ready.require(len(treatments) == len(refs) == 1, "one original treatment and same-tier NoWrite required")
    return refs[0], treatments[0]


def _episode_wire(episode):
    return {"kappa": episode.kappa, "phase": episode.phi,
            "tape": [episode.tape.phase, episode.tape.error_flag, episode.tape.cause_rank],
            "snapshot_pre": _store_wire(episode.snapshot_pre),
            "reference_sha256": episode.reference.digest(),
            "mask": factual._mask_payload(episode.mask, episode.option_fault),
            "base_option": episode.base_option, "reward_mode": episode.reward_mode,
            "interventions": [repr(x) for x in episode.interventions.members]}


def capture_oracle_source(pre_state, *, scene, regime, q_reference, healthy_reference,
                          mask=None, option_fault=None, counterfactual=False):
    """Own one deterministic factual episode. No trace/truth/callback/seed input.

    This is newly authored engineering code, not a runtime claim. Source capture
    is not native calibration, sampling or permission to collect science.
    """
    _guard()
    parent = ready.load_parent()
    ready.validate_reference(healthy_reference, parent)
    ready.require(type(pre_state) is LearnerPersistentState and type(scene) is EvaluationScene
                  and type(q_reference) is QReferenceView, "exact native source inputs required")
    scene.__post_init__()
    ready.require(type(regime) is str and regime in ("T", "P"), "separate T/P only")
    ready.require(q_reference.digest() == healthy_reference["q_reference_sha256"], "shared Q reference differs")
    mask = K.FaultMask() if mask is None else mask
    factual._strict_mask(mask, option_fault)
    pre = pre_state.clone()
    ready.require(pre is not pre_state and _stores(pre) == _stores(pre_state), "independent full-pre clone required")
    snap = pre.snapshot()
    ready.require(snap.healthy if regime == "T" else not snap.healthy, "regime baseline differs")
    if regime == "P":
        ready.require(mask == K.FaultMask() and option_fault is None, "P plus transient is not P")
    ready.require(type(counterfactual) is bool, "explicit bool CF source mode required")
    ready.require(not counterfactual or not snap.decision_overrides,
                  "original CfEpisode is Q-decision-only, not a patch substitution")
    solution = ReferenceSolution(q=q_reference.rows, v=MappingProxyType({}),
                                 policy=MappingProxyType({}), horizon=K.HORIZON)
    episode = None
    before = fingerprint(pre)
    provider, controller = learner_channels(snap, q_reference)
    try:
        if counterfactual:
            episode = native_cf.CfEpisode(kappa=scene.kappa, tape=scene.tape,
                snapshot_pre=snap, reference=q_reference, base_option=scene.base_option,
                mask=deepcopy(mask), option_fault=option_fault)
            trace = episode.factual_trace
        else:
            trace = K.rollout(kappa=scene.kappa, tape=scene.tape, base_option=scene.base_option,
                              command_provider=provider, controller=controller,
                              learner_process_commit=snap.process_commit_provider(),
                              mask=deepcopy(mask), option_fault=option_fault)
    finally:
        _guard(parent)
        ready.require(fingerprint(pre) == before, "factual source mutated its learner")
    ready.require(type(trace) is K.RolloutTrace and trace.steps and trace.steps[-1].terminal is True
                  and trace.steps[-1].outcome == trace.outcome
                  and trace.outcome in (K.Outcome.SUCCESS,) + factual.FAILURES
                  and trace.base_option == scene.base_option and trace.mask == mask
                  and not trace.interventions.members and trace.option_in_force ==
                  (option_fault if option_fault is not None else snap.process_overrides.get(
                      scene.base_option, scene.base_option)), "complete native source provenance differs")
    raw = factual._trace_payload(trace, scene)  # Capture BEFORE deriving truth.
    truth = evidence = None
    route = "SUCCESS_NO_REFLECTION"
    if trace.outcome != K.Outcome.SUCCESS:
        truth = (factual._persistent_truth(trace, scene, q_reference) if regime == "P"
                 else factual._transient_truth(trace, scene, mask, q_reference))
        gamma = truth["Gamma_P_star" if regime == "P" else "Gamma_T_star"]
        route = "P_FAILURE_WITHOUT_MANIFESTATION_NO_REFLECTION"
        if gamma:
            evidence = make_evidence(learner_rows(trace, scene.kappa, scene.phase),
                                     trace.option_in_force, scene.kappa, scene.phase)
            _ordered_oracle(evidence, tuple(gamma))
            route = "COMPLETE_ORACLE_CREDIT_READY_NOT_DIAGNOSTIC_RUN"
    payload = {"regime": regime, "route": route, "scene": list(scene.key),
               "owned_cf_configuration": _episode_wire(episode) if episode is not None else None,
               "full_pre_stores": _store_wire(pre), "fingerprint_pre": before,
               "raw_factual": raw, "truth_evaluator_only": truth,
               "trace_metadata": {"outcome": trace.outcome, "base_option": trace.base_option,
                   "option_in_force": trace.option_in_force,
                   "faults": factual._mask_payload(trace.mask, None)},
               "parent_sources_digest": parent["sources_digest"], "lock_sha256": parent["lock_sha256"],
               "healthy_reference_sha256": _sha(healthy_reference),
               "q_reference_sha256": q_reference.digest(),
               "diagnostic_method_calls": 0, "science_acquisition_origin_authenticated": False}
    handle = object.__new__(OwnedOracleSource)
    _SOURCES[handle] = _Source(pre, scene, regime, q_reference, parent,
                              deepcopy(healthy_reference), trace, evidence, deepcopy(truth),
                              deepcopy(payload), _sha(payload), episode, solution)
    _CONSUMED[handle] = set()
    _checked_source(handle)
    return handle


def _checked_source(handle):
    ready.require(type(handle) is OwnedOracleSource and handle in _SOURCES, "issued source, not nominal/hash, required")
    d = _SOURCES[handle]
    _guard(d.parent)
    ready.validate_reference(d.healthy, d.parent)
    ready.require(type(d.solution) is ReferenceSolution and d.solution.q is d.reference.rows
                  and not d.solution.v and not d.solution.policy and d.solution.horizon == K.HORIZON,
                  "sealed same-reference alternative source changed")
    if d.episode is not None:
        ready.require(type(d.episode) is native_cf.CfEpisode and d.episode.factual_trace is d.trace
                      and _stores(d.episode.snapshot_pre) == _stores(d.pre)
                      and d.episode.reference is d.reference
                      and _episode_wire(d.episode) == d.payload["owned_cf_configuration"],
                      "owned full CF configuration or pre-source changed")
    else:
        ready.require(d.payload["owned_cf_configuration"] is None, "missing CF episode")
    ready.require(type(d.regime) is str and d.regime in ("T", "P")
                  and d.regime == d.payload["regime"] and list(d.scene.key) == d.payload["scene"]
                  and _sha(d.payload) == d.seal and _store_wire(d.pre) == d.payload["full_pre_stores"]
                  and fingerprint(d.pre) == d.payload["fingerprint_pre"]
                  and d.reference.digest() == d.payload["q_reference_sha256"]
                  and _sha(d.healthy) == d.payload["healthy_reference_sha256"]
                  and factual._trace_payload(d.trace, d.scene) == d.payload["raw_factual"],
                  "source/configuration/full stores/raw changed")
    ready.require(type(d.trace) is K.RolloutTrace and d.trace.steps and
                  d.trace.steps[-1].terminal is True and d.trace.steps[-1].outcome == d.trace.outcome
                  and not d.trace.interventions.members and
                  {"outcome": d.trace.outcome, "base_option": d.trace.base_option,
                   "option_in_force": d.trace.option_in_force,
                   "faults": factual._mask_payload(d.trace.mask, None)} == d.payload["trace_metadata"],
                  "source native terminal/configuration metadata changed")
    expected_truth = None
    route = "SUCCESS_NO_REFLECTION"
    if d.trace.outcome != K.Outcome.SUCCESS:
        ready.require(d.trace.outcome in factual.FAILURES, "source has a nonnative outcome")
        expected_truth = (factual._persistent_truth(d.trace, d.scene, d.reference) if d.regime == "P"
                          else factual._transient_truth(d.trace, d.scene, d.trace.mask, d.reference))
        gamma = expected_truth["Gamma_P_star" if d.regime == "P" else "Gamma_T_star"]
        route = ("COMPLETE_ORACLE_CREDIT_READY_NOT_DIAGNOSTIC_RUN" if gamma
                 else "P_FAILURE_WITHOUT_MANIFESTATION_NO_REFLECTION")
    ready.require(d.truth == expected_truth == d.payload["truth_evaluator_only"]
                  and route == d.payload["route"]
                  and (d.evidence is not None) == (route == "COMPLETE_ORACLE_CREDIT_READY_NOT_DIAGNOSTIC_RUN"),
                  "regime truth/failure-first source route changed")
    if d.evidence is not None:
        expected = make_evidence(learner_rows(d.trace, d.scene.kappa, d.scene.phase),
                                 d.trace.option_in_force, d.scene.kappa, d.scene.phase)
        ready.require(d.evidence == expected and d.truth == d.payload["truth_evaluator_only"],
                      "source learner projection/truth changed")
        gamma = tuple(d.truth["Gamma_P_star" if d.regime == "P" else "Gamma_T_star"])
        _ordered_oracle(d.evidence, gamma)
    return d


def _validate_result(result, clone, source, projected, architecture, *, reference):
    spec = SLICES[architecture]
    ready.require(type(result) is native_b1.B1Result and result.post_state is clone
                  and type(clone) is LearnerPersistentState, "native result lost its actual state")
    ledger = result.ledger
    ready.require(type(ledger) is UpdateLedger and type(ledger.receipts) is tuple
                  and len(ledger.receipts) == len(projected.addresses)
                  and ledger.scalar_metrics_applicable is spec.scalar
                  and ledger.fingerprint_pre == fingerprint(source.pre)
                  and ledger.fingerprint_post == fingerprint(clone), "complete immediate ledger differs")
    before, after = spec.view(source.pre), spec.view(clone)
    for view in _VIEWS:
        if view != _VIEW[architecture]:
            ready.require(dict(getattr(source.pre, view)) == dict(getattr(clone, view)),
                          "write escaped its architecture")
    changed = {a for a in set(before) | set(after) if before.get(a) != after.get(a)}
    ready.require(all(spec.domain.owner(a) in projected.addresses for a in changed),
                  "write escaped the full credited owner set")
    for receipt, address in zip(ledger.receipts, projected.addresses):
        ready.require(type(receipt) is DecisionWriteReceipt and receipt.address == address
                      and type(receipt.address) is type(address)
                      and receipt.canonical_form == spec.domain.canonical(address)
                      and receipt.status in (APPLIED, EVALUABLE_NOOP, NO_VALID_ALTERNATIVE)
                      and type(receipt.store_changed) is bool
                      and receipt.store_changed == any(spec.domain.owner(a) == address for a in changed),
                      "per-owner receipt changed, disappeared or was filtered")
    ready.require(type(ledger.n_scalar) is int and ledger.n_scalar >= 0
                  and all(type(v) in (int, float) and math.isfinite(v) and v >= 0
                          for v in (ledger.sum_abs_delta, ledger.max_abs_delta)),
                  "typed finite scalar accounting required")
    deltas = []
    if spec.scalar:
        # Independent observed full-store differences, not the law plan or native
        # scalar helper. Sparse absence is the injected effective Q*, never zero.
        for entry in sorted(changed, key=lambda a: (a.state.x, a.state.y, a.state.t,
                            a.state.kappa, a.state.phi, a.z, a.m, a.a)):
            was = before[entry] if entry in before else source.reference.value(entry)
            now = after[entry] if entry in after else source.reference.value(entry)
            deltas.append(abs(float(now) - float(was)))
    expected_scalar = (len(deltas), math.fsum(deltas), max(deltas, default=0.0))
    ready.require(ledger.n_scalar == expected_scalar[0]
                  and float(ledger.sum_abs_delta).hex() == expected_scalar[1].hex()
                  and float(ledger.max_abs_delta).hex() == expected_scalar[2].hex(),
                  "ledger differs from independent full-store scalar accounting")
    ledger.check_fingerprint_invariants()
    if reference:
        ready.require(_stores(clone) == _stores(source.pre) and
                      all(r.status == EVALUABLE_NOOP and not r.store_changed for r in ledger.receipts),
                      "same-tier NoWrite changed the full learner")
    return {"full_post_stores": _store_wire(clone), "ledger_canonical": ledger.canonical(),
            "ordered_receipts": [[r.canonical_form, r.status, r.store_changed] for r in ledger.receipts]}


def _apply_original(law, clone, source, projected, architecture, assisted):
    rows = projection.factual_projection(source.evidence)[0]
    if architecture == "D_Q":
        if law.tier is Tier.L2_COUNTERFACTUAL:
            ready.require(source.episode is not None, "L2 requires its owned config-generated factual episode")
            return native_b1.run_dq_law(law, clone, projected.addresses, rows, source.reference,
                                         sol=source.solution, episode=source.episode)
        return native_b1.run_dq_law(law, clone, projected.addresses, rows, source.reference)
    if architecture == "D_patch":
        return native_b1.run_patch_law(law, clone, projected.cell_units, source.trace,
                                       source.scene.kappa, source.scene.phase, source.solution)
    if architecture == "X":
        return native_b1.run_controller_law(law, clone, projected.addresses, rows)
    return native_b1.run_process_law(law, clone, projected.cell_units, assisted)


def run_oracle_pair(source, *, architecture, tier, law_name, assisted=None):
    """Each inherited arm receives its ENTIRE cell once. Never per-address loops.

    Mark a cell consumed before the first native call. A failed/partial execution
    issues no pair; no retry or usable partial result is provided.
    """
    d = _checked_source(source)
    originals = _registered(architecture, tier, law_name)
    ready.require(tier is not Tier.L2_COUNTERFACTUAL or d.episode is not None,
                  "L2 cannot borrow a general/patch factual source or fall back")
    key = (architecture, tier, law_name)
    ready.require(key not in _CONSUMED[source], "this source/cell was already attempted; no retry")
    projected = None
    clones = results = ()
    route = d.payload["route"]
    if d.evidence is not None:
        gamma = tuple(d.truth["Gamma_P_star" if d.regime == "P" else "Gamma_T_star"])
        projected = _project(d.evidence, gamma, architecture, assisted)
        if architecture == "P" and projected.cell_units:
            ready.require(assisted.z_proposal == d.scene.base_option, "explicit proposal differs from owned source")
        if architecture in ("D_Q", "D_patch"):
            native_addresses = tuple(resolve_credited_units(projected.cell_units, d.trace,
                                      d.scene.kappa, d.scene.phase))
        elif architecture == "X":
            native_addresses = tuple(resolve_controller_sites(projected.cell_units, d.trace,
                                      d.scene.kappa, d.scene.phase))
        else:
            native_addresses = projected.addresses
        ready.require(native_addresses == projected.addresses, "native rho differs from complete projection")
        route = "NO_CREDIT_IN_CELL_NO_FAKE_LEDGER_OR_FUTURE"
        if projected.addresses:
            _CONSUMED[source].add(key)
            clones = tuple(d.pre.clone() for _ in originals)
            ready.require(clones[0] is not clones[1] and
                          all(c is not d.pre and _stores(c) == _stores(d.pre) for c in clones),
                          "two distinct identical full-pre states required")
            collected = []
            try:
                for law, clone in zip(originals, clones):
                    collected.append(_apply_original(law, clone, d, projected, architecture, assisted))
                results = tuple(collected)
            finally:
                _checked_source(source)
            route = "COMPLETE_ORACLE_WHOLE_B1_PAIR"
    ready.require(projected is not None or assisted is None, "skipped reflection cannot consume assistance")
    arms = [_validate_result(r, c, d, projected, architecture, reference=i == 0)
            for i, (r, c) in enumerate(zip(results, clones))]
    payload = {"route": route, "source_sha256": d.seal, "architecture": architecture,
               "tier": tier.name, "original_laws": [x.name for x in originals],
               "whole_oracle_units": list(projected.whole_units) if projected else None,
               "cell_units": list(projected.cell_units) if projected else None,
               "residual_units_preserved": list(projected.residual_units) if projected else None,
               "all_owner_receipts": arms, "native_B1_arm_calls": len(results),
               "primary_Collateral": None, "scientific_PASS": False}
    handle = object.__new__(OwnedOraclePair)
    _PAIRS[handle] = _Pair(source, architecture, tier, law_name, projected, assisted,
                          clones, results, deepcopy(payload), _sha(payload))
    _checked_pair(handle, source)
    return handle


def _checked_pair(handle, source):
    ready.require(type(handle) is OwnedOraclePair and handle in _PAIRS, "issued complete pair required")
    d = _PAIRS[handle]
    ready.require(d.source is source, "pair belongs to another source")
    sd = _checked_source(source)
    ready.require(_sha(d.payload) == d.seal and d.payload["source_sha256"] == sd.seal,
                  "pair content/source seal changed")
    _registered(d.architecture, d.tier, d.law_name)
    if d.projected is not None:
        gamma = tuple(sd.truth["Gamma_P_star" if sd.regime == "P" else "Gamma_T_star"])
        ready.require(d.projected == _project(sd.evidence, gamma, d.architecture, d.assisted),
                      "whole credit/cell projection changed")
    ready.require(len(d.results) == len(d.clones) == d.payload["native_B1_arm_calls"]
                  and len(d.results) in (0, 2), "partial native pair refused")
    if d.results:
        ready.require(d.clones[0] is not d.clones[1] and all(c is not sd.pre for c in d.clones),
                      "immediate states alias")
    expected = [_validate_result(r, c, sd, d.projected, d.architecture, reference=i == 0)
                for i, (r, c) in enumerate(zip(d.results, d.clones))]
    ready.require(expected == d.payload["all_owner_receipts"], "immediate post-state/ledger changed")
    return d


def pair_audit(handle, source):
    d = _checked_pair(handle, source)
    return deepcopy({"schema": "v74-direct-oracle-whole-b1", "payload": d.payload,
                     "payload_sha256": d.seal, "diagnostic_calls": 0,
                     "keys_allocated": False, "future_training": 0,
                     "collection_authorized": False, "research_complete": False})


def clone_immediate_post(handle, source, *, role):
    ready.require(type(role) is str and role in _ROLES, "explicit registered role required")
    d = _checked_pair(handle, source)
    ready.require(len(d.clones) == 2, "skip/empty has no manufactured post-state")
    pinned = d.clones[_ROLES.index(role)]
    exported = pinned.clone()
    ready.require(exported is not _SOURCES[source].pre and all(exported is not c for c in d.clones)
                  and _stores(exported) == _stores(pinned), "fresh exact requested-role clone required")
    return exported


def _template(parent, healthy):
    """Locked constants and all integer checkpoints; NO seed/protocol/RNG."""
    design = ready.validate_design(parent["lock"])
    vpre = ready.validate_reference(healthy, parent)
    sample = prefix(design["N_eval"])
    return MappingProxyType({"alpha": Fraction(1, 2), "epsilon": Fraction(1, 10),
        "T": design["T"], "grid": tuple(design["grid"]), "sample": sample,
        "v_pre": vpre, "evaluation_sha256": prefix_digest(len(sample)),
        "lock_sha256": parent["lock_sha256"], "healthy_sha256": _sha(healthy)})


def _template_wire(template):
    return {"alpha": [template["alpha"].numerator, template["alpha"].denominator],
            "epsilon": [template["epsilon"].numerator, template["epsilon"].denominator],
            "T": template["T"], "grid": list(template["grid"]),
            "evaluation_units": [list(s.key) for s in template["sample"]],
            "evaluation_sha256": template["evaluation_sha256"],
            "v_pre_hex": template["v_pre"].hex(), "lock_sha256": template["lock_sha256"],
            "healthy_sha256": template["healthy_sha256"], "seed": None}


def prepare_future_inputs(handle, source):
    """Prepare shared design and full immediate clones; do NOT start a future.

    This removes an incidental single-map/diagnostic dependency, not the original
    requirement for valid Collateral and complete gates BEFORE scientific execution.
    """
    pd = _checked_pair(handle, source)
    sd = _checked_source(source)
    template = None
    starts = ()
    if pd.results:
        template = _template(sd.parent, sd.healthy)
        starts = tuple(clone_immediate_post(handle, source, role=r) for r in _ROLES)
    payload = {"pair_sha256": pd.seal, "shared_template": _template_wire(template) if template else None,
               "ordered_full_future_starts": [_store_wire(s) for s in starts],
               "primary_Collateral": None, "collateral_complete": False,
               "native_future_protocol_instantiated": False, "future_training": 0,
               "keys_allocated": False, "collection_authorized": False}
    result = object.__new__(OwnedOracleFutureInputs)
    _FUTURES[result] = _Future(handle, source, template, starts, deepcopy(payload), _sha(payload))
    _checked_future(result, source)
    return result


def _checked_future(handle, source):
    ready.require(type(handle) is OwnedOracleFutureInputs and handle in _FUTURES, "issued future-input handle required")
    d = _FUTURES[handle]
    ready.require(d.source is source, "future inputs belong to another source")
    pd = _checked_pair(d.pair, source)
    sd = _checked_source(source)
    ready.require(_sha(d.payload) == d.seal and d.payload["pair_sha256"] == pd.seal,
                  "future input/pair seal changed")
    ready.require(len(d.starts) == len(pd.results) and len(d.starts) in (0, 2), "partial/fake future starts")
    if d.starts:
        ready.require(_template_wire(d.template) == _template_wire(_template(sd.parent, sd.healthy)),
                      "locked shared design changed")
        ready.require(d.starts[0] is not d.starts[1] and all(
            start is not sd.pre and all(start is not c for c in pd.clones)
            and _stores(start) == _stores(immediate)
            for start, immediate in zip(d.starts, pd.clones)), "future start aliases/drifts from immediate state")
    ready.require([_store_wire(s) for s in d.starts] == d.payload["ordered_full_future_starts"],
                  "complete future-start entries changed")
    return d


def future_inputs_audit(handle, source):
    d = _checked_future(handle, source)
    return deepcopy({"schema": "v74-direct-oracle-future-inputs-not-execution",
                     "payload": d.payload, "payload_sha256": d.seal,
                     "shared_template_object_count": int(d.template is not None),
                     "future_training": 0, "collection_authorized": False})


def clone_future_start(handle, source, *, role):
    ready.require(type(role) is str and role in _ROLES, "explicit registered role required")
    d = _checked_future(handle, source)
    ready.require(len(d.starts) == 2, "skip/empty has no zero-filled future")
    exported = d.starts[_ROLES.index(role)].clone()
    pd = _PAIRS[d.pair]
    ready.require(exported is not _SOURCES[source].pre
                  and all(exported is not s for s in (*d.starts, *pd.clones))
                  and _stores(exported) == _stores(d.starts[_ROLES.index(role)]),
                  "fresh exact future-start export required")
    return exported
