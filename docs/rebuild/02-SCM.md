# 02 — Structural causal model

**Status:** FROZEN. Depends on `01-OBSERVATION-MODEL.md`.

This document defines the environment as an explicit structural model with
intervention semantics. The point of writing it as an SCM rather than as a
simulator is that **every causal claim in the project must be expressible as a
`do()` operation on a named variable**, and every such operation must be
executable by the evaluator. If a claim cannot be written that way, it is not a
claim this project can test.

---

## 1. Latent variables

Five exogenous causes, each independently assignable:

| symbol | name | what it means when active |
|---|---|---|
| $Z_P$ | process **commit/routing integrity** | the process/commit layer did **not** faithfully commit the planner's $z^{\text{proposal}}$; $z^{\text{in-force}} \neq z^{\text{proposal}}$ (A55). It does **not** mean the proposal was a bad plan, nor that it was unsuited to the context |
| $Z_D$ | decision | a specific $a^{cmd}_t$ is a poor choice **in its context** |
| $Z_X$ | execution | the body failed to carry out a correct command |
| $Z_E$ | environment | an external perturbation changed the world, not the agent |
| $Z_U$ | unmodelled | a cause the agent's hypothesis space cannot represent |

Plus $M$, the evaluator's fault mask, which records *which timesteps and which
variables* were perturbed. $M$ is bookkeeping, not a cause.

$$Z = (Z_P,\, Z_D,\, Z_X,\, Z_E,\, Z_U) \in \{0,1\}^5,\qquad \text{entries independent}$$

**Multi-label is required.** $Z = (1,1,0,0,0)$ — a bad process *and* a bad local
decision — is a legal episode. The learner's output

$$p = (p_P,\, p_D,\, p_X,\, p_E,\, p_U)$$

is likewise **not required to sum to 1**, and no softmax over the five is
imposed. Any method that internally normalises must report the unnormalised
scores it would have produced, because "sums to 1 over five causes" is a modelling
assumption the spec does not grant.

> **Symbol note.** The vector of fault presence is $Z$; the option set is
> $\mathcal Z$ with element $z$. They are distinguished by case and script. The
> **but-for relevance** vector is $B$ (`11-ENVIRONMENT.md` §6.1) — not $A$, which
> is the action set, and deliberately not called "but-for relevance", because in
> overdetermination two genuinely broken mechanisms can both have $B_i = 0$. The
> name must not promise more than the definition delivers. See
> `12-AMENDMENTS.md` **A13**.

---

## 2. The strategy variable

The legacy design had no object at the process level, which is why "WholeProcess"
degenerated into "two local faults happened to co-occur" and inflated to 68.4% of
failures. The rebuild gives the process level a real, intervenable referent:

$$z \in \mathcal Z,\qquad \boxed{|\mathcal Z| = 4}$$

### 2.1 $z$ is an option, not an action emitter

$$\boxed{\kappa \;\longrightarrow\; z \;\longrightarrow\; Q_D(s, z, m, \cdot) \;\longrightarrow\; a^{cmd}}$$

$z$ is a **strategy/option identifier**. It selects *which slice of the decision
table governs behaviour*; it does not compute $a^{cmd}$ itself.

This is load-bearing and was wrong in the first draft of this specification.

$$\boxed{\text{If } z \text{ emitted actions directly, } Q_D \text{ would not participate in behaviour at all.}}$$

A decision repair ($\Delta Q_D$) would then change no rollout, and the rebuild
would reproduce the legacy failure exactly: *"we repaired the decision precisely
and the task utility did not move"* — because the policy never read the table we
repaired. Writing $d_t = z(s_t, t, \kappa)$ and simultaneously calling
$\Delta Q_D$ a repair is the contradiction; the two cannot both hold.

So the four programs are four **option-conditioned policies**, and the behaviour
chain is:

$$z \;\text{selected by context}\; \longrightarrow\; \pi_D(s) = \arg\max_a Q_D(s, z, m, a) \;\longrightarrow\; a^{cmd}$$

Both levels are now real interventions that change behaviour:

| intervention | changes | does it move the rollout? |
|---|---|---|
| $do(z = z')$ | which slice governs | **yes** — different option, different policy |
| $do(d_t = d')$ | one entry of one slice, one timestep | **yes** — one decision differs |

and neither is expressible as the other. That is what makes "process" a
granularity rather than a sum of locals.

$Q_D(s, z, m, \cdot)$ is one table over $(s, z, a)$; the reference checkpoint
$Q^{*}$ (`11-ENVIRONMENT.md` §12) is trained across all four options, so switching
option at test time selects an already-trained slice rather than an untrained one.

### 2.2 Consequences for the DAG

$$z \to d_1, \ldots, d_T$$

is realised as "$z$ selects the slice, the slice emits the decisions", so a local
decision repair must be a genuine intervention that leaves $z$ intact:

$$do(d_t = d') \quad\text{changes } d_t \text{ only}$$

and a process repair is

$$do(z = z') \quad\text{which changes which slice is read for the whole episode}$$

These are different operations on different nodes.

### 2.3 What makes the four options four *different* policies

A1 fixed the chain $\kappa \to z \to Q_D(s, z, m, \cdot)$ but left a hole that would
have reopened the same failure in a new costume:

$$\boxed{\text{Four slices of one table, with identical action sets and identical reward, converge to the same optimal policy.}}$$

Under tabular Q-learning each slice would be driven to the same fixed point, and
$do(z = z')$ would again change the *name* of the behaviour without changing the
behaviour — the A1 failure, one level down. Worse, `11` §12 trained $Q^{*}$ under
$z = z^{*}$ while `02` §2.1 claimed $Q^{*}$ covers all four options, so it
was not even specified how $z_2$ and $z_4$ acquire a policy.

So an option must **constrain the policy class it governs**:

$$\boxed{A_z(m,s) \subseteq A \quad\text{— the option-specific admissible action set}}$$

An option is a **finite waypoint automaton** carrying obligations; $A_z(m,s)$ is the
set of actions legal under the automaton's current state. Concretely:

| $z$ | obligation the automaton enforces | optimal policy inside the class |
|---|---|---|
| $z_1$ `rush` | none | shortest path, 4 moves |
| $z_2$ `detour_upper` | must visit $(2,1)$ before entering $G$ | upper bypass, 6 moves |
| $z_3$ `wait_then_cross` | must hold at $(1,2)$ until the hazard clears, then cross | 4 moves plus the wait |
| $z_4$ `loop_lower` | must visit $(2,4)$ before entering $G$ | lower loop, 8 moves |

### 2.4 The automata, as transition tables

**Obligation prose is not an automaton.** `11-ENVIRONMENT.md` §4.1 already had to
promote route properties from prose to assertions after A4 and A12; the option
constraints are the same hazard, one level up. `src/rfl_rebuild/env/kernel.py` has
*option constraints* among its responsibilities, so an implementer given only the
table above would have to invent the automaton state, its initial value, when an
obligation discharges, how $A_z$ varies with it, and whether a detour is
recoverable. Those are design decisions that change the experiment.

They are fixed here. See `12-AMENDMENTS.md` **A17**.

#### 2.4.1 Common structure

For each option $z$:

$$M_z = \text{finite automaton state set},\qquad m_0 = 0,\qquad \delta_z(m, s, a, s') = m'$$

$$A_z(m, s) \subseteq A_{\text{legal}}(s)$$

$$A_{\text{legal}}(s) = \{\,a \in A : \text{the move from } s \text{ is inside the grid and not into a wall}\,\}$$

$$\boxed{\text{Every admissible set is a subset of } A_{\text{legal}}(s).}$$

This matters before any DP runs: the environment resolves an illegal action to
`WAIT` and records the illegality (`11` §3). If $A_z$ were allowed to contain
illegal actions, exact DP would treat that resolution rule as part of the
environment and generate spurious ties and Q-entries for moves the agent cannot
make. $z_1$ is therefore $A_{z_1}(m,s) = A_{\text{legal}}(s)$, **not** $A$.

Let `enter(a, s)` denote the cell the agent would occupy. Write
$\text{enter}(a,s) = G$ for "leads into the goal cell".

#### 2.4.2 $z_1$ `rush` — strict static descent

$$M_{z_1} = \{0\},\qquad \delta_{z_1} \equiv 0$$

$$\boxed{A_{z_1}(0,s) = \bigl\{a \in A_{\text{legal}}(s) \;:\; d_G\bigl(\text{enter}(a,s)\bigr) = d_G(\text{cell}(s)) - 1\bigr\}}$$

where $d_G(c)$ is the **static** shortest-path distance from cell $c$ to $G$ over
the open-cell graph — ignoring the hazard, $\kappa$, $\phi$ and $t$, and never
consulting $Q^{*}$ or $z^{*}$.

An earlier revision set $A_{z_1} = A_{\text{legal}}(s)$, i.e. **no obligation at
all**. The exact DP immediately showed what that means: the optimal policy *inside*
$z_1$ is the unconstrained optimum, so $z_1$ dominated every specialised option,
the context-appropriate option was constant, and `rush` under $\kappa=1,\phi=2$
played `RIGHT, WAIT, RIGHT, RIGHT, RIGHT` — it waited out the hazard and succeeded.
A rush that waits is not a rush. See `12-AMENDMENTS.md` **A39**.

Strict descent implies $\texttt{WAIT} \notin A_{z_1}$ and excludes any temporary
detour to dodge the hazard. From $S$ it is exactly `RIGHT, RIGHT, RIGHT, RIGHT`.
It is still a *process* rather than a hard-coded trajectory: if an execution fault
displaces the agent, it resumes descending from wherever it now is rather than
deadlocking.

**Why this is not tuning the environment to pass a test.** The constraint reads no
result — not $Q^{*}$, not $z^{*}$, not `hazard_at`, not the reward. It expresses a
pre-declarable behavioural commitment: *rush always advances along the static
shortest path; it does not wait and does not detour.* The environment then decides
for itself in which contexts that commitment is good and bad. That is categorically
different from "if a hazard is detected, forbid action $a$", which would write the
answer into the option.

**Consequence worth recording:** $A_{z_1}$ is a **singleton** at most cells, so
under `rush` there is often no alternative action available for a decision fault.
$Z_D$ injections must be made under an option with room — see the note in
`12-AMENDMENTS.md` **A39**.

#### 2.4.3 $z_2$ `detour_upper` — visit $(2,1)$ before $G$

$$M_{z_2} = \{0, 1\}$$

| $m$ | meaning | $A_{z_2}(m,s)$ |
|---|---|---|
| 0 | waypoint $(2,1)$ not yet visited | $A_{\text{legal}}(s) \setminus \{a : \text{enter}(a,s) = G\}$ |
| 1 | visited | $A_{\text{legal}}(s)$ |

$$\delta_{z_2}(m, s, a, s') = \begin{cases} 1 & m = 0 \ \text{and}\ s' = (2,1)\\ m & \text{otherwise}\end{cases}$$

#### 2.4.4 $z_3$ `wait_then_cross` — hold until the hazard clears

Let $\text{clear}(s)$ be the observable predicate *"the hazard does not occupy
$(2,2)$ at this timestep"* (hazard occupancy is part of $s$ and is visible).

$$M_{z_3} = \{0, 1\}$$

| $m$ | meaning | $A_{z_3}(m,s)$ |
|---|---|---|
| 0 | not yet cleared to cross | $A_{\text{legal}}(s) \setminus \{a : \text{enter}(a,s) \in \{(2,2),\, G\}\}$ |
| 1 | cleared | $A_{\text{legal}}(s)$ |

$$\delta_{z_3}(m, s, a, s') = \begin{cases} 1 & m = 0 \ \text{and}\ s = (1,2) \ \text{and}\ \text{clear}(s)\\ m & \text{otherwise}\end{cases}$$

#### 2.4.5 $z_4$ `loop_lower` — visit $(2,4)$ before $G$

$$M_{z_4} = \{0, 1\}$$

| $m$ | meaning | $A_{z_4}(m,s)$ |
|---|---|---|
| 0 | waypoint $(2,4)$ not yet visited | $A_{\text{legal}}(s) \setminus \{a : \text{enter}(a,s) = G\}$ |
| 1 | visited | $A_{\text{legal}}(s)$ |

$$\delta_{z_4}(m, s, a, s') = \begin{cases} 1 & m = 0 \ \text{and}\ s' = (2,4)\\ m & \text{otherwise}\end{cases}$$

#### 2.4.6 Detours are recoverable

All four automata are **monotone**: $m$ never decreases, and every obligation is
discharged by reaching a cell that remains reachable from anywhere the agent can
wander. Nothing is irreversible except the fault itself. That is deliberate — a
non-recoverable obligation would make a decision fault indistinguishable from a
process fault, which is the distinction the whole design rests on.

#### 2.4.7 $do(d_t)$ may **not** escape the option obligation

$$\boxed{do(d_t = d') \text{ is well-formed} \iff d' \in A_{z}(m_t, s_t)}$$

where $m_t$ and $s_t$ are the **factual** prefix's automaton state and environment
state at $t$.

A local decision intervention changes **one decision inside the current option**;
it does not lift the option's constraint. The alternative — allowing
$do(d_t = d')$ with $d' \notin A_z(m_t,s_t)$ — would let a nominal *decision*
repair deliver a *process* repair, because escaping the obligation is precisely
what changing $z$ does. Local and process granularity would merge again, and P3/P4
would stop distinguishing anything.

**Consequences, which are intended:**

* an ill-formed $d'$ is rejected at generation and recorded in the exclusion
  table of the identifiability artifact (`03` §4). It is not silently clamped;
* when the option itself is wrong, **no local decision intervention can rescue
  the episode**, because every legal local action still respects the obligation.
  That is exactly what a process fault means, and it is what makes P4 satisfiable
  without contrivance;
* $do(z = z')$ remains unrestricted over $\mathcal Z$: it changes the automaton,
  and therefore the admissible sets, and therefore the reachable behaviour.

This is the frozen answer to the question the review posed. See
`12-AMENDMENTS.md` **A17**.

$Q_D$ is defined **only for $a \in A_z(m,s)$**, and because $A_z$ depends on $m$,
**$m$ is part of the decision state**:

$$\boxed{Q_D(s, z, m, a)},\qquad \boxed{\pi_D^{*}(s, z, m) = \arg\max_{a \in A_z(m,s)} Q_D^{*}(s, z, m, a)}$$

### 2.3.1 Why $m$ cannot be dropped

An earlier draft wrote $Q_D(s,z,a)$ and $\pi_D^{*}(s,z)$ while simultaneously
letting $A_z$ depend on $m$. Those are inconsistent, and the counterexample is
immediate. Take $z_2$ (obliged to visit $(2,1)$ before $G$) at one physical state
$s = (3,2)$:

$$m = 0:\ \texttt{RIGHT} \notin A_{z_2}(m,s) \qquad\qquad m = 1:\ \texttt{RIGHT} \in A_{z_2}(m,s)$$

The same $(s, z_2)$ admits $\texttt{RIGHT}$ in one automaton state and forbids it
in the other. No single $Q_D(s, z, m, \cdot)$ can be correct for both, so
$(s,z)$ is **not a sufficient statistic** and the representation would not be
Markov. See `12-AMENDMENTS.md` **A22**.

### 2.3.2 The learner's control state, and no third category of information

The learner must be able to evaluate $A_z(m,s)$ and index $Q_D(s,z,m,\cdot)$, so
$z$ and $m$ must be available to it:

$$x^{D}_t = (s_t,\; z_t,\; m_t) \quad\text{— the learner-visible internal control state}$$

$z_t$ and $m_t$ are **not sensor observations**; they are the agent's own control
commitments. That is exactly the status of $a^{cmd}_t$ (`01-OBSERVATION-MODEL.md`
§2.3), and the same argument applies: a system knows which option it committed to
and what obligations it is carrying. Hiding one's own control state from oneself
is manufactured partial observability, not modelled partial observability.

Two consequences, both binding:

1. **They enter the identifiability signature's usable information set**
   (`03-IDENTIFIABILITY.md` §2.1). A field the policy may read but the
   identifiability analysis may not is an undeclared third category, and `01` §2.2
   forbids exactly that: every field is either in `obs` or in the hidden set.
2. **$Z_P$ does not become trivial — but not for the reason first written here.**
   An earlier revision said the fault is "in the *match* between $z$ and the
   state, not in $z$ itself", i.e. that knowing the option in force leaves open
   whether it was the right one for the context. **A55 removed that reading.**
   $Z_P$ is a **commit/routing integrity fault**:

   $$\kappa \rightarrow z^{\text{proposal}} \rightarrow C_P \rightarrow z^{\text{in-force}} \rightarrow Q_D(s,z,m,\cdot) \rightarrow a^{cmd}$$

   Healthy means $C_P(z^{\text{proposal}}) = z^{\text{proposal}}$, and
   $Z_P^{\text{fire}} = \mathbf 1[z^{\text{in-force}} \neq z^{\text{proposal}}]$.
   The proposal itself is **not** required to be optimal or even correct: the
   fault is an unfaithful commit, not a bad plan. So $Z_P$ stays non-trivial for
   a structural reason — $I_t$ exposes $z^{\text{in-force}}$ but **not**
   $z^{\text{proposal}}$ — and a learner must spend a process-proposal audit
   (`03` §3.1) to see the commit edge. "Was this option right for the context?"
   is a *different*, normative question (`11` §6.4) and is not $Z_P$.

Note that $m$ depends on the trajectory ($\delta_z$ consumes $s'$), so $x^D$ is
deterministic given the episode; it carries no information about the fault beyond
what $s$ and $z$ already carry.

Because the four admissible sets differ, their optimal policies differ on states
they share — $z_1$ and $z_4$ both pass through $(1,2)$ and both head for $G$, but
$z_4$ cannot enter $G$ until it has visited $(2,4)$. The options are therefore
genuinely different **policy classes**, not four names for one policy, and

$$do(z = z') \;\text{changes } A_z \;\Longrightarrow\; \text{changes reachable behaviour}$$

Two consequences that bind the rest of the specification:

**Decision faults are defined relative to the current option.** A decision fault
is a deviation from $\pi_D^{*}(\cdot, z, m)$ **for the $z$ actually in force**:

$$\text{decision fault at } t \iff a^{cmd}_t \neq \pi_D^{*}(s_t, z_{\text{current}}, m_t)$$

Defining it against a single global reference policy would re-create the
process/decision overlap the whole rebuild exists to remove: an episode with a
wrong $z$ would have its *locally correct* actions re-labelled as decision faults,
and the two fault kinds would be entangled again. See `12-AMENDMENTS.md` **A9**.

**The reference is option-conditioned**, which retires the single global reference
policy of `11` §12.2 as one object: it becomes the family
$\{\pi_D^{*}(\cdot, z, m)\}_{z \in \mathcal Z}$, and the canonical conversion rule of
`11` §11.2 uses the member indexed by the current $z$.

---

## 3. The execution system

Execution is not a label on a decision. It is a separate mechanism with its own
parameters:

$$\pi_D:\; s \to a^{cmd} \qquad\qquad C_X:\; (s, a^{cmd}) \to u \qquad\qquad P:\; (s, u, \epsilon_E) \to a^{realized}$$

* $C_X$ is a **learnable tabular controller**. Its parameters are distinct from
  $Q_D$, and updating it is $\Delta C_X$, never $\Delta Q_D$.
* $P$ is the plant. External faults enter through $\epsilon_E$.

This split yields two failure modes that the legacy code could not distinguish:

| mode | condition | correct response |
|---|---|---|
| **internal controller fault** | $C_X$ produced a wrong $u$ | update $C_X$; **do not touch $Q_D$** |
| **external plant fault** | $C_X$ was right, $P$ misbehaved | environment / unmodelled; **default: update nothing** |

The second row is a first-class **external-fault control condition**, not an
awkward special case. Under $Z_E$ or $Z_U$ the correct behaviour is frequently to
make no edit at all, and an arm that edits anyway is measurably wrong.

---

## 4. Cause truth and repair truth are different objects

This distinction is new and load-bearing.

$$Z = (Z_P, Z_D, Z_X, Z_E, Z_U) \qquad\text{— \textbf{fault presence}: what is broken}$$

$$R^{*} = \text{minimal sufficient intervention set} \qquad\text{— \textbf{repair truth}: what must change}$$

They are both evaluator truth and they are **not** the same set. A broken decision
may be repairable by a process change; an execution fault whose controller is
already optimal may be unrepairable.

This is exactly the split the four-version chain needs:

$$\text{V0.1R predicts } Z^{\text{fire}} \qquad\qquad \text{V0.2R predicts } R^{*}$$

and it removes a confusion that ran through the whole legacy project, where
"attribution" was asked to be simultaneously a diagnosis and a prescription.

---

## 5. The intervention lattice, and what `WholeProcess` actually means

The admissible intervention space is

$$\mathcal I = \underbrace{\{do(z = z')\}_{z' \in \mathcal Z}}_{\text{strategy replay}} \;\cup\; \underbrace{\{do(C_P = \text{identity})\}}_{\text{process repair}} \;\cup\; \underbrace{\{do(d_t = d')\}_{t, d'}}_{\text{decision}} \;\cup\; \underbrace{\{do(C_X(s, a) = a)\}_{(s,a)}}_{\text{execution}} \;\cup\; \{\varnothing\}$$

with $\varnothing$ meaning *change nothing* — which is a legal repair and must be
a legal answer.

### 5.0 $do(C_P = \text{identity})$ is the process repair, and it is evaluator-only

**A55.** Replacing the in-force option is *not* the same operation as repairing
the commit layer, and the earlier lattice conflated them by having only
$do(z=z')$ under "process":

$$\boxed{do(C_P = \text{identity}) \quad\text{restores}\quad z^{\text{in-force}} = z^{\text{proposal}}}$$

| operation | what it does | whose |
|---|---|---|
| $do(z = z')$ | runs option $z'$ for the whole episode, bypassing the commit edge | **learner's** — *strategy replay* |
| $do(C_P = \text{identity})$ | restores a faithful commit, leaving $z^{\text{proposal}}$ untouched | **evaluator's** — process repair |
| $\mathrm{audit\_process\_proposal}()$ | reports $z^{\text{proposal}}$; changes nothing | **learner's**, cost 1 |

They must not be conflated (`11` §6.4). Strategy replay changes the answer for
reasons that have nothing to do with integrity — it replaces the option outright
— so treating it as a process repair would let $R^{*}$ claim credit for a
strategy change while nominally fixing a commit. And $do(C_P=\text{identity})$
stays **out of the learner's query set**: admitting it would be
$do(Z_P{=}\text{off})$, which certifies $B$ by handing over the very operation
that defines it (`12-AMENDMENTS.md` **A51**).

Note that $do(C_P=\text{identity})$ is what the but-for construction for $B_P$
already evaluates (`kernel.but_for_relevance`, the `Z_P` trial): dropping the
option fault restores a faithful commit. So the repair primitive and the but-for
construction coincide here by construction, not by accident — and that is exactly
why the *learner* may not have it.

**A57 makes it first-class in the code, not just in this lattice.** It is
`Intervention(kind="process_commit")`, built by `Intervention.commit_identity()`,
with its **own structural node** `("process_commit",)` distinct from
`("process",)`. That matters mechanically: it counts toward repair cardinality
$|r|$, it composes into joint candidates such as
$\{do(C_P{=}\text{identity}), do(d_t{=}d')\}$, the `InterventionSet`
node-collision rule covers it, and $R^{*}_{\text{suff}}$ can express a process
repair in the same type as every other member. Simulating it with a boolean flag
would have distorted all four.

The rollout priority is frozen as

$$\boxed{do(z{=}z') \;>\; do(C_P{=}\text{identity}) \;>\; Z_P\ \text{fault} \;>\; z^{\text{proposal}}}$$

Strategy replay is a downstream root intervention that specifies
$z^{\text{in-force}}$ outright; the commit repair restores the
proposal→commit identity and therefore **shadows** the fault. When both are
present strategy replay wins and the commit repair is merely shadowed — that is a
legal composition, not MALFORMED, and it is why the two carry distinct nodes.

### 5.1 The execution primitive acts on one cell

$$\boxed{do\bigl(C_X(s^{*}, a^{cmd}) = a^{cmd}\bigr) \text{ is the execution primitive}}$$

Not $do(C_X = C')$. The first draft wrote the latter, which reads as *replace the
entire controller table*, and that breaks the lattice:

| primitive | scope of a size-1 repair |
|---|---|
| $do(d_t = d')$ | **one** decision at **one** timestep |
| $do(C_X = C')$ | **every** cell of the controller |
| $do(C_X(s^{*},a^{cmd}) = a^{cmd})$ | **one** cell |

Under the second row a single execution repair could fix an arbitrarily large
controller while a single decision repair fixes one step, and $|R^{*}|$ would no
longer be comparable across fault kinds — a size-1 execution repair would be
"cheaper" only because it silently does more work. Narrowing to one cell makes the
cardinality mean the same thing everywhere.

See `12-AMENDMENTS.md` **A7**.

A **repair** is a finite subset $r \subseteq \mathcal I$. It is **sufficient** iff
the episode succeeds under $do(r)$. The **minimal sufficient set** is

$$R^{*} = \arg\min_{r \text{ sufficient}} |r|$$

### 5.0.1 Joint interventions: fixed before the rollout, validated on the counterfactual

The well-formedness rule of §2.4.7 is stated for a single intervention. $R^{*}$ is
a *set*, and a set has semantics that a singleton does not. An earlier draft
checked each member against the **factual** prefix, which is wrong as soon as the
set has two members:

* $do(d_2 = a')$ changes the trajectory, so at $t=5$ the counterfactual state
  $(s_5^{cf}, m_5^{cf})$ generally differs from the factual one;
* checking $do(d_5 = b')$ against the factual prefix may therefore repair a
  decision that **does not exist** in the counterfactual run, or write an action
  that is **no longer admissible** there.

**Frozen semantics:**

$$\boxed{\text{the intervention set } r \text{ is fixed once, before the rollout}}$$

The SCM is then advanced in time order; when the rollout reaches an intervened
$t$, validity is checked against the **current counterfactual**

$$d' \in A_{z}\bigl(m_t^{cf},\, s_t^{cf}\bigr)$$

If any member fails, the **entire candidate is marked `MALFORMED`** — not
silently clamped, not skipped, not partially applied. Two interventions targeting
the same structural node are `MALFORMED` as well, since their composition is not
defined.

`MALFORMED` candidates are excluded from $R^{*}$ and counted in the exclusion
table of the identifiability artifact (`03` §4). See `12-AMENDMENTS.md` **A24**.

### 5.0.2 The fault generator obeys the same constraint

A17 fixed the *counterfactual* side but left the *generator* free to violate its
own option. `11-ENVIRONMENT.md` §6 required only that a decision fault's $a'$ be
*physically legal*, which lets a nominal "decision fault" step outside the option
obligation — that is, perform a process-level change while being labelled local,
and the two granularities collapse again.

A decision fault is therefore

$$\boxed{a' \in A_z(m_t, s_t) \setminus \{\pi_D^{*}(s_t, z, m_t)\}}$$

within the option, not adjacent to it.

### 5.1 The corrected definition of a process fault — and of process *granularity*

Two different statements used to share one formula here. A55 separates them.

**What $Z_P$ is** (the fault, §1 and `11` §6.4): a commit/routing integrity
failure, $z^{\text{in-force}} \neq z^{\text{proposal}}$. Its repair is
$do(C_P = \text{identity})$, evaluator-only.

**What "the process is the right granularity" is** (a statement about the repair
lattice, *not* the definition of $Z_P$):

$$\boxed{\text{process-granularity repair} \iff \exists\, z' : \{do(z=z')\} \text{ suffices, and no single local intervention suffices}}$$

That is: **the process is the right level to intervene at** — not "two things are
broken". It is *not* defined as $|R^{*}| > 1$, and it is **not** the definition of
$Z_P$. A run can have process-granularity repair available with no commit fault at
all, and a commit fault can be repairable by a single local intervention. Reading
the formula as a definition of $Z_P$ is precisely the conflation A55 removes:
$do(z=z')$ replaces the option outright, whereas $do(C_P=\text{identity})$ repairs
the commit edge and leaves $z^{\text{proposal}}$ alone.

This is the direct fix for the legacy failure, where the definition effectively
became "minimal size > 1", and where a reconstruction bug then manufactured
multi-fault episodes until they were 68.4% of the data. Under §5.1 a single
co-occurring pair of independent local faults is a *size-2 repair whose members
are each independently sufficient*, i.e. $|R^{*}| = 1$ with two candidates — see
invariant **I3** in `04-SEMANTIC-INVARIANTS.md`.

### 5.2 Ties are first-class

When several size-1 repairs each suffice, $R^{*}$ is a **set of candidates**, not
a chosen one:

$$|R^{*}| = 1 \text{ (size)},\qquad \#\text{candidates} = k \ge 1$$

The evaluator reports both numbers separately. Any metric that assumes a unique
repair is ill-defined and is prohibited.

---

## 6. Forward generation only

The evaluator must **never** re-derive a cause from a trace. Every episode is
generated forward:

1. assign $Z$ and $M$ exogenously;
2. assign $z$ (or perturb it if $Z_P$ active);
3. assign controller state and any $Z_X$ perturbation;
4. roll out $z \to d_1..d_T \to a^{cmd} \to u \to a^{realized}$;
5. carry $Z$, $M$, $z$, and the true $a^{cmd}$ alongside the trace as **truth
   fields**, never as reconstructed fields.

$$\boxed{\text{No cause is ever inferred from the trace, even by the evaluator.}}$$

The legacy `scene_from_trace` was exactly this prohibited step, and it produced
the `WholeProcess` inflation. It has no counterpart here: if the evaluator wants
to know $Z_D$ it reads the assignment it made, not the rollout.

### 6.1 Reconstruction is permitted only as a checked inverse

One operation is allowed: given a trace and the truth fields, verify that the
forward model reproduces the trace exactly. This is a **test**, not a source of
labels (`04-SEMANTIC-INVARIANTS.md`, invariant **I5**).

---

## 7. Reward

Task reward is terminal plus a **per-step cost** (`11-ENVIRONMENT.md` §1 fixes it
at $-0.02$), with two terminal modes as a secondary factor (see `06-V01R.md` §6
for why reward is demoted out of the main line):

$$R^{(A)}: \text{success } +1,\ \text{failure } -1 \qquad\qquad R^{(B)}: \text{success } +1,\ \text{failure } 0$$

### 7.1 The affine equivalence does **not** hold here

An earlier draft claimed the two modes are affine transforms and therefore induce
the same optimal policy:

$$\mathbb{E}[R^{(A)}] = 2P(S) - 1, \qquad \mathbb{E}[R^{(B)}] = P(S) \qquad\text{— \textbf{withdrawn}}$$

**That argument ignored the step cost.** Write $L$ for the number of steps the
policy actually takes, which is policy-dependent — the three route lengths differ
(4 / 6 / 8, `11` §1). Then the returns are

$$G_A = 2\cdot\mathbf{1}_{\text{success}} - 1 - 0.02\,L, \qquad\qquad G_B = \mathbf{1}_{\text{success}} - 0.02\,L$$

so

$$\mathbb{E}[G_A] = 2P(S) - 1 - 0.02\,\mathbb{E}[L], \qquad \mathbb{E}[G_B] = P(S) - 0.02\,\mathbb{E}[L]$$

and $2\,\mathbb{E}[G_B] - 1 = 2P(S) - 1 - 0.04\,\mathbb{E}[L] \neq \mathbb{E}[G_A]$
whenever $\mathbb{E}[L] \neq 0$. **The two objectives are not affine transforms of
one another, and they do not in general share an optimal policy.** See
`12-AMENDMENTS.md` **A14**.

### 7.2 What follows

1. **The step cost stays.** It is what makes the short corridor better than the
   bypass when both are safe, and therefore what gives the option semantics of
   §2.3 any content. Removing it would collapse $z_1$ and $z_4$ onto the same
   return.
2. **"Same optimal policy" is retracted**, and with it the reason the legacy
   Alpha pilot found the modes equivalent — that reason was an artefact of the
   legacy environment having no policy-dependent step cost, and it does not carry
   over.
3. **Reward × Update becomes a genuine secondary factorial** between two
   *different objectives*, not a null manipulation. It therefore cannot be used
   as a "does reward matter" probe; it asks which objective, crossed with which
   update rule, performs better, and the answer may legitimately be that they
   differ.
4. The update-dynamics ledger (`10-REPRODUCIBILITY-AND-OPS.md` §4) remains
   mandatory, because the two objectives still differ in TD-error scale
   independently of the policy argument above.

---

## 8. Hierarchy: demoted, not deleted

The legacy H/L (high-level plan / low-level action) split is **not the ontology**
of the rebuild. It survives as one candidate credit representation:

$$R_{\text{module}}$$

competing in V0.2R against $R_{\text{trajectory}}$, $R_{\text{causal}}$ and
$R_{\text{repair}}$. If it loses on the V0.2R endpoints, it is removed. What is
prohibited is starting from it as an assumption.

---

## 9. Frozen

This document fixes structure. The **concrete instantiation** — the grid, the
four strategy programs, the controller parameterisation, the feedback error model,
the tape-addressing rule — is fixed separately in `11-ENVIRONMENT.md`, so that
every version runs on one environment and results stay comparable.

1. the five exogenous causes and their independence;
2. multi-label $C$, and $p$ not summing to 1;
3. $|\mathcal Z| = 4$, discrete and fully enumerated;
4. the DAG $z \to d_1..d_T$, and $do(d_t)$ being a local intervention;
5. the three-part execution system $\pi_D / C_X / P$, with $C_X$ learnable and
   parameter-disjoint from $Q_D$;
6. the separation of cause truth $C$ from repair truth $R^{*}$;
7. the intervention lattice $\mathcal I$ and the definition §5.1;
8. forward generation only (§6);
9. $R^{*}$ as a candidate set with ties (§5.2).
