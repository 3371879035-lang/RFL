"""Frozen evaluations only; no training or old native entrypoint."""
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
