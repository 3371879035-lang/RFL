# Frozen-protocol results — N = 400

**This is the only confirmatory document in the project.**

Everything else — `docs/RESULTS.md`, `docs/V0_3_CLOSEOUT.md`, `docs/V0_4_RESULTS.md`,
`docs/SEED_AUDIT_200.md`, `docs/ROBUSTNESS_AUDIT.md` — reports runs made at
8 / 12 / 20 / 30 / 40 / 50 / 100 / 200 / 300 seeds under a rule ("if the
conclusion changed, run more seeds") that is optional stopping. Those documents
are retained as history and are **not** evidence. This one is.

Protocol: `docs/SEED_BLOCK_PROTOCOL.md`. `N_max = 400` in four fresh,
non-overlapping 100-seed blocks; looks at N = 100/200/300/400 each reporting the
cumulative result **and** the new block alone; conclusion defined by where the CI
sits relative to $\Delta_{\min} = 0.01$, not by whether $p$ crossed 0.05.

---

## 0. Code provenance

A reproducibility defect in `src/rflv04` was found mid-collection: training
depended on `PYTHONHASHSEED`, giving a **3.3x spread in `WMD`** for identical
inputs (`docs/V0_4_REPRODUCIBILITY_DEFECT.md`). Under §9.1 of the protocol a bug
voids the entire seed set, so every in-flight v0.4 run was killed, the fix was
committed, and **all v0.4 pilots restarted from N = 0** on the fixed code. The
pre-fix numbers at 6/12/100/200/300 seeds are void.

Verified after the fact, not asserted:

| check | result |
|---|---|
| `git status --short src/` during collection | empty — tree matched `HEAD` throughout |
| commits touching `src/` since pilots began | one, the fix `9c03f43` |
| files that commit changed | `src/rflv04/credit_units.py` only |
| `src/rflnext` (v0.3 pilots) affected? | **no** |

Because the fix touched only `src/rflv04`, the v0.3 pilots ran on a single
unchanged codebase at every seed count. Confirmed empirically as well as by
inspection: the 300-seed Stage 5 run and the first 300 seeds of the 400-seed run
were separate processes, and all 1,800 `(setting, seed)` pairs match bit-for-bit.

---

## 1. The headline

$$\boxed{\text{Oracle routing is harmful in exactly one regime, and nothing else about it is resolvable.}}$$

The project's three recorded "reversals" in Stage 5 were all movements of
quantities that were never distinguishable from noise. Under the pre-registered
rule, **five of the six difficulty settings are `EQUIVALENT` or `INCONCLUSIVE`,
and one is `SUPPORT_B` in all four blocks independently.** That is the entire
difficulty-sweep result.

### Where the reversals actually happened

Full ledger in `docs/REVERSAL_LEDGER.md`. In summary, across 23 contrasts:

| | count | at which N |
|---|---|---|
| **frozen-verdict reversals** | **5** | three at **N=400**, one at N=300, one at N=200 |
| of those, direction changes | **0** | every one was the effect shrinking toward zero |
| CI-exclusion flips | 7 | **all 7 were no-ops** — the verdict did not move |
| cumulative-mean sign flips | 6 | all in quantities well inside $\Delta_{\min}$ |

The three new reversals at N=400 are `tight_h6_a10` (`INCONCLUSIVE →
EQUIVALENT`, B4 alone = +0.00114), `tight_h5_a10` (`SUPPORT_B → INCONCLUSIVE`,
B4 alone = −0.00959) and `base_h8_a01` (`INCONCLUSIVE → EQUIVALENT`, B4 alone =
−0.00382). Each is the fourth block landing closer to zero than the running mean
— a statement about the decision boundary, not about the phenomenon.

**Not one effect large enough to matter ever changed sign**, at any N.
`DecisionOracle − ModuleOracle` wandered $+0.0055 \rightarrow -0.0003
\rightarrow +0.0083 \rightarrow +0.0082$ and was `INCONCLUSIVE` at every look;
the rule refused to turn that into three findings.

---

## 2. v0.3 Stage 5 — difficulty sweep (N = 400)

Contrast `oracle − traditional` on task AUC, $\Delta_{\min} = 0.01$.

| setting | ΔAUC | 95% CI | **decision** | trajectory across looks | blocks |
|---|---:|---|---|---|---|
| `base_h8_a10` | +0.00265 | [+0.00127, +0.00410] | `EQUIVALENT` | E → E → E → E | **sign-disagree** |
| `tight_h6_a10` | +0.00477 | [+0.00081, +0.00863] | `EQUIVALENT` | I → I → I → E | — |
| `tight_h5_a10` | −0.01480 | [−0.01994, −0.00955] | `INCONCLUSIVE` | B → B → B → **I** | — |
| `base_h8_a03` | −0.00294 | [−0.00507, −0.00082] | `EQUIVALENT` | E → E → E → E | — |
| **`tight_h5_a03`** | **−0.08275** | **[−0.08919, −0.07609]** | **`SUPPORT_B`** | **B → B → B → B** | **all four** |
| `base_h8_a01` | −0.00656 | [−0.00952, −0.00350] | `EQUIVALENT` | I → I → I → E | — |

Oracle's innocent-module KnowledgeDamage is **exactly 0.00000 in all six
settings**, as at every earlier seed count. That is structural: the router never
writes to the innocent module, so no seed count can move it.

### The one finding

`tight_h5_a03` — horizon 5, `alpha = 0.03` — is harmful by **−0.0828 AUC**, and
this holds in **every one of the four independent blocks** (`−0.0902`, `−0.0833`,
`−0.0840`, `−0.0736`), with 269 of 300 non-tied seeds negative at N=300 and only
2% of the net sum coming from the five largest seeds.

### Why the other five are not findings

* `base_h8_a10` and `base_h8_a03` are `EQUIVALENT` at **every look**, and their
  blocks disagree in sign. The +0.0026 at N=300 that was briefly read as "Oracle
  routing now helps" came from a setting where **90% of seeds are exactly tied**
  — only 30 of 300 seeds differ at all.
* `tight_h6_a10` was the 100-seed "positive finding", lost it at 200, regained it
  at 300, and at 400 is `EQUIVALENT`. At 300 its sign test was p = 0.1455 and it
  **failed Holm** (p = 0.0673). It was never significant under any
  multiple-comparison correction.
* `tight_h5_a10` and `base_h8_a01` weaken from `SUPPORT_B` to `INCONCLUSIVE` /
  `EQUIVALENT` as the block means shrink toward zero, which is variance
  reduction, not a reversal.

**The defensible sentence:** *Oracle routing is neutral across the base
configurations, mildly and unsteadily negative under a tight horizon with
`alpha = 0.10`, and clearly harmful — about −0.08 AUC, replicated in four
independent blocks — under a tight horizon with `alpha = 0.03`.*

---

## 3. v0.3 Alpha — reward shaping (N = 400)

Contrast `traditional − positive_only`.

| | 12 | 100 | 200 | 300 | **400** |
|---|---|---|---|---|---|
| ΔAUC | +0.00247 | +0.00174 | +0.00132 | +0.00116 | **+0.00083** |
| 95% CI | [−0.00376, +0.01071] | [−0.00008, +0.00398] | [+0.00005, +0.00278] | [+0.00015, +0.00229] | **[−0.00004, +0.00172]** |
| p | — | — | <0.05 | 0.0328 | **0.0698** |

**Decision: `EQUIVALENT` at every look and in every block.** The 200- and
300-seed CIs that excluded zero were an artifact of five seeds carrying 72% of
the net sum: 210 of 300 seeds are exactly tied, and among those that moved the
split was 46 up against 44 down — a sign test of p = 0.92.

This result was predicted by `docs/ROBUSTNESS_AUDIT.md` before the 400-seed data
existed, and the 400-seed CI crossing back over zero confirms it. The earlier
write-up ("a difference of about +0.001 that the CI resolves") is withdrawn.

---

## 4. v0.3 Stage 4 — end-to-end (N = 400)

Contrast `arm − traditional` on task AUC.

| arm | ΔAUC | 95% CI | p | Holm | verdict |
|---|---:|---|---:|---:|---|
| `direct_feedback` | −0.00532 | — | 0.0000 | 0.0000 | **ROBUST harmful** |
| `random_correction` | −0.00322 | — | 0.0000 | 0.0000 | **ROBUST harmful** |
| `aux_penalty_rfl` | −0.00277 | [−0.00372, −0.00186] | 0.0000 | 0.0000 | **ROBUST harmful** |
| `positive_only` | −0.00181 | — | 0.0032 | 0.0158 | tail-driven (5 seeds) |
| `global_value_rfl` | −0.00089 | [−0.00170, −0.00010] | 0.0118 | 0.0471 | direction unresolved |
| `sequence_rfl` | −0.00056 | [−0.00130, +0.00017] | 0.0915 | 0.2077 | direction unresolved |
| `learned_rfl` | −0.00056 | [−0.00132, +0.00017] | 0.0915 | 0.2077 | direction unresolved |
| `oracle_rfl` | +0.00052 | [−0.00006, +0.00111] | 0.0692 | 0.2077 | tail-driven |

Pre-registered gates, both **pass**:

* `learned_rfl` non-inferior on AUC at margin 0.02 — the CI is
  [−0.00132, +0.00017], well inside;
* `learned_rfl` reduces knowledge damage vs `direct_feedback` —
  ΔCollateral **−0.26509**, CI [−0.27139, −0.25854], p = 0.0000.

The conclusion holds and is now sharpened: **three correction mechanisms are
robustly worse than doing nothing, and the two RFL arms are the only ones that
are not — while cutting collateral by 0.265 against the strongest naive
baseline.** `oracle_rfl`, the evaluator-truth ceiling, is not distinguishable
from zero, which is the same defect Stage 5 localised.

---

## 5. v0.4 Alpha — credit-unit granularity (N = 400)

| arm | SuccessAUC | final | WMD | KD_innocent | collateral | sites |
|---|---:|---:|---:|---:|---:|---:|
| `NoCorruption` (clean ceiling) | 0.9949 | 1.0000 | 0.00000 | 0.00000 | 0.0000 | 0 |
| `NoCorrection` (damaged) | 0.9432 | 0.9988 | 0.00000 | 0.00000 | 0.0000 | 0 |
| `ModuleOracle` | 0.8782 | 0.9587 | 0.04167 | 0.00082 | **0.4352** | 4,574.7 |
| `DecisionOracle` | 0.8864 | 0.9413 | **0.06571** | 0.00312 | **0.0000** | 1,714.8 |
| `RepairOracle` | 0.8864 | 0.9413 | **0.06571** | 0.00312 | **0.0000** | 1,714.8 |

Three results, and they carry **different** evidential weight:

**(a) Granularity eliminates collateral. `0.4352 → 0.0000`, exactly.**
Structural — the fine unit never writes outside the blamed decision — and
therefore unmovable by any seed count. With **2.67x fewer edits**
(4,574.7 → 1,714.8).

**(b) Granularity raises within-module damage. ΔWMD = +0.024033, `ROBUST`.**
This is a genuine finding, and the audit says so on every axis: only 5 of 400
seeds tied, **304 positive against 91 negative**, median (+0.0232) agrees with
the mean, the five largest seeds carry just **23%** of the net sum, and dropping
them leaves +0.0188. Relative increase **+57.7%**.

**(c) The utility contrast is not resolvable — and the earlier "utility-neutral"
reading of it was wrong too.**

| | ΔAUC `DecisionOracle − ModuleOracle` |
|---|---|
| mean | **+0.00815** |
| median | **0.00000** |
| trimmed 5% | **−0.00494** |
| ties | 122 / 400 |
| non-tied split | **87 positive / 191 negative** |
| sign test | p = 0.0000, *in the negative direction* |
| top-5 share of net sum | **76%** |
| mean without those 5 | +0.00199 |
| cumulative CI | [−0.0065, +0.0236] → **`INCONCLUSIVE`** |

The mean is positive; the median, the trimmed mean and the sign test all point
the other way. **The honest statement is not "utility-neutral" and not
"harmful": the effect of granularity on task utility is unresolved, and the mean
that made it look mildly positive is carried by five seeds out of four hundred.**

> **Correction to `docs/V0_4_RESULTS.md`.** That document reported granularity as
> "utility-neutral, a resolved null". Both halves were wrong. The pre-fix 300-seed
> numbers it rested on were also one `PYTHONHASHSEED` draw. The collateral figure
> it reported survives exactly; the utility and WMD readings do not survive as
> written.

---

## 6. v0.4 Beta — update target (N = 400)

Granularity fixed at the Alpha representation. Contrasts **vs `NegativeOnly`**.

| arm | SuccessAUC | final | WMD | collateral | sites |
|---|---:|---:|---:|---:|---:|
| `NoCorrection` | 0.9432 | 0.9988 | 0.00000 | 0.0000 | 0 |
| **`NegativeOnly`** | **0.9477** | **0.9988** | **0.03589** | **0.0000** | 1,708.1 |
| `PositiveAlternative` | 0.9312 | 0.9888 | 0.09139 | 0.0245 | 2,217.0 |
| `Contrastive` | 0.9336 | 0.9475 | 0.05479 | 0.0054 | 3,772.5 |
| `CFRevalue` | **0.8509** | 0.9325 | **0.26616** | 0.0000 | 1,578.0 |

| contrast | ΔAUC | 95% CI | p (sign-flip) | Wilcoxon | PoI | top-5 share | robustness |
|---|---:|---|---:|---:|---:|---:|---|
| `NoCorrection` | −0.00455 | — | 0.0030 | 0.0030 | — | 70% | tail-driven |
| `PositiveAlternative` | −0.01656 | — | 0.0000 | 0.0000 | 0.000 | 11% | **ROBUST** |
| **`Contrastive`** | **−0.01414** | **[−0.01719, −0.01117]** | **0.0000** | **3.0e−16** | **0.000** | 13% | **ROBUST** |
| `CFRevalue` | −0.09680 | — | 0.0000 | 0.0000 | 0.000 | 12% | **ROBUST** |

**Decision: `PRIMARY_NOT_SUPPORTED`.** The plan's hypothesis
$H_B: (\text{bad}\downarrow + \text{good}\uparrow) > (\text{bad}\downarrow
\text{only})$ is **refuted**, and this is the most robust result in the project:
CI width 0.0060, sign-flip p = 0.0000, Wilcoxon p = 3e−16, probability of
improvement **0.000**, and 100 non-tied seeds negative against 6 positive.

`NegativeOnly` is best on every axis: highest AUC, only correction arm
statistically indistinguishable from `NoCorrection`, and lowest WMD — 1.5x below
`Contrastive`, 2.5x below `PositiveAlternative`, **7.4x below `CFRevalue`**.

### The plan's strong falsification condition fires

| | SuccessAUC |
|---|---:|
| `CFRevalue` — Oracle site + Oracle target + counterfactual value | **0.8509** |
| `NoCorrection` — make no update at all | **0.9432** |

Δ = **−0.0923**. The strongest repair available performs far *worse* than doing
nothing. Per the plan's own decision tree the required conclusion is:

> **直接修补 Q-entry 不是合适的 update primitive.**

---

## 7. v0.4 Gamma — robustness (N = 400, 12 cells)

| mechanism | A / mild | A / severe | B / mild | B / severe |
|---|---:|---:|---:|---:|
| `NoCorrection` | 0.8833 | 0.7899 | 0.8578 | 0.7628 |
| **`NegativeOnly`** | **0.8948** | **0.8279** | **0.8725** | **0.8097** |
| `DecisionOracle` | 0.8385 | 0.7324 | 0.8423 | 0.7501 |

| mechanism | contrast | mean | 95% CI | p |
|---|---|---:|---|---:|
| `NoCorrection` | reward B − A | **−0.02629** | [−0.03396, −0.01837] | 0.0000 |
| `NegativeOnly` | reward B − A | **−0.02026** | [−0.02629, −0.01424] | 0.0000 |
| `DecisionOracle` | reward B − A | +0.01078 | [+0.00176, +0.02007] | 0.0198 |
| all three | severe − mild | −0.09425 / −0.06484 / −0.09921 | all exclude 0 | 0.0000 |

`N_delta_neg` under reward B: `NoCorrection` 896, `NegativeOnly` 565,
`DecisionOracle` 521 per 2,000 episodes.

1. **`NegativeOnly` wins all four cells**, and in `B/severe` beats
   `NoCorrection` by +0.047.
2. **The reward ablation is not null.** Removing the explicit failure penalty
   costs −0.026 and −0.020 for the two non-oracle mechanisms, both p = 0.0000 —
   an order of magnitude larger than $\Delta_{\min}$, so this is a real effect
   and not a boundary case.
3. **`r_failure = 0` is not "no negative learning"**: 521–896 negative TD errors
   per run remain, now measured directly.
4. **Severity hurts the complex mechanism most** (−0.0648 vs −0.0992).

---

## 8. v0.1 Experiment A — 50 → 200 seeds

The original confirmatory run used 50 seeds; it was re-run at 200 from a clean
output directory (the runner appends to its CSVs, so the 50-seed artifacts were
moved aside to `outputs/confirmatory_a/_as_run_50seeds/` first).

| statistic | 50 seeds | **200 seeds** |
|---|---:|---:|
| ΔAE, symmetric condition | −0.272 | **−0.268** (d_z −5.99) |
| ΔWUR, symmetric condition | −0.026 | **−0.025** (d_z −0.44) |

The confirmatory result **replicates**: the attribution-error effect is stable at
−0.27 with d_z ≈ −6, and the write-utilization effect remains far short of its
pre-registered ≤ −0.10 threshold. This is the one pilot in the project whose
conclusion did not move with seed count — and it is also the one with the
largest effect size relative to its threshold.

---

## 9. What is a finding

| claim | evidence | status |
|---|---|---|
| Oracle routing is harmful at horizon 5, alpha 0.03 (−0.0828) | `SUPPORT_B` in 4/4 blocks | **finding** |
| `Contrastive − NegativeOnly` = −0.0141, $H_B$ refuted | CI width 0.0060, PoI 0.000, robust | **finding** |
| `CFRevalue` − `NoCorrection` = −0.0923; patching Q-entries is the wrong primitive | CI excludes 0, robust | **finding** |
| Granularity eliminates collateral (0.4352 → 0.0000) | structural, exact | **finding** |
| Granularity raises WMD by 57.7% | 304/395 non-tied positive, top-5 share 23% | **finding** |
| Reward ablation costs −0.020 to −0.026 | p = 0.0000, ≫ Δ_min | **finding** |
| Two RFL arms non-inferior; collateral −0.265 vs `direct_feedback` | gates pass | **finding** |
| v0.1 ΔAE = −0.268 | d_z −5.99 at 200 seeds | **finding** |
| Granularity is utility-neutral | mean +0.0082 but median 0, sign test negative, top-5 share 76% | **withdrawn → `INCONCLUSIVE`** |
| Oracle routing helps at tight_h6_a10 | failed Holm at 300; `EQUIVALENT` at 400 | **withdrawn** |
| Oracle routing helps at base_h8_a10 | 90% ties; blocks disagree in sign | **withdrawn** |
| v0.3 reward contrast is resolved | 70% ties; CI includes 0 at 400 | **withdrawn** |

## 10. Open defects

Found by the candidate-ledger audit (`scripts/v04_ledger.py`), **not fixed** —
they were reported after the 400-seed collection was launched, and changing
behaviour mid-collection is prohibited by §9 of the protocol. They are recorded
for v0.5:

1. **`scene_from_trace` (`oracle.py:157`) uses the realized action** to locate
   the critical decision, although `env.py` records intent and realized
   separately precisely so execution faults are never mistaken for bad
   decisions. Consequence: `Execution` is 0.36% of failures while 56% carry an
   execution fault, and **`WholeProcess` at 68.4% is inflated by reconstruction,
   not by genuinely multi-fault episodes.** This is the most consequential open
   item — it means the family the spec singles out as the hard case is largely an
   artifact.
2. **The `DECISION`/`EXECUTION` collision** (`docs/V0_4_REPRODUCIBILITY_DEFECT.md`
   §7): the two units are nominally distinct but write the same Q entry. The fix
   made the outcome deterministic; it did not make it principled. Now counted and
   reported via `Credit.collisions()` rather than hidden.
3. `enumerate_sufficient` stops at the first sufficient size, so `minimal` is
   `True` for all 7,083 candidates and carries no information.
4. `classify` returns family `"CLEAN"` for **failed** episodes whose
   reconstruction is reference-solvable — 83 rows (1.2%) with empty candidate
   sets, silently skipped by `train.py`.
5. Latent: `Repair.describe()` is the tie-break key, so for `t >= 10`
   `exec:(10,)` sorts before `exec:(2,)`. Inactive at `HORIZON = 4`.

Confirmed correct in the same audit: **`WholeProcess == (minimal_size > 1)`**,
7,137/7,137 rows, 0 disagreements. The spec's operational definition holds; what
is in doubt is how many real episodes belong to the family.

## 11. Pilot Delta — still not run

Delta requires a learned attributor emitting `p_whole, p_plan, p_decision,
p_execution, p_U` with an independent unknown channel, trained on an
8,000/2,000/4,000 corpus. It is not indicated: Alpha, Beta and Gamma all remove
the *same* thing, the diagnostic update itself. Running a learned attributor
against a mechanism already shown to be net-negative measures attribution quality
against a broken consumer — the ordering error the plan's own decision tree warns
against.
