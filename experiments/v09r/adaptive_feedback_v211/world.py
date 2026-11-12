"""New four-tick partial-history environment; private rules stay outside learner."""
import random
from feedback_program_v210 import Fact

FAMILIES = ('single', 'triple', 'switch_pair', 'noise')
ARMS = ('full', 'fixed_order', 'pooled_history', 'mean_eight')


def specification(family, seed):
    rng = random.Random(21141000+101*seed+FAMILIES.index(family))
    order = {'single': 1, 'triple': 3, 'switch_pair': 2, 'noise': 0}[family]
    return {'family': family, 'relevant': sorted(rng.sample(range(4), order)),
            'flip': rng.randrange(2), 'switch_cycle': 3 if family == 'switch_pair' else None}


def scenario(family, seed, cycle, phase, slot):
    # All arm/role identities omitted; no collisions between warm/train/eval coordinates.
    phase_number = {'warm': 0, 'train': 1, 'eval': 2}[phase]
    prefix = ((FAMILIES.index(family)*100+seed)*20+(cycle+2))*10+phase_number
    shared_slot = (64+(slot-64)//2 if phase == 'train' and slot >= 64 else slot)
    context_rng = random.Random(211000000000+prefix*10000+shared_slot)
    noise_rng = random.Random(211900000000+prefix*10000+slot)
    return {'context': tuple(context_rng.randrange(2) for _ in range(4)),
            'action_u': noise_rng.random(), 'outcome_u': noise_rng.random()}


class World:
    def __init__(self, spec):
        self.spec = spec
        self.episodes = 0
        self.steps = 0

    def run(self, policy, tape, cycle, event_id, epsilon):
        visible, actions = [], []
        for tick, bit in enumerate(tape['context']):
            visible.append(bit)
            if tick < 3:
                actions.append(-1)
            else:
                base = policy.act(tuple(visible))
                p_one = (1.-epsilon)*base+epsilon/2
                action = int(tape['action_u'] < p_one)
                propensity = (1.-epsilon)*int(action == base)+epsilon/2
                actions.append(action)
            self.steps += 1
        desired = self.spec['flip']
        for j in self.spec['relevant']:
            desired ^= visible[j]
        if self.spec['switch_cycle'] is not None and cycle >= self.spec['switch_cycle']:
            desired ^= 1
        p = .5 if self.spec['family'] == 'noise' else .9 if action == desired else .1
        outcome = int(tape['outcome_u'] < p)
        self.episodes += 1
        return Fact(event_id, tuple(visible), action, outcome, propensity, policy.identity), {
            'actions': actions, 'base_action': base, 'action_u': tape['action_u'],
            'outcome_u': tape['outcome_u'], 'terminal': 'SUCCESS' if outcome else 'FAIL'}
