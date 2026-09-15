# v0.4 semantic and implementation corrections

**Date:** 2026-09-01, after the frozen 400-seed collection completed.
**Status:** these are **post-hoc corrections to interpretation**, not re-runs.
No training code was changed to produce this document, and no seed was re-run.
Where a correction changes a published conclusion, the published wording is
quoted and then withdrawn.

The seed-count work answered *"is the effect real?"*. These are the questions it
could not answer, because they are about **what the code actually computes**.
Four of them matter.

---

## 1. `CFRevalue` is not a ceiling arm — the published conclusion is withdrawn

### What the spec says

`docs/V0_4_SPEC.md` §5 describes `CFRevalue` as the ceiling:

> `CFRevalue` is the ceiling arm: Oracle site **and** Oracle target. If the
> strongest available repair cannot beat making no update at all, then site and
> direction are not the missing pieces.

and `docs/FROZEN_RESULTS_400.md` §6 drew the strong conclusion from it:

> The strongest repair available performs far *worse* than doing nothing. Per the
> plan's own decision tree the required conclusion is: **直接修补 Q-entry 不是合适的
> update primitive.**

### What the code does

`src/rflv04/train.py:355-366`:

```python
if arm == "CFRevalue":
    cf_return = rollout_intervened(
        source_trace.scene,
        sel.primitives if sel is not None else frozenset(),
    ).return_value
    targets = {site.key: cf_return for site in credit.sites}      # <-- factual sites
    alt_targets = {site.key: cf_return for site in alts}

if arm == "CFRevalue":
    rec = MODES["negative_only"](q, credit.sites, targets, alpha=alpha_diag)
```

Two facts settle the question:

* `env.py:236` sets `return_value = 1.0` **iff the repaired rollout succeeds**,
  else `-1.0`.
* `updates.negative_only` applies `Q(s,a) ← Q(s,a) + α·(y − Q(s,a))`, and it is
  called with `credit.sites` — the **factual** sites, i.e. the actions the agent
  actually took and which led to failure. `alts` is built and then **never read**
  on this path.

So on every episode where the counterfactual repair succeeds, `CFRevalue` writes

$$Q(s, a_{\text{bad}}) \leftarrow Q(s, a_{\text{bad}}) + \alpha\,(1.0 - Q(s, a_{\text{bad}}))$$

That **raises the value of the action that caused the failure.** It is not
"reinforce the verified alternative"; it is the opposite of a repair. On episodes
where the repair fails, `cf_return = −1.0` and the arm degenerates to exactly
`NegativeOnly`.

### Consequence

`CFRevalue` differs from `NegativeOnly` **only on the episodes where the repair
worked — and there it does the wrong thing.** Its catastrophic score is a
predicted consequence of the implementation, not evidence about credit
assignment.

| arm | SuccessAUC (N=400) |
|---|---:|
| `CFRevalue` | 0.8509 |
| `NoCorrection` | 0.9432 |

**Withdrawn.** The claim *"patching a Q-entry is the wrong update primitive"* is
**not supported by this arm**. The defensible claim is narrower:

> Writing a counterfactual return into the factual failing action's Q-entry is
> harmful. Whether a *correctly aimed* Q-entry repair — one that raises the
> verified alternative and lowers the factual action — would help remains
> **untested**, because no arm in v0.4 implements it.

Note that `PositiveAlternative` and `Contrastive` do target the alternative
(they write to `alts` via `positive_alternative_only` / `contrastive`), and both
are also worse than `NegativeOnly` — but neither uses an Oracle-derived value for
the alternative; both use a constant `+1.0`. So the ceiling question is still
open, and the plan's falsification branch did **not** fire.

---

## 2. `DECISION` and `EXECUTION` are distinct names over one Q-table

`Site.unit` distinguishes `DECISION` from `EXECUTION`. `updates._write` routes
**every non-PLAN unit to the same low-level table**:

```python
def _write(q, unit, state, action, value):
    if unit == "PLAN":
        q.high_update(state, action, value, 1.0)
    else:
        q.low_update(state, action, value, 1.0)
```

`Site.key` is `(unit, state, action)`, so a `DECISION` site and an `EXECUTION`
site on the same step have different keys and **both survive `dedup()`** — while
being two successive relative writes to one Q entry, carrying opposing targets.

This is what made training `PYTHONHASHSEED`-dependent
(`docs/V0_4_REPRODUCIBILITY_DEFECT.md`). The fix sorted the iteration, which made
the outcome **deterministic**. It did not make it **principled**.

**Consequence.** Pilot Alpha's `ModuleOracle` / `DecisionOracle` / `RepairOracle`
comparison is not a clean credit-unit decomposition: the "fine" units are finer
in name, and partly identical in effect. The two results that survive are the
ones that do not depend on this:

* collateral **0.4352 → 0.0000** — structural, because the fine unit never emits
  a site outside the blamed decision;
* WMD **+57.7%** — robust at the seed level (304/395 non-tied seeds positive).

The utility contrast was already `INCONCLUSIVE`, so nothing there changes.
`Site.write_key` and `Credit.collisions()` now expose the collision; it is
counted, not silently resolved.

---

## 3. The Oracle's failure families are inflated by reconstruction

`oracle.scene_from_trace()` locates the critical decision with

```python
step.realized != reference_action(...)
```

but `env.py` records `intent` and `realized` **separately**, precisely so that an
execution fault (intent correct, realized deviated) is never mistaken for a bad
decision. Reconstructing with `realized` injects a spurious decision fault at the
same timestep, so no size-1 `exec` repair can suffice.

Measured in the candidate-ledger audit (7,137 failed episodes):

| | |
|---|---:|
| failures carrying an execution fault | 4,000 (56.1%) |
| failures classified `Execution` | 26 (**0.36%**) |
| failures classified `WholeProcess` | 4,881 (**68.4%**) |

**`WholeProcess` — the family the spec singles out as the hard case — is largely
a reconstruction artifact, not a population of genuinely multi-fault episodes.**

The spec's operational definition is still correct as a definition:
`WholeProcess == (minimal_size > 1)` was confirmed on 7,137/7,137 rows with 0
disagreements. What is in doubt is how many real episodes belong to the family.

**Consequence for v0.4 Alpha/Beta:** the family-anchored readings of those pilots
should not be treated as mechanism facts. The arm-level AUC/WMD/collateral
comparisons are unaffected — they do not condition on family.

---

## 4. Pilot Gamma's interaction statistics were computed on duplicated,
   non-independent observations

### The defect

`scripts/pilot_v04_gamma.py:98-102` builds the paired vectors:

```python
for r in REWARDS:
    for s, _ in SEVERITIES:
        (hi_spec, lo_spec) = pick(r, s)
        xs.append(get(hi_spec)); ys.append(get(lo_spec))
```

with

```python
("reward_B_minus_A",  lambda r, s: (("B", s), ("A", s))),
("severe_minus_mild", lambda r, s: ((r, "severe"), (r, "mild"))),
```

Both `pick` functions ignore one argument, so the outer loop appends **the same
pair twice**: every observation entered the paired test exactly twice. Separately,
one seed contributes *two* severity cells, and cell-level pairs are not
independent samples — the cells of a seed share its environment draws and noise
tape.

A mean is unaffected by duplication, which is why the published effect sizes are
right. The bootstrap CI, the sign-flip permutation and the Wilcoxon test are not:
they treat $n$ as 2× the independent count, making all three anti-conservative.

### Recomputation

`scripts/v04_gamma_seedlevel.py` aggregates to the seed first (mean over
severities for the reward interaction, mean over rewards for the severity
interaction), then tests across the 400 seeds. It reports the published
computation alongside, so the inflation is on the record.

| mechanism | interaction | mean | published CI | **seed-level CI** | published | **corrected** |
|---|---|---:|---|---|---|---|
| `NoCorrection` | reward B − A | −0.02629 | [−0.03183, −0.02075] | **[−0.03957, −0.01344]** | `SUPPORT_B` | **`SUPPORT_B`** |
| `NoCorrection` | severe − mild | −0.09425 | [−0.09910, −0.08946] | **[−0.10516, −0.08365]** | `SUPPORT_B` | **`SUPPORT_B`** |
| `NegativeOnly` | reward B − A | −0.02026 | [−0.02451, −0.01601] | **[−0.03080, −0.00979]** | `SUPPORT_B` | **`INCONCLUSIVE`** |
| `NegativeOnly` | severe − mild | −0.06484 | [−0.06818, −0.06155] | **[−0.07227, −0.05764]** | `SUPPORT_B` | **`SUPPORT_B`** |
| `DecisionOracle` | reward B − A | +0.01078 | [+0.00418, +0.01745] | **[−0.00475, +0.02590]** | `INCONCLUSIVE` | **`INCONCLUSIVE`** |
| `DecisionOracle` | severe − mild | −0.09921 | [−0.10514, −0.09341] | **[−0.11227, −0.08629]** | `SUPPORT_B` | **`SUPPORT_B`** |

Means are identical to 5 decimal places, as expected. **CIs are 2.2–2.5× wider**
at the correct unit. One verdict changes:

* **`NegativeOnly`: `reward B − A` moves from `SUPPORT_B` to `INCONCLUSIVE`.**
  Its CI upper bound is −0.00979 — a hair inside the equivalence band. The honest
  reading is that the reward ablation is *unresolved* for this mechanism, not
  confirmed.
* `DecisionOracle`: `reward B − A` was p = 0.0198 published; at the correct unit
  it is p = 0.16. The published significance was an artifact of the duplicated
  $n$.

The **severity** effect is unaffected and is the robust half of Pilot Gamma:
`severe − mild` is `SUPPORT_B` for all three mechanisms, means −0.065 to −0.099,
CIs far below $-\Delta_{\min}$, and stable under the correction.

### Also wrong in the same script

`pilot_v04_gamma.py` prints `"N_delta_neg under reward B (per 2000 episodes)"` as
a hardcoded string. The 400-seed run was launched with `--episodes 1000`, so it
used **1,000** training episodes. The `n_negative_td` figures (896 / 565 / 521)
are per 1,000 episodes, not per 2,000. The relative reading — that `r_failure = 0`
removes the explicit penalty but not the downward updates — is unchanged.

---

## 5. Corrected experiment scale (the seed description was wrong)

An earlier description stated flatly that "one seed = 300 warmup + 2,000 episodes
+ 100 greedy evaluation". **That is true only for v0.4 Alpha and Beta.** Each
pilot has its own budget, and the reversal ledger spans five pilots:

| pilot | warmup | training episodes | eval every | eval episodes |
|---|---:|---:|---:|---:|
| v0.3 Alpha | — | **10,000** | 250 | 200 |
| v0.3 Stage 4 | — | **5,000** | 250 | 150 |
| v0.3 Stage 5 | — | **2,000** | 250 | 150 |
| v0.4 Alpha | 300 | **2,000** | 250 | 100 |
| v0.4 Beta | 300 | **2,000** | 250 | 100 |
| v0.4 Gamma | 300 | **1,000** | 250 | 100 |

What *is* true across all of them: **one seed = one complete independent training
run**, and increasing N from 100 to 400 increased the number of independent runs,
**not** the length of any single run.

That distinction matters for how results may be described. These data say nothing
about whether a single agent would change its mind with more experience. A
statement like *"at 100 seeds the policy had not yet matured"* is **not
applicable** here — no agent was trained any longer at N=400 than at N=100.

Testing that question is a different axis:

$$N_{\text{episodes}} = 500,\ 1000,\ 2000,\ 5000,\dots \quad\text{with seeds held fixed}$$

No such sweep exists in this project.

---

## 6. The `ROBUST` label was being used for two different things

`FROZEN_RESULTS_400.md` §4 described `direct_feedback`, `random_correction` and
`aux_penalty_rfl` as **"ROBUST harmful"**, while `REVERSAL_LEDGER.md` recorded all
eight Stage 4 arms as **`EQUIVALENT` × 4**. Both were reported from the same
data, which reads as a contradiction.

It is a terminology collision, and the ledger is right:

* `robustness_audit.verdict()` returns `ROBUST` when the mean, median and trimmed
  mean agree in sign **and** the sign test is significant **and** the effect is
  not tail-driven. It is a statement about **whether the direction is reliably
  non-zero**.
* The four-way rule asks whether the effect is **practically meaningful**, i.e.
  whether the CI clears $\Delta_{\min} = 0.01$.

These are different questions. `direct_feedback` has ΔAUC = −0.00532 with a tight
CI — its direction is reliably negative, but its magnitude is **half** the
pre-registered minimum meaningful effect. Calling that "harmful" overstates it.

**Corrected wording:** `direct_feedback`, `random_correction` and
`aux_penalty_rfl` are **directionally negative and statistically reliable, but
practically equivalent** — $|\Delta| < \Delta_{\min}$. What *is* large is the
knowledge-level effect, and that is where the RFL claim lives:

| Stage 4 result | value | status |
|---|---|---|
| `learned_rfl` vs `traditional`, task utility | ΔAUC −0.00056, CI [−0.00132, +0.00017] | non-inferior, `EQUIVALENT` |
| `learned_rfl` vs `direct_feedback`, collateral | **−0.26509**, CI [−0.27139, −0.25854] | **large, `SUPPORT_B`-scale** |

The project's claim was never "RFL improves task utility" — it was "RFL is the
only mechanism that corrects without paying for it". That claim is **strengthened**
by the correction, because the thing RFL is better at (collateral) is an order of
magnitude larger than the thing its competitors are worse at (utility).

---

## 7. Coverage of the reversal ledger

`scripts/reversal_ledger.py` covers **5 pilots and 23 contrasts**:

```
v03_stage5 (6)   v03_alpha (1)   v03_stage4 (8)   v04_alpha (4)   v04_beta (4)
```

**Pilot Gamma is not among them** — its contrasts are interactions within a
12-cell design rather than arm-versus-baseline pairs, and it needed the
recomputation in §4 before it could be included at all. Phrasing such as "5
reversals in 23 contrasts" refers to those 23, not to every experiment in the
project.

## 8. Status of every headline claim

| claim | before | **after these corrections** |
|---|---|---|
| v0.1: RFL attributes better under wrong feedback | high | **high** (unchanged) |
| v0.3: `+1/−1` vs `+1/0` equivalent in the Alpha environment | high | **high, environment-limited** |
| v0.3: RFL reduces wrong-module collateral | high | **high** |
| v0.3: RFL improves policy utility | none | **no evidence** (unchanged) |
| Stage 5: Oracle routing is harmful at h5, α=0.03 | high | **high** (4/4 blocks) |
| v0.4: finer credit eliminates cross-unit collateral | structural | **structural** (unchanged) |
| v0.4: finer credit improves utility | unresolved | **unresolved** (unchanged) |
| v0.4: `Contrastive` beats `NegativeOnly` | refuted | **refuted** (unchanged, robust) |
| v0.4: patching a Q-entry is the wrong primitive | asserted | **withdrawn** — §1 |
| v0.4 Gamma: failure penalty, ~0.02–0.026 | confirmed | **only `NoCorrection` confirmed** — §4 |
| v0.4 `WholeProcess` / `Execution` proportions | reported | **not credible** — §3 |
| v0.4: credit-unit decomposition is clean | assumed | **not clean** — §2 |

The strongest surviving evidence for RFL remains **V0.1's attribution effect**
and the **collateral reduction** in v0.3/v0.4. The link that has never been
demonstrated is still:

$$\text{better interpretation} \;\rightarrow\; \text{better policy learning}$$

---

## 9. What should happen next

The user-facing recommendation is **not** more seeds. The frozen protocol
completed at N=400 and raising it further would answer nothing new — the
remaining uncertainty is about semantics, not sampling error. The valuable next
step is a semantic closeout, after which a v0.5 / v0.4.1 restart from N=0 on
fresh seeds would be meaningful:

1. fix `scene_from_trace` to use `intent`, not `realized`, so `Execution` and
   `WholeProcess` mean what the spec says (§3);
2. give `DECISION` and `EXECUTION` genuinely separate representations, or merge
   them honestly into one unit and rename (§2);
3. fix `enumerate_sufficient` to enumerate sizes in order rather than stopping at
   the first sufficient size, so `minimal` carries information;
4. redefine `CFRevalue` so the value lands on the **repair candidate**, making it
   the ceiling the spec claims (§1);
5. recompute Gamma's statistics — **already done here, no re-run needed** (§4).

Items 1–4 change training semantics, so under protocol §9.1 they would void the
current seed set and require a restart from N=0. Item 5 does not: it is analysis
only, and is done.
