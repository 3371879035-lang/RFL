# RFL-CausalChase v0.3 — Closeout

> ## Seed-count audit (added after v0.4 showed 12 → 100 seeds can flip results)
>
> The v0.3 pilots ran at **12 / 20 / 8 / 40 / 30 / 8** seeds (Alpha / Beta /
> Gamma / Timing / Stage 4 / Stage 5). That is a real weakness: when the v0.4
> pilots were re-run at 100 seeds, **three of their conclusions changed**,
> including one sign flip.
>
> Two v0.3 pilots have since been re-run at **100 paired seeds**:
>
> | pilot | at original seeds | at 100 seeds | verdict |
> |---|---|---|---|
> | **Pilot Alpha** | ΔAUC +0.00247, CI [−0.00376, +0.01071], p = 0.75 | ΔAUC **+0.00174**, CI **[−0.00008, +0.00398]**, p = 0.094 | **stable** — the null is confirmed with a much tighter CI, and `FinalSuccess Δ = 0.00000` exactly |
> | **Stage 5** | 1 of 6 settings separated | **3 of 6 separate** | **changed** — see below |
>
> **Stage 5 at 100 seeds:**
>
> | setting | horizon | alpha | ΔAUC (Oracle − Traditional) | 95% CI | separates |
> |---|---:|---:|---:|---|---|
> | `base_h8_a10` | 8 | 0.10 | −0.00029 | [−0.00269, +0.00211] | no |
> | `tight_h6_a10` | 6 | 0.10 | **+0.00757** | [+0.00033, +0.01486] | **yes, POSITIVE** |
> | `tight_h5_a10` | 5 | 0.10 | **−0.02673** | [−0.03611, −0.01732] | **yes** (did not separate at 8 seeds) |
> | `base_h8_a03` | 8 | 0.03 | −0.00188 | [−0.00618, +0.00276] | no |
> | `tight_h5_a03` | 5 | 0.03 | **−0.09018** | [−0.10169, −0.07816] | **yes** |
> | `base_h8_a01` | 8 | 0.01 | −0.00647 | [−0.01294, +0.00101] | no (marginal) |
>
> Oracle's innocent-module KnowledgeDamage is **exactly 0.00000 in all six
> settings at 100 seeds**, unchanged.
>
> **The v0.3 Stage 5 verdict below is therefore superseded.** The correct
> statement is not "correct routing never helps and stress reverses it" but:
> **correct routing helps in some regimes (+0.0076 at `tight_h6_a10`) and hurts
> in others (−0.0902 at `tight_h5_a03`); the sign depends on the regime.** The
> 8-seed run saw only the harmful end.
>
> Still at their original seed counts and therefore still exposed: **Gamma (8)**,
> **Stage 4 (30)**, **Beta (20)**, **Timing (40)**. Timing's headline
> (correct credit 1.0 → 0.0, identical across all 40 seeds) and Beta's headline
> (Oracle collateral exactly 0.00000) are *structural* — they cannot move with
> seed count. Gamma's composition effect and Stage 4's marginal p-values
> (0.0215, 0.0295 at 30 seeds) are not, and remain candidates for the same
> treatment.

**Status:** closed. This document is the consolidated conclusion; the evidence
ledger is `docs/RESULTS.md` and the raw artifacts are under `outputs/`.

> **责任归因能减少错误 credit，但责任归因本身不足以定义正确的学习更新。**

---

## 1. The chain, arrow by arrow

The research plan's chain was
`Outcome → Causal/Functional Diagnosis → Learning Responsibility → Update → Learning`.
v0.3 measured each arrow separately.

| arrow | status | decisive evidence |
|---|---|---|
| Outcome → Causal diagnosis | **supported** | Pilot Gamma: sequence evidence alone reaches AUPRC_H 0.67 / AUROC_E 0.65; CF lifts AUPRC_E to 1.00 |
| Causal diagnosis → Learning responsibility | **supported** | Beta: at fixed Oracle `U`, innocent-module KnowledgeDamage is **exactly 0.00000** in every family, every seed; every blunt rule damages it (0.0181–0.1000, p < 0.01) |
| **Learning responsibility → Correct update** | **FAILED** | Stage 5: across 6 difficulty settings, Oracle routing never reliably improved policy utility, and at `horizon=5, alpha=0.03` it was **significantly worse**: ΔAUC **−0.08490**, CI [−0.10188, −0.06823] |
| Update → Task learning | **not established** | All arms end at identical final success in every environment variant tested |

## 2. What is and is not claimed

Supported:

$$\text{correct routing} \Rightarrow \text{fewer wrong updates}$$

**Not** supported:

$$\text{correct routing} \Rightarrow \text{better final learning performance}$$

These were conflated in earlier versions and must stay separate.

## 3. Stage-by-stage verdicts

| stage | verdict | one-line reason |
|---|---|---|
| Pilot Alpha | `BENCHMARK_NO_DISCRIMINATING_POWER` | at `gamma=1`, fixed horizon, no step reward, `+1/−1` and `+1/0` induce the same policy ordering; 9 of 12 seeds give bit-identical curves |
| Pilot Beta | `KNOWLEDGE_PROTECTION_IMPROVES_WITHOUT_POLICY_UTILITY` | Oracle collateral exactly 0; final success identical across all 7 arms |
| Pilot Gamma | `COMPOSITION_EFFECT_CONFIRMED` (with `p_U`) | sequence prior beats a fixed query order at equal CF budget; but see §4 |
| Stage 3 | `REVISION_IS_NET_HARMFUL_UNDER_A_BLIND_CONTRADICTION_RULE` | correct credit 1.0 → 0.0 (p = 0.0000); revision precision 0.167 |
| Stage 4 | `RFL_IMPROVES_CREDIT_WITHOUT_HURTING_UTILITY` | collateral 0.674 → 0.422 vs direct feedback (p = 0.0000), AUC non-inferior |
| Stage 5 | `CORRECT_ROUTING_NEVER_HELPS_AND_STRESS_REVERSES_IT` | 5/6 settings null, 1 significantly negative |

## 4. Three findings that changed the plan

**(a) `p_U` was not conceptual hygiene — it changed the result.** With an
unexplained-cause channel present, one counterfactual query *degrades*
calibration: `AUROC_U` falls 0.6873 → 0.2515 (below chance) and Brier rises
0.1620 → 0.1966, because CF's hypothesis space can only answer H or L and it
answers confidently on causes outside the taxonomy.

**(b) A counterfactual buys calibration, not decisions.** In Stage 4,
`sequence_rfl` and `learned_rfl` are identical to four decimals on every metric
while the latter spends 2,115 extra queries. At K=1 the CF query tests exactly
the hypothesis the sequence prior already ranks first, so it cannot move the
argmax.

**(c) Historical revision needs a replay, not a patch.** `Q ← Q − ΔQ_old`
overshoots: it drives the correct plan's credit to **−2.0** where a true replay
lands at 0.0, and pushes the wrong plan 0.43 lower than it should. 40/40 seeds
agree, Wilcoxon p = 2⁻⁴⁰.

## 5. Architecture comparison (Stage 4 formal, 30 seeds x 5,000 episodes)

| architecture | formula | collateral | AUC |
|---|---|---:|---:|
| Auxiliary penalty | `ΔQ_m = ΔQ_m^task + λ ΔQ_m^diag`, all modules | **0.7081** | 0.7302 |
| Global value + module knowledge | `Score = Q_G + λ_H Q_H` | 0.4383 | 0.7313 |
| **Responsibility-gated** | `ΔQ_m = U_m α δ` | **0.4217** | **0.7336** |
| gated + Oracle | SCM truth | 0.0000 | 0.7338 |

Gating wins. The auxiliary penalty is the worst arm on knowledge damage —
exactly the drawback the plan predicted for it.

## 6. The diagnosis that motivates v0.4

Stage 5's negative result is **not** evidence against learning responsibility.
It localises a defect:

$$\text{knowing \emph{which module} to change} \neq \text{knowing \emph{which entry} to change} \neq \text{knowing \emph{which direction} to change it}$$

The current correction is

$$Q_L(s,a) \leftarrow Q_L(s,a) - \alpha_{\text{diag}}$$

where `a` is merely the **last visited** action. That action may be locally
correct. So a fully correct `U_L = 1` still produces a wrong update.

Oracle's innocent-module KD is always 0, yet it still damages correct
sub-knowledge *inside the responsible module* — and the old `KnowledgeDamage`
metric is blind to this **by construction**, because it only ever looks at the
other module.

That is the concrete question v0.4 must answer.

## 7. What must NOT be added

Per the decision tree, the extensions in the frozen pool (SSP-BO, hippocampal
selective replay, more CF, active evidence, DQN/GRPO) all address *attribution
cost*. Stage 5 shows the bottleneck is not "how to find the cause more cheaply"
but **update semantics**. None of them is indicated.

## 8. Requirement completion

| plan requirement | status |
|---|---|
| core roadmap, pilot → formal scale | done (20 / 40 / 30 seeds) |
| throughput calibration | done (66,607 episodes/s single-process) |
| `p_U` channel | done, with a new finding |
| Random / prevalence baseline | done |
| AUROC / AUPRC / Hamming / exact-set / Brier / ECE / update precision / KD / CF queries / diagnosis ms | done |
| `K_CF ∈ {0,1,2,4}` | done (K=4 saturated, reported) |
| Wilcoxon, probability of improvement | done |
| all three plan architectures compared | done |
| revision ledger with `old_U → new_U` | done |
| per-attribution raw evidence | done (48,000 rows) |
| absorbing-to-horizon, literal | done, with equivalence tests |
| fixed figures | done (4 PNGs) |
| seed-parallel execution | unavailable — sandbox denies named pipes; single-process was sufficient |
| per-episode table, one row per episode | partial — aggregated per seed in `summary.json` |
