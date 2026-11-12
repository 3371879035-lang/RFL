"""Bounded fresh-instance test of a portable frozen-parameter feedback model."""
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
sys.path.insert(0, str(ROOT / 'src'))


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


def load_legacy(path):
    spec = importlib.util.spec_from_file_location('v204_legacy_control', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def worker(seed):
    import numpy as np
    import torch
    from feedback_program_v204 import load_model
    from tasks import Task
    torch.set_num_threads(1)
    contract = json.loads((HERE / 'contract.json').read_text(encoding='utf-8'))
    legacy = load_legacy(ROOT / contract['old_source'])
    goal = np.array([1., 0., 0.], np.float32)
    counter, episodes, results = 0, 0, []
    started = time.perf_counter()

    def rng(*parts):
        digest = hashlib.sha256(('v204|' + '|'.join(map(str, parts))).encode()).digest()
        return np.random.default_rng(int.from_bytes(digest[:8], 'little'))

    try:
        with gzip.open(HERE / 'evidence' / f'{seed}.jsonl.gz', 'xt', encoding='utf-8', compresslevel=3) as trace:
            def emit(data):
                trace.write(json.dumps(data, separators=(',', ':'), allow_nan=False) + '\n')

            with torch.inference_mode():
                for family in contract['families']:
                    for variant in contract['variants']:
                        task = Task(seed, family)
                        is_legacy = variant == 'v203_original'
                        model = (legacy.load_model(ROOT / contract['old_checkpoint']) if is_legacy else
                                 load_model(HERE / 'evidence/initial_written.pt', adaptive=variant != 'v204_fixed_age'))
                        model.eval().requires_grad_(False)
                        origin = parameter_hash(model)
                        prepare = lambda: model.prepare(task.actions, goal)
                        policies, nodes = {-1: prepare()}, []
                        counts = dict(episodes=0, steps=0, memory_updates=0)
                        evaluations, shadows, starts = [], [], []
                        adoption_queries, adopted_queries = 0, 0

                        def select(initial, route):
                            checks = []
                            for node in reversed(route):
                                if node['kind'] == 'all':
                                    decision = dict(adopt=True)
                                elif node['kind'] == 'exact':
                                    decision = dict(adopt=tuple(initial.tolist()) in node['scopes'])
                                else:
                                    decision = model.trial_decision(initial, node['evidence'])
                                checks.append(dict(policy_id=node['policy_id'], **decision))
                                if decision['adopt']:
                                    return node['policy_id'], checks
                            return -1, checks

                        def execute(cycle, phase, index, route=None, fixed_id=None, discovery_policy=None):
                            nonlocal counter, episodes
                            group = ('trial' if phase.endswith('_trial') else
                                     'evaluation' if phase.startswith('evaluation_') else phase)
                            initial_uniforms = rng(seed, family, cycle, group, index, 'initial').random(2)
                            tape = rng(seed, family, cycle, group, index, 'tie').random((5, 2))
                            noise_role = phase if phase.endswith('_trial') else group
                            uniforms = rng(seed, family, cycle, noise_role, index, 'outcome').random(5)
                            world = task.begin(index % 4, cycle, uniforms, initial_uniforms)
                            initial = world.observe()
                            if discovery_policy is not None:
                                policy, policy_id, route_checks = discovery_policy, f'discovery-{cycle}-{index}', []
                            else:
                                policy_id, route_checks = (fixed_id, []) if fixed_id is not None else select(initial, route)
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
                                row = dict(context=context.tolist(), action_descriptor=task.actions[action].tolist(),
                                           chosen=action, scores=scores.tolist(), successor=successor.tolist(),
                                           facts=facts.tolist(), known=known.tolist(), terminal=bool(terminal))
                                if not is_legacy:
                                    row['expert_probabilities'] = output['expert_probabilities'].tolist()
                                rows.append(row)
                            episodes += 1
                            counter += len(rows)
                            counts['episodes'] += 1
                            counts['steps'] += len(rows)
                            assert counter <= contract['budget']['per_seed_max_transitions']
                            record = dict(kind='episode', seed=seed, family=family, variant=variant, episode_id=episodes,
                                          cycle=cycle, phase=phase, case=index % 4, index=index, initial_context=initial.tolist(),
                                          initial_uniforms=initial_uniforms.tolist(), outcome_uniforms=uniforms.tolist(),
                                          action_tape=tape.tolist(), policy_id=policy_id, route_checks=route_checks,
                                          policy_source_records=policy['count'], transitions=rows,
                                          final_facts=facts.tolist(), value=float(facts @ goal))
                            starts.append(tuple(initial.tolist()))
                            emit(record)
                            return record

                        def absorb(records):
                            ingest = []
                            for record in records:
                                before = model.count
                                last = None
                                for row in record['transitions']:
                                    last = model.observe_transition(row['context'], row['action_descriptor'], row['successor'],
                                                                    row['terminal'], row['facts'], row['known'])
                                entry = dict(episode_id=record['episode_id'], source_records_before=before,
                                             source_records_after=model.count)
                                if not is_legacy:
                                    entry['terminal_prediction_receipt'] = last
                                ingest.append(entry)
                                counts['memory_updates'] += len(record['transitions'])
                            emit(dict(kind='ingest', seed=seed, family=family, variant=variant, records=ingest,
                                      source_records_after=model.count))

                        for cycle in range(contract['cycles']):
                            for j in range(4):
                                record = execute(cycle, 'discovery', j, discovery_policy=prepare())
                                absorb([record])
                            policies[cycle] = prepare()
                            source_count = model.count
                            before = list(nodes)
                            new, old, contexts, trials = [], [], [], []
                            for j in range(16):
                                a = execute(cycle, 'candidate_trial', j, fixed_id=cycle)
                                b = execute(cycle, 'incumbent_trial', j, route=before)
                                assert a['initial_context'] == b['initial_context']
                                assert a['outcome_uniforms'] != b['outcome_uniforms']
                                new.append(a['final_facts'])
                                old.append(b['final_facts'])
                                contexts.append(a['initial_context'])
                                trials.extend((a, b))
                            assert model.count == source_count
                            after = list(before)
                            if variant in ('v204_full', 'v204_fixed_age'):
                                evidence = model.assess_local_trials(contexts, new, old, goal, policies[cycle])
                                after.append(dict(kind='kernel', policy_id=cycle, evidence=evidence))
                                verdict = dict(rule='kernel_supported_actual_trials',
                                               minimum=evidence['minimum'].tolist(), scale=evidence['scale'].tolist(),
                                               differences=evidence['differences'].tolist())
                            elif variant == 'v204_no_gate':
                                after.append(dict(kind='all', policy_id=cycle))
                                verdict = dict(rule='unconditional_after_equal_cost_trials')
                            else:
                                if variant == 'v204_exact_gate':
                                    scope = np.unique(np.array(contexts, np.float32), axis=0)
                                    match = np.all(scope[:, None, :] == np.array(contexts, np.float32)[None, :, :], axis=-1).astype(np.float32)
                                    count = match.sum(-1)
                                    difference = (np.array(new, np.float32) - np.array(old, np.float32)) @ goal
                                    estimate = (match @ difference) / (1. + count)
                                    verdict = dict(rule='v203_exact_scope_formula', contexts=scope.tolist(),
                                                   counts=count.tolist(), estimates=estimate.tolist(),
                                                   adopt=((count >= 2.) & (estimate > 0.)).tolist())
                                else:
                                    verdict = model.assess_local_trials(contexts, new, old, goal)
                                scopes = {tuple(c) for c, adopt in zip(verdict['contexts'], verdict['adopt']) if adopt}
                                after.append(dict(kind='exact', policy_id=cycle, scopes=scopes))
                            emit(dict(kind='decision', seed=seed, family=family, variant=variant, cycle=cycle,
                                      source_records=source_count, contexts=contexts, candidate_actual=new,
                                      incumbent_actual=old, verdict=verdict))
                            absorb(trials)
                            current_values, old_values = [], []
                            for j in range(8):
                                a = execute(cycle, 'evaluation_after', j, route=after)
                                b = execute(cycle, 'evaluation_before', j, route=before)
                                current_values.append(a['value'])
                                old_values.append(b['value'])
                                adoption_queries += 1
                                adopted_queries += int(a['policy_id'] == cycle)
                            evaluations.append(current_values)
                            shadows.append(old_values)
                            nodes = after
                            assert parameter_hash(model) == origin
                            assert all(not p.requires_grad and p.grad is None for p in model.parameters())
                        row = dict(seed=seed, family=family, variant=variant, episodes=counts['episodes'],
                                   environment_transitions=counts['steps'], memory_records_written=counts['memory_updates'],
                                   parameter_hash_before=origin, parameter_hash_after=parameter_hash(model),
                                   evaluation_values=evaluations, shadow_before_values=shadows,
                                   first4_cycles=float(np.mean(evaluations[:4])), last4_cycles=float(np.mean(evaluations[-4:])),
                                   change_first2_cycles=float(np.mean(evaluations[8:10])), whole_evaluation=float(np.mean(evaluations)),
                                   heldout_adoption_difference=float(np.mean(evaluations) - np.mean(shadows)),
                                   heldout_adoption_wins=int(np.sum(np.array(evaluations) > np.array(shadows))),
                                   heldout_adoption_losses=int(np.sum(np.array(evaluations) < np.array(shadows))),
                                   adopted_queries=adopted_queries, adoption_queries=adoption_queries,
                                   unique_initial_contexts=len(set(starts)), initial_context_records=len(starts))
                        emit(dict(kind='run_end', **row))
                        results.append(row)
                        trace.flush()
                        print(json.dumps({k: row[k] for k in ('seed', 'family', 'variant', 'last4_cycles', 'change_first2_cycles', 'adopted_queries')}), flush=True)
        dump(HERE / 'evidence' / f'{seed}_result.json', dict(status='COMPLETE', results=results,
             episodes=episodes, environment_transitions=counter, wall_seconds=time.perf_counter() - started))
        return results
    except BaseException:
        dump(HERE / 'evidence' / f'{seed}_failure.json', dict(status='FAILED_OR_PARTIAL', episodes=episodes,
             environment_transitions=counter, completed_runs=len(results), traceback=traceback.format_exc(),
             wall_seconds=time.perf_counter() - started))
        raise


def main():
    import torch
    from feedback_program_v204 import save_initial_model
    from checks import run_checks
    torch.set_num_threads(1)
    out = HERE / 'evidence'
    out.mkdir(exist_ok=False)
    started = time.perf_counter()
    contract = json.loads((HERE / 'contract.json').read_text(encoding='utf-8'))
    paths = [HERE / p for p in ['run.py', 'tasks.py', 'checks.py', 'launch.py', 'contract.json', 'DERIVATION.md']]
    paths += list((ROOT / contract['source_package']).glob('*.py'))
    paths += [ROOT / contract[p] for p in ['old_source', 'old_base_source', 'old_checkpoint']]
    inputs = {str(p.relative_to(ROOT)).replace('\\', '/'): sha(p) for p in paths}
    dump(out / 'claim.json', dict(started_utc=utc(), attempt=1, inputs=inputs, contract=contract))
    try:
        model = save_initial_model(out / 'initial_written.pt')
        dump(out / 'construction.json', dict(parameter_count=sum(p.numel() for p in model.parameters()),
             nonzero_parameters=sum(int(torch.count_nonzero(p)) for p in model.parameters()),
             parameter_hash=parameter_hash(model), checkpoint_sha256=sha(out / 'initial_written.pt'),
             environment_calls_before_weight_construction=0, pretrained_parameters_loaded_by_writer=0,
             optimizer_updates=0, portable_source_independent_of_experiments=True))
        checked = run_checks(out / 'initial_written.pt')
        dump(out / 'checks.json', checked)
        print('New interface checks complete; starting fixed V204 matrix.', flush=True)
        with ProcessPoolExecutor(max_workers=4) as pool:
            batches = list(pool.map(worker, contract['seeds']))
        results = [row for batch in batches for row in batch]
        aggregates = []
        for family in contract['families']:
            for variant in contract['variants']:
                rows = [r for r in results if r['family'] == family and r['variant'] == variant]
                a = dict(family=family, variant=variant, seeds=len(rows))
                for key in ['first4_cycles', 'last4_cycles', 'change_first2_cycles', 'whole_evaluation', 'heldout_adoption_difference']:
                    a[key] = sum(r[key] for r in rows) / len(rows)
                for key in ['environment_transitions', 'heldout_adoption_wins', 'heldout_adoption_losses', 'adopted_queries', 'adoption_queries']:
                    a[key] = sum(r[key] for r in rows)
                a['seed_last4'] = [r['last4_cycles'] for r in rows]
                a['seed_change_first2'] = [r['change_first2_cycles'] for r in rows]
                aggregates.append(a)
        assert len(results) == 400
        assert sum(r['episodes'] for r in results) == contract['budget']['total_episodes']
        assert sum(r['environment_transitions'] for r in results) <= contract['budget']['max_transitions']
        assert all(sha(ROOT / p) == h for p, h in inputs.items())
        result = dict(status='COMPLETE_LOCAL_GENERAL_NUMERIC_FEEDBACK_TEST', results=results, aggregates=aggregates,
                      episodes=sum(r['episodes'] for r in results), environment_transitions=sum(r['environment_transitions'] for r in results),
                      parameter_updates=0, optimizer_updates=0, game_calls=0, unchanged_inputs=inputs,
                      checks=checked, wall_seconds=time.perf_counter() - started, finished_utc=utc(),
                      goal_status='ACTIVE_NOT_UNIVERSAL_MODEL_COMPLETION')
        dump(out / 'result.json', result)
        print(json.dumps({k: v for k, v in result.items() if k not in ('results', 'aggregates', 'unchanged_inputs', 'checks')}, indent=2), flush=True)
    except BaseException:
        dump(out / 'failure.json', dict(status='FAILED_OR_PARTIAL', traceback=traceback.format_exc(),
             wall_seconds=time.perf_counter() - started, finished_utc=utc()))
        raise


if __name__ == '__main__':
    main()
