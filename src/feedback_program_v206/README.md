# V206: frozen arithmetic, evidence-dependent memory, real trial decisions

This is the first bounded module implementation of `MEMORY_AND_TRIAL_MODEL_V2.md`, not a general neural agent or a replacement for V205's multi-step additive planner.

## Actual mechanisms

- A finite set of unary selectors reads current binary fields or past event positions. The learner is not given the hidden relevant position, task family, regime, or generating probabilities.
- Each selector has factual outcome statistics at three cross-episode time scales (half-lives 8, 32, infinity). Pre-observation squared errors update the relative weights. Missing history has its own category.
- Neural `Parameter` tensors implement fixed arithmetic and never change. Evidence counts and mixture weights are **mutable learner state**, not parameter training. Freezing parameters does not imply that behavior cannot change.
- A candidate is an immutable snapshot. It is compared with the actual incumbent in fresh paired trials. A finite-budget dynamic program chooses additional trials, keeping the incumbent, or adoption. Only actual outcomes increment trial counts.
- Shared initial experience, discovery, trials and deployment all feed the next candidate in chronological order. Held-out evaluation never feeds learning. The incumbent is not frozen across cycles if a real adoption occurs.

## Limits that matter

1. The network does not invent feature operators. It selects and combines a human-declared unary family; this family cannot represent XOR perfectly.
2. Success/failure is an explicit goal-completion signal. This is not absence of preference, not unsupervised learning, and not a comparison against pure RL.
3. Exponentially decayed Beta-like counts are predictive pseudocounts, not calibrated Bayesian evidence. The separate trial posterior uses integer actual outcomes.
4. The dynamic program is optimal only inside its declared two-policy, stationary, binary-outcome prior model. Its utility cost of 0.02 per pair is illustrative, not measured time or a universal threshold.
5. History selection by predictive error is not causal attribution. Testing a whole policy can measure a policy difference without identifying which past event caused a failure.
6. No semantic observation encoder, parameter optimization, sleep/distillation, arbitrary long-horizon planning, or game adaptation is supplied by this module.

The experiment is `experiments/v09r/memory_trial_model_v206/`. Its first execution and any failure are retained; old V205 experiments are not rerun.
