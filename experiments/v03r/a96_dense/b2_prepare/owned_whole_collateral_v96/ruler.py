"""Owned fullpre -> sanitized complete S -> shared C -> original whole B1 -> I_post.

An explicit candidate instrument; no old singleton API changes, no fake D_Q
handle for patch, no fitted threshold/family or science collection authority.
"""
from copy import deepcopy
from dataclasses import dataclass, field
from weakref import WeakKeyDictionary

import adaptive_training as A
import handoff as H
import oracle_mainline_v75 as O
import instrument as M
from rfl_rebuild.b2.environment import learner_channels
from rfl_rebuild.b2.unaffected import scene_domain
from rfl_rebuild.env import kernel as K


class PreparedWhole:
    __slots__ = ('__weakref__',)
    def __new__(cls):
        raise A.ProtocolError('genuine pre-arm owned preparation required')


class WholeMeasurement:
    __slots__ = ('__weakref__',)
    def __new__(cls):
        raise A.ProtocolError('only a complete owned measured pair can issue this result')


@dataclass
class _Prepared:
    bound: object
    architecture: str
    assisted: object
    projected: object
    pre_input: object
    records: tuple
    owners: tuple
    region: object
    status: str
    origin: dict
    seal: str
    attempts: dict = field(default_factory=dict)


@dataclass(frozen=True)
class _Measured:
    prepared: object
    pair: object
    starts: tuple
    records: tuple
    shared_units: tuple
    payload: dict
    seal: str


_PREPARED = WeakKeyDictionary()
_SOURCE_PRE_ATTEMPTS = WeakKeyDictionary()
_MEASURED = WeakKeyDictionary()


def _owner(architecture, address):
    if architecture == 'P':
        return M.Owner('process', (address,))
    s = address.state
    key = (s.x, s.y, s.t, s.kappa, s.phi)
    return M.Owner('decision', key+(address.z, address.m)) if architecture in ('D_Q', 'D_patch') else M.Owner('controller', key+(int(address.cmd),))


def _run_scene(channels, scene, stage):
    command, controller, process = channels
    return K.rollout(kappa=scene.kappa, tape=scene.tape, base_option=scene.base_option,
                     command_provider=command, controller=controller,
                     learner_process_commit=process)


def _ordinary_bank(state, reference, ordered_units, stage, collected):
    before = A.stores(state)
    snapshot = state.snapshot()
    command, controller = learner_channels(snapshot, reference)
    channels = (command, controller, snapshot.process_commit_provider())
    try:
        for scene in ordered_units:
            trace = _run_scene(channels, scene, stage)
            A.require(type(trace) is K.RolloutTrace and trace.steps and trace.steps[-1].terminal
                      and trace.steps[-1].outcome == trace.outcome and trace.mask == K.FaultMask()
                      and not trace.interventions.members and trace.base_option == scene.base_option
                      and trace.option_in_force == snapshot.process_overrides.get(scene.base_option, scene.base_option),
                      'ordinary complete actual option/configuration required')
            collected.append(M.PreRecord(scene, trace))
    finally:
        A.require(A.stores(state) == before, 'readonly ordinary bank wrote complete state')


def prepare(bound, *, architecture, assisted=None):
    source, sd = H._checked_source(bound)
    A.require(bound not in _SOURCE_PRE_ATTEMPTS, 'pre-census already attempted; no retry')
    A.require(not H._ATTEMPTS[bound], 'region must be prepared before any B1 arm')
    A.require(architecture in O.base.SLICES and (architecture not in ('D_Q', 'D_patch') or
              architecture == ('D_Q' if source.mode == 'dq' else 'D_patch')), 'architecture differs from pre-bound mode')
    _SOURCE_PRE_ATTEMPTS[bound] = {'stage': 'projection_started', 'records': []}
    gamma = () if sd.truth is None else tuple(sd.truth['Gamma_P_star' if sd.regime == 'P' else 'Gamma_T_star'])
    projected = O.base._project(sd.evidence, gamma, architecture, assisted) if gamma else O.base._Projection((), (), (), ())
    owners = tuple(_owner(architecture, a) for a in projected.addresses)
    origin = {'bound_before_arms': H.source_audit(bound), 'architecture': architecture,
              'all_manifestations': projected.whole_units, 'cell_manifestations': projected.cell_units,
              'residual_manifestations': projected.residual_units, 'owners': owners,
              'full_pre': A.stores(sd.pre), 'reference_digest': sd.reference.digest(),
              'S_selection': 'complete original rho before arms, never receipt/WriteSet/effect'}
    collected = _SOURCE_PRE_ATTEMPTS[bound]['records']
    _SOURCE_PRE_ATTEMPTS[bound]['stage'] = 'full_pre_census'
    try:
        _ordinary_bank(sd.pre, sd.reference, scene_domain(), 'pre', collected)
    finally:
        H._checked_source(bound)
    records = tuple(collected)
    pre_input = M._issue_pre_input(records, owners)
    region, status = M.build(pre_input)
    origin.update({'pre_input_pin': M._checked_input(pre_input)[2], 'status': status,
                   'pre_rollouts': len(records), 'candidate_not_final_scientific_rule': True})
    handle = object.__new__(PreparedWhole)
    _PREPARED[handle] = _Prepared(bound, architecture, deepcopy(assisted), projected,
        pre_input, records, owners, region, status, deepcopy(origin), A.digest(origin))
    _SOURCE_PRE_ATTEMPTS[bound]['stage'] = status
    _checked_prepared(handle)
    return handle


def _checked_prepared(handle):
    A.require(type(handle) is PreparedWhole and handle in _PREPARED, 'issued pre-arm preparation required')
    d = _PREPARED[handle]
    source, sd = H._checked_source(d.bound)
    A.require(A.digest(d.origin) == d.seal and H.source_audit(d.bound) == d.origin['bound_before_arms']
              and A.stores(sd.pre) == d.origin['full_pre'] and d.owners == tuple(_owner(d.architecture, a) for a in d.projected.addresses)
              and d.owners == M._checked_input(d.pre_input)[1] and d.status == d.origin['status'],
              'pre/source/all owners changed')
    return d, source, sd


def run_cell(handle, *, tier, law_name):
    d, source, sd = _checked_prepared(handle)
    A.require(d.status == 'READY' and d.region is not None, 'undefined region has no B1/measurement value')
    O.base._registered(d.architecture, tier, law_name)
    cell = (tier.name, law_name)
    A.require(cell not in d.attempts, 'whole measurement already attempted; no retry')
    partial = {'stage': 'B1_started', 'records': [[], []], 'pair': None, 'starts': ()}
    d.attempts[cell] = partial  # before any native arm or post replay
    pair = H.run_whole_pair(d.bound, architecture=d.architecture, tier=tier,
                            law_name=law_name, assisted=d.assisted)
    partial['pair'] = pair
    _, _, native, declaration, pair_seal = H._checked_original_pair(d.bound, pair)
    A.require(native.projected == d.projected and len(native.clones) == 2, 'whole owner/residual/complete B1 provenance differs')
    starts = tuple(c.clone() for c in native.clones)
    partial['starts'] = starts
    A.require(starts[0] is not starts[1] and all(s is not sd.pre and all(s is not c for c in native.clones)
              and A.stores(s) == A.stores(c) for s, c in zip(starts, native.clones)), 'fresh full immediate roles required')
    ordered = M.units(d.region)  # ONE exact tuple, shared with both measured roles
    scores = []
    for i, role in enumerate(H.ROLES):
        partial['stage'] = role+'_post_measurement'
        try:
            _ordinary_bank(starts[i], sd.reference, ordered, role, partial['records'][i])
        finally:
            H._checked_original_pair(d.bound, pair)
            A.require(all(A.stores(s) == A.stores(c) for s, c in zip(starts, native.clones)), 'I_post drifted during measurement')
        post_map = {r.scene: float(r.trace.return_value) for r in partial['records'][i]}
        scores.append(M.loss(d.region, post_map))
    payload = {'origin_sha256': d.seal, 'original_pair_declaration': declaration,
               'original_pair_sha256': pair_seal, 'full_immediate_posts': [A.stores(c) for c in native.clones],
               'region': M.audit(d.region), 'scores': scores,
               'paired_difference': scores[0]['value']-scores[1]['value'],
               'complete_post_rollouts': [len(x) for x in partial['records']],
               'post_records_sha256': A.digest(tuple(tuple(x) for x in partial['records'])),
               'scientific_qualification': False, 'future_training': 0}
    result = object.__new__(WholeMeasurement)
    _MEASURED[result] = _Measured(handle, pair, starts, tuple(tuple(x) for x in partial['records']),
                                 ordered, deepcopy(payload), A.digest(payload))
    partial['stage'] = 'COMPLETE'
    _checked_result(result)
    return result


def _checked_result(handle):
    A.require(type(handle) is WholeMeasurement and handle in _MEASURED, 'issued complete measurement required')
    md = _MEASURED[handle]
    d, _, sd = _checked_prepared(md.prepared)
    _, _, native, declaration, seal = H._checked_original_pair(d.bound, md.pair)
    A.require(md.shared_units is M.units(d.region) and len(md.records) == 2
              and A.digest(md.payload) == md.seal and md.payload['original_pair_declaration'] == declaration
              and md.payload['original_pair_sha256'] == seal
              and md.payload['post_records_sha256'] == A.digest(md.records)
              and all(tuple(r.scene for r in records) == md.shared_units for records in md.records)
              and md.starts[0] is not md.starts[1] and all(s is not sd.pre and all(s is not c for c in native.clones)
              and A.stores(s) == A.stores(c) for s, c in zip(md.starts, native.clones)),
              'shared region/full I_post/complete records changed')
    return md


def preparation_audit(handle):
    d, _, _ = _checked_prepared(handle)
    return deepcopy({'origin': d.origin, 'origin_sha256': d.seal, 'complete_pre_records': d.records,
                     'region': M.audit(d.region) if d.region is not None else None})


def audit(handle):
    d = _checked_result(handle)
    return deepcopy({'payload': d.payload, 'payload_sha256': d.seal, 'ordered_post_records': d.records})


def partial_audit(handle, *, tier, law_name):
    d, _, _ = _checked_prepared(handle)
    cell = (tier.name, law_name)
    A.require(cell in d.attempts and d.attempts[cell]['stage'] != 'COMPLETE', 'actual partial attempt required')
    p = d.attempts[cell]
    return deepcopy({'origin_sha256': d.seal, 'stage': p['stage'], 'ordered_records': p['records'],
                     'full_starts': [A.stores(s) for s in p['starts']],
                     'original_pair': O.pair_audit(p['pair'], H._SOURCES[d.bound].original) if p['pair'] else None,
                     'has_measurement_handle': False, 'automatic_retry': False})
