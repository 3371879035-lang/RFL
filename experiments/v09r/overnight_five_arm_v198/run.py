"""Five genuinely separate longitudinal learners under common charged budgets.

RL-plain never calls collect_cases, fit, dream_order, or a teacher. Every other
group charges all outer trials, development rollouts and rejected updates.
"""
import argparse
import concurrent.futures as cf
import copy
import datetime
import gzip
import hashlib
import json
import os
import subprocess
import sys
import time
import traceback
from collections import Counter, deque
from pathlib import Path

import components as C
import numpy as np
import torch
from learning import Agent
from world import MapBank, World, rng_for

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BANK = None


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def write(path, value, replace=False):
    path = Path(path)
    if replace:
        temp = path.with_name(path.name+'.tmp')
        with temp.open('w', encoding='utf-8', newline='\n') as f:
            json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write('\n')
        os.replace(temp, path)
    else:
        with path.open('x', encoding='utf-8', newline='\n') as f:
            json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write('\n')


def load(path):
    with gzip.open(path, 'rb') as f:
        return torch.load(f, map_location='cpu', weights_only=False)


def worker_init():
    global BANK
    BANK = MapBank(ROOT/'experiments/v09r/spatial_feedback_v178/evidence_prepare/maps')


class Capture:
    def __init__(self, directory, block, quota, optimizer_quota):
        self.raw = gzip.open(directory/'raw.jsonl.gz', 'xt', encoding='utf-8', compresslevel=1)
        self.events = gzip.open(directory/'events.jsonl.gz', 'xt', encoding='utf-8', compresslevel=1)
        self.block, self.quota, self.optimizer_quota = block, quota, optimizer_quota
        self.steps = self.charged = self.episodes = self.optimizers = 0
        self.partial_segments = 0
        self.counts = Counter()
        self.update_roles = Counter()
        self.event_kinds = Counter()
        self.data = []

    def event(self, kind, **kw):
        self.event_kinds[kind] += 1
        if kind == 'optimizer':
            self.update_roles[kw['role']] += kw.get('updates', 1)
        self.events.write(json.dumps(dict(kind=kind, **kw), separators=(',', ':'), allow_nan=False)+'\n')

    def check_step(self, kind):
        if 'report' not in kind and self.charged >= self.quota:
            raise RuntimeError('Charged environment budget exhausted before a required stage')

    def step(self, kind, episode, world, before, action, proposed, fact, agent):
        self.steps += 1
        self.charged += int('report' not in kind)
        self.counts[kind] += 1
        reward = None if agent.arm == 'F0' else .015+fact.pickup-agent.penalty*fact.captured
        uid = f'{self.block}:{self.steps}'
        row = dict(id=self.steps, uid=uid, rollout=self.episodes, kind=kind, episode=episode,
                   map=world.map_id, mode=world.mode, t=world.t, before=list(before),
                   hero=world.hero.tolist(), monsters=world.monsters.tolist(),
                   action=int(action), proposed=int(proposed), pickup=int(fact.pickup),
                   captured=bool(fact.captured), completed=bool(fact.completed),
                   collected=world.collected, score=1.5*world.t+100*world.collected, reward=reward)
        self.raw.write(json.dumps(row, separators=(',', ':'))+'\n')
        return uid, reward

    def close(self):
        self.raw.close()
        self.events.close()


def pack_world(world):
    if world is None:
        return None
    fixed = {'roads', 'index', 'coords', 'neighbor', 'distances'}
    return {k: v for k, v in vars(world).items() if k not in fixed}


def restore_world(state):
    if state is None:
        return None
    world = World.__new__(World)
    world.__dict__.update(state)
    for k in ('roads', 'index', 'coords', 'neighbor', 'distances'):
        setattr(world, k, BANK.maps[world.map_id][k])
    return world


def practice(state, cap, requested, finish_episode=False):
    agent = state['agent']
    world = restore_world(state['world'])
    done_steps = 0
    begin_t = world.t if world is not None else 0
    while done_steps < requested or (finish_episode and world is not None):
        if world is None:
            episode = state['next_episode']
            state['next_episode'] += 1
            state['ordinary_episode'] = episode
            agent.reset_episode('train', episode)
            world = World(BANK, agent.seed, 'train', episode)
            begin_t = 0
        episode = state['ordinary_episode']
        cap.check_step('ordinary')
        obs = world.observe()
        action = agent.act(obs, True)
        nxt, fact = world.step(action)
        _, reward = cap.step('ordinary', episode, world, tuple(obs.hero), action, action, fact, agent)
        before = agent.counters['v191_optimizer_updates']
        agent.suppress_auto_learning = cap.optimizers >= cap.optimizer_quota
        agent.observe(nxt, fact, reward)
        agent.label_events.clear()
        updates = agent.counters['v191_optimizer_updates']-before
        cap.optimizers += updates
        if updates:
            cap.event('optimizer', role='ordinary_online', updates=updates,
                      training_steps=agent.training_steps, total_loss=agent.last_loss,
                      preference_loss=0., behavior_kl=0.)
        done_steps += 1
        if world.done:
            cap.event('episode', rollout=cap.episodes, phase='ordinary', episode=episode,
                      begin_t=begin_t, steps=world.t, new_steps=world.t-begin_t,
                      score=1.5*world.t+100*world.collected, treasures=world.collected,
                      captured=bool(fact.captured), completed=bool(fact.completed))
            cap.episodes += 1
            world = None
    if world is not None and done_steps:
        cap.event('ordinary_partial', rollout=cap.episodes, episode=state['ordinary_episode'], begin_t=begin_t,
                  t=world.t, new_steps=world.t-begin_t, terminal=False)
        cap.episodes += 1
        cap.partial_segments += 1
    state['world'] = pack_world(world)
    assert cap.optimizers <= cap.optimizer_quota


def historical_action(history, key, legal, original):
    # Actual previous intervention contexts, not imagined successor scores.
    ranked = sorted(((float(np.mean(np.abs(np.asarray(r['key'])-key))), r) for r in history),
                    key=lambda x: x[0])[:8]
    weighted, weights = Counter(), Counter()
    for distance, item in ranked:
        weight = 1/(1+distance)
        for comparison in item['comparisons']:
            if not comparison['supported']:
                continue
            action = comparison['action'] if comparison['mean'] > 0 else item['original_action']
            if action == original or not legal[action]:
                continue
            weighted[action] += weight*abs(comparison['mean'])
            weights[action] += weight
    estimates = {a: weighted[a]/weights[a] for a in weighted}
    selected = max(sorted(estimates), key=lambda a: estimates[a]) if estimates else None
    return selected, dict(available_history=len(history), neighbors=[dict(case_id=r['case_id'], distance=d) for d, r in ranked],
                         historical_advantage_hints=estimates, proposed_action=selected,
                         interpretation='A hypothesis for a new actual trial, not a causal probability or adopted action rule')


def collect_cases(agent, cap, block, cfg, history):
    traces, cases, prefs = [], [], []
    history_queries = history_suggestions = 0
    for i in range(cfg['sources']):
        episode = 8100000+block*100+i
        a, world, obs = C.new_episode(agent, BANK, 'train', episode)
        tr, snapshots = C.rollout(a, world, obs, cap, 'source', episode, True, snapshots=True)
        traces.append(tr)
        eligible = [s for s in snapshots if tr['records'][s['index']]['stationary']]
        if len(cases) < cfg['max_cases'] and tr['captured'] and tr['steps'] <= 96 and eligible:
            snap = eligible[0]
            snap['source'] = tr
            cases.append(snap)
    for ci, snap in enumerate(cases):
        root, source = snap['world'], snap['source']
        root_hash = C.world_hash(root)
        original = source['records'][snap['index']]['action']
        legal = root.observe().legal
        root_record = source['records'][snap['index']]
        key = np.r_[root_record['scalar'][2:28], root_record['image'][:, 8:13, 8:13].reshape(-1)].astype(np.float32)
        proposed, memory = historical_action(history, key, legal, original)
        history_queries += 1
        history_suggestions += int(proposed is not None)
        cap.event('history_proposal', block=block, case=ci, **memory)
        candidates = ([proposed] if proposed is not None else [])+[(original % 8+2) % 8, (original % 8-2) % 8]
        alternatives = [a for a in dict.fromkeys(candidates) if a != original and legal[a]][:2]
        actions = [original]+alternatives
        outcomes = []
        for replicate in range(cfg['replicates']):
            environment_uniform = root.uniform.copy()
            action_uniform = snap['actor'].action_uniform.copy()
            if replicate:
                rr = rng_for(agent.seed, 'v198-real-continuation', block, ci, replicate)
                environment_uniform[root.t:] = rr.random(environment_uniform[root.t:].shape)
                action_uniform[root.t:] = rr.random(action_uniform[root.t:].shape)
            scores = []
            for action in actions:
                world = C.world_clone(root)
                world.uniform = environment_uniform.copy()
                actor = C.tiny_clone(snap['actor'])
                actor.action_uniform = action_uniform.copy()
                tr, _ = C.rollout(actor, world, world.observe(), cap, 'trial', source['episode'],
                                  True, action, snap['prefix'])
                traces.append(tr)
                scores.append(tr['score'])
                if replicate == 0 and action == original:
                    left, right = source['records'][snap['index']:], tr['records'][snap['index']:]
                    assert len(left) == len(right)
                    assert all(x['action'] == y['action'] and x['captured'] == y['captured'] and
                               x['pickup'] == y['pickup'] and np.array_equal(x['next_image'], y['next_image'])
                               for x, y in zip(left, right)), 'Original source continuation not reproduced'
                assert C.world_hash(root) == root_hash
            outcomes.append(scores)
        accepted = []
        images = np.stack([r['image'] for r in source['records'][:snap['index']+1]])
        scalars = np.stack([r['scalar'] for r in source['records'][:snap['index']+1]])
        for j in range(1, len(actions)):
            ds = [x[j]-x[0] for x in outcomes]
            avg = float(np.mean(ds))
            agreeing = sum(x > 0 for x in ds) if avg > 0 else sum(x < 0 for x in ds)
            supported = avg != 0 and agreeing >= cfg['replicates']//2+1
            accepted.append(dict(action=actions[j], paired_effects=ds, mean=avg, supported=supported))
            if supported and agent.arm != 'RL-RP':
                pos, neg = (actions[j], original) if avg > 0 else (original, actions[j])
                prefs.append(dict(images=images, scalars=scalars, positive=pos, negative=neg,
                                  case=ci, difference=avg))
        cap.event('intervention', block=block, case=ci, source_episode=source['episode'],
                  root_t=root.t, root_hash=root_hash, actions=actions, actual_scores=outcomes,
                  comparisons=accepted, original_reproduced=True, root_preserved=True,
                  preference_channel=agent.arm != 'RL-RP')
        history.append(dict(case_id=f'{block}:{ci}', key=key, original_action=original,
                            actions=actions, comparisons=accepted, real_scores=outcomes,
                            source_episode=source['episode'], root_t=root.t))
    cap.data.extend(traces)
    return traces, prefs, dict(cases=len(cases), preferences=len(prefs),
                              history_queries=history_queries, history_suggestions=history_suggestions,
                              historical_cases_retained=len(history))


def outer_round(state, cap, block, cfg):
    parent = state['agent']
    parent_hash = C.nh(parent.net)
    traces, prefs, case_report = collect_cases(parent, cap, block, cfg, state['interventions'])
    state['data'].extend(traces)
    data = list(state['data'])
    nfit = cfg['fit_updates']
    assert cap.optimizers+5*nfit <= cap.optimizer_quota
    reference, reference_fit = C.fit(parent, data, [], nfit, 1., cap, block, 'ordinary')
    if case_report['cases'] == 0:
        order, dream = C.dream_order(state['history'], state['order'])
        state['order'] = order
        dream['skipped_reason'] = 'No qualifying failure; continue ordinary learning, no diagnostic teacher or Sleep.'
        cap.event('dream', block=block, **dream)
        state['history'].append(dict(parent_hash=parent_hash, reference_mean=None, children={}))
        state['agent'] = reference
        row = dict(cases=case_report, reference_fit=reference_fit, reference_probe=None,
                   dream=dream, teachers={}, teacher_selected=None, sleep=None, matched_reference=None,
                   reference_gate=None, student_gate=None, two_block_gains=[], adopted=False,
                   parent_hash=parent_hash, deployed_hash=C.nh(reference.net))
        cap.event('adopt', block=block, **row)
        return row
    ep = 198000+block*256
    ref_probe = C.evaluate(reference, BANK, cap, 'v198-probe', ep, cfg['probe_episodes'], 'reference_probe')
    order, dream = C.dream_order(state['history'], state['order'])
    state['order'] = order
    cap.event('dream', block=block, **dream)
    names = ['weak', 'strong'] if block == 1 else [order, 'strong' if order == 'weak' else 'weak']
    teachers, children, selected = {}, {}, None
    for name in names:
        teacher, fit = C.fit(parent, data, prefs, nfit, {'weak': .25, 'strong': 1.}[name], cap, block, name)
        probe = C.evaluate(teacher, BANK, cap, 'v198-probe', ep, cfg['probe_episodes'], 'teacher_probe')
        teachers[name], children[name] = teacher, dict(probe=probe, fit=fit)
        if probe['mean'] > ref_probe['mean'] and (selected is None or probe['mean'] > children[selected]['probe']['mean']):
            selected = name
        if block != 1 and selected is not None:
            break
    state['history'].append(dict(parent_hash=parent_hash, reference_mean=ref_probe['mean'],
                                children={k: dict(mean=v['probe']['mean'], hash=v['probe']['parameter_hash']) for k, v in children.items()}))
    student = None
    gate_reference = gate_student = sleep_fit = matched_fit = None
    adopted, block_gains = False, []
    if selected is not None:
        teacher = teachers[selected]
        wake = []
        for j in range(cfg['wake_episodes']):
            wake_ep = 9100000+block*100+j
            a, world, obs = C.new_episode(reference, BANK, 'train', wake_ep)
            tr, _ = C.rollout(a, world, obs, cap, 'student_wake', wake_ep, True, shadow=teacher)
            wake.append(tr)
        cap.data.extend(wake)
        state['data'].extend(wake)
        student, sleep_fit = C.fit(reference, wake, [], nfit, 1., cap, block, 'student', kd=True)
        reference, matched_fit = C.fit(reference, wake, [], nfit, 1., cap, block, 'sleep_ordinary_reference')
        gate_reference = C.evaluate(reference, BANK, cap, 'v198-gate', ep, cfg['gate_episodes'], 'reference_gate')
        gate_student = C.evaluate(student, BANK, cap, 'v198-gate', ep, cfg['gate_episodes'], 'student_gate')
        half = cfg['gate_episodes']//2
        for begin in (0, half):
            block_gains.append(float(np.mean([s['score']-r['score'] for s, r in
                zip(gate_student['rows'][begin:begin+half], gate_reference['rows'][begin:begin+half])])))
        adopted = all(x > 0 for x in block_gains) and gate_student['captured'] <= gate_reference['captured']
    assert C.nh(parent.net) == parent_hash
    state['agent'] = student if adopted else reference
    state['agent'].suppress_auto_learning = False
    row = dict(cases=case_report, reference_fit=reference_fit, reference_probe=ref_probe,
               dream=dream, teachers=children, teacher_selected=selected, sleep=sleep_fit,
               matched_reference=matched_fit, reference_gate=gate_reference, student_gate=gate_student,
               two_block_gains=block_gains, adopted=adopted, parent_hash=parent_hash,
               deployed_hash=C.nh(state['agent'].net))
    cap.event('adopt', block=block, **row)
    return row


def initial_state(binding):
    source = ROOT/binding['path']
    assert C.sha(source) == binding['sha256']
    obj = load(source)
    agent = obj['agent']
    assert isinstance(agent, Agent) and agent.training_steps == 147456
    agent.configure_v198(binding['group'])
    agent._v196_extra = None
    agent.label_events = []
    agent.suppress_auto_learning = False
    provenance = dict(source=binding, original_partial_t=obj['world'].t, original_partial_done=obj['world'].done)
    return dict(agent=agent, world=None, next_episode=7100000, ordinary_episode=None,
                data=deque(maxlen=128), interventions=deque(maxlen=128), history=[], order='weak', completed_blocks=0,
                charged_environment_total=0, optimizer_total=0, provenance=provenance)


def run_task(binding, folder, stage, block, cfg, input_path=None):
    start, cpu = time.perf_counter(), time.process_time()
    directory = Path(folder)/f"seed{binding['seed']}"/binding['group']/stage
    directory.mkdir(parents=True, exist_ok=False)
    cap = Capture(directory, block, cfg['charged_steps'] if stage.startswith('block') else 0,
                  cfg['optimizer_steps'] if stage.startswith('block') else 0)
    result = dict(seed=binding['seed'], group=binding['group'], arm=binding['arm'], block=block,
                  stage=stage, status='RUNNING', started_utc=now())
    try:
        state = initial_state(binding) if input_path is None else load(input_path)
        result['input_hash'] = binding['sha256'] if input_path is None else C.sha(input_path)
        result['initial_parameter_hash'] = C.nh(state['agent'].net)
        report = None
        if stage == 'initial':
            report = C.evaluate(state['agent'], BANK, cap, 'v198-report-fixed', 19800000,
                                cfg['initial_report'], 'initial_report')
        elif stage == 'final':
            report = C.evaluate(state['agent'], BANK, cap, 'v198-report-final', 19810000,
                                cfg['final_report'], 'final_report')
        else:
            assert state['completed_blocks'] == block-1
            if binding['group'] == 'RL-plain':
                assert state['agent'].arm == 'RL-RP' and not state['agent'].factual
                assert state['agent']._v196_extra is None and state['agent']._sleep_teacher is None
                assert len(state['history']) == len(state['data']) == len(state['interventions']) == 0
                practice(state, cap, cfg['charged_steps'])
                result['outer'] = None
            else:
                practice(state, cap, cfg['warm_steps'], finish_episode=True)
                assert state['world'] is None
                result['outer'] = outer_round(state, cap, block, cfg)
                practice(state, cap, cfg['charged_steps']-cap.charged)
            while cap.optimizers < cap.optimizer_quota:
                state['agent']._v196_extra = None
                state['agent'].learn()
                cap.optimizers += 1
                cap.event('optimizer', role='ordinary_budget_replay', updates=1,
                          total_loss=state['agent'].last_loss, preference_loss=0., behavior_kl=0.)
            assert cap.charged == cfg['charged_steps'] and cap.optimizers == cfg['optimizer_steps']
            state['completed_blocks'] = block
            state['charged_environment_total'] += cap.charged
            state['optimizer_total'] += cap.optimizers
            if block in cfg['report_blocks']:
                report = C.evaluate(state['agent'], BANK, cap, 'v198-report-fixed', 19800000,
                                    cfg['interim_report'], 'interim_report')
        result['report'] = report
        result['parameter_hash'] = C.nh(state['agent'].net)
        result['ordinary_training_steps_total'] = state['agent'].training_steps-147456
        result['charged_environment_total'] = state['charged_environment_total']
        result['optimizer_total'] = state['optimizer_total']
        result['replay_records'] = state['agent'].replay.n
        assert cap.optimizers == sum(cap.update_roles.values())
        if stage.startswith('block'):
            if binding['group'] == 'RL-plain':
                assert not (set(cap.update_roles)-{'ordinary_online', 'ordinary_budget_replay'})
                assert not (set(cap.counts)-{'ordinary', 'interim_report'})
                assert cap.event_kinds['intervention'] == cap.event_kinds['adopt'] == 0
            else:
                assert cap.event_kinds['adopt'] == cap.event_kinds['dream'] == 1
                assert len(state['history']) == block
                if result['outer']['teacher_selected'] is not None:
                    assert cap.update_roles['student'] == cap.update_roles['sleep_ordinary_reference'] == cfg['fit_updates']
                    assert result['outer']['student_gate'] is not None and result['outer']['reference_gate'] is not None
        if stage != 'final':
            checkpoint = directory/'checkpoint.pt.gz'
            C.save(checkpoint, state)
            result['checkpoint'] = str(checkpoint)
            result['checkpoint_sha256'] = C.sha(checkpoint)
        if cap.data:
            C.save(directory/'diagnostic_data.pt.gz', cap.data)
        result['status'] = 'COMPLETE'
    except BaseException:
        result['status'] = 'ERROR_PARTIAL'
        result['error'] = traceback.format_exc()
    finally:
        result.update(environment_steps=cap.steps, charged_environment_steps=cap.charged,
                      step_counts=dict(cap.counts), complete_rollout_segments=cap.episodes-cap.partial_segments,
                      rollout_segments=cap.episodes, partial_segments=cap.partial_segments,
                      optimizer_roles=dict(cap.update_roles), mechanism_events=dict(cap.event_kinds),
                      optimizer_updates=cap.optimizers, wall_seconds=time.perf_counter()-start,
                      cpu_seconds=time.process_time()-cpu, finished_utc=now())
        cap.close()
        write(directory/'result.json', result)
    return result


def config(mode):
    if mode == 'smoke':
        return dict(charged_steps=16384, optimizer_steps=128, warm_steps=512,
                    sources=2, max_cases=1, replicates=2, probe_episodes=4, wake_episodes=2,
                    gate_episodes=4, fit_updates=8, initial_report=8, interim_report=8,
                    final_report=8, report_blocks=[1, 2], max_blocks=2, wall_seconds=900, reserve=60)
    return dict(charged_steps=131072, optimizer_steps=1024, warm_steps=32768,
                sources=8, max_cases=2, replicates=3, probe_episodes=64, wake_episodes=8,
                gate_episodes=64, fit_updates=32, initial_report=128, interim_report=128,
                final_report=512, report_blocks=[1, 2, 4, 8, 16, 32, 64, 128, 256], max_blocks=256,
                wall_seconds=43200, reserve=900)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['smoke', 'long'], required=True)
    args = parser.parse_args()
    cfg = config(args.mode)
    out = HERE/f'evidence_{args.mode}'
    out.mkdir(exist_ok=False)
    bindings = json.loads((HERE/'checkpoint_binding.json').read_text())['files']
    if args.mode == 'smoke':
        bindings = [b for b in bindings if b['seed'] == 93002]
    pins = {p.relative_to(ROOT).as_posix(): C.sha(p) for p in HERE.iterdir() if p.suffix in ('.py', '.json')}
    for b in bindings+json.loads((HERE/'map_binding.json').read_text())['files']:
        assert C.sha(ROOT/b['path']) == b['sha256']
        pins[b['path']] = b['sha256']
    write(out/'claim.json', dict(started_utc=now(), mode=args.mode, config=cfg, inputs=pins,
                               git_head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()))
    started = time.perf_counter()
    records, paths = [], {}
    common = 0
    last_block_wall = 0.
    failed = False
    with cf.ProcessPoolExecutor(max_workers=min(8, len(bindings)), initializer=worker_init) as pool:
        def stage(name, block):
            nonlocal failed
            stage_started = time.perf_counter()
            # Rotate submission order without inspecting outcomes.
            ordered = bindings[block % len(bindings):]+bindings[:block % len(bindings)]
            active = {pool.submit(run_task, b, str(out), name, block, cfg,
                                  paths.get((b['seed'], b['group']))): b for b in ordered}
            current = []
            for future in cf.as_completed(active):
                b = active[future]
                try:
                    row = future.result()
                except BaseException:
                    row = dict(seed=b['seed'], group=b['group'], stage=name, block=block,
                               status='WORKER_ERROR', error=traceback.format_exc())
                records.append(row)
                current.append(row)
                if row['status'] != 'COMPLETE':
                    failed = True
                print(json.dumps({k: row[k] for k in ('seed', 'group', 'stage', 'status')}), flush=True)
                write(out/'progress.json', dict(updated_utc=now(), last_common_block=common,
                      current_stage=name, completed_in_stage=len(current), jobs=len(bindings),
                      elapsed_seconds=time.perf_counter()-started, failed=failed), replace=True)
            if not failed and name != 'final':
                for row in current:
                    paths[(row['seed'], row['group'])] = row['checkpoint']
            write(out/f'{name}_receipt.json', dict(status='COMPLETE' if not failed else 'PARTIAL_OR_ERROR',
                  elapsed_seconds=time.perf_counter()-stage_started, jobs=current))
            return current, time.perf_counter()-stage_started
        initial, _ = stage('initial', 0)
        if not failed:
            for seed in {b['seed'] for b in bindings}:
                left = next(r for r in initial if r['seed'] == seed and r['group'] == 'RL-plain')
                right = next(r for r in initial if r['seed'] == seed and r['group'] == 'RL-outer')
                assert left['parameter_hash'] == right['parameter_hash'] and left['report'] == right['report']
        for block in range(1, cfg['max_blocks']+1):
            if failed:
                break
            remaining = cfg['wall_seconds']-(time.perf_counter()-started)
            if common and remaining < cfg['reserve']+1.3*last_block_wall:
                break
            rows, last_block_wall = stage(f'block{block:03}', block)
            if failed:
                break
            assert len({r['charged_environment_total'] for r in rows}) == 1
            assert len({r['optimizer_total'] for r in rows}) == 1
            common = block
            write(out/'last_common.json', dict(block=common, checkpoints=[dict(seed=s, group=g, path=p) for (s, g), p in paths.items()],
                  charged_per_job=common*cfg['charged_steps'], updates_per_job=common*cfg['optimizer_steps'], utc=now()), replace=True)
        if not failed:
            stage('final', common)
    changed = [p for p, h in pins.items() if C.sha(ROOT/p) != h]
    summary = dict(status='COMPLETE_BUDGETED_CONTINUATION' if not failed and not changed else 'PARTIAL_OR_ERROR',
                   mode=args.mode, completed_common_blocks=common, jobs=len(bindings),
                   wall_seconds=time.perf_counter()-started, changed_inputs=changed,
                   environment_steps=sum(r.get('environment_steps', 0) for r in records),
                   charged_environment_steps=sum(r.get('charged_environment_steps', 0) for r in records),
                   optimizer_updates=sum(r.get('optimizer_updates', 0) for r in records),
                   results=records, finished_utc=now())
    write(out/'summary.json', summary)
    print(json.dumps({k: v for k, v in summary.items() if k != 'results'}), flush=True)
    return 0 if summary['status'] == 'COMPLETE_BUDGETED_CONTINUATION' else 1


if __name__ == '__main__':
    raise SystemExit(main())
