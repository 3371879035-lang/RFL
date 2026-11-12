# Robustness audit — why the seed-block protocol exists

**Scope:** the exploratory runs at 8 / 12 / 20 / 30 / 40 / 50 / 100 / 200 / 300
seeds. These are **history, not evidence**. The confirmatory analysis is the
frozen protocol in `docs/SEED_BLOCK_PROTOCOL.md`.

---

## 1. What happened

As the seed count went up, conclusions moved — repeatedly, and sometimes twice:

| pilot | 8 / 12 | 100 | 200 | 300 |
|---|---|---|---|---|
| v0.4 Alpha (granularity) | "hurts" (−0.0156) | +0.0055 | resolved null | resolved null |
| v0.3 Alpha (reward) | null | null | CI excludes 0 | CI excludes 0 |
| v0.3 Stage 5 (difficulty) | 1/6 separate | 3/6, one positive | positive gone | 5/6, two positive |

The original response was to add seeds whenever a conclusion changed. **That
response was itself an error**: it is optional stopping. Letting a p-value decide
whether to keep collecting inflates the type-I error rate, and the intervals
reported along the way do not mean what they appear to mean. Two errors were
being compounded — the instability, and the method used to chase it.

## 2. The mechanism

The instability is not generic small-sample noise. Per-seed paired deltas in this
codebase have a specific, diagnosable shape:

* **Zero-inflation.** A large fraction of seeds produce *bit-identical* runs
  across two arms, because the tabular Q-iteration reaches the same fixed point
  and the only difference between the arms is a correction that never fires. The
  paired delta is then exactly `0.0`.
* **Heavy tails.** Among the seeds that do differ, a single divergent bootstrap
  can change which fixed point is reached, moving AUC by 0.3–0.5.

A mean over such a distribution is a statement about a handful of seeds. The
sign of the mean can disagree with the sign of the median, and a bootstrap CI
that excludes zero can coexist with a sign test that is indistinguishable from a
coin flip.

Produced by `scripts/robustness_audit.py`.

## 3. The audit at 300 seeds

`top5%` is the share of the net sum contributed by the five largest `|Δ|` seeds.
`mean_wo5` drops those five. `sign_p` is an exact binomial test on the non-tied
seeds only — it uses direction, never magnitude. `holm` corrects across the six
Stage 5 settings.

### v0.3 Alpha — `traditional − positive_only`

| n | mean | median | trim 5% | ties | +/− | sign_p | Wilcoxon | top5% | mean_wo5 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 300 | **+0.00116** | **0.00000** | +0.00015 | **210 (70%)** | **46/−44** | **0.9161** | 0.3058 | **72%** | +0.00033 |

At 200 and 300 seeds the bootstrap CI excluded zero and this was written up as
"a difference of about +0.001 that the CI resolves". The audit says otherwise:
**70% of seeds are exactly tied, and among the 90 that moved the split is 46 up
against 44 down — a coin flip (p = 0.92).** The positive mean exists only because
five seeds carry 72% of the net sum; drop them and the mean falls to +0.00033.

This was never a finding, at any seed count. The CI crossed zero between 100 and
200 seeds for the same reason: it was tracking tail magnitude, not a replicating
effect.

### v0.4 Alpha — `DecisionOracle − ModuleOracle`

| n | mean | median | trim 5% | ties | +/− | sign_p | Wilcoxon | top5% | mean_wo5 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 300 | **+0.00826** | **−0.00812** | **−0.00420** | 78 | **71/−151** | **0.0000** | 0.0809 | **97%** | **+0.00028** |

This is the most consequential correction in the audit. The published reading was
"granularity is utility-neutral, a resolved null". Every robust statistic
disagrees:

* the **median seed is negative** (−0.00812) — the typical run is *worse* with
  finer granularity;
* **151 of the 222 non-tied seeds are negative**, against 71 positive; the sign
  test is significant in the **negative** direction (p = 0.0000);
* five seeds contribute **97%** of the net sum; without them the mean is
  +0.00028, indistinguishable from zero.

So the correct statement is not "utility-neutral". It is: **granularity is
mildly harmful on the typical seed, and the mean-based screen hid this behind
five outliers.** The 300-seed CI `[−0.0094, +0.0269]` is dominated by those five
seeds and should not have been read as a resolved null.

The two structural findings from that pilot are unaffected and remain exact:
collateral `0.4350 → 0.0000`, and WMD `+62%`.

### v0.3 Stage 5 — `oracle − traditional`

| setting | mean | median | trim 5% | ties | +/− | sign_p | Holm | top5% | mean_wo5 | verdict |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `base_h8_a10` | +0.00260 | 0.00000 | +0.00084 | **270 (90%)** | 22/−8 | 0.0161 | 0.0095 | 31% | +0.00183 | tail-driven |
| `tight_h6_a10` | +0.00598 | 0.00000 | +0.00467 | 111 (37%) | 105/−84 | **0.1455** | **0.0673** | 20% | +0.00487 | tail-driven |
| `tight_h5_a10` | −0.01654 | −0.01875 | −0.01855 | 47 (16%) | 74/−179 | 0.0000 | 0.0000 | −4% | −0.01745 | **robust** |
| `base_h8_a03` | −0.00233 | 0.00000 | −0.00319 | **240 (80%)** | 21/−39 | 0.0273 | 0.0797 | −62% | −0.00384 | tail-driven |
| `tight_h5_a03` | −0.08581 | −0.09500 | −0.08881 | **9 (3%)** | 22/−269 | 0.0000 | 0.0000 | 2% | −0.08531 | **robust** |
| `base_h8_a01` | −0.00748 | 0.00000 | −0.00794 | 211 (70%) | 22/−67 | 0.0000 | 0.0000 | −3% | −0.00784 | **robust** |

This resolves the third reversal. **The two settings that "became positive"
at 300 seeds are the two weakest entries in the table**, not findings:

* `base_h8_a10` has **90% ties** — only 30 of 300 seeds differ at all, and the
  mean is a statement about those 30;
* `tight_h6_a10` fails a sign test (p = 0.1455) and **fails Holm** (p = 0.0673).

Every reversal the project recorded happened in a row with a tie fraction above
37%. The rows that never moved — `tight_h5_a03` at 3% ties with 269 of 300 seeds
negative, and `tight_h5_a10` at 16% — were robust at every seed count.

## 4. What the audit changes

| claim as previously written | status after audit |
|---|---|
| v0.3 Alpha: reward contrast resolved, CI excludes 0 | **withdrawn** — 70% ties, sign test p = 0.92 |
| v0.4 Alpha: granularity is utility-neutral (resolved null) | **corrected** — median negative; mean is 97% five seeds |
| v0.3 Stage 5: two settings now favour Oracle routing | **withdrawn** — 90% ties, and Holm-failing |
| v0.4 Beta: `H_B` refuted, PoI = 0 | holds — need the audit at 400 to confirm robustness |
| v0.4 Alpha: collateral 0.4350 → 0.0000; WMD +62% | holds — structural, seed-invariant |
| v0.3 Beta: Oracle innocent-module KD exactly 0.00000 | holds — structural |
| v0.3 Timing: Δ exactly −1.00000 | holds — structural |

The pattern is consistent: **structural claims never moved; every claim resting
on a mean over seeds was at risk, and three of them did not survive.**

## 5. Consequence

Two things follow, and both are now enforced:

1. **No more optional stopping.** `N_max = 400` is frozen, in four disjoint
   100-seed blocks, with the four-way decision rule of
   `docs/SEED_BLOCK_PROTOCOL.md`. A p-value crossing 0.05 is not a conclusion
   change; only movement of the CI relative to `Δ_min = 0.01` is.
2. **No mean without its robustness statistics.** Tie fraction, median, trimmed
   mean, sign test and top-5 share are reported for every contrast. A contrast
   whose mean, median and trimmed mean disagree in sign is `TAIL-DRIVEN` and is
   not a finding, whatever its CI says.

## 6. Reproducing this document

```bash
python scripts/robustness_audit.py outputs/v03_stage5_300
python scripts/robustness_audit.py outputs/v04_alpha_300 --baseline ModuleOracle
python scripts/robustness_audit.py outputs/v03_alpha_300 --baseline traditional
python scripts/block_analysis.py   outputs/v03_stage5_300
```

`tests/test_block_protocol.py` pins the four-way decision boundaries and the
block-decomposition identity.
