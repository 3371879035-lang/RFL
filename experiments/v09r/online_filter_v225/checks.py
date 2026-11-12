from dataclasses import asdict, replace
import math
import torch
from feedback_program_v225 import filtering
from feedback_program_v225.losses import sequence_nll
from feedback_program_v224.imagination import noise_tape, thought_record


def gradients(model, loss):
    named = list(model.named_parameters())
    gs = torch.autograd.grad(loss, [p for _, p in named], allow_unused=True, retain_graph=True)
    nonzero = []; groups = {}; finite = True
    for (name, _), g in zip(named, gs):
        if g is None: continue
        finite = finite and bool(torch.isfinite(g).all())
        norm = float(g.double().square().sum().sqrt())
        groups[name.split('.')[0]] = groups.get(name.split('.')[0], 0.)+norm
        if norm: nonzero.append(name)
    return dict(finite=finite, nonzero_tensors=len(nonzero), nonzero_names=nonzero, groups=groups)


def run_checks(model, agent, trace, credit, seed):
    results = {}; diagnostic = {}; bank = agent.bank
    p = next(model.parameters()); tensor = lambda x: torch.as_tensor(x, dtype=p.dtype, device=p.device)
    receipts = {r['event_id']: r for r in trace['filter_receipts']}
    by_episode = {}
    for event in bank.events: by_episode.setdefault(event.episode, []).append(event.id)
    def check(name, function):
        try: results[name] = dict(passed=True, **function())
        except Exception as error: results[name] = dict(passed=False, error=type(error).__name__+': '+str(error))

    @torch.no_grad()
    def temporal_alignment():
        max_nll = max_joint = max_forecast = max_logw = max_segment = 0.; h_matches = 0; scored = 0
        for ids in by_episode.values():
            loss, details = sequence_nll(model, bank, ids)
            online = -sum(receipts[i]['log_predictive'] for i in ids)
            max_nll = max(max_nll, abs(float(loss)-online))
            max_joint = max(max_joint, abs(float(loss-details['direct_joint_nll'])))
            for eid, before, terms in zip(ids, details['pre_states'], details['terms']):
                e = bank.events[bank.index[eid]]; recorded = receipts[eid]
                state = filtering.state_record(before)
                assert state['anchor_ids'] == recorded['before']['anchor_ids'] and state['used_ids'] == recorded['before']['used_ids']
                h_matches += state['h_sha256'] == recorded['before']['h_sha256']
                max_logw = max(max_logw, max(abs(a-b) for a, b in zip(state['log_weights'], recorded['before']['log_weights'])))
                output = model(tensor([e.observation]), tensor([e.goal]), tensor([e.actions]), bank.forecast_view(e.previous_id, bank.index[eid]))
                diff = (output['feedback_prediction'][0, e.action_index]-tensor(e.predicted_feedback)).abs().max()
                max_forecast = max(max_forecast, float(diff)); scored += 1
                assert abs(float(terms['log_predictive'])-recorded['log_predictive']) < 1e-6
            if len(ids) >= 3:
                head, _ = sequence_nll(model, bank, ids[:2])
                tail, middle = sequence_nll(model, bank, ids[2:])
                max_segment = max(max_segment, abs(float(loss-head-tail)))
                assert list(middle['pre_consumed_ids']) == ids[:2]
        assert max_nll < 1e-6 and max_joint < 1e-6 and max_segment < 1e-6
        assert max_forecast < 3e-6 and max_logw < 1e-9
        return dict(actual_events_compared=scored, complete_episode_count=len(by_episode),
            nll_online_vs_training_max=max_nll, joint_vs_filtering_nll_max=max_joint, conditional_middle_nll_max=max_segment,
            online_vs_rebuilt_prediction_max=max_forecast, log_posterior_max=max_logw, exact_pre_state_h_matches=h_matches,
            actual_filter_updates=trace['actual_filter_updates'])
    check('online_full_and_middle_training_are_one_conditioning_model', temporal_alignment)

    @torch.no_grad()
    def reset_gap():
        rows = []
        for episode in trace['episodes']:
            for eid in episode['source_ids']:
                event = bank.events[bank.index[eid]]; stop = bank.index[eid]
                obs = tensor([event.observation]); goal = tensor([event.goal]); actions = tensor([event.actions])
                proper = model(obs, goal, actions, bank.forecast_view(event.previous_id, stop))
                # This is the formerly used reset formula on NEW facts, not an old native rerun.
                reset = filtering.start(model, obs, goal, bank.view(stop))
                alternate = model(obs, goal, actions, bank.view(stop), belief=reset)
                ll, _, _ = filtering.component_likelihood(model, reset, event)
                logz = torch.logsumexp(reset.log_weights+ll, -1)
                rows.append(dict(event_id=eid, step=event.step,
                    next_prediction_max=float((proper['next_prediction']-alternate['next_prediction']).abs().max()),
                    feedback_prediction_max=float((proper['feedback_prediction']-alternate['feedback_prediction']).abs().max()),
                    log_predictive_delta=float(logz)-receipts[eid]['log_predictive']))
        starts = [r for r in rows if r['step'] == 0]; later = [r for r in rows if r['step'] > 0]
        assert all(r['next_prediction_max'] == 0. and abs(r['log_predictive_delta']) < 1e-10 for r in starts)
        gap = max(r['next_prediction_max'] for r in later)
        assert gap > 1e-6
        return dict(new_actual_prefix_comparisons=rows, reset_later_next_prediction_max=gap,
                    first_step_matches=True, performance_comparison=False, actual_environment_calls=0)
    check('formerly_resetting_formula_has_measurable_conditioning_gap', reset_gap)

    @torch.no_grad()
    def once_and_confidence():
        prior = torch.tensor([.5, .5], dtype=torch.float64).log()
        first, _ = filtering.posterior_update(prior, torch.tensor([.9, .1], dtype=torch.float64).log())
        second, _ = filtering.posterior_update(first, torch.tensor([.1, .9], dtype=torch.float64).log())
        entropy = lambda lp: float(-(lp.exp()*lp).sum())
        assert torch.allclose(first.exp(), torch.tensor([.9, .1], dtype=torch.float64))
        assert torch.allclose(second.exp(), prior.exp()) and entropy(first) < entropy(prior) and entropy(second) > entropy(first)
        ids = trace['episodes'][0]['source_ids']; _, data = sequence_nll(model, bank, ids)
        e = bank.events[bank.index[ids[0]]]; already = data['pre_states'][1]
        rejected = False
        try: filtering.observe(model, already, e)
        except ValueError as error: rejected = 'already been consumed' in str(error)
        assert rejected
        terminal_rejected = False
        try:
            filtering.require_query(model, data['final_state'], tensor([data['final_state'].expected_observation.tolist()]),
                                    tensor([e.goal]), data['final_state'].anchor_ids+data['final_state'].used_ids)
        except ValueError as error: terminal_rejected = 'terminated' in str(error)
        assert terminal_rejected
        up = down = 0
        for receipt in trace['filter_receipts']:
            before = receipt['before']; after = receipt['after']
            assert not (set(before['anchor_ids']) & set(before['used_ids']))
            assert after['used_ids'] == before['used_ids']+[receipt['event_id']]
            assert after['anchor_ids'] == before['anchor_ids']
            a = -sum(math.exp(v)*v for v in before['log_weights']); b = -sum(math.exp(v)*v for v in after['log_weights'])
            up += b > a+1e-12; down += b < a-1e-12
        assert len({r['event_id'] for r in trace['filter_receipts']}) == len(bank.events)
        return dict(duplicate_same_event_rejected=True, terminated_chain_continuation_rejected=True,
            toy_posteriors=[prior.exp().tolist(), first.exp().tolist(), second.exp().tolist()],
            toy_entropies=[entropy(prior), entropy(first), entropy(second)],
            actual_entropy_increases=up, actual_entropy_decreases=down,
            actual_updates=len(trace['filter_receipts']), reference_current_evidence_overlap=0,
            calibrated_confidence_claim=False)
    check('unique_evidence_and_bidirectional_posterior', once_and_confidence)

    def real_gradients():
        world_loss, world_details = sequence_nll(model, bank, trace['episodes'][-1]['source_ids'])
        world = gradients(model, world_loss); policy = gradients(model, credit['zero_baseline_losses'][1])
        critic = gradients(model, credit['critic_losses'][0])
        assert world['finite'] and policy['finite'] and critic['finite']
        assert all(n.split('.')[0] in model.WORLD_GROUPS for n in world['nonzero_names'])
        assert all(n.split('.')[0] not in model.WORLD_GROUPS and not n.startswith('critic') for n in policy['nonzero_names'])
        assert all(n.startswith(('critic.', 'critic_phase.')) for n in critic['nonzero_names'])
        for key in ('belief_update', 'mixture_head', 'memory_blocks'): assert world['groups'][key] > 0.
        for key in ('proposal_net', 'policy_reader', 'policy_context', 'actor'): assert policy['groups'][key] > 0.
        assert abs(float(world_loss-world_details['direct_joint_nll'])) < 1e-6
        return dict(world_nll=float(world_loss), world=world, actual_cost_policy=policy, actual_target_critic=critic,
                    replay_errors=credit['errors'], actual_goal_and_cost_returns=credit['targets'][0].tolist(), cross_route_leaks=0)
    check('real_credit_and_recurrent_world_gradients_remain_connected', real_gradients)

    @torch.no_grad()
    def imagination_boundary():
        ids = trace['episodes'][-1]['source_ids']; event = bank.events[bank.index[ids[3]]]
        output = model(tensor([event.observation]), tensor([event.goal]), tensor([event.actions]),
                       bank.forecast_view(event.previous_id, bank.index[event.id]))
        before = filtering.state_record(output['_belief']); factual = bank.to_json()
        codes = torch.cat((model.base_code[None, None], model.propose(output)), 1)
        tape = noise_tape(2259000+seed, 2, model.config.hypotheses, model.schema.observation, model.innovations, 4)
        thought = model.dream(output, codes, tape)
        assert torch.equal(thought['root_weights'], output['_belief'].log_weights.exp().to(p.dtype))
        assert filtering.state_record(output['_belief']) == before and bank.to_json() == factual
        assert before['used_ids'] == ids[:3]
        foreign = replace(output['_belief'], world_id='diagnostic_different_world')
        rejected = False
        try:
            filtering.require_query(model, foreign, tensor([event.observation]), tensor([event.goal]), bank.view(bank.index[event.id])['ids'])
        except ValueError as error: rejected = 'different world version' in str(error)
        assert rejected
        diagnostic.update(thought=thought_record(thought), source_event_id=event.id, actual_conditioning=before,
                          imagined_nodes=len(thought['nodes']), particle_rows=thought['allocated_particle_rows'])
        return dict(real_predecessors_consumed=len(before['used_ids']), imagined_nodes=len(thought['nodes']),
            allocated_particle_rows=thought['allocated_particle_rows'], actual_state_and_memory_unchanged=True,
            world_version_mismatch_rejected=True, actual_environment_calls=0)
    check('imagination_starts_from_actual_belief_without_becoming_evidence', imagination_boundary)
    return results, diagnostic
