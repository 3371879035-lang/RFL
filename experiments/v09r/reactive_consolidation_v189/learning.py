"""V188 learner plus an explicit observation-driven action/episodic-memory layer."""
from base_learning import *
from base_learning import Agent as BaseAgent
from reaction import ReactionMemory, context_key


class Agent(BaseAgent):
    def attach_feedback(self, mode):
        self.feedback = ReactionMemory(mode)
        self.feedback_event = None

    def reset_episode(self, phase, episode):
        super().reset_episode(phase, episode)
        if hasattr(self, 'feedback'):
            self.feedback.reset()

    @torch.no_grad()
    def act(self, obs, training):
        proposed = super().act(obs, training)
        chosen, report = self.feedback.choose(context_key(obs), obs.hero, obs.legal,
            self.last_behavior_scores, proposed, self.last_choice['explored'])
        image, scalar, key, before, old, forecast = self.last_input
        forecast = float(self.last_readout_scores[chosen])
        self.last_input = image, scalar, key, before, chosen, forecast
        self.last_choice.update(report)
        self.last_choice.update(action=chosen, forecast=forecast)
        return chosen

    def receive_feedback(self, nxt, fact, persist):
        before, action = self.last_input[3:5]
        moved = tuple(before.hero) != tuple(nxt.hero)
        self.feedback.observe(context_key(before), before.hero, action, moved)
        self.feedback_event = None
        if fact.captured or fact.completed:
            self.feedback_event = self.feedback.finish(fact.captured, persist)

    def observe(self, nxt, fact, reward):
        super().observe(nxt, fact, reward)
        self.receive_feedback(nxt, fact, True)

    def observe_frozen(self, nxt, fact):
        self.receive_feedback(nxt, fact, False)
        self.last_action, self.last_pickup = self.last_choice['action'], fact.pickup
        self.local_t += 1
