"""Fixed actual-state battery and source-factored finite Process census; no keys."""
from __future__ import annotations
import ast
from collections import Counter
from hashlib import sha1, sha256
from itertools import product
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
PREP = HERE.parent
ROOT = PREP.parents[3]
sys.path.insert(0, str(PREP))
import readiness as ready
import factual_event_candidate as factual
from rfl_rebuild.b1.contract import fingerprint
from rfl_rebuild.b2.environment import learned_rollout
from rfl_rebuild.b2.numerics import mean
from rfl_rebuild.b2.unaffected import scene_domain
from rfl_rebuild.env import kernel as K
from rfl_rebuild.learner.reference import reference_view_from
from rfl_rebuild.learner.store import PROCESS, Edit, LearnerPersistentState
from rfl_rebuild.solve.dp import solve_reference


def require(ok, message):
    if not ok:
        raise AssertionError(message)


def canonical(obj):
    return (json.dumps(obj, ensure_ascii=True, sort_keys=True,
                       separators=(',', ':'), allow_nan=False) + '\n').encode('utf8')


def emit(tag, obj):
    raw = canonical(obj)
    print(tag + '=' + raw.decode('utf8').rstrip('\n'), flush=True)
    return raw


def bindings():
    contract = ready.read_json(HERE / 'contract.json')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip()
    require(head == contract['parent_commit'], 'parent changed')
    sources = ready.read_json(ROOT / ready.FOLDER / 'pipeline/frozen_inputs.json')['sources']
    audit = ready.read_json(ROOT / ready.FOLDER / 'pipeline/full_f1_complete_external_audit.json')['audit']
    native = audit['fixed_native_file_hashes'] | audit['post_controller_commit_native_tail_hashes']
    tree = {}
    for row in subprocess.check_output(['git', 'ls-tree', '-r', '-z', head], cwd=ROOT).split(b'\0'):
        if row:
            meta, name = row.split(b'\t', 1)
            tree[name.decode('utf8')] = meta.split()[2].decode()
    prior = {p for p in tree if p.startswith(PREP.relative_to(ROOT).as_posix() + '/')}
    bound = set(sources) | prior | {'experiments/rebuild_status_current.json'}
    want = contract['expected_parent']
    require((len(sources), len(native), len(prior), len(bound)) ==
            (want['sources'], want['native'], want['prior_preparation'], want['HEAD_byte_bindings']),
            'parent extent changed')
    for p in sorted(bound):
        raw = (ROOT / p).read_bytes()
        require(sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() == tree[p], p)
    for p, digest in (sources | native).items():
        require(sha256((ROOT / p).read_bytes()).hexdigest() == digest, p)
    names = bound | set(native) | {p.relative_to(ROOT).as_posix() for p in
                                 (HERE / 'candidate.py', HERE / 'contract.json', HERE / 'execute.py')}
    require(len(names) == want['runtime_inputs'], 'runtime extent changed')
    return {'parent_HEAD': head, 'parent_HEAD_bindings': len(bound),
            'input_sha256': {p: sha256((ROOT / p).read_bytes()).hexdigest() for p in sorted(names)}}


def state_payload(state):
    s = state.snapshot()
    require(not s.q_overrides and not s.decision_overrides and not s.controller_overrides,
            'Process-only predictor cannot cover other defective stores')
    return {'process': sorted([[k, v] for k, v in s.process_overrides.items()]),
            'q': [], 'decision': [], 'controller': [], 'healthy': s.healthy,
            'fingerprint': fingerprint(state)}


def raw_scene(trace, scene):
    rows = factual._trace_payload(trace, scene)
    names = ['pre_state', 'z', 'm', 'a_cmd', 'u', 'a_realized', 'reward_hex',
             'post_state', 'post_control', 'terminal', 'outcome', 'illegal']
    return {'scene': list(scene.key), 'outcome': trace.outcome,
            'return_hex': float(trace.return_value).hex(), 'z_in_force': trace.option_in_force,
            'trace': [[r[n] for n in names] for r in rows]}


def source_proof():
    p = ROOT / 'src/rfl_rebuild/env/kernel.py'
    root = ast.parse(p.read_text(encoding='utf8'))
    fs = {n.name: n for n in root.body if isinstance(n, ast.FunctionDef)}
    step = fs['step']
    require(not any(isinstance(n, ast.Name) and n.id == 'tape' for n in ast.walk(step)),
            'step now reads semantic tape; reduction invalid')
    cont = fs['continue_rollout']
    parents = {c: n for n in ast.walk(cont) for c in ast.iter_child_nodes(n)}
    for n in ast.walk(cont):
        if isinstance(n, ast.Name) and n.id in ('base_option', 'option_in_force'):
            parent = parents[n]
            require(isinstance(parent, ast.keyword) and parent.arg == n.id and
                    isinstance(parents[parent], ast.Call) and
                    isinstance(parents[parent].func, ast.Name) and
                    parents[parent].func.id == 'RolloutTrace',
                    'proposal affects continuation, reduction invalid')
    paths = ['src/rfl_rebuild/env/kernel.py', 'src/rfl_rebuild/learner/store.py',
             'src/rfl_rebuild/b2/environment.py', 'src/rfl_rebuild/solve/dp.py']
    return {'role': 'SOURCE_BOUND_PROCESS_ONLY_REDUCTION_NOT_NATIVE_WORLD_CENSUS',
            'source_sha256': {n: sha256((ROOT / n).read_bytes()).hexdigest() for n in paths},
            'step_no_tape_read_AST': True, 'continuation_proposal_only_trace_provenance_AST': True,
            'assumptions': ['all other persistent stores empty', 'no mask or evaluator do',
                            'original Q-reference argmax and automaton', 'committed option read once'],
            'outside_assumptions_certified': False}


def stored_pre(contract, domain):
    folder = ROOT / contract['preserved_counterexample']['folder']
    receipt = ready.read_json(folder / 'evidence/exit.json')
    raw = (folder / 'evidence/stdout.log').read_bytes()
    digest = sha256(raw).hexdigest()
    require(receipt['native_child_exit_code'] == 0 and digest ==
            receipt['files']['stdout.log']['sha256'] ==
            contract['preserved_counterexample']['stdout_sha256'], 'stored origin differs')
    rows, h, scalar = [], sha256(), {}
    for line in raw.splitlines():
        tag, value = line.split(b'=', 1)
        obj = json.loads(value)
        require(canonical(obj).rstrip(b'\n') == value, 'stored noncanonical payload')
        if tag == b'PRE_SCENE':
            rows.append(obj)
            h.update(canonical(obj))
        elif tag != b'POST_SCENE':
            require(tag not in scalar, 'stored duplicate scalar stage')
            scalar[tag] = obj
    require([tuple(r['scene']) for r in rows] == [s.key for s in domain], 'stored U2 incomplete')
    require(h.hexdigest() == contract['preserved_counterexample']['canonical_pre_map_sha256'],
            'stored full canonical map differs')
    event = scalar[b'FIXED_FACTUAL_EVENT']
    region = scalar[b'REGION']
    require(event['truth']['Gamma_P_star'] == contract['fixed_world']['complete_original_credit'] and
            region['complete_owners'] == contract['fixed_world']['complete_original_owners'],
            'complete original manifestation/owner changed; never trim')
    emit('STORED_PRE_ORIGIN', {'stdout_sha256': digest, 'canonical_map_sha256': h.hexdigest(),
         'native_pre_scenes_read': len(rows), 'new_pre_rollouts': 0,
         'whole_truth': event['truth'], 'complete_original_owners': region['complete_owners'],
         'stored_native_event': event, 'old_noop_repeated': False})
    return rows, region


def finite_census(basis, domain):
    counts = Counter()
    registry_hash = sha256()
    for world in product(range(4), repeat=4):
        if world == tuple(range(4)):
            continue
        outcomes = Counter()
        owners = set()
        returns = []
        region_indices = {}
        for i, s in enumerate(domain):
            b = basis[s.kappa, s.phase, world[s.base_option]]
            outcomes[b['outcome']] += 1
            returns.append(float.fromhex(b['return_hex']))
            if b['outcome'] != 'SUCCESS' and world[s.base_option] != s.base_option:
                owners.add(s.base_option)
        owner_rows = []
        for owner in sorted(owners):
            indices = [i for i, s in enumerate(domain) if s.base_option != owner and
                       basis[s.kappa, s.phase, world[s.base_option]]['outcome'] == 'SUCCESS']
            region_indices[owner] = indices
            if not indices:
                owner_rows.append({'owner': owner, 'region_size': 0, 'status': 'EMPTY_UNDEFINED',
                                   'battery': [], 'address_replacement': False})
                counts['empty_owner_regions'] += 1
                continue
            first = domain[indices[0]]
            site = first.base_option
            targets = [v for v in range(4) if v != world[site]]
            before = mean([returns[i] for i in indices])
            effects = []
            for target in targets:
                values = [float.fromhex(basis[domain[i].kappa, domain[i].phase,
                        target if domain[i].base_option == site else world[domain[i].base_option]]
                        ['return_hex']) for i in indices]
                after = mean(values)
                effects.append({'target': target, 'post_mean_hex': after.hex(),
                                'signed_difference_hex': (before - after).hex()})
            sensitive = any(float.fromhex(e['signed_difference_hex']) != 0.0 for e in effects)
            status = 'NONZERO_BATTERY_EXISTS' if sensitive else 'ALL_ZERO_UNCERTIFIED'
            counts['owner_regions'] += 1
            counts['sensitive_owner_regions' if sensitive else 'all_zero_owner_regions'] += 1
            owner_rows.append({'owner': owner, 'region_size': len(indices),
                'complete_truth': ['ProcessCommit'], 'first_region_scene': list(first.key),
                'site': site, 'actual_pre_value': world[site], 'pre_mean_hex': before.hex(),
                'status': status, 'battery': effects, 'address_replacement': False})
        counts['worlds'] += 1
        counts['trigger_worlds' if owners else 'nontrigger_worlds_retained'] += 1
        record = {'world': list(world), 'k': sum(v != i for i, v in enumerate(world)),
                  'derived_outcomes': dict(outcomes), 'actual_manifesting_failure_owners': sorted(owners),
                  'owner_regions': owner_rows, 'native_world_rollouts': 0,
                  'basis': 'source-factorized original native committed-option traces',
                  'statistical_N': None, 'scientific_population_adopted': False}
        registry_hash.update(emit('DERIVED_WORLD', record))
    return {'counts': dict(counts), 'canonical_registry_sha256': registry_hash.hexdigest(),
            'all255_including_nontriggers_retained': counts['worlds'] == 255,
            'native_world_census_executed': False, 'full_B2_totality_certified': False}


def main():
    before = bindings()
    emit('INPUT_BINDING_BEFORE', before)
    contract = ready.read_json(HERE / 'contract.json')
    emit('SOURCE_REDUCTION', source_proof())
    parent = ready.load_parent()
    healthy = ready.read_json(PREP / 'healthy_reference_candidate.json')
    ready.validate_reference(healthy, parent)
    solution = solve_reference()
    reference = reference_view_from(solution)
    require(reference.digest() == healthy['q_reference_sha256'], 'reference differs')
    require(K.option_ids() == (0, 1, 2, 3), 'Process domain changed')
    domain = scene_domain()
    require(len(domain) == 5760, 'U2 changed')
    old, rg = stored_pre(contract, domain)
    world = dict(contract['fixed_world']['proposal_mapping'])
    pre = LearnerPersistentState()
    pre.apply_transaction([Edit(PROCESS, z, v) for z, v in sorted(world.items())])
    pre_payload = state_payload(pre)
    old_event = ready.read_json(PREP / 'feasibility_v28/result_summary.json')['fixed_world']['pre']
    require(pre_payload == old_event, 'not the complete original pre-state')
    owners = contract['fixed_world']['complete_original_owners']
    indices = [i for i, r in enumerate(old) if r['outcome'] == 'SUCCESS' and r['scene'][4] not in owners]
    require([old[i]['scene'] for i in indices] == rg['region_units'], 'not original full region')
    first = domain[indices[0]]
    site = first.base_option
    require(site == contract['new_engineering_execution']['fixed_owner'] and site not in owners,
            'not same fixed legal off-full-S site')
    targets = tuple(v for v in K.option_ids() if v != world[site])
    require(list(targets) == contract['new_engineering_execution']['all_targets_selected_before_measurement'],
            'actual-state battery differs')
    emit('BATTERY_SELECTED', {'pre': pre_payload, 'owners': owners, 'region_size': len(indices),
         'first_region_scene': list(first.key), 'site': site, 'actual_pre_value': world[site],
         'targets': list(targets), 'old_target1_is_noop_preserved_not_repeated': True})
    predicted, predictions = {}, {}
    pre_values = [float.fromhex(r['return_hex']) for r in old]
    pre_errors = []
    for i, s in enumerate(domain):
        start = K.State(x=K.START[0], y=K.START[1], t=0, kappa=s.kappa, phi=s.phase)
        pre_errors.append(abs(solution.value(start, world[s.base_option], 0) - pre_values[i]))
    require(max(pre_errors) <= 1e-12, 'stored actual pre-state differs from Process-only DP prediction')
    emit('STORED_PRE_PREDICTION_CHECK', {'all5760_entries_read': True,
         'maximum_scene_prediction_error': max(pre_errors), 'new_rollouts': 0})
    pre_mean = mean([pre_values[i] for i in indices])
    for target in targets:
        values = []
        for s in domain:
            z = target if s.base_option == site else world[s.base_option]
            start = K.State(x=K.START[0], y=K.START[1], t=0, kappa=s.kappa, phi=s.phase)
            values.append(solution.value(start, z, 0))
        predicted[target] = values
        post_mean = mean([values[i] for i in indices])
        predictions[target] = pre_mean - post_mean
        emit('PREDICTION_BEFORE_ANY_POST', {'target': target, 'all_scene_return_hex': [v.hex() for v in values],
             'pre_ordered_mean_hex': pre_mean.hex(), 'predicted_post_ordered_mean_hex': post_mean.hex(),
             'signed_difference_hex': predictions[target].hex(), 'uses_measured_post': False})
    basis = {}
    all_maps = [(1, old)]
    results = []
    post_rows = 0
    for target in targets:
        post = pre.clone()
        post.apply_transaction([Edit(PROCESS, site, target)])
        post_payload = state_payload(post)
        require(post_payload['fingerprint'] != pre_payload['fingerprint'], 'actual-state no-op refused')
        expected = dict(world)
        expected[site] = target
        require(post_payload['process'] == [[z, v] for z, v in sorted(expected.items()) if z != v],
                'write changed another Process key or failed canonical identity deletion')
        emit('POST_STATE', {'target': target, 'state': post_payload, 'actual_state_changed': True})
        rows, values, h, errors = [], [], sha256(), []
        for i, s in enumerate(domain):
            tr = learned_rollout(post, kappa=s.kappa, tape=s.tape, base_option=s.base_option,
                                 q_reference=reference)
            require(tr.mask == K.FaultMask() and not tr.interventions.members, 'non-ordinary rollout')
            r = raw_scene(tr, s)
            post_rows += len(r['trace'])
            h.update(emit('POST_SCENE', {'target': target, 'payload': r}))
            rows.append(r)
            values.append(tr.return_value)
            errors.append(abs(values[-1] - predicted[target][i]))
            require(errors[-1] <= 1e-12, 'independent DP prediction mismatch')
            if s.base_option != site:
                require(r == old[i], 'untouched proposal behavior changed')
        measured_mean = mean([values[i] for i in indices])
        diff = pre_mean - measured_mean
        require(abs(diff - predictions[target]) <= max(1e-12, 1e-6 * abs(predictions[target])),
                'aggregate prediction mismatch')
        require(state_payload(pre) == pre_payload and state_payload(post) == post_payload, 'evaluation mutation')
        item = {'target': target, 'actual_state_changed': True, 'canonical_post_map_sha256': h.hexdigest(),
                'pre_ordered_mean_hex': pre_mean.hex(), 'post_ordered_mean_hex': measured_mean.hex(),
                'predicted_difference_hex': predictions[target].hex(), 'measured_difference_hex': diff.hex(),
                'maximum_scene_prediction_error': max(errors), 'native_scene_count': len(rows),
                'untouched_other_entries_and_stores': True, 'behavioral_zero_retained': diff == 0.0}
        emit('BATTERY_RESULT', item)
        results.append(item)
        all_maps.append((target, rows))
    for z, rows in all_maps:
        for r in rows:
            if r['scene'][4] == site:
                key = (r['scene'][0], r['scene'][1], z)
                b = {n: r[n] for n in ('outcome', 'return_hex', 'z_in_force', 'trace')}
                require(r['z_in_force'] == z, 'native basis committed option differs')
                if key in basis:
                    require(basis[key] == b, 'error/cause changes behavior; reduction invalid')
                basis[key] = b
    require(len(basis) == 48, 'native option basis incomplete')
    for z, rows in all_maps:
        for r in rows:
            proposal = r['scene'][4]
            effective = z if proposal == site else world[proposal]
            require({n: r[n] for n in ('outcome', 'return_hex', 'z_in_force', 'trace')} ==
                    basis[r['scene'][0], r['scene'][1], effective], 'full basis factorization mismatch')
    emit('NATIVE_BASIS', {'entries': [{'kappa': k, 'phase': p, 'committed': z, 'payload': b}
         for (k, p, z), b in sorted(basis.items())], 'entry_count': len(basis),
         'actual_stored_and_new_native_scene_checks': 4 * len(domain),
         'new_native_scene_rollouts': 3 * len(domain), 'old_native_scene_rollouts_read': len(domain),
         'source_assumptions_checked': True})
    census = finite_census(basis, domain)
    emit('FINITE_PROCESS_CENSUS', census)
    after = bindings()
    require(after == before, 'execution inputs changed')
    emit('INPUT_BINDING_AFTER', after)
    emit('FINAL', {'status': 'ACTUAL_STATE_BATTERY_AND_FINITE_PROCESS_ONLY_CENSUS_COMPLETE',
         'battery_results': results, 'finite_process_census': census,
         'new_native_post_rollouts': 3 * len(domain), 'new_native_post_trace_rows': post_rows,
         'new_native_pre_or_factual_rollouts': 0, 'native_update_law_treatment_calls': 0,
         'state_installation_transactions': 1, 'calibration_transactions': len(targets),
         'runtime_input_bindings': len(before['input_sha256']), 'before_after_inputs_equal': True,
         'whole_scientific_domain_totality': False, 'scientific_PASS': False,
         'new_scientific_rule_adopted': False, 'delta_joint_computed_or_adopted': False,
         'population_reduced': False, 'science_or_workload_keys_allocated': 0,
         'future_training': 0, 'old_fixtures_or_tests_rerun': False, 'collection_authorized': False,
         'original_mechanism_contradicted_by_this_calibration_check': False,
         'valid_current_scientific_STOP': False, 'research_complete': False})


if __name__ == '__main__':
    from rfl_rebuild.b2 import training
    with patch.object(training.ExogenousEpisode, 'derive', side_effect=AssertionError('no keys')), \
         patch.object(training, 'train_curve', side_effect=AssertionError('no training')):
        main()
