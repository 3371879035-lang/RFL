"""One first-run family/seed shard; four arms are serial, other shards may run in parallel."""
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import asdict
from itertools import product
import gzip
import hashlib
import json
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT/'src'))
import torch
from feedback_program_v210 import AdaptiveFeedbackNet, EvidenceBook, rank_candidates
from feedback_program_v210.network import parameter_digest
from feedback_program_v211.mean_comparator import MeanEightBook
from world import ARMS, FAMILIES, World, scenario, specification

CONTEXTS = tuple(product((0, 1), repeat=4))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def policy_wire(policy):
    h = policy._head
    with torch.no_grad():
        values = [policy([row])[0].tolist() for row in CONTEXTS]
    state = {k: {'shape': list(v.shape), 'values': v.reshape(-1).tolist()}
             for k, v in policy.state_dict().items()}
    return {'id': policy.identity, 'last_fact_id': policy.last_fact_id,
            'meta': [h.lift.cardinalities, h.lift.structure, h.actions, h.outcomes,
                     h.block_size, h.hazard, h.starts, h.n, policy.goal],
            'state': state, 'values': values,
            'actions': [max(range(len(v)), key=lambda a: v[a]) for v in values]}


def main(family, seed):
    contract = json.loads((HERE/'contract.json').read_text(encoding='utf-8'))
    assert family in contract['families'] and seed in contract['seeds']
    folder = HERE/'shards'/f'{family}_s{seed:02d}'
    folder.mkdir(parents=True, exist_ok=True)
    with (folder/'claim.json').open('x', encoding='utf-8') as stream:
        json.dump({'utc': datetime.now(timezone.utc).isoformat(), 'family': family, 'seed': seed}, stream)
    before = {p: sha(ROOT/p) for p in contract['input_sha256']}
    assert before == contract['input_sha256']
    torch.set_num_threads(1)
    rng = torch.get_rng_state().clone()
    started = time.perf_counter()
    summaries = []
    record_count = 0
    with (folder/'raw.jsonl.gz').open('xb') as binary, gzip.GzipFile(fileobj=binary, mode='wb', mtime=0) as raw:
        def emit(kind, **payload):
            nonlocal record_count
            raw.write((json.dumps({'kind': kind, **payload}, ensure_ascii=False, sort_keys=True,
                                  separators=(',', ':'), allow_nan=False)+'\n').encode('utf-8'))
            record_count += 1

        emit('shard_start', family=family, seed=seed, input_sha256=before,
             contract_sha256=sha(HERE/'contract.json'), torch_version=torch.__version__)
        offset = (seed+FAMILIES.index(family)) % len(ARMS)
        for arm in ARMS[offset:]+ARMS[:offset]:
            start_wall, start_cpu = time.perf_counter(), time.process_time()
            net = AdaptiveFeedbackNet((2,)*4, block_size=32, hazard=0. if arm == 'pooled_history' else .05)
            initial_growth = net.grow(32)
            initial_parameters = [parameter_digest(h) for h in net.heads]
            net.set_initial_policy(net.snapshot((0., 1.))[0])
            book = MeanEightBook(.05) if arm == 'mean_eight' else EvidenceBook(.05)
            world = World(specification(family, seed))
            event_id = 0
            learned_count = evaluation_count = trial_episodes = 0
            timings = {'world_and_action_seconds': 0., 'ordinary_observe_seconds': 0.,
                       'paired_update_seconds': 0., 'snapshot_seconds': 0., 'ranking_seconds': 0.,
                       'response_and_growth_seconds': 0.}
            emit('run_begin', arm=arm, spec=world.spec, initial=policy_wire(net.active),
                 initial_growth=initial_growth, initial_parameters=initial_parameters)

            def episode(cycle, phase, slot, policy, epsilon=.2, learn=True, role=None, paired=False):
                nonlocal event_id, learned_count, evaluation_count, trial_episodes
                tape = scenario(family, seed, cycle, phase, slot)
                tick = time.perf_counter()
                fact, private = world.run(policy, tape, cycle, event_id, epsilon)
                timings['world_and_action_seconds'] += time.perf_counter()-tick
                event_id += 1
                if learn and not paired:
                    tick = time.perf_counter()
                    net.observe(fact)
                    timings['ordinary_observe_seconds'] += time.perf_counter()-tick
                if learn:
                    learned_count += 1
                else:
                    evaluation_count += 1
                if paired:
                    trial_episodes += 1
                emit('episode', arm=arm, cycle=cycle, phase=phase, slot=slot, role=role,
                     learn=learn, paired=paired, epsilon=epsilon, public=asdict(fact), private=private)
                return fact

            def evaluate(checkpoint, cycle):
                n = len(net.history)
                facts = [episode(cycle, 'eval', i, net.active, learn=False) for i in range(128)]
                assert len(net.history) == n
                result = {'checkpoint': checkpoint, 'cycle': cycle, 'successes': sum(f.outcome for f in facts),
                          'episodes': len(facts), 'policy_id': net.active.identity,
                          'learned_facts': len(net.history)}
                emit('evaluation', arm=arm, **result)
                return result

            checkpoints = [evaluate(0, -1)]
            for slot in range(64):
                episode(-1, 'warm', slot, net.active, epsilon=1.)
            cycles = []
            for cycle in range(6):
                cycle_facts = []
                for slot in range(32):
                    cycle_facts.append(episode(cycle, 'train', slot, net.active))
                tick = time.perf_counter()
                bank = net.snapshot((0., 1.))
                timings['snapshot_seconds'] += time.perf_counter()-tick
                emit('bank', arm=arm, cycle=cycle, memory_ids=[f.id for f in net.history],
                     incumbent=policy_wire(net.active), candidates=[policy_wire(p) for p in bank])
                ranking = [episode(cycle, 'train', slot, net.active) for slot in range(32, 64)]
                cycle_facts.extend(ranking)
                tick = time.perf_counter()
                nomination, scores = rank_candidates(bank, net.active, ranking, epsilon=.2)
                timings['ranking_seconds'] += time.perf_counter()-tick
                emit('nomination', arm=arm, cycle=cycle, **scores,
                     candidate=nomination.candidate.identity, selection_cutoff=nomination.known_through_id)
                trial = net.start_trial(nomination, book, horizon=256, switch_cost=0.,
                                       max_pairs=8 if arm == 'mean_eight' else 128,
                                       pair_cost=0., epsilon=.2)
                slot = 64
                while trial.status == 'continue':
                    ref = episode(cycle, 'train', slot, trial.reference, role='reference', paired=True)
                    cand = episode(cycle, 'train', slot+1, trial.candidate, role='candidate', paired=True)
                    tick = time.perf_counter()
                    net.record_trial_pair(trial, ref, cand, f'{cycle}:{trial.n}')
                    timings['paired_update_seconds'] += time.perf_counter()-tick
                    cycle_facts.extend((ref, cand))
                    slot += 2
                tick = time.perf_counter()
                decision = net.respond_to_trial(trial, expansion_cell_budget=0 if arm == 'fixed_order' else 16)
                timings['response_and_growth_seconds'] += time.perf_counter()-tick
                emit('decision', arm=arm, cycle=cycle, **decision)
                for remaining in range(slot, 320):
                    cycle_facts.append(episode(cycle, 'train', remaining, net.active))
                assert len(cycle_facts) == 320
                row = {'cycle': cycle, 'status': trial.status, 'trial_pairs': trial.n,
                       'training_successes': sum(f.outcome for f in cycle_facts),
                       'ordinary_after_trial': 320-slot, 'structures': len(net.heads),
                       'active_structure': net.active._head.lift.structure,
                       'memory_facts': len(net.history), 'replay_reads': net.replay_reads}
                cycles.append(row)
                emit('cycle_end', arm=arm, **row)
                checkpoints.append(evaluate(cycle+1, cycle))
            after_parameters = [parameter_digest(h) for h in net.heads[:len(initial_parameters)]]
            assert after_parameters == initial_parameters
            assert all(not p.requires_grad for p in net.parameters())
            assert len(net.history) == learned_count == 1984
            assert evaluation_count == 896 and world.episodes == 2880 and world.steps == 11520
            summary = {'arm': arm, 'family': family, 'seed': seed, 'episodes': world.episodes,
                       'steps': world.steps, 'learned_facts': learned_count, 'evaluations': evaluation_count,
                       'trial_episodes': trial_episodes, 'adoptions': sum(c['status'] == 'adopt' for c in cycles),
                       'cycles': cycles, 'checkpoints': checkpoints, 'timings': timings,
                       'growth_seconds': net.growth_seconds, 'replay_reads': net.replay_reads,
                       'final_structures': [h.lift.structure for h in net.heads],
                       'parameter_scalars': sum(p.numel() for h in net.heads for p in h.parameters()),
                       'buffer_bytes': sum(b.numel()*b.element_size() for h in net.heads for b in h.buffers()),
                       'original_parameters_unchanged': after_parameters == initial_parameters,
                       'wall_seconds': time.perf_counter()-start_wall, 'cpu_seconds': time.process_time()-start_cpu}
            emit('run_end', **summary)
            summaries.append(summary)
            print(f'{family} seed={seed} {arm} completed {summary["wall_seconds"]:.2f}s', flush=True)
        after = {p: sha(ROOT/p) for p in before}
        assert after == before and torch.equal(rng, torch.get_rng_state())
        emit('shard_end', input_unchanged=True, torch_rng_unchanged=True, runs=len(summaries))
    result = {'family': family, 'seed': seed, 'runs': summaries, 'records': record_count,
              'wall_seconds': time.perf_counter()-started, 'input_unchanged': True,
              'torch_rng_unchanged': True, 'gradient_updates': 0, 'raw_sha256': sha(folder/'raw.jsonl.gz')}
    with (folder/'native_summary.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')


if __name__ == '__main__':
    main(sys.argv[1], int(sys.argv[2]))
