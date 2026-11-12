"""One fixed-budget new-instance comparison; all policies/weights auditable."""
from concurrent.futures import ProcessPoolExecutor
import datetime as dt
import gzip
import hashlib
import json
from pathlib import Path
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


def route_wire(route):
    return dict(default=route['default'], scopes=[dict(context=list(k), policy_id=v)
                 for k, v in sorted(route['scopes'].items())])


def worker(seed):
    import numpy as np
    import torch
    from model import BASE, load_model
    from tasks import Task
    torch.set_num_threads(1)
    contract = json.loads((HERE / 'contract.json').read_text(encoding='utf-8'))
    goal = np.array([1., 0., 0.], np.float32)
    results, counter, episodes = [], 0, 0
    started = time.perf_counter()

    def rng(*parts):
        digest = hashlib.sha256(('v203|' + '|'.join(map(str, parts))).encode()).digest()
        return np.random.default_rng(int.from_bytes(digest[:8], 'little'))

    try:
        with gzip.open(HERE / 'evidence' / f'{seed}.jsonl.gz', 'xt', encoding='utf-8', compresslevel=3) as trace:
            def emit(data):
                trace.write(json.dumps(data, separators=(',', ':'), allow_nan=False) + '\n')

            with torch.inference_mode():
                for family in contract['families']:
                    for variant in contract['variants']:
                        task = Task(seed, family)
                        legacy = variant == 'v202_original'
                        model = (BASE.load_model(ROOT / contract['old_checkpoint']) if legacy else
                                 load_model(HERE / 'evidence/initial_written.pt', conditional_age=variant != 'v203_global_age'))
                        model.eval().requires_grad_(False)
                        origin = parameter_hash(model)
                        prepare = lambda: model.prepare(task.actions, goal)
                        policies = {-1: prepare()}
                        routing = dict(default=-1, scopes={})
                        used_steps, used_episodes, adopted_contexts, changed_cycles = 0, 0, 0, 0
                        evaluations, shadows = [], []

                        def absorb(transitions):
                            for row in transitions:
                                model.observe_transition(row['context'], row['action_descriptor'], row['successor'],
                                                         row['terminal'], row['facts'], row['known'])

                        def execute(cycle, phase, index, route=None, fixed_id=None, discovery_policy=None):
                            nonlocal counter, episodes, used_steps, used_episodes
                            tape_role = ('trial' if phase in ('candidate_trial', 'incumbent_trial') else
                                         'evaluation' if phase in ('evaluation_after', 'evaluation_before') else phase)
                            random = rng(seed, family, cycle, tape_role, index)
                            uniforms, tape = random.random(5), random.random((5, 2))
                            world = task.begin(index % 4, cycle, uniforms)
                            initial = world.observe()
                            if discovery_policy is not None:
                                policy, policy_id = discovery_policy, f'discovery-{cycle}-{index}'
                            else:
                                policy_id = fixed_id if fixed_id is not None else route['scopes'].get(tuple(initial.tolist()), route['default'])
                                policy = policies[policy_id]
                            rows = []
                            while not world.done:
                                context = world.observe()
                                output = model(context, policy, explore=phase == 'discovery')
                                scores = output['scores'].numpy()
                                assert np.isfinite(scores).all()
                                j = len(rows)
                                options = (np.arange(2) if phase == 'discovery' and tape[j, 0] < .1 else
                                           np.flatnonzero(np.isclose(scores, scores.max(), atol=1e-6, rtol=0.)))
                                action = int(options[min(int(tape[j, 1] * len(options)), len(options) - 1)])
                                successor, facts, known, terminal = world.step(action)
                                rows.append(dict(context=context.tolist(), action_descriptor=task.actions[action].tolist(),
                                                 chosen=action, scores=scores.tolist(), successor=successor.tolist(),
                                                 facts=facts.tolist(), known=known.tolist(), terminal=bool(terminal)))
                            episodes += 1
                            counter += len(rows)
                            used_steps += len(rows)
                            used_episodes += 1
                            assert counter <= contract['budget']['per_seed_max_transitions']
                            record = dict(kind='episode', seed=seed, family=family, variant=variant, episode_id=episodes,
                                          cycle=cycle, phase=phase, case=index % 4, index=index,
                                          initial_context=initial.tolist(), policy_id=policy_id,
                                          policy_source_records=policy['count'],
                                          outcome_uniforms=uniforms.tolist(), action_tape=tape.tolist(),
                                          transitions=rows, final_facts=facts.tolist(), value=float(facts @ goal))
                            emit(record)
                            return record

                        for cycle in range(contract['cycles']):
                            for j in range(4):
                                record = execute(cycle, 'discovery', j, discovery_policy=prepare())
                                absorb(record['transitions'])
                            policies[cycle] = prepare()
                            candidate_count = policies[cycle]['count']
                            before = dict(default=routing['default'], scopes=dict(routing['scopes']))
                            new, old, contexts, trial_records = [], [], [], []
                            for j in range(8):
                                a = execute(cycle, 'candidate_trial', j, fixed_id=cycle)
                                b = execute(cycle, 'incumbent_trial', j, route=before)
                                assert a['initial_context'] == b['initial_context']
                                new.append(a['final_facts'])
                                old.append(b['final_facts'])
                                contexts.append(a['initial_context'])
                                trial_records.extend(a['transitions'])
                                trial_records.extend(b['transitions'])
                            assert model.count == candidate_count
                            after = dict(default=before['default'], scopes=dict(before['scopes']))
                            if variant in ('v203_full', 'v203_global_age'):
                                verdict = model.assess_local_trials(contexts, new, old, goal)
                                changes = sum(verdict['adopt'])
                                for context, adopt in zip(verdict['contexts'], verdict['adopt']):
                                    if adopt:
                                        after['scopes'][tuple(context)] = cycle
                            elif variant == 'v203_no_gate':
                                verdict = dict(rule='unconditional_after_equal_cost_trials', accept=True)
                                changes = len(set(map(tuple, contexts)))
                                after = dict(default=cycle, scopes={})
                            else:
                                verdict = dict(model.assess_trials(new, old, goal), rule='v202_global_2se')
                                changes = len(set(map(tuple, contexts))) if verdict['accept'] else 0
                                if verdict['accept']:
                                    after = dict(default=cycle, scopes={})
                            changed_cycles += int(changes > 0)
                            adopted_contexts += changes
                            emit(dict(kind='decision', seed=seed, family=family, variant=variant, cycle=cycle,
                                      candidate_source_records=candidate_count, contexts=contexts,
                                      candidate_actual=new, incumbent_actual=old, verdict=verdict,
                                      routing_before=route_wire(before), routing_after=route_wire(after),
                                      changed_contexts=changes))
                            # Actual complete trial records become future memory;
                            # neither heldout evaluation stream is ever absorbed.
                            absorb(trial_records)
                            current_values, old_values = [], []
                            for j in range(8):
                                a = execute(cycle, 'evaluation_after', j, route=after)
                                b = execute(cycle, 'evaluation_before', j, route=before)
                                current_values.append(a['value'])
                                old_values.append(b['value'])
                            routing = after
                            evaluations.append(current_values)
                            shadows.append(old_values)
                            assert parameter_hash(model) == origin
                            assert all(not p.requires_grad and p.grad is None for p in model.parameters())
                        row = dict(seed=seed, family=family, variant=variant, episodes=used_episodes,
                                   environment_transitions=used_steps, parameter_hash_before=origin,
                                   parameter_hash_after=parameter_hash(model), parameter_updates=0,
                                   changed_cycles=changed_cycles, adopted_contexts=adopted_contexts,
                                   memory_records_written=model.count, evaluation_values=evaluations,
                                   shadow_before_values=shadows,
                                   first4_cycles=float(np.mean(evaluations[:4])),
                                   last4_cycles=float(np.mean(evaluations[-4:])),
                                   change_first2_cycles=float(np.mean(evaluations[8:10])),
                                   whole_evaluation=float(np.mean(evaluations)),
                                   heldout_adoption_difference=float(np.mean(evaluations) - np.mean(shadows)),
                                   heldout_adoption_wins=int(np.sum(np.array(evaluations) > np.array(shadows))),
                                   heldout_adoption_losses=int(np.sum(np.array(evaluations) < np.array(shadows))),
                                   discovery_episodes=64, trial_episodes=256,
                                   evaluation_after_episodes=128, evaluation_before_episodes=128)
                        emit(dict(kind='run_end', **row))
                        results.append(row)
                        trace.flush()
                        print(json.dumps({k: row[k] for k in ('seed', 'family', 'variant', 'last4_cycles', 'adopted_contexts')}), flush=True)
        dump(HERE / 'evidence' / f'{seed}_result.json', dict(status='COMPLETE', results=results,
             episodes=episodes, environment_transitions=counter, wall_seconds=time.perf_counter() - started))
        return results
    except BaseException:
        dump(HERE / 'evidence' / f'{seed}_failure.json', dict(status='FAILED_OR_PARTIAL',
             episodes=episodes, environment_transitions=counter, completed_runs=len(results),
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
    inputs = {str((HERE / name).relative_to(ROOT)).replace('\\', '/'): sha(HERE / name)
              for name in ['model.py', 'tasks.py', 'checks.py', 'run.py', 'launch.py', 'contract.json', 'DERIVATION.md']}
    for rel in (contract['old_source'], contract['old_checkpoint']):
        inputs[rel] = sha(ROOT / rel)
    dump(out / 'claim.json', dict(started_utc=utc(), inputs=inputs, contract=contract, attempt=1))
    try:
        model = save_initial_model(out / 'initial_written.pt')
        dump(out / 'construction.json', dict(parameter_count=sum(p.numel() for p in model.parameters()),
             nonzero_parameters=sum(int(torch.count_nonzero(p)) for p in model.parameters()),
             parameter_hash=parameter_hash(model), checkpoint_sha256=sha(out / 'initial_written.pt'),
             environment_calls_before_weight_construction=0, optimizer_updates=0,
             pretrained_parameters_loaded_by_writer=0, old_source_reused_not_modified=True))
        checked = run_checks(out / 'initial_written.pt', ROOT / contract['old_checkpoint'])
        dump(out / 'checks.json', checked)
        print('Twelve synthetic checks complete; starting the predeclared new-instance matrix.', flush=True)
        with ProcessPoolExecutor(max_workers=4) as pool:
            batches = list(pool.map(worker, contract['seeds']))
        results = [row for batch in batches for row in batch]
        aggregates = []
        for family in contract['families']:
            for variant in contract['variants']:
                rows = [r for r in results if r['family'] == family and r['variant'] == variant]
                aggregate = dict(family=family, variant=variant, seeds=len(rows))
                for key in ['first4_cycles', 'last4_cycles', 'whole_evaluation', 'change_first2_cycles', 'heldout_adoption_difference']:
                    aggregate[key] = sum(r[key] for r in rows) / len(rows)
                for key in ['changed_cycles', 'adopted_contexts', 'environment_transitions', 'heldout_adoption_wins', 'heldout_adoption_losses']:
                    aggregate[key] = sum(r[key] for r in rows)
                aggregate['seed_last4'] = [r['last4_cycles'] for r in rows]
                aggregates.append(aggregate)
        assert len(results) == 320
        assert sum(r['episodes'] for r in results) == 184320
        assert sum(r['environment_transitions'] for r in results) <= 921600
        assert all(sha(ROOT / rel) == h for rel, h in inputs.items())
        result = dict(status='COMPLETE_LOCAL_WEIGHT_PROGRAM_TEST', results=results, aggregates=aggregates,
                      episodes=sum(r['episodes'] for r in results),
                      environment_transitions=sum(r['environment_transitions'] for r in results),
                      parameter_updates=0, optimizer_updates=0, sleep_calls=0, game_calls=0,
                      unchanged_inputs=inputs, checks=checked, wall_seconds=time.perf_counter() - started,
                      finished_utc=utc(), scope='Bounded repeated-condition numerical tasks; neither universal semantics nor causal identification')
        dump(out / 'result.json', result)
        print(json.dumps({k: v for k, v in result.items() if k not in ('results', 'unchanged_inputs', 'checks')}, indent=2), flush=True)
    except BaseException:
        dump(out / 'failure.json', dict(status='FAILED_OR_PARTIAL', traceback=traceback.format_exc(),
             wall_seconds=time.perf_counter() - started, finished_utc=utc()))
        raise


if __name__ == '__main__':
    main()
