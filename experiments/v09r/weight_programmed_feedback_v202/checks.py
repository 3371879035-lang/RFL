"""Synthetic algebra/interface checks, not environment samples or score tuning."""
import ast
import hashlib
from pathlib import Path
import torch
from model import load_model


def parameter_hash(model):
    h = hashlib.sha256()
    for name, value in model.state_dict().items():
        h.update(name.encode())
        h.update(value.detach().numpy().tobytes())
    return h.hexdigest()


@torch.inference_mode()
def run_checks(checkpoint):
    base = load_model(checkpoint).eval().requires_grad_(False)
    origin = parameter_hash(base)
    c, a, goal = torch.eye(6), torch.eye(6)[:2], torch.tensor([1., 0., 0.])
    empty = base(c[0], base.prepare(a, goal))
    assert torch.allclose(empty['objective'], torch.full((2,), .5))
    assert torch.allclose(empty['outcome_variance'], torch.full((2,), 1. / 12.), atol=1e-6)
    assert torch.equal(empty['scores'], load_model(checkpoint)(c[0], load_model(checkpoint).prepare(a, goal))['scores'])
    records = []
    for _ in range(8):
        records += [(c[0], a[0], c[1], False, [0., 0., 0.], [False] * 3),
                    (c[0], a[1], c[2], False, [0., 0., 0.], [False] * 3)]
        for action in a:
            records += [(c[1], action, c[3], True, [0., 1., .5], [True] * 3),
                        (c[2], action, c[3], True, [1., 0., .5], [True] * 3)]
    for record in records:
        base.observe_transition(*record)
    linked = base(c[0], base.prepare(a, goal))
    unlinked = base(c[0], base.prepare(a, goal, link_successors=False))
    assert linked['scores'][1] > linked['scores'][0] + .4
    assert torch.allclose(unlinked['scores'], torch.full((2,), .5), atol=1e-5)
    switched = base(c[0], base.prepare(a, torch.tensor([0., 1., 0.])))
    assert switched['scores'][0] > switched['scores'][1] + .4
    permuted = base(c[0], base.prepare(a.flip(0), goal))
    assert torch.allclose(permuted['scores'].flip(0), linked['scores'], atol=1e-5)

    # Same real-shaped synthetic data under a changed numerical coordinate unit.
    rescaled = load_model(checkpoint).eval().requires_grad_(False)
    permutation = torch.tensor([3, 0, 5, 1, 4, 2])
    scale, shift = torch.tensor([2., 3., 4., 5., 6., 7.]), torch.tensor([7., -3., 1., 2., -1., 4.])
    transform = lambda x: (x * scale + shift)[..., permutation]
    for context, action, successor, terminal, facts, known in records:
        rescaled.observe_transition(transform(context), transform(action), transform(successor), terminal, facts, known)
    relabeled = rescaled(transform(c[0]), rescaled.prepare(transform(a), goal))
    assert torch.allclose(relabeled['scores'], linked['scores'], atol=1e-4)

    missing = load_model(checkpoint)
    missing.observe_transition(c[0], a[0], c[1], True, [float('nan'), 1., .5], [False, True, True])
    unknown = missing(c[0], missing.prepare(a, goal))
    assert torch.equal(unknown['objective'], torch.full((2,), .5))
    noise, stable = load_model(checkpoint), load_model(checkpoint)
    for j in range(48):
        y = float(j % 2)
        noise.observe_transition(c[0], a[0], c[1], True, [y, 1. - y, .5], [True] * 3)
        stable.observe_transition(c[0], a[0], c[1], True, [1., 0., .5], [True] * 3)
    noisy = noise(c[0], noise.prepare(a, goal))
    certain = stable(c[0], stable.prepare(a, goal))
    assert noisy['support'][0] > .95
    assert noisy['outcome_variance'][0] > .2 and certain['outcome_variance'][0] < .03
    assert noisy['epistemic_proxy'][0] < .1
    # Anticorrelated facts should not acquire independent additive variances.
    joint = noise(c[0], noise.prepare(a, torch.tensor([.5, .5, 0.])))
    assert joint['outcome_variance'][0] < .01
    better = base.assess_trials([[1., 0., .5]] * 8, [[0., 1., .5]] * 8, goal)
    worse = base.assess_trials([[0., 1., .5]] * 8, [[1., 0., .5]] * 8, goal)
    equal = base.assess_trials([[1., 0., .5]] * 8, [[1., 0., .5]] * 8, goal)
    too_short = base.assess_trials([[1., 0., .5]] * 7, [[0., 1., .5]] * 7, goal)
    assert better['accept'] and not worse['accept'] and not equal['accept'] and not too_short['accept']
    assert all(parameter_hash(m) == origin for m in (base, rescaled, missing, noise, stable))
    tree = ast.parse((Path(__file__).parent / 'model.py').read_text(encoding='utf-8'))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(a.name.split('.')[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module.split('.')[0])
    assert imports == {'dataclasses', 'math', 'torch'}
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                   and node.func.attr in ('backward', 'fit', 'step') for node in ast.walk(tree))
    return dict(status='PASS_LIMITED_SYNTHETIC_CHECKS', checks=12, environment_calls=0,
                parameter_hash=origin, linked_scores=linked['scores'].tolist(),
                unlinked_scores=unlinked['scores'].tolist(),
                noisy_variance=float(noisy['outcome_variance'][0]),
                stable_variance=float(certain['outcome_variance'][0]),
                noisy_epistemic_proxy=float(noisy['epistemic_proxy'][0]),
                paired_gate_examples=dict(better=better, worse=worse, equal=equal, too_short=too_short))
