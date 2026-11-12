"""One fixed v27 actual-state calibration feasibility witness, no keys or training."""
from __future__ import annotations
from fractions import Fraction
from hashlib import sha1, sha256
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
from rfl_rebuild.b1.process import AssistedInput, resolve_process_addresses
from rfl_rebuild.b2.calibration import spillover_edit
from rfl_rebuild.b2.environment import learned_rollout
from rfl_rebuild.b2.numerics import mean
from rfl_rebuild.b2.unaffected import (CreditedSite, EvaluationScene, UnaffectedSet,
    eligibility, pre_update_traces, scene_domain)
from rfl_rebuild.env import kernel as K
from rfl_rebuild.learner.reference import reference_view_from
from rfl_rebuild.learner.store import PROCESS, Edit, LearnerPersistentState
from rfl_rebuild.method.credit import OracleCreditAdapter
from rfl_rebuild.solve.dp import solve_reference


def require(ok, message):
    if not ok:
        raise AssertionError(message)


def emit(tag, payload):
    raw = (json.dumps(payload, ensure_ascii=True, sort_keys=True,
                      separators=(',', ':'), allow_nan=False) + '\n').encode('utf8')
    print(tag + '=' + raw.decode('utf8').rstrip('\n'), flush=True)
    return raw


def bound_inputs():
    contract = ready.read_json(HERE / 'contract.json')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip()
    require(head == contract['parent_commit'], 'parent HEAD changed')
    sources = ready.read_json(ROOT / ready.FOLDER / 'pipeline/frozen_inputs.json')['sources']
    audit = ready.read_json(ROOT / ready.FOLDER / 'pipeline/full_f1_complete_external_audit.json')['audit']
    native = dict(audit['fixed_native_file_hashes'])
    native.update(audit['post_controller_commit_native_tail_hashes'])
    tree = {}
    for row in subprocess.check_output(['git', 'ls-tree', '-r', '-z', head], cwd=ROOT).split(b'\0'):
        if row:
            meta, name = row.split(b'\t', 1)
            tree[name.decode('utf8')] = meta.split()[2].decode('ascii')
    prior = {p for p in tree if p.startswith(PREP.relative_to(ROOT).as_posix() + '/')}
    bound = set(sources) | prior | {'experiments/rebuild_status_current.json'}
    want = contract['expected_parent']
    require((len(sources), len(native), len(prior), len(bound)) ==
            (want['sources'], want['native'], want['prior_preparation'], want['HEAD_byte_bindings']),
            'parent inventory extent changed')
    for name in sorted(bound):
        raw = (ROOT / name).read_bytes()
        require(sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() == tree[name], name)
    for name, digest in (sources | native).items():
        require(sha256((ROOT / name).read_bytes()).hexdigest() == digest, name)
    names = bound | set(native) | {p.relative_to(ROOT).as_posix() for p in
                                 (HERE / 'candidate.py', HERE / 'execute.py', HERE / 'contract.json')}
    require(len(names) == want['runtime_inputs'], 'runtime input extent changed')
    return {'parent_HEAD': head, 'parent_HEAD_bindings': len(bound),
            'source_count': len(sources), 'prior_preparation_count': len(prior),
            'native_count': len(native),
            'input_sha256': {p: sha256((ROOT / p).read_bytes()).hexdigest() for p in sorted(names)}}


def state_payload(state):
    snap = state.snapshot()
    require(not snap.q_overrides and not snap.decision_overrides and not snap.controller_overrides,
            'fixed Process-only witness gained another store')
    return {'process': sorted([[key, value] for key, value in snap.process_overrides.items()]),
            'q': [], 'decision': [], 'controller': [], 'healthy': snap.healthy,
            'fingerprint': fingerprint(state)}


def raw_scene(trace, scene):
    rows = factual._trace_payload(trace, scene)
    return {'scene': list(scene.key), 'outcome': trace.outcome,
            'return_hex': float(trace.return_value).hex(), 'z_in_force': trace.option_in_force,
            'trace': [[r['pre_state'], r['z'], r['m'], r['a_cmd'], r['u'], r['a_realized'],
                       r['reward_hex'], r['post_state'], r['post_control'],
                       r['terminal'], r['outcome'], r['illegal']] for r in rows]}


def joint_units(sites, traces, domain):
    require(type(sites) is tuple and sites and all(type(c) is CreditedSite for c in sites),
            'complete sites must be a nonempty nominal tuple')
    require(len(set(sites)) == len(sites) and all(c.channel == 'P' for c in sites),
            'this test-only witness supports distinct Process owners only')
    return tuple(u for u in domain if traces.successful(u)
                 and not any(traces.consults(c, u) for c in sites))


def main():
    before = bound_inputs()
    emit('INPUT_BINDING', before)
    contract = ready.read_json(HERE / 'contract.json')
    plan = ready.read_json(PREP / 'formal_validation_plan_v27.json')
    require(plan['status'] == 'DRAFT_FOR_REVIEW_NOT_ADOPTED_NOT_FROZEN_NOT_IMPLEMENTED',
            'v27 status changed')
    require(plan['calibration_proposal']['Process'] == 'minimum other option',
            'v27 fixed target changed')
    parent = ready.load_parent()
    healthy = ready.read_json(PREP / 'healthy_reference_candidate.json')
    solution = solve_reference()
    reference = reference_view_from(solution)
    ready.validate_reference(healthy, parent)
    require(reference.digest() == healthy['q_reference_sha256'], 'reference bytes differ')
    ids = K.option_ids()
    require(ids == (0, 1, 2, 3), 'original Process domain differs')
    declared = contract['fixed_world']['proposal_mapping']
    require(declared == [[z, min(set(ids) - {z})] for z in ids],
            'world is not predeclared lex-first k4 assignment')
    pre = LearnerPersistentState()
    pre.apply_transaction([Edit(PROCESS, z, target) for z, target in declared])
    fp = fingerprint(pre)
    emit('FIXED_WORLD', {'declared': declared, 'k': len(declared), 'pre': state_payload(pre),
                        'conditional_on_k4_defect_mass': [1, 81],
                        'proposed_Process_family_defect_mass': [1, 324],
                        'same_world_not_independent_seeds': True})
    domain = scene_domain()
    require(len(domain) == 5760 and len(set(domain)) == 5760, 'full native U2 changed')
    traces = pre_update_traces(learner=pre, q_reference=reference)
    pre_digest = sha256()
    outcomes = {x: 0 for x in (K.Outcome.SUCCESS, K.Outcome.COLLISION,
                              K.Outcome.TRAP, K.Outcome.TIMEOUT)}
    failure_mass = Fraction(0)
    for scene in domain:
        tr = traces.trace(scene)
        require(tr.mask == K.FaultMask() and not tr.interventions.members,
                'census gained transient fault or evaluator do')
        pre_digest.update(emit('PRE_SCENE', raw_scene(tr, scene)))
        outcomes[tr.outcome] += 1
        if tr.outcome != K.Outcome.SUCCESS:
            failure_mass += Fraction(1, 2) * Fraction(1, 6) * Fraction(1, 4) * Fraction(1, 60) * (
                Fraction(3, 5) if scene.error_flag == 0 else Fraction(2, 5))
    require(fingerprint(pre) == fp, 'pre census mutated learner')
    fixed = EvaluationScene(*contract['fixed_world']['trigger_scene'])
    audit = factual.prepare_factual_event(pre, scene=fixed, regime='P', q_reference=reference,
                 parent=parent, reference=healthy)['evaluator_audit']
    emit('FIXED_FACTUAL_EVENT', audit)
    require(factual._trace_payload(traces.trace(fixed), fixed) == audit['raw_trace'],
            'fixed original factual trace differs from full census')
    if audit['truth'] is None or not audit['truth']['Gamma_P_star']:
        require(bound_inputs() == before, 'execution inputs drifted')
        emit('FINAL', {'status': 'FIXED_WITNESS_NOT_A_TRIGGER_NO_REPLACEMENT_SEARCH',
                      'full_pre_scene_count': len(domain), 'outcomes': outcomes,
                      'counterexample_confirmed': False, 'collection_authorized': False})
        return
    truth = audit['truth']['Gamma_P_star']
    oracle = OracleCreditAdapter.evaluate(truth)
    require(oracle == frozenset(truth), 'Oracle lost complete manifestation')
    require(oracle == frozenset(('ProcessCommit',)), 'full actual credit has extra channels; never trim')
    owners = resolve_process_addresses(tuple(truth), AssistedInput(fixed.base_option))
    sites = tuple(CreditedSite('P', z) for z in owners)
    units = joint_units(sites, traces, domain)
    require(len(sites) == 1 and units == eligibility(sites[0], traces),
            'complete singleton set differs from original E(c)')
    conditional_trigger_mass = Fraction(1, 4800) / failure_mass
    emit('REGION', {'complete_truth': truth, 'complete_owners': list(owners),
                   'full_U2': len(domain), 'pre_outcomes': outcomes, 'region_size': len(units),
                   'region_units': [list(u.key) for u in units],
                   'canonical_pre_scenes_sha256': pre_digest.hexdigest(),
                   'trigger_original_scene_mass': [1, 4800],
                   'trigger_failure_conditional_mass': [conditional_trigger_mass.numerator,
                                                        conditional_trigger_mass.denominator],
                   'full_failure_mass': [failure_mass.numerator, failure_mass.denominator]})
    if not units:
        require(bound_inputs() == before, 'execution inputs drifted')
        emit('FINAL', {'status': 'PROPOSED_DOMAIN_EMPTY_REGION_COUNTEREXAMPLE',
                      'counterexample_confirmed': True, 'region_size': 0,
                      'future_training_episodes': 0, 'scientific_PASS': False,
                      'collection_authorized': False, 'research_complete': False})
        return
    region = UnaffectedSet(units=units, construction='V27_TEST_ONLY_COMPLETE_PROCESS_INTERSECTION')
    injection = spillover_edit('P', traces, 'eligible_all', solution=solution, c_cal=sites[0])
    first = units[0]
    require(injection.unit == first and injection.channel_address == first.base_option,
            'original selection is not lex first eligible off-S Process site')
    require(injection.target == min(set(ids) - {first.base_option}),
            'original least-other target changed')
    require(injection.channel_address not in owners, 'injection touched a credited owner')
    post = pre.clone()
    post.apply_transaction([injection.substrate_edit])
    post_fp = fingerprint(post)
    state_equal = state_payload(post) == state_payload(pre)
    prediction = {'basis': 'identical complete canonical learner state, before any post measurement',
                  'same_all_store_payload': state_equal,
                  'scene_difference': 0.0 if state_equal else None,
                  'aggregate_difference': 0.0 if state_equal else None,
                  'does_not_use_measured_post_or_healthy_Q_continuation': True}
    emit('CALIBRATION_PREDICTION_BEFORE_POST', {'first_region_scene': list(first.key),
         'site': injection.site.render(), 'target': injection.target,
         'prior_effective_value': pre.snapshot().process_overrides.get(injection.channel_address,
                                                                     injection.channel_address),
         'off_all_complete_S': True, 'pre': state_payload(pre), 'post': state_payload(post),
         'prediction': prediction})
    post_digest = sha256()
    post_values = {}
    max_error = 0.0
    for scene in domain:
        tr = learned_rollout(post, kappa=scene.kappa, tape=scene.tape,
                             base_option=scene.base_option, q_reference=reference)
        payload = raw_scene(tr, scene)
        post_digest.update(emit('POST_SCENE', payload))
        post_values[scene] = tr.return_value
        if state_equal:
            require(payload == raw_scene(traces.trace(scene), scene),
                    'identical state produced different native full trace')
            max_error = max(max_error, abs(traces.trace(scene).return_value - tr.return_value))
    pre_mean = mean([traces.trace(u).return_value for u in region.units])
    post_mean = mean([post_values[u] for u in region.units])
    measured = pre_mean - post_mean
    require(fingerprint(pre) == fp and fingerprint(post) == post_fp,
            'observation mutated a learner')
    confirmed = state_equal and measured == 0.0 and prediction['aggregate_difference'] == 0.0
    require(bound_inputs() == before, 'execution input bytes changed')
    emit('FINAL', {'status': 'V27_UNIVERSAL_NONZERO_CALIBRATION_COUNTEREXAMPLE' if confirmed
                  else 'FIXED_WITNESS_NOT_A_NOOP_COUNTEREXAMPLE_NO_REPLACEMENT_SEARCH',
         'counterexample_confirmed': confirmed, 'all_actual_manifestations': truth,
         'original_resolved_owners': list(owners), 'installed_entries': len(declared),
         'region_size': len(units), 'proper_region': len(units) < len(domain),
         'first_region_scene': list(first.key), 'injection_owner': injection.channel_address,
         'injection_target': injection.target, 'same_all_stores': state_equal,
         'pre_ordered_mean_hex': pre_mean.hex(), 'post_ordered_mean_hex': post_mean.hex(),
         'independent_predicted_difference': prediction['aggregate_difference'],
         'measured_difference': measured, 'maximum_scene_difference': max_error,
         'canonical_pre_scenes_sha256': pre_digest.hexdigest(),
         'canonical_post_scenes_sha256': post_digest.hexdigest(),
         'native_pre_scene_rollouts': len(domain), 'native_post_scene_rollouts': len(domain),
         'native_fixed_event_rollouts': audit['native_rollout_count'],
         'native_B1_law_calls': 0, 'installation_transactions': 1, 'calibration_transactions': 1,
         'before_after_input_bindings_equal': True, 'runtime_input_files': len(before['input_sha256']),
         'full_proposed_domain_totality_certified': False, 'delta_joint_computed_or_adopted': False,
         'new_scientific_rule_adopted': False, 'population_reduced': False,
         'future_training_episodes': 0, 'scientific_or_workload_keys_allocated': 0,
         'old_tests_or_fixtures_rerun': False, 'scientific_PASS': False,
         'valid_current_scientific_STOP': False, 'collection_authorized': False,
         'research_complete': False})


if __name__ == '__main__':
    from rfl_rebuild.b2 import training
    with patch.object(training.ExogenousEpisode, 'derive', side_effect=AssertionError('no keys permitted')), \
         patch.object(training, 'train_curve', side_effect=AssertionError('no future training permitted')):
        main()
