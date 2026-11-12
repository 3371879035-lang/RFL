"""Original process/controller fixed owned-failure mechanisms, test-only and seedless."""
from __future__ import annotations
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
from rfl_rebuild.b1.controller import resolve_controller_sites
from rfl_rebuild.b1.laws import NoWriteRef, PId, XId
from rfl_rebuild.b1.process import AssistedInput, resolve_process_addresses
from rfl_rebuild.b1.runner import run_process_law, run_controller_law
from rfl_rebuild.b1.tier import Tier
from rfl_rebuild.b2.environment import learned_rollout
from rfl_rebuild.b2.unaffected import EvaluationScene
from rfl_rebuild.env import kernel as K
from rfl_rebuild.env.observation import learner_rows
from rfl_rebuild.learner.reference import reference_view_from
from rfl_rebuild.learner.store import PROCESS, CONTROLLER, Edit, LearnerPersistentState
from rfl_rebuild.method.credit import OracleCreditAdapter
from rfl_rebuild.solve.dp import solve_reference


def check(ok, message):
    if not ok:
        raise AssertionError(message)


def bound_inputs():
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip()
    contract = ready.read_json(HERE / 'contract.json')
    check(head == contract['parent_commit'], 'engineering parent HEAD changed')
    frozen = ready.read_json(ROOT / ready.FOLDER / 'pipeline/frozen_inputs.json')
    sources = frozen['sources']
    audit = ready.read_json(ROOT / ready.FOLDER / 'pipeline/full_f1_complete_external_audit.json')['audit']
    natives = dict(audit['fixed_native_file_hashes'])
    natives.update(audit['post_controller_commit_native_tail_hashes'])
    trees = {}
    for row in subprocess.check_output(['git', 'ls-tree', '-r', '-z', head], cwd=ROOT).split(b'\0'):
        if row:
            meta, name = row.split(b'\t', 1)
            trees[name.decode('utf8')] = meta.split()[2].decode('ascii')
    prior = {n for n in trees if n.startswith(PREP.relative_to(ROOT).as_posix() + '/')}
    bound = set(sources) | prior | {'experiments/rebuild_status_current.json'}
    check((len(sources), len(natives), len(prior), len(bound)) == (313, 153, 261, 575),
          'prior binding universe changed')
    for name in bound:
        raw = (ROOT / name).read_bytes()
        check(sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() == trees[name], name)
    for name, wanted in (sources | natives).items():
        check(sha256((ROOT / name).read_bytes()).hexdigest() == wanted, name)
    names = bound | set(natives) | {p.relative_to(ROOT).as_posix() for p in HERE.glob('*.py')}
    names.add((HERE / 'contract.json').relative_to(ROOT).as_posix())
    return {'parent_HEAD': head, 'parent_HEAD_bindings': len(bound),
            'input_file_sha256': {n: sha256((ROOT / n).read_bytes()).hexdigest() for n in sorted(names)}}


def state_payload(state):
    snap = state.snapshot()
    sx = lambda s: [s.x, s.y, s.t, s.kappa, s.phi]
    return {
        'process': sorted([[z, v] for z, v in snap.process_overrides.items()]),
        'controller': sorted([[sx(site.state), site.cmd, u] for site, u in snap.controller_overrides.items()]),
        'decision': sorted([[sx(a.state), a.z, a.m, v] for a, v in snap.decision_overrides.items()]),
        'q': sorted([[sx(a.state), a.z, a.m, a.a, float(v).hex()] for a, v in snap.q_overrides.items()]),
        'healthy': snap.healthy, 'fingerprint': fingerprint(state)}


def main():
    before = bound_inputs()
    print('INPUT_BINDING=' + json.dumps(before, sort_keys=True), flush=True)
    parent = ready.load_parent()
    healthy = ready.read_json(ROOT / ready.FOLDER / 'b2_prepare/healthy_reference_candidate.json')
    solution = solve_reference()
    reference = reference_view_from(solution)
    scene = EvaluationScene(0, 2, 0, 0, 1)
    healthy_trace = learned_rollout(LearnerPersistentState(), kappa=scene.kappa,
                                   tape=scene.tape, base_option=scene.base_option, q_reference=reference)
    check(healthy_trace.outcome == K.Outcome.SUCCESS, 'fixed healthy scene did not succeed')
    primary = K.ControllerSite(K.State(1, 2, 1, 0, 2), K.UP)
    sentinel = K.ControllerSite(K.State(1, 2, 1, 1, 2), K.UP)
    healthy_rows = factual._trace_payload(healthy_trace, scene)
    check(any(r['pre_state'] == [1, 2, 1, 0, 2] and r['a_cmd'] == K.UP for r in healthy_rows),
          'fixed controller site is not visited with UP; do not search replacement')
    check(K.RIGHT in K.option_actions(1, K.ControlState(1, 0), primary.state),
          'fixed controller output is inadmissible')
    process_state = LearnerPersistentState()
    process_state.apply_transaction([Edit(PROCESS, 1, 0), Edit(PROCESS, 3, 2)])
    controller_state = LearnerPersistentState()
    controller_state.apply_transaction([Edit(CONTROLLER, primary, K.RIGHT),
                                        Edit(CONTROLLER, sentinel, K.WAIT)])
    print('FIXTURE=' + json.dumps({'scene': list(scene.key),
          'full_healthy_trace': healthy_rows,
          'process_pre': state_payload(process_state),
          'controller_pre': state_payload(controller_state)}, sort_keys=True), flush=True)
    outputs = []
    for architecture, pre, tier, treatment in (
            ('P', process_state, Tier.L1_CORRECTIVE, PId),
            ('X', controller_state, Tier.L0_FACTUAL, XId)):
        fp = fingerprint(pre)
        audit = factual.prepare_factual_event(pre, scene=scene, regime='P', q_reference=reference,
                 parent=parent, reference=healthy)['evaluator_audit']
        # Capture BEFORE checking coverage/outcome, so a genuine unexpected observation is retained.
        print('OWNED_FAILURE=' + json.dumps({'architecture': architecture, 'audit': audit},
                                           sort_keys=True, allow_nan=False), flush=True)
        check(audit['factual_outcome'] != K.Outcome.SUCCESS,
              'fixed case did not fail; no diagnosis on success and no outcome search')
        truth = audit['truth']['Gamma_P_star']
        check(truth and audit['truth']['Gamma_T_star'] is None, 'missing original P truth')
        oracle = OracleCreditAdapter.evaluate(truth)
        check(oracle == frozenset(truth), 'Oracle lost actual credit')
        trace = learned_rollout(pre, kappa=scene.kappa, tape=scene.tape,
                                base_option=scene.base_option, q_reference=reference)
        check(factual._trace_payload(trace, scene) == audit['raw_trace'], 'owned factual trace mismatch')
        if architecture == 'P':
            check(oracle == frozenset(('ProcessCommit',)), 'full process-case truth has extra channels; do not trim')
            units = tuple(truth)
            assisted = AssistedInput(scene.base_option)
            owners = resolve_process_addresses(units, assisted)
            check(owners == (1,) and trace.option_in_force == 0, 'wrong original process owner/commit')
        else:
            check(all(u.startswith('ControllerSite_') for u in oracle), 'full execution truth has extra channels; do not trim')
            units = tuple(sorted(oracle))
            owners = resolve_controller_sites(units, trace, scene.kappa, scene.phase)
            check(owners == (primary,), 'fixed controller owner differs; do not trim')
        check(fingerprint(pre) == fp, 'factual execution mutated source')
        arms = []
        for role, law in (('reference', NoWriteRef(tier)), ('treatment', treatment)):
            clone = pre.clone()
            transactions = []
            native_apply = LearnerPersistentState.apply_transaction
            def apply(state, edits, **kwargs):
                edits = tuple(edits)
                transactions.append({'on_this_clone': state is clone, 'fingerprint_pre': fingerprint(state),
                                     'entry_edits': len(edits), 'stores': [e.store for e in edits],
                                     'addresses': [str(e.address) for e in edits]})
                return native_apply(state, edits, **kwargs)
            with patch.object(LearnerPersistentState, 'apply_transaction', new=apply):
                if architecture == 'P':
                    result = run_process_law(law, clone, units, assisted)
                else:
                    result = run_controller_law(law, clone, owners,
                                               learner_rows(trace, scene.kappa, scene.phase))
            check(tuple(r.address for r in result.ledger.receipts) == owners, 'native ledger lost original owner')
            if transactions:
                check(len(transactions) == 1 and transactions[0]['on_this_clone']
                      and transactions[0]['fingerprint_pre'] == fp, 'not single same-pre-state commit')
                check(transactions[0]['stores'] == [PROCESS if architecture == 'P' else CONTROLLER],
                      'repair wrote to another persistent channel')
            snap = clone.snapshot()
            original = pre.snapshot()
            check(snap.decision_overrides == original.decision_overrides
                  and snap.q_overrides == original.q_overrides, 'repair changed a decision store')
            if architecture == 'P':
                check(snap.process_overrides.get(3) == 2 and snap.controller_overrides == original.controller_overrides,
                      'process repair removed unrelated defect or changed controller')
                if role == 'treatment':
                    check(1 not in snap.process_overrides, 'P_id did not restore identity at credited proposal')
            else:
                check(snap.controller_overrides.get(sentinel) == K.WAIT
                      and snap.process_overrides == original.process_overrides,
                      'controller repair removed unrelated defect or changed process')
                if role == 'treatment':
                    check(primary not in snap.controller_overrides, 'X_id did not restore identity at credited site')
            post = learned_rollout(clone, kappa=scene.kappa, tape=scene.tape,
                                   base_option=scene.base_option, q_reference=reference)
            check(fingerprint(clone) == result.ledger.fingerprint_post, 'post observation mutated learner')
            if role == 'reference':
                check(fingerprint(clone) == fp and factual._trace_payload(post, scene) == audit['raw_trace']
                      and not transactions, 'NoWrite changed state/behavior')
            check(not snap.healthy, 'off-trajectory defect was incorrectly globally restored')
            arms.append({'role': role, 'law': law.name, 'tier': tier.name,
                         'ledger': json.loads(result.ledger.canonical()), 'transactions': transactions,
                         'all_store_post': state_payload(clone),
                         'immediate_outcome': post.outcome, 'immediate_return': post.return_value,
                         'z_in_force': post.option_in_force,
                         'full_immediate_trace': factual._trace_payload(post, scene)})
        check(fingerprint(pre) == fp, 'paired arms changed source state')
        outputs.append({'architecture': architecture, 'installed_override_entries': 2,
                        'actual_manifestations': len(truth), 'full_Oracle_credit': units,
                        'original_resolved_owners': [str(x) for x in owners],
                        'original_owned_audit': audit, 'all_store_pre': state_payload(pre),
                        'same_tier_pair': arms, 'off_trajectory_defect_preserved': True,
                        'source_unchanged': True})
    print('COMPLETE_CHANNELS=' + json.dumps(outputs, sort_keys=True, allow_nan=False), flush=True)
    check(bound_inputs() == before, 'original inputs drifted during execution')
    print('FINAL=' + json.dumps({'status': 'ENGINEERING_MECHANISM_EXECUTION_COMPLETE_NOT_SCIENCE_PASS',
          'before_after_inputs_equal': True, 'all_actual_Oracle_credit_retained': True,
          'native_B1_arm_executions': 4, 'native_B1_repair_transactions': 2,
          'native_learner_rollouts': 9,
          'off_trajectory_defects_preserved': True, 'no_wrong_store_writes': True,
          'immediate_recovery_observed': {x['architecture']: x['same_tier_pair'][1]['immediate_outcome'] == K.Outcome.SUCCESS
                                        for x in outputs},
          'remaining_defects_mean_not_global_restore': True,
          'future_training_episodes': 0, 'scientific_or_workload_keys_allocated': 0,
          'joint_ruler_or_primary_endpoint_used': False, 'old806_v24_v25_or_science_rerun': False,
          'collection_authorized': False, 'research_complete': False}, sort_keys=True), flush=True)


if __name__ == '__main__':
    from rfl_rebuild.b2 import training
    with patch.object(training.ExogenousEpisode, 'derive', side_effect=AssertionError('no environment keys allowed')), \
         patch.object(training, 'train_curve', side_effect=AssertionError('no future training authorized')):
        main()
