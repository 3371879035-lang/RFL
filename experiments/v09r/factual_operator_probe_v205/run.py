"""One bounded execution of the preregistered diagnostic contract, no optimizer."""
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
from feedback_program_v205 import FactNet, FactMemory, Policy, parameter_digest
from tasks import rollout, conditional_expected_return


def seed_for(*parts):
    return int.from_bytes(hashlib.sha256('|'.join(map(str, parts)).encode()).digest()[:8], 'big')


def append(stream, item):
    stream.write(json.dumps(item, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n')


def operator_checks():
    net = FactNet(2)
    keys = torch.tensor([[1., 10000.0001]], dtype=torch.float64)
    got = float(net.kernel((1., 10000.), keys)[0])
    import math
    expected = math.exp(-16. * (10000. - 10000.0001) ** 2)
    assert abs(got - expected) < 1e-14
    row = dict(context=(0., 0.), successor=(1., 0.), action=0, x=(0., 0.),
               known=(False, True), terminal=True, legal_next=(), episode='synthetic_operator_only', step=0)
    policy = Policy(net, [row], 0, (1., -1.))
    _, mask = policy.values((0., 0.), (0,))
    assert mask.tolist() == [[False, True]]
    missing_mask = mask.tolist()
    clean = dict(row, known=(True, True), x=(1., .2))
    source = [clean]
    frozen = Policy(net, source, 0, (1., -1.))
    source[0]['x'] = (0., 5.)
    assert frozen.rows[0]['x'] == (1., .2)
    value, mask = frozen.values((0., 0.), (0,))
    assert value.tolist() == [[1., .2]] and mask.all()
    return dict(new_operator_checks=3, status='MATCH', environment_episodes=0,
                direct_difference_abs_error=abs(got - expected), missing_mask=missing_mask,
                note='New neural arithmetic/mask/snapshot checks; not reruns of the stored algebra script.')


def main():
    start = time.perf_counter()
    cfg = json.loads((HERE / 'contract.json').read_text(encoding='utf-8'))
    out = HERE / 'evidence'
    out.mkdir(exist_ok=False)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    (out / 'operator_checks.json').write_text(json.dumps(operator_checks(), indent=2), encoding='utf-8')
    episodes = steps = prediction_count = nonterminal_losses = 0
    results = []
    with gzip.open(out / 'episodes.jsonl.gz', 'xt', encoding='utf-8', compresslevel=1) as raw, \
         gzip.open(out / 'pre_observation.jsonl.gz', 'xt', encoding='utf-8', compresslevel=1) as pre, \
         gzip.open(out / 'model_queries.jsonl.gz', 'xt', encoding='utf-8', compresslevel=1) as queries:
        def execute(family, seed, cycle, cue, actor, role, rid):
            nonlocal episodes, steps
            ep = rollout(family, seed, cycle, cue, actor, episodes, role, rid)
            episodes += 1
            steps += len(ep['steps'])
            assert episodes <= cfg['maximum_actual_episodes'] and steps <= cfg['maximum_actual_steps']
            append(raw, ep)
            return ep

        for family in cfg['families']:
            for seed in range(cfg['seeds']):
                systems = {}
                for variant, setting in cfg['variants'].items():
                    window = setting['window']
                    net = FactNet(2 + 3 * window, beta=cfg['beta'], gamma=cfg['gamma'])
                    netfile = out / ('initial_dim_%d.pt' % net.dim)
                    if not netfile.exists():
                        with netfile.open('xb') as f:
                            torch.save(net.state_dict(), f)
                    systems[variant] = dict(net=net, memory=FactMemory(net, window, setting['terminal_only']),
                                            incumbent=None, parameter_before=parameter_digest(net))
                for cycle in range(cfg['cycles']):
                    discovery = []
                    for j in range(cfg['discovery_episodes_per_seed_family_cycle_shared_across_variants']):
                        actor = lambda obs, previous, legal, j=j: legal[j % len(legal)]
                        discovery.append(execute(family, seed_for(seed, family, cycle, 'discovery', j), cycle,
                                                 (j // 3) % 2, actor, 'discovery', f'{family}:{seed}:shared'))
                    for variant, setting in cfg['variants'].items():
                        variant_started = time.perf_counter()
                        system = systems[variant]
                        net, memory, incumbent = system['net'], system['memory'], system['incumbent']
                        rid = f'{family}:{seed}:{variant}'
                        for ep in discovery:
                            memory.ingest(ep)
                        candidate = memory.snapshot(cfg['goal'], cfg['depth'], setting['mean_successor'])
                        prior_actor = incumbent.act if incumbent is not None else lambda obs, previous, legal: legal[0]
                        trial_data, diffs, expected_diffs, factual_diffs = [], [], [], []
                        for j in range(cfg['fresh_actual_trial_pairs_per_variant_cycle']):
                            pair = []
                            for role, actor in [('trial_incumbent', prior_actor), ('trial_candidate', candidate.act)]:
                                ep = execute(family, seed_for(seed, family, cycle, role, j), cycle, j % 2, actor, role, rid)
                                pair.append(ep)
                                trial_data.append(ep)
                            diffs.append(pair[1]['utility'] - pair[0]['utility'])
                            expected_diffs.append(conditional_expected_return(pair[1]) - conditional_expected_return(pair[0]))
                            factual_diffs.append([a - b for a, b in zip(pair[1]['facts'], pair[0]['facts'])])
                        goal = torch.tensor(cfg['goal'], dtype=torch.float64)
                        neural_diffs = net.utility(torch.tensor(factual_diffs, dtype=torch.float64), goal).tolist()
                        assert all(abs(a - b) < 1e-12 for a, b in zip(neural_diffs, diffs))
                        estimate = sum(neural_diffs) / (len(neural_diffs) + 1.)
                        adopted = estimate > 0.
                        chosen = candidate if adopted else incumbent
                        deployed_actor = chosen.act if chosen is not None else lambda obs, previous, legal: legal[0]
                        evaluation = {'eval_incumbent': [], 'eval_deployed': []}
                        expected_eval = {'eval_incumbent': [], 'eval_deployed': []}
                        for j in range(cfg['heldout_actual_eval_pairs_per_variant_cycle']):
                            for role, actor in [('eval_incumbent', prior_actor), ('eval_deployed', deployed_actor)]:
                                ep = execute(family, seed_for(seed, family, cycle, role, j), cycle, j % 2, actor, role, rid)
                                evaluation[role].append(ep['utility'])
                                expected_eval[role].append(conditional_expected_return(ep))
                        # Capture computed model queries separately: none are actual environment records.
                        for (context, legal, depth), (values, known) in candidate.cache.items():
                            append(queries, dict(run=rid, cycle=cycle, context=context, legal=legal, depth=depth,
                                                 factual=values.tolist(), known=known.tolist()))
                        # Newly observed actual trials enter only future candidates, after this frozen comparison.
                        snapshot_rows_before = tuple(candidate.rows)
                        for ep in trial_data:
                            memory.ingest(ep)
                        assert candidate.rows == snapshot_rows_before
                        parameter_after = parameter_digest(net)
                        assert parameter_after == system['parameter_before']
                        for record in memory.prediction_records:
                            append(pre, dict(run=rid, cycle=cycle, **record))
                            prediction_count += 1
                            nonterminal_losses += int(not record['terminal'] and any(x is not None for x in record['loss']))
                        memory.prediction_records.clear()
                        result = dict(run=rid, family=family, seed=seed, variant=variant, cycle=cycle,
                                      candidate_mean_trial=sum(ep['utility'] for ep in trial_data if ep['role'] == 'trial_candidate') / len(diffs),
                                      incumbent_mean_trial=sum(ep['utility'] for ep in trial_data if ep['role'] == 'trial_incumbent') / len(diffs),
                                      trial_differences=diffs, estimate=estimate, adopted=adopted,
                                      analyst_expected_trial_delta=sum(expected_diffs) / len(expected_diffs),
                                      evaluation=evaluation, analyst_expected_eval=expected_eval,
                                      parameter_before=system['parameter_before'], parameter_after=parameter_after,
                                      parameters=sum(p.numel() for p in net.parameters()),
                                      live_rows=len(memory.rows), snapshot_rows=len(candidate.rows),
                                      variant_cycle_wall_seconds=time.perf_counter() - variant_started,
                                      unknown_fallbacks=candidate.unknown_action_fallbacks)
                        results.append(result)
                        with (out / 'progress.jsonl').open('a', encoding='utf-8') as stream:
                            append(stream, result)
                        system['incumbent'] = chosen
                print(json.dumps(dict(family=family, seed=seed, episodes=episodes, steps=steps,
                                      seconds=round(time.perf_counter() - start, 2))), flush=True)
    summary = dict(status='EXECUTED', results=len(results), actual_episodes=episodes, actual_steps=steps,
                   prediction_records=prediction_count, nonterminal_prediction_loss_records=nonterminal_losses,
                   optimizer_steps=0, parameters_changed=False, wall_seconds=time.perf_counter() - start,
                   independent_seed_ids=cfg['seeds'], families=len(cfg['families']), variants=len(cfg['variants']))
    with (HERE / 'native_result.json').open('x', encoding='utf-8') as stream:
        json.dump(summary, stream, indent=2)
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
