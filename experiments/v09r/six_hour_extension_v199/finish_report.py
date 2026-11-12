"""Read-only paired 12-hour versus additional-six-hour report; no learner import."""
import gzip
import hashlib
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
GROUPS = ('RL-plain', 'RL-outer', 'F0', 'F-RP', 'F-R')


def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))


def mean(xs):
    return statistics.mean(xs) if xs else None


def write(p, value):
    with Path(p).open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


def main():
    e = HERE/'evidence'
    native = read(HERE/'native_exit.json')
    binding = read(e/'source_binding.json')
    claim = read(e/'claim.json')
    summary = read(e/'summary.json') if (e/'summary.json').exists() else None
    records = summary['results'] if summary else [read(p) for p in e.glob('seed*/*/*/result.json')]
    common = read(e/'last_common.json')['block'] if (e/'last_common.json').exists() else binding['base_block']
    blocks = [r for r in records if r['status'] == 'COMPLETE' and r['stage'].startswith('block') and r['block'] <= common]
    finals = [r for r in records if r['status'] == 'COMPLETE' and r['stage'] == 'final' and r['block'] == common]
    changed = []
    for p, h in claim['inputs'].items():
        with (ROOT/p).open('rb') as f:
            if hashlib.file_digest(f, 'sha256').hexdigest() != h:
                changed.append(p)
    for b in range(binding['base_block']+1, common+1):
        rows = [r for r in blocks if r['block'] == b]
        assert len(rows) == 20
        assert all(r['charged_environment_steps'] == 131072 and r['optimizer_updates'] == 1024 for r in rows)
    mechanisms, groups, losses = [], [], []
    for group in GROUPS:
        rows = [r for r in blocks if r['group'] == group]
        roles, events, phases = Counter(), Counter(), Counter()
        loss_blocks = []
        for r in rows:
            roles.update(r['optimizer_roles'])
            events.update(r['mechanism_events'])
            phases.update(r['step_counts'])
            assert sum(r['optimizer_roles'].values()) == 1024
            if group == 'RL-plain':
                assert r['outer'] is None and not (set(r['optimizer_roles'])-{'ordinary_online','ordinary_budget_replay'})
            elif r['outer']['teacher_selected'] is not None:
                o = r['outer']
                assert r['optimizer_roles']['student'] == r['optimizer_roles']['sleep_ordinary_reference'] == 32
                assert o['adopted'] == (all(x > 0 for x in o['two_block_gains']) and
                                        o['student_gate']['captured'] <= o['reference_gate']['captured'])
            vals = []
            with gzip.open(e/f"seed{r['seed']}"/group/r['stage']/'events.jsonl.gz', 'rt', encoding='utf-8') as f:
                for line in f:
                    if line.startswith('{"kind":"optimizer",'):
                        q = json.loads(line)
                        if q['role'] == 'ordinary_online':
                            vals.append(q['total_loss'])
            loss_blocks.append(dict(seed=r['seed'], block=r['block'], mean=mean(vals), n=len(vals)))
        os = [r['outer'] for r in rows if r['outer'] is not None]
        mechanisms.append(dict(group=group, history_suggestions=sum(o['cases']['history_suggestions'] for o in os),
            teachers_tested=sum(len(o['teachers']) for o in os), sleep=sum(o['teacher_selected'] is not None for o in os),
            adopted=sum(o['adopted'] for o in os), optimizer_roles=dict(roles), events=dict(events), step_roles=dict(phases)))
        losses.append(dict(group=group, block_means=loss_blocks))
        if len(finals) == 20:
            pairs = []
            for r in sorted([r for r in finals if r['group'] == group], key=lambda r:r['seed']):
                before = next(b['parent_final_report'] for b in binding['files'] if b['seed'] == r['seed'] and b['group'] == group)
                after = r['report']
                assert len(before['rows']) == len(after['rows']) == 512
                assert [x['episode'] for x in before['rows']] == [x['episode'] for x in after['rows']]
                assert before['mean'] == mean([x['score'] for x in before['rows']])
                assert after['mean'] == mean([x['score'] for x in after['rows']])
                ref = next(x for x in finals if x['seed'] == r['seed'] and x['group'] == 'RL-plain')['report']
                pairs.append(dict(seed=r['seed'], before=before['mean'], after=after['mean'],
                    change=after['mean']-before['mean'], versus_plain=after['mean']-ref['mean'],
                    before_capture=before['captured']/512, after_capture=after['captured']/512,
                    before_steps=before['mean_steps'], after_steps=after['mean_steps']))
            groups.append(dict(group=group, paired_seeds=pairs, before=mean([r['before'] for r in pairs]),
                after=mean([r['after'] for r in pairs]), change=mean([r['change'] for r in pairs]),
                positive_seeds=sum(r['change'] > 0 for r in pairs), versus_plain=mean([r['versus_plain'] for r in pairs])))
    ok = (native['exit_code'] == 0 and native['interruption'] is None and len(finals) == 20 and
          not changed and summary is not None and summary['status'] == 'COMPLETE_BUDGETED_EXTENSION')
    result = dict(status='COMPLETED_LOCAL_EXTENSION' if ok else 'PARTIAL_OR_INCOMPLETE',
                  base_block=binding['base_block'], final_common_block=common,
                  additional_blocks=common-binding['base_block'], native=native,
                  groups=groups, mechanisms=mechanisms, ordinary_losses=losses,
                  interim_curves=[dict(seed=r['seed'], group=r['group'], block=r['block'], report=r['report'])
                                  for r in blocks if r.get('report') is not None],
                  changed_inputs=changed, actual_environment_steps=sum(r.get('environment_steps',0) for r in records),
                  actual_optimizer_updates=sum(r.get('optimizer_updates',0) for r in records),
                  limits=['Extension authorized after interim results, not preregistered confirmatory stopping.',
                          'Four continuing seed clusters, not extra independent training seeds.',
                          'Same held-out report bank across endpoints; no report-driven adoption.',
                          'Additional training/history effects combined; not a Sleep-only ablation.',
                          'Equal environment/update budgets, not equal FLOPs; conditional Sleep may be skipped.'])
    write(e/'analysis.json', result)
    text = ['# V199 追加六小时结果', '', f"状态：{result['status']}。新增共同预算块 {result['additional_blocks']}。", '',
            '|组别|原十二小时终点|追加预算后|配对增量|改善种子数|追加后相对普通RL|',
            '|---|---:|---:|---:|---:|---:|']
    for g in groups:
        text.append(f"|{g['group']}|{g['before']:.3f}|{g['after']:.3f}|{g['change']:+.3f}|{g['positive_seeds']}/4|{g['versus_plain']:+.3f}|")
    text += ['', '## 额外预算内机制计数', '', '|组别|历史实测建议|候选试训|SLEEP|学生采用|', '|---|---:|---:|---:|---:|']
    for m in mechanisms:
        text.append(f"|{m['group']}|{m['history_suggestions']}|{m['teachers_tested']}|{m['sleep']}|{m['adopted']}|")
    text += ['', '原十二小时结果保留，不被本次追加覆盖。全状态继续，包括优化器、目标网络、回放、随机状态、历史与未结束对局。',
             '两终点使用同一512回合报告银行作配对比较，报告不参与训练选择；四个训练种子仍然只有四个。',
             '增加时长可检查学习曲线是否继续改善，不能替代更多独立训练种子或证明通用结论。',
             '普通训练损失逐种子逐轮保存在 analysis.json；不同组的损失配方不能横向排名。', '']
    (e/'report.md').write_text('\n'.join(text), encoding='utf-8')
    print(json.dumps(dict(status=result['status'], groups=groups), ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
