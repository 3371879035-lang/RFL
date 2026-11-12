"""Once-only stdlib report of the actual v111 T dense workload and audit.

No old fixture/checker or RFL module is imported.  Closed external observation
views are the only inputs to descriptive curve measurement.  Source truth,
ledger/cost, state, role and resource evidence are attached outside that feature
door.  A complete fixed engineering case is not 400/200 seed confirmation.
"""
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
MODES = ('dq', 'patch-adaptive')
ROLES = ('reference', 'treatment')
FIELDS = ('future_rewards', 'future_outcomes', 'future_trajectories',
          'future_actions', 'future_observations')
AUDIT_SCHEMA = 'V111_INDEPENDENT_STDLIB_TRANSIENT_DECISION_FULL_WORKLOAD_STORED_AUDIT'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def read_json(path):
    return json.loads(path.read_bytes())


def meta(path):
    digest, size = hashlib.sha256(), 0
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
            size += len(block)
    return {'path': path.relative_to(ROOT).as_posix(), 'bytes': size, 'sha256': digest.hexdigest()}


def bare(pin):
    return {key: pin[key] for key in ('bytes', 'sha256')}


def scalar(marker):
    assert type(marker) is dict and set(marker) == {'binary64_hex'}
    value = float.fromhex(marker['binary64_hex'])
    assert math.isfinite(value)
    return value


def measure_closed_view(view):
    """Descriptive observation-only input; no truth, role, state, cost or source."""
    assert set(view) == {'fields', 'episodes', 'values', 'pre_level', 't_max'}
    assert set(view['fields']) == set(FIELDS)
    assert view['t_max'] == 465 and view['episodes'] == list(range(466))
    values = tuple(scalar(value) for value in view['values'])
    assert len(values) == 466
    assert all(len(view['fields'][name]) == 466 and
               all(len(bank) == 100 for bank in view['fields'][name]) for name in FIELDS)
    pre = scalar(view['pre_level'])
    change_points, previous = [], None
    for epoch, value in enumerate(values):
        if previous is None or previous.hex() != value.hex():
            change_points.append({'epoch': epoch, 'mean_return': value, 'mean_hex': value.hex()})
        previous = value
    return {'quantity': 'original ordered bank mean return, not success rate',
            'checkpoint_count': 466, 'evaluation_scenes_per_checkpoint': 100,
            'shared_pre_level': pre, 'shared_pre_level_hex': pre.hex(),
            'W0_mean_return': values[0], 'W0_mean_hex': values[0].hex(),
            'W465_mean_return': values[-1], 'W465_mean_hex': values[-1].hex(),
            'minimum_mean_return': min(values), 'maximum_mean_return': max(values),
            'equal_to_shared_pre_at_every_checkpoint': all(value.hex() == pre.hex() for value in values),
            'all_values_at_or_above_shared_pre': all(value >= pre for value in values),
            'change_points': change_points, 'curve_values_hex': [value.hex() for value in values],
            'closed_external_view_sha256': hashlib.sha256(canonical(view).encode('ascii')).hexdigest(),
            'no_seed_inference_or_final_utility_qualification': True}


def describe_pair(curves):
    reference, treatment = (curves[role] for role in ROLES)
    reference_values = [float.fromhex(value) for value in reference['curve_values_hex']]
    treatment_values = [float.fromhex(value) for value in treatment['curve_values_hex']]
    assert len(reference_values) == len(treatment_values) == 466
    differences = [treatment_value - reference_value for reference_value, treatment_value in
                   zip(reference_values, treatment_values)]
    sustained = next((epoch for epoch in range(466) if all(
        reference['curve_values_hex'][index] == treatment['curve_values_hex'][index]
        for index in range(epoch, 466))), None)
    return {'W0_treatment_minus_NoWrite': differences[0],
            'W0_treatment_minus_NoWrite_hex': differences[0].hex(),
            'W465_treatment_minus_NoWrite': differences[-1],
            'W465_treatment_minus_NoWrite_hex': differences[-1].hex(),
            'all_checkpoint_means_exact_equal': reference['curve_values_hex'] == treatment['curve_values_hex'],
            'maximum_absolute_checkpoint_mean_difference': max(abs(value) for value in differences),
            'sustained_exact_mean_equality_from_epoch': sustained,
            'not_original_recovery_time_or_statistical_equivalence': True,
            'not_punishment_ablation_or_architecture_ranking': True}


def numeric(payload):
    return payload['current'] if payload['mode'] == 'dq' else payload['learning_values']


def normalized_store_content(stores):
    """Compare the two explicit stored wire formats, not runtime identities."""
    result = {}
    for channel in ('D', 'P', 'X', 'Q'):
        entries = []
        for entry in stores[channel]:
            if type(entry) is dict:
                address, value = entry['address'], entry['value']
                if type(address) is dict:
                    state = address['state']
                    address = [state[name] for name in ('x', 'y', 't', 'kappa', 'phi')] + \
                        ([address['z'], address['m']] + ([address['a']] if channel == 'Q' else [])
                         if channel in ('D', 'Q') else [address['cmd']])
            else:
                address, value = entry
            if channel == 'Q':
                value = (scalar(value) if type(value) is dict else float.fromhex(value)).hex()
            entries.append([address, value])
        result[channel] = sorted(entries, key=canonical)
    return result


def read_ledger_arms(pair_record):
    original = pair_record['payload']['original_v74_pair']['payload']
    arms = []
    for role, arm in zip(ROLES, original['all_owner_receipts']):
        ledger = json.loads(arm['ledger_canonical'])
        receipts = arm['ordered_receipts']
        assert len(receipts) == 1 and len(ledger['receipts']) == 1
        status_counts = Counter(receipt[1] for receipt in receipts)
        arms.append({'role': role, 'full_immediate_post': arm['full_post_stores'],
                     'ordered_owner_receipts': receipts, 'ledger_canonical': arm['ledger_canonical'],
                     'status_counts': dict(status_counts),
                     'store_changed_addresses': sum(receipt[2] is True for receipt in receipts),
                     'scalar_metrics_applicable': ledger['scalar_metrics_applicable'],
                     'n_scalar': ledger['n_scalar'], 'sum_abs_delta': ledger['sum_abs_delta'],
                     'max_abs_delta': ledger['max_abs_delta'],
                     'fingerprint_pre': ledger['fingerprint_pre'],
                     'fingerprint_post': ledger['fingerprint_post'],
                     'full_store_changed': ledger['fingerprint_pre'] != ledger['fingerprint_post']})
    assert len(arms) == 2 and original['native_B1_arm_calls'] == 2
    return {'original_pair_payload': original, 'ordered_arms': arms,
            'complete_whole_pair': original['route'] == 'COMPLETE_ORACLE_WHOLE_B1_PAIR',
            'all_owner_receipts': 2, 'native_B1_arm_calls': original['native_B1_arm_calls']}


def scan_child(mode, folder, receipt, audited):
    summary = read_json(folder / 'child_summary.json')
    assert summary['mode'] == receipt['mode'] == audited['mode'] == mode
    for name in ('stdout', 'stderr'):
        assert bare(meta(folder / (name + '.log'))) == receipt[name]
    for name in ('raw.jsonl.gz', 'child_summary.json'):
        assert bare(meta(folder / name)) == receipt[name]
    assert bare(meta(folder / 'raw.jsonl.gz')) == audited['compressed_meta']
    digest, size, sequence = hashlib.sha256(), 0, 0
    tags, raw_stage_counts = Counter(), Counter()
    source_install_tx = therapy_tx = after_pair_source_tx = ordinary_tx = 0
    source_bound, pair_complete, b1_returns, arm_therapy_tx = False, False, [], []
    current_arm_therapy_tx = 0
    source_configuration = source = source_truth = source_pair = original_pair = result = failure = None
    prepared = restoration = inventory = None
    bank_means, training, curves, final_composites, external = [], [], {}, {}, {}
    with gzip.open(folder / 'raw.jsonl.gz', 'rb') as stream:
        for line in stream:
            assert line.endswith(b'\n')
            digest.update(line)
            size += len(line)
            record = json.loads(line)
            assert record['seq'] == sequence and record['mode'] == mode
            assert line == (canonical(record) + '\n').encode('ascii')
            sequence += 1
            tag, payload, role, epoch, stage = (record['tag'], record['payload'], record['role'],
                                               record['epoch'], record['stage'])
            tags[tag] += 1
            if tag == 'SOURCE_CONFIGURATION_PLANNED':
                assert source_configuration is None
                source_configuration = payload
            elif tag == 'ORIGINAL_SOURCE':
                assert source is None
                source = payload['audit']
            elif tag == 'SOURCE_TRUTH_ACTUAL':
                assert source_truth is None
                source_truth = payload
            elif tag == 'BOUND_BEFORE_ARMS':
                assert source_bound is False
                source_bound = True
            elif tag == 'ORIGINAL_PAIR':
                assert original_pair is None
                original_pair = payload
                pair_complete = True
            elif tag == 'SOURCE_PAIR_ACTUAL':
                assert source_pair is None
                source_pair = payload
            elif tag == 'CURVE_PREPARED':
                assert prepared is None
                prepared = payload
            elif tag == 'RAW_ROLLOUT':
                raw_stage_counts[stage] += 1
                assert payload['actual_step_object_links'] is True
            elif tag == 'TX_CALL':
                if stage == 'B1':
                    assert source_bound and not pair_complete
                    therapy_tx += 1
                    current_arm_therapy_tx += 1
                elif stage == 'source':
                    if not source_bound:
                        source_install_tx += 1
                    elif not pair_complete:
                        therapy_tx += 1
                        current_arm_therapy_tx += 1
                    else:
                        after_pair_source_tx += 1
                elif stage == 'training':
                    ordinary_tx += 1
            elif tag == 'NATIVE_B1_RETURN':
                b1_returns.append(payload)
                arm_therapy_tx.append(current_arm_therapy_tx)
                current_arm_therapy_tx = 0
            elif tag == 'BANK_END':
                bank_means.append({'record_seq': record['seq'], 'role': role, 'epoch': epoch,
                                   'count': payload['count'], 'mean_hex': payload['mean_hex'],
                                   'raw_sha256': payload['ordered_raw_sha256']})
            elif tag == 'CORE_EPISODE':
                before, after = payload['before'], payload['after']
                assert before['mode'] == after['mode'] == mode and before['role'] == after['role'] == role
                numerical_before, numerical_after = numeric(before), numeric(after)
                training.append({'record_seq': record['seq'], 'role': role, 'epoch': payload['epoch'],
                                 'numeric_content_changed': numerical_before != numerical_after,
                                 'literal_policy_content_changed': before['current']['D'] != after['current']['D'],
                                 'numeric_edits_count': len(payload['numeric_edits']),
                                 'policy_improvement_edits_count': len(payload['policy_improvement_edits']),
                                 'numeric_entries_before': len(numerical_before['Q']),
                                 'numeric_entries_after': len(numerical_after['Q']),
                                 'protected_I_unchanged': before['immediate'] == after['immediate'],
                                 'P_unchanged': before['current']['P'] == after['current']['P'],
                                 'X_unchanged': before['current']['X'] == after['current']['X'],
                                 'actual_return_hex': payload['return_hex'],
                                 'receipt_sha256': hashlib.sha256(canonical(payload).encode('ascii')).hexdigest()})
            elif tag == 'FINAL_COMPOSITE':
                assert role in ROLES and role not in final_composites
                final_composites[role] = payload
            elif tag == 'EXTERNAL_VIEW':
                assert role in ROLES and role not in curves
                measured = measure_closed_view(payload)
                curves[role] = dict(measured, role=role, mode=mode)
                external[role] = {'record_seq': record['seq'], 'feature_names': sorted(payload['fields']),
                                  'closed_external_view_sha256': measured['closed_external_view_sha256']}
            elif tag == 'RESULT':
                assert result is None
                result = payload
            elif tag == 'CAPTURE_RESTORATION':
                assert restoration is None
                restoration = payload
            elif tag == 'ACTUAL_LOADED_SOURCE_INVENTORY':
                assert inventory is None
                inventory = payload
            elif tag == 'FAILURE':
                assert failure is None
                failure = payload
    assert sequence == summary['records'] == audited['records']
    assert size == summary['uncompressed_bytes'] == audited['uncompressed_bytes']
    assert digest.hexdigest() == summary['canonical_sha256'] == audited['canonical_sha256']
    assert restoration == summary['capture_restoration']
    for counter in ('rollout', 'step', 'transaction', 'B1'):
        assert summary['counts'].get(counter, 0) == audited['actual_counts'].get(counter, 0)
    complete = bool(receipt['child_exit_code'] == 0 and summary['completed'] and audited['complete'])
    if complete:
        assert result is not None and result['completed'] is True and failure is None
        assert result['counts'] == summary['counts']
        assert inventory is not None and all(restoration.values())
        assert summary['extra_original_sources'] == summary['issued_original_sources'] == 1
        assert summary['source_transactions'] == 0 and summary['source_regime'] == 'T'
        assert summary['whole_owner_count'] == 1 and summary['original_feedback_may_be_evaluable_noop'] is True
        assert source_configuration is not None and source is not None and source_truth is not None
        assert source_pair is not None and original_pair is not None and prepared is not None
        assert set(curves) == set(final_composites) == set(external) == set(ROLES)
        assert tags['CORE_EPISODE'] == len(training) == 930 and len(bank_means) == 932
        assert summary['counts']['rollout'] == summary['counts']['rollout_return'] == 94131
        assert summary['counts']['B1'] == 2 and not summary['counts'].get('forbidden', 0)
        assert raw_stage_counts['source'] == 1 and raw_stage_counts['evaluation'] == 93200
        assert raw_stage_counts['training'] == 930
        assert source_configuration['regime'] == source_truth['regime'] == 'T'
        assert source_configuration['scene'] == [0, 2, 0, 44, 1]
        assert source_truth['outcome'] == 'COLLISION' and source_truth['return_hex'] == (-1.04).hex()
        assert source_truth['truth']['Gamma_T_star'] == ['Decision_1']
        assert source_truth['truth']['Gamma_P_star'] is None
        assert source_pair['whole_units'] == source_pair['cell_units'] == ['Decision_1']
        assert len(source_pair['owner_addresses']) == 1 and source_pair['residual_units'] == []
        assert source_install_tx == after_pair_source_tx == 0
        assert source_configuration['source_transactions'] == source_configuration['source_install_edits'] == 0
        assert source_configuration['option_fault'] is None and source_configuration['forced_action'] == 3
        assert source_truth['actual_mask']['decision'] == {'t': 1, 'action': 3}
        assert source_truth['actual_mask'] == source_configuration['mask']
        assert all(source_truth['actual_mask'][name] is None for name in ('controller', 'plant', 'trap'))
        assert all(not source_truth['full_pre'][name] for name in ('D', 'P', 'X', 'Q'))
        assert source_truth['base_option'] == source_truth['option_in_force'] == 1
        for role in ROLES:
            expected = [entry['mean_hex'] for entry in next(
                curve for curve in audited['ordered_curves'] if curve['role'] == role)['ordered_curve']]
            assert curves[role]['curve_values_hex'] == expected
            recorded = sorted((entry for entry in bank_means if entry['role'] == role), key=lambda entry: entry['epoch'])
            assert [entry['epoch'] for entry in recorded] == list(range(466))
            assert all(entry['count'] == 100 for entry in recorded)
            assert [entry['mean_hex'] for entry in recorded] == expected
    ledger = read_ledger_arms(original_pair) if original_pair is not None else None
    if ledger is not None:
        assert source_pair is not None
        assert len(b1_returns) == len(arm_therapy_tx) == 2
        assert [normalized_store_content(arm['full_immediate_post']) for arm in ledger['ordered_arms']] == \
            [normalized_store_content(stores) for stores in source_pair['full_immediate_posts']]
        for arm, actual_receipts in zip(ledger['ordered_arms'], source_pair['ordered_receipts']):
            assert [(receipt['canonical_form'], receipt['status'], receipt['store_changed']) for receipt in actual_receipts] == \
                [tuple(receipt) for receipt in arm['ordered_owner_receipts']]
        for arm, returned, calls in zip(ledger['ordered_arms'], b1_returns, arm_therapy_tx):
            assert returned['ledger_canonical'] == arm['ledger_canonical']
            assert normalized_store_content(returned['full_post']) == normalized_store_content(arm['full_immediate_post'])
            arm['actual_therapy_transaction_calls'] = calls
        assert sum(arm_therapy_tx) == therapy_tx
    assert source_install_tx + therapy_tx + after_pair_source_tx + ordinary_tx == summary['counts'].get('transaction', 0)
    assert source_install_tx == audited['source_installation_transactions']
    assert therapy_tx == audited['original_B1_therapy_transactions']
    assert ordinary_tx == audited['ordinary_TD_transactions']
    source_no_new_value = bool(source_truth is not None and
        source_truth['factual_suffix_return_hex'] == source_truth['Q_reference_factual_action_hex'])
    return {'mode': mode, 'complete': complete, 'native_child_exit_code': receipt['child_exit_code'],
            'capture': meta(folder / 'raw.jsonl.gz'), 'canonical_records': sequence,
            'canonical_uncompressed_bytes': size, 'canonical_sha256': digest.hexdigest(),
            'tag_inventory': dict(tags), 'actual_raw_stage_counts': dict(raw_stage_counts),
            'source_configuration': source_configuration, 'actual_owned_source': source,
            'actual_source_truth': source_truth, 'actual_source_pair': source_pair,
            'source_factual_suffix_exactly_matches_Q_reference_for_bad_action': source_no_new_value,
            'actual_B1_ledger_arms': ledger, 'actual_curve_origin': prepared,
            'source_install_transactions': source_install_tx, 'actual_therapy_transaction_calls': therapy_tx,
            'post_pair_source_phase_transactions': after_pair_source_tx,
            'ordinary_training_transactions': ordinary_tx,
            'actual_counts': audited['actual_counts'], 'native_call_return_counts': summary['counts'],
            'actual_extra_original_sources': summary['extra_original_sources'],
            'actual_issued_original_sources': summary['issued_original_sources'],
            'capture_restoration': restoration, 'actual_loaded_source_inventory': inventory,
            'independent_T_source_and_B1_observations': audited['T_source_and_B1_observations'],
            'complete_checkpoint_banks': len(bank_means), 'ordered_checkpoint_banks': bank_means,
            'chronological_training_diagnostics': training,
            'numeric_content_change_episodes': sum(entry['numeric_content_changed'] for entry in training),
            'literal_policy_content_change_episodes': sum(entry['literal_policy_content_changed'] for entry in training),
            'actual_TD_and_policy_audit_diagnostics': audited['TD_and_policy_diagnostics'],
            'closed_external_curve_descriptions': curves, 'external_input_pins': external,
            'final_composites': final_composites,
            'observed_bookkeeping_roles': None if result is None else result['roles'],
            'actual_result_record': result, 'actual_failure_record': failure,
            'instrumented_resources': {'wall_seconds': summary['wall_seconds'], 'cpu_seconds': summary['cpu_seconds'],
                                     'peaks': summary['peaks'],
                                     'capture_encode_seconds': summary['encode_seconds'],
                                     'capture_write_seconds': summary['write_seconds'],
                                     'actual_resource_samples': audited['resource_samples'],
                                     'not_production_or_general_worst_case_timing': True},
            'current_pair_Collateral_status': 'NOT_MEASURED_FOR_THIS_PAIR', 'current_pair_Collateral': None,
            'old_P_Collateral_result_transferred': False, 'not_punishment_ablation': True,
            'ordinary_future_does_not_carry_source_transient_fault': True,
            'source_failure_internalization_harm_claimed': False,
            'numeric_learning_or_L_nonempty_required': False}


def render(report):
    completed = report['complete_fixed_T_dense_case']
    lines = ['# V0.3：真实 T/Decision₁ 完整未来学习对照', '',
             ('两个架构的首次完整 dense 输入流均已执行并经新存储审阅核对。' if completed else
              '本次首次实际执行未全部闭合，以下保留已完成与失败/partial，不补全、不重跑。'), '',
             '来源是健康 learner 在 T 环境的真实 transient decision fault：第 1 步强制 RIGHT，',
             '两步发生 COLLISION，回报 −1.04；原结构责任只有 `Decision_1`，一个 owner，无残余。',
             '普通 future 不携带这个 transient fault，不将失败归因换成 P 的最优成员规则。', '',
             '| 路径 | NoWrite W0 | 原更新后 W0 | NoWrite W465 | 原更新后 W465 | 全 checkpoint 均值精确相同 |',
             '|---|---:|---:|---:|---:|---|']
    for child in report['children']:
        if child['complete']:
            curves = child['closed_external_curve_descriptions']
            reference, treatment = (curves[role] for role in ROLES)
            pair = report['per_complete_stream_descriptive_pairs'][child['mode']]
            lines.append(f"| {child['mode']} | {reference['W0_mean_return']:.17g} | {treatment['W0_mean_return']:.17g} | "
                         f"{reference['W465_mean_return']:.17g} | {treatment['W465_mean_return']:.17g} | "
                         f"{'是' if pair['all_checkpoint_means_exact_equal'] else '否'} |")
        else:
            lines.append(f"| {child['mode']} | 未签完整曲线 | 未签完整曲线 | 未签完整曲线 | 未签完整曲线 | 不补零 |")
    lines += ['', '## 实际更新与学习', '']
    for child in report['children']:
        ledger = child['actual_B1_ledger_arms']
        if ledger is not None:
            statuses = '; '.join(f"{arm['role']}: {arm['status_counts']} / changed={arm['store_changed_addresses']}"
                                 for arm in ledger['ordered_arms'])
            lines.append(f"- {child['mode']} 的原完整 B1：{statuses}；实际治疗事务调用 {child['actual_therapy_transaction_calls']} 次。"
                         'NOOP 是 0 状态差，不等于没有事务；完整原 receipt、标量和全 store 留在 JSON。')
        if child['actual_source_truth'] is not None:
            truth = child['actual_source_truth']
            lines.append(f"- 该来源 factual suffix={truth['factual_suffix_return_hex']}，"
                         f"原 Q* 的错误 RIGHT 值={truth['Q_reference_factual_action_hex']}；"
                         f"精确同值={child['source_factual_suffix_exactly_matches_Q_reference_for_bad_action']}。")
        lines.append(f"- 实际 {len(child['chronological_training_diagnostics'])} 个 TD receipt："
                     f"numeric 内容变化 {child['numeric_content_change_episodes']} 次，"
                     f"literal-D 内容变化 {child['literal_policy_content_change_episodes']} 次，"
                     f"普通训练事务调用 {child['ordinary_training_transactions']} 次。所有零值保留，不要求 APPLIED 或 L 非空。")
    all_noop = completed and all(all(not arm['full_store_changed'] for arm in child['actual_B1_ledger_arms']['ordered_arms'])
                                for child in report['children'])
    if all_noop:
        lines += ['', '这是合法真实的“反馈没有提供新的值信息”对照：原 B1 可评估而未改变持久 store，',
                  '不等于删去失败或裁剪责任。不能从此声称“内化 T 错误产生了损害”，也不能把 no-op 宣称为治疗收益。']
    lines += ['', '## 执行证据与边界', '']
    for child in report['children']:
        resource = child['instrumented_resources']
        lines.append(f"- {child['mode']}：native exit {child['native_child_exit_code']}，"
                     f"actual={child['actual_counts']}，完整 bank={child['complete_checkpoint_banks']}，"
                     f"wall={resource['wall_seconds']:.3f}s，CPU={resource['cpu_seconds']:.3f}s；计时含 profile/记录/检查，非生产证书。")
    lines += ['', '当前 pair 的 Collateral 没有实际测量：`NOT_MEASURED_FOR_THIS_PAIR`，值为 null；不迁移旧 P 的 whole 零值。',
              '本次是固定 T 机制与预声明工程输入流的条件性结果，不是处罚/不处罚实验、跨架构优胜、统计等效或一般零伤害。',
              '正收益不是 V0.3 完成前提；本个案完整也不冒充原完整 T/P/k×shape family、400/200 独立 seed 确认或最终合取已完成。',
              'Q*、alpha、epsilon、原 ordinary 学习及 F1 字节保持；没有 keys/RNG/DP/native calibration/正式 collector，自动续接仍关闭。',
              '旧 fixture、失败、超时和 partial 没有重跑或改成通过。数据来自当前新首 native 与新的独立 stdlib 存储审阅，非独立专家认可。', '',
              '完整来源/B1/原始曲线/逐 TD/资源/哈希与真实失败信息见同目录 `result_summary.json`。', '']
    return '\n'.join(lines)


def main():
    assert not (HERE / 'result_summary.json').exists() and not (HERE / 'result.md').exists(), 'exclusive report outputs'
    contract = read_json(HERE / 'contract.json')
    native = read_json(HERE / 'evidence/exit.json')
    claim = read_json(HERE / 'evidence/claim.json')
    assert native['input_bytes_unchanged'] and not native['automatic_retry']
    assert claim['input_binding_before'] == native['input_binding_after']
    assert claim['parent_commit'] == contract['parent_commit'] and claim['serial_children'] is True
    assert claim['planned_modes'] == list(MODES)
    for path, pin in claim['input_binding_before'].items():
        assert bare(meta(ROOT / path)) == pin, 'declared input drift: ' + path
    audit_exit = read_json(HERE / 'evidence_stored_audit/exit.json')
    audit = read_json(HERE / 'stored_audit_result.json')
    assert audit_exit['native_exit_code'] == 0 and audit_exit['input_bytes_unchanged']
    assert bare(meta(HERE / 'stored_audit_result.json')) == audit_exit['stored_audit_result']
    assert audit['schema'] == AUDIT_SCHEMA and audit['scientific_qualification'] is False
    assert audit['native_child_receipts_preserved'] == native['child_receipts']
    children = []
    for receipt in native['child_receipts']:
        mode = receipt['mode']
        assert mode in MODES and mode not in [child['mode'] for child in children]
        folder = HERE / 'evidence' / mode
        assert read_json(folder / 'exit.json') == receipt
        audited = next(child for child in audit['children'] if child['mode'] == mode)
        children.append(scan_child(mode, folder, receipt, audited))
    assert [child['mode'] for child in children] == list(MODES[:len(children)])
    complete = bool(len(children) == 2 and native['completed'] and all(child['complete'] for child in children))
    descriptions = {child['mode']: describe_pair(child['closed_external_curve_descriptions'])
                    for child in children if child['complete']}
    selected = [HERE / 'contract.json', HERE / 'evidence/claim.json', HERE / 'evidence/exit.json',
                HERE / 'stored_audit_result.json', HERE / 'evidence_stored_audit/exit.json',
                HERE / 'workload.py', HERE / 'execute.py', HERE / 'audit_stored.py', HERE / 'execute_audit.py',
                Path(__file__), ROOT / contract['healthy_reference']['path'], ROOT / contract['dev_lock']['path']]
    for mode in [child['mode'] for child in children]:
        selected += [HERE / 'evidence' / mode / name for name in
                     ('claim.json', 'exit.json', 'child_summary.json', 'raw.jsonl.gz', 'stdout.log', 'stderr.log')]
    pins = {path.relative_to(ROOT).as_posix(): bare(meta(path)) for path in selected}
    report = {'schema': 'V111_ACTUAL_TRANSIENT_DECISION_FULL_DENSE_FIXED_CASE_RESULT',
              'generated_at_utc': datetime.now(timezone.utc).isoformat(), 'parent_commit': contract['parent_commit'],
              'status': 'COMPLETE_FIXED_T_ENGINEERING_CASE_NOT_CONFIRMATORY_PASS' if complete else
                        'ACTUAL_PARTIAL_FIXED_T_CASE_PRESERVED_NO_RETRY',
              'complete_fixed_T_dense_case': complete, 'original_confirmatory_study_complete': False,
              'positive_overall_benefit_is_not_a_completion_requirement': True,
              'question': 'Given the actual transient Decision_1 responsibility, what do original legal persistent laws change and how does ordinary future learning proceed?',
              'mean_return_is_not_success_rate': True, 'children': children,
              'per_complete_stream_descriptive_pairs': descriptions,
              'aggregate_actual_counts': dict(sum((Counter(child['actual_counts']) for child in children), Counter())),
              'new_actual_owned_sources': len([child for child in children if child['actual_owned_source'] is not None]),
              'current_pair_Collateral_status': 'NOT_MEASURED_FOR_THIS_PAIR', 'current_pair_Collateral': None,
              'old_P_Collateral_zero_transferred': False,
              'closed_metric_feature_door': 'Only actual completed EXTERNAL_VIEW fields/episodes/values/pre_level/t_max; source/truth/role/state/ledger/cost are separate provenance.',
              'fixed_engineering_stream_not_seed_inference': True, 'punishment_ablation': False,
              'universal_no_harm_equivalence_or_architecture_winner': False,
              'source_T_fault_carried_into_ordinary_future': False,
              'nonzero_TD_APPLIED_or_nonempty_L_required': False,
              'scientific_qualification': False, 'old_F1_PASS_transferred': False,
              'old_fixture_checker_native_reexecution': 0, 'automatic_retry': False,
              'new_science_or_workload_keys': 0, 'RNG_keyderive_DP_nativecalibration': 0,
              'formal_keyed_Protocol_Curve_train_curve_collector_collection': False,
              'collection_authorized': False, 'scientific_STOP': False,
              'automation_remains_disabled': True,
              'stored_review': {'source': meta(HERE / 'audit_stored.py'),
                                'launcher': meta(HERE / 'execute_audit.py'),
                                'receipt': meta(HERE / 'evidence_stored_audit/exit.json'),
                                'result': meta(HERE / 'stored_audit_result.json'),
                                'not_independent_expert_or_sciencegate': True,
                                'runtime_identity_reconstructed': False},
              'source_binding_before': pins}
    assert pins == {path.relative_to(ROOT).as_posix(): bare(meta(path)) for path in selected}
    report['source_binding_after'] = pins.copy()
    report['input_bytes_unchanged'] = True
    with (HERE / 'result_summary.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, sort_keys=True, ensure_ascii=False, indent=2)
        stream.write('\n')
    with (HERE / 'result.md').open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(render(report))
    print(canonical({'schema': report['schema'], 'status': report['status'],
                     'complete_fixed_T_dense_case': complete,
                     'aggregate_actual_counts': report['aggregate_actual_counts'],
                     'result_summary': meta(HERE / 'result_summary.json'), 'result_md': meta(HERE / 'result.md')}))


if __name__ == '__main__':
    main()
