# C3 master acquisition integration results

## 1. Verified result

The predeclared integration rehearsal in `27-F0-ACQUISITION-INTEGRATION.md` passed.
C3 now has an explicit initializer on the actual master acquisition path. The
streaming and in-memory APIs use the same A91 learning loop and full-U2 eligibility
construction. The saved schema is CF-5's index plus deterministic compressed shards.

| Quantity | Observed result |
|---|---|
| Role | OPERATIONAL_REHEARSAL, no scientific seeds |
| Keys | 940001, 940002, permanently excluded from scientific sampling |
| Envelope | cap 2, master bank 1024; complete U2 for domains and incidence |
| Saved records | 6, e=0,1,2 per key |
| Stored site-scene incidence pairs | 81032 |
| Training episodes | 4 acquisition + 4 independent A91 verification replay |
| Frozen archive | 71 source/spec/test files, all digests verified |
| Saved means vs independent A91 replay | all 6 bit-equal |
| Acquisition plus serialization | 7.943 seconds |
| Entire rehearsal plus verification | 10.259 seconds |
| F0 status | NOT VALID |

The small cap is an integration fixture. It supplies neither a convergence sample
nor a full-cap benchmark, and is not evidence of treatment benefit. C3's earlier
32-by-576 construction remains a separate experiment with its original archive.

## 2. Evidence and reproducibility

Directory: `experiments/v03r/c3_acquisition_integration/`.

* `manifest.json`: frozen envelope, keys, exact working-tree hashes and HEAD context.
* `frozen_sources.zip`: pre-run bytes, including the A91 and F0 statistical documents.
* `baseline.json`: index/provenance; SHA-256
  `dc6ec9082ec87f03b7ff017d13b1d8847e9c79a1c0531f5600fd7eda6944c0e9`.
* `baseline/seed-940001.jsonl.gz` and `baseline/seed-940002.jsonl.gz`: all raw records.
* `report.json`: integrity, independent replay and design-readiness results.

The normative shard hashes cover uncompressed canonical JSONL. The container
uses mtime zero, but changing gzip compression/header alone does not invalidate
the data digest. The index is published only after the declared stream completes;
existing directories/files are not overwritten. An interrupted acquisition leaves
unpublished shards for inspection, not an automatically resumed run.

Current source bytes may evolve after this rehearsal. Replay uses the archived
sources and frozen manifest, not whichever working-tree version happens to exist.
The HEAD commit alone does not describe the uncommitted acquisition implementation.

## 3. Convergence clarification and implementation

An initial read of the short main protocol suggested an incomplete convergence
definition. The complete amendment search found the authoritative definition in
`12` §79.7. No new slope/window convention was needed. The implementation now
follows A91: endpoint slope on real episode indices, one K-point window tested once,
constant FlipRate zero, nonconstant zero-denominator windows failing, and the last
checkpoint of the first qualifying window as T_conv.

The main protocol now links to A91. The F0 document's ambiguous "missing T_conv"
sentence now explicitly follows A91's censoring rule: the original n fixes the
nearest rank; enough uncensored observations identify that rank without substituting
the cap or dropping censored runs from n. For n=32, 29 uncensored runs suffice;
28 do not. Missing acquisition records remain invalid, not censored observations.
The exact 6/5 ceiling gives the horizon; a horizon beyond the cap is NO_ADMISSIBLE_T.

These functions were tested on synthetic numerical fixtures only. No operational
C3 curve was passed to a design selector. A local flat segment may qualify before
later learning resumes under the frozen rule; the implementation does not silently
replace it with a stronger all-future stability condition.

## 4. Integrity and readiness are separate

The read-only preflight verified the saved artifact and returned native exit 3,
with no design metric or lock file produced. It rejected promotion of operational
keys and a two-episode fixture into development data, and separately named the
remaining repository requirements: validate the C3 F0 amendment/stage manifest,
complete f_N/f_G/f_C/f_R and the combined lock, and resolve the independent
persistent-regime P RMST practical-effect rationale. The remaining smoke/manifest
stage commands and full-envelope runtime measurement are not closed by this rehearsal.

The codec validates full fixed D_Q/P domains and structural Controller-domain
information. It does not claim that a hash alone proves a Controller trajectory;
the actual full-U2 acquisition path and direct instrument comparisons establish
that separate property. No treatment arm or formal smoke/development seed was run.

## 5. Validation

The new artifact and convergence regression modules passed all 47 tests in
`experiments/v03r/c3_acquisition_convergence_targeted.xml`. They cover the archived
840-edit initializer, full-U2 domains even for a one-scene bank, round-trip values
and CF-1 errors, deterministic compression, every-shard-before-first-value checking,
bad digests and axes, truncated/extra records, noncanonical and nonfinite JSON,
duplicate/out-of-bounds incidence, path confinement, incomplete publication,
cross-seed mutable-state reuse, no-write/no-episode plan mode and operational-role
refusal. Convergence tests cover the real episode denominator, strict thresholds,
constant versus undefined windows, reversals, original-sample censoring and cap failure.

Full repository regression: **837 passed, 1 existing skip**, 838 collected,
173.116 seconds; `experiments/v03r/c3_acquisition_full_regression.xml`. No errors
or failures. The skip remains the fully consulted Process domain having no
uncontacted representative. The earlier acquisition/temporal integration subset
passed 58 with the same skip (`c3_acquisition_targeted.xml`).

After the full suite, every one of the 71 frozen working-tree and archived source
digests still matched, and the baseline index digest matched the rehearsal report.
The final document audit is `experiments/v03r/c3_acquisition_spec_audit_final.json`.
Changes and evidence remain local, uncommitted and unpushed. Earlier candidate
records and archives were preserved.
