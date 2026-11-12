"""Exact recorded ordinary post banks bound to a NEW genuine native pair.

This is not cache-by-policy/effect and never recreates old source/pair/role
objects. RecordedTrace is a data type. Complete four-store inputs, reference,
original producer, owners, region, role receipts and every raw row must match.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from weakref import WeakKeyDictionary

import adaptive_training as A
import handoff as H
import instrument as M
import ruler as R
from recorded import RecordedTrace, decode
from wire_boundary import seal
from rfl_rebuild.env import kernel as K
from rfl_rebuild.b2.unaffected import EvaluationScene
from rfl_rebuild.learner.store import DecisionAddress, QAddress

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
OLD=HERE.parent/'owned_whole_completion_v98'
EXPECTED_RAW='cb8766e9665e1b99ea7045bfaa52381c01b33f83829928234593a9898a53d53d'


class RecordedImmediateBanks:
    __slots__=('__weakref__',)
    def __new__(cls):
        raise A.ProtocolError('requires exact data bound to a genuinely issued native pair')


@dataclass(frozen=True)
class _Data:
    prepared: object
    pair: object
    starts: tuple
    rows: tuple
    ordered: tuple
    posts: tuple
    payload: dict
    seal: str


_ATTEMPTS=WeakKeyDictionary()
_RECORDED=WeakKeyDictionary()


def _sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def _physical_lines():
    with (OLD/'evidence/stdout.log').open(encoding='ascii') as stream:
        yield from stream


def _actual_binding(prepared,pair,starts):
    d,source,sd=R._checked_prepared(prepared)
    _,_,native,declaration,pair_seal=H._checked_original_pair(d.bound,pair)
    A.require(d.architecture=='D_Q' and source.mode=='dq' and d.status=='READY'
              and declaration['architecture']=='D_Q' and declaration['tier']=='L0_FACTUAL'
              and declaration['law_name']=='FactualReturnWrite', 'exact prospective DQ L0 cell required')
    A.require(type(starts) is tuple and len(starts)==2 and starts[0] is not starts[1]
              and all(s is not sd.pre and all(s is not c for c in native.clones)
                      and A.stores(s)==A.stores(c) for s,c in zip(starts,native.clones)),
              'complete fresh native immediate roles, in original order, required')
    A.require(native.projected==d.projected,'complete owner/residual provenance differs')
    return d,sd,native,pair_seal


def load_for(prepared,pair,starts):
    d,sd,native,pair_seal=_actual_binding(prepared,pair,starts)
    A.require(pair not in _ATTEMPTS,'post transfer already attempted; no retry')
    progress={'stage':'binding_started','rows':[[],[]]}
    _ATTEMPTS[pair]=progress  # BEFORE artifact reads, including a partial failure
    claim=json.loads((OLD/'evidence/claim.json').read_bytes())
    timeout=json.loads((OLD/'evidence/timeout.json').read_bytes())
    A.require(not (OLD/'evidence/exit.json').exists() and timeout['native_exit_not_fabricated']
              and not timeout['automatic_retry'] and _sha(OLD/'evidence/stdout.log')==EXPECTED_RAW,
              'exact preserved timeout capture required; do not manufacture native exit')
    old_contract=json.loads((OLD/'contract.json').read_bytes())
    original_manifest=json.loads((ROOT/old_contract['frozen_manifest']).read_bytes())['sources']
    names=set(original_manifest)|{old_contract['frozen_manifest'],old_contract['reference_input']['path']}
    names|={str((OLD/x).relative_to(ROOT)).replace('\\','/') for x in
            ('ruler.py','instrument.py','recorded.py','test_completion.py')}
    dependencies={n:claim['input_binding_before'][n]['sha256'] for n in sorted(names)}
    A.require(all(_sha(ROOT/n)==h for n,h in dependencies.items()),'ordinary producer/kernel/reference changed')
    ordered=M.units(d.region)
    posts=tuple(A.stores(s) for s in starts)
    old_pre=None;old_prep=None;old_ref=None;headers={};old_b1=[];seen_roles=[]
    progress['stage']='reading_records'
    for physical in _physical_lines():
        A.require(physical.endswith('\n'),'incomplete stored EOF')
        line=physical.rstrip('\r\n');packet=json.loads(line)
        A.require(json.dumps(packet,sort_keys=True,separators=(',',':'),ensure_ascii=True)==line,'noncanonical stored row')
        tag,mode,p=packet['tag'],packet['mode'],packet['payload']
        if tag=='REFERENCE':old_ref=p['digest']
        if mode!='dq':continue
        if tag=='FULL_SOURCE_PRE':
            A.require(old_pre is None and p['stores']==A.stores(sd.pre),'complete new fullpre differs')
            old_pre=p['stores']
        elif tag=='PREPARATION_COMPLETE':
            A.require(old_prep is None and old_pre is not None,'unique complete pre origin required')
            old_prep=p
            A.require(p['origin']['architecture']=='D_Q' and p['origin']['full_pre']==A.stores(sd.pre)
                      and p['origin']['reference_digest']==sd.reference.digest()
                      and p['origin']['owners']==A.wire(d.owners)
                      and p['origin']['all_manifestations']==A.wire(d.projected.whole_units)
                      and p['origin']['cell_manifestations']==A.wire(d.projected.cell_units)
                      and p['origin']['residual_manifestations']==A.wire(d.projected.residual_units)
                      and p['region']==A.wire(M.audit(d.region)), 'complete owner/region/pre map differs')
        elif tag=='NATIVE_B1_RETURN':
            i=len(old_b1)
            A.require(i<2 and p['full_post']==posts[i] and p['receipts']==A.wire(native.results[i].ledger.receipts)
                      and p['ledger_canonical']==native.results[i].ledger.canonical()
                      and p['law']==('NoWrite' if i==0 else 'FactualReturnWrite'),
                      'actual native fullpost/role/allreceipts/scalar accounting differs')
            old_b1.append(p)
        elif tag=='BANK_BEGIN' and p['stage'] in H.ROLES:
            role=p['stage'];i=H.ROLES.index(role)
            A.require(old_prep is not None and len(old_b1)==2 and role not in headers
                      and p['state']==posts[i] and tuple(tuple(x) for x in p['units'])==tuple(s.key for s in ordered),
                      'complete matching ordinary role header/order required')
            A.require(seen_roles==list(H.ROLES[:i]),'ordinary role chronology differs')
            seen_roles.append(role);headers[role]=p
        elif tag=='RAW_ROLLOUT' and p['stage'] in H.ROLES:
            role=p['stage'];i=H.ROLES.index(role);collected=progress['rows'][i]
            A.require(role in headers and len(collected)<len(ordered),'raw without header/excess rows')
            scene=EvaluationScene(*p['scene']);trace=decode(p['trace'])
            A.require(type(trace) is RecordedTrace and A.wire(trace)==p['trace']
                      and scene==ordered[len(collected)] and trace.option_in_force==starts[i].process_overrides.get(scene.base_option,scene.base_option),
                      'exact recorded raw/order/ordinary configuration required')
            state=K.State(*K.START,0,scene.kappa,scene.phase);z,m=trace.option_in_force,0
            for step in trace.steps:
                row=sd.reference.row(state,z,m)
                values={a:starts[i].q_overrides.get(QAddress(state,z,m,a),v) for a,v in row.items()}
                best=max(values.values())
                cmd=starts[i].decision_overrides.get(DecisionAddress(state,z,m),min(a for a,v in values.items() if v==best))
                A.require(step.a_cmd==cmd and cmd in row and step.u==starts[i].controller_overrides.get(K.ControllerSite(state,cmd),cmd),
                          'recorded current-channel read path differs')
                state=step.state;z,m=step.control.z,step.control.m
            collected.append((scene,trace))
    A.require(old_pre is not None and old_prep is not None and old_ref==sd.reference.digest()
              and seen_roles==list(H.ROLES) and len(old_b1)==2
              and all(tuple(s for s,t in bank)==ordered for bank in progress['rows']),
              'two complete ordered ordinary post banks required')
    rows=tuple(tuple(x) for x in progress['rows'])
    _actual_binding(prepared,pair,starts)
    payload={'old_raw_sha256':EXPECTED_RAW,'old_native_exit_preserved':None,'old_launcher_timeout_preserved':True,
             'new_actual_pair_sha256':pair_seal,'new_fullpre_sha256':seal(A.stores(sd.pre)),
             'reference_digest':sd.reference.digest(),'actual_fullposts':posts,'original_all_receipts':tuple(A.wire(x.ledger.receipts) for x in native.results),
             'owners':A.wire(d.owners),'region_sha256':seal(M.audit(d.region)),'dependencies':dependencies,
             'ordinary_configuration':{'mask':'empty','option_fault':None,'interventions':[],'reward_mode':'A'},
             'roles':H.ROLES,'complete_rows_each':len(ordered),'rows_sha256':seal(rows),
             'new_post_kernel_replays':0,'old_source_pair_role_identity_reconstructed':False,
             'proof':'Exact deterministic fullchannel/state/reference/kernel/tape/order inputs; stored records are not re-created native handles or scientific samples.'}
    handle=object.__new__(RecordedImmediateBanks)
    _RECORDED[handle]=_Data(prepared,pair,starts,rows,ordered,posts,payload,seal(payload))
    progress['stage']='COMPLETE'
    _checked(handle,prepared,pair,starts)
    return handle


def _checked(handle,prepared,pair,starts):
    A.require(type(handle) is RecordedImmediateBanks and handle in _RECORDED,'issued exact post-data transfer required')
    d=_RECORDED[handle]
    prepared_data,sd,native,pair_seal=_actual_binding(prepared,pair,starts)
    A.require(d.prepared is prepared and d.pair is pair and d.starts==starts
              and all(a is b for a,b in zip(d.starts,starts)) and d.ordered is M.units(prepared_data.region)
              and d.posts==tuple(A.stores(s) for s in starts) and seal(d.payload)==d.seal
              and pair_seal==d.payload['new_actual_pair_sha256'] and sd.reference.digest()==d.payload['reference_digest']
              and seal(d.rows)==d.payload['rows_sha256']
              and all(type(t) is RecordedTrace for bank in d.rows for s,t in bank),
              'post-data/source/pair/role/content binding changed')
    return d


def rows(handle,prepared,pair,starts):return _checked(handle,prepared,pair,starts).rows


def audit(handle,prepared,pair,starts):
    d=_checked(handle,prepared,pair,starts)
    return {'payload':d.payload,'payload_sha256':d.seal}


def partial(pair):
    A.require(pair in _ATTEMPTS and _ATTEMPTS[pair]['stage']!='COMPLETE','actual partial read required')
    d=_ATTEMPTS[pair]
    return {'stage':d['stage'],'ordered_rows':tuple(tuple(x) for x in d['rows']),
            'has_recorded_handle':False,'automatic_retry':False}
