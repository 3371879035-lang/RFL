"""Stdlib-only audit of the preserved FAILED v92 child, lineage, raw and zero L/TD.
Does not import RFL, the addon/core, any old checker or any fixture. Contents do
not reconstruct runtime identity; identity gates belong to the captured child.
"""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent/'owned_adaptive_handoff_v92'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')).hexdigest()


def skey(state):
    return tuple(state[k] for k in ('x', 'y', 't', 'kappa', 'phi'))


def key(address):
    result = skey(address['state'])
    if 'z' in address:
        result += (address['z'], address['m'])
    return result+(address['a'],) if 'a' in address else result


def qmap(entries):
    return {key(e['address']): float.fromhex(e['value']['binary64_hex']) for e in entries}


def dmap(entries):
    return {key(e['address']): e['value'] for e in entries}


def old_wire(stores):
    return {'D': sorted([[list(key(e['address'])), e['value']] for e in stores['D']]),
            'P': sorted([[e['address'], e['value']] for e in stores['P']]),
            'X': sorted([[list(skey(e['address']['state'])+(e['address']['cmd'],)), e['value']] for e in stores['X']]),
            'Q': sorted([[list(key(e['address'])), e['value']['binary64_hex']] for e in stores['Q']])}



def restored_source(audit_payload):
    value = deepcopy(audit_payload)
    truth = value['native_source_payload']['truth_evaluator_only']
    encoded = truth['whole_optimal_set_tolerance']
    assert set(encoded) == {'binary64_hex'}
    truth['whole_optimal_set_tolerance'] = float.fromhex(encoded['binary64_hex'])
    return value


def main():
    started = datetime.now(timezone.utc).isoformat()
    result_path = HERE/'failed_capture_decoded_audit_result.json'
    assert not result_path.exists(), 'one audit only; do not retry'
    contract = json.loads((HERE/'contract.json').read_bytes())
    claim = json.loads((HERE/'evidence/claim.json').read_bytes())
    end = json.loads((HERE/'evidence/exit.json').read_bytes())
    assert end['child_exit_code'] == 1 and end['input_bytes_unchanged'] and end['capture_budget_met']
    assert claim['input_binding_before'] == end['input_binding_after']
    assert claim['parent_commit'] == contract['parent_commit']
    for name, expected in end['input_binding_after'].items():
        raw = (ROOT/name).read_bytes()
        assert len(raw) == expected['bytes'] and hashlib.sha256(raw).hexdigest() == expected['sha256'], name
    for name in ('stdout', 'stderr'):
        raw = (HERE/'evidence'/f'{name}.log').read_bytes()
        assert len(raw) == end[name]['bytes'] and hashlib.sha256(raw).hexdigest() == end[name]['sha256']
    reference, allowed = {}, {}
    for line in (ROOT/contract['reference_input']['path']).read_text(encoding='utf-8').splitlines():
        if line.startswith('DECISION_CONTEXT='):
            data = json.loads(line.split('=', 1)[1]); context = tuple(data['context'])
            allowed[context] = [a for a, v in data['q_row_hex']]
            reference.update({context+(a,): float.fromhex(v) for a, v in data['q_row_hex']})
    assert len(allowed) == 13824
    raw = (HERE/'evidence/stdout.log').read_bytes()
    assert raw.endswith(b'\n')
    rows = []
    for line in raw.splitlines():
        item = json.loads(line)
        assert json.dumps(item, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii') == line
        rows.append(item)
    assert rows[-1]['tag'] == 'RESULT'
    result = rows[-1]['payload']
    assert (result['tests'], result['failures'], result['errors'], result['skips']) == (5, 1, 0, 0)
    assert result['counts'].get('forbidden', 0) == 0 and result['actual_loaded_inventory_bound']
    tags = Counter(r['tag'] for r in rows)
    sources, declarations, pairs, origins = {}, {}, {}, {}
    full_rollouts, prefix = [], []
    steps = train = evaluation = policy_changes = 0
    tx_before = None

    def validate_composite(payload):
        origin = payload['origin']; assert digest(origin) == payload['origin_sha256']
        declaration = origin['original_declaration']; pair_seal = digest(declaration)
        assert pair_seal == origin['original_pair_binding']
        native = declaration['original_pair']['payload']['original_v74_pair']['payload']
        for i, p in enumerate(payload['ordered_current_composites']):
            assert digest(p) == payload['ordered_full_composite_sha256'][i]
            assert p['role'] == ('reference', 'treatment')[i] and p['source_label'] == pair_seal
            assert p['mode'] == declaration['mode_before_arms']
            assert p['immediate'] == origin['protected_immediate_posts'][i]
            assert old_wire(p['immediate']) == native['all_owner_receipts'][i]['full_post_stores']
            assert p['current']['P'] == p['immediate']['P'] and p['current']['X'] == p['immediate']['X']
            if p['mode'] == 'dq':
                assert p['learning_values'] is None and not p['current']['D']
            else:
                assert not p['current']['Q']
                assert all(not p['learning_values'][channel] for channel in ('D', 'P', 'X'))

    def behavior(receipt, training=False):
        p = receipt['before']; trace = receipt['trace']; state = (0, 2, 0, 0, 2)
        z, m = trace['option_in_force'], 0
        processes = {e['address']: e['value'] for e in p['current']['P']}
        controllers = {(skey(e['address']['state']), e['address']['cmd']): e['value'] for e in p['current']['X']}
        assert z == processes.get(trace['base_option'], trace['base_option'])
        numeric = qmap((p['current'] if p['mode'] == 'dq' else p['learning_values'])['Q'])
        patches = dmap(p['current']['D']) if p['mode'] == 'patch-adaptive' else {}
        for i, step in enumerate(trace['steps']):
            context = state+(z, m); legal = allowed[context]
            greedy = min(legal, key=lambda a: (-numeric.get(context+(a,), reference[context+(a,)]), a))
            action = patches.get(context, greedy)
            if training:
                ep = receipt['episode']; eps = receipt['parameters']['epsilon']['rational']
                explore = ep['coins'][i]*eps[1] < eps[0]*(1 << 64)
                draw = receipt['draws'][i]
                assert draw == {'i': i, 'explore': explore, 'admissible': legal, 'a_cmd': step['a_cmd']}
                if explore:
                    limit = (1 << 64)-((1 << 64) % len(legal))
                    accepted = next(v for v in ep['action_draws'][i] if v < limit)
                    action = legal[accepted % len(legal)]
            assert step['a_cmd'] == action and action in legal
            assert step['u'] == controllers.get((state, action), action) == step['a_realized']
            assert not step['illegal']
            state, z, m = skey(step['state']), step['control']['z'], step['control']['m']

    def td(receipt):
        nonlocal train, policy_changes
        behavior(receipt, training=True)
        before, after = receipt['before'], receipt['after']
        assert before['immediate'] == after['immediate']
        for k in ('role', 'mode', 'source_label', 'reference_digest'):
            assert before[k] == after[k]
        work = qmap((before['current'] if before['mode'] == 'dq' else before['learning_values'])['Q'])
        state = (0, 2, 0, 0, 2); z, m = receipt['trace']['option_in_force'], 0
        effective = lambda q: work.get(q, reference[q])
        order, contexts = [], []
        for step in receipt['trace']['steps']:
            context = state+(z, m); q = context+(step['a_cmd'],)
            current = effective(q); target = float.fromhex(step['reward']['binary64_hex'])
            next_state, nz, nm = skey(step['state']), step['control']['z'], step['control']['m']
            if not step['terminal']:
                target += max(effective(next_state+(nz, nm, a)) for a in allowed[next_state+(nz, nm)])
            work[q] = current+0.5*(target-current)
            if q not in order: order.append(q)
            contexts.append(context); state, z, m = next_state, nz, nm
        assert [key(e['address']) for e in receipt['numeric_edits']] == order
        assert all(float.fromhex(e['value']['binary64_hex']).hex() == work[q].hex()
                   for e, q in zip(receipt['numeric_edits'], order))
        canonical = {q: v for q, v in work.items() if v != reference[q]}
        observed = qmap((after['current'] if after['mode'] == 'dq' else after['learning_values'])['Q'])
        assert {q: v.hex() for q, v in canonical.items()} == {q: v.hex() for q, v in observed.items()}
        patches = dmap(before['current']['D']); expected = dict(patches); edits = []
        if before['mode'] == 'patch-adaptive':
            for context in dict.fromkeys(contexts):
                if context in patches:
                    action = min(allowed[context], key=lambda a: (-canonical.get(context+(a,), reference[context+(a,)]), a))
                    expected[context] = action; edits.append((context, action))
        assert [(key(e['address']), e['value']) for e in receipt['policy_improvement_edits']] == edits
        assert dmap(after['current']['D']) == expected
        assert after['completed_episodes'] == before['completed_episodes']+1
        policy_changes += sum(expected[k] != v for k, v in patches.items())
        train += 1

    for row in rows:
        tag, p = row['tag'], row['payload']
        if tag == 'RAW_STEP':
            context = skey(p['pre_state'])+(p['pre_control']['z'], p['pre_control']['m'])
            assert p['a_cmd'] in allowed[context]
            if prefix:
                assert p['pre_state'] == prefix[-1]['result']['state'] and p['pre_control'] == prefix[-1]['result']['control']
            else: assert skey(p['pre_state'])[:3] == (0, 2, 0)
            prefix.append(p); steps += 1
        elif tag == 'RAW_ROLLOUT':
            assert [e['result'] for e in prefix] == p['steps']
            assert p['steps'][-1]['terminal'] and p['steps'][-1]['outcome'] == p['outcome']
            assert all(not e['terminal'] for e in p['steps'][:-1])
            assert p['mask'] == {'decision': None, 'controller': None, 'plant': None, 'trap': None}
            assert p['interventions'] == {'members': []}
            full_rollouts.append(p); prefix = []
        elif tag == 'INCOMPLETE_ROLLOUT':
            raise AssertionError('unexpected partial capture must remain failed')
        elif tag == 'TX_CALL':
            assert tx_before is None
            tx_before = p
        elif tag == 'TX_RETURN':
            assert tx_before is not None
            # All actual full transaction inputs/outputs retained; TD and B1 checks below independently account writes.
            tx_before = None
        elif tag == 'ORIGINAL_SOURCE':
            mode = p['mode']; audit = deepcopy(p['audit']); audit['payload'] = restored_source(audit['payload'])
            assert digest(audit['payload']) == audit['payload_sha256']
            sd = audit['payload']['native_source_payload']
            assert digest(sd) == audit['payload']['native_source_sha256']
            assert sd['scene'] == contract['new_scene'] and sd['regime'] == 'P'
            trace = full_rollouts[-1]; raw_factual = sd['raw_factual']
            state = (0, 2, 0, 0, 2); z, m = trace['option_in_force'], 0
            gamma = ['ProcessCommit'] if z != trace['base_option'] else []
            tolerance = sd['truth_evaluator_only']['whole_optimal_set_tolerance']
            for step, raw_step in zip(trace['steps'], raw_factual):
                assert raw_step == {'pre_state': list(state), 'z': z, 'm': m, 'a_cmd': step['a_cmd'],
                    'u': step['u'], 'a_realized': step['a_realized'], 'reward_hex': step['reward']['binary64_hex'],
                    'post_state': list(skey(step['state'])), 'post_control': [step['control']['z'], step['control']['m']],
                    'terminal': step['terminal'], 'outcome': step['outcome'], 'illegal': step['illegal']}
                legal = allowed[state+(z, m)]; best = max(reference[state+(z, m, a)] for a in legal)
                optimal = [a for a in legal if reference[state+(z, m, a)] >= best-tolerance]
                if step['a_cmd'] not in optimal: gamma.append('Decision_'+str(state[2]))
                assert step['u'] == step['a_cmd']
                state, z, m = skey(step['state']), step['control']['z'], step['control']['m']
            assert len(raw_factual) == len(trace['steps']) and gamma == sd['truth_evaluator_only']['Gamma_P_star']
            sources[mode] = sd
        elif tag == 'BOUND_BEFORE_ARMS':
            p = deepcopy(p)
            p['payload']['source']['payload'] = restored_source(p['payload']['source']['payload'])
            assert digest(p['payload']) == p['payload_sha256']
            declarations[p['payload']['decision_mode_before_arms']] = p['payload_sha256']
        elif tag == 'ORIGINAL_PAIR':
            mode = p['mode']; audit = p['audit']; assert digest(audit['payload']) == audit['payload_sha256']
            old = audit['payload']['original_v74_pair']; assert digest(old['payload']) == old['payload_sha256']
            pd = old['payload']; pre = sources[mode]['full_pre_stores']
            owners = {tuple(int(x) for x in arm[0].split(',')) for arm in pd['all_owner_receipts'][0]['ordered_receipts']}
            assert len(owners) == len(pd['cell_units']) == 7 and pd['residual_units_preserved'] == ['ProcessCommit']
            assert pd['whole_oracle_units'] == sources[mode]['truth_evaluator_only']['Gamma_P_star']
            for i, arm in enumerate(pd['all_owner_receipts']):
                post = arm['full_post_stores']; ledger = json.loads(arm['ledger_canonical'])
                assert post['P'] == pre['P'] and post['X'] == pre['X']
                channel = 'Q' if mode == 'dq' else 'D'
                assert post['D' if mode == 'dq' else 'Q'] == pre['D' if mode == 'dq' else 'Q']
                was = {tuple(a): v for a, v in pre[channel]}; now = {tuple(a): v for a, v in post[channel]}
                changed = {q for q in set(was)|set(now) if was.get(q) != now.get(q)}
                assert all((q[:-1] if mode == 'dq' else q) in owners for q in changed)
                if i == 0: assert post == pre and not changed
                deltas = []
                if mode == 'dq':
                    for q in sorted(changed):
                        before = float.fromhex(was[q]) if q in was else reference[q]
                        after = float.fromhex(now[q]) if q in now else reference[q]
                        deltas.append(abs(after-before))
                assert (ledger['n_scalar'], float(ledger['sum_abs_delta']).hex(), float(ledger['max_abs_delta']).hex()) == (
                    len(deltas), math.fsum(deltas).hex(), max(deltas, default=0.0).hex())
                for address, status, changed_flag in arm['ordered_receipts']:
                    owner = tuple(int(x) for x in address.split(','))
                    assert changed_flag == any((q[:-1] if mode == 'dq' else q) == owner for q in changed)
                    assert status == ('APPLIED' if changed_flag else 'EVALUABLE_NOOP')
            pairs[mode] = pd
        elif tag == 'HANDOFF':
            validate_composite(p); mode = p['ordered_current_composites'][0]['mode']; origins[mode] = p['origin_sha256']
            assert p['origin']['original_declaration']['bound_source_sha256'] == declarations[mode]
            assert all(c['completed_episodes'] == 0 for c in p['ordered_current_composites'])
        elif tag == 'OWNED_TRAIN':
            validate_composite(p['complete_pair_after']); r = p['training']
            assert p['origin_sha256'] == origins[r['before']['mode']] and p['role'] == r['before']['role']
            assert r['trace'] == full_rollouts[-1]
            td(r)
        elif tag == 'OWNED_EVAL':
            validate_composite(p['complete_pair_after']); r = p['evaluation']
            assert r['before'] == r['after'] and r['draws'] == [] and r['readonly']
            assert r['trace'] == full_rollouts[-1]
            behavior(r); evaluation += 1
        elif tag in ('FINAL_OWNED_PAIR',):
            validate_composite(p)
        elif tag in ('OWNERSHIP_REFUSALS', 'ROLE_AND_FULL_L_GATES'):
            assert p['counts_before'] == p['counts_after']
            if tag == 'ROLE_AND_FULL_L_GATES': validate_composite(p['complete_composites'])
        elif tag == 'ACTUAL_LOADED_SOURCE_INVENTORY':
            assert all(claim['input_binding_before'][name]['sha256'] == h for name, h in p.items())
    stderr = (HERE/'evidence/stderr.log').read_text(encoding='utf-8')
    assert 'test_04_full_L_fingerprint_role_alias_and_export_isolation' in stderr and 'AssertionError: mappingproxy({}) is not true' in stderr
    assert 'Ran 5 tests' in stderr and 'FAILED (failures=1)' in stderr
    native_returns = [r['payload'] for r in rows if r['tag'] == 'NATIVE_B1_RETURN']
    expected_arms = [arm for mode in ('dq', 'patch-adaptive') for arm in pairs[mode]['all_owner_receipts']]
    for observed, expected in zip(native_returns, expected_arms):
        assert old_wire(observed['full_post']) == expected['full_post_stores']
        assert observed['ledger_canonical'] == expected['ledger_canonical']
    assert not prefix and tx_before is None
    assert set(sources) == set(pairs) == set(origins) == {'dq', 'patch-adaptive'}
    assert len(full_rollouts) == result['counts']['rollout'] == 10
    assert steps == result['counts']['step'] and steps <= contract['budget']['step']
    patch_train = [r['payload']['training'] for r in rows if r['tag'] == 'OWNED_TRAIN' and r['payload']['training']['before']['mode'] == 'patch-adaptive']
    assert len(patch_train) == 2 and all(not r['after']['learning_values']['Q'] for r in patch_train)
    assert all(r['before']['learning_values'] == r['after']['learning_values'] for r in patch_train)
    assert train == evaluation == 4 and tags['NATIVE_B1_RETURN'] == result['counts']['B1'] == 4
    assert tags['TX_CALL'] == tags['TX_RETURN'] == result['counts']['transaction']
    output = {'status': 'V92_FAILED_CHILD_CONTENTS_VERIFIED_NOT_INTEGRATION_PASS',
              'started_at_utc': started, 'completed_at_utc': datetime.now(timezone.utc).isoformat(),
              'audit_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'capture_stdout_sha256': end['stdout']['sha256'], 'records': len(rows), 'tag_inventory': dict(tags),
              'bound_inputs': len(end['input_binding_after']), 'complete_raw_rollouts': len(full_rollouts),
              'raw_steps': steps, 'original_whole_B1_arms': 4, 'owned_manual_training_episodes': train,
              'owned_readonly_evaluations': evaluation, 'literal_policy_changes': policy_changes,
              'failed_method': 'test_04_full_L_fingerprint_role_alias_and_export_isolation',
              'failure': 'assert expected nonempty L but actual exact numeric TD leaves L empty',
              'nonempty_L_commitment_gate_completed': False,
              'runtime_identity_reconstructed_from_bytes': False, 'independent_expert': False,
              'scientific_qualification': False, 'old_checkers_or_RFL_executed': False,
              'canonical_decode_correction': 'restore only native source tolerance float for its original seal; full composite Q value markers remain literal wire content',
              'first_failed_stored_audit_preserved_not_rerun': True}
    with result_path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(output, stream, sort_keys=True, separators=(',', ':'), ensure_ascii=True); stream.write('\n')
    print(json.dumps(output, sort_keys=True))


if __name__ == '__main__':
    main()


