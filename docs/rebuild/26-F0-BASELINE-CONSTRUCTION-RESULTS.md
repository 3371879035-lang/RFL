# Baseline construction follow-up and CF-1 integration (2026-09-26)

## 1. Result and scope

**C3 passes its isolated construction checks with the scientific recovery endpoint
unchanged.** Its initial bank mean is 0.5144140624999989, below the existing threshold
0.7248574218749967. All 32 fresh operational runs meet maintained recovery at a positive
episode, and all remain above threshold through the remaining run. F0 itself remains
NOT VALID; no smoke, dev, confirmatory or RFL treatment data was collected.

This resolves the specific mismatch established in document 23 for a concrete new
candidate. It does not retroactively admit C1, establish that C3 is optimal, or prove
that RFL beats ordinary learning. The runs use ordinary A91 learning only.

## 2. Retained experiments

| Candidate | Construction | Fixed cap per run | Runs | Outcome |
|---|---|---:|---:|---|
| C1 | one optimistic t=0 entry | 40 | 32 | construction pass, endpoint-observability rejection |
| C2 | every effective Q entry initially zero | 6912 | 32 | detectable deficit, no maintained recovery within cap |
| C3 | one time layer of optimistic wrong-action entries | 576 | 32 | detectable deficit and maintained recovery, construction pass |

These are **different construction hypotheses with different budgets**, not a
controlled efficacy comparison between learning algorithms. No failed run was dropped,
no key was replaced, no cap was extended, and no scientific claim is estimated here.

C2 completed 221184 training episodes in 249.836 seconds. Its ordinary learning
curves move, but 0 of 32 runs reaches the frozen recovery condition by episode 6912.
This rejects that instance/budget for the current construction; it does not prove
zero-initialized Q learning cannot eventually learn the task.

C3 completed 18432 episodes in 17.783 seconds. Its construction witnesses occur
between episodes 27 and 372; 32 of 32 maintain recovery through the end. These are
diagnostic witness counts/ranges, not scientific rates or an effect-size estimate.
All final levels equal the healthy bank mean 0.7630078124999966. This also means
that late retention spread must NOT be assumed: no f_R selection was performed,
and cap is not a locked scientific horizon T.

## 3. Why C3's scope was chosen

The exact reference bound rules out all t=0-only Q corruptions under otherwise
healthy future decisions: even the worst first action in every initial cell cannot
lower the average below the unchanged recovery threshold. This is stronger than
the finite-sample C1 finding and applies to all registered prefixes and full support.

C3's deterministic constructor examines time layers in ascending order, selecting
the first whose fixed, untrained corrupted state is observable on every bank. It
inspected only t=0 (rejected) and t=1 (qualified). It then froze the exact 840 legal
Q edits, alpha=1/2, epsilon=1/10, cap=48*12=576 and new keys 930001..930032 before
training. Many legal domain rows are not on healthy trajectories; the edit count is
not an estimate of encountered faults or a scientific update budget.

The constructor uses evaluator-side reference values. It is a synthetic stage
baseline with known retained knowledge, not a learner-side method for discovering
errors. Its preserved knowledge and lack of corruption after t=1 distinguish it
from the full-reset construction; this is why a smaller prespecified construction
budget has a mechanistic rationale, not evidence that it is a better learning algorithm.

## 4. Exact execution and evidence integrity

The cell factorization was checked against a full persistent learner, including
actual A91 transitions, the entire effective Q state, and direct bank rollouts.
For C2 all 48 cells were exercised; C3 additionally repeated each cell to exercise
updates after the initial change. No training or policy step uses a reference-policy
shortcut. Grouped evaluations are expanded into the original scene order and summed
with the frozen left-to-right algorithm.

Both operational runs performed uncached evaluation checks at four fixed checkpoints
per key. All 128 checks passed for each candidate. Each result stores initial cell
returns plus every per-episode cell-return change, so the whole-bank curve can be
reconstructed without rerunning learning or inventing unrecorded points.

Primary artifacts are in `experiments/v03r/c2_construction/` and
`experiments/v03r/c3_construction/`: `manifest.json`, `seedless.json`, `runs.jsonl`,
`report.json`, `frozen_sources.zip`. Archives retain the exact pre-acquisition source
bytes and are checked against manifests. New keys 920001..920032 and 930001..930032
join prior operational keys in the permanent exclusion set for scientific sampling.

The C2 source archive predates the optional factory parameter added to its runner
to reuse the same acquisition loop for C3. The default C2 behaviour is unchanged.
Both source archives predate the CF-1 integration below; its SE/cache helpers were
not on either operational curve path. Do not equate current working-tree bytes
with archived acquisition bytes.

## 5. CF-1 implementation completed

Rev 4 already requires authoritative SE to be computed from the actual slice values
in ascending bank order, with constant values handled exactly. The numerical helper
implemented that rule, but `MasterBaseline.error` still used the cancellation-prone
count/sum/squared-sum expansion. Thus the approved correction was not connected to
the artifact API that future selectors would call.

`error` now reads the slice values and calls the authoritative two-pass helper.
`generic_error` supplies the same rule for uncontacted sites. Both statistic-cache
paths use the specified left-to-right sums. `sufficient_error` remains available
only as a labelled diagnostic demonstrating why the old expansion is unsafe.

Regressions reject entering the diagnostic path, require exact zero SE for constant
0.1/0.7/0.9 slices, preserve empty-set handling, and compare the real artifact API
against the value-based definition. This is implementation of an existing rule,
not a change to a scientific threshold or selector.

## 6. Remaining decisions and boundaries

C3 is ready as a concrete amendment candidate, with reproducible construction evidence.
The production baseline is still the old initializer; a construction pass is not an
unrecorded switch. The remaining F0 work includes adopting an explicit stage initializer
and cap, completing master acquisition/serialization/manifest/lock commands, validating
the horizon and retention selection logic, and resolving the independent practical-effect
rationale for the persistent-regime P RMST threshold. Nothing here ratifies that threshold.

C2's numerical scale of 0.001 was an engineering budget judgement, not a convergence
guarantee. In document 24 its numeric reuse of epsilon_s must not be read as a unit
identity: a Q-value precision scale has return units, whereas a curve slope tolerance
has return-per-episode units. This clarification changes neither the frozen cap nor
the failed result, and supplies no new reason to extend the budget.

## 7. Final validation

Final full regression: **790 passed, 1 skipped** (791 collected), 131.532 seconds,
`experiments/v03r/c3_cf1_full_regression.xml`. The targeted acquisition/numerics
regression passed 31 tests with the same existing skip. The skip is the fully
consulted Process domain having no uncontacted representative, not a new failure.

`scripts/verify_f0_candidate_records.py` independently verified ordered unique keys,
manifest/data digests, every archived source digest and every curve point reconstructed
from cell-return events. Results: 221216 points for C2 and 18464 for C3, all bit-equal;
63 and 67 archived source files verified respectively. Evidence is
`experiments/v03r/c2_c3_record_integrity.json`. All code and evidence remain local,
uncommitted and unpushed. The original failed construction artifacts are preserved.
