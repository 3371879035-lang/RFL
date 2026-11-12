"""Genuine DQ whole-B1 -> exact RecordedOrdinary posts -> complete candidate.

Separate explicit result type; never forge v98 WholeMeasurement or old pair.
The sanitized pre-region and original separate orderedmeans are unchanged.
"""
from copy import deepcopy
from dataclasses import dataclass
from weakref import WeakKeyDictionary

import adaptive_training as A
import handoff as H
import instrument as M
import ruler as R
import post_transfer as P
from wire_boundary import seal
from rfl_rebuild.b1.tier import Tier


class RecordedDQWholeMeasurement:
    __slots__=('__weakref__',)
    def __new__(cls):raise A.ProtocolError('requires complete new-owned native pair and audited record transfer')


@dataclass(frozen=True)
class _Data:
    prepared: object
    pair: object
    starts: tuple
    transfer: object
    records: tuple
    shared_units: tuple
    payload: dict
    seal: str


_RESULTS=WeakKeyDictionary()
_PARTIAL=WeakKeyDictionary()


def run(prepared):
    d,source,sd=R._checked_prepared(prepared)
    A.require(d.architecture=='D_Q' and source.mode=='dq' and d.status=='READY','ready owned DQ required')
    cell=(Tier.L0_FACTUAL.name,'FactualReturnWrite')
    A.require(cell not in d.attempts,'complete/partial entry consumed; no retry')
    progress={'stage':'B1_started','pair':None,'starts':(),'transfer':None}
    d.attempts[cell]=progress
    _PARTIAL[prepared]=progress
    pair=H.run_whole_pair(d.bound,architecture='D_Q',tier=Tier.L0_FACTUAL,law_name='FactualReturnWrite')
    progress['pair']=pair
    _,_,native,declaration,pair_seal=H._checked_original_pair(d.bound,pair)
    A.require(native.projected==d.projected,'full owner/residual differs')
    starts=tuple(c.clone() for c in native.clones);progress['starts']=starts
    progress['stage']='recorded_post_transfer'
    transferred=P.load_for(prepared,pair,starts);progress['transfer']=transferred
    rows=P.rows(transferred,prepared,pair,starts)
    records=tuple(tuple(M.PreRecord(s,t) for s,t in bank) for bank in rows)
    shared=M.units(d.region)
    scores=tuple(M.loss(d.region,{r.scene:float(r.trace.return_value) for r in bank}) for bank in records)
    payload={'origin_sha256':d.seal,'original_pair_declaration':declaration,'original_pair_sha256':pair_seal,
             'full_immediate_posts':[A.stores(c) for c in native.clones],'region':M.audit(d.region),
             'scores':scores,'paired_difference':scores[0]['value']-scores[1]['value'],
             'complete_post_records':[len(x) for x in records],'new_post_kernel_rollouts':0,
             'post_records_sha256':seal(records),'recorded_post_provenance':P.audit(transferred,prepared,pair,starts),
             'scientific_qualification':False,'future_training':0}
    handle=object.__new__(RecordedDQWholeMeasurement)
    _RESULTS[handle]=_Data(prepared,pair,starts,transferred,records,shared,deepcopy(payload),seal(payload))
    _checked(handle)
    progress['stage']='COMPLETE'
    return handle


def _checked(handle):
    A.require(type(handle) is RecordedDQWholeMeasurement and handle in _RESULTS,'issued complete DQ record-derived measure required')
    md=_RESULTS[handle];d,_,_=R._checked_prepared(md.prepared)
    _,_,native,declaration,pair_seal=H._checked_original_pair(d.bound,md.pair)
    rows=P.rows(md.transfer,md.prepared,md.pair,md.starts)
    A.require(md.shared_units is M.units(d.region) and len(md.records)==2
              and all(tuple((r.scene,r.trace) for r in bank)==row for bank,row in zip(md.records,rows))
              and all(tuple(r.scene for r in bank)==md.shared_units for bank in md.records)
              and seal(md.payload)==md.seal and seal(md.records)==md.payload['post_records_sha256']
              and md.payload['original_pair_declaration']==declaration and md.payload['original_pair_sha256']==pair_seal
              and md.payload['recorded_post_provenance']==P.audit(md.transfer,md.prepared,md.pair,md.starts)
              and md.payload['full_immediate_posts']==[A.stores(c) for c in native.clones],
              'complete measure/source/pair/data lineage changed')
    return md


def audit(handle):
    d=_checked(handle)
    return deepcopy({'payload':d.payload,'payload_sha256':d.seal,'ordered_post_records':d.records})


def partial_audit(prepared):
    d,_,_=R._checked_prepared(prepared)
    A.require(prepared in _PARTIAL and _PARTIAL[prepared]['stage']!='COMPLETE','actual partial measure entry required')
    p=_PARTIAL[prepared]
    return deepcopy({'stage':p['stage'],'full_starts':[A.stores(s) for s in p['starts']],
                     'recorded_partial':P.partial(p['pair']) if p['pair'] is not None else None,
                     'has_measurement_handle':False,'automatic_retry':False})
