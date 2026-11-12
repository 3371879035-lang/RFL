"""One exact recorded pre-census -> NEW actually issued source, before arms.

The source/pair/role are never deserialized. RecordedTrace is an explicit data
type, not a forged K.RolloutTrace or a new kernel execution. Transfer is allowed
only on exact fullpre/reference/dependency/domain/configuration binding. The
original kernel is deterministic on the declared ordinary inputs; equal full
channels and tape keys imply the same path by step induction.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from weakref import WeakKeyDictionary

import adaptive_training as A
import handoff as H
from wire_boundary import seal as canonical_seal
from rfl_rebuild.b2.unaffected import EvaluationScene, scene_domain
from rfl_rebuild.env import kernel as K
from rfl_rebuild.learner.store import DecisionAddress, QAddress
from recorded import RecordedTrace, decode

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
OLD=ROOT/'experiments/v03r/a96_dense/b2_prepare/owned_whole_collateral_v96'
EXPECTED_STDOUT='8fd385c23d503b8ba6efbc7fcc9eb8e1547f4e2210615a8a11385b1929197104'


class RecordedOrdinaryCensus:
    __slots__=('__weakref__',)
    def __new__(cls):
        raise A.ProtocolError('only exact artifact-to-genuine-source transfer can issue this type')


@dataclass(frozen=True)
class _Data:
    bound: object
    rows: tuple
    fullpre: dict
    reference_digest: str
    payload: dict
    seal: str


_ATTEMPTS=WeakKeyDictionary()
_RECORDED=WeakKeyDictionary()


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_for(bound):
    source,sd=H._checked_source(bound)
    A.require(source.mode=='dq' and not H._ATTEMPTS[bound], 'only actual DQ source before B1 arms')
    A.require(bound not in _ATTEMPTS, 'recorded transfer already attempted; no retry')
    _ATTEMPTS[bound]=True
    claim=json.loads((OLD/'evidence/claim.json').read_bytes())
    exit_record=json.loads((OLD/'evidence/exit.json').read_bytes())
    old_contract=json.loads((OLD/'contract.json').read_bytes())
    A.require(exit_record['child_exit_code']==1 and claim['input_binding_before']==exit_record['input_binding_after']
              and exit_record['stdout']['sha256']==EXPECTED_STDOUT and _sha(OLD/'evidence/stdout.log')==EXPECTED_STDOUT,
              'exact failed capture with preserved completed pre-census required')
    pins=claim['input_binding_before']
    frozen=json.loads((ROOT/old_contract['frozen_manifest']).read_bytes())['sources']
    dependencies=set(frozen)|{old_contract['reference_input']['path'],old_contract['frozen_manifest'],
        'experiments/v03r/a96_dense/b2_prepare/owned_whole_collateral_v96/ruler.py',
        'experiments/v03r/a96_dense/b2_prepare/owned_whole_collateral_v96/instrument.py',
        'experiments/v03r/a96_dense/b2_prepare/owned_whole_collateral_v96/test_whole.py'}
    dependency_pins={name:pins[name]['sha256'] for name in sorted(dependencies)}
    A.require(all(_sha(ROOT/name)==p for name,p in dependency_pins.items()), 'ordinary producer/kernel/reference dependencies changed')
    old_state=None;old_reference=None;declared_units=None;parsed=[];stats={}
    with (OLD/'evidence/stdout.log').open(encoding='utf-8') as stream:
        for physical in stream:
            A.require(physical.endswith('\n'), 'incomplete stored JSONL')
            line=physical.rstrip('\r\n');record=json.loads(line)
            A.require(json.dumps(record,sort_keys=True,separators=(',',':'),ensure_ascii=True)==line, 'noncanonical stored record')
            p=record['payload']
            if record['tag']=='REFERENCE':old_reference=p['digest']
            if record['mode']=='dq' and record['tag']=='BANK_BEGIN' and p['stage']=='pre':
                A.require(old_state is None,'duplicate pre-bank header')
                old_state=p['state'];declared_units=tuple(tuple(s) for s in p['units'])
                A.require(old_state==A.stores(sd.pre),'new actual fullpre differs from old measured fullpre')
            if record['mode']=='dq' and record['tag']=='RAW_ROLLOUT' and p['stage']=='pre':
                A.require(old_state is not None,'raw before fullpre header')
                scene=EvaluationScene(*p['scene']);trace=decode(p['trace'])
                A.require(A.wire(trace)==p['trace'],'recorded geometry/value encoding changed')
                A.require(scene.key==declared_units[len(parsed)],'ordered pre-census gap/duplicate')
                A.require(trace.base_option==scene.base_option and trace.option_in_force==sd.pre.process_overrides.get(scene.base_option,scene.base_option),
                          'recorded ordinary proposal/in-force differs')
                state=K.State(*K.START,0,scene.kappa,scene.phase);z,m=trace.option_in_force,0
                for step in trace.steps:
                    row=sd.reference.row(state,z,m)
                    effective={a:sd.pre.q_overrides.get(QAddress(state,z,m,a),v) for a,v in row.items()}
                    best=max(effective.values());cmd=sd.pre.decision_overrides.get(DecisionAddress(state,z,m),min(a for a,v in effective.items() if v==best))
                    A.require(step.a_cmd==cmd and cmd in row and step.u==sd.pre.controller_overrides.get(K.ControllerSite(state,cmd),cmd),
                              'recorded full-current read path differs')
                    A.require(step.state.kappa==scene.kappa and step.state.phi==scene.phase,'recorded context drift')
                    state=step.state;z,m=step.control.z,step.control.m
                parsed.append((scene,trace));stats[trace.outcome]=stats.get(trace.outcome,0)+1
    domain=scene_domain()
    A.require(len(parsed)==5760 and tuple(s for s,t in parsed)==domain
              and declared_units==tuple(s.key for s in domain) and old_reference==sd.reference.digest(),
              'complete exact pre-domain/reference required')
    payload={'old_native_capture_sha256':EXPECTED_STDOUT,'old_native_exit_preserved':1,
             'actual_new_fullpre_sha256':canonical_seal(A.stores(sd.pre)), 'reference_digest':sd.reference.digest(),
             'dependencies':dependency_pins,'old_ordinary_producer':'v96/ruler._ordinary_bank -> learner_channels -> original K.rollout',
             'ordinary_configuration':{'mask':'empty','option_fault':None,'interventions':[],'reward_mode':'A'},
             'full_pre_records':len(parsed),'outcomes':stats,'recorded_rows_sha256':canonical_seal(tuple(parsed)),
             'new_kernel_replays':0,'old_source_pair_role_identity_reconstructed':False,
             'proof_scope':'Exact ordinary deterministic fullpre/channel/reference/kernel/U2 binding; no finite-key probability or new science population claim.'}
    handle=object.__new__(RecordedOrdinaryCensus)
    _RECORDED[handle]=_Data(bound,tuple(parsed),A.stores(sd.pre),sd.reference.digest(),payload,canonical_seal(payload))
    _checked(handle,bound)
    return handle


def _checked(handle,bound):
    A.require(type(handle) is RecordedOrdinaryCensus and handle in _RECORDED,'issued recorded census transfer required')
    d=_RECORDED[handle];source,sd=H._checked_source(bound)
    A.require(d.bound is bound and source.mode=='dq' and d.fullpre==A.stores(sd.pre)
              and d.reference_digest==sd.reference.digest() and canonical_seal(d.payload)==d.seal
              and canonical_seal(d.rows)==d.payload['recorded_rows_sha256']
              and all(type(t) is RecordedTrace for s,t in d.rows),'recorded source/content/binding changed')
    return d


def rows(handle,bound):
    return _checked(handle,bound).rows


def audit(handle,bound):
    d=_checked(handle,bound)
    return {'payload':d.payload,'payload_sha256':d.seal}
