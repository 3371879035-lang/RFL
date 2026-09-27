# 2026-09-27 amendment review

This record concerns the failure-only trigger, the current C3 acquisition
protocol, and the bounded interpretation of the RMST margin. It is an internal
engineering/method review, not an external review or a scientific PASS.

## Decisions

1. Follow the researcher's current instruction: diagnose observed task failures
   only. Native SUCCESS bypasses reflection while ordinary reward/TD learning
   remains enabled. Unknown outcomes are rejected. Historical transcript evidence
   is in `../review_20260927/FAILURE_ONLY_HISTORY.md`.
2. Keep the proposed 1.5-episode value as a declared quantitative benchmark
   margin, and withdraw the unsupported practical-importance and equivalence
   claims. The revised study asks whether the reference-minus-treatment RMST
   interval exceeds this margin on the locked grid. This does not establish
   cost-effectiveness. T's independent constraint is L >= -1.5, inclusive.
3. Declare the actual stage initializer, `c3-temporal-layer-1-v1`, and cap 576 in
   the main protocol. Archive the previous protocol bytes rather than erasing
   their history. All other joint gates and the final-400 schedule remain.
4. Preserve the completed benchmark at `7da3830` with its original source
   inventory. New source bytes require a new full benchmark at operational keys
   970001-970037; old timing is not transferred. No scientific seeds were used
   to choose this amendment.

## Implementation and review

`PairedRunner.run` requires a factual terminal outcome and returns
`NO_REFLECTION` on SUCCESS before inspecting reflection inputs. Its private core
serves controlled instrument tests. The complete future V0.4R orchestrator must
still apply the trigger before constructing diagnostic evidence. This amendment
does not claim that future integration already exists.

The runner previously discarded the B1 result and read a nonexistent
`_last_ledger` from learner state, recording None. It now retains the actual B1
ledger for each arm. An identity/fingerprint regression verifies that accounting
survives the paired run.

The RMST policy has exact fields and explicit false practical-meaning,
equivalence and zero-harm flags. A nonempty rationale and `ratified=true` cannot
authorize an arbitrary numeric or practical-effect policy. P's interval label
and T's harm-bound result are evaluated separately.

Internal read-only review found no remaining blocking inconsistency in the
failure boundary, T interval sign/inclusivity, A92 precedence, retained joint
gates or source-binding requirements. The review specifically checked that
[-1,3] can satisfy T's numeric bound while its P margin label is INCONCLUSIVE.
It also confirmed that historical all-DGP V0.1R and offline V0.2R findings have
not been relabeled as failure-conditional validation. Prospective validation on
the failure population remains required for learned V0.4R transfer.

## Verification before the new benchmark

- Full regression: 964 collected, 963 passed, one existing skip, no failures or
  errors (`full_regression.xml`).
- RMST policy: 47 passed (`rmst_policy_tests.xml`), including the 11 T-bound
  cases added after full-suite collection.
- Runtime inspector: 18 passed (`monitor_tests.xml`).
- B2 mutation gate: 45/45 expected failures; source restored byte-identically
  (`b2_gate_review.json`).
- A91 mutation gate: 6/6 expected failures; source restored byte-identically
  (`a91_gate_review.json`).
- Calibration: 18/18 cells agree; worst absolute gap 4.441e-16.
- F0 contract self-check: 31/31 corruptions rejected; zero scientific seed draws.
- Specification audit: 32 documents, 457 cross-references; no blocking defects
  (`spec_audit.json`). Existing editorial summary omissions are nonblocking.

The new benchmark runs the complete frozen six-gate suite again, serially, and
binds its exit codes and artifact hashes to its own runtime evidence. These
preflight checks are not substituted for that measured suite.

## Preservation and next evidence

`prior_runtime_preservation.json` records the original runtime/index hashes and
all 32 raw gzip shards' container/canonical hashes. The raw shards remain local
under `../f0_runtime/baseline/` (about 784.5 MiB); publishing the metadata is not
publishing those raw files. Four `prior-*.json` files preserve the exact gate
artifacts referenced by the old runtime before any refresh.

`source_bound_review.json` ratifies only this limited protocol for its exact
source inventory. It is not an F0 manifest and authorizes no stage. The one-shot
completion helper will verify the entire new benchmark and, only on success,
try to create a NEW `f0_manifest_rev5.json`. That candidate remains uncommitted;
stage guards reject it until its bytes are committed. The helper neither mutates
Git nor launches scientific stages. The old NOT_VALID draft is preserved.
