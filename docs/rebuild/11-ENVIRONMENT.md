# 11 — The environment, concretely

**Status:** FROZEN. Depends on `01-OBSERVATION-MODEL.md` and `02-SCM.md`.

`02-SCM.md` fixes the *structure*: five causes, a strategy variable, a three-layer
action, an intervention lattice. It deliberately does not fix a task, and an
implementer cannot build `src/rfl_rebuild/env/` from structure alone. This
document supplies the concrete instantiation, and it supplies it **once**, so
that every version runs on the same environment and results are comparable.

Everything here is chosen to be small enough to enumerate exhaustively and to
make each of the five causes physically real rather than notational.

---

## 1. Task

A 5×5 grid. The agent starts at $S = (0,2)$ and must reach $G = (4,2)$.

```
        col 0    1    2    3    4
row 0    .     .    .    .    .
row 1    .     #    .    #    .        # = wall
row 2    S     .    ·    .    G        · = contested cell
row 3    .     #    .    #    .
row 4    .     .    .    .    .
```

Two routes: the **short corridor** along row 2 ($S \to \cdot \to G$, 4 steps), and
the **long way** around via rows 0 or 4 (8 steps).

A **hazard** patrols the short corridor. It occupies the contested cell $(2,2)$ at
deterministic times given the noise tape, with a period that depends on the
episode's context.

$$H = 12 \quad\text{(episode length, fixed)}$$

A step cost of $-0.02$ applies, terminal reward as in `02-SCM.md` §7. Success
requires reaching $G$ **without** occupying a cell the hazard occupies at that
timestep.

$$5 \times 5 \times 13 \times 2 \;=\; 650 \text{ states} \quad\text{— fully enumerable}$$

(The factor 13 is $H+1$ for the timestep, 2 for the context lane.)

---

## 2. Context lane

Each episode carries an observable context $\kappa \in \{0,1\}$:

| $\kappa$ | meaning | hazard period |
|---|---|---|
| 0 | slow patrol | 6 |
| 1 | fast patrol | 3 |

$\kappa$ is **visible** at $t=0$ and is part of $s_t$. It is what makes
"context-appropriate" a real property: the same strategy can be right under
$\kappa = 0$ and wrong under $\kappa = 1$, which is the mechanism behind $Z_P$.

---

## 3. Actions

$$A = \{\texttt{UP},\ \texttt{DOWN},\ \texttt{LEFT},\ \texttt{RIGHT},\ \texttt{WAIT}\},\qquad |A| = 5$$

An action that would enter a wall or leave the grid is **illegal**; the reference
policy never selects one, and a fault injecting one resolves to `WAIT` with the
illegality recorded in $M$.

---

## 4. The four strategy programs

$z$ is a function `(state, t, κ) → A`. Four programs, frozen:

| $z$ | name | behaviour | property it exists to provide (`02-SCM.md` §2) |
|---|---|---|---|
| $z_1$ | `rush` | head straight along row 2 to $G$ | the default; **correct iff $\kappa = 0$** |
| $z_2$ | `rush_detour` | row 2, but sidestep to row 1 or 3 when the hazard is at $(2,2)$ | **locally improvable**: one decision — the sidestep *timing* — is wrong, everything else is sound |
| $z_3$ | `wait_then_cross` | advance to $(1,2)$, `WAIT` until the hazard clears, then cross | **genuinely different**: succeeds under $\kappa = 1$ where $z_1$ collides |
| $z_4$ | `long_way` | go around via rows 0/4 | **delayed failure**: looks healthy for ~5 steps, then times out at $H$ |

$z_1$ under $\kappa = 1$ collides. $z_3$ and $z_4$ succeed under both contexts.
$z_2$ succeeds under $\kappa = 0$ and, depending on the tape, may or may not under
$\kappa = 1$ — this is deliberate, it gives $Z_P$ episodes whose outcome is
tape-dependent rather than context-determined.

$$\boxed{|\mathcal Z| = 4,\ \text{enumerated in full}.}$$

---

## 5. The three-layer action, instantiated

$$d_t = z(s_t, t, \kappa) \;\longrightarrow\; a^{cmd}_t = d_t \;\longrightarrow\; u_t = C_X(s_t, a^{cmd}_t) \;\longrightarrow\; a^{realized}_t = P(s_t, u_t, \epsilon_E)$$

with $u \in A$, and the **healthy plant is the identity**: $P(s, u, \epsilon_E) = u$
unless $\epsilon_E$ is active at $t$.

### 5.1 Controller $C_X$

A tabular map on $(s, a^{cmd})$, initialised to the identity:

$$C_X(s, a) = a \quad \forall s, a$$

It is **learnable**, with its own parameters, disjoint from $Q_D$ — this is
invariant **I1** of `04-SEMANTIC-INVARIANTS.md` and the structural fix for the
legacy `DECISION`/`EXECUTION` collision.

An **internal controller fault** ($Z_X$) writes a perturbation at a specific
$(s^{*}, a^{*})$: $C_X(s^{*}, a^{*}) = a' \neq a^{*}$. It is repairable, and the
repair is $\Delta C_X$.

### 5.2 Plant and external faults

The plant is identity unless an **external perturbation** ($Z_E$) is active, in
which case at one specific timestep $P$ returns $u' \neq u$ regardless of $C_X$.
This is **not repairable by the learner** and the correct response is to change
nothing (`04-SEMANTIC-INVARIANTS.md`, case **C8**).

The three channels are therefore physically distinct:

| observed | inference | correct repair |
|---|---|---|
| $a^{cmd}$ deviates from reference | decision fault | $\Delta Q_D$ |
| $a^{cmd}$ fine, $u \neq a^{cmd}$ | internal execution fault | $\Delta C_X$ |
| $a^{cmd}$ fine, $u = a^{cmd}$, $a^{realized} \neq u$ | external fault | **none** |

---

## 6. Cause injection

Each cause is assigned exogenously (`02-SCM.md` §6), never reconstructed.

| cause | injection | feasibility constraint |
|---|---|---|
| $Z_P$ | $z \leftarrow z' \neq z^{*}(\kappa)$, where $z^{*}(\kappa)$ is the context-appropriate program | $z'$ must not be outcome-equivalent to $z^{*}(\kappa)$ on this tape |
| $Z_D$ | $d_{t^{*}} \leftarrow a' \neq d_{t^{*}}$ for one $t^{*}$ | $a'$ must be legal and must change the outcome on this tape |
| $Z_X$ | $C_X(s^{*}, a^{*}) \leftarrow a'$ | $a^{*}$ must actually be issued at $s^{*}$ on this tape |
| $Z_E$ | activate $\epsilon_E$ at one $t$ | must change the outcome on this tape |
| $Z_U$ | draw from the **unmodelled** generator: a rare cell-specific trap that the agent's hypothesis space has no symbol for | must change the outcome |

### 6.1 The feasibility filter is mandatory

An injection that does **not** change the outcome on the realised tape produces an
episode where the cause is present but inert. Labeling those as faults would
inflate every cause and destroy the meaning of $R^{*}$.

$$\boxed{\text{A cause is recorded as active only if the injection is outcome-relevant on this tape.}}$$

The filter is applied by re-running the episode with and without the injection and
comparing outcomes. Inactive injections are recorded in $M$ as `inert` and the
corresponding $c$ is set to $0$.

This is the direct structural replacement for the legacy `scene_from_trace`
disaster, where causes were *added* by reconstruction rather than *removed* by
relevance.

---

## 7. Feedback channel

At episode end the feedback channel emits a claimed cause vector

$$\hat C^{fb} \in \{0,1\}^5$$

with error model, error rate $\eta$ frozen at $0.4$ for the primary claim:

* with probability $1-\eta$: $\hat C^{fb}$ names a cause that **is** active —
  possibly not all of them, chosen uniformly among the active set;
* with probability $\eta$: $\hat C^{fb}$ names a cause that is **not** active,
  chosen uniformly among the inactive set.

The channel therefore never emits the empty vector when a fault exists, and
frequently names a wrong cause. This is what makes `DirectFeedback`
(`06-V01R.md` §3) a genuine straw man rather than a parody.

**Substitution condition.** $\text{feedback}_t$ must be replaceable by pure noise
without changing anything else, and that substitution is itself a factor
(`01-OBSERVATION-MODEL.md`, **C3**).

---

## 8. Noise tape and the counterfactual validity rule

This is the most easily-broken part of the design and it is specified exactly.

$$\boxed{\text{The tape is addressed by } (t, \text{role}), \text{ never by draw order.}}$$

Roles: `hazard`, `plant`, `injection`, `feedback`.

Every rollout — factual or intervened — reads the **same slot** $(t, \text{role})$
at step $t$. A `do()` operation therefore changes *what is done with* the draw, not
*which draw is used*. Without this, an intervention that changes the trajectory
length or the number of draws silently shifts every subsequent random value, and
counterfactuals compare two different noise realisations while claiming to hold
noise fixed.

$$\boxed{\text{Two rollouts of the same episode under different } do() \text{ operations must read an identical tape.}}$$

This is asserted mechanically: a test re-runs a factual and an intervened rollout
and checks that the tape access log is identical in $(t, \text{role})$ terms.

---

## 9. Identifiability signature

For `03-IDENTIFIABILITY.md`, the signature of a case under query $q$ is the hash of

$$\bigl(s_t,\ a^{cmd}_t,\ a^{realized}_t,\ r_t,\ \text{feedback}_t\bigr)_{t=0}^{T}$$

— exactly the fields of `01-OBSERVATION-MODEL.md` §2.1, in order, serialised
deterministically. Truth fields ($C$, $M$, $z$, $\epsilon_E$) are **excluded**;
including them would make the matrix trivially injective and the gate vacuous.

---

## 10. Values deferred to per-version preregistration

These are the only numbers not fixed here. Each has a **default** so that a
version cannot accidentally run without one, and each is declared in
`experiments/<version>/config.yaml` before collection.

| quantity | default | rule |
|---|---|---|
| $B_{CF}$ | **4** | one rollout per $z' \neq z$ (3) plus one decision replay (1). The smallest budget that lets a method test every strategy once. The sweep $\{0,1,2,5,20\}$ is tier-2 (`06-V01R.md` §5) |
| $\Delta_{\min}$, AUC-like endpoints | **0.01** | inherited from the legacy `noninferiority_margin`; already the threshold the legacy four-way rule used, so it is not a new invention |
| $\Delta_{\min}$, AUPRC-like endpoints | **0.03** | rarer positives, noisier estimate; declared explicitly rather than silently inheriting 0.01 |
| $N_{\text{eval}}$ | **100** | per checkpoint |
| $\eta$ (feedback error) | **0.4** | §7 |
| $K$ (recovery persistence) | **3** | `05` §8.1 |
| headroom $h$ for $T$ | **0.20** | `05` §6.1 |
| $\lambda, \beta$ (V0.4R only) | declared in V0.4R prereg | `09` §3.2 |

---

## 11. Two definitions that were floating

### 11.1 $R_{\text{module}}$ in the rebuild

The rebuild has no H/L hierarchy (`02-SCM.md` §8), so $R_{\text{module}}$ needs a
referent. It is defined as the **coarsest causal collapse**:

$$R_{\text{module}} = \{\text{process level},\ \text{action level}\}$$

i.e. $R_{\text{causal}}$ with decision and execution merged. This is the
strongest form the legacy H/L hypothesis can take in the rebuild — a two-way
split that is still finer than $R_{\text{trajectory}}$ — and it is the form it
must compete in. If it loses, H/L is finished as an ontology, which is the
outcome `07-V02R.md` §3 was written to allow.

### 11.2 The canonical conversion rule

`07-V02R.md` §4.2 requires one rule, identical across representations, converting
a proposed unit set $\hat R$ into an intervention set:

* a proposed **process** unit converts to $do(z = z')$ where $z'$ is the program
  the representation names; if it names none, $z'$ is the context-appropriate
  program $z^{*}(\kappa)$;
* a proposed **decision** unit $(t)$ converts to $do(d_t = d')$ where $d'$ is the
  alternative the representation names; if it names none, $d'$ is the reference
  policy's action at that state;
* a proposed **execution** unit converts to $do(C_X = \text{identity})$ at the
  implicated $(s^{*}, a^{*})$;
* an empty $\hat R$ converts to $\varnothing$ — change nothing.

The rule is oracle-assisted (it may consult $z^{*}$ and the reference policy),
which is admissible in V0.2R because V0.2R receives cause truth and is scored
against repair truth (`07` §1). It would not be admissible in V0.4R, and it is not
used there.

---

## 12. The reference checkpoint and the reference policy

V0.2R, V0.3R and V0.4R all refer to "the reference" without the source having been
fixed. It is fixed here, and it is a **single shared artifact** so that no version
can quietly use a different one.

### 12.1 $Q^{*}$

A tabular checkpoint trained on the **healthy** environment — no cause injected,
$z = z^{*}(\kappa)$, $C_X$ = identity, no external perturbation — using the
baseline learner to convergence under the $T$-freezing rule of
`05-STATISTICAL-PROTOCOL.md` §6.

$Q^{*}$ is:

* **committed** to `experiments/_shared/reference/`, not regenerated per run;
* **fingerprinted** alongside the source tree (`10` §2), so a version cannot
  silently train against a different reference;
* **frozen**: any change to it voids every experiment that used it, by the same
  rule that voids a seed set.

The learner used to produce $Q^{*}$ is the *baseline*, not any RFL arm. Training
the reference with a treatment arm would bake that arm's assumptions into the
target that every other arm is scored against.

### 12.2 The reference policy

$$\pi_{\text{ref}}(s) = \arg\max_a Q^{*}(s,a)$$

with ties broken by a frozen, declared order. $\pi_{\text{ref}}$ is used for:

* defining a decision fault (a decision deviating from $\pi_{\text{ref}}$ at a
  state where the deviation is outcome-relevant — `Z_D`, §6);
* the canonical conversion rule's fallback alternative (`11` §11.2);
* the `is_deviation` flag in any step trace.

### 12.3 $V_{\text{pre}}$

The recovery endpoints of `05` §8 compare against pre-corruption performance.
$V_{\text{pre}}$ is measured on $Q^{*}$ itself, at the same $N_{\text{eval}}$ and
over the same evaluation scenes as the post-corruption checkpoints, and is stored
with the reference artifact. It is **not** re-measured per run.

---

## 13. Frozen

1. the grid, start, goal, hazard, horizon $H = 12$, step cost;
2. the context lane and its two regimes;
3. the action set and the ill-formed-action rule;
4. the four strategy programs and their properties;
5. the controller/plant split and the three-channel table (§5.2);
6. the feasibility filter (§6.1) — **a cause counts only if it is outcome-relevant**;
7. the feedback error model and $\eta = 0.4$;
8. tape addressing by $(t, \text{role})$ (§8) and the counterfactual validity rule;
9. the identifiability signature (§9), excluding truth fields;
10. the deferred-value table (§10) and its defaults;
11. the $R_{\text{module}}$ referent (§11.1) and the canonical conversion rule (§11.2);
12. $Q^{*}$, $\pi_{\text{ref}}$ and $V_{\text{pre}}$ as one shared, frozen,
    fingerprinted reference artifact (§12).
