"""Owned COMPLETE-singleton raw maps in actual pre -> B1 -> post order.

Seedless in-process component only. No caller-supplied pair/census/map/state,
multi-credit E(S), partial credit selection, future collector or collection gate.
The hash chain records this owner's own calls, not a hostile-Python security proof
or portable scientific acquisition authentication.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from weakref import WeakKeyDictionary

import readiness as ready
import native_record_candidate as bridge
import credit_delivery_candidate as credit
import counterfactual_source_candidate as owned
import diagnostic_source_candidate as diagnostic
import pair_source_candidate as pair
import pre_census_source_candidate as census
import collateral_evidence_candidate as raw_module
from rfl_rebuild.b1.contract import fingerprint
from rfl_rebuild.b2 import unaffected as native
from rfl_rebuild.b2 import collateral as maps
from rfl_rebuild.learner.store import LearnerPersistentState


_CODE_PATHS = tuple(Path(m.__file__) for m in
    (ready, bridge, credit, owned, diagnostic, pair, census, raw_module)) + (Path(__file__),)
_CODE_BINDING = tuple(sha256(p.read_bytes()).hexdigest() for p in _CODE_PATHS)
_PARENT = ready.load_parent()
_REFERENCE = ready.read_json(ready.ROOT / ready.FOLDER / "b2_prepare/healthy_reference_candidate.json")
_STAGES = ("actual_diagnostic_complete_singleton", "full_native_pre_census",
    "shared_eligible_all_one_pre_map", "unique_owned_B1_pair",
    "immediate_reference_map", "immediate_treatment_map", "all_raw_maps_validated")


class OwnedSingleMaps:
    __slots__ = ("__weakref__",)

    def __new__(cls):
        raise ready.ProtocolError("single maps require their own actual ordered source route")


@dataclass(frozen=True, slots=True)
class _Data:
    source: object
    run: object
    arms: object
    diagnostic_sha: str
    cell_payload: object
    site: object
    census: object
    pair: object
    unaffected: object
    pre_map: object
    post_clones: tuple
    post_maps: tuple
    raw: object
    raw_sha: object
    sequence: tuple
    route: str


_ISSUED = WeakKeyDictionary()


def _guard():
    census._guard()
    ready.require(tuple(sha256(p.read_bytes()).hexdigest() for p in _CODE_PATHS) == _CODE_BINDING,
                  "single-map/dependency code changed after loading")
    ready.require(ready.validate_design(_PARENT["lock"])["refinement"] == "eligible_all",
                  "only the actually locked refinement, no map-driven refinement choice")
    ready.validate_reference(_REFERENCE, _PARENT)


def _context(run, source, arms):
    _guard()
    ds, cell, payload, sites, _ = census._context(run, source, arms)
    if cell is None:
        return ds, payload, None, "SKIPPED_REFLECTION_NO_MAPS_OR_B1"
    if not sites:
        return ds, payload, None, "NO_CREDIT_IN_CELL_NO_MAPS_OR_B1_NOT_SCIENTIFIC_ZERO"
    ready.require(len(sites) == len(cell.addresses) == len(cell.credited_units) == 1 and
        cell.prepared.expanded_units == cell.credited_units and not payload["residual_predictions"],
        "complete singleton required; no first/min/truth-best site or discarded residual")
    if type(cell) is credit.CellPreparation:
        ready.require(credit.single_credited_site(cell) == sites[0], "original singleton guard differs")
    else:
        # The owned L2 cell has already undergone its full original validation.
        # No current positive D_Q singleton integration is implied by this branch.
        ready.require(type(cell) is owned.PreparedL2Cell, "closed original singleton cell required")
    sites[0].__post_init__()
    return ds, payload, sites[0], "OWNED_COMPLETE_SINGLETON_PRE_B1_POST_MAPS_NOT_COLLECTION"


def _values(mapping, units):
    ready.require(type(mapping) is dict and tuple(mapping) == units,
                  "complete actual native map in original unaffected order required")
    for scene in mapping:
        ready.require(type(scene) is native.EvaluationScene, "strict native map scene key required")
        scene.__post_init__()
    values = tuple(mapping[s] for s in units)
    ready.require(all(type(v) is float and bridge.finite(v, "native map value") == v for v in values),
                  "complete finite original float map values required")
    return values


def _measure(state, unaffected, q_reference):
    ready.require(type(state) is LearnerPersistentState, "actual owned learner clone required")
    before = fingerprint(state)
    mapping = maps.measure_scene_map(state, unaffected.units, q_reference=q_reference)
    ready.require(fingerprint(state) == before, "native raw map mutated its learner state")
    _values(mapping, unaffected.units)
    return mapping


def _append(sequence, stage, payload):
    ready.require(stage == _STAGES[len(sequence)], "owner execution stage order differs")
    content = bridge.sha(payload)
    prior = sequence[-1][2] if sequence else "0" * 64
    sequence.append((stage, content, bridge.sha([prior, stage, content])))


def _census_payload(d, data):
    return {"source_fingerprint_pre": data.fingerprint_pre,
        "full_ordered_census_sha256": bridge.sha([[list(s.key), h, list(f), ts, rs]
            for s, h, f, ts, rs in d.census]),
        "production_domain_size": d.production_payload[0],
        "production_domain_sha256": d.production_payload[1],
        "production_membership": list(d.production_payload[2])}


def _pre_payload(site, unaffected, values, data):
    return {"site": site.render(), "construction": unaffected.construction,
        "ordered_unit_keys": [list(s.key) for s in unaffected.units],
        "values_hex": [v.hex() for v in values], "fingerprint_pre": data.fingerprint_pre}


def _post_payload(role, clone, values, ledger):
    return {"role": role, "fingerprint_post": fingerprint(clone),
        "values_hex": [v.hex() for v in values], "native_ledger": ledger.canonical()}


def run_owned_single_maps(run, source, arms):
    """Construct pre material and map BEFORE this owner's one native B1 pair.

    Reflection skip precedes arm reads. Empty projection produces no metric,
    pair or zero-filled future. Errors issue no partial capability; no retry.
    """
    ds, cell_payload, site, route = _context(run, source, arms)
    ch = ph = unaffected = pre_map = raw = raw_sha = None
    post_clones = post_maps = (); sequence = []
    if site is not None:
        data = owned._checked(source)
        try:
            _append(sequence, _STAGES[0], {"diagnostic_sha256": ds, "whole_cell": cell_payload})
            ch = census.prepare_owned_pre_census(run, source, arms)
            cd = census._checked(ch, run, source)
            ready.require(cd.sites == (site,) and cd.cell_payload == cell_payload and
                cd.production_payload[2] == (True,), "complete original production singleton required")
            _append(sequence, _STAGES[1], _census_payload(cd, data))
            unaffected = native.build_unaffected(site, cd.traces, "eligible_all")
            pre_map = _measure(data.pre_state, unaffected, data.reference)
            _append(sequence, _STAGES[2], _pre_payload(site, unaffected,
                _values(pre_map, unaffected.units), data))
            # NO existing pair input: this is the first and only pair invocation
            # belonging to this component, after the actual shared pre map.
            ph = pair.run_owned_b1_pair(run, source, arms)
            pd = pair._checked_pair(ph, run, source)
            ready.require(pd.cell_payload == cell_payload and len(pd.results) == 2,
                          "unique native B1 must consume the same complete singleton")
            _append(sequence, _STAGES[3], pair.pair_audit(ph, run, source))
            clones = []; measured = []
            for i, role in enumerate(("reference", "treatment")):
                clone = pair.clone_immediate_post(ph, run, source, role=role)
                ready.require(all(clone is not other for other in clones), "independent post exports required")
                mapping = _measure(clone, unaffected, data.reference)
                clones.append(clone); measured.append(mapping)
                _append(sequence, _STAGES[4 + i], _post_payload(role, clone,
                    _values(mapping, unaffected.units), pd.results[i].ledger))
            post_clones, post_maps = tuple(clones), tuple(measured)
            names = tuple(a.name for a in arms)
            raw = raw_module.RawCollateralEvidence(raw_module.ROLE, names, site,
                tuple((s, h, flags[0]) for s, h, flags, ts, rs in cd.census), unaffected,
                _values(pre_map, unaffected.units),
                tuple((n, _values(m, unaffected.units)) for n, m in zip(names, post_maps)),
                data.fingerprint_pre, tuple((n, fingerprint(c)) for n, c in zip(names, post_clones)),
                tuple((n, r.ledger) for n, r in zip(names, pd.results)), data.reference.digest(),
                data.audit["lock_sha256"], data.audit["parent_sources_digest"],
                data.audit["healthy_reference_canonical_payload_sha256"], raw_module.ORDER)
            checked = raw_module.validate_collateral_evidence(raw, arms=arms, credited_site=site,
                parent=_PARENT, reference=_REFERENCE)
            raw_sha = checked["input_sha256"]
            _append(sequence, _STAGES[6], {"raw_input_sha256": raw_sha})
        finally:
            _guard(); diagnostic._checked_run(run, source)
            ready.require(bridge.sha(diagnostic.diagnostic_audit(run, source)) == ds,
                          "raw-map execution changed its actual source/diagnostic")
    record = _Data(source, run, arms, ds, cell_payload, site, ch, ph, unaffected,
                   pre_map, post_clones, post_maps, raw, raw_sha, tuple(sequence), route)
    _validate(record, run, source)  # failed final checks never issue partial handles
    handle = object.__new__(OwnedSingleMaps)
    _ISSUED[handle] = record
    return handle


def _validate(d, run, source):
    ready.require(d.run is run and d.source is source, "single maps belong to another actual source/run")
    ds, payload, site, route = _context(run, source, d.arms)
    ready.require(ds == d.diagnostic_sha and payload == d.cell_payload and site == d.site and route == d.route,
                  "whole source/diagnostic/singleton binding changed")
    if site is None:
        ready.require(all(v is None for v in (d.census, d.pair, d.unaffected, d.pre_map, d.raw, d.raw_sha))
            and d.post_clones == d.post_maps == d.sequence == (), "skip/empty cannot carry raw maps or metric zeros")
        return None
    data = owned._checked(source)
    cd = census._checked(d.census, run, source)
    pd = pair._checked_pair(d.pair, run, source)
    ready.require(cd.sites == (site,) and cd.production_payload[2] == (True,) and
        cd.cell_payload == pd.cell_payload == payload and len(pd.results) == 2,
        "full actual pre-census and unique native pair must share the original singleton")
    ready.require(type(d.unaffected) is native.UnaffectedSet, "same original shared unaffected object required")
    # The original raw validator below freshly performs the full nominal set
    # validation; do not duplicate its quadratic full-domain membership walk.
    ready.require(d.unaffected.construction == f"E1(c={site.render()})@eligible_all" and
        d.unaffected.units == tuple(s for s, h, flags, ts, rs in cd.census if h and not flags[0]),
        "shared region differs from complete original H_pre and Consult, no new E(S)")
    ready.require(type(d.post_clones) is type(d.post_maps) is tuple and
        len(d.post_clones) == len(d.post_maps) == 2 and d.post_clones[0] is not d.post_clones[1],
        "two complete original post maps/clones required")
    ready.require(d.pre_map is not d.post_maps[0] and d.pre_map is not d.post_maps[1] and
        d.post_maps[0] is not d.post_maps[1], "three distinct actually measured map dictionaries required")
    for i, clone in enumerate(d.post_clones):
        ready.require(type(clone) is LearnerPersistentState and clone is not data.pre_state and
            all(clone is not c for c in pd.clones) and fingerprint(clone) == fingerprint(pd.clones[i]),
            "requested-role post export changed/aliased or lost immediate native state")
    raw = d.raw; names = tuple(a.name for a in d.arms)
    ready.require(type(raw) is raw_module.RawCollateralEvidence and raw.site is d.site and
        raw.unaffected is d.unaffected and raw.arm_names == names and
        raw.pre_census == tuple((s, h, f[0]) for s, h, f, ts, rs in cd.census) and
        raw.fingerprint_pre == data.fingerprint_pre and
        raw.values_pre == _values(d.pre_map, d.unaffected.units), "raw maps lost actual pre-state material")
    checked = raw_module.validate_collateral_evidence(raw, arms=d.arms, credited_site=site,
        parent=_PARENT, reference=_REFERENCE)  # strict shape before positional reads
    ready.require(tuple(v.hex() for v in raw.values_pre) ==
        tuple(v.hex() for v in _values(d.pre_map, d.unaffected.units)), "pre float bits differ")
    for i, name in enumerate(names):
        values = _values(d.post_maps[i], d.unaffected.units)
        ready.require(raw.values_post[i][0] == name and
            tuple(v.hex() for v in raw.values_post[i][1]) == tuple(v.hex() for v in values) and
            raw.fingerprints_post[i] == (name, fingerprint(d.post_clones[i])) and
            raw.ledgers[i][0] == name and raw.ledgers[i][1] is pd.results[i].ledger,
            "raw post role/value bits/fingerprint/actual native ledger identity differs")
    ready.require(checked["input_sha256"] == d.raw_sha, "sealed full raw input changed")
    stages = [{"diagnostic_sha256": ds, "whole_cell": payload}, _census_payload(cd, data),
        _pre_payload(site, d.unaffected, raw.values_pre, data), pair.pair_audit(d.pair, run, source)]
    stages += [_post_payload(role, clone, values, result.ledger) for role, clone, (_, values), result in
        zip(("reference", "treatment"), d.post_clones, raw.values_post, pd.results)]
    stages.append({"raw_input_sha256": d.raw_sha})
    expected = []
    for name, value in zip(_STAGES, stages): _append(expected, name, value)
    ready.require(type(d.sequence) is tuple and d.sequence == tuple(expected),
                  "owner's runtime checkpoints/content chain changed")
    return checked


def single_maps_audit(handle, run, source):
    """Fresh stored-content audit; no U2/map rollout, diagnosis, B1 or future.

    Original L2 target validation, if ever supported by an actual singleton,
    retains its fresh native seedless counterfactual replays, not cached PASS.
    Current positive integration fixtures cover X only.
    """
    ready.require(type(handle) is OwnedSingleMaps and handle in _ISSUED,
                  "issued own ordered map handle required, not detached audit/hash/pair")
    d = _ISSUED[handle]; checked = _validate(d, run, source)
    return deepcopy({"schema": "a96-owned-complete-singleton-raw-maps-candidate-v11",
        "role": "SEEDLESS_IN_PROCESS_COMPONENT_LINEAGE_NOT_SCIENTIFIC_RECEIPT", "route": d.route,
        "diagnostic_audit_sha256": d.diagnostic_sha, "whole_cell": d.cell_payload,
        "credited_site": d.site.render() if checked else None,
        "native_U2_pre_rollouts": 5760 if checked else 0,
        "unaffected_size": d.unaffected.size if checked else None,
        "native_map_calls": 3 if checked else 0, "B1_arm_calls": 2 if checked else 0,
        "raw_input_sha256": d.raw_sha,
        "complete_raw_input": checked["input_payload"] if checked else None,
        "collateral_hex": {k: v.hex() for k, v in checked["collateral"].items()} if checked else None,
        "actual_owned_pre_before_unique_B1_order_in_process": bool(checked),
        "runtime_content_chain": [list(row) for row in d.sequence],
        "supplied_pair_retroactive_order_authenticated": False,
        "multi_credit_region_or_residual_selection_defined": False,
        "portable_security_or_science_acquisition_origin_authenticated": False,
        "future_training_episodes": 0, "environment_seed_draws": 0,
        "collection_authorized": False, "scientific_claim_authorized": False, "research_complete": False})
