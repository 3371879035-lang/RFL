"""Explicit whole-owner candidate, consuming only issued ordinary PRE records.

No arm, law, tier, source audit, truth, write target or receipt is a constructor
input. Ownership of the records is established by ruler.py's audited flow.
This in-process boundary is not a hostile-Python sandbox or a science gate.
"""
from dataclasses import dataclass, fields, is_dataclass
from hashlib import sha256
import json
import math
from types import MappingProxyType
from weakref import WeakKeyDictionary

from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b2.unaffected import EvaluationScene, scene_domain
from rfl_rebuild.env import kernel as K
from recorded import RecordedTrace


def require(condition, message):
    if not condition:
        raise ProtocolError(message)


def wire(value):
    if is_dataclass(value):
        return {f.name: wire(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, float):
        return {'binary64_hex': value.hex()}
    if isinstance(value, (tuple, list)):
        return [wire(x) for x in value]
    if isinstance(value, dict):
        return {k: wire(v) for k, v in value.items()}
    return value


def pin(value):
    return sha256(json.dumps(wire(value), sort_keys=True, separators=(',', ':'),
                             ensure_ascii=True).encode('ascii')).hexdigest()


@dataclass(frozen=True, slots=True)
class Owner:
    channel: str
    key: tuple

    def __post_init__(self):
        sizes = {'decision': 7, 'controller': 6, 'process': 1}
        require(type(self.channel) is str and self.channel in sizes, 'closed owner channel')
        require(type(self.key) is tuple and len(self.key) == sizes[self.channel]
                and all(type(x) is int for x in self.key), 'exact integer owner fields')
        if self.channel == 'process':
            require(self.key[0] in K.option_ids(), 'proposal outside domain')
        else:
            K.State(*self.key[:5])
            require(self.key[3] in (0, 1) and self.key[4] in K.PHASE_DOMAIN
                    and 0 <= self.key[2] < K.HORIZON, 'owner context outside domain')
            require((self.key[5] in K.option_ids() and self.key[6] in (0, 1))
                    if self.channel == 'decision' else self.key[5] in range(5),
                    'owner control outside domain')


@dataclass(frozen=True, slots=True)
class PreRecord:
    scene: EvaluationScene
    trace: K.RolloutTrace | RecordedTrace


class PreInput:
    __slots__ = ('__weakref__',)
    def __new__(cls):
        raise ProtocolError('only the owned pre-census can issue inputs')


class Region:
    __slots__ = ('__weakref__',)
    def __new__(cls):
        raise ProtocolError('only the checked full pre-input can issue a region')


_INPUTS = WeakKeyDictionary()
_REGIONS = WeakKeyDictionary()


def consulted(owner, scene, trace):
    require(type(owner) is Owner and type(scene) is EvaluationScene
            and type(trace) in (K.RolloutTrace, RecordedTrace), 'nominal consultation inputs required')
    if owner.channel == 'process':
        return owner.key == (scene.base_option,)
    state = K.State(*K.START, 0, scene.kappa, scene.phase)
    control = K.initial_control(trace.option_in_force)
    for step in trace.steps:
        key = (state.x, state.y, state.t, state.kappa, state.phi)
        key += (control.z, control.m) if owner.channel == 'decision' else (int(step.a_cmd),)
        if owner.key == key:
            return True
        state, control = step.state, step.control
    return False


def _issue_pre_input(records, owners):
    require(type(records) is tuple and type(owners) is tuple
            and all(type(x) is Owner for x in owners) and len(set(owners)) == len(owners),
            'complete exact ordered typed owner tuple required')
    require(tuple(x.scene for x in records) == scene_domain(), 'complete ordered U2 required')
    for r in records:
        require(type(r) is PreRecord and type(r.scene) is EvaluationScene
                and type(r.trace) in (K.RolloutTrace, RecordedTrace), 'complete nominal pre records')
        t = r.trace
        require(t.steps and t.steps[-1].terminal and t.steps[-1].outcome == t.outcome
                and t.base_option == r.scene.base_option and t.mask == K.FaultMask()
                and not t.interventions.members and math.isfinite(t.return_value),
                'ordinary complete no-fault/no-do pre record required')
    handle = object.__new__(PreInput)
    _INPUTS[handle] = (records, owners, pin((records, owners)))
    return handle


def _checked_input(handle):
    require(type(handle) is PreInput and handle in _INPUTS, 'issued complete pre input required')
    records, owners, seal = _INPUTS[handle]
    require(pin((records, owners)) == seal, 'ordinary pre input/owner content changed')
    return records, owners, seal


def require_extent(domain, units):
    require(type(units) is tuple and all(type(x) is EvaluationScene for x in units),
            'exact scene tuple required')
    require(units and len(units) < len(domain), 'region must be nonempty and proper')
    members = set(units)
    require(len(members) == len(units) and units == tuple(x for x in domain if x in members),
            'region duplicate/outside/original-order drift')


def build(handle):
    records, owners, seal = _checked_input(handle)
    if not owners:
        return None, 'EMPTY_OWNERS'
    selected = tuple(r for r in records if r.trace.outcome == K.Outcome.SUCCESS
                     and not any(consulted(c, r.scene, r.trace) for c in owners))
    units = tuple(r.scene for r in selected)
    if not units:
        return None, 'EMPTY_REGION'
    if len(units) == len(records):
        return None, 'NONPROPER_REGION'
    require_extent(tuple(r.scene for r in records), units)
    result = object.__new__(Region)
    pre_map = MappingProxyType({r.scene: float(r.trace.return_value) for r in selected})
    _REGIONS[result] = (handle, seal, units, pre_map, pin(tuple((u.key, pre_map[u]) for u in units)))
    return result, 'READY'


def _checked_region(region):
    require(type(region) is Region and region in _REGIONS, 'issued whole region required')
    source, seal, units, pre_map, values_pin = _REGIONS[region]
    records, owners, actual_seal = _checked_input(source)
    require(actual_seal == seal and units == tuple(r.scene for r in records
        if r.trace.outcome == K.Outcome.SUCCESS and not any(consulted(c, r.scene, r.trace) for c in owners)),
        'shared pre-region content/provenance changed')
    require(set(pre_map) == set(units) and values_pin == pin(tuple((u.key, pre_map[u]) for u in units)),
            'pre measured map changed')
    return units, pre_map


def units(region):
    return _checked_region(region)[0]


def loss(region, post_map):
    ordered, pre_map = _checked_region(region)
    require(type(post_map) is dict and set(post_map) == set(ordered), 'exact post-map coverage required')
    require(all(type(v) is float and math.isfinite(v) for v in post_map.values()), 'finite actual returns')
    # The original functional: TWO separate left-to-right sums, then subtraction.
    pre = sum(float(pre_map[u]) for u in ordered) / len(ordered)
    post = sum(float(post_map[u]) for u in ordered) / len(ordered)
    return {'pre_mean': pre, 'post_mean': post, 'value': pre-post}


def audit(region):
    ordered, pre_map = _checked_region(region)
    return {'units': [u.key for u in ordered],
            'pre_values': [(u.key, pre_map[u]) for u in ordered]}
