"""New actual owned multi-epoch entry, not an old fixture or science collection."""
import ast
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path[:0] = [str(HERE), str(HERE.parent/'owned_adaptive_handoff_v92'),
               str(HERE.parent/'adaptive_training_v90'), str(HERE.parent), str(ROOT/'src')]
import adaptive_training as A
import handoff as H
import oracle_mainline_v75 as O
import learning as L
import owned_curve as C
import external as E
from rfl_rebuild.env import kernel as K
from rfl_rebuild.b2 import training as T
from rfl_rebuild.b2.unaffected import EvaluationScene
from rfl_rebuild.b1.tier import Tier
from rfl_rebuild.learner.reference import QReferenceView
from rfl_rebuild.learner.store import LearnerPersistentState, Edit, DecisionAddress, QAddress, DECISION, PROCESS, CONTROLLER, Q

CONTRACT = json.loads((HERE/'contract.json').read_bytes())
COUNTS = Counter()
STARTED = time.monotonic()
CASE = 'prospective-setup'


def emit(tag, data):
    print(json.dumps({'tag': tag, 'case': CASE, 'payload': A.wire(data)},
                     sort_keys=True, separators=(',', ':'), ensure_ascii=True), flush=True)


def profile(frame, event, arg):
    path = frame.f_code.co_filename.replace('\\', '/')
    name = frame.f_code.co_name
    kernel = path.endswith('rfl_rebuild/env/kernel.py')
    store = path.endswith('rfl_rebuild/learner/store.py')
    b1 = path.endswith('rfl_rebuild/b1/runner.py') and name in ('run_patch_law', 'run_dq_law')
    if event == 'call':
        counted = name if kernel and name in ('step', 'rollout') else 'transaction' if store and name == 'apply_transaction' else 'B1' if b1 else None
        if counted:
            COUNTS[counted] += 1
            if COUNTS[counted] > CONTRACT['budget'][counted]:
                raise RuntimeError('finite native budget: '+counted)
        forbidden = ((path.endswith('rfl_rebuild/b2/training.py') and name in ('derive', 'key', 'mix', 'train_curve', 'pre_level')) or
                     (kernel and name == 'sample') or (path.endswith('rfl_rebuild/solve/dp.py') and name == 'solve_reference') or
                     (path.endswith('random.py') and name in ('__init__', 'random', 'randrange')) or
                     (frame.f_code.co_qualname in ('FutureTrainingProtocol.__init__', 'Curve.__init__')))
        if forbidden:
            COUNTS['forbidden'] += 1
            raise RuntimeError('ungranted key/DP/formal entry: '+name)
        if time.monotonic()-STARTED > CONTRACT['budget']['seconds']:
            raise RuntimeError('finite wall budget')
        if store and name == 'apply_transaction':
            emit('TX_CALL', {'before': A.stores(frame.f_locals['self']), 'edits': frame.f_locals['edits']})
    elif event == 'return':
        if kernel and name == 'step' and type(arg) is K.StepResult:
            emit('RAW_STEP', {'pre_state': frame.f_locals['state'], 'pre_control': frame.f_locals['control'],
                              'a_cmd': frame.f_locals['a_cmd'], 'result': arg})
        elif kernel and name == 'rollout':
            emit('RAW_ROLLOUT' if type(arg) is K.RolloutTrace else 'INCOMPLETE_ROLLOUT', arg)
        elif store and name == 'apply_transaction':
            emit('TX_RETURN', {'after': A.stores(frame.f_locals['self'])})
        elif b1 and type(arg) is O.base.native_b1.B1Result:
            emit('NATIVE_B1_RETURN', {'law': frame.f_locals['law'].name, 'full_post': A.stores(arg.post_state),
                                     'ledger_canonical': arg.ledger.canonical(), 'receipts': arg.ledger.receipts})
        elif path.endswith('/learning.py') and name == 'train_episode' and isinstance(arg, dict):
            emit('CORE_EPISODE', arg)
        elif path.endswith('/owned_curve.py') and name == '_evaluate_bank' and isinstance(arg, tuple):
            emit('CHECKPOINT_BANK', {'role': frame.f_locals['actor'].role,
                                     'epoch': frame.f_locals['actor']._completed,
                                     'traces': arg[0], 'mean_hex': arg[1].hex()})


def reference():
    raw = (ROOT/CONTRACT['reference_input']['path']).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == CONTRACT['reference_input']['sha256']
    rows = {}
    for line in raw.decode('utf-8').splitlines():
        if line.startswith('DECISION_CONTEXT='):
            d = json.loads(line.split('=', 1)[1]); x, y, t, k, phi, z, m = d['context']
            rows[K.State(x, y, t, k, phi), z, m] = {a: float.fromhex(v) for a, v in d['q_row_hex']}
    ref = QReferenceView(rows, name='v95-existing-Q-star-not-new-DP')
    assert ref.digest() == CONTRACT['reference_input']['q_digest'] and K.START == (0, 2)
    emit('REFERENCE', {'rows': len(rows), 'digest': ref.digest()})
    return ref


def new_pre(ref, mode):
    contexts = [DecisionAddress(K.State(*K.START, t, 0, 2), 1, m) for t in range(K.HORIZON) for m in (0, 1)]
    contexts += [DecisionAddress(K.State(1, 2, 1, 0, 2), 1, m) for m in (0, 1)]
    sentinel = DecisionAddress(K.State(*K.START, 0, 1, 2), 1, 0)
    contexts.append(sentinel)
    sites = ((K.ControllerSite(K.State(*K.START, 0, 0, 2), K.WAIT), K.RIGHT),
             (K.ControllerSite(K.State(1, 2, 1, 0, 2), K.WAIT), K.LEFT),
             (K.ControllerSite(sentinel.state, K.WAIT), K.RIGHT))
    legality = []
    for site, target in sites:
        service = []
        for z in K.option_ids():
            for m in (0, 1):
                legal = ref.row(site.state, z, m)
                if site.cmd in legal:
                    assert target in legal
                    service.append({'z': z, 'm': m, 'legal': list(legal)})
        assert service
        legality.append({'site': site, 'target': target, 'all_serving_contexts': service})
    edits = [Edit(PROCESS, 0, 1), Edit(PROCESS, 3, 2)]
    edits += [Edit(CONTROLLER, site, target) for site, target in sites]
    for address in contexts:
        row = ref.row(address.state, address.z, address.m)
        assert K.WAIT in row
        edits.append(Edit(Q, QAddress(address.state, address.z, address.m, K.WAIT), max(row.values())+1.0)
                     if mode == 'dq' else Edit(DECISION, address, K.WAIT))
    assert len(edits) == 32 and len(contexts) == 27
    emit('SOURCE_INSTALL_PLANNED', {'mode': mode, 'edits': edits, 'legality': legality})
    pre = LearnerPersistentState()
    pre.apply_transaction(tuple(edits), q_reference=ref)
    emit('FULL_SOURCE_PRE', {'mode': mode, 'stores': A.stores(pre)})
    return pre


def episodes():
    result = []
    for spec in CONTRACT['episodes']:
        coins = [T.M64]*K.HORIZON
        rejections = [(0,)]*K.HORIZON
        if spec['first_step_explore']:
            coins[0], rejections[0] = 0, (T.M64, 4)
        result.append(L.EngineeringEpisode(spec['epoch'], spec['kappa'], spec['proposal'],
                     K.SemanticTape(spec['phase'], spec['error_flag'], spec['cause_rank']),
                     tuple(coins), tuple(rejections)))
    return tuple(result)


def independent_td(receipt, ref):
    def qaddr(d):
        s = d['state']
        return QAddress(K.State(*(s[k] for k in ('x', 'y', 't', 'kappa', 'phi'))), d['z'], d['m'], d['a'])
    numeric = receipt['before']['current'] if receipt['before']['mode'] == 'dq' else receipt['before']['learning_values']
    work = {qaddr(x['address']): float.fromhex(x['value']['binary64_hex']) for x in numeric['Q']}
    inp = receipt['episode']; tape = inp['tape']
    state = K.State(*K.START, 0, inp['kappa'], tape['phase'])
    z, m = receipt['trace']['option_in_force'], 0
    order, details = [], []
    for item in receipt['trace']['steps']:
        q = QAddress(state, z, m, item['a_cmd'])
        current = work.get(q, ref.value(q))
        post = item['state']; ns = K.State(*(post[k] for k in ('x', 'y', 't', 'kappa', 'phi')))
        nz, nm = item['control']['z'], item['control']['m']
        target = float.fromhex(item['reward']['binary64_hex'])
        if not item['terminal']:
            legal = ref.row(ns, nz, nm)
            target += max(work.get(QAddress(ns, nz, nm, a), ref.value(QAddress(ns, nz, nm, a))) for a in legal)
        updated = current+0.5*(target-current)
        details.append({'address': q, 'current_hex': current.hex(), 'target_hex': target.hex(),
                        'residual_hex': (target-current).hex(), 'updated_hex': updated.hex()})
        work[q] = updated
        if q not in order:
            order.append(q)
        state, z, m = ns, nz, nm
    return tuple(Edit(Q, q, float(work[q])) for q in order), details


class ConnectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ref = reference(); cls.scene = EvaluationScene(*CONTRACT['new_scene'])
        cls.stream = episodes(); cls.sources, cls.bounds, cls.pairs, cls.bundles, cls.handles = {}, {}, {}, {}, {}
        raw = {}
        healthy = json.loads((ROOT/CONTRACT['healthy_reference']).read_bytes())
        for mode, arch, law in (('dq', 'D_Q', 'FactualReturnWrite'), ('patch-adaptive', 'D_patch', 'DeleteFactualPatch')):
            pre = new_pre(cls.ref, mode)
            source = O.capture_source(pre, scene=cls.scene, regime='P', q_reference=cls.ref,
                                      healthy_reference=healthy, counterfactual=False)
            cls.sources[mode] = source
            raw[mode] = A.wire(O._checked_source(source)[1].trace)
            emit('ORIGINAL_SOURCE', {'mode': mode, 'audit': O.source_audit(source)})
            bound = H.bind_source(source, mode=mode); cls.bounds[mode] = bound
            emit('BOUND_BEFORE_ARMS', H.source_audit(bound))
            pair = H.run_whole_pair(bound, architecture=arch, tier=Tier.L0_FACTUAL, law_name=law)
            cls.pairs[mode] = pair
            emit('ORIGINAL_PAIR', {'mode': mode, 'audit': O.pair_audit(pair, source)})
            bundle = C.prepare_curve(bound, pair, episodes=cls.stream,
                                     evaluation_indices=tuple(CONTRACT['evaluation_indices']))
            cls.bundles[mode] = bundle
            emit('CURVE_HANDOFF', {'mode': mode, 'audit': C.audit(bundle)})
        assert raw['dq'] == raw['patch-adaptive']
        emit('SOURCE_EXTENSIONAL_EQUALITY', raw)
        # This extra genuine cell is solely for partial-curve consumption, not another positive-state demo.
        cls.partial_pair = H.run_whole_pair(cls.bounds['patch-adaptive'], architecture='D_patch',
                                            tier=Tier.L3_ORACLE, law_name='LocalOracleRestore')
        emit('PARTIAL_ORIGINAL_PAIR', O.pair_audit(cls.partial_pair, cls.sources['patch-adaptive']))
        cls.partial_bundle = C.prepare_curve(cls.bounds['patch-adaptive'], cls.partial_pair, episodes=cls.stream,
                                             evaluation_indices=tuple(CONTRACT['evaluation_indices']))
        emit('PARTIAL_HANDOFF', C.audit(cls.partial_bundle))

    def setUp(self):
        global CASE
        CASE = self._testMethodName

    def test_01_actual_multi_epoch_curves_and_TD(self):
        for mode in self.bundles:
            bundle = self.bundles[mode]; before = C.audit(bundle)
            handles = C.run_pair_curve(bundle); self.handles[mode] = handles
            for handle in handles:
                record = C.curve_audit(handle)
                emit('COMPLETED_ROLE_CURVE', {'mode': mode, 'audit': record})
                self.assertEqual([c['epoch'] for c in record['checkpoints']], [0, 1, 2, 3])
                self.assertEqual([r['epoch'] for r in record['training']], [0, 1, 2])
                for r in record['training']:
                    expected, details = independent_td(r, self.ref)
                    emit('INDEPENDENT_TD', {'mode': mode, 'role': record['role'], 'epoch': r['epoch'],
                                             'edits': expected, 'details': details})
                    self.assertEqual(r['numeric_edits'], A.wire(expected))
                    self.assertEqual(r['after']['completed_episodes'], r['epoch']+1)
                    self.assertEqual(r['before']['current']['P'], r['after']['current']['P'])
                    self.assertEqual(r['before']['current']['X'], r['after']['current']['X'])
                    self.assertEqual(r['before']['immediate'], r['after']['immediate'])
                for c in record['checkpoints']:
                    total = 0.0
                    for trace in c['traces']:
                        total += float(sum(float.fromhex(s['reward']['binary64_hex']) for s in trace['steps']))
                    self.assertEqual((total/len(c['traces'])).hex(), c['mean_hex'])
            after = C.audit(bundle)
            self.assertEqual(before['origin'], after['origin'])
            self.assertTrue(after['completed'])
            for actor in after['ordered_composites']:
                self.assertEqual(actor['completed_episodes'], 3)
                self.assertEqual(actor['attempted_epochs'], [0, 1, 2])
            # Paired variates agree by coordinate even when commands/path lengths differ.
            r0, r1 = (C.curve_audit(h)['training'] for h in handles)
            for a, b in zip(r0, r1):
                ca = {tuple(x[:3]): x[3] for x in a['coordinates']}
                cb = {tuple(x[:3]): x[3] for x in b['coordinates']}
                self.assertTrue(all(ca[k] == cb[k] for k in ca.keys() & cb.keys()))
                self.assertEqual(a['episode'], b['episode'])
            emit('COMPLETE_MULTI_EPOCH_PAIR', {'mode': mode, 'audit': after})

    def test_02_external_constructor_and_forged_feature_gate(self):
        for mode, handles in self.handles.items():
            for handle in handles:
                view = E.build(handle); p = E.read(view)
                exported = dict(p); exported['fields'] = dict(p['fields'])
                emit('EXTERNAL_CURVE_VIEW', {'mode': mode, 'projection': exported})
                self.assertEqual(set(p), {'fields', 'episodes', 'values', 'pre_level', 't_max'})
                self.assertEqual(tuple(p['fields']), E.FIELDS)
                self.assertEqual(p['episodes'], (0, 1, 2, 3))
                self.assertEqual(p['pre_level'], CONTRACT['shared_v_pre'])
                with self.assertRaises(TypeError):
                    p['values'] = (1.0,)*4
                with self.assertRaises(A.ProtocolError):
                    E.build({'Gamma_P_star': ['Decision_0'], 'values': (1.0,)*4})
                original = E._VIEWS[view]
                forged = dict(p); forged_fields = dict(p['fields'])
                forged_fields['future_rewards'] = (True,)  # A derived truth-like feature inside an otherwise issued view.
                forged['fields'] = forged_fields
                counts = dict(COUNTS)
                try:
                    E._VIEWS[view] = (handle, forged)
                    with self.assertRaisesRegex(A.ProtocolError, 'differs from its own observed records'):
                        E.read(view)
                finally:
                    E._VIEWS[view] = original
                self.assertEqual(dict(COUNTS), counts)
                self.assertEqual(E.read(view), p)
                emit('EXTERNAL_FORGED_FEATURE_REJECTED', {'projection_before': exported,
                                                         'forged_rewards': forged_fields['future_rewards'],
                                                         'native_counts_unchanged': True})
        tree = ast.parse((HERE/'external.py').read_text(encoding='utf-8'))
        bad = {'Gamma_T_star', 'Gamma_P_star', 'Z_fire', 'J_L', 'R_mech', 'R_rescue', 'pi_credit',
               'world_id', 'block_id', 'ledger', 'source_label', 'role'}
        reads = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
        reads |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Load)}
        self.assertFalse(reads & bad)
        emit('EXTERNAL_AST_GATE', {'forbidden_loads': sorted(reads & bad)})

    def test_03_real_partial_curve_and_no_retry(self):
        target = C._BUNDLES[self.partial_bundle].actors[0]
        original = L.CoordinateLearner.evaluate
        seen = []
        def planned_fault(actor, scene):
            if actor is target:
                seen.append(scene.key)
                if len(seen) == 2:
                    raise RuntimeError('planned new-connector second-scene interruption')
            return original(actor, scene)
        try:
            L.CoordinateLearner.evaluate = planned_fault
            try:
                C.run_pair_curve(self.partial_bundle)
                self.fail('partial curve unexpectedly completed')
            except RuntimeError as exc:
                self.assertIn('planned new-connector', str(exc))
                emit('PARTIAL_CURVE_FAILURE', {'traceback': traceback.format_exc(),
                                              'full_partial_audit': C.audit(self.partial_bundle),
                                              'completed_scenes_before_fault': seen[:-1]})
        finally:
            L.CoordinateLearner.evaluate = original
        self.assertIs(L.CoordinateLearner.evaluate, original)
        self.assertNotIn(self.partial_bundle, C._COMPLETED)
        counts = dict(COUNTS)
        with self.assertRaisesRegex(A.ProtocolError, 'already attempted'):
            C.run_pair_curve(self.partial_bundle)
        self.assertEqual(dict(COUNTS), counts)
        emit('PARTIAL_ONCE_AND_RESTORE', {'counts_before': counts, 'counts_after': dict(COUNTS),
                                         'audit': C.audit(self.partial_bundle)})

    def test_04_shared_plan_and_protected_state_guard(self):
        bundle = self.bundles['patch-adaptive']; data = C._BUNDLES[bundle]
        actor = data.actors[1]; plan = actor.plan
        counts = dict(COUNTS)
        try:
            actor.plan = L.EngineeringPlan(plan.episodes, plan.evaluation_sample, plan.v_pre,
                                           plan.parameters, plan.lock_digest)
            with self.assertRaisesRegex(A.ProtocolError, 'one shared plan'):
                C.audit(bundle)
        finally:
            actor.plan = plan
        original = actor._current
        try:
            actor._current = actor._immediate
            with self.assertRaisesRegex(A.ProtocolError, 'aliases protected immediate'):
                C.audit(bundle)
        finally:
            actor._current = original
        with self.assertRaises(A.ProtocolError):
            actor.train_episode(plan.episode(0))
        with self.assertRaisesRegex(A.ProtocolError, 'not issued'):
            L.FutureExecutionPermit()
        self.assertEqual(dict(COUNTS), counts)
        for b in self.bundles.values():
            with self.assertRaisesRegex(A.ProtocolError, 'already attempted'):
                C.run_pair_curve(b)
        self.assertEqual(dict(COUNTS), counts)
        emit('SHARED_PLAN_I_ONCE_GATES', {'counts_before': counts, 'counts_after': dict(COUNTS),
                                         'full_patch_pair': C.audit(bundle), 'formal_activation_closed': True})


if __name__ == '__main__':
    sys.setprofile(profile)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ConnectorTests))
    sys.setprofile(None)
    inputs = json.loads((HERE/'evidence/claim.json').read_bytes())['input_binding_before']
    inventory = {}
    for module in tuple(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename:
            path = Path(filename).resolve()
            if path.is_relative_to(ROOT) and path.suffix == '.py':
                inventory[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    inventory_ok = all(n in inputs and inputs[n]['sha256'] == pin for n, pin in inventory.items())
    emit('ACTUAL_LOADED_SOURCE_INVENTORY', inventory)
    emit('RESULT', {'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
                    'skips': len(result.skipped), 'counts': dict(COUNTS), 'seconds': time.monotonic()-STARTED,
                    'loaded_source_inventory_bound': inventory_ok, 'keyed_protocol_executed': False,
                    'scientific_qualification': False, 'collection_authorized': False})
    raise SystemExit(0 if result.wasSuccessful() and inventory_ok else 1)
