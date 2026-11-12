from dataclasses import asdict
from pathlib import Path
import json
import random
import sys
import time
ROOT = Path(__file__).resolve().parents[3]; HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'src'))
import torch
from feedback_program_v225 import FilteredFeedbackNet, PracticeAgent, FeedbackLayout, View
from feedback_program_v225.identity import model_identity, world_identity
from feedback_program_v225.learning import evaluate_trace
from checks import run_checks


def layout():
    return FeedbackLayout(('measurement_0', 'measurement_1'), (
        View((('goal_met', 0, 1.),)), View((('next', 0, 1.),)),
        View((('next', 0, 1.), ('observation', 0, -1.))), View((), 1.),
        View((('action_index', 0, 1.),)), View((('terminal', 0, 1.),)),
        View((('innovation', 0, 1.),)), View((('innovation', 1, 1.),))))


class Environment:
    def __init__(self, seed, spec, record):
        self.rng = random.Random(seed); self.layout = spec; self.record = record; self.calls = 0
    def initial(self, x0):
        return (x0, *[self.rng.uniform(-.5, .5) for _ in range(15)])
    def executor(self, observation, goal, actions, episode, step, horizon, purpose):
        def execute(action):
            self.calls += 1; x = observation; a = actions[action]
            noise = [self.rng.uniform(-.01, .01) for _ in x]
            nxt = tuple(.8*v+.08*a[i % 8]+noise[i] for i, v in enumerate(x))
            u = (nxt[0]+self.rng.uniform(-.1, .1), nxt[1]-x[1]+self.rng.uniform(-.1, .1))
            mask = (self.rng.random() < .65, self.rng.random() < (.8 if u[1] > 0 else .3))
            terminal = step == horizon-1; met = terminal and nxt[0] > .15
            raw = self.layout.render(nxt, u, float(met), float(terminal), x, a, action)
            visible = self.layout.visible_views(mask)
            result = dict(next_observation=nxt, feedback=tuple(v if m else 0. for v, m in zip(raw, visible)),
                          feedback_mask=visible, goal_met=met, terminal=terminal, cost=1.)
            self.record(dict(kind='external_execution', call=self.calls, episode=episode, step=step, horizon=horizon,
                purpose=purpose, observation=x, goal=goal, actions=actions, action_index=action, noise=noise, result=result))
            return result
        return execute


def save(path, value):
    with path.open('x', encoding='utf-8') as f: json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)


def main():
    contract = json.loads((HERE/'contract.json').read_text()); cap = HERE/'capture'; torch.set_num_threads(1)
    start = time.perf_counter(); runs = []; all_checks = []
    with (cap/'events.jsonl').open('x', encoding='utf-8', buffering=1) as stream:
        def record(row): stream.write(json.dumps(row, sort_keys=True, allow_nan=False)+'\n')
        for seed in contract['model_seeds']:
            torch.manual_seed(seed); model = FilteredFeedbackNet(layout()).eval(); before = model_identity(model)
            assert sum(p.numel() for p in model.parameters()) == contract['parameter_count_expected']
            rid = f'v225/seed{seed}'
            def rr(row): record(dict(run_id=rid, **row))
            rr(dict(kind='run_start', seed=seed, model_id=before, world_id=world_identity(model),
                    schema=asdict(model.schema), config=asdict(model.config), layout=model.layout.to_dict()))
            agent = PracticeAgent(model, rid, random.Random(225000+seed), thought_depth=contract['thought_depth'])
            env = Environment(2251000+seed, model.layout, rr); episodes = []
            goal = (1., 0., 0., 0., 0., 0., 0., 0.)
            def task(label, x0, horizon, purpose):
                observation = env.initial(x0); previous = None; ids = []
                for step in range(horizon):
                    n = contract['action_counts_by_step_cycle'][step % 3]
                    actions = tuple(tuple(float(i == j) for j in range(8)) for i in range(n))
                    execute = env.executor(observation, goal, actions, label, step, horizon, purpose)
                    event = agent.execute(observation, goal, actions, execute, label, step, previous, purpose=purpose)
                    ids.append(event.id); observation = event.next_observation; previous = event.id
                return event, ids
            for episode, horizon in enumerate(contract['source_lengths']):
                source, ids = task(f'{rid}/source/{episode}', -3., horizon, 'source')
                assert source.terminal and not source.goal_met
                trial_env = env.executor(source.observation, goal, source.actions, f'{rid}/trial/{episode}', horizon-1, horizon, 'practice')
                session = agent.reflect(source, trial_env, contract['practice_budget_per_failure'])
                post = []
                for index, x0 in enumerate(contract['post_initial_x0']):
                    _, fresh_ids = task(f'{rid}/post/{episode}/{index}', x0, horizon, 'post_choice'); post.append(fresh_ids)
                episodes.append(dict(source_ids=ids, session_id=None if session is None else session.id, post_task_ids=post, horizon=horizon))
            trace = agent.export_trace(episodes); save(cap/f'trace_seed{seed}.json', trace)
            for event in agent.bank.events: rr(dict(kind='actual_event', event=asdict(event)))
            for decision in agent.decisions: rr(dict(kind='decision', decision=decision))
            for thought in agent.thoughts: rr(dict(kind='thought', thought=thought))
            for receipt in agent.filter_receipts: rr(dict(kind='filter_receipt', receipt=receipt))
            replay = evaluate_trace(model, trace)
            save(cap/f'credit_seed{seed}.json', dict(reward=replay['reward'].tolist(), returns=replay['targets'].tolist(),
                values=replay['values'].detach().tolist(), log_steps=replay['log_steps'].detach().tolist(), errors=replay['errors']))
            checks, diagnostic = run_checks(model, agent, trace, replay, seed)
            save(cap/f'checks_seed{seed}.json', checks); save(cap/f'diagnostic_seed{seed}.json', diagnostic)
            all_checks.extend(checks.values()); after = model_identity(model)
            assert before == after and env.calls == len(agent.bank.events) == len(agent.filter_receipts)
            torch.save(dict(state_dict=model.state_dict(), schema=asdict(model.schema), config=asdict(model.config),
                layout=model.layout.to_dict(), model_id=before, seed=seed, status='UNTRAINED_INITIALIZATION',
                class_name='feedback_program_v225.FilteredFeedbackNet'), cap/f'untrained_seed{seed}.pt')
            run = dict(seed=seed, model_before=before, model_after=after, world_id=world_identity(model), actual_calls=env.calls,
                counters=agent.counters, actual_filter_updates=len(agent.filter_receipts), memory_nodes=len(agent.bank.events),
                thought_sessions=len(agent.thoughts), imagined_nodes=sum(len(t['nodes']) for t in agent.thoughts),
                thought_particle_rows=sum(t['allocated_particle_rows'] for t in agent.thoughts),
                diagnostic_imagined_nodes=diagnostic.get('imagined_nodes', 0), diagnostic_particle_rows=diagnostic.get('particle_rows', 0),
                decisions=len(agent.decisions), return_vector=replay['targets'][0].tolist(), replay_errors=replay['errors'],
                parameters=sum(p.numel() for p in model.parameters()), parameter_tensors=len(list(model.parameters())),
                checks_passed=all(c['passed'] for c in checks.values()), optimizer_steps=0)
            rr(dict(kind='run_complete', **run)); runs.append(run); del replay
        summary = dict(status='UNTRAINED_ONLINE_FILTER_CHECKED' if all(c['passed'] for c in all_checks) else 'DIRECTED_FAILURES_RETAINED',
            runs=runs, checks=len(all_checks), checks_all_passed=all(c['passed'] for c in all_checks),
            actual_calls=sum(r['actual_calls'] for r in runs), optimizer_steps=0, old_native_reruns=0,
            wall_seconds=time.perf_counter()-start, torch_version=torch.__version__)
        assert summary['actual_calls'] <= contract['actual_environment_calls_maximum']
        assert sum(r['diagnostic_particle_rows'] for r in runs) <= contract['diagnostic_allocated_particle_rows_maximum']
        save(cap/'summary.json', summary); print(json.dumps(summary, indent=2))
    return 0 if summary['checks_all_passed'] else 1


if __name__ == '__main__': sys.exit(main())
