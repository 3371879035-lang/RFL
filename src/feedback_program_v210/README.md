# V210 fixed-parameter adaptive feedback network

This is a finite-categorical hybrid: an analytic neural relation lift, explicit
temporal factual memory, and a separate sequential paired-evidence controller.
It does not train neural weights, import a game, provide a Q* oracle, or implement
multi-step imagination / SLEEP distillation.

## Data flow

1. Construct `AdaptiveFeedbackNet(cardinalities, actions, outcomes, block_size, hazard)`.
2. `grow(cell_budget)` instantiates the next public relation structures. Record
   its replay reads, cell allocation, and elapsed time as computation costs.
3. Add chronological `Fact` objects through `observe`. Set one initial snapshot
   with `set_initial_policy` before attempting a replacement.
4. Freeze a candidate bank with `snapshot(goal)` BEFORE acquiring ranking data.
5. `rank_candidates(bank, active, new_ranking_records, epsilon)` returns a
   nomination carrying the selection-data cutoff, plus non-adoption scores.
   All ranking facts also belong in ordinary memory. An unguided nomination is
   available as `net.nominate(local_snapshot)`; it is not an improvement claim.
6. `start_trial(nomination, persistent_evidence_book, horizon=..., switch_cost=...,
   max_pairs=..., pair_cost=..., epsilon=...)` fixes the comparison and budget.
7. The external task actually executes both fixed policies on paired conditions.
   Feed both public records through `record_trial_pair`. This preserves both in
   ordinary memory while keeping the comparison snapshots frozen.
8. When no longer `continue`, `respond_to_trial` adopts the candidate or preserves
   the incumbent. An explicit expansion budget may grow the hypothesis space.

The evidence book persists across candidates. IDs must refer to distinct actual
observations; the Python interface alone cannot prove an event occurred. A real
experiment still needs raw external capture. Same observed context is necessary
for this pairing protocol but alone does not prove comparable hidden conditions.

`unresolved_keep` is not a finding of zero effect. Snapshot identity proves exact
snapshot equality only, not general behavioral inequivalence. Goal utilities in
[0,1], epsilon, future deployment horizon, cost, and alpha are explicit inputs;
no implicit universal risk/benefit threshold is imposed by the package.

The recorded checks and budget analysis are in
`experiments/v09r/adaptive_feedback_v210`. Their inputs are mathematical fixtures,
not new task performance evidence. Their exclusive launchers preserve the first
capture and deliberately do not overwrite it on a second invocation.
