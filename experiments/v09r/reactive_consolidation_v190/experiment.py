"""One small, authentic four-group continuation with a three-way F0 ablation."""
import concurrent.futures
import copy
import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import time
import traceback

os.environ['OMP_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'
import numpy as np
import psutil
import torch
from learning import Agent
from world import MapBank, World

torch.set_num_threads(1)
torch.set_num_interop_threads(1)
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DTYPE = np.dtype([
    ('kind','u1'),('checkpoint','<i4'),('episode','<i4'),('step','<u2'),('map','<i4'),('mode','u1'),
    ('before_hero','u1',(2,)),('hero','u1',(2,)),('monsters','<i2',(2,2)),
    ('cooldown','u1'),('buff','u1'),('context','<u2'),('action','u1'),('proposed','u1'),
    ('q_action','u1'),('full_action','u1'),('explore','u1'),('training_q_control','u1'),
    ('reason','u1'),('local_mask','<u2'),('memory_mask','<u2'),('streak_before','<u2'),
    ('pickup','u1'),('captured','u1'),('completed','u1'),('score','<f4'),('reward','<f4'),
    ('scores','<f4',(16,))])
LABEL_DTYPE = np.dtype([('uid','<i8'),('horizon','u1'),('observed_at','<i8'),
    ('steps','<u2'),('pickups','u1'),('terminal','u1'),('target_steps','<f4'),('target_pickups','<f4')])


def utc(): return datetime.datetime.now(datetime.timezone.utc).isoformat()


def write(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False); f.write('\n')


def filepin(path):
    return dict(path=path.relative_to(ROOT).as_posix(), bytes=path.stat().st_size,
                sha256=hashlib.file_digest(path.open('rb'), 'sha256').hexdigest())


def pins():
    return [filepin(p) for p in sorted(HERE.iterdir()) if p.suffix == '.py' or p.name in
            ('contract.json','checkpoint_binding.json','initial_evaluation_binding.json','map_binding.json','pure_check_result.json')]


class Binary:
    def __init__(self, path, dtype, header):
        self.file = gzip.open(path, 'xb', compresslevel=1)
        header = dict(header, dtype=dtype.descr)
        payload = json.dumps(header, sort_keys=True, separators=(',', ':')).encode()
        self.file.write(struct.pack('<I', len(payload)) + payload)
        self.buffer = np.zeros(4096, dtype)
        self.n = self.total = 0
        self.hash = hashlib.sha256()

    def add(self, value):
        self.buffer[self.n] = value
        self.n += 1; self.total += 1
        if self.n == len(self.buffer): self.flush()

    def flush(self):
        data = self.buffer[:self.n].tobytes()
        self.hash.update(data); self.file.write(data); self.n = 0

    def close(self):
        self.flush(); self.file.close()


def record(raw, agent, kind, checkpoint, episode, before, world, fact, reward):
    c = agent.last_choice
    raw.add((kind, checkpoint, episode, world.t, world.map_id, world.mode,
        before['hero'], world.hero, world.monsters, before['cooldown'], before['buff_left'],
        c['context'], c['action'], c['proposed'], c['old_action'], c['full_action'], c['explored'],
        c['training_q_control'], c['reason'], c['local_mask'], c['memory_mask'], c['streak_before'],
        fact.pickup, fact.captured, fact.completed, 1.5*world.t+100*world.collected,
        np.nan if reward is None else reward, agent.last_behavior_scores))


def save_checkpoint(path, agent, world, episode, obs):
    with gzip.open(path, 'xb', compresslevel=1) as f:
        torch.save(dict(schema='V190_FULL_CONTINUATION', agent=agent, world=world,
                        episode=episode, observation=obs), f)


def counters_delta(a, b): return {k: a[k]-b.get(k, 0) for k in a}


def evaluate(agent, bank, count, cp, raw, episodes):
    clone = agent.frozen()
    before = (clone.parameter_hash(), clone.feedback.digest(), clone.replay.n, clone.training_steps)
    counters = clone.counters.copy()
    rows = []
    for j in range(256, 256+count):
        world = World(bank, clone.seed, 'evaluation', j)
        obs = world.observe(); clone.reset_episode('evaluation', j)
        stationary = long_stall = responses = memory = moved_after = 0
        while not world.done:
            old = world.audit()
            action = clone.act(obs, False)
            nxt, fact = world.step(action)
            record(raw, clone, 1, cp, j, old, world, fact, None)
            clone.observe_frozen(nxt, fact)
            moved = tuple(obs.hero) != tuple(nxt.hero)
            stationary += int(not moved)
            long_stall += int(clone.feedback.streak >= 8)
            responses += int(clone.last_choice['reason'] != 0)
            memory += int(clone.last_choice['reason'] == 2)
            moved_after += int(clone.last_choice['reason'] != 0 and moved)
            obs = nxt
        row = dict(kind='evaluation', checkpoint=cp, episode=j, map=world.map_id, mode=world.mode,
            steps=world.t, treasures=world.collected, captured=bool(fact.captured),
            completed=bool(fact.completed), score=1.5*world.t+100*world.collected,
            stationary=stationary, long_stall=long_stall, corrections=responses,
            memory_corrections=memory, moved_after_correction=moved_after)
        rows.append(row); episodes.write(json.dumps(row, separators=(',', ':'))+'\n')
    assert before == (clone.parameter_hash(), clone.feedback.digest(), clone.replay.n, clone.training_steps)
    delta = counters_delta(clone.counters, counters)
    for k in ('Q_updates','fact_updates','measurement_updates','reward_packets'):
        assert delta.get(k, 0) == 0
    steps = sum(r['steps'] for r in rows)
    return dict(checkpoint=cp, episodes=count, steps=steps,
        mean_score=float(np.mean([r['score'] for r in rows])),
        mean_survival=float(np.mean([r['steps'] for r in rows])),
        mean_treasures=float(np.mean([r['treasures'] for r in rows])),
        stationary_rate=sum(r['stationary'] for r in rows)/steps,
        long_stall_rate=sum(r['long_stall'] for r in rows)/steps,
        corrections=sum(r['corrections'] for r in rows),
        memory_corrections=sum(r['memory_corrections'] for r in rows),
        moved_after_correction=sum(r['moved_after_correction'] for r in rows),
        parameters_persistent_memory_replay_frozen=True, memory=agent.feedback.summary(), counters=delta)


def run_case(spec):
    torch.use_deterministic_algorithms(True)
    seed, arm, variant, binding = spec
    directory = HERE/'evidence_pilot'/f'seed{seed}'/arm/variant
    directory.mkdir(parents=True, exist_ok=False)
    start, cpu = time.perf_counter(), time.process_time()
    inputs = pins()
    path = ROOT/binding['path']
    assert filepin(path) == {k: binding[k] for k in ('path','bytes','sha256')}
    with gzip.open(path, 'rb') as f:
        initial = torch.load(f, map_location='cpu', weights_only=False)
    agent = initial['agent']
    assert isinstance(agent, Agent) and agent.seed == seed and agent.arm == arm
    assert agent.training_steps == agent.replay.n == 131072
    old_partial = dict(episode=initial['episode'], steps=initial['world'].t,
                       terminal=initial['world'].done)
    del initial
    agent.attach_feedback(variant)
    agent.label_events = []
    initial_hash = agent.parameter_hash()
    recorded_path=HERE.parent/'reactive_consolidation_v189/evidence_pilot'/f'seed{seed}'/arm/variant/'result.json'
    recorded=json.loads(recorded_path.read_text())
    assert recorded['initial_parameter_hash']==initial_hash and recorded['initial_checkpoint']==binding
    assert len(recorded['evaluations'])==1 and recorded['evaluations'][0]['checkpoint']==0
    assert recorded['evaluations'][0]['episodes']==128 and recorded['evaluations'][0]['parameters_persistent_memory_replay_frozen']
    initial_evaluation=dict(recorded['evaluations'][0],recorded_transfer=True)
    counters = agent.counters.copy()
    bank = MapBank(HERE.parent/'spatial_feedback_v178/evidence_prepare/maps')
    raw = Binary(directory/'steps.bin.gz', DTYPE, dict(schema='V190_STEPS', seed=seed, arm=arm,
        variant=variant, checkpoint_source=binding, initial_parameter_hash=initial_hash))
    labels = Binary(directory/'labels.bin.gz', LABEL_DTYPE, dict(schema='V190_REAL_FUTURE_LABELS'))
    episodes = gzip.open(directory/'episodes.jsonl.gz','xt',encoding='utf-8',compresslevel=1)
    consolidations = gzip.open(directory/'consolidation.jsonl.gz','xt',encoding='utf-8',compresslevel=1)
    episode, world, obs, evaluations = 200000, None, None, [initial_evaluation]
    completed = sources = 0
    error = None
    try:
        for cp in (8192, 16384):
            while agent.training_steps < 131072+cp:
                if world is None or world.done:
                    world = World(bank, seed, 'train', episode)
                    agent.reset_episode('train', episode); obs = world.observe(); sources += 1
                before = world.audit()
                action = agent.act(obs, True)
                nxt, fact = world.step(action)
                reward = None if arm == 'F0' else .015+fact.pickup-agent.penalty*fact.captured
                record(raw, agent, 0, cp, episode, before, world, fact, reward)
                agent.observe(nxt, fact, reward)
                for row in agent.label_events: labels.add(row)
                agent.label_events.clear()
                if agent.feedback_event is not None:
                    consolidations.write(json.dumps(dict(episode=episode, global_step=agent.training_steps,
                        **agent.feedback_event), separators=(',', ':'))+'\n')
                obs = nxt
                if world.done:
                    completed += 1
                    episodes.write(json.dumps(dict(kind='training', episode=episode, steps=world.t,
                        global_step=agent.training_steps, map=world.map_id, mode=world.mode,
                        treasures=world.collected, captured=bool(fact.captured), completed=bool(fact.completed),
                        score=1.5*world.t+100*world.collected), separators=(',', ':'))+'\n')
                    episode += 1
                if agent.training_steps % 128 == 0 and (HERE/'evidence_pilot/STOP.json').exists():
                    raise RuntimeError('Pilot stop boundary; exact partial retained, no retry')
            evaluations.append(evaluate(agent, bank, 256 if cp == 16384 else 128, cp, raw, episodes))
        save_checkpoint(directory/'checkpoint_final.pt.gz', agent, world, episode, obs)
    except BaseException:
        error = traceback.format_exc()
        write(directory/'error.json', dict(utc=utc(), error=error, training_steps=agent.training_steps))
        save_checkpoint(directory/'error_boundary.pt.gz', agent, world, episode, obs)
    finally:
        raw.close(); labels.close(); episodes.close(); consolidations.close()
    assert pins() == inputs
    result = dict(status='COMPLETE' if error is None else 'ERROR_PARTIAL_RETAINED', seed=seed, arm=arm,
        variant=variant, error=error, utc=utc(), initial_parameter_hash=initial_hash,
        final_parameter_hash=agent.parameter_hash(), initial_checkpoint=binding,
        initial_evaluation_source=recorded_path.relative_to(ROOT).as_posix(),
        old_partial_preserved_not_completed=old_partial, additional_training_steps=agent.training_steps-131072,
        training_episodes_completed=completed, training_sources=sources,
        unfinished_new_episode_steps=world.t if world is not None and not world.done else 0,
        counters=counters_delta(agent.counters, counters), evaluations=evaluations,
        raw_records=raw.total, raw_payload_sha256=raw.hash.hexdigest(),
        labels=labels.total, label_payload_sha256=labels.hash.hexdigest(),
        memory=agent.feedback.summary(), parameters=sum(p.numel() for p in agent.net.parameters()),
        q_present=agent.net.q is not None, wall_seconds=time.perf_counter()-start,
        cpu_seconds=time.process_time()-cpu, inputs_unchanged=True)
    if error is None:
        assert result['additional_training_steps'] == 16384
        assert result['counters']['reward_packets'] == (0 if arm == 'F0' else 16384)
        assert result['counters']['Q_updates'] == (0 if arm == 'F0' else 128)
        assert result['counters']['fact_updates'] == (0 if arm == 'RL-RP' else 128)
        assert result['counters'].get('measurement_updates', 0) == (128 if arm == 'F0' else 0)
    write(directory/'memory_final.json', dict(counts=agent.feedback.counts, rules=agent.feedback.rules,
        completed=agent.feedback.completed, failures=agent.feedback.failures))
    write(directory/'result.json', result)
    return result


def main():
    output = HERE/'evidence_pilot'; output.mkdir(exist_ok=False)
    contract = json.loads((HERE/'contract.json').read_text(encoding='utf-8'))
    bindings = json.loads((HERE/'checkpoint_binding.json').read_text())['files']
    inputs = pins(); begin = time.perf_counter()
    specs = [(seed, arm, variant, next(p for p in bindings if p['seed']==seed and p['arm']==arm))
        for seed in contract['matrix']['seeds'] for arm, variants in contract['matrix']['cells'].items()
        for variant in variants]
    write(output/'claim.json', dict(utc=utc(), pid=os.getpid(), argv=sys.argv, cases=len(specs),
        workers=4, inputs=inputs, python=sys.version, torch=torch.__version__, numpy=np.__version__))
    results, error, peak_rss = [], None, 0
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
            remaining=iter(specs)
            pending = {pool.submit(run_case, next(remaining)) for _ in range(4)}
            while pending:
                finished, pending = concurrent.futures.wait(pending, timeout=5,
                    return_when=concurrent.futures.FIRST_COMPLETED)
                processes = [psutil.Process()]+psutil.Process().children(recursive=True)
                rss = sum(p.memory_info().rss for p in processes if p.is_running())
                peak_rss = max(peak_rss, rss)
                reason = None
                if rss > 20*1024**3: reason='20GiB RAM'
                if time.perf_counter()-begin > 3600: reason='3600 second pilot budget'
                if sum(p.stat().st_size for p in output.rglob('*') if p.is_file()) > 8*1024**3:
                    reason='8GiB artifact budget'
                for future in finished:
                    result = future.result(); results.append(result)
                    print(json.dumps(dict(completed=len(results), seed=result['seed'], arm=result['arm'],
                        variant=result['variant'], status=result['status'])), flush=True)
                    if result['status'] != 'COMPLETE': reason='Case error, no retry'
                if reason and not (output/'STOP.json').exists(): write(output/'STOP.json',dict(reason=reason,utc=utc()))
                if not (output/'STOP.json').exists():
                    for _ in finished:
                        spec=next(remaining,None)
                        if spec is not None: pending.add(pool.submit(run_case,spec))
        assert len(results) == 32 and all(r['status']=='COMPLETE' for r in results)
        assert not (output/'STOP.json').exists()
        assert pins() == inputs
        for pin in bindings + json.loads((HERE/'map_binding.json').read_text())['files'] + json.loads((HERE/'initial_evaluation_binding.json').read_text())['files']:
            assert filepin(ROOT/pin['path']) == {k:pin[k] for k in ('path','bytes','sha256')}
    except BaseException:
        error = traceback.format_exc()
    result = dict(exit_code=int(error is not None), status='COMPLETE' if error is None else 'ERROR_PARTIAL_RETAINED',
        error=error, utc=utc(), cases=len(results), wall_seconds=time.perf_counter()-begin,
        peak_process_tree_rss=peak_rss, inputs_unchanged=pins()==inputs)
    write(output/'result.json',dict(exit=result,cases=results)); write(output/'exit.json',result)
    print(json.dumps(result),flush=True)
    return result['exit_code']


if __name__=='__main__': raise SystemExit(main())
