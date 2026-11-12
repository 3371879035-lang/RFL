"""Automatic stored-results report; no model selection, training or environment calls."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
import statistics
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
GROUPS = ('RL-plain', 'RL-outer', 'F0', 'F-RP', 'F-R')


def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))


def sha(p):
    with Path(p).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def mean(xs):
    return statistics.mean(xs) if xs else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', choices=['smoke', 'long'], required=True)
    mode = ap.parse_args().mode
    folder = HERE/f'evidence_{mode}'
    try:
        native = read(HERE/f'native_{mode}_exit.json')
        summary_path = folder/'summary.json'
        if summary_path.exists():
            summary = read(summary_path)
            records = summary['results']
            common = summary['completed_common_blocks']
        else:
            records = [read(p) for p in folder.glob('seed*/*/*/result.json')]
            common_path = folder/'last_common.json'
            common = read(common_path)['block'] if common_path.exists() else 0
            summary = dict(status='INCOMPLETE_NATIVE', completed_common_blocks=common)
        claim = read(folder/'claim.json')
        cfg = claim['config']
        changed = [p for p, h in claim['inputs'].items() if sha(ROOT/p) != h]
        complete = [r for r in records if r['status'] == 'COMPLETE']
        blocks = [r for r in complete if r['stage'].startswith('block') and r['block'] <= common]
        seeds = sorted({r['seed'] for r in complete if r['stage'] == 'initial'})
        for block in range(1, common+1):
            rows = [r for r in blocks if r['block'] == block]
            assert len(rows) == len(seeds)*5
            assert all(r['charged_environment_steps'] == cfg['charged_steps'] and
                       r['optimizer_updates'] == cfg['optimizer_steps'] for r in rows)
        for seed in seeds:
            a = next(r for r in complete if r['seed'] == seed and r['group'] == 'RL-plain' and r['stage'] == 'initial')
            b = next(r for r in complete if r['seed'] == seed and r['group'] == 'RL-outer' and r['stage'] == 'initial')
            assert a['parameter_hash'] == b['parameter_hash'] and a['report'] == b['report']
        mechanisms, coverage = [], []
        for group in GROUPS:
            rows = [r for r in blocks if r['group'] == group]
            count = Counter()
            updates = Counter()
            step_counts = Counter()
            for row in rows:
                count.update(row['mechanism_events'])
                updates.update(row['optimizer_roles'])
                step_counts.update(row['step_counts'])
                assert sum(row['optimizer_roles'].values()) == row['optimizer_updates']
                if group == 'RL-plain':
                    assert row['outer'] is None
                    assert not (set(row['optimizer_roles'])-{'ordinary_online', 'ordinary_budget_replay'})
                    assert not (set(row['step_counts'])-{'ordinary', 'interim_report'})
                else:
                    o = row['outer']
                    assert row['mechanism_events']['adopt'] == row['mechanism_events']['dream'] == 1
                    if o['teacher_selected'] is not None:
                        assert row['optimizer_roles']['student'] == row['optimizer_roles']['sleep_ordinary_reference'] == cfg['fit_updates']
                        assert o['adopted'] == (all(v > 0 for v in o['two_block_gains']) and
                                                o['student_gate']['captured'] <= o['reference_gate']['captured'])
            outers = [r['outer'] for r in rows if r['outer'] is not None]
            mechanisms.append(dict(group=group, complete_blocks=len(rows), mechanism_events=dict(count),
                                   optimizer_roles=dict(updates), environment_step_roles=dict(step_counts),
                                   history_suggestions=sum(o['cases']['history_suggestions'] for o in outers),
                                   teachers_tested=sum(len(o['teachers']) for o in outers),
                                   teachers_qualified=sum(o['teacher_selected'] is not None for o in outers),
                                   students_adopted=sum(o['adopted'] for o in outers),
                                   ordinary_no_qualifying_failure=sum(o['cases']['cases'] == 0 for o in outers)))
            for seed in seeds:
                episodes = []
                for r in rows:
                    if r['seed'] != seed:
                        continue
                    path = folder/f'seed{seed}'/group/r['stage']/'events.jsonl.gz'
                    with gzip.open(path, 'rt', encoding='utf-8') as f:
                        for line in f:
                            e = json.loads(line)
                            if e['kind'] == 'episode' and e.get('phase') == 'ordinary':
                                episodes.append(e)
                coverage.append(dict(seed=seed, group=group, finished_ordinary_episodes=len(episodes),
                                     mean_episode_steps=mean([e['steps'] for e in episodes]),
                                     reached96=sum(e['steps'] >= 96 for e in episodes),
                                     reached160=sum(e['steps'] >= 160 for e in episodes),
                                     reached256=sum(e['steps'] >= 256 for e in episodes),
                                     score_mean=mean([e['score'] for e in episodes])))
        curves = [dict(seed=r['seed'], group=r['group'], block=r['block'], stage=r['stage'],
                       charged_steps=r.get('charged_environment_total', 0), mean=r['report']['mean'],
                       mean_steps=r['report']['mean_steps'], captured=r['report']['captured'],
                       episodes=len(r['report']['rows'])) for r in complete if r.get('report') is not None]
        finals = [r for r in complete if r['stage'] == 'final' and r['block'] == common]
        final_complete = len(finals) == len(seeds)*5 and bool(seeds)
        groups = []
        if final_complete:
            for r in finals:
                rep = r['report']
                assert rep['mean'] == mean([x['score'] for x in rep['rows']])
                assert rep['captured'] == sum(x['captured'] for x in rep['rows'])
                assert len(rep['rows']) == cfg['final_report']
            for group in GROUPS:
                rs = sorted([r for r in finals if r['group'] == group], key=lambda r: r['seed'])
                differences = []
                strata = {}
                for r in rs:
                    base = next(x for x in finals if x['group'] == 'RL-plain' and x['seed'] == r['seed'])
                    assert [x['episode'] for x in r['report']['rows']] == [x['episode'] for x in base['report']['rows']]
                    differences.append(r['report']['mean']-base['report']['mean'])
                for name, parity in (('seen', 0), ('reserved_report', 1)):
                    strata[name] = mean([mean([x['score'] for x in r['report']['rows'] if x['episode'] % 2 == parity]) for r in rs])
                groups.append(dict(group=group, seeds=len(rs), mean_score=mean([r['report']['mean'] for r in rs]),
                                   mean_steps=mean([r['report']['mean_steps'] for r in rs]),
                                   capture_rate=mean([r['report']['captured']/len(r['report']['rows']) for r in rs]),
                                   difference_vs_plain=mean(differences), per_seed_difference=differences,
                                   positive_seeds=sum(x > 0 for x in differences), strata=strata,
                                   report_episodes_per_seed=cfg['final_report']))
        succeeded = native['exit_code'] == 0 and native['interruption'] is None and not changed and final_complete
        artifact_bytes = sum(p.stat().st_size for p in folder.rglob('*') if p.is_file())
        result = dict(status='COMPLETED_LOCAL_CONTINUATION' if succeeded else 'PARTIAL_OR_INCOMPLETE',
                      native=native, common_blocks=common, seeds=seeds, groups=groups,
                      charged_steps_per_job=common*cfg['charged_steps'], optimizer_steps_per_job=common*cfg['optimizer_steps'],
                      total_actual_environment_steps=sum(r.get('environment_steps', 0) for r in records),
                      total_actual_optimizer_steps=sum(r.get('optimizer_updates', 0) for r in records),
                      input_pins_checked=len(claim['inputs']), changed_inputs=changed,
                      mechanism_audit=mechanisms, ordinary_coverage=coverage, curves=curves,
                      artifact_bytes_before_report=artifact_bytes,
                      limits=['Four existing pretrained seed clusters; no guarantee from long duration alone.',
                              'F0 means no environment reward/Q, but has explicit goal preferences.',
                              'Equal environment calls and optimizer steps, not identical FLOPs.',
                              'Historical similarity proposes a trial, not a proved complete cause.',
                              'Conditional Sleep is skipped if no teacher qualifies; no forced adoption.'])
        with (folder/'analysis.json').open('x', encoding='utf-8', newline='\n') as f:
            json.dump(result, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write('\n')
        text = ['# V198 自动结果报告', '', f"状态：{result['status']}；共同完成 {common} 个预算块。",
                f"每条轨迹累计实际计费环境步 {result['charged_steps_per_job']:,}；优化器更新 {result['optimizer_steps_per_job']:,}。",
                '普通 RL 与增强 RL 起始参数和初始报告完全相同；普通 RL 没有候选试训/教师/蒸馏。', '',
                '|组别|最终平均分|相对普通 RL|正差种子|平均局长|被抓率|', '|---|---:|---:|---:|---:|---:|']
        for g in groups:
            text.append(f"|{g['group']}|{g['mean_score']:.3f}|{g['difference_vs_plain']:+.3f}|{g['positive_seeds']}/{g['seeds']}|{g['mean_steps']:.2f}|{g['capture_rate']:.3%}|")
        text += ['', '## 核心流程实际计数', '', '|组别|历史改法建议|教师试训|教师合格/SLEEP|学生采用|无合格问题而普通学习|', '|---|---:|---:|---:|---:|---:|']
        for m in mechanisms:
            text.append(f"|{m['group']}|{m['history_suggestions']}|{m['teachers_tested']}|{m['teachers_qualified']}|{m['students_adopted']}|{m['ordinary_no_qualifying_failure']}|")
        text += ['', '## 解释边界', '', '这是一轮更长训练和修复对照后的实验，不是只改变训练时长的单因素试验。四个已有种子而非几千个独立模型。教师/学生均按开发阶段实测后才采用，最终报告不参与筛选。',
                 '历史给出待检验的改法，不是确定原因。没有合格教师时跳过 SLEEP，不为保证调用数量强制更新。',
                 f"总实际环境步（含报告）{result['total_actual_environment_steps']:,}；总优化器更新（含拒绝候选）{result['total_actual_optimizer_steps']:,}。",
                 '详细逐种子、覆盖率、学习曲线和机制调用见同目录 analysis.json。未完成/中断保持原状，不自动重试。', '']
        (folder/'report.md').write_text('\n'.join(text), encoding='utf-8', newline='\n')
        print(json.dumps(dict(status=result['status'], common_blocks=common, groups=groups), ensure_ascii=False))
        return 0 if succeeded else 1
    except BaseException:
        error = traceback.format_exc()
        with (folder/'analysis_error.json').open('x', encoding='utf-8') as f:
            json.dump(dict(status='ANALYSIS_ERROR', error=error), f, indent=2)
        print(error)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
