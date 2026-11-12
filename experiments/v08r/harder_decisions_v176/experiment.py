"""V176 first bounded V0.8 execution. Old native/checkers are never invoked."""
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import argparse
import ctypes
import gzip
import hashlib
import json
import random
import sys
import time
import traceback
import learning as L
from world import Engine, RewardPacket, make_source

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def wire(x):
    return json.dumps(x, sort_keys=True, separators=(',', ':'))


def digest(x):
    return hashlib.sha256(wire(x).encode()).hexdigest()


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''):
            h.update(b)
    return h.hexdigest()


def save(path, obj):
    with path.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write('\n')


class Recorder:
    def __init__(self, output, phase, contract):
        output.mkdir(exist_ok=False)
        self.output, self.phase, self.contract = output, phase, contract
        self.file = (output/'raw.jsonl.gz').open('xb', buffering=1024*1024)
        self.gzip = gzip.GzipFile(filename='', mode='wb', compresslevel=1, mtime=0, fileobj=self.file)
        self.counts, self.seq, self.uid, self.bytes = Counter(), 0, 0, 0
        self.start, self.cpu = time.perf_counter(), time.process_time()

    def emit(self, tag, obj):
        b = (wire({'seq': self.seq, 'tag': tag, 'payload': obj})+'\n').encode()
        self.gzip.write(b)
        self.bytes += len(b)
        self.seq += 1
        if self.seq % 4096 == 0 and tag not in ('FINAL', 'FAILURE'):
            limit = self.contract['phase_limits'][self.phase]
            if self.file.tell() > limit['compressed_bytes']-65536:
                raise RuntimeError('Declared capture budget exhausted')
            if time.perf_counter()-self.start > limit['wall_seconds']:
                raise RuntimeError('Declared native wall budget exhausted')

    def begin_native(self, mode):
        assert self.counts['rollouts'] < self.contract['phase_limits'][self.phase]['rollouts']
        self.counts['rollouts'] += 1
        self.counts[mode+'_rollouts'] += 1
        self.uid += 1
        return self.uid

    def native_step(self, mode):
        assert self.counts['steps'] < self.contract['phase_limits'][self.phase]['steps']
        self.counts['steps'] += 1
        self.counts[mode+'_steps'] += 1


def materialize(plan, log):
    tapes = {}
    for seed in range(8001, 8033):
        for mirror in (0, 1):
            for condition in plan['environments']:
                name, n = condition['id'], condition['states']
                rng = {p: random.Random(f'V08|{seed}|{mirror}|{name}|{p}') for p in ('train_env', 'train_action', 'eval_env')}
                block = {'seed': seed, 'mirror': mirror, 'condition': name,
                         'train_env': [[rng['train_env'].random() for _ in range(n)] for _ in range(256)],
                         'train_action': [[[rng['train_action'].random(), rng['train_action'].random()] for _ in range(n)] for _ in range(256)],
                         'eval_env': [[rng['eval_env'].random() for _ in range(n)] for _ in range(512)]}
                tapes[seed, mirror, name] = block
                log.emit('TAPE', {'block': block, 'sha256': digest(block)})
                log.counts['train_env_PRNG'] += 256*n
                log.counts['train_action_PRNG'] += 256*n*2
                log.counts['eval_env_PRNG'] += 512*n
    assert sum(log.counts[k] for k in ('train_env_PRNG', 'train_action_PRNG', 'eval_env_PRNG')) == 2211840
    return tapes


def policy_cost(learner, log):
    t = time.perf_counter_ns()
    program, details = learner.policy()
    elapsed = time.perf_counter_ns()-t
    log.counts['policy_calls'] += 1
    n = learner.task.goal
    if type(learner) is L.FactualLearner:
        log.counts['goal_planning_edges'] += 2*n
    elif type(learner) is L.Hybrid:
        log.counts['actual_M1_edges' if learner.mode == 'M1' else 'actual_tie_candidate_scores'] += 2*n
    return program, details, elapsed


def learn(learner, obs, log):
    start = time.perf_counter_ns()
    if type(learner) is L.FactualLearner:
        rewards = None
        updates, facts = learner.learn(obs)
    else:
        rewards = tuple(1.0 if row[3] == 'SUCCESS' else learner.failure_reward if row[3] == 'COLLISION' else 0.0 for row in obs.steps)
        updates, facts = learner.learn(RewardPacket(obs, rewards))
    elapsed = time.perf_counter_ns()-start
    for u in updates:
        log.counts[u[0]+'_backups'] += 1
        log.counts['numeric_changes'] += u[3] != u[5]
    log.counts['fact_updates'] += len(facts)
    log.emit('LEARN', {'uid': obs.uid, 'rewards': rewards, 'updates': updates, 'facts': facts,
                       'after': learner.snapshot(), 'update_ns': elapsed})
    return elapsed


def evaluate(learner, engine, log, checkpoint, vectors):
    original = learner.snapshot()
    frozen = L.FrozenPolicy(learner)
    before = frozen.snapshot()
    program, details, ns = policy_cost(frozen.clone, log)
    log.emit('FREEZE_BEGIN', {'checkpoint': checkpoint, 'state': before, 'live_state_sha256': digest(original),
                              'nonalias_asserted': True, 'program': program, 'readout': details, 'policy_ns': ns})
    first, successes, steps = log.uid+1, 0, 0
    for vector in vectors:
        obs = engine.rollout(program, vector, 'eval')
        successes += obs.terminal == 'SUCCESS'
        steps += len(obs.steps)
    assert frozen.snapshot() == before and learner.snapshot() == original
    bank = {'checkpoint': checkpoint, 'first_uid': first, 'last_uid': log.uid, 'episodes': len(vectors),
            'successes': successes, 'steps': steps, 'program': program, 'mean_success': successes/len(vectors),
            'frozen_before': digest(before), 'frozen_after': digest(frozen.snapshot()),
            'live_after': digest(learner.snapshot()), 'learning_writes': 0, 'policy_ns': ns}
    log.emit('FREEZE_END', bank)
    return bank


def run_stream(plan, arm, condition, mirror, context, log, tape=None):
    baseline = Counter(log.counts)
    task, probabilities = make_source(plan, condition, mirror)
    engine, learner = Engine(task, probabilities, log), L.make_learner(task, arm)
    log.emit('STREAM_INITIAL', {'context': context, 'source': engine.audit_source(), 'learner': learner.snapshot()})
    wiring, rows, banks = log.phase == 'wiring', [], []
    train_n = 2 if wiring else 256
    successes = steps = policy_ns = update_ns = shadow_ns = 0
    behavior = hashlib.sha256()
    for e in range(train_n+1):
        if wiring and e == 2:
            banks.append(evaluate(learner, engine, log, e, [[.1]*task.goal, [.99]*task.goal]))
            assert banks[-1]['successes'] == 1
        elif not wiring and e in plan['matrix']['checkpoints']:
            banks.append(evaluate(learner, engine, log, e, tape['eval_env']))
        if e == train_n:
            break
        greedy, details, ns = policy_cost(learner, log)
        coins = [(False, 0)]*task.goal if wiring else [(u < .1, int(v*2)) for u, v in tape['train_action'][e]]
        scripted = wiring and e == 0
        program = tuple(0 for _ in greedy) if scripted else tuple(b if explore else greedy[s] for s, (explore, b) in enumerate(coins))
        shadow, sns = None, 0
        if type(learner) is L.Hybrid:
            t = time.perf_counter_ns()
            shadow = L.proposals(learner)
            sns = time.perf_counter_ns()-t
            log.counts['shadow_calls'] += 1
            log.counts['shadow_M1_edges'] += 2*task.goal
            log.counts['shadow_tie_scores'] += 2*task.goal
        log.emit('TRAIN_POLICY', {'epoch': e+1, 'greedy': greedy, 'program': program, 'readout': details,
                                  'coins': coins, 'scripted': scripted, 'shadow': shadow,
                                  'shadow_covered': shadow is not None, 'policy_ns': ns, 'shadow_ns': sns})
        vector = ([.1, .99, .1] if e == 0 else [.1]*task.goal) if wiring else tape['train_env'][e]
        obs = engine.rollout(program, vector, 'train')
        update_ns += learn(learner, obs, log)
        policy_ns += ns
        shadow_ns += sns
        successes += obs.terminal == 'SUCCESS'
        steps += len(obs.steps)
        behavior.update((wire(asdict(obs)['steps'])+'\n').encode())
        if wiring:
            assert obs.terminal == ('COLLISION' if e == 0 else 'SUCCESS')
        row = {'epoch': e+1, 'uid': obs.uid, 'successes': successes, 'train_steps': steps,
               'policy_ns': policy_ns, 'update_ns': update_ns, 'shadow_ns': shadow_ns}
        rows.append(row)
        log.emit('TRAIN_CHECKPOINT', row)
    assert engine.audit_source() == engine._initial
    result = {**context, 'train_tasks': train_n, 'train_successes': successes, 'train_steps': steps,
              'train_curve': rows, 'eval_banks': banks, 'counts': dict(log.counts-baseline),
              'final_state': learner.snapshot(), 'behavior_sha256': behavior.hexdigest(), 'source_unchanged': True}
    log.emit('STREAM_FINAL', result)
    return result


def run(plan, log):
    results = []
    if log.phase == 'wiring':
        condition = {'id': 'wiring_unit', 'kind': 'serial_fork_rejoin', 'units': 1, 'states': 3, 'maximum_decisions': 2}
        for arm in plan['arms']:
            results.append(run_stream(plan, arm, condition, 0, {'phase': 'wiring', 'arm': arm['id']}, log))
    else:
        tapes = materialize(plan, log)
        for seed in range(8001, 8033):
            for mirror in (0, 1):
                for condition in plan['environments']:
                    name = condition['id']
                    for arm in plan['arms']:
                        ctx = {'phase': 'matrix', 'seed': seed, 'mirror': mirror, 'condition': name, 'arm': arm['id']}
                        results.append(run_stream(plan, arm, condition, mirror, ctx, log, tapes[seed, mirror, name]))
            print(wire({'completed_seed': seed, 'streams': len(results), 'rollouts': log.counts['rollouts']}), flush=True)
    return results


def process_memory():
    class PMC(ctypes.Structure):
        _fields_ = [('cb', ctypes.c_ulong), ('faults', ctypes.c_ulong)]+[(k, ctypes.c_size_t) for k in
                    ('PeakWorkingSetSize', 'WorkingSetSize', 'qpp', 'qpu', 'qnpp', 'qnpu', 'pf', 'ppf')]
    kernel = ctypes.windll.kernel32
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    getinfo = ctypes.windll.psapi.GetProcessMemoryInfo
    getinfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(PMC), ctypes.c_ulong]
    info = PMC()
    info.cb = ctypes.sizeof(info)
    assert getinfo(kernel.GetCurrentProcess(), ctypes.byref(info), info.cb)
    return {'working_set_bytes': info.WorkingSetSize, 'peak_working_set_bytes': info.PeakWorkingSetSize,
            'scope': 'Windows process working set sampled after native loops, before capture finalization/result serialization'}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--phase', choices=('wiring', 'matrix'), required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    contract = json.loads((HERE/'contract.json').read_text(encoding='utf-8'))
    plan = json.loads((ROOT/contract['plan']).read_text(encoding='utf-8'))
    inputs = {path: sha(ROOT/path) for path in contract['inputs']}
    log = Recorder(args.output, args.phase, contract)
    complete, error, results = False, None, []
    log.emit('RUN_START', {'utc': datetime.now(timezone.utc).isoformat(), 'phase': args.phase,
                           'python': sys.version, 'contract': contract, 'plan': plan, 'inputs': inputs})
    try:
        results = run(plan, log)
        assert log.counts['rollouts'] == contract['phase_limits'][args.phase]['rollouts']
        complete = True
    except BaseException as exc:
        error = {'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc()}
        log.emit('FAILURE', error)
        traceback.print_exc()
    finally:
        unchanged = all(sha(ROOT/path) == h for path, h in inputs.items())
        receipt = {'phase': args.phase, 'complete': complete, 'child_exit_code': 0 if complete and unchanged else 1,
                   'utc': datetime.now(timezone.utc).isoformat(), 'counts': dict(log.counts), 'error': error,
                   'inputs_unchanged': unchanged, 'wall_seconds': time.perf_counter()-log.start,
                   'cpu_seconds': time.process_time()-log.cpu, 'memory': process_memory()}
        log.emit('FINAL', receipt)
        receipt['canonical_records'], receipt['uncompressed_bytes'] = log.seq, log.bytes
        log.gzip.close()
        log.file.close()
        receipt['compressed_bytes'] = (args.output/'raw.jsonl.gz').stat().st_size
        receipt['raw_sha256'] = sha(args.output/'raw.jsonl.gz')
        save(args.output/'exit.json', receipt)
        if complete:
            save(args.output/'result.json', {'streams': results, 'counts': dict(log.counts)})
        print(wire(receipt), flush=True)
    return receipt['child_exit_code']


if __name__ == '__main__':
    raise SystemExit(main())
