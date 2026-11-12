"""Frozen V200 parameters on the unchanged V198 pursuit kernel. No training."""
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
import datetime as dt
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def dump(path, payload):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def parameter_hash(model):
    h = hashlib.sha256()
    for name, value in model.state_dict().items():
        h.update(name.encode())
        h.update(value.detach().numpy().tobytes())
    return h.hexdigest()


def summarize(rows):
    n = len(rows)
    return dict(episodes=n, mean_score=sum(x['score'] for x in rows) / n,
                mean_steps=sum(x['steps'] for x in rows) / n,
                mean_treasures=sum(x['treasures'] for x in rows) / n,
                captured=sum(x['captured'] for x in rows),
                completed=sum(x['completed'] for x in rows))


def worker(seed):
    # Imports are limited to the new model, public encoder, and old world kernel.
    # No prior learner, runner, SLEEP module, or checkpoint is imported.
    import numpy as np
    import torch
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    model_module = load('v201_written_model', ROOT / 'experiments/v09r/weight_programmed_feedback_v200/model.py')
    world_module = load('v201_world', ROOT / 'experiments/v09r/overnight_five_arm_v198/world.py')
    adapter = load('v201_adapter', HERE / 'adapter.py')
    contract = json.loads((HERE / 'contract.json').read_text(encoding='utf-8'))
    bank = world_module.MapBank(ROOT / contract['map_bank'])
    goal = np.array(contract['goal'], dtype=np.float32)
    results = []
    started = time.perf_counter()
    for variant in contract['variants']:
        model = model_module.load_model(ROOT / contract['checkpoint'])
        model.eval().requires_grad_(False)
        before = parameter_hash(model)
        assert before == contract['parameter_hash'] and model.count == 0
        rows = []
        prefix = f'{seed}_{variant}'
        with gzip.open(HERE / 'evidence' / f'{prefix}.jsonl.gz', 'xt', encoding='utf-8', compresslevel=3) as stream:
            def emit(record):
                stream.write(json.dumps(record, separators=(',', ':'), allow_nan=False) + '\n')

            with torch.inference_mode():
                for episode in contract['episodes']:
                    world = world_module.World(bank, seed, contract['phase'], episode)
                    observation = world.observe()
                    # Identical action-selection uniforms for both variants. The
                    # environment uses its original, independent source stream.
                    tape = world_module.rng_for(seed, 'v201-policy', episode, 'tape').random((256, 2))
                    pending = deque()
                    steps = pickups = buffs = write_count = 0
                    support_sum = prior_dominated = exploration = bump_count = 0
                    initial_memory = model.count
                    emit(dict(kind='start', seed=seed, variant=variant, episode=episode,
                              memory_count=initial_memory, parameter_hash=before,
                              environment=world.audit(),
                              environment_uniform_sha256=hashlib.sha256(world.uniform.tobytes()).hexdigest()))
                    while not world.done:
                        context, candidates = adapter.encode(observation, world_module.DIR)
                        legal = np.flatnonzero(observation.legal)
                        output = model(context, candidates[legal], goal)
                        scores = output['scores'].numpy()
                        assert np.isfinite(scores).all()
                        explore = bool(tape[steps, 0] < contract['epsilon'])
                        choices = np.arange(len(legal)) if explore else np.flatnonzero(scores == scores.max())
                        local = int(choices[min(int(tape[steps, 1] * len(choices)), len(choices) - 1)])
                        action = int(legal[local])
                        support = output['support'][local].numpy()
                        support_sum += float(support.mean())
                        prior_dominated += int(support.mean() < .5)
                        exploration += int(explore)
                        pending.append((steps, pickups, context.copy(), candidates[action].copy()))
                        previous_hero = observation.hero
                        next_observation, fact = world.step(action)
                        no_movement = previous_hero == next_observation.hero
                        bump_count += int(no_movement)
                        steps += fact.steps
                        pickups += fact.pickup
                        buffs += fact.buff_pickup
                        emit(dict(kind='step', episode=episode, t=steps,
                                  public_image_bits=np.packbits(observation.image.reshape(-1)).tobytes().hex(),
                                  public_scalar=observation.scalar.tolist(), legal=legal.tolist(),
                                  context=context.tolist(), candidates=candidates[legal].tolist(),
                                  scores=scores.tolist(), chosen_action=action, explore=explore,
                                  prediction=output['prediction'][local].tolist(),
                                  support=support.tolist(), memory_count=model.count,
                                  no_movement=no_movement, fact=asdict(fact)))
                        # Only outcomes ALREADY OBSERVED may enter memory. These
                        # are conditional 64-step factual windows, not causal
                        # labels and not model-predicted rollouts.
                        while pending and (world.done or steps - pending[0][0] >= contract['fact_horizon']):
                            start_t, start_pickups, c, a = pending.popleft()
                            facts = [float(steps - start_t) / contract['fact_horizon'],
                                     float(pickups - start_pickups) / 10., float(fact.captured)]
                            if variant == 'frozen_memory':
                                model.observe(c, a, facts)
                                write_count += 1
                            emit(dict(kind='feedback', episode=episode, at_step=steps,
                                      source_step=start_t + 1, facts=facts,
                                      written=variant == 'frozen_memory'))
                        observation = next_observation
                    assert not pending
                    after = parameter_hash(model)
                    assert after == before
                    assert all(not p.requires_grad and p.grad is None for p in model.parameters())
                    assert model.count - initial_memory == write_count
                    assert write_count == (steps if variant == 'frozen_memory' else 0)
                    assert steps == world.t and pickups == world.collected
                    row = dict(seed=seed, variant=variant, episode=episode, steps=steps,
                               treasures=pickups, buffs=buffs, captured=bool(fact.captured),
                               completed=bool(fact.completed), score=1.5 * steps + 100 * pickups,
                               memory_before=initial_memory, memory_after=model.count,
                               memory_writes=write_count, mean_support=support_sum / steps,
                               prior_dominated_actions=prior_dominated, exploration_actions=exploration,
                               no_movement_actions=bump_count, parameter_hash_after=after)
                    rows.append(row)
                    emit(dict(kind='episode', **row))
                    if len(rows) % 128 == 0:
                        stream.flush()
                        print(json.dumps(dict(seed=seed, variant=variant, completed=len(rows),
                                              mean_score=summarize(rows)['mean_score'])), flush=True)
        result = dict(seed=seed, variant=variant, parameter_hash_before=before,
                      parameter_hash_after=parameter_hash(model), optimizer_updates=0,
                      sleep_calls=0, backward_calls=0, summary=summarize(rows),
                      first128=summarize(rows[:128]), last128=summarize(rows[-128:]), rows=rows)
        dump(HERE / 'evidence' / f'{prefix}.json', result)
        results.append(result)
    dump(HERE / 'evidence' / f'{seed}_finish.json', dict(seed=seed, status='COMPLETE',
         wall_seconds=time.perf_counter() - started, finished_utc=utc()))
    return results


def main():
    started = time.perf_counter()
    evidence = HERE / 'evidence'
    evidence.mkdir(exist_ok=False)
    contract = json.loads((HERE / 'contract.json').read_text(encoding='utf-8'))
    inputs = [HERE / n for n in ('adapter.py', 'run.py', 'launch.py', 'contract.json')]
    inputs += [ROOT / p for p in (contract['checkpoint'], contract['model_source'],
                                 contract['world_source'], contract['reference_receipt'])]
    inputs += sorted((ROOT / contract['map_bank']).iterdir())
    pins = {p.relative_to(ROOT).as_posix(): dict(sha256=sha(p), bytes=p.stat().st_size)
            for p in inputs if p.is_file()}
    assert sha(ROOT / contract['checkpoint']) == contract['checkpoint_sha256']
    dump(evidence / 'claim.json', dict(started_utc=utc(), contract_sha256=sha(HERE / 'contract.json'),
                                      input_pins=pins, no_retries=True, processes=4))
    with ProcessPoolExecutor(max_workers=4) as executor:
        groups = list(executor.map(worker, contract['seeds']))
    runs = [run for group in groups for run in group]
    all_rows = [row for run in runs for row in run['rows']]
    assert len(all_rows) == contract['max_episodes']
    assert sum(row['steps'] for row in all_rows) <= contract['max_environment_steps']
    pins_after = {rel: dict(sha256=sha(ROOT / rel), bytes=(ROOT / rel).stat().st_size) for rel in pins}
    assert pins_after == pins
    summaries = {v: summarize([row for row in all_rows if row['variant'] == v])
                 for v in contract['variants']}
    old = json.loads((ROOT / contract['reference_receipt']).read_text(encoding='utf-8-sig'))
    references = {}
    for group in sorted({job['group'] for job in old['jobs']}):
        jobs = [job for job in old['jobs'] if job['group'] == group]
        assert sorted(job['seed'] for job in jobs) == contract['seeds']
        assert all([row['episode'] for row in job['report']['rows']] == contract['episodes'] for job in jobs)
        references[group] = summarize([row for job in jobs for row in job['report']['rows']])
    result = dict(status='COMPLETE', frozen_parameters=True, summaries=summaries,
                  parameter_hash=contract['parameter_hash'],
                  episodes=len(all_rows), environment_steps=sum(row['steps'] for row in all_rows),
                  memory_writes=sum(row['memory_writes'] for row in all_rows),
                  optimizer_updates=0, sleep_calls=0, backward_calls=0,
                  reference_scope='stored trained-model scores on identical environment seeds/phase/episodes; '
                                  'NOT equal training, observation interface, or evaluation-memory protocol',
                  stored_references=references, input_pins_after=pins_after,
                  runs=[{k: v for k, v in run.items() if k != 'rows'} for run in runs],
                  wall_seconds=time.perf_counter() - started, finished_utc=utc())
    dump(evidence / 'result.json', result)
    print(json.dumps({k: v for k, v in result.items() if k not in ('input_pins_after', 'runs')},
                     ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
