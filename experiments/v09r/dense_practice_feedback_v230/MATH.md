# V230: dense actual-outcome supervision for the practice proposal

This is an explicitly result-informed second experiment, not a retry or a replacement
of V229. V229 completed: at 24576 steps/model its learned selector lost to the strong
F-R comparator in both tasks and lost to random selection in pursuit. Each selector
had only SIX distinct paired-effect targets, repeatedly reused by many updates.
Sparse supervision is a concrete limitation, not a proven sole cause of the loss.

## One change in what the proposal head can learn from

For every transition in an actually COMPLETED trajectory, measure its remaining
physical outcome vector G_t=sum_{k=t}^{T-1} f_k, then y_t=w_goal^T G_t. These are
observations from that historical behavior, not the correct answer for a new state.
Incomplete tails have NO such target, rather than an invented zero.

Train the existing head e_theta(h,a) on those conditional outcome samples:

    L_actual_return = Huber(e_theta(h_t,a_t), y_t).
    L_actual_pair   = Huber(e_theta(h,a)-e_theta(h,b), D_actual_pair).
    L = L_Q + L_facts + 0.1 L_actual_return + 0.1 L_actual_pair
        + 0.2 L_signed_preference (only during the candidate's rehearsal).

The ordinary trajectory gives a dense empirical prior; the new paired intervention
checks the proposed action contrast. A single historical outcome is not a causal
label. The return head averages conditional samples collected under evolving,
partly exploratory behavior; it is not guaranteed to equal the current greedy
policy's return. Its output is ONLY used to propose another actual trial, never as
a Q target or direct policy override. Applicability and representation receive
gradients as in V229. All other code-level learning conditions remain unchanged.

This does not make F0 a reward learner: F0 is not in this targeted experiment. These
are the same reward-only mixed agents as V229, with a denser proposal learning path.

## Fixed comparison before execution

Two newly trained conditions: dense/random and dense/learned. The sole algorithmic
change from their corresponding V229 conditions is the actual-return loss. Same
architecture (213329), initialization, task, reward, seeds 271/277/283, noise splits,
memory, real trial horizon, exploration, step and optimizer budgets. V229's saved
original F-R AND open/random AND open/learned results are reused as historical
matched comparators; none of those trained models or evaluations is rerun.

Pursuit + generic, three seeds, six rounds, 4096 steps and 256 optimizer calls each.
New training 294912 actual steps; evaluation at rounds 0/3/6, 32 episodes at epsilon
0 and .1: maximum 301824 evaluation steps. Total cap 596736, wall cap 1200 seconds,
six CPU workers, one Torch thread each. First failure retained, no retry or budget
extension. Same evaluation cases are reused to isolate this modification; this is
developmental evidence following V229, not a new untouched confirmation population.
Positive, zero, adverse results all remain. No full 3-hour superiority claim.
