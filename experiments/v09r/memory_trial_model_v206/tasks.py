"""Non-game processes, private generating rules outside the learner."""
import random

FAMILIES = ('remote_signal', 'rule_reversal', 'two_cue_xor')
GATE_CASES = {'large_gain': (.30, .70), 'small_gain': (.55, .65), 'null': (.60, .60),
              'large_harm': (.70, .30), 'small_harm': (.65, .55)}


def scenario(seed, family, cycle, instance):
    rng = random.Random(seed)
    length = rng.choice((8, 10, 12))
    observations = [[t, rng.randrange(2), rng.randrange(2)] for t in range(length + 1)]
    slot = instance % 5
    field = (instance // 5) % 2
    label = observations[slot][field + 1]
    if family == 'two_cue_xor':
        label ^= observations[(slot + 2) % 5][2 - field]
    if family == 'rule_reversal' and cycle >= 2:
        label = 1 - label
    return observations, label


def run_memory_episode(episode_id, family, instance, cycle, context_seed, outcome_seed, actor, role, run):
    all_observations, label = scenario(context_seed, family, cycle, instance)
    # Actual chronological observation/action calls. No future observation is passed to the actor.
    observed, actions = [], []
    for obs in all_observations:
        observed.append(obs)
        terminal = len(observed) == len(all_observations)
        actions.append(int(actor(observed)) if terminal else 0)
    if actions[-1] not in (0, 1):
        raise ValueError('Illegal terminal action')
    p = .9 if actions[-1] == label else .1
    u = random.Random(outcome_seed).random()
    return dict(id=episode_id, section='memory', run=run, role=role, family=family, instance=instance, cycle=cycle,
                context_seed=context_seed, outcome_seed=outcome_seed, observations=observed, actions=actions,
                outcome=int(u < p), steps=len(actions), draw=u, analyst_probability=p)


def run_gate_episode(episode_id, case, outcome_seed, action, role, run):
    probability = GATE_CASES[case][action]
    u = random.Random(outcome_seed).random()
    return dict(id=episode_id, section='gate', run=run, role=role, case=case, outcome_seed=outcome_seed,
                observations=[[0, 0, 0]], actions=[action], outcome=int(u < probability), steps=1,
                draw=u, analyst_probability=probability)


def public_episode(ep):
    return dict(id=ep['id'], observations=ep['observations'], action=ep['actions'][-1], outcome=ep['outcome'])
