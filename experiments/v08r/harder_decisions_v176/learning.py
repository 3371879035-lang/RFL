"""New DAG port of the declared V0.6/7 equations, with the frozen V175 M1.

Learners only receive PublicTask and their own Observation/RewardPacket.
No source, seed, probability tape, hidden cause or evaluator is accepted here.
"""
from collections import deque
import copy
import importlib.util
from pathlib import Path
from world import Observation, RewardPacket

_path = Path(__file__).resolve().parents[1]/'decision_readout_v175/readout.py'
_spec = importlib.util.spec_from_file_location('frozen_v175_readout', _path)
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)


class Facts:
    def __init__(self):
        self.counts = {}

    def p(self, s, a):
        yes, no = self.counts.get((s, a), (0, 0))
        return (yes+1)/(yes+no+2)

    def record(self, task, obs):
        receipts = []
        for s, a, nxt, outcome in obs.steps:
            before = self.counts.get((s, a), (0, 0))
            if outcome == 'COLLISION' and nxt == s:
                after = (before[0], before[1]+1)
            else:
                assert outcome in ('NEXT', 'SUCCESS') and nxt == task.successors[s][a]
                after = (before[0]+1, before[1])
            self.counts[s, a] = after
            receipts.append([s, a, before, after])
        return receipts


def q_program(task, q):
    return tuple(0 if q.get((s, 0), 0.0) >= q.get((s, 1), 0.0) else 1 for s in range(task.goal))


def proposals(learner):
    """Diagnostic-only alternatives on the same pre-training state."""
    rows = []
    for s in range(learner.task.goal):
        q = [learner.q.get((s, a), 0.0) for a in (0, 1)]
        counts = [learner.facts.counts.get((s, a), (0, 0)) for a in (0, 1)]
        p = [learner.facts.p(s, a) for a in (0, 1)]
        candidates = [a for a in (0, 1) if q[a] == max(q)]
        m1, terms = M.factual_one_step_readout(s, learner.successors, learner.task.goal,
                                               learner.facts.counts, learner.q, learner.failure_reward)
        rows.append({'state': s, 'q': q, 'counts': counts, 'p': p, 'argmax': candidates,
                     'FT': min(candidates, key=lambda a: (-p[a], a)),
                     'CT': min(candidates, key=lambda a: (sum(counts[a]), a)),
                     'M1': m1, 'M1_terms': terms})
    return rows


class FactualLearner:
    def __init__(self, task):
        self.task, self.facts, self.history = task, Facts(), []

    def snapshot(self):
        return {'family': 'F0', 'counts': [self.facts.counts.get((s, a), (0, 0)) for s in range(self.task.goal) for a in (0, 1)],
                'history': list(self.history)}

    def policy(self):
        reach, program, details = {self.task.goal: 1.0}, {}, []
        for s in reversed(range(self.task.goal)):
            values = [self.facts.p(s, a)*reach[self.task.successors[s][a]] for a in (0, 1)]
            a = 0 if values[0] >= values[1] else 1
            program[s], reach[s] = a, values[a]
            details.append([s, values])
        return tuple(program[s] for s in range(self.task.goal)), details

    def learn(self, obs):
        assert type(obs) is Observation and obs.uid not in self.history
        updates = self.facts.record(self.task, obs)
        self.history.append(obs.uid)
        return [], updates


class QLearner:
    def __init__(self, task, failure_reward):
        self.task, self.failure_reward = task, failure_reward
        self.q, self.history, self.buffer = {}, [], deque(maxlen=64)

    def snapshot(self):
        return {'family': 'Q', 'failure_reward': self.failure_reward,
                'q': [self.q.get((s, a), 0.0) for s in range(self.task.goal) for a in (0, 1)],
                'buffer': list(self.buffer), 'history': list(self.history)}

    def policy(self):
        return q_program(self.task, self.q), None

    def backup(self, s, a, target, kind, origin):
        before = self.q.get((s, a), 0.0)
        after = before+0.5*(target-before)
        self.q[s, a] = after
        return [kind, s, a, before, target, after, origin]

    def real_backup(self, item, kind):
        uid, i, s, a, reward, nxt, terminal = item
        target = reward if terminal else reward+max(self.q.get((nxt, b), 0.0) for b in (0, 1))
        return self.backup(s, a, target, kind, [uid, i])

    def ordinary(self, packet):
        assert type(packet) is RewardPacket and packet.observation.uid not in self.history
        obs, updates = packet.observation, []
        assert len(packet.rewards) == len(obs.steps)
        for i, ((s, a, nxt, outcome), reward) in enumerate(zip(obs.steps, packet.rewards)):
            item = (obs.uid, i, s, a, reward, nxt, outcome in ('SUCCESS', 'COLLISION'))
            self.buffer.append(item)
            updates.append(self.real_backup(item, 'ordinary'))
        self.history.append(obs.uid)
        return updates

    def learn(self, packet):
        updates = self.ordinary(packet)
        for item in tuple(reversed(self.buffer))[:12]:
            updates.append(self.real_backup(item, 'replay'))
        return updates, []


class Hybrid(QLearner):
    def __init__(self, task, failure_reward, mode):
        super().__init__(task, failure_reward)
        self.mode, self.facts = mode, Facts()
        self.successors = {(s, a): task.successors[s][a] for s in range(task.goal) for a in (0, 1)}

    def snapshot(self):
        return {**super().snapshot(), 'family': 'hybrid', 'mode': self.mode,
                'counts': [self.facts.counts.get((s, a), (0, 0)) for s in range(self.task.goal) for a in (0, 1)]}

    def policy(self):
        program, details = [], []
        for s in range(self.task.goal):
            if self.mode == 'M1':
                a, terms = M.factual_one_step_readout(s, self.successors, self.task.goal,
                                                     self.facts.counts, self.q, self.failure_reward)
                details.append(terms)
            else:
                q = [self.q.get((s, b), 0.0) for b in (0, 1)]
                candidates = [b for b in (0, 1) if q[b] == max(q)]
                a = min(candidates, key=(lambda b: (-self.facts.p(s, b), b)) if self.mode == 'FT'
                        else (lambda b: (sum(self.facts.counts.get((s, b), (0, 0))), b)))
                details.append([q, candidates])
            program.append(a)
        return tuple(program), details

    def learn(self, packet):
        updates = self.ordinary(packet)
        facts = self.facts.record(self.task, packet.observation)
        contexts = sorted(self.facts.counts, key=lambda x: (-self.task.layers[x[0]], x[0], x[1]))
        for i in range(min(12, len(self.buffer))):
            s, a = contexts[i % len(contexts)]
            p, nxt = self.facts.p(s, a), self.task.successors[s][a]
            continuation = 1.0 if nxt == self.task.goal else max(self.q.get((nxt, b), 0.0) for b in (0, 1))
            target = p*continuation+(1.0-p)*self.failure_reward
            updates.append(self.backup(s, a, target, 'model', [p, continuation]))
        return updates, facts


def make_learner(task, arm):
    if arm['id'] == 'F0':
        return FactualLearner(task)
    if arm['id'].startswith('RL-'):
        return QLearner(task, float(arm['failure_reward']))
    return Hybrid(task, float(arm['failure_reward']), arm['id'].rsplit('-', 1)[1])


class FrozenPolicy:
    def __init__(self, learner):
        self.clone = copy.deepcopy(learner)
        assert self.clone.task == learner.task
        for field in ('q', 'facts', 'buffer', 'history'):
            if hasattr(learner, field):
                assert getattr(self.clone, field) is not getattr(learner, field)
        assert self.clone.snapshot() == learner.snapshot()

    def snapshot(self):
        return self.clone.snapshot()

    def policy(self):
        return self.clone.policy()
