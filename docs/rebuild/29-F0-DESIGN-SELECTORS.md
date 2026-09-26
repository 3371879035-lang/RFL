# F0 design selectors and combined lock implementation

## 1. Status and scope (2026-09-27)

The five frozen selectors now have executable implementations: f_T in convergence,
and f_N/f_G/f_C/f_R in design_selection. The combined threshold registry and
development-only lock consumer are implemented. This closes those implementation
items from `28-F0-ACQUISITION-RESULTS.md`, not F0 itself. No formal development
dataset, selected scientific design, threshold ratification or treatment result is
created by this change. F0 remains NOT VALID.

The current consumer does not generate an F0 approval. The smoke/baseline stage
commands, manifest generation/selfcheck and full-envelope runtime gate still need
completion. The independent practical rationale for the persistent-regime P RMST
threshold remains unresolved. The consumer refuses to supply a default ratification.

## 2. Selector implementation

All formulae, inclusive thresholds, tie orders, real-episode integration and
population-spread arithmetic follow `20` §§4–6 and `12` §79.7. The master bank
remains 1024 for every design calculation, even when f_N chooses a smaller bank
for future confirmatory measurement.

* f_N visits every seed/episode, including episodes beyond selected T. It takes
  the worst standardized prefix discrepancy, handles exact zero-spread cases,
  and selects the smallest admissible size from 100, 256, 512, 1024.
* f_G instantiates the three frozen dense-early templates, including the doubling
  tail. It compares each seed's restricted recovery time and trapezoidal DeficitAUC
  against the full episode axis, then takes the maximum. A recovery lost by a
  coarse grid remains a nonzero discrepancy, including one-sided censoring.
* f_C validates all eighteen calibration cells and uses each run's own successful,
  unconsulted scene values for each refinement. The statistic is actual value-based
  SE, never the cancellation-prone triple expansion. Empty sets are inadmissible;
  zero/zero is equal stability (ratio one). Coverage is reported, never thresholded.
* f_R configures H=T or H1=grid[-3], H2=T and computes the two existing estimators.
  Relative range and Spearman redundancy use per-seed observations. Constant
  series make correlation undefined and the candidate inadmissible. Tied values
  receive average ranks, with Pearson correlation of the rank series; the main
  protocol now spells out that standard executable convention.

The composed calculation verifies every expected seed/episode coordinate and
exhausts the whole master stream. It retains small per-seed mean curves for f_T,
f_G and f_R, with no f_N-to-f_G/f_R dependency. A NO_ADMISSIBLE result remains a
result: no fallback candidate, relaxed threshold, cap substitution or partial lock.

## 3. Exact grouping and threshold population

Within a run, sites with identical consulted-scene indices have identical eligible
refinement values. Their numerical calculations can be shared, but their population
multiplicity is retained. Uncontacted sites contribute domain_size-contacted_count,
separately for each architecture. This matters because the P BehavioralCollateral
threshold is the nearest-rank 95th percentile over ALL credited sites, seeds and
episodes, not over distinct incidence groups. A weighted frequency table computes
that exact rank without expanding a potentially very large population in memory.

Coverage descriptors are frequency tables of (eligible_count, refined_count) per
architecture/refinement. The original shard's full domains/incidence and frozen
membership predicates recover each individual site's descriptor. No coverage floor
or aggregate-size gate is introduced. Dense enumeration on independent synthetic
fixtures checks metrics, coverage counts, spread multiplicities and quantiles.

The threshold registry has six separate regime/statistic identities. T RMST and
T DeficitAUC are explicit aliases by value with distinct identities; DeficitAUC
retains 0.01. P Retention uses 0.25 times the selected form's per-seed population
standard deviation. All-zero collateral spread or zero retention spread blocks the
corresponding threshold. A nonzero family whose 95th percentile is zero is not
silently replaced with a positive floor. P RMST comes only from a prior, ratified
F0 policy with its independent rationale; the tests' synthetic policies ratify no
real experiment.

## 4. Development lock consumer and publication

```text
python scripts/run_dev_lock.py --design experiments/v03r/dev_baseline.json --plan
python scripts/run_dev_lock.py --design experiments/v03r/dev_baseline.json
```

The default manifest is experiments/v03r/f0_manifest.json. The consumer expects
schema f0-c3-design-v1, status VALID, currently_authorises containing design_lock,
the exact implemented constants, a complete instrument source inventory, calibration
digest and ratified RMST policy. This is the consumer contract; a manifest satisfying
it has NOT been generated or approved in this work. Manifest bytes must already be
committed and match HEAD, and all declared source hashes must match the checkout.
The instrument inventory covers all rebuild source files, the lock CLI, and the
statistical, A91, F0 and selector documents. F0 construction must freeze these fields
before any development acquisition; this consumer cannot turn a post-data policy
edit into the manifest used by an earlier acquisition.

Only DEVELOPMENT_BASELINE with the ordered keys 1000..1031, complete 0..576 axis
and balanced bank 1024 is accepted. Its constant block must equal F0's, and its
execution provenance must bind that exact manifest and source inventory. All
canonical shard bytes and structure are checked before any selector metric.
--plan computes no selector, solves no reference, runs no episode and writes nothing.

The executing path computes the healthy master-bank reference level through the
existing instrument, derives every selector and threshold, then rechecks provenance
before publication. A successful payload contains design, six-row threshold registry,
selection diagnostics and hashes tying it to F0 and the baseline. A temporary file is
fully flushed and atomically hard-linked to its final name; an existing lock is never
overwritten. Temporary files are removed on success or failure. An unsupported
filesystem hard-link fails instead of falling back to overwriting publication.

The file is one indivisible design/threshold artifact. Its subsequent single Git
commit remains required by the F1 protocol before any treatment stage. Creating a
file cannot authorize that stage by itself. No such scientific file is created here.
Exit 2 means invalid/unauthorized inputs; exit 3 means a legitimate NO_ADMISSIBLE
selector/threshold result; only a complete lock or a valid --plan exits zero.

## 5. Validation and publication evidence

New tests use synthetic numerical/site populations and isolated temporary outputs.
They do not read C1/C2/C3 operational curves to choose a scientific design. Tests
cover worst-case aggregation, exact zero cases, tied ranks, undefined correlations,
late-envelope observations, master-bank dependencies, grouping versus dense
enumeration, schema/provenance refusal and atomic no-overwrite publication.

Full repository regression: **863 passed, 1 existing skip**, 864 collected,
123.764 seconds; `experiments/v03r/design_selectors_full_regression.xml`. This includes
26 new selector/lock tests. The earlier 23-test targeted run is retained as
`experiments/v03r/design_selectors_targeted.xml`; the additional authorization and
failure-publication tests were included in the full run. The existing skip remains
the fully consulted Process domain having no uncontacted representative.

The actual lock CLI was invoked with --plan against the engineering acquisition.
It exited with native code 2 before metrics because F0 is absent, wrote no lock,
and drew no seed. Evidence: `experiments/v03r/design_lock_refusal.json`.

Publication targets origin/f0-rev3, preserving the existing branch history. The
remote and local starting commit were both d31312d. The publication includes the
earlier uncommitted C1/C2/C3 construction and acquisition evidence, not just the
new selector source. `scripts/verify_rfl_publication.py --staged` verifies the
actual Git-index bytes against each experiment's own pre-run manifest and report,
including 262 archived source/spec/test entries across four snapshots, 96 candidate
run records, and all six integration shard records / 81032 incidence pairs.
The four evidence folders contain 98 distinct operational keys; this is not a
replacement for the complete historical exclusion set (which also includes the
old 900001..900032 construction keys).

Staged publication verification is recorded in
`experiments/v03r/publication_integrity.json`, with the final document audit in
`experiments/v03r/design_selectors_spec_audit_final.json`. Earlier source archives
and raw candidate failures remain unchanged; current source bytes are not
substituted into their pre-acquisition manifests. GitHub publication does not make
F0 valid or the construction results a scientific effect estimate.
