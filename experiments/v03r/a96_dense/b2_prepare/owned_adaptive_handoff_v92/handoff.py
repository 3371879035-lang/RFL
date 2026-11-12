"""Owned original whole-B1 lineage -> explicit v90 engineering learner revision.

Mode is declared on an issued source BEFORE either native arm. Serialized
receipts, caller states and existing unbound pairs cannot create training roles.
This is in-process ownership, not a hostile-Python sandbox or scientific gate.
The original libraries and the executed v90 core remain byte-for-byte unchanged.
"""
from copy import deepcopy
from dataclasses import dataclass
from weakref import WeakKeyDictionary

import oracle_mainline_v75 as O
import adaptive_training as A

ROLES = ("reference", "treatment")


class BoundSource:
    __slots__ = ("__weakref__",)
    def __new__(cls):
        raise A.ProtocolError("requires a genuine source bound before B1")


class OwnedTrainingPair:
    __slots__ = ("__weakref__",)
    def __new__(cls):
        raise A.ProtocolError("requires complete bound native whole-B1 handoff")


class OwnedTrainingRole:
    __slots__ = ("__weakref__",)
    def __new__(cls):
        raise A.ProtocolError("requires the issued pair's exact role")


@dataclass(frozen=True)
class _Source:
    original: object
    mode: str
    payload: dict
    seal: str


@dataclass(frozen=True)
class _Pair:
    bound: object
    original: object
    future: object
    actors: tuple
    handles: tuple
    payload: dict
    seal: str


_SOURCES = WeakKeyDictionary()
_BOUND = WeakKeyDictionary()
_ATTEMPTS = WeakKeyDictionary()
_ORIGINAL_PAIRS = WeakKeyDictionary()
_PREPARED = WeakKeyDictionary()
_PAIRS = WeakKeyDictionary()
_ROLE_BINDINGS = WeakKeyDictionary()


def bind_source(source, *, mode):
    """An explicit source declaration, never inferred from post-state emptiness."""
    _, sd = O._checked_source(source)
    A.require(mode in ("dq", "patch-adaptive"), "explicit decision architecture required")
    sd.pre.snapshot().q_decision_provider(sd.reference)  # old guard, unchanged
    A.require(not sd.pre.decision_overrides if mode == "dq" else not sd.pre.q_overrides,
              "declared mode disagrees with full issued pre-state")
    A.require(source not in _BOUND, "source already bound; no rebinding after arms")
    payload = {"revision": "v92-owned-handoff-to-v90-not-scientific-backend",
               "source": O.source_audit(source), "decision_mode_before_arms": mode,
               "full_pre": A.stores(sd.pre), "reference_digest": sd.reference.digest()}
    result = object.__new__(BoundSource)
    _SOURCES[result] = _Source(source, mode, deepcopy(payload), A.digest(payload))
    _BOUND[source], _ATTEMPTS[result] = result, set()
    _checked_source(result)
    return result


def _checked_source(bound):
    A.require(type(bound) is BoundSource and bound in _SOURCES, "issued bound source required")
    d = _SOURCES[bound]
    _, sd = O._checked_source(d.original)
    A.require(_BOUND.get(d.original) is bound and A.digest(d.payload) == d.seal
              and d.mode == d.payload["decision_mode_before_arms"]
              and O.source_audit(d.original) == d.payload["source"]
              and A.stores(sd.pre) == d.payload["full_pre"]
              and sd.reference.digest() == d.payload["reference_digest"],
              "bound source/mode/full pre/reference changed")
    return d, sd


def source_audit(bound):
    d, _ = _checked_source(bound)
    return deepcopy({"payload": d.payload, "payload_sha256": d.seal})


def run_whole_pair(bound, *, architecture, tier, law_name, assisted=None):
    d, _ = _checked_source(bound)
    A.require(architecture in ("D_Q", "D_patch", "X", "P"), "original architecture required")
    A.require(architecture not in ("D_Q", "D_patch") or
              architecture == ("D_Q" if d.mode == "dq" else "D_patch"),
              "decision cell disagrees with pre-arm source mode")
    key = (architecture, tier, law_name)
    A.require(key not in _ATTEMPTS[bound], "cell already attempted; no native retry")
    _ATTEMPTS[bound].add(key)  # BEFORE original dispatch, including partial failures
    pair = O.run_pair(d.original, architecture=architecture, tier=tier,
                      law_name=law_name, assisted=assisted)
    O._checked_pair(pair, d.original)
    declaration = {"bound_source_sha256": d.seal, "mode_before_arms": d.mode,
                   "architecture": architecture, "tier": tier.name, "law_name": law_name,
                   "original_pair": O.pair_audit(pair, d.original)}
    _ORIGINAL_PAIRS[pair] = (bound, deepcopy(declaration), A.digest(declaration))
    return pair


def _checked_original_pair(bound, pair):
    d, sd = _checked_source(bound)
    A.require(type(pair) is O.OwnedPair and pair in _ORIGINAL_PAIRS,
              "requires a genuine pair executed after source-mode binding")
    owner, declaration, seal = _ORIGINAL_PAIRS[pair]
    A.require(owner is bound and A.digest(declaration) == seal
              and declaration["bound_source_sha256"] == d.seal
              and declaration["mode_before_arms"] == d.mode
              and O.pair_audit(pair, d.original) == declaration["original_pair"],
              "pair source/mode/complete receipts changed")
    _, _, _, pd = O._checked_pair(pair, d.original)
    A.require(len(pd.results) == len(pd.clones) == 2, "empty/partial has no training roles")
    return d, sd, pd, declaration, seal


def prepare_training(bound, pair):
    d, sd, pd, declaration, pair_seal = _checked_original_pair(bound, pair)
    A.require(pair not in _PREPARED, "pair already prepared/attempted; no duplicate future")
    _PREPARED[pair] = True  # BEFORE clones/construction; partial produces no handle
    future = O.prepare_future_inputs(pair, d.original)
    starts = tuple(O.clone_future_start(future, d.original, role=r) for r in ROLES)
    A.require(starts[0] is not starts[1] and all(
        start is not sd.pre and all(start is not c for c in pd.clones)
        and A.stores(start) == A.stores(immediate)
        for start, immediate in zip(starts, pd.clones)), "fresh full role starts required")
    actors = tuple(A.AdaptiveTrainingState(start, mode=d.mode, role=role,
                   source_label=pair_seal, reference=sd.reference)
                   for role, start in zip(ROLES, starts))
    payload = {"original_declaration": deepcopy(declaration), "original_pair_binding": pair_seal,
               "original_future": O.future_audit(future, d.original),
               "ordered_initial_composites": [a.payload() for a in actors],
               "protected_immediate_posts": [A.stores(c) for c in pd.clones],
               "scientific_qualification": False, "formal_training_or_collection": False}
    bundle = object.__new__(OwnedTrainingPair)
    handles = tuple(object.__new__(OwnedTrainingRole) for _ in ROLES)
    _PAIRS[bundle] = _Pair(bound, pair, future, actors, handles, deepcopy(payload), A.digest(payload))
    for role, handle in zip(ROLES, handles):
        _ROLE_BINDINGS[handle] = (bundle, role)
    _checked_pair(bundle)
    return bundle


def _checked_pair(bundle):
    A.require(type(bundle) is OwnedTrainingPair and bundle in _PAIRS, "issued training pair required")
    d = _PAIRS[bundle]
    sd, source, native, declaration, pair_seal = _checked_original_pair(d.bound, d.original)
    A.require(A.digest(d.payload) == d.seal and d.payload["original_declaration"] == declaration
              and d.payload["original_pair_binding"] == pair_seal
              and O.future_audit(d.future, sd.original) == d.payload["original_future"],
              "full handoff origin/shared design changed")
    owned_objects = []
    for i, (role, actor, handle, immediate) in enumerate(zip(ROLES, d.actors, d.handles, native.clones)):
        A.require(type(actor) is A.AdaptiveTrainingState and _ROLE_BINDINGS.get(handle) == (bundle, role),
                  "role handle/actor ownership changed")
        p = actor.payload()
        A.require(p["mode"] == sd.mode and p["role"] == role and p["source_label"] == pair_seal
                  and p["reference_digest"] == source.reference.digest()
                  and p["immediate"] == A.stores(immediate) == d.payload["protected_immediate_posts"][i]
                  and p["immediate"] == d.payload["ordered_initial_composites"][i]["immediate"],
                  "role/full immediate/reference/source mode drifted")
        owned_objects.extend((actor, actor._immediate, actor._current))
        if actor._values is not None:
            owned_objects.append(actor._values)
    A.require(len({id(x) for x in owned_objects}) == len(owned_objects)
              and all(x is not source.pre and all(x is not c for c in native.clones)
                      for x in owned_objects), "roles/immediate/current/value states alias")
    return d


def pair_audit(bundle):
    d = _checked_pair(bundle)
    current = [a.payload() for a in d.actors]
    return deepcopy({"origin": d.payload, "origin_sha256": d.seal,
                     "ordered_current_composites": current,
                     "ordered_full_composite_sha256": [A.digest(p) for p in current]})


def role(bundle, *, role):
    A.require(type(role) is str and role in ROLES, "exact registered role required")
    d = _checked_pair(bundle)
    return d.handles[ROLES.index(role)]


def _checked_role(handle):
    A.require(type(handle) is OwnedTrainingRole and handle in _ROLE_BINDINGS, "issued training role required")
    bundle, role_name = _ROLE_BINDINGS[handle]
    d = _checked_pair(bundle)
    i = ROLES.index(role_name)
    A.require(d.handles[i] is handle, "role is not this pair's issued handle")
    return bundle, d, i


def train_episode(handle, episode, *, parameters=A.LearningParameters()):
    bundle, d, i = _checked_role(handle)
    try:
        result = d.actors[i].train_episode(episode, parameters=parameters)
    finally:
        _checked_pair(bundle)  # native immediate I_a/source remain protected even on failure
    return {"origin_sha256": d.seal, "role": ROLES[i], "training": result,
            "complete_pair_after": pair_audit(bundle)}


def evaluate(handle, *, kappa, tape, proposal):
    bundle, d, i = _checked_role(handle)
    result = d.actors[i].evaluate(kappa=kappa, tape=tape, proposal=proposal)
    return {"origin_sha256": d.seal, "role": ROLES[i], "evaluation": result,
            "complete_pair_after": pair_audit(bundle)}
