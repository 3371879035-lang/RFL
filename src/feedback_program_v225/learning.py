"""V224 credit with V225 actual-episode conditioning; no environment execution."""
import hashlib
import json
import math
import torch
from .memory import MemoryBank
from .runtime import PHASES, model_identity, world_identity


def validate_trace(trace):
    if trace['format'] != 'V225_CLOSED_ACTUAL_TRACE' or not trace['closed'] or trace['initial_history_ids']:
        raise ValueError('Full-trajectory credit requires a closed trace from empty initial memory')
    bank = MemoryBank.from_json(json.dumps(trace['memory']))
    sessions = {s['id']: s for s in trace['sessions']}
    thoughts = {t['id']: t for t in trace['thoughts']}
    seen = []; used_thoughts = []; activated = set(); adopted = set()
    active_origin = {'kind': 'base'}; pending = None
    for sid, s in sessions.items():
        g = trace['generations'][sid]; n = len(g['history_ids'])
        if list(g['history_ids']) != list(bank.index)[:n] or n != bank.index[s['source_event_id']]+1:
            raise ValueError('Candidate generation must use the original failure prefix')
        source = bank.events[n-1]
        if source.goal_met or not source.terminal or g['source_event_id'] != source.id:
            raise ValueError('Reflection source is not an observed terminal failure')
        if g['model_id'] != trace['model_id'] or s['model_id'] != trace['model_id']:
            raise ValueError('Generation model mismatch')
        for arm in s['arms']:
            raw = {k: v for k, v in arm.items() if k != 'digest'}
            if hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest() != arm['digest']:
                raise ValueError('Stored code digest mismatch')
            if arm['source_event_id'] != source.id or list(arm['history_ids']) != list(g['history_ids']):
                raise ValueError('Candidate source mismatch')
        receipt_ids = [r['event_id'] for r in s['receipts']]
        if len(receipt_ids) != len(set(receipt_ids)):
            raise ValueError('A real trial cannot count twice')
        for r in s['receipts']:
            arm = s['arms'][r['arm']]; event = bank.events[bank.index[r['event_id']]]
            if (r['session_id'] != sid or r['candidate_digest'] != arm['digest'] or r['candidate_id'] != arm['id']
                or event.candidate_id != arm['id'] or event.role != 'trial' or r['model_id'] != trace['model_id']):
                raise ValueError('Actual practice ownership mismatch')

    def origin(sid, arm):
        return trace['generations'][sid]['baseline_origin'] if arm == 0 else dict(kind='proposal', session_id=sid, arm=arm)

    for dec in trace['decisions']:
        if list(dec['history_ids']) != seen or dec['model_id'] != trace['model_id']:
            raise ValueError('Decision reads future/missing history or another model version')
        kind = dec['kind']; sid = dec.get('session_id')
        choice = dec['action'] if kind in ('task', 'trial') else dec['choice']
        if not math.isclose(sum(dec['policy']), 1., abs_tol=1e-6) or dec['propensity'] != dec['policy'][choice] or dec['propensity'] <= 0:
            raise ValueError('Behavior probability mismatch')
        if pending is not None and (kind != 'trial' or (sid, dec['arm']) != pending):
            raise ValueError('Trial choice lacks its immediate actual trial')
        if kind in ('task', 'trial'):
            event = bank.events[len(seen)]
            if dec['event_id'] != event.id or event.action_index != choice or event.propensity != dec['propensity'] or event.role != kind:
                raise ValueError('Action receipt mismatch')
            if kind == 'trial':
                if pending is None:
                    raise ValueError('Unselected trial')
                expected_origin = origin(sid, dec['arm'])
                s = sessions[sid]; source = bank.events[bank.index[s['source_event_id']]]
                if (event.observation, event.goal, event.actions) != (source.observation, source.goal, source.actions):
                    raise ValueError('Trial is not the declared actual context')
                if sum(r['event_id'] == event.id for r in s['receipts']) != 1:
                    raise ValueError('Missing trial receipt')
                pending = None
            else:
                expected_origin = active_origin
                if dec['purpose'] not in ('source', 'post_choice'):
                    raise ValueError('Unknown task purpose')
            if dec['code_origin'] != expected_origin:
                raise ValueError('Actual control origin mismatch')
            seen.append(event.id)
        else:
            if kind not in ('trial_choice', 'adoption') or sid in adopted:
                raise ValueError('Invalid or already closed practice decision')
            s = sessions[sid]; g = trace['generations'][sid]
            if sid not in activated:
                if list(g['history_ids']) != seen or g['baseline_origin'] != active_origin:
                    raise ValueError('Candidate creation was shifted after seeing new evidence')
                activated.add(sid)
            groups = [[] for _ in s['arms']]
            for r in s['receipts']:
                if r['event_id'] in seen:
                    groups[r['arm']].append(r['event_id'])
            if [list(x) for x in dec['evidence_ids']] != groups:
                raise ValueError('Decision used unseen or duplicate practice results')
            if kind == 'trial_choice':
                thought = thoughts[dec['thought_id']]
                if list(thought['history_ids']) != seen or thought['session_id'] != sid or thought['model_id'] != trace['model_id']:
                    raise ValueError('Thought does not belong to this decision prefix')
                used_thoughts.append(thought['id'])
                if choice:
                    pending = (sid, choice-1)
            else:
                if choice and not groups[choice]:
                    raise ValueError('Untried candidate adopted')
                active_origin = origin(sid, choice); adopted.add(sid)
    if pending or seen != list(bank.index) or adopted != set(sessions) or active_origin != trace['final_origin']:
        raise ValueError('Trace is not completely closed')
    if len(used_thoughts) != len(set(used_thoughts)) or set(used_thoughts) != set(thoughts):
        raise ValueError('Missing or double-counted internal policy path')
    return bank, sessions, thoughts


def reward_schedule(trace, bank, thoughts):
    terminal_post = [d['event_id'] for d in trace['decisions'] if d['kind'] == 'task' and d['purpose'] == 'post_choice'
                     and bank.events[bank.index[d['event_id']]].terminal]
    if not terminal_post:
        raise ValueError('Actual future task outcomes are required for this credit target')
    rewards = []
    for d in trace['decisions']:
        r = [0., 0., 0.]
        if d['kind'] in ('task', 'trial'):
            event = bank.events[bank.index[d['event_id']]]
            r[1] = -event.cost
            if event.id in terminal_post:
                r[0] = float(event.goal_met)/len(terminal_post)
        if d['kind'] == 'trial_choice':
            r[2] = -float(thoughts[d['thought_id']]['allocated_particle_rows'])
        rewards.append(r)
    returns = []; total = [0., 0., 0.]
    for r in reversed(rewards):
        total = [x+y for x, y in zip(total, r)]; returns.append(total)
    return rewards, list(reversed(returns))


def evaluate_trace(model, trace, mode='on_policy', diagnostic_detach_candidates=False):
    """Rebuild deterministic candidate computations, not runtime issued handles."""
    if mode not in ('on_policy', 'same_world_IS'):
        raise ValueError('Unknown replay mode')
    if world_identity(model) != trace['world_id']:
        raise ValueError('World changed: old imagined-path policy replay is not qualified; real facts remain usable')
    same = model_identity(model) == trace['model_id']
    if mode == 'on_policy' and not same:
        raise ValueError('On-policy requires the actual behavior snapshot')
    bank, sessions, thoughts = validate_trace(trace)
    if bank.schema != model.schema or bank.layout != model.layout:
        raise ValueError('Observation semantics changed')
    p = next(model.parameters()); tensor = lambda x: torch.as_tensor(x, dtype=p.dtype, device=p.device)
    generated = {}; replayed = {}; code_errors = []

    def infer(event, history, code=None, ongoing=False):
        memory = bank.forecast_view(event.previous_id, len(history)) if ongoing else bank.view(len(history))
        return model(tensor([event.observation]), tensor([event.goal]), tensor([event.actions]), memory, code)

    def code_for(origin):
        if origin['kind'] == 'base':
            return model.base_code[None]
        sid = origin['session_id']
        if sid not in generated:
            g = trace['generations'][sid]
            source = bank.events[bank.index[g['source_event_id']]]
            generated[sid] = model.propose(infer(source, g['history_ids']))
            if diagnostic_detach_candidates:
                # Forward-identical derivative intervention, never an issued runtime model.
                generated[sid] = generated[sid].detach()
        result = generated[sid][:, origin['arm']-1]
        if same:
            expected = tensor([sessions[sid]['arms'][origin['arm']]['code']])
            code_errors.append(float((result.detach()-expected).abs().max()))
        return result

    def codes_for(sid):
        origins = [trace['generations'][sid]['baseline_origin']]
        origins += [dict(kind='proposal', session_id=sid, arm=i) for i in range(1, len(sessions[sid]['arms']))]
        return torch.stack([code_for(o) for o in origins], 1)

    logs = []; values = []; policy_errors = []; value_errors = []; behavior = 0.
    for dec in trace['decisions']:
        kind = dec['kind']; b = tensor([dec['budget_features']]); internal = p.new_zeros(())
        if kind in ('task', 'trial'):
            event = bank.events[bank.index[dec['event_id']]]; code = code_for(dec['code_origin'])
            output = infer(event, dec['history_ids'], code, ongoing=True); logits = output['logits']; choice = dec['action']
        else:
            sid = dec['session_id']; source = bank.events[bank.index[sessions[sid]['source_event_id']]]
            codes = codes_for(sid); code = codes[:, 0]
            output = infer(source, dec['history_ids'], code)
            evidence = bank.evidence(dec['evidence_ids'], len(dec['history_ids'])); choice = dec['choice']
            if kind == 'trial_choice':
                old = thoughts[dec['thought_id']]
                tape = {key: tensor(value) if isinstance(value, list) else value for key, value in old['noise_tape'].items()}
                thought = model.dream(output, codes, tape, replay_decisions=old['decisions'])
                replayed[old['id']] = thought
                internal = thought['internal_log_probability']
                behavior += old['internal_log_probability']
                logits, _ = model.trial_logits_with_thought(output, codes, evidence, b, thought)
            else:
                logits, _ = model.adoption_logits(output, codes, evidence)
        value = model.values(output, code, PHASES[kind], b)[0]
        logs.append(logits.log_softmax(-1)[0, choice] + internal)
        values.append(value); behavior += math.log(dec['propensity'])
        if same:
            policy_errors.append(float((logits.detach().softmax(-1)[0]-tensor(dec['policy'])).abs().max()))
            value_errors.append(float((value.detach()-tensor(dec['value_prediction'])).abs().max()))
    log_steps = torch.stack(logs); v = torch.stack(values)
    reward, returns = reward_schedule(trace, bank, thoughts); targets = tensor(returns)
    log_ratio = log_steps.sum().double() - behavior
    ratio = log_ratio.exp()
    if not torch.isfinite(ratio):
        raise ValueError('Full trajectory importance weight is non-finite')
    weight = ratio.detach() if mode == 'same_world_IS' else p.new_ones(())
    advantages = targets-v.detach()
    policy_losses = -(weight * advantages * log_steps[:, None]).sum(0)
    # No hidden scalar weighting is chosen between objectives.
    critic_losses = weight * (v-targets).square().mean(0)
    zero_baseline_losses = -(weight * targets * log_steps[:, None]).sum(0)
    errors = dict(candidate_code_max=max(code_errors, default=0.), policy_max=max(policy_errors, default=0.),
                  value_max=max(value_errors, default=0.), log_probability_delta=float(log_ratio.detach()))
    if same and (max(errors['candidate_code_max'], errors['policy_max'], errors['value_max']) > 3e-6 or abs(errors['log_probability_delta']) > 2e-4):
        raise ValueError(f'Behavior replay mismatch: {errors}')
    return dict(policy_losses=policy_losses, critic_losses=critic_losses, zero_baseline_losses=zero_baseline_losses,
                targets=targets, reward=tensor(reward), values=v, log_steps=log_steps,
                importance_weight=ratio, errors=errors, generated_codes=generated, replayed_thoughts=replayed,
                mode=mode, diagnostic_detach_candidates=diagnostic_detach_candidates,
                world_id=trace['world_id'], behavior_model_id=trace['model_id'])
