"""One new retained-active-X owned L branch. Never imports any old test/checker."""
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
sys.path[:0] = [str(HERE.parent/'owned_adaptive_handoff_v92'), str(HERE.parent/'adaptive_training_v90'),
               str(HERE.parent), str(ROOT/'src')]
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
CASE = 'new-owned-active-X-source'


def emit(tag, data):
    print(json.dumps({'tag': tag, 'case': CASE, 'payload': A.wire(data)},
                     sort_keys=True, separators=(',', ':'), ensure_ascii=True), flush=True)


def profile(frame, event, arg):
    path = frame.f_code.co_filename.replace('\\', '/')
    name = frame.f_code.co_name
    kernel = path.endswith('rfl_rebuild/env/kernel.py')
    store = path.endswith('rfl_rebuild/learner/store.py')
    b1 = path.endswith('rfl_rebuild/b1/runner.py') and name == 'run_patch_law'
    if event == 'call':
        counted = name if kernel and name in ('step', 'rollout') else 'transaction' if store and name == 'apply_transaction' else 'B1' if b1 else None
        if counted:
            COUNTS[counted] += 1
            if COUNTS[counted] > C['budget'][counted]: raise RuntimeError('finite native budget: '+counted)
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
        if time.monotonic()-STARTED > C['budget']['seconds']: raise RuntimeError('finite wall budget')
    elif event == 'return':
        if kernel and name == 'step' and type(arg) is K.StepResult:
            emit('RAW_STEP', {'pre_state': frame.f_locals['state'], 'pre_control': frame.f_locals['control'],
                              'a_cmd': frame.f_locals['a_cmd'], 'result': arg})
        elif kernel and name == 'rollout':
            emit('RAW_ROLLOUT' if type(arg) is K.RolloutTrace else 'INCOMPLETE_ROLLOUT', arg)
        elif store and name == 'apply_transaction': emit('TX_RETURN', {'after': A.stores(frame.f_locals['self'])})
        elif b1 and type(arg) is O.base.native_b1.B1Result:
            emit('NATIVE_B1_RETURN', {'law': frame.f_locals['law'].name, 'full_post': A.stores(arg.post_state),
                                     'ledger_canonical': arg.ledger.canonical(), 'receipts': arg.ledger.receipts})
        elif path.endswith('/adaptive_training.py') and name == 'train_episode' and isinstance(arg, dict):
            emit('CORE_TRAIN_RECEIPT', arg)
        elif path.endswith('/handoff.py') and name in ('train_episode', 'evaluate') and isinstance(arg, dict):
            emit('OWNED_TRAIN' if name == 'train_episode' else 'OWNED_EVAL', arg)


def reference():
    raw = (ROOT/C['reference_input']['path']).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == C['reference_input']['sha256']
    rows = {}
    for line in raw.decode('utf-8').splitlines():
        if line.startswith('DECISION_CONTEXT='):
            data = json.loads(line.split('=', 1)[1]); x, y, t, k, phi, z, m = data['context']
            rows[K.State(x, y, t, k, phi), z, m] = {a: float.fromhex(v) for a, v in data['q_row_hex']}
    ref = QReferenceView(rows, name='unchanged-full-reference-for-new-owned-X-response')
    assert ref.digest() == C['reference_input']['q_digest'] and K.START == (0, 2)
    emit('REFERENCE', {'digest': ref.digest(), 'rows': len(rows), 'new_DP': 0})
    return ref


def new_pre(ref):
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
        legality.append({'site': site, 'target': target, 'full_serving_contexts': service})
    edits = [Edit(PROCESS, 0, 1), Edit(PROCESS, 3, 2)]
    edits += [Edit(CONTROLLER, site, target) for site, target in sites]
    for address in contexts:
        assert K.WAIT in ref.row(address.state, address.z, address.m)
        edits.append(Edit(DECISION, address, K.WAIT))
    assert len(edits) == 32 and len(contexts) == 27
    emit('SOURCE_INSTALL_PLANNED', {'edits': edits, 'all_X_domain_legality': legality})
    pre = LearnerPersistentState()
    pre.apply_transaction(tuple(edits))
    emit('NEW_FULL_PRE', A.stores(pre))
    return pre, sentinel


def independent_td(receipt, ref):
    def address(d):
        s = d['state']; return QAddress(K.State(*(s[k] for k in ('x', 'y', 't', 'kappa', 'phi'))), d['z'], d['m'], d['a'])
    work = {address(v['address']): float.fromhex(v['value']['binary64_hex'])
            for v in receipt['before']['learning_values']['Q']}
    state = K.State(*K.START, 0, 0, 2)
    z, m = receipt['trace']['option_in_force'], 0
    value = lambda q: work.get(q, ref.value(q))
    order, details = [], []
    for item in receipt['trace']['steps']:
        q = QAddress(state, z, m, item['a_cmd']); current = value(q)
        post = item['state']; ns = K.State(*(post[k] for k in ('x', 'y', 't', 'kappa', 'phi')))
        ctrl = K.ControlState(item['control']['z'], item['control']['m'])
        target = float.fromhex(item['reward']['binary64_hex'])
        if not item['terminal']:
            target += max(value(QAddress(ns, ctrl.z, ctrl.m, a)) for a in K.option_actions(ctrl.z, ctrl, ns))
        updated = current+0.5*(target-current)
        details.append({'address': q, 'current_hex': current.hex(), 'target_hex': target.hex(),
                        'residual_hex': (target-current).hex(), 'updated_hex': updated.hex()})
        work[q] = updated
        if q not in order: order.append(q)
        state, z, m = ns, ctrl.z, ctrl.m
    edits = tuple(Edit(Q, q, float(work[q])) for q in order)
    return edits, details


class OwnedResponseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ref = reference(); cls.scene = EvaluationScene(*C['new_scene'])
        pre, cls.sentinel = new_pre(cls.ref)
        cls.source = O.capture_source(pre, scene=cls.scene, regime='P', q_reference=cls.ref,
                                      healthy_reference=json.loads((ROOT/C['healthy_reference']).read_bytes()), counterfactual=False)
        emit('ORIGINAL_SOURCE', O.source_audit(cls.source))
        cls.bound = H.bind_source(cls.source, mode='patch-adaptive')
        emit('BOUND_BEFORE_ARMS', H.source_audit(cls.bound))
        cls.native = H.run_whole_pair(cls.bound, architecture='D_patch', tier=Tier.L0_FACTUAL, law_name='DeleteFactualPatch')
        emit('ORIGINAL_PAIR', O.pair_audit(cls.native, cls.source))
        cls.bundle = H.prepare_training(cls.bound, cls.native)
        cls.initial = H.pair_audit(cls.bundle)
        emit('HANDOFF', cls.initial)
        cls.receipts = {}

    def setUp(self):
        global CASE
        CASE = self._testMethodName

    def test_01_real_owned_TD_response_and_full_preservation(self):
        original = self.initial['origin']['original_declaration']['original_pair']['payload']['original_v74_pair']['payload']
        self.assertGreater(len(original['cell_units']), 1)
        self.assertEqual(set(original['residual_units_preserved']),
                         {'ProcessCommit', 'ControllerSite_0_2_0_4', 'ControllerSite_1_2_1_4'})
        for role in H.ROLES:
            episode = A.ScriptedEpisode('v93-one-shared-active-X-episode', 0, 0, self.scene.tape,
                                        (T.M64,)*K.HORIZON, ((0,),)*K.HORIZON)
            result = H.train_episode(H.role(self.bundle, role=role), episode)
            self.receipts[role] = result
            r = result['training']; expected, details = independent_td(r, self.ref)
            emit('INDEPENDENT_TD', {'origin_sha256': result['origin_sha256'], 'role': role,
                                     'expected_edits': expected, 'details': details})
            self.assertEqual(r['numeric_edits'], A.wire(expected))
            self.assertTrue(all(not d['explore'] for d in r['draws']))
            after = result['complete_pair_after']
            self.assertEqual(after['origin'], self.initial['origin'])
            for p, old in zip(after['ordered_current_composites'], self.initial['ordered_current_composites']):
                self.assertEqual(p['immediate'], old['immediate'])
                self.assertEqual(p['current']['P'], old['immediate']['P'])
                self.assertEqual(p['current']['X'], old['immediate']['X'])
                self.assertEqual(next(x['value'] for x in p['current']['D'] if x['address'] == A.wire(self.sentinel)), K.WAIT)
            if role == 'reference':
                self.assertTrue(r['after']['learning_values']['Q'])
                self.assertEqual(r['trace']['steps'][0]['a_cmd'], K.WAIT)
                self.assertEqual(r['trace']['steps'][0]['u'], K.RIGHT)
                self.assertEqual(details[0]['target_hex'], '0x1.c28f5c28f5c28p-1')
                self.assertEqual(details[0]['residual_hex'], '0x1.47ae147ae1480p-6')
            # Treatment is assessed from its own exact TD; zero is not forced nonzero.
        emit('ACTUAL_OWNED_RESPONSE', H.pair_audit(self.bundle))

    def test_02_nonempty_L_commitment_export_and_role_alias(self):
        before = H.pair_audit(self.bundle)
        actual = before['ordered_current_composites'][0]
        self.assertTrue(actual['learning_values']['Q'])
        for i, value in enumerate(before['ordered_current_composites']):
            self.assertEqual(A.digest(value), before['ordered_full_composite_sha256'][i])
        altered = deepcopy(actual)
        old_hex = altered['learning_values']['Q'][0]['value']['binary64_hex']
        altered['learning_values']['Q'][0]['value']['binary64_hex'] = (float.fromhex(old_hex)+1.0).hex()
        changed_digest = A.digest(altered)
        self.assertNotEqual(changed_digest, before['ordered_full_composite_sha256'][0])
        exported = H.pair_audit(self.bundle)
        exported['ordered_current_composites'][0]['learning_values']['Q'].clear()
        self.assertEqual(H.pair_audit(self.bundle), before)
        record = H._PAIRS[self.bundle]; actor = record.actors[0]; original = actor._values
        counts = dict(COUNTS)
        try:
            actor._values = record.actors[1]._values
            with self.assertRaises(A.ProtocolError): H.pair_audit(self.bundle)
        finally:
            actor._values = original
        self.assertEqual(dict(COUNTS), counts)
        self.assertEqual(H.pair_audit(self.bundle), before)
        emit('NONEMPTY_L_COMMITMENT_GATE', {'full_before': before, 'original_digest': before['ordered_full_composite_sha256'][0],
                                           'altered_copy_digest': changed_digest, 'altered_copy': altered,
                                           'counts_before': counts, 'counts_after': dict(COUNTS), 'runtime_alias_restored': True})

    def test_03_owned_readonly_eval_of_learned_composite(self):
        before = H.pair_audit(self.bundle)
        for role in H.ROLES:
            result = H.evaluate(H.role(self.bundle, role=role), kappa=0, tape=self.scene.tape, proposal=0)
            self.assertEqual(result['evaluation']['before'], result['evaluation']['after'])
            self.assertEqual(result['evaluation']['draws'], [])
            self.assertTrue(result['evaluation']['readonly'])
        self.assertEqual(H.pair_audit(self.bundle), before)
        emit('FINAL_OWNED_PAIR', before)


if __name__ == '__main__':
    sys.setprofile(profile)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(OwnedResponseTests))
    sys.setprofile(None)
    inputs = json.loads((HERE/'evidence/claim.json').read_bytes())['input_binding_before']
    inventory = {}
    for module in tuple(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename:
            path = Path(filename).resolve()
            if path.is_relative_to(ROOT) and path.suffix == '.py':
                inventory[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    emit('ACTUAL_LOADED_SOURCE_INVENTORY', inventory)
    inventory_ok = all(name in inputs and inputs[name]['sha256'] == pin for name, pin in inventory.items())
    emit('RESULT', {'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
                    'skips': len(result.skipped), 'counts': dict(COUNTS), 'seconds': time.monotonic()-STARTED,
                    'actual_loaded_inventory_bound': inventory_ok, 'scientific_qualification': False,
                    'formal_training_or_collection': False})
    raise SystemExit(0 if result.wasSuccessful() and inventory_ok else 1)
