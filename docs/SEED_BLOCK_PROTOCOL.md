# Seed-block protocol — frozen pre-registration

**Frozen:** 2026-09-01, *before* any 400-seed result was inspected.
**Supersedes the ad-hoc rule** "if the conclusion changed, run more seeds".

---

## 1. Why this document exists

The earlier practice in this project was: run a pilot, look at the result, and if
it disagreed with the previous seed count, run more seeds. That is **optional
stopping**. It was applied to v0.4 Alpha (12 → 100 → 200), v0.3 Alpha
(12 → 100 → 200) and v0.3 Stage 5 (8 → 100 → 200 → 300), and every one of them
moved. Repeatedly peeking and letting `p < 0.05` decide whether to continue
inflates the type-I error rate and makes the reported interval meaningless.

The reversals were real and worth chasing, but the mechanism used to chase them
was itself a source of error. This document replaces it.

## 2. Frozen design

$$\boxed{N_{\max} = 400}$$

partitioned into four **fresh, non-overlapping** seed blocks of 100:

| block | seed indices | seed values (per pilot: `seed_base + index`) |
|---|---|---|
| $B_1$ | 0–99 | `base+0` … `base+99` |
| $B_2$ | 100–199 | `base+100` … `base+199` |
| $B_3$ | 200–299 | `base+200` … `base+299` |
| $B_4$ | 300–399 | `base+300` … `base+399` |

Every pilot uses a single seed base for all four blocks, so the blocks are
disjoint and each block is a genuine replication, not a re-labelling of the
same episodes. Seed bases are unchanged from the existing configs:

| pilot | seed base |
|---|---|
| v0.3 Alpha | `4000000` |
| v0.3 Beta | `4100000` |
| v0.3 Gamma | `4200000` |
| v0.3 Timing | `4300000` |
| v0.3 Stage 4 | `4400000` |
| v0.3 Stage 5 | `4500000` |
| v0.4 (Alpha / Beta / Gamma) | `4600000` |

Four scheduled looks, at $N = 100, 200, 300, 400$.

## 3. What is reported at every look

At each $N$ **both** numbers are reported, and neither substitutes for the other:

$$\text{cumulative}_N = \text{pool}(B_1,\dots,B_k) \qquad\text{and}\qquad \text{block}_k \text{ alone}$$

The second is the one that answers the question the old procedure was groping
for. A cumulative shift from $\Delta = +0.04$ at $N=100$ to $\Delta = +0.01$ at
$N=200$ has two entirely different explanations:

* $B_2$ genuinely came in at $\approx -0.02$ — a **reversal**, and the real
  finding is that the effect does not replicate; or
* $B_2$ came in near zero and the pooled mean simply regressed as variance
  shrank — **no reversal at all**, just a smaller error bar.

Reporting only cumulative numbers cannot distinguish these. Reporting only the
new block cannot either, because a single 100-seed block is noisy on its own.
Report both.

## 4. "The conclusion changed" — redefined

**A change in $p$-value is not a change in conclusion.** The most dangerous
pattern in the earlier record is $p = 0.04 \rightarrow p = 0.07$ being written up
as a reversal, when the two results can be very nearly identical and differ only
in how much data they average over.

The conclusion is instead defined by where the 95% CI sits relative to a
**pre-specified minimum meaningful effect**:

$$\Delta_{\min} = 0.01 \; \text{AUC}$$

This value is not new: it is exactly the `noninferiority_margin: 0.01` already
present in the v0.4 configs, adopted here as the equivalence threshold so that
one number governs both the non-inferiority gate and the conclusion language.

### Four-way decision rule

For a contrast with cumulative CI $[L, U]$:

| outcome | condition | wording |
|---|---|---|
| **`SUPPORT_A`** | $L > +\Delta_{\min}$ | the effect is positive and practically meaningful |
| **`EQUIVALENT`** | $[L,U] \subset [-\Delta_{\min}, +\Delta_{\min}]$ | practically equivalent; no meaningful effect either way |
| **`SUPPORT_B`** | $U < -\Delta_{\min}$ | the effect is negative and practically meaningful |
| **`INCONCLUSIVE`** | otherwise | the CI spans a decision boundary; **not** a finding |

`SUPPORT_A` / `SUPPORT_B` name the *directions of the pre-registered hypothesis*,
which differ per pilot (see §6); they are not "good" and "bad".

This rule is markedly more stable than significance testing. `INCONCLUSIVE`
absorbs exactly the cases that the old procedure kept mislabelling as reversals:
a CI of $[-0.004, +0.022]$ is inconclusive under both readings and stays
inconclusive. What it stops doing is flipping to a confident claim because
$p$ crossed $0.05$ on a re-run.

### What is *not* allowed to count as a finding

* a CI that excludes zero but lies wholly inside $[-\Delta_{\min}, +\Delta_{\min}]$
  — this is `EQUIVALENT`, and it is the correct reading of a statistically
  detectable but practically negligible effect;
* a significant sign test with a median of exactly zero (see §7);
* any intermediate look reported as if it were confirmatory (§5).

## 5. Confirmatory status of each look

* The **only confirmatory** result is the cumulative $N = 400$ analysis.
* The $N = 100, 200, 300$ looks are **descriptive and diagnostic**: they exist to
  show the trajectory and to feed §3's block decomposition. They must not be
  quoted as the study's conclusion, and no stopping rule is applied at them.
* Consequently there is no alpha-spending adjustment across the four looks: the
  final analysis is a single pre-specified test at a single pre-specified $N$.
  Multiplicity *across contrasts within a pilot* is still handled by Holm.

## 6. Contrasts and directions per pilot

| pilot | contrast | `SUPPORT_A` means | `SUPPORT_B` means |
|---|---|---|---|
| v0.3 Alpha | `traditional − positive_only` | positive-only credit beats traditional | it is worse |
| v0.3 Stage 4 | `arm − traditional` | the RFL arm beats traditional | it is worse |
| v0.3 Stage 5 | `oracle − traditional` | Oracle routing helps | it is harmful |
| v0.4 Alpha | `DecisionOracle − ModuleOracle` | finer granularity helps | it is worse |
| v0.4 Beta | `Contrastive − NegativeOnly` | $H_B$ holds | $H_B$ is refuted |
| v0.4 Gamma | `reward B − A` | the failure penalty matters | it does not |

## 7. Mandatory companion statistics

Every contrast is reported alongside the robustness statistics produced by
`scripts/robustness_audit.py`, because in this codebase a mean alone is not
interpretable:

| statistic | why it is mandatory |
|---|---|
| tie fraction | seeds where the two arms are bit-identical — the effective $n$ is far below $N$ |
| median and 5%-trimmed mean | if these disagree in sign with the mean, the mean is tail-driven |
| exact sign test on non-tied seeds | assumption-light counterpart to the bootstrap CI; uses direction only |
| top-5 share of the net sum | above ~50%, the mean is a statement about five seeds |
| mean after dropping those five | the diagnostic: if it collapses toward zero, the published effect was tail |

A contrast may be reported as a finding only if the mean, the median and the
trimmed mean agree in sign, **and** the sign test agrees, **and** the top-5 share
is below 50%. Otherwise it is labelled `TAIL-DRIVEN` or `DIRECTION UNRESOLVED`
and is not a finding regardless of its CI.

## 8. Prohibited after this freeze

* Adding seeds past 400 and re-testing.
* Dropping a block that disagrees.
* Changing $\Delta_{\min}$ after seeing the 400-seed CI.
* Reporting an intermediate look as the conclusion.
* Writing up a $p$-value crossing as a "reversal" without the §3 block
  decomposition.

## 9. Never change the algorithm while increasing seeds

$$\boxed{\text{During seed collection the code is frozen.}}$$

If a pilot at 100 seeds looks bad, the parameter is not tuned. If 200 disagrees,
the threshold is not moved. If 300 flips again, the environment is not adjusted.
Any of those turns $N = 100, 200, 300, 400$ into four samples from four
*different* distributions, which cannot be pooled, compared, or drawn on one
curve — and the "instability" that motivated the change is then partly caused by
the change itself. It is optional stopping wearing a different hat.

### 9.1 The bug rule

$$\boxed{\text{A bug voids the entire seed set.}}$$

A defect is **not** patched in place and the run resumed. The fix lands, and
collection restarts from $N = 0$ on the new code. Partially collected seeds from
the old code are not a head start; they are a second distribution.

This was applied literally during the v0.4 re-run. A reproducibility defect was
found in `src/rflv04` mid-collection (`docs/V0_4_REPRODUCIBILITY_DEFECT.md`:
training depended on `PYTHONHASHSEED`, giving a 3.3x spread in `WMD` for
identical inputs). Every in-flight v0.4 run was killed, the fix was committed,
and all v0.4 pilots restarted from $N = 0$ on the fixed code. The pre-fix numbers
at 6 / 12 / 100 / 200 / 300 seeds are void as evidence and are retained only as
a record of what the defect did.

### 9.2 Enforcement

Rule 9 is checked mechanically, not by discipline:

```bash
python scripts/src_fingerprint.py --record docs/PROVENANCE.json   # before a run
python scripts/src_fingerprint.py --check  docs/PROVENANCE.json   # after / before resuming
```

`src_fingerprint.py` hashes the repo-relative path and normalized contents of
every `.py` under `src/`, and fails (exit 1) if any package differs from the
record or if `src/` has uncommitted changes. Paths are hashed relative to the
repo root so the digest is portable, and line endings are normalized so that
`core.autocrlf` rewriting LF to CRLF does not raise a false alarm — a provenance
check that cries wolf gets ignored, which is worse than not having one.

## 10. Provenance of the 400-seed runs

Verified after the fact rather than asserted:

| check | result |
|---|---|
| `git status --short src/` during collection | empty — the tree matched `HEAD` throughout |
| commits touching `src/` since the pilots | exactly one, the reproducibility fix `9c03f43` |
| files changed by that commit | `src/rflv04/credit_units.py` only |
| `src/rflnext` (v0.3 pilots) touched? | **no** — verified two ways |
| `git_commit` recorded in `v04_alpha_400` / `v03_alpha_400` summary | `095238b` (post-fix) |

Because the fix commit touched only `src/rflv04`, the v0.3 pilots ran on one
unchanged codebase across every seed count. This is confirmed empirically as well
as by inspection: the 300-seed Stage 5 run and the first 300 seeds of the
400-seed run were separate processes, and all 1,800 `(setting, seed)` pairs match
bit-for-bit.

The v0.4 400-seed runs are therefore a clean $N = 0$ restart on fixed code, as
§9.1 requires. `v03_stage5_400` records the earlier commit `86a2e0b`, which is
correct for it: that run predates the fix and does not include it, and does not
need to, because it does not import `rflv04`.

Fingerprints at the time of writing, recorded in `docs/PROVENANCE.json`:

```
src/rflv04     b928bc5e3ba34d833e628b4da07ee0b59f6c453f1d5df06f14f0e421a69ed12b
src/rflnext    009557a1fc8941cd0a7cd68e364a80ccb3f542f6e0ee2016d30d4b05c585cfb8
```

## 11. Execution log

| pilot | 400-seed run | status |
|---|---|---|
| v0.3 Stage 5 | `outputs/v03_stage5_400` | run |
| v0.3 Alpha | `outputs/v03_alpha_400` | run |
| v0.3 Stage 4 | `outputs/v03_stage4_400` | run |
| v0.4 Alpha | `outputs/v04_alpha_400` | run |
| v0.4 Beta | `outputs/v04_beta_400` | run |
| v0.4 Gamma | `outputs/v04_gamma_400` | run |

The 8 / 12 / 20 / 30 / 40 / 50 / 100 / 200 / 300-seed runs are **retained on
disk** and are not overwritten. Under this protocol they are exploratory
history: they document how the effect estimates moved before the design was
frozen, and they are the reason the freeze was necessary. They are not evidence.
