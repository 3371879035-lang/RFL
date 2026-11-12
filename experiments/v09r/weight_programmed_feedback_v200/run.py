"""First finite experiment. All hidden task tables stay outside FeedbackNet."""
import ast
import datetime as dt
import gzip
import hashlib
import json
import pathlib
import time
import traceback
import numpy as np
import torch
from model import Config, FeedbackNet, load_model, save_initial_model, write_initial_weights

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / 'evidence'


def dump(path, obj):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(obj, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parameter_hash(model):
    h = hashlib.sha256()
    for name, value in model.state_dict().items():
        h.update(name.encode())
        h.update(value.detach().numpy().tobytes())
    return h.hexdigest()


@torch.inference_mode()
def checks(checkpoint):
    m = load_model(checkpoint)
    context, actions, goal = np.eye(6, dtype=np.float32)[0], np.eye(6, dtype=np.float32)[:4], np.array([1., 0., 0.], np.float32)
    origin = parameter_hash(m)
    assert all(torch.isfinite(p).all() for p in m.parameters())
    fresh = load_model(checkpoint)
    assert torch.equal(m(context, actions, goal)['scores'], fresh(context, actions, goal)['scores'])
    for _ in range(4):
        m.observe(context, actions[0], [0., 1., 0.5])
        m.observe(context, actions[1], [1., 0., 0.5])
        m.observe(context, actions[2], [0., 0., 0.5])
        m.observe(context, actions[3], [0., 0., 0.5])
    original = m(context, actions, goal)
    assert int(original['scores'].argmax()) == 1
    assert int(m(context, actions, np.array([0., 1., 0.], np.float32))['scores'].argmax()) == 0
    perm = [2, 0, 3, 1]
    assert torch.allclose(m(context, actions[perm], goal)['scores'], original['scores'][perm], atol=1e-6)
    # Isotropic matching must not depend on arbitrary coordinate names.
    permutation = np.array([4, 2, 0, 5, 3, 1])
    relabeled = load_model(checkpoint)
    for _ in range(4):
        for a, y in [(0, [0., 1., .5]), (1, [1., 0., .5]), (2, [0., 0., .5]), (3, [0., 0., .5])]:
            relabeled.observe(context[permutation], actions[a][permutation], y)
    assert torch.allclose(relabeled(context[permutation], actions[:, permutation], goal)['scores'], original['scores'], atol=1e-6)
    missing = load_model(checkpoint)
    missing.observe(context, actions[0], [0., float('nan'), 1.], [True, False, True])
    p = missing(context, actions, goal)['prediction']
    assert p[0, 1] == .5 and p[0, 0] < .01
    assert parameter_hash(m) == origin == parameter_hash(relabeled) == parameter_hash(missing)
    assert m.count == 16 and fresh.count == 0
    tree = ast.parse((HERE/'model.py').read_text(encoding='utf-8'))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split('.')[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module.split('.')[0])
    assert imports == {'dataclasses', 'math', 'torch'}
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                   and node.func.attr in ('backward', 'step', 'fit') for node in ast.walk(tree))
    return dict(status='PASS_LIMITED_ENGINEERING_CHECKS', checks=8,
                feedback_preferred_action=1, changed_goal_preferred_action=0,
                missing_fact_prediction=float(p[0, 1]), parameter_hash=origin,
                optimizer_steps=0, no_old_model_or_environment_imports=True)


def select(scores, legal, uniform, tie):
    allowed = np.flatnonzero(legal)
    if uniform < .1:
        return int(allowed[min(len(allowed)-1, int(tie * len(allowed)))])
    best = allowed[np.isclose(scores[allowed], scores[allowed].max(), rtol=0., atol=1e-6)]
    return int(best[min(len(best)-1, int(tie * len(best)))])


def make_world(seed, family, rounds):
    # Seeds create engineering instances, never fitted writer weights.
    rng = np.random.default_rng(seed)
    ctx = np.eye(6, dtype=np.float32)[:4]
    actions = np.eye(6, dtype=np.float32)[:4]
    order = rng.permutation(4)
    means = np.full((4, 4, 3), .2, np.float32)
    for c in range(4):
        means[c, order[c], 0] = .8 if family == 'noisy_context' else 1.
        if family != 'noisy_context':
            means[c, :, 0] = (np.arange(4) == order[c]).astype(np.float32)
        means[c, :, 1] = np.array([.2, .4, .6, .8])
        means[c, :, 2] = .5
    if family == 'changed_goal':
        means[:] = np.array([[1., 0., .5], [0., 1., .5], [.55, .55, .75], [.3, .3, .95]], np.float32)
    if family == 'continuous_context':
        actions = np.zeros((4, 6), np.float32)
        actions[:, :2] = np.array([[1, 1], [1, -1], [-1, 1], [-1, -1]], np.float32) / np.sqrt(2.)
    return dict(contexts=ctx, actions=actions, means=means,
                contexts_tape=rng.integers(0, 4, rounds),
                continuous_tape=rng.uniform(-1, 1, (rounds, 2)).astype(np.float32),
                outcomes=rng.random((rounds, 4, 3)),
                exploration=rng.random((rounds, 2)), permutations=np.array([rng.permutation(4) for _ in range(rounds)]))


@torch.inference_mode()
def episode_run(checkpoint, seed, family, variant, rounds, trace, counter):
    world = make_world(seed, family, rounds)
    if variant == 'random_untrained':
        torch.manual_seed(seed)
        model = FeedbackNet()
    else:
        model = load_model(checkpoint)
    start_hash = parameter_hash(model)
    rows = []
    for t in range(rounds):
        if variant == 'written_no_history':
            model.clear_memory()
        ci = int(world['contexts_tape'][t])
        context = world['contexts'][ci].copy()
        goal = np.array([1., 0., 0.], np.float32)
        expected = world['means'][ci].copy()
        action_features = world['actions']
        if family == 'changed_dynamics' and t >= rounds // 2:
            expected = np.roll(expected, 1, axis=0)
        if family == 'changed_goal' and t >= rounds // 2:
            goal = np.array([0., 1., 0.], np.float32)
        if family == 'continuous_context':
            context[:] = 0
            context[:2] = world['continuous_tape'][t]
            expected[:, 0] = (1 + action_features[:, :2] @ context[:2] / np.sqrt(2.)) / 2
        if family == 'delayed_credit':
            context = np.array([0., 0., 0., 0., 1., 0.], np.float32)
            goal = np.array([0., 1., 0.], np.float32)
            action_features = np.eye(6, dtype=np.float32)[:2]
            permutation = np.array([0, 1])
        else:
            permutation = world['permutations'][t]
        descriptors = action_features[permutation]
        result = model(context, descriptors, goal)
        scores = result['scores'].numpy()
        assert np.isfinite(scores).all()
        selected = select(scores, np.ones(len(scores), bool), *world['exploration'][t])
        action = int(permutation[selected])
        predicted = result['prediction'][selected].numpy()
        if family == 'delayed_credit':
            # No final-outcome label is supplied for the first decision.
            observed = np.array([float(action == 0), 0., 1.], np.float32)
            known = np.array([True, False, True])
            model.observe(context, action_features[action], observed, known)
            terminal_context = np.array([0., 0., 0., 0., 0., 1. if action else -1.], np.float32)
            terminal = np.array([0., float(action == 1), 1.], np.float32)
            model.observe(terminal_context, action_features[0], terminal)
            measured = float(terminal[1])
            oracle, regret, optimal = 1., 1.-measured, action == 1
            counter[0] += 2
            terminal_wire = terminal.tolist()
        else:
            if family in ('noisy_context', 'continuous_context'):
                observed = (world['outcomes'][t, action] < expected[action]).astype(np.float32)
            else:
                observed = expected[action]
            known = np.ones(3, bool)
            model.observe(context, action_features[action], observed, known)
            measured = float(observed @ goal)
            candidate_values = expected @ goal
            oracle = float(candidate_values.max())
            regret = oracle - float(candidate_values[action])
            optimal = bool(np.isclose(candidate_values[action], oracle))
            counter[0] += 1
            terminal_wire = None
        row = dict(seed=seed, family=family, variant=variant, round=t,
                   context=context.tolist(), goal=goal.tolist(), action=action,
                   action_descriptor=action_features[action].tolist(), action_order=permutation.tolist(),
                   scores=scores.tolist(), prediction=predicted.tolist(),
                   observed_facts=observed.tolist(), known=known.tolist(), terminal_facts=terminal_wire,
                   measured_goal=measured, oracle_expected=oracle, expected_regret=regret,
                   optimal=bool(optimal), stored_records=model.count)
        trace.write(json.dumps(row, separators=(',', ':'), allow_nan=False)+'\n')
        rows.append(row)
        assert counter[0] <= 50000
    assert parameter_hash(model) == start_hash
    def window(start, end):
        data = rows[start:end]
        return dict(n=len(data), observed=float(np.mean([r['measured_goal'] for r in data])),
                    optimal=float(np.mean([r['optimal'] for r in data])),
                    regret=float(np.mean([r['expected_regret'] for r in data])))
    return dict(seed=seed, family=family, variant=variant, parameter_hash=start_hash,
                weights_unchanged=True, initial=window(0, 64), final=window(rounds-64, rounds),
                after_change_early=window(rounds//2, rounds//2+32),
                after_change_late=window(rounds-32, rounds), whole=window(0, rounds))


def main():
    OUT.mkdir(exist_ok=False)
    started = time.perf_counter()
    contract = json.loads((HERE/'contract.json').read_text(encoding='utf-8'))
    pins = {name: sha(HERE/name) for name in ['model.py', 'run.py', 'launch.py', 'contract.json']}
    dump(OUT/'claim.json', dict(started_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                              inputs=pins, limits=contract['budget']))
    counter = [0]
    results = []
    try:
        torch.set_num_threads(1)
        checkpoint = OUT/'initial_written.pt'
        model = save_initial_model(checkpoint)
        dump(OUT/'construction.json', dict(parameter_count=sum(p.numel() for p in model.parameters()),
             nonzero_parameters=sum(int(torch.count_nonzero(p)) for p in model.parameters()),
             parameter_hash=parameter_hash(model), checkpoint_sha256=sha(checkpoint),
             optimizer_steps=0, forward_passes_before_construction=0, source_checkpoints_read=0,
             environment_calls_before_construction=0, memory_records=0,
             architecture='parameterized two-timescale attention memory with goal-conditioned readout'))
        checked = checks(checkpoint)
        dump(OUT/'checks.json', checked)
        print('Construction and 8 limited checks complete.', flush=True)
        with gzip.open(OUT/'raw.jsonl.gz', 'xt', encoding='utf-8', newline='\n') as trace:
            for family in contract['families']:
                for seed in contract['seeds']:
                    for variant in contract['variants']:
                        results.append(episode_run(checkpoint, seed, family, variant, contract['rounds_per_run'], trace, counter))
                print('Completed family:', family, 'elapsed:', round(time.perf_counter()-started, 2), flush=True)
        aggregates = []
        for family in contract['families']:
            for variant in contract['variants']:
                data = [r for r in results if r['family']==family and r['variant']==variant]
                aggregate = dict(family=family, variant=variant, seeds=len(data))
                for period in ['initial', 'final', 'whole', 'after_change_early', 'after_change_late']:
                    aggregate[period] = {key: float(np.mean([r[period][key] for r in data])) for key in ['observed', 'optimal', 'regret']}
                aggregate['seed_final_observed'] = [r['final']['observed'] for r in data]
                aggregates.append(aggregate)
        changed = [name for name, digest in pins.items() if sha(HERE/name) != digest]
        assert not changed
        dump(OUT/'result.json', dict(status='COMPLETED_LOCAL_PROTOTYPE',
             started_inputs=pins, changed_inputs=changed, checks=checked, results=results, aggregates=aggregates,
             task_runs=len(results), task_rounds=len(results)*contract['rounds_per_run'],
             environment_transitions=counter[0], optimizer_steps=0,
             trained_pure_feedback_baseline_runs=0, old_rfl_calls=0,
             wall_seconds=time.perf_counter()-started,
             limitation='Experience updates memory, not weights; controls are not trained baselines; delayed credit is absent.'))
        dump(OUT/'finish.json', dict(status='COMPLETE', finished_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
             wall_seconds=time.perf_counter()-started, environment_transitions=counter[0]))
    except BaseException:
        dump(OUT/'failure.json', dict(status='FAILED_OR_PARTIAL', environment_transitions=counter[0],
             completed_runs=len(results), wall_seconds=time.perf_counter()-started, traceback=traceback.format_exc()))
        raise


if __name__ == '__main__':
    main()
