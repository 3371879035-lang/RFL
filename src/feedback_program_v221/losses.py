"""Training targets are actual later outcomes, never the support observations themselves."""
import math
from feedback_program_v220.losses import factual_nll,off_policy_loss,replay_distillation_loss


def comparison_nll(state,arm_a,arm_b,actual_difference):
    mean=state['contrast_mean'][:,arm_a,arm_b]
    variance=state['contrast_variance'][:,arm_a,arm_b]
    if arm_a==arm_b:raise ValueError('Comparison training uses two different behavior arms')
    return .5*(math.log(2*math.pi)+variance.log()+(actual_difference-mean).square()/variance).mean()
