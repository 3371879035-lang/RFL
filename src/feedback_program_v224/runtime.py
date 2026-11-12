"""Live ownership is unchanged; recorded origins are data for differentiable replay."""
from dataclasses import asdict
import hashlib
import json
import torch
from feedback_program_v223.runtime import PracticeAgent as PreviousAgent, model_identity
from .memory import MemoryBank
from .imagination import noise_tape, thought_record

PHASES = {'task': 0, 'trial_choice': 1, 'trial': 2, 'adoption': 3}


def world_identity(model):
    h = hashlib.sha256(json.dumps({'schema': asdict(model.schema), 'config': asdict(model.config),
                                  'layout': model.layout.to_dict(), 'memory_version': 224}, sort_keys=True).encode())
    for name, tensor in model.state_dict().items():
        if name.split('.')[0] in model.WORLD_GROUPS or name == 'forecast_uniforms':
            h.update(name.encode()); h.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    return h.hexdigest()


class PracticeAgent(PreviousAgent):
    def __init__(self, model, namespace, rng, bank=None, thought_depth=3):
        super().__init__(model, namespace, rng, MemoryBank(model.schema, model.layout) if bank is None else bank, thought_depth)
        self.active_origin = {'kind': 'base'}
        self.generations = {}
        self.initial_history_ids = tuple(self.bank.index)
        self._trial_budget = [0., 0.]

    def infer(self, *args, **kwargs):
        self._last_inference = super().infer(*args, **kwargs)
        return self._last_inference

    def replace_model(self, model):
        old = self.version
        super().replace_model(model)
        if old != self.version:
            self.active_origin = {'kind': 'base'}

    def origin(self, session, arm):
        if arm == 0:
            return self.generations[session.id]['baseline_origin']
        return {'kind': 'proposal', 'session_id': session.id, 'arm': arm}

    @torch.no_grad()
    def new_session(self, event):
        session = super().new_session(event)
        self.generations[session.id] = {'source_event_id': event.id, 'history_ids': tuple(self.bank.index),
                                       'baseline_origin': dict(self.active_origin), 'model_id': self.version}
        return session

    def promote(self, session, arm):
        super().promote(session, arm)
        self.active_origin = dict(self.origin(session, arm))

    @torch.no_grad()
    def execute(self, observation, goal, actions, environment, episode, step=0, previous_id=None,
                session=None, arm=None, purpose='source'):
        origin = dict(self.active_origin if session is None else self.origin(session, arm))
        event = super().execute(observation, goal, actions, environment, episode, step, previous_id, session, arm)
        decision = self.decisions[-1]
        raw_code = self.model.base_code[None] if decision['code'] is None else self.tensor([decision['code']])
        budget = self._trial_budget if session is not None else [0., 0.]
        values = self.model.values(self._last_inference, raw_code, PHASES[decision['kind']], self.tensor([budget]))
        decision.update(code_origin=origin, purpose='practice' if session is not None else purpose,
                        value_prediction=values[0].tolist(), budget_features=list(budget))
        return event

    @torch.no_grad()
    def reflect(self, event, environment, budget):
        if not event.terminal or event.goal_met:
            return None
        session = self.new_session(event); codes = self.tensor([[c.code for c in session.arms]])
        for index in range(budget):
            output = self.infer(event.observation, event.goal, event.actions)
            evidence = self.evidence(session); b = [float(budget-index), float(index)]
            # The baseline is evaluated BEFORE the random thought choices.
            values = self.model.values(output, codes[:, 0], PHASES['trial_choice'], self.tensor([b]))
            tape = noise_tape(self.rng.randrange(2**31), self.thought_depth, self.model.config.hypotheses,
                              self.model.schema.observation, self.model.innovations, len(session.arms))
            thought = self.model.dream(output, codes, tape); tid = f'{self.namespace}/thought/{len(self.thoughts)}'
            self.thoughts.append(dict(thought_record(thought), id=tid, session_id=session.id, model_id=self.version,
                                      history_ids=tuple(self.bank.index), evidence_ids=evidence['ids']))
            logits, _ = self.model.trial_logits_with_thought(output, codes, evidence, self.tensor([b]), thought)
            choice, propensity, policy = self.choose(logits)
            self.decisions.append(dict(kind='trial_choice', session_id=session.id, history_ids=tuple(self.bank.index),
                evidence_ids=evidence['ids'], model_id=self.version, choice=choice, propensity=propensity, policy=policy,
                remaining_budget=budget-index, thought_id=tid, budget_features=b, value_prediction=values[0].tolist()))
            if choice == 0:
                break
            self._trial_budget = b
            self.trial(session, choice-1, environment)
        output = self.infer(event.observation, event.goal, event.actions); evidence = self.evidence(session)
        logits, state = self.model.adoption_logits(output, codes, evidence)
        values = self.model.values(output, codes[:, 0], PHASES['adoption'], self.tensor([[0., 0.]]))
        choice, propensity, policy = self.choose(logits)
        self.decisions.append(dict(kind='adoption', session_id=session.id, history_ids=tuple(self.bank.index),
            evidence_ids=evidence['ids'], model_id=self.version, choice=choice, propensity=propensity, policy=policy,
            counts=state['counts'][0].tolist(), budget_features=[0., 0.], value_prediction=values[0].tolist()))
        self.promote(session, choice)
        return session

    def export_trace(self, episodes):
        self.assert_snapshot()
        return {'format': 'V224_CLOSED_ACTUAL_TRACE', 'closed': True, 'initial_history_ids': self.initial_history_ids,
                'model_id': self.version, 'world_id': world_identity(self.model), 'memory': json.loads(self.bank.to_json()),
                'decisions': self.decisions, 'thoughts': self.thoughts, 'generations': self.generations,
                'sessions': [self.session_record(s) for s in self.sessions.values()], 'episodes': episodes,
                'final_origin': self.active_origin, 'counters': self.counters}
