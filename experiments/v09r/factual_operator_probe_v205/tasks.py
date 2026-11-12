"""Small non-game controlled processes. Generating laws stay outside the learner."""
import random


FAMILIES = ('process_cost', 'branching', 'short_history', 'long_history', 'stochastic_reversal')


class Task:
    def __init__(self, family, seed, cycle, cue):
        self.family, self.cycle, self.cue = family, cycle, int(cue)
        self.rng = random.Random(seed)
        self.phase, self.value, self.done = 0, (2. * cue - 1. if 'history' in family else 0.), False
        self.choice = None

    def observation(self):
        return [float(self.phase), float(self.value)]

    def legal(self):
        if self.done:
            return []
        if self.family == 'short_history':
            return [0] if self.phase == 0 else [0, 1, 2]
        if self.family == 'long_history':
            return [0] if self.phase < 5 else [0, 1, 2]
        return [0, 1, 2] if self.phase == 0 else [0]

    def step(self, action):
        if action not in self.legal():
            raise ValueError('Illegal actual action')
        before, legal = self.observation(), self.legal()
        c, y, u = [0., 0.], [0., 0.], None
        if self.phase == 0 and self.family not in ('short_history', 'long_history'):
            self.choice = action
            if self.family == 'process_cost':
                c[1], self.value = (.8, .1, .2)[action], float(action)
            elif self.family == 'branching':
                if action == 0:
                    u = self.rng.random()
                    self.value = -1. if u < .5 else 1.
                else:
                    self.value = .4 if action == 1 else 0.
            else:
                probs = (.65, .55, .45) if self.cycle == 0 else (.30, .75, .50)
                u = self.rng.random()
                c[0] = float(u < probs[action])
                self.value = 0.
        elif self.family in ('short_history', 'long_history'):
            last = 1 if self.family == 'short_history' else 5
            if self.phase == last:
                y[0] = .25 if action == 2 else float(action == self.cue)
                self.done = True
            self.value = 0.
        else:
            if self.family == 'process_cost':
                y[0] = (1., .9, .7)[self.choice]
            elif self.family == 'branching':
                y[0] = 1. if abs(self.value) == 1. else (.65 if self.value == .4 else 0.)
            self.done = True
        t = self.phase
        self.phase += 1
        return dict(t=t, observation=before, legal=legal, action=int(action), contribution=c,
                    terminal_fact=y, known=[True, True], terminal=self.done,
                    successor=self.observation(), legal_next=self.legal(), draw=u)


def rollout(family, seed, cycle, cue, actor, episode_id, role, run_id):
    task, previous, steps = Task(family, seed, cycle, cue), [], []
    while not task.done:
        obs = task.observation()
        action = actor(obs, previous, task.legal())
        step = task.step(action)
        steps.append(step)
        previous.append(obs)
    facts = [sum(s['contribution'][k] + s['terminal'] * s['terminal_fact'][k] for s in steps) for k in range(2)]
    return dict(id=episode_id, run=run_id, family=family, cycle=cycle, cue=cue, env_seed=seed,
                role=role, steps=steps, facts=facts, utility=facts[0] - facts[1])


def conditional_expected_return(episode):
    """Analyst-only law for the executed policy actions; never fed to the learner."""
    family, action = episode['family'], episode['steps'][0]['action']
    if family == 'stochastic_reversal':
        return ((.65, .55, .45) if episode['cycle'] == 0 else (.30, .75, .50))[action]
    return episode['utility']
