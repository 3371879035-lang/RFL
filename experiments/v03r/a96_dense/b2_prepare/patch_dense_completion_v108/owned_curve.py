"""Versioned owned curve with the v107 read-only bank optimization.

All source/bundle/role, training, chronological grid, once, and external outcome
semantics remain the v105 normal path; only checkpoint bank evaluation delegates
to its separately audited immutable-snapshot read path. Engineering scope is
explicit: historical lock constants do not grant scientific execution.
"""
from copy import deepcopy
from dataclasses import dataclass
from weakref import WeakKeyDictionary

import adaptive_training as A
import handoff as H
import oracle_mainline_v75 as O
from rfl_rebuild.env import kernel as K
import v107_bank as B
from v105_normal_learning import CoordinateLearner, EngineeringEpisode, EngineeringPlan

ROLES = ("reference", "treatment")


class OwnedCurvePair:
    __slots__ = ("__weakref__",)
    def __new__(cls):
        raise A.ProtocolError("requires an actual source-bound whole pair")


class RoleCurve:
    __slots__ = ("__weakref__",)
    def __new__(cls):
        raise A.ProtocolError("requires a completely observed issued role curve")


@dataclass(frozen=True)
class _Bundle:
    bound: object
    pair: object
    future: object
    plan: object
    actors: tuple
    origin: dict
    seal: str


_BUNDLES = WeakKeyDictionary()
_PREPARED = WeakKeyDictionary()
_ATTEMPTED = WeakKeyDictionary()
_ROLE_CURVES = WeakKeyDictionary()
_COMPLETED = WeakKeyDictionary()
_PROGRESS = WeakKeyDictionary()


def prepare_curve(bound, pair, *, episodes, evaluation_indices):
    source, sd, native, declaration, pair_seal = H._checked_original_pair(bound, pair)
    A.require(pair not in _PREPARED, "whole pair already prepared; no repeated future")
    _PREPARED[pair] = True  # Before any new clones or construction.
    A.require(type(episodes) is tuple and episodes and all(type(e) is EngineeringEpisode for e in episodes),
              "explicit finite engineering stream required")
    A.require(type(evaluation_indices) is tuple and evaluation_indices and
              all(type(i) is int and i >= 0 for i in evaluation_indices) and
              tuple(sorted(set(evaluation_indices))) == evaluation_indices,
              "fixed unique ordered engineering bank indices required")
    future = O.prepare_future_inputs(pair, source.original)
    fd, config = O._checked_future(future, source.original)
    template = O.base._checked_future(fd.native, config.native).template
    A.require(template is not None and evaluation_indices[-1] < len(template["sample"]), "complete shared bank required")
    plan = EngineeringPlan(episodes, tuple(template["sample"][i] for i in evaluation_indices), template["v_pre"],
                           A.LearningParameters(template["alpha"], template["epsilon"]), template["lock_sha256"])
    starts = tuple(O.clone_future_start(future, source.original, role=r) for r in ROLES)
    actors = tuple(CoordinateLearner(s, mode=source.mode, role=r, source_label=pair_seal,
                                     reference=sd.reference, plan=plan) for s, r in zip(starts, ROLES))
    origin = {"declaration": declaration, "original_pair_seal": pair_seal,
              "original_future": O.future_audit(future, source.original),
              "initial_composites": [a.payload() for a in actors],
              "engineering_plan": {"episodes": A.wire(episodes), "grid": list(plan.grid),
                  "sample": [list(s.key) for s in plan.evaluation_sample],
                  "engineering_bank_indices": list(evaluation_indices), "v_pre_hex": plan.v_pre.hex(),
                  "parameters": A.wire(plan.parameters), "original_lock_sha256": plan.lock_digest,
                  "keyed": False, "formal_execution": False}}
    bundle = object.__new__(OwnedCurvePair)
    _BUNDLES[bundle] = _Bundle(bound, pair, future, plan, actors, deepcopy(origin), A.digest(origin))
    _ATTEMPTED[bundle], _PROGRESS[bundle] = False, []
    _checked(bundle)
    return bundle


def _checked(bundle):
    A.require(type(bundle) is OwnedCurvePair and bundle in _BUNDLES, "issued complete curve bundle required")
    d = _BUNDLES[bundle]
    source, sd, native, declaration, pair_seal = H._checked_original_pair(d.bound, d.pair)
    A.require(A.digest(d.origin) == d.seal and d.origin["declaration"] == declaration and
              d.origin["original_pair_seal"] == pair_seal and
              O.future_audit(d.future, source.original) == d.origin["original_future"], "curve origin changed")
    objects = []
    for role, actor, immediate, initial in zip(ROLES, d.actors, native.clones, d.origin["initial_composites"]):
        A.require(type(actor) is CoordinateLearner and actor.plan is d.plan and actor.role == role,
                  "role did not consume the one shared plan")
        objects += [actor, actor._immediate, actor._current]
        if actor._values is not None:
            objects.append(actor._values)
        A.require(actor.mode == source.mode and actor.source_label == pair_seal and
                  actor._initial == A.stores(immediate) == initial["immediate"], "protected I/source/mode drift")
    A.require(len({id(x) for x in objects}) == len(objects) and all(
        x is not sd.pre and all(x is not c for c in native.clones) for x in objects),
        "future actor/current aliases protected immediate or another role")
    for actor in d.actors:
        actor._check()
    return d


def audit(bundle):
    d = _checked(bundle)
    return deepcopy({"origin": d.origin, "origin_sha256": d.seal,
                     "ordered_composites": [a.payload() for a in d.actors],
                     "attempted": _ATTEMPTED[bundle], "progress": _PROGRESS[bundle],
                     "completed": bundle in _COMPLETED, "scientific_qualification": False})


def _evaluate_bank(actor, sample):
    token = B.prepare_bank(actor, sample)
    return B.run_bank(token)

def run_pair_curve(bundle):
    d = _checked(bundle)
    A.require(not _ATTEMPTED[bundle], "curve already attempted; no native retry")
    _ATTEMPTED[bundle] = True  # Before first evaluation or training call.
    collected = []
    try:
        for role, actor in zip(ROLES, d.actors):
            checkpoints, training = [], []
            for e in d.plan.grid:
                A.require(actor._completed == e, "checkpoint is not the entered real epoch")
                _PROGRESS[bundle].append({"role": role, "epoch": e, "stage": "evaluation_started"})
                before = actor.payload()
                traces, mean = _evaluate_bank(actor, d.plan.evaluation_sample)
                checkpoints.append((e, traces, mean))
                _PROGRESS[bundle].append({"role": role, "epoch": e, "stage": "evaluation_completed",
                                         "mean_hex": mean.hex(), "full_composite": before})
                if e < d.plan.t_max:
                    _PROGRESS[bundle].append({"role": role, "epoch": e, "stage": "training_started"})
                    receipt = actor.train_episode(d.plan.episode(e))
                    training.append(receipt)
                    _PROGRESS[bundle].append({"role": role, "epoch": e, "stage": "training_completed"})
            collected.append((role, tuple(checkpoints), tuple(training)))
        _checked(bundle)
        A.require(len(collected) == 2, "partial pair cannot mint curves")
        handles = tuple(object.__new__(RoleCurve) for _ in ROLES)
        for handle, (role, checkpoints, training) in zip(handles, collected):
            _ROLE_CURVES[handle] = (bundle, role, checkpoints, training)
        _COMPLETED[bundle] = handles
        return handles
    finally:
        _checked(bundle)  # Even a partial curve cannot alter the source or I_a.


def _external_material(handle):
    A.require(type(handle) is RoleCurve and handle in _ROLE_CURVES, "actual completed role curve required")
    bundle, role, checkpoints, _training = _ROLE_CURVES[handle]
    d = _checked(bundle)
    A.require(bundle in _COMPLETED and _COMPLETED[bundle][ROLES.index(role)] is handle,
              "external role curve is not this completed pair")
    A.require(tuple(e for e, _traces, _mean in checkpoints) == d.plan.grid and
              all(len(traces) == len(d.plan.evaluation_sample) for _e, traces, _mean in checkpoints),
              "external checkpoint/sample extent incomplete")
    # No audit/source/role/state/truth/ledger is returned through this input door.
    return checkpoints, d.plan.v_pre, d.plan.t_max


def curve_audit(handle):
    A.require(type(handle) is RoleCurve and handle in _ROLE_CURVES, "completed curve handle required")
    bundle, role, checkpoints, training = _ROLE_CURVES[handle]
    _external_material(handle)
    return deepcopy({"origin_sha256": _BUNDLES[bundle].seal, "role": role,
                     "checkpoints": [{"epoch": e, "traces": A.wire(t), "mean_hex": m.hex()}
                                     for e, t, m in checkpoints], "training": training,
                     "full_pair_after": audit(bundle), "scientific_qualification": False})
