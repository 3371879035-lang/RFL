# RFL-CausalChase v0.4 — Credit-unit and Repair Semantics

**Status:** active spec, supersedes
`docs/superpowers/specs/2026-09-01-rfl-v04-update-semantics-design.md`
(`SUPERSEDED_BY_V04_CREDIT_REPAIR_SPEC`).

**Origin:** Stage 5's negative result. With `U` fixed at the SCM truth, Oracle
routing never reliably improved policy utility in any of six difficulty
settings, and at `horizon=5, alpha=0.03` it was significantly worse
(ΔAUC −0.08490, CI [−0.10188, −0.06823]). That is not evidence against learning
responsibility; it localises a defect downstream of it.

**What changes relative to the superseded draft.** The draft kept the H/L
module responsibility `U_m` as the ontology and added `Update site` / `Update
direction` beneath it. That is still an assumption that *the module is the unit
of credit*. v0.4 moves one layer further out and makes the unit itself the
experimental variable:

```
Outcome -> CreditUnit -> CandidateRepairs -> RepairSelection -> Update -> Learning
```

`U_m` is **demoted from axiom to candidate representation** — one candidate
among several, and a losing one if the data says so. Failure families are
defined by **intervention**, never by label.

---

## 1. The defect, restated without assuming modules

v0.3's diagnostic correction is a single rule:

$$Q_m(s,a) \leftarrow Q_m(s,a) - \alpha_{\text{diag}} \quad\text{where } (s,a) \text{ is the last visited entry of module } m$$

Two independent things are wrong with it, and v0.3 could not separate them:

1. **The site is arbitrary.** In an `L_error` the last visited action may be
   locally correct. `U_L = 1` says "the low level went wrong somewhere"; it does
   not say *where*.
2. **The direction is fixed and monotone.** The update only ever subtracts. It
   cannot raise a value, and it is not a TD target — it is an arbitrary push of
   magnitude `alpha_diag`.

So a perfectly correct `U_m` still produces a wrong update:

$$\text{knowing \emph{which module}} \neq \text{knowing \emph{which entry}} \neq \text{knowing \emph{which direction}}$$

## 2. Why v0.3 could not see this

`KnowledgeDamage` is defined as harm to the **correct-but-not-responsible**
module. Oracle's KD is exactly `0.00000` in every family and every seed — so by
that metric Oracle is perfect. But it still damages correct sub-knowledge
*inside the module it correctly blames*, and the metric is blind to this **by
construction**, because it only ever looks at the other module.

> A metric that cannot see the failure cannot diagnose it.

v0.4 therefore starts with a **new endpoint**, not a new algorithm.

## 3. The chain, stage by stage

| stage | variable | question it answers |
|---|---|---|
| Outcome | `o` | did the episode succeed? |
| **CreditUnit** | `c` | *what* is the thing that should change? |
| **CandidateRepairs** | `R = {r_1..r_k}` | *what are the admissible edits* to that unit? |
| **RepairSelection** | `r*` | which one is chosen, and by what rule? |
| Update | `q'` | the actual write, with a receipt |
| Learning | — | does utility improve on fresh contexts? |

**Interventions fix the family.** A scenario is assigned to a family by running
it under each single-variable intervention and observing which one repairs it —
not by which generator flag produced it. `WholeProcess` is defined as *the
minimal sufficient set has size > 1* (verified: `minimal_size == 2`), not as a
list of labels.

### 3.1 Endpoints

Both damage endpoints are the **same function** applied to different knowledge
sets, so they are directly comparable:

* `KI_m` — knowledge items of unit `m`: `(state, correct_action)` pairs a
  pretrained checkpoint holds with a correct-vs-wrong margin ≥ `theta`.
  Established **before any shock**, on the clean reference path — never at a
  failing trace's terminal transition, which is what killed the v0.2 probe.
* **CollateralDamage** — margin loss over `KI` for units *not* blamed. This is
  v0.3's KD, retained for continuity.
* **`WithinModuleDamage` (WMD)** — margin loss over `KI` for the unit that *was*
  blamed. **New.** This is the quantity v0.3 was blind to and Stage 5's reversal
  is attributed to.

A correction rule is admissible only if it reduces `U`-weighted error without
raising WMD. That is the v0.4 **admission test**.

### 3.2 Safe constraints (enforced in code, tested)

* no site → no update (`UpdateRecord.no_site`), so a failure to localise is
  never silently converted into a repair;
* `|ΔQ| ≤ DELTA_MAX = 0.25` per write, with `clipped` flagged on the receipt;
* every write emits a full `AppliedUpdate` receipt (`unit`, `state`, `action`,
  `q_before`, `q_after`, `target_value`, `clipped`, `role`, `delta_q`);
* `p`, `U`, `S`, `T` are four distinct variables and stay distinct in code.

## 4. Representations under test

The unit is the variable. All three are evaluator-side ground truth, so that
Pilot Alpha measures **representation**, not attribution quality:

| representation | credit unit | granularity |
|---|---|---|
| `ModuleOracle` | the blamed H/L module | coarse — v0.3's unit |
| `DecisionOracle` | the specific decision that failed | fine |
| `RepairOracle` | the minimal sufficient repair set, sized by intervention | fine + minimal |

## 5. Update targets under test

Granularity is frozen at the Alpha winner; only the target varies.

| arm | target |
|---|---|
| `NoCorrection` | — (baseline) |
| `NegativeOnly` | push the factual bad action down |
| `PositiveAlternative` | raise a verified alternative |
| `Contrastive` | bad↓ **and** good↑ |
| `CFRevalue` | target from an actual counterfactual re-execution |

`CFRevalue` is the ceiling arm: Oracle site **and** Oracle target. If the
strongest available repair cannot beat making no update at all, then site and
direction are not the missing pieces.

## 6. Pilots

| pilot | factor | cells |
|---|---|---|
| **Alpha** | credit-unit granularity | 3 representations + clean ceiling + damaged baseline |
| **Beta** | update target | 5 arms, granularity fixed at the Alpha winner |
| **Gamma** | robustness: reward × severity × mechanism | 12 cells |
| **Delta** | learned `p`, `p_U` | *not run — see §8* |

Common protocol: paired seeds, identical scenes and `NoiseTape` across arms;
300 warmup + 2,000 training episodes; 100 greedy evaluation episodes per
checkpoint; reward `+1/−1`; Oracle failure truth.

### 6.1 Pre-registered gates

| gate | threshold |
|---|---|
| practical non-inferiority margin | `0.01` |
| WMD relative decrease required | `0.20` |
| CI width above which the result is `INCONCLUSIVE_PRECISION` | `0.05` |
| clean-ceiling success | `0.98` |
| learning-failure floor | `0.30` |

### 6.2 Pre-registered falsification

* If some `(site, direction)` pair is non-inferior on task AUC **and** reduces
  WMD relative to `last_visited`, the defect is located and fixable: adopt it.
* If `oracle_site × oracle_direction` still fails to beat `no_correction`, then
  site and direction are **not** the missing pieces, and the conclusion is
  stronger and more useful: **incremental correction of a module's Q entries is
  the wrong update primitive.** That redirects v0.5 toward re-solving the
  module's policy or targeted replay, and away from any further attribution
  work.

Either outcome is a result. The forbidden move is adding SSP-BO, selective
replay, more CF budget, or a neural attributor to rescue it — Stage 5 rules all
of those out, because the bottleneck is not attribution cost.

## 7. Environment calibration

Difficulty is set on the **NoCorrection baseline only**, as the spec requires:

* `H=8`, `X_MAX=3` (the earlier values): baseline saturates — a delay-heavy
  policy is also optimal, so no policy-independent correct action exists and the
  Knowledge Set is either empty or circular. No induced damage persists.
* `X_MAX=7`, `H=8`: zero slack, but baseline never learns it at this budget.
* **`H=4`, `X_MAX=3`** (adopted): the long path costs exactly 4 steps, so zero
  slack; baseline learns (eval 1.0) and the damage calibration shows real
  dynamic range at every magnitude (min 0.013, recovered by episode 150–200).

`knowledge_theta = 0.20`. At `0.60` the checkpoint yields only PLAN items, so
nothing is ever corrupted and every damage number is a structural zero rather
than a measurement.

## 8. Explicit non-goals

Neural attributors, DQN, GRPO, SSP-BO, hippocampal selective replay, active
evidence acquisition, human-feedback source weighting, CPO/CMDP. None is
indicated by v0.3. The frozen extension pool stays frozen.

**Pilot Delta is deliberately not run.** It requires a learned attributor
emitting `p_whole, p_plan, p_decision, p_execution, p_U` with an independent
(non-softmax) unknown channel, trained on an 8,000/2,000/4,000 corpus — a
separate build. It is also not indicated by the results: Alpha, Beta and Gamma
all remove the *same* thing, the diagnostic update itself. Running a learned
attributor against a mechanism already shown to be net-negative would measure
attribution quality against a broken consumer, which is the ordering error this
spec's own decision tree warns against (*Oracle 失败时不训练更复杂 attribution
model*).

## 9. Carry-over from v0.3 (do not redo)

| asset | why it carries over |
|---|---|
| two-level causal grid, `NoiseTape`, label generator | fully deterministic, exact `U` by construction |
| grounded `p` (multi-label, non-normalised) and `p_U` | showed it changes results, not just notation |
| revision ledger + replay-from-checkpoint | naive patching is disproven (overshoots to −2.0) |
| seed-paired stats + Wilcoxon + POI + Holm | already matches the plan's statistics section |
| output-integrity and reproducibility envelope | keep every run in a fresh `outputs/v04_*` |

## 10. Result

See `docs/V0_4_RESULTS.md`. Both pre-registered hypotheses are **negative**, and
both negatives are resolved rather than underpowered. Seed-scale history and the
conclusions that moved are recorded in `docs/SEED_AUDIT_300.md`; no earlier run
was overwritten.
