# F0 follow-up: construction success does not imply recovery observability

## 1. Disposition (2026-09-26)

The isolated C1 proposal in `22-F0-INITIALIZER-CANDIDATE.md` passed its predeclared
construction experiment but is **NOT ADMITTED as the F0 development initializer**.
The production initializer and scientific recovery rule remain unchanged. This is
a new measurement-design finding, not evidence against RFL learning benefit.

The reason is a seedless negative-control failure: both the rev-4 initializer and
C1 are classified as recovered at episode zero even if the learner never updates.
This matters because F0's retention admissibility compares against the per-run
restricted recovery time and refuses undefined correlations with constant series.

## 2. What C1 did establish

Its protocol and source hashes were frozen before a single new keyed run. All
32 reserved operational keys 910001..910032 ran exactly 40 episodes against the
1024-scene bank, alpha=1/2, epsilon=1/10. There was one candidate and no sweep.

All five **candidate** construction propositions passed. The affected address was
visited in 14 of 1280 episodes. Fourteen runs recovered behaviour and maintained it
through their remaining checkpoints. None removed the Q override exactly. These
are operational construction diagnostics, not an estimated scientific recovery rate.

An actual chronological-sweep fixture restored the healthy action on the first
matching greedy visit. Its repaired state matched healthy returns on all 5760 U2
scenes, despite a remaining numeric deviation. This supplies a concrete counterexample
to treating exact Q equality as a necessary condition of behavioural recovery.

Artifacts: `experiments/v03r/c1_construction/manifest.json`, `runs.jsonl`,
`report.json`, and `frozen_sources.zip` in that directory. The archive retains all
61 manifest-hashed files as they stood before acquisition, verified byte-for-byte.
After acquisition, section headings in document 22 were numbered for the spec
auditor and the RMST label was corrected from Process to persistent regime P;
its frozen pre-acquisition text is in the archive. Later working-tree
edits must not be mistaken for the source of these observations. A rerun refuses
source mismatch and existing outputs rather than silently replacing evidence.

## 3. A stronger, seedless necessary check fails

`scripts/f0_recovery_observability.py` reads no operational or scientific run. It
constructs healthy, rev-4 and C1 states and evaluates the frozen bank candidates
and the entire U2 support. The two defective states produce identical return
vectors: one undervalues action 3, the other overvalues action 4, but both choose
action 4 at the same context and otherwise behave identically.

At the 1024-scene bank:

| Quantity | Value |
|---|---:|
| Healthy mean | 0.7630078124999966 |
| Defective mean, either initializer | 0.7625781249999969 |
| Existing recovery threshold, 0.95 times healthy | 0.7248574218749967 |
| Actual initial deficit | 0.0004296874999997202 |
| No-learning control recovery time | 0 |

The same conclusion holds at N=100, 256, 512 and on all 5760 scenes. On full
support only 120 scenes degrade, each by one step cost (about 0.02), so their
aggregate deficit is only about 0.00041667. Increasing the evaluation sample
does not solve this scale mismatch.

The necessary check is concrete: a purported recoverable-defect baseline must
first be distinguishable from recovery by the intended endpoint. Here a constant
curve at its defective level satisfies the threshold at every checkpoint, so for
any grid with at least three checkpoints the maintained-recovery time is zero.
Any curve confined between these defective and healthy levels also has time zero.
This is a mathematical counterexample independent of the new operational results;
no f_R selection or ranking is performed with operational keys.

Machine-readable result: `experiments/v03r/c1_recovery_observability.json`, verdict
`ENTRY_DEFICIT_BELOW_ENDPOINT_RESOLUTION` (intentional exit 1). This finding is
why the weaker construction pass is not promoted to F0 validity.

## 4. Consequences for the next design step

There are two distinct design questions, and neither should be hidden in a code fix:

1. Keep the current whole-bank, absolute recovery endpoint and construct a baseline
   whose initial deficit it can detect. Scope and training coverage must be justified
   before new runs; a calibration canary is not automatically a suitable baseline.
2. If the intended claim is recovery of a local loss, preregister an endpoint tied to
   that loss or to a prospectively defined evaluation population. Its reference,
   denominator, zero-loss cases and measurement isolation need explicit definitions.

Do not tighten the threshold after seeing curves, pick only favourable keys, or
call additional training a remedy for an already-zero recovery time. The current
records establish the obstruction but do not select a new scientific endpoint.
Operational keys 900001..900032 and 910001..910032 must remain excluded from all
future scientific seed sets.

F0 also retains its independent unresolved items: the practical meaning of the
persistent-regime (P) RMST effect threshold and completion of the acquisition/manifest/lock
toolchain. This document does not ratify those items or authorise formal data.

## 5. Validation and reproducibility

The candidate's five new tests pass, including actual A91 updates, the 5760-scene
repaired-state comparison and healthy/no-learning negative controls. The full suite
passes with 779 passed and 1 skipped. The existing skipped test concerns a fully
consulted Process domain without an uncontacted representative; it is unrelated
to the candidate. The spec auditor passes with 24 documents and 429 checked
cross-references, and `git diff --check` is clean. No mutation selfcheck ran alongside
acquisition or tests, and the acquisition verified its source hashes again at exit.

The two gate labels must be read together: C1 construction PASS, recovery
observability FAIL. F0 remains NOT VALID. This work is local and uncommitted.
