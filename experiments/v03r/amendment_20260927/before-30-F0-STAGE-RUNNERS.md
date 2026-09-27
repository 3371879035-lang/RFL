# 30 — F0 stage runners and immutable authorization

Status: **F0 NOT VALID. No formal smoke, development or confirmatory run.**
This records implementation, not approval of the C3 amendment, the runtime rule,
or the independent persistent-regime RMST practical threshold.

## 1. Implemented command surface

```text
python scripts/f0_manifest.py
python scripts/f0_manifest_selfcheck.py
python scripts/benchmark_f0_runtime.py --plan
python scripts/run_smoke.py --seeds-file experiments/v03r/smoke_seeds.txt --plan
python experiments/v03r/evaluate_smoke_gate.py
python scripts/run_dev_baseline.py --seeds-file experiments/v03r/dev_seeds.txt --plan
python scripts/run_dev_lock.py --design experiments/v03r/dev_baseline.json --plan
```

The generator publishes a new file exclusively. Its default output is a draft
with no stage authorizations. `--plan` only checks inputs; it cannot bypass F0.
The stage commands refuse a draft before creating outputs or drawing seeds.
The smoke evaluator is read-only and returns native 0/3/2 for PASS/FAIL/invalid
inputs. Run commands also distinguish protocol refusal from a completed gate.

`--finalize --runtime <runtime.json> --review <review.json> --output <new-path>`
requires measured runtime evidence and an explicit, source-bound review with a
ratified positive RMST threshold and independent practical rationale. Review
fields are `decision: VALID`, `sources_digest`, and `rmst_policy` containing
`ratified`, `value`, and `rationale`. The generator cannot supply a scientific
rationale. A finalized manifest must be committed before execution. The draft
must not be overwritten; a subsequent reviewed manifest can use a new path,
passed explicitly to all stages.

## 2. Three separate evidence layers

1. The pre-smoke manifest pins byte-identical committed instrument sources,
   source inventory, seed files, constants, balanced ordering, gate commands and
   expected gate-artifact digests, shard schema, review and measured bounds.
   It contains no future baseline digest or selected horizon/grid.
2. Smoke emits exactly `{stage, seeds, tree, runtime_s, gate_exit_codes,
   artifact_paths, artifact_digests, errors, fallbacks}`. `tree` binds both the
   instrument commit and manifest SHA-256. No outcome curve is saved. A separate
   evaluator checks identity, all six native exit codes, artifact hashes, empty
   errors/fallbacks, and runtime. An exclusive `smoke_attempt.json` reservation
   prevents a concurrent or interrupted run from automatically reusing seeds.
3. Development requires that passing smoke receipt before collection. The
   baseline index records its SHA-256 plus manifest/source provenance. All
   checkpoints and full-U2 incidence are retained. Source identity, receipt and
   runtime are rechecked before publishing the index. A failed acquisition can
   leave incomplete shards, never a published valid-looking index. F1 verifies
   the same receipt again before any design metric or combined lock is written.

The fixed six gates are pytest, spec audit, B2 view mutation check, A91 training
mutation check, calibration, and the seedless F0 manifest mutation check. Run
them **serially**: the two mutation harnesses temporarily edit and restore source.
The last gate tests a synthetic contract and never approves the actual manifest;
its deterministic report avoids a self-referential manifest/artifact digest.

## 3. Runtime measurement remains outstanding

The executable operational benchmark reserves 950001..950005 for the smoke
shape and 950006..950037 for development. These keys must remain excluded from
scientific populations. It measures the serial gate suite, then the actual
5-key discarded stream and 32-key serialized acquisition, each with cap 576 and
master bank 1024: 21,312 training episodes and 21,349 checkpoints in total.
Every checkpoint uses full U2 for domains/incidence. It pins the committed
instrument before running and refuses source drift or reuse of its output dir.

`runtime.json` is published only after completion. Stage bounds use the proposed
`2 * (suite_seconds + 10 * stage_workload_seconds)` rule. The benchmark itself
does not authorize F0. A short cap-2 integration run, synthetic fixture timings,
or historical single-bank timings cannot substitute for this measurement.

This publication implements and checks the benchmark plan; it does **not** report
a completed full-envelope timing run. F0 still needs that measurement, independent
RMST policy ratification, and review of the complete C3 instrument/amendment.

## 4. Verification boundary

New tests cover contract mutations, forbidden smoke outcome fields, invalid
runtime/identity/digests, source byte and inventory drift in an actual temporary
Git repository, no-draw refusal, serial gate order, spent-attempt reservations,
missing/failed smoke receipts, and index suppression after a failed postcheck.
The real short-stream test exercises A91, full-U2 acquisition, serialization and
verified readback using engineering keys 960001/960002 in pytest temporary
directories. Only the test fixture replaces stage authorization and reduces the
cap; there is no production CLI override. Those runs are engineering checks.

Full regression: **907 passed, 1 existing skip (908 collected)**. An initial
test-only cap-0 fixture was corrected to cap 1 so the post-acquisition failure
test reaches its intended guard. Its first-run failure remains recorded in
`f0_stages_initial_regression.xml`. The final full run passed. The document audit
also caught missing numbered section headings here; those headings were fixed
before the final audit. Neither repair changes a scientific parameter.

Publication review also found unstable B2 diagnostic tails: pytest's temporary
directory counter and decimal object IDs changed three stored failures between
runs. The relevant tests now assert the same object/map counts and diagnostic
reason through local variables, keeping process-specific IDs and paths out of
pytest's failure explanation. Native failures and their required reasons remain
the gate; no outcome number is redacted. Consecutive full mutation runs are
compared byte-for-byte before the expected artifact hash is frozen.

Validation evidence is stored as `f0_stages_full_regression.xml`, the four gate
JSON artifacts, `f0_stage_gate_evidence.json`, and `publication_stage_integrity.json`
under `experiments/v03r/`. The generated draft and refusal audit are committed
after the source commit so that the draft can identify committed source bytes.
Earlier C1/C2/C3 archives and failures retain their original manifests and hashes.
