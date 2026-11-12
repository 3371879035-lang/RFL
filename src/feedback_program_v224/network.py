"""Actual-outcome trainable policy reading, candidate generation and critic heads."""
import torch
from torch import nn
from torch.nn import functional as F
from feedback_program_v220.network import ConditionalRead, mlp
from feedback_program_v222.network import consistent_comparison
from feedback_program_v223.network import ObservableFeedbackNet, NetworkConfig
from .memory import Schema


class FeedbackCreditNet(ObservableFeedbackNet):
    def __init__(self, layout, schema=Schema(), config=NetworkConfig(), comparison_rank=8):
        super().__init__(layout, schema, config, comparison_rank)
        d = config.width
        self.policy_query = mlp(schema.observation + schema.goal, d, d)
        self.policy_reader = ConditionalRead(d)
        self.policy_context = mlp(2*d, 2*d, d)
        self.critic_phase = nn.Embedding(4, d)
        self.critic = mlp(3*d+2, 2*d, 3)

    def forward(self, observation, goal, actions, memory, code=None):
        # World/measurement learning uses sequence_nll, not policy-return gradients.
        with torch.no_grad():
            output = super().forward(observation, goal, actions, memory)
        query = self.policy_query(torch.cat((observation, goal), -1))
        root = output['_root']
        read, weights, gates = self.policy_reader(query[:, None, :], root['encoded'].detach(), root['valid'])
        context = root['context'].detach() + self.policy_context(torch.cat((query, read[:, 0]), -1))
        if code is None:
            code = self.base_code[None, :].expand(observation.shape[0], -1)
        logits = self.actor_logits(output['action_state'], output['moments'], code + context)
        output.update(context=context, logits=logits, policy=logits.softmax(-1),
                      policy_memory_weights=weights, policy_memory_applicability=gates)
        return output

    def propose(self, output):
        context = output['context']; b = context.shape[0]; c = self.config.candidates
        extras = torch.cat((output['innovation_prediction'].detach().mean(1),
                            output['moments']['within_variance'].detach().mean(-1, keepdim=True)), -1)
        return torch.tanh(self.proposal_net(torch.cat((context[:, None, :].expand(-1, c, -1),
            self.proposal_keys[None, :, :].expand(b, -1, -1), extras[:, None, :].expand(-1, c, -1)), -1)))

    def practice_state(self, output, codes, evidence):
        p = self.null_memory; b, arms, d = codes.shape
        f = evidence['features'].to(p); sources = evidence['sources'].to(p.device); valid = evidence['valid'].to(p.device)
        count = valid.sum(-1).to(p.dtype)
        with torch.no_grad():
            raw = self.event_encoder(f) + self.source_embedding(sources)
        encoded = self.evidence_adapter(raw).reshape(b*arms, f.shape[2], d)
        valid = valid.reshape(b*arms, -1)
        encoded = torch.cat((self.evidence_null.expand(b*arms, 1, d), encoded), 1)
        valid = torch.cat((torch.ones(b*arms, 1, dtype=torch.bool, device=p.device), valid), 1)
        context = output['context'][:, None, :].expand(-1, arms, -1)
        query = self.evidence_query(torch.cat((context, codes), -1)).reshape(b*arms, 1, d)
        read, _, gates = self.evidence_reader(query, encoded, valid)
        states = self.evidence_fusion(torch.cat((context, codes, read.reshape(b, arms, d), count.log1p()[:, :, None]), -1))
        potential = self.contrast_mean(states).squeeze(-1)
        residual = F.softplus(self.contrast_scale(states).squeeze(-1)) + 1e-4
        mean, variance, covariance = consistent_comparison(potential, self.comparison_factor(states), residual)
        return dict(states=states, counts=count, contrast_mean=mean, contrast_variance=variance,
                    comparison_covariance=covariance, applicability=gates.reshape(b, arms, -1))

    def trial_logits_with_thought(self, output, codes, evidence, budget, thought):
        logits, state = self.trial_logits(output, codes, evidence, budget)
        context = output['context']; summary = thought['summary']; n = codes.shape[1]
        meta = torch.stack((thought['depths'].to(summary.dtype), thought['active_counts'].to(summary.dtype)), -1)[None]
        arm = self.thought_trial(torch.cat((context[:, None, :].expand(-1, n, -1), summary, meta), -1)).squeeze(-1)
        stop = self.thought_stop(torch.cat((context, summary.mean(1), budget), -1))
        return logits + torch.cat((stop, arm), -1), state

    def values(self, output, code, phase, budget):
        index = torch.full((code.shape[0],), phase, dtype=torch.long, device=code.device)
        return self.critic(torch.cat((output['context'].detach(), code.detach(), self.critic_phase(index), budget), -1))

    def dream(self, output, codes, tape, replay_decisions=None):
        from .imagination import unfold
        return unfold(self, output, codes + output['context'][:, None, :], tape, replay_decisions=replay_decisions)
