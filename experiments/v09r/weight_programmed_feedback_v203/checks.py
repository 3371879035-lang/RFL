"""Finite synthetic checks for new mechanisms; no environment execution."""
import hashlib
import math
import torch
from model import BASE, load_model


def parameter_hash(model):
    h = hashlib.sha256()
    for name, value in model.state_dict().items():
        h.update(name.encode())
        h.update(value.detach().numpy().tobytes())
    return h.hexdigest()


@torch.inference_mode()
def run_checks(checkpoint, old_checkpoint):
    m = load_model(checkpoint).eval().requires_grad_(False)
    old = BASE.load_model(old_checkpoint).eval().requires_grad_(False)
    origin = parameter_hash(m)
    assert all(torch.equal(v, m.state_dict()[k]) for k, v in old.state_dict().items())
    c, a, goal = torch.eye(6), torch.eye(6)[:2], torch.tensor([1., 0., 0.])
    contexts = torch.stack([c[j] for j in range(4) for _ in range(2)])
    incumbent = torch.zeros(8, 3)
    candidate = incumbent.clone()
    candidate[:2, 0] = 1.
    global_verdict = old.assess_trials(candidate, incumbent, goal)
    local = m.assess_local_trials(contexts, candidate, incumbent, goal)
    assert not global_verdict['accept'] and sum(local['adopt']) == 1
    selected = next(x for x, adopt in zip(local['contexts'], local['adopt']) if adopt)
    assert selected == c[0].tolist()
    incumbent[2:4, 0] = 1.
    mixed = m.assess_local_trials(contexts, candidate, incumbent, goal)
    assert sum(mixed['adopt']) == 1
    negative = next(i for i, x in enumerate(mixed['contexts']) if x == c[1].tolist())
    assert not mixed['adopt'][negative] and mixed['raw_mean_differences'][negative] == -1.
    perm = torch.tensor([7, 2, 0, 6, 1, 5, 3, 4])
    reordered = m.assess_local_trials(contexts[perm], candidate[perm], incumbent[perm], goal)
    assert reordered['contexts'] == mixed['contexts'] and reordered['adopt'] == mixed['adopt']
    short = m.assess_local_trials(contexts[:1], candidate[:1], incumbent[:1], goal)
    assert short['counts'] == [1.] and short['adopt'] == [False]
    equal = m.assess_local_trials(contexts, incumbent, incumbent, goal)
    assert not any(equal['adopt'])

    # Matched evidence, not unrelated elapsed clock, defines the new age.
    query = torch.cat((c[0], a[0]))[None, :]
    memory = query.expand(3, -1).clone()
    extra = torch.cat((c[1], a[1]))[None, :].expand(100, -1)
    zero, one = torch.zeros(12), torch.ones(12)
    before = m._weights(query, memory, zero, one, torch.tensor([2., 1., 0.]))
    after = m._weights(query, torch.cat((memory, extra)), zero, one, torch.arange(102, -1, -1).float())
    assert torch.allclose(before, after[:, :3], atol=1e-6, rtol=0.)
    global_before = old._weights(query, memory, zero, one, torch.tensor([2., 1., 0.]))
    global_after = old._weights(query, torch.cat((memory, extra)), zero, one, torch.arange(102, -1, -1).float())
    assert global_after[0, 0] < global_before[0, 0] * .9
    nine = query.expand(9, -1).clone()
    half = m._weights(query, nine, zero, one, torch.arange(8, -1, -1).float())
    assert abs(float(half[0, 0] / half[0, -1]) - .5) < 1e-6
    for j in range(24):
        y = float(j < 16)
        for net in (m, old):
            net.observe_transition(c[0], a[0], c[2], True, [y, 1. - y, .5], [True] * 3)
    current = m(c[0], m.prepare(a, goal, link_successors=False))
    prior = old(c[0], old.prepare(a, goal, link_successors=False))
    assert current['objective'][0] + .15 < prior['objective'][0]

    frozen = m.prepare(a, goal)
    original = m(c[0], frozen)['scores'].clone()
    m.observe_transition(c[0], a[0], c[2], True, [1., 0., .5], [True] * 3)
    assert torch.equal(original, m(c[0], frozen)['scores'])
    # A genuinely unobserved initial condition cannot match any adoption scope.
    assert not any(torch.equal(c[5], torch.tensor(x)) for x in mixed['contexts'])
    assert parameter_hash(m) == origin
    reloaded = load_model(checkpoint)
    assert parameter_hash(reloaded) == origin and reloaded.count == 0
    return dict(status='PASS_LIMITED_SYNTHETIC_CHECKS', checks=12, environment_calls=0,
                inherited_v202_parameters_exact=True, parameter_hash=origin,
                global_rejected_local_improvement=global_verdict,
                scoped_improvement_and_regression=mixed,
                conditional_half_life_ratio=float(half[0, 0] / half[0, -1]),
                prediction_after_synthetic_change=dict(conditional=float(current['objective'][0]),
                                                       global_age=float(prior['objective'][0])),
                unrelated_evidence_does_not_age_matching_records=True,
                snapshot_predictions_unchanged_after_new_observation=True)
