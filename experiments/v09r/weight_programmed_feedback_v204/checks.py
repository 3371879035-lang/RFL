"""Synthetic interface/mechanism checks; these are not world performance tests."""
import hashlib
import torch
from feedback_program_v204 import Config, FeedbackNet, load_model, write_initial_weights


def parameter_hash(model):
    h = hashlib.sha256()
    for name, value in model.state_dict().items():
        h.update(name.encode())
        h.update(value.detach().numpy().tobytes())
    return h.hexdigest()


@torch.inference_mode()
def run_checks(checkpoint):
    m = load_model(checkpoint).eval().requires_grad_(False)
    original = parameter_hash(m)
    actions, goal = torch.eye(6)[:2], torch.tensor([1., 0., 0.])
    c, nxt = torch.zeros(6), torch.ones(6)
    first = m.observe_transition(c, actions[0], nxt, True, [1., 0., .5], [True] * 3)
    assert first['source_records_before'] == 0 and first['pre_observation_losses'] == [[.25, .25, 0.], [.25, .25, 0.]]
    for _ in range(39):
        m.observe_transition(c, actions[0], nxt, True, [1., 0., .5], [True] * 3)
    frozen = m.prepare(actions, goal, link_successors=False)
    prediction = m(c, frozen)
    assert torch.allclose(prediction['expert_probabilities'].sum(-1), torch.ones(2))
    assert torch.all(prediction['outcome_variance'] >= 0)
    before = prediction['scores'].clone()
    unchanged = m.observe_transition(c, actions[0], nxt, True, [999., 999., 999.], [False] * 3)
    assert not unchanged['loss_known']
    assert torch.equal(before, m(c, frozen)['scores'])
    for _ in range(16):
        m.observe_transition(c, actions[0], nxt, True, [0., 1., .5], [True] * 3)
    changed = m(c, m.prepare(actions, goal, link_successors=False))
    assert changed['expert_probabilities'][0, 0] > prediction['expert_probabilities'][0, 0]
    assert changed['objective'][0] < prediction['objective'][0]
    # A new numerical context receives locally supported actual trial evidence.
    prepared = dict(minimum=torch.zeros(12), scale=torch.ones(12))
    contexts = torch.stack([torch.full((6,), v) for v in [.48, .49, .51, .52]])
    old, new = torch.zeros(4, 3), torch.zeros(4, 3)
    new[:, 0] = 1.
    evidence = m.assess_local_trials(contexts, new, old, goal, prepared)
    nearby = m.trial_decision(torch.full((6,), .5), evidence)
    far = m.trial_decision(torch.full((6,), 2.), evidence)
    assert nearby['adopt'] and not far['adopt']
    negative = m.assess_local_trials(contexts, old, new, goal, prepared)
    assert not m.trial_decision(torch.full((6,), .5), negative)['adopt']
    snapshot = m.memory_state()
    duplicate = load_model(checkpoint).eval().requires_grad_(False)
    duplicate.restore_memory(snapshot)
    assert torch.equal(changed['scores'], duplicate(c, duplicate.prepare(actions, goal, link_successors=False))['scores'])
    alternate = write_initial_weights(FeedbackNet(Config(context_dim=4, action_dim=3, fact_dim=2, capacity=12, planning_depth=2)))
    result = alternate(torch.ones(4), alternate.prepare(torch.eye(3), torch.tensor([1., 0.])))
    assert result['scores'].shape == (3,) and torch.isfinite(result['scores']).all()
    assert original == parameter_hash(m) == parameter_hash(duplicate)
    return dict(status='COMPLETE_SYNTHETIC_INTERFACE_CHECKS', checks=10, environment_calls=0,
                parameter_hash=original, nearby_adoption=nearby, far_adoption=far,
                expert_probability_before=prediction['expert_probabilities'][0].tolist(),
                expert_probability_after=changed['expert_probabilities'][0].tolist(),
                memory_roundtrip_exact=True, alternate_dimensions=[4, 3, 2])
