"""Private, new categorical sequential micro-environments for V209 only.

Four observed ticks; only the final action is a choice. No game engine or old RFL
backend. The public learner record does not contain the task rule or random tape.
"""
import random

FAMILIES = ('single_remote', 'pair_joint', 'pair_switch', 'triple_joint')
PHASE_IDS = {'warm': 0, 'fit': 1, 'rank': 2, 'trial': 3, 'deploy': 4, 'eval': 5}


def specification(family, seed):
    rng = random.Random(20900000 + seed*97 + FAMILIES.index(family))
    order = 1 if family == 'single_remote' else 3 if family == 'triple_joint' else 2
    population = range(4) if family == 'single_remote' else range(8)
    return {'family': family, 'relevant': sorted(rng.sample(list(population), order)),
            'initial_flip': rng.randrange(2), 'switch_cycle': 3 if family == 'pair_switch' else None}


def scenario(family, seed, cycle, phase, index):
    # Arm/role deliberately absent: common random numbers across comparison groups.
    code = (((FAMILIES.index(family)*100 + seed)*10 + cycle+1)*10 + PHASE_IDS[phase])*1000 + index
    rng = random.Random(2090000000 + code)
    return {'bits': [rng.randrange(2) for _ in range(8)],
            'action_u': rng.random(), 'outcome_u': rng.random()}


class World:
    def __init__(self, spec):
        self.spec = spec
        self.episodes = 0
        self.steps = 0

    def run(self, policy, tape, cycle, public_id, warm=False):
        observations, actions = [], []
        for tick in range(4):
            observations.append(tape['bits'][2*tick:2*tick+2])
            if tick < 3:
                actions.append(-1)  # Passive waiting while facts are revealed.
            else:
                base_action = policy.act(observations)
                probability_one = .5 if warm else (.9 if base_action == 1 else .1)
                action = int(tape['action_u'] < probability_one)
                propensity = [1, 2] if warm else ([9, 10] if action == base_action else [1, 10])
                actions.append(action)
            self.steps += 1
        desired = self.spec['initial_flip']
        for j in self.spec['relevant']:
            desired ^= tape['bits'][j]
        if self.spec['switch_cycle'] is not None and cycle >= self.spec['switch_cycle']:
            desired ^= 1
        p = .9 if actions[-1] == desired else .1
        outcome = int(tape['outcome_u'] < p)
        self.episodes += 1
        public = {'id': public_id, 'observations': observations, 'actions': actions,
                  'outcome': outcome, 'propensity': propensity, 'policy_id': policy.identity}
        private = {'action_u': tape['action_u'], 'outcome_u': tape['outcome_u']}
        return public, private
