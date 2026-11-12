"""Source-isolated raw collateral evidence, NOT a B2 collection instrument.

The pure bridge rechecks supplied values/census, never treating a Python object
or an input hash as acquisition authentication. The separate seedless builder
owns full-U2 pre traces, one pre map and immediate post-B1 clones, but runs NO
factual trigger, diagnostic method, future training or scientific seed. It is
engineering preparation, not a replacement for the frozen PairedRunner.
"""
from __future__ import annotations

from dataclasses import dataclass

import readiness as ready
import native_record_candidate as bridge
from rfl_rebuild.b1.contract import fingerprint
from rfl_rebuild.b2.collateral import behavioral_collateral_scenes, measure_scene_map
from rfl_rebuild.b2.runner import PairedRunner
from rfl_rebuild.b2.unaffected import (CreditedSite, EvaluationScene, UnaffectedSet,
    _slice, build_unaffected, credited_domain, pre_update_traces, scene_domain)
from rfl_rebuild.learner.reference import QReferenceView
from rfl_rebuild.learner.store import LearnerPersistentState

ROLE = "CONSTRUCTED_OR_SEEDLESS_MAPS_NOT_AUTHENTICATED_COLLECTION"
ORDER = ("pre_state", "full_U2_pretraces", "shared_unaffected", "one_pre_map",
         "clone_reference", "clone_treatment", "B1_reference", "B1_treatment",
         "immediate_post_reference", "immediate_post_treatment")


@dataclass(frozen=True, slots=True)
class RawCollateralEvidence:
    """Closed portable inputs; even exact nominal instances can be constructed.

    Census entries are (scene, healthy_pre, consults_credit_pre) for EVERY U2
    scene in its original order. Values are frozen tuples in unaffected order.
    IDs/addresses of live objects are deliberately not portable authentication.
    """
    role: str
    arm_names: tuple
    site: CreditedSite
    pre_census: tuple
    unaffected: UnaffectedSet
    values_pre: tuple
    values_post: tuple
    fingerprint_pre: str
    fingerprints_post: tuple
    ledgers: tuple
    q_reference_sha256: str
    lock_sha256: str
    parent_sources_digest: str
    healthy_reference_canonical_payload_sha256: str
    order: tuple


def _sha(value, label):
    bridge.require(type(value) is str and len(value) == 64 and
                   all(c in "0123456789abcdef" for c in value), f"{label}: canonical SHA256 required")


def _values(values, units, label):
    bridge.require(type(values) is tuple and len(values) == len(units),
                   f"{label}: complete frozen values in unaffected order required")
    for value in values:
        bridge.require(type(bridge.finite(value, label)) is float,
                       f"{label}: original measured float required")
    return dict(zip(units, values))


def _ordered_pairs(rows, names, label):
    bridge.require(type(rows) is tuple and len(rows) == 2 and
        all(type(row) is tuple and len(row) == 2 and type(row[0]) is str for row in rows) and
        tuple(row[0] for row in rows) == names, f"{label}: exact reference/treatment order required")
    return dict(rows)


def validate_collateral_evidence(raw, *, arms, credited_site, parent, reference):
    """Recompute maps/eligibility from SUPPLIED material, not certify its origin."""
    binding = bridge.validate_pair(arms)
    d = ready.validate_design(parent["lock"])
    ready.validate_reference(reference, parent)
    names = tuple(arm.name for arm in arms)
    bridge.require(type(raw) is RawCollateralEvidence and raw.role == ROLE,
                   "nominal raw map evidence with preparation-only role required")
    bridge.require(type(credited_site) is type(raw.site) is CreditedSite and
                   credited_site.channel == binding["architecture"] and raw.site == credited_site,
                   "raw maps belong to the exact credited site/architecture")
    credited_site.__post_init__()
    bridge.SLICES[binding["architecture"]].domain.require_credited(credited_site.address)
    bridge.require(type(raw.arm_names) is tuple and raw.arm_names == names and
                   type(raw.order) is tuple and raw.order == ORDER,
                   "map pair role/order or declared pre-before-B1 sequence differs")
    bridge.require(raw.lock_sha256 == parent["lock_sha256"] and
                   raw.parent_sources_digest == parent["sources_digest"] and
                   raw.healthy_reference_canonical_payload_sha256 == bridge.sha(reference) and
                   raw.q_reference_sha256 == reference["q_reference_sha256"],
                   "maps/reference/parent binding differs")
    for value, label in ((raw.lock_sha256, "lock"), (raw.parent_sources_digest, "source"),
        (raw.q_reference_sha256, "Q reference"),
        (raw.healthy_reference_canonical_payload_sha256, "healthy reference"),
        (raw.fingerprint_pre, "pre state")):
        _sha(value, label)

    domain = scene_domain()
    bridge.require(type(raw.pre_census) is tuple and len(raw.pre_census) == len(domain),
                   "full U2 pre-trace census required; a prefix/subsample cannot prove eligibility")
    eligible, census_payload = [], []
    for row, expected in zip(raw.pre_census, domain):
        bridge.require(type(row) is tuple and len(row) == 3 and
                       type(row[0]) is EvaluationScene and type(row[1]) is type(row[2]) is bool,
                       "strict scene/healthy/consults census row required")
        scene, healthy, consults = row
        scene.__post_init__()
        bridge.require(scene == expected, "U2 census missing/duplicated/reordered scene")
        if healthy and not consults and _slice(d["refinement"], scene):
            eligible.append(scene)
        census_payload.append([list(scene.key), healthy, consults])
    u = raw.unaffected
    bridge.require(type(u) is UnaffectedSet, "nominal shared scene set required")
    u.__post_init__()
    for scene in u.units:
        scene.__post_init__()
    bridge.require(u.construction == f"E1(c={credited_site.render()})@{d['refinement']}" and
                   u.units == tuple(eligible),
                   "unaffected set differs from full pre-census conjuncts/locked refinement")
    values_pre = _values(raw.values_pre, u.units, "one pre map")
    post_rows = _ordered_pairs(raw.values_post, names, "post maps")
    post_fps = _ordered_pairs(raw.fingerprints_post, names, "post fingerprints")
    ledgers = _ordered_pairs(raw.ledgers, names, "ledgers")
    collateral, ledger_text, post_payload = {}, {}, {}
    for i, name in enumerate(names):
        _sha(post_fps[name], "immediate post state")
        values_post = _values(post_rows[name], u.units, "immediate post map")
        collateral[name] = behavioral_collateral_scenes(u, values_pre=values_pre, values_post=values_post)
        bridge.finite(collateral[name], "recomputed collateral")
        ledger_text[name] = bridge.validate_ledger(ledgers[name], binding["architecture"],
            credited_site, raw.fingerprint_pre, post_fps[name], reference=i == 0)
        if i == 0:
            bridge.require(tuple(v.hex() for v in post_rows[name]) ==
                           tuple(v.hex() for v in raw.values_pre),
                           "NoWrite raw maps must match elementwise, not just have a zero mean loss")
        post_payload[name] = [v.hex() for v in post_rows[name]]
    payload = {"schema": "a96-b2-raw-collateral-input-v1", "role": ROLE,
        "law_binding": binding, "credited_site": credited_site.render(),
        "lock_sha256": raw.lock_sha256, "parent_sources_digest": raw.parent_sources_digest,
        "q_reference_sha256": raw.q_reference_sha256,
        "healthy_reference_canonical_payload_sha256": raw.healthy_reference_canonical_payload_sha256,
        "pre_census": census_payload, "unaffected_construction": u.construction,
        "unaffected_unit_keys": [list(scene.key) for scene in u.units],
        "pre_values_hex": [v.hex() for v in raw.values_pre], "post_values_hex": post_payload,
        "fingerprint_pre": raw.fingerprint_pre, "fingerprints_post": post_fps,
        "ledger_canonical": ledger_text, "declared_order": list(raw.order),
        "collateral_hex": {name: value.hex() for name, value in collateral.items()}}
    return {"input_payload": payload, "input_sha256": bridge.sha(payload),
        "collateral": collateral, "raw_collateral_maps_recomputed": True,
        "eligibility_recomputed_from_full_supplied_pre_census": True,
        "supplied_census_prestate_origin_authenticated": False,
        "actual_factual_failure_origin_authenticated": False,
        "population_seed_registry_and_collection_gate_authenticated": False,
        "collection_authorized": False, "scientific_claim_authorized": False, "research_complete": False}


def extract_with_collateral(raw, **record_inputs):
    """Join raw maps to the full-curve bridge, refusing cross-pair/summary drift.

    Neither component can authenticate acquisition. A matching hash or a full
    nominal census does not upgrade that boundary. Existing input files stay
    unchanged; the joined payload has a new digest, never a migrated PASS.
    """
    base = bridge.extract_paired_record(**record_inputs)
    checked = validate_collateral_evidence(raw, **{key: record_inputs[key]
        for key in ("arms", "credited_site", "parent", "reference")})
    record, capture = record_inputs["record"], record_inputs["capture"]
    bridge.require(raw.unaffected.units == capture.events[0][1].units and
                   raw.unaffected.construction == record.unaffected_construction,
                   "maps and curve record do not share the same unaffected material")
    for name in record.arm_names:
        bridge.require(raw.fingerprint_pre == record.fingerprints_pre[name] and
            dict(raw.fingerprints_post)[name] == record.fingerprints_post[name] and
            checked["input_payload"]["ledger_canonical"][name] == record.ledgers[name].canonical(),
            "maps/curves ledgers or immediate post-state binding differ")
        bridge.require(type(record.collateral[name]) is float and
            record.collateral[name].hex() == checked["collateral"][name].hex(),
            "reported collateral differs from original ordered-map recomputation")
    payload = {"curve_record": base["input_payload"], "raw_collateral": checked["input_payload"]}
    return {**base, "role": "JOINED_RAW_MAP_CURVE_INPUT_NOT_AUTHENTICATED_ACQUISITION",
        "input_payload": payload, "input_sha256": bridge.sha(payload),
        "raw_collateral_maps_recomputed": True,
        "eligibility_recomputed_from_full_supplied_pre_census": True,
        "supplied_census_prestate_origin_authenticated": False}


def measure_seedless_pair(pre_state, *, arms, evidence, credited_site, q_reference,
                          parent, reference):
    """Controlled B1 + raw collateral engineering ONLY, with no subset shortcut.

    Caller supplies a declared pre-state and inherited evidence. No failure is
    invented and no science seed is accepted. The full U2 traces and pre map are
    built once before either arm; original frozen B1 dispatch updates independent
    clones; original scene measurements read their immediate post states. There
    is intentionally no future, diagnostic/credit selector, file writer or CLI.
    """
    binding = bridge.validate_pair(arms)
    d = ready.validate_design(parent["lock"])
    ready.validate_reference(reference, parent)
    bridge.require(type(pre_state) is LearnerPersistentState and type(q_reference) is QReferenceView,
                   "nominal learner/reference required, not factories or custom environments")
    bridge.require(q_reference.digest() == reference["q_reference_sha256"],
                   "injected Q reference differs from shared B2 reference artifact")
    bridge.require(type(credited_site) is CreditedSite and credited_site.channel == binding["architecture"],
                   "exact matching credited site required")
    credited_site.__post_init__()
    bridge.require(PairedRunner._resolved_credit(binding["architecture"], evidence) == (credited_site.address,),
                   "B1 credit and collateral singleton differ")
    before = fingerprint(pre_state)
    traces = pre_update_traces(learner=pre_state, q_reference=q_reference)
    bridge.require(traces.learner is pre_state and fingerprint(pre_state) == before,
                   "full pre traces changed or replaced their source")
    bridge.require(credited_site in credited_domain(binding["architecture"], traces),
                   "credited site outside full pre-state production extent")
    census = tuple((scene, traces.successful(scene), traces.consults(credited_site, scene))
                   for scene in scene_domain())
    unaffected = build_unaffected(credited_site, traces, d["refinement"])
    pre_map = measure_scene_map(pre_state, unaffected.units, q_reference=q_reference)
    bridge.require(fingerprint(pre_state) == before, "shared pre-map measurement mutated source")
    clones = tuple(pre_state.clone() for _ in arms)
    bridge.require(len({id(c) for c in clones} | {id(pre_state)}) == 3 and
                   all(fingerprint(c) == before for c in clones), "pair must be independent clones of ONE source")
    ledgers = tuple((a.name, PairedRunner._apply(a, c, evidence, q_reference).ledger)
                    for a, c in zip(arms, clones))
    post_fps = tuple((a.name, fingerprint(c)) for a, c in zip(arms, clones))
    post_maps = []
    for arm, clone in zip(arms, clones):
        post_map = measure_scene_map(clone, unaffected.units, q_reference=q_reference)
        post_maps.append((arm.name, tuple(post_map[s] for s in unaffected.units)))
    post_maps = tuple(post_maps)
    bridge.require(fingerprint(pre_state) == before and
                   post_fps == tuple((a.name, fingerprint(c)) for a, c in zip(arms, clones)),
                   "raw collateral measurement changed pre/immediate post states")
    raw = RawCollateralEvidence(ROLE, tuple(a.name for a in arms), credited_site, census,
        unaffected, tuple(pre_map[s] for s in unaffected.units), post_maps, before, post_fps,
        ledgers, q_reference.digest(), parent["lock_sha256"], parent["sources_digest"],
        bridge.sha(reference), ORDER)
    result = validate_collateral_evidence(raw, arms=arms, credited_site=credited_site,
                                         parent=parent, reference=reference)
    return {"role": "SEEDLESS_B1_COLLATERAL_ENGINEERING_NOT_B2_ACQUISITION", "raw": raw,
        "checked": result, "environment_seed_draws": 0, "future_training_episodes": 0,
        "full_U2_pretrace_count": len(census), "unaffected_count": unaffected.size,
        "native_B1_dispatch_executed": True, "collection_authorized": False,
        "scientific_claim_authorized": False, "research_complete": False}
