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

## 9. Execution log

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
