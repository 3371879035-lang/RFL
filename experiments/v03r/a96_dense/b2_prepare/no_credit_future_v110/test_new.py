"""First actual genuine T empty-credit ordinary future, without fake therapy.

All source/trace/truth/state/receipt records are written before assertions.
The old fixture/checker scripts are not imported or executed.  Unchanged
production functions and separately preserved addon functions are used on
these two fresh independently constructed owned sources.
"""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import traceback
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path[:0] = [str(HERE.parent / 'owned_adaptive_handoff_v92'),
               str(HERE.parent / 'adaptive_training_v90'), str(HERE.parent), str(ROOT / 'src')]
import adaptive_training as A
import handoff as H
import oracle_mainline_v75 as O
from rfl_rebuild.b1.tier import Tier
from rfl_rebuild.b2 import training as T
from rfl_rebuild.b2.unaffected import EvaluationScene
from rfl_rebuild.env import kernel as K
from rfl_rebuild.learner.reference import QReferenceView
from rfl_rebuild.learner.store import LearnerPersistentState

CONTRACT = json.loads((HERE / 'contract.json').read_bytes())
OUT = HERE / 'evidence'
COUNTS = Counter()
START = time.monotonic()
SCOPE = {'mode': None, 'stage': 'setup', 'role': None, 'epoch': None}
BANK = None
PENDING = []
L = B = N = None


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


class Capture:
    def __init__(self):
        self.stream = (OUT / 'raw.jsonl').open('xb')
        self.records = self.raw_bytes = 0
        self.digest = hashlib.sha256()

    def emit(self, tag, payload, *, force=False):
        record = dict(seq=self.records, tag=tag, payload=A.wire(payload), **SCOPE)
        raw = (canonical(record) + '\n').encode('ascii')
        self.stream.write(raw)
        self.stream.flush()
        self.digest.update(raw)
        self.records += 1
        self.raw_bytes += len(raw)
        if not force:
            if self.raw_bytes > CONTRACT['budget']['capture_bytes']:
                raise RuntimeError('prospective complete capture byte budget exhausted')
            if time.monotonic() - START > CONTRACT['budget']['seconds']:
                raise RuntimeError('prospective finite wall-time budget exhausted')

    def close(self):
        self.stream.close()


LOG = None


def meta(path):
    raw = path.read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def loaded_sources():
    result = {}
    for module in tuple(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if not name:
            continue
        path = Path(name).resolve()
        if path.suffix == '.py' and path.is_relative_to(ROOT) and path.exists():
            result[path.relative_to(ROOT).as_posix()] = meta(path)
    return dict(sorted(result.items()))


def handler(frame, event, arg):
    global SCOPE, BANK, PENDING
    path, name, qual = (frame.f_code.co_filename.replace('\\', '/'),
                        frame.f_code.co_name, frame.f_code.co_qualname)
    kernel = path.endswith('rfl_rebuild/env/kernel.py')
    store = path.endswith('rfl_rebuild/learner/store.py')
    native = path.endswith('rfl_rebuild/b1/runner.py') and name in ('run_patch_law', 'run_dq_law')
    learn = path.endswith('complete_curve_source_gates_v105/variants/normal/learning.py')
    bank = path.endswith('readonly_bank_optimization_v107/bank.py')
    if event == 'call':
        forbidden = ((path.endswith('rfl_rebuild/b2/training.py') and name in
                      ('derive', 'key', 'mix', 'train_curve', 'pre_level')) or
                     (kernel and name == 'sample') or
                     (path.endswith('rfl_rebuild/solve/dp.py') and name == 'solve_reference') or
                     (path.endswith('random.py') and name in ('__init__', 'random', 'randrange')) or
                     qual in ('FutureTrainingProtocol.__init__', 'Curve.__init__'))
        if forbidden:
            COUNTS['forbidden'] += 1
            LOG.emit('FORBIDDEN_CALL', {'path': path, 'function': name}, force=True)
            raise RuntimeError('ungranted key/formal/RNG/DP path: ' + name)
        counter = (name if kernel and name in ('step', 'rollout') else
                   'transaction' if store and name == 'apply_transaction' else
                   'B1' if native else
                   'law_plan' if path.endswith('rfl_rebuild/b1/laws.py') and name == 'plan' else None)
        if counter is not None:
            COUNTS[counter] += 1
            if COUNTS[counter] > CONTRACT['budget'][counter]:
                LOG.emit('NATIVE_BUDGET_EXCEEDED', {'counter': counter, 'counts': dict(COUNTS)}, force=True)
                raise RuntimeError('prospective native budget exhausted: ' + counter)
        if bank and name == 'run_bank':
            token = frame.f_locals['token']
            record = B._BANKS[token]
            actor = record.actor
            SCOPE = {'mode': actor.mode, 'stage': 'evaluation', 'role': actor.role,
                     'epoch': record.epoch}
            BANK = {'actor': actor, 'hash': hashlib.sha256(), 'count': 0}
            COUNTS['bank_started'] += 1
            LOG.emit('BANK_BEGIN', {'before': actor.payload(),
                                   'sample': [list(scene.key) for scene in record.sample]})
        elif learn and name == 'train_episode':
            actor, episode = frame.f_locals['self'], frame.f_locals['episode']
            SCOPE = {'mode': actor.mode, 'stage': 'training', 'role': actor.role,
                     'epoch': episode.epoch}
            COUNTS['training_started'] += 1
            LOG.emit('TRAIN_BEGIN', {'before': actor.payload(), 'declared_episode': episode._input})
        elif store and name == 'apply_transaction':
            LOG.emit('TX_CALL', {'before': A.stores(frame.f_locals['self']),
                                 'edits': frame.f_locals['edits']})
    elif event == 'return':
        if kernel and name == 'step' and type(arg) is K.StepResult:
            COUNTS['step_return'] += 1
            PENDING.append(arg)
        elif kernel and name == 'rollout' and type(arg) is K.RolloutTrace:
            COUNTS['rollout_return'] += 1
            linked = len(PENDING) == len(arg.steps) and all(
                result is step for result, step in zip(PENDING, arg.steps))
            LOG.emit('RAW', {'trace': arg, 'kappa': frame.f_locals['kappa'],
                             'tape': frame.f_locals['tape'], 'return_hex': arg.return_value.hex(),
                             'actual_step_object_links': linked, 'returned_steps': len(PENDING)})
            if SCOPE['stage'] == 'evaluation':
                if BANK is None:
                    raise RuntimeError('returned evaluation raw lacks its actual bank')
                BANK['hash'].update((canonical(A.wire(arg)) + '\n').encode('ascii'))
                BANK['count'] += 1
            PENDING = []
            if not linked:
                raise AssertionError('native rollout returned different actual step objects')
        elif kernel and name == 'rollout':
            LOG.emit('INCOMPLETE_RAW', {'kappa': frame.f_locals.get('kappa'),
                                       'tape': frame.f_locals.get('tape'),
                                       'returned_value': arg,
                                       'actual_returned_steps': tuple(PENDING),
                                       'no_complete_trace_or_value_claimed': True}, force=True)
        elif store and name == 'apply_transaction':
            COUNTS['transaction_return'] += 1
            LOG.emit('TX_RETURN', {'after': A.stores(frame.f_locals['self']),
                                   'returned_value': arg, 'not_a_manufactured_receipt': True})
        elif learn and name == 'train_episode' and type(arg) is dict:
            COUNTS['training_completed'] += 1
            LOG.emit('TRAIN_END', arg)
        elif bank and name == 'run_bank' and type(arg) is tuple and len(arg) == 2:
            traces, mean = arg
            actor = BANK['actor']
            LOG.emit('BANK_END', {'traces_count': len(traces), 'captured_raw_count': BANK['count'],
                                 'orderedmean_hex': mean.hex(), 'raw_sha256': BANK['hash'].hexdigest(),
                                 'after': actor.payload()})
            COUNTS['bank_completed'] += 1
            if len(traces) != BANK['count']:
                raise AssertionError('bank returned incomplete raw trace extent')
            BANK = None


def interesting(code):
    path, name, qual = code.co_filename.replace('\\', '/'), code.co_name, code.co_qualname
    return ((path.endswith('rfl_rebuild/env/kernel.py') and name in ('step', 'rollout', 'sample')) or
            (path.endswith('rfl_rebuild/learner/store.py') and name == 'apply_transaction') or
            (path.endswith('rfl_rebuild/b1/runner.py') and name in ('run_patch_law', 'run_dq_law')) or
            (path.endswith('rfl_rebuild/b1/laws.py') and name == 'plan') or
            (path.endswith('rfl_rebuild/b2/training.py') and name in
             ('derive', 'key', 'mix', 'train_curve', 'pre_level')) or
            (path.endswith('rfl_rebuild/solve/dp.py') and name == 'solve_reference') or
            (path.endswith('random.py') and name in ('__init__', 'random', 'randrange')) or
            qual in ('FutureTrainingProtocol.__init__', 'Curve.__init__') or
            (path.endswith('complete_curve_source_gates_v105/variants/normal/learning.py') and
             name == 'train_episode') or
            (path.endswith('readonly_bank_optimization_v107/bank.py') and name == 'run_bank'))


DISPATCH = {}


def observe(frame, event, arg):
    key = id(frame.f_code)
    item = DISPATCH.get(key)
    if item is None:
        item = (frame.f_code, interesting(frame.f_code))
        DISPATCH[key] = item
    if item[1]:
        handler(frame, event, arg)


def load_modules():
    global L, B, N
    normal = HERE.parent / 'complete_curve_source_gates_v105/variants/normal'
    loaded = []
    for fullname, path in (('v105_normal_td', normal / 'td.py'),
                           ('v105_normal_learning', normal / 'learning.py'),
                           ('v107_bank', HERE.parent / 'readonly_bank_optimization_v107/bank.py'),
                           ('v110_nocredit', HERE / 'nocredit.py')):
        spec = importlib.util.spec_from_file_location(fullname, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[fullname] = module
        spec.loader.exec_module(module)
        loaded.append(module)
    L, B, N = loaded[1:]


def read_reference():
    entry = CONTRACT['reference_input']
    raw = (ROOT / entry['path']).read_bytes()
    if hashlib.sha256(raw).hexdigest() != entry['sha256']:
        raise AssertionError('reference source bytes changed')
    rows = {}
    for line in raw.decode('utf-8').splitlines():
        if line.startswith('DECISION_CONTEXT='):
            value = json.loads(line.split('=', 1)[1])
            x, y, t, k, phase, z, m = value['context']
            rows[K.State(x, y, t, k, phase), z, m] = {
                action: float.fromhex(number) for action, number in value['q_row_hex']}
    reference = QReferenceView(rows, name='v110-fixed-original-reference')
    LOG.emit('REFERENCE', {'digest': reference.digest(), 'rows': len(reference)})
    if reference.digest() != entry['q_digest']:
        raise AssertionError('reference full domain differs')
    return reference


def episodes():
    result = []
    for epoch in range(3):
        k = epoch % 2
        proposal = (epoch // 2) % 4
        phase, error, rank = (epoch // 8) % 6, (epoch // 48) % 2, (epoch // 96) % 60
        coins = tuple(0 if (epoch + step) % 10 == 0 else T.M64 for step in range(12))
        draws = tuple((T.M64, epoch * 12 + step) for step in range(12))
        result.append(L.EngineeringEpisode(epoch, k, proposal, K.SemanticTape(phase, error, rank), coins, draws))
    return tuple(result)


def rejection(label, action):
    before = dict(COUNTS)
    try:
        action()
    except A.ProtocolError as error:
        LOG.emit('GUARD_REJECTION', {'label': label, 'exception_type': type(error).__name__,
                                     'message': str(error), 'before_counts': before,
                                     'after_counts': dict(COUNTS)})
        if before != dict(COUNTS):
            raise AssertionError('rejection performed extra native work: ' + label)
        return
    LOG.emit('GUARD_UNEXPECTED_ACCEPTANCE', {'label': label, 'before_counts': before,
                                          'after_counts': dict(COUNTS)})
    raise AssertionError('expected exact rejection: ' + label)


class NoCreditFutureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global SCOPE
        cls.reference = read_reference()
        cls.episodes = episodes()
        cls.cases = []
        healthy_entry = CONTRACT['healthy_reference']
        healthy_raw = (ROOT / healthy_entry['path']).read_bytes()
        if hashlib.sha256(healthy_raw).hexdigest() != healthy_entry['sha256']:
            raise AssertionError('shared healthy reference bytes changed')
        healthy = json.loads(healthy_raw)
        for mode in CONTRACT['modes']:
            SCOPE = {'mode': mode, 'stage': 'source', 'role': None, 'epoch': None}
            pre = LearnerPersistentState()
            before = dict(COUNTS)
            source = O.capture_source(pre, scene=EvaluationScene(*CONTRACT['source_scene']), regime='T',
                                      q_reference=cls.reference, healthy_reference=healthy,
                                      mask=K.FaultMask(trap=K.Trap((1, 2), 0)), counterfactual=False)
            source_audit = O.source_audit(source)
            LOG.emit('ORIGINAL_SOURCE', {'mode': mode, 'audit': source_audit,
                                         'supplied_pre': A.stores(pre), 'before_counts': before,
                                         'after_counts': dict(COUNTS)})
            _source_record, sd = O._checked_source(source)
            LOG.emit('SOURCE_TRUTH_ACTUAL', {'truth': sd.truth, 'fullpre': A.stores(sd.pre),
                                           'outcome': sd.trace.outcome, 'return_hex': sd.trace.return_value.hex(),
                                           'actual_mask': sd.trace.mask, 'regime': sd.regime})
            if (sd.trace.outcome != K.Outcome.TRAP or sd.trace.return_value.hex() != (-1.02).hex() or
                    sd.truth['Gamma_T_star'] != ['Unknown/NoWrite'] or
                    sd.truth['R_mech'] != [{'kind': 'rho_U', 'cell': [1, 2], 't': 0}] or
                    not sd.pre.snapshot().healthy):
                raise AssertionError('actual predeclared healthy T trap source differs; no fallback world')
            bound = H.bind_source(source, mode=mode)
            LOG.emit('BOUND_BEFORE_ARMS', H.source_audit(bound))
            architecture = 'D_Q' if mode == 'dq' else 'D_patch'
            law = 'FactualReturnWrite' if mode == 'dq' else 'DeleteFactualPatch'
            rejection('wrong_source_mode_' + mode, lambda: N.run_no_credit_pair(
                bound, architecture='D_patch' if mode == 'dq' else 'D_Q',
                tier=Tier.L0_FACTUAL, law_name='DeleteFactualPatch' if mode == 'dq' else 'FactualReturnWrite'))
            pair = N.run_no_credit_pair(bound, architecture=architecture, tier=Tier.L0_FACTUAL, law_name=law)
            LOG.emit('ORIGINAL_PAIR', O.pair_audit(pair, source))
            LOG.emit('NO_CREDIT_METADATA', N.metadata_audit(bound, pair))
            bundle = N.prepare_curve(bound, pair, episodes=cls.episodes, evaluation_indices=tuple(range(100)))
            LOG.emit('FUTURE_BEGIN', N.audit(bundle))
            cls.cases.append({'mode': mode, 'source': source, 'bound': bound, 'pair': pair,
                              'bundle': bundle, 'architecture': architecture, 'law': law,
                              'source_state': sd.pre, 'source_audit': source_audit})

    def test_01_actual_empty_projection_preserves_full_residual(self):
        for case in self.cases:
            declaration = N.metadata_audit(case['bound'], case['pair'])['declaration']
            self.assertEqual(declaration['whole_units'], ['Unknown/NoWrite'])
            self.assertEqual(declaration['residual_units'], ['Unknown/NoWrite'])
            self.assertEqual(declaration['cell_units'], [])
            self.assertEqual(declaration['owner_addresses'], [])
            self.assertEqual(declaration['native_B1_arm_calls'], 0)
            self.assertEqual(declaration['owner_receipts'], 0)
            self.assertEqual(declaration['therapy_transactions'], 0)
            self.assertEqual(declaration['collateral_status'], N.COLLATERAL_STATUS)
            self.assertIsNone(declaration['collateral'])
            self.assertEqual(N.audit(case['bundle'])['contrast_status'], N.CONTRAST_STATUS)
        self.assertEqual(COUNTS['rollout'], 2)
        self.assertEqual(COUNTS['transaction'], 0)
        self.assertEqual(COUNTS['B1'], 0)
        self.assertEqual(COUNTS['law_plan'], 0)

    def test_02_authentic_source_role_alias_and_once_boundaries(self):
        global SCOPE
        for cls in (N.OwnedNoCreditFuture, N.RoleCurve, N.ExternalCurveView):
            rejection('closed_nominal_' + cls.__name__, cls)
        for index, case in enumerate(self.cases):
            SCOPE = {'mode': case['mode'], 'stage': 'guard', 'role': None, 'epoch': None}
            foreign = self.cases[1 - index]
            rejection('foreign_actual_source_' + case['mode'], lambda: N.prepare_curve(
                foreign['bound'], case['pair'], episodes=self.episodes, evaluation_indices=tuple(range(100))))
            rejection('prepared_once_' + case['mode'], lambda: N.prepare_curve(
                case['bound'], case['pair'], episodes=self.episodes, evaluation_indices=tuple(range(100))))
            rejection('original_metadata_once_' + case['mode'], lambda: N.run_no_credit_pair(
                case['bound'], architecture=case['architecture'], tier=Tier.L0_FACTUAL, law_name=case['law']))
            data = N._FUTURES[case['bundle']]
            actual = data.actors[1]._current
            data.actors[1]._current = data.actors[0]._current
            try:
                rejection('live_role_value_alias_' + case['mode'], lambda: N.audit(case['bundle']))
            finally:
                data.actors[1]._current = actual
            live_source = H._SOURCES[case['bound']]
            actual_mode = live_source.mode
            object.__setattr__(live_source, 'mode', 'patch-adaptive' if actual_mode == 'dq' else 'dq')
            try:
                rejection('source_mode_tamper_' + case['mode'], lambda: N.audit(case['bundle']))
            finally:
                object.__setattr__(live_source, 'mode', actual_mode)
            LOG.emit('GUARDS_RESTORED', {'audit': N.audit(case['bundle']),
                                        'source': O.source_audit(case['source'])})
            self.assertEqual(O.source_audit(case['source']), case['source_audit'])

    def test_03_complete_actual_ordinary_future_without_treatment(self):
        global SCOPE
        for case in self.cases:
            SCOPE = {'mode': case['mode'], 'stage': 'future', 'role': None, 'epoch': None}
            handles = N.run_pair_curve(case['bundle'])
            case['handles'] = handles
            observed = []
            for role, handle in zip(N.ROLES, handles):
                SCOPE = {'mode': case['mode'], 'stage': 'export', 'role': role, 'epoch': None}
                checkpoints, v_pre, t_max = N._external_material(handle)
                means = []
                pins = []
                for epoch, traces, mean in checkpoints:
                    total = 0.0
                    digest = hashlib.sha256()
                    for trace in traces:
                        total += trace.return_value
                        digest.update((canonical(A.wire(trace)) + '\n').encode('ascii'))
                    actual_mean = total / len(traces)
                    pins.append({'epoch': epoch, 'mean_hex': mean.hex(), 'actual_orderedmean_hex': actual_mean.hex(),
                                 'count': len(traces), 'raw_sha256': digest.hexdigest()})
                    means.append(mean)
                    self.assertEqual(actual_mean.hex(), mean.hex())
                    self.assertEqual(len(traces), 100)
                    self.assertTrue(all(trace.mask == K.FaultMask() for trace in traces))
                _bundle, actual_role, _checkpoints, training = N._ROLE_CURVES[handle]
                LOG.emit('CURVE_COMPLETE', {'role': role, 'actual_role': actual_role,
                                            'origin_sha256': N._FUTURES[case['bundle']].seal,
                                            'checkpoints': pins, 'training_count': len(training),
                                            'v_pre_hex': v_pre.hex(), 't_max': t_max,
                                            'full_after': N.audit(case['bundle']),
                                            'contrast_status': N.CONTRAST_STATUS,
                                            'collateral_status': N.COLLATERAL_STATUS, 'collateral': None})
                self.assertEqual(tuple(epoch for epoch, _traces, _mean in checkpoints), (0, 1, 2, 3))
                self.assertEqual(len(training), 3)
                self.assertEqual(actual_role, role)
                observed.append((checkpoints, tuple(mean.hex() for mean in means)))
            self.assertEqual(A.wire(observed[0][0]), A.wire(observed[1][0]))
            self.assertEqual(observed[0][1], observed[1][1])
            SCOPE = {'mode': case['mode'], 'stage': 'pair_summary', 'role': None, 'epoch': None}
            LOG.emit('NO_EDIT_ROLE_EQUALITY', {'mode': case['mode'], 'ordered_means_hex': list(observed[0][1]),
                                              'actual_full_raw_equal': True,
                                              'not_independent_samples': True,
                                              'not_substantive_treatment_contrast': True})
            self.assertEqual(O.source_audit(case['source']), case['source_audit'])
        self.assertEqual(COUNTS['rollout'], 1614)
        self.assertEqual(COUNTS['rollout_return'], 1614)
        self.assertEqual(COUNTS['bank_completed'], 16)
        self.assertEqual(COUNTS['training_completed'], 12)
        self.assertEqual(COUNTS['B1'], 0)
        self.assertEqual(COUNTS['law_plan'], 0)
        self.assertEqual(PENDING, [])

    def test_04_closed_external_observations_and_complete_once(self):
        global SCOPE
        for case in self.cases:
            for role, handle in zip(N.ROLES, case['handles']):
                SCOPE = {'mode': case['mode'], 'stage': 'external', 'role': role, 'epoch': None}
                view = N.build_external(handle)
                payload = N.read_external(view)
                wire = {'fields': dict(payload['fields']), 'episodes': payload['episodes'],
                        'values': payload['values'], 'pre_level': payload['pre_level'],
                        't_max': payload['t_max']}
                LOG.emit('EXTERNAL', {'role': role, 'origin_sha256': N._FUTURES[case['bundle']].seal,
                                      'projection': wire, 'source_or_truth_or_cost_feature': False})
                self.assertEqual(set(payload), {'fields', 'episodes', 'values', 'pre_level', 't_max'})
                self.assertEqual(set(payload['fields']), set(N.FIELDS))
                self.assertEqual(payload['episodes'], (0, 1, 2, 3))
                self.assertTrue(all(len(bank) == 100 for banks in payload['fields'].values() for bank in banks))
                with self.assertRaises(TypeError):
                    payload['source'] = 'not_a_feature'
                with self.assertRaises(TypeError):
                    payload['fields']['truth'] = ('not_a_feature',)
            SCOPE = {'mode': case['mode'], 'stage': 'guard', 'role': None, 'epoch': None}
            rejection('complete_future_once_' + case['mode'], lambda: N.run_pair_curve(case['bundle']))
            rejection('external_rejects_origin_' + case['mode'], lambda: N.build_external(case['bundle']))
            self.assertEqual(O.source_audit(case['source']), case['source_audit'])


def main():
    global LOG
    load_modules()
    LOG = Capture()
    old_profile = sys.getprofile()
    originals = (K.step, K.rollout, H.bind_source, H.run_whole_pair, O.run_pair,
                 LearnerPersistentState.apply_transaction, L.CoordinateLearner.train_episode)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(NoCreditFutureTests)
    result = None
    try:
        sys.setprofile(observe)
        LOG.emit('CONTRACT', {'contract': CONTRACT, 'loaded_before': loaded_sources(),
                              'started_at_utc': datetime.now(timezone.utc).isoformat()})
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    except BaseException as error:
        LOG.emit('TOPLEVEL_FAILURE', {'type': type(error).__name__, 'message': str(error),
                                      'traceback': traceback.format_exc(), 'counts': dict(COUNTS)}, force=True)
        raise
    finally:
        profile_was_installed = sys.getprofile() is observe
        sys.setprofile(old_profile)
        if PENDING:
            LOG.emit('PENDING_NATIVE_STEP_RETURNS', {'actual_steps': tuple(PENDING),
                                                    'no_complete_trace_or_value_claimed': True}, force=True)
        restored = originals == (K.step, K.rollout, H.bind_source, H.run_whole_pair, O.run_pair,
                                  LearnerPersistentState.apply_transaction, L.CoordinateLearner.train_episode)
        summary = {'tests_run': result.testsRun if result else None,
                   'failures': len(result.failures) if result else None,
                   'errors': len(result.errors) if result else None,
                   'skipped': len(result.skipped) if result else None,
                   'counts': dict(COUNTS), 'pending_native_step_returns': len(PENDING),
                   'loaded_sources': loaded_sources(), 'profile_was_installed': profile_was_installed,
                   'profile_restored': sys.getprofile() is old_profile, 'original_function_identities_unchanged': restored,
                   'wall_seconds': time.monotonic() - START,
                   'B1_arm_calls': COUNTS['B1'], 'therapy_transactions': 0, 'owner_receipts': 0,
                   'fresh_original_sources': 2 if hasattr(NoCreditFutureTests, 'cases') and
                   len(NoCreditFutureTests.cases) == 2 else None,
                   'collateral_status': N.COLLATERAL_STATUS, 'collateral': None,
                   'contrast_status': N.CONTRAST_STATUS, 'partial_native_gate_claimed': False,
                   'scientific_qualification': False, 'formal_collection_enabled': False,
                   'automatic_retry': False}
        LOG.emit('SUMMARY', summary, force=True)
        summary.update(records=LOG.records, raw_bytes=LOG.raw_bytes,
                       canonical_sha256=LOG.digest.hexdigest())
        with (OUT / 'child_summary.json').open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(summary, stream, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
            stream.write('\n')
        LOG.close()
        print(canonical(summary), flush=True)
    return 0 if result and result.wasSuccessful() and profile_was_installed and restored else 1


if __name__ == '__main__':
    raise SystemExit(main())
