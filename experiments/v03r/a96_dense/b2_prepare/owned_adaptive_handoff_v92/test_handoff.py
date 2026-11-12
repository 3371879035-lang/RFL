"""New owned-source integration only; no old fixture/checker/launcher execution."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import time
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path[:0] = [str(HERE), str(HERE.parent/'adaptive_training_v90'), str(HERE.parent), str(ROOT/'src')]
import handoff as H
import adaptive_training as A
import oracle_mainline_v75 as O
from rfl_rebuild.env import kernel as K
from rfl_rebuild.b2 import training as T
from rfl_rebuild.b2.unaffected import EvaluationScene
from rfl_rebuild.b1.tier import Tier
from rfl_rebuild.learner.reference import QReferenceView
from rfl_rebuild.learner.store import LearnerPersistentState, Edit, DecisionAddress, QAddress, DECISION, PROCESS, CONTROLLER, Q

C = json.loads((HERE/'contract.json').read_bytes())
COUNTS = Counter()
STARTED = time.monotonic()
CASE = 'setup'


def emit(tag, payload):
    print(json.dumps({'tag': tag, 'case': CASE, 'payload': A.wire(payload)},
                     sort_keys=True, separators=(',', ':'), ensure_ascii=True), flush=True)


def profile(frame, event, arg):
    path = frame.f_code.co_filename.replace('\\', '/')
    name = frame.f_code.co_name
    kernel = path.endswith('rfl_rebuild/env/kernel.py')
    store = path.endswith('rfl_rebuild/learner/store.py')
    b1 = path.endswith('rfl_rebuild/b1/runner.py') and name in ('run_dq_law', 'run_patch_law')
    if event == 'call':
        counted = name if kernel and name in ('step', 'rollout') else 'transaction' if store and name == 'apply_transaction' else 'B1' if b1 else None
        if counted:
            COUNTS[counted] += 1
            if COUNTS[counted] > C['budget'][counted]:
                raise RuntimeError('prospective native budget exceeded: '+counted)
        if store and name == 'apply_transaction':
            emit('TX_CALL', {'before': A.stores(frame.f_locals['self']), 'edits': frame.f_locals['edits']})
        forbidden = ((path.endswith('rfl_rebuild/b2/training.py') and name in ('derive', 'key', 'mix', 'train_curve', 'pre_level')) or
                     (kernel and name == 'sample') or (path.endswith('rfl_rebuild/solve/dp.py') and name == 'solve_reference') or
                     (path.endswith('random.py') and name in ('__init__', 'random', 'randrange')) or
                     (frame.f_code.co_qualname in ('FutureTrainingProtocol.__init__', 'Curve.__init__')) or
                     (path.endswith('readiness.py') and name == 'build_reference'))
        if forbidden:
            COUNTS['forbidden'] += 1
            raise RuntimeError('forbidden production/key/DP entry: '+name)
        if time.monotonic()-STARTED > C['budget']['seconds']:
            raise RuntimeError('wall budget exceeded')
    elif event == 'return':
        if kernel and name == 'step' and type(arg) is K.StepResult:
            emit('RAW_STEP', {'pre_state': frame.f_locals['state'], 'pre_control': frame.f_locals['control'],
                              'a_cmd': frame.f_locals['a_cmd'], 'result': arg})
        elif kernel and name == 'rollout':
            emit('RAW_ROLLOUT' if type(arg) is K.RolloutTrace else 'INCOMPLETE_ROLLOUT', arg)
        elif store and name == 'apply_transaction':
            emit('TX_RETURN', {'after': A.stores(frame.f_locals['self'])})
        elif b1 and type(arg) is O.base.native_b1.B1Result:
            emit('NATIVE_B1_RETURN', {'law': frame.f_locals['law'].name,
                 'full_post': A.stores(arg.post_state), 'ledger_canonical': arg.ledger.canonical(),
                 'receipts': arg.ledger.receipts})
        elif path.endswith('/handoff.py') and name in ('train_episode', 'evaluate') and isinstance(arg, dict):
            emit('OWNED_TRAIN' if name == 'train_episode' else 'OWNED_EVAL', arg)


def reference():
    data = (ROOT/C['reference_input']['path']).read_bytes()
    assert hashlib.sha256(data).hexdigest() == C['reference_input']['sha256']
    rows = {}
    for line in data.decode('utf-8').splitlines():
        if line.startswith('DECISION_CONTEXT='):
            item = json.loads(line.split('=', 1)[1])
            x, y, t, k, phi, z, m = item['context']
            rows[K.State(x, y, t, k, phi), z, m] = {a: float.fromhex(v) for a, v in item['q_row_hex']}
    result = QReferenceView(rows, name='unchanged-full-stored-reference-v92')
    assert result.digest() == C['reference_input']['q_digest']
    assert K.START == (0, 2)
    emit('REFERENCE', {'rows': len(rows), 'digest': result.digest(), 'new_DP_calls': 0})
    return result


def new_pre(ref, mode):
    addresses = [DecisionAddress(K.State(*K.START, t, 0, 2), 1, m)
                 for t in range(K.HORIZON) for m in (0, 1)]
    sentinel = DecisionAddress(K.State(*K.START, 0, 1, 2), 1, 0)
    state = LearnerPersistentState()
    edits = [Edit(PROCESS, 0, 1), Edit(PROCESS, 3, 2),
             Edit(CONTROLLER, K.ControllerSite(sentinel.state, K.WAIT), K.RIGHT)]
    for address in (*addresses, sentinel):
        assert K.WAIT in ref.row(address.state, address.z, address.m)
        edits.append(Edit(DECISION, address, K.WAIT) if mode == 'patch-adaptive' else
                     Edit(Q, QAddress(address.state, address.z, address.m, K.WAIT),
                          max(ref.row(address.state, address.z, address.m).values())+1.0))
    emit('SOURCE_INSTALL_PLANNED', {'mode': mode, 'addresses': addresses, 'sentinel': sentinel, 'edits': edits})
    state.apply_transaction(tuple(edits), q_reference=ref)
    emit('NEW_FULL_PRE', {'mode': mode, 'stores': A.stores(state)})
    return state, sentinel


class HandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global CASE
        cls.ref = reference()
        healthy = json.loads((ROOT/C['healthy_reference']).read_bytes())
        cls.bound, cls.native, cls.bundles, cls.sources, cls.initial = {}, {}, {}, {}, {}
        cls.scene = EvaluationScene(*C['new_scene'])
        for mode, architecture, law in (('dq', 'D_Q', 'FactualReturnWrite'),
                                        ('patch-adaptive', 'D_patch', 'DeleteFactualPatch')):
            CASE = 'new-owned-source-'+mode
            pre, sentinel = new_pre(cls.ref, mode)
            source = O.capture_source(pre, scene=cls.scene, regime='P', q_reference=cls.ref,
                                      healthy_reference=healthy, counterfactual=False)
            emit('ORIGINAL_SOURCE', {'mode': mode, 'audit': O.source_audit(source)})
            bound = H.bind_source(source, mode=mode)
            emit('BOUND_BEFORE_ARMS', H.source_audit(bound))
            pair = H.run_whole_pair(bound, architecture=architecture, tier=Tier.L0_FACTUAL, law_name=law)
            emit('ORIGINAL_PAIR', {'mode': mode, 'audit': O.pair_audit(pair, source)})
            bundle = H.prepare_training(bound, pair)
            emit('HANDOFF', H.pair_audit(bundle))
            cls.sources[mode], cls.bound[mode], cls.native[mode], cls.bundles[mode] = source, bound, pair, bundle
            cls.initial[mode] = H.pair_audit(bundle)

    def setUp(self):
        global CASE
        CASE = self._testMethodName

    def test_01_complete_origin_full_owners_roles_and_residual(self):
        for mode, bundle in self.bundles.items():
            audit = H.pair_audit(bundle)
            original = audit['origin']['original_declaration']['original_pair']['payload']['original_v74_pair']['payload']
            self.assertEqual(original['native_B1_arm_calls'], 2)
            self.assertGreater(len(original['cell_units']), 1)
            self.assertIn('ProcessCommit', original['residual_units_preserved'])
            for arm in original['all_owner_receipts']:
                self.assertEqual(len(arm['ordered_receipts']), len(original['cell_units']))
            native = O._checked_pair(self.native[mode], self.sources[mode])[3]
            for i, actor in enumerate(audit['ordered_current_composites']):
                self.assertEqual(actor['mode'], mode)
                self.assertEqual(actor['role'], H.ROLES[i])
                self.assertEqual(actor['immediate'], A.stores(native.clones[i]))
                self.assertEqual(actor['current'], actor['immediate'])
                self.assertEqual(actor['learning_values'], None if mode == 'dq' else {'D': [], 'P': [], 'X': [], 'Q': []})
            self.assertIsNot(H.role(bundle, role='reference'), H.role(bundle, role='treatment'))
            self.assertEqual(audit, self.initial[mode])
        dq = O._checked_source(self.sources['dq'])[1]
        patch = O._checked_source(self.sources['patch-adaptive'])[1]
        self.assertEqual(A.wire(dq.trace), A.wire(patch.trace))
        emit('WHOLE_SOURCE_EXTENT', {'dq_units': self.initial['dq']['origin']['original_declaration'],
                                     'patch_units': self.initial['patch-adaptive']['origin']['original_declaration']})

    def test_02_unissued_foreign_rebinding_and_duplicate_refusals(self):
        before = dict(COUNTS)
        checks = [lambda: H.bind_source(A.stores(LearnerPersistentState()), mode='dq'),
                  lambda: H.bind_source(object.__new__(O.OwnedSource), mode='dq'),
                  lambda: H.bind_source(self.sources['patch-adaptive'], mode='dq'),
                  lambda: H.bind_source(self.sources['dq'], mode='dq'),
                  lambda: H.prepare_training(self.bound['dq'], self.native['patch-adaptive']),
                  lambda: H.prepare_training(self.bound['dq'], object.__new__(O.OwnedPair)),
                  lambda: H.prepare_training(self.bound['dq'], self.native['dq']),
                  lambda: H.role(object.__new__(H.OwnedTrainingPair), role='reference'),
                  lambda: H.evaluate(object.__new__(H.OwnedTrainingRole), kappa=0, tape=self.scene.tape, proposal=0),
                  lambda: H.run_whole_pair(self.bound['dq'], architecture='D_patch', tier=Tier.L0_FACTUAL, law_name='DeleteFactualPatch'),
                  lambda: H.run_whole_pair(self.bound['dq'], architecture='D_Q', tier=Tier.L0_FACTUAL, law_name='FactualReturnWrite')]
        errors = []
        for check in checks:
            try:
                check()
            except A.ProtocolError as error:
                errors.append(str(error))
            else:
                self.fail('unissued/foreign/duplicate request accepted')
        self.assertEqual(dict(COUNTS), before)
        emit('OWNERSHIP_REFUSALS', {'errors': errors, 'counts_before': before, 'counts_after': dict(COUNTS)})

    def test_03_actual_role_learning_preserves_full_native_I_and_shared_inputs(self):
        for mode, bundle in self.bundles.items():
            for role_name in H.ROLES:
                episode = A.ScriptedEpisode('v92-shared-single-episode', 0, 0, self.scene.tape,
                                           (0, 0)+(T.M64,)*(K.HORIZON-2),
                                           ((0,), (3,))+((0,),)*(K.HORIZON-2))
                result = H.train_episode(H.role(bundle, role=role_name), episode)
                self.assertEqual(result['role'], role_name)
                self.assertTrue(all(value is None for value in result['training']['trace']['mask'].values()))
                self.assertEqual(result['training']['trace']['interventions']['members'], [])
                self.assertEqual(result['training']['trace']['option_in_force'], 1)
                after = H.pair_audit(bundle)
                initial = self.initial[mode]
                self.assertEqual(after['origin'], initial['origin'])
                for p, old in zip(after['ordered_current_composites'], initial['ordered_current_composites']):
                    self.assertEqual(p['immediate'], old['immediate'])
                    self.assertEqual(p['current']['P'], old['immediate']['P'])
                    self.assertEqual(p['current']['X'], old['immediate']['X'])
            final = H.pair_audit(bundle)
            self.assertEqual([p['completed_episodes'] for p in final['ordered_current_composites']], [1, 1])
            self.assertEqual(final['origin']['protected_immediate_posts'], self.initial[mode]['origin']['protected_immediate_posts'])

    def test_04_full_L_fingerprint_role_alias_and_export_isolation(self):
        bundle = self.bundles['patch-adaptive']
        before = H.pair_audit(bundle)
        copy = H.pair_audit(bundle)
        copy['ordered_current_composites'][0]['learning_values']['Q'].clear()
        self.assertEqual(H.pair_audit(bundle), before)
        record = H._PAIRS[bundle]
        actor = record.actors[0]
        foreign = record.actors[1]._values
        values = actor._values
        counts = dict(COUNTS)
        try:
            actor._values = foreign
            with self.assertRaises(A.ProtocolError): H.pair_audit(bundle)
        finally:
            actor._values = values
        saved_role = actor.role
        try:
            actor.role = 'treatment'
            with self.assertRaises(A.ProtocolError): H.pair_audit(bundle)
        finally:
            actor.role = saved_role
        self.assertTrue(values.q_overrides)
        # Test complete L commitment without a transaction/native rerun.
        export = deepcopy(before['ordered_current_composites'][0])
        export['learning_values']['Q'][0]['value']['binary64_hex'] = '0x1.0p+10'
        self.assertNotEqual(A.digest(export), before['ordered_full_composite_sha256'][0])
        self.assertEqual(dict(COUNTS), counts)
        self.assertEqual(H.pair_audit(bundle), before)
        emit('ROLE_AND_FULL_L_GATES', {'counts_before': counts, 'counts_after': dict(COUNTS),
                                      'complete_composites': before, 'runtime_alias_restored': True})

    def test_05_owned_readonly_evaluation_and_training_once(self):
        for mode, bundle in self.bundles.items():
            before = H.pair_audit(bundle)
            for role_name in H.ROLES:
                handle = H.role(bundle, role=role_name)
                result = H.evaluate(handle, kappa=0, tape=self.scene.tape, proposal=0)
                self.assertTrue(result['evaluation']['readonly'])
                self.assertEqual(result['evaluation']['draws'], [])
                episode = A.ScriptedEpisode('v92-shared-single-episode', 0, 0, self.scene.tape,
                                           (0, 0)+(T.M64,)*(K.HORIZON-2),
                                           ((0,), (3,))+((0,),)*(K.HORIZON-2))
                counts = dict(COUNTS)
                with self.assertRaises(A.ProtocolError): H.train_episode(handle, episode)
                self.assertEqual(dict(COUNTS), counts)
            self.assertEqual(H.pair_audit(bundle), before)
            emit('FINAL_OWNED_PAIR', H.pair_audit(bundle))


if __name__ == '__main__':
    sys.setprofile(profile)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(HandoffTests))
    sys.setprofile(None)
    inputs = json.loads((HERE/'evidence/claim.json').read_bytes())['input_binding_before']
    inventory = {}
    for module in tuple(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename:
            path = Path(filename).resolve()
            if path.is_relative_to(ROOT) and path.suffix == '.py':
                name = path.relative_to(ROOT).as_posix()
                inventory[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    emit('ACTUAL_LOADED_SOURCE_INVENTORY', inventory)
    inventory_ok = all(name in inputs and inputs[name]['sha256'] == pin for name, pin in inventory.items())
    emit('RESULT', {'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
                    'skips': len(result.skipped), 'counts': dict(COUNTS), 'seconds': time.monotonic()-STARTED,
                    'actual_loaded_inventory_bound': inventory_ok,
                    'scientific_qualification': False, 'formal_training_or_collection': False})
    raise SystemExit(0 if result.wasSuccessful() and inventory_ok else 1)
