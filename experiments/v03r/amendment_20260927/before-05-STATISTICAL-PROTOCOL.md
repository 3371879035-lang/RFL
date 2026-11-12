# 05 — Statistical protocol

**Status:** FROZEN. Applies to every version in the rebuild.

This document exists because the legacy project's rule — *"if the conclusion
changed, run more seeds"* — is optional stopping, and it produced four recorded
"reversals" that were all movements of quantities never distinguishable from
noise. Everything here is a direct consequence of that failure.

---

## 1. Four quantities that must never be conflated

$$\boxed{N_{\text{seeds}}}\quad \boxed{N_{\text{train}}}\quad \boxed{N_{\text{eval}}}\quad \boxed{\mathcal G_{\text{ckpt}}}$$

| quantity | meaning |
|---|---|
| $N_{\text{seeds}}$ | number of independent complete runs |
| $N_{\text{train}}$ | training episodes **per run** |
| $N_{\text{eval}}$ | evaluation episodes per checkpoint |
| $\mathcal G_{\text{ckpt}}$ | the checkpoint grid at which evaluation happens |

Every reported number carries all four. The legacy mistake of quoting "N=400" as
though it described training length is prohibited; so is generalising one
version's budget to another.

For V0.1R, which has no training loop, the unit is $N_{\text{scenes}}$ — the
number of independently generated episodes. It must **not** be called a training
seed.

---

## 2. Stages

| stage | $N$ | purpose | may inform |
|---|---:|---|---|
| Semantic / identifiability | 0 random seeds | invariants, identifiability matrix | design only |
| Smoke | 5 | crashes, logging, obvious breakage | nothing scientific |
| Development | 32 | benchmark calibration, $T$, variance structure | design only |
| Secondary confirmatory | 200 = 2×100 | pre-declared secondary contrasts | results |
| Primary confirmatory | 400 = 4×100 | the single core claim per version | results |

Development seeds and confirmatory seeds are **disjoint**. Development seeds are
spent once and never reused for a confirmatory claim.

### 2.1 Contrast tiers are frozen before confirmatory seeds

$$\boxed{\text{A contrast's tier is fixed before collection and may not be upgraded afterwards.}}$$

If a dev-only ablation turns out beautifully:

> ~~"then let us add 400 seeds and see"~~ — **prohibited.**

An upgrade is a **new pre-registered study**, with a fresh seed base. This is the
single rule that most directly prevents the legacy failure, where the seed count
was chosen after seeing the result.

---

## 3. Pairing and dependence

* **Paired seeds** across arms; the same seed drives the same environment draws.
* **Common random numbers.** Each seed's noise tape is pre-sampled and shared
  across arms, so counterfactual comparisons are valid.
* **The seed is the statistical unit.** Episodes are nested within seeds and are
  never treated as independent samples. Cell-level observations within a seed are
  likewise not independent — see §7.
* Arms within a seed share the tape; arms across seeds do not.

---

## 4. The decision rule

A conclusion is **not** "the p-value crossed 0.05". It is where the 95% CI sits
relative to the pre-specified minimum meaningful effect $\Delta_{\min}$:

| outcome | condition | meaning |
|---|---|---|
| `SUPPORT_A` | $L > +\Delta_{\min}$ | positive and practically meaningful |
| `EQUIVALENT` | $[L,U] \subset [-\Delta_{\min}, +\Delta_{\min}]$ | practically equivalent |
| `SUPPORT_B` | $U < -\Delta_{\min}$ | negative and practically meaningful |
| `INCONCLUSIVE` | otherwise | spans a boundary — **not a finding** |

$\Delta_{\min}$ is declared per endpoint before collection and may not be changed
after seeing an interval. A CI that excludes zero but lies wholly inside
$[-\Delta_{\min}, +\Delta_{\min}]$ is `EQUIVALENT`, and that is the correct reading
of a statistically detectable but practically negligible effect.

### 4.1 Look schedule

Four blocks of 100. At each look $N = 100, 200, 300, 400$ report **both**:

$$\text{cumulative}_{N} \qquad\text{and}\qquad \text{block}_k \text{ alone}$$

The second distinguishes a genuine reversal from variance shrinkage: a cumulative
move from $+0.04$ to $+0.01$ means something entirely different if the fresh block
came in at $-0.02$ than if it came in near zero.

Only $N=400$ is confirmatory. Earlier looks are diagnostic, so no alpha spending
across looks is required.

### 4.2 What counts as a reversal

$$\boxed{\text{A reversal is a change of the four-way verdict, and it is reportable only with the fresh block's own mean.}}$$

A CI-exclusion flip that leaves the verdict unchanged is a **no-op** and is not a
reversal. The legacy ledger contained 7 such flips and 0 conclusion changes.

A reversal caused by a block whose mean lies inside $[-\Delta_{\min}, +\Delta_{\min}]$
is a statement about the decision boundary, not about the phenomenon, and is
labelled as such.

---

## 5. Mandatory companion statistics

$$\boxed{\text{Look at the per-seed distribution first. Look at the mean second.}}$$

Tabular RL readily produces *70% exact ties plus a few huge outliers*, in which
case the mean is a statement about a handful of runs.

Every contrast reports:

| statistic | why |
|---|---|
| tie fraction | effective $n$ is far below $N$ |
| median, 5%-trimmed mean | if these disagree in sign with the mean, the mean is tail-driven |
| exact sign test on non-tied seeds | assumption-light; uses direction only |
| Wilcoxon signed-rank | rank-based, robust to a few enormous seeds |
| paired bootstrap CI | the interval used in §4 |
| probability of improvement | proportion of seeds favouring the arm |
| Holm correction | across contrasts within a version |
| effect size | Cohen $d_z$ |
| top-5 share of the net sum, and the mean without them | the diagnostic: if the mean collapses, the effect was tail |

A contrast may be reported as a finding only if the mean, median and trimmed mean
agree in sign, **and** the sign test agrees, **and** the top-5 share is below 50%.
Otherwise it is labelled `TAIL-DRIVEN` or `DIRECTION UNRESOLVED` and is not a
finding regardless of its interval.

---

## 6. Freezing $T = N_{\text{train}}$

$T$ is chosen on **development seeds only**, from the **baseline curve only**:

$$\boxed{\text{The treatment curve may not be inspected before } T \text{ is written into the preregistration.}}$$

### 6.1 Baseline convergence

For each development seed, using the `NoCorrection` / baseline arm only, define
convergence at the first checkpoint after which, for $K$ consecutive checkpoints,

$$\bigl|\mathrm{slope}_{K}\bigr| < \epsilon_s \qquad\text{and}\qquad \mathrm{FlipRate}_{K} < \epsilon_f$$

giving $T^{(i)}_{\mathrm{conv}}$ per seed.

The executable interpretation is clarified by `12` §79.7 (A91): one window of
$K$ checkpoints tested once; endpoint slope on the real episode axis; the declared
constant/undefined FlipRate cases; the last checkpoint of the first qualifying
window; and the original-sample nearest-rank censoring rule. This paragraph does
not require $K$ consecutive qualifying windows. Freeze

$$\boxed{T = Q_{0.9}\bigl(T_{\mathrm{conv}}\bigr) \times (1 + h)}$$

with headroom $h$ declared in advance (default 0.20).

This asks *"how long does an ordinary learner take to stabilise on this
benchmark?"* — not *"when does the treatment look best?"* Using the treatment
effect to choose $T$ would select the design at the effect's maximum and invalidate
the confirmatory test.

**Hard rule:** until $T$ is frozen and committed, no treatment-arm curve may be
plotted, printed, or summarised. $T$, the checkpoint grid, and $N_{\text{eval}}$
are frozen **together** and may not be changed afterwards.

### 6.2 Checkpoint grid

$$\mathcal G_{\text{ckpt}} = \{0, 1, 2, 5, 10, 20, 50, 100, 150, 200, 300, 500, \ldots, T\}$$

dense early, because recovery is fast when it happens. Every time-integrated
endpoint is computed by integrating over the **real episode index**, not by
averaging checkpoint values — a non-uniform grid makes those two different.

---

## 7. Within-design contrasts

Pilot Gamma's statistics were computed on duplicated, non-independent
observations: a loop appended every pair twice while each selector ignored one of
its arguments, and cell-level pairs from one seed were treated as independent.
Means were unaffected; CIs were 2.2–2.5× too narrow, and one verdict changed once
corrected.

The rule that prevents this:

$$\boxed{\text{Aggregate to the seed first, then test across seeds.}}$$

For a factorial design with $c$ cells per seed, the seed-level statistic is the
within-seed aggregate over cells, and the test has $n = N_{\text{seeds}}$, not
$n = N_{\text{seeds}} \times c$. Any sub-seed level analysis is secondary and must
report the seed-level result alongside.

A required check: the number of independent observations entering any test must
equal $N_{\text{seeds}}$, asserted mechanically.

---

## 8. Recovery endpoints — survival, not averages

When the endpoint is time-to-recover, averaging over seeds that recovered is
selection bias.

### 8.1 Recovery definition

$$\tau = \inf\bigl\{t : V_{t'} \ge 0.95\,V_{\text{pre}} \ \forall t' \in [t, t+K-1]\bigr\},\qquad K = 3$$

$K$ consecutive checkpoints, not a single crossing. Seeds that never recover are
**right-censored at $T_{\max}$**.

### 8.2 Primary endpoint

$$\boxed{\mathrm{RMST}(T_{\max}) = \int_0^{T_{\max}} P(\tau > t)\,dt}$$

Smaller means faster recovery. RMST handles censoring without discarding seeds.

### 8.3 Continuous companion

$$\mathrm{DeficitAUC} = \frac{1}{T_{\max}}\int_0^{T_{\max}} \bigl[V_{\text{pre}} - V(t)\bigr]_+\,dt$$

so that two arms whose seeds mostly never recover can still be compared on *how
far* they are from recovery.

Both are integrated over the real episode axis using $\mathcal G_{\text{ckpt}}$.

---

## 9. Prohibited after a freeze

* adding seeds past the frozen $N$ and re-testing;
* dropping a block that disagrees;
* changing $\Delta_{\min}$, $T$, $\mathcal G_{\text{ckpt}}$, or $N_{\text{eval}}$
  after seeing an interval;
* upgrading a contrast's tier;
* reporting an intermediate look as the conclusion;
* writing up a $p$-value crossing as a reversal without the block decomposition;
* pooling runs made under different code, different $T$, or different $N_{\text{eval}}$.

## 10. The bug rule

$$\boxed{\text{A bug found after collection voids the entire seed set.}}$$

The fix lands, and collection restarts from $N=0$ on the new code. Partially
collected seeds from old code are not a head start; they are a second
distribution. This was applied in the legacy project and it will be applied here.

Any change to `src/rfl_rebuild/` between the first and last seed of a run voids
the run. Source fingerprints are the mechanism
(`10-REPRODUCIBILITY-AND-OPS.md` §2).
