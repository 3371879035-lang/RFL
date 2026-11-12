"""V101 authentic DQ whole endpoint with exact recorded pre/post data.
No old fixture execution and no repeat native ordinary bank.
"""
import ast
from collections import Counter
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path[:0] = [str(HERE), str(HERE.parent/'owned_whole_completion_v98'), str(HERE.parent/'sealing_observer_cost_v99'), str(HERE.parent/'whole_collateral_wire_revision_v97'), str(HERE.parent/'owned_adaptive_handoff_v92'),
               str(HERE.parent/'adaptive_training_v90'), str(HERE.parent), str(ROOT/'src')]
import adaptive_training as A
import handoff as H
import oracle_mainline_v75 as O
import instrument as M
import ruler as R
import transfer as T
import post_transfer as P
import completion as C
from observer import make_observer
from recorded import RecordedTrace
from rfl_rebuild.env import kernel as K
from rfl_rebuild.b2.unaffected import EvaluationScene, scene_domain
from rfl_rebuild.b1.tier import Tier
from rfl_rebuild.learner.reference import QReferenceView
from rfl_rebuild.learner.store import LearnerPersistentState, Edit, DecisionAddress, QAddress, DECISION, PROCESS, CONTROLLER, Q

CONTRACT = json.loads((HERE/'contract.json').read_bytes())
COUNTS = Counter()
STARTED = time.monotonic()
CASE, MODE, STAGE = 'prospective-setup', 'dq', 'source'
CODE_INFO = {}


def emit(tag, data):
    line = json.dumps({'tag': tag, 'case': CASE, 'mode': MODE, 'payload': A.wire(data)},
                      sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    COUNTS['stdout_bound_bytes'] += len(line.encode('ascii'))+2
    if COUNTS['stdout_bound_bytes'] > CONTRACT['budget']['stdout_bytes']:
        raise RuntimeError('finite complete-capture byte budget')
    print(line, flush=True)


def profile(frame, event, arg):
    code = frame.f_code
    if code not in CODE_INFO:
        CODE_INFO[code] = (code.co_filename.replace('\\', '/'), code.co_name, code.co_qualname)
    path, name, qualname = CODE_INFO[code]
    kernel = path.endswith('rfl_rebuild/env/kernel.py')
    store = path.endswith('rfl_rebuild/learner/store.py')
    b1 = path.endswith('rfl_rebuild/b1/runner.py') and name in ('run_patch_law', 'run_dq_law', 'run_process_law', 'run_controller_law')
    if event == 'call':
        kind = name if kernel and name in ('step', 'rollout') else 'transaction' if store and name == 'apply_transaction' else 'B1' if b1 else None
        if kind:
            COUNTS[kind] += 1
            if COUNTS[kind] > CONTRACT['budget'][kind]:
                raise RuntimeError('finite native budget: '+kind)
        if kernel and name == 'rollout' and time.monotonic()-STARTED > CONTRACT['budget']['seconds']:
            raise RuntimeError('finite wall budget')
        forbidden = ((path.endswith('rfl_rebuild/b2/training.py') and name in ('derive', 'key', 'mix', 'train_curve', 'pre_level')) or
            (kernel and name == 'sample') or (path.endswith('rfl_rebuild/solve/dp.py') and name == 'solve_reference') or
            (path.endswith('random.py') and name in ('__init__', 'random', 'randrange')) or
            qualname in ('FutureTrainingProtocol.__init__', 'Curve.__init__'))
        if forbidden:
            COUNTS['forbidden'] += 1
            raise RuntimeError('ungranted key/DP/formal entry')
        if store and name == 'apply_transaction':
            emit('TX_CALL', {'before': A.stores(frame.f_locals['self']), 'edits': frame.f_locals['edits']})
        if path.endswith('/ruler.py') and name == '_ordinary_bank':
            emit('BANK_BEGIN', {'stage': frame.f_locals['stage'], 'units': [s.key for s in frame.f_locals['ordered_units']],
                               'state': A.stores(frame.f_locals['state']),
                               'sanitized_owners': frame.f_back.f_locals.get('owners')})
    elif event == 'return':
        if kernel and name == 'rollout':
            caller = frame.f_back
            scene = caller.f_locals.get('scene')
            emit('RAW_ROLLOUT' if type(arg) is K.RolloutTrace else 'INCOMPLETE_ROLLOUT',
                 {'stage': caller.f_locals.get('stage', STAGE),
                  'scene': scene.key if type(scene) is EvaluationScene else CONTRACT['new_scene'], 'trace': arg})
        elif store and name == 'apply_transaction':
            emit('TX_RETURN', {'after': A.stores(frame.f_locals['self'])})
        elif b1 and type(arg) is O.base.native_b1.B1Result:
            emit('NATIVE_B1_RETURN', {'law': frame.f_locals['law'].name,
                'full_post': A.stores(arg.post_state), 'ledger_canonical': arg.ledger.canonical(), 'receipts': arg.ledger.receipts})


def reference():
    raw = (ROOT/CONTRACT['reference_input']['path']).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == CONTRACT['reference_input']['sha256']
    rows = {}
    for line in raw.decode('utf-8').splitlines():
        if line.startswith('DECISION_CONTEXT='):
            d=json.loads(line.split('=',1)[1]); x,y,t,k,p,z,m=d['context']
            rows[K.State(x,y,t,k,p),z,m] = {a:float.fromhex(v) for a,v in d['q_row_hex']}
    ref = QReferenceView(rows, name='v101-existing-Q-star-no-new-DP')
    assert ref.digest() == CONTRACT['reference_input']['q_digest'] and K.START == (0,2)
    emit('REFERENCE', {'rows':len(rows), 'digest':ref.digest()})
    return ref


def new_pre(ref, mode):
    contexts = [DecisionAddress(K.State(*K.START,t,0,2),1,m) for t in range(K.HORIZON) for m in (0,1)]
    contexts += [DecisionAddress(K.State(1,2,1,0,2),1,m) for m in (0,1)]
    sentinel = DecisionAddress(K.State(*K.START,0,1,2),1,0)
    contexts.append(sentinel)
    sites = ((K.ControllerSite(K.State(*K.START,0,0,2),K.WAIT),K.RIGHT),
             (K.ControllerSite(K.State(1,2,1,0,2),K.WAIT),K.LEFT),
             (K.ControllerSite(sentinel.state,K.WAIT),K.RIGHT))
    legality=[]
    for site,target in sites:
        service=[]
        for z in K.option_ids():
            for m in (0,1):
                legal=ref.row(site.state,z,m)
                if site.cmd in legal:
                    assert target in legal
                    service.append({'z':z,'m':m,'legal':list(legal)})
        assert service
        legality.append({'site':site,'target':target,'all_serving_contexts':service})
    edits=[Edit(PROCESS,0,1),Edit(PROCESS,3,2)]+[Edit(CONTROLLER,s,t) for s,t in sites]
    for a in contexts:
        row=ref.row(a.state,a.z,a.m); assert K.WAIT in row
        edits.append(Edit(Q,QAddress(a.state,a.z,a.m,K.WAIT),max(row.values())+1.0)
                     if mode=='dq' else Edit(DECISION,a,K.WAIT))
    assert len(edits)==32 and len(contexts)==27
    emit('SOURCE_INSTALL_PLANNED', {'mode':mode,'edits':edits,'legality':legality})
    state=LearnerPersistentState(); state.apply_transaction(tuple(edits),q_reference=ref)
    emit('FULL_SOURCE_PRE', {'stores':A.stores(state)})
    return state




class RecordedDQTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global STAGE
        cls.ref=reference();cls.healthy=json.loads((ROOT/CONTRACT['healthy_reference']).read_bytes())
        cls.sources=[];cls.bounds=[];cls.preps=[]
        for scene_key in CONTRACT['new_scenes']:
            STAGE='source'
            state=new_pre(cls.ref,'dq')
            source=O.capture_source(state,scene=EvaluationScene(*scene_key),regime='P',
                q_reference=cls.ref,healthy_reference=cls.healthy,counterfactual=False)
            emit('ORIGINAL_SOURCE',O.source_audit(source))
            bound=H.bind_source(source,mode='dq')
            emit('BOUND_BEFORE_ARMS',H.source_audit(bound))
            cls.sources.append(source);cls.bounds.append(bound)
        emit('EXTRA_SOURCE_WORK',{'actual_extra_owned_sources':2,'source_scenes':CONTRACT['new_scenes'],
             'complete_factual_wire_equal':A.wire(O._checked_source(cls.sources[0])[1].trace)==
                                           A.wire(O._checked_source(cls.sources[1])[1].trace),
             'old_handles_recreated':False})

    def setUp(self):
        global CASE
        CASE=self._testMethodName
        self.assertIs(sys.getprofile(),ACTIVE_OBSERVER)

    def test_01_complete_new_owned_DQ_measure_without_native_bank_replay(self):
        global STAGE
        for index,bound in enumerate(self.bounds):
            before={k:COUNTS[k] for k in ('B1','rollout','step','transaction')}
            recorded=T.load_for(bound)
            emit('RECORDED_PRE_TRANSFER',T.audit(recorded,bound))
            if index==0:
                for scene,trace in T.rows(recorded,bound):
                    emit('RECORDED_PRE_OBSERVATION',{'stage':'recorded-pre','scene':scene.key,'trace':trace,
                         'old_capture_sha256':T.EXPECTED_STDOUT,'is_new_kernel_return':False})
            prep=R.prepare(bound,architecture='D_Q',recorded_census=recorded)
            self.assertEqual(before,{k:COUNTS[k] for k in before})
            self.preps.append(prep)
            d=R._PREPARED[prep]
            self.assertEqual(len(d.owners),7);self.assertEqual(len(d.projected.residual_units),3)
            self.assertEqual(d.status,'READY')
            emit('PREPARATION_COMPLETE',{'source_index':index,'origin':d.origin,'origin_sha256':d.seal,
                 'region':M.audit(d.region),'new_pre_kernel_rollouts':0})
        STAGE='recorded-post'
        before_rollout=COUNTS['rollout'];before_step=COUNTS['step']
        result=C.run(self.preps[0]);type(self).completed=result
        md=C._RESULTS[result]
        emit('RECORDED_POST_TRANSFER',P.audit(md.transfer,md.prepared,md.pair,md.starts))
        for role,bank in zip(H.ROLES,md.records):
            for record in bank:
                self.assertIs(type(record.trace),RecordedTrace)
                self.assertIsNot(type(record.trace),K.RolloutTrace)
                emit('RECORDED_POST_OBSERVATION',{'stage':role,'scene':record.scene.key,'trace':record.trace,
                     'old_capture_sha256':P.EXPECTED_RAW,'is_new_kernel_return':False})
        measured=C.audit(result);emit('WHOLE_MEASUREMENT_COMPLETE',measured)
        self.assertIs(type(result),C.RecordedDQWholeMeasurement)
        self.assertIsNot(type(result),R.WholeMeasurement)
        self.assertEqual(COUNTS['rollout'],before_rollout);self.assertEqual(COUNTS['step'],before_step)
        self.assertEqual(measured['payload']['new_post_kernel_rollouts'],0)
        self.assertIs(md.shared_units,M.units(R._PREPARED[md.prepared].region))
        self.assertEqual(measured['payload']['scores'][0]['value'].hex(),0.0.hex())
        self.assertEqual(measured['payload']['scores'][1]['value'].hex(),0.0.hex())
        self.assertEqual(measured['payload']['paired_difference'].hex(),0.0.hex())
        emit('RECORDED_ENDPOINT_COMPLETE',{'runtime_complete_handle_issued':True,'new_native_banks':0,
            'pre_recorded_count_each':5760,'post_recorded_count_each':len(md.shared_units),
            'no_loss_or_shortened_region':True,'original_timeout_reinterpreted':False})

    def test_02_wrong_source_role_and_missing_record_cannot_issue_value(self):
        md=C._RESULTS[self.completed]
        counts={k:COUNTS[k] for k in ('B1','rollout','step','transaction')}
        with self.assertRaises(A.ProtocolError):P.RecordedImmediateBanks()
        with self.assertRaises(A.ProtocolError):C.RecordedDQWholeMeasurement()
        with self.assertRaises(A.ProtocolError):C.audit({'scores':[0.,0.]})
        with self.assertRaises(A.ProtocolError) as caught:P.rows(md.transfer,self.preps[1],md.pair,md.starts)
        emit('WRONG_SOURCE_REJECTED',{'message':str(caught.exception)})
        with self.assertRaises(A.ProtocolError) as caught:P.rows(md.transfer,md.prepared,md.pair,tuple(reversed(md.starts)))
        emit('SWAPPED_ROLE_REJECTED',{'message':str(caught.exception)})
        original=P._RECORDED[md.transfer]
        try:
            P._RECORDED[md.transfer]=replace(original,rows=(original.rows[0][:-1],original.rows[1]))
            with self.assertRaises(A.ProtocolError) as caught:C.audit(self.completed)
            emit('MISSING_POST_RECORD_REJECTED',{'message':str(caught.exception)})
        finally:P._RECORDED[md.transfer]=original
        try:
            C._RESULTS[self.completed]=replace(md,starts=(md.starts[0],md.starts[0]))
            with self.assertRaises(A.ProtocolError) as caught:C.audit(self.completed)
            emit('IMMEDIATE_ROLE_ALIAS_REJECTED',{'message':str(caught.exception)})
        finally:C._RESULTS[self.completed]=md
        self.assertIs(C._RESULTS[self.completed],md)
        self.assertIs(P._RECORDED[md.transfer],original)
        C._checked(self.completed)
        self.assertEqual(counts,{k:COUNTS[k] for k in counts})
        emit('TRANSFER_INPUTS_RESTORED',{'new_native_calls':0,'complete_handle_restored':True})

    def test_03_actual_record_read_partial_preserved_no_handle_no_retry(self):
        original=P._physical_lines
        yielded=0
        def planned():
            nonlocal yielded
            for physical in original():
                row=json.loads(physical)
                yield physical
                if row['mode']=='dq' and row['tag']=='RAW_ROLLOUT' and row['payload']['stage']=='reference':
                    yielded+=1
                    if yielded==1:raise RuntimeError('v101 prospective recorded-reader fault AFTER firstpostrecord BEFORE handle')
        try:
            P._physical_lines=planned
            try:C.run(self.preps[1])
            except RuntimeError:emit('PARTIAL_TRANSFER_FAILURE',{'traceback':traceback.format_exc(),'partial':C.partial_audit(self.preps[1])})
            else:self.fail('planned record-reader failure did not fire')
        finally:P._physical_lines=original
        self.assertIs(P._physical_lines,original)
        p=C.partial_audit(self.preps[1])
        self.assertFalse(p['has_measurement_handle']);self.assertFalse(p['recorded_partial']['has_recorded_handle'])
        self.assertEqual([len(x) for x in p['recorded_partial']['ordered_rows']],[1,0])
        pair=C._PARTIAL[self.preps[1]]['pair'];starts=C._PARTIAL[self.preps[1]]['starts']
        counts={k:COUNTS[k] for k in ('B1','rollout','step','transaction')}
        with self.assertRaises(A.ProtocolError):C.run(self.preps[1])
        with self.assertRaises(A.ProtocolError):C.run(self.preps[0])
        with self.assertRaises(A.ProtocolError):P.load_for(self.preps[1],pair,starts)
        self.assertEqual(counts,{k:COUNTS[k] for k in counts})
        self.assertIs(sys.getprofile(),ACTIVE_OBSERVER)
        emit('PARTIAL_COMPLETE_ONCE_AND_RESTORE',{'recorded_partial_rows':[1,0],'new_post_kernel_calls':0,
            'dependency_restored':True,'duplicate_entries_rejected_no_native':True})


if __name__=='__main__':
    ACTIVE_OBSERVER=make_observer(profile)
    previous=sys.getprofile();assert previous is None
    sys.setprofile(ACTIVE_OBSERVER)
    try:
        suite=unittest.defaultTestLoader.loadTestsFromTestCase(RecordedDQTests)
        result=unittest.TextTestRunner(verbosity=2,failfast=True).run(suite)
        loaded={}
        for module in tuple(sys.modules.values()):
            filename=getattr(module,'__file__',None)
            if filename:
                p=Path(filename).resolve()
                if p.is_file() and p.suffix=='.py' and p.is_relative_to(ROOT):
                    loaded[p.relative_to(ROOT).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
        binding=json.loads((HERE/'evidence/claim.json').read_bytes())['input_binding_before']
        assert all(n in binding and binding[n]['sha256']==h for n,h in loaded.items())
        assert sys.getprofile() is ACTIVE_OBSERVER
        emit('ACTUAL_LOADED_SOURCE_INVENTORY',loaded)
    finally:sys.setprofile(previous)
    emit('RESULT',{'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
        'skips':len(result.skipped),'counts':dict(COUNTS),'seconds':time.monotonic()-STARTED,
        'profile_restored':sys.getprofile() is previous,'new_pre_post_native_banks':0,
        'scientific_qualification':False,'collection_authorized':False,'keyed_protocol_executed':False})
    raise SystemExit(0 if result.wasSuccessful() else 1)
