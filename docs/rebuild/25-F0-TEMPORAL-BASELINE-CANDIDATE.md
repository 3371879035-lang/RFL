# C3: structurally chosen single-time-layer overestimation

## 1. Predeclared construction rule

This is an isolated development-baseline construction, not a B2 treatment or a
production change. C2 tests learning from a completely untrained Q table; C3 tests
recovery with the remainder of the learned table intact. Its rule does not consume
C1/C2 training curves, select seeds or choose hyperparameters by performance.

Enumerate time layers t=0..H-1 in ascending order. For every legal reference row
in one layer, let b=max Q*. If the row has strict suboptimal actions, choose the
smallest action ID among the **minimum-valued** actions, with value q, and set
that one entry to b+(b-q). Leave all other entries at the reference. All non-Q
stores stay healthy. Skip rows with no gap. The initial corrupted action is then
greedy, and after reaching its uncorrupted successor its target is its healthy q.

For each layer, evaluate the fixed state on complete U2 support and on all four
registered bank prefixes. Choose the **earliest** layer whose initial mean is
below the existing 95%-of-healthy threshold on every bank and full support.
If none exists, reject this construction without any training run. This is a
finite model-based structural selection, disclosed as such; it is not evidence
about learned RFL or a naturally occurring defect distribution. No statistical
data or operational key enters the choice. All inspected layers are retained.

The intent is a defect that is detectable by the existing metric without erasing
the whole learner. t=0-only states are already ruled out by the support bound.
At most one layer defect is encountered per episode. Ordinary Q updates before
that layer may temporarily propagate its overestimate backwards; these effects
are allowed and measured, not bypassed or patched away. Two direct visits are
not claimed to guarantee the entire learner has recovered.

## 2. Fixed operational envelope

Use alpha=1/2, epsilon=1/10, the unchanged recovery threshold and K=3 rule, and
the 1024-scene bank at every episode. Budget **48*H=576 episodes per run**, a
pre-data engineering heuristic allowing one horizon's worth of expected visits
per initial cell, not a convergence guarantee or a power calculation. Unlike
the full reset, direct targets beyond the corrupted layer are initially healthy.
Do not increase the budget if the construction fails.

Fresh operational keys: 930001..930032, reserved against all scientific stages.
Same binary construction checks as C2: initially below threshold, no-learning
control censored, real Q movement, moving curves, distinct curves between runs,
and at least one maintained recovery at a positive episode. Finish every run.
No scientific selector or ranking uses this operational data. Record post-recovery
relapses instead of treating first recovery as permanent.

## 3. Implementation and provenance

Use the same exact cell-factorization principle as C2: all state changes are Q-only,
and kappa/phase/option remain fixed within episodes. Each partition still uses the
existing A91 episode, chronological sweep and transaction, with boundary assertions.
Evaluation is actual learner rollout. Keep raw per-cell return changes, allowing
every whole-bank curve point to be reconstructed in the original summation order.
Validate uncached evaluation at 0,H,cap/2,cap. Compare a full learner against the
partitioned learner in independent regression fixtures before acquiring new keys.

Freeze source hashes, the exact selected layer and edits, the complete seedless
record and a source archive before training. A pass is construction evidence only;
F0 still needs an explicit amendment and the remaining instrument/lock work.
