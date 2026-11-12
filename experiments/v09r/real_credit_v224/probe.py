from dataclasses import asdict
from pathlib import Path
import hashlib
import json
import random
import sys
import time
ROOT = Path(__file__).resolve().parents[3]; HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'src'))
import torch
from feedback_program_v224 import FeedbackCreditNet, PracticeAgent, FeedbackLayout, View
from feedback_program_v224.runtime import model_identity, world_identity
from feedback_program_v224.learning import evaluate_trace
from checks import run_checks


def layout():
    return FeedbackLayout(('measurement_0', 'measurement_1'), (
        View((('goal_met', 0, 1.),)), View((('next', 0, 1.),)),
        View((('next', 0, 1.), ('observation', 0, -1.))), View((), 1.),
        View((('action_index', 0, 1.),)), View((('terminal', 0, 1.),)),
        View((('innovation', 0, 1.),)), View((('innovation', 1, 1.),))))


class Environment:
    """New generic numeric task, not a game adapter. Every result is actually executed."""
    def __init__(self, seed, spec, record):
        self.rng = random.Random(seed); self.layout = spec; self.record = record; self.calls = 0
    def initial(self, x0):
        return (x0, *[self.rng.uniform(-.5, .5) for _ in range(15)])
    def executor(self, observation, goal, actions, episode, step, purpose):
        def execute(action):
            self.calls += 1; x = observation; a = actions[action]
            noise = [self.rng.uniform(-.01, .01) for _ in x]
            nxt = tuple(.6*v + .15*a[i % 8] + noise[i] for i, v in enumerate(x))
            u = (nxt[0] + self.rng.uniform(-.1, .1), nxt[1] - x[1] + self.rng.uniform(-.1, .1))
            mask = (self.rng.random() < .65, self.rng.random() < (.8 if u[1] > 0 else .3))
            terminal = step == 2; met = terminal and nxt[0] > .15
            raw = self.layout.render(nxt, u, float(met), float(terminal), x, a, action)
            visible = self.layout.visible_views(mask)
            result = dict(next_observation=nxt, feedback=tuple(v if m else 0. for v, m in zip(raw, visible)),
                          feedback_mask=visible, goal_met=met, terminal=terminal, cost=1.)
            self.record(dict(kind='external_execution', call=self.calls, episode=episode, step=step, purpose=purpose,
                observation=x, goal=goal, actions=actions, action_index=action, noise=noise, result=result))
            return result
        return execute


def save(path, value):
    with path.open('x', encoding='utf-8') as f:
        json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)


def main():
    contract = json.loads((HERE/'contract.json').read_text()); cap = HERE/'capture'; torch.set_num_threads(1)
    start = time.perf_counter(); runs = []; all_checks = []
    with (cap/'events.jsonl').open('x', encoding='utf-8', buffering=1) as stream:
        def record(row):
            stream.write(json.dumps(row, sort_keys=True, allow_nan=False)+'\n')
        for seed in contract['model_seeds']:
            torch.manual_seed(seed); model = FeedbackCreditNet(layout()).eval(); before = model_identity(model)
            rid = f'v224/seed{seed}'
            def rr(row): record(dict(run_id=rid, **row))
            rr(dict(kind='run_start', seed=seed, model_id=before, world_id=world_identity(model),
                    schema=asdict(model.schema), config=asdict(model.config), layout=model.layout.to_dict()))
            agent = PracticeAgent(model, rid, random.Random(224000+seed), thought_depth=contract['thought_depth'])
            env = Environment(2241000+seed, model.layout, rr); episodes = []
            goal = (1., 0., 0., 0., 0., 0., 0., 0.)
            def task(label, x0, actions, purpose):
                observation = env.initial(x0); previous = None; ids = []
                for step in range(3):
                    execute = env.executor(observation, goal, actions, label, step, purpose)
                    event = agent.execute(observation, goal, actions, execute, label, step, previous, purpose=purpose)
                    ids.append(event.id); observation = event.next_observation; previous = event.id
                return event, ids
            for episode in range(contract['source_episodes_per_seed']):
                actions = tuple(tuple(float(i == j) for j in range(8)) for i in range((2, 3, 5)[episode]))
                source, ids = task(f'{rid}/source/{episode}', -2., actions, 'source')
                if source.goal_met:
                    raise AssertionError('Predeclared path-coverage transition bound violated')
                trial_env = env.executor(source.observation, goal, actions, f'{rid}/trial/{episode}', 2, 'practice')
                session = agent.reflect(source, trial_env, contract['practice_budget_per_failure'])
                post = []
                for index, x0 in enumerate(contract['post_choice_initial_x0']):
                    _, fresh_ids = task(f'{rid}/post/{episode}/{index}', x0, actions, 'post_choice'); post.append(fresh_ids)
                episodes.append(dict(source_ids=ids, session_id=None if session is None else session.id, post_task_ids=post))
            trace = agent.export_trace(episodes); save(cap/f'trace_seed{seed}.json', trace)
            for event in agent.bank.events: rr(dict(kind='actual_event', event=asdict(event)))
            for decision in agent.decisions: rr(dict(kind='decision', decision=decision))
            for thought in agent.thoughts: rr(dict(kind='thought', thought=thought))
            for session in trace['sessions']: rr(dict(kind='session', session=session))
            replay = evaluate_trace(model, trace)
            save(cap/f'credit_seed{seed}.json', dict(reward=replay['reward'].tolist(), returns=replay['targets'].tolist(),
                values=replay['values'].detach().tolist(), log_steps=replay['log_steps'].detach().tolist(),
                policy_losses=replay['policy_losses'].detach().tolist(), critic_losses=replay['critic_losses'].detach().tolist(),
                zero_baseline_losses=replay['zero_baseline_losses'].detach().tolist(), errors=replay['errors']))
            checks = run_checks(model, agent, trace, replay, seed); save(cap/f'checks_seed{seed}.json', checks)
            all_checks.extend(checks.values())
            after = model_identity(model)
            if after != before or env.calls != len(agent.bank.events):
                raise AssertionError('Actual-event count or frozen parameter mismatch')
            torch.save(dict(state_dict=model.state_dict(), schema=asdict(model.schema), config=asdict(model.config),
                layout=model.layout.to_dict(), model_id=before, seed=seed, status='UNTRAINED_INITIALIZATION',
                class_name='feedback_program_v224.FeedbackCreditNet'), cap/f'untrained_seed{seed}.pt')
            run = dict(seed=seed, model_before=before, model_after=after, world_id=world_identity(model),
                actual_calls=env.calls, counters=agent.counters, memory_nodes=len(agent.bank.events),
                thought_sessions=len(agent.thoughts), imagined_nodes=sum(len(t['nodes']) for t in agent.thoughts),
                thought_particle_rows=sum(t['allocated_particle_rows'] for t in agent.thoughts),
                decisions=len(agent.decisions), return_vector=replay['targets'][0].tolist(), replay_errors=replay['errors'],
                parameters=sum(p.numel() for p in model.parameters()), parameter_tensors=len(list(model.parameters())),
                checks_passed=all(c['passed'] for c in checks.values()), optimizer_steps=0)
            rr(dict(kind='run_complete', **run)); runs.append(run)
            del replay
        summary = dict(status='UNTRAINED_REAL_CREDIT_CHECKED' if all(c['passed'] for c in all_checks) else 'DIRECTED_FAILURES_RETAINED',
            runs=runs, checks=len(all_checks), checks_all_passed=all(c['passed'] for c in all_checks),
            actual_calls=sum(r['actual_calls'] for r in runs), optimizer_steps=0, old_native_reruns=0,
            wall_seconds=time.perf_counter()-start, torch_version=torch.__version__)
        assert summary['actual_calls'] <= contract['actual_environment_calls_maximum']
        save(cap/'summary.json', summary)
        print(json.dumps(summary, indent=2))
    return 0 if summary['checks_all_passed'] else 1


if __name__ == '__main__': sys.exit(main())
