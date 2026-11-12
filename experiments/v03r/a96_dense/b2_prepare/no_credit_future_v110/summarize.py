"""Read-only stdlib summary of the first complete v110 native and stored audit.

This builder imports no learner, fixture, checker, protocol or collector.  It
requires actual complete native and stored-audit receipts before writing new
result artifacts once.  It does not turn empty responsibility into a treatment
contrast, zero Collateral, independent samples, or scientific qualification.
"""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
MODES = ('dq', 'patch-adaptive')
ROLES = ('reference', 'treatment')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def meta(path):
    digest, size = hashlib.sha256(), 0
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
            size += len(block)
    return {'bytes': size, 'sha256': digest.hexdigest()}


def load(path):
    return json.loads(path.read_bytes())


def output_once(path, data):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(canonical(data) + '\n')


def numeric_state(payload):
    return payload['current'] if payload['mode'] == 'dq' else payload['learning_values']


def scan_capture(path, child):
    digest, size, sequence = hashlib.sha256(), 0, 0
    tags, raw_stages = Counter(), Counter()
    sources, truth, metadata, futures = {}, {}, {}, {}
    banks, training, complete, equality, external, guards = [], [], [], {}, [], []
    source_transactions = ordinary_transactions = 0
    summary = None
    with path.open('rb') as stream:
        for raw in stream:
            assert raw.endswith(b'\n'), 'physical capture has incomplete final line'
            digest.update(raw)
            size += len(raw)
            record = json.loads(raw)
            assert record['seq'] == sequence, 'physical capture sequence differs'
            assert raw == (canonical(record) + '\n').encode('ascii'), 'noncanonical physical record'
            sequence += 1
            tag, mode, role, epoch, stage, payload = (record['tag'], record['mode'], record['role'],
                                                     record['epoch'], record['stage'], record['payload'])
            tags[tag] += 1
            if tag == 'ORIGINAL_SOURCE':
                assert mode not in sources
                sources[mode] = {'record_seq': record['seq'], 'audit': payload['audit'],
                                 'supplied_pre': payload['supplied_pre']}
            elif tag == 'SOURCE_TRUTH_ACTUAL':
                assert mode not in truth
                truth[mode] = dict(record_seq=record['seq'], **payload)
            elif tag == 'NO_CREDIT_METADATA':
                assert mode not in metadata
                metadata[mode] = dict(record_seq=record['seq'], **payload)
            elif tag == 'FUTURE_BEGIN':
                assert mode not in futures
                futures[mode] = dict(record_seq=record['seq'], **payload)
            elif tag == 'RAW':
                raw_stages[stage] += 1
                assert payload['actual_step_object_links'] is True
            elif tag == 'TX_CALL':
                if stage == 'source':
                    source_transactions += 1
                else:
                    assert stage == 'training', 'unexpected transaction scope'
                    ordinary_transactions += 1
            elif tag == 'BANK_END':
                assert mode in MODES and role in ROLES and type(epoch) is int
                banks.append({'record_seq': record['seq'], 'mode': mode, 'role': role, 'epoch': epoch,
                              'mean_hex': payload['orderedmean_hex'], 'raw_sha256': payload['raw_sha256'],
                              'raw_count': payload['traces_count'],
                              'captured_raw_count': payload['captured_raw_count']})
            elif tag == 'TRAIN_END':
                before, after = payload['before'], payload['after']
                assert before['mode'] == after['mode'] == mode
                assert before['role'] == after['role'] == role
                numeric_before, numeric_after = numeric_state(before), numeric_state(after)
                training.append({'record_seq': record['seq'], 'mode': mode, 'role': role, 'epoch': epoch,
                                 'return_hex': payload['return_hex'],
                                 'numeric_content_changed': numeric_before != numeric_after,
                                 'literal_policy_content_changed': before['current']['D'] != after['current']['D'],
                                 'numeric_edits_count': len(payload['numeric_edits']),
                                 'policy_improvement_edits_count': len(payload['policy_improvement_edits']),
                                 'numeric_entries_before': len(numeric_before['Q']),
                                 'numeric_entries_after': len(numeric_after['Q']),
                                 'explore_actual_steps': sum(draw['explore'] is True for draw in payload['draws']),
                                 'protected_immediate_unchanged': before['immediate'] == after['immediate'],
                                 'P_unchanged': before['current']['P'] == after['current']['P'],
                                 'X_unchanged': before['current']['X'] == after['current']['X'],
                                 'receipt_sha256': hashlib.sha256(canonical(payload).encode('ascii')).hexdigest()})
            elif tag == 'CURVE_COMPLETE':
                assert payload['role'] == role == payload['actual_role']
                complete.append({'record_seq': record['seq'], 'mode': mode, 'role': role,
                                 'origin_sha256': payload['origin_sha256'],
                                 'checkpoints': payload['checkpoints'],
                                 'training_count': payload['training_count'],
                                 'v_pre_hex': payload['v_pre_hex'], 't_max': payload['t_max'],
                                 'contrast_status': payload['contrast_status'],
                                 'collateral_status': payload['collateral_status'],
                                 'collateral': payload['collateral']})
            elif tag == 'NO_EDIT_ROLE_EQUALITY':
                assert payload['mode'] == mode
                equality[mode] = dict(record_seq=record['seq'], **payload)
            elif tag == 'EXTERNAL':
                assert mode in MODES and payload['role'] == role
                external.append({'record_seq': record['seq'], 'mode': mode, 'role': role,
                                 'origin_sha256': payload['origin_sha256'],
                                 'field_names': sorted(payload['projection']['fields']),
                                 'episodes': payload['projection']['episodes'],
                                 'projection_sha256': hashlib.sha256(
                                     canonical(payload['projection']).encode('ascii')).hexdigest(),
                                 'source_or_truth_or_cost_feature': payload['source_or_truth_or_cost_feature']})
            elif tag == 'GUARD_REJECTION':
                assert payload['before_counts'] == payload['after_counts']
                guards.append({'record_seq': record['seq'], 'mode': mode, **payload})
            elif tag == 'SUMMARY':
                assert summary is None
                summary = payload
    assert sequence == child['records'] and size == child['raw_bytes']
    assert digest.hexdigest() == child['canonical_sha256']
    assert summary is not None
    for key, value in summary.items():
        if key == 'wall_seconds':
            assert type(child[key]) is float and type(value) is dict and set(value) == {'binary64_hex'}, \
                'final physical wall_seconds wire shape differs'
            assert float.fromhex(value['binary64_hex']).hex() == child[key].hex(), \
                'final physical wall_seconds decoded exacthex differs'
        else:
            assert child[key] == value, 'final physical summary differs: ' + key
    assert tags['SUMMARY'] == 1 and not any(tags[tag] for tag in
        ('TOPLEVEL_FAILURE', 'FORBIDDEN_CALL', 'NATIVE_BUDGET_EXCEEDED', 'INCOMPLETE_RAW',
         'PENDING_STEP_RETURNS', 'PENDING_NATIVE_STEP_RETURNS', 'GUARD_UNEXPECTED_ACCEPTANCE'))
    assert set(sources) == set(truth) == set(metadata) == set(futures) == set(equality) == set(MODES)
    assert len(banks) == 16 and len(training) == 12 and len(complete) == len(external) == 4
    assert len(guards) == 19
    assert raw_stages == Counter({'source': 2, 'evaluation': 1600, 'training': 12})
    assert source_transactions == 0 and ordinary_transactions == child['counts']['transaction']
    for mode in MODES:
        actual_truth = truth[mode]
        assert actual_truth['regime'] == 'T' and actual_truth['outcome'] == 'TRAP'
        assert actual_truth['return_hex'] == (-1.02).hex()
        assert actual_truth['truth']['Gamma_T_star'] == ['Unknown/NoWrite']
        assert actual_truth['truth']['R_mech'] == [{'kind': 'rho_U', 'cell': [1, 2], 't': 0}]
        declaration = metadata[mode]['declaration']
        assert declaration['whole_units'] == declaration['residual_units'] == ['Unknown/NoWrite']
        assert declaration['cell_units'] == declaration['owner_addresses'] == []
        assert declaration['native_B1_arm_calls'] == declaration['owner_receipts'] == declaration['therapy_transactions'] == 0
        assert declaration['collateral_status'] == 'NOT_APPLICABLE_EMPTY_OWNER_SET' and declaration['collateral'] is None
        assert declaration['contrast_status'] == 'NO_SUBSTANTIVE_UPDATE_CONTRAST'
        for role in ROLES:
            role_banks = sorted((bank for bank in banks if bank['mode'] == mode and bank['role'] == role),
                                key=lambda bank: bank['epoch'])
            assert [bank['epoch'] for bank in role_banks] == list(range(4))
            assert all(bank['raw_count'] == bank['captured_raw_count'] == 100 for bank in role_banks)
    return {'records': sequence, 'raw_bytes': size, 'canonical_sha256': digest.hexdigest(),
            'tag_inventory': dict(tags), 'raw_stages': dict(raw_stages), 'sources': sources,
            'source_truth': truth, 'no_credit_metadata': metadata, 'future_origins': futures,
            'checkpoint_banks': banks, 'training_diagnostics': training, 'complete_role_curves': complete,
            'bookkeeping_role_equality': equality, 'closed_external_projections': external,
            'guard_rejections': guards, 'source_transactions': source_transactions,
            'ordinary_transactions': ordinary_transactions}


def prospective_v109():
    path = HERE.parent / 'paired_protocol_entry_v109'
    assert not any((path / name).exists() for name in ('evidence', 'evidence_preflight'))
    files = {file.name: meta(file) for file in sorted(path.glob('*')) if file.is_file()}
    return {'status': 'UNEXECUTED_PROSPECTIVE_SOURCE_ONLY', 'files': files,
            'actual_protocol_factory_or_permit_activation': 0, 'keys_allocated': 0,
            'formal_backend_connected': False, 'not_a_formal_collection_or_qualification_result': True}


def report_text(report):
    observed = report['actual_finite_result']
    counts = report['native']['counts']
    rows = []
    for curve in observed['role_curve_summaries']:
        means = ', '.join(format(float.fromhex(value), '.17g') for value in curve['means_hex'])
        equal = '是' if curve['equal_to_shared_pre_level_at_every_checkpoint'] else '否'
        rows.append(f"| {curve['mode']} | {curve['role']} | {means} | {equal} |")
    return '\n'.join([
        '# V0.3：真实 T 空责任投影的普通未来分支', '',
        '此前缺失的分支现在完成了有限真实执行：失败来源确实为 T/TRAP，完整责任是 `Unknown/NoWrite`，',
        'D_Q 与 D_patch 的责任投影均为空。保留失败和全部残余责任，不制造 B1 写入、回执或零 Collateral。', '',
        f"实际新增两个独立健康 owned 来源、两次 factual；两个来源各产生两个独立 no-edit 普通学习角色。",
        f"每角色执行 3 个训练回合，在 checkpoint 0、1、2、3 先评估原锁完整 100 场景。",
        f"首 native 的 4 个方法全部完成：{counts['rollout']} 次 rollout、{counts['step']} 步、",
        f"{counts['transaction']} 次普通 TD 事务，耗时 {report['native']['wall_seconds']:.3f} 秒。",
        '来源安装事务、B1 调用、law plan、owner 回执和治疗事务均为 0。事务调用并不等于学到新价值。', '',
        '| 路径 | 记账角色 | checkpoint 0、1、2、3 平均回报 | 每点精确等于共同健康参考 |',
        '|---|---|---|---|', *rows, '',
        f"实际 {len(observed['training_diagnostics'])} 个完整 TD receipt 中，",
        f"numeric 内容变化 {observed['numeric_content_change_episodes']} 次，",
        f"literal-D 内容变化 {observed['literal_policy_content_change_episodes']} 次。所有真实零响应均保留，",
        '没有要求 L 必须非空，也没有把无编辑角色的一致轨迹称为架构等效或反馈治疗收益。', '',
        '**本分支结论：没有归到该架构的责任，不应杜撰持久修正；但真实失败及残余责任仍保留，普通后续学习继续。**',
        'Transient trap 仅属于 factual 来源，后续普通环境不携带该 trap。因而普通表现不是证明“从该失败学会了规避 trap”，',
        '也不是处罚/不处罚实验、零一般伤害或独立种子总体结论。', '',
        '完整原始轨迹、TD、来源/模式/角色/I/R+L 绑定与 null/N/A、19 个真实无额外 native 门禁拒绝及闭合外部投影，',
        '已由新的 stdlib 存储审阅核对；运行时身份由实际新入口验证，存储审阅不重建身份，也不是独立专家认可。', '',
        '首次存储审阅实际 exit 1：最终 wall_seconds 的 native float 与 binary64 wire marker 比较不一致。',
        '原失败源码、完整 920 字节 stderr 和 capture 全部保留；新的定向 wire 修订审阅实际 exit 0，',
        '只解码该计时元数据，未改数值状态 marker，也没有重跑 native 或把第一次审阅改为通过。', '',
        '这补齐一个真实未完成的工程分支，不要求正收益才允许收口。原完整 T/P 条件族及 400/200 种子确认研究仍未完成。',
        '未启动 keys、正式 keyed Protocol/Curve/train_curve、RNG/DP/native calibration 或 collector。',
        'v109 仅为未执行的前瞻源码，没有已连接的正式学习后端、已激活 permit 或正式采集进展。',
        '旧失败、超时和 partial 记录未修改或重跑；自动续接仍关闭。', '',
        '入口：`result_summary.json`、`evidence/exit.json`、`stored_audit_wire_result.json`、`evidence_stored_audit_wire/exit.json`。',
        '首次审阅失败原件：`audit_stored.py`、`execute_audit.py`、`evidence_stored_audit/`。', ''
    ])


def main():
    contract = load(HERE / 'contract.json')
    folder = HERE / 'evidence'
    claim, exit_record, child = (load(folder / name) for name in ('claim.json', 'exit.json', 'child_summary.json'))
    assert exit_record['child_exit_code'] == 0 and exit_record['input_bytes_unchanged'] is True
    assert claim['input_binding_before'] == exit_record['input_binding_after']
    assert child['tests_run'] == 4 and child['failures'] == child['errors'] == child['skipped'] == 0
    assert child['pending_native_step_returns'] == 0
    assert child['profile_was_installed'] and child['profile_restored'] and child['original_function_identities_unchanged']
    for name in ('stdout', 'stderr'):
        assert meta(folder / (name + '.log')) == exit_record[name]
    for name in ('raw.jsonl', 'child_summary.json'):
        assert meta(folder / name) == exit_record[name]
    for path, pin in claim['input_binding_before'].items():
        assert meta(ROOT / path) == pin, 'declared native input changed: ' + path
    first_audit_folder = HERE / 'evidence_stored_audit'
    first_audit_exit = load(first_audit_folder / 'exit.json')
    first_audit_claim = load(first_audit_folder / 'claim.json')
    assert first_audit_exit['child_exit_code'] == 1 and first_audit_exit['input_bytes_unchanged'] is True
    assert first_audit_exit['native_child_exit_preserved'] == 0
    assert first_audit_claim['input_binding_before'] == first_audit_exit['input_binding_after']
    assert first_audit_exit['automatic_retry'] is False
    for name in ('stdout', 'stderr'):
        assert meta(first_audit_folder / (name + '.log')) == first_audit_exit[name]
    assert first_audit_exit['stderr'] == {
        'bytes': 920, 'sha256': '507eb01fe269dc8e2f34218829826ca0ff54108a2ffd08ef76fc13e899d531fd'}
    for name in ('audit_stored.py', 'execute_audit.py'):
        assert meta(HERE / name) == first_audit_claim['input_binding_before'][(HERE / name).relative_to(ROOT).as_posix()]
    first_failure = {'child_exit_code': first_audit_exit['child_exit_code'],
                     'native_child_exit_preserved': first_audit_exit['native_child_exit_preserved'],
                     'input_bytes_unchanged': first_audit_exit['input_bytes_unchanged'],
                     'source': meta(HERE / 'audit_stored.py'),
                     'launcher': meta(HERE / 'execute_audit.py'),
                     'claim': meta(first_audit_folder / 'claim.json'),
                     'receipt': meta(first_audit_folder / 'exit.json'),
                     'stdout': first_audit_exit['stdout'], 'stderr': first_audit_exit['stderr'],
                     'full_original_stderr': (first_audit_folder / 'stderr.log').read_bytes().decode('utf-8'),
                     'complete_stored_result_issued': (HERE / 'stored_audit_result.json').is_file(),
                     'error_scope': 'native float wall_seconds versus its binary64 wire metadata marker',
                     'failed_source_capture_preserved': True, 'native_reexecuted': False,
                     'not_a_first_stored_audit_pass': True, 'not_a_scientific_or_mechanism_failure': True}
    audit_folder = HERE / 'evidence_stored_audit_wire'
    audit_exit = load(audit_folder / 'exit.json')
    audit_claim = load(audit_folder / 'claim.json')
    assert audit_exit['child_exit_code'] == 0 and audit_exit['input_bytes_unchanged'] is True
    assert audit_claim['input_binding_before'] == audit_exit['input_binding_after']
    for name in ('stdout', 'stderr'):
        assert meta(audit_folder / (name + '.log')) == audit_exit[name]
    assert meta(HERE / 'stored_audit_wire_result.json') == audit_exit['stored_audit_wire_result.json']
    audit = load(HERE / 'stored_audit_wire_result.json')
    assert audit['schema'] == 'V110_INDEPENDENT_STDLIB_GENUINE_T_NO_CREDIT_FUTURE_STORED_AUDIT_WIRE_REVISION'
    assert audit['evidence']['complete_native_branch'] is True
    assert audit['evidence']['complete_checkpoint_banks'] == 16
    assert audit['evidence']['complete_role_handles'] == audit['evidence']['closed_external_projections'] == 4
    assert audit['native_receipt_preserved']['child_exit_code'] == 0
    assert audit['scientific_qualification'] is False
    capture = scan_capture(folder / 'raw.jsonl', child)
    counts = child['counts']
    assert counts['rollout'] == counts['rollout_return'] == 1614
    assert counts['step'] == counts['step_return'] and counts['transaction'] == counts['transaction_return']
    assert not any(counts.get(name, 0) for name in ('B1', 'law_plan', 'forbidden'))
    role_curves = []
    for curve in capture['complete_role_curves']:
        means_hex = [checkpoint['mean_hex'] for checkpoint in curve['checkpoints']]
        assert len(means_hex) == 4
        role_curves.append({'mode': curve['mode'], 'role': curve['role'], 'means_hex': means_hex,
                            'shared_pre_level_hex': curve['v_pre_hex'],
                            'equal_to_shared_pre_level_at_every_checkpoint': all(
                                value == curve['v_pre_hex'] for value in means_hex),
                            'training_episodes': curve['training_count'],
                            'not_independent_statistical_sample': True,
                            'not_substantive_treatment_arm': True})
    evidence = capture.copy()
    numeric_changes = sum(receipt['numeric_content_changed'] for receipt in capture['training_diagnostics'])
    policy_changes = sum(receipt['literal_policy_content_changed'] for receipt in capture['training_diagnostics'])
    evidence.update(role_curve_summaries=role_curves, numeric_content_change_episodes=numeric_changes,
                    literal_policy_content_change_episodes=policy_changes,
                    positive_numeric_response_required=False, L_nonempty_required=False,
                    ordinary_TRAP_avoidance_learning_claimed=False,
                    contrast_status='NO_SUBSTANTIVE_UPDATE_CONTRAST',
                    substantive_treatment_effect=None, collateral_status='NOT_APPLICABLE_EMPTY_OWNER_SET',
                    collateral=None, owner_receipts=0, B1_arm_calls=0, law_plans=0, therapy_transactions=0,
                    new_partial_native_gate_claimed=False)
    draft = prospective_v109()
    assert not any('paired_protocol_entry_v109/' in path for path in child['loaded_sources'])
    report = {'schema': 'V110_COMPLETE_FINITE_GENUINE_T_NO_CREDIT_FUTURE_RESULT',
              'created_at_utc': datetime.now(timezone.utc).isoformat(), 'parent_commit': contract['parent_commit'],
              'native': {'child_exit_code': exit_record['child_exit_code'], 'tests_run': child['tests_run'],
                         'failures': child['failures'], 'errors': child['errors'], 'skipped': child['skipped'],
                         'counts': counts, 'wall_seconds': child['wall_seconds'],
                         'input_binding_pins': len(claim['input_binding_before']),
                         'input_binding_bytes': sum(pin['bytes'] for pin in claim['input_binding_before'].values()),
                         'actual_loaded_source_pins': len(child['loaded_sources']),
                         'profile_was_installed': child['profile_was_installed'],
                         'profile_restored': child['profile_restored'],
                         'original_function_identities_unchanged': child['original_function_identities_unchanged'],
                         'receipt': meta(folder / 'exit.json'), 'capture': meta(folder / 'raw.jsonl')},
              'actual_finite_result': evidence,
              'stored_review': {'child_exit_code': audit_exit['child_exit_code'],
                                'result': meta(HERE / 'stored_audit_wire_result.json'),
                                'receipt': meta(audit_folder / 'exit.json'),
                                'wire_revised_source': meta(HERE / 'audit_stored_wire.py'),
                                'wire_revised_launcher': meta(HERE / 'execute_audit_wire.py'),
                                'wall_seconds_wire_revision': audit['wall_seconds_wire_revision'],
                                'not_independent_expert_or_sciencegate': True,
                                'runtime_identity_reconstructed': False},
              'first_stored_review_failure_preserved': first_failure,
              'prospective_v109_only': draft,
              'branch_complete': True, 'actual_T_empty_projection_future_gap_resolved': True,
              'scientific_qualification': False, 'original_confirmatory_study_complete': False,
              'collection_enabled': False, 'science_workload_keys_allocated': 0,
              'formal_protocol_episode_curve_collector_execution': 0, 'RNG_keyderive_DP_nativecalibration': 0,
              'old_fixture_checker_native_reexecution': 0, 'automatic_retry': False,
              'positive_total_benefit_required_for_V03_completion': False,
              'no_new_population_family_threshold_rule_adopted': True,
              'automation_remains_disabled': True,
              'builder_source': meta(Path(__file__))}
    output_once(HERE / 'result_summary.json', report)
    with (HERE / 'result.md').open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(report_text(report))
    print(canonical({'schema': report['schema'], 'branch_complete': True,
                     'records': capture['records'], 'raw_bytes': capture['raw_bytes'],
                     'counts': counts, 'numeric_content_change_episodes': numeric_changes,
                     'literal_policy_content_change_episodes': policy_changes,
                     'role_curve_summaries': role_curves, 'result_summary': meta(HERE / 'result_summary.json'),
                     'result_md': meta(HERE / 'result.md')}))


if __name__ == '__main__':
    main()
