"""First-run-only bounded matrix. Hold-out evaluation never enters the learner."""
from pathlib import Path
from datetime import datetime, timezone
import gzip
import hashlib
import json
import random
import sys
import time
import torch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT/'src'))
from feedback_program_v209.network import RelationalFeedbackNet, Policy, select_candidate
from world import World, specification, scenario

CONTRACT = json.loads((HERE/'contract.json').read_text(encoding='utf-8'))
EVIDENCE = HERE/'evidence'
EVIDENCE.mkdir(exist_ok=True)
if (EVIDENCE/'raw.jsonl.gz').exists() or (HERE/'native_summary.json').exists():
    raise SystemExit('Existing first-run evidence retained; no automatic retry')
torch.set_num_threads(1)
TORCH_RNG = torch.get_rng_state().clone()
START = time.perf_counter()


def hash_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


before = {p: hash_file(ROOT/p) for p in CONTRACT['input_sha256']}
if before != CONTRACT['input_sha256']:
    raise SystemExit('Declared source input differs before run')
counts = {'episodes': 0, 'steps': 0, 'state_observations': 0, 'evaluations': 0,
          'trials': 0, 'candidate_builds': 0, 'adoptions': 0}
summaries = []
record_count = 0


with (EVIDENCE/'raw.jsonl.gz').open('xb') as binary, gzip.GzipFile(fileobj=binary, mode='wb', mtime=0) as raw:
    def emit(kind, **payload):
        global record_count
        raw.write((json.dumps({'kind': kind, **payload}, sort_keys=True, separators=(',', ':'),
                              ensure_ascii=False, allow_nan=False)+'\n').encode('utf-8'))
        record_count += 1

    emit('start', contract_sha256=hash_file(HERE/'contract.json'), utc=datetime.now(timezone.utc).isoformat(),
         input_sha256=before, torch_version=torch.__version__, threads=torch.get_num_threads())
    for family in CONTRACT['families']:
        for seed in CONTRACT['seeds']:
            for arm in CONTRACT['arms']:
                run_id = f'{family}/{seed}/{arm}'
                world = World(specification(family, seed))
                learner = RelationalFeedbackNet(fields=8, max_order=1 if arm == 'unary_verified' else 2,
                                                memory_size=CONTRACT['memory_size'])
                parameter_before = learner.parameter_digest()
                incumbent = Policy((0,)*256, ())
                emit('run_begin', run=run_id, family=family, seed=seed, arm=arm, world_spec=world.spec,
                     parameters_sha256=parameter_before,
                     parameter_scalars=sum(p.numel() for p in learner.parameters()))

                def episode(cycle, phase, index, policy, learn=True, role=None):
                    tape = scenario(family, seed, cycle, phase, index)
                    public, private = world.run(policy, tape, cycle, counts['episodes'], warm=phase == 'warm')
                    counts['episodes'] += 1
                    counts['steps'] += 4
                    if learn:
                        learner.observe(public)
                        counts['state_observations'] += 1
                    else:
                        counts['evaluations'] += 1
                    if phase == 'trial':
                        counts['trials'] += 1
                    emit('episode', run=run_id, cycle=cycle, phase=phase, index=index, role=role,
                         learned=learn, public=public, private=private)
                    return public

                for i in range(CONTRACT['warm_episodes']):
                    episode(-1, 'warm', i, incumbent)
                cycles = []
                for cycle in range(CONTRACT['cycles']):
                    for i in range(CONTRACT['fit_episodes']):
                        episode(cycle, 'fit', i, incumbent)
                    bank, bank_info = learner.candidates()
                    counts['candidate_builds'] += 1
                    emit('bank', run=run_id, cycle=cycle, incumbent=incumbent.wire(),
                         candidates=[p.wire() for p in bank], diagnostics=bank_info)
                    ranking = [episode(cycle, 'rank', i, incumbent) for i in range(CONTRACT['rank_episodes'])]
                    rng = (random.Random(209700000+seed*100+cycle) if arm == 'joint_uniform_verified' else None)
                    candidate, chosen, scores, baseline = select_candidate(bank, incumbent, ranking, rng)
                    rank_delta = 0 if chosen is None else scores[chosen]-baseline
                    emit('proposal', run=run_id, cycle=cycle, chosen=chosen, scores=scores,
                         baseline_score=baseline, rank_delta_numerator=rank_delta, candidate=candidate.wire())
                    trial_delta = 0
                    for i in range(CONTRACT['trial_pairs']):
                        ref = episode(cycle, 'trial', i, incumbent, role='reference')
                        new = episode(cycle, 'trial', i, candidate, role='candidate')
                        trial_delta += new['outcome']-ref['outcome']
                    identical = candidate.table == incumbent.table
                    adopt = not identical and (rank_delta > 0 if arm == 'joint_rank_only' else trial_delta > 0)
                    previous = incumbent
                    if adopt:
                        incumbent = candidate
                        counts['adoptions'] += 1
                    emit('decision', run=run_id, cycle=cycle, previous=previous.wire(), candidate=candidate.wire(),
                         next=incumbent.wire(), identical=identical, adopt=adopt,
                         trial_difference_sum=trial_delta, rank_delta_numerator=rank_delta)
                    deployment = [episode(cycle, 'deploy', i, incumbent) for i in range(CONTRACT['deploy_episodes'])]
                    evaluation = [episode(cycle, 'eval', i, incumbent, learn=False) for i in range(CONTRACT['eval_episodes'])]
                    row = {'cycle': cycle, 'trial_delta': trial_delta, 'adopt': adopt,
                           'deployment_success': sum(x['outcome'] for x in deployment),
                           'evaluation_success': sum(x['outcome'] for x in evaluation),
                           'selected_structure': list(candidate.structure),
                           'next_policy_id': incumbent.identity}
                    cycles.append(row)
                    emit('cycle_end', run=run_id, **row)
                parameter_after = learner.parameter_digest()
                assert parameter_after == parameter_before
                assert all(not p.requires_grad for p in learner.parameters())
                summary = {'run': run_id, 'family': family, 'seed': seed, 'arm': arm,
                           'episodes': world.episodes, 'steps': world.steps, 'observations': learner.seen,
                           'parameter_sha256_before': parameter_before, 'parameter_sha256_after': parameter_after,
                           'neural_build_seconds': learner.build_seconds, 'cycles': cycles}
                summaries.append(summary)
                emit('run_end', **summary)
            print(f'completed {family} seed={seed}', flush=True)
    after = {p: hash_file(ROOT/p) for p in CONTRACT['input_sha256']}
    assert before == after
    assert torch.equal(TORCH_RNG, torch.get_rng_state())
    assert counts == {**CONTRACT['expected_counts_except_adoptions'], 'adoptions': counts['adoptions']}
    result = {'status': 'COMPLETE', 'counts': counts, 'runs': summaries,
              'wall_seconds': time.perf_counter()-START, 'inputs_unchanged': before == after,
              'input_sha256_before': before, 'input_sha256_after': after,
              'torch_parameter_initialization_rng_unchanged': True,
              'gradient_steps': 0, 'optimizer_steps': 0, 'old_runs': 0}
    emit('complete', counts=counts, run_count=len(summaries), wall_seconds=result['wall_seconds'])
with (HERE/'native_summary.json').open('x', encoding='utf-8', newline='\n') as out:
    json.dump(result, out, ensure_ascii=False, indent=2)
    out.write('\n')
print(json.dumps({'status': result['status'], 'counts': counts, 'canonical_records': record_count,
                  'wall_seconds': result['wall_seconds']}, ensure_ascii=False))
