# V231: predictions influence practice probabilities, not an argmax instruction

Result-informed development, after the completed V229 and V230 failures; all earlier
bytes/results retained. In V230 pursuit learned selection, predicted improvement
averaged +0.176106 but actual paired improvement averaged -0.070833 over 18 choices.
Adding dense actual-outcome supervision did not fix this selected-set optimism.
This does not identify the sole cause: policy mismatch, approximation, correlated
errors and limited data remain. It does show that repeatedly choosing the largest
prediction is not justified by those observed trials.

## One choice-rule change, not another gate

For the existing 16-state history sample, define p0(c,a) uniform over sources and
then uniform over legal alternative actions within each source. Let g(c,a) be the
same learned, real-data-trained predicted effect as V230. The allocation problem

    maximize_p E_p[g] - tau KL(p || p0)

has solution p(c,a) = p0(c,a) exp(g(c,a)/tau) / Z. Use tau=1 in the unchanged task
utility units (one pursuit treasure / one generic success unit), plus the same
20% uniform exploration as V230. This is not confidence calibration or a causal
probability. It is an explicit regularized stochastic allocation of REAL trials.
Every legal option retains nonzero mathematical probability; no confidence veto,
worst-case penalty, or fixed 'important cause' list is introduced. Candidate practice
and the single actual final comparison still determine subsequent consolidation.

Taking the maximum of many noisy estimates can preferentially select positive
estimation errors even when their unselected average is zero. The soft allocation
reduces hard exploitation of the largest estimate; it does NOT guarantee unbiased
selection or better performance. No performance conclusion is assumed in advance.

All V230 architecture, dense factual-return training, paired-effect training,
loss weights, memory and real-trial budgets remain. No new neural head or parameter.

## Predeclared final bounded comparison in this repair pass

One new condition, soft-learned. Pursuit and generic, seeds 271/277/283. Same fresh
initializations and report cases as V229/V230. Six rounds of 4096 real steps and
256 optimizer calls per model. 147456 training steps; evaluations at 0/3/6, 32
episodes at epsilon 0/.1, maximum 150912 evaluation steps. Cap 298368 total steps,
900 wall seconds, six CPU workers/one Torch thread each. Stored V229/V230 comparators
are reused, never rerun. This is adaptive development on the same cases, not held-out
confirmation. This repair pass stops after this comparison regardless of its sign;
no budget escalation or tuning until a positive result appears. F0 remains outside
this targeted reward-only mechanism test and is not claimed fixed.
