"""Predeclared V0.8 stored-only outcomes/costs; no environment or learning calls.

The small-DAG evaluator is external. Mechanism examples are post-run diagnostic
descriptions of actual visits, not additional counterfactual training streams.
"""
from collections import Counter, defaultdict
from pathlib import Path
import csv
import gzip
import hashlib
import json
import math
import random
import statistics
import time
from stored_review import world

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def read(p):
    return json.loads(p.read_text(encoding='utf-8'))


def save(name, x):
    with (HERE/name).open('x', encoding='utf-8', newline='\n') as f:
        json.dump(x, f, ensure_ascii=False, indent=2); f.write('\n')


def csv_save(name, rows):
    keys = list(dict.fromkeys(k for row in rows for k in row))
    with (HERE/name).open('x', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rows)


def mean(xs):
    return statistics.mean(xs)


def quantile(xs, p):
    xs = sorted(xs); position = (len(xs)-1)*p
    low = int(position); frac = position-low
    return xs[low]*(1-frac)+xs[min(low+1, len(xs)-1)]*frac


def wilson(k, n):
    z = 1.959963984540054
    phat = k/n; denom = 1+z*z/n
    center = (phat+z*z/(2*n))/denom
    radius = z*math.sqrt(phat*(1-phat)/n+z*z/(4*n*n))/denom
    return center-radius, center+radius


def true_values(source, program=None):
    task = source['public']; values = {task['goal']: 1.0}
    for s in range(task['goal']-1, -1, -1):
        row = [source['probabilities'][s][a]*values[task['successors'][s][a]] for a in (0, 1)]
        values[s] = max(row) if program is None else row[program[s]]
    return values


def auc(rows, key, end):
    data = [row for row in rows if row['checkpoint'] <= end]
    return sum((b['checkpoint']-a['checkpoint'])*(a[key]+b[key])/2 for a, b in zip(data, data[1:]))/end


def totals_at(row, epoch):
    return {'successes': 0, 'train_steps': 0} if epoch == 0 else row['train_curve'][epoch-1]


def mechanism(plan, sources):
    """The raw file was fully reconstructed by stored_review beforehand.

    This pass reads to EOF, reuses that review for evaluation records, and parses
    actual training records only. External counts are never learner inputs.
    """
    stats, examples = {}, {}
    visited_raw = 0
    pending = None
    tags = {name: ('"tag":"'+name+'"}\n').encode() for name in
            ('STREAM_INITIAL', 'TRAIN_POLICY', 'RAW', 'LEARN', 'STREAM_FINAL')}
    with gzip.open(HERE/'evidence_matrix/raw.jsonl.gz', 'rb') as f:
        for line in f:
            if line.endswith(tags['STREAM_INITIAL']):
                x = json.loads(line)['payload']; ctx = x['context']
                key = (ctx['condition'], ctx['arm'])
                state = x['learner']; external_counts = Counter()
                src = sources[ctx['condition'], ctx['mirror']]
                optimum = true_values(src)
                counter = stats.setdefault(key, Counter())
            elif line.endswith(tags['TRAIN_POLICY']):
                pending = json.loads(line)['payload']
            elif line.endswith(tags['RAW']) and pending is not None:
                x = json.loads(line)['payload']
                assert x['mode'] == 'train'
                visited_raw += 1
                for s, a, nxt, outcome in x['steps']:
                    greedy = pending['greedy'][s]
                    exploration = pending['coins'][s][0]
                    counter['actual_visits'] += 1
                    counter['collisions'] += outcome == 'COLLISION'
                    counter['repeated_collisions'] += outcome == 'COLLISION' and external_counts[s, a, 'COLLISION'] > 0
                    counter['greedy_overridden_by_exploration'] += a != greedy
                    quality = [src['probabilities'][s][b]*optimum[src['public']['successors'][s][b]] for b in (0, 1)]
                    counter['actual_suboptimal_choices'] += quality[a] < max(quality)
                    counter['greedy_suboptimal_visits'] += quality[greedy] < max(quality)
                    if ctx['condition'].startswith('branch') and s % 3 == 0:
                        counter['fork_visits'] += 1
                        counter['locally_easier_globally_worse_fork_choices'] += src['probabilities'][s][a] == .95
                    unique = False
                    if 'q' in state:
                        q = state['q'][2*s:2*s+2]
                        unique = q[0] != q[1]
                        qa = 0 if q[0] >= q[1] else 1
                        counter['Q_unique_max_visits'] += unique
                        counter['strict_wrong_Q_visits'] += unique and quality[qa] < max(quality)
                    if pending['shadow_covered']:
                        shadow = pending['shadow'][s]
                        ft, m1 = shadow['FT'], shadow['M1']
                        counter['M1_shadow_diff_FT'] += m1 != ft
                        counter['M1_shadow_better_than_FT'] += quality[m1] > quality[ft]
                        counter['M1_shadow_worse_than_FT'] += quality[m1] < quality[ft]
                        counter['M1_shadow_equal_quality_FT'] += quality[m1] == quality[ft]
                        counter['strict_Q_disagrees_with_M1'] += unique and m1 != qa
                        changed = not exploration and greedy != ft
                        counter['actual_nonexplore_changed_from_FT'] += changed
                        counter['actual_change_better_than_FT'] += changed and quality[greedy] > quality[ft]
                        counter['actual_change_worse_than_FT'] += changed and quality[greedy] < quality[ft]
                        counter['actual_change_equal_quality_FT'] += changed and quality[greedy] == quality[ft]
                        kinds = []
                        if ctx['arm'].endswith('M1') and changed and unique and quality[qa] < max(quality):
                            kinds.append('M1_actual_change_of_strict_wrong_Q')
                        if ctx['arm'].endswith('M1') and changed and quality[greedy] < quality[ft]:
                            kinds.append('M1_actual_worse_choice_than_FT')
                        for kind in kinds:
                            token = '|'.join((ctx['condition'], ctx['arm'], kind))
                            if token not in examples:
                                examples[token] = {'context': ctx, 'epoch': pending['epoch'], 'uid': x['uid'],
                                                   'state': s, 'shadow': shadow, 'actual_greedy': greedy,
                                                   'actual_action': a, 'actual_visible_outcome': outcome,
                                                   'external_optimal_continuation_action_values': quality,
                                                   'interpretation': 'First chronological matching actual visit. Alternative readout/value is diagnostic, not an executed counterfactual learning stream.'}
                    external_counts[s, a, outcome] += 1
            elif line.endswith(tags['LEARN']):
                assert pending is not None
                state = json.loads(line)['payload']['after']; pending = None
    assert visited_raw == 442368
    rows = []
    q_fields = ['Q_unique_max_visits', 'strict_wrong_Q_visits']
    shadow_fields = ['M1_shadow_diff_FT', 'M1_shadow_better_than_FT', 'M1_shadow_worse_than_FT',
                     'M1_shadow_equal_quality_FT', 'strict_Q_disagrees_with_M1', 'actual_nonexplore_changed_from_FT',
                     'actual_change_better_than_FT', 'actual_change_worse_than_FT', 'actual_change_equal_quality_FT']
    ordinary_fields = ['actual_visits', 'collisions', 'repeated_collisions', 'greedy_overridden_by_exploration',
                       'actual_suboptimal_choices', 'greedy_suboptimal_visits', 'fork_visits',
                       'locally_easier_globally_worse_fork_choices']
    for (condition, arm), c in stats.items():
        q_covered, shadow_covered = arm != 'F0', arm.startswith('F-')
        row = {'condition': condition, 'arm': arm, 'external_actual_history_covered': True,
               'Q_diagnostic_covered': q_covered, 'shadow_covered': shadow_covered}
        row.update({f: c[f] for f in ordinary_fields})
        row.update({f: c[f] if q_covered else None for f in q_fields})
        row.update({f: c[f] if shadow_covered else None for f in shadow_fields})
        rows.append(row)
    return rows, examples


def main():
    started = time.perf_counter()
    plan = read(HERE.parent/'plan_v175.json')
    audit = read(HERE/'evidence_matrix/audit_result.json')
    assert audit['exit_code'] == 0
    streams = read(HERE/'evidence_matrix/result.json')['streams']
    sources = {(c['id'], m): world(plan, c, m) for c in plan['environments'] for m in (0, 1)}
    frozen, summaries, targets, online = [], [], [], []
    case_metrics, groups, case_streams = {}, defaultdict(list), {}
    for stream in streams:
        c, arm, seed, mirror = (stream[k] for k in ('condition', 'arm', 'seed', 'mirror'))
        src = sources[c, mirror]; jstar = true_values(src)[0]
        context = {'condition': c, 'arm': arm, 'seed': seed, 'mirror': mirror}
        curve, observed_first, exact_first = [], None, None
        exact_drops = observed_drops = 0
        prior_exact = prior_observed = False
        for bank in stream['eval_banks']:
            jp = true_values(src, bank['program'])[0]
            lo, hi = wilson(bank['successes'], bank['episodes'])
            row = {**context, 'checkpoint': bank['checkpoint'], 'successes': bank['successes'],
                   'episodes': bank['episodes'], 'observed_success': bank['mean_success'],
                   'Wilson95_low': lo, 'Wilson95_high': hi, 'exact_policy_success': jp,
                   'exact_optimal_success': jstar, 'exact_relative': jp/jstar,
                   'observed_relative': bank['mean_success']/jstar,
                   'observed_minus_exact': bank['mean_success']-jp,
                   'observed_target_uncertain': lo <= .9*jstar <= hi}
            exact_ok, observed_ok = jp >= .9*jstar, bank['mean_success'] >= .9*jstar
            if exact_ok and exact_first is None:
                exact_first = bank['checkpoint']
            if observed_ok and observed_first is None:
                observed_first = bank['checkpoint']
            exact_drops += prior_exact and not exact_ok; observed_drops += prior_observed and not observed_ok
            prior_exact, prior_observed = exact_ok, observed_ok
            curve.append(row); frozen.append(row)
        target = {**context, 'exact_first_checkpoint': exact_first, 'observed_first_checkpoint': observed_first,
                  'exact_first_train_steps': None if exact_first is None else totals_at(stream, exact_first)['train_steps'],
                  'observed_first_train_steps': None if observed_first is None else totals_at(stream, observed_first)['train_steps'],
                  'first_target_disagreement': exact_first != observed_first, 'exact_drops': exact_drops, 'observed_drops': observed_drops}
        targets.append(target)
        metric = {**context, 'early_exact_relative_AUC': auc(curve, 'exact_relative', 64),
                  'early_observed_relative_AUC': auc(curve, 'observed_relative', 64),
                  'whole_exact_relative_AUC': auc(curve, 'exact_relative', 256),
                  'final_exact_success': curve[-1]['exact_policy_success'], 'final_exact_relative': curve[-1]['exact_relative'],
                  'final_observed_success': curve[-1]['observed_success'], 'train_steps': stream['train_steps'],
                  'train64_successes': totals_at(stream, 64)['successes'],
                  'train128_successes': totals_at(stream, 128)['successes'], 'train256_successes': stream['train_successes']}
        case_metrics[c, seed, mirror, arm] = metric
        case_streams[c, seed, mirror, arm] = stream
        groups[c, arm].append((stream, metric, target, curve))
        for row in stream['train_curve']:
            online.append({**context, **row})
    for (c, arm), g in groups.items():
        counters = Counter()
        for s, _, _, _ in g:
            counters.update(s['counts'])
        metric = {'condition': c, 'arm': arm, 'independent_seed_blocks': 32, 'streams': len(g), 'train_tasks': 256*len(g)}
        for f in ('train64_successes', 'train128_successes', 'train256_successes', 'train_steps'):
            metric[f] = sum(x[1][f] for x in g)
        for f in ('early_exact_relative_AUC', 'early_observed_relative_AUC', 'whole_exact_relative_AUC',
                  'final_exact_success', 'final_exact_relative', 'final_observed_success'):
            metric[f] = mean(x[1][f] for x in g)
        metric.update(exact_target_reached=sum(x[2]['exact_first_checkpoint'] is not None for x in g),
                      observed_target_reached=sum(x[2]['observed_first_checkpoint'] is not None for x in g),
                      target_first_disagreements=sum(x[2]['first_target_disagreement'] for x in g),
                      exact_target_drops=sum(x[2]['exact_drops'] for x in g), observed_target_drops=sum(x[2]['observed_drops'] for x in g))
        for f in ('ordinary_backups', 'replay_backups', 'model_backups', 'fact_updates', 'numeric_changes',
                  'policy_calls', 'goal_planning_edges', 'actual_M1_edges', 'actual_tie_candidate_scores',
                  'shadow_M1_edges', 'shadow_tie_scores'):
            metric[f] = counters[f]
        metric['actual_policy_ns'] = sum(s['train_curve'][-1]['policy_ns']+sum(b['policy_ns'] for b in s['eval_banks']) for s, _, _, _ in g)
        metric['actual_update_ns'] = sum(s['train_curve'][-1]['update_ns'] for s, _, _, _ in g)
        metric['diagnostic_shadow_ns'] = sum(s['train_curve'][-1]['shadow_ns'] for s, _, _, _ in g)
        summaries.append(metric)

    rng = random.Random('V08|analysis_bootstrap')
    indices = [[rng.randrange(32) for _ in range(32)] for _ in range(10000)]
    comparisons, deltas, matched, matched_summary = [], [], [], []
    pairs = plan['evaluation']['primary_pairs']+plan['evaluation']['secondary_pairs']
    for condition in plan['environments']:
        c = condition['id']
        for left, right in pairs:
            ds = []
            for seed in range(8001, 8033):
                values = [case_metrics[c, seed, m, left]['early_exact_relative_AUC']-case_metrics[c, seed, m, right]['early_exact_relative_AUC'] for m in (0, 1)]
                d = mean(values); ds.append(d)
                deltas.append({'condition': c, 'left': left, 'right': right, 'seed': seed, 'paired_mirror_mean_early_exact_AUC_delta': d})
            boots = [sum(ds[i] for i in ids)/32 for ids in indices]
            row = {'condition': c, 'left': left, 'right': right,
                   'primary': c in plan['evaluation']['primary_conditions'] and [left, right] in plan['evaluation']['primary_pairs'],
                   'paired_seed_blocks': 32, 'early_exact_relative_AUC_delta': mean(ds), 'median_delta': statistics.median(ds),
                   'bootstrap95_low': quantile(boots, .025), 'bootstrap95_high': quantile(boots, .975),
                   'positive_seeds': sum(d > 0 for d in ds), 'zero_seeds': sum(d == 0 for d in ds), 'negative_seeds': sum(d < 0 for d in ds)}
            for f in ('early_observed_relative_AUC', 'final_exact_success', 'train64_successes', 'train128_successes', 'train256_successes', 'train_steps'):
                row[f+'_mean_case_delta'] = mean(case_metrics[c, s, m, left][f]-case_metrics[c, s, m, right][f] for s in range(8001, 8033) for m in (0, 1))
            comparisons.append(row)
            for fraction in (.25, .5, .75, 1.0):
                cutoffs, successes_l, successes_r = [], [], []
                for seed in range(8001, 8033):
                    for m in (0, 1):
                        sl, sr = (case_streams[c, seed, m, a] for a in (left, right))
                        cutoff = int(min(sl['train_steps'], sr['train_steps'])*fraction)
                        def prefix(s):
                            completed = [r for r in s['train_curve'] if r['train_steps'] <= cutoff]
                            return completed[-1]['successes'] if completed else 0
                        l, r = prefix(sl), prefix(sr)
                        cutoffs.append(cutoff); successes_l.append(l); successes_r.append(r)
                        matched.append({'condition': c, 'left': left, 'right': right, 'fraction': fraction,
                                        'seed': seed, 'mirror': m, 'shared_train_step_budget': cutoff,
                                        'left_completed_successes': l, 'right_completed_successes': r})
                matched_summary.append({'condition': c, 'left': left, 'right': right, 'fraction': fraction,
                                        'shared_train_step_budget_sum': sum(cutoffs),
                                        'left_completed_successes': sum(successes_l), 'right_completed_successes': sum(successes_r)})

    mech, examples = mechanism(plan, sources)
    native = [read(HERE/p/'exit.json') for p in ('evidence_wiring', 'evidence_matrix')]
    combined = Counter()
    for receipt in native:
        assert receipt['child_exit_code'] == 0
        combined.update(receipt['counts'])
    assert combined['rollouts'] == plan['budgets']['combined_rollouts']
    csv_save('group_summary.csv', summaries); csv_save('comparisons.csv', comparisons)
    csv_save('frozen_curves.csv', frozen); csv_save('online_curves.csv', online)
    csv_save('paired_seed_deltas.csv', deltas); csv_save('targets.csv', targets)
    csv_save('matched_train_steps.csv', matched); csv_save('matched_cost_summary.csv', matched_summary)
    csv_save('mechanism.csv', mech); save('mechanism_examples.json', examples)
    report = {'status': 'STORED_ANALYSIS_COMPLETE_CONDITIONAL_LOCAL_STUDY', 'group_summaries': summaries,
              'comparisons': comparisons, 'matched_cost': matched_summary, 'mechanism': mech,
              'targets': {'streams': len(targets), 'exact_reached': sum(t['exact_first_checkpoint'] is not None for t in targets),
                          'observed_reached': sum(t['observed_first_checkpoint'] is not None for t in targets),
                          'first_label_disagreements': sum(t['first_target_disagreement'] for t in targets),
                          'bank_threshold_measurement_uncertain': sum(r['observed_target_uncertain'] for r in frozen)},
              'native_combined_counts': dict(combined), 'native_wall_seconds_sum': sum(n['wall_seconds'] for n in native),
              'compressed_capture_bytes': sum(n['compressed_bytes'] for n in native),
              'native_PRNG_random_calls': 2211840, 'bootstrap_randrange_calls': 320000, 'bootstrap_resamples': 10000,
              'analysis_wall_seconds_before_final_reports': time.perf_counter()-started,
              'new_native_in_analysis': 0, 'qualification': False}
    save('analysis.json', report)
    lines = ['# V0.8 实际结果：更难的选择，及时使用事实', '',
             '**固定矩阵已执行；以下为本地有限任务结论，不是通用强化反馈学习资格。**', '',
             '九组、32独立训练seed、两镜像、三地图；每流256训练，7点各512冻结评估。',
             f'含新接线共{combined["rollouts"]}真实回合、{combined["steps"]}真实步；native两phase首次exit0。', '',
             '## 分地图结果', '',
             '主AUC为前64训练范围内的精确策略成功率/可达最优值的梯形均值，不是V0.7的实测前32AUC口径。', '']
    for condition in plan['environments']:
        c = condition['id']; star = true_values(sources[c, 0])[0]
        lines += [f'### {c}（真实最优成功概率 {star:.8f}）', '',
                  '|组|训练成功/16384|前64成功/4096|早期相对AUC|终点精确成功率|终点实测成功率|达标流/64|',
                  '|---|---:|---:|---:|---:|---:|---:|']
        for g in [g for g in summaries if g['condition'] == c]:
            lines.append(f'|{g["arm"]}|{g["train256_successes"]}|{g["train64_successes"]}|{g["early_exact_relative_AUC"]:.6f}|{g["final_exact_success"]:.6f}|{g["final_observed_success"]:.6f}|{g["exact_target_reached"]}|')
        lines += ['', '|对照（左−右）|早期AUC差|seed配对bootstrap95|正/零/负seed|', '|---|---:|---|---|']
        for x in [x for x in comparisons if x['condition'] == c and x['left'] == 'F-R-M1' and x['right'] in ('F-R-FT', 'F-R-CT')]:
            lines.append(f'|{x["left"]}−{x["right"]}|{x["early_exact_relative_AUC_delta"]:.6f}|[{x["bootstrap95_low"]:.6f}, {x["bootstrap95_high"]:.6f}]|{x["positive_seeds"]}/{x["zero_seeds"]}/{x["negative_seeds"]}|')
        lines.append('')
    lines += ['## 解释边界', '',
              '- 更难的图不仅是更长：局部.95的分叉通向较差后继，不能把即时前进概率更大当全局较好。外部动作质量计入最优后继；未喂给学习器。',
              '- 本轮接受正、零、负结果；不要求所有方法或指标都赢。最终追平不抹去早期效率，早失败导致步数少也不是效率胜利。共同步数结果见matched_cost_summary.csv。',
              '- 纯RL/纯反馈是明确实现路线，不是全部RL算法的代表。所有组都保留普通成功与失败学习；不增加成功诊断、调查或治疗。',
              '- 同状态FT/CT/M1建议与外部动作值用于机制诊断，不是三条已经执行的反事实训练。M1仍依赖后继Q，不能从局部改变推出全部事实利用已解决。',
              '- 512实际评估、精确策略值与首次达标标签分开。精确计算去除小图评估抽样噪声，不去除训练seed差异；未达null/后续退步保留。',
              '- 原生计时含capture与机制仪器，shadow计算单列；不是生产算法速度。内部存储审阅不是独立专家或科学PASS。', '',
              '全部成对差值、成本、机制、正负例及原始捕获均保留；不重跑旧阶段，不按结果改参数或加样本。']
    with (HERE/'result.md').open('x', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines)+'\n')

    colors = ['#164e63', '#dc2626', '#16a34a', '#9333ea', '#ca8a04', '#2563eb']
    selected = ['RL-RP', 'RL-R', 'F0', 'F-R-FT', 'F-R-CT', 'F-R-M1']
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="440" viewBox="0 0 1200 440">',
           '<rect width="1200" height="440" fill="white"/>',
           '<g font-family="Arial, sans-serif" font-size="13">',
           '<text x="30" y="24">V0.8 frozen policy quality J_pi/J_star (32 seed blocks, mirrors averaged)</text>']
    for panel, condition in enumerate(plan['environments']):
        c = condition['id']; x0, y0, w, h = 45+panel*395, 60, 340, 270
        svg.append(f'<text x="{x0}" y="48">{c}</text><path d="M{x0},{y0}V{y0+h}H{x0+w}" stroke="#555" fill="none"/>')
        for epoch in plan['matrix']['checkpoints']:
            x = x0+w*epoch/256
            svg.append(f'<text x="{x}" y="{y0+h+18}" text-anchor="middle">{epoch}</text>')
        for arm, color in zip(selected, colors):
            points = []
            for epoch in plan['matrix']['checkpoints']:
                val = mean(row['exact_relative'] for row in frozen if row['condition'] == c and row['arm'] == arm and row['checkpoint'] == epoch)
                points.append(f'{x0+w*epoch/256:.2f},{y0+h*(1-val):.2f}')
            svg.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="2"/>')
    for i, (arm, color) in enumerate(zip(selected, colors)):
        x = 40+i*190
        svg.append(f'<path d="M{x},395h25" stroke="{color}" stroke-width="3"/><text x="{x+32}" y="399">{arm}</text>')
    svg += ['<text x="40" y="427">All nine arms, raw banks, paired intervals and observed rates are retained in CSV/JSON; plotted lines are means, not confidence bands.</text>', '</g></svg>']
    with (HERE/'frozen_curves.svg').open('x', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(svg)+'\n')
    print(json.dumps({'status': report['status'], 'native_rollouts': combined['rollouts'],
                      'primary': [x for x in comparisons if x['primary']], 'analysis_wall_seconds': time.perf_counter()-started}))


if __name__ == '__main__':
    main()
