# 08 — V0.3R: Credit truth → Repair primitive

$$\boxed{\text{SUPERSEDED ON B2 BY A79 (\S67). See \S3's banner.}}$$

$$\boxed{\text{Knowing exactly what to change and where, \emph{how} should it be changed?}}$$

All attribution and all credit assignment are **Oracle truth** in this version.
No learned component is allowed to influence a result.

This is the load-bearing version of the whole programme. If the answer here is
"even with perfect cause, perfect responsibility, perfect site and a verified
alternative, the repair still does not improve learning", then the RFL chain
$\text{attribution} \to \text{learning}$ is broken at the primitive, and that is a
strong negative result obtained cheaply.

---

## 1. Two blocks, in order

$$B_1:\ \text{Offline semantic repair} \quad\longrightarrow\quad B_2:\ \text{Online recovery}$$

$$\boxed{B_1 = \text{PASS} \;\Longrightarrow\; B_2 \text{ is permitted}}$$

The gate exists because of the legacy failure: `CFRevalue` was implemented so
that it wrote the post-repair return into the **factual failing action**, which
made the strongest arm perform worst and produced a false negative that was
briefly written up as a conclusion about the primitive. A primitive must be shown
to point the right way on a known target *before* it is judged by an online curve.

---

## 2. Block 1 — Offline semantic repair (the gate)

### 2.1 Construction

1. Obtain a clean reference checkpoint $Q^{*}$ (pretrained, frozen, committed).
2. Apply a **known corruption** $M$ to a known set of entries, giving
   $Q_{\text{corrupted}}$.
3. Run the repair primitive on $Q_{\text{corrupted}}$ using only failure evidence.
4. Compare against $Q^{*}$.

No learning loop, no environment interaction beyond the evidence the primitive
needs. This isolates one question:

$$\boxed{\text{Does this primitive move the parameters in the right direction?}}$$

### 2.2 Two tiers of information

| tier | what the repair sees | answers |
|---|---|---|
| **known mask** | the corruption mask $M$ | *if you are told where the damage is, can this primitive fix it?* — a sanity ceiling |
| **unknown mask** | only failures/evidence; $M$ is held by the evaluator | the real test |

The known-mask tier is a **ceiling check, not a result**. If a primitive cannot
repair a fault whose location is given to it, it is broken and the version stops.
Reported, never used as evidence for the primitive.

### 2.3 Endpoints

Raw $\|Q - Q^{*}\|$ is **prohibited as primary**: Q-values are not unique — two
tables with different numbers can induce identical greedy policies — and the norm
depends on table size and value scale, so it is not comparable across settings.

| endpoint | definition | role |
|---|---|---|
| **OptimalActionSetAgreement** | fraction of states where $\pi_{\text{repair}}(s) \in A^{*}(s)$, with $A^{*}(s) = \arg\max_a Q^{*}(s,a)$ | **primary** |
| **PolicyRegret** | $Q^{*}(s, a^{*}) - Q^{*}(s, \pi_{\text{repair}}(s))$ | **co-primary** |
| **CollateralDamage$_{\neg M}$** | damage on entries the corruption **never touched** | **co-primary** |
| $\|Q - Q^{*}\|$, normalised by entry count and value scale | secondary diagnostic only | secondary |

Using the **optimal action set** $A^{*}(s)$ rather than a single argmax means ties
in $Q^{*}$ do not force agreement with an arbitrary choice.

The unknown-mask tier must beat a **no-repair baseline** on
OptimalActionSetAgreement while not raising CollateralDamage$_{\neg M}$. Both
conditions are required; either alone is gameable.

---

## 3. Block 2 — Online recovery

$$\boxed{\text{SUPERSEDED BY A79 (\S67): this section does not govern B2.}}$$

The arms below were retired by A76 (the $\pm1$ targets as information-deficient; the rest by the tier-matched matrix), and the process reading in \S3.4 -- $do(z=z')$ as mechanism repair -- is rejected by the frozen reading, where mechanism repair is $do(C_P=\mathrm{identity})$ and $do(z=z')$ is strategy replay. It is kept as the record of what the design had to learn. A79 \S67 governs B2; \S2 above is not addressed by A79 either way.

Only after Block 1 passes. All attribution and site selection remain Oracle.

### 3.1 Arms

| arm | unit | target | writes to |
|---|---|---|---|
| `NoCorrection` | — | — | nothing |
| `NegativeOnly` | factual decision site | failure value | $Q_D(s, a_{\text{bad}})$ |
| `PositiveAlternative` | verified alternative | $+1$ | $Q_D(s, a_{\text{alt}})$ |
| `Contrastive` | both | failure / $+1$ | both entries |
| **`CFTarget`** | verified alternative | $G^{CF}_{a_{\text{alt}}}$ | $Q_D(s, a_{\text{alt}})$ |
| `ControllerUpdate` | execution site | — | $C_X$ |
| `NoUpdateWhenExternal` | environment / unmodelled | — | nothing (the correct answer) |

### 3.2 The corrected counterfactual target

$$\boxed{Q(s, a_{\text{alt}}) \leftarrow Q(s, a_{\text{alt}}) + \alpha\bigl(G^{CF}_{a_{\text{alt}}} - Q(s, a_{\text{alt}})\bigr)}$$

The return goes to $a_{\text{alt}}$ — **the action that produced it**. Writing
$G^{CF}$ into $a_{\text{bad}}$ is prohibited and is detected by the semantic suite
(invariant I1 and case C2).

This is the arm the legacy `CFRevalue` claimed to be and was not. It is the
specification's ceiling primitive, and the plan's falsification branch — *if the
strongest available repair cannot beat making no update, incrementally editing
Q-entries is the wrong primitive* — is only testable through this arm.

### 3.3 Execution faults write to the controller

An internal controller fault is repaired by $\Delta C_X$, **never** by
$\Delta Q_D$. An external plant fault is repaired by nothing: `NoUpdateWhenExternal`
is the correct arm by construction, and an arm that edits under $Z_E$/$Z_U$ is
measurably wrong. The legacy code could not express this distinction because
`DECISION` and `EXECUTION` shared one table.

### 3.4 Process faults replace the strategy

A process fault is repaired by $do(z = z')$ — replacing the strategy program —
not by decrementing a visited Q-entry. With $|\mathcal Z| = 4$ the candidate set
is enumerable, so this is a well-posed choice rather than a search.

### 3.5 Endpoints

| endpoint | role |
|---|---|
| **RMST** over $\tau$, right-censored (`05` §8) | **primary** |
| DeficitAUC | co-primary |
| PolicyFlipRate | secondary |
| WithinUnitDamage | secondary |
| CrossUnitCollateral | secondary |
| RepairPrecision | secondary |
| TimeToRecover (per-seed, censoring reported) | descriptive |

Time-to-recover is preferred over whole-curve AUC because this is a recovery
problem: the question is *how fast*, not *on average over the whole run*. Both
are reported; RMST is primary because it handles the seeds that never recover.

### 3.6 The update-dynamics ledger

Because reward mode and clipping change the optimisation trajectory even when the
optimal policy is unchanged (`02-SCM.md` §7), every arm logs:

$$N_{\text{writes}},\quad \textstyle\sum|\Delta Q|,\quad \overline{|\Delta Q|},\quad P(\text{clipped}),\quad \overline{|\delta_{TD}|},\quad N(\delta_{TD} < 0)$$

and the same broken out per unit (factual / alternative / controller). Without
this, an arm that "wins" cannot be distinguished between *it carries outcome
information* and *it merely produced larger TD errors that happened to land
outside the clip*.

---

## 4. Go / no-go

| gate | condition |
|---|---|
| Semantic suite (`04`) | PASS |
| **Block 1 known-mask ceiling** | primitive repairs a located fault |
| **Block 1 unknown-mask** | beats no-repair on OptimalActionSetAgreement **and** does not raise CollateralDamage$_{\neg M}$ |
| Runtime calibration (`10` §3) | reported before collection |

$$\boxed{\text{Block 1 FAIL} \;\Longrightarrow\; \text{Block 2 is not run, and no claim is made about online recovery.}}$$

**If V0.3R fails at Block 2** — with truth given and a validated primitive — the
correct conclusion is that *incremental correction of this kind does not improve
learning in this environment*, and the programme redirects to a different update
family (re-solving the unit's policy, or targeted replay) rather than to more
attribution work.

---

## 5. Scale

| item | value |
|---|---|
| unit | $N_{\text{seeds}}$ |
| smoke | 5 |
| development | 32 |
| primary confirmatory | 400 = 4×100 |
| secondary confirmatory | 200 = 2×100 |
| $N_{\text{train}}$ | **frozen by `05` §6 from the baseline only**, before collection |
| $N_{\text{eval}}$ | 100 per checkpoint |
| $\mathcal G_{\text{ckpt}}$ | dense early (`05` §6.2), frozen with $T$ |
