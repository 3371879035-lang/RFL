"""Owned locked-bank round-zero measurement ingredient, NOT future learning or Collateral.
Original training._mean_return and environment.learned_rollout, no new policy or mean.
Finite SERIAL addon: internally scoped capture hook; no caller callback/state/sample/key.
In-process ownership, not arbitrary hostile Python or portable science authentication.
"""
from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch
from weakref import WeakKeyDictionary
import math
import oracle_mainline_v75 as owner
from rfl_rebuild.b2 import environment, training

base = owner.base
ready = base.ready
K = base.K
_ROLES = ("reference", "treatment")
_PATHS = tuple(Path(m.__file__) for m in (owner, environment, training)) + (Path(__file__),)
_BINDING = tuple(sha256(p.read_bytes()).hexdigest() for p in _PATHS)
_ORIGINAL_MEAN = training._mean_return
_ORIGINAL_LEARNED = environment.learned_rollout
_BUSY = False
_ATTEMPTED = WeakKeyDictionary()
_BANKS = WeakKeyDictionary()

class OwnedBank:
    __slots__ = ("__weakref__",)
    def __new__(cls):
        raise ready.ProtocolError("owned complete original bank measurement required")

@dataclass(frozen=True, slots=True)
class _Bank:
    future: object
    source: object
    starts: tuple
    traces: tuple
    means: tuple
    payload: object
    seal: str

def _guard():
    ready.require(tuple(sha256(p.read_bytes()).hexdigest() for p in _PATHS) == _BINDING,
                  "owned bank/dependency source bytes changed")
    owner._guard()

def _inputs(future, source):
    _guard()
    fd, config = owner._checked_future(future, source)
    native = base._checked_future(fd.native, config.native)
    _, sd = owner._checked_source(source)
    return fd, config, native, sd

def _trace_wire(trace, state, scene, ordinal):
    ready.require(type(trace) is K.RolloutTrace and 1 <= len(trace.steps) <= K.HORIZON
                  and trace.steps[-1].terminal is True
                  and trace.steps[-1].outcome == trace.outcome
                  and trace.outcome in (K.Outcome.SUCCESS,) + base.factual.FAILURES
                  and all(not step.terminal for step in trace.steps[:-1])
                  and trace.base_option == scene.base_option and trace.mask == K.FaultMask()
                  and not trace.interventions.members
                  and trace.option_in_force == state.process_overrides.get(
                      scene.base_option, scene.base_option),
                  "complete ordinary no-fault bank trace differs")
    return {"ordinal": ordinal, "scene": list(scene.key),
            "raw": base.factual._trace_payload(trace, scene),
            "outcome": trace.outcome, "return_hex": trace.return_value.hex(),
            "base_option": trace.base_option, "option_in_force": trace.option_in_force,
            "faults": base.factual._mask_payload(trace.mask, None),
            "interventions": []}

def _ordered_mean(traces):
    # Audit only. Execution uses the ORIGINAL operator, not this reconstruction.
    total = 0.0
    for trace in traces:
        total += trace.return_value
    return total / len(traces)

def _measure_original(state, sample, reference):
    """Capture within one ORIGINAL _mean_return call, restoring global hook in finally.
    No external callback is accepted. SERIAL ownership prevents overlapping hooks.
    """
    ready.require(training.learned_rollout is _ORIGINAL_LEARNED,
                  "original mean-return read path differs")
    before = base._stores(state)
    traces = []
    def capture(learner, *, kappa, tape, base_option, q_reference):
        i = len(traces)
        ready.require(learner is state and q_reference is reference and i < len(sample),
                      "bank role/reference/extra scene differs")
        scene = sample[i]
        ready.require((kappa, tape, base_option) == (scene.kappa, scene.tape, scene.base_option),
                      "bank order/actual configuration differs")
        trace = _ORIGINAL_LEARNED(learner, kappa=kappa, tape=tape,
                                  base_option=base_option, q_reference=q_reference)
        _trace_wire(trace, state, scene, i)
        ready.require(base._stores(state) == before, "bank rollout wrote a store")
        traces.append(trace)
        return trace
    try:
        with patch.object(training, "learned_rollout", capture):
            mean = _ORIGINAL_MEAN(state, sample, q_reference=reference)
    finally:
        ready.require(training.learned_rollout is _ORIGINAL_LEARNED,
                      "original measurement hook not restored")
        ready.require(base._stores(state) == before, "original bank mean wrote learner")
    ready.require(len(traces) == len(sample) == 100 and type(mean) is float
                  and math.isfinite(mean) and mean == _ordered_mean(traces),
                  "incomplete original bank/ordered mean differs")
    return tuple(traces), mean

def _payload(future, source, starts, traces, means):
    fd, config, native, sd = _inputs(future, source)
    arms = []
    if starts:
        ready.require(native.template is not None and len(native.template["sample"]) == 100,
                      "complete locked bank100 required")
        for role, state, rows, mean in zip(_ROLES, starts, traces, means):
            sample = native.template["sample"]
            ready.require(len(rows) == 100 and mean == _ordered_mean(rows),
                          "partial bank/mean differs")
            arms.append({"role": role, "full_start_stores": base._store_wire(state),
                         "fingerprint": base.fingerprint(state),
                         "ordered_scenes": [_trace_wire(t, state, s, i)
                             for i, (t, s) in enumerate(zip(rows, sample))],
                         "original_ordered_mean_hex": mean.hex(), "readonly": True})
    return {"source_sha256": config.seal,
            "future_input_sha256": native.seal,
            "pair_sha256": owner._PAIRS[fd.pair].seal,
            "source_configuration_not_reused_as_bank_faults": deepcopy(config.configuration),
            "shared_locked_template": base._template_wire(native.template) if native.template else None,
            "measurement_mode": "ORIGINAL_ORDINARY_NO_FAULT_BANK100_ROUND_ZERO_INGREDIENT",
            "route": "COMPLETE_ORIGINAL_BANK" if arms else "INAPPLICABLE_NO_FAKE_BANK",
            "ordered_arms": arms, "native_bank_rollout_calls": sum(len(t) for t in traces),
            "training_episodes": 0, "curve_created": False, "keys_allocated": False,
            "primary_Collateral": None, "scientific_effect": None, "scientific_PASS": False}

def measure_bank(future, source):
    """One attempt per ORIGINAL owned pair, even if future handle is prepared again."""
    global _BUSY
    fd, config, native, sd = _inputs(future, source)
    ready.require(not _BUSY and fd.pair not in _ATTEMPTED,
                  "serial bank already attempted; no retry or overlapping capture")
    _ATTEMPTED[fd.pair] = True  # Before clones/first native; partial never gets a handle.
    starts = traces = means = ()
    _BUSY = True
    try:
        if native.starts:
            starts = tuple(owner.clone_future_start(future, source, role=r) for r in _ROLES)
            ready.require(starts[0] is not starts[1], "bank role starts alias")
            collected = []
            for state in starts:
                collected.append(_measure_original(state, native.template["sample"], sd.reference))
            traces = tuple(c[0] for c in collected)
            means = tuple(c[1] for c in collected)
    finally:
        _BUSY = False
        _inputs(future, source)
    payload = _payload(future, source, starts, traces, means)
    result = object.__new__(OwnedBank)
    _BANKS[result] = _Bank(future, source, starts, traces, means, deepcopy(payload), base._sha(payload))
    _checked_bank(result, source)
    return result

def _checked_bank(handle, source):
    ready.require(type(handle) is OwnedBank and handle in _BANKS, "issued complete bank handle required")
    d = _BANKS[handle]
    ready.require(d.source is source, "bank belongs to another source")
    fd, config, native, sd = _inputs(d.future, source)
    ready.require(fd.pair in _ATTEMPTED and len(d.starts) == len(d.traces) == len(d.means)
                  == len(native.starts) and len(d.starts) in (0, 2)
                  and base._sha(d.payload) == d.seal, "partial bank/payload differs")
    if d.starts:
        ready.require(d.starts[0] is not d.starts[1] and all(
            state is not sd.pre and all(state is not s for s in native.starts)
            and base._stores(state) == base._stores(pinned)
            for state, pinned in zip(d.starts, native.starts)), "bank full-store/role/alias differs")
    ready.require(_payload(d.future, source, d.starts, d.traces, d.means) == d.payload,
                  "bank source/template/full ordered raw changed")
    return d

def bank_audit(handle, source):
    d = _checked_bank(handle, source)
    return deepcopy({"schema": "v77-owned-original-bank-ingredient-not-science",
                     "payload": d.payload, "payload_sha256": d.seal})
