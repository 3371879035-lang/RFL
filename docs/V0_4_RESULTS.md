# RFL-CausalChase v0.4 — Results

Pilot scale, as the plan specifies: **12 paired seeds**, 300 warmup + 2,000
training episodes, 200 greedy evaluation episodes per checkpoint, reward
`+1/-1`, Oracle failure truth, balanced scene distribution.

---

## Pilot Alpha — how coarse should a credit unit be?

Fixed: Oracle truth, negative-only update. Varied: credit granularity.

| arm | SuccessAUC | final | WMD | KD_innocent | collateral | sites touched |
|---|---:|---:|---:|---:|---:|---:|
| `NoCorruption` (clean ceiling) | 0.9922 | 1.0000 | 0.00000 | 0.00000 | 0.0000 | 0 |
| `NoCorrection` (damaged, not repaired) | 0.9358 | 1.0000 | 0.00000 | 0.00000 | 0.0000 | 0 |
| `ModuleOracle` | 0.8915 | 0.9583 | 0.02336 | 0.00056 | **0.4425** | 4,536 |
| `DecisionOracle` | 0.8759 | 0.9583 | **0.07504** | 0.00173 | **0.0000** | 1,765 |
| `RepairOracle` | 0.8759 | 0.9583 | **0.07504** | 0.00173 | **0.0000** | 1,765 |

**Verdict: `INCONCLUSIVE_PRECISION`** — the paired ΔAUC CI for
`DecisionOracle − ModuleOracle` is **[−0.0938, +0.0911]**, width 0.185, against
the plan's 0.05 threshold. At 12 seeds the contrast is not resolved either way.

What *is* resolved, and does not depend on the CI:

1. **Granularity works on exactly what it targets.** Decision and Repair reach
   **collateral = 0.0000** against Module's 0.4425, with **2.6x fewer touched
   sites** (1,765 vs 4,536). The plan's `H_D` prediction about collateral holds.
2. **But it does not convert.** Within-module damage is **2.2x higher**
   (0.0750 vs 0.0234, `WMD_rel = −2.212`), and AUC is numerically *lower* than
   both Module and no-correction.

Preflight: `ceiling_risk=True` (`NoCorruption` = 0.9922). Even the clean ceiling
sits at 0.99, so the remaining headroom is small; the run is recorded as
diagnostic rather than confirmatory.

---

## Pilot Beta — what should the update target be?

Granularity fixed at the Alpha winner (`DecisionOracle`). Only the target varies.

| arm | SuccessAUC | final | WMD | collateral | sites |
|---|---:|---:|---:|---:|---:|
| `NoCorrection` | 0.9358 | 1.0000 | 0.00000 | 0.0000 | 0 |
| **`NegativeOnly`** | **0.9410** | **1.0000** | **0.02002** | **0.0000** | 1,707 |
| `PositiveAlternative` | 0.9019 | 0.9583 | 0.12954 | 0.0199 | 2,240 |
| `Contrastive` | 0.9097 | 0.9167 | 0.11758 | 0.0054 | 3,731 |
| `CFRevalue` | **0.8446** | 0.9583 | 0.10002 | 0.0000 | 1,599 |

Primary pre-registered contrast, `Contrastive − NegativeOnly`:

| statistic | value |
|---|---|
| ΔAUC mean | **−0.03125** |
| 95% paired CI | **[−0.05729, −0.00781]** |
| CI width | 0.0495 |
| sign-flip p | 0.1263 |
| Wilcoxon p | 0.125 |
| probability of improvement | **0.000** |

**Verdict: `PRIMARY_NOT_SUPPORTED`.** The plan's hypothesis
`H_B: (bad↓ + good↑) > (bad↓ only)` is **refuted**: adding positive
reinforcement of the verified alternative is *worse* on every axis — AUC down
0.031, WMD **6.5x higher** (0.118 vs 0.020), and 2.2x more sites touched.
`NegativeOnly` alone is the best arm, and the only one that beats
`NoCorrection` on AUC.

### The plan's strong falsification condition fires

The plan states:

> `OracleRepair + CFRevalue <= NoCorrection` → stop the local Q-correction line.

Here `CFRevalue` = **0.8446** against `NoCorrection` = **0.9358**. The strongest
repair — Oracle site, Oracle target, counterfactual-valued — does worse than
making no update at all.

Per the plan's own decision tree the required conclusion is therefore:

> **直接修补 Q-entry 不是合适的 update primitive.**

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
| Pilot Gamma (reward x distribution) | **not run** |
| Pilot Delta (learned `p`, `p_U`) | **not run** |
| candidate ledger, step traces, fixed figures | **not done** |

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
