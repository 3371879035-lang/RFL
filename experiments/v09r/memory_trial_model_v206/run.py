import gzip
import hashlib
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'src'))
import torch
from feedback_program_v206 import BinaryFactLearner, BudgetController, FixedEightController, digest_parameters
from tasks import run_memory_episode, run_gate_episode, public_episode, GATE_CASES


def seed_for(*values):
    return int.from_bytes(hashlib.sha256('|'.join(map(str, values)).encode()).digest()[:8], 'big')


def emit(stream, value):
    stream.write(json.dumps(value, separators=(',', ':'), allow_nan=False) + '\n')


def initial_checks():
    learner = BinaryFactLearner(slots=2)
    obs = [[0, 1, 0], [1, 0, 1], [2, 0, 0]]
    frozen = learner.snapshot()
    assert max(abs(x-.5) for x in frozen.probabilities(obs).tolist()) < 1e-12
    digest = digest_parameters(learner.net)
    receipt = learner.observe(dict(id=-1, observations=obs, action=1, outcome=1))
    assert abs(receipt['prediction']-.5) < 1e-12
    assert max(abs(x-.5) for x in frozen.probabilities(obs).tolist()) < 1e-12
    assert learner.snapshot().probabilities(obs)[1] > .5
    assert digest_parameters(learner.net) == digest
    ctrl = BudgetController()
    value, decision = ctrl.value(4, 1, (0, 0, 0, 0))
    assert abs(value - 2.08) < 1e-12 and decision == 'trial'
    means = ctrl.net.pair_means((1, 2, 3, 4))
    assert max(abs(a-b) for a, b in zip(means, (9/14, 8/14, -1/14))) < 1e-12
    return dict(status='MATCH', neural_interface_snapshot_and_posterior=True,
                finite_budget_value=value, finite_budget_choice=decision, environment_calls=0)


def main():
    started = time.perf_counter()
    cfg = json.loads((HERE / 'contract.json').read_text())
    out = HERE / 'evidence'
    out.mkdir(exist_ok=False)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    with (out / 'initial_checks.json').open('x') as f:
        json.dump(initial_checks(), f, indent=2)
    budget_controller = BudgetController(cfg['pair_cost_utility_proxy'], cfg['maximum_trial_pairs'])
    controllers = {'budget': budget_controller, 'fixed8': FixedEightController()}
    controller_hash = digest_parameters(budget_controller.net)
    with (out / 'initial_arithmetic.pt').open('xb') as f:
        torch.save(budget_controller.net.state_dict(), f)
    episodes = steps = updates = 0
    records = []
    with gzip.open(out / 'episodes.jsonl.gz', 'xt', encoding='utf-8', compresslevel=1) as raw, \
         gzip.open(out / 'updates.jsonl.gz', 'xt', encoding='utf-8', compresslevel=1) as upd, \
         gzip.open(out / 'snapshots.jsonl.gz', 'xt', encoding='utf-8', compresslevel=1) as snap, \
         (out / 'results.jsonl').open('x', encoding='utf-8') as results:
        def save(ep):
            nonlocal episodes, steps
            episodes += 1
            steps += ep['steps']
            assert episodes <= cfg['maximum_actual_episodes'] and steps <= cfg['maximum_actual_steps']
            emit(raw, ep)
            return ep

        def memory_episode(family, instance, cycle, lane, j, actor, role, rid, arm):
            return save(run_memory_episode(episodes, family, instance, cycle,
                        seed_for('context', family, instance, cycle, lane, j),
                        seed_for('outcome', family, instance, cycle, lane, j, arm), actor, role, rid))

        def ingest(learner, ep, rid):
            nonlocal updates
            emit(upd, dict(run=rid, **learner.observe(public_episode(ep))))
            updates += 1

        for family in cfg['memory_families']:
            for instance in range(cfg['memory_seeds']):
                systems = {}
                for variant, setting in cfg['variants'].items():
                    learner = BinaryFactLearner(fields=cfg['public_binary_fields'], slots=cfg['history_slots'],
                                **{k: setting[k] for k in ('recent', 'static_time', 'uniform')})
                    systems[variant] = dict(learner=learner, incumbent=None, parameter=digest_parameters(learner.net))
                shared_run = f'{family}:{instance}:shared'
                warm = []
                for j in range(cfg['shared_initial_episodes']):
                    warm.append(memory_episode(family, instance, 0, 'warm', j, lambda obs, j=j: j % 2,
                                               'warm', shared_run, 'shared'))
                for variant, system in systems.items():
                    for ep in warm:
                        ingest(system['learner'], ep, f'{family}:{instance}:{variant}')
                for cycle in range(cfg['cycles']):
                    discovery = []
                    for j in range(cfg['shared_discovery_per_cycle']):
                        discovery.append(memory_episode(family, instance, cycle, 'discovery', j, lambda obs, j=j: j % 2,
                                                        'discovery', shared_run, 'shared'))
                    for variant, system in systems.items():
                        tick = time.perf_counter()
                        rid = f'{family}:{instance}:{variant}'
                        learner, incumbent = system['learner'], system['incumbent']
                        for ep in discovery:
                            ingest(learner, ep, rid)
                        candidate = learner.snapshot()
                        emit(snap, dict(run=rid, cycle=cycle, seen=learner.seen, definitions=learner.definitions,
                                        half_lives=[None if x == float('inf') else x for x in learner.half_lives],
                                        counts=candidate.counts.tolist(), weights=candidate.weights.tolist()))
                        old_actor = incumbent.act if incumbent is not None else lambda obs: 0
                        ctrl = controllers[cfg['variants'][variant]['controller']]
                        counts, active, decisions = [0, 0, 0, 0], [], []
                        while True:
                            decision = ctrl.decide(cfg['active_budget_per_variant_cycle'], counts)
                            decisions.append(dict(counts=list(counts), decision=decision))
                            if decision != 'trial':
                                break
                            j = sum(counts)
                            old = memory_episode(family, instance, cycle, 'trial', j, old_actor, 'trial_old', rid, 'old')
                            new = memory_episode(family, instance, cycle, 'trial', j, candidate.act, 'trial_new', rid, 'new')
                            active.extend((old, new))
                            counts[2 * old['outcome'] + new['outcome']] += 1
                        adopted = decision == 'adopt'
                        deployed = candidate if adopted else incumbent
                        actor = deployed.act if deployed is not None else lambda obs: 0
                        pairs = sum(counts)
                        for j in range(cfg['active_budget_per_variant_cycle'] - 2 * pairs):
                            active.append(memory_episode(family, instance, cycle, 'deployment', j, actor, 'deployment', rid, 'deployed'))
                        evaluation = {'eval_old': [], 'eval_candidate': []}
                        for j in range(cfg['heldout_pairs_per_variant_cycle']):
                            for role, policy, arm in [('eval_old', old_actor, 'old'), ('eval_candidate', candidate.act, 'new')]:
                                evaluation[role].append(memory_episode(family, instance, cycle, 'evaluation', j, policy, role, rid, arm))
                        chosen_evaluation = evaluation['eval_candidate' if adopted else 'eval_old']
                        # Snapshot hashes verify state immutability through real trials, deployment and later ingestion.
                        before_memory = hashlib.sha256(candidate.counts.numpy().tobytes() + candidate.weights.numpy().tobytes()).hexdigest()
                        for ep in active:
                            ingest(learner, ep, rid)
                        after_memory = hashlib.sha256(candidate.counts.numpy().tobytes() + candidate.weights.numpy().tobytes()).hexdigest()
                        assert before_memory == after_memory
                        assert digest_parameters(learner.net) == system['parameter']
                        top = int(candidate.weights.flatten().argmax())
                        summary = dict(section='memory', run=rid, family=family, instance=instance, variant=variant, cycle=cycle,
                                       trial_pairs=pairs, decisions=decisions, adopted=adopted,
                                       active_ids=[e['id'] for e in active],
                                       active_gross=sum(e['outcome'] for e in active),
                                       active_net=sum(e['outcome'] for e in active)-cfg['pair_cost_utility_proxy'] * pairs,
                                       eval_old=[e['id'] for e in evaluation['eval_old']],
                                       eval_candidate=[e['id'] for e in evaluation['eval_candidate']],
                                       eval_selected=[e['id'] for e in chosen_evaluation],
                                       deployed_mean=sum(e['outcome'] for e in chosen_evaluation)/len(chosen_evaluation),
                                       candidate_mean=sum(e['outcome'] for e in evaluation['eval_candidate'])/len(chosen_evaluation),
                                       incumbent_mean=sum(e['outcome'] for e in evaluation['eval_old'])/len(chosen_evaluation),
                                       selected_law_mean=sum(e['analyst_probability'] for e in chosen_evaluation)/len(chosen_evaluation),
                                       top_definition=learner.definitions[top % learner.r], top_scale=top // learner.r,
                                       top_weight=float(candidate.weights.flatten()[top]),
                                       parameter_before=system['parameter'], parameter_after=digest_parameters(learner.net),
                                       snapshot_before=before_memory, snapshot_after=after_memory,
                                       cycle_wall_seconds=time.perf_counter()-tick)
                        emit(results, summary)
                        records.append(summary)
                        system['incumbent'] = deployed
                print(json.dumps(dict(section='memory', family=family, instance=instance, episodes=episodes,
                                      elapsed=round(time.perf_counter()-started, 2))), flush=True)
        for case in cfg['gate_cases']:
            for budget in cfg['gate_episode_budgets']:
                for instance in range(cfg['gate_seeds']):
                    for method in cfg['gate_methods']:
                        tick = time.perf_counter()
                        rid = f'{case}:{budget}:{instance}:{method}'
                        counts, active, decisions = [0, 0, 0, 0], [], []
                        ctrl = controllers[method]
                        while True:
                            decision = ctrl.decide(budget, counts)
                            decisions.append(dict(counts=list(counts), decision=decision))
                            if decision != 'trial':
                                break
                            j = sum(counts)
                            pair = []
                            for action, role in [(0, 'trial_old'), (1, 'trial_new')]:
                                pair.append(save(run_gate_episode(episodes, case,
                                    seed_for('gate', case, budget, instance, 'trial', j, action), action, role, rid)))
                            active.extend(pair)
                            counts[2 * pair[0]['outcome'] + pair[1]['outcome']] += 1
                        adopted = decision == 'adopt'
                        for j in range(budget - 2 * sum(counts)):
                            active.append(save(run_gate_episode(episodes, case,
                                seed_for('gate', case, budget, instance, 'deploy', j), int(adopted), 'deployment', rid)))
                        p0, ph = GATE_CASES[case]
                        summary = dict(section='gate', run=rid, case=case, budget=budget, instance=instance, method=method,
                                       trial_pairs=sum(counts), adopted=adopted, decisions=decisions,
                                       active_ids=[e['id'] for e in active], gross=sum(e['outcome'] for e in active),
                                       net=sum(e['outcome'] for e in active)-cfg['pair_cost_utility_proxy']*sum(counts),
                                       law_expected_total=sum(e['analyst_probability'] for e in active),
                                       harmful_adoption=bool(adopted and ph < p0),
                                       missed_gain=bool(not adopted and ph > p0),
                                       cycle_wall_seconds=time.perf_counter()-tick)
                        emit(results, summary)
                        records.append(summary)
                print(json.dumps(dict(section='gate', case=case, budget=budget, episodes=episodes,
                                      elapsed=round(time.perf_counter()-started, 2))), flush=True)
    assert digest_parameters(budget_controller.net) == controller_hash
    with gzip.open(out / 'dp_table.jsonl.gz', 'xt', encoding='utf-8') as f:
        for (budget, cap, counts), (value, decision) in budget_controller.table.items():
            emit(f, dict(budget=budget, cap=cap, counts=counts, value=value, decision=decision))
    assert episodes == cfg['maximum_actual_episodes']
    final = dict(status='EXECUTED', actual_episodes=episodes, actual_steps=steps, learning_update_events=updates,
                 result_rows=len(records), dp_states=len(budget_controller.table),
                 controller_parameter_before=controller_hash, controller_parameter_after=digest_parameters(budget_controller.net),
                 optimizer_steps=0, parameters_changed=False, wall_seconds=time.perf_counter()-started)
    with (HERE / 'native_result.json').open('x') as f:
        json.dump(final, f, indent=2)
    print(json.dumps(final), flush=True)


if __name__ == '__main__':
    main()
