"""V203: conditional evidence age and context-scoped actual-trial adoption.

Reuses the frozen V202 algorithm source, never its task/runner. New neural
weights are analytically written; all experience updates are memory state.
"""
from dataclasses import asdict
import importlib.util
import math
from pathlib import Path
import sys
import torch
from torch import nn

_path = Path(__file__).resolve().parents[1] / 'weight_programmed_feedback_v202/model.py'
_spec = importlib.util.spec_from_file_location('v203_base_model', _path)
BASE = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = BASE
_spec.loader.exec_module(BASE)
Config = BASE.Config


class FeedbackNet(BASE.FeedbackNet):
    def __init__(self, config=Config(), conditional_age=True):
        super().__init__(config)
        self.conditional_age = bool(conditional_age)
        self.evidence_decay = nn.Linear(1, 1, bias=False)
        self.local_margin = nn.Linear(2, 1, bias=False)
        self.local_extent = nn.Linear(2, 1, bias=False)

    def _weights(self, queries, memory, minimum, scale, ages):
        if not self.conditional_age:
            return super()._weights(queries, memory, minimum, scale, ages)
        # The existing Q/K still computes the SAME normalized similarity.
        similarity = super()._weights(queries, memory, minimum, scale, torch.zeros_like(ages))
        # A datum ages when matching conditions are observed again, not merely
        # when many unrelated conditions happen to consume the global clock.
        order = torch.argsort(ages, descending=True)
        ordered = similarity[:, order]
        newer = ordered.flip(-1).cumsum(-1).flip(-1) - ordered
        local_age = torch.empty_like(similarity)
        local_age[:, order] = newer
        decay = self.evidence_decay(local_age.unsqueeze(-1)).squeeze(-1).exp()
        return similarity * decay

    def assess_local_trials(self, contexts, candidate_outcomes, incumbent_outcomes, goal):
        """Only new REAL paired trials authorize a scoped policy-state change.

        Exact public initial-condition identity is an explicit evidence scope,
        not a task label. Unknown conditions retain the previous whole policy.
        This is a risk-neutral decision estimate, NOT a significance test.
        """
        contexts = torch.as_tensor(contexts, dtype=torch.float32)
        new = torch.as_tensor(candidate_outcomes, dtype=torch.float32)
        old = torch.as_tensor(incumbent_outcomes, dtype=torch.float32)
        goal = torch.as_tensor(goal, dtype=torch.float32)
        if contexts.ndim != 2 or contexts.shape[1] != self.config.context_dim:
            raise ValueError('Actual paired trial initial conditions required')
        if new.shape != old.shape or new.shape != (len(contexts), self.f):
            raise ValueError('Paired actual outcomes must match the observed conditions')
        scope = torch.unique(contexts, dim=0)
        match = torch.all(scope[:, None, :] == contexts[None, :, :], dim=-1).float()
        count = match.sum(-1)
        difference = self.goal_readout(new - old, goal.expand_as(new)).squeeze(-1)
        # Zero-centered one-observation prior makes unsupported differences zero.
        estimate = (match @ difference) / (1. + count)
        raw_mean = (match @ difference) / count.clamp_min(1.)
        variance = (match @ difference.square() - count * raw_mean.square()).clamp_min(0.) / (count - 1.).clamp_min(1.)
        stderr = (variance / count.clamp_min(1.)).sqrt()
        margin = self.local_margin(torch.stack((estimate, stderr), -1)).squeeze(-1)
        extent = self.local_extent(torch.stack((count, torch.ones_like(count)), -1)).squeeze(-1)
        adopt = (margin > 0.) & (extent > 0.)
        return dict(rule='context_scoped_actual_paired_estimate', contexts=scope.tolist(),
                    counts=count.tolist(), raw_mean_differences=raw_mean.tolist(),
                    estimates=estimate.tolist(), standard_errors=stderr.tolist(),
                    adopt=adopt.tolist(), paired_differences=difference.tolist(),
                    risk_statement='Small samples can favor a worse policy by chance; adoption is reversible policy state, not a correctness certificate.')


@torch.no_grad()
def write_initial_weights(net):
    BASE.write_initial_weights(net)
    net.evidence_decay.weight.fill_(-math.log(2.) / 8.)
    # Expected utility maximization with a symmetric zero-centered prior. The
    # uncertainty is reported, not turned into another arbitrary global veto.
    net.local_margin.weight[0].copy_(torch.tensor([1., 0.]))
    net.local_extent.weight[0].copy_(torch.tensor([1., -1.]))
    return net


def save_initial_model(path, config=Config()):
    model = write_initial_weights(FeedbackNet(config))
    with open(path, 'xb') as stream:
        torch.save(dict(config=asdict(config), state_dict=model.state_dict(),
                        origin='analytic_weight_programming_v203', optimizer_steps=0,
                        environment_data_read_by_writer=0), stream)
    return model


def load_model(path, conditional_age=True):
    payload = torch.load(path, map_location='cpu', weights_only=True)
    model = FeedbackNet(Config(**payload['config']), conditional_age=conditional_age)
    model.load_state_dict(payload['state_dict'], strict=True)
    return model
