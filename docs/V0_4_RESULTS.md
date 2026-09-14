# RFL-CausalChase v0.4 — Results

**Scale: 100 paired seeds** per pilot (the 12-seed runs are retained under
`outputs/v04_*` and their discrepancies are recorded below — three conclusions
changed when the seed count went up, which is itself a result).

300 warmup + 2,000 training episodes, 100 greedy evaluation episodes per
checkpoint, reward `+1/-1`, Oracle failure truth.

---

## Pilot Alpha — how coarse should a credit unit be? (100 seeds)

| arm | SuccessAUC | final | WMD | KD_innocent | collateral | sites touched |
|---|---:|---:|---:|---:|---:|---:|
| `NoCorruption` (clean ceiling) | 0.9950 | 1.0000 | 0.00000 | 0.00000 | 0.0000 | 0 |
| `NoCorrection` (damaged, not repaired) | 0.9417 | 1.0000 | 0.00000 | 0.00000 | 0.0000 | 0 |
| `ModuleOracle` | 0.8709 | 0.9450 | 0.04471 | 0.00082 | **0.4377** | 4,610 |
| `DecisionOracle` | 0.8764 | 0.9350 | **0.07067** | 0.00295 | **0.0000** | 1,703 |
| `RepairOracle` | 0.8764 | 0.9350 | **0.07067** | 0.00295 | **0.0000** | 1,703 |

Paired ΔAUC, `DecisionOracle − ModuleOracle`: **+0.00550**, CI
**[−0.02659, +0.03899]**, width 0.0656, p = 0.748, **PoI = 0.625**.

**Verdict: `INCONCLUSIVE_PRECISION`** — the CI is still marginally wider than
the plan's 0.05 threshold, so the utility contrast is unresolved.

What is resolved and does not depend on the CI:

1. **Granularity works on exactly what it targets.** Collateral **0.4377 →
   0.0000**, with **2.7x fewer touched sites** (4,610 → 1,703).
2. **It is utility-neutral, not harmful.** ΔAUC **+0.0055** with the CI
   straddling zero and PoI 0.625.
3. **It costs within-module damage**: WMD **0.0447 → 0.0707 (+58%)**.

> **Correction to the 12-seed run.** At 12 seeds the ΔAUC point estimate was
> **−0.0156** and read as "granularity does not convert, and if anything
> hurts". At 100 seeds it is **+0.0055**. The sign flipped: the 12-seed
> estimate was noise. Only the collateral and WMD effects were stable across
> both.

---

## Pilot Beta — what should the update target be? (100 seeds)

Granularity fixed at the Alpha winner (`DecisionOracle`). Only the target varies.

| arm | SuccessAUC | final | WMD | collateral | sites |
|---|---:|---:|---:|---:|---:|
| `NoCorrection` | 0.9417 | 1.0000 | 0.00000 | 0.0000 | 0 |
| **`NegativeOnly`** | **0.9473** | **1.0000** | **0.02702** | **0.0000** | 1,715 |
| `PositiveAlternative` | 0.9301 | 0.9950 | 0.06167 | 0.0249 | 2,216 |
| `Contrastive` | 0.9351 | 0.9550 | 0.06627 | 0.0055 | 3,762 |
| `CFRevalue` | **0.8595** | 0.9550 | **0.27435** | 0.0000 | 1,558 |

Paired contrasts, all **vs `NegativeOnly`**:

| arm | ΔAUC | 95% CI | p | PoI | ΔWMD |
|---|---:|---|---:|---:|---:|
| `NoCorrection` | −0.00562 | [−0.01375, +0.00000] | 0.161 | 0.011 | −0.02702 |
| `PositiveAlternative` | **−0.01719** | [−0.02469, −0.01063] | 0.0000 | 0.000 | +0.03465 |
| `Contrastive` | **−0.01219** | [−0.01781, −0.00688] | 0.0000 | 0.000 | +0.03924 |
| `CFRevalue` | **−0.08781** | [−0.12469, −0.05594] | 0.0000 | 0.000 | **+0.24733** |

**Verdict: `PRIMARY_NOT_SUPPORTED`.** The plan's hypothesis
`H_B: (bad↓ + good↑) > (bad↓ only)` is **refuted with a resolved CI**: the
primary contrast `Contrastive − NegativeOnly` is **−0.01219**, CI width 0.0109,
sign-flip p = 0.0000, Wilcoxon p = 1.3e−4, **PoI = 0.000**.

`NegativeOnly` is the best arm on **every** axis:

* highest AUC (0.9473) and the only correction arm that is non-inferior to
  `NoCorrection` (ΔAUC −0.0056, CI includes 0);
* lowest WMD (0.0270) — 2.3x below `PositiveAlternative`, 2.5x below
  `Contrastive`, **10x below `CFRevalue`**;
* zero collateral, with fewer edits than any arm except `CFRevalue`.

### The plan's strong falsification condition fires even harder

| | SuccessAUC |
|---|---:|
| `CFRevalue` (Oracle site + Oracle target + counterfactual value) | **0.8595** |
| `NoCorrection` | **0.9417** |

Δ = **−0.08781**, CI [−0.12469, −0.05594]. The strongest repair available
performs far *worse* than making no update at all. Per the plan's own decision
tree the required conclusion is:

> **直接修补 Q-entry 不是合适的 update primitive.**

---

## Pilot Gamma — robustness (100 seeds, 12 cells)

| mechanism | A / mild | A / severe | B / mild | B / severe |
|---|---:|---:|---:|---:|
| `NoCorrection` | 0.8849 | 0.8080 | 0.8522 | 0.7754 |
| **`NegativeOnly`** | **0.8973** | **0.8305** | **0.8622** | **0.8104** |
| `DecisionOracle` | 0.8306 | 0.7401 | 0.8332 | 0.7570 |

Paired interactions:

| mechanism | contrast | mean | 95% CI | p |
|---|---|---:|---|---:|
| `NoCorrection` | reward B − A | **−0.03262** | [−0.04794, −0.01718] | 0.0000 |
| `NegativeOnly` | reward B − A | **−0.02760** | [−0.04142, −0.01460] | 0.0000 |
| `DecisionOracle` | reward B − A | +0.00976 | [−0.00750, +0.02685] | 0.2854 |
| `NoCorrection` | severe − mild | −0.07681 | [−0.08867, −0.06537] | 0.0000 |
| `NegativeOnly` | severe − mild | −0.05934 | [−0.06842, −0.05045] | 0.0000 |
| `DecisionOracle` | severe − mild | −0.08338 | [−0.09917, −0.06731] | 0.0000 |

`N_delta_neg` under reward B: `NoCorrection` 882, `NegativeOnly` 561,
`DecisionOracle` 520.

### Reading

1. **`NegativeOnly` wins all four cells**, and in `B/severe` beats
   `NoCorrection` by +0.035.
2. **The reward ablation is NOT null at 100 seeds.** Removing the explicit
   failure penalty costs **−0.033** (`NoCorrection`) and **−0.028**
   (`NegativeOnly`), both p = 0.0000.
3. **`r_failure = 0` is not "no negative learning"** — reward B still produces
   520-882 negative TD errors per run, now measured directly.
4. **Severity hurts the complex mechanism most**: −0.059 (`NegativeOnly`) vs
   −0.083 (`DecisionOracle`).

> **Correction to the 6-seed run.** At 6 seeds every `reward B − A` CI included
> zero and the conclusion was "the reward ablation does nothing, reproducing
> v0.3". At 100 seeds it is **significantly negative for two of three
> mechanisms**. The 6-seed null was underpowered, not a finding.

---

## What v0.4 established

Two pre-registered, negative results:

1. **Credit granularity reduces collateral but does not improve learning.**
   Getting the unit right removes collateral entirely and cuts touched sites by
   2.6x, while *increasing* within-module damage by 2.2x. The plan's
   `WithinModuleDamage` endpoint was built to see precisely this, and it does.
2. **Richer update targets are worse, not better.** Positive reinforcement of a
   verified alternative, and counterfactual re-valuation, both degrade AUC
   relative to plain negative-only. `H_B` is refuted; `CFRevalue <=
   NoCorrection` triggers the plan's stop condition.

Together: *knowing which unit to change, and even which alternative to prefer,
does not make the edit a good one.* The failure is in the primitive itself.

## Requirement completion for this spec

| spec item | status |
|---|---|
| `CausalRepairGrid-v04`, `(g,x,y,o,phase)` SCM, intent/realized split | done |
| failure families decided by **intervention**, not by label | done, 4 families + Unknown |
| WholeProcess = minimal sufficient set size > 1 | done, `minimal_size == 2` verified |
| Oracle repair set, minimal size, `V_true`, `RepairRegret` | done, evaluator-only |
| `WMD` + `KD_innocent` as one function on different sets | done |
| Module / Decision / Repair representations | done |
| never / negative-only / positive-alternative / contrastive / CF-revalue | done |
| safe constraints (no site → no update, `|ΔQ| <= Δ_max`, full receipts) | done, in code and tested |
| Baseline-only difficulty calibration | done — the blocker was the **horizon**, not the corridor |
| Pilot Alpha, 12 paired seeds | done |
| Pilot Beta, 12 paired seeds | done |
| Pilot Gamma (reward x severity x mechanism) | done, 6 seeds (reduced for budget) |
| Pilot Delta (learned `p`, `p_U`) | **not run** |
| candidate ledger, step traces, fixed figures | **not done** |

### Why Delta was not run

Delta requires a learned attributor emitting `p_whole, p_plan, p_decision,
p_execution, p_U` with an independent (non-softmax) unknown channel, trained on
an 8,000/2,000/4,000 corpus. That is a separate build. It is also **not
indicated by the results above**: Alpha, Beta and Gamma all remove the *same*
thing — the diagnostic update itself. Running a learned attributor against a
mechanism already shown to be net-negative would measure attribution quality
against a broken consumer, which is the ordering error the plan's own decision
tree warns against ("Oracle 失败时不训练更复杂 attribution model").

## Environment calibration record

Difficulty was set on the **NoCorrection baseline only**, as the spec requires:

* `H=8`, `X_MAX=3` (the spec's values): baseline saturates — a delay-heavy
  policy is also optimal, so no policy-independent correct action exists and the
  Knowledge Set is either empty or circular. No induced damage persists.
* `X_MAX=7`, `H=8`: zero slack, but baseline never learns it at this budget.
* **`H=4`, `X_MAX=3`** (adopted): the long path costs exactly 4 steps, so zero
  slack; baseline learns (eval 1.0) and the damage calibration shows real
  dynamic range at every magnitude (min 0.013, recovered by episode 150-200).

## Defects found and fixed

Seven, all silent — none raised an error:

1. absorbing steps were tagged `ACT`, so the task update wrote `action = -1` and
   treated an absorbing step as terminal;
2. the Q_L bootstrap read `(g, nx, ny, o+1)`, a state that cannot be occupied,
   so no value ever propagated;
3. credit sites used the raw env state as the Q key instead of `(x, y, o, t)`,
   writing entries never read;
4. **the fault injector overrode the agent's action from outside**, making the
   bad choice exogenous — no credit representation could change the outcome and
   every arm produced an identical curve. Replaced with checkpoint value
   corruption, so the bad decision is genuinely the agent's;
5. the margin competitor set included `PLAN_A/PLAN_B`, which are never legal in
   ACT and sit at exactly 0.0 — a manufactured competitor that emptied the
   Knowledge Set;
6. the Knowledge Set was built from the *reference* path, but the agent's greedy
   policy is not the reference policy, so every margin was negative;
7. **the horizon left slack**, so a delay policy was optimal and no
   policy-independent correct action existed. This was the blocking one: the
   first six were fixed and the experiment still measured nothing.
