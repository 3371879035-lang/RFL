# Reversal ledger — exactly at which N every conclusion changed

**Unit:** the statistical unit here is the **seed**. One seed = one complete,
independent training run (300 warmup + 2,000 episodes + 100 greedy evaluation
episodes). So "N = 300" means 300 independent runs, and the four scheduled looks
are at **100 / 200 / 300 / 400 局**.

Produced by `scripts/reversal_ledger.py`; raw output in
`outputs/reversal_ledger.txt` and `outputs/reversal_ledger.json`.

---

## 1. What counts as a reversal

Two readings are recorded side by side at every look.

| reading | rule | status |
|---|---|---|
| **CI** | does the 95% bootstrap CI of the cumulative mean exclude zero? | what the *old* rule used — reported only so the record shows what it said |
| **4-way** | where the CI sits relative to $\Delta_{\min} = 0.01$: `SUPPORT_A` / `EQUIVALENT` / `SUPPORT_B` / `INCONCLUSIVE` | **the frozen rule; this is what counts** |

A **reversal** is a change of the **4-way** verdict between two scheduled looks.
A CI-exclusion flip that leaves the 4-way verdict untouched is recorded as a
**no-op** — this is precisely the $p = 0.04 \rightarrow 0.07$ case that must not
be written up as a reversal.

## 2. Answer: yes, three new reversals appeared at N = 400

All three are in v0.3 Stage 5, and **all three are effects shrinking toward
zero — not one is a change of direction.**

| # | contrast | at N | reversal | caused by that fresh block alone |
|---|---|---|---|---|
| 1 | `v03_stage5 tight_h6_a10` | **400** | `INCONCLUSIVE → EQUIVALENT` | B4 = **+0.00114** |
| 2 | `v03_stage5 tight_h5_a10` | **400** | `SUPPORT_B → INCONCLUSIVE` | B4 = **−0.00959** |
| 3 | `v03_stage5 base_h8_a01` | **400** | `INCONCLUSIVE → EQUIVALENT` | B4 = **−0.00382** |

Two further reversals occurred earlier in the same 400-seed record — one of which
*strengthened* rather than weakened:

| # | contrast | at N | reversal | caused by that fresh block alone |
|---|---|---|---|---|
| 4 | `v04_beta Contrastive − NegativeOnly` | **200** | `INCONCLUSIVE → SUPPORT_B` | B2 = **−0.01625** |
| 5 | `v04_beta NoCorrection − NegativeOnly` | **300** | `INCONCLUSIVE → EQUIVALENT` | B3 = **−0.00000** |

**Five reversals in 23 contrasts.** Every one of them is explained by the fresh
block landing *closer to zero* than the running mean (reversals 1, 2, 3, 5) or
*further from it* (reversal 4). None is a block landing on the opposite side.

## 3. The seven reversals that were not reversals

Across all 23 contrasts there were **seven** CI-exclusion flips. Under the old
rule each would have been reported as a change in conclusion. Under the frozen
rule **the verdict did not move at a single one of them — all seven are no-ops.**

| contrast | at N | CI flipped | verdict before → after |
|---|---|---|---|
| `v03_stage5 base_h8_a10` | 300 | not-excl → excl | `EQUIVALENT → EQUIVALENT` |
| `v03_stage5 base_h8_a03` | 400 | not-excl → excl | `EQUIVALENT → EQUIVALENT` |
| `v03_stage5 base_h8_a01` | 200 | not-excl → excl | `INCONCLUSIVE → INCONCLUSIVE` |
| `v03_alpha` | 200 | not-excl → excl | `EQUIVALENT → EQUIVALENT` |
| `v03_alpha` | **400** | **excl → not-excl** | `EQUIVALENT → EQUIVALENT` |
| `v03_stage4 positive_only` | 200 | not-excl → excl | `EQUIVALENT → EQUIVALENT` |
| `v04_beta NoCorrection` | 200 | not-excl → excl | `INCONCLUSIVE → INCONCLUSIVE` |

Seven flips, zero conclusion changes. That is the entire yield of the
significance-testing lens on this dataset.

The `v03_alpha` row is the clearest case in the project. The old rule saw
*significant at 200* and *not significant at 400* and would have recorded a
reversal. The frozen rule records `EQUIVALENT` at **all four looks** — nothing
ever happened. The 200- and 300-seed "significant" intervals were five seeds
carrying 72% of the net sum in a contrast where 70% of seeds are exactly tied and
the movers split 46 up / 44 down.

The `base_h8_a10` row at N=300 is the one that was actually written up as
"Oracle routing now helps". It is a no-op: the verdict was `EQUIVALENT` before
and after.

## 4. Sign flips — six events, none of them material

Six times a cumulative mean crossed zero. All six sit **far inside**
$\Delta_{\min} = 0.01$:

| contrast | means at N = 100 / 200 / 300 / 400 | flips |
|---|---|---|
| `v03_stage5 base_h8_a10` | −0.00029 → **+0.00190** → +0.00260 → +0.00265 | 1 |
| `v03_stage4 oracle_rfl` | −0.00024 → **+0.00010** → +0.00011 → +0.00052 | 1 |
| `v04_alpha DecisionOracle − ModuleOracle` | +0.00550 → **−0.00033** → **+0.00826** → +0.00815 | **2** |
| `v04_alpha RepairOracle − ModuleOracle` | identical to the above | **2** |

Every flipped quantity is an order of magnitude below the minimum effect the
study was pre-registered to detect. **No effect large enough to matter ever
changed sign at any N.**

This is the frozen rule doing its job. `DecisionOracle − ModuleOracle` is v0.4
Alpha's headline: its point estimate wandered $+0.0055 \rightarrow -0.0003
\rightarrow +0.0083 \rightarrow +0.0082$ — three apparent "reversals" in the
narrative — while the honest verdict was `INCONCLUSIVE` at **every single look**.
The rule refused to manufacture a finding out of a quantity that never left the
undecided band.

## 5. What never moved

| contrast | verdict at 100 / 200 / 300 / 400 |
|---|---|
| **`v03_stage5 tight_h5_a03`** | **`SUPPORT_B` × 4** |
| `v04_beta Contrastive − NegativeOnly` (after N=200) | `SUPPORT_B` × 3 |
| `v04_beta CFRevalue − NegativeOnly` | `SUPPORT_B` × 4 |
| `v04_beta PositiveAlternative − NegativeOnly` | `SUPPORT_B` × 4 |
| `v04_alpha DecisionOracle / RepairOracle − ModuleOracle` | `INCONCLUSIVE` × 4 |
| `v04_alpha NoCorruption` / `NoCorrection − ModuleOracle` | `SUPPORT_A` × 4 |
| all 8 `v03_stage4` arms | `EQUIVALENT` × 4 |

The single confirmatory effect in the difficulty sweep — `tight_h5_a03`,
ΔAUC = −0.08275 — was `SUPPORT_B` in **all four looks and all four blocks
separately** (−0.0902, −0.0833, −0.0840, −0.0736). It never wobbled, at any N.

## 6. The pattern

$$\boxed{\text{Effects shrank toward zero as N grew; directions never changed in anything that mattered.}}$$

The three historical "reversals" that motivated running to 300 and then 400 were
movements of quantities with tie fractions of 90%, 80% and 70% — settings where
the majority of seeds are bit-identical between arms and the mean is a statement
about a few dozen runs. Adding seeds did not reveal a reversal; it revealed that
there had never been an effect to reverse.

**Consequence for the write-up rule:** a change in verdict is only reportable as
a reversal when it is accompanied by (a) the fresh block's own mean, and (b) the
sign test and top-5 share for that block. A reversal caused by a block whose mean
is inside $[-\Delta_{\min}, +\Delta_{\min}]$ is a statement about the decision
boundary, not about the phenomenon.
