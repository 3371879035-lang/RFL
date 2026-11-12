"""Exclusive, finite V09 experiments. Current workspace only; no old native imports."""
import argparse
import concurrent.futures
import copy
import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import struct
import sys
import time
import traceback

os.environ['OMP_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'
import numpy as np
import psutil
import torch
from learning import Agent, ARMS
from world import MapBank, World, prepare_maps

torch.set_num_threads(1)
torch.set_num_interop_threads(1)
ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
DTYPE = np.dtype([
    ('kind', 'u1'), ('checkpoint', '<i4'), ('episode', '<i4'), ('map', '<i4'),
    ('mode', 'u1'), ('step', '<u2'), ('before_hero', 'u1', (2,)),
    ('before_monsters', '<i2', (2, 2)), ('hero', 'u1', (2,)),
    ('monsters', '<i2', (2, 2)), ('action', 'u1'), ('stage', 'u1'),
    ('depth', 'u1'), ('explore', 'u1'), ('cooldown_before', 'u1'),
    ('buff_before', 'u1'), ('pickup', 'u1'), ('captured', 'u1'),
    ('completed', 'u1'), ('score', '<f4'), ('forecast', '<f4'), ('reward', '<f4')])


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def write_json(path, data, exclusive=False):
    with Path(path).open('x' if exclusive else 'w', encoding='utf-8', newline='\n') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


def pins():
    paths = [HERE/'world.py', HERE/'learning.py', HERE/'experiment.py',
             HERE/'contract.json', HERE.parent/'plan_v177.json']
    return [{'path': str(p.relative_to(ROOT)).replace('\\', '/'), 'bytes': p.stat().st_size,
             'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths]


class Capture:
    def __init__(self, path, header):
        self.file = gzip.open(path, 'xb', compresslevel=1)
        payload = json.dumps(header, sort_keys=True, separators=(',', ':')).encode()
        self.file.write(struct.pack('<I', len(payload))+payload)
        self.buffer = np.zeros(4096, DTYPE)
        self.n = self.total = 0
        self.hash = hashlib.sha256()

    def record(self, kind, checkpoint, episode, before, world, agent, fact, reward):
        x = self.buffer[self.n]
        choice = agent.last_choice
        x['kind'], x['checkpoint'], x['episode'] = kind, checkpoint, episode
        x['map'], x['mode'], x['step'] = world.map_id, world.mode, world.t
        x['before_hero'], x['before_monsters'] = before['hero'], before['monsters']
        x['hero'], x['monsters'] = world.hero, world.monsters
        x['action'], x['stage'], x['depth'], x['explore'] = choice['action'], choice['stage'], choice['depth'], choice['explored']
        x['cooldown_before'], x['buff_before'] = before['cooldown'], before['buff_left']
        x['pickup'], x['captured'], x['completed'] = fact.pickup, fact.captured, fact.completed
        x['score'], x['forecast'] = 1.5*world.t+100*world.collected, choice['forecast']
        x['reward'] = np.nan if reward is None else reward
        self.n += 1
        self.total += 1
        if self.n == len(self.buffer):
            self.flush()

    def flush(self):
        payload = self.buffer[:self.n].tobytes()
        self.file.write(payload)
        self.hash.update(payload)
        self.n = 0

    def close(self):
        self.flush()
        self.file.close()


def checkpoint(agent, world, episode, obs, path):
    # A complete continuation state, not just a policy export. No source/pair deserialization.
    with gzip.open(path, 'xb', compresslevel=1) as f:
        torch.save(dict(agent=agent, world=world, episode=episode, observation=obs,
                        schema='V09_COMPLETE_LOCAL_CONTINUATION_V179'), f)


def evaluate(agent, bank, count, capture, episode_file, checkpoint_step, kind=1, ablation=None):
    clone = agent.frozen(ablation)
    parameter_before = clone.parameter_hash()
    n_before = clone.replay.n
    counters_before = clone.counters.copy()
    rows, step_count = [], 0
    for j in range(count):
        world = World(bank, clone.seed, 'evaluation', j)
        obs = world.observe()
        clone.reset_episode('evaluation', j)
        while not world.done:
            before = world.audit()
            action = clone.act(obs, False)
            obs, fact = world.step(action)
            capture.record(kind, checkpoint_step, j, before, world, clone, fact, None)
            clone.last_action, clone.last_pickup = action, fact.pickup
            clone.local_t += 1
            step_count += 1
        row = dict(kind='evaluation' if kind == 1 else 'ablation', ablation=ablation,
                   checkpoint=checkpoint_step, episode=j, map=world.map_id, mode=world.mode,
                   heldout=world.map_id >= 90109, steps=world.t, treasures=world.collected,
                   captured=bool(fact.captured), completed=bool(fact.completed),
                   score=1.5*world.t+100*world.collected)
        rows.append(row)
        episode_file.write(json.dumps(row, sort_keys=True, separators=(',', ':'))+'\n')
    assert clone.parameter_hash() == parameter_before
    assert clone.replay.n == n_before
    assert clone.optimizer.state_dict()['state'].keys() == agent.optimizer.state_dict()['state'].keys()
    delta = {k: clone.counters[k]-counters_before[k] for k in clone.counters}
    return dict(episodes=count, steps=step_count, parameter_hash=parameter_before,
                counters=delta, ablation=ablation, checkpoint=checkpoint_step,
                mean_score=float(np.mean([r['score'] for r in rows])),
                mean_survival=float(np.mean([r['steps'] for r in rows])))


def run_case(spec):
    torch.use_deterministic_algorithms(True)
    seed, arm, phase, parent, map_directory = spec
    directory = Path(parent)/f'seed{seed}'/arm
    directory.mkdir(parents=True, exist_ok=False)
    start, cpu = time.perf_counter(), time.process_time()
    bank = MapBank(map_directory)
    override = 2 if phase in ('wiring', 'profile') else None
    train_steps = 1024 if phase == 'wiring' else 4096 if phase == 'profile' else 262144
    checkpoints = [0, train_steps] if phase == 'wiring' else [train_steps] if phase == 'profile' else [0, 16384, 65536, 131072, 262144]
    input_pins = pins()
    agent = Agent(seed, arm, override)
    initial_hash = agent.parameter_hash()
    capture = Capture(directory/'steps.bin.gz', dict(schema='V09_STEP_CAPTURE_V179', seed=seed,
                       arm=arm, phase=phase, dtype=DTYPE.descr, pins=input_pins,
                       stage_override=override, initial_parameter_hash=initial_hash))
    episodes = gzip.open(directory/'episodes.jsonl.gz', 'xt', encoding='utf-8', compresslevel=1)
    episode, world, obs = 0, None, None
    evaluations, train_complete, sources = [], 0, 0
    status, error = 'RUNNING', None
    try:
        for target in checkpoints:
            while agent.training_steps < target:
                if world is None or world.done:
                    world = World(bank, seed, 'train', episode)
                    agent.reset_episode('train', episode)
                    obs = world.observe()
                    sources += 1
                before = world.audit()
                action = agent.act(obs, True)
                nxt, fact = world.step(action)
                reward = None if arm == 'F0' else .015+fact.pickup-agent.penalty*fact.captured
                capture.record(0, target, episode, before, world, agent, fact, reward)
                agent.observe(nxt, fact, reward)
                obs = nxt
                if world.done:
                    train_complete += 1
                    row = dict(kind='training', episode=episode, steps=world.t, map=world.map_id,
                               mode=world.mode, captured=bool(fact.captured), completed=bool(fact.completed),
                               treasures=world.collected, score=1.5*world.t+100*world.collected,
                               global_step=agent.training_steps)
                    episodes.write(json.dumps(row, sort_keys=True, separators=(',', ':'))+'\n')
                    episode += 1
                if agent.training_steps % 4096 == 0:
                    write_json(directory/'progress.json', dict(status='TRAINING', seed=seed, arm=arm,
                               steps=agent.training_steps, target=train_steps, episodes=train_complete,
                               wall_seconds=time.perf_counter()-start, counters=agent.counters))
                if agent.training_steps % 128 == 0 and (Path(parent)/'STOP.json').exists():
                    raise RuntimeError('Declared resource boundary reached; exact partial retained')
            # Store full policy/history even at zero; resume state includes current real episode.
            if phase != 'profile' or target == train_steps:
                checkpoint(agent, world, episode, obs, directory/f'checkpoint_{target}.pt.gz')
            count = 2 if phase == 'wiring' else 8 if phase == 'profile' else 1024 if target == train_steps else 128
            evaluations.append(evaluate(agent, bank, count, capture, episodes, target))
            sources += count
        if phase == 'matrix' and agent.factual:
            for kind, ablation in [(2, 'H1_only'), (3, 'no_cross_episode_history_retrieval')]:
                evaluations.append(evaluate(agent, bank, 128, capture, episodes, train_steps, kind, ablation))
                sources += 128
        status = 'COMPLETE'
    except BaseException:
        error = traceback.format_exc()
        status = 'ERROR_PARTIAL_RETAINED_NO_RETRY'
        write_json(directory/'error.json', dict(error=error, training_steps=agent.training_steps,
                                               raw_records=capture.total, utc=utc()), True)
        # Preserve the exact boundary for diagnosis; not automatically claimed resumable.
        checkpoint(agent, world, episode, obs, directory/'error_boundary.pt.gz')
    finally:
        episodes.close()
        capture.close()
    assert pins() == input_pins, 'Executed input changed'
    if status == 'COMPLETE':
        assert agent.training_steps == train_steps
        assert agent.counters['reward_packets'] == (0 if arm == 'F0' else train_steps)
        assert train_complete >= train_steps//256
    result = dict(status=status, seed=seed, arm=arm, phase=phase, stage_override=override,
                  training_steps=agent.training_steps, completed_training_episodes=train_complete,
                  partial_training_episode_steps=world.t if world is not None and not world.done else 0,
                  source_instances=sources, source_uniform_draws=sources*2048,
                  record_count=capture.total, record_payload_sha256=capture.hash.hexdigest(),
                  record_bytes=DTYPE.itemsize, initial_parameter_hash=initial_hash,
                  final_parameter_hash=agent.parameter_hash(), counters=agent.counters,
                  evaluations=evaluations, wall_seconds=time.perf_counter()-start,
                  cpu_seconds=time.process_time()-cpu, error=error, inputs_unchanged=True)
    write_json(directory/'result.json', result, True)
    write_json(directory/'progress.json', dict(status=status, training_steps=agent.training_steps,
                                             completed_episodes=train_complete))
    return result


def run_seed(args):
    seed, phase, directory, maps = args
    results = []
    for arm in ARMS:
        if (Path(directory)/'STOP.json').exists():
            break
        result = run_case((seed, arm, phase, directory, maps))
        results.append(result)
        if result['status'] != 'COMPLETE':
            break
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=['prepare', 'wiring', 'profile', 'matrix'], required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--maps')
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--wall-seconds', type=float, default=86400)
    args = parser.parse_args()
    start = time.perf_counter()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    input_pins = pins()
    write_json(output/'claim.json', dict(phase=args.phase, utc=utc(), pid=os.getpid(),
               python=platform.python_version(), torch=torch.__version__, numpy=np.__version__,
               input_pins=input_pins, workers=args.workers, argv=sys.argv), True)
    error, results = None, []
    try:
        if args.phase == 'prepare':
            inventory = prepare_maps(output/'maps')
            results = inventory
        else:
            assert args.maps and 1 <= args.workers <= 12
            seeds = [91000] if args.phase == 'wiring' else list(range(91001, 91005)) if args.phase == 'profile' else list(range(9001, 9065))
            specs = [(seed, args.phase, str(output), args.maps) for seed in seeds]
            if args.workers == 1:
                for spec in specs:
                    batch = run_seed(spec)
                    results.extend(batch)
                    write_json(output/'progress.json', dict(completed_cases=len(results),
                               last_seed=spec[0], wall_seconds=time.perf_counter()-start))
                    if any(r['status'] != 'COMPLETE' for r in batch):
                        raise RuntimeError('Native case failed; retained without retry')
            else:
                with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
                    futures = {pool.submit(run_seed, spec): spec[0] for spec in specs}
                    pending = set(futures)
                    last_disk_check = 0.
                    resource = None
                    while pending:
                        completed, pending = concurrent.futures.wait(pending, timeout=2,
                                             return_when=concurrent.futures.FIRST_COMPLETED)
                        processes = [psutil.Process()]+psutil.Process().children(recursive=True)
                        memory = sum(p.memory_info().rss for p in processes if p.is_running())
                        if memory > 20*1024**3:
                            resource = '20GiB aggregate RAM'
                        if time.perf_counter()-start > args.wall_seconds:
                            resource = 'native cumulative wall budget'
                        if time.perf_counter()-last_disk_check > 30:
                            disk = sum(p.stat().st_size for p in output.rglob('*') if p.is_file())
                            last_disk_check = time.perf_counter()
                            if disk > 25*1024**3:
                                resource = '25GiB compressed capture/checkpoint budget'
                        if resource and not (output/'STOP.json').exists():
                            write_json(output/'STOP.json', dict(reason=resource, utc=utc()), True)
                        for future in completed:
                            batch = future.result()
                            results.extend(batch)
                            write_json(output/'progress.json', dict(completed_cases=len(results),
                                       last_seed=futures[future], wall_seconds=time.perf_counter()-start,
                                       aggregate_rss=memory))
                            if any(r['status'] != 'COMPLETE' for r in batch):
                                if not (output/'STOP.json').exists():
                                    write_json(output/'STOP.json', dict(reason='Native case error; no retries', utc=utc()), True)
                    if resource or any(r['status'] != 'COMPLETE' for r in results):
                        raise RuntimeError('Stopped at recorded execution/resource boundary; partials retained')
        assert pins() == input_pins
    except BaseException:
        error = traceback.format_exc()
    exit_record = dict(status='COMPLETE' if error is None else 'ERROR_PARTIAL_RETAINED',
                       exit_code=0 if error is None else 1, phase=args.phase, utc=utc(),
                       wall_seconds=time.perf_counter()-start, cases=len(results), error=error,
                       pins_after=pins(), inputs_unchanged=pins() == input_pins)
    write_json(output/'result.json', dict(exit=exit_record, cases=results), True)
    write_json(output/'exit.json', exit_record, True)
    print(json.dumps(exit_record, ensure_ascii=False), flush=True)
    return exit_record['exit_code']


if __name__ == '__main__':
    raise SystemExit(main())
