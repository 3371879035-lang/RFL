"""V0.8 public DAG tasks and external stochastic sources; no reward in facts."""
from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class PublicTask:
    successors: tuple
    layers: tuple
    goal: int
    horizon: int = 12


@dataclass(frozen=True)
class Observation:
    uid: int
    steps: tuple  # (state, command, next_state, visible_outcome)
    terminal: str


@dataclass(frozen=True)
class RewardPacket:
    observation: Observation
    rewards: tuple


def make_source(plan, condition, mirror):
    n = condition['states']
    successors, probabilities, layers = [None]*n, [None]*n, [None]*n
    if condition['kind'] == 'layered_chain':
        for s, row in enumerate(condition['canonical_forward_probabilities']):
            successors[s] = (s+1, s+1)
            probabilities[s] = tuple(row[a ^ mirror] for a in (0, 1))
            layers[s] = s
    else:
        unit = plan['branch_unit']
        for j in range(condition['units']):
            fork, left, right, nxt = 3*j, 3*j+1, 3*j+2, 3*j+3
            successors[fork] = tuple((left, right)[a ^ mirror] for a in (0, 1))
            probabilities[fork] = tuple(unit['canonical_fork_probabilities'][a ^ mirror] for a in (0, 1))
            layers[fork] = 2*j
            for s, field in ((left, 'canonical_A_probabilities'), (right, 'canonical_B_probabilities')):
                successors[s] = (nxt, nxt)
                probabilities[s] = tuple(unit[field][a ^ mirror] for a in (0, 1))
                layers[s] = 2*j+1
    task = PublicTask(tuple(successors), tuple(layers), n)
    assert all(s < nxt <= n for s, row in enumerate(successors) for nxt in row)
    return task, tuple(probabilities)


class Engine:
    def __init__(self, task, probabilities, log):
        self.public, self._probabilities, self.log = task, probabilities, log
        self._initial = self.audit_source()
        log.counts['source_instances'] += 1

    def audit_source(self):
        return {'public': asdict(self.public), 'probabilities': self._probabilities}

    def rollout(self, program, uniforms, mode):
        assert len(program) == self.public.goal and len(uniforms) == self.public.goal
        uid = self.log.begin_native(mode)
        steps, audit = [], []
        s = 0
        for _ in range(self.public.horizon):
            a = program[s]
            assert a in (0, 1)
            p, u = self._probabilities[s][a], uniforms[s]
            self.log.native_step(mode)
            if u < p:
                nxt = self.public.successors[s][a]
                outcome = 'SUCCESS' if nxt == self.public.goal else 'NEXT'
            else:
                nxt, outcome = s, 'COLLISION'
            steps.append((s, a, nxt, outcome))
            audit.append((u, p))
            if outcome in ('SUCCESS', 'COLLISION'):
                break
            s = nxt
        else:
            outcome = 'TIMEOUT'
        obs = Observation(uid, tuple(steps), outcome)
        self.log.emit('RAW', {'uid': uid, 'mode': mode, 'steps': steps, 'terminal': outcome, 'audit': audit})
        return obs
