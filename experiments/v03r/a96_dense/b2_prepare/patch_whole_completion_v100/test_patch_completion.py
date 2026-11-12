"""V100 first native PATCH pre/whole/post/handle and sparse observer capture.
No old fixture execution or repeated DQ bank; executed dependencies unchanged.
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
CASE, MODE, STAGE = 'prospective-setup', 'patch-adaptive', 'source'
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
    ref = QReferenceView(rows, name='v100-existing-Q-star-no-new-DP')
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



class PatchCompletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global STAGE
        cls.ref=reference()
        cls.healthy=json.loads((ROOT/CONTRACT['healthy_reference']).read_bytes())
        STAGE='source'
        state=new_pre(cls.ref,'patch-adaptive')
        cls.source=O.capture_source(state,scene=EvaluationScene(*CONTRACT['new_scene']),regime='P',
            q_reference=cls.ref,healthy_reference=cls.healthy,counterfactual=False)
        emit('ORIGINAL_SOURCE',O.source_audit(cls.source))
        cls.bound=H.bind_source(cls.source,mode='patch-adaptive')
        emit('BOUND_BEFORE_ARMS',H.source_audit(cls.bound))
        # Read only old stored data to document mechanical same-fullpre, never
        # import an old test/checker or recreate its source/pair/role.
        archive=ROOT/CONTRACT['preserved_v98_raw']['path']
        assert hashlib.sha256(archive.read_bytes()).hexdigest()==CONTRACT['preserved_v98_raw']['sha256']
        old_state=None;old_factual=None
        with archive.open(encoding='ascii') as stream:
            for line in stream:
                row=json.loads(line)
                if row['mode']=='patch-adaptive':
                    if row['tag']=='FULL_SOURCE_PRE':old_state=row['payload']['stores']
                    elif row['tag']=='RAW_ROLLOUT' and row['payload']['stage']=='source':
                        old_factual=row['payload']['trace'];break
        assert old_state==A.stores(state)
        assert old_factual==A.wire(O._checked_source(cls.source)[1].trace)
        emit('EXTRA_SOURCE_WORK',{'extra_owned_source':1,'fullpre_and_factual_wire_equal_v98_stored_patch':True,
            'new_scene':CONTRACT['new_scene'],'old_handles_recreated':False,'new_DQ_bank':False})

    def setUp(self):
        global CASE
        CASE=self._testMethodName
        self.assertIs(sys.getprofile(),ACTIVE_OBSERVER)

    def test_01_first_real_patch_census_pair_posts_and_complete_handle(self):
        global STAGE
        STAGE='pre'
        counts={k:COUNTS[k] for k in ('B1','rollout','step','transaction')}
        prep=R.prepare(self.bound,architecture='D_patch')
        type(self).prep=prep
        d=R._PREPARED[prep]
        self.assertEqual(COUNTS['B1'],counts['B1'])
        self.assertEqual(COUNTS['transaction'],counts['transaction'])
        self.assertEqual(d.status,'READY')
        self.assertEqual(len(d.records),5760)
        self.assertEqual(d.origin['pre_provenance'],{'kind':'fresh_kernel_census','native_pre_rollouts':5760})
        self.assertEqual(len(d.owners),7)
        self.assertEqual(len(d.projected.residual_units),3)
        self.assertTrue(all(type(r.trace) is K.RolloutTrace for r in d.records))
        self.assertTrue(all(type(r.trace) is not RecordedTrace for r in d.records))
        region=M.units(d.region)
        self.assertTrue(0<len(region)<5760)
        self.assertIs(region,M.units(d.region))
        emit('PREPARATION_COMPLETE',{'origin':d.origin,'origin_sha256':d.seal,'region':M.audit(d.region),
                                    'B1_unchanged_during_pre':True})
        STAGE='post'
        result=R.run_cell(prep,tier=Tier.L0_FACTUAL,law_name='DeleteFactualPatch')
        type(self).completed=result
        audit=R.audit(result)
        emit('WHOLE_MEASUREMENT_COMPLETE',audit)
        md=R._MEASURED[result]
        self.assertIs(type(result),R.WholeMeasurement)
        self.assertIs(md.shared_units,region)
        self.assertEqual(len(md.records),2)
        pre={r.scene:r.trace for r in d.records}
        for records in md.records:
            self.assertEqual(tuple(r.scene for r in records),region)
            for record in records:
                self.assertEqual(A.wire(record.trace),A.wire(pre[record.scene]))
        self.assertEqual(audit['payload']['scores'][0]['value'].hex(),0.0.hex())
        self.assertEqual(audit['payload']['scores'][1]['value'].hex(),0.0.hex())
        self.assertEqual(audit['payload']['paired_difference'].hex(),0.0.hex())
        self.assertIs(sys.getprofile(),ACTIVE_OBSERVER)
        emit('WHOLE_LOCALITY_MATCH',{'selected_scenes':len(region),'all_two_role_raw_equal_pre':True,
            'scores':audit['payload']['scores'],'paired_difference':audit['payload']['paired_difference'],
            'runtime_complete_handle_issued':True,'readonly_fullIposts':True})

    def test_02_real_scope_alias_and_content_gates_restore_without_native(self):
        d=R._PREPARED[self.prep]
        counts={k:COUNTS[k] for k in ('B1','rollout','step','transaction')}
        original_owners=d.owners
        try:
            d.owners=original_owners[:-1]
            with self.assertRaises(A.ProtocolError) as caught:R._checked_prepared(self.prep)
            emit('OWNER_DROP_REJECTED',{'message':str(caught.exception)})
        finally:d.owners=original_owners
        original_region=M._REGIONS[d.region]
        try:
            M._REGIONS[d.region]=(original_region[0],original_region[1],original_region[2][1:],
                                  original_region[3],original_region[4])
            with self.assertRaises(A.ProtocolError) as caught:M.units(d.region)
            emit('REGION_TRIM_REJECTED',{'message':str(caught.exception)})
        finally:M._REGIONS[d.region]=original_region
        md=R._MEASURED[self.completed]
        try:
            R._MEASURED[self.completed]=replace(md,starts=(md.starts[0],md.starts[0]))
            with self.assertRaises(A.ProtocolError) as caught:R.audit(self.completed)
            emit('IMMEDIATE_ROLE_ALIAS_REJECTED',{'message':str(caught.exception)})
        finally:R._MEASURED[self.completed]=md
        units=M.units(d.region);domain=scene_domain()
        for candidate in ((),domain,(units[0],units[0]),(units[1],units[0])):
            with self.assertRaises(A.ProtocolError) as caught:M.require_extent(domain,candidate)
            emit('STRICT_EXTENT_REJECTED',{'size':len(candidate),'message':str(caught.exception)})
        with self.assertRaises(A.ProtocolError):M.Owner('process',(True,))
        with self.assertRaises(A.ProtocolError):M.PreInput()
        with self.assertRaises(A.ProtocolError):M.build({'owners':[],'truth':True})
        with self.assertRaises(A.ProtocolError):R.audit({'value':0.0})
        self.assertEqual(counts,{k:COUNTS[k] for k in counts})
        self.assertIs(R._MEASURED[self.completed],md)
        R._checked_result(self.completed)
        tree=ast.parse(Path(M.__file__).read_text(encoding='utf-8'))
        forbidden={'Gamma','truth','tier','law','ledger','receipt','WriteSet','architecture'}
        names={n.id for n in ast.walk(tree) if isinstance(n,ast.Name)}
        self.assertFalse(names&forbidden)
        emit('RESTORED_INPUT_AND_AST_GATE',{'forbidden_feature_names_loaded':sorted(names&forbidden),
            'native_counts_unchanged':True,'actual_complete_handle_restored':True,
            'scope_and_alias_mutation_targets':3})
        paths={path+':'+name for path,name,_ in CODE_INFO.values()}
        required={'src/rfl_rebuild/env/kernel.py:step','src/rfl_rebuild/env/kernel.py:rollout',
                  'src/rfl_rebuild/learner/store.py:apply_transaction','src/rfl_rebuild/b1/runner.py:run_patch_law'}
        normalized={s.split('/src/',1)[-1] for s in paths}
        self.assertTrue({s.split('src/',1)[-1] for s in required}<=normalized)
        emit('SPARSE_NATIVE_OBSERVER_CAPTURED',{'required_actual_code_paths':sorted(required),
            'original_frame_event_arg_handler':True,'observer_still_installed':sys.getprofile() is ACTIVE_OBSERVER})

    def test_03_first_real_patch_partial_pair_once_and_dependency_restore(self):
        global STAGE
        STAGE='partial-post'
        original=R._run_scene
        post_calls=0
        def planned(channels,scene,stage):
            nonlocal post_calls
            if stage=='reference':
                post_calls+=1
                if post_calls==2:raise RuntimeError('v100 prospective second PATCH post scene failure BEFORE kernel')
            return original(channels,scene,stage)
        try:
            R._run_scene=planned
            try:R.run_cell(self.prep,tier=Tier.L3_ORACLE,law_name='LocalOracleRestore')
            except RuntimeError:
                emit('PARTIAL_POST_FAILURE',{'traceback':traceback.format_exc(),
                    'partial':R.partial_audit(self.prep,tier=Tier.L3_ORACLE,law_name='LocalOracleRestore')})
            else:self.fail('planned dependency fault did not fire')
        finally:R._run_scene=original
        self.assertIs(R._run_scene,original)
        p=R.partial_audit(self.prep,tier=Tier.L3_ORACLE,law_name='LocalOracleRestore')
        self.assertEqual([len(x) for x in p['ordered_records']],[1,0])
        self.assertFalse(p['has_measurement_handle'])
        counts={k:COUNTS[k] for k in ('B1','rollout','step','transaction')}
        with self.assertRaises(A.ProtocolError):R.run_cell(self.prep,tier=Tier.L3_ORACLE,law_name='LocalOracleRestore')
        with self.assertRaises(A.ProtocolError):R.run_cell(self.prep,tier=Tier.L0_FACTUAL,law_name='DeleteFactualPatch')
        with self.assertRaises(A.ProtocolError):R.prepare(self.bound,architecture='D_patch')
        self.assertEqual(counts,{k:COUNTS[k] for k in counts})
        self.assertIs(sys.getprofile(),ACTIVE_OBSERVER)
        emit('PARTIAL_COMPLETE_ONCE_AND_RESTORE',{'actual_completed_post_scenes':[1,0],
            'native_counts_unchanged':True,'dependency_restored':True,'observer_still_installed':True})


if __name__=='__main__':
    ACTIVE_OBSERVER=make_observer(profile)
    previous=sys.getprofile()
    assert previous is None
    sys.setprofile(ACTIVE_OBSERVER)
    try:
        suite=unittest.defaultTestLoader.loadTestsFromTestCase(PatchCompletionTests)
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
    finally:
        sys.setprofile(previous)
    emit('RESULT',{'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
        'skips':len(result.skipped),'counts':dict(COUNTS),'seconds':time.monotonic()-STARTED,
        'profile_restored':sys.getprofile() is previous,'scientific_qualification':False,
        'collection_authorized':False,'keyed_protocol_executed':False})
    raise SystemExit(0 if result.wasSuccessful() else 1)
