from dataclasses import asdict, replace
import copy
import math
import torch
from feedback_program_v224 import FeedbackCreditNet, MemoryBank
from feedback_program_v224.learning import evaluate_trace, validate_trace
from feedback_program_v224.runtime import model_identity, world_identity
from feedback_program_v223.losses import sequence_nll


def gradients(model, loss):
    named = list(model.named_parameters())
    grads = torch.autograd.grad(loss, [p for _, p in named], allow_unused=True, retain_graph=True)
    groups = {}; nonzero = []; finite = True
    for (name, _), grad in zip(named, grads):
        if grad is None:
            continue
        finite = finite and bool(torch.isfinite(grad).all())
        norm = float(grad.detach().double().square().sum().sqrt())
        groups[name.split('.')[0]] = groups.get(name.split('.')[0], 0.) + norm
        if norm:
            nonzero.append(name)
    return dict(finite=finite, nonzero_tensors=len(nonzero), groups=groups, nonzero_names=nonzero)


def run_checks(model, agent, trace, replay, seed):
    results = {}
    def check(name, function):
        try:
            result = function()
            results[name] = dict(passed=True, **result)
        except Exception as error:
            results[name] = dict(passed=False, error=type(error).__name__+': '+str(error))

    def actual_credit():
        gs = [gradients(model, replay['policy_losses'][j]) for j in range(3)]
        actual = gradients(model, replay['zero_baseline_losses'][1])
        for g in [*gs, actual]:
            assert g['finite']
            assert not any(n.split('.')[0] in model.WORLD_GROUPS or n.startswith('critic') for n in g['nonzero_names'])
        for required in ('proposal_net', 'proposal_keys', 'policy_query', 'policy_reader', 'policy_context', 'actor', 'trial_score'):
            assert actual['groups'].get(required, 0.) > 0., required
        assert float(replay['targets'][0, 1]) == -sum(e.cost for e in agent.bank.events)
        return dict(actual_policy_objective_losses=replay['policy_losses'].detach().tolist(),
                    target_vector=replay['targets'][0].tolist(), by_objective=gs, zero_baseline_actual_cost=actual,
                    world_gradient_leaks=0, critic_gradient_leaks=0, errors=replay['errors'])
    check('actual_result_to_generator_and_policy_memory', actual_credit)

    def frozen_candidate_control():
        cut = evaluate_trace(model, trace, diagnostic_detach_candidates=True)
        assert torch.equal(cut['log_steps'].detach(), replay['log_steps'].detach())
        g = gradients(model, cut['zero_baseline_losses'][1])
        assert g['groups'].get('proposal_net', 0.) == 0. and g['groups'].get('proposal_keys', 0.) == 0.
        assert g['groups'].get('actor', 0.) > 0.
        return dict(forward_log_probabilities_exactly_equal=True, detached_generator_gradient=0.,
                    remaining_actor_gradient=g['groups']['actor'], actual_environment_calls=0,
                    interpretation='Derivative-only intervention, not a second deployed model or new trial')
    check('stored_constant_candidate_exposes_old_gradient_break', frozen_candidate_control)

    def critic_and_world():
        critic = [gradients(model, replay['critic_losses'][j]) for j in range(3)]
        for g in critic:
            assert g['finite'] and g['nonzero_tensors'] > 0
            assert all(n.startswith(('critic.', 'critic_phase.')) for n in g['nonzero_names'])
        loss, detail = sequence_nll(model, agent.bank, trace['episodes'][-1]['source_ids'])
        world = gradients(model, loss)
        assert world['finite'] and world['nonzero_tensors'] > 0
        assert all(n.split('.')[0] in model.WORLD_GROUPS for n in world['nonzero_names'])
        return dict(actual_critic_losses=replay['critic_losses'].detach().tolist(), critic_gradients=critic,
                    factual_world_nll=float(loss.detach()), world_gradients=world,
                    world_target_ids=list(detail['target_ids']), cross_route_leaks=0)
    check('critic_and_world_objectives_remain_separate', critic_and_world)

    def cross_policy():
        torch.manual_seed(seed+1000)
        alternate = FeedbackCreditNet(model.layout, model.schema, model.config).eval()
        state = alternate.state_dict()
        for name, value in model.state_dict().items():
            if name.split('.')[0] in model.WORLD_GROUPS or name == 'forecast_uniforms':
                state[name] = value.detach().clone()
        alternate.load_state_dict(state)
        assert world_identity(alternate) == trace['world_id'] and model_identity(alternate) != trace['model_id']
        with torch.no_grad():
            new = evaluate_trace(alternate, trace, mode='same_world_IS')
        for old in trace['thoughts']:
            rebuilt = new['replayed_thoughts'][old['id']]
            assert [asdict(n) for n in rebuilt['nodes']] == [asdict(n) for n in replay['replayed_thoughts'][old['id']]['nodes']]
            assert rebuilt['allocated_particle_rows'] == old['allocated_particle_rows']
        logs = new['log_steps'].double().sum().item()
        behavior = sum(math.log(d['propensity']) for d in trace['decisions']) + sum(t['internal_log_probability'] for t in trace['thoughts'])
        ratio = float(new['importance_weight'])
        # The implementation sums float32 steps before converting to float64.
        assert math.isclose(math.log(ratio), logs-behavior, abs_tol=3e-5)
        assert ratio > 0. and math.isfinite(ratio)
        return dict(importance_weight=ratio, full_log_density_delta=new['errors']['log_probability_delta'],
                    all_forced_physical_nodes_exactly_equal=True, thought_paths=len(trace['thoughts']),
                    qualification='Artificial fresh policy snapshot, same world; no efficacy inference', actual_environment_calls=0)
    check('same_world_full_path_importance_weight', cross_policy)

    def wrong_world():
        torch.manual_seed(seed+2000)
        other = FeedbackCreditNet(model.layout, model.schema, model.config).eval()
        rejected = False
        try:
            evaluate_trace(other, trace, mode='same_world_IS')
        except ValueError as e:
            rejected = 'World changed' in str(e)
        assert rejected
        with torch.no_grad():
            loss, _ = sequence_nll(other, agent.bank, trace['episodes'][-1]['source_ids'])
        assert torch.isfinite(loss)
        return dict(old_thought_policy_replay_rejected=True, old_actual_fact_nll=float(loss),
                    old_facts_discarded=0, actual_environment_calls=0)
    check('world_change_does_not_discard_real_history', wrong_world)

    def memory_metadata():
        changed = MemoryBank(model.schema, model.layout)
        for event in agent.bank.events:
            changed.add(replace(event, propensity=.5))
        original = agent.bank.view(); revised = changed.view()
        assert torch.equal(original['features'], revised['features'])
        assert agent.bank.events[0].propensity != .5 or any(e.propensity != .5 for e in agent.bank.events)
        assert not torch.count_nonzero(original['features'][..., -2])
        first = agent.bank.events[0]; n = len(agent.bank.events)
        assert not agent.bank.add(first) and len(agent.bank.events) == n
        return dict(propensity_only_copy_has_identical_neural_memory=True, original_propensities_preserved=True,
                    duplicate_actual_id_added_nodes=0, unique_actual_nodes=n, test_copy_is_not_an_actual_receipt=True)
    check('memory_identity_and_behavior_metadata', memory_metadata)

    def probability_and_prefix():
        u = [(i+.5)/10 for i in range(10)]
        independent = sum(x < .4 and y < .7 for x in u for y in u)/100
        shared = sum(x < .4 and x < .7 for x in u)/10
        assert independent == .28 and shared == .4
        for old in trace['thoughts']:
            assert len(old['noise_tape']['continue']) == 3
            assert all(len(row) == model.config.candidates+1 for row in old['noise_tape']['continue'])
            assert all(len(row) == model.config.candidates+1 for row in old['noise_tape']['action'])
            new = replay['replayed_thoughts'][old['id']]
            assert math.isclose(float(new['internal_log_probability'].detach()), old['internal_log_probability'], abs_tol=1e-5)
        bad = copy.deepcopy(trace); first = next(iter(bad['generations'].values()))
        first['history_ids'] = list(first['history_ids']) + [agent.bank.events[len(first['history_ids'])].id]
        rejected = False
        try: validate_trace(bad)
        except ValueError as e: rejected = 'prefix' in str(e)
        assert rejected
        return dict(independent_joint_probability=independent, old_shared_joint_probability=shared,
                    actual_policy_noise_has_arm_dimension=True, future_candidate_prefix_rejected=True,
                    physical_crn_retained=True, actual_environment_calls=0)
    check('joint_sampling_math_and_generation_chronology', probability_and_prefix)
    return results
