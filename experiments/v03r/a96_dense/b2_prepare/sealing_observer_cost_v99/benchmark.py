"""Bounded stdlib-only cost attribution on actual stored v98 raw records.

WIRE shapes are not RFL objects/issued handles. Only the two pure wire/seal
functions and the observer function are AST-extracted; no old test, checker,
native module, constructor or main is imported or executed.
"""
import ast
from collections import Counter
from dataclasses import dataclass, fields, is_dataclass, make_dataclass
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import sys
import time

from observer import interesting, make_observer

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
C = json.loads((HERE/'contract.json').read_bytes())
START = time.monotonic()


def emit(tag, payload):
    print(json.dumps({'tag': tag, 'payload': payload}, sort_keys=True,
                     separators=(',', ':'), ensure_ascii=True), flush=True)


def extract(path, names, namespace):
    raw = (ROOT/path).read_bytes()
    assert sha256(raw).hexdigest() == C['inputs'][path]
    tree = ast.parse(raw.decode('utf-8-sig'))
    nodes = [x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name in names]
    assert {x.name for x in nodes} == set(names)
    module = ast.Module(body=nodes, type_ignores=[])
    exec(compile(module, path, 'exec'), namespace)
    return {x.name: sha256(ast.dump(x, include_attributes=False).encode()).hexdigest() for x in nodes}


SHAPES = {name: make_dataclass('WireShape_'+name, [(k, object) for k in keys],
                              frozen=True, slots=True)
          for name, keys in {
              'State': ('x', 'y', 't', 'kappa', 'phi'),
              'Control': ('z', 'm'),
              'Mask': ('decision', 'controller', 'plant', 'trap'),
              'Interventions': ('members',),
              'Step': ('state', 'control', 'a_cmd', 'u', 'a_realized', 'reward', 'terminal', 'outcome', 'illegal'),
              'Trace': ('steps', 'outcome', 'control', 'mask', 'interventions', 'base_option', 'option_in_force'),
              'Scene': ('kappa', 'phase', 'error_flag', 'cause_rank', 'base_option'),
              'Record': ('scene', 'trace'),
          }.items()}


def shape(name, values):
    cls = SHAPES[name]
    assert set(values) == {f.name for f in fields(cls)}
    return cls(**values)


def decode_record(scene, trace):
    steps = []
    for step in trace['steps']:
        d = dict(step)
        d['state'], d['control'] = shape('State', d['state']), shape('Control', d['control'])
        d['reward'] = float.fromhex(d['reward']['binary64_hex'])
        steps.append(shape('Step', d))
    d = dict(trace)
    d['steps'] = tuple(steps)
    d['control'] = shape('Control', d['control'])
    d['mask'] = shape('Mask', d['mask'])
    d['interventions'] = shape('Interventions', {'members': tuple(d['interventions']['members'])})
    return shape('Record', {'scene': shape('Scene', dict(zip(
        ('kappa', 'phase', 'error_flag', 'cause_rank', 'base_option'), scene))), 'trace': shape('Trace', d)})


def old_profile_namespace():
    # Ordinary sealing frames never touch K/A/emit; assertion prevents a hidden
    # event from silently being mistaken for a native function in this probe.
    def forbidden_emit(*args):
        raise AssertionError('native/capture event in pure cost probe')
    ns = {'CODE_INFO': {}, 'COUNTS': Counter(), 'CONTRACT': {'budget': {}},
          'STARTED': START, 'time': time, 'emit': forbidden_emit}
    pins = extract(C['observer_source'], ('profile',), ns)
    return ns['profile'], pins


def timed(label, operation, profile=None):
    assert time.monotonic()-START < C['budget']['seconds']
    start = time.perf_counter()
    previous = sys.getprofile()
    assert previous is None
    try:
        if profile is not None:
            sys.setprofile(profile)
        result = operation()
    finally:
        sys.setprofile(previous)
    seconds = time.perf_counter()-start
    emit('TIMING', {'label': label, 'seconds': seconds, 'result_sha256': result,
                    'profile_restored': sys.getprofile() is previous})
    return result, seconds


def observer_action_codes(tree, filename):
    # Entire finite observer predicates' vocabularies, not learner scenarios.
    names = ('step', 'rollout', 'sample', 'apply_transaction', 'run_patch_law',
             'run_dq_law', 'run_process_law', 'run_controller_law', 'derive',
             'key', 'mix', 'train_curve', 'pre_level', 'solve_reference',
             '__init__', 'random', 'randrange', '_ordinary_bank', 'unwatched')
    paths = ('rfl_rebuild/env/kernel.py', 'rfl_rebuild/learner/store.py',
             'rfl_rebuild/b1/runner.py', 'rfl_rebuild/b2/training.py',
             'rfl_rebuild/solve/dp.py', 'random.py', 'probe/ruler.py', 'probe/ordinary.py')
    qualnames = ('normal', 'FutureTrainingProtocol.__init__', 'Curve.__init__')
    calls = next(x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == 'profile')
    labels = [x for x in calls.body if isinstance(x, ast.Assign) and any(
        isinstance(t, ast.Name) and t.id in ('kernel', 'store', 'b1') for t in x.targets)]
    branch = next(x for x in calls.body if isinstance(x, ast.If)
                  and isinstance(x.test, ast.Compare)
                  and isinstance(x.test.left, ast.Name) and x.test.left.id == 'event')
    call_branch = branch.body
    forbidden_assignment = next(x for x in call_branch if isinstance(x, ast.Assign)
        and isinstance(x.targets[0], ast.Name) and x.targets[0].id == 'forbidden')
    kind_assignment = call_branch[0]
    decisions = ast.Module(body=labels+[kind_assignment, forbidden_assignment], type_ignores=[])
    compiled = compile(decisions, filename, 'exec')
    checked = 0
    for path in paths:
        for name in names:
            for qualname in qualnames:
                ns = {'path': path, 'name': name, 'qualname': qualname}
                exec(compiled, ns)
                legacy_action = bool(ns['kind'] or ns['forbidden'] or
                    (ns['kernel'] and name == 'rollout') or
                    (ns['store'] and name == 'apply_transaction') or
                    ns['b1'] or (path.endswith('/ruler.py') and name == '_ordinary_bank'))
                # Pure code metadata proxy; never a State/Trace/native callable.
                code = type('CodeMetadata', (), {'co_filename': path, 'co_name': name, 'co_qualname': qualname})()
                assert interesting(code) == legacy_action, (path, name, qualname)
                checked += 1
    emit('OBSERVER_PREDICATE_EQUIVALENCE', {'metadata_combinations': checked,
        'basis': 'exact finite path/name/qualname predicate partitions', 'native_calls': 0})


def main():
    for path, expected in C['inputs'].items():
        assert sha256((ROOT/path).read_bytes()).hexdigest() == expected, path
    before = set(sys.modules)
    ns = {'fields': fields, 'is_dataclass': is_dataclass, 'Fraction': Fraction,
          'sha256': sha256, 'json': json}
    wire_pins = extract(C['seal_source'], ('encode', 'seal'), ns)
    for source_path, original_names in C['shape_schema_sources'].items():
        schema = ast.parse((ROOT/source_path).read_text(encoding='utf-8-sig'))
        for original_name, shape_name in original_names.items():
            node = next(x for x in schema.body if isinstance(x, ast.ClassDef) and x.name == original_name)
            names = {x.target.id for x in node.body if isinstance(x, ast.AnnAssign) and isinstance(x.target, ast.Name)}
            assert names == {f.name for f in fields(SHAPES[shape_name])}, original_name
    tree = ast.parse((ROOT/C['observer_source']).read_text(encoding='utf-8-sig'))
    observer_action_codes(tree, C['observer_source'])
    banks = {'reference': [], 'treatment': []}
    with (ROOT/C['raw_input']).open(encoding='ascii') as stream:
        lines = 0
        for line in stream:
            row = json.loads(line)
            lines += 1
            p = row['payload']
            if row['tag'] == 'RAW_ROLLOUT' and row['mode'] == 'dq' and p['stage'] in banks:
                record = decode_record(p['scene'], p['trace'])
                assert ns['encode'](record.trace) == p['trace']
                banks[p['stage']].append(record)
    assert lines == 16824 and all(len(x) == 5520 for x in banks.values())
    records = tuple(tuple(banks[role]) for role in ('reference', 'treatment'))
    timings = {}
    for count in C['sample_prefixes_per_role']:
        sample = tuple(bank[:count] for bank in records)
        baseline, timings[f'{count}_off'] = timed(f'prefix_{count}_profile_off', lambda: ns['seal'](sample))
        old, _ = old_profile_namespace()
        old_result, timings[f'{count}_legacy'] = timed(f'prefix_{count}_legacy_global_profile', lambda: ns['seal'](sample), old)
        old, observer_pins = old_profile_namespace()
        revised = make_observer(old)
        new_result, timings[f'{count}_sparse'] = timed(f'prefix_{count}_sparse_profile', lambda: ns['seal'](sample), revised)
        assert baseline == old_result == new_result
    full, timings['full_off'] = timed('all_11040_post_records_profile_off', lambda: ns['seal'](records))
    old, _ = old_profile_namespace()
    full_new, timings['full_sparse'] = timed('all_11040_post_records_sparse_profile', lambda: ns['seal'](records), make_observer(old))
    assert full == full_new
    assert not any(x.startswith('rfl_rebuild') for x in sys.modules)
    assert not (set(sys.modules)-before) & {'instrument', 'ruler', 'transfer', 'adaptive_training', 'handoff'}
    emit('RESULT', {'status': 'FIRST_PURE_OFFLINE_COST_PROBE_COMPLETE', 'raw_lines_read': lines,
        'post_wire_shapes': 11040, 'wire_ast_pins': wire_pins, 'observer_ast_pins': observer_pins,
        'timings': timings, 'all_same_input_digests_equal': True,
        'profile_restored': sys.getprofile() is None, 'RFL_import': False,
        'native_step_rollout_B1_TX_keys_DP_training_collector': 0,
        'v98_timeout_cause_uniquely_proven': False,
        'new_observer_native_qualification': False, 'scientific_qualification': False})


if __name__ == '__main__':
    main()
