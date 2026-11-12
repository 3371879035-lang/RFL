"""Once-only actual v112 recovery-observability canary summary, stdlib only.

Original utility/retention formula source is copied and checked below. Metrics
see only completed closed raw-derived external observation views. Source truth,
role, state, ledger/cost and whole-Collateral provenance are kept outside that
feature door. No old fixture/checker or RFL module is imported or executed.
"""
import ast
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import textwrap

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
MODES = ('dq', 'patch-adaptive')
ROLES = ('reference', 'treatment')
FIELDS = ('future_rewards', 'future_outcomes', 'future_trajectories',
          'future_actions', 'future_observations')
K_RECOVERY = 3
RECOVERY_FRACTION = 0.95
ProtocolError = ValueError
COPIED_FUNCTIONS = ('_require_real', '_require_horizon', '_require_curve',
                    'recovery_time', 'deficit_auc', '_require_grid', '_at',
                    'retention_at_h', 'late_window_retention')
AUDIT_SCHEMA = 'V112_INDEPENDENT_STDLIB_RECOVERY_OBSERVABILITY_FULL_WORKLOAD_STORED_AUDIT'


def _require_real(value, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProtocolError(f"{what} {value!r} is not a real number")
    return float(value)


def _require_horizon(t_max) -> int:
    if isinstance(t_max, bool) or not isinstance(t_max, int):
        raise ProtocolError(
            f"T_max {t_max!r} is not an integer episode index; the horizon is a design quantity "
            "supplied by the caller, never inferred from the curve")
    if t_max <= 0:
        raise ProtocolError(f"T_max {t_max!r} must be a positive episode index")
    return t_max


def _require_curve(values, episodes, t_max: int) -> tuple:
    r"""A curve is a sequence of observations at **real episode indices spanning the horizon**.

    $$\boxed{episodes[0] = 0, \qquad episodes[-1] = T_{\max}, \qquad 0 \le t_i \le T_{\max}}$$
    """
    values, episodes = tuple(values), tuple(episodes)
    if len(values) != len(episodes):
        raise ProtocolError(
            f"the curve has {len(values)} values and {len(episodes)} episode indices; every "
            "observation belongs to the episode index it was taken at")
    if not values:
        raise ProtocolError("the curve is empty; an empty curve has no recovery and no deficit")
    for i, (v, t) in enumerate(zip(values, episodes)):
        _require_real(v, f"the curve value at position {i}")
        if isinstance(t, bool) or not isinstance(t, int):
            raise ProtocolError(
                f"the episode index at position {i} is {t!r}, not an integer; a checkpoint grid is "
                "a set of real episode indices")
        if not 0 <= t <= t_max:
            raise ProtocolError(
                f"the episode index {t} at position {i} lies outside [0, T_max={t_max}]; the curve "
                "describes the horizon and nothing beyond it")
    for a, b in zip(episodes, episodes[1:]):
        if not a < b:
            raise ProtocolError(
                f"the episode indices must be strictly increasing, got {a} then {b}")
    if episodes[0] != 0:
        raise ProtocolError(
            f"the curve starts at episode {episodes[0]} rather than 0; the checkpoint grid contains "
            "the start of the horizon (05 6.2), so a curve missing it would leave the first "
            "interval unobserved")
    if episodes[-1] != t_max:
        raise ProtocolError(
            f"the curve ends at episode {episodes[-1]} but T_max is {t_max}; a curve that stops "
            "short is refused rather than padded, because RMST and DeficitAUC would then describe "
            "different intervals and any tail rule would be an estimator chosen silently")
    return values, episodes


def recovery_time(values, episodes, *, pre_level: float, t_max: int) -> int | None:
    r"""$\tau$, or ``None`` for a right-censored observation at $t_{\max}$.

    $$\boxed{\tau = \inf\{t : V_{t'} \ge 0.95\,V_{\text{pre}}\ \forall t' \in [t, t+K-1]\}}$$

    A *maintained* run of $K$ consecutive checkpoints at or above the threshold. One or two
    crossings are not a recovery, and a dip inside a window voids that window rather than being
    averaged away.
    """
    t_max = _require_horizon(t_max)
    values, episodes = _require_curve(values, episodes, t_max)
    threshold = RECOVERY_FRACTION * _require_real(pre_level, "the pre-update level")
    at_or_above = [v >= threshold for v in values]
    for i in range(len(values) - K_RECOVERY + 1):
        if episodes[i + K_RECOVERY - 1] > t_max:
            continue                      # a window reaching past the horizon cannot qualify
        if all(at_or_above[i:i + K_RECOVERY]):
            return episodes[i]
    return None


def deficit_auc(values, episodes, *, pre_level: float, t_max: int) -> float:
    r"""$\frac{1}{T_{\max}}\int_0^{T_{\max}} [V_{\text{pre}} - V(t)]_+\,dt$, trapezoidally.

    $$\boxed{\frac{1}{T_{\max}} \sum_i \frac{d_i + d_{i+1}}{2}\,(t_{i+1} - t_i)}, \qquad
    d_i = \bigl[V_{\text{pre}} - V_{t_i}\bigr]_+$$

    Both halves matter: the $1/T_{\max}$ is `05` §8.3's normalisation, so the number is a mean
    deficit over the horizon rather than an area that grows with it; and the rule is trapezoidal on
    the real grid (A84 §72), exact on constant and linear deficits.
    """
    t_max = _require_horizon(t_max)
    values, episodes = _require_curve(values, episodes, t_max)
    pre = _require_real(pre_level, "the pre-update level")
    deficits = [max(0.0, pre - v) for v in values]
    total = 0.0
    for i in range(len(values) - 1):
        total += 0.5 * (deficits[i] + deficits[i + 1]) * (episodes[i + 1] - episodes[i])
    return total / t_max


def _require_grid(values, episodes) -> tuple:
    values, episodes = tuple(values), tuple(episodes)
    if len(values) != len(episodes) or not values:
        raise ProtocolError("the curve and its episode indices must be non-empty and equal length")
    for i, (v, t) in enumerate(zip(values, episodes)):
        _require_real(v, f"the curve value at position {i}")
        if isinstance(t, bool) or not isinstance(t, int):
            raise ProtocolError(f"the episode index at position {i} is {t!r}, not an integer")
    for a, b in zip(episodes, episodes[1:]):
        if not a < b:
            raise ProtocolError(
                f"the episode indices must be strictly increasing, got {a} then {b}")
    return values, episodes


def _at(values, episodes, episode: int) -> float:
    if episode not in episodes:
        raise ProtocolError(
            f"episode {episode} is not a checkpoint; a Retention horizon must be one of the "
            f"pre-registered checkpoints {episodes[:4]}..., never interpolated silently")
    return float(values[episodes.index(episode)])


def retention_at_h(values, episodes, *, H: int) -> float:
        values, episodes = _require_grid(values, episodes)
        if isinstance(H, bool) or not isinstance(H, int):
            raise ProtocolError(f"the retention horizon H={H!r} is not an integer episode index")
        return _at(values, episodes, H)


def late_window_retention(values, episodes, *, H1: int, H2: int) -> float:
        values, episodes = _require_grid(values, episodes)
        for name, h in (("H1", H1), ("H2", H2)):
            if isinstance(h, bool) or not isinstance(h, int):
                raise ProtocolError(f"the window bound {name}={h!r} is not an integer episode index")
        if not H1 < H2:
            raise ProtocolError(f"the window [{H1}, {H2}] is empty or inverted")
        inside = [(t, v) for t, v in zip(episodes, values) if H1 <= t <= H2]
        if len(inside) < 2:
            raise ProtocolError(
                f"the window [{H1}, {H2}] contains {len(inside)} checkpoint(s); a maintained level "
                "over a window needs at least two")
        return sum(float(v) for _t, v in inside) / len(inside)


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


def metric_source_review():
    originals = {'utility': ROOT / 'src/rfl_rebuild/b2/utility.py',
                 'retention': ROOT / 'src/rfl_rebuild/b2/retention.py'}
    texts = {name: path.read_text(encoding='utf-8') for name, path in originals.items()}
    trees = {name: ast.parse(text) for name, text in texts.items()}
    new_text = Path(__file__).read_text(encoding='utf-8')
    new_tree = ast.parse(new_text)
    functions = {}
    for name in COPIED_FUNCTIONS:
        new_node = next(node for node in new_tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
        if name in ('retention_at_h', 'late_window_retention'):
            class_name = 'RetentionAtH' if name == 'retention_at_h' else 'LateWindowRetention'
            cls = next(node for node in trees['retention'].body if isinstance(node, ast.ClassDef) and node.name == class_name)
            original = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == 'value')
            expected = textwrap.dedent(ast.get_source_segment(texts['retention'], original)).replace('def value(', 'def ' + name + '(', 1)
            normalized = ast.parse(expected).body[0]
            assert ast.dump(normalized, include_attributes=False) == ast.dump(new_node, include_attributes=False)
            assert expected == ast.get_source_segment(new_text, new_node)
            origin, qualified = 'retention', class_name + '.value'
        else:
            origin = 'utility' if name in COPIED_FUNCTIONS[:5] else 'retention'
            original = next(node for node in trees[origin].body if isinstance(node, ast.FunctionDef) and node.name == name)
            assert ast.dump(original, include_attributes=False) == ast.dump(new_node, include_attributes=False)
            assert ast.get_source_segment(texts[origin], original) == ast.get_source_segment(new_text, new_node)
            qualified = name
        functions[name] = {'original_qualified_function': qualified, 'original_line': original.lineno,
                           'source_sha256': hashlib.sha256(ast.get_source_segment(texts[origin], original).encode('utf-8')).hexdigest()}
    return {'physical_sources': [meta(path) for path in originals.values()], 'actual_function_pins': functions,
            'mechanical_transport_only': ['two static value methods renamed; decorators omitted',
                                          'ProtocolError locally bound to ValueError; no original module execution'],
            'K': 3, 'fraction': 0.95, 'late_window_arithmetic': 'original builtin sum/checkpoint count, not += or fsum',
            'old_checker_fixture_or_RFL_metric_import_execution': False}


def measure_closed(view):
    """The only metric feature door: issued raw-derived external observations."""
    assert set(view) == {'fields', 'episodes', 'values', 'pre_level', 't_max'}
    assert set(view['fields']) == set(FIELDS)
    episodes, values = tuple(view['episodes']), tuple(scalar(value) for value in view['values'])
    pre, horizon = scalar(view['pre_level']), view['t_max']
    assert horizon == 465 and episodes == tuple(range(466)) and len(values) == 466
    assert all(len(view['fields'][name]) == 466 and all(len(bank) == 100 for bank in view['fields'][name]) for name in FIELDS)
    tau = recovery_time(values, episodes, pre_level=pre, t_max=horizon)
    auc = deficit_auc(values, episodes, pre_level=pre, t_max=horizon)
    retention = retention_at_h(values, episodes, H=465)
    late = late_window_retention(values, episodes, H1=387, H2=465)
    changes, previous = [], None
    for epoch, value in zip(episodes, values):
        if previous is None or value.hex() != previous.hex():
            changes.append({'epoch': epoch, 'mean_return': value, 'mean_hex': value.hex()})
        previous = value
    return {'quantity': 'original ordered bank mean return, not success rate', 'checkpoints': 466, 'bank_scenes': 100,
            'shared_healthy_pre_level': pre, 'shared_healthy_pre_level_hex': pre.hex(),
            'recovery_threshold': RECOVERY_FRACTION * pre, 'recovery_threshold_hex': (RECOVERY_FRACTION * pre).hex(),
            'K_consecutive_integer_episodes': 3, 'tau': tau, 'recovered': tau is not None,
            'restricted_time': horizon if tau is None else min(tau, horizon), 'not_cross_seed_RMST': True,
            'DeficitAUC': auc, 'DeficitAUC_hex': auc.hex(), 'RetentionAtH465': retention,
            'RetentionAtH465_hex': retention.hex(), 'LateWindowRetention387_465': late,
            'LateWindowRetention387_465_hex': late.hex(), 'late_window_checkpoints': 79,
            'W0_mean_return': values[0], 'W0_mean_hex': values[0].hex(),
            'W465_mean_return': values[-1], 'W465_mean_hex': values[-1].hex(),
            'minimum_mean_return': min(values), 'maximum_mean_return': max(values),
            'change_points': changes, 'curve_values_sha256': hashlib.sha256(canonical([value.hex() for value in values]).encode('ascii')).hexdigest(),
            'closed_external_view_sha256': hashlib.sha256(canonical(view).encode('ascii')).hexdigest()}


def paired_metrics(roles):
    reference, treatment = (roles[role] for role in ROLES)
    values = {'restricted_time_NoWrite_minus_treatment': reference['restricted_time'] - treatment['restricted_time'],
              'DeficitAUC_NoWrite_minus_treatment': reference['DeficitAUC'] - treatment['DeficitAUC'],
              'RetentionAtH_treatment_minus_NoWrite': treatment['RetentionAtH465'] - reference['RetentionAtH465'],
              'LateWindowRetention_treatment_minus_NoWrite': treatment['LateWindowRetention387_465'] - reference['LateWindowRetention387_465'],
              'W0_mean_treatment_minus_NoWrite': treatment['W0_mean_return'] - reference['W0_mean_return'],
              'W465_mean_treatment_minus_NoWrite': treatment['W465_mean_return'] - reference['W465_mean_return']}
    return dict(values, binary64_hex={name: value.hex() for name, value in values.items() if type(value) is float},
                direction='Positive favors treatment for each signed difference; no sign/CI/family verdict is applied.',
                tau_NoWrite=reference['tau'], tau_treatment=treatment['tau'], censored_NoWrite=not reference['recovered'],
                censored_treatment=not treatment['recovered'], not_ensemble_RMST=True)


def scan_child(mode, folder, receipt, audited):
    child = read_json(folder / 'child_summary.json')
    assert mode == receipt['mode'] == child['mode'] == audited['mode']
    for name in ('stdout', 'stderr'):
        assert bare(meta(folder / (name + '.log'))) == receipt[name]
    for name in ('raw.jsonl.gz', 'child_summary.json'):
        assert bare(meta(folder / name)) == receipt[name]
    assert bare(meta(folder / 'raw.jsonl.gz')) == audited['compressed_meta']
    digest, size, sequence = hashlib.sha256(), 0, 0
    tags, numeric_changes, policy_changes = Counter(), 0, 0
    metric_roles, curve_values, source_records = {}, {}, {}
    result = failure = restoration = None
    with gzip.open(folder / 'raw.jsonl.gz', 'rb') as stream:
        for line in stream:
            assert line.endswith(b'\n')
            digest.update(line); size += len(line)
            record = json.loads(line)
            assert record['seq'] == sequence and record['mode'] == mode
            assert line == (canonical(record) + '\n').encode('ascii')
            sequence += 1
            tag, payload = record['tag'], record['payload']
            tags[tag] += 1
            if tag in ('SOURCE_INSTALL_PLANNED', 'ORIGINAL_SOURCE', 'SOURCE_TRUTH_ACTUAL',
                       'ORIGINAL_PAIR', 'SOURCE_PAIR_ACTUAL', 'CURVE_PREPARED',
                       'WHOLE_PREPARED', 'WHOLE_MEASUREMENT_COMPLETED'):
                assert tag not in source_records
                pin = {'record_seq': record['seq'],
                       'payload_sha256': hashlib.sha256(canonical(payload).encode('ascii')).hexdigest()}
                if tag == 'WHOLE_PREPARED':
                    pin.update(origin_sha256=payload['origin_sha256'], status=payload['status'],
                               owners=payload['owners'], complete_pre_records=payload['complete_pre_records'],
                               fresh_kernel_pre_only=payload['fresh_kernel_pre_only'],
                               all_pre_traces_actual_native=payload['all_pre_traces_actual_native'],
                               full_region_map_retained_in_bound_capture=True)
                elif tag == 'WHOLE_MEASUREMENT_COMPLETED':
                    pin.update(measurement_payload_sha256=payload['payload_sha256'],
                               prepared_origin_sha256=payload['prepared_origin_sha256'],
                               ordered_post_records_count=payload['ordered_post_records_count'],
                               actual_same_pair_for_future=payload['actual_same_pair_for_future'],
                               all_post_traces_actual_native=payload['all_post_traces_actual_native'],
                               scores=payload['payload']['scores'], paired_difference=payload['payload']['paired_difference'],
                               full_typed_region_keys_and_measured_payload_retained_in_bound_capture=True)
                elif tag == 'CURVE_PREPARED':
                    origin, plan = payload['origin'], payload['origin']['engineering_plan']
                    pin['origin_sha256'] = payload['origin_sha256']
                    pin['original_pair_seal'] = origin['original_pair_seal']
                    pin['initial_composites'] = payload['initial_composites']
                    pin['engineering_plan'] = {'training_episodes': len(plan['episodes']),
                                               'grid_count': len(plan['grid']),
                                               'grid_endpoints': [plan['grid'][0], plan['grid'][-1]],
                                               'sample_count': len(plan['sample']),
                                               'v_pre_hex': plan['v_pre_hex'], 'parameters': plan['parameters'],
                                               'original_lock_sha256': plan['original_lock_sha256'],
                                               'keyed': plan['keyed'], 'formal_execution': plan['formal_execution'],
                                               'complete_plan_retained_in_bound_capture': True}
                else:
                    pin['payload'] = payload
                source_records[tag] = pin
            elif tag == 'CORE_EPISODE':
                before, after = payload['before'], payload['after']
                field = 'current' if mode == 'dq' else 'learning_values'
                numeric_changes += before[field] != after[field]
                policy_changes += before['current']['D'] != after['current']['D']
            elif tag == 'EXTERNAL_VIEW':
                role = record['role']
                assert role in ROLES and role not in metric_roles
                measured = measure_closed(payload)
                metric_roles[role] = dict(measured, mode=mode, role=role,
                                          record_seq=record['seq'])
                curve_values[role] = [marker['binary64_hex'] for marker in payload['values']]
            elif tag == 'RESULT':
                assert result is None
                result = payload
            elif tag == 'FAILURE':
                assert failure is None
                failure = payload
            elif tag == 'CAPTURE_RESTORATION':
                assert restoration is None
                restoration = payload
    assert sequence == child['records'] == audited['records']
    assert size == child['uncompressed_bytes'] == audited['uncompressed_bytes']
    assert digest.hexdigest() == child['canonical_sha256'] == audited['canonical_sha256']
    assert restoration == child['capture_restoration']
    for name in ('rollout', 'step', 'transaction', 'B1'):
        assert child['counts'].get(name, 0) == audited['actual_counts'].get(name, 0)
    complete = bool(receipt['child_exit_code'] == 0 and child['completed'] and audited['complete'])
    if complete:
        assert result is not None and result['completed'] is True and result['counts'] == child['counts']
        assert failure is None and all(restoration.values()) and set(metric_roles) == set(ROLES)
        assert tags['CORE_EPISODE'] == 930
        for role in ROLES:
            observed = next(curve for curve in audited['ordered_curves'] if curve['role'] == role)
            assert [entry['mean_hex'] for entry in observed['ordered_curve']] == curve_values[role]
            assert observed['pre_level_hex'] == metric_roles[role]['shared_healthy_pre_level_hex']
            assert observed['t_max'] == 465
    collateral = audited['same_pair_whole_collateral']
    collateral_complete = bool(collateral is not None and collateral['complete_measurement'] is True)
    if collateral_complete:
        assert collateral['full_pre_ordinary_rollouts'] == 5760
        assert len(collateral['owners']) == 1 and 0 < collateral['region_size'] < 5760
        assert len(collateral['arm_B_hex']) == len(collateral['arm_post_mean_hex']) == len(collateral['full_immediate_sha256']) == 2
        assert 'WHOLE_MEASUREMENT_COMPLETED' in source_records and 'WHOLE_PREPARED' in source_records
        assert source_records['WHOLE_MEASUREMENT_COMPLETED']['measurement_payload_sha256'] == collateral['measurement_payload_sha256']
        assert source_records['WHOLE_PREPARED']['origin_sha256'] == collateral['preparation_origin_sha256']
        scores = source_records['WHOLE_MEASUREMENT_COMPLETED']['scores']
        assert [score['value']['binary64_hex'] for score in scores] == collateral['arm_B_hex']
        assert [score['post_mean']['binary64_hex'] for score in scores] == collateral['arm_post_mean_hex']
        assert all(score['pre_mean']['binary64_hex'] == collateral['pre_mean_hex'] for score in scores)
        assert source_records['WHOLE_MEASUREMENT_COMPLETED']['paired_difference']['binary64_hex'] == collateral['pair_difference_hex']
        if 'CURVE_PREPARED' in source_records:
            assert collateral['curve_initial_I_exact_same_pair'] is True
            assert source_records['CURVE_PREPARED']['original_pair_seal'] == collateral['original_pair_declaration_sha256']
    return {'mode': mode, 'complete': complete, 'native_child_exit_code': receipt['child_exit_code'],
            'actual_counts': audited['actual_counts'], 'native_call_return_counts': child['counts'],
            'canonical_records': sequence, 'canonical_uncompressed_bytes': size,
            'canonical_sha256': digest.hexdigest(), 'capture': meta(folder / 'raw.jsonl.gz'),
            'tag_inventory': dict(tags), 'source_and_pair_records': source_records,
            'per_role_closed_external_metrics': metric_roles,
            'signed_future_metric_differences': paired_metrics(metric_roles) if complete else None,
            'same_genuine_pair_immediate_wholeCollateral': collateral,
            'same_genuine_pair_wholeCollateral_complete': collateral_complete,
            'same_genuine_pair_I_curve_initial_link_complete': bool(collateral_complete and
                'CURVE_PREPARED' in source_records and collateral['curve_initial_I_exact_same_pair'] is True),
            'numeric_content_change_episodes': numeric_changes,
            'literal_policy_content_change_episodes': policy_changes,
            'actual_TD_and_policy_audit_diagnostics': audited['TD_and_policy_diagnostics'],
            'actual_transaction_kind_counts': audited['transaction_kind_counts'],
            'actual_failure': failure, 'capture_restoration': restoration,
            'resources': {'wall_seconds': child['wall_seconds'], 'cpu_seconds': child['cpu_seconds'],
                          'peaks': child['peaks'], 'encode_seconds': child['encode_seconds'],
                          'write_seconds': child['write_seconds'], 'not_production_worstcase_certificate': True},
            'actual_result_record_sha256': None if result is None else hashlib.sha256(canonical(result).encode('ascii')).hexdigest(),
            'full_curves_raw_TD_and_resources_retained_in_bound_capture_and_audit': True}


def render(report):
    lines = ['# V0.3：恢复量可观测性 canary 实验', '',
             '这是针对此前初始回报已高于健康参考、恢复量无法区分的问题，事前固定的工程 canary。',
             '设计受到既有结果启发，不是盲采样的原科学总体；0.6122/0.6506 仅为静态预期，不拿它替代实测。', '',
             '| 路径/角色 | W0 平均回报 | W465 平均回报 | τ / restricted time | DeficitAUC | Retention@465 | 晚窗 387..465 |',
             '|---|---:|---:|---|---:|---:|---:|']
    for child in report['children']:
        for role in ROLES:
            measured = child['per_role_closed_external_metrics'].get(role)
            if measured is None:
                lines.append(f"| {child['mode']}/{role} | 缺失 | 缺失 | partial，不补值 | 缺失 | 缺失 | 缺失 |")
            else:
                tau = '未恢复' if measured['tau'] is None else str(measured['tau'])
                lines.append(f"| {child['mode']}/{role} | {measured['W0_mean_return']:.17g} | {measured['W465_mean_return']:.17g} | "
                             f"{tau} / {measured['restricted_time']} | {measured['DeficitAUC']:.17g} | "
                             f"{measured['RetentionAtH465']:.17g} | {measured['LateWindowRetention387_465']:.17g} |")
    lines += ['', 'τ 保持原 0.95×共同健康参考阈值及连续 3 个整数回合；restricted time 是本输入流的量，不叫总体 RMST。',
              'DeficitAUC 使用原有序真实回合轴梯形和除以 465，Retention 使用原终点及晚窗 checkpoint mean。', '']
    lines += ['差值方向：NoWrite−treatment 的恢复时间或 DeficitAUC 为正，表示治疗的受限恢复时间更短或缺口更小；',
              'treatment−NoWrite 的 Retention 为正，表示治疗的终点或晚窗回报更高。零和负值同样保留，不套胜负门槛。', '']
    for child in report['children']:
        differences = child['signed_future_metric_differences']
        if differences is not None:
            lines.append(f"- {child['mode']}：NoWrite−treatment restricted time={differences['restricted_time_NoWrite_minus_treatment']}，"
                         f"DeficitAUC={differences['DeficitAUC_NoWrite_minus_treatment']:.17g}；"
                         f"treatment−NoWrite Retention@465={differences['RetentionAtH_treatment_minus_NoWrite']:.17g}，"
                         f"晚窗={differences['LateWindowRetention_treatment_minus_NoWrite']:.17g}。")
        collateral = child['same_genuine_pair_immediate_wholeCollateral']
        if child['same_genuine_pair_wholeCollateral_complete']:
            linkage = ('source/完整 owner/完整 I_post 与未来初始状态链相同' if
                       child['same_genuine_pair_I_curve_initial_link_complete'] else
                       '即时测量完整，但未来初始入口的同 pair 链接尚未完成，不作完整 future 联结声明')
            lines.append(f"- 同一真实 pair 的即时 wholeCollateral：C={collateral['region_size']} 场景，"
                         f"B_NoWrite={float.fromhex(collateral['arm_B_hex'][0]):.17g}，"
                         f"B_treatment={float.fromhex(collateral['arm_B_hex'][1]):.17g}，"
                         f"NoWrite−treatment={float.fromhex(collateral['pair_difference_hex']):.17g}。"
                         f'{linkage}，不借旧 P 零值；这个局部值不是一般零伤害。')
        else:
            lines.append('- 同一 pair 的 wholeCollateral 尚未签发完整测量：partial/null 原样保留，不补零、不借旧结果。')
        lines.append(f"- 实际 numeric 内容变化 {child['numeric_content_change_episodes']} 个 episode，"
                     f"literal-D 内容变化 {child['literal_policy_content_change_episodes']} 个；"
                     f"counts={child['actual_counts']}，wall={child['resources']['wall_seconds']:.3f}s。")
    lines += ['', 'NoWrite 也完整普通学习，未冻结对照。只修本事件的一个 owner，另外三个持久 canary context 保留。',
              'patch 的 visited-existing-D 策略改进可能由已有 Q* 先验触发，即便 numeric TD 为零；',
              '因此数值内容变化与 literal-D 策略变化分列，不把策略改进叫新数值知识或新增 B1 责任，也不据此给 DQ/patch 排名。',
              '所有零、负、未恢复和 partial 结果按实际保留；正收益不是完成条件。',
              '这是固定机制/工程输入流的条件性结果，不证明架构优胜、一般零伤害、处罚结论、统计等效或全 RFL。',
              '原完整 k/shape 与独立 400/200 seed 确认仍未完成；没有 keys、正式 collector、RNG/DP/native calibration 或 F1 PASS 迁移。',
              'v111 的真实 T/NOOP 结果保留，没有重跑、删除或当作错误试验。本次开始前，主代理实际核实 rfl-a96 每 15 分钟续接为 ACTIVE；这记录观察，不预测后续配置。实验失败不自动重试。', '',
              '完整机器数值、源码/物理证据 pins、同 pair 的尺子值与限制见 `result_summary.json`；大体积原曲线/TD不在摘要重复拷贝。', '']
    return '\n'.join(lines)


def main():
    assert not (HERE / 'result_summary.json').exists() and not (HERE / 'result.md').exists(), 'exclusive report outputs'
    contract = read_json(HERE / 'contract.json')
    native = read_json(HERE / 'evidence/exit.json')
    claim = read_json(HERE / 'evidence/claim.json')
    assert native['input_bytes_unchanged'] and not native['automatic_retry']
    assert claim['input_binding_before'] == native['input_binding_after']
    assert claim['parent_commit'] == contract['parent_commit'] and claim['serial_children'] is True
    for path, pin in claim['input_binding_before'].items():
        assert bare(meta(ROOT / path)) == pin
    audit_exit = read_json(HERE / 'evidence_stored_audit/exit.json')
    audit = read_json(HERE / 'stored_audit_result.json')
    assert audit_exit['native_exit_code'] == 0 and audit_exit['input_bytes_unchanged']
    assert bare(meta(HERE / 'stored_audit_result.json')) == audit_exit['stored_audit_result']
    assert audit['schema'] == AUDIT_SCHEMA and audit['scientific_qualification'] is False
    assert audit['native_child_receipts_preserved'] == native['child_receipts']
    metric_pins = metric_source_review()
    children = []
    for receipt in native['child_receipts']:
        mode = receipt['mode']
        folder = HERE / 'evidence' / mode
        assert read_json(folder / 'exit.json') == receipt
        audited = next(child for child in audit['children'] if child['mode'] == mode)
        children.append(scan_child(mode, folder, receipt, audited))
    assert [child['mode'] for child in children] == list(MODES[:len(children)])
    complete = bool(len(children) == 2 and native['completed'] and all(child['complete'] for child in children))
    selected = [HERE / 'contract.json', HERE / 'workload.py', HERE / 'execute.py', HERE / 'audit_stored.py',
                HERE / 'execute_audit.py', HERE / 'stored_audit_result.json', HERE / 'evidence/claim.json',
                HERE / 'evidence/exit.json', HERE / 'evidence_stored_audit/exit.json', Path(__file__),
                ROOT / contract['healthy_reference']['path'], ROOT / contract['dev_lock']['path'],
                ROOT / 'src/rfl_rebuild/b2/utility.py', ROOT / 'src/rfl_rebuild/b2/retention.py']
    for child in children:
        selected += [HERE / 'evidence' / child['mode'] / name for name in
                     ('claim.json', 'exit.json', 'child_summary.json', 'raw.jsonl.gz', 'stdout.log', 'stderr.log')]
    pins = {path.relative_to(ROOT).as_posix(): bare(meta(path)) for path in selected}
    report = {'schema': 'V112_ACTUAL_RECOVERY_OBSERVABILITY_ENGINEERING_CANARY_RESULT',
              'generated_at_utc': datetime.now(timezone.utc).isoformat(), 'parent_commit': contract['parent_commit'],
              'status': 'COMPLETE_FIXED_CANARY_NOT_CONFIRMATORY_PASS' if complete else 'ACTUAL_PARTIAL_CANARY_PRESERVED_NO_RETRY',
              'complete_fixed_canary': complete, 'original_confirmatory_study_complete': False,
              'positive_gain_required': False, 'result_informed_engineering_canary': True,
              'static_predicted_W0_is_not_observed_effect': {'reference': 0.6122, 'treatment': 0.6506},
              'source_definition': 'four persistent contexts (1,2,t1,kappa0/1,phase2,z1/3,m0); independent DQ-promoted RIGHT and literal patch; current P scene[0,2,0,43,1], one whole owner, other three retained; no P/X/mask/option fault',
              'children': children, 'metric_source_review': metric_pins,
              'metric_inputs': 'Only actual completed issued raw-derived EXTERNAL_VIEW payload; truth, source, role, state, ledger and cost are exterior provenance',
              'wholeCollateral': 'Current same-genuine-pair fullU2/pre region/immediate I_post measurement only; not previous P evidence transfer or final delta/family qualification',
              'aggregate_actual_counts': dict(sum((Counter(child['actual_counts']) for child in children), Counter())),
              'all_zero_negative_censored_partial_and_NoWrite_learning_retained': True,
              'not_original_scientific_population_or_keyblind_seed': True,
              'no_universal_architecture_ranking_harm_equivalence_or_punishment_claim': True,
              'no_old_F1_qualification_transfer': True, 'original_kshape_fair_family_400_200_complete': False,
              'new_science_or_workload_keys': 0, 'RNG_keyderive_DP_nativecalibration': 0,
              'formal_keyed_Protocol_Curve_train_curve_collector_collection': False,
              'scientific_qualification': False, 'collection_authorized': False,
              'old_fixture_checker_native_reexecution': 0, 'automatic_retry': False,
              'v111_original_T_NOOP_preserved_not_reexecuted': True,
              'automation': {'id': 'rfl-a96', 'observed_status': 'ACTIVE', 'observed_interval_minutes': 15,
                             'same_chat_observed': True, 'actual_configuration_verified_by_main_agent': True,
                             'observation_scope': 'Main agent actual configuration observation before this run; not a persistent future-state claim',
                             'failed_native_experiment_automatic_retry': False},
              'stored_review': {'source': meta(HERE / 'audit_stored.py'), 'launcher': meta(HERE / 'execute_audit.py'),
                                'result': meta(HERE / 'stored_audit_result.json'),
                                'receipt': meta(HERE / 'evidence_stored_audit/exit.json'),
                                'runtime_identity_reconstructed': False, 'not_expert_or_sciencegate': True},
              'source_binding_before': pins}
    assert pins == {path.relative_to(ROOT).as_posix(): bare(meta(path)) for path in selected}
    report['source_binding_after'], report['input_bytes_unchanged'] = pins.copy(), True
    with (HERE / 'result_summary.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, sort_keys=True, ensure_ascii=False, indent=2); stream.write('\n')
    with (HERE / 'result.md').open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(render(report))
    print(canonical({'schema': report['schema'], 'status': report['status'], 'complete_fixed_canary': complete,
                     'actual_counts': report['aggregate_actual_counts'], 'result_summary': meta(HERE / 'result_summary.json'),
                     'result_md': meta(HERE / 'result.md')}))


if __name__ == '__main__':
    main()
