"""Continue every V198 endpoint unchanged; no reinitialization or best-arm selection."""
import concurrent.futures as cf
import hashlib
import json
import subprocess
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PARENT = HERE.parent / 'overnight_five_arm_v198'
sys.path.insert(0, str(PARENT))
import run as V

GROUPS = ('RL-plain', 'RL-outer', 'F0', 'F-RP', 'F-R')
SEEDS = (93001, 93002, 93003, 93004)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def extension_config(base):
    cfg = V.config('long').copy()
    cfg.update(wall_seconds=21600, reserve=900,
               report_blocks=list(range(base+8, base+129, 8)))
    return cfg


def parent_binding():
    pe = PARENT / 'evidence_long'
    native = read(PARENT / 'native_long_exit.json')
    analysis_exit = read(PARENT / 'analysis_long_exit.json')
    analysis = read(pe / 'analysis.json')
    assert native['exit_code'] == 0 and native['interruption'] is None
    assert analysis_exit['exit_code'] == 0
    assert analysis['status'] == 'COMPLETED_LOCAL_CONTINUATION'
    last = read(pe / 'last_common.json')
    base = last['block']
    prior = read(pe / f'block{base:03d}_receipt.json')
    final = read(pe / 'final_receipt.json')
    assert prior['status'] == final['status'] == 'COMPLETE'
    expected = {(s, g) for s in SEEDS for g in GROUPS}
    assert {(r['seed'], r['group']) for r in prior['jobs']} == expected
    assert {(r['seed'], r['group']) for r in final['jobs']} == expected
    assert len(prior['jobs']) == len(final['jobs']) == 20
    files = []
    for r in sorted(prior['jobs'], key=lambda r: (r['seed'], GROUPS.index(r['group']))):
        f = next(x for x in final['jobs'] if (x['seed'], x['group']) == (r['seed'], r['group']))
        path = Path(r['checkpoint'])
        h = sha(path)
        assert r['status'] == f['status'] == 'COMPLETE'
        assert r['block'] == f['block'] == base
        assert h == r['checkpoint_sha256'] == f['input_hash']
        assert r['parameter_hash'] == f['initial_parameter_hash'] == f['parameter_hash']
        files.append(dict(seed=r['seed'], group=r['group'], arm=r['arm'],
                          path=path.relative_to(ROOT).as_posix(), sha256=h,
                          parameter_hash=r['parameter_hash'],
                          charged_environment_total=r['charged_environment_total'],
                          optimizer_total=r['optimizer_total'],
                          ordinary_training_steps_total=r['ordinary_training_steps_total'],
                          replay_records=r['replay_records'],
                          parent_final_report=f['report']))
    parent_files = [PARENT/'native_long_exit.json', PARENT/'analysis_long_exit.json',
                    pe/'analysis.json', pe/'last_common.json', pe/'final_receipt.json',
                    pe/f'block{base:03d}_receipt.json', pe/'claim.json']
    return dict(base_block=base, files=files,
                parent_result_pins={p.relative_to(ROOT).as_posix(): sha(p) for p in parent_files})


def resume_check(binding, base):
    """Read the full checkpoint once, without an action, forward pass or update."""
    path = ROOT / binding['path']
    assert sha(path) == binding['sha256']
    state = V.load(path)
    agent = state['agent']
    assert state['completed_blocks'] == base
    assert state['charged_environment_total'] == binding['charged_environment_total']
    assert state['optimizer_total'] == binding['optimizer_total']
    assert agent.training_steps-147456 == binding['ordinary_training_steps_total']
    assert agent.replay.n == binding['replay_records']
    assert agent.arm == binding['arm']
    assert V.C.nh(agent.net) == binding['parameter_hash']
    assert agent._v196_extra is None and agent._sleep_teacher is None
    assert len(state['history']) == (0 if binding['group'] == 'RL-plain' else base)
    if binding['group'] == 'RL-plain':
        assert not agent.factual and not state['data'] and not state['interventions']
    return dict(seed=binding['seed'], group=binding['group'], status='COMPLETE',
                checkpoint_sha256=binding['sha256'], parameter_hash=binding['parameter_hash'],
                completed_blocks=base, history_entries=len(state['history']),
                retained_interventions=len(state['interventions']),
                retained_diagnostic_traces=len(state['data']),
                replay_records=agent.replay.n, optimizer_state_entries=len(agent.optimizer.state),
                pending_episode_t=None if state['world'] is None else state['world']['t'],
                next_episode=state['next_episode'], state_keys=sorted(state),
                environment_steps=0, optimizer_updates=0)


def main():
    out = HERE / 'evidence'
    out.mkdir(exist_ok=False)
    binding = parent_binding()
    V.write(out/'source_binding.json', binding)
    base = binding['base_block']
    cfg = extension_config(base)
    pins = dict(read(PARENT/'evidence_long/claim.json')['inputs'])
    pins.update(binding['parent_result_pins'])
    for name in ('continue_run.py', 'finish_report.py', 'launch.py', 'contract.json',
                 'README.md', 'test_extension.py'):
        path = HERE/name
        pins[path.relative_to(ROOT).as_posix()] = sha(path)
    for b in binding['files']:
        pins[b['path']] = b['sha256']
    assert all(sha(ROOT/p) == h for p, h in pins.items())
    V.write(out/'claim.json', dict(started_utc=V.now(), base_block=base, config=cfg,
                                 inputs=pins, git_head=subprocess.check_output(
                                     ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                                 reuse='Unchanged V198 run_task, Agent, loss, trial and Sleep code.',
                                 evaluation='Same final reporting bank at 12h and extension endpoint; scores never select updates.'))
    started = time.perf_counter()
    records, common, failed = [], base, False
    paths = {(b['seed'], b['group']): str(ROOT/b['path']) for b in binding['files']}
    last_wall = 0.
    with cf.ProcessPoolExecutor(max_workers=8, initializer=V.worker_init) as pool:
        probes = list(pool.map(resume_check, binding['files'], [base]*20))
        V.write(out/'resume_receipt.json', dict(status='COMPLETE', jobs=probes,
                                               environment_steps=0, optimizer_updates=0))
        def stage(name, block):
            nonlocal failed
            t = time.perf_counter()
            bs = binding['files']
            ordered = bs[block % len(bs):]+bs[:block % len(bs)]
            active = {pool.submit(V.run_task, b, str(out), name, block, cfg,
                                  paths[(b['seed'], b['group'])]): b for b in ordered}
            rows = []
            for future in cf.as_completed(active):
                b = active[future]
                try:
                    r = future.result()
                except BaseException:
                    r = dict(seed=b['seed'], group=b['group'], stage=name, block=block,
                             status='WORKER_ERROR', error=traceback.format_exc())
                rows.append(r)
                records.append(r)
                failed = failed or r['status'] != 'COMPLETE'
                print(json.dumps({k: r[k] for k in ('seed', 'group', 'stage', 'status')}), flush=True)
                V.write(out/'progress.json', dict(updated_utc=V.now(), base_block=base,
                        last_common_block=common, additional_common_blocks=common-base,
                        current_stage=name, completed_in_stage=len(rows), jobs=20,
                        elapsed_seconds=time.perf_counter()-started, failed=failed), replace=True)
            if not failed and name != 'final':
                for r in rows:
                    paths[(r['seed'], r['group'])] = r['checkpoint']
            V.write(out/f'{name}_receipt.json', dict(status='COMPLETE' if not failed else 'PARTIAL_OR_ERROR',
                                                    elapsed_seconds=time.perf_counter()-t, jobs=rows))
            return rows, time.perf_counter()-t
        for block in range(base+1, base+cfg['max_blocks']+1):
            remaining = cfg['wall_seconds']-(time.perf_counter()-started)
            if failed or (common > base and remaining < cfg['reserve']+1.3*last_wall):
                break
            rows, last_wall = stage(f'block{block:03d}', block)
            if failed:
                break
            assert len({r['charged_environment_total'] for r in rows}) == 1
            assert len({r['optimizer_total'] for r in rows}) == 1
            common = block
            V.write(out/'last_common.json', dict(block=common, base_block=base,
                    additional_common_blocks=common-base,
                    additional_charged_per_job=(common-base)*cfg['charged_steps'],
                    additional_updates_per_job=(common-base)*cfg['optimizer_steps'],
                    checkpoints=[dict(seed=s, group=g, path=p) for (s, g), p in paths.items()],
                    utc=V.now()), replace=True)
        if not failed:
            stage('final', common)
    changed = [p for p, h in pins.items() if sha(ROOT/p) != h]
    summary = dict(status='COMPLETE_BUDGETED_EXTENSION' if not failed and not changed else 'PARTIAL_OR_ERROR',
                   base_block=base, completed_common_blocks=common, additional_common_blocks=common-base,
                   wall_seconds=time.perf_counter()-started, changed_inputs=changed,
                   environment_steps=sum(r.get('environment_steps', 0) for r in records),
                   charged_environment_steps=sum(r.get('charged_environment_steps', 0) for r in records),
                   optimizer_updates=sum(r.get('optimizer_updates', 0) for r in records),
                   results=records, finished_utc=V.now())
    V.write(out/'summary.json', summary)
    print(json.dumps({k: x for k, x in summary.items() if k != 'results'}), flush=True)
    return 0 if summary['status'] == 'COMPLETE_BUDGETED_EXTENSION' else 1


if __name__ == '__main__':
    raise SystemExit(main())
