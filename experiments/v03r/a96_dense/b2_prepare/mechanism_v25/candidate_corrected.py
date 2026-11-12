"""Test-only matched defect mechanisms, not science acquisition or future learning."""
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
from rfl_rebuild.b1.laws import DeleteFactualPatch, FactualReturnWrite, NoWriteRef
from rfl_rebuild.b1.runner import run_dq_law, run_patch_law
from rfl_rebuild.b1.targets import resolve_credited_units
from rfl_rebuild.b1.tier import Tier
from rfl_rebuild.b2.environment import learned_rollout
from rfl_rebuild.b2.unaffected import EvaluationScene
from rfl_rebuild.env import kernel as K
from rfl_rebuild.env.observation import learner_rows
from rfl_rebuild.learner.reference import reference_view_from
from rfl_rebuild.learner.store import Q, DECISION, DecisionAddress, Edit, LearnerPersistentState, QAddress
from rfl_rebuild.method.credit import OracleCreditAdapter
from rfl_rebuild.solve.dp import solve_reference


def check(ok, message):
    if not ok:
        raise AssertionError(message)


def bound_inputs():
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip()
    contract = ready.read_json(HERE / 'contract.json')
    check(head == contract['parent_commit'], 'engineering parent HEAD changed')
    sources = ready.read_json(ROOT / ready.FOLDER / 'pipeline/frozen_inputs.json')['sources']
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
    check(len(sources) == 313 and len(natives) == 153 and len(prior) == 244 and len(bound) == 558,
          'prior binding universe changed')
    for name in bound:
        raw = (ROOT / name).read_bytes()
        check(sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() == trees[name], name)
    for name, wanted in (sources | natives).items():
        check(sha256((ROOT / name).read_bytes()).hexdigest() == wanted, name)
    names = bound | set(natives) | {p.relative_to(ROOT).as_posix() for p in HERE.glob('*.py')}
    names.add((HERE / 'contract.json').relative_to(ROOT).as_posix())
    repair = ready.read_json(HERE / 'repair_contract.json')
    check(repair['parent_commit'] == head, 'repair parent changed')
    names.add((HERE / 'repair_contract.json').relative_to(ROOT).as_posix())
    for initial_name, expected in repair['initial_attempt_SHA256'].items():
        p = HERE / initial_name
        check(sha256(p.read_bytes()).hexdigest() == expected, 'initial failure evidence changed: ' + initial_name)
        names.add(p.relative_to(ROOT).as_posix())
    return {'parent_HEAD': head, 'parent_HEAD_bindings': len(bound),
            'input_file_sha256': {n: sha256((ROOT / n).read_bytes()).hexdigest() for n in sorted(names)}}


def main():
    before = bound_inputs()
    print('INPUT_BINDING=' + json.dumps(before, sort_keys=True), flush=True)
    parent = ready.load_parent()
    healthy = ready.read_json(ROOT / ready.FOLDER / 'b2_prepare/healthy_reference_candidate.json')
    solution = solve_reference()
    reference = reference_view_from(solution)
    scene = EvaluationScene(0, 2, 0, 0, 1)
    owner = DecisionAddress(K.State(1, 2, 1, 0, 2), 1, 0)
    row = reference.row(owner.state, owner.z, owner.m)
    check(K.RIGHT in row and K.RIGHT not in factual._optimal_actions(row),
          'fixed defect action is inadmissible or optimal; do not search replacement')
    healthy_state = LearnerPersistentState()
    healthy_trace = learned_rollout(healthy_state, kappa=scene.kappa, tape=scene.tape,
                                   base_option=scene.base_option, q_reference=reference)
    check(healthy_trace.outcome == K.Outcome.SUCCESS, 'fixed healthy scene does not succeed')
    print('FIXTURE=' + json.dumps({'scene': list(scene.key), 'owner': str(owner), 'action': K.RIGHT,
          'original_Q_row_hex': {str(a): float(v).hex() for a, v in row.items()},
          'healthy_trace': factual._trace_payload(healthy_trace, scene)}, sort_keys=True), flush=True)

    # The two installers depend independently on the extensional literal, not each other.
    q_state = LearnerPersistentState()
    q_state.apply_transaction([Edit(Q, QAddress(owner.state, 1, 0, K.RIGHT), max(row.values()) + 1.)],
                             q_reference=reference)
    patch_state = LearnerPersistentState()
    patch_state.apply_transaction([Edit(DECISION, DecisionAddress(K.State(1, 2, 1, 0, 2), 1, 0), K.RIGHT)])
    states = (('D_Q', q_state), ('D_patch', patch_state))
    prepared = []
    for architecture, pre in states:
        fp = fingerprint(pre)
        event = factual.prepare_factual_event(pre, scene=scene, regime='P', q_reference=reference,
                                            parent=parent, reference=healthy)
        audit = event['evaluator_audit']
        check(audit['factual_outcome'] == K.Outcome.COLLISION, 'fixed collision did not manifest; no tuning')
        truth = audit['truth']['Gamma_P_star']
        check(truth and audit['truth']['Gamma_T_star'] is None, 'missing original P truth')
        oracle = OracleCreditAdapter.evaluate(truth)
        check(oracle == frozenset(truth) and all(x.startswith('Decision_') for x in truth),
              'complete actual credit projection not covered; do not trim')
        units = tuple(sorted(oracle, key=lambda x: int(x.split('_')[1])))
        trace = learned_rollout(pre, kappa=scene.kappa, tape=scene.tape,
                                base_option=scene.base_option, q_reference=reference)
        check(factual._trace_payload(trace, scene) == audit['raw_trace'], 'owned factual trace mismatch')
        owners = resolve_credited_units(units, trace, scene.kappa, scene.phase)
        check(owners == (owner,) and len(owners) == len(truth), 'actual full owners differ from fixture')
        check(fingerprint(pre) == fp, 'factual execution changed source state')
        prepared.append((architecture, pre, fp, audit, units, trace, owners))
    check(prepared[0][3]['raw_trace'] == prepared[1][3]['raw_trace'],
          'independent architectures do not induce same complete factual episode')
    check(prepared[0][4] == prepared[1][4], 'same induced defect has different actual credit')
    print('STAGE=matched_owned_P_credit_and_independent_installation', flush=True)
    outputs = []
    for architecture, pre, fp, audit, units, trace, owners in prepared:
        arms = []
        for role, law in (('reference', NoWriteRef(Tier.L0_FACTUAL)),
                          ('treatment', FactualReturnWrite if architecture == 'D_Q' else DeleteFactualPatch)):
            clone = pre.clone()
            transactions = []
            native_apply = LearnerPersistentState.apply_transaction
            def apply(state, edits, **kwargs):
                transactions.append({'on_this_clone': state is clone, 'fingerprint_pre': fingerprint(state),
                                     'entry_edits': len(edits)})
                return native_apply(state, edits, **kwargs)
            with patch.object(LearnerPersistentState, 'apply_transaction', new=apply):
                if architecture == 'D_Q':
                    result = run_dq_law(law, clone, owners,
                                       learner_rows(trace, scene.kappa, scene.phase), reference)
                else:
                    result = run_patch_law(law, clone, units, trace, scene.kappa, scene.phase, solution)
            check(tuple(r.address for r in result.ledger.receipts) == owners, 'native ledger lost owner')
            if transactions:
                check(len(transactions) == 1 and transactions[0]['on_this_clone']
                      and transactions[0]['fingerprint_pre'] == fp, 'not single same-pre-state transaction')
            post = learned_rollout(clone, kappa=scene.kappa, tape=scene.tape,
                                   base_option=scene.base_option, q_reference=reference)
            check(fingerprint(clone) == result.ledger.fingerprint_post, 'post observation changed learner')
            if role == 'reference':
                check(fingerprint(clone) == fp and factual._trace_payload(post, scene) == audit['raw_trace'],
                      'NoWrite reference changed original behavior')
                check(not transactions, 'NoWrite committed a transaction')
            arms.append({'role': role, 'law': law.name, 'tier': Tier.L0_FACTUAL.name,
                         'ledger': json.loads(result.ledger.canonical()), 'transactions': transactions,
                         'immediate_outcome': post.outcome, 'immediate_return': post.return_value,
                         'full_immediate_trace': factual._trace_payload(post, scene)})
        check(fingerprint(pre) == fp, 'paired arms changed source learner')
        outputs.append({'architecture': architecture, 'installed_contexts': 1,
                        'actual_manifestations': len(units), 'full_Oracle_credit': units,
                        'full_resolved_owners': [str(x) for x in owners], 'original_owned_audit': audit,
                        'source_fingerprint': fp, 'same_tier_pair': arms, 'source_unchanged': True})
    print('COMPLETE_ARCHITECTURES=' + json.dumps(outputs, sort_keys=True, allow_nan=False), flush=True)
    check(bound_inputs() == before, 'original inputs drifted during execution')
    recoveries = {o['architecture']: o['same_tier_pair'][1]['immediate_outcome'] == K.Outcome.SUCCESS
                  for o in outputs}
    print('FINAL=' + json.dumps({'status': 'ENGINEERING_MECHANISM_EXECUTION_COMPLETE_NOT_SCIENCE_PASS',
          'before_after_inputs_equal': True, 'independent_extensional_installation': True,
          'full_factual_episodes_equal': True, 'all_actual_Oracle_credit_retained': True,
          'immediate_recovery_observed': recoveries, 'treatment_failure_would_be_reported_not_tuned': True,
          'old806_or_v24_fixtures_rerun': False, 'scientific_or_workload_keys_allocated': 0,
          'future_training_episodes': 0, 'joint_ruler_or_primary_endpoint_used': False,
          'collection_authorized': False, 'research_complete': False}, sort_keys=True), flush=True)


if __name__ == '__main__':
    from rfl_rebuild.b2 import training
    with patch.object(training.ExogenousEpisode, 'derive', side_effect=AssertionError('no environment keys allowed')), \
         patch.object(training, 'train_curve', side_effect=AssertionError('no future training authorized')):
        main()
