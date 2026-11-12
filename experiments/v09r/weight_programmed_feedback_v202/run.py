"""First finite, equal-interaction test of the frozen V202 tensor program."""
import copy
from concurrent.futures import ProcessPoolExecutor
import datetime as dt
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, data):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def parameter_hash(model):
    h = hashlib.sha256()
    for name, value in model.state_dict().items():
        h.update(name.encode())
        h.update(value.detach().numpy().tobytes())
    return h.hexdigest()


def import_old():
    path = ROOT / 'experiments/v09r/weight_programmed_feedback_v200/model.py'
    spec = importlib.util.spec_from_file_location('v202_old_model', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def worker(seed):
    import numpy as np
    import torch
    from model import load_model
    from tasks import Task
    torch.set_num_threads(1)
    contract = json.loads((HERE / 'contract.json').read_text(encoding='utf-8'))
    old_module = import_old()
    goal = np.array([1., 0., 0.], np.float32)
    results = []
    counter, episodes = 0, 0
    started = time.perf_counter()

    def rng(*parts):
        digest = hashlib.sha256(('v202|' + '|'.join(map(str, parts))).encode()).digest()
        return np.random.default_rng(int.from_bytes(digest[:8], 'little'))

    try:
        with gzip.open(HERE / 'evidence' / f'{seed}.jsonl.gz', 'xt', encoding='utf-8', compresslevel=3) as trace:
            def emit(data):
                trace.write(json.dumps(data, separators=(',', ':'), allow_nan=False) + '\n')

            with torch.inference_mode():
                for family in contract['families']:
                    for variant in contract['variants']:
                        task = Task(seed, family)
                        old = variant == 'v200_original'
                        model = (old_module.load_model(ROOT / contract['old_checkpoint']) if old
                                 else load_model(HERE / 'evidence/initial_written.pt'))
                        model.eval().requires_grad_(False)
                        initial_hash = parameter_hash(model)
                        link = variant != 'v202_no_successor'
                        used_steps, used_episodes, adoptions, evaluations, decisions = 0, 0, 0, [], []

                        def prepare():
                            return copy.deepcopy(model) if old else model.prepare(task.actions, goal, link_successors=link)

                        def absorb(transitions):
                            for row in transitions:
                                if old:
                                    model.observe(row['context'], row['action_descriptor'], row['facts'], row['known'])
                                else:
                                    model.observe_transition(row['context'], row['action_descriptor'], row['successor'],
                                                             row['terminal'], row['facts'], row['known'])

                        def execute(policy, policy_id, cycle, phase, index, exploration=False):
                            nonlocal counter, episodes, used_steps, used_episodes
                            # Trial pair shares exogenous outcomes AND tie tape;
                            # candidate/incumbent do not receive any table/seed.
                            tape_role = 'trial' if phase in ('candidate_trial', 'incumbent_trial') else phase
                            random = rng(seed, family, cycle, tape_role, index)
                            case = index % 4
                            uniforms, action_tape = random.random(5), random.random((5, 2))
                            world = task.begin(case, cycle, uniforms)
                            rows = []
                            while not world.done:
                                context = world.observe()
                                output = policy(context, task.actions, goal) if old else model(context, policy, explore=exploration)
                                scores = output['scores'].numpy()
                                assert np.isfinite(scores).all()
                                j = len(rows)
                                choose_random = exploration and action_tape[j, 0] < .1
                                options = np.arange(2) if choose_random else np.flatnonzero(np.isclose(scores, scores.max(), atol=1e-6, rtol=0.))
                                action = int(options[min(int(action_tape[j, 1] * len(options)), len(options) - 1)])
                                successor, facts, known, terminal = world.step(action)
                                rows.append(dict(context=context.tolist(), action_descriptor=task.actions[action].tolist(),
                                                 chosen=action, scores=scores.tolist(), successor=successor.tolist(),
                                                 facts=facts.tolist(), known=known.tolist(), terminal=bool(terminal),
                                                 outcome_variance=None if old else output['outcome_variance'].tolist(),
                                                 grounded_mass=None if old else output['grounded_mass'].tolist()))
                            counter += len(rows)
                            episodes += 1
                            used_steps += len(rows)
                            used_episodes += 1
                            assert counter <= contract['budget']['per_seed_max_transitions']
                            emit(dict(kind='episode', seed=seed, family=family, variant=variant, episode_id=episodes,
                                      cycle=cycle, phase=phase, case=case, index=index, policy_id=policy_id,
                                      policy_source_records=policy.count if old else policy['count'],
                                      outcome_uniforms=uniforms.tolist(), action_tape=action_tape.tolist(),
                                      transitions=rows, final_facts=facts.tolist(), value=float(facts @ goal)))
                            return facts.tolist(), rows

                        incumbent, incumbent_id = prepare(), -1
                        for cycle in range(contract['cycles']):
                            for j in range(4):
                                _, transitions = execute(prepare(), f'discovery-{cycle}-{j}', cycle, 'discovery', j, exploration=True)
                                absorb(transitions)
                            candidate, trial_records = prepare(), []
                            candidate_count = candidate.count if old else candidate['count']
                            new_facts, old_facts = [], []
                            for j in range(8):
                                y, rows = execute(candidate, cycle, cycle, 'candidate_trial', j)
                                new_facts.append(y)
                                trial_records.extend(rows)
                                y, rows = execute(incumbent, incumbent_id, cycle, 'incumbent_trial', j)
                                old_facts.append(y)
                                trial_records.extend(rows)
                            assert model.count == candidate_count  # no trial feedback entered the frozen proposal
                            if old:
                                verdict = dict(accept=True, reason='original_memory_policy_refresh_no_trial_gate', pairs=8)
                            else:
                                verdict = model.assess_trials(new_facts, old_facts, goal)
                                if variant == 'v202_no_gate':
                                    verdict = dict(verdict, accept=True, ungated_accept=True,
                                                   diagnostic_gate_would_accept=verdict['accept'])
                            previous_id = incumbent_id
                            if verdict['accept']:
                                incumbent, incumbent_id = candidate, cycle
                                adoptions += 1
                            decision = dict(kind='decision', seed=seed, family=family, variant=variant, cycle=cycle,
                                            candidate_source_records=candidate_count,
                                            incumbent_before=previous_id, incumbent_after=incumbent_id,
                                            candidate_actual=new_facts, incumbent_actual=old_facts, verdict=verdict)
                            emit(decision)
                            decisions.append(decision)
                            # Only actual completed trial records become future
                            # working memory. No imagined plan is inserted here.
                            absorb(trial_records)
                            values = []
                            for j in range(4):
                                y, _ = execute(incumbent, incumbent_id, cycle, 'evaluation', j)
                                values.append(y[0])
                            evaluations.append(values)
                            assert parameter_hash(model) == initial_hash
                            assert all(not p.requires_grad and p.grad is None for p in model.parameters())
                        row = dict(seed=seed, family=family, variant=variant, episodes=used_episodes,
                                   environment_transitions=used_steps, parameter_hash_before=initial_hash,
                                   parameter_hash_after=parameter_hash(model), parameter_updates=0,
                                   adoptions=adoptions, memory_records_written=model.count,
                                   evaluation_values=evaluations,
                                   first4_cycles=float(np.mean(evaluations[:4])),
                                   last4_cycles=float(np.mean(evaluations[-4:])),
                                   after_reversal_first2=float(np.mean(evaluations[8:10])),
                                   whole_evaluation=float(np.mean(evaluations)),
                                   discovery_episodes=64, trial_episodes=256, heldout_evaluation_episodes=64)
                        results.append(row)
                        emit(dict(kind='run_end', **row))
                        trace.flush()
                        print(json.dumps({k: row[k] for k in ('seed', 'family', 'variant', 'last4_cycles', 'adoptions')}), flush=True)
        dump(HERE / 'evidence' / f'{seed}_result.json', dict(status='COMPLETE', results=results,
             episodes=episodes, environment_transitions=counter, wall_seconds=time.perf_counter() - started))
        return results
    except BaseException:
        dump(HERE / 'evidence' / f'{seed}_failure.json', dict(status='FAILED_OR_PARTIAL',
             episodes=episodes, environment_transitions=counter, complete_runs=len(results),
             traceback=traceback.format_exc(), wall_seconds=time.perf_counter() - started))
        raise


def main():
    import torch
    from model import save_initial_model
    from checks import run_checks
    torch.set_num_threads(1)
    out = HERE / 'evidence'
    out.mkdir(exist_ok=False)
    started = time.perf_counter()
    contract = json.loads((HERE / 'contract.json').read_text(encoding='utf-8'))
    names = ['model.py', 'tasks.py', 'checks.py', 'run.py', 'launch.py', 'contract.json', 'DERIVATION.md']
    inputs = {str((HERE / name).relative_to(ROOT)).replace('\\', '/'): sha(HERE / name) for name in names}
    for rel in (contract['old_source'], contract['old_checkpoint']):
        inputs[rel] = sha(ROOT / rel)
    dump(out / 'claim.json', dict(started_utc=utc(), inputs=inputs, contract=contract, native_attempt=1))
    try:
        model = save_initial_model(out / 'initial_written.pt')
        dump(out / 'construction.json', dict(parameter_count=sum(p.numel() for p in model.parameters()),
             nonzero_parameters=sum(int(torch.count_nonzero(p)) for p in model.parameters()),
             parameter_hash=parameter_hash(model), checkpoint_sha256=sha(out / 'initial_written.pt'),
             environment_calls_before_weight_construction=0, optimizer_updates=0,
             pretrained_parameters_read=0, model_source_sha256=sha(HERE / 'model.py')))
        checked = run_checks(out / 'initial_written.pt')
        dump(out / 'checks.json', checked)
        print('Twelve synthetic mechanism checks complete; starting real task matrix.', flush=True)
        with ProcessPoolExecutor(max_workers=4) as pool:
            batches = list(pool.map(worker, contract['seeds']))
        results = [row for batch in batches for row in batch]
        aggregates = []
        for family in contract['families']:
            for variant in contract['variants']:
                rows = [r for r in results if r['family'] == family and r['variant'] == variant]
                aggregates.append(dict(family=family, variant=variant, seeds=len(rows),
                     first4_cycles=sum(r['first4_cycles'] for r in rows) / len(rows),
                     last4_cycles=sum(r['last4_cycles'] for r in rows) / len(rows),
                     whole_evaluation=sum(r['whole_evaluation'] for r in rows) / len(rows),
                     after_reversal_first2=sum(r['after_reversal_first2'] for r in rows) / len(rows),
                     adoptions=sum(r['adoptions'] for r in rows),
                     seed_last4=[r['last4_cycles'] for r in rows],
                     environment_transitions=sum(r['environment_transitions'] for r in rows)))
        assert len(results) == 96
        assert sum(r['episodes'] for r in results) == 36864
        assert sum(r['environment_transitions'] for r in results) <= 184320
        assert all(sha(ROOT / rel) == h for rel, h in inputs.items())
        result = dict(status='COMPLETE_LOCAL_WEIGHT_PROGRAM_TEST', results=results, aggregates=aggregates,
                      episodes=sum(r['episodes'] for r in results),
                      environment_transitions=sum(r['environment_transitions'] for r in results),
                      parameter_updates=0, optimizer_updates=0, sleep_calls=0, game_calls=0,
                      checks=checked, unchanged_inputs=inputs, wall_seconds=time.perf_counter() - started,
                      finished_utc=utc(), generality='Bounded numeric episodic processes only; not universal causality or semantic representation')
        dump(out / 'result.json', result)
        print(json.dumps({k: v for k, v in result.items() if k not in ('results', 'unchanged_inputs', 'checks')}, indent=2), flush=True)
    except BaseException:
        dump(out / 'failure.json', dict(status='FAILED_OR_PARTIAL', traceback=traceback.format_exc(),
             wall_seconds=time.perf_counter() - started, finished_utc=utc()))
        raise


if __name__ == '__main__':
    main()
