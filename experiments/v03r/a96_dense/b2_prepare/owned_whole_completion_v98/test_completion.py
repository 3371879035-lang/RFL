"""V98 NEW authentic completion, explicit recorded DQpre and fresh patch/post."""
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
sys.path[:0] = [str(HERE), str(HERE.parent/'whole_collateral_wire_revision_v97'), str(HERE.parent/'owned_adaptive_handoff_v92'),
               str(HERE.parent/'adaptive_training_v90'), str(HERE.parent), str(ROOT/'src')]
import adaptive_training as A
import handoff as H
import oracle_mainline_v75 as O
import instrument as M
import ruler as R
import transfer as T
from recorded import RecordedTrace
from rfl_rebuild.env import kernel as K
from rfl_rebuild.b2.unaffected import EvaluationScene, scene_domain
from rfl_rebuild.b1.tier import Tier
from rfl_rebuild.learner.reference import QReferenceView
from rfl_rebuild.learner.store import LearnerPersistentState, Edit, DecisionAddress, QAddress, DECISION, PROCESS, CONTROLLER, Q

CONTRACT = json.loads((HERE/'contract.json').read_bytes())
COUNTS = Counter()
STARTED = time.monotonic()
CASE, MODE, STAGE = 'prospective-setup', '', 'source'
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
    ref = QReferenceView(rows, name='v98-existing-Q-star-no-new-DP')
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


class WholeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global MODE,STAGE
        cls.ref=reference(); cls.healthy=json.loads((ROOT/CONTRACT['healthy_reference']).read_bytes())
        cls.sources=[]; cls.bounds=[]; cls.preps=[]; cls.results=[]
        for mode in ('dq','patch-adaptive'):
            MODE=mode; STAGE='source'
            source=O.capture_source(new_pre(cls.ref,mode),scene=EvaluationScene(*CONTRACT['new_scene']),regime='P',
                                    q_reference=cls.ref,healthy_reference=cls.healthy,counterfactual=False)
            emit('ORIGINAL_SOURCE', O.source_audit(source))
            bound=H.bind_source(source,mode=mode); emit('BOUND_BEFORE_ARMS',H.source_audit(bound))
            cls.sources.append(source); cls.bounds.append(bound)
        raw0=O._checked_source(cls.sources[0])[1].trace
        raw1=O._checked_source(cls.sources[1])[1].trace
        assert A.wire(raw0)==A.wire(raw1)
        emit('SOURCE_EXTENSIONAL_EQUALITY', {'equal_full_raw':True,'additional_owned_sources':2})

    def setUp(self):
        global CASE
        CASE=self._testMethodName

    def test_01_full_pre_before_arms_and_complete_whole_metrics(self):
        global MODE,STAGE
        for source,bound,mode,architecture,law in zip(self.sources,self.bounds,('dq','patch-adaptive'),
            ('D_Q','D_patch'),('FactualReturnWrite','DeleteFactualPatch')):
            MODE=mode; STAGE='pre'
            before=COUNTS['B1']
            recorded=None
            if mode=='dq':
                native_before={k:COUNTS[k] for k in ('B1','rollout','step','transaction')}
                recorded=T.load_for(bound)
                self.recorded=recorded
                emit('RECORDED_CENSUS_TRANSFER',T.audit(recorded,bound))
                for scene,trace in T.rows(recorded,bound):
                    self.assertIs(type(trace),RecordedTrace)
                    self.assertIsNot(type(trace),K.RolloutTrace)
                    emit('RECORDED_PRE_OBSERVATION',{'stage':'recorded-pre','scene':scene.key,'trace':trace,
                          'old_capture_sha256':T.EXPECTED_STDOUT,'is_new_kernel_return':False})
                self.assertEqual(native_before,{k:COUNTS[k] for k in native_before})
            prep=R.prepare(bound,architecture=architecture,recorded_census=recorded)
            data=R._PREPARED[prep]; self.assertEqual(before,COUNTS['B1'])
            self.assertEqual(data.status,'READY'); self.assertEqual(len(data.records),5760)
            self.assertEqual(data.origin['pre_provenance']['kind'],'recorded_exact_binding' if mode=='dq' else 'fresh_kernel_census')
            self.assertEqual(len(data.owners),7); self.assertEqual(len(data.projected.residual_units),3)
            region=M.units(data.region); self.assertTrue(0<len(region)<5760)
            self.assertIs(region,M.units(data.region))
            emit('PREPARATION_COMPLETE', {'origin':data.origin,'origin_sha256':data.seal,'region':M.audit(data.region),
                                         'B1_unchanged_during_pre':True})
            self.preps.append(prep)
            STAGE='post'
            result=R.run_cell(prep,tier=Tier.L0_FACTUAL,law_name=law)
            audit=R.audit(result); emit('WHOLE_MEASUREMENT_COMPLETE',audit)
            self.results.append(result)
            md=R._MEASURED[result]
            self.assertIs(md.shared_units,region)
            pre={r.scene:r.trace for r in data.records}
            # Source-local B1 changes cannot alter a deterministic trajectory
            # that never consults any modified owner. Test all selected scenes.
            for records in md.records:
                self.assertEqual(tuple(r.scene for r in records),region)
                for r in records:
                    self.assertEqual(A.wire(r.trace),A.wire(pre[r.scene]))
            emit('WHOLE_LOCALITY_MATCH', {'selected_scenes':len(region),'all_two_role_raw_equal_pre':True,
                                          'scores':audit['payload']['scores'],'paired_difference':audit['payload']['paired_difference']})

    def test_02_strict_extent_and_nominal_inputs(self):
        global MODE
        MODE='dq'
        domain=scene_domain(); units=M.units(R._PREPARED[self.preps[0]].region)
        for candidate in ((),domain,(units[0],units[0]),(units[1],units[0])):
            with self.assertRaises(A.ProtocolError) as caught:
                M.require_extent(domain,candidate)
            emit('STRICT_EXTENT_REJECTED',{'size':len(candidate),'message':str(caught.exception)})
        with self.assertRaises(A.ProtocolError): M.Owner('process',(True,))
        with self.assertRaises(A.ProtocolError): M.PreInput()
        with self.assertRaises(A.ProtocolError): M.build({'owners':[],'truth':True})
        with self.assertRaises(A.ProtocolError): R.audit({'value':0.0})
        emit('NOMINAL_INPUTS_REJECTED',{'fake_pre_fake_result_bool_owner':True})

    def test_03_owner_and_region_tampering_rejected_without_native(self):
        global MODE
        MODE='dq'; prep=self.preps[0]; d=R._PREPARED[prep]; counts=dict(COUNTS)
        with self.assertRaises(A.ProtocolError): T.RecordedOrdinaryCensus()
        with self.assertRaises(A.ProtocolError): T.rows(self.recorded,self.bounds[1])
        with self.assertRaises(A.ProtocolError): T.load_for(self.bounds[0])
        original_recorded=T._RECORDED[self.recorded]
        try:
            T._RECORDED[self.recorded]=replace(original_recorded,rows=original_recorded.rows[:-1])
            with self.assertRaises(A.ProtocolError) as caught: T.rows(self.recorded,self.bounds[0])
            emit('RECORDED_TRIM_REJECTED',{'message':str(caught.exception)})
        finally: T._RECORDED[self.recorded]=original_recorded
        old=d.owners
        try:
            d.owners=old[:-1]
            with self.assertRaises(A.ProtocolError) as caught: R._checked_prepared(prep)
            emit('OWNER_DROP_REJECTED',{'message':str(caught.exception)})
        finally: d.owners=old
        original=M._REGIONS[d.region]
        try:
            M._REGIONS[d.region]=(original[0],original[1],original[2][1:],original[3],original[4])
            with self.assertRaises(A.ProtocolError) as caught: M.units(d.region)
            emit('REGION_TRIM_REJECTED',{'message':str(caught.exception)})
        finally: M._REGIONS[d.region]=original
        for key in ('B1','rollout','step','transaction'):
            self.assertEqual(COUNTS[key],counts[key])
        tree=ast.parse((HERE/'instrument.py').read_text(encoding='utf-8'))
        forbidden={'Gamma','truth','tier','law','ledger','receipt','WriteSet','architecture'}
        names={n.id for n in ast.walk(tree) if isinstance(n,ast.Name)}
        self.assertFalse(names&forbidden)
        emit('RESTORED_INPUT_AND_AST_GATE',{'forbidden_feature_names_loaded':sorted(names&forbidden),'native_counts_unchanged':True})

    def test_04_real_partial_post_preserved_once(self):
        global MODE,STAGE
        MODE='dq'; STAGE='partial-post'; prep=self.preps[0]
        original=R._run_scene; post_calls=0
        def planned(channels,scene,stage):
            nonlocal post_calls
            if stage=='reference':
                post_calls+=1
                if post_calls==2: raise RuntimeError('prospective second post scene failure BEFORE kernel')
            return original(channels,scene,stage)
        try:
            R._run_scene=planned
            try: R.run_cell(prep,tier=Tier.L3_ORACLE,law_name='LocalOracleRestore')
            except RuntimeError:
                emit('PARTIAL_POST_FAILURE',{'traceback':traceback.format_exc(),
                     'partial':R.partial_audit(prep,tier=Tier.L3_ORACLE,law_name='LocalOracleRestore')})
            else: self.fail('planned dependency fault did not fire')
        finally: R._run_scene=original
        self.assertIs(R._run_scene,original)
        p=R.partial_audit(prep,tier=Tier.L3_ORACLE,law_name='LocalOracleRestore')
        self.assertEqual([len(x) for x in p['ordered_records']],[1,0])
        before={k:COUNTS[k] for k in ('B1','rollout','step','transaction')}
        with self.assertRaises(A.ProtocolError): R.run_cell(prep,tier=Tier.L3_ORACLE,law_name='LocalOracleRestore')
        with self.assertRaises(A.ProtocolError): R.run_cell(prep,tier=Tier.L0_FACTUAL,law_name='FactualReturnWrite')
        with self.assertRaises(A.ProtocolError): R.prepare(self.bounds[0],architecture='D_Q')
        self.assertEqual(before,{k:COUNTS[k] for k in before})
        emit('PARTIAL_COMPLETE_ONCE_AND_RESTORE',{'actual_completed_post_scenes':[1,0],
                                                'native_counts_unchanged':True,'dependency_restored':True})


if __name__=='__main__':
    sys.setprofile(profile)
    try:
        suite=unittest.defaultTestLoader.loadTestsFromTestCase(WholeTests)
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
        emit('ACTUAL_LOADED_SOURCE_INVENTORY',loaded)
        emit('RESULT',{'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
             'skips':len(result.skipped),'counts':dict(COUNTS),'seconds':time.monotonic()-STARTED,
             'scientific_qualification':False,'collection_authorized':False,'keyed_protocol_executed':False})
    finally: sys.setprofile(None)
    raise SystemExit(0 if result.wasSuccessful() else 1)
