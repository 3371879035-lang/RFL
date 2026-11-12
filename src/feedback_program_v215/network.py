"""V7: keep history as predictive evidence, not a mandatory action quota."""
import torch
from torch import nn
from torch.nn import functional as F

from feedback_program_v214 import HistoricalFeedbackNet


class ExpectedUtilityReadout(nn.Module):
    def __init__(self, goal=(0., 1.), epsilon=.2):
        super().__init__()
        if len(goal)<2 or any(not 0<=v<=1 for v in goal) or not 0<epsilon<1:
            raise ValueError('Bounded public goal and explicit action exploration required')
        self.epsilon = epsilon
        self.weight = nn.Parameter(torch.tensor([goal], dtype=torch.float64), requires_grad=False)

    def forward(self, prediction):
        if prediction.ndim != 3 or prediction.shape[-1] != self.weight.shape[-1] or prediction.shape[1]<2:
            raise ValueError('Use batch/action/outcome predictions with at least two actions')
        scores = F.linear(prediction, self.weight).squeeze(-1)
        best = scores.argmax(-1)
        count = scores.shape[-1]
        behavior = (1.-self.epsilon)*F.one_hot(best, count).to(torch.float64)+self.epsilon/count
        top = scores.topk(2, dim=-1).values
        margin = top[:,0]-top[:,1]
        return behavior, scores, margin


class DecisionSeparatedNet(HistoricalFeedbackNet):
    """Only the decision readout changes; V214 factual learning is inherited unchanged."""
    def __init__(self, history_model, temporal_model, history, epsilon=.2, goal=(0.,1.)):
        super().__init__('conditional_gate', history_model, temporal_model, history, epsilon, goal)
        self.mode = 'decision_separated_v215'
        self.readout = ExpectedUtilityReadout(goal, epsilon)
        self.eval().requires_grad_(False)

    def predict(self, rows):
        prediction, previous_behavior, share, cache = super().predict(rows)
        behavior, scores, margin = self.readout(prediction)
        cache.update(source_mixture_behavior=previous_behavior, decision_scores=scores,
                     estimated_margin=margin)
        return prediction, behavior, share, cache

    @torch.no_grad()
    def offer(self, context, observation_id):
        wire = super().offer(context, observation_id)
        cache = self.pending[1]
        wire.update(decision_scores=cache['decision_scores'][0].tolist(),
                    estimated_margin=float(cache['estimated_margin'][0]),
                    source_mixture_behavior_not_executed=cache['source_mixture_behavior'][0].tolist(),
                    history_share_semantics='predictive_weight_not_execution_fraction')
        return wire
