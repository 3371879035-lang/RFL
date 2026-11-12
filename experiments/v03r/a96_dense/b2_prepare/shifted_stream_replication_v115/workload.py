"""Human-requested fresh known-mechanism shifted-stream replication.

The unchanged four-context mechanism is not a new defect family. A fixed offset
of seven changes the predeclared ordinary training order for an early H64 view;
it is not chosen from the new result and no benefit or lead is required.
Each genuine pair supplies its own fresh immediate wholeCollateral and future.
All reused modules remain byte-unchanged; no prior bank or ownership is replayed.
"""
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path[:0] = [str(HERE.parent/'owned_adaptive_handoff_v92'), str(HERE.parent/'adaptive_training_v90'),
               str(HERE.parent), str(HERE.parent/'patch_dense_completion_v108'), str(ROOT/'src')]
import adaptive_training as A
import handoff as H
import oracle_mainline_v75 as O
import resource_meter as RM
from rfl_rebuild.b2 import training as T
from rfl_rebuild.b2.unaffected import EvaluationScene
from rfl_rebuild.b1.tier import Tier
from rfl_rebuild.env import kernel as K
from rfl_rebuild.learner.reference import QReferenceView
from rfl_rebuild.learner.store import LearnerPersistentState, QAddress, DecisionAddress, Edit, Q, DECISION, PROCESS, CONTROLLER

CONTRACT = json.loads((HERE/'contract.json').read_bytes())
T_MAX = CONTRACT['t_max']
N_EVAL = CONTRACT['n_eval']
STREAM_OFFSET = CONTRACT['stream_offset']
GRID = tuple(range(T_MAX + 1))
CHECKPOINT_BANKS = 2 * (T_MAX + 1)
TRAINING_EPISODES = 2 * T_MAX
FUTURE_ROLLOUTS = TRAINING_EPISODES + CHECKPOINT_BANKS * N_EVAL
MODE = sys.argv[1]
assert MODE in ('dq','patch-adaptive') and MODE in CONTRACT['modes']
OUT = HERE/'evidence'/MODE
COUNTS = Counter()
START = time.monotonic()
SCOPE = {'stage':'source', 'role':None, 'epoch':None}
BANK = None
COLLATERAL_BANK = None
R = M = None
BANK_OBJECTS, BANK_DIGESTS = {}, {}
PENDING = []
PEAK = {'working_set_bytes':0, 'peak_working_set_bytes':0, 'private_bytes':0, 'peak_commit_bytes':0,
        'minimum_available_physical_bytes': 1 << 64}


def canonical(obj):
    return json.dumps(obj,sort_keys=True,separators=(',', ':'),ensure_ascii=True)


class Capture:
    def __init__(self, path):
        self.file = path.open('xb')
        self.z = gzip.GzipFile(filename='',fileobj=self.file,mode='wb',compresslevel=1,mtime=0)
        self.records = self.raw_bytes = 0
        self.encode_seconds = self.write_seconds = 0.0
        self.canonical_sha = hashlib.sha256()

    def emit(self, tag, data, *, force=False):
        t = time.monotonic()
        payload = A.wire(data)
        record = dict(seq=self.records,mode=MODE,tag=tag,payload=payload,**SCOPE)
        line = (canonical(record)+'\n').encode('ascii')
        self.encode_seconds += time.monotonic()-t
        t = time.monotonic()
        self.z.write(line)
        self.write_seconds += time.monotonic()-t
        self.canonical_sha.update(line)
        self.raw_bytes += len(line); self.records += 1
        if not force and (self.raw_bytes > CONTRACT['budget']['uncompressed_bytes_per_child'] or
                          self.file.tell() > CONTRACT['budget']['compressed_bytes_per_child']):
            raise RuntimeError('prospective capture extent budget exhausted')
        return payload

    def close(self):
        self.z.close(); self.file.close()


LOG = None


def resource(label, *, check=True):
    now = RM.sample()
    for name in ('working_set_bytes','peak_working_set_bytes','private_bytes','peak_commit_bytes'):
        PEAK[name] = max(PEAK[name], now[name])
    PEAK['minimum_available_physical_bytes'] = min(PEAK['minimum_available_physical_bytes'], now['available_physical_bytes'])
    now.update(label=label, wall_seconds=time.monotonic()-START, raw_bytes=LOG.raw_bytes,
               compressed_bytes=LOG.file.tell(), counts=dict(COUNTS))
    LOG.emit('RESOURCE', now, force=not check)
    if check:
        assert now['working_set_bytes'] <= CONTRACT['budget']['working_set_bytes_per_child'], 'working-set cap'
        assert now['peak_working_set_bytes'] <= CONTRACT['budget']['working_set_bytes_per_child'], 'peak working-set cap'
        assert now['private_bytes'] <= CONTRACT['budget']['private_bytes_per_child'], 'private-commit cap'
        assert now['peak_commit_bytes'] <= CONTRACT['budget']['private_bytes_per_child'], 'peak private-commit cap'
        assert now['available_physical_bytes'] >= CONTRACT['budget']['minimum_available_physical_bytes'], 'host RAM reserve'
        assert now['wall_seconds'] <= CONTRACT['budget']['seconds_per_child'], 'wall-time cap'
    return now


def transaction_kind(edits):
    channels={edit.store for edit in edits}
    if SCOPE['stage']=='source_install':
        return 'source_install'
    if SCOPE['stage']=='B1':
        return 'B1_feedback'
    if SCOPE['stage']=='training' and (not channels or channels=={Q}):
        return 'numeric_TD'
    if SCOPE['stage']=='training' and channels=={DECISION}:
        return 'visited_existing_D_policy'
    return 'unexpected_transaction_phase_or_channels'


def handler(frame,event,arg):
    global SCOPE, BANK, PENDING, COLLATERAL_BANK
    p,n = frame.f_code.co_filename.replace('\\','/'),frame.f_code.co_name
    kernel = p.endswith('rfl_rebuild/env/kernel.py')
    store = p.endswith('rfl_rebuild/learner/store.py')
    native = p.endswith('rfl_rebuild/b1/runner.py') and n in ('run_patch_law','run_dq_law')
    learn = p.endswith('complete_curve_source_gates_v105/variants/normal/learning.py')
    curve = p.endswith('patch_dense_completion_v108/owned_curve.py')
    ruler = p.endswith('owned_whole_completion_v98/ruler.py')
    if event == 'call':
        counter = n if kernel and n in ('step','rollout') else 'transaction' if store and n=='apply_transaction' else 'B1' if native else None
        if counter:
            COUNTS[counter] += 1
            assert COUNTS[counter] <= CONTRACT['budget'][counter+'_per_child'], 'native budget '+counter
        if (p.endswith('owned_whole_completion_v98/transfer.py') and n in ('load_for','rows')) or (p.endswith('owned_whole_completion_v98/recorded.py') and n=='decode') or (p.endswith('rfl_rebuild/b2/training.py') and n in ('derive','key','mix','train_curve','pre_level')) or (kernel and n=='sample') or (p.endswith('rfl_rebuild/solve/dp.py') and n=='solve_reference') or (p.endswith('random.py') and n in ('__init__','random','randrange')) or frame.f_code.co_qualname in ('FutureTrainingProtocol.__init__','Curve.__init__'):
            COUNTS['forbidden'] += 1
            raise RuntimeError('ungranted formal/key/RNG/DP path: '+n)
        if ruler and n=='_ordinary_bank':
            stage=frame.f_locals['stage']
            SCOPE={'stage':'collateral_pre' if stage=='pre' else 'collateral_post',
                   'role':None if stage=='pre' else stage,'epoch':None}
            state=frame.f_locals['state']
            COLLATERAL_BANK={'state':state,'before':A.stores(state),'traces':[],
                             'hash':hashlib.sha256(),'units':frame.f_locals['ordered_units']}
            LOG.emit('COLLATERAL_BANK_BEGIN',{'stage_label':stage,'full_state':COLLATERAL_BANK['before'],
                     'reference_digest':frame.f_locals['reference'].digest(),
                     'ordered_scene_keys':[list(unit.key) for unit in COLLATERAL_BANK['units']]})
        elif curve and n=='_evaluate_bank':
            actor=frame.f_locals['actor']
            SCOPE={'stage':'evaluation','role':actor.role,'epoch':actor._completed}
            BANK={'hash':hashlib.sha256(),'traces':[]}
            LOG.emit('BANK_BEGIN', {'before':actor.payload(),'sample':[list(s.key) for s in frame.f_locals['sample']]})
        elif learn and n=='train_episode':
            actor=frame.f_locals['self']; episode=frame.f_locals['episode']
            SCOPE={'stage':'training','role':actor.role,'epoch':episode.epoch}
            LOG.emit('TRAIN_BEGIN',{'before':actor.payload(),'declared_episode':episode._input})
        elif store and n=='apply_transaction':
            kind=transaction_kind(frame.f_locals['edits'])
            COUNTS[kind+'_transaction'] += 1
            LOG.emit('TX_CALL',{'before':A.stores(frame.f_locals['self']),'edits':frame.f_locals['edits'],
                               'transaction_kind':kind})
    elif event=='return':
        if kernel and n=='step' and type(arg) is K.StepResult:
            COUNTS['step_return'] += 1
            PENDING.append(arg)
        elif kernel and n=='rollout':
            if type(arg) is K.RolloutTrace:
                linked=len(PENDING)==len(arg.steps) and all(x is y for x,y in zip(PENDING,arg.steps))
                COUNTS['rollout_return'] += 1
                if SCOPE['stage']=='source':
                    COUNTS['source_factual_returned'] += 1
                record=LOG.emit('RAW_ROLLOUT', {'trace':arg,'kappa':frame.f_locals['kappa'],'tape':frame.f_locals['tape'],
                                               'return_hex':arg.return_value.hex(),
                                               'actual_step_object_links':linked,'returned_steps':len(PENDING)})
                assert linked, 'actual step/rollout identity'
                if COLLATERAL_BANK is not None and SCOPE['stage'] in ('collateral_pre','collateral_post'):
                    COLLATERAL_BANK['hash'].update((canonical(record['trace'])+'\n').encode('ascii'))
                    COLLATERAL_BANK['traces'].append(arg)
                if BANK is not None and SCOPE['stage']=='evaluation':
                    BANK['hash'].update((canonical(record['trace'])+'\n').encode('ascii'))
                    BANK['traces'].append(arg)
                PENDING=[]
            else:
                LOG.emit('INCOMPLETE_ROLLOUT',{'returned':arg,'actual_completed_steps':PENDING},force=True)
                PENDING=[]
        elif store and n=='apply_transaction':
            LOG.emit('TX_RETURN',{'after':A.stores(frame.f_locals['self']),
                                 'transaction_kind':transaction_kind(frame.f_locals['edits'])})
        elif native and type(arg) is O.base.native_b1.B1Result:
            LOG.emit('NATIVE_B1_RETURN',{'law':frame.f_locals['law'].name,'full_post':A.stores(arg.post_state),
                                       'ledger_canonical':arg.ledger.canonical(),'receipts':arg.ledger.receipts})
        elif ruler and n=='_ordinary_bank':
            records=frame.f_locals['collected']
            linked=len(records)==len(COLLATERAL_BANK['traces']) and all(
                type(record) is M.PreRecord and type(record.trace) is K.RolloutTrace and record.trace is trace
                for record,trace in zip(records,COLLATERAL_BANK['traces']))
            complete=len(records)==len(COLLATERAL_BANK['units'])
            after=A.stores(COLLATERAL_BANK['state'])
            LOG.emit('COLLATERAL_BANK_END',{'stage_label':frame.f_locals['stage'],
                     'count':len(records),'declared_count':len(COLLATERAL_BANK['units']),
                     'raw_sha256':COLLATERAL_BANK['hash'].hexdigest(),'full_after':after,
                     'actual_native_record_object_links':linked,'complete_extent':complete,
                     'read_only_full_state_equal':after==COLLATERAL_BANK['before']})
            assert linked,'actual collateral record/rollout identity'
            COLLATERAL_BANK=None
            resource('collateral_bank_boundary')
        elif curve and n=='_evaluate_bank' and type(arg) is tuple:
            actor=frame.f_locals['actor']
            assert len(BANK['traces'])==len(arg[0]) and all(x is y for x,y in zip(BANK['traces'],arg[0]))
            key=(actor.role,actor._completed)
            assert key not in BANK_OBJECTS
            BANK_OBJECTS[key]=arg[0]; BANK_DIGESTS[key]=BANK['hash'].hexdigest()
            LOG.emit('BANK_END',{'count':len(arg[0]),'mean_hex':arg[1].hex(),'ordered_raw_sha256':BANK_DIGESTS[key],
                                'after':actor.payload()})
            BANK=None
            now=resource('checkpoint')
            if actor._completed % 50==0 or actor._completed==T_MAX:
                print(canonical({'tag':'PROGRESS','mode':MODE,'role':actor.role,'checkpoint':actor._completed,
                                 'mean_hex':arg[1].hex(),'resource':now}),flush=True)
        elif learn and n=='train_episode' and isinstance(arg,dict):
            LOG.emit('CORE_EPISODE',arg)


def interesting(code):
    p,n,q=code.co_filename.replace('\\','/'),code.co_name,code.co_qualname
    return ((p.endswith('rfl_rebuild/env/kernel.py') and n in ('step','rollout','sample')) or
            (p.endswith('rfl_rebuild/learner/store.py') and n=='apply_transaction') or
            (p.endswith('rfl_rebuild/b1/runner.py') and n in ('run_patch_law','run_dq_law')) or
            (p.endswith('rfl_rebuild/b2/training.py') and n in ('derive','key','mix','train_curve','pre_level')) or
            (p.endswith('rfl_rebuild/solve/dp.py') and n=='solve_reference') or
            (p.endswith('random.py') and n in ('__init__','random','randrange')) or
            q in ('FutureTrainingProtocol.__init__','Curve.__init__') or
            (p.endswith('complete_curve_source_gates_v105/variants/normal/learning.py') and n=='train_episode') or
            (p.endswith('patch_dense_completion_v108/owned_curve.py') and n=='_evaluate_bank') or
            (p.endswith('owned_whole_completion_v98/ruler.py') and n=='_ordinary_bank') or
            (p.endswith('owned_whole_completion_v98/transfer.py') and n in ('load_for','rows')) or
            (p.endswith('owned_whole_completion_v98/recorded.py') and n=='decode'))


DISPATCH={}


def observe(frame,event,arg):
    key=id(frame.f_code)
    item=DISPATCH.get(key)
    if item is None:
        item=(frame.f_code,interesting(frame.f_code)); DISPATCH[key]=item
    if item[1]: handler(frame,event,arg)


def load_modules():
    global R,M
    folder=HERE.parent/'owned_whole_completion_v98'
    for fullname,file in (('wire_boundary',HERE.parent/'whole_collateral_wire_revision_v97'/'wire_boundary.py'),
                          ('recorded',folder/'recorded.py'),('instrument',folder/'instrument.py'),
                          ('transfer',folder/'transfer.py'),('v98_ruler',folder/'ruler.py')):
        spec=importlib.util.spec_from_file_location(fullname,file)
        mod=importlib.util.module_from_spec(spec); sys.modules[fullname]=mod; spec.loader.exec_module(mod)
        if fullname=='instrument': M=mod
        if fullname=='v98_ruler': R=mod
    modules=[]
    folder=HERE.parent/'complete_curve_source_gates_v105/variants/normal'
    for fullname,file in (('v105_normal_td',folder/'td.py'),
                          ('v105_normal_learning',folder/'learning.py'),
                          ('v107_bank',HERE.parent/'readonly_bank_optimization_v107'/'bank.py'),
                          ('v108_curve',HERE.parent/'patch_dense_completion_v108'/'owned_curve.py'),
                          ('v108_external',HERE.parent/'patch_dense_completion_v108'/'external.py')):
        spec=importlib.util.spec_from_file_location(fullname,file)
        mod=importlib.util.module_from_spec(spec); sys.modules[fullname]=mod; spec.loader.exec_module(mod)
        if fullname!='v107_bank': modules.append(mod)
    return modules

def read_reference():
    spec=CONTRACT['reference_input']; raw=(ROOT/spec['path']).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==spec['sha256']
    rows={}
    for line in raw.decode('utf-8').splitlines():
        if line.startswith('DECISION_CONTEXT='):
            d=json.loads(line.split('=',1)[1]); x,y,t,k,phi,z,m=d['context']
            rows[K.State(x,y,t,k,phi),z,m]={a:float.fromhex(v) for a,v in d['q_row_hex']}
    reference=QReferenceView(rows,name='v115-fixed-original-reference')
    assert reference.digest()==spec['q_digest']
    LOG.emit('REFERENCE',{'digest':reference.digest(),'rows':len(reference)})
    return reference


def make_source(reference):
    global SCOPE
    scene=EvaluationScene(*CONTRACT['source_scene'])
    contexts=tuple(DecisionAddress(K.State(1,2,1,k,2),z,0) for k in (0,1) for z in (1,3))
    rows=[]
    edits=[]
    for address in contexts:
        row=reference.row(address.state,address.z,address.m)
        rows.append({'address':address,'q_row_hex':[[a,v.hex()] for a,v in row.items()],
                     'promoted_RIGHT_hex':(max(row.values())+1.0).hex()})
        assert K.RIGHT in row and row[K.RIGHT].hex()==(-1.02).hex()
        edits.append(Edit(Q,QAddress(address.state,address.z,address.m,K.RIGHT),max(row.values())+1.0)
                     if MODE=='dq' else Edit(DECISION,address,K.RIGHT))
    pre=LearnerPersistentState()
    LOG.emit('SOURCE_INSTALL_PLANNED',{'mode':MODE,'regime':'P','scene':list(scene.key),
              'contexts':contexts,'reference_rows':rows,'edits':tuple(edits),'P_X_empty':True,
              'installed_contexts':4,'source_install_transactions':1,
              'motivation':'Human-requested fresh replication of the known four-context mechanism with fixed shifted training order; not a new defect family, blind scientific population or benefit screen'})
    SCOPE={'stage':'source_install','role':None,'epoch':None}
    pre.apply_transaction(tuple(edits),q_reference=reference)
    SCOPE={'stage':'source','role':None,'epoch':None}
    healthy_spec=CONTRACT['healthy_reference']
    healthy_raw=(ROOT/healthy_spec['path']).read_bytes()
    assert hashlib.sha256(healthy_raw).hexdigest()==healthy_spec['sha256']
    healthy=json.loads(healthy_raw)
    source=O.capture_source(pre,scene=scene,regime='P',q_reference=reference,healthy_reference=healthy,
                            mask=K.FaultMask(),option_fault=None,counterfactual=False)
    COUNTS['source_capture_complete'] += 1
    LOG.emit('ORIGINAL_SOURCE',{'mode':MODE,'audit':O.source_audit(source)})
    _configuration,sd=O._checked_source(source)
    owner=DecisionAddress(K.State(1,2,1,0,2),1,0)
    suffix=0.0
    for step in reversed(sd.trace.steps[1:]):
        suffix=step.reward+suffix
    LOG.emit('SOURCE_TRUTH_ACTUAL',{'regime':sd.regime,'truth':sd.truth,'full_pre':A.stores(sd.pre),
              'outcome':sd.trace.outcome,'return_hex':sd.trace.return_value.hex(),
              'actual_mask':sd.trace.mask,'base_option':sd.trace.base_option,
              'option_in_force':sd.trace.option_in_force,'factual_owner':owner,
              'installed_contexts':contexts,'B1_nonowners':[a for a in contexts if a!=owner],
              'factual_suffix_return_hex':suffix.hex(),
              'Q_reference_factual_action_hex':reference.value(QAddress(owner.state,1,0,K.RIGHT)).hex()})
    assert sd.regime=='P' and A.stores(sd.pre)==A.stores(pre) and not sd.pre.snapshot().healthy
    assert not sd.pre.process_overrides and not sd.pre.controller_overrides
    assert sd.trace.mask==K.FaultMask() and sd.trace.base_option==sd.trace.option_in_force==1
    assert sd.trace.outcome==K.Outcome.COLLISION and sd.trace.return_value.hex()==(-1.04).hex()
    assert len(sd.trace.steps)==2
    first,second=sd.trace.steps
    assert (first.a_cmd,first.u,first.a_realized)==(K.RIGHT,K.RIGHT,K.RIGHT)
    assert first.state==owner.state and first.control==K.ControlState(z=1,m=0)
    assert first.reward.hex()==(-0.02).hex() and not first.terminal and first.outcome is None
    assert (second.a_cmd,second.u,second.a_realized)==(K.RIGHT,K.RIGHT,K.RIGHT)
    assert second.state==K.State(2,2,2,0,2) and second.control==K.ControlState(z=1,m=0)
    assert second.reward.hex()==(-1.02).hex() and second.terminal and second.outcome==K.Outcome.COLLISION
    assert suffix.hex()==reference.value(QAddress(owner.state,1,0,K.RIGHT)).hex()
    assert sd.truth['Gamma_P_star']==['Decision_1'] and sd.truth['Gamma_T_star'] is None and sd.truth['R_mech'] is None
    bound=H.bind_source(source,mode=MODE)
    LOG.emit('BOUND_BEFORE_ARMS',H.source_audit(bound))
    return source,bound


def confirm_source_pair(source,bound,pair,measurement,prepared):
    _source,sd,native,declaration,pair_seal=H._checked_original_pair(bound,pair)
    owner=DecisionAddress(K.State(1,2,1,0,2),1,0)
    contexts=tuple(DecisionAddress(K.State(1,2,1,k,2),z,0) for k in (0,1) for z in (1,3))
    md=R._checked_result(measurement)
    LOG.emit('SOURCE_PAIR_ACTUAL',{'mode_before_arms':_source.mode,'pair_seal':pair_seal,
              'whole_units':list(native.projected.whole_units),'cell_units':list(native.projected.cell_units),
              'owner_addresses':native.projected.addresses,'residual_units':list(native.projected.residual_units),
              'full_immediate_posts':[A.stores(result.post_state) for result in native.results],
              'ordered_receipts':[result.ledger.receipts for result in native.results],
              'actual_same_pair_as_whole_measurement':md.pair is pair,
              'actual_preparation_bound':R._PREPARED[prepared].bound is bound,
              'status_note':'All observed APPLIED/NOOP/zero/signed results retained, not selection gates'})
    assert md.pair is pair and native.projected.whole_units==native.projected.cell_units==('Decision_1',)
    assert native.projected.addresses==(owner,) and native.projected.residual_units==()
    assert len(native.results)==len(native.clones)==2
    protected=A.stores(sd.pre)
    nonowners=tuple(address for address in contexts if address!=owner)
    for i,result in enumerate(native.results):
        receipts=tuple(result.ledger.receipts)
        assert len(receipts)==1 and receipts[0].address==owner
        assert receipts[0].status in ('APPLIED','EVALUABLE_NOOP')
        post=A.stores(result.post_state)
        assert post['P']==protected['P'] and post['X']==protected['X']
        assert post==md.payload['full_immediate_posts'][i]
        if MODE=='dq':
            assert post['D']==protected['D']
            assert all(result.post_state.q_overrides.get(QAddress(a.state,a.z,a.m,K.RIGHT))==
                       sd.pre.q_overrides.get(QAddress(a.state,a.z,a.m,K.RIGHT)) for a in nonowners)
            assert all(DecisionAddress(q.state,q.z,q.m) in contexts and q.a==K.RIGHT
                       for q in result.post_state.q_overrides)
        else:
            assert post['Q']==protected['Q']
            assert all(result.post_state.decision_overrides.get(a)==sd.pre.decision_overrides.get(a)
                       for a in nonowners)
            assert all(address in contexts for address in result.post_state.decision_overrides)
        if i==0:
            assert post==protected
    return md

def make_episodes(L):
    result=[]
    for e in range(T_MAX):
        r=e+STREAM_OFFSET
        k=r%2; proposal=(r//2)%4; phase=(r//8)%6; flag=(r//48)%2; rank=(r//96)%60
        coins=tuple(0 if (r+i)%10==0 else T.M64 for i in range(12))
        draws=tuple((T.M64,r*12+i) for i in range(12))
        result.append(L.EngineeringEpisode(e,k,proposal,K.SemanticTape(phase,flag,rank),coins,draws))
    return tuple(result)


def confirm_handles(C,E,bundle,handles):
    global SCOPE
    summaries=[]
    for role,handle in zip(('reference','treatment'),handles):
        SCOPE={'stage':'export','role':role,'epoch':T_MAX}
        checkpoints,pre,tmax=C._external_material(handle)
        own_bundle,own_role,stored,training=C._ROLE_CURVES[handle]
        assert own_bundle is bundle and own_role==role and checkpoints is stored
        assert tmax==T_MAX and len(checkpoints)==T_MAX+1 and len(training)==T_MAX
        for epoch,traces,mean in checkpoints:
            assert traces is BANK_OBJECTS[(role,epoch)] and len(traces)==N_EVAL
            LOG.emit('HANDLE_CHECKPOINT',{'epoch':epoch,'count':N_EVAL,'mean_hex':mean.hex(),
                    'ordered_raw_sha256':BANK_DIGESTS[(role,epoch)]})
        assert all(r['epoch']==i for i,r in enumerate(training))
        actor=C._BUNDLES[bundle].actors[('reference','treatment').index(role)]
        LOG.emit('FINAL_COMPOSITE',actor.payload())
        # The actual closed constructor is part of the measured complete path.
        resource('before_external_constructor')
        view=E.build(handle); projected=E.read(view)
        LOG.emit('EXTERNAL_VIEW',dict(projected,fields=dict(projected['fields'])))
        resource('after_external_constructor')
        values=[{'epoch':e,'mean_hex':m.hex()} for e,_traces,m in checkpoints]
        summaries.append({'role':role,'ordered_curve':values,'pre_level_hex':pre.hex(),'t_max':tmax,
                          'full_composite_sha256':A.digest(actor.payload()),
                          'numeric_entry_count':len(actor._current.q_overrides) if MODE=='dq' else len(actor._values.q_overrides),
                          'decision_entry_count':len(actor._current.decision_overrides)})
        del projected,view
    C._checked(bundle)
    return summaries


def main():
    global LOG,SCOPE
    LOG=Capture(OUT/'raw.jsonl.gz')
    source=bound=pair=bundle=prepared=measurement=None
    succeeded=False
    old_profile=sys.getprofile()
    originals=(K.step,K.rollout,H.bind_source,H.run_whole_pair,O.capture_source,O.run_pair,
               LearnerPersistentState.apply_transaction,O.base.native_b1.run_dq_law,O.base.native_b1.run_patch_law)
    normal_train=None
    restoration=None
    try:
        sys.setprofile(observe)
        LOG.emit('RUN_BEGIN',{'mode':MODE,'started_at_utc':datetime.now(timezone.utc).isoformat(),
                             'contract_sha256':hashlib.sha256((HERE/'contract.json').read_bytes()).hexdigest()})
        resource('startup')
        _td,L,C,E=load_modules()
        normal_train=L.CoordinateLearner.train_episode
        reference=read_reference(); source,bound=make_source(reference)
        architecture='D_Q' if MODE=='dq' else 'D_patch'
        law_name='FactualReturnWrite' if MODE=='dq' else 'DeleteFactualPatch'
        prepared=R.prepare(bound,architecture=architecture,recorded_census=None)
        pd,_,_=R._checked_prepared(prepared)
        LOG.emit('WHOLE_PREPARED',{'origin':pd.origin,'origin_sha256':pd.seal,'owners':pd.owners,
                 'status':pd.status,'region':M.audit(pd.region) if pd.region is not None else None,
                 'complete_pre_records':len(pd.records),'fresh_kernel_pre_only':True,
                 'all_pre_traces_actual_native':all(type(record.trace) is K.RolloutTrace for record in pd.records)})
        resource('whole_prepared')
        SCOPE={'stage':'B1','role':None,'epoch':None}
        measurement=R.run_cell(prepared,tier=Tier.L0_FACTUAL,law_name=law_name)
        md=R._checked_result(measurement)
        pair=md.pair
        SCOPE={'stage':'source','role':None,'epoch':None}
        LOG.emit('ORIGINAL_PAIR',O.pair_audit(pair,source))
        LOG.emit('WHOLE_MEASUREMENT_COMPLETED',{'payload':md.payload,'payload_sha256':md.seal,
                 'prepared_origin_sha256':pd.seal,'ordered_post_records_count':[len(records) for records in md.records],
                 'shared_region_keys':[list(unit.key) for unit in md.shared_units],
                 'actual_same_pair_for_future':md.pair is pair,
                 'all_post_traces_actual_native':all(type(record.trace) is K.RolloutTrace
                                                    for records in md.records for record in records)})
        confirm_source_pair(source,bound,pair,measurement,prepared)
        resource('whole_immediate_complete')
        stream=make_episodes(L)
        bundle=C.prepare_curve(bound,pair,episodes=stream,evaluation_indices=tuple(range(N_EVAL)))
        d=C._checked(bundle)
        assert d.pair is md.pair and all(actor._initial==md.payload['full_immediate_posts'][i]
                                        for i,actor in enumerate(d.actors))
        assert d.plan.grid==GRID and len(d.plan.evaluation_sample)==N_EVAL and d.plan.t_max==T_MAX
        LOG.emit('CURVE_PREPARED',{'origin':d.origin,'origin_sha256':d.seal,
                                 'initial_composites':[a.payload() for a in d.actors],
                                 'engineering_t_max':T_MAX,'engineering_grid':GRID,
                                 'evaluation_scenes':N_EVAL,'stream_offset':STREAM_OFFSET})
        resource('prepared')
        handles=C.run_pair_curve(bundle)
        assert len(handles)==2
        summaries=confirm_handles(C,E,bundle,handles)
        LOG.emit('ORIGINAL_PAIR_AFTER',O.pair_audit(pair,source))
        region_count=len(md.shared_units)
        assert COUNTS['rollout']==COUNTS['rollout_return']==1+FUTURE_ROLLOUTS+5760+2*region_count
        assert COUNTS['source_install_transaction']==1 and COUNTS['source_factual_returned']==1
        assert COUNTS['step']==COUNTS['step_return'] and COUNTS['B1']==2 and not COUNTS['forbidden']
        assert not COUNTS['unexpected_transaction_phase_or_channels_transaction']
        assert len(BANK_OBJECTS)==CHECKPOINT_BANKS
        loaded={}
        for mod in tuple(sys.modules.values()):
            filename=getattr(mod,'__file__',None)
            if filename:
                p=Path(filename).resolve()
                if p.is_relative_to(ROOT) and p.suffix=='.py':
                    loaded[p.relative_to(ROOT).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
        pins=json.loads((HERE/'evidence/claim.json').read_bytes())['input_binding_before']
        assert all(n in pins and pins[n]['sha256']==h for n,h in loaded.items())
        LOG.emit('ACTUAL_LOADED_SOURCE_INVENTORY',loaded)
        final_resource=resource('complete')
        LOG.emit('RESULT',{'completed':True,'counts':dict(COUNTS),'roles':summaries,
                          'resources':final_resource,'peaks':PEAK,'checkpoint_banks':CHECKPOINT_BANKS,
                          'training_episodes':TRAINING_EPISODES,'raw_records_before_result':LOG.records,
                          'capture_encode_seconds':LOG.encode_seconds,'capture_write_seconds':LOG.write_seconds,
                          'source_mode_bound_before_arms':True,'formal_keyed_stream':False,
                          'scientific_qualification':False,'collection_authorized':False,
                          'same_pair_immediate_and_future':True,'whole_measurement_sha256':md.seal,
                          'region_count':region_count,'whole_scores':md.payload['scores'],
                          'whole_paired_difference':md.payload['paired_difference'],
                          'engineering_canary_result_informed':True,
                          'known_mechanism_shifted_stream_replication':True,
                          'engineering_t_max':T_MAX,'stream_offset':STREAM_OFFSET,
                          'early_optimization_horizon_only':True})
        succeeded=True
    except BaseException as exc:
        if PENDING: LOG.emit('PENDING_RETURNED_STEPS',PENDING,force=True)
        failed={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc(),
                'counts':dict(COUNTS),'complete_handle_issued':False,'peaks':PEAK,
                'bank_partial_count':0 if BANK is None else len(BANK['traces']),
                'collateral_bank_partial_count':0 if COLLATERAL_BANK is None else len(COLLATERAL_BANK['traces']),
                'whole_measurement_handle_issued':measurement is not None and measurement in R._MEASURED}
        if bundle is not None:
            d=C._BUNDLES[bundle]
            failed['curve_attempted']=C._ATTEMPTED[bundle]
            failed['complete_handle_issued']=bundle in C._COMPLETED
            failed['actors']=[{'role':a.role,'completed':a._completed,'attempted':sorted(a._attempted),
                              'immediate':A.stores(a._immediate),'current':A.stores(a._current),
                              'L':None if a._values is None else A.stores(a._values)} for a in d.actors]
        if prepared is not None:
            p=R._PREPARED[prepared]
            partial=p.attempts.get((Tier.L0_FACTUAL.name,'FactualReturnWrite' if MODE=='dq' else 'DeleteFactualPatch'))
            failed['whole_preparation_status']=p.status
            failed['whole_pre_records']=len(p.records)
            if partial is not None:
                failed['whole_partial_stage']=partial['stage']
                failed['whole_partial_record_counts']=[len(records) for records in partial['records']]
                failed['whole_partial_pair_issued']=partial['pair'] is not None
                failed['whole_partial_full_starts']=[A.stores(state) for state in partial['starts']]
        LOG.emit('FAILURE',failed,force=True)
        print(canonical({'tag':'FAILURE','mode':MODE,'error':failed,'resource':RM.sample()}),flush=True)
        traceback.print_exc()
    finally:
        profile_was_installed=sys.getprofile() is observe
        functions_unchanged=originals==(K.step,K.rollout,H.bind_source,H.run_whole_pair,O.capture_source,O.run_pair,
                   LearnerPersistentState.apply_transaction,O.base.native_b1.run_dq_law,O.base.native_b1.run_patch_law)
        normal_unchanged=normal_train is None or normal_train is L.CoordinateLearner.train_episode
        sys.setprofile(old_profile)
        restoration={'profile_was_installed':profile_was_installed,'profile_restored':sys.getprofile() is old_profile,
                     'original_function_identities_unchanged':functions_unchanged and normal_unchanged}
        LOG.emit('CAPTURE_RESTORATION',restoration,force=True)
        succeeded=succeeded and all(restoration.values())
        LOG.close()
        summary={'completed':succeeded,'mode':MODE,'counts':dict(COUNTS),'records':LOG.records,
                 'uncompressed_bytes':LOG.raw_bytes,'canonical_sha256':LOG.canonical_sha.hexdigest(),
                 'compressed_bytes':(OUT/'raw.jsonl.gz').stat().st_size,
                 'wall_seconds':time.monotonic()-START,'cpu_seconds':time.process_time(),
                 'encode_seconds':LOG.encode_seconds,'write_seconds':LOG.write_seconds,'peaks':PEAK,
                 'capture_restoration':restoration,'extra_original_sources':COUNTS['source_factual_returned'],
                 'issued_original_sources':COUNTS['source_capture_complete'],
                 'source_transactions':COUNTS['source_install_transaction'],'source_regime':'P','whole_owner_count':1,
                 'original_feedback_may_be_evaluable_noop':True,
                 'whole_measurement_handle_issued':measurement is not None and measurement in R._MEASURED}
        with (OUT/'child_summary.json').open('x',encoding='utf-8',newline='\n') as stream:
            stream.write(canonical(summary)+'\n')
        print(canonical({'tag':'CHILD_EXIT_SUMMARY',**summary}),flush=True)
    return 0 if succeeded else 1


if __name__=='__main__':
    raise SystemExit(main())
