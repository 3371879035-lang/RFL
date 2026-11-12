"""Owned full-U2 RAW pre-state engineering material, not Collateral/gate.

No multi-credit E(S), map mean, B1, future or scientific sampling. These raw
observations do not authenticate pre-before-B1 sequencing for an existing pair.
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
import factual_event_candidate as factual
from rfl_rebuild.b1.contract import fingerprint
from rfl_rebuild.b1.tier import Tier
from rfl_rebuild.b2 import unaffected as native
from rfl_rebuild.env import kernel as K


_CODE_PATHS = tuple(Path(m.__file__) for m in
    (ready, bridge, credit, owned, diagnostic, pair, factual)) + (Path(__file__),)
_CODE_BINDING = tuple(sha256(p.read_bytes()).hexdigest() for p in _CODE_PATHS)
_DOMAIN = native.scene_domain()


class OwnedPreCensus:
    __slots__ = ("__weakref__",)

    def __new__(cls):
        raise ready.ProtocolError("pre-census requires actual owned source/diagnostic construction")


@dataclass(frozen=True, slots=True)
class _Data:
    source: object
    run: object
    arms: object
    diagnostic_sha: str
    cell: object
    cell_payload: object
    sites: tuple
    traces: object
    census: tuple
    production_payload: tuple
    route: str


_ISSUED = WeakKeyDictionary()


def _guard():
    pair._code_guard()
    ready.require(tuple(sha256(p.read_bytes()).hexdigest() for p in _CODE_PATHS) == _CODE_BINDING,
                  "pre-census/dependency bytes changed after loading")
    ready.require(_DOMAIN == native.scene_domain() and len(_DOMAIN) == 5760,
                  "full original U2 support required")


def _context(run, source, arms):
    _guard()
    d = diagnostic._checked_run(run, source)
    ds = bridge.sha(diagnostic.diagnostic_audit(run, source))
    if d.prepared is None:
        return ds, None, None, (), "SKIPPED_REFLECTION_NO_PRE_CENSUS"
    matrix = bridge.validate_pair(arms)
    cell = (diagnostic.prepare_diagnosed_l2_cell(run, source, arms)
        if matrix["architecture"] == "D_Q" and arms[0].tier is Tier.L2_COUNTERFACTUAL
        else diagnostic.prepare_diagnosed_cell(run, source, arms))
    payload = pair._cell_payload(cell, run, source)
    sites = tuple(native.CreditedSite(matrix["architecture"], a) for a in cell.addresses)
    return ds, cell, payload, sites, ("OWNED_FULL_U2_RAW_PRE_MATERIAL_NO_B1_ORDER_CLAIM"
        if sites else "NO_CREDIT_IN_CELL_NO_PRE_CENSUS_NOT_SCIENTIFIC_ZERO")


def _seal(traces, source_data, sites):
    """Inspect ALL stored native traces and incidence; never repeat rollouts."""
    ready.require(type(traces) is native.PreUpdateTraces and traces.learner is source_data.pre_state
        and all(type(getattr(traces, k)) is dict and tuple(getattr(traces, k)) == _DOMAIN
                for k in ("_traces", "_rows", "_walks")),
        "original full ordered native pretraces from this exact learner required")
    for name in ("_traces", "_rows", "_walks"):
        for scene in getattr(traces, name):
            ready.require(type(scene) is native.EvaluationScene, "strict stored native scene key required")
            scene.__post_init__()
    channel = sites[0].channel
    ready.require(type(channel) is str and channel in native.CHANNELS,
                  "registered native channel required, no unknown-channel P fallback")
    production = native.credited_domain(channel, traces)
    ready.require(type(production) is tuple and len(set(production)) == len(production),
                  "full original production credited domain required")
    production_set = set(production)
    production_payload = (len(production), bridge.sha([c.render() for c in production]),
                          tuple(c in production_set for c in sites))
    census = []
    for scene in _DOMAIN:
        ready.require(type(scene) is native.EvaluationScene, "strict original scene required")
        scene.__post_init__()
        trace = traces.trace(scene)
        ready.require(type(trace) is K.RolloutTrace and type(trace.steps) is tuple and trace.steps
            and type(trace.outcome) is str and trace.outcome in (K.Outcome.SUCCESS,) + factual.FAILURES
            and type(trace.base_option) is int and trace.base_option == scene.base_option
            and type(trace.option_in_force) is int and type(trace.mask) is K.FaultMask
            and trace.mask == K.FaultMask() and type(trace.interventions) is K.InterventionSet
            and type(trace.interventions.members) is tuple and not trace.interventions.members
            and type(trace.control) is K.ControlState
            and all(type(v) is int for v in (trace.control.z, trace.control.m))
            and trace.control == trace.steps[-1].control,
            "complete unedited native U2 episode required, never source transient faults/do")
        for i, step in enumerate(trace.steps):
            ready.require(type(step) is K.StepResult and type(step.state) is K.State and
                type(step.control) is K.ControlState and all(type(v) is int for v in
                    (step.state.x, step.state.y, step.state.t, step.state.kappa, step.state.phi,
                     step.control.z, step.control.m, step.a_cmd, step.u, step.a_realized)) and
                type(step.reward) is float and bridge.finite(step.reward, "native pre reward") == step.reward
                and type(step.terminal) is bool and step.terminal == (i == len(trace.steps) - 1)
                and type(step.illegal) is bool and step.outcome == (trace.outcome if step.terminal else None),
                "strict full terminal trace fields required")
        walk = tuple(native._episode_walk(trace, scene))
        stored_walk = traces.walk(scene)
        ready.require(type(stored_walk) is tuple and len(stored_walk) == len(trace.steps) == len(walk)
            and all(type(r) is tuple and len(r) == 3 and type(r[0]) is K.State
                and type(r[1]) is K.ControlState and all(type(v) is int for v in
                    (r[0].x, r[0].y, r[0].t, r[0].kappa, r[0].phi, r[1].z, r[1].m))
                and r[2] is trace.steps[i] for i, r in enumerate(stored_walk))
            and stored_walk == walk,
                      "stored native pre-action walk differs from its own trace")
        expected_rows = tuple((s.x, s.y, s.t, s.kappa, s.phi, c.z, c.m,
            step.a_cmd, step.a_realized, step.reward) for s, c, step in walk)
        rows = traces.rows(scene)
        ready.require(type(rows) is tuple and len(rows) == len(expected_rows), "full native factual rows required")
        for row, expected in zip(rows, expected_rows):
            ready.require(type(row) is tuple and len(row) == 10 and
                all(type(v) is int for v in row[:-1]) and row[:-1] == expected[:-1] and
                type(row[-1]) is float and row[-1].hex() == expected[-1].hex(),
                "pre rows must preserve native true types and original reward bits")
        healthy = traces.successful(scene)
        consulted = traces.consulted(channel, scene)
        ready.require(type(healthy) is bool and healthy == (trace.outcome == K.Outcome.SUCCESS)
            and type(consulted) is tuple and len(set(consulted)) == len(consulted),
            "native H_pre/Consult relation required")
        for c in consulted:
            ready.require(type(c) is native.CreditedSite and c.channel == channel,
                          "native same-channel consulted sites required")
            c.__post_init__(); bridge.SLICES[channel].domain.require_credited(c.address)
        # This is the original consulted relation, not an eligibility aggregate.
        flags = tuple(c in consulted for c in sites)
        trace_payload = {"steps": factual._trace_payload(trace, scene),
                         "metadata": owned._trace_metadata(trace),
                         "final_control": [trace.control.z, trace.control.m]}
        rows_payload = [list(r[:-1]) + [r[-1].hex()] for r in rows]
        census.append((scene, healthy, flags, bridge.sha(trace_payload), bridge.sha(rows_payload)))
    return tuple(census), production_payload


def prepare_owned_pre_census(run, source, arms):
    """Generate full5760 native pre-state observations ONCE, no B1 call."""
    ds, cell, payload, sites, route = _context(run, source, arms)
    traces = None; census = production = ()
    if sites:
        data = owned._checked(source)
        try:
            traces = native.pre_update_traces(learner=data.pre_state, q_reference=data.reference)
            census, production = _seal(traces, data, sites)
        finally:
            _guard(); diagnostic._checked_run(run, source)
            ready.require(bridge.sha(diagnostic.diagnostic_audit(run, source)) == ds,
                          "pre-census construction changed its actual diagnostic/source")
    handle = object.__new__(OwnedPreCensus)
    _ISSUED[handle] = _Data(source, run, arms, ds, cell, payload, sites,
                           traces, census, production, route)
    _checked(handle, run, source)
    return handle


def _checked(handle, run, source):
    ready.require(type(handle) is OwnedPreCensus and handle in _ISSUED,
                  "issued pre-census required, not audit/hash/supplied native traces")
    d = _ISSUED[handle]
    ready.require(d.run is run and d.source is source, "pre-census belongs to another actual source/run")
    ds, cell, payload, sites, route = _context(run, source, d.arms)
    ready.require(ds == d.diagnostic_sha and payload == d.cell_payload and sites == d.sites and route == d.route,
                  "whole original credit/source/cell changed after pre-census")
    ready.require(type(d.sites) is tuple, "complete site tuple required")
    for c in d.sites:
        ready.require(type(c) is native.CreditedSite and type(c.channel) is str and c.channel in native.CHANNELS,
                      "strict registered captured credited site required")
        c.__post_init__(); bridge.SLICES[c.channel].domain.require_credited(c.address)
    if cell is not None:
        ready.require(pair._cell_payload(d.cell, run, source) == payload, "captured original cell differs")
    if not sites:
        ready.require(d.traces is None and d.census == () and d.production_payload == (),
                      "skipped/empty projection has no zero-filled census")
    else:
        ready.require(type(d.production_payload) is tuple and len(d.production_payload) == 3 and
            type(d.production_payload[0]) is int and d.production_payload[0] > 0 and
            type(d.production_payload[1]) is str and len(d.production_payload[1]) == 64 and
            type(d.production_payload[2]) is tuple and len(d.production_payload[2]) == len(sites) and
            all(type(v) is bool for v in d.production_payload[2]), "typed complete production membership required")
        ready.require(type(d.census) is tuple and len(d.census) == len(_DOMAIN), "full5760 captured census required")
        for row, scene in zip(d.census, _DOMAIN):
            ready.require(type(row) is tuple and len(row) == 5 and type(row[0]) is native.EvaluationScene
                and row[0] == scene and type(row[1]) is bool and type(row[2]) is tuple
                and len(row[2]) == len(sites) and all(type(v) is bool for v in row[2])
                and all(type(v) is str and len(v) == 64 for v in row[3:]),
                "complete ordered typed census and incidence columns required")
            row[0].__post_init__()
        actual, production = _seal(d.traces, owned._checked(source), sites)
        ready.require(actual == d.census and production == d.production_payload,
                      "stored full native trace/row/incidence/production content changed")
    return d


def pre_census_audit(handle, run, source):
    """Full detached evaluator audit is never an issued scientific capability."""
    d = _checked(handle, run, source)
    data = owned._checked(source)
    return deepcopy({"schema": "a96-owned-pre-U2-census-candidate-v10",
        "role": "SEEDLESS_RAW_PRE_STATE_MATERIAL_NOT_COLLATERAL_OR_SCIENTIFIC_RECEIPT",
        "route": d.route, "diagnostic_audit_sha256": d.diagnostic_sha, "cell": d.cell_payload,
        "source_fingerprint_pre": data.fingerprint_pre,
        "q_reference_sha256": data.reference.digest(),
        "parent_sources_digest": data.audit["parent_sources_digest"], "lock_sha256": data.audit["lock_sha256"],
        "healthy_reference_canonical_payload_sha256": data.audit["healthy_reference_canonical_payload_sha256"],
        "ordered_credited_sites": [c.render() for c in d.sites],
        "production_domain_size": d.production_payload[0] if d.sites else None,
        "production_domain_sha256": d.production_payload[1] if d.sites else None,
        "production_membership": list(d.production_payload[2]) if d.sites else [],
        "full_ordered_census": [[list(s.key), h, list(flags), ts, rs] for s, h, flags, ts, rs in d.census],
        "census_sha256": bridge.sha([[list(s.key), h, list(flags), ts, rs] for s, h, flags, ts, rs in d.census])
            if d.sites else None,
        "native_U2_pre_rollouts": len(d.census), "B1_arm_calls": 0,
        "environment_seed_draws": 0, "future_training_episodes": 0,
        "pre_before_B1_execution_order_authenticated": False,
        "multi_credit_unaffected_region_defined": False, "primary_Collateral_scalar_defined": False,
        "scientific_admissibility_or_F1_threshold_claimed": False,
        "collection_authorized": False, "scientific_claim_authorized": False, "research_complete": False})
