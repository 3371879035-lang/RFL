"""One new stdlib-only stored audit; no RFL/addon/old checker imports or reruns."""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent/'owned_value_response_v93'


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')).hexdigest()


def state_key(state):
    return tuple(state[k] for k in ('x', 'y', 't', 'kappa', 'phi'))


def address_key(address):
    key = state_key(address['state'])+(address['z'], address['m'])
    return key+(address['a'],) if 'a' in address else key


def qmap(entries):
    return {address_key(x['address']): float.fromhex(x['value']['binary64_hex']) for x in entries}


def dmap(entries):
    return {address_key(x['address']): x['value'] for x in entries}


def old_wire(stores):
    return {'D': sorted([[list(address_key(x['address'])), x['value']] for x in stores['D']]),
            'P': sorted([[x['address'], x['value']] for x in stores['P']]),
            'X': sorted([[list(state_key(x['address']['state'])+(x['address']['cmd'],)), x['value']] for x in stores['X']]),
            'Q': sorted([[list(address_key(x['address'])), x['value']['binary64_hex']] for x in stores['Q']])}


def restore_source_payload(data):
    result = deepcopy(data)
    truth = result['native_source_payload']['truth_evaluator_only']
    encoded = truth['whole_optimal_set_tolerance']
    assert set(encoded) == {'binary64_hex'}
    truth['whole_optimal_set_tolerance'] = float.fromhex(encoded['binary64_hex'])
    return result


def main():
    started = datetime.now(timezone.utc).isoformat()
    result_path = HERE/'stored_audit_result.json'
    assert not result_path.exists(), 'exclusive stored audit; no retry'
    c = json.loads((HERE/'contract.json').read_bytes())
    claim = json.loads((HERE/'evidence/claim.json').read_bytes())
    end = json.loads((HERE/'evidence/exit.json').read_bytes())
    assert end['child_exit_code'] == 0 and end['input_bytes_unchanged'] and end['capture_budget_met']
    assert claim['parent_commit'] == c['parent_commit'] and claim['input_binding_before'] == end['input_binding_after']
    for name, pin in end['input_binding_after'].items():
        raw = (ROOT/name).read_bytes()
        assert len(raw) == pin['bytes'] and hashlib.sha256(raw).hexdigest() == pin['sha256'], name
    for name in ('stdout', 'stderr'):
        raw = (HERE/'evidence'/f'{name}.log').read_bytes()
        assert len(raw) == end[name]['bytes'] and hashlib.sha256(raw).hexdigest() == end[name]['sha256']
    allowed, ref = {}, {}
    for line in (ROOT/c['reference_input']['path']).read_text(encoding='utf-8').splitlines():
        if line.startswith('DECISION_CONTEXT='):
            row = json.loads(line.split('=', 1)[1]); context = tuple(row['context'])
            allowed[context] = [a for a, v in row['q_row_hex']]
            ref.update({context+(a,): float.fromhex(v) for a, v in row['q_row_hex']})
    assert len(allowed) == 13824
    raw = (HERE/'evidence/stdout.log').read_bytes(); assert raw.endswith(b'\n')
    rows = []
    for line in raw.splitlines():
        item = json.loads(line)
        assert json.dumps(item, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii') == line
        rows.append(item)
    assert rows[-1]['tag'] == 'RESULT'
    summary = rows[-1]['payload']
    assert (summary['tests'], summary['failures'], summary['errors'], summary['skips']) == (3, 0, 0, 0)
    assert summary['actual_loaded_inventory_bound'] and summary['counts'].get('forbidden', 0) == 0
    tags = Counter(x['tag'] for x in rows)
    prefixes, rollouts, native_results, core_receipts, owned_receipts, eval_receipts = [], [], [], [], [], []
    source = pair = origin = None
    steps = 0
    for item in rows:
        tag, p = item['tag'], item['payload']
        if tag == 'RAW_STEP':
            context = state_key(p['pre_state'])+(p['pre_control']['z'], p['pre_control']['m'])
            assert p['a_cmd'] in allowed[context]
            if prefixes:
                assert p['pre_state'] == prefixes[-1]['result']['state'] and p['pre_control'] == prefixes[-1]['result']['control']
            else: assert state_key(p['pre_state'])[:3] == (0, 2, 0)
            prefixes.append(p); steps += 1
        elif tag == 'RAW_ROLLOUT':
            assert [x['result'] for x in prefixes] == p['steps']
            assert p['steps'][-1]['terminal'] and p['steps'][-1]['outcome'] == p['outcome']
            assert all(not x['terminal'] for x in p['steps'][:-1])
            assert p['mask'] == {'decision': None, 'controller': None, 'plant': None, 'trap': None}
            assert p['interventions'] == {'members': []}
            rollouts.append(p); prefixes = []
        elif tag == 'INCOMPLETE_ROLLOUT': raise AssertionError('unexpected partial must remain failed')
        elif tag == 'ORIGINAL_SOURCE':
            restored = restore_source_payload(p['payload'])
            assert digest(restored) == p['payload_sha256']
            source = restored['native_source_payload']; assert digest(source) == restored['native_source_sha256']
            assert source['scene'] == c['new_scene'] and source['regime'] == 'P'
            factual = rollouts[-1]; state = (0, 2, 0, 0, 2); z, m = factual['option_in_force'], 0
            decisions, controllers = [], []
            tolerance = source['truth_evaluator_only']['whole_optimal_set_tolerance']
            for step, data in zip(factual['steps'], source['raw_factual']):
                assert data == {'pre_state': list(state), 'z': z, 'm': m, 'a_cmd': step['a_cmd'], 'u': step['u'],
                    'a_realized': step['a_realized'], 'reward_hex': step['reward']['binary64_hex'],
                    'post_state': list(state_key(step['state'])), 'post_control': [step['control']['z'], step['control']['m']],
                    'terminal': step['terminal'], 'outcome': step['outcome'], 'illegal': step['illegal']}
                legal = allowed[state+(z, m)]; best = max(ref[state+(z, m, a)] for a in legal)
                if step['a_cmd'] not in [a for a in legal if ref[state+(z, m, a)] >= best-tolerance]: decisions.append('Decision_'+str(state[2]))
                if step['u'] != step['a_cmd']: controllers.append('ControllerSite_'+str(state[0])+'_'+str(state[1])+'_'+str(state[2])+'_'+str(step['a_cmd']))
                state, z, m = state_key(step['state']), step['control']['z'], step['control']['m']
            assert len(source['raw_factual']) == len(factual['steps'])
            assert ['ProcessCommit']+decisions+controllers == source['truth_evaluator_only']['Gamma_P_star']
        elif tag == 'BOUND_BEFORE_ARMS':
            restored = deepcopy(p['payload'])
            restored['source']['payload'] = restore_source_payload(restored['source']['payload'])
            assert digest(restored) == p['payload_sha256'] and restored['decision_mode_before_arms'] == 'patch-adaptive'
        elif tag == 'NATIVE_B1_RETURN': native_results.append(p)
        elif tag == 'ORIGINAL_PAIR':
            assert digest(p['payload']) == p['payload_sha256']
            old = p['payload']['original_v74_pair']; assert digest(old['payload']) == old['payload_sha256']
            pair = old['payload']; pre = source['full_pre_stores']
            assert pair['whole_oracle_units'] == source['truth_evaluator_only']['Gamma_P_star']
            assert set(pair['residual_units_preserved']) == {'ProcessCommit', 'ControllerSite_0_2_0_4', 'ControllerSite_1_2_1_4'}
            for i, (arm, native) in enumerate(zip(pair['all_owner_receipts'], native_results)):
                assert old_wire(native['full_post']) == arm['full_post_stores'] and native['ledger_canonical'] == arm['ledger_canonical']
                assert len(arm['ordered_receipts']) == len(pair['cell_units'])
                ledger = json.loads(arm['ledger_canonical'])
                assert not ledger['scalar_metrics_applicable'] and (ledger['n_scalar'], ledger['sum_abs_delta'], ledger['max_abs_delta']) == (0, 0.0, 0.0)
                post = arm['full_post_stores']; assert post['P'] == pre['P'] and post['X'] == pre['X'] and post['Q'] == pre['Q'] == []
                was = {tuple(a): v for a, v in pre['D']}; now = {tuple(a): v for a, v in post['D']}
                owners = {tuple(int(n) for n in receipt[0].split(',')) for receipt in arm['ordered_receipts']}
                changed = {a for a in set(was)|set(now) if was.get(a) != now.get(a)}
                assert changed <= owners
                if i == 0: assert post == pre and not changed
                for address, status, flag in arm['ordered_receipts']:
                    key = tuple(int(n) for n in address.split(','))
                    assert flag == (key in changed) and status == ('APPLIED' if flag else 'EVALUABLE_NOOP')
        elif tag == 'HANDOFF': origin = p
        elif tag == 'CORE_TRAIN_RECEIPT': core_receipts.append(p)
        elif tag == 'OWNED_TRAIN': owned_receipts.append(p)
        elif tag == 'OWNED_EVAL': eval_receipts.append(p)
        elif tag == 'ACTUAL_LOADED_SOURCE_INVENTORY':
            assert all(claim['input_binding_before'][n]['sha256'] == pin for n, pin in p.items())
    assert not prefixes and source and pair and origin

    def composite(audit):
        assert audit['origin'] == origin['origin'] and digest(audit['origin']) == audit['origin_sha256'] == origin['origin_sha256']
        for i, p in enumerate(audit['ordered_current_composites']):
            assert digest(p) == audit['ordered_full_composite_sha256'][i]
            assert p['mode'] == 'patch-adaptive' and p['role'] == ('reference', 'treatment')[i]
            assert p['source_label'] == origin['origin']['original_pair_binding']
            assert p['immediate'] == origin['origin']['protected_immediate_posts'][i]
            assert old_wire(p['immediate']) == pair['all_owner_receipts'][i]['full_post_stores']
            assert p['current']['P'] == p['immediate']['P'] and p['current']['X'] == p['immediate']['X']
            assert not p['current']['Q'] and all(not p['learning_values'][k] for k in ('D', 'P', 'X'))

    def behavior(r):
        before = r['before']; state = (0, 2, 0, 0, 2); z, m = r['trace']['option_in_force'], 0
        p = {x['address']: x['value'] for x in before['current']['P']}; assert z == p.get(r['trace']['base_option'], r['trace']['base_option'])
        patches = dmap(before['current']['D']); values = qmap(before['learning_values']['Q'])
        controllers = {(state_key(x['address']['state']), x['address']['cmd']): x['value'] for x in before['current']['X']}
        for step in r['trace']['steps']:
            context = state+(z, m); legal = allowed[context]
            action = patches.get(context, min(legal, key=lambda a: (-values.get(context+(a,), ref[context+(a,)]), a)))
            assert action == step['a_cmd'] and step['u'] == controllers.get((state, action), action) == step['a_realized']
            state, z, m = state_key(step['state']), step['control']['z'], step['control']['m']

    responses, policy_changes = [], 0
    assert len(core_receipts) == len(owned_receipts) == len(eval_receipts) == 2
    for i, p in enumerate(owned_receipts):
        r = p['training']; assert r == core_receipts[i] and p['role'] == r['before']['role']
        assert r['trace'] == rollouts[i+1]
        composite(p['complete_pair_after']); behavior(r)
        before, after = r['before'], r['after']; assert before['immediate'] == after['immediate']
        assert r['parameters'] == {'alpha': {'rational': [1, 2]}, 'epsilon': {'rational': [1, 10]}}
        work = qmap(before['learning_values']['Q']); state = (0, 2, 0, 0, 2); z, m = r['trace']['option_in_force'], 0
        value = lambda q: work.get(q, ref[q]); order, contexts, residuals = [], [], []
        for j, step in enumerate(r['trace']['steps']):
            context = state+(z, m); q = context+(step['a_cmd'],); legal = allowed[context]
            assert r['draws'][j] == {'i': j, 'explore': False, 'admissible': legal, 'a_cmd': step['a_cmd']}
            assert r['episode']['coins'][j] == (1 << 64)-1
            current = value(q); target = float.fromhex(step['reward']['binary64_hex'])
            nxt, nz, nm = state_key(step['state']), step['control']['z'], step['control']['m']
            if not step['terminal']: target += max(value(nxt+(nz, nm, a)) for a in allowed[nxt+(nz, nm)])
            residuals.append((target-current).hex()); work[q] = current+0.5*(target-current)
            if q not in order: order.append(q)
            contexts.append(context); state, z, m = nxt, nz, nm
        assert [address_key(e['address']) for e in r['numeric_edits']] == order
        assert all(float.fromhex(e['value']['binary64_hex']).hex() == work[q].hex() for e, q in zip(r['numeric_edits'], order))
        canonical = {q: v for q, v in work.items() if v != ref[q]}
        assert {q: v.hex() for q, v in canonical.items()} == {q: v.hex() for q, v in qmap(after['learning_values']['Q']).items()}
        patches = dmap(before['current']['D']); updated = dict(patches); expected_edits = []
        for context in dict.fromkeys(contexts):
            if context in patches:
                action = min(allowed[context], key=lambda a: (-canonical.get(context+(a,), ref[context+(a,)]), a))
                updated[context] = action; expected_edits.append((context, action))
        assert [(address_key(e['address']), e['value']) for e in r['policy_improvement_edits']] == expected_edits
        assert dmap(after['current']['D']) == updated
        policy_changes += sum(v != updated[k] for k, v in patches.items())
        assert after['completed_episodes'] == before['completed_episodes']+1
        responses.append({'role': p['role'], 'L_entries': len(canonical), 'first_residual_hex': residuals[0], 'all_residuals_hex': residuals})
    assert responses[0]['L_entries'] > 0 and responses[0]['first_residual_hex'] == '0x1.47ae147ae1480p-6'
    for p, rollout in zip(eval_receipts, rollouts[3:]):
        r = p['evaluation']; assert r['trace'] == rollout
        assert r['before'] == r['after'] and r['draws'] == [] and r['readonly']; behavior(r); composite(p['complete_pair_after'])
    for item in rows:
        if item['tag'] == 'NONEMPTY_L_COMMITMENT_GATE':
            p = item['payload']; composite(p['full_before'])
            assert p['counts_before'] == p['counts_after'] and p['runtime_alias_restored']
            assert p['original_digest'] == p['full_before']['ordered_full_composite_sha256'][0]
            assert p['altered_copy_digest'] == digest(p['altered_copy']) != p['original_digest']
            actual = deepcopy(p['full_before']['ordered_current_composites'][0]); changed = deepcopy(p['altered_copy'])
            assert actual['learning_values']['Q']
            actual['learning_values']['Q'][0]['value'] = changed['learning_values']['Q'][0]['value']
            assert actual == changed
        elif item['tag'] in ('ACTUAL_OWNED_RESPONSE', 'FINAL_OWNED_PAIR'): composite(item['payload'])
    assert len(rollouts) == summary['counts']['rollout'] == 5 and steps == summary['counts']['step']
    assert tags['NATIVE_B1_RETURN'] == summary['counts']['B1'] == 2
    assert tags['TX_CALL'] == tags['TX_RETURN'] == summary['counts']['transaction']
    assert tags['NONEMPTY_L_COMMITMENT_GATE'] == 1
    output = {'status': 'V93_FINITE_OWNED_ACTIVE_X_L_RESPONSE_CONTENTS_VERIFIED_NOT_SCIENCE',
              'started_at_utc': started, 'completed_at_utc': datetime.now(timezone.utc).isoformat(),
              'audit_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'stdout_sha256': end['stdout']['sha256'], 'records': len(rows), 'tag_inventory': dict(tags),
              'bound_inputs': len(end['input_binding_after']), 'full_raw_rollouts': len(rollouts), 'raw_steps': steps,
              'actual_role_responses': responses, 'literal_policy_changes': policy_changes,
              'all_full_B1_owner_receipts_and_residual_preserved': True, 'nonempty_L_commitment_gate': True,
              'old_native_checker_or_RFL_execution': False, 'runtime_identity_reconstructed_from_bytes': False,
              'independent_expert_or_scientific_gate': False, 'scientific_qualification': False}
    with result_path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(output, stream, sort_keys=True, separators=(',', ':'), ensure_ascii=True); stream.write('\n')
    print(json.dumps(output, sort_keys=True))


if __name__ == '__main__': main()
