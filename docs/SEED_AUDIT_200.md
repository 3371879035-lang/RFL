# Seed-count audit — everything re-run at 200 paired seeds

The v0.3 pilots originally ran at 12 / 20 / 8 / 40 / 30 / 8 seeds and the v0.4
pilots at 12. When v0.4 was re-run at 100 seeds **three of its conclusions
changed**, which made every earlier number suspect. Everything was therefore
re-run at **200 paired seeds**.

This document records what moved and what did not. Nothing below overwrites an
earlier artifact; the 8/12/20/30/40/100-seed runs are all still on disk.

---

## Summary: what changed with more seeds

| pilot | conclusion at original seeds | at 100 | **at 200** | stable? |
|---|---|---|---|---|
| v0.4 Alpha (granularity) | "hurts utility" (12) | sign flipped to +0.0055 | **resolved null** | **changed twice** |
| v0.4 Beta (target) | — | refuted | **refuted, tighter** | **stable** |
| v0.4 Gamma (robustness) | — | reward significant | **stable** | **stable** |
| v0.3 Alpha (reward) | null (12) | null (100) | **CI excludes 0** | **changed** |
| v0.3 Beta (oracle collateral) | exactly 0 | — | **exactly 0** | **stable** |
| v0.3 Gamma (composition) | Δ −0.0078 (8) | — | **Δ −0.0075** | **stable** |
| v0.3 Timing (revision) | −1.0000 exactly | — | **−1.0000 exactly** | **stable** |
| v0.3 Stage 4 (end-to-end) | marginal p = 0.02–0.03 (30) | — | **p ≤ 0.003** | **strengthened** |
| v0.3 Stage 5 (difficulty) | 1/6 separate (8) | 3/6, one **positive** | **3/6, positive one gone** | **changed twice** |

---

## v0.4 — Credit-unit and repair semantics

### Alpha (200 seeds)

| arm | SuccessAUC | WMD | collateral | sites |
|---|---:|---:|---:|---:|
| `NoCorruption` | 0.9933 | 0.00000 | 0.0000 | 0 |
| `NoCorrection` | 0.9418 | 0.00000 | 0.0000 | 0 |
| `ModuleOracle` | 0.8771 | 0.04252 | **0.4340** | 4,589 |
| `DecisionOracle` | 0.8768 | **0.06718** | **0.0000** | 1,713 |

ΔAUC `DecisionOracle − ModuleOracle`: CI **[−0.0217, +0.0217]**, width **0.0434**
— now *below* the plan's 0.05 threshold, so the utility contrast is **resolved
as a null**, not inconclusive.

* granularity removes collateral entirely (0.4340 → 0.0000) with 2.7x fewer edits;
* it is **utility-neutral** (resolved null);
* it costs **+58% within-module damage** — the screen fails on WMD alone.

### Beta (200 seeds) — stable

`Contrastive − NegativeOnly`: **−0.01375**, CI [−0.01812, −0.00969], width
0.0084, p = 0.0000, Wilcoxon 2.4e−8, **PoI = 0.000**.
`CFRevalue` 0.8410 vs `NoCorrection` 0.9418 → **−0.1008**.
`NegativeOnly` wins every axis again. The plan's `H_B` is refuted and its strong
falsification condition holds.

### Gamma (200 seeds) — stable

`reward B − A`: **−0.0278** (`NoCorrection`), **−0.0260** (`NegativeOnly`), both
p = 0.0000; null for `DecisionOracle`. `severe − mild` negative for all three.
`NegativeOnly` wins all four cells. `N_delta_neg` under reward B: 890 / 566 / 525
— `r_failure = 0` is still not "no negative learning".

---

## v0.3 — re-run at 200 seeds

### Pilot Alpha — the CI now excludes zero

| | 12 seeds | 100 seeds | **200 seeds** |
|---|---|---|---|
| ΔAUC | +0.00247 | +0.00174 | **+0.00132** |
| 95% CI | [−0.00376, +0.01071] | [−0.00008, +0.00398] | **[+0.00005, +0.00278]** |
| median Δ | 0.00000 | 0.00000 | **0.00000** |
| ΔFinalSuccess | 0.00000 | 0.00000 | **0.00000** |

The bootstrap CI crossed zero between 100 and 200 seeds. **The statistical claim
changes; the substantive one does not**: the median paired difference is exactly
0, final success is identical to the digit, and the effect size is ~0.0013 AUC.
The honest statement is now "a difference of about +0.001 that the CI resolves,
with a zero median" — not "no difference".

### Pilot Beta — structural, unchanged

Oracle's innocent-module KnowledgeDamage is **exactly 0.00000** in every family
at 200 seeds, as at 20. `oracle_advantage` still true via `E_failure`; both
fatal gates pass. This is structural: the Oracle router never writes to the
innocent module, so no seed count can move it.

### Timing — structural, unchanged

`immediate_revisable − immediate_fixed` on correct credit: **−1.00000**, CI
[−1, −1], p = 0.0000 at 200 seeds, identical to 12 and 40. Every seed gives the
same number. Deferral's overcredit penalty likewise unchanged at +0.05009.

### Pilot Gamma — stable

| method | CF queries | Brier (8 seeds) | **Brier (200 seeds)** |
|---|---:|---:|---:|
| `oracle` | 0.00 | 0.0000 | 0.0000 |
| `sequence_only` | 0.00 | 0.1620 | **0.1621** |
| `seq_then_cf_k1` | 1.00 | 0.1966 | **0.1971** |
| `cf_only_k1` | 1.00 | 0.2044 | **0.2046** |
| `seq_then_cf_k2` | 1.40 | 0.1498 | **0.1501** |
| `cf_only_k2` | 1.60 | 0.1498 | **0.1501** |

The K=1 composition effect is **−0.00752** at 200 seeds against −0.00779 at 8,
and K=4 still saturates exactly at K=2 on every metric. Every number is
reproduced to three decimals. The `p_U` finding is likewise unchanged:
`sequence_only` detects the unexplained family far better than a single
one-hot counterfactual query does, and `AUPRC_L` stays low because
sufficiency-testing can only ever answer H or L.

### Stage 4 — strengthened

| arm | ΔAUC vs Traditional | p (30 seeds) | **p (200 seeds)** |
|---|---:|---:|---:|
| `positive_only` | −0.00272 | 0.0295 | **0.0029** |
| `direct_feedback` | −0.00595 | 0.0215 | **0.0000** |
| `random_correction` | −0.00322 | 0.4069 | **0.0000** |
| `global_value_rfl` | −0.00133 | 0.0943 | **0.0184** |
| `sequence_rfl` | −0.00076 | 1.0000 | 0.1169 |
| `learned_rfl` | −0.00076 | 1.0000 | 0.1206 |
| `oracle_rfl` | +0.00010 | 1.0000 | 0.8270 |

At 200 seeds **four** arms are significantly worse than doing nothing, and the
two RFL arms remain non-inferior. The conclusion "RFL is the only arm that
corrects without paying for it" is now much better supported, and the marginal
p-values that looked fragile at 30 seeds were real.

### Stage 5 — the 100-seed positive finding evaporates

| setting | 8 seeds | 100 seeds | **200 seeds** |
|---|---:|---:|---:|
| `base_h8_a10` | — | −0.00029 | +0.00190 (no) |
| `tight_h6_a10` | — | **+0.00757 (yes)** | **+0.00516 (no)** |
| `tight_h5_a10` | −0.021 (no) | −0.02673 (yes) | −0.01928 (yes) |
| `base_h8_a03` | — | −0.00188 (no) | −0.00201 (no) |
| `tight_h5_a03` | −0.08490 (yes) | −0.09018 (yes) | **−0.08672 (yes)** |
| `base_h8_a01` | — | −0.00647 (no) | **−0.00762 (yes)** |

**The one setting where Oracle routing helped at 100 seeds no longer separates
at 200.** The settings that survive are all *harmful* ones. Oracle's
innocent-module KD remains exactly 0.00000 in all six.

The defensible statement at 200 seeds: **Oracle routing is null at the base
settings and harmful under a tight horizon or very slow learning; the only
regime where it appeared to help was a 100-seed artifact.**

---

## The methodological point

Three v0.4 conclusions and two v0.3 conclusions moved as seeds increased, and
two of them moved **twice** (12 → 100 → 200). The ones that never moved are
exactly the ones that are **structural** rather than statistical:

* a router that never writes to a module cannot damage it — collateral is
  exactly 0.00000 at any seed count;
* a revision rule that touches nothing correct gives Δ = exactly −1.00000 on
  every seed;
* two arms whose difference is architecturally impossible (CF at K=1 cannot
  change the argmax) are identical to the last decimal.

Everything resting on a *mean* over seeds was exposed, and marginal settings
kept crossing the zero line. Results in this project should be reported with the
seed count attached, and conclusions that only ever lived near a CI boundary
should be treated as unresolved rather than as findings.
