"""Owned configuration -> original whole Oracle pair -> read-only same-source post.
Finite independent addon. Not a scientific Collateral, future outcome or collection gate.
The v74 implementation and all executed evidence remain immutable.
"""
from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from weakref import WeakKeyDictionary
import oracle_mainline_v74 as base

ready = base.ready
K = base.K
_ROLES = ("reference", "treatment")
_PATHS = (Path(__file__), Path(base.__file__))
_BINDING = tuple(sha256(p.read_bytes()).hexdigest() for p in _PATHS)

def _guard():
    ready.require(tuple(sha256(p.read_bytes()).hexdigest() for p in _PATHS) == _BINDING,
                  "new configuration/measurement source bytes changed")
    base._guard()

class OwnedSource:
    __slots__ = ("__weakref__",)
    def __new__(cls):
        raise ready.ProtocolError("configuration must be captured by this entry")
class OwnedPair:
    __slots__ = ("__weakref__",)
    def __new__(cls):
        raise ready.ProtocolError("actual complete original pair required")
class OwnedImmediate:
    __slots__ = ("__weakref__",)
    def __new__(cls):
        raise ready.ProtocolError("actual owned read-only immediate measurement required")
class OwnedFutureInputs:
    __slots__ = ("__weakref__",)
    def __new__(cls):
        raise ready.ProtocolError("actual owned immediate states required")

@dataclass(frozen=True, slots=True)
class _Source:
    native: object
    mask: object
    option_fault: object
    configuration: object
    payload: object
    seal: str
@dataclass(frozen=True, slots=True)
class _Pair:
    source: object
    native: object
    payload: object
    seal: str
@dataclass(frozen=True, slots=True)
class _Immediate:
    pair: object
    source: object
    starts: tuple
    traces: tuple
    payload: object
    seal: str
@dataclass(frozen=True, slots=True)
class _Future:
    pair: object
    source: object
    native: object

_SOURCES = WeakKeyDictionary()
_PAIRS = WeakKeyDictionary()
_IMMEDIATES = WeakKeyDictionary()
_FUTURES = WeakKeyDictionary()
_MEASURED = WeakKeyDictionary()

def _configuration(scene, mask, option_fault, reference):
    base.factual._strict_mask(mask, option_fault)
    return {"scene": list(scene.key), "faults": base.factual._mask_payload(mask, option_fault),
            "reward_mode": "A", "interventions": [],
            "reference_sha256": reference.digest(), "source_policy": "original learner_channels"}

def capture_source(pre_state, *, scene, regime, q_reference, healthy_reference,
                   mask=None, option_fault=None, counterfactual=False):
    """Capture supplied exact descriptors BEFORE native; no trace/truth/seed/callback."""
    _guard()
    ready.require(type(scene) is base.EvaluationScene and type(q_reference) is base.QReferenceView,
                  "exact original scene/reference required")
    scene.__post_init__()
    mask = K.FaultMask() if mask is None else deepcopy(mask)
    configuration = _configuration(scene, mask, option_fault, q_reference)
    native = base.capture_oracle_source(pre_state, scene=scene, regime=regime,
        q_reference=q_reference, healthy_reference=healthy_reference, mask=mask,
        option_fault=option_fault, counterfactual=counterfactual)
    sd = base._checked_source(native)
    payload = {"configuration_declared_before_native": deepcopy(configuration),
               "native_source_sha256": sd.seal, "native_source_payload": deepcopy(sd.payload),
               "scientific_origin_authenticated": False}
    result = object.__new__(OwnedSource)
    _SOURCES[result] = _Source(native, mask, option_fault, deepcopy(configuration),
                              deepcopy(payload), base._sha(payload))
    _checked_source(result)
    return result

def _checked_source(source):
    _guard()
    ready.require(type(source) is OwnedSource and source in _SOURCES, "issued new-source handle required")
    d = _SOURCES[source]
    sd = base._checked_source(d.native)
    expected = _configuration(sd.scene, d.mask, d.option_fault, sd.reference)
    ready.require(d.configuration == expected == d.payload["configuration_declared_before_native"]
                  and base._sha(d.payload) == d.seal
                  and d.payload["native_source_sha256"] == sd.seal
                  and d.payload["native_source_payload"] == sd.payload,
                  "owned configuration/source bytes changed")
    ready.require(sd.trace.mask == d.mask and sd.trace.option_in_force ==
        (d.option_fault if d.option_fault is not None else
         sd.pre.process_overrides.get(sd.scene.base_option, sd.scene.base_option)),
        "declared option/transient configuration differs from actual source")
    if sd.episode is not None:
        ready.require(sd.episode.option_fault == d.option_fault and sd.episode.mask == d.mask,
                      "CF configuration differs from declared source")
    return d, sd

def source_audit(source):
    d, _ = _checked_source(source)
    return deepcopy({"schema": "v75-owned-exact-source-config", "payload": d.payload,
                     "payload_sha256": d.seal})

def run_pair(source, *, architecture, tier, law_name, assisted=None):
    d, _ = _checked_source(source)
    native = base.run_oracle_pair(d.native, architecture=architecture, tier=tier,
                                 law_name=law_name, assisted=assisted)
    audit = base.pair_audit(native, d.native)
    payload = {"source_sha256": d.seal, "original_v74_pair": audit,
               "primary_Collateral": None, "scientific_PASS": False}
    result = object.__new__(OwnedPair)
    _PAIRS[result] = _Pair(source, native, deepcopy(payload), base._sha(payload))
    _MEASURED[result] = False
    _checked_pair(result, source)
    return result

def _checked_pair(pair, source):
    d, sd = _checked_source(source)
    ready.require(type(pair) is OwnedPair and pair in _PAIRS, "issued complete new-pair required")
    pd = _PAIRS[pair]
    ready.require(pd.source is source and base._sha(pd.payload) == pd.seal
                  and pd.payload["source_sha256"] == d.seal
                  and pd.payload["original_v74_pair"] == base.pair_audit(pd.native, d.native),
                  "pair/configuration source differs")
    native = base._checked_pair(pd.native, d.native)
    return d, sd, pd, native

def pair_audit(pair, source):
    _, _, pd, _ = _checked_pair(pair, source)
    return deepcopy({"schema": "v75-config-owned-whole-pair", "payload": pd.payload,
                     "payload_sha256": pd.seal})

def _trace_wire(trace, state, sd, config, role):
    ready.require(type(trace) is K.RolloutTrace and trace.steps and
        trace.steps[-1].terminal is True and trace.steps[-1].outcome == trace.outcome and
        trace.outcome in (K.Outcome.SUCCESS,) + base.factual.FAILURES and
        trace.base_option == sd.scene.base_option and trace.mask == config.mask and
        not trace.interventions.members and trace.option_in_force ==
        (config.option_fault if config.option_fault is not None else
         state.process_overrides.get(sd.scene.base_option, sd.scene.base_option)),
        "immediate complete trace/configuration differs")
    raw = base.factual._trace_payload(trace, sd.scene)
    return {"role": role, "full_immediate_stores": base._store_wire(state),
            "fingerprint": base.fingerprint(state), "raw": raw,
            "outcome": trace.outcome, "return_hex": trace.return_value.hex(),
            "base_option": trace.base_option, "option_in_force": trace.option_in_force,
            "faults": base.factual._mask_payload(trace.mask, config.option_fault),
            "readonly": True}

def measure_immediate(pair, source):
    """One attempt, two exact role clones, SAME captured configuration, no user override.
    This finite engineering replay is NOT a selected scientific post/Collateral endpoint.
    T transients remain here; future inputs below instead start ordinary no-fault learning.
    """
    d, sd, pd, native = _checked_pair(pair, source)
    ready.require(not _MEASURED[pair], "immediate measurement already attempted; no retry")
    starts = traces = ()
    # Success/empty is inapplicable, never a manufactured zero-valued measurement.
    if native.results:
        _MEASURED[pair] = True
        starts = tuple(base.clone_immediate_post(pd.native, d.native, role=r) for r in _ROLES)
        ready.require(starts[0] is not starts[1], "measurement roles alias")
        collected = []
        for state in starts:
            before = base._stores(state)
            snap = state.snapshot()
            provider, controller = base.learner_channels(snap, sd.reference)
            try:
                trace = K.rollout(kappa=sd.scene.kappa, tape=sd.scene.tape,
                    base_option=sd.scene.base_option, command_provider=provider,
                    controller=controller, learner_process_commit=snap.process_commit_provider(),
                    mask=deepcopy(d.mask), option_fault=d.option_fault, reward_mode="A")
                _trace_wire(trace, state, sd, d, _ROLES[len(collected)])
                collected.append(trace)
            finally:
                _checked_pair(pair, source)
                ready.require(base._stores(state) == before, "immediate replay wrote learner state")
        traces = tuple(collected)
    else:
        _MEASURED[pair] = True
    arms = [_trace_wire(t, s, sd, d, r) for t, s, r in zip(traces, starts, _ROLES)]
    payload = {"pair_sha256": pd.seal, "source_sha256": d.seal,
        "exact_configuration": deepcopy(d.configuration),
        "route": "COMPLETE_READONLY_SAME_SOURCE_IMMEDIATE" if arms else "INAPPLICABLE_NO_FAKE_POST",
        "ordered_arms": arms, "native_post_rollout_calls": len(traces),
        "primary_Collateral": None, "future_training": 0, "scientific_PASS": False}
    result = object.__new__(OwnedImmediate)
    _IMMEDIATES[result] = _Immediate(pair, source, starts, traces, deepcopy(payload), base._sha(payload))
    _checked_immediate(result, source)
    return result

def _checked_immediate(handle, source):
    ready.require(type(handle) is OwnedImmediate and handle in _IMMEDIATES, "issued complete measurement required")
    md = _IMMEDIATES[handle]
    ready.require(md.source is source, "measurement belongs to another source")
    d, sd, pd, native = _checked_pair(md.pair, source)
    ready.require(len(md.starts) == len(md.traces) == len(native.results) and
                  len(md.traces) in (0, 2) and base._sha(md.payload) == md.seal
                  and md.payload["pair_sha256"] == pd.seal and md.payload["source_sha256"] == d.seal
                  and md.payload["exact_configuration"] == d.configuration,
                  "partial measurement/configuration/pair changed")
    if md.starts:
        ready.require(md.starts[0] is not md.starts[1] and all(
            s is not sd.pre and all(s is not c for c in native.clones) and
            base._stores(s) == base._stores(c) for s, c in zip(md.starts, native.clones)),
            "measurement start alias/role/full-store drift")
    expected = [_trace_wire(t, s, sd, d, r) for t, s, r in zip(md.traces, md.starts, _ROLES)]
    ready.require(expected == md.payload["ordered_arms"], "complete original raw/role measurement changed")
    return md

def immediate_audit(handle, source):
    md = _checked_immediate(handle, source)
    return deepcopy({"schema": "v75-owned-readonly-immediate-not-science",
                     "payload": md.payload, "payload_sha256": md.seal})

def prepare_future_inputs(pair, source):
    """Owned two full immediate starts and locked shared template only. No training."""
    d, _, pd, _ = _checked_pair(pair, source)
    native = base.prepare_future_inputs(pd.native, d.native)
    result = object.__new__(OwnedFutureInputs)
    _FUTURES[result] = _Future(pair, source, native)
    _checked_future(result, source)
    return result

def _checked_future(handle, source):
    ready.require(type(handle) is OwnedFutureInputs and handle in _FUTURES, "issued future-input handle required")
    fd = _FUTURES[handle]
    ready.require(fd.source is source, "future inputs belong to another source")
    d, _, pd, _ = _checked_pair(fd.pair, source)
    native = base._checked_future(fd.native, d.native)
    ready.require(native.pair is pd.native, "future points at a foreign pair")
    return fd, d

def future_audit(handle, source):
    fd, d = _checked_future(handle, source)
    return base.future_inputs_audit(fd.native, d.native)

def clone_future_start(handle, source, *, role):
    fd, d = _checked_future(handle, source)
    return base.clone_future_start(fd.native, d.native, role=role)
