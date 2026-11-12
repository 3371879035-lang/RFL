"""Authentic empty architecture-credit source -> ordinary paired future.

This explicit engineering origin does not impersonate an original B1 result or
future-input handle. The original metadata-only pair has no B1 calls, receipts,
post clones, or therapy transaction. Its real full source state is preserved as
the no-edit immediate state, then independently cloned for ordinary learning.
Role names are bookkeeping labels, not a substantive treatment contrast.
"""
from copy import deepcopy
from dataclasses import dataclass
from types import MappingProxyType
from weakref import WeakKeyDictionary

import adaptive_training as A
import handoff as H
import oracle_mainline_v75 as O
import v107_bank as B
from v105_normal_learning import CoordinateLearner, EngineeringEpisode, EngineeringPlan

ROLES = ("reference", "treatment")
CONTRAST_STATUS = "NO_SUBSTANTIVE_UPDATE_CONTRAST"
COLLATERAL_STATUS = "NOT_APPLICABLE_EMPTY_OWNER_SET"
FIELDS = ("future_rewards", "future_outcomes", "future_trajectories",
          "future_actions", "future_observations")


class OwnedNoCreditFuture:
    __slots__ = ("__weakref__",)
    def __new__(cls):
        raise A.ProtocolError("requires authentic pre-bound empty-credit source metadata")


class RoleCurve:
    __slots__ = ("__weakref__",)
    def __new__(cls):
        raise A.ProtocolError("requires this no-credit origin's complete observed role curve")


class ExternalCurveView:
    __slots__ = ("__weakref__",)
    def __new__(cls):
        raise A.ProtocolError("requires actual complete no-credit future observations")


@dataclass(frozen=True)
class _Metadata:
    bound: object
    declaration: dict
    seal: str


@dataclass(frozen=True)
class _Future:
    bound: object
    pair: object
    plan: object
    immediate: tuple
    actors: tuple
    origin: dict
    seal: str


_CELL_ATTEMPTS = WeakKeyDictionary()
_METADATA = WeakKeyDictionary()
_PREPARED = WeakKeyDictionary()
_FUTURES = WeakKeyDictionary()
_ATTEMPTED = WeakKeyDictionary()
_PROGRESS = WeakKeyDictionary()
_ROLE_CURVES = WeakKeyDictionary()
_COMPLETED = WeakKeyDictionary()
_VIEWS = WeakKeyDictionary()


def _empty_projection(source, sd, *, architecture, assisted):
    A.require(sd.evidence is not None and sd.truth is not None,
              "this entry requires real failure truth, not success or fabricated credit")
    gamma_name = "Gamma_P_star" if sd.regime == "P" else "Gamma_T_star"
    gamma = tuple(sd.truth[gamma_name])
    projected = O.base._project(sd.evidence, gamma, architecture, assisted)
    A.require(projected.whole_units and not projected.cell_units and not projected.addresses,
              "only a genuinely empty architecture projection may use no-edit future")
    return projected


def run_no_credit_pair(bound, *, architecture, tier, law_name, assisted=None):
    """Record an original metadata-only pair after explicit source-mode binding.

    Whole truth and residual units survive. The source/cell attempt is consumed
    before original dispatch, even if validation or dispatch later fails.
    """
    source, sd = H._checked_source(bound)
    A.require(architecture in ("D_Q", "D_patch", "X", "P"), "original architecture required")
    A.require(architecture not in ("D_Q", "D_patch") or
              architecture == ("D_Q" if source.mode == "dq" else "D_patch"),
              "decision cell disagrees with explicit pre-arm source mode")
    key = (architecture, tier, law_name)
    attempts = _CELL_ATTEMPTS.setdefault(bound, set())
    A.require(key not in attempts, "no-credit source/cell already attempted; no retry")
    attempts.add(key)
    O.base._registered(architecture, tier, law_name)
    _empty_projection(source, sd, architecture=architecture, assisted=assisted)
    pair = H.run_whole_pair(bound, architecture=architecture, tier=tier,
                            law_name=law_name, assisted=assisted)
    _config, _sd, _pair, native = O._checked_pair(pair, source.original)
    A.require(native.payload["route"] == "NO_CREDIT_IN_CELL_NO_FAKE_LEDGER_OR_FUTURE"
              and native.projected is not None and not native.projected.addresses
              and not native.projected.cell_units and not native.results and not native.clones
              and native.payload["native_B1_arm_calls"] == 0
              and native.payload["all_owner_receipts"] == [],
              "original pair is not authentic empty-credit metadata")
    owner, original_declaration, original_seal = H._ORIGINAL_PAIRS[pair]
    A.require(owner is bound and A.digest(original_declaration) == original_seal,
              "original metadata pair lacks actual pre-bound handoff ownership")
    declaration = {"bound_source_sha256": source.seal,
                   "decision_mode_before_metadata": source.mode,
                   "source": O.source_audit(source.original),
                   "original_metadata_pair": O.pair_audit(pair, source.original),
                   "original_bound_pair_declaration": deepcopy(original_declaration),
                   "original_bound_pair_sha256": original_seal,
                   "architecture": architecture, "tier": tier.name, "law_name": law_name,
                   "whole_units": list(native.projected.whole_units),
                   "cell_units": [], "owner_addresses": [],
                   "residual_units": list(native.projected.residual_units),
                   "native_B1_arm_calls": 0, "owner_receipts": 0,
                   "therapy_transactions": 0, "contrast_status": CONTRAST_STATUS,
                   "collateral_status": COLLATERAL_STATUS, "collateral": None}
    _METADATA[pair] = _Metadata(bound, deepcopy(declaration), A.digest(declaration))
    _checked_metadata(bound, pair)
    return pair


def _checked_metadata(bound, pair):
    source, sd = H._checked_source(bound)
    A.require(type(pair) is O.OwnedPair and pair in _METADATA,
              "requires metadata actually issued by this entry after mode binding")
    record = _METADATA[pair]
    A.require(pair in H._ORIGINAL_PAIRS, "original pre-bound metadata ownership lost")
    owner, original_declaration, original_seal = H._ORIGINAL_PAIRS[pair]
    _config, _sd, pd, native = O._checked_pair(pair, source.original)
    projected = _empty_projection(source, sd, architecture=native.architecture,
                                  assisted=native.assisted)
    A.require(record.bound is bound and owner is bound
              and A.digest(original_declaration) == original_seal
              and record.declaration["original_bound_pair_declaration"] == original_declaration
              and record.declaration["original_bound_pair_sha256"] == original_seal
              and original_declaration["bound_source_sha256"] == source.seal
              and original_declaration["mode_before_arms"] == source.mode
              and original_declaration["original_pair"] == O.pair_audit(pair, source.original)
              and A.digest(record.declaration) == record.seal
              and record.declaration["bound_source_sha256"] == source.seal
              and record.declaration["decision_mode_before_metadata"] == source.mode
              and record.declaration["architecture"] == native.architecture == original_declaration["architecture"]
              and record.declaration["tier"] == native.tier.name == original_declaration["tier"]
              and record.declaration["law_name"] == native.law_name == original_declaration["law_name"]
              and record.declaration["source"] == O.source_audit(source.original)
              and record.declaration["original_metadata_pair"] == O.pair_audit(pair, source.original)
              and native.projected == projected and not native.results and not native.clones
              and native.payload["route"] == "NO_CREDIT_IN_CELL_NO_FAKE_LEDGER_OR_FUTURE"
              and native.payload["native_B1_arm_calls"] == 0
              and native.payload["all_owner_receipts"] == []
              and record.declaration["whole_units"] == list(projected.whole_units)
              and record.declaration["residual_units"] == list(projected.residual_units)
              and record.declaration["cell_units"] == record.declaration["owner_addresses"] == []
              and record.declaration["native_B1_arm_calls"] == record.declaration["owner_receipts"] == record.declaration["therapy_transactions"] == 0
              and record.declaration["contrast_status"] == CONTRAST_STATUS
              and record.declaration["collateral_status"] == COLLATERAL_STATUS
              and record.declaration["collateral"] is None,
              "empty-credit source/mode/metadata/full truth lineage changed")
    return source, sd, pd, native, record


def metadata_audit(bound, pair):
    _source, _sd, _pd, _native, record = _checked_metadata(bound, pair)
    return deepcopy({"declaration": record.declaration, "declaration_sha256": record.seal})


def _plan_wire(plan, indices):
    return {"episodes": A.wire(plan.episodes), "grid": list(plan.grid),
            "sample": [list(scene.key) for scene in plan.evaluation_sample],
            "engineering_bank_indices": list(indices), "v_pre_hex": plan.v_pre.hex(),
            "parameters": A.wire(plan.parameters), "original_lock_sha256": plan.lock_digest,
            "keyed": False, "formal_execution": False}


def prepare_curve(bound, pair, *, episodes, evaluation_indices):
    """Clone actual complete source state, never fabricate original future handles."""
    source, sd, _pd, _native, metadata = _checked_metadata(bound, pair)
    A.require(pair not in _PREPARED, "empty-credit metadata already prepared; no repeated future")
    _PREPARED[pair] = True
    A.require(type(episodes) is tuple and episodes and
              all(type(episode) is EngineeringEpisode for episode in episodes),
              "explicit finite engineering stream required")
    A.require(type(evaluation_indices) is tuple and evaluation_indices and
              all(type(index) is int and index >= 0 for index in evaluation_indices) and
              tuple(sorted(set(evaluation_indices))) == evaluation_indices,
              "fixed unique ordered engineering bank indices required")
    # This pure original factory reads this authenticated source's locked config.
    # It does not create or register an original OwnedOracleFutureInputs handle.
    template = O.base._template(sd.parent, sd.healthy)
    A.require(evaluation_indices[-1] < len(template["sample"]), "complete shared bank required")
    plan = EngineeringPlan(episodes, tuple(template["sample"][index] for index in evaluation_indices),
                           template["v_pre"], A.LearningParameters(template["alpha"], template["epsilon"]),
                           template["lock_sha256"])
    immediate = tuple(sd.pre.clone() for _role in ROLES)
    starts = tuple(state.clone() for state in immediate)
    actors = tuple(CoordinateLearner(state, mode=source.mode, role=role,
                                    source_label=metadata.seal, reference=sd.reference, plan=plan)
                   for state, role in zip(starts, ROLES))
    A.require(len({id(state) for state in (*immediate, *starts)}) == 4 and all(
        state is not sd.pre and A.stores(state) == A.stores(sd.pre) for state in (*immediate, *starts)),
        "no-edit immediate/future clones must be exact and independent")
    origin = {"revision": "v110-authentic-empty-architecture-credit-ordinary-future",
              "declaration": deepcopy(metadata.declaration), "metadata_sha256": metadata.seal,
              "full_source_pre": A.stores(sd.pre),
              "protected_no_edit_immediate": [A.stores(state) for state in immediate],
              "original_locked_template": O.base._template_wire(template),
              "initial_composites": [actor.payload() for actor in actors],
              "engineering_plan": _plan_wire(plan, evaluation_indices),
              "contrast_status": CONTRAST_STATUS,
              "collateral_status": COLLATERAL_STATUS, "collateral": None,
              "native_B1_arm_calls": 0, "owner_receipts": 0, "therapy_transactions": 0,
              "scientific_qualification": False, "collection_authorized": False}
    bundle = object.__new__(OwnedNoCreditFuture)
    _FUTURES[bundle] = _Future(bound, pair, plan, immediate, actors, deepcopy(origin), A.digest(origin))
    _ATTEMPTED[bundle], _PROGRESS[bundle] = False, []
    _checked(bundle)
    return bundle


def _checked(bundle):
    A.require(type(bundle) is OwnedNoCreditFuture and bundle in _FUTURES,
              "issued authentic no-credit future required")
    data = _FUTURES[bundle]
    source, sd, _pd, _native, metadata = _checked_metadata(data.bound, data.pair)
    indices = tuple(data.origin["engineering_plan"]["engineering_bank_indices"])
    A.require(A.digest(data.origin) == data.seal
              and data.origin["declaration"] == metadata.declaration
              and data.origin["metadata_sha256"] == metadata.seal
              and data.origin["full_source_pre"] == A.stores(sd.pre)
              and data.origin["original_locked_template"] == O.base._template_wire(
                  O.base._template(sd.parent, sd.healthy))
              and data.origin["engineering_plan"] == _plan_wire(data.plan, indices),
              "no-credit origin/shared locked plan changed")
    objects = list(data.immediate)
    for role, actor, immediate, initial in zip(ROLES, data.actors, data.immediate,
                                             data.origin["initial_composites"]):
        A.require(type(actor) is CoordinateLearner and actor.plan is data.plan and actor.role == role
                  and actor.mode == source.mode and actor.source_label == metadata.seal
                  and actor._initial == A.stores(immediate) == initial["immediate"] == A.stores(sd.pre),
                  "no-edit immediate/source/mode/role binding changed")
        objects += [actor, actor._immediate, actor._current]
        if actor._values is not None:
            objects.append(actor._values)
        actor._check()
    A.require(len({id(obj) for obj in objects}) == len(objects) and
              all(obj is not sd.pre for obj in objects), "no-credit future roles or source states alias")
    A.require([A.stores(state) for state in data.immediate] == data.origin["protected_no_edit_immediate"],
              "protected complete no-edit immediate state changed")
    return data


def audit(bundle):
    data = _checked(bundle)
    return deepcopy({"origin": data.origin, "origin_sha256": data.seal,
                     "ordered_composites": [actor.payload() for actor in data.actors],
                     "attempted": _ATTEMPTED[bundle], "progress": _PROGRESS[bundle],
                     "completed": bundle in _COMPLETED, "contrast_status": CONTRAST_STATUS,
                     "collateral_status": COLLATERAL_STATUS, "collateral": None,
                     "scientific_qualification": False})


def run_pair_curve(bundle):
    data = _checked(bundle)
    A.require(not _ATTEMPTED[bundle], "no-credit curve already attempted; no retry")
    _ATTEMPTED[bundle] = True
    collected = []
    try:
        for role, actor in zip(ROLES, data.actors):
            checkpoints, training = [], []
            for epoch in data.plan.grid:
                A.require(actor._completed == epoch, "checkpoint is not the entered real epoch")
                _PROGRESS[bundle].append({"role": role, "epoch": epoch, "stage": "evaluation_started"})
                before = actor.payload()
                traces, mean = B.run_bank(B.prepare_bank(actor, data.plan.evaluation_sample))
                checkpoints.append((epoch, traces, mean))
                _PROGRESS[bundle].append({"role": role, "epoch": epoch, "stage": "evaluation_completed",
                                         "mean_hex": mean.hex(), "full_composite": before})
                if epoch < data.plan.t_max:
                    _PROGRESS[bundle].append({"role": role, "epoch": epoch, "stage": "training_started"})
                    receipt = actor.train_episode(data.plan.episode(epoch))
                    training.append(receipt)
                    _PROGRESS[bundle].append({"role": role, "epoch": epoch, "stage": "training_completed"})
            collected.append((role, tuple(checkpoints), tuple(training)))
        _checked(bundle)
        A.require(len(collected) == 2, "partial no-credit pair cannot mint complete curves")
        handles = tuple(object.__new__(RoleCurve) for _role in ROLES)
        for handle, (role, checkpoints, training) in zip(handles, collected):
            _ROLE_CURVES[handle] = (bundle, role, checkpoints, training)
        _COMPLETED[bundle] = handles
        return handles
    finally:
        _checked(bundle)


def _external_material(handle):
    A.require(type(handle) is RoleCurve and handle in _ROLE_CURVES,
              "actual completed no-credit role curve required")
    bundle, role, checkpoints, _training = _ROLE_CURVES[handle]
    data = _checked(bundle)
    A.require(bundle in _COMPLETED and _COMPLETED[bundle][ROLES.index(role)] is handle
              and tuple(epoch for epoch, _traces, _mean in checkpoints) == data.plan.grid
              and all(len(traces) == len(data.plan.evaluation_sample)
                      for _epoch, traces, _mean in checkpoints), "external curve extent/origin incomplete")
    return checkpoints, data.plan.v_pre, data.plan.t_max


def curve_audit(handle):
    A.require(type(handle) is RoleCurve and handle in _ROLE_CURVES, "complete no-credit role required")
    bundle, role, checkpoints, training = _ROLE_CURVES[handle]
    _external_material(handle)
    return deepcopy({"origin_sha256": _FUTURES[bundle].seal, "role": role,
                     "checkpoints": [{"epoch": epoch, "traces": A.wire(traces), "mean_hex": mean.hex()}
                                     for epoch, traces, mean in checkpoints], "training": training,
                     "full_pair_after": audit(bundle), "contrast_status": CONTRAST_STATUS,
                     "collateral_status": COLLATERAL_STATUS, "collateral": None,
                     "scientific_qualification": False})


def _project(checkpoints):
    fields = {name: [] for name in FIELDS}
    times, means = [], []
    for epoch, traces, mean in checkpoints:
        values = {name: [] for name in FIELDS}
        for trace in traces:
            steps = trace.steps
            values["future_rewards"].append(tuple(float(step.reward) for step in steps))
            values["future_outcomes"].append(tuple(step.outcome for step in steps))
            values["future_trajectories"].append(tuple(step.state for step in steps))
            values["future_actions"].append(tuple(int(step.a_cmd) for step in steps))
            values["future_observations"].append(tuple(getattr(step, "obs", None) for step in steps))
        for name in FIELDS:
            fields[name].append(tuple(values[name]))
        times.append(epoch)
        means.append(mean)
    return MappingProxyType({name: tuple(value) for name, value in fields.items()}), tuple(times), tuple(means)


def build_external(handle):
    checkpoints, pre_level, t_max = _external_material(handle)
    fields, times, means = _project(checkpoints)
    payload = MappingProxyType({"fields": fields, "episodes": times, "values": means,
                                "pre_level": pre_level, "t_max": t_max})
    view = object.__new__(ExternalCurveView)
    _VIEWS[view] = (handle, payload)
    return view


def read_external(view):
    A.require(type(view) is ExternalCurveView and view in _VIEWS, "issued closed external view required")
    handle, payload = _VIEWS[view]
    checkpoints, pre_level, t_max = _external_material(handle)
    fields, times, means = _project(checkpoints)
    A.require(set(payload) == {"fields", "episodes", "values", "pre_level", "t_max"}
              and payload["fields"] == fields and payload["episodes"] == times
              and payload["values"] == means and payload["pre_level"] == pre_level
              and payload["t_max"] == t_max, "external input differs from its actual raw observations")
    return payload
