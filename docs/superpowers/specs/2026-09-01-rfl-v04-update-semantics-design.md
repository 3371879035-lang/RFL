# RFL-CausalChase v0.4 — Update Semantics Design

**Status:** design proposal, derived from the v0.3 closeout.

**Origin:** Stage 5's negative result. With `U` fixed at the SCM truth, Oracle
routing never reliably improved policy utility in any of six difficulty
settings, and at `horizon=5, alpha=0.03` it was significantly worse
(ΔAUC −0.08490, CI [−0.10188, −0.06823]). That is not evidence against learning
responsibility; it localises a defect downstream of it.

---

## 1. The defect

v0.3's diagnostic correction is a single rule:

$$Q_m(s,a) \leftarrow Q_m(s,a) - \alpha_{\text{diag}} \quad\text{where } (s,a) \text{ is the last visited entry of module } m$$

Two things are wrong with it, and v0.3 could not separate them:

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
module. Oracle's KD is exactly 0.00000 in every family and every seed — so by
that metric Oracle is perfect. But it still damages correct sub-knowledge
*inside the module it correctly blames*, and the metric is blind to this **by
construction**, because it only ever looks at the other module.

**A metric that cannot see the failure cannot diagnose it.** v0.4 therefore
starts with a new endpoint, not a new algorithm.

## 3. New layer

The chain gains two stages after responsibility:

```
Causal contribution
  -> Functional correctness
  -> Module responsibility   U_m      which module must change
  -> Update site             S_{m,i}  which decision / state-action entry
  -> Update direction        T_{m,i}  lower, raise, or re-value it
```

* `U_m in {0,1}` — unchanged from v0.3.
* `S_{m,i}` — a selection rule over the entries module `m` touched this episode.
* `T_{m,i}` — a rule mapping the selected entry to a target value.

`p`, `U`, `S`, `T` are four distinct variables and stay distinct in code.

## 4. New endpoints

Both endpoints are the *same function* applied to different knowledge sets, so
they are directly comparable:

* `KI_m` — the knowledge items of module `m`: `(state, correct_action)` pairs
  that a pretrained checkpoint holds with a correct-vs-wrong margin of at least
  `theta`. Established before any shock, on the **clean reference path** — never
  at a failing trace's terminal transition, which is what killed the v0.2 probe.
* **CollateralDamage** — margin loss over `KI_m` for the module *not* blamed.
  This is v0.3's KD, retained for continuity.
* **`WithinModuleDamage` (WMD)** — margin loss over `KI_m` for the module *that
  was blamed*. **New.** This is the quantity v0.3 was blind to and Stage 5's
  reversal is attributed to.

A correction rule is only admissible if it reduces `U`-weighted error without
raising WMD. That is the v0.4 admission test.

## 5. Stage 6 experiment

**The critical design choice: hold `U` at the SCM truth throughout.** Attribution
is perfect by construction, so any remaining failure is unambiguously an
update-semantics failure. This is precisely the confound that made Stage 5's
result hard to interpret.

### Arms: site rules

| rule | selects | rationale |
|---|---|---|
| `last_visited` | the final `(s,a)` of the episode | **v0.3's rule** — the thing on trial |
| `all_visited` | every `(s,a)` the module chose | blunt within-module baseline |
| `cf_critical` | the timestep where a counterfactual intervention flips the outcome | attacks the site question directly |
| `deviation` | the first timestep whose action differs from the reference policy for the chosen option | cheap, requires only the reference policy |
| `oracle_site` | the entry whose correction most improves the outcome | evaluator-only upper bound |

### Arms: direction rules

| rule | target |
|---|---|
| `subtract_alpha` | `Q - alpha_diag` | **v0.3's rule** |
| `toward_failure` | `Q + alpha (r_failure - Q)` — a proper TD-style target |
| `toward_counterfactual` | the counterfactual outcome value for that entry |
| `revalue` | recompute the entry by targeted replay, no incremental patch |

### Design

* baseline `no_correction`
* full `site x direction` grid, plus `oracle_site x oracle_direction` as the ceiling
* 20+ paired seeds; identical scenes and `NoiseTape` across arms
* task-AUC, `WithinModuleDamage`, `CollateralDamage`, and final success
* a difficulty sweep as in Stage 5, since Stage 5 showed the reversal only
  appears under a tight horizon with slow learning

### Pre-registered falsification

* If some `(site, direction)` pair is non-inferior on task AUC **and** reduces
  WMD relative to `last_visited`, the defect is located and fixable: adopt it.
* If `oracle_site × oracle_direction` still fails to beat `no_correction`, then
  site and direction are **not** the missing pieces, and the conclusion is
  stronger and more useful: **incremental correction of a module's Q entries is
  the wrong update primitive.** That redirects v0.5 toward re-solving the
  module's policy or targeted replay, and away from any further attribution work.

Either outcome is a result. The forbidden move is adding SSP-BO, selective
replay, more CF budget, or a neural attributor to rescue it — Stage 5 rules all
of those out, because the bottleneck is not attribution cost.

## 6. Carry-over from v0.3 (do not redo)

| asset | why it carries over |
|---|---|
| two-level causal grid, `NoiseTape`, label generator | fully deterministic, exact `U` by construction |
| grounded `p` (multi-label, non-normalised) and `p_U` | showed it changes results, not just notation |
| revision ledger + replay-from-checkpoint | naive patching is disproven (overshoots to −2.0) |
| seed-paired stats + Wilcoxon + POI + Holm | already matches the plan's statistics section |
| output-integrity and reproducibility envelope | keep every run in a fresh `outputs/v04_*` |

## 7. Explicit non-goals

Neural attributors, DQN, GRPO, SSP-BO, hippocampal selective replay, active
evidence acquisition, human-feedback source weighting, CPO/CMDP. None is
indicated by v0.3. The frozen extension pool stays frozen.
