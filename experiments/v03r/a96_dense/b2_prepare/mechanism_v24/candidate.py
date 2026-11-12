"""Test-only causal-chain checks. No collector, RNG, training or science endpoint.

Joint nonconsult is implemented only as an experimental ruler. Fixture B has
literal test sites, NOT Oracle units from one episode; no production totality
claim is made. All output is engineering mechanism evidence, not seed samples.
"""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha1, sha256
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
PREP = HERE.parent
ROOT = PREP.parents[3]
sys.path.insert(0, str(PREP))
import readiness as ready
import factual_event_candidate as factual
from rfl_rebuild.b1.contract import fingerprint
from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b1.laws import DQLocalOracleRestore, FactualReturnWrite, NoWriteRef
from rfl_rebuild.b1.runner import run_dq_law
from rfl_rebuild.b1.targets import resolve_credited_units
from rfl_rebuild.b1.tier import Tier
from rfl_rebuild.b2 import calibration, collateral, environment, unaffected
from rfl_rebuild.env import kernel as K
from rfl_rebuild.env.observation import learner_rows
from rfl_rebuild.learner.reference import reference_view_from
from rfl_rebuild.learner.store import Q, Edit, LearnerPersistentState, QAddress, DecisionAddress
from rfl_rebuild.method.credit import OracleCreditAdapter
from rfl_rebuild.solve.dp import solve_reference


def check(ok, message):
    if not ok:
        raise AssertionError(message)


def bound_inputs():
    """Actual original bytes and parent Git blobs; no cached PASS or rerun."""
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip()
    contract = json.loads((HERE / 'contract.json').read_bytes())
    check(head == contract['parent_commit'], 'different engineering parent HEAD')
    sources = ready.read_json(ROOT / ready.FOLDER / 'pipeline/frozen_inputs.json')['sources']
    audit = ready.read_json(ROOT / ready.FOLDER / 'pipeline/full_f1_complete_external_audit.json')['audit']
    natives = dict(audit['fixed_native_file_hashes'])
    natives.update(audit['post_controller_commit_native_tail_hashes'])
    check(len(sources) == 313 and len(natives) == 153, 'parent inventory count')
    entries = {}
    for row in subprocess.check_output(['git', 'ls-tree', '-r', '-z', head], cwd=ROOT).split(b'\0'):
        if row:
            meta, name = row.split(b'\t', 1)
            entries[name.decode('utf8')] = meta.split()[2].decode('ascii')
    prior = [n for n in entries if n.startswith(PREP.relative_to(ROOT).as_posix() + '/')]
    check(len(prior) == 234, 'prior preparation universe changed')
    bound = set(sources) | set(prior) | {'experiments/rebuild_status_current.json'}
    check(len(bound) == 548, 'parent byte binding universe changed')
    for name in bound:
        raw = (ROOT / name).read_bytes()
        check(sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() == entries[name], name)
    for name, wanted in (sources | natives).items():
        check(sha256((ROOT / name).read_bytes()).hexdigest() == wanted, name)
    all_names = sorted(bound | set(natives) | {p.relative_to(ROOT).as_posix() for p in HERE.glob('*.py')}
                       | {(HERE / 'contract.json').relative_to(ROOT).as_posix()})
    return {'parent_HEAD': head, 'parent_HEAD_bindings': len(bound), 'original_sources': 313,
            'old_native_bindings': 153,
            'input_file_sha256': {n: sha256((ROOT / n).read_bytes()).hexdigest() for n in all_names}}


def joint_region(sites, traces):
    """Experimental all-pre-nonconsult ruler; no Gamma/arm/post/law argument.

    Local checks are NOT hostile-Python security or upstream truth blindness.
    The caller in this test owns full pre traces; arbitrary production calls are
    not authenticated by this plain helper and have no scientific authority.
    """
    if type(sites) is not tuple or not sites or len(set(sites)) != len(sites):
        raise ProtocolError('complete nonempty unique declared sites required')
    if type(traces) is not unaffected.PreUpdateTraces:
        raise ProtocolError('native pre traces required')
    if any(type(s) is not unaffected.CreditedSite or s.channel != 'D_Q' for s in sites):
        raise ProtocolError('this engineering ruler is D_Q only')
    for site in sites:
        site.__post_init__()
    domain = unaffected.scene_domain()
    units = tuple(u for u in domain if traces.successful(u) and
                  not any(traces.consults(c, u) for c in sites))
    return unaffected.UnaffectedSet(units, 'EXPERIMENTAL_V24_JOINT_NONCONSULT_NOT_PRIMARY')


def map_rows(units, *maps):
    check(all(set(m) == set(units) for m in maps), 'whole map domain differs')
    return [[list(u.key)] + [float(m[u]).hex() for m in maps] for u in units]


def complete_credit_check(return_payload=False):
    parent = ready.load_parent()
    healthy_payload = ready.read_json(ROOT / ready.FOLDER / 'b2_prepare/healthy_reference_candidate.json')
    solution = solve_reference()
    reference = reference_view_from(solution)
    scene = unaffected.EvaluationScene(0, 0, 0, 0, 1)
    pre = LearnerPersistentState()
    edits = []
    for t in range(K.HORIZON):
        s = K.State(*K.START, t, 0, 0)
        edits.append(Edit(Q, QAddress(s, 1, 0, K.WAIT), max(reference.row(s, 1, 0).values()) + 1.))
    pre.apply_transaction(edits, q_reference=reference)
    before = fingerprint(pre)
    event = factual.prepare_factual_event(pre, scene=scene, regime='P', q_reference=reference,
                                        parent=parent, reference=healthy_payload)
    audit = event['evaluator_audit']
    check(audit['factual_outcome'] in factual.FAILURES, 'fixture did not cause a genuine failure')
    truth = audit['truth']['Gamma_P_star']
    check(audit['truth']['Gamma_T_star'] is None and len(truth) > 1, 'no whole persistent manifestation set')
    oracle = OracleCreditAdapter.evaluate(truth)
    check(oracle == frozenset(truth), 'Oracle lost true units')
    check(all(u.startswith('Decision_') for u in truth), 'uncovered projection, do not trim')
    ordered = tuple(sorted(oracle, key=lambda u: int(u.split('_')[1])))
    census = unaffected.pre_update_traces(learner=pre, q_reference=reference)
    trace = census.trace(scene)
    check(factual._trace_payload(trace, scene) == audit['raw_trace'], 'owned event/census source mismatch')
    addresses = resolve_credited_units(ordered, trace, scene.kappa, scene.phase)
    check(len(addresses) == len(truth), 'truth to owner projection lost units')
    sites = tuple(unaffected.CreditedSite('D_Q', a) for a in addresses)
    region = joint_region(sites, census)
    pre_map = collateral.measure_scene_map(pre, region.units, q_reference=reference)
    rows = learner_rows(trace, scene.kappa, scene.phase)
    arms = []
    for tier, treatment in ((Tier.L0_FACTUAL, FactualReturnWrite), (Tier.L3_ORACLE, DQLocalOracleRestore)):
        records = []
        for role, law in (('reference', NoWriteRef(tier)), ('treatment', treatment)):
            clone = pre.clone()
            transactions = []
            original_apply = LearnerPersistentState.apply_transaction
            from unittest.mock import patch
            def apply(state, changes, **kw):
                transactions.append({'fingerprint_pre': fingerprint(state),
                                     'edit_count': len(changes), 'state_is_this_clone': state is clone})
                return original_apply(state, changes, **kw)
            with patch.object(LearnerPersistentState, 'apply_transaction', new=apply):
                result = run_dq_law(law, clone, addresses, rows, reference)
            check(tuple(r.address for r in result.ledger.receipts) == addresses, 'incomplete native receipt group')
            if transactions:
                check(len(transactions) == 1 and transactions[0]['fingerprint_pre'] == before
                      and transactions[0]['state_is_this_clone'], 'not one complete transaction on same pre-state')
            post_map = collateral.measure_scene_map(clone, region.units, q_reference=reference)
            observation = environment.learned_rollout(clone, kappa=scene.kappa, tape=scene.tape,
                                                     base_option=scene.base_option, q_reference=reference)
            check(fingerprint(clone) == result.ledger.fingerprint_post, 'evaluation mutated immediate post')
            if role == 'reference':
                check(fingerprint(clone) == before and map_rows(region.units, pre_map) == map_rows(region.units, post_map),
                      'NoWrite changed state or unrelated behavior')
            records.append({'role': role, 'tier': tier.name, 'ledger': json.loads(result.ledger.canonical()),
                            'transactions': transactions, 'immediate_outcome': observation.outcome,
                            'immediate_return': observation.return_value,
                            'raw_immediate_trace': factual._trace_payload(observation, scene),
                            'joint_ruler_value': collateral.behavioral_collateral_scenes(region,
                                values_pre=pre_map, values_post=post_map),
                            'pre_and_post_map_hex': map_rows(region.units, pre_map, post_map)})
        arms.append({'tier': tier.name, 'same_declared_credit_and_region_object': True, 'arms': records})
    check(fingerprint(pre) == before, 'source learner mutated')
    # L3 is a mechanism upper bound, NOT ordinary learning or ranking across tiers.
    check(arms[1]['arms'][1]['immediate_outcome'] == K.Outcome.SUCCESS, 'whole row restore did not recover fixture')
    payload = {'fixture': 'actual_P_FAILURE_ALL_MANIFESTATIONS_NOT_SCIENCE_POPULATION',
               'installed_override_count': len(edits), 'actual_manifestation_count': len(truth),
               'declared_owner_count': len(addresses), 'original_factual_audit': audit,
               'ordered_Oracle_credit': ordered, 'complete_owner_sites': [c.render() for c in sites],
               'full_pre_census': [[list(u.key), census.successful(u),
                    [census.consults(c, u) for c in sites]] for u in unaffected.scene_domain()],
               'joint_region_size': region.size, 'same_tier_pairs': arms,
               'source_fingerprint_unchanged': fingerprint(pre) == before,
               'post_observation_is_future_training': False}
    return payload


def ruler_check():
    solution = solve_reference()
    reference = reference_view_from(solution)
    pre = LearnerPersistentState()
    before = fingerprint(pre)
    sites = tuple(unaffected.CreditedSite('D_Q', DecisionAddress(K.State(*K.START, 0, 0, phase), 1, 0))
                  for phase in (0, 1))
    traces = unaffected.pre_update_traces(learner=pre, q_reference=reference)
    region = joint_region(sites, traces)
    individuals = tuple(unaffected.eligibility(c, traces) for c in sites)
    check(set(region.units) == set(individuals[0]) & set(individuals[1]), 'intersection differs')
    contamination = [sum(traces.consults(sites[1-i], u) for u in individuals[i]) for i in (0, 1)]
    check(all(n > 0 for n in contamination), 'fixture does not distinguish per-site/joint semantics')
    chosen = None
    for u in region.units:
        for address in calibration._consulted_channel_sites('D_Q', traces, u):
            owner = calibration._owner_of('D_Q', address, solution)
            if owner in sites:
                continue
            made = calibration._make_edit('D_Q', solution, traces, u, address)
            if made is not None:
                chosen = calibration.SpilloverEdit('D_Q', 'EXPERIMENTAL_V24_JOINT', u, address, owner,
                                                   made[0], made[0].value, made[1], made[2], owner.address)
                break
        if chosen is not None:
            break
    check(chosen is not None and chosen.site not in sites, 'no lawful off-all-sites injection; no fallback')
    # Predictions fully constructed BEFORE measured values, never copied from them.
    expected_pre = {u: calibration.predicted_pre_value('D_Q', u, solution=solution) for u in region.units}
    expected_post = {u: calibration.predicted_spill_value('D_Q', u, chosen, traces=traces, solution=solution)
                     for u in region.units}
    expected = sum(expected_pre.values())/region.size - sum(expected_post.values())/region.size
    check(expected > 0, 'predeclared engineering ruler cannot see harm; do not chase another site')
    post = pre.clone()
    post.apply_transaction([chosen.substrate_edit], q_reference=reference)
    values_pre = collateral.measure_scene_map(pre, region.units, q_reference=reference)
    values_post = collateral.measure_scene_map(post, region.units, q_reference=reference)
    measured = collateral.behavioral_collateral_scenes(region, values_pre=values_pre, values_post=values_post)
    tolerance = json.loads((HERE / 'contract.json').read_bytes())['fixture_numerical_tolerance']
    max_error = max(abs(a[u]-b[u]) for a,b in ((expected_pre, values_pre), (expected_post, values_post))
                    for u in region.units)
    check(max_error <= tolerance and abs(expected-measured) <= tolerance and measured > 0,
          'measured whole-region maps disagree with independent prediction')
    check(fingerprint(pre) == before, 'ruler changed its owned pre-state')
    rejected = []
    def refuse(name, call):
        try:
            call()
        except ProtocolError:
            rejected.append(name)
        else:
            raise AssertionError('mutation accepted: ' + name)
    # Serial argument/record challenges; NO on-disk or frozen-source mutation.
    refuse('empty_credit_not_zero', lambda: joint_region((), traces))
    refuse('duplicated_owner_not_deduplicated', lambda: joint_region(sites+sites[:1], traces))
    refuse('wrong_owner_granularity', lambda: joint_region((chosen.channel_address,), traces))
    refuse('missing_map_scene_not_shrunk_denominator', lambda: collateral.behavioral_collateral_scenes(region,
        values_pre={u:v for u,v in values_pre.items() if u != region.units[0]}, values_post=values_post))
    refuse('nonfinite_map_not_silently_ignored', lambda: collateral.behavioral_collateral_scenes(region,
        values_pre=values_pre, values_post={**values_post, region.units[0]: float('nan')}))
    payload = {'fixture': 'synthetic_TWO_PHASE_TEST_SITES_NOT_ONE_EVENTS_TRUTH_OR_PRODUCTION_DOMAIN',
               'declared_test_sites': [c.render() for c in sites], 'full_U2_pre_census_count': 5760,
               'full_pre_census': [[list(u.key), traces.successful(u), [traces.consults(c,u) for c in sites]]
                                    for u in unaffected.scene_domain()],
               'individual_region_sizes': list(map(len, individuals)), 'joint_region_size': region.size,
               'each_individual_region_reads_other_declared_owner_count': contamination,
               'genuine_substrate_spill': {'scene': list(chosen.unit.key), 'owner': chosen.site.render(),
                    'Q_address': repr(chosen.channel_address), 'value_hex': chosen.target.hex(),
                    'applied_action': chosen.applied_action, 'outside_all_sites': True},
               'independent_prediction': expected, 'measured_joint_harm': measured,
               'max_per_scene_prediction_error': max_error,
               'ordered_predicted_pre_post_measured_pre_post_hex': map_rows(region.units,
                    expected_pre, expected_post, values_pre, values_post),
               'rejected_serial_argument_mutations': rejected,
               'source_fingerprint_unchanged': fingerprint(pre) == before}
    return payload


def main():
    from unittest.mock import patch
    from rfl_rebuild.b2.training import ExogenousEpisode
    before = bound_inputs()
    print('INPUT_BINDING=' + json.dumps(before, sort_keys=True), flush=True)
    with patch.object(ExogenousEpisode, 'derive', side_effect=AssertionError('forbidden environment key')), \
         patch('rfl_rebuild.b2.runner.train_curve', side_effect=AssertionError('forbidden keyed training')):
        print('STAGE=owned_Oracle_full_credit_native_B1', flush=True)
        credit = complete_credit_check()
        print('COMPLETE_CREDIT=' + json.dumps(credit, sort_keys=True, allow_nan=False), flush=True)
        print('STAGE=joint_ruler_genuine_off_target_injection', flush=True)
        ruler = ruler_check()
        print('COMPLETE_RULER=' + json.dumps(ruler, sort_keys=True, allow_nan=False), flush=True)
    after = bound_inputs()
    check(before == after, 'input/source/Git bytes changed during execution')
    print('FINAL=' + json.dumps({'status': 'ENGINEERING_MECHANISM_CHECK_COMPLETE_NOT_SCIENTIFIC_PASS',
        'before_after_bindings_equal': True, 'all_actual_credit_preserved': True,
        'L3_fixture_recovers_success': True, 'joint_ruler_detects_independently_predicted_spill': True,
        'serial_argument_mutations_rejected': len(ruler['rejected_serial_argument_mutations']),
        'delta_joint': None, 'scientific_population_chosen': False, 'collection_authorized': False,
        'scientific_or_workload_keys_allocated': 0, 'training_episodes': 0,
        'old806_tests_rerun': 0, 'research_complete': False}, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
