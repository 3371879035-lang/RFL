"""Owned protected future *inputs*, not a trainer or a collection gate.

Consumes one actually issued v11 raw-map lineage. Creates a single seed-free
template and independent role-bound future-start bases from its existing unique
B1 pair. No seed, protocol, curve, callback, learner or receipt input can open
collection. No FutureTrainingProtocol, Curve, PairedSceneRecord or recorder
events are fabricated: those require a later frozen, keyed actual execution.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
from weakref import WeakKeyDictionary

import readiness as ready
import native_record_candidate as bridge
import counterfactual_source_candidate as owned
import pair_source_candidate as pair
import single_map_source_candidate as maps
from rfl_rebuild.b1.contract import fingerprint
from rfl_rebuild.b2 import training
from rfl_rebuild.b2.evalorder import prefix, prefix_digest
from rfl_rebuild.b2.unaffected import EvaluationScene
from rfl_rebuild.learner.store import LearnerPersistentState


_PARENT = ready.load_parent()
_REFERENCE_PATH = ready.ROOT / ready.FOLDER / "b2_prepare/healthy_reference_candidate.json"
_REFERENCE = ready.read_json(_REFERENCE_PATH)
_REFERENCE_SHA = bridge.sha(_REFERENCE)
_CODE_PATHS = tuple(Path(m.__file__) for m in (ready, bridge, owned, pair, maps, training)) + (
    Path(__file__), _REFERENCE_PATH)
_CODE_BINDING = tuple(sha256(p.read_bytes()).hexdigest() for p in _CODE_PATHS)
_ROLES = ("reference", "treatment")


class OwnedFutureInputs:
    __slots__ = ("__weakref__",)

    def __new__(cls):
        raise ready.ProtocolError("future inputs require an actual owned single-map route")


class _FutureBase:
    __slots__ = ("state", "__weakref__")

    def __new__(cls):
        raise ready.ProtocolError("future bases are owner-created, not supplied states")


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False)
class _SeedFreeTemplate:
    alpha: object
    epsilon: object
    t_max: object
    grid: object
    evaluation_sample: object
    v_pre: object


@dataclass(frozen=True, slots=True)
class _Data:
    map_handle: object
    run: object
    source: object
    maps_sha: str
    template: object
    role_templates: tuple
    bases: tuple
    route: str
    payload_sha: str


_ISSUED = WeakKeyDictionary()
_TEMPLATES = WeakKeyDictionary()
_BASES = WeakKeyDictionary()


def _guard():
    maps._guard()
    ready.require(tuple(sha256(p.read_bytes()).hexdigest() for p in _CODE_PATHS) == _CODE_BINDING,
                  "future-input/dependency/reference bytes changed after loading")
    ready.require(bridge.sha(_REFERENCE) == _REFERENCE_SHA,
                  "shared B2 reference payload changed in memory")
    ready.validate_reference(_REFERENCE, _PARENT)


def _template_payload(template):
    ready.require(type(template) is _SeedFreeTemplate and template in _TEMPLATES,
                  "one owner-issued seed-free template required, not a nominal supplied protocol")
    d = ready.validate_design(_PARENT["lock"])
    v_pre = ready.validate_reference(_REFERENCE, _PARENT)
    ready.require(type(template.alpha) is Fraction and type(template.epsilon) is Fraction and
        template.alpha == Fraction(1, 2) and template.epsilon == Fraction(1, 10),
        "original exact shared learning constants required")
    ready.require(type(template.t_max) is int and template.t_max == d["T"] and
        type(template.grid) is tuple and all(type(e) is int for e in template.grid) and
        template.grid == tuple(d["grid"]) == tuple(range(d["T"] + 1)),
        "full locked integer episode axis required, no cap/prefix/sparse grid")
    sample = template.evaluation_sample
    ready.require(type(sample) is tuple and sample == prefix(d["N_eval"]),
                  "original locked ordered evaluation bank required")
    for scene in sample:
        ready.require(type(scene) is EvaluationScene, "nominal native scene required")
        scene.__post_init__()
    ready.require(type(template.v_pre) is float and
        bridge.finite(template.v_pre, "shared healthy reference") == v_pre and
        template.v_pre.hex() == v_pre.hex(), "injected once-shared B2 reference bytes differ")
    payload = {"alpha": [1, 2], "epsilon": [1, 10], "T": template.t_max,
        "grid": list(template.grid), "ordered_evaluation_unit_keys": [list(s.key) for s in sample],
        "N_eval": len(sample), "evaluation_sample_sha256": prefix_digest(len(sample)),
        "v_pre_hex": template.v_pre.hex(), "healthy_reference_payload_sha256": _REFERENCE_SHA,
        "lock_sha256": _PARENT["lock_sha256"], "parent_sources_digest": _PARENT["sources_digest"],
        "native_protocol_class": "rfl_rebuild.b2.training.FutureTrainingProtocol",
        "native_protocol_instantiated": False, "environment_seed": None}
    ready.require(bridge.sha(payload) == _TEMPLATES[template], "shared template seal changed")
    return payload


def _payload(d):
    _guard()
    audit = maps.single_maps_audit(d.map_handle, d.run, d.source)
    ready.require(bridge.sha(audit) == d.maps_sha, "actual raw-map/source lineage changed")
    md = maps._ISSUED[d.map_handle]
    if md.site is None:
        ready.require(d.route == md.route and d.template is None and
            d.role_templates == d.bases == (), "skip/empty has no fake protocol/bases/future zeros")
        return {"route": d.route, "single_maps_audit_sha256": d.maps_sha,
                "template": None, "ordered_future_bases": []}
    ready.require(d.route == "OWNED_FUTURE_INPUTS_PREPARED_NO_KEY_OR_TRAINING" and
        type(d.role_templates) is tuple and len(d.role_templates) == 2 and
        all(t is d.template for t in d.role_templates), "paired roles require ONE exact shared template")
    template = _template_payload(d.template)
    source_data = owned._checked(d.source)
    pd = pair._checked_pair(md.pair, d.run, d.source)
    ready.require(type(d.bases) is tuple and len(d.bases) == 2 and d.bases[0] is not d.bases[1],
                  "complete independent future-start bases required")
    states = []
    for role, base, immediate in zip(_ROLES, d.bases, pd.clones):
        ready.require(type(base) is _FutureBase and base in _BASES,
                      "actual owner-issued role base required, not an equal detached learner")
        initial = _BASES[base]
        ready.require(initial[:5] == (d.map_handle, d.run, d.source, role, fingerprint(immediate)),
                      "future base belongs to another role/source/pair")
        state = base.state
        ready.require(state is initial[5], "future base lost its initial state identity for this role")
        ready.require(type(state) is LearnerPersistentState and state is not source_data.pre_state and
            all(state is not s for s in (*pd.clones, *md.post_clones, *states)) and
            fingerprint(state) == fingerprint(immediate),
            "future base aliased/moved from its protected immediate native post state")
        states.append(state)
    ready.require(source_data.reference.digest() == _REFERENCE["q_reference_sha256"],
                  "future would use a different nominal Q reference")
    return {"route": d.route, "single_maps_audit_sha256": d.maps_sha,
        "raw_collateral_input_sha256": md.raw_sha, "template": template,
        "ordered_future_bases": [{"role": r, "fingerprint_start": fingerprint(s)}
                                 for r, s in zip(_ROLES, states)]}


def prepare_owned_future_inputs(map_handle, run, source):
    """Prepare clones/template only; never rerun B1/maps or draw a seed.

    Existing maps are consumed with exact source/run identity. Success/empty
    routes carry no future quantity. The complete scientific execution path and
    single-use collection gate do not yet exist in this preparation module.
    """
    _guard()
    audit = maps.single_maps_audit(map_handle, run, source)
    md = maps._ISSUED[map_handle]
    template = None; role_templates = bases = (); route = md.route
    if md.site is not None:
        d = ready.validate_design(_PARENT["lock"])
        sample = prefix(d["N_eval"])
        v_pre = ready.validate_reference(_REFERENCE, _PARENT)
        template = _SeedFreeTemplate(Fraction(1, 2), Fraction(1, 10), d["T"],
                                     tuple(d["grid"]), sample, v_pre)
        # Register this exact object before the full fresh validation. There is
        # deliberately no seed field and no FutureTrainingProtocol constructor.
        payload = {"alpha": [1, 2], "epsilon": [1, 10], "T": d["T"],
            "grid": list(template.grid), "ordered_evaluation_unit_keys": [list(s.key) for s in sample],
            "N_eval": len(sample), "evaluation_sample_sha256": prefix_digest(len(sample)),
            "v_pre_hex": v_pre.hex(), "healthy_reference_payload_sha256": _REFERENCE_SHA,
            "lock_sha256": _PARENT["lock_sha256"], "parent_sources_digest": _PARENT["sources_digest"],
            "native_protocol_class": "rfl_rebuild.b2.training.FutureTrainingProtocol",
            "native_protocol_instantiated": False, "environment_seed": None}
        _TEMPLATES[template] = bridge.sha(payload)
        role_templates = (template, template)
        collected = []
        for role in _ROLES:
            base = object.__new__(_FutureBase)
            base.state = pair.clone_immediate_post(md.pair, run, source, role=role)
            _BASES[base] = (map_handle, run, source, role, fingerprint(base.state), base.state)
            collected.append(base)
        bases = tuple(collected)
        route = "OWNED_FUTURE_INPUTS_PREPARED_NO_KEY_OR_TRAINING"
    data = _Data(map_handle, run, source, bridge.sha(audit), template, role_templates, bases, route, "")
    payload_sha = bridge.sha(_payload(data))
    data = _Data(map_handle, run, source, data.maps_sha, template, role_templates, bases, route, payload_sha)
    _checked_data(data, run, source)
    handle = object.__new__(OwnedFutureInputs); _ISSUED[handle] = data
    return handle


def _checked_data(d, run, source):
    ready.require(d.run is run and d.source is source, "future inputs belong to another actual source/run")
    payload = _payload(d)
    ready.require(bridge.sha(payload) == d.payload_sha, "complete protected input seal changed")
    return payload


def _checked(handle, run, source):
    ready.require(type(handle) is OwnedFutureInputs and handle in _ISSUED,
                  "owner-issued future-input handle required, not detached audit/curve/protocol/receipt")
    d = _ISSUED[handle]
    return d, _checked_data(d, run, source)


def future_inputs_audit(handle, run, source):
    """Fresh stored lineage/content checks, no nominal SCI record fabrication.

    Checks repeat no diagnosis/U2/map/B1/future. Original L2 target validation,
    if ever reachable, continues its native CF replay boundary unchanged.
    """
    d, payload = _checked(handle, run, source)
    return deepcopy({"schema": "a96-owned-protected-future-inputs-candidate-v12",
        "role": "SEEDLESS_PREPARATION_NOT_FUTURE_EXECUTION_OR_SCIENTIFIC_RECEIPT",
        "input_sha256": d.payload_sha, "complete_input_payload": payload,
        "shared_template_object_count": int(d.template is not None),
        "independent_future_start_bases": len(d.bases),
        "existing_unique_B1_pair_consumed_no_reexecution": bool(d.bases),
        "future_training_episodes": 0, "environment_seed_draws": 0,
        "native_future_protocol_or_curve_or_paired_record_created": False,
        "actual_keyed_curve_origin_authenticated": False,
        "full_dense_B2_workload_resources_certified": False,
        "population_seed_registry_and_collection_gate_authenticated": False,
        "collection_authorized": False, "scientific_claim_authorized": False, "research_complete": False})


def clone_future_start(handle, run, source, *, role):
    """Fresh preparation export, NOT permission to run a keyed future.

    Export edits cannot move the pinned bases, native immediate post states or
    raw maps. A later collector must itself own training and complete raw curves;
    detached exports/audits cannot certify origin of an externally supplied run.
    """
    ready.require(type(role) is str and role in _ROLES, "explicit registered paired role required")
    d, _ = _checked(handle, run, source)
    ready.require(len(d.bases) == 2, "skip/empty has no future start or zero-filled curve")
    exported = d.bases[_ROLES.index(role)].state.clone()
    md = maps._ISSUED[d.map_handle]; pd = pair._checked_pair(md.pair, run, source)
    source_data = owned._checked(source)
    ready.require(type(exported) is LearnerPersistentState and
        all(exported is not s for s in (source_data.pre_state, *pd.clones, *md.post_clones,
                                      *(b.state for b in d.bases))) and
        fingerprint(exported) == fingerprint(d.bases[_ROLES.index(role)].state),
        "export must remain a separate exact requested-role preparation clone")
    _checked(handle, run, source)
    return exported
