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
    ('depth', 'u1'), ('explore', 'u1'), ('q_action', 'u1'),
    ('full_action', 'u1'), ('training_q_control', 'u1'), ('cooldown_before', 'u1'),
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
             HERE/'contract.json', HERE/'repairs.py', HERE/'pilot.py',
             HERE/'map_binding.json', HERE/'pure_check_result.json', HERE/'control_binding.json']
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
        x['q_action'], x['full_action'], x['training_q_control'] = choice['old_action'], choice['full_action'], choice['training_q_control']
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


def parameter_parts(agent):
    hashes = {'core': hashlib.sha256(), 'facts': hashlib.sha256()}
    for name, value in agent.net.state_dict().items():
        hashes['facts' if name.startswith('heads.') else 'core'].update(value.detach().numpy().tobytes())
    return {k: h.hexdigest() for k, h in hashes.items()}


def checkpoint(agent, world, episode, obs, path):
    # A complete continuation state, not just a policy export. No source/pair deserialization.
    with gzip.open(path, 'xb', compresslevel=1) as f:
        torch.save(dict(agent=agent, world=world, episode=episode, observation=obs,
                        schema='V09_COMPLETE_LOCAL_CONTINUATION_V185'), f)


@torch.no_grad()
def evaluate(agent, bank, count, capture, episode_file, prediction_file, checkpoint_step, kind=1, ablation=None):
    clone = agent.frozen(ablation)
    parameter_before = clone.parameter_hash()
    n_before = clone.replay.n
    counters_before = clone.counters.copy()
    rows, step_count = [], 0
    audit = dict(outcomes=0, capture_brier_sum=0., pickup_mse_sum=0., successors=0,
                 model_mse_sum=0., identity_mse_sum=0., successor_Q_MAE_sum=0.)
    for j in range(count):
        world = World(bank, clone.seed, 'evaluation', j)
        obs = world.observe()
        clone.reset_episode('evaluation', j)
        pending = None
        while not world.done:
            before = world.audit()
            action = clone.act(obs, False)
            if pending is not None:
                predicted_h, old_h = pending
                model_mse = float(((predicted_h-clone.h)**2).mean())
                identity_mse = float(((old_h-clone.h)**2).mean())
                q_error = None
                if clone.q_enabled:
                    mask = torch.from_numpy(obs.legal[None])
                    qp = clone.net.q(predicted_h).masked_fill(~mask, -1e9).max(-1).values
                    qa = clone.net.q(clone.h).masked_fill(~mask, -1e9).max(-1).values
                    q_error = float((qp-qa).abs().mean())
                    audit['successor_Q_MAE_sum'] += q_error
                audit['successors'] += 1
                audit['model_mse_sum'] += model_mse
                audit['identity_mse_sum'] += identity_mse
                prediction_file.write(json.dumps(dict(kind=kind, checkpoint=checkpoint_step, episode=j,
                    next_observation_step=world.t, model_mse=model_mse, identity_mse=identity_mse,
                    own_Q_successor_MAE=q_error), separators=(',', ':'))+'\n')
            factual_readout = clone.factual and ablation != 'Q_only'
            if factual_readout:
                k = int(np.flatnonzero(np.flatnonzero(obs.legal) == action)[0])
                prediction = clone.last_predictions
                capture_prob = float(np.mean([x[1][k, 0] for x in prediction]))
                pickup_pred = float(np.mean([x[2][k] for x in prediction]))
                predicted_h = torch.stack([x[3][k:k+1] for x in prediction]).mean(0)
                old_h = clone.h.clone()
            obs, fact = world.step(action)
            if factual_readout:
                audit['outcomes'] += 1
                audit['capture_brier_sum'] += (capture_prob-fact.captured)**2
                audit['pickup_mse_sum'] += (pickup_pred-fact.pickup)**2
                pending = None if world.done else (predicted_h, old_h)
            else:
                pending = None
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
                mean_survival=float(np.mean([r['steps'] for r in rows])), prediction_audit=audit)


def run_case(spec):
    torch.use_deterministic_algorithms(True)
    seed, arm, phase, parent, map_directory = spec
    directory = Path(parent)/f'seed{seed}'/arm
    directory.mkdir(parents=True, exist_ok=False)
    start, cpu = time.perf_counter(), time.process_time()
    bank = MapBank(map_directory)
    override = None
    train_steps = 131072
    checkpoints = [0, 16384, 65536, 131072]
    input_pins = pins()
    agent = Agent(seed, arm, override)
    initial_hash = agent.parameter_hash()
    initial_parts = parameter_parts(agent)
    capture = Capture(directory/'steps.bin.gz', dict(schema='V09_STEP_CAPTURE_V185', seed=seed,
                       arm=arm, phase=phase, dtype=DTYPE.descr, pins=input_pins,
                       stage_override=override, initial_parameter_hash=initial_hash))
    episodes = gzip.open(directory/'episodes.jsonl.gz', 'xt', encoding='utf-8', compresslevel=1)
    predictions = gzip.open(directory/'prediction_checks.jsonl.gz', 'xt', encoding='utf-8', compresslevel=1)
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
            checkpoint(agent, world, episode, obs, directory/f'checkpoint_{target}.pt.gz')
            count = 256 if target == train_steps else 128
            evaluations.append(evaluate(agent, bank, count, capture, episodes, predictions, target))
            sources += count
            evaluations.append(evaluate(agent, bank, 128, capture, episodes, predictions, target, 2, 'Q_only'))
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
        predictions.close()
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
                  final_parameter_hash=agent.parameter_hash(), initial_parameter_parts=initial_parts,
                  final_parameter_parts=parameter_parts(agent), counters=agent.counters,
                  evaluations=evaluations, wall_seconds=time.perf_counter()-start,
                  cpu_seconds=time.process_time()-cpu, error=error, inputs_unchanged=True)
    write_json(directory/'result.json', result, True)
    write_json(directory/'progress.json', dict(status=status, training_steps=agent.training_steps,
                                             completed_episodes=train_complete))
    return result

