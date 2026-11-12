"""Build a compact bounded V0.3 stage finding after actual v108 closure.

This stdlib program reads closed EXTERNAL_VIEW payloads only for curve metrics.
Original source/cost/role/B1 truth records bind provenance outside that feature
door; they are not metric inputs. Pure original utility/retention formulas are
mechanically copied and AST-reviewed below. This is reporting, not a native
experiment, seed-level inference, scientific adoption, or an old audit rerun.
"""
import ast
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
import textwrap

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
PREP = HERE.parent
K_RECOVERY = 3
RECOVERY_FRACTION = 0.95
ProtocolError = ValueError
EXTERNAL_FIELDS = ('future_rewards','future_outcomes','future_trajectories',
                   'future_actions','future_observations')
COPIED_FUNCTIONS = ["_require_real","_require_horizon","_require_curve","recovery_time","deficit_auc","_require_grid","_at","retention_at_h","late_window_retention"]

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


def canonical(payload):
    return json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=True)


def meta(path):
    h,size=hashlib.sha256(),0
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            h.update(block); size+=len(block)
    return {'path':path.relative_to(ROOT).as_posix(),'bytes':size,'sha256':h.hexdigest()}


def read_json(path):
    return json.loads(path.read_bytes())


def bare_meta(pin):
    return {k:pin[k] for k in ('bytes','sha256')}


def metric_source_review():
    original_files={name:ROOT/'src/rfl_rebuild/b2'/filename for name,filename in
                    [('utility','utility.py'),('retention','retention.py')]}
    text={name:path.read_text(encoding='utf-8') for name,path in original_files.items()}
    trees={name:ast.parse(source) for name,source in text.items()}
    newtext=Path(__file__).read_text(encoding='utf-8'); newtree=ast.parse(newtext)
    pins={}
    for name in COPIED_FUNCTIONS:
        new=next(n for n in newtree.body if isinstance(n,ast.FunctionDef) and n.name==name)
        if name in ('retention_at_h','late_window_retention'):
            cls='RetentionAtH' if name=='retention_at_h' else 'LateWindowRetention'
            klass=next(n for n in trees['retention'].body if isinstance(n,ast.ClassDef) and n.name==cls)
            old=next(n for n in klass.body if isinstance(n,ast.FunctionDef) and n.name=='value')
            expected=textwrap.dedent(ast.get_source_segment(text['retention'],old)).replace(
                'def value(', 'def '+name+'(',1)
            normalized=ast.parse(expected).body[0]
            assert ast.dump(normalized,include_attributes=False)==ast.dump(new,include_attributes=False)
            assert expected==ast.get_source_segment(newtext,new)
            origin='retention'; qualified=cls+'.value'
        else:
            origin='utility' if name in ('_require_real','_require_horizon','_require_curve','recovery_time','deficit_auc') else 'retention'
            old=next(n for n in trees[origin].body if isinstance(n,ast.FunctionDef) and n.name==name)
            assert ast.dump(old,include_attributes=False)==ast.dump(new,include_attributes=False)
            assert ast.get_source_segment(text[origin],old)==ast.get_source_segment(newtext,new)
            qualified=name
        pins[name]={'original_qualified_function':qualified,'original_line':old.lineno,
                    'original_source_sha256':hashlib.sha256(ast.get_source_segment(text[origin],old).encode('utf-8')).hexdigest()}
    return {'physical_sources':[meta(path) for path in original_files.values()],
            'mechanically_bound_pure_formulas':pins,
            'allowed_local_transport_changes':['Two static value methods renamed and dedented; staticmethod decorator omitted',
                                               'ProtocolError bound to local ValueError for a stdlib-only reporting program'],
            'RFL_or_original_metric_module_import_execution':False,
            'FutureUtility_K':3,'recovery_fraction':0.95,
            'LateWindowRetention_arithmetic':'Original sum(float(v) for checkpoints) / count; not incremental fold or fsum'}


def scalar(marker):
    assert type(marker) is dict and set(marker)=={'binary64_hex'}
    result=float.fromhex(marker['binary64_hex'])
    assert math.isfinite(result)
    return result


def measure_external(view):
    """The metric feature door: no source/role/state/truth/cost/audit argument."""
    assert set(view)=={'fields','episodes','values','pre_level','t_max'}
    assert set(view['fields'])==set(EXTERNAL_FIELDS)
    episodes=tuple(view['episodes']); values=tuple(scalar(v) for v in view['values'])
    pre=scalar(view['pre_level']); horizon=view['t_max']
    assert horizon==465 and episodes==tuple(range(466)) and len(values)==466
    assert all(len(view['fields'][name])==466 and all(len(bank)==100 for bank in view['fields'][name])
               for name in EXTERNAL_FIELDS)
    tau=recovery_time(values,episodes,pre_level=pre,t_max=horizon)
    auc=deficit_auc(values,episodes,pre_level=pre,t_max=horizon)
    retention=retention_at_h(values,episodes,H=465)
    late=late_window_retention(values,episodes,H1=387,H2=465)
    descriptive_area=0.0
    for i in range(len(values)-1):
        descriptive_area+=0.5*(values[i]+values[i+1])*(episodes[i+1]-episodes[i])
    changes=[]
    previous=None
    for e,value in zip(episodes,values):
        if previous is None or previous.hex()!=value.hex():
            changes.append({'epoch':e,'mean_return':value,'mean_hex':value.hex()})
        previous=value
    return {'quantity':'ordered bank mean return, not success rate',
            'checkpoints':466,'bank_scenes':100,'pre_level':pre,'pre_level_hex':pre.hex(),
            'W0_mean_return':values[0],'W0_mean_hex':values[0].hex(),
            'W465_mean_return':values[-1],'W465_mean_hex':values[-1].hex(),
            'minimum_mean_return':min(values),'maximum_mean_return':max(values),
            'all_values_at_or_above_healthy_pre':all(value>=pre for value in values),
            'FutureUtility':{'tau':tau,'recovered':tau is not None,
                'restricted_time':horizon if tau is None else tau,'DeficitAUC':auc,'DeficitAUC_hex':auc.hex(),
                'interpretation':'Per-stream recovery/deficit quantities; not cross-seed RMST or a formal inference'},
            'RetentionAtH465':retention,'RetentionAtH465_hex':retention.hex(),
            'LateWindowRetention387_465':late,'LateWindowRetention387_465_hex':late.hex(),
            'descriptive_normalized_learning_return_trapezoid':descriptive_area/horizon,
            'descriptive_auc_is_not_a_primary_metric_or_new_PASS_rule':True,
            'change_points':changes,
            'curve_values_hex':[value.hex() for value in values],
            'closed_view_sha256':hashlib.sha256(canonical(view).encode('ascii')).hexdigest()}


def extract_external(mode,folder,child_audit,native_receipt):
    raw=folder/'raw.jsonl.gz'; summary=read_json(folder/'child_summary.json')
    assert bare_meta(meta(raw))==native_receipt['raw.jsonl.gz']==child_audit['compressed_meta']
    assert bare_meta(meta(folder/'child_summary.json'))==native_receipt['child_summary.json']
    assert native_receipt['child_exit_code']==0 and child_audit['complete'] and summary['completed']
    views={}; checksum=hashlib.sha256(); size=0; count=0
    with gzip.open(raw,'rb') as stream:
        for line in stream:
            assert line.endswith(b'\n')
            checksum.update(line); size+=len(line)
            record=json.loads(line); assert record['seq']==count; count+=1
            if record['tag']=='EXTERNAL_VIEW':
                role=record['role']; assert role in ('reference','treatment') and role not in views
                # Metrics are computed from the closed external payload before role/provenance labels are attached.
                measured=measure_external(record['payload'])
                views[role]=measured
    assert count==summary['records']==child_audit['records']
    assert size==summary['uncompressed_bytes']==child_audit['uncompressed_bytes']
    assert checksum.hexdigest()==summary['canonical_sha256']==child_audit['canonical_sha256']
    assert set(views)=={'reference','treatment'}
    audited={role['role']:role for role in child_audit['ordered_curves']}
    for role in ('reference','treatment'):
        expected=[entry['mean_hex'] for entry in audited[role]['ordered_curve']]
        assert views[role]['curve_values_hex']==expected
        assert audited[role]['pre_level_hex']==views[role]['pre_level_hex'] and audited[role]['t_max']==465
        views[role]['mode']=mode; views[role]['role']=role
    return views


def pair_description(views):
    """Descriptive comparison of the two already-closed external metric results."""
    reference,treatment=(views[role] for role in ('reference','treatment'))
    refvals=[float.fromhex(v) for v in reference['curve_values_hex']]
    treatvals=[float.fromhex(v) for v in treatment['curve_values_hex']]
    sustained=None
    for e in range(466):
        if all(refvals[i].hex()==treatvals[i].hex() for i in range(e,466)):
            sustained=e; break
    result={'immediate_bank_mean_treatment_minus_NoWrite':treatvals[0]-refvals[0],
            'final_bank_mean_treatment_minus_NoWrite':treatvals[-1]-refvals[-1],
            'final_bank_mean_exact_equal':treatvals[-1].hex()==refvals[-1].hex(),
            'sustained_pair_mean_equality_from_epoch':sustained,
            'sustained_equality_is_not_original_recovery_time':True,
            'restricted_time_NoWrite_minus_treatment':reference['FutureUtility']['restricted_time']-treatment['FutureUtility']['restricted_time'],
            'DeficitAUC_NoWrite_minus_treatment':reference['FutureUtility']['DeficitAUC']-treatment['FutureUtility']['DeficitAUC'],
            'RetentionAtH_treatment_minus_NoWrite':treatment['RetentionAtH465']-reference['RetentionAtH465'],
            'LateWindowRetention_treatment_minus_NoWrite':treatment['LateWindowRetention387_465']-reference['LateWindowRetention387_465'],
            'descriptive_learning_return_area_treatment_minus_NoWrite':treatment['descriptive_normalized_learning_return_trapezoid']-reference['descriptive_normalized_learning_return_trapezoid'],
            'no_seed_statistical_inference_or_architecture_ranking':True}
    return result


def compact_resource(child_audit,native_receipt):
    return {'native_exit_code':native_receipt['child_exit_code'],
            'complete':child_audit['complete'],'actual_counts':child_audit['actual_counts'],
            'complete_banks':child_audit['complete_banks'],
            'chronological_training_receipts':child_audit['tag_inventory']['CORE_EPISODE'],
            'canonical_records':child_audit['records'],'raw_bytes':child_audit['uncompressed_bytes'],
            'gzip':child_audit['compressed_meta'],
            'instrumented_wall_seconds':child_audit['instrumented_wall_seconds'],
            'cpu_seconds':child_audit['cpu_seconds'],'Win32_peaks':child_audit['peaks'],
            'capture_encode_seconds':child_audit['capture_encode_seconds'],
            'capture_write_seconds':child_audit['capture_write_seconds'],
            'timing_includes_prepare_checks_profile_capture_export':True,
            'production_time_or_general_worstcase_certificate':False}


def phase_finding(curves,pairs):
    parts=[]
    if all(pair['immediate_bank_mean_treatment_minus_NoWrite']>0 for pair in pairs.values()):
        parts.append('Initial ordered mean return improved in both declared streams')
    else:
        parts.append('Initial ordered mean return differences are reported separately for each declared stream')
    if all(pair['final_bank_mean_exact_equal'] and pair['sustained_pair_mean_equality_from_epoch'] is not None
           for pair in pairs.values()):
        parts.append('NoWrite ordinary learning catches up; terminal advantage absent in these streams')
    else:
        parts.append('Terminal differences remain descriptive per-stream findings, not population or architecture ranking')
    if all(view['all_values_at_or_above_healthy_pre'] and view['FutureUtility']['tau']==0 and
           view['FutureUtility']['DeficitAUC']==0 for modes in curves.values() for view in modes.values()):
        parts.append('Original recovery utility differences are zero because all complete curves start and remain above the healthy reference')
    else:
        parts.append('Original recovery utility values are reported without a positive-result completion gate')
    return '; '.join(parts)+'.'


def preserved_offtarget():
    results=[]
    for folder,label,units in (('dq_recorded_completion_v101','dq','shared_C_units'),
                               ('patch_whole_completion_v100','patch-adaptive','shared_pre_region_units')):
        path=PREP/folder/'result_summary.json'; report=read_json(path)
        measurement=report['complete_candidate_measurement']
        assert measurement['B_reference_hex']==measurement['B_treatment_hex']==measurement['paired_NoWrite_minus_treatment_hex']=='0x0.0p+0'
        results.append({'mode':label,'source':meta(path),'shared_no_consult_region_scenes':measurement[units],
                        'B_NoWrite_hex':measurement['B_reference_hex'],'B_treatment_hex':measurement['B_treatment_hex'],
                        'paired_NoWrite_minus_treatment_hex':measurement['paired_NoWrite_minus_treatment_hex'],
                        'claim':'Previously measured immediate deterministic no-consult off-target zero only',
                        'different_necessary_engineering_owned_pair_not_current_future_pair':True,
                        'not_general_harm_equivalence_population_effect_or_final_wholeCollateral_qualification':True})
    return results


def render_markdown(report):
    streams=report['closed_external_curve_metrics']; pairs=report['per_stream_descriptive_pairs']
    resources=report['completed_workloads']
    lead=('责任反馈后的 whole 更新改善了初期回报；NoWrite 后续普通学习追平，终点没有显示更高的回报。'
          if all(p['immediate_bank_mean_treatment_minus_NoWrite']>0 and p['final_bank_mean_exact_equal']
                 for p in pairs.values()) else
          '初期和终点差异按各输入流分别列出，不按结果改规则或追求获胜。')
    lines=['# V0.3 当前有界机制阶段结果','',
           '本次固定 P 故障与已声明工程输入流的结果已经完整：'+lead+'这个阶段允许正、零、负或条件性发现，完成不以“必须总体正收益”为前提。','',
           '以下数值均为每个 checkpoint 按原顺序评估 100 场景的**平均回报**，不是成功率。DQ 的旧完整结果只读复用；patch 使用新只读银行入口，从新的真实 source 开始完成，未恢复或覆盖旧 partial。','',
           '| 输入流 / 架构 | NoWrite W0 | 更新后 W0 | NoWrite W465 | 更新后 W465 | 此后两条均值曲线相同的起点 |',
           '| --- | ---: | ---: | ---: | ---: | ---: |']
    for mode,label in (('dq','DQ'),('patch-adaptive','literal patch + L')):
        ref,treat=(streams[mode][r] for r in ('reference','treatment'))
        lines.append(f"| {label} | {ref['W0_mean_return']:.10g} | {treat['W0_mean_return']:.10g} | {ref['W465_mean_return']:.10g} | {treat['W465_mean_return']:.10g} | {pairs[mode]['sustained_pair_mean_equality_from_epoch']} |")
    zero_utility=all(v['all_values_at_or_above_healthy_pre'] and v['FutureUtility']['tau']==0 and
                     v['FutureUtility']['DeficitAUC']==0 for modes in streams.values() for v in modes.values())
    equal_retention=all(p['RetentionAtH_treatment_minus_NoWrite']==0 and p['LateWindowRetention_treatment_minus_NoWrite']==0
                        for p in pairs.values())
    utility_text=(f"共同健康参考为 {report['healthy_reference_level']:.17g}。本次四条完整曲线在 W0 已高于该参考，因而按原 K=3、0.95×健康参考阈值，tau 均为 0，DeficitAUC 均为 0；这不是恢复速度收益。"
                  if zero_utility else f"共同健康参考为 {report['healthy_reference_level']:.17g}。原 K=3、0.95×参考阈值的恢复量与 DeficitAUC 在机器报告中逐流列出，不用新的阈值代替它们。")
    retention_text=('终点 Retention@465 相同，晚窗 387..465 的均值相同。'
                    if equal_retention else '终点 Retention@465 与晚窗 387..465 的各流差值保留在机器报告中。')
    lines+=['','两条架构路径的普通更新方式不同，这张表不作架构胜负排名。NoWrite 的改善不能归功于 B1；patch 的先验 D 策略改进也不等同于获得了新的数值知识。','',
            '## 原定义下的 Utility 与 Retention','',utility_text+retention_text+'原始曲线变化和原恢复指标必须分别报告。','',
            '旧 DQ / patch 即时 wholeCollateral 候选均在“pre 成功且不咨询完整 owner S”的 5,520 场景区域实测为 0。这只是局部确定性 off-target 诊断，来自此前不同真实工程 pair，不是本次完整未来曲线同 pair 的全终点合取，更不等于一般零伤害。','',
            '## 完整执行与性能','']
    for mode,label in (('dq','DQ 旧完整捕获'),('patch-adaptive','patch 新完整捕获')):
        r=resources[mode]
        lines.append(f"- {label}：{r['actual_counts']['rollout']:,} rollout，{r['chronological_training_receipts']:,} 训练 episode，{r['complete_banks']:,} checkpoint bank；含完整记录与检查的 wall={r['instrumented_wall_seconds']:.3f}s、CPU={r['cpu_seconds']:.3f}s，峰值工作集={r['Win32_peaks']['peak_working_set_bytes']/1048576:.2f} MiB。")
    perf=report['readpath_finite_performance']
    lines+=['',f"v107 八组差分核对全部 raw / 均值精确相同。原 evaluator 的计时合计 {perf['old_timed_section_wall_seconds']:.6f}s，新 run_bank 合计 {perf['new_timed_run_section_wall_seconds']:.6f}s，计时段比值 {perf['timed_section_wall_ratio']:.3f}×。新段不含事先 prepare_bank/token/snapshot，因此不能称完整流水线或生产速度提高这个倍数；本次 patch 全 wall 已包含该准备工作。",'',
            '旧 v106 patch 因 2,400 秒上限停止：reference 完成 465 个训练回合，treatment 完成 415 个，未签完整 pair 曲线。其真实失败、partial 及审阅错误原样保留；本次是新版本入口、新 source 的首次运行，不把旧失败改成通过。','',
            '## 完成边界','',
            '当前必要技术链已从真实责任 source、whole B1、完整 future R+L 学习，走到每整数 checkpoint 与封闭外部后果读口，可以回答本次固定机制案例的阶段问题。没有正收益或最终两组追平，不会成为拖延该阶段报告的理由。','',
            '这不冒充原完整 k/shape 公平 family、全部条件、正式随机 Xi / 独立 seed、400/200 确认性统计或最终科学合取已经结束。没有新增 science/workload key、RNG/DP/校准、正式 collector 或采集；自动续接仍关闭。','',
            '机器可核查的完整数值、物理证据 SHA 与边界见同目录 result_summary.json。','']
    return '\n'.join(lines)


def main():
    assert not (HERE/'result_summary.json').exists() and not (HERE/'stage_result.md').exists(), 'report outputs are exclusive'
    contract=read_json(HERE/'contract.json')
    new_native=read_json(HERE/'evidence/exit.json')
    new_audit_exit=read_json(HERE/'evidence_stored_audit/exit.json')
    new_audit=read_json(HERE/'stored_audit_result.json')
    assert new_native['completed'] and new_native['input_bytes_unchanged'] and not new_native['automatic_retry']
    assert new_audit_exit['native_exit_code']==0 and new_audit_exit['input_bytes_unchanged']
    assert bare_meta(meta(HERE/'stored_audit_result.json'))==new_audit_exit['stored_audit_result']
    assert new_audit['schema']=='V108_INDEPENDENT_STDLIB_PATCH_READONLY_FULL_WORKLOAD_STORED_AUDIT'
    assert new_audit['complete_patch_architecture'] and not new_audit['scientific_qualification']
    assert len(new_audit['children'])==1 and new_audit['children'][0]['mode']=='patch-adaptive'
    patch_audit=new_audit['children'][0]
    patch_receipt=read_json(HERE/'evidence/patch-adaptive/exit.json')
    assert patch_receipt==new_native['child_receipts'][0]
    assert new_audit['native_child_receipts_preserved']==new_native['child_receipts']
    dqfolder=PREP/'dense_resource_workload_v106'
    old_audit=read_json(dqfolder/'stored_audit_kernel_return_revised_result.json')
    old_audit_exit=read_json(dqfolder/'evidence_stored_audit_kernel_return_revised/exit.json')
    old_native=read_json(dqfolder/'evidence/exit.json')
    assert old_audit_exit['native_exit_code']==0 and old_audit_exit['input_bytes_unchanged']
    assert bare_meta(meta(dqfolder/'stored_audit_kernel_return_revised_result.json'))==old_audit_exit['stored_audit_result']
    assert not old_native['completed'] and old_native['input_bytes_unchanged']
    dq_audit=next(child for child in old_audit['children'] if child['mode']=='dq')
    dq_receipt=read_json(dqfolder/'evidence/dq/exit.json')
    old_partial=next(child for child in old_audit['children'] if child['mode']=='patch-adaptive')
    assert not old_partial['complete'] and old_partial['native_failure_preserved']['message']=='wall-time cap'
    bankfolder=PREP/'readonly_bank_optimization_v107'
    bank_audit=read_json(bankfolder/'stored_audit_result.json')
    bank_exit=read_json(bankfolder/'evidence_stored_audit/exit.json')
    assert bank_exit['native_exit_code']==0 and bank_exit['input_bytes_unchanged']
    assert bare_meta(meta(bankfolder/'stored_audit_result.json'))==bank_exit['stored_audit_result']
    assert bank_audit['actual_counts']['transaction']==9 and len(bank_audit['eight_comparisons'])==8
    selected=[HERE/'contract.json',HERE/'stored_audit_result.json',HERE/'evidence/exit.json',
              HERE/'evidence/patch-adaptive/exit.json',HERE/'evidence/patch-adaptive/child_summary.json',
              HERE/'evidence/patch-adaptive/raw.jsonl.gz',HERE/'evidence_stored_audit/exit.json',
              dqfolder/'stored_audit_kernel_return_revised_result.json',dqfolder/'evidence/exit.json',
              dqfolder/'evidence/dq/exit.json',dqfolder/'evidence/dq/child_summary.json',
              dqfolder/'evidence/dq/raw.jsonl.gz',dqfolder/'evidence_stored_audit_kernel_return_revised/exit.json',
              bankfolder/'stored_audit_result.json',bankfolder/'evidence_stored_audit/exit.json',
              PREP/'dq_recorded_completion_v101/result_summary.json',
              PREP/'patch_whole_completion_v100/result_summary.json',
              ROOT/'src/rfl_rebuild/b2/utility.py',ROOT/'src/rfl_rebuild/b2/retention.py',
              ROOT/contract['healthy_reference']['path'],ROOT/contract['dev_lock']['path'],
              Path(__file__)]
    before={p.relative_to(ROOT).as_posix():bare_meta(meta(p)) for p in selected}
    review=metric_source_review()
    assert sys.implementation.name=='cpython' and tuple(sys.version_info[:3])==(3,12,14)
    curves={'dq':extract_external('dq',dqfolder/'evidence/dq',dq_audit,dq_receipt),
            'patch-adaptive':extract_external('patch-adaptive',HERE/'evidence/patch-adaptive',patch_audit,patch_receipt)}
    pairs={mode:pair_description(view) for mode,view in curves.items()}
    healthy=read_json(ROOT/contract['healthy_reference']['path'])
    assert bare_meta(meta(ROOT/contract['healthy_reference']['path']))['sha256']==contract['healthy_reference']['sha256']
    assert all(view['pre_level_hex']==float(healthy['v_pre']).hex()
               for modes in curves.values() for view in modes.values())
    oldwall=sum(c['old_wall_seconds'] for c in bank_audit['eight_comparisons'])
    newwall=sum(c['new_wall_seconds'] for c in bank_audit['eight_comparisons'])
    oldcpu=sum(c['old_cpu_seconds'] for c in bank_audit['eight_comparisons'])
    newcpu=sum(c['new_cpu_seconds'] for c in bank_audit['eight_comparisons'])
    report={'schema':'V108_COMPLETE_PATCH_WORKLOAD_AND_BOUNDED_V03_STAGE_FINDING',
            'generated_at_utc':datetime.now(timezone.utc).isoformat(),
            'parent_commit':contract['parent_commit'],
            'status':'COMPLETE_BOUNDED_OWNED_TECHNICAL_PAIR_CURVE_STAGE_FINDING_NOT_FORMAL_POPULATION_PASS',
            'stage_question':'Given fixed P responsibility and legal whole persistent correction, how does this complete declared future learning stream change?',
            'finding':phase_finding(curves,pairs),
            'positive_overall_benefit_is_not_a_completion_requirement':True,
            'bounded_stage_complete':True,'original_confirmatory_study_complete':False,
            'mean_return_is_not_success_rate':True,
            'closed_external_curve_metrics':curves,'per_stream_descriptive_pairs':pairs,
            'healthy_reference_level':healthy['v_pre'],'metric_source_review':review,
            'metric_inputs':'Only the physically bound completed EXTERNAL_VIEW payload values/episodes/pre_level/t_max; source/role/cost/B1 audits outside metric features',
            'completed_workloads':{'dq':compact_resource(dq_audit,dq_receipt),
                                   'patch-adaptive':compact_resource(patch_audit,patch_receipt)},
            'current_v108_extra_sources':1,'current_v108_extra_source_install_transactions':1,
            'current_v108_whole_B1_arms':2,'current_v108_original_owner_receipts':14,
            'current_v108_stored_audit_elapsed_seconds':new_audit_exit['elapsed_seconds'],
            'readpath_finite_performance':{'comparisons':bank_audit['eight_comparisons'],
                'old_timed_section_wall_seconds':oldwall,'new_timed_run_section_wall_seconds':newwall,
                'timed_section_wall_ratio':oldwall/newwall,
                'old_timed_section_cpu_seconds':oldcpu,'new_timed_run_section_cpu_seconds':newcpu,
                'timed_section_cpu_ratio':oldcpu/newcpu,
                'new_bank_prepare_token_snapshot_not_in_new_timed_section':True,
                'complete_v108_workflow_wall_includes_preparation':True,
                'not_production_or_complete_pipeline_speedup_ratio':True,
                'actual_v107_transactions':9},
            'previous_immediate_offtarget_diagnostics':preserved_offtarget(),
            'preserved_v106_patch_failure':{'complete':False,'native_exit_code':1,
                'message':old_partial['native_failure_preserved']['message'],
                'actual_counts':old_partial['actual_counts'],'training_receipts':old_partial['tag_inventory']['CORE_EPISODE'],
                'complete_recorded_banks':old_partial['complete_banks'],
                'complete_pair_handle':False,'reference_completed_epochs':465,'treatment_completed_epochs':415,
                'actual_wall_seconds':old_partial['instrumented_wall_seconds'],
                'unchanged_no_retry_or_resumption':True,
                'new_v108_entry_fresh_source_first_run_not_old_fixture_retry':True},
            'claim_limits':['This exact deterministic engineering stream is not independent seed inference or full keyed Xi qualification',
                'No universal mechanism/architecture winner, general zero harm, equivalence, CI, Holm or full family claim',
                'Original full k/shape fairness/family/400primary/200secondary confirmation remains uncollected',
                'No old F1 qualification transfer and no rewritten original PASS rule or evidence',
                'NoWrite also learns; patch prior policy improvement is distinct from numeric knowledge and B1 responsibility',
                'Original costs and truth are audit/provenance, never external outcome metric features',
                'Stored evidence does not reconstruct runtime identity'],
            'new_science_or_workload_keys':0,'RNG_keyderive_DP_nativecalibration':0,
            'formal_keyed_permit_issued_or_stream_executed':False,
            'formal_Protocol_Curve_train_curve_collector_collection':False,
            'scientific_qualification':False,'collection_authorized':False,
            'valid_original_mechanism_refutation':False,'scientific_STOP':False,
            'automation':'Disabled by direct human instruction; no automation tool called.',
            'source_binding_before':before,'old_executed_bytes_or_failure_artifacts_modified':False}
    after={p.relative_to(ROOT).as_posix():bare_meta(meta(p)) for p in selected}
    assert before==after
    report['source_binding_after']=after; report['input_bytes_unchanged']=True
    markdown=render_markdown(report)
    with (HERE/'result_summary.json').open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(report,stream,ensure_ascii=False,sort_keys=True,indent=2); stream.write('\n')
    with (HERE/'stage_result.md').open('x',encoding='utf-8',newline='\n') as stream:
        stream.write(markdown)
    print(canonical({'schema':report['schema'],'status':report['status'],
                     'result_summary':meta(HERE/'result_summary.json'),
                     'stage_result':meta(HERE/'stage_result.md'),
                     'bounded_stage_complete':True,'original_confirmatory_study_complete':False}),flush=True)


if __name__=='__main__':
    main()

