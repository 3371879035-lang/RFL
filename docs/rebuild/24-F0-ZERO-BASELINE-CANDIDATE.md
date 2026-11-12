# C2: full zero-Q baseline construction

## 1. Scope and rationale

This is a new, isolated **stage-baseline candidate**, not a change to A87's canary,
the production initializer, B2 treatments, recovery endpoints or F0 validity.
It follows the obstruction in `23-F0-RECOVERY-OBSERVABILITY.md`. User continuation
authorises implementation and construction experiments; it is not evidence of
scientific efficacy or of a completed formal review.

In the reference, every initial cell has at most 0.06 first-action regret. Taking
the worst first action in all 48 (kappa, phase, option) cells and then following the
healthy policy gives mean 0.7441666666666665 versus healthy 0.7591666666666667 on
uniform full support. The 95% threshold is about 0.72120833. Thus **no t=0-only
Q initialization can make the whole-support baseline unrecovered** while later
decisions remain healthy. This is a support bound, not a training experiment.
The script also evaluates this lower envelope on each registered bank prefix.

The C2 initializer assigns effective Q=0 at **every legal address**, not an empty
sparse store (which would mean Q*). All non-Q stores remain healthy. This is a
common-value initial prior without action preferences beyond the frozen tie rule;
it uses the reference only to enumerate the legal domain and canonicalize storage.
There is no selected corruption location, gap multiplier or outcome-tuned magnitude.
Its role is ordinary-learning baseline acquisition from an untrained table,
not a claim that real errors erase all knowledge, nor a treatment for a local event.

## 2. Pre-data envelope

Keep alpha=1/2, epsilon=1/10 and all registered evaluation-bank prefixes. The
scientific 95%-of-healthy, K=3 maintained-recovery definition is unchanged.

The old cap=40 is retained with the rejected local construction. C2's proposed
cap is dimension-based, declared before any new stream:

- 48 exogenous initial cells;
- H=12 kernel steps per episode;
- n=ceil(log2(R/epsilon_s))=12 half-error reductions, with epsilon_s=0.001
  inherited as a numerical design scale and conservative return range
  R=|success-failure|+H*|step_cost|=2.24;
- **cap = 48 * 12 * 12 = 6912 episodes per run**.

This is a conservative engineering budget heuristic, NOT a convergence theorem:
changing bootstrap targets, uneven visits and exploration prevent interpreting it
as a guaranteed contraction rate or a sample-size/power calculation. epsilon_s is
not used here to change the recovery endpoint. The budget is not extended on failure.

New non-scientific keys: 920001..920032 inclusive, reserved permanently against
smoke/dev/confirmatory. One candidate and one full run. No treatment arm, selector,
ranking, power calculation or scientific effect estimate uses these observations.
No scientific seed is drawn. Freeze protocol, hashes and source archive first.

## 3. Necessary construction checks

Before training, for N=100,256,512,1024 and the full support, check initial level
strictly below the unchanged recovery threshold. The no-learning control must be
censored, rather than recovered at zero. These are binary negative-control checks.
Then on the full operational workload require Q movement, a moving bank curve,
different whole curves between keys, and at least one run with a maintained recovery
at positive episode index using the 1024-scene bank and complete episode grid.
All rows and later changes are recorded even after first recovery; no early stop.
Failure preserves every observation and rejects the construction.

Passing these conditions is necessary, not sufficient, for a development lock.
It does not select T, a grid, retention form, collateral refinement or effect size,
nor does it guarantee nonconstant late retention values. Those remain separate
protocol questions and scientific-development checks.

## 4. Exact computational reduction, isolated from production

With healthy non-Q stores and no environment fault, kappa, phase and option stay
fixed within an episode. A91 edits Q addresses only in that cell. A full Q table
therefore factors into 48 independent tables. The construction runner uses these
partitions for storage but calls the existing A91 rollout, sweep and transaction
on the selected partition. It refuses edits outside that partition; a reference
fallback in another partition is never used during a legal episode.

Evaluation uses actual learned_rollout on each partition, not Q* predictions. In
this no-fault kernel, tape error_flag and cause_rank cannot affect transitions;
their effects are guarded by fault-mask branches. Evaluate one real rollout per
(kappa,phase,option) cell and expand its value into the original bank order, keeping
all repeated scene weights and the frozen left-to-right sum. After a training
episode only its one cell is invalidated. This does NOT redefine the sample size:
1024 denotes the original scene bank, not 1024 independent transition outcomes.

Tests compare the partitioned learner against a full zero-initialized learner on
actual keyed transitions, effective Q tables, and direct full-bank rollouts. The
runner performs fresh uncached checks at fixed checkpoints 0, H, cap/2 and cap.
An invariant/cache mismatch is a construction error, not permission to smooth data.

This reduction is specific to the isolated ordinary-Q candidate. It is not enabled
in the production B2 path, mixed updates, external faults or collateral acquisition.
