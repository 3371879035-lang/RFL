# V227: decision learnability, actual conditional effects, capacity-matched training

This is a substantial compact revision, not a patch that retrospectively makes V226 successful. V226 and all earlier bytes/results remain unchanged. The user authorized 3 hours on pursuit and generic tasks concurrently on 2026-11-12. Both domains start from scratch; no pretrained competence is claimed.

## 1. What the old equations actually allow

V225 `forward` builds action states under `no_grad`; V222 `actor_logits` detaches states and predicted moments. The trainable history/goal context enters the same scalar actor for every action. Write its simplified form as

    l_a = v^T GELU(W s_a + U c + b).
    d(l_a-l_b)/dc = U^T diag(GELU'(z_a)-GELU'(z_b)) v.

In the linear limit, a common context contributes the same offset, exactly cancelling in softmax. With GELU this is not an exact invariance, but discrimination depends on a mixed interaction with the detached action states. This is an architectural bottleneck, NOT proof that its gradient is always zero or the sole cause of the failed run. The observed almost-uniform stochastic policy and constant greedy action are compatible with weak discrimination.

The revision has a directly trainable observation/goal/history encoder z and independent action outputs Q_a(z). TD gradients reach this encoder. Physical-fact heads do not impose their loss on the Q encoder: they take detached z in mixed agents. F0 instead trains its encoder through observed physical targets. Consequently improving factual prediction is neither assumed to imply better control nor allowed to suppress the only task-gradient path.

## 2. Remove an actual objective loophole

V226 R-only used max(0,d_t-d_{t+1}). The cycle .5 -> .25 -> .5 earns .25 despite zero net progress. This is not potential shaping. The generic physical dynamics are reused unchanged, but the NEW reward convention is terminal-only:

    R+ = 1[success] + 1/(1+d_T), at the real terminal, zero otherwise.
    R+- = R+ - 1[terminal failure].

Both groups' task reports remain success and final distance. R-only is genuinely nonnegative. Pursuit preserves its existing .015 per real step + treasure pickup, with an additional -1 capture penalty only in punishment groups. This protocol change prevents a causal one-factor comparison to V226.

## 3. Memory is evidence, not an answer

Each memory node encodes an actual public transition (observation, action, next observation, physical facts, terminal). A learned query/key read includes an explicit null node. A learned sigmoid applicability modulates the read. The direct current-state path remains available. The same evidence is replayed for optimization, but its event ID is never counted as a new environmental observation. No old residual is copied into an action value as truth. Attention/applicability values are NOT calibrated causal probabilities.

For F0, directly observed finite-window targets M_h are learned for h in {1,4,16,64}; only completed windows or real terminal absorption have labels. Unfinished tails remain masked. Public goal readout ranks these predictions. No reward packet, Q target or Q* enters F0. This remains goal-directed prediction and can resemble value learning; 'no explicit reward input' does not prove it is philosophically outside RL. F0's limited prediction horizon is disclosed.

## 4. Historical hypotheses must meet actual trials

A failure exposes candidate historical source states, not a unique true cause. N227 ranks the latest failed trajectory's candidate states with learned factual disagreement/error, and proposes an alternative using learned fact/effect outputs. Other outer groups use a randomly chosen failed-history source; RL-outer has no factual model. No private environment state is fed to a learner.

At a source s, two actions a,b receive two fresh, paired actual continuations with common future random numbers and a fixed continuation policy. For H=16:

    Delta_H(s,a,b) = (1/2) sum_j [U_H(real rollout a,j)-U_H(real rollout b,j)].

All outcomes, including zero/adverse ones, are retained. The separate effect head learns E_a(s)-E_b(s) against Delta_H. This is a conditional, finite-horizon policy-continuation effect, not a probability of a unique cause. It MUST NOT be substituted as a full-horizon Q target. Two replicates are an engineering screen, not a statistical significance test.

A positive repeated effect proposes a temporary teacher preference update. A matched ordinary-learning reference receives the same number of base updates on identical replay minibatches. The teacher must beat that reference in two new paired full tasks. A student is then distilled from that tested teacher; a second matched reference receives the same base updates, and the student must again beat it on two different paired full tasks. Only that student may replace the live model. Failed teachers/students leave their ordinary reference in place. Practice, rejected candidates, validation and optimization are all charged.

SLEEP is thus bounded rehearsal/distillation of an empirically tested candidate, not a claim to reproduce the original paper. History-guided proposal/test/reuse is Dream-RSI-inspired; no mature free-running dream world model is claimed.

## 5. Fair comparison and conclusions

Six groups: RL-plain, RL-outer, F0, F-RP, F-R, N227. All use exactly the same compact tensor architecture and initialization per seed, including the memory encoder; irrelevant small output heads remain inactive and active/inactive parameter counts are reported rather than padded with a huge unused network. N227 uses R-only Q behavior plus factual/effect learning. Its contrasts with F-R concern history-based proposal/effect reuse, not punishment.

Every round allocates 4096 real training/practice/gate environment calls and 256 optimizer calls to EACH group. RL-plain spends all on ordinary learning. This matches calls, not FLOPs or unique information: a branched simulator continuation and a new full task are different experiences. Wall time, steps, completed episodes, optimization counts, discarded trials and acceptance are reported. Three independent seeds per domain; the two domains run concurrently in six CPU workers for one shared 10800-second window including final evaluation. No comparison of raw scores across domains.

Fixed-weight greedy and epsilon=.1 evaluation are both reported, separately. They test consolidated competence, not an always-on extra-test inference service. Training records additionally report the real online candidate/gate outcomes. Independent evaluation experience never enters training memory or replay. Initial and final banks have the same 32 scenarios per domain/seed/policy mode. All six groups and all workers reach a barrier after each round; final evaluation uses the last completed common round, not a stale power-of-two checkpoint.

Double-DQN target: y = r + gamma(1-done) Q_target(s', argmax Q_online(s')). Replay uses only real transitions. Source: van Hasselt et al., https://arxiv.org/abs/1509.06461. This is a standard baseline component, not a new RFL theorem.

The experiment may still fail: finite-window F0 can be myopic; public partial observability and limited historical memory remain; an applicability gate is not calibrated uncertainty; two-task adoption can be noisy; three seeds are limited. Positive, zero and negative results are all admissible. Do not infer generality, causal-factor percentages, saturation, or superiority from this implementation check.
