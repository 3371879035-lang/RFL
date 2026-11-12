"""Versioned ordinary checkpoint bank for the unchanged v105 normal learner.

This is a read-path optimization, not a learner, policy, TD, or scientific
protocol revision. A bank snapshots the full current actor and its explicit L
once, builds the original Q or D-over-L greedy adapters once, and still checks
the complete canonical composite at both bank boundaries. Every scene also
checks binding, epoch, backing-map identity, and exact in-memory contents before
and after native execution, including on an exceptional return.

The old per-scene entry repeatedly sorted/wired/deep-copied every store and
rebuilt the same providers. Here canonical sorting/wiring is O(M log M) at
bank boundaries, snapshot/provider construction is O(M) once per bank, and
O(N*M) cheap, unsorted scalar comparisons are retained rather than pretending
that read-only checking is O(1). No mutable store map is shared with a rollout.

Tokens authenticate a live nominal actor and its actual shared plan/sample,
not original B1 lineage by themselves. That lineage remains the owned curve
entry's responsibility. A token/actor/epoch is consumed before first native
execution; a partial bank returns no traces/mean and cannot be retried through
this entry. Frozen dataclass keys are checked by primitive field signatures as
well as object identity, so value-preserving type substitutions are refused.
"""

from copy import deepcopy
from dataclasses import dataclass
import math
from weakref import WeakKeyDictionary

import adaptive_training as A
import v105_normal_learning as L
from rfl_rebuild.b2 import training as T
from rfl_rebuild.env import kernel as K
from rfl_rebuild.learner.store import (
    DecisionAddress, LearnerPersistentState, LearnerSnapshot, QAddress,
)


class ReadonlyBank:
    """Opaque nominal token; only prepare_bank can register one."""
    __slots__ = ("__weakref__",)

    def __new__(cls):
        raise A.ProtocolError("requires a validated live actor and its exact shared sample")


@dataclass(frozen=True, slots=True)
class _StoreGuard:
    state: object
    snapshot: object
    maps: tuple
    contents: tuple


@dataclass(slots=True)
class _BankRecord:
    actor: object
    plan: object
    sample: tuple
    scene_fields: tuple
    before: dict
    initial: dict
    binding: tuple
    fields: tuple
    plan_fields: tuple
    epoch: int
    attempted_epochs: frozenset
    attempted_object: object
    guards: tuple
    command: object
    controller: object
    process: object
    attempted: bool = False
    complete: bool = False
    completed_scenes: int = 0
    failure: object = None
    traces: tuple = ()
    mean: object = None


_BANKS = WeakKeyDictionary()
_ACTOR_ATTEMPTS = WeakKeyDictionary()
_STORE_NAMES = ("_decision", "_process", "_controller", "_q")


def _int_fields(values, what):
    A.require(all(type(value) is int for value in values), what)
    return values


def _key_fields(key, index):
    """Primitive typed signature without JSON, sorting, or dataclass recursion."""
    if index == 1:
        return _int_fields((key,), "process key is not a true integer")
    expected = DecisionAddress if index == 0 else K.ControllerSite if index == 2 else QAddress
    A.require(type(key) is expected and type(key.state) is K.State,
              "read-only bank requires original nominal store addresses")
    state = key.state
    fields = (state.x, state.y, state.t, state.kappa, state.phi)
    if index in (0, 3):
        fields += (key.z, key.m)
    if index == 2:
        fields += (key.cmd,)
    elif index == 3:
        fields += (key.a,)
    return _int_fields(fields, "store address contains a non-integer field")


def _value_field(value, index):
    if index == 3:
        A.require(type(value) is float and math.isfinite(value),
                  "numeric store contains a non-binary64 finite value")
        return value.hex()  # Exact signed zero is significant to canonical audit.
    A.require(type(value) is int, "literal store value is not a true integer")
    return value


def _freeze_store(state):
    A.require(type(state) is LearnerPersistentState, "original nominal store state required")
    snapshot = state.snapshot()
    A.require(type(snapshot) is LearnerSnapshot, "original immutable snapshot required")
    maps, contents = [], []
    for index, name in enumerate(_STORE_NAMES):
        backing = getattr(state, name)
        A.require(type(backing) is dict, "state backing map is not the original dict")
        maps.append(backing)
        # Separate scalar/signature tuples do not alias mutable backing maps.
        contents.append(tuple((key, _key_fields(key, index), _value_field(value, index))
                              for key, value in backing.items()))
    return _StoreGuard(state, snapshot, tuple(maps), tuple(contents))


def _check_store(guard):
    A.require(type(guard.state) is LearnerPersistentState, "read-only store identity/type changed")
    for index, (name, backing, expected) in enumerate(zip(_STORE_NAMES, guard.maps, guard.contents)):
        current = getattr(guard.state, name)
        A.require(current is backing and type(current) is dict and len(current) == len(expected),
                  "read-only bank replaced a backing map or changed its extent")
        for (key, value), (frozen_key, fields, frozen_value) in zip(current.items(), expected):
            A.require(key is frozen_key and _key_fields(key, index) == fields and
                      _value_field(value, index) == frozen_value,
                      "read-only scene changed complete store contents or insertion order")


def _plan_fields(plan):
    A.require(type(plan) in (L.EngineeringPlan, L.KeyedPlan), "exact original shared plan required")
    common = (plan.parameters, (type(plan.parameters.alpha), plan.parameters.alpha),
              (type(plan.parameters.epsilon), plan.parameters.epsilon),
              id(plan.evaluation_sample), (type(plan.v_pre), plan.v_pre.hex()),
              (type(plan.t_max), plan.t_max), plan.grid)
    if type(plan) is L.EngineeringPlan:
        return ("engineering", id(plan.episodes), (type(plan.lock_digest), plan.lock_digest)) + common
    return ("keyed", id(plan.protocol)) + common


def _sample_fields(sample):
    A.require(type(sample) is tuple and all(type(scene) is L.EvaluationScene for scene in sample),
              "nominal scene sample type changed")
    return tuple(_int_fields(scene.key, "scene contains a non-integer field") for scene in sample)


def _scene_guard(record, scene=None, scene_fields=None):
    actor = record.actor
    A.require(type(actor) is L.CoordinateLearner and actor.plan is record.plan,
              "nominal learner/shared plan identity changed")
    A.require(all(type(value) is str for value in (actor.mode, actor.role, actor.source_label)) and
              (actor.mode, actor.role, actor.source_label, actor.reference) == record.fields and
              actor.reference is record.fields[3] and actor._binding == record.binding,
              "read-only source/mode/role/reference binding changed")
    A.require(actor._completed == record.epoch and type(actor._completed) is int and
              actor._attempted is record.attempted_object and type(actor._attempted) is set and
              frozenset(actor._attempted) == record.attempted_epochs and
              all(type(e) is int for e in actor._attempted),
              "checkpoint changed chronological epoch or attempt bookkeeping")
    A.require(actor._initial == record.initial and actor.plan.evaluation_sample is record.sample and
              _plan_fields(actor.plan) == record.plan_fields and
              actor.plan.parameters is record.plan_fields[-7],
              "read-only initial state/shared plan/sample changed")
    if scene is None:
        A.require(_sample_fields(record.sample) == record.scene_fields, "shared sample contents changed")
    else:
        A.require(type(scene) is L.EvaluationScene and
                  _int_fields(scene.key, "scene contains a non-integer field") == scene_fields,
                  "current shared scene contents changed")
    expected_states = tuple(guard.state for guard in record.guards)
    actual_states = (actor._immediate, actor._current) + (() if actor._values is None else (actor._values,))
    A.require(len(actual_states) == len(expected_states) and
              all(actual is expected for actual, expected in zip(actual_states, expected_states)),
              "read-only actor/I/current/L identity changed")
    for guard in record.guards:
        _check_store(guard)


def prepare_bank(actor, sample):
    """Issue a once-only bank token from a validated actual CoordinateLearner.

    Sample identity is intentional: a reordered, trimmed, reconstructed, or
    merely equal tuple is not the one actual shared plan input.
    """
    A.require(type(actor) is L.CoordinateLearner, "exact v105 normal learner required")
    actor._check()
    A.require(type(sample) is tuple and sample is actor.plan.evaluation_sample and
              T._require_scene_sample(sample, what="read-only bank shared sample") == sample,
              "exact original ordered shared sample required")
    epoch = actor._completed
    A.require(type(epoch) is int and 0 <= epoch <= actor.plan.t_max and
              actor._attempted == set(range(epoch)) and
              epoch not in _ACTOR_ATTEMPTS.get(actor, set()),
              "checkpoint is not an unattempted complete chronological epoch")
    before = actor.payload()
    states = (actor._immediate, actor._current) + (() if actor._values is None else (actor._values,))
    A.require(len({id(state) for state in states}) == len(states), "I/current/L state alias")
    guards = tuple(_freeze_store(state) for state in states)
    current = guards[1].snapshot
    numeric = current if actor.mode == "dq" else guards[2].snapshot
    base = numeric.q_decision_provider(actor.reference)
    command = base if actor.mode == "dq" else current.decision_provider(base)
    token = object.__new__(ReadonlyBank)
    record = _BankRecord(
        actor, actor.plan, sample, _sample_fields(sample), before,
        deepcopy(actor._initial), tuple(actor._binding),
        (actor.mode, actor.role, actor.source_label, actor.reference), _plan_fields(actor.plan),
        epoch, frozenset(actor._attempted), actor._attempted, guards,
        command, current.controller_mapping(), current.process_commit_provider())
    _BANKS[token] = record
    _scene_guard(record)
    return token


def _checked_token(token):
    A.require(type(token) is ReadonlyBank and token in _BANKS,
              "issued nominal read-only bank token required")
    return _BANKS[token]


def run_bank(token):
    """Return the same actual trace tuple and ordered binary64 mean, once.

    There is no command draw, exploration, learning, transaction, cloning,
    counterfactual, pre-level measurement, or policy update on this path.
    """
    record = _checked_token(token)
    A.require(not record.attempted and
              record.epoch not in _ACTOR_ATTEMPTS.get(record.actor, set()),
              "bank/actor/epoch already attempted; no partial retry")
    record.attempted = True
    _ACTOR_ATTEMPTS.setdefault(record.actor, set()).add(record.epoch)  # Before any native call.
    traces, total = [], 0.0
    try:
        _scene_guard(record)
        record.actor._check()
        A.require(record.actor.payload() == record.before, "composite changed after token issuance")
        for scene, fields in zip(record.sample, record.scene_fields):
            _scene_guard(record, scene, fields)
            try:
                trace = K.rollout(kappa=scene.kappa, tape=scene.tape, base_option=scene.base_option,
                                  command_provider=record.command, controller=record.controller,
                                  learner_process_commit=record.process, reward_mode="A")
            finally:
                _scene_guard(record, scene, fields)  # Includes failed native and a mutation still present at return.
            A.require(type(trace) is K.RolloutTrace and trace.steps and trace.steps[-1].terminal,
                      "partial checkpoint has no mean")
            traces.append(trace)
            record.completed_scenes += 1
            total += trace.return_value  # Original left-to-right binary64 addition; never fsum.
    except BaseException as error:
        record.failure = {"type": type(error).__name__, "text": str(error)}
        raise
    finally:
        record.traces = tuple(traces)
        try:
            _scene_guard(record)
            record.actor._check()
            A.require(record.actor.payload() == record.before, "checkpoint wrote complete R/L/I")
        except BaseException as error:
            record.failure = {"type": type(error).__name__, "text": str(error),
                              "during_final_readonly_guard": True, "prior": record.failure}
            raise
    A.require(len(traces) == len(record.sample), "partial checkpoint cannot publish a bank")
    record.mean, record.complete = total / len(record.sample), True
    return record.traces, record.mean


def audit_bank(token):
    """Audit-only progress; partial data is never a completed measurement handle."""
    record = _checked_token(token)
    return deepcopy({"revision": "v107-readonly-bank-v105-learner-semantics",
                     "mode": record.fields[0], "role": record.fields[1],
                     "source_label": record.fields[2], "epoch": record.epoch,
                     "sample": [list(key) for key in record.scene_fields],
                     "before": record.before, "attempted": record.attempted,
                     "complete": record.complete, "completed_scenes": record.completed_scenes,
                     "mean_hex": record.mean.hex() if record.complete else None,
                     "failure": record.failure, "traces": A.wire(record.traces),
                     "scientific_qualification": False})
