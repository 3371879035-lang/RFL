"""Actual episode continuity, fresh trial branches, and one assimilation per receipt."""
import torch
from feedback_program_v224.runtime import PracticeAgent as PreviousAgent, PHASES
from .identity import model_identity, world_identity
from .memory import MemoryBank
from .filtering import observe, state_record


class PracticeAgent(PreviousAgent):
    def __init__(self, model, namespace, rng, bank=None, thought_depth=3):
        super().__init__(model, namespace, rng, MemoryBank(model.schema, model.layout) if bank is None else bank, thought_depth)
        self.version = model_identity(model)
        self._beliefs = {}; self._live_belief = None
        self.filter_receipts = []

    def assert_snapshot(self):
        if model_identity(self.model) != self.version:
            raise ValueError('Weights or episode semantics changed without replacing the model')

    def replace_model(self, model):
        if model.schema != self.bank.schema or model.layout != self.bank.layout:
            raise ValueError('Observation semantics need an explicit conversion')
        version = model_identity(model)
        if version != self.version:
            self.current_code = None; self.current_candidate = None; self.active_origin = {'kind': 'base'}
            self._beliefs.clear(); self._live_belief = None
            for session in self.sessions.values(): session.active = False
        self.model = model; self.version = version

    def infer(self, observation, goal, actions, code=None, memory=None):
        if code is None: code = self.current_code
        view = self.bank.view() if memory is None else memory
        self._last_inference = self.model(self.tensor([observation]), self.tensor([goal]), self.tensor([actions]), view,
            None if code is None else self.tensor([code]), belief=self._live_belief if memory is None else None)
        return self._last_inference

    @torch.no_grad()
    def execute(self, observation, goal, actions, environment, episode, step=0, previous_id=None,
                session=None, arm=None, purpose='source'):
        if previous_id is None:
            if episode in self._beliefs:
                raise ValueError('A reset needs a new episode identity')
            self._live_belief = None
        else:
            state = self._beliefs[episode]
            if not state.used_ids or state.used_ids[-1] != previous_id:
                raise ValueError('Continuation is not the cached actual predecessor')
            self._live_belief = state
        try:
            event = super().execute(observation, goal, actions, environment, episode, step, previous_id, session, arm, purpose)
            before = self._last_inference['_belief']
            after, terms = observe(self.model, before, event)
            self._beliefs[episode] = after
            pre_record = state_record(before)
            self.decisions[-1]['conditioning'] = pre_record
            self.filter_receipts.append(dict(event_id=event.id, before=pre_record, after=state_record(after),
                component_log_likelihood=terms['component_log_likelihood'].tolist(),
                mask_log_likelihood=terms['mask'].tolist(), discrete_log_likelihood=terms['discrete'].tolist(),
                continuous_log_likelihood=terms['continuous'].tolist(),
                log_predictive=float(terms['log_predictive']), observed_continuous_coordinates=terms['observed_continuous_coordinates']))
            return event
        finally:
            self._live_belief = None

    def export_trace(self, episodes):
        data = super().export_trace(episodes)
        data.update(format='V225_CLOSED_ACTUAL_TRACE', world_id=world_identity(self.model),
                    filter_receipts=self.filter_receipts, actual_filter_updates=len(self.filter_receipts))
        return data
