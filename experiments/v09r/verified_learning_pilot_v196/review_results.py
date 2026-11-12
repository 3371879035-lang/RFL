"""Stored-only V196 accounting and decision reconstruction; no environment/fit calls.

Authored after the native claim. This is not a native input or an independent
scientific review. Exclusive output retains this review's first failure.
"""
import collections
import datetime
import gzip
import hashlib
import json
import statistics
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ARMS = ('RL-RP', 'F0', 'F-RP', 'F-R')


def sha(p):
    with Path(p).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))


def write(p, value):
    with Path(p).open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


def lines(p):
    def bad(x):
        raise ValueError('Non-finite JSON: '+x)
    with gzip.open(p, 'rt', encoding='utf-8') as f:
        for line in f:
            yield json.loads(line, parse_constant=bad)


def mean(values):
    return statistics.mean(values)


def describe(values):
    return dict(n=len(values), mean=mean(values) if values else None,
                positive=sum(x > 0 for x in values), zero=sum(x == 0 for x in values),
                negative=sum(x < 0 for x in values), values=values)


def eval_rows(report, actual):
    rows = report['rows']
    assert len(rows) == len(actual)
    for r, a in zip(rows, actual):
        assert r == {k: a[k] for k in r}, (r, a)
    assert report['mean'] == mean(r['score'] for r in rows)
    assert report['mean_steps'] == mean(r['steps'] for r in rows)
    assert report['captured'] == sum(r['captured'] for r in rows)


def audit_job(job):
    seed, arm = job['seed'], job['arm']
    d = HERE/'evidence'/f'seed{seed}'/arm
    assert read(d/'result.json') == job and job['status'] == 'COMPLETE'
    events = list(lines(d/'events.jsonl.gz'))
    episode_events = [e for e in events if e['kind'] == 'episode']
    assert len(episode_events) == job['actual_rollouts']
    assert [e['rollout'] for e in episode_events] == list(range(len(episode_events)))
    rollouts = [[] for _ in episode_events]
    counts = collections.Counter()
    raw_count = 0
    for r in lines(d/'raw.jsonl.gz'):
        raw_count += 1
        assert r['id'] == raw_count
        e = episode_events[r['rollout']]
        rs = rollouts[r['rollout']]
        assert r['kind'] == e['phase'] and r['episode'] == e['episode']
        assert r['t'] == e['begin_t']+len(rs)+1
        assert 0 <= r['action'] < 16 and 0 <= r['proposed'] < 16
        assert r['score'] == 1.5*r['t']+100*r['collected']
        assert r['completed'] == (r['t'] == 256 and not r['captured'])
        assert r['reward'] == (None if arm == 'F0' else .015+r['pickup']-(int(r['captured']) if arm in ('RL-RP', 'F-RP') else 0))
        if rs:
            prev = rs[-1]
            assert r['before'] == prev['hero'] and not prev['captured'] and not prev['completed']
            assert r['collected'] == prev['collected']+r['pickup']
            assert (r['map'], r['mode']) == (prev['map'], prev['mode'])
        elif e['begin_t'] == 0:
            assert r['collected'] == r['pickup']
        rs.append(r)
        counts[r['kind']] += 1
    assert raw_count == job['environment_steps'] and dict(counts) == job['step_counts']
    episode_rows = []
    for e, rs in zip(episode_events, rollouts):
        last = rs[-1]
        assert len(rs) == e['new_steps'] and last['t'] == e['steps']
        assert last['captured'] or last['completed']
        for k in ('score', 'captured', 'completed'):
            assert e[k] == last[k]
        episode_rows.append(dict(episode=e['episode'], steps=last['t'], treasures=last['collected'],
                                 captured=last['captured'], completed=last['completed'], score=last['score'],
                                 map=last['map'], mode=last['mode']))
    # Every stored evaluation is independently reconstructed from actual terminal rows.
    by = collections.defaultdict(list)
    for e, r in zip(episode_events, episode_rows):
        by[e['phase']].append(r)
    offsets = collections.Counter()
    def take(kind, n):
        start = offsets[kind]
        rows = by[kind][start:start+n]
        offsets[kind] += n
        assert len(rows) == n
        return rows
    optimizers = [e for e in events if e['kind'] == 'optimizer']
    assert len(optimizers) == job['optimizer_updates']
    reports = []
    branch_differences = []
    preference_changes = []
    history = []
    previous_deployed = job['source_parameter_hash']
    for cycle, row in enumerate(job['cycles']):
        assert cycle == row['cycle'] and row['parent_hash'] == previous_deployed
        source_events = [(e, rs) for e, rs in zip(episode_events, rollouts)
                         if e['phase'] == 'source' and 1960000+cycle*100 <= e['episode'] < 1960008+cycle*100]
        assert len(source_events) == 8
        source_map = {e['episode']: rs for e, rs in source_events}
        eligible = []
        for e, rs in source_events:
            stationary = [r for r in rs[-8:] if r['before'] == r['hero']]
            if e['captured'] and e['steps'] <= 96 and stationary:
                eligible.append((e['episode'], stationary[0]['t']-1))
        interventions = [e for e in events if e['kind'] == 'intervention' and e['cycle'] == cycle]
        assert [(e['source_episode'], e['root_t']) for e in interventions] == eligible[:2]
        n_prefs = 0
        for e in interventions:
            rs = source_map[e['source_episode']]
            trials = [r for ev, r in zip(episode_events, rollouts)
                      if ev['phase'] == 'trial' and ev['episode'] == e['source_episode']]
            assert len(trials) == len(e['actions'])
            assert [t[0]['action'] for t in trials] == e['actions']
            assert [t[-1]['score'] for t in trials] == e['actual_scores']
            assert all(t[0]['t'] == e['root_t']+1 for t in trials)
            assert e['prefix_records_reused'] == e['root_t']
            assert e['original_reproduced'] and e['root_preserved']
            original = rs[e['root_t']:]
            assert len(original) == len(trials[0])
            for a, b in zip(original, trials[0]):
                for k in ('t', 'before', 'hero', 'monsters', 'action', 'pickup', 'captured', 'completed', 'score'):
                    assert a[k] == b[k]
            differences = [x-e['actual_scores'][0] for x in e['actual_scores'][1:]]
            branch_differences.extend(differences)
            if arm != 'RL-RP':
                n_prefs += sum(x != 0 for x in differences)
            assert e['preference_channel'] == (arm != 'RL-RP')
        assert row['cases']['cases'] == len(interventions)
        assert row['cases']['preferences'] == n_prefs and row['cases']['sources'] == 8
        assert row['cases']['source_scores'] == [rs[-1]['score'] for _, rs in source_events]
        reference_probe = take('reference_probe', 16)
        ref_probe_mean = mean(x['score'] for x in reference_probe)
        expected_order = 'weak'
        if cycle:
            prior = history[0]
            gains = {k: max(0, v-prior['reference']) for k, v in prior['children'].items()}
            expected_order = 'strong' if gains['strong'] > gains['weak'] else 'weak'
            assert row['dream']['replay_improvement'] == gains
        assert row['dream']['selected'] == expected_order
        assert row['dream']['available_trees'] == cycle
        expected_recipes = ['weak', 'strong'] if cycle == 0 else [expected_order, 'strong' if expected_order == 'weak' else 'weak']
        teachers = row['teachers']
        assert list(teachers) == expected_recipes[:len(teachers)]
        selected = None
        for name, t in teachers.items():
            eval_rows(t['probe'], take('teacher_probe', 16))
            assert t['fit']['parent_hash'] == row['parent_hash'] and t['fit']['updates'] == 16
            assert t['fit']['child_hash'] == t['probe']['parameter_hash']
            assert len(t['fit']['margins_before']) == n_prefs
            assert len(t['fit']['margins_after']) == n_prefs
            preference_changes.extend(b-a for a, b in zip(t['fit']['margins_before'], t['fit']['margins_after']))
            if t['probe']['mean'] > ref_probe_mean and (selected is None or t['probe']['mean'] > teachers[selected]['probe']['mean']):
                selected = name
        assert row['teacher_selected'] == selected
        if cycle == 0:
            assert len(teachers) == 2
        elif selected == expected_order:
            assert len(teachers) == 1
        else:
            assert len(teachers) == 2
        history.append(dict(reference=ref_probe_mean, children={k: v['probe']['mean'] for k, v in teachers.items()}))
        expected_fits = {'ordinary': row['reference_fit'], **{k: v['fit'] for k, v in teachers.items()}}
        if selected is not None:
            assert row['sleep']['parent_hash'] == row['reference_fit']['child_hash']
            assert row['matched_sleep_reference']['parent_hash'] == row['reference_fit']['child_hash']
            assert row['sleep']['updates'] == row['matched_sleep_reference']['updates'] == 16
            expected_fits['student'] = row['sleep']
            expected_fits['sleep_ordinary_reference'] = row['matched_sleep_reference']
            eval_rows(row['reference_gate'], take('reference_gate', 16))
            eval_rows(row['student_gate'], take('student_gate', 16))
            assert row['reference_gate']['parameter_hash'] == row['matched_sleep_reference']['child_hash']
            assert row['student_gate']['parameter_hash'] == row['sleep']['child_hash']
            expected_adopt = row['student_gate']['mean'] > row['reference_gate']['mean'] and row['student_gate']['captured'] <= row['reference_gate']['captured']
            assert row['student_adopted'] == expected_adopt
        else:
            assert not row['student_adopted'] and row['sleep'] is None and row['student_report'] is None
        fits = [e for e in events if e['kind'] == 'fit' and e['cycle'] == cycle]
        assert len(fits) == len(expected_fits)
        for e in fits:
            fr = expected_fits[e['role']]
            assert fr == {k: e[k] for k in fr}
            os = [o for o in optimizers if o['cycle'] == cycle and o['role'] == e['role']]
            assert [o['step'] for o in os] == list(range(fr['updates']))
            for o in os:
                assert o['arm'] == arm
                assert o['preferences'] == (n_prefs if arm != 'RL-RP' and e['role'] in ('weak', 'strong') else 0)
                if e['role'] != 'student':
                    assert o['behavior_kl'] == 0
                if arm == 'RL-RP':
                    assert o['preference_loss'] == 0
        adopt_event = next(e for e in events if e['kind'] == 'adopt' and e['cycle'] == cycle)
        previous_deployed = adopt_event['deployed_hash']
        assert previous_deployed == (row['sleep']['child_hash'] if row['student_adopted'] else (row['matched_sleep_reference'] or row['reference_fit'])['child_hash'])
        event_index = events.index(adopt_event)
        report_index = next(i for i, e in enumerate(events) if e['kind'] == 'episode' and e['phase'] == 'reference_report' and e['episode'] == 4096+cycle*64)
        assert event_index < report_index
        eval_rows(row['reference_report'], take('reference_report', 64))
        assert row['reference_report']['parameter_hash'] == adopt_event['reference_hash']
        if selected is not None:
            eval_rows(row['teacher_report'], take('teacher_report', 64))
            assert row['teacher_report']['parameter_hash'] == teachers[selected]['fit']['child_hash']
            eval_rows(row['student_report'], take('deployed_report' if row['student_adopted'] else 'rejected_student_report', 64))
            assert row['student_report']['parameter_hash'] == row['sleep']['child_hash']
        if row['student_adopted']:
            assert row['deployed_report'] == row['student_report']
        else:
            assert row['deployed_report'] == dict(row['reference_report'], shared_exact_reference=True)
        report = dict(seed=seed, arm=arm, cycle=cycle, cases=len(interventions), preferences=n_prefs,
                      reference=row['reference_report']['mean'], deployed=row['deployed_report']['mean'],
                      selected=selected, adopted=row['student_adopted'],
                      teacher=None if selected is None else row['teacher_report']['mean'],
                      student=None if selected is None else row['student_report']['mean'],
                      dream_order=expected_order, candidates=len(teachers))
        report['deployed_gain'] = report['deployed']-report['reference']
        for name in ('teacher', 'student'):
            report[name+'_gain'] = None if report[name] is None else report[name]-report['reference']
        report['consolidation_loss'] = None if selected is None else report['teacher']-report['student']
        if selected is not None:
            assert report['student_gain'] == report['teacher_gain']-report['consolidation_loss']
            report['gate_gain'] = row['student_gate']['mean']-row['reference_gate']['mean']
        report['scope'] = {}
        for scope, parity in (('seen', 0), ('heldout', 1)):
            vals = {name: mean(r['score'] for r in row[name+'_report']['rows'] if r['episode'] % 2 == parity)
                    for name in ('reference', 'deployed')}
            vals['gain'] = vals['deployed']-vals['reference']
            report['scope'][scope] = vals
        reports.append(report)
    for kind, start in offsets.items():
        assert start == len(by[kind]), (kind, start, len(by[kind]))
    return dict(seed=seed, arm=arm, raw_rows=raw_count, events=len(events), rollouts=len(rollouts),
                optimizer_updates=len(optimizers), step_counts=dict(counts), decisions=reports,
                branch_differences=describe(branch_differences), preference_margin_changes=describe(preference_changes))


def main():
    out = HERE/'analysis'
    out.mkdir(exist_ok=False)
    write(out/'review_claim.json', dict(started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                      reviewer_sha256=sha(__file__), scope='Stored consistency and accounting only, zero rollout/optimizer calls'))
    result = {}
    try:
        summary, native = read(HERE/'evidence/summary.json'), read(HERE/'native_exit.json')
        assert native['exit_code'] == 0 and native['interruption'] is None
        assert summary['status'] == 'COMPLETE' and summary['jobs'] == 16 and summary['changed_inputs'] == []
        pins = read(HERE/'evidence/claim.json')['inputs']
        changed = [p for p, h in pins.items() if sha(ROOT/p) != h]
        assert not changed, changed
        jobs = [audit_job(j) for j in sorted(summary['results'], key=lambda j: (j['seed'], ARMS.index(j['arm'])))]
        for key, sourcekey in (('environment_steps', 'raw_rows'), ('actual_rollouts', 'rollouts'), ('optimizer_updates', 'optimizer_updates')):
            assert summary[key] == sum(j[sourcekey] for j in jobs)
        decisions = [d for j in jobs for d in j['decisions']]
        groups = []
        for cycle in (0, 1):
            for arm in ARMS:
                ds = [d for d in decisions if d['cycle'] == cycle and d['arm'] == arm]
                groups.append(dict(arm=arm, cycle=cycle, seeds=len(ds),
                                   ordinary_reference=mean(d['reference'] for d in ds),
                                   deployed=mean(d['deployed'] for d in ds),
                                   deployed_gain=describe([d['deployed_gain'] for d in ds]),
                                   eligible_teachers=sum(d['selected'] is not None for d in ds),
                                   adopted=sum(d['adopted'] for d in ds),
                                   seen_gain=mean(d['scope']['seen']['gain'] for d in ds),
                                   heldout_gain=mean(d['scope']['heldout']['gain'] for d in ds)))
        eligible = [d for d in decisions if d['selected'] is not None]
        adopted = [d for d in decisions if d['adopted']]
        files = [p for p in (HERE/'evidence').rglob('*') if p.is_file()]
        artifacts = [dict(path=p.relative_to(ROOT).as_posix(), bytes=p.stat().st_size, sha256=sha(p)) for p in files]
        budget = read(HERE/'contract.json')['budget']
        assert summary['environment_steps'] <= budget['max_environment_steps']
        assert native['wall_seconds'] <= budget['wall_seconds'] and native['peak_tree_rss'] <= budget['ram_bytes']
        assert sum(x['bytes'] for x in artifacts) <= budget['artifact_bytes']
        result = dict(status='PASS_STORED_CONSISTENCY', native=native, inputs_checked=len(pins), changed_inputs=changed,
                      jobs=jobs, groups=groups, decisions=decisions,
                      totals={k: summary[k] for k in ('environment_steps', 'actual_rollouts', 'optimizer_updates')},
                      total_events=sum(j['events'] for j in jobs),
                      diagnosis=dict(cycles=len(decisions), eligible_teachers=len(eligible), adopted=len(adopted),
                          teachers_positive_report=sum(d['teacher_gain'] > 0 for d in eligible),
                          students_positive_report=sum(d['student_gain'] > 0 for d in eligible),
                          adopted_positive_report=sum(d['student_gain'] > 0 for d in adopted),
                          adopted_negative_report=sum(d['student_gain'] < 0 for d in adopted),
                          rejected_positive_report=sum(d['student_gain'] > 0 for d in eligible if not d['adopted']),
                          teacher_positive_student_nonpositive=sum(d['teacher_gain'] > 0 and d['student_gain'] <= 0 for d in eligible),
                          dream_order_changes=sum(d['cycle'] == 1 and d['dream_order'] != 'weak' for d in decisions)),
                      artifact_bytes=sum(x['bytes'] for x in artifacts), artifacts=artifacts,
                      limitations=['Not a kernel re-execution or independent scientific gate.',
                                   'Four existing seeds; cycle1 ordinary references inherit the prior deployed parent.',
                                   'Shared Sleep data/update counts do not equalize total search and validation resources.',
                                   'F0 has no reward packet/Q, but receives goal-conditioned action preferences and task-score selection.',
                                   'Actual intervention alternatives are fixed externally, not autonomous causal explanation.'])
    except BaseException:
        result = dict(status='ERROR_STORED_REVIEW', error=traceback.format_exc())
    write(out/'result.json', result)
    print(json.dumps({k: v for k, v in result.items() if k in ('status', 'error', 'totals', 'diagnosis', 'groups')}, ensure_ascii=False))
    return 0 if result['status'] == 'PASS_STORED_CONSISTENCY' else 1


if __name__ == '__main__':
    raise SystemExit(main())
