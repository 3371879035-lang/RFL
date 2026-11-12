"""First finite semantic/performance check of a new ordinary bank read path.

The old evaluator is a comparator on fresh v107 actors, not an old fixture or
completed v106 bank retry. Guard-only constructor clones are explicitly NOT
owned curve handles or additional experimental roles. All native raw results
are captured before assertions; one induced post-scene violation is retained.
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
from rfl_rebuild.learner.store import (
    LearnerPersistentState, QAddress, DecisionAddress, Edit, Q, DECISION, PROCESS, CONTROLLER,
)

CONTRACT = json.loads((HERE / 'contract.json').read_bytes())
COUNTS = Counter()
SCOPE = {'stage': 'initialization', 'mode': None, 'role': None, 'phase': None, 'case': None}
PENDING = []
DISPATCH = {}
LOG = None
START = time.monotonic()
MUTATE_ON_RETURN = None


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


class Capture:
    def __init__(self, path):
        self.file = path.open('xb')
        self.records = self.bytes = 0
        self.sha = hashlib.sha256()

    def emit(self, tag, data, *, force=False):
        payload = A.wire(data)
        line = (canonical(dict(seq=self.records, tag=tag, payload=payload, **SCOPE)) + '\n').encode('ascii')
        self.file.write(line)
        self.file.flush()
        self.records += 1
        self.bytes += len(line)
        self.sha.update(line)
        if not force:
            A.require(self.bytes <= CONTRACT['budget']['capture_bytes'], 'capture byte cap')
            A.require(time.monotonic() - START <= CONTRACT['budget']['seconds'], 'wall-time cap')
        return payload

    def close(self):
        self.file.close()


def interesting(code):
    path = code.co_filename.replace('\\', '/')
    name = code.co_name
    return ((path.endswith('rfl_rebuild/env/kernel.py') and name in ('step', 'rollout', 'sample')) or
            (path.endswith('rfl_rebuild/learner/store.py') and name == 'apply_transaction') or
            (path.endswith('rfl_rebuild/b1/runner.py') and name in ('run_patch_law', 'run_dq_law')) or
            (path.endswith('rfl_rebuild/b2/training.py') and name in ('derive', 'key', 'mix', 'train_curve', 'pre_level')) or
            (path.endswith('rfl_rebuild/solve/dp.py') and name == 'solve_reference') or
            (path.endswith('random.py') and name in ('__init__', 'random', 'randrange')) or
            code.co_qualname in ('FutureTrainingProtocol.__init__', 'Curve.__init__') or
            (path.endswith('complete_curve_source_gates_v105/variants/normal/learning.py') and
             name == 'train_episode'))


def handler(frame, event, arg):
    global PENDING, MUTATE_ON_RETURN
    path, name = frame.f_code.co_filename.replace('\\', '/'), frame.f_code.co_name
    kernel = path.endswith('rfl_rebuild/env/kernel.py')
    store = path.endswith('rfl_rebuild/learner/store.py')
    native = path.endswith('rfl_rebuild/b1/runner.py') and name in ('run_patch_law', 'run_dq_law')
    learning = path.endswith('complete_curve_source_gates_v105/variants/normal/learning.py')
    if event == 'call':
        counter = name if kernel and name in ('step', 'rollout') else 'transaction' if store and name == 'apply_transaction' else 'B1' if native else None
        if counter:
            COUNTS[counter] += 1
            A.require(COUNTS[counter] <= CONTRACT['budget'][counter], 'native cap: ' + counter)
        if ((path.endswith('rfl_rebuild/b2/training.py') and name in ('derive', 'key', 'mix', 'train_curve', 'pre_level')) or
                (kernel and name == 'sample') or
                (path.endswith('rfl_rebuild/solve/dp.py') and name == 'solve_reference') or
                (path.endswith('random.py') and name in ('__init__', 'random', 'randrange')) or
                frame.f_code.co_qualname in ('FutureTrainingProtocol.__init__', 'Curve.__init__')):
            COUNTS['forbidden'] += 1
            raise RuntimeError('ungranted original formal/key/RNG/DP path: ' + name)
        if store and name == 'apply_transaction':
            LOG.emit('TX_CALL', {'before': A.stores(frame.f_locals['self']), 'edits': frame.f_locals['edits']})
        elif learning and name == 'train_episode':
            LOG.emit('TRAIN_BEGIN', {'before': frame.f_locals['self'].payload(),
                                    'episode': frame.f_locals['episode']._input})
    elif event == 'return':
        if kernel and name == 'step' and type(arg) is K.StepResult:
            COUNTS['step_return'] += 1
            PENDING.append(arg)
        elif kernel and name == 'rollout':
            if type(arg) is K.RolloutTrace:
                linked = len(PENDING) == len(arg.steps) and all(x is y for x, y in zip(PENDING, arg.steps))
                COUNTS['rollout_return'] += 1
                LOG.emit('RAW_ROLLOUT', {'trace': arg, 'kappa': frame.f_locals['kappa'],
                                        'tape': frame.f_locals['tape'], 'step_objects_linked': linked})
                PENDING = []
                A.require(linked, 'actual step-to-rollout object linkage')
                if MUTATE_ON_RETURN is not None:
                    actor = MUTATE_ON_RETURN
                    MUTATE_ON_RETURN = None
                    actor._current._process[0] = 2
                    LOG.emit('INDUCED_POSTSCENE_WRITE', {'current': A.stores(actor._current),
                                                       'actual_returned_trace_complete': True})
            else:
                LOG.emit('INCOMPLETE_ROLLOUT', {'returned': arg, 'completed_step_returns': PENDING}, force=True)
                PENDING = []
        elif store and name == 'apply_transaction':
            LOG.emit('TX_RETURN', {'after': A.stores(frame.f_locals['self'])})
        elif native and type(arg) is O.base.native_b1.B1Result:
            LOG.emit('NATIVE_B1_RETURN', {'law': frame.f_locals['law'].name,
                                        'full_post': A.stores(arg.post_state),
                                        'ledger_canonical': arg.ledger.canonical(),
                                        'receipts': arg.ledger.receipts})
        elif learning and name == 'train_episode' and isinstance(arg, dict):
            LOG.emit('CORE_EPISODE', arg)


def observe(frame, event, arg):
    key = id(frame.f_code)
    item = DISPATCH.get(key)
    if item is None:
        item = (frame.f_code, interesting(frame.f_code))
        DISPATCH[key] = item
    if item[1]:
        handler(frame, event, arg)


def load_modules():
    result = []
    folder = HERE.parent / 'complete_curve_source_gates_v105/variants/normal'
    for name, filename in (('td', 'td.py'), ('learning', 'learning.py'), ('curve', 'owned_curve.py'), ('external', 'external.py')):
        fullname = 'v105_normal_' + name
        spec = importlib.util.spec_from_file_location(fullname, folder / filename)
        module = importlib.util.module_from_spec(spec)
        sys.modules[fullname] = module
        spec.loader.exec_module(module)
        result.append(module)
    import bank
    return (*result, bank)


def read_reference():
    spec = CONTRACT['reference_input']
    raw = (ROOT / spec['path']).read_bytes()
    A.require(hashlib.sha256(raw).hexdigest() == spec['sha256'], 'complete reference catalog binding')
    rows = {}
    for line in raw.decode('utf-8').splitlines():
        if line.startswith('DECISION_CONTEXT='):
            entry = json.loads(line.split('=', 1)[1])
            x, y, t, k, phi, z, m = entry['context']
            rows[K.State(x, y, t, k, phi), z, m] = {a: float.fromhex(value) for a, value in entry['q_row_hex']}
    reference = QReferenceView(rows, name='v107-fixed-original-reference')
    LOG.emit('REFERENCE', {'digest': reference.digest(), 'row_count': len(reference)})
    A.require(reference.digest() == spec['q_digest'], 'nominal Q* binding')
    return reference


def make_source(mode, reference):
    global SCOPE
    SCOPE = dict(stage='source', mode=mode, role=None, phase=None, case=None)
    contexts = [DecisionAddress(K.State(*K.START, t, 0, 2), 1, m) for t in range(12) for m in (0, 1)]
    contexts += [DecisionAddress(K.State(1, 2, 1, 0, 2), 1, m) for m in (0, 1)]
    sentinel = DecisionAddress(K.State(*K.START, 0, 1, 2), 1, 0)
    contexts.append(sentinel)
    sites = ((K.ControllerSite(K.State(*K.START, 0, 0, 2), K.WAIT), K.RIGHT),
             (K.ControllerSite(K.State(1, 2, 1, 0, 2), K.WAIT), K.LEFT),
             (K.ControllerSite(sentinel.state, K.WAIT), K.RIGHT))
    legality = []
    for site, target in sites:
        service = [(z, m, tuple(reference.row(site.state, z, m))) for z in K.option_ids() for m in (0, 1)
                   if site.cmd in reference.row(site.state, z, m)]
        A.require(service and all(target in row for _z, _m, row in service), 'complete controller target service legality')
        legality.append({'site': site, 'target': target, 'all_serving_contexts': service})
    edits = [Edit(PROCESS, 0, 1), Edit(PROCESS, 3, 2)] + [Edit(CONTROLLER, site, target) for site, target in sites]
    for address in contexts:
        row = reference.row(address.state, address.z, address.m)
        A.require(K.WAIT in row, 'legal WAIT context')
        edits.append(Edit(Q, QAddress(address.state, address.z, address.m, K.WAIT), max(row.values()) + 1.0)
                     if mode == 'dq' else Edit(DECISION, address, K.WAIT))
    LOG.emit('SOURCE_INSTALL_PLANNED', {'edits': edits, 'all_controller_legality': legality})
    A.require(len(edits) == 32, 'complete fixed source edit extent')
    pre = LearnerPersistentState()
    pre.apply_transaction(tuple(edits), q_reference=reference)
    healthy = json.loads((ROOT / CONTRACT['healthy_reference']['path']).read_bytes())
    source = O.capture_source(pre, scene=EvaluationScene(*CONTRACT['source_scene']), regime='P',
                              q_reference=reference, healthy_reference=healthy, counterfactual=False)
    LOG.emit('ORIGINAL_SOURCE', {'mode': mode, 'audit': O.source_audit(source)})
    bound = H.bind_source(source, mode=mode)
    LOG.emit('BOUND_BEFORE_ARMS', H.source_audit(bound))
    pair = H.run_whole_pair(bound, architecture='D_Q' if mode == 'dq' else 'D_patch', tier=Tier.L0_FACTUAL,
                           law_name='FactualReturnWrite' if mode == 'dq' else 'DeleteFactualPatch')
    LOG.emit('ORIGINAL_PAIR', O.pair_audit(pair, source))
    return source, bound, pair


def traces_digest(traces):
    digest = hashlib.sha256()
    for trace in traces:
        digest.update((canonical(A.wire(trace)) + '\n').encode('ascii'))
    return digest.hexdigest()


def timed(function):
    counts, wall, cpu = dict(COUNTS), time.monotonic(), time.process_time()
    value = function()
    timing = {'wall_seconds': time.monotonic() - wall, 'cpu_seconds': time.process_time() - cpu,
              'count_delta': {key: COUNTS[key] - counts.get(key, 0) for key in COUNTS}}
    return value, timing


class NewBankValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.td, cls.L, cls.C, cls.E, cls.B = load_modules()
        cls.reference = read_reference()
        cls.items = []
        cls.comparisons, cls.challenges, cls.guard_actors = [], [], []
        for mode in ('dq', 'patch-adaptive'):
            source, bound, pair = make_source(mode, cls.reference)
            episode = cls.L.EngineeringEpisode(0, 0, 0, K.SemanticTape(2, 0, 0),
                                               tuple(T.M64 for _ in range(K.HORIZON)),
                                               tuple((T.M64, i) for i in range(K.HORIZON)))
            bundle = cls.C.prepare_curve(bound, pair, episodes=(episode,), evaluation_indices=tuple(range(100)))
            data = cls.C._checked(bundle)
            LOG.emit('CURVE_PREPARED', {'origin': data.origin, 'origin_sha256': data.seal,
                                       'initial_composites': [actor.payload() for actor in data.actors]})
            cls.items.append((mode, source, bound, pair, bundle))

    def test_01_all_eight_fresh_state_differentials(self):
        global SCOPE
        for mode, source, bound, pair, bundle in self.items:
            data = self.C._checked(bundle)
            for role, actor in zip(self.C.ROLES, data.actors):
                for phase in ('before_td', 'after_td'):
                    SCOPE = dict(stage='comparison', mode=mode, role=role, phase=phase, case=len(self.comparisons))
                    before = actor.payload()
                    token = self.B.prepare_bank(actor, data.plan.evaluation_sample)
                    LOG.emit('BANK_TOKEN_PREPARED', self.B.audit_bank(token))
                    order = ('old', 'new') if phase == 'before_td' else ('new', 'old')
                    results, timings = {}, {}
                    for name in order:
                        SCOPE['stage'] = 'evaluate_' + name
                        if name == 'old':
                            results[name], timings[name] = timed(lambda: self.C._evaluate_bank(actor, data.plan.evaluation_sample))
                        else:
                            results[name], timings[name] = timed(lambda: self.B.run_bank(token))
                    old_traces, old_mean = results['old']
                    new_traces, new_mean = results['new']
                    record = {'order': list(order), 'before': before, 'after': actor.payload(),
                              'old_count': len(old_traces), 'new_count': len(new_traces),
                              'old_mean_hex': old_mean.hex(), 'new_mean_hex': new_mean.hex(),
                              'old_ordered_raw_sha256': traces_digest(old_traces),
                              'new_ordered_raw_sha256': traces_digest(new_traces), 'timings': timings,
                              'new_bank_audit': self.B.audit_bank(token),
                              'full_raw_equal': A.wire(old_traces) == A.wire(new_traces)}
                    LOG.emit('COMPARISON', record)
                    self.comparisons.append(record)
                    self.assertEqual(record['old_count'], 100)
                    self.assertEqual(record['new_count'], 100)
                    self.assertEqual(old_mean.hex(), new_mean.hex())
                    self.assertTrue(record['full_raw_equal'])
                    self.assertEqual(actor.payload(), before)
                    self.assertEqual(timings['old']['count_delta'].get('transaction', 0), 0)
                    self.assertEqual(timings['new']['count_delta'].get('transaction', 0), 0)
                    self.assertEqual(timings['old']['count_delta']['rollout'], 100)
                    self.assertEqual(timings['new']['count_delta']['rollout'], 100)
                    with self.assertRaises(A.ProtocolError):
                        self.B.run_bank(token)
                    with self.assertRaises(A.ProtocolError):
                        self.B.prepare_bank(actor, data.plan.evaluation_sample)
                    if phase == 'before_td':
                        SCOPE['stage'] = 'training'
                        receipt = actor.train_episode(data.plan.episode(0))
                        LOG.emit('OWNED_TRAIN_RETURN', receipt)
                        self.assertEqual(actor._completed, 1)
                self.C._checked(bundle)
            LOG.emit('ORIGINAL_PAIR_AFTER_DIFFERENTIAL', O.pair_audit(pair, source))
        self.assertEqual(len(self.comparisons), 8)

    def guard_actor(self, label):
        mode, source, bound, pair, bundle = self.items[1]
        data = self.C._checked(bundle)
        clone = O.clone_future_start(data.future, source, role='reference')
        actor = self.L.CoordinateLearner(clone, mode=mode, role='reference', source_label=data.actors[0].source_label,
                                         reference=self.reference, plan=data.plan)
        native = H._checked_original_pair(bound, pair)[2]
        record = {'label': label, 'constructor_kind': 'guard-only nominal constructor; no owned role curve minted',
                  'original_pair_seal': data.actors[0].source_label,
                  'original_future': O.future_audit(data.future, source),
                  'actual_immediate_clone': A.stores(clone), 'actor': actor.payload(),
                  'full_reference_I': A.stores(native.clones[0]),
                  'runtime_nonalias': all(obj is not existing for obj in (clone, actor._immediate, actor._current, actor._values)
                                          for existing in (*native.clones, *[a._immediate for a in data.actors],
                                                           *[a._current for a in data.actors]))}
        LOG.emit('GUARD_CONSTRUCTOR', record)
        self.assertEqual(A.stores(clone), A.stores(native.clones[0]))
        self.assertTrue(record['runtime_nonalias'])
        self.guard_actors.append(actor)
        return actor

    def test_02_eight_actual_precall_guard_entries(self):
        global SCOPE
        names = ('immediate', 'current', 'learning_values', 'process', 'controller', 'role', 'shared_plan', 'primitive_key')
        for index, name in enumerate(names):
            SCOPE = dict(stage='precall_guard', mode='patch-adaptive', role='reference', phase='guard-only', case=name)
            actor = self.guard_actor(name)
            token = self.B.prepare_bank(actor, actor.plan.evaluation_sample)
            before, counts = actor.payload(), dict(COUNTS)
            restore = None
            if name in ('immediate', 'process'):
                state = actor._immediate if name == 'immediate' else actor._current
                mapping = state._process
                saved = tuple(mapping.items())
                mapping[0] = 2
                restore = lambda mapping=mapping, saved=saved: (mapping.clear(), mapping.update(saved))
            elif name == 'current':
                mapping, saved = actor._current._decision, tuple(actor._current._decision.items())
                key = next(iter(mapping))
                mapping[key] = K.RIGHT
                restore = lambda mapping=mapping, saved=saved: (mapping.clear(), mapping.update(saved))
            elif name == 'learning_values':
                mapping, saved = actor._values._q, tuple(actor._values._q.items())
                address = QAddress(K.State(*K.START, 0, 0, 2), 1, 0, K.WAIT)
                mapping[address] = self.reference.value(address) + 1.0
                restore = lambda mapping=mapping, saved=saved: (mapping.clear(), mapping.update(saved))
            elif name == 'controller':
                mapping, saved = actor._current._controller, tuple(actor._current._controller.items())
                key = next(iter(mapping))
                mapping[key] = K.LEFT if mapping[key] != K.LEFT else K.RIGHT
                restore = lambda mapping=mapping, saved=saved: (mapping.clear(), mapping.update(saved))
            elif name == 'role':
                saved = actor.role
                actor.role = 'treatment'
                restore = lambda actor=actor, saved=saved: setattr(actor, 'role', saved)
            elif name == 'shared_plan':
                saved = actor.plan
                actor.plan = self.L.EngineeringPlan(saved.episodes, saved.evaluation_sample, saved.v_pre,
                                                    saved.parameters, saved.lock_digest)
                restore = lambda actor=actor, saved=saved: setattr(actor, 'plan', saved)
            else:
                key = next(iter(actor._current._decision))
                saved = key.state.kappa
                object.__setattr__(key.state, 'kappa', bool(saved))
                restore = lambda key=key, saved=saved: object.__setattr__(key.state, 'kappa', saved)
            error = None
            try:
                try:
                    self.B.run_bank(token)
                except A.ProtocolError as exc:
                    error = {'type': type(exc).__name__, 'message': str(exc)}
                LOG.emit('PRECALL_CHALLENGE', {'name': name, 'error': error, 'audit': self.B.audit_bank(token),
                                               'native_delta': {key: COUNTS[key] - counts.get(key, 0) for key in COUNTS}})
                self.assertIsNotNone(error)
            finally:
                restore()
            record = {'name': name, 'restored_full_composite': actor.payload() == before,
                      'audit': self.B.audit_bank(token), 'error': error,
                      'native_delta': {key: COUNTS[key] - counts.get(key, 0) for key in COUNTS}}
            LOG.emit('PRECALL_RESTORED', record)
            self.challenges.append(record)
            self.assertTrue(record['restored_full_composite'])
            self.assertEqual(record['native_delta'].get('rollout', 0), 0)
            self.assertEqual(record['native_delta'].get('transaction', 0), 0)
            self.assertTrue(record['audit']['attempted'])
            self.assertFalse(record['audit']['complete'])
            self.assertIsNone(record['audit']['mean_hex'])
            with self.assertRaises(A.ProtocolError):
                self.B.run_bank(token)
            with self.assertRaises(A.ProtocolError):
                self.B.prepare_bank(actor, actor.plan.evaluation_sample)
        self.assertEqual(len(self.challenges), 8)

    def test_03_nominal_once_and_actual_postscene_partial(self):
        global SCOPE, MUTATE_ON_RETURN
        SCOPE = dict(stage='partial_guard', mode='patch-adaptive', role='reference', phase='guard-only', case='postscene')
        actor = self.guard_actor('actual_postscene_partial')
        sample = actor.plan.evaluation_sample
        counts = dict(COUNTS)
        for candidate in (None, object(), object.__new__(self.B.ReadonlyBank)):
            with self.assertRaises(A.ProtocolError):
                self.B.run_bank(candidate)
        with self.assertRaises(A.ProtocolError):
            self.B.ReadonlyBank()
        with self.assertRaises(A.ProtocolError):
            self.B.prepare_bank(actor, tuple(list(sample)))
        with self.assertRaises(A.ProtocolError):
            self.B.prepare_bank(actor, sample[:-1])
        with self.assertRaises(A.ProtocolError):
            self.B.prepare_bank(actor, tuple(reversed(sample)))
        LOG.emit('NOMINAL_CHALLENGES', {'count': 7, 'native_delta': {key: COUNTS[key] - counts.get(key, 0) for key in COUNTS}})
        token = self.B.prepare_bank(actor, sample)
        before = actor.payload()
        mapping, saved = actor._current._process, tuple(actor._current._process.items())
        error = None
        MUTATE_ON_RETURN = actor
        try:
            try:
                self.B.run_bank(token)
            except A.ProtocolError as exc:
                error = {'type': type(exc).__name__, 'message': str(exc)}
            LOG.emit('POSTSCENE_PARTIAL', {'error': error, 'audit': self.B.audit_bank(token),
                                          'native_delta': {key: COUNTS[key] - counts.get(key, 0) for key in COUNTS},
                                          'actual_complete_raw_return_count': 1})
        finally:
            MUTATE_ON_RETURN = None
            mapping.clear()
            mapping.update(saved)
        record = {'error': error, 'restored_full_composite': actor.payload() == before,
                  'audit': self.B.audit_bank(token), 'native_delta': {key: COUNTS[key] - counts.get(key, 0) for key in COUNTS}}
        LOG.emit('POSTSCENE_RESTORED', record)
        self.assertIsNotNone(error)
        self.assertTrue(record['restored_full_composite'])
        self.assertEqual(record['native_delta']['rollout'], 1)
        self.assertFalse(record['audit']['complete'])
        self.assertIsNone(record['audit']['mean_hex'])
        self.assertEqual(record['audit']['completed_scenes'], 0)
        type(self).partial_record = record
        with self.assertRaises(A.ProtocolError):
            self.B.run_bank(token)
        with self.assertRaises(A.ProtocolError):
            self.B.prepare_bank(actor, sample)

    def test_04_original_sources_and_protected_roles(self):
        global SCOPE
        SCOPE = dict(stage='final', mode=None, role=None, phase=None, case=None)
        states = []
        for mode, source, bound, pair, bundle in self.items:
            data = self.C._checked(bundle)
            LOG.emit('ORIGINAL_PAIR_FINAL', O.pair_audit(pair, source))
            for actor in data.actors:
                LOG.emit('FINAL_COMPOSITE', actor.payload())
                states.extend((actor._immediate, actor._current))
                if actor._values is not None:
                    states.append(actor._values)
                self.assertEqual(actor._completed, 1)
                self.assertEqual(actor._attempted, {0})
                self.assertEqual(A.stores(actor._immediate), actor._initial)
        self.assertEqual(len(states), len({id(state) for state in states}))
        guard_states = [state for actor in self.guard_actors
                        for state in (actor._immediate, actor._current, actor._values)]
        self.assertEqual(len(guard_states), 27)
        self.assertEqual(len(guard_states + states), len({id(state) for state in guard_states + states}))
        self.assertEqual(len(self.comparisons), 8)
        self.assertTrue(all(record['full_raw_equal'] for record in self.comparisons))
        self.assertEqual(len(self.challenges), 8)
        self.assertTrue(all(record['error'] and record['restored_full_composite'] for record in self.challenges))
        self.assertTrue(type(self).partial_record['restored_full_composite'])
        self.assertEqual(COUNTS['rollout'], COUNTS['rollout_return'])
        self.assertEqual(COUNTS['step'], COUNTS['step_return'])
        self.assertEqual(COUNTS['B1'], 4)
        self.assertEqual(COUNTS['rollout'], 1607)
        self.assertEqual(COUNTS['forbidden'], 0)
        loaded = {}
        for module in tuple(sys.modules.values()):
            filename = getattr(module, '__file__', None)
            if filename:
                path = Path(filename).resolve()
                if path.is_relative_to(ROOT) and path.suffix == '.py':
                    loaded[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        LOG.emit('ACTUAL_LOADED_SOURCE_INVENTORY', loaded)
        pins = json.loads((HERE / 'evidence/claim.json').read_bytes())['input_binding_before']
        self.assertTrue(all(name in pins and pins[name]['sha256'] == digest for name, digest in loaded.items()))
        LOG.emit('RESULT', {'completed': True, 'counts': dict(COUNTS), 'differential_states': 8,
                            'precall_challenges': 8, 'guard_only_constructor_clones': 9,
                            'actual_partial_scene_returns': 1, 'four_actual_owned_roles': True,
                            'positive_benefit_required': False, 'scientific_qualification': False,
                            'formal_training_or_collection': False})


def main():
    global LOG
    LOG = Capture(HERE / 'evidence/raw.jsonl')
    old_profile = sys.getprofile()
    result = None
    try:
        LOG.emit('RUN_BEGIN', {'started_at_utc': datetime.now(timezone.utc).isoformat(),
                              'contract_sha256': hashlib.sha256((HERE / 'contract.json').read_bytes()).hexdigest()})
        sys.setprofile(observe)
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(NewBankValidation))
        LOG.emit('TEST_RESULT', {'tests_run': result.testsRun, 'failures': len(result.failures),
                                'errors': len(result.errors), 'skipped': len(result.skipped),
                                'counts': dict(COUNTS), 'wall_seconds': time.monotonic() - START,
                                'cpu_seconds': time.process_time()})
        return 0 if result.wasSuccessful() and not result.skipped else 1
    except BaseException as error:
        LOG.emit('FAILURE', {'type': type(error).__name__, 'text': str(error),
                             'traceback': traceback.format_exc(), 'counts': dict(COUNTS)}, force=True)
        traceback.print_exc()
        return 1
    finally:
        sys.setprofile(old_profile)
        if PENDING:
            LOG.emit('PENDING_STEP_RETURNS', PENDING, force=True)
        LOG.close()
        summary = {'records': LOG.records, 'bytes': LOG.bytes, 'canonical_sha256': LOG.sha.hexdigest(),
                   'counts': dict(COUNTS), 'wall_seconds': time.monotonic() - START,
                   'cpu_seconds': time.process_time(), 'automatic_retry': False}
        with (HERE / 'evidence/child_summary.json').open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(canonical(summary) + '\n')
        print(canonical(summary), flush=True)


if __name__ == '__main__':
    raise SystemExit(main())
