"""Same learned modules; one history-conditioned predictor in training and action."""
import torch
from feedback_program_v220.network import joint_moments
from feedback_program_v224.network import FeedbackCreditNet, NetworkConfig
from . import filtering


class FilteredFeedbackNet(FeedbackCreditNet):
    def forward(self, observation, goal, actions, memory, code=None, belief=None):
        with torch.no_grad():
            belief = filtering.from_view(self, observation, goal, memory) if belief is None else belief
            filtering.require_query(self, belief, observation, goal, memory['ids'])
            root = filtering.root_dict(belief); k = self.config.hypotheses
            repeat = lambda t: t.repeat_interleave(k, 0)
            out = self.kernel(repeat(observation), repeat(goal), repeat(actions), repeat(root['encoded']), repeat(root['valid']),
                              belief.h, torch.arange(k, device=observation.device))
            out = {key: value.reshape(1, k, *value.shape[1:]) for key, value in out.items()}
            moments = joint_moments(root['weights'], out['value_mean'], out['value_variance'])
            state = torch.einsum('bk,bkad->bad', root['weights'], out['state'])
            # Policy can reference all real facts; the world initializer cannot recount the active segment.
            if belief.used_ids:
                policy_memory, policy_valid = self.encode_memory(memory)
            else:
                policy_memory, policy_valid = root['encoded'], root['valid']
        query = self.policy_query(torch.cat((observation, goal), -1))
        read, weights, gates = self.policy_reader(query[:, None, :], policy_memory.detach(), policy_valid)
        context = root['context'].detach()+self.policy_context(torch.cat((query, read[:, 0]), -1))
        if code is None:
            code = self.base_code[None]
        logits = self.actor_logits(state, moments, code+context)
        return {**out, 'logits': logits, 'policy': logits.softmax(-1), 'context': context, 'weights': root['weights'],
                'action_state': state, 'moments': moments, 'policy_memory_weights': weights, 'policy_memory_applicability': gates,
                'feedback_prediction': torch.einsum('bk,bkaf->baf', root['weights'], out['feedback_mean']).detach(),
                'innovation_prediction': torch.einsum('bk,bkap->bap', root['weights'], out['innovation_mean']).detach(),
                'next_prediction': torch.einsum('bk,bkao->bao', root['weights'], out['next_mean']).detach(),
                '_root': root, '_belief': belief, '_observation': observation, '_goal': goal, '_actions': actions}
