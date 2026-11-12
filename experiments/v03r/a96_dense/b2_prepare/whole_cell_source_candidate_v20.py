"""Owned whole D_Q cell raw per-site diagnostics, not a primary endpoint.

All original predictions/residuals and all D_Q addresses are preserved. Each
E1(c) is the original singleton region, measured after the SAME whole-cell
B1 pair. Such a region can consult OTHER credited addresses. No E(S), aggregate
Collateral, singleton update attribution, future protocol or science gate is
defined here. Seedless, in-process lineage only; not hostile-Python security.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from weakref import WeakKeyDictionary

import readiness as ready
import native_record_candidate as bridge
import counterfactual_source_candidate as owned
import diagnostic_source_candidate as diagnostic
import pair_source_candidate as pair
import pre_census_source_candidate as census
import single_map_source_candidate as single
from rfl_rebuild.b1.contract import fingerprint
from rfl_rebuild.b1.tier import Tier
from rfl_rebuild.b2 import collateral as native_maps
from rfl_rebuild.learner.store import LearnerPersistentState

_PARENT = ready.load_parent()
_CODE_PATHS = tuple(Path(m.__file__) for m in
    (ready, bridge, owned, diagnostic, pair, census, single, native_maps)) + (
    Path(__file__), Path(__file__).with_name("whole_cell_contract_candidate_v20.json"))
_CODE_BINDING = tuple(sha256(p.read_bytes()).hexdigest() for p in _CODE_PATHS)
_STAGES = ("actual_whole_diagnostic", "full_U2_pre_census", "all_original_E1_pre_maps",
           "one_whole_B1_pair", "all_reference_post_maps", "all_treatment_post_maps",
           "full_per_site_diagnostic_seal")
_ROLES = ("reference", "treatment")


class OwnedWholeCellMaps:
    __slots__ = ("__weakref__",)

    def __new__(cls):
        raise ready.ProtocolError("whole maps require their own ordered actual execution")


@dataclass(frozen=True, slots=True)
class _Data:
    source: object
    run: object
    arms: object
    diagnostic_sha: str
    cell_payload: object
    sites: tuple
    census: object
    pair: object
    regions: tuple
    pre_maps: tuple
    clones: tuple
    post_maps: tuple
    sequence: tuple
    payload_sha: object
    route: str


_ISSUED = WeakKeyDictionary()


def _guard():
    single._guard()
    ready.require(tuple(sha256(p.read_bytes()).hexdigest() for p in _CODE_PATHS) == _CODE_BINDING,
                  "whole-cell/dependency/contract bytes changed after loading")


def _context(run, source, arms):
    _guard()
    ds, cell, payload, sites, _ = census._context(run, source, arms)
    if cell is None:
        return ds, payload, (), "SKIPPED_REFLECTION_NO_WHOLE_MAPS_OR_B1"
    binding = bridge.validate_pair(arms)
    ready.require(binding["architecture"] == "D_Q" and
        arms[0].tier is Tier.L0_FACTUAL and binding["treatment_law"] == "FactualReturnWrite",
        "v20 is closed to original D_Q L0 FactualReturnWrite/NoWrite, not P assistance or L2")
    if not sites:
        return ds, payload, (), "NO_DQ_CREDIT_NO_MAPS_OR_B1_NOT_SCIENTIFIC_ZERO"
    ready.require(len(sites) == len(cell.addresses) == len(cell.credited_units) and
        len(set(sites)) == len(sites), "complete unique original D_Q projection required")
    return ds, payload, sites, "OWNED_WHOLE_DQ_CELL_PER_SITE_RAW_DIAGNOSTICS_NOT_COLLECTION"


def _append(sequence, stage, value):
    ready.require(stage == _STAGES[len(sequence)], "whole-cell execution stage order differs")
    content = bridge.sha(value); previous = sequence[-1][2] if sequence else "0" * 64
    sequence.append((stage, content, bridge.sha([previous, stage, content])))


def _census_payload(cd):
    return {"full_census_sha256": bridge.sha([[list(s.key), h, list(flags), ts, rs]
        for s, h, flags, ts, rs in cd.census]),
        "ordered_sites": [s.render() for s in cd.sites],
        "production_payload": list(cd.production_payload)}


def _map_payload(sites, regions, mappings):
    ready.require(type(regions) is type(mappings) is tuple and
        len(sites) == len(regions) == len(mappings), "all sites/maps required, no prefix")
    out = []
    for site, region, mapping in zip(sites, regions, mappings):
        ready.require(type(region) is census.native.UnaffectedSet,
                      "original native E1 object required")
        out.append({"site": site.render(), "construction": region.construction,
            "ordered_unit_keys": [list(s.key) for s in region.units],
            "values_hex": [v.hex() for v in single._values(mapping, region.units)]})
    return out


def _content(d, run, source):
    """Fresh stored-content validation; no new rollouts, maps, diagnosis or B1."""
    ds, whole, sites, route = _context(run, source, d.arms)
    ready.require(d.source is source and d.run is run and ds == d.diagnostic_sha and
        whole == d.cell_payload and sites == d.sites and route == d.route,
        "whole maps belong to another source/diagnostic/complete projection")
    if not sites:
        ready.require(d.census is d.pair is d.payload_sha is None and
            d.regions == d.pre_maps == d.clones == d.post_maps == d.sequence == (),
            "skip/empty cannot carry maps, pair, hash or scientific zero")
        return None, ()
    source_data = owned._checked(source)
    cd = census._checked(d.census, run, source)
    pd = pair._checked_pair(d.pair, run, source)
    ready.require(cd.sites == sites and cd.cell_payload == pd.cell_payload == whole and
        cd.production_payload[2] == (True,) * len(sites) and len(pd.results) == 2,
        "all original production sites and one complete native pair required")
    ready.require(type(d.clones) is type(d.post_maps) is tuple and
        len(d.clones) == len(d.post_maps) == 2 and d.clones[0] is not d.clones[1],
        "complete independent immediate role exports required")
    for i, clone in enumerate(d.clones):
        ready.require(type(clone) is LearnerPersistentState and clone is not source_data.pre_state and
            all(clone is not c for c in pd.clones) and
            fingerprint(clone) == fingerprint(pd.clones[i]),
            "post clone identity/role/immediate native state changed")
    pre = _map_payload(sites, d.regions, d.pre_maps)
    post = tuple(_map_payload(sites, d.regions, m) for m in d.post_maps)
    all_maps = d.pre_maps + d.post_maps[0] + d.post_maps[1]
    ready.require(len({id(m) for m in all_maps}) == 3 * len(sites),
                  "every pre/reference/treatment site map must be independently measured")
    rows = []
    for i, (site, region) in enumerate(zip(sites, d.regions)):
        site.__post_init__()
        ready.require(region.construction == f"E1(c={site.render()})@eligible_all" and
            region.units == tuple(s for s, h, f, ts, rs in cd.census if h and not f[i]),
            "original E1 differs from FULL pre-state H_pre/Consult at this exact site")
        ready.require(pre[i]["values_hex"] == post[0][i]["values_hex"],
                      "NoWrite maps must match elementwise including float bits, not merely means")
        consulted_other = [0] * len(sites)
        eligible = set(region.units)
        for scene, healthy, flags, ts, rs in cd.census:
            if scene in eligible:
                for j, flag in enumerate(flags):
                    consulted_other[j] += int(flag)
        values = tuple(native_maps.behavioral_collateral_scenes(region,
            values_pre=d.pre_maps[i], values_post=d.post_maps[role][i]) for role in range(2))
        ready.require(all(type(v) is float and bridge.finite(v, "per-site raw difference") == v for v in values),
                      "finite native per-site arithmetic required")
        rows.append({"site": site.render(), "E1_size": region.size,
            "ordered_other_credit_consult_counts": consulted_other,
            "ordered_native_raw_difference_hex": [v.hex() for v in values],
            "single_credit_counterfactual_effect": False,
            "unaffected_by_whole_set_claimed": False})
    payload = {"role": "SEEDLESS_WHOLE_DQ_CELL_PER_SITE_DIAGNOSTICS_NOT_PRIMARY_COLLATERAL",
        "diagnostic_sha256": ds, "whole_cell_with_all_residuals": whole,
        "pre_census": _census_payload(cd), "all_pre_maps": pre,
        "ordered_post_maps": [{"role": role, "maps": maps,
            "fingerprint_post": fingerprint(clone)} for role, maps, clone in zip(_ROLES, post, d.clones)],
        "whole_native_pair": pair.pair_audit(d.pair, run, source),
        "per_site_diagnostics_after_same_whole_update": rows,
        "parent_sources_digest": _PARENT["sources_digest"], "lock_sha256": _PARENT["lock_sha256"],
        "multi_credit_region": None, "primary_Collateral_scalar": None,
        "per_site_to_primary_aggregation": None}
    stages = [{"diagnostic_sha256": ds, "whole_cell": whole}, _census_payload(cd), pre,
        payload["whole_native_pair"], payload["ordered_post_maps"][0],
        payload["ordered_post_maps"][1], {"complete_payload_sha256": bridge.sha(payload)}]
    expected = []
    for stage, content in zip(_STAGES, stages): _append(expected, stage, content)
    return payload, tuple(expected)


def run_owned_whole_cell_maps(run, source, arms):
    """One complete pre census; ALL E1 pre maps; ONE whole pair; ALL post maps.

    No supplied pair/map/census/callback/seed/partial selection. Any production,
    native pre or post error issues no partial handle and triggers no retry.
    Per-site reads preserve the whole ledger; no fabricated singleton ledger.
    """
    ds, whole, sites, route = _context(run, source, arms)
    ch = ph = None; regions = pre = clones = post = (); sequence = []; payload_sha = None
    if sites:
        source_data = owned._checked(source)
        try:
            _append(sequence, _STAGES[0], {"diagnostic_sha256": ds, "whole_cell": whole})
            ch = census.prepare_owned_pre_census(run, source, arms)
            cd = census._checked(ch, run, source)
            ready.require(cd.sites == sites and cd.production_payload[2] == (True,) * len(sites),
                          "all production sites required before any map or B1, no partial pass")
            _append(sequence, _STAGES[1], _census_payload(cd))
            regions = tuple(census.native.build_unaffected(site, cd.traces, "eligible_all") for site in sites)
            pre = tuple(single._measure(source_data.pre_state, region, source_data.reference) for region in regions)
            _append(sequence, _STAGES[2], _map_payload(sites, regions, pre))
            ph = pair.run_owned_b1_pair(run, source, arms)
            pd = pair._checked_pair(ph, run, source)
            ready.require(pd.cell_payload == whole and len(pd.results) == 2,
                          "unique B1 pair must consume entire same cell and residuals")
            _append(sequence, _STAGES[3], pair.pair_audit(ph, run, source))
            collected_clones = []; collected_maps = []
            for i, role in enumerate(_ROLES):
                clone = pair.clone_immediate_post(ph, run, source, role=role)
                mappings = tuple(single._measure(clone, region, source_data.reference) for region in regions)
                collected_clones.append(clone); collected_maps.append(mappings)
                _append(sequence, _STAGES[4 + i], {"role": role,
                    "maps": _map_payload(sites, regions, mappings), "fingerprint_post": fingerprint(clone)})
            clones, post = tuple(collected_clones), tuple(collected_maps)
            provisional = _Data(source, run, arms, ds, whole, sites, ch, ph, regions,
                                pre, clones, post, (), None, route)
            payload, expected = _content(provisional, run, source)
            payload_sha = bridge.sha(payload)
            _append(sequence, _STAGES[6], {"complete_payload_sha256": payload_sha})
            ready.require(tuple(sequence) == expected, "actual owner chronology differs from stored content")
        finally:
            _guard(); diagnostic._checked_run(run, source)
            ready.require(bridge.sha(diagnostic.diagnostic_audit(run, source)) == ds,
                          "whole-map execution changed owned source/diagnostic")
    d = _Data(source, run, arms, ds, whole, sites, ch, ph, regions, pre, clones,
              post, tuple(sequence), payload_sha, route)
    _validate(d, run, source)
    handle = object.__new__(OwnedWholeCellMaps); _ISSUED[handle] = d
    return handle


def _validate(d, run, source):
    payload, expected = _content(d, run, source)
    ready.require(type(d.sequence) is tuple and d.sequence == expected,
                  "complete whole-map chronology/content chain changed")
    if payload is not None:
        ready.require(bridge.sha(payload) == d.payload_sha, "complete whole-map raw payload changed")
    return payload


def whole_cell_maps_audit(handle, run, source):
    ready.require(type(handle) is OwnedWholeCellMaps and handle in _ISSUED,
                  "issued whole-map handle required, not detached JSON/hash/pair")
    d = _ISSUED[handle]; payload = _validate(d, run, source)
    return deepcopy({"schema": "a96-owned-whole-cell-per-site-diagnostics-candidate-v20",
        "role": "SEEDLESS_COMPONENT_NOT_SCIENTIFIC_EFFECT_OR_COLLECTION_RECEIPT", "route": d.route,
        "complete_payload": payload, "complete_payload_sha256": d.payload_sha,
        "runtime_content_chain": [list(row) for row in d.sequence],
        "complete_DQ_credited_site_count": len(d.sites),
        "native_U2_pre_rollouts": 5760 if payload else 0,
        "native_scene_map_calls": 3 * len(d.sites), "native_B1_arm_calls": 2 if payload else 0,
        "map_scene_rollouts": 3 * sum(r.size for r in d.regions),
        "all_original_residual_predictions_preserved": bool(payload),
        "owner_pre_before_one_whole_B1_order_in_process": bool(payload),
        "primary_Collateral_scalar": None, "multi_credit_E_S_defined": False,
        "singleton_update_attribution_claimed": False,
        "native_raw_collateral_record_or_future_protocol_fabricated": False,
        "portable_security_or_scientific_acquisition_origin_authenticated": False,
        "environment_seed_draws": 0, "future_training_episodes": 0,
        "full_dense_B2_workload_resources_certified": False,
        "collection_authorized": False, "scientific_claim_authorized": False, "research_complete": False})
