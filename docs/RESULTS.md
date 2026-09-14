# RFL-CausalChase v0.3 — Stage 1 results

Statistical unit is the **seed** throughout. Episodes are nested inside seeds and
are never treated as independent samples.

---

## Pilot Alpha — Traditional (+1/−1) vs Positive-only (+1/0)

### Provenance

| item | value |
|---|---|
| commit | `5cb0177` |
| config | `configs/alpha.yaml` |
| environment | 5x2 corridor, horizon 8, gamma 1.0, no step reward, `p_hazard` 0.25, absorbing terminal |
| learning | alpha_L = alpha_H = 0.10, epsilon 0.30 -> 0.05 over the first 80% |
| design | 12 paired seeds (4000000..4000011), 10,000 episodes per arm per seed, greedy eval of 200 episodes every 250 episodes |
| artifacts | `outputs/v03_alpha/{config.yaml,summary.json,analysis.json}` |

Both arms share one `NoiseTape` per seed and differ **only** in the failure
reward: `-1` for Traditional, `0` for Positive-only.

### An invalid first run, recorded

The first full pilot used the low-level state `s_L = (x, y, o)`, omitting the
timestep -- a modelling error, not a tuning issue.

With gamma = 1 and no step reward, a no-op action (WAIT, or UP while already on
lane 0) leaves the state unchanged, so its TD target is `0 + max_a Q(s,a)`, the
value of its *own* state. The Bellman optimality equation is then satisfied for
**any** value: the self-loop inflates `V(s)` and every action that actually
leaves the state is left looking strictly worse.

Observed on that run (seed 4000000, Traditional):

```
s=(0,0,0)   Q=[0.7259, 0.7259, 0.7227, 0.7259]   -> greedy picks UP, a no-op
Q_H         {-1.0, -1.0} for every state and option
FinalSuccess 0.000 for both arms   (400-episode smoke had given 0.725)
```

The greedy policy froze at the start cell and never moved. **That run is not a
result and is not reported as one.** Fixed by `s_L = (x, y, o, t)` with horizon
expiry as a terminal carrying exactly the failure reward; gamma, the step
reward, the action set, and every md fairness constraint are unchanged.
Regression test: `tests/test_runner.py::test_low_level_state_includes_the_timestep`.

### Pre-registered gates

| gate | outcome |
|---|---|
| ceiling | `benchmark_no_discriminating_power` -- `auc_spread` 0.00247 < `min_auc_gap` 0.005 |
| family | `ok` -- smallest realized family 3,663, floor was 400 |
| `saturated_at_ceiling` | `True` -- finals 0.7275 against a realized ceiling of 0.728 |
| process exit code | **2** |

Realized families across 12 seeds per arm:

| family | Traditional | Positive-only |
|---|---:|---:|
| `H_error` | 3,663 | 4,313 |
| `L_error` | 8,459 | 10,422 |
| `HL_error` | 6,844 | 5,184 |
| `E_failure` | 29,830 | 29,830 |

### Paired analysis (unit = seed, 12 pairs)

| endpoint | value |
|---|---|
| AUC delta (Traditional − Positive-only) | **+0.00247** |
| median delta | **0.00000** |
| Cohen d_z | +0.187 |
| paired sign-flip p (10,000 permutations) | **0.7525** |
| 95% paired bootstrap CI | **[−0.00376, +0.01071]** |
| FinalSuccess delta | **0.00000** |
| N(delta < 0), Traditional | 463,810 |
| N(delta < 0), Positive-only | 395,221 |

The CI includes zero and the median delta is exactly zero.

### Verdict

**`BENCHMARK_NO_DISCRIMINATING_POWER`** (the pre-registered ceiling gate fired).

### Reading — two separate claims

**1. The two arms are indistinguishable.** CI includes 0, median delta exactly
0, final success identical to the digit.

**2. This is what the research plan predicts algebraically, not an accident.**
With gamma = 1, no step cost, and every outcome settled at the same horizon,
`E[R_A] = 2P(S) − 1` and `E[R_B] = P(S)` are strictly monotone transforms of the
same success probability, so the *optimal* policy is identical under A and B.
The plan states this and says the A/B difference should then appear only in
learning *dynamics*.

Empirically it does not appear there either, at this resolution: only 3 of 12
seeds show any AUC difference at all (4000002, 4000003, 4000011); the other 9
produce bit-identical curves. Checkpoints every 250 episodes do not resolve the
transient, which is over within roughly the first 250.

Honest summary: **the explicit global failure penalty contributes no measurable
difference in this regime -- neither in the converged policy nor in the learning
trajectory at this checkpoint resolution.** The pre-registered gate cannot
distinguish "treatment inert" from "benchmark saturated", and it fired; that
ambiguity is a limitation of the gate, recorded here rather than resolved by
reinterpretation.

### `N(delta < 0)` confirms the plan's warning

The plan required recording this so that "Positive-only" is never described as
"no negative learning". It is not: mode B still produced **395,221** negative TD
errors. Setting `r_failure = 0` does not stop Q from falling -- it only removes
the extra explicit global penalty.

### What was *not* done

No threshold, `p_hazard`, epsilon schedule, label definition, action set, or
endpoint was changed after seeing these results. The two design changes made
(the timestep in the state; the realized-ceiling correction) were both made
**before** this run and are recorded as X4 and X5 in the implementation plan.

### Implications for the next step

- Per the plan's decision tree, the A/B reward contrast is not where the
  question lives; **Oracle selective correction (Pilot Beta)** is.
- If learning *dynamics* are to be compared at all, checkpoint resolution in the
  transient must be raised (e.g. every 10 episodes for the first 500). That is a
  pre-registerable change, not a post-hoc one.
- Pilot Beta additionally needs `U` gating and knowledge probes, and per the
  plan those probes are defined on **clean reference states** with a verified
  pre-margin -- never on a failure's terminal transition.

---

## Pilot Beta — Penalty x Oracle selective correction

### Provenance

| item | value |
|---|---|
| config | `configs/beta.yaml` |
| environment | identical to Pilot Alpha (5x2, horizon 8, gamma 1.0, no step reward, `p_hazard` 0.25) |
| correction | `dQ_m -= alpha_diag` (=0.10) on the responsible module's chosen action(s); H at `(s_H, option_chosen)`, L at every low-level transition of the episode |
| design | 8 paired seeds (4100000..4100007), 12,000 episodes per condition, greedy eval of 200 episodes every 250 |
| conditions | the 2x2 `{traditional, positive_only} x {none, oracle}` plus blunt `h_only`, `l_only`, `hl` |
| artifacts | `outputs/v03_beta/{config.yaml,summary.json,analysis.json,run.log}` |
| process exit | **0** (both fatal gates pass) |

**Episode count was raised from the plan's 2,000 to 12,000.** D6 pre-registers
exactly this remedy. It was forced by the treatment itself: 2,000 episodes
cannot deliver the plan's own ">= 400-500 effective failures per scene" floor,
and the Oracle arms cut failures *further* by learning better, so `HL_error` in
`positive_only_oracle` fell to 337 pooled events. No threshold, `p_hazard`,
epsilon value, or label definition was touched. At 12,000 episodes the floor is
met in every family of every condition.

### KnowledgeDamage on the correct-but-not-responsible module

Mean absolute margin loss per diagnostic event. `HL_error` has no innocent
module by construction, so its column is undefined.

| family (innocent module) | traditional | positive_only | T+Oracle | PO+Oracle | h_only | l_only | hl |
|---|---:|---:|---:|---:|---:|---:|---:|
| `H_error` (L) | 0.00000 | 0.00000 | **0.00000** | **0.00000** | 0.00000 | 0.04072 | 0.04020 |
| `L_error` (H) | 0.00000 | 0.00000 | **0.00000** | **0.00000** | 0.10000 | 0.00000 | 0.10000 |
| `E_failure` (both) | 0.00000 | 0.00000 | **0.00000** | **0.00000** | 0.02502 | 0.01923 | 0.04382 |

### Paired contrasts (unit = seed, 8 pairs)

**Knowledge damage**

| family | contrast | mean | 95% CI | p |
|---|---|---:|---|---:|
| `H_error` | `l_only` − `traditional` | **+0.04046** | [+0.03357, +0.04697] | 0.0079 |
| `H_error` | `hl` − `traditional` | **+0.04030** | [+0.03592, +0.04526] | 0.0079 |
| `L_error` | `h_only` − `traditional` | **+0.10000** | [+0.10000, +0.10000] | 0.0077 |
| `L_error` | `hl` − `traditional` | **+0.10000** | [+0.10000, +0.10000] | 0.0080 |
| `E_failure` | `h_only` − `traditional` | **+0.02502** | [+0.02485, +0.02522] | 0.0085 |
| `E_failure` | `l_only` − `traditional` | **+0.01923** | [+0.01709, +0.02065] | 0.0068 |
| `E_failure` | `hl` − `traditional` | **+0.04381** | [+0.04263, +0.04513] | 0.0082 |
| all | any **Oracle** − its counterpart | **0.00000** | [0, 0] | 1.0000 |

Every blunt rule damages knowledge it had no business touching, at p < 0.01.
Both Oracle arms score **exactly zero** in every family: they do not damage the
innocent module even once.

**Policy utility (SuccessAUC)**

| contrast | mean | 95% CI | d_z | p |
|---|---:|---|---:|---:|
| `T+Oracle` − `traditional` | **+0.00000** | [0, 0] | 0.000 | 1.0000 |
| `PO+Oracle` − `positive_only` | +0.00237 | [+0.00036, +0.00495] | +0.651 | 0.2483 |
| `h_only` − `traditional` | −0.00210 | [−0.00487, 0] | −0.535 | 0.4954 |
| `l_only` − `traditional` | −0.00079 | [−0.00238, 0] | −0.354 | 1.0000 |
| `hl` − `traditional` | −0.00490 | [−0.00974, −0.00099] | −0.683 | 0.2478 |

Penalty x Oracle interaction, `(PO+O − PO) − (T+O − T)`: **+0.00237**
[+0.00036, +0.00495]. The CI excludes zero, but the magnitude is ~0.002 on a
~0.75 AUC, it is uncorrected for multiplicity, and it rests on 8 seeds; it is
reported as negligible rather than as a finding.

### Gates

| gate | role | outcome |
|---|---|---|
| `family_gate` | **fatal** | `ok` — floor of 400 met in every family of every condition |
| `oracle_advantage` | **fatal** | **True** |
| `auc_check` | secondary, not fatal | `benchmark_no_discriminating_power` — spread 0.00490 < 0.005 |

`oracle_advantage` is true **only through `E_failure`** (gap 0.0192 over the
closest blunt rule). In `H_error` and `L_error` the Oracle arms tie with
`h_only` and `l_only` respectively, at gap exactly 0, because in those families
that blunt rule happens to target the module that really was responsible. The
structural advantage appears precisely in the genuinely ambiguous family, where
*no* module is responsible and every blunt rule therefore fires on an innocent
one.

### Verdict

**`KNOWLEDGE_PROTECTION_IMPROVES_WITHOUT_POLICY_UTILITY`** — one of the valid
outcomes the research plan names in advance.

### Reading

1. **Selective correction works as designed, and the effect is structural, not
   marginal.** Oracle never damages the innocent module (0.00000 in every
   family, every seed); every blunt rule does, significantly.
2. **It buys nothing in task performance at this scale.** All seven conditions
   end at *identical* final success (0.7575), and the AUC spread is 0.005 —
   statistically indistinguishable. `T+Oracle − traditional` is exactly 0.
3. **The reason is visible in the run, and it is the one the plan's decision
   tree predicts** ("knowledge protection improves but return does not"): the
   task is learned so fast, and its damage repaired so fast, that collateral
   knowledge loss never survives long enough to change the policy. Ordinary RL
   re-learns the damaged values before the next evaluation checkpoint.
4. Corroborating evidence: the Oracle arms also produce **fewer failures**
   during training (31.0k-32.6k diagnostic events vs 37.5k-40.8k) and about
   **6x fewer `HL_error`s** (524-603 vs 3245-4915). Selective correction does
   change the learning trajectory — it just does not change where it lands.

### What this implies

- The plan's precondition for Pilot Gamma **is met** (Oracle shows a structural
  advantage in an ambiguous scene), so Gamma is permitted.
- But the binding constraint is now the *benchmark*, not the attributor: this
  task cannot express a utility benefit because it self-repairs too quickly. A
  utility effect would need a task where damage persists — longer horizons,
  less redundant paths, or a utility endpoint measured before recovery.
- No threshold, `p_hazard`, epsilon, label definition, or endpoint was changed
  after seeing these results. The only change was episode count, per D6, and it
  was made to satisfy a pre-registered power floor.

---

## Pilot Gamma — Sequence evidence x counterfactual verification

### Provenance

| item | value |
|---|---|
| config | `configs/gamma.yaml` |
| data | 8 seeds (4200000..4200007), 8,000 balanced offline traces per seed, 4,000 train / 4,000 test |
| families | exactly balanced by construction: 2,000 per family per seed |
| budgets | K in {1, 2} |
| artifacts | `outputs/v03_gamma/{config.yaml,summary.json}` |
| process exit | **0** — the pre-registered composition test passes |

### What the diagnoser is allowed to see

Only what a learner could see: the sequence of low-level `(state, action)` pairs,
the chosen `option`, and the terminal kind. **Not** `goal_lane`, **not**
`hazard`; both are recorded evaluator-side only.

That leaves one irreducible ambiguity, verified by test
(`test_stalled_and_jammed_are_observationally_identical`): when the agent times
out *without* reaching the end of its corridor, a stalled execution and a jammed
gate are byte-identical in the action sequence.

### Pareto: verification cost vs attribution quality

| method | CF queries | Brier | update prec. | collateral | exp. KD | AUPRC_H | AUPRC_L | AUPRC_E |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `oracle` | 0.00 | 0.0000 | 1.0000 | 0.0000 | 0.00000 | 1.0000 | 1.0000 | 1.0000 |
| `sequence_only` | 0.00 | 0.1659 | 0.8007 | 0.1993 | 0.01993 | 0.7161 | 0.8030 | 0.5022 |
| **`seq_then_cf_k1`** | **1.00** | **0.1447** | 0.8007 | 0.1993 | 0.01993 | **0.8777** | 0.9359 | **0.8134** |
| `cf_only_k1` | 1.00 | 0.1573 | 0.8007 | 0.1993 | 0.01993 | 0.7824 | 0.9359 | 0.5292 |
| **`seq_then_cf_k2`** | **1.50** | **0.0845** | **1.0000** | **0.0000** | **0.00000** | 1.0000 | 0.8227 | 1.0000 |
| `cf_only_k2` | 1.75 | 0.0845 | 1.0000 | 0.0000 | 0.00000 | 1.0000 | 0.8227 | 1.0000 |

### Findings

1. **The composition effect is real at equal budget.** At exactly 1.00 query,
   `seq_then_cf` beats the fixed order on Brier, **0.1447 vs 0.1573**
   (delta **−0.0127**, lower is better). The gain is concentrated where the
   ambiguity lives: `AUPRC_E` **0.8134 vs 0.5292 (+0.284)**, and `AUPRC_H`
   +0.095. The prior does not merely reshuffle a budget — it picks the *right*
   query.

2. **The prior buys a genuine budget reduction.** `seq_then_cf_k2` matches
   `cf_only_k2` on every quality axis (Brier 0.0845, precision 1.0000,
   collateral 0.0000) while using **1.50 vs 1.75** queries — a **14% saving at
   identical attribution quality**. This is precisely the claim the research
   plan wanted tested ("在相同 downstream quality 下，减少了多少反事实查询").

3. **One well-chosen query does not replace two.** `seq_then_cf_k1` (0.1447) is
   far behind `cf_only_k2` (0.0845). The budget can be trimmed, not halved.

4. **Counterfactuals earn their cost specifically on the environment cause.**
   `AUPRC_E` climbs 0.5022 -> 0.8134 -> 1.0000 across 0, 1, 2 queries, while
   `AUPRC_L` is already 0.8030 from the sequence alone. This is exactly the
   predicted division of labour: cheap observational evidence handles what is
   visible, verification resolves what is latent.

5. **Two queries eliminate downstream collateral damage entirely.** Update
   precision goes 0.8007 -> **1.0000** and collateral rate 0.1993 -> **0.0000**,
   so expected knowledge damage falls to **0.00000** — the same figure the
   Oracle reaches. This links Gamma to Pilot Beta's KnowledgeDamage directly.

6. **A limitation worth stating: `AUPRC_L` never reaches 1.0** (0.8227 even at
   K=2, versus 1.0000 for Oracle). Counterfactual verification here tests
   single-module *sufficiency*: in an `HL_error` both modules are responsible,
   so repairing either one alone does not flip the outcome and CF credits only
   H. Concurrent faults are systematically under-detected. This is a property of
   sufficiency-based CF, not a tuning issue.

### Verdict

**`COMPOSITION_EFFECT_CONFIRMED`** — sequence evidence makes counterfactual
verification cheaper at matched quality, and the saving is largest on the cause
that is invisible to observation alone.

### Defect found and fixed during this pilot

The sequence model originally stored its likelihood tuple as
`(log p1, log(1-p1))` while indexing it with the binary feature value, which
**reads every feature inverted**: `reached_end = 1` looked up `log P(f = 0)`.
A jammed gate consequently scored as an execution failure (`L = 0.72`). Caught
by `test_sequence_model_separates_the_observable_cases`, fixed, and locked with
`test_likelihood_indexing_is_not_inverted`.

A second defect: `generate_balanced` filled families at different rates, so a
naive head/tail split was badly imbalanced (E_failure 192 vs H_error 132 in a
600-trace training half). Fixed by shuffling deterministically before returning.

---

## Stage 3 — attribution timing x historical revision

### Provenance

| item | value |
|---|---|
| config | `configs/timing.yaml` |
| env | extended with a **lucky shortcut** (`lucky=1` opens the exit on the other lane), the only exogenous cause of *unearned success*; `hazard` remains the only exogenous cause of failure |
| design | 12 paired seeds (4300000..4300011); 200 warmup + 120 lucky + 12 contradiction episodes; every 4th contradiction episode is an unlucky failure |
| cells | `{immediate, deferred} x {fixed, revisable}` |
| artifacts | `outputs/v03_timing/{config.yaml,summary.json}` |
| process exit | **2** — the pre-registered "revisable beats fixed" test does **not** pass |

### The protocols, stated plainly

* **Lucky success**: the agent is made to run a *wrong* plan while `lucky=1`, so
  it succeeds. Ordinary reinforcement credits the wrong plan.
* **Contradiction**: the same wrong plan, no luck, fails.
* **Unlucky failure**: the *correct* plan fails because `hazard=1`, while the
  same plan normally succeeds.
* **Revision rule** (identical in both revisable cells, deliberately blind):
  on a contradiction, withdraw the outcome evidence of every earlier success of
  the same plan, by restoring a checkpoint and replaying the ledger forward --
  never by `Q <- Q - dQ_old + dQ_new`.

### Results

| cell | overcredit after lucky | overcredit after contradiction | **correct credit after contradiction** | recovery | revision precision | false reversals |
|---|---:|---:|---:|---:|---:|---:|
| `immediate_fixed` | 1.0000 | −0.8377 | **1.0000** | 1.00 | — | 0 |
| `immediate_revisable` | 1.0000 | −0.8377 | **0.0000** | 1.00 | 0.1667 | 720 |
| `deferred_fixed` | 1.0000 | −0.7876 | **1.0000** | 1.00 | — | 0 |
| `deferred_revisable` | 1.0000 | −0.7876 | **0.0000** | 1.00 | 0.1667 | 720 |

Paired contrasts (12 seeds). `overcredit` = Q of the wrong plan (lower better);
`correct credit` = Q of the right plan (higher better).

| contrast | metric | mean | 95% CI | p |
|---|---|---:|---|---:|
| `immediate_revisable` − `immediate_fixed` | overcredit | **+0.00000** | [0, 0] | 1.0000 |
| `immediate_revisable` − `immediate_fixed` | **correct credit** | **−1.00000** | [−1, −1] | **0.0004** |
| `immediate_revisable` − `immediate_fixed` | recovery episodes | +0.00000 | [0, 0] | 1.0000 |
| `deferred_fixed` − `immediate_fixed` | overcredit | **+0.05009** | [+0.05009, +0.05009] | **0.0006** |
| `deferred_fixed` − `immediate_fixed` | correct credit | +0.00000 | [0, 0] | 1.0000 |

### Verdict

**`REVISION_IS_NET_HARMFUL_UNDER_A_BLIND_CONTRADICTION_RULE`**

### Reading

1. **Revisable credit destroyed the correct plan's credit completely** — Q(right
   plan) fell from 1.0000 to 0.0000, Δ = −1.0, p = 0.0004 — while producing
   **exactly zero** reduction in the wrong plan's overcredit.

2. **Why it could not help.** Task RL already drives the wrong plan's value down
   within a single episode: `recovery_episodes = 1` in *every* cell. By the time
   a contradiction is confirmed there is no overcredit left to remove — but
   plenty of correct credit to destroy.

3. **The revision rule had no luck-detector.** It withdrew evidence from every
   earlier success of the same plan, and could not tell an unearned success from
   an earned one. Only **1 in 6** revisions was justified
   (`revision_precision = 0.1667`); `false_reversal_rate = 0.8333`. This is
   precisely the failure the research plan asked to test for, and it occurs.

4. **Deferral is simply weaker, not "slower but eventually better".** Deferred
   cells diagnose less (10 vs 12 events) and end with *more* residual overcredit
   (+0.050, p = 0.0006) with no compensating gain on correct credit. It defers
   without acquiring any new information, so the delay buys nothing.

5. **Conclusion that connects the stages:** revision is only viable *on top of*
   a working attributor. The blind rule failed because it could not distinguish
   lucky from earned success — which is exactly the discrimination Pilot Gamma's
   sequence + counterfactual machinery provides. Stage 3 as specified is not a
   standalone improvement; it is a consumer of Stage 2.

### Protocol note (recorded, not hidden)

The first run of this experiment used 120 contradiction episodes and was
**degenerate**: all four cells produced numerically identical overcredit
(−2.000 for the immediate pair), because a long contradiction phase drives
Q(wrong) to the same fixed point regardless of what the revision did. The
revision effect was washed out before measurement. The phase was shortened to
12 episodes so the revision is measured before it is overwritten — a
measurement-window change, not a change to any threshold, label, or endpoint.
The degenerate run is not reported as a result.

---

## Stage 4 — end-to-end Q-learning with attribution in the loop

### Provenance

| item | value |
|---|---|
| config | `configs/stage4.yaml` |
| design | 20 paired seeds (4400000..4400019), 3,000 episodes per arm per seed, greedy eval of 100 episodes every 250 |
| feedback | the environment emits a diagnostic label that is **wrong with probability 0.40**; the outcome reward is never falsified, only the explanation attached to it |
| attributor | sequence model pretrained offline on 1,000 generated traces and frozen |
| artifacts | `outputs/v03_stage4/{config.yaml,summary.json,run.log}` |
| process exit | **0** — both gates pass |

### Pooled by arm

| arm | success AUC | final success | collateral rate | update precision | exp. knowledge damage | corrections | CF queries |
|---|---:|---:|---:|---:|---:|---:|---:|
| `traditional` | 0.7308 | 0.7610 | — | — | 0.00000 | 0 | 0 |
| `positive_only` | 0.7316 | 0.7610 | — | — | 0.00000 | 0 | 0 |
| `direct_feedback` | 0.7232 | 0.7610 | **0.6427** | 0.3573 | 0.06427 | 1,175 | 0 |
| `sequence_rfl` | 0.7316 | 0.7610 | **0.3807** | 0.6193 | 0.03807 | 776 | 0 |
| `learned_rfl` | 0.7316 | 0.7610 | **0.3807** | 0.6193 | 0.03807 | 776 | 1,319 |
| `oracle_rfl` | 0.7313 | 0.7610 | **0.0000** | 1.0000 | 0.00000 | 526 | 0 |

`collateral rate` = share of diagnostic corrections that targeted a module the
SCM says was **not** responsible.

### Paired contrasts (20 seeds)

**Utility, vs `traditional`**

| arm | ΔAUC | 95% CI | p |
|---|---:|---|---:|
| `direct_feedback` | **−0.00754** | [−0.01775, +0.00008] | 0.1925 |
| `sequence_rfl` | +0.00088 | [+0.00000, +0.00263] | 1.0000 |
| `learned_rfl` | +0.00088 | [+0.00000, +0.00263] | 1.0000 |
| `oracle_rfl` | +0.00054 | [−0.00100, +0.00263] | 1.0000 |

**Knowledge damage, vs `direct_feedback`** (the only other arm that corrects)

| arm | Δcollateral | 95% CI | p | Δprecision |
|---|---:|---|---:|---:|
| `sequence_rfl` | **−0.26204** | [−0.29126, −0.23091] | **0.0000** | +0.26204 |
| `learned_rfl` | **−0.26204** | [−0.29159, −0.23128] | **0.0000** | +0.26204 |
| `oracle_rfl` | **−0.64269** | [−0.65649, −0.62831] | **0.0000** | +0.64269 |

### Gates

| gate | outcome |
|---|---|
| `learned_rfl` non-inferior on AUC vs `traditional` (margin 0.02) | **True** |
| `learned_rfl` reduces knowledge damage vs `direct_feedback` | **True** |

### Verdict

**`RFL_IMPROVES_CREDIT_WITHOUT_HURTING_UTILITY`** — a valid outcome the research
plan names in advance.

### Reading

1. **Trusting the diagnostic label is the worst option available.**
   `direct_feedback` lands at **64.3%** collateral — *worse* than the 40% label
   error rate, because it also corrects on environment-caused failures where
   neither module is responsible. It is also the **only** arm whose task
   utility is numerically hurt (ΔAUC −0.0075).

2. **Verification cuts wrong-module updates by 41%**: collateral 0.6427 ->
   0.3807, a paired effect of **−0.262** with CI [−0.291, −0.231], p = 0.0000.
   Update precision rises 0.3573 -> 0.6193. Expected knowledge damage falls
   0.0643 -> 0.0381.

3. **The Oracle upper bound is qualitatively different**, not just better:
   collateral **exactly 0.0000** and precision **1.0000**. It also corrects less
   often (526 vs 776), so the honest gap between learned and oracle RFL is
   concentrated in *how often* the learner commits an update at all.

4. **The counterfactual component added exactly nothing online.** `sequence_rfl`
   and `learned_rfl` are identical to four decimals on every metric — collateral
   0.3807, precision 0.6193, AUC 0.7316 — while `learned_rfl` spent **1,319 extra
   CF queries**. This is the plan's "Core-RFL minus one component" ablation, and
   it says the component is dispensable *in this loop*. The reason is visible in
   `attribute_seq_then_cf`: at K=1 it tests precisely the hypothesis the sequence
   prior already ranks first, so it can change the *probability* but not the
   *argmax*. Gamma showed the same thing from the other side — at K=1 CF improved
   AUPRC and Brier (calibration) while the top-1 decision was already made by the
   prior. **Across both pilots, CF buys calibration, not decisions.**

5. **No arm changes task performance.** Final success is identical at 0.7610 for
   all six arms and AUCs sit within 0.008. Consistent with Alpha and Beta: this
   benchmark cannot express a utility difference.

### Gate correction, recorded

The first run of this stage exited 3 on a gate that was **ill-posed**. It
compared `learned_rfl`'s collateral against `traditional`, which makes *zero*
corrections and therefore has no collateral at all — the contrast cannot exist,
so the gate could never pass. Utility is now judged against `traditional` and
knowledge damage against `direct_feedback`, the arm that actually acts on the
label. The first run's numbers were unchanged; only the comparison was fixed.

---

## Stage 5 — difficulty sweep: does correct routing ever convert to utility?

Every earlier stage located its effect in credit or knowledge and never in policy
utility. The research plan's decision tree anticipates exactly this ("knowledge
protection improves but return does not") and directs a check of whether the
benchmark is too easy, i.e. whether ordinary RL repairs the damage too quickly.

This sweeps the two things that govern repair speed and task slack — `horizon`
(5 is exactly enough for the longer lane: zero slack) and `alpha` (how fast
ordinary RL re-learns a damaged value) — and asks at each setting whether the
paired task-AUC difference between Oracle selective correction and Traditional
ever separates from zero.

### Provenance

| item | value |
|---|---|
| config | `configs/stage5.yaml` |
| design | 8 paired seeds (4500000..4500007), 2,000 episodes per arm per setting, 6 settings |
| arms | `traditional` vs `traditional_oracle` |
| artifacts | `outputs/v03_stage5/{config.yaml,summary.json}` |
| process exit | **0** — but read the sign |

### Results

| setting | horizon | alpha | traditional AUC | Oracle AUC | ΔAUC | 95% CI | separates | Oracle KD |
|---|---:|---:|---:|---:|---:|---|---:|---:|
| `base_h8_a10` | 8 | 0.10 | 0.7051 | 0.7112 | +0.00615 | [+0.00000, +0.01844] | no | 0.00000 |
| `tight_h6_a10` | 6 | 0.10 | 0.6915 | 0.7035 | +0.01198 | [−0.00260, +0.02782] | no | 0.00000 |
| `tight_h5_a10` | 5 | 0.10 | 0.6642 | 0.6436 | −0.02052 | [−0.05823, +0.02042] | no | 0.00000 |
| `base_h8_a03` | 8 | 0.03 | 0.7112 | 0.7112 | **+0.00000** | [+0.00000, +0.00000] | no | 0.00000 |
| **`tight_h5_a03`** | **5** | **0.03** | **0.6576** | **0.5727** | **−0.08490** | **[−0.10188, −0.06823]** | **yes** | 0.00000 |
| `base_h8_a01` | 8 | 0.01 | 0.7112 | 0.7055 | −0.00573 | [−0.01719, +0.00000] | no | 0.00000 |

### Verdict

**`CORRECT_ROUTING_NEVER_HELPS_AND_STRESS_REVERSES_IT`**

### Reading

1. **Nowhere does correct responsibility routing improve task performance.**
   Five of six settings fail to separate. The one that does separates the wrong
   way: at a tight horizon with slow learning, Oracle selective correction is
   **significantly worse** — ΔAUC **−0.08490**, CI [−0.10188, −0.06823].

2. **The knowledge-protection benefit is real but never converts.** Oracle's
   knowledge damage is **exactly 0.00000** in every setting, as established in
   Pilot Beta — and it buys nothing on the task. The channel from "protect
   knowledge" to "behave better" is empty in this environment family.

3. **Why the correction hurts, and why `KnowledgeDamage` cannot see it.** The
   diagnostic update only ever *subtracts*. Oracle never touches the innocent
   module, so its KD is zero — but in an `L_error` it pushes down `Q_L` at the
   last visited `(s, a)`, which is not necessarily a wrong action. That damages
   the *responsible* module's own correct sub-knowledge, which the
   innocent-module KD metric is blind to by construction. Under slow learning
   (`alpha = 0.03`) the accumulated downward pressure cannot be repaired, and at
   `horizon = 5` there is no slack to absorb it.

4. **Repair speed is the moderator, and it confirms the plan's suspicion.** At
   `alpha = 0.10` the same tight task shows no harm (−0.021, CI includes 0)
   because ordinary RL repairs the damage between checkpoints. Slow the repair
   by 3x and the identical correction becomes significantly harmful. The
   benchmark was not "too easy" in the sense of being solved; it was too *fast
   at healing*, exactly the branch the decision tree flagged.

5. **Consequence for the programme.** The plan's precondition for the extension
   mechanisms — "ordinary RL repairs the error quickly" — is now confirmed as
   the binding constraint, and the extensions in the frozen pool (selective
   replay, SSP-BO, active evidence) all address *attribution cost*, not the
   repair channel. None of them is indicated by this result. What this result
   indicates is that the **diagnostic update rule itself** is the problem: a
   correlate that only ever subtracts from a module cannot be rescued by making
   attribution more accurate.

### Defect found and fixed during this sweep

`run_episode` iterated over the module constant `HORIZON = 8` instead of
`tape.horizon`, so a configured horizon other than 8 indexed past the end of the
tape and crashed. Every earlier experiment used horizon 8, which is why it never
surfaced, and **no earlier result is affected**. Fixed by taking the span from
the tape, and locked with
`test_horizon_comes_from_the_tape_not_the_module_constant` plus a
short-horizon reachability test.

---

# Formal-scale reruns, the `p_U` channel, and remaining requirements

## Throughput calibration (run before committing to any budget)

| item | value |
|---|---|
| measured | 10,000 baseline episodes at horizon 8 |
| single process | **66,607 episodes/s** |
| parallel (21 workers) | **unavailable** — `BrokenProcessPool`; multiprocessing needs named pipes, which this sandbox denies |
| artifacts | `outputs/v03_reproducibility/benchmark.json` |

Parallel measurement was not worked around. Formal scale is therefore affordable
single-process, which is why every formal run below was executed.

## Formal-scale reruns

### Pilot Beta — 20 seeds x 7 conditions x 5,000 episodes (exit **0**)

All gates pass. The pilot's conclusions hold with tighter CIs:

| family (innocent module) | traditional | PO | T+Oracle | PO+Oracle | h_only | l_only | hl |
|---|---:|---:|---:|---:|---:|---:|---:|
| `H_error` (L) | 0 | 0 | **0.00000** | **0.00000** | 0 | 0.04281 | 0.04327 |
| `L_error` (H) | 0 | 0 | **0.00000** | **0.00000** | 0.10000 | 0 | 0.10000 |
| `E_failure` (both) | 0 | 0 | **0.00000** | **0.00000** | 0.02500 | 0.01813 | 0.04367 |

`family_gate = ok`, `auc_check = ok`, `oracle_advantage = True`.
Artifacts: `outputs/v03_beta_formal/`.

### Stage 3 — 40 seeds x 4 cells (exit **2**)

The pilot's verdict is unchanged and now much sharper:

| contrast | metric | mean | 95% CI | p |
|---|---|---:|---|---:|
| `immediate_revisable` − `immediate_fixed` | overcredit | +0.00000 | [0, 0] | 1.0000 |
| `immediate_revisable` − `immediate_fixed` | **correct credit** | **−1.00000** | [−1, −1] | **0.0000** |
| `deferred_fixed` − `immediate_fixed` | overcredit | +0.05009 | [+0.05009, +0.05009] | **0.0000** |

At 40 seeds the false-reversal harm reaches **p = 0.0000** (was 0.0004 at 12).
Artifacts: `outputs/v03_timing_formal/`.

### Stage 4 — 30 seeds x 7 arms x 5,000 episodes (exit **0**)

| arm | success AUC | final | collateral | update precision | exp. KD | corrections | CF |
|---|---:|---:|---:|---:|---:|---:|---:|
| `traditional` | 0.7337 | 0.7522 | — | — | 0.00000 | 0 | 0 |
| `positive_only` | 0.7308 | 0.7522 | — | — | 0.00000 | 0 | 0 |
| `direct_feedback` | 0.7274 | 0.7522 | 0.6735 | 0.3265 | 0.06735 | 1,872 | 0 |
| **`random_correction`** | 0.7321 | 0.7522 | **0.7298** | 0.2702 | 0.07298 | 1,432 | 0 |
| `sequence_rfl` | 0.7336 | 0.7522 | 0.4217 | 0.5783 | 0.04217 | 1,187 | 0 |
| `learned_rfl` | 0.7336 | 0.7522 | 0.4217 | 0.5783 | 0.04217 | 1,187 | 2,115 |
| `oracle_rfl` | 0.7338 | 0.7522 | **0.0000** | 1.0000 | 0.00000 | 978 | 0 |

Paired vs `traditional` on AUC: `positive_only` **−0.00293** (p=0.0295),
`direct_feedback` **−0.00630** (p=0.0215), `random_correction` −0.00156 (p=0.4069),
`sequence_rfl` and `learned_rfl` **−0.00011** (p=1.0000), `oracle_rfl` +0.00011.

**This is sharper than the pilot.** At 30 seeds, *both* unverified correction
strategies are now significantly **worse** than doing nothing, while the two RFL
arms are exactly non-inferior. RFL is the only arm that corrects without paying
for it.

The Random/prevalence baseline lands **below** `direct_feedback`
(collateral 0.7298 vs 0.6735), which is not a bug: online, `H_error` is rare
(~5% of failures), so an uninformed "pick H" is usually wrong. That is precisely
what a lower bound should look like.
Artifacts: `outputs/v03_stage4_formal/`.

## `p_U`: the unexplained-cause channel

The plan requires `p = (p_H, p_L, p_E, p_U)` so the system can decline to
attribute rather than being forced into H/L/E. Implemented as a fifth failure
family: **correct plan, correct execution, no gate hazard, but an unmodelled
blockage on the agent's own corridor.** The cause is genuinely outside the
taxonomy, and `truth_scores` now returns a four-way multi-label vector.

Adding it changed the Gamma conclusions materially:

| method | CF | Brier | Hamming | exact-set | ECE | AUROC_E | **AUROC_U** | ms/trace |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `oracle` | 0.00 | 0.0000 | 0.0000 | 1.0000 | 0.0000 | 1.0000 | 1.0000 | 0.001 |
| `sequence_only` | 0.00 | **0.1620** | 0.2248 | 0.4507 | **0.0546** | 0.6537 | **0.6873** | 0.004 |
| `seq_then_cf_k1` | 1.00 | 0.1966 | 0.2248 | 0.4507 | 0.1903 | 0.9375 | 0.2515 | 0.011 |
| `cf_only_k1` | 1.00 | 0.2044 | 0.2248 | 0.4507 | 0.2001 | 0.7795 | 0.1258 | 0.008 |
| `seq_then_cf_k2` | 1.40 | 0.1498 | 0.1498 | 0.6006 | 0.1498 | 1.0000 | 0.5000 | 0.010 |
| `seq_then_cf_k4` | 1.40 | 0.1498 | 0.1498 | 0.6006 | 0.1498 | 1.0000 | 0.5000 | 0.010 |
| `cf_only_k2` | 1.60 | 0.1498 | 0.1498 | 0.6006 | 0.1498 | 1.0000 | 0.5000 | 0.007 |
| `cf_only_k4` | 1.60 | 0.1498 | 0.1498 | 0.6006 | 0.1498 | 1.0000 | 0.5000 | 0.007 |

1. **A single counterfactual now makes calibration worse, not better.** With no
   unexplained channel, one CF query improved Brier. With `p_U` present,
   `sequence_only` (0.1620) **beats** `seq_then_cf_k1` (0.1966), and ECE degrades
   0.0546 -> 0.1903. The reason is visible in `AUROC_U`: sequence evidence
   detects the unexplained family at **0.6873**, while one CF query drops it to
   **0.2515** — below chance. CF answers one-hot, and on an unexplained failure
   its one-hot answer is confidently wrong.

2. **This is the blind spot, now measured rather than asserted.**
   Counterfactuals test single-module *sufficiency*, so they can only ever
   conclude "H" or "L"; they have no way to output "unexplained". `AUPRC_L`
   correspondingly collapses from 0.8227 to 0.4707, because the unknown family
   gets blamed on the low level.

3. **K=4 saturates at K=2**, exactly and on every metric, at 1.40/1.60 queries.
   This design has only two distinct counterfactual hypotheses, so budget beyond
   2 buys nothing. Reported, not papered over.

4. **Diagnosis cost is negligible**: 0.001-0.011 ms per trace, so the CF-query
   count in the Pareto column — not wall time — is the real budget.

5. The K=1 composition effect survives the new family:
   `seq_then_cf_k1` 0.1966 vs `cf_only_k1` 0.2044 at an identical 1.00 query.

## Figures

Four fixed figures are produced by `scripts/make_figures.py` from the artifacts
already on disk (no analytical logic in the plotting step):
`alpha_success_curves.png`, `gamma_pareto.png`, `beta_knowledge_damage.png`,
`stage5_difficulty_sweep.png`, in `outputs/v03_figures/`.

## Requirement status after this pass

| previously missing | status |
|---|---|
| throughput calibration | **done** (66,607 ep/s single-process) |
| formal scale for Beta / Stage 3 / Stage 4 | **done** (20 / 40 / 30 seeds) |
| `p_U` and an unknown-cause family | **done**, with a new finding |
| Random / prevalence baseline | **done** (Stage 4 `random_correction`) |
| AUROC, Hamming, exact-set, ECE, diagnosis ms | **done** |
| `K_CF in {0,1,2,4}` | **done**, K=4 reported as saturated |
| fixed figures | **done** (4 PNGs) |
| absorbing-to-horizon, literal | **not done** — equivalent under gamma=1 with no step reward, but not literally implemented |
| per-attribution raw evidence serialized | **not done** |
| revision ledger `old_U -> new_U` schema | **not done** |






