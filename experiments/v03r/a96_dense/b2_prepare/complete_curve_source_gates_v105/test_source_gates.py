"""Prospective complete-entry source mutation gates; fresh owned pair per case."""
import ast
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path[:0] = [str(HERE.parent / 'owned_adaptive_handoff_v92'),
               str(HERE.parent / 'adaptive_training_v90'), str(HERE.parent), str(ROOT / 'src')]
import adaptive_training as A
import handoff as H
import oracle_mainline_v75 as O
from rfl_rebuild.b2 import training as T
from rfl_rebuild.b2.unaffected import EvaluationScene
from rfl_rebuild.b1.tier import Tier
from rfl_rebuild.env import kernel as K
from rfl_rebuild.learner.reference import QReferenceView
from rfl_rebuild.learner.store import LearnerPersistentState, QAddress, DecisionAddress, Edit, Q, DECISION, PROCESS, CONTROLLER, ReferenceContractError

CONTRACT = json.loads((HERE / 'contract.json').read_bytes())
COUNTS, CASE_COUNTS = Counter(), Counter()
STARTED = time.monotonic()
CASE, VARIANT, STAGE = 'setup', 'none', 'setup'
LAST_SWEEP, SWEEP_CALLS, PRE_CALLS, CORE = None, 0, [], []
RECORDS = 0


def emit(tag, payload):
    global RECORDS
    RECORDS += 1
    print(json.dumps({'tag': tag, 'case': CASE, 'stage': STAGE, 'payload': A.wire(payload)},
                     sort_keys=True, separators=(',', ':'), ensure_ascii=True), flush=True)


def handler(frame, event, arg):
    global LAST_SWEEP, SWEEP_CALLS
    path, name = frame.f_code.co_filename.replace('\\', '/'), frame.f_code.co_name
    kernel = path.endswith('rfl_rebuild/env/kernel.py')
    store = path.endswith('rfl_rebuild/learner/store.py')
    native_b1 = path.endswith('rfl_rebuild/b1/runner.py') and name in ('run_patch_law', 'run_dq_law')
    td = '/complete_curve_source_gates_v105/variants/' in path and path.endswith('/td.py')
    learning = '/complete_curve_source_gates_v105/variants/' in path and path.endswith('/learning.py')
    if event == 'call':
        counted = name if kernel and name in ('step', 'rollout') else 'transaction' if store and name == 'apply_transaction' else 'B1' if native_b1 else None
        if counted:
            COUNTS[counted] += 1
            CASE_COUNTS[counted] += 1
            if COUNTS[counted] > CONTRACT['budget'][counted]:
                raise RuntimeError('prospective finite budget exhausted: ' + counted)
        if (path.endswith('rfl_rebuild/b2/training.py') and name in ('derive', 'key', 'mix', 'train_curve')) or (kernel and name == 'sample') or (path.endswith('rfl_rebuild/solve/dp.py') and name == 'solve_reference') or (path.endswith('random.py') and name in ('__init__', 'random', 'randrange')) or frame.f_code.co_qualname in ('FutureTrainingProtocol.__init__', 'Curve.__init__'):
            COUNTS['forbidden'] += 1
            raise RuntimeError('ungranted formal/RNG/DP path: ' + name)
        if time.monotonic() - STARTED > CONTRACT['budget']['seconds']:
            raise RuntimeError('prospective wall budget exhausted')
        if store and name == 'apply_transaction':
            emit('TX_CALL', {'before': A.stores(frame.f_locals['self']), 'edits': frame.f_locals['edits']})
        if td and name == 'sweep_edits':
            SWEEP_CALLS += 1
            emit('SOURCE_TD_ENTER', {'source': path, 'source_sha256': hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                                    'before': A.stores(frame.f_locals['learner']), 'trace': frame.f_locals['trace']})
        if path.endswith('rfl_rebuild/b2/training.py') and name == 'pre_level':
            if VARIANT != 'remeasure_pre' or STAGE != 'curve':
                raise RuntimeError('unexpected shared-pre remeasurement')
            PRE_CALLS.append(None)
            emit('ACTUAL_PRE_REMEASUREMENT_ENTER', {'sample': frame.f_locals['sample']})
    elif event == 'return':
        if kernel and name == 'step' and type(arg) is K.StepResult:
            emit('RAW_STEP', {'pre_state': frame.f_locals['state'], 'pre_control': frame.f_locals['control'],
                              'a_cmd': frame.f_locals['a_cmd'], 'result': arg})
        elif kernel and name == 'rollout':
            emit('RAW_ROLLOUT' if type(arg) is K.RolloutTrace else 'INCOMPLETE_ROLLOUT', arg)
        elif store and name == 'apply_transaction':
            emit('TX_RETURN', {'after': A.stores(frame.f_locals['self'])})
        elif native_b1 and type(arg) is O.base.native_b1.B1Result:
            emit('NATIVE_B1_RETURN', {'law': frame.f_locals['law'].name, 'full_post': A.stores(arg.post_state),
                                     'ledger_canonical': arg.ledger.canonical(), 'receipts': arg.ledger.receipts})
        elif td and name == 'sweep_edits':
            LAST_SWEEP = {'source': path, 'current_address': frame.f_locals.get('q_j'),
                          'actual_pre_state': frame.f_locals.get('state_j'),
                          'actual_pre_control': frame.f_locals.get('control_j'),
                          'actual_result': frame.f_locals.get('result'), 'edits': arg}
            emit('SOURCE_TD_RETURN' if type(arg) is tuple else 'SOURCE_TD_INTERRUPTED', LAST_SWEEP)
        elif learning and name == 'train_episode' and isinstance(arg, dict):
            CORE.append(arg)
            emit('CORE_EPISODE', arg)
        elif path.endswith('rfl_rebuild/b2/training.py') and name == 'pre_level' and isinstance(arg, float):
            PRE_CALLS[-1] = arg.hex()
            emit('ACTUAL_PRE_REMEASUREMENT_RETURN', {'mean_hex': arg.hex()})


def interesting(code):
    p, n, q = code.co_filename.replace('\\', '/'), code.co_name, code.co_qualname
    return ((p.endswith('rfl_rebuild/env/kernel.py') and n in ('step', 'rollout', 'sample')) or
            (p.endswith('rfl_rebuild/learner/store.py') and n == 'apply_transaction') or
            (p.endswith('rfl_rebuild/b1/runner.py') and n in ('run_patch_law', 'run_dq_law')) or
            (p.endswith('rfl_rebuild/b2/training.py') and n in ('derive', 'key', 'mix', 'train_curve', 'pre_level')) or
            (p.endswith('rfl_rebuild/solve/dp.py') and n == 'solve_reference') or
            (p.endswith('random.py') and n in ('__init__', 'random', 'randrange')) or
            q in ('FutureTrainingProtocol.__init__', 'Curve.__init__') or
            ('/complete_curve_source_gates_v105/variants/' in p and
             ((p.endswith('/td.py') and n == 'sweep_edits') or
              (p.endswith('/learning.py') and n == 'train_episode'))))


DISPATCH = {}


def observe(frame, event, arg):
    code = frame.f_code
    item = DISPATCH.get(id(code))
    if item is None:
        item = (code, interesting(code))
        DISPATCH[id(code)] = item
    if item[1]:
        handler(frame, event, arg)


def load(variant):
    prefix = 'v105_' + variant
    modules = []
    for suffix, filename in (('td', 'td.py'), ('learning', 'learning.py'), ('curve', 'owned_curve.py'), ('external', 'external.py')):
        name = prefix + '_' + suffix
        if name not in sys.modules:
            path = HERE / 'variants' / variant / filename
            spec = importlib.util.spec_from_file_location(name, path)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[name] = mod
            spec.loader.exec_module(mod)
        modules.append(sys.modules[name])
    return modules


def reference():
    spec = CONTRACT['reference_input']
    raw = (ROOT / spec['path']).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == spec['sha256']
    rows = {}
    for line in raw.decode('utf-8').splitlines():
        if line.startswith('DECISION_CONTEXT='):
            item = json.loads(line.split('=', 1)[1]); x, y, t, k, phi, z, m = item['context']
            rows[K.State(x, y, t, k, phi), z, m] = {a: float.fromhex(v) for a, v in item['q_row_hex']}
    ref = QReferenceView(rows, name='v105-same-declared-nominal-Q-star')
    assert ref.digest() == spec['q_digest']
    emit('REFERENCE', {'digest': ref.digest(), 'rows': len(ref)})
    return ref


def make_source(ref, mode, healthy):
    # Canonical legal mechanism definition; outcomes are not used to select it.
    contexts = [DecisionAddress(K.State(*K.START, t, 0, 2), 1, m) for t in range(K.HORIZON) for m in (0, 1)]
    contexts += [DecisionAddress(K.State(1, 2, 1, 0, 2), 1, m) for m in (0, 1)]
    sentinel = DecisionAddress(K.State(*K.START, 0, 1, 2), 1, 0)
    contexts.append(sentinel)
    sites = ((K.ControllerSite(K.State(*K.START, 0, 0, 2), K.WAIT), K.RIGHT),
             (K.ControllerSite(K.State(1, 2, 1, 0, 2), K.WAIT), K.LEFT),
             (K.ControllerSite(sentinel.state, K.WAIT), K.RIGHT))
    legality = []
    for site, target in sites:
        served = [(z, m, tuple(ref.row(site.state, z, m))) for z in K.option_ids() for m in (0, 1)
                  if site.cmd in ref.row(site.state, z, m)]
        assert served and all(target in legal for z, m, legal in served)
        legality.append({'site': site, 'target': target, 'all_serving_contexts': served})
    edits = [Edit(PROCESS, 0, 1), Edit(PROCESS, 3, 2)] + [Edit(CONTROLLER, site, target) for site, target in sites]
    for address in contexts:
        row = ref.row(address.state, address.z, address.m)
        assert K.WAIT in row
        edits.append(Edit(Q, QAddress(address.state, address.z, address.m, K.WAIT), max(row.values())+1.0)
                     if mode == 'dq' else Edit(DECISION, address, K.WAIT))
    assert len(edits) == 32 and len(contexts) == 27
    emit('SOURCE_INSTALL_PLANNED', {'mode': mode, 'edits': edits, 'legality': legality})
    pre = LearnerPersistentState()
    pre.apply_transaction(tuple(edits), q_reference=ref)
    source = O.capture_source(pre, scene=EvaluationScene(*CONTRACT['source_scene']), regime='P',
                              q_reference=ref, healthy_reference=healthy, counterfactual=False)
    emit('ORIGINAL_SOURCE', {'mode': mode, 'audit': O.source_audit(source)})
    bound = H.bind_source(source, mode=mode)
    emit('BOUND_BEFORE_ARMS', H.source_audit(bound))
    pair = H.run_whole_pair(bound, architecture='D_Q' if mode == 'dq' else 'D_patch', tier=Tier.L0_FACTUAL,
                            law_name='FactualReturnWrite' if mode == 'dq' else 'DeleteFactualPatch')
    emit('ORIGINAL_PAIR', O.pair_audit(pair, source))
    return source, bound, pair


def episodes(L):
    out = []
    for spec in CONTRACT['episodes']:
        coins = [T.M64] * K.HORIZON
        draws = [(0,)] * K.HORIZON
        if spec['epoch'] == 0:
            coins[0] = coins[1] = 0
            draws[1] = (T.M64, 4)
        out.append(L.EngineeringEpisode(spec['epoch'], spec['kappa'], spec['proposal'],
                    K.SemanticTape(spec['phase'], spec['error_flag'], spec['cause_rank']), tuple(coins), tuple(draws)))
    return tuple(out)


def state_from(s):
    return K.State(*(s[k] for k in ('x', 'y', 't', 'kappa', 'phi')))


def independent_td(receipt, ref):
    numeric = receipt['before']['current'] if receipt['before']['mode'] == 'dq' else receipt['before']['learning_values']
    def qa(item):
        return QAddress(state_from(item['state']), item['z'], item['m'], item['a'])
    work = {qa(x['address']): float.fromhex(x['value']['binary64_hex']) for x in numeric['Q']}
    inp = receipt['episode']
    state, z, m = K.State(*K.START, 0, inp['kappa'], inp['tape']['phase']), receipt['trace']['option_in_force'], 0
    order, details = [], []
    for result in receipt['trace']['steps']:
        address = QAddress(state, z, m, result['a_cmd'])
        old = work.get(address, ref.value(address))
        target = float.fromhex(result['reward']['binary64_hex'])
        ns, nz, nm = state_from(result['state']), result['control']['z'], result['control']['m']
        if not result['terminal']:
            legal = ref.row(ns, nz, nm)
            target += max(work.get(QAddress(ns, nz, nm, a), ref.value(QAddress(ns, nz, nm, a))) for a in legal)
        new = old + 0.5*(target-old)
        work[address] = new
        if address not in order:
            order.append(address)
        details.append({'address': address, 'current_hex': old.hex(), 'target_hex': target.hex(), 'updated_hex': new.hex()})
        state, z, m = ns, nz, nm
    return A.wire(tuple(Edit(Q, q, float(work[q])) for q in order)), details


def independent_coordinates(receipt, declared):
    expected, draws = [], []
    for i, row in enumerate(receipt['draws']):
        coin = declared.coins[i]
        expected.append((i, 0, 0, coin))
        explore = coin*10 < (1 << 64)
        action = row['a_cmd']
        if explore:
            allowed = tuple(row['admissible'])
            limit = (1 << 64) - ((1 << 64) % len(allowed))
            for c, r in enumerate(declared.rejections[i]):
                expected.append((i, 1, c, r))
                if r < limit:
                    action = allowed[r % len(allowed)]
                    break
            else:
                raise AssertionError('declared finite rejection exhausted')
        draws.append({'i': i, 'explore': explore, 'a_cmd': action})
    return A.wire(expected), draws


def verify_complete(C, E, bundle, handles, stream, ref):
    failures, details = [], []
    curves = []
    for handle in handles:
        record = C.curve_audit(handle)
        curves.append(record)
        emit('COMPLETE_ROLE_CURVE', record)
        assert [x['epoch'] for x in record['checkpoints']] == [0, 1, 2]
        assert [x['epoch'] for x in record['training']] == [0, 1]
        for receipt in record['training']:
            expected, td = independent_td(receipt, ref)
            coords, actions = independent_coordinates(receipt, stream[receipt['epoch']])
            td_ok = expected == receipt['numeric_edits']
            coordinate_ok = (receipt['episode'] == A.wire(stream[receipt['epoch']]) and coords == receipt['coordinates'] and
                             all(x['explore'] == y['explore'] and x['a_cmd'] == y['a_cmd'] for x, y in zip(actions, receipt['draws'])))
            emit('INDEPENDENT_EXPECTATION', {'role': record['role'], 'epoch': receipt['epoch'], 'TD': td,
                 'expected_edits': expected, 'expected_coordinates': coords, 'expected_draws': actions,
                 'td_matches': td_ok, 'coordinate_matches': coordinate_ok})
            if not td_ok:
                failures.append('chronological_TD')
            if not coordinate_ok:
                failures.append('exact_coordinate_stream')
            assert receipt['before']['immediate'] == receipt['after']['immediate']
            for channel in ('P', 'X'):
                assert receipt['before']['current'][channel] == receipt['after']['current'][channel]
            if receipt['epoch'] == 0:
                assert receipt['trace']['base_option'] == 0 and receipt['trace']['option_in_force'] == 1
                actual = receipt['draws'][1]
                assert actual['i'] == 1 and len(actual['admissible']) == 5 and actual['explore']
                details.append({'role': record['role'], 'true_n5_step': actual,
                                'actual_calls': [c for c in receipt['coordinates'] if c[0] == 1]})
        for checkpoint in record['checkpoints']:
            total = 0.0
            for trace in checkpoint['traces']:
                episode_return = 0.0
                for step in trace['steps']:
                    episode_return += float.fromhex(step['reward']['binary64_hex'])
                total += episode_return
            assert (total/len(checkpoint['traces'])).hex() == checkpoint['mean_hex']
        view = E.read(E.build(handle))
        emit('EXTERNAL_VIEW', dict(view, fields=dict(view['fields'])))
        if view['pre_level'] != CONTRACT['shared_v_pre']:
            failures.append('shared_pre_level')
    if PRE_CALLS:
        failures.append('pre_level_remeasurement')
    assert C.audit(bundle)['completed']
    return sorted(set(failures)), details


def run_case(ref, healthy, variant, mode):
    global CASE, VARIANT, STAGE, CASE_COUNTS, LAST_SWEEP, SWEEP_CALLS, PRE_CALLS, CORE
    CASE, VARIANT, STAGE = variant + ':' + mode, variant, 'source'
    CASE_COUNTS, LAST_SWEEP, SWEEP_CALLS, PRE_CALLS, CORE = Counter(), None, 0, [], []
    _td, L, C, E = load(variant)
    emit('CASE_BEGIN', {'variant': variant, 'mode': mode,
                        'physical_sources': json.loads((HERE/'variant_manifest.json').read_bytes())['variants'][variant]})
    source, bound, pair = make_source(ref, mode, healthy)
    stream = episodes(L)
    bundle = C.prepare_curve(bound, pair, episodes=stream, evaluation_indices=tuple(CONTRACT['evaluation_indices']))
    before = C.audit(bundle)
    emit('CURVE_PREPARED', before)
    STAGE = 'curve'
    failure, handles = None, None
    try:
        handles = C.run_pair_curve(bundle)
    except (A.ProtocolError, ReferenceContractError) as exc:
        failure = {'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc(),
                   'sweep_calls': SWEEP_CALLS, 'last_source_sweep': LAST_SWEEP,
                   'immediate_states': [A.stores(a._immediate) for a in C._BUNDLES[bundle].actors],
                   'current_states': [A.stores(a._current) for a in C._BUNDLES[bundle].actors],
                   'initial_immediate': [a._initial for a in C._BUNDLES[bundle].actors],
                   'attempted': C._ATTEMPTED[bundle], 'complete_handle_issued': bundle in C._COMPLETED}
        emit('ACTUAL_TARGET_EXCEPTION', failure)
    STAGE = 'verification'
    if failure is not None:
        assert handles is None and not failure['complete_handle_issued'] and failure['attempted']
        if variant == 'post_address':
            q, post, pre = LAST_SWEEP['current_address'], LAST_SWEEP['actual_result'], LAST_SWEEP['actual_pre_state']
            assert SWEEP_CALLS > 0 and isinstance(q, QAddress) and q.state == post.state and q.state != pre
            assert isinstance(failure['message'], str) and ('reference has no row' in failure['message'] or 'not admissible' in failure['message'])
            reason = 'actual_post_address_outside_valid_reference'
        elif variant == 'immediate_write':
            assert 'protected immediate state changed' in failure['message'] and SWEEP_CALLS > 0
            assert failure['immediate_states'] != failure['initial_immediate']
            reason = 'actual_future_write_changed_protected_immediate'
        else:
            raise AssertionError('unexpected exception variant: ' + variant)
        before_counts = dict(CASE_COUNTS)
        try:
            C.run_pair_curve(bundle)
        except A.ProtocolError:
            pass
        else:
            raise AssertionError('partial entry accepted retry')
        assert dict(CASE_COUNTS) == before_counts
        issues, n5 = [reason], []
    else:
        assert variant not in ('post_address', 'immediate_write'), 'expected mutation survived without guard failure'
        issues, n5 = verify_complete(C, E, bundle, handles, stream, ref)
        expected_issue = {'normal': [], 'proposal_option': ['chronological_TD'],
                          'floor_draw': ['exact_coordinate_stream'],
                          'remeasure_pre': ['pre_level_remeasurement', 'shared_pre_level'],
                          'different_stream': ['exact_coordinate_stream']}[variant]
        assert issues == expected_issue, (variant, issues, expected_issue)
        assert (len(PRE_CALLS) == 2 and all(x is not None for x in PRE_CALLS)) if variant == 'remeasure_pre' else not PRE_CALLS
    # Original genuine source and immediate post must survive even faulty future copies.
    original_posts = O.pair_audit(pair, source)
    emit('ORIGINAL_PAIR_AFTER', original_posts)
    result = {'variant': variant, 'mode': mode, 'source_level_mutant_rejected': variant != 'normal',
              'normal_complete': variant == 'normal', 'issues': issues, 'actual_counts': dict(CASE_COUNTS),
              'source_sweep_calls': SWEEP_CALLS, 'actual_pre_measurements': PRE_CALLS,
              'complete_role_handles': 0 if handles is None else len(handles), 'actual_n5': n5,
              'automatic_retry': False}
    emit('CASE_RESULT', result)
    return result


def main():
    sys.setprofile(observe)
    try:
        ref = reference()
        healthy = json.loads((ROOT / CONTRACT['healthy_reference']['path']).read_bytes())
        results = []
        for variant in CONTRACT['variants']:
            for mode in ('dq', 'patch-adaptive'):
                results.append(run_case(ref, healthy, variant, mode))
        assert len(results) == 14 and sum(r['source_level_mutant_rejected'] for r in results) == 12
        assert not COUNTS['forbidden']
        loaded = {}
        for module in tuple(sys.modules.values()):
            filename = getattr(module, '__file__', None)
            if filename:
                path = Path(filename).resolve()
                if path.is_relative_to(ROOT) and path.suffix == '.py':
                    loaded[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        pins = json.loads((HERE/'evidence/claim.json').read_bytes())['input_binding_before']
        assert all(name in pins and pins[name]['sha256'] == digest for name, digest in loaded.items())
        emit('ACTUAL_LOADED_SOURCE_INVENTORY', loaded)
        emit('RESULT', {'cases': results, 'counts': dict(COUNTS), 'canonical_records_before_result': RECORDS,
                        'seconds': time.monotonic()-STARTED, 'loaded_inventory_bound': True,
                        'six_targets_both_architectures': True, 'formal_keyed_stream': False,
                        'scientific_qualification': False, 'collection_authorized': False})
    finally:
        sys.setprofile(None)


if __name__ == '__main__':
    main()

