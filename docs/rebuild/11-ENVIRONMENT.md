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
Coordinates are $(x, y)$ with $x$ the column.

```
          x=0   x=1   x=2   x=3   x=4
  y=0      #     #     #     #     #
  y=1      #     .     .     .     #
  y=2      S     .     ·     .     G       · = contested cell
  y=3      #     .     #     .     #
  y=4      #     .     .     .     #
```

Hand-verified routes from $S$ to $G$, with move counts:

| route | path | moves |
|---|---|---:|
| short corridor | $(0,2)\,(1,2)\,(2,2)\,(3,2)\,(4,2)$ | **4** |
| upper bypass | $(0,2)\,(1,2)\,(1,1)\,(2,1)\,(3,1)\,(3,2)\,(4,2)$ | **6** |
| lower loop | $(0,2)\,(1,2)\,(1,3)\,(1,4)\,(2,4)\,(3,4)\,(3,3)\,(3,2)\,(4,2)$ | **8** |

Every listed step is between adjacent open cells. The walls at $(2,1)$ and
$(2,3)$ are what force the upper bypass to commit at $(1,2)$ and the lower loop to
commit at $(1,3)$ — neither can rejoin the short corridor except at $(3,2)$.

> **Corrected.** The first draft drew the side walls at $(1,1)$ and $(1,3)$
> instead of $(2,1)$ and $(2,3)$. Under that map the "sidestep around the
> contested cell" was **physically impossible**: from $(1,2)$ both $(1,1)$ and
> $(1,3)$ were walls, and the only cell from which the contested cell can be
> avoided is $(2,2)$ itself — the cell the hazard occupies. The property was
> asserted in prose without a route being walked. See `12-AMENDMENTS.md` **A4**.

A **hazard** occupies the contested cell $(2,2)$ at deterministic timesteps given
the tape and the context (§2).

$$H = 12 \quad\text{(episode length, fixed)}$$

A step cost of $-0.02$ applies, terminal reward as in `02-SCM.md` §7. Success
requires reaching $G$ **without** occupying a cell the hazard occupies at that
timestep.

$$\boxed{s_t = (x_t,\; y_t,\; t,\; \kappa,\; \phi)} \qquad 5 \times 5 \times 13 \times 2 \times 6 = 3900 \text{ states}$$

fully enumerable. (The factor 13 is $H+1$ for the timestep, 2 for the context
lane, 6 for the hazard phase $\phi$ of §2.)

> **Why $\phi$ is in the state.** An earlier draft put the hazard phase on the
> tape and left it out of $s_t$, keeping only the *current* occupancy. That
> breaks the Markov property: two episodes can share
> $(x, y, t, \kappa, \text{occupancy now})$ and still have different *future*
> hazard schedules, so $P(s_{t+1} \mid s_t, a_t)$ is not well defined by
> $s_t, a_t$ alone. Both tabular Q-learning and ordinary finite-horizon DP would
> be solving the wrong object, and they would agree with each other while doing
> it — the hardest kind of error to notice. See `12-AMENDMENTS.md` **A23**.

Hazard occupancy at time $t$ is then a deterministic function of the state:

$$\text{hazard\_at}(t,\kappa,\phi) = \mathbf{1}\bigl[t \equiv \phi \pmod{p(\kappa)}\bigr]$$

---

## 1.1 The order of events within one step

The state is Markov (A23), but a Markov state does not by itself say *what happens
in what order inside a step*. Two readings are both consistent with everything
written so far, and they differ observably:

$$\text{hazard check at } t \to \text{action} \qquad\text{vs.}\qquad
\text{action} \to s_{t+1} \to \text{hazard check at } t+1$$

They change when `rush` collides, what $\text{clear}(s)$ means, how $z_3$ behaves,
which of P1–P4 have witnesses, and — later — the Bellman target. The kernel cannot
choose this; it is frozen as:

$$\boxed{
(s_t, z, m) \to a^{cmd}_t \to u_t \to a^{realized}_t \to (x_{t+1}, y_{t+1}) \to t{+}1 \to \text{hazard check} \to \text{terminal/reward} \to m_{t+1}
}$$

Reading it out:

1. the option and automaton state select $A_z(m, s_t)$ and the policy picks
   $a^{cmd}_t$;
2. the controller and plant produce $u_t$ then $a^{realized}_t$ (§5);
3. the **realized** action moves the agent;
4. $t$ advances;
5. **the hazard is then checked against the newly occupied cell**, not the cell
   the agent left;
6. terminal conditions and reward are evaluated;
7. finally the option automaton updates on $s_{t+1}$ (§2.4).

**Consequences that must be read off this order, not guessed:**

* **an agent occupying the contested cell at step $t$ is caught by the hazard at
  step $t$, evaluated after its own move into that cell.** `rush` arrives at
  $(2,2)$ at $t=2$ and is caught there if `hazard_at$(2,\kappa,\phi)=1$`;
* $\text{clear}(s)$ in $z_3$ (§2.4.4) tests **the hazard at the current step**, so
  "wait until clear, then move" means the agent may enter $(2,2)$ on the following
  step only if the hazard has left by then;
* the automaton updates **last**, on $s_{t+1}$, so an obligation discharged by the
  move just made is available to the next decision — which is what makes the
  waypoint automata of §2.4 work as intended.

See `12-AMENDMENTS.md` **A29**.

---

## 2. Context lane

Each episode carries an observable context $\kappa \in \{0,1\}$ and an observable
hazard phase $\phi \in \{0,\dots,5\}$, both drawn per episode and both part of
$s_t$ (§1):

| $\kappa$ | meaning | period $p(\kappa)$ | hazard occupies $(2,2)$ at |
|---|---|---|---|
| 0 | slow patrol | 6 | $t \equiv \phi \pmod 6$ |
| 1 | fast patrol | 3 | $t \equiv \phi \pmod 3$ |

$\phi$ is drawn uniformly over $\{0,\dots,5\}$ and is the **only** hazard
randomness: it is a tape key (`§8.1.1`), it is visible, and it lives in the state.
The earlier draft's fixed phase offsets are gone — a fixed phase is not a
distribution over schedules, and the tape was described as supplying uncertainty
about occupancy while the schedule was simultaneously described as frozen. Both
could not be true.

$\kappa$ and $\phi$ together are what make "context-appropriate" a real property:
the same option can be right for one $(\kappa,\phi)$ and wrong for another.

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

## 4. The four options

$z$ is an **option identifier** (`02-SCM.md` §2.1). Each option is a slice of the
decision table, $Q_D(s, z, m, \cdot)$, not a script that emits actions.

$$\boxed{|\mathcal Z| = 4,\ \text{enumerated in full}.}$$

| $z$ | name | intent | the property it must witness |
|---|---|---|---|
| $z_1$ | `rush` | strict static descent toward $G$ | **P1a/P1b/P1c** — see §4.2 |
| $z_2$ | `detour_upper` | commit at $(1,2)$ to the upper bypass | **P2** locally improvable: an episode with $|R^{*}| = 1$ whose unique member is a *decision* intervention |
| $z_3$ | `wait_then_cross` | hold at $(1,2)$ until the hazard clears | **P3** genuinely different: succeeds on a $(\kappa, \text{tape})$ where $z_1$ fails, and is unreachable from $z_1$ by any size-1 local intervention |
| $z_4$ | `loop_lower` | commit at $(1,3)$ to the lower loop | **P4** process granularity: an episode where **no size-1 local Decision or Execution intervention** suffices, but some $do(z = z')$ does |

### 4.1 Properties are asserted, not described

The first draft of this section described the four programs in prose and stated
that "`long_way` fails by timeout" two lines after stating that $z_3$ and $z_4$
succeed under both contexts. Both claims cannot hold, and with an 8-move route
under $H = 12$ the timeout claim was simply false. See `12-AMENDMENTS.md` **A4**.

Prose descriptions of route properties are how the map defect of §1 survived
review. So the properties are promoted to **assertions the generator must
witness**, discharged by exhaustive enumeration:

```python
# scripts/route_check.py  -- must pass after the kernel and the exact DP, and before Gate E/L
for z, kappa, tape in product(Z, KAPPA, CANONICAL_TAPES):
    trace = rollout(z=z, kappa=kappa, tape=tape)
    ...
assert witness_exists("P1"); assert witness_exists("P2")
assert witness_exists("P3"); assert witness_exists("P4")
```

The check enumerates the full product and reports, for each property, a concrete
witness $(\kappa, \text{tape}, \text{injection})$. A property with no witness is a
**gate failure**, not a note.

### 4.2 Status of the four properties

$$\boxed{\text{All four are enumeration-pending. None is claimed.}}$$

| property | status |
|---|---|
| P1 | **restated over the full context** by A39 as P1a/P1b/P1c below — **to be witnessed** |
| P2 | **A40**: a *singleton* Decision minimal repair must **exist**; uniqueness is explicitly **not** required — **to be witnessed** |
| P3 | **withdrawn as a claim** — see below — **to be witnessed** |
| P4 | **never claimed** — **to be witnessed**, with a defined failure mode |

**P1, restated over the full context (A39).** The earlier form — *"`rush` succeeds
under $\kappa=0$ and fails under $\kappa=1$"* — is the wrong predicate once $\phi$
is in the state: what decides whether the short corridor is safe at $t=2$ is the
pair $(\kappa,\phi)$, not $\kappa$ alone.

$$\text{P1a}:\quad \neg\text{hazard\_at}(2,\kappa,\phi) \;\Rightarrow\; \text{4-step success}$$

$$\text{P1b}:\quad \text{hazard\_at}(2,\kappa,\phi) \;\Rightarrow\; \text{collision at the contested cell on step 2}$$

$$\text{P1c}:\quad \bigl|\{\,z^{*}(s_0(\kappa,\phi)) : \kappa \in \{0,1\},\ \phi \in \{0,\dots,5\}\,\}\bigr| \;\ge\; 2$$

P1a and P1b verify that `rush` really is a rush. **P1c verifies that the
context-appropriate option is not a constant**, which is what closes the A39
degeneracy. P1c deliberately does **not** require a particular winner in the
hazardous contexts — whether `wait_then_cross`, `detour_upper` or a tie wins is
for the DP to report, not for the environment to arrange.

**P2, restated by A40 — existence, not uniqueness.**

$$\exists e:\quad \min_{r\,\text{sufficient}} |r| = 1 \quad\wedge\quad \exists r \in R^{*}(e),\ r = \{do(d_t = d')\}$$

$$\boxed{\#R^{*} = 1 \text{ is \textbf{not} required.}}$$

Multiple tied size-1 repairs are first-class (`02-SCM.md` §5.2), and any metric
assuming a unique repair is prohibited there. Demanding uniqueness here would
contradict the repair-truth ontology and, worse, would require editing the map until
repairs became unique — deleting exactly the tie cases V0.2R's tie-handling
endpoint exists to face.

**P2 is a coverage gate, not a result.** It asks whether this benchmark contains
the object *"a local Decision-level repair"* at all. It does not ask whether a
Decision is the only correct explanation; that is V0.2R's question. A weak P2 is
correct; making P2 look like a main hypothesis would be the error. P1–P4 all
establish that the environment **can express** a mechanism, not that RFL works.

The size-1 family is enumerated as $\mathcal F_1 = \mathcal F_{\text{process}} \cup
\mathcal F_{\text{decision}} \cup \mathcal F_{\text{execution}}$ — omitting the
process family, as an earlier revision did, leaves any claim about $R^{*}$'s
size-1 candidates unsupported. `route_check` reports candidate count, unique-site
count and per-kind counts as **diagnostics**; ties are described, never penalised.

An earlier draft graded these "available / available / not established". That
grading was wrong on P3 and incoherent on P4, in two separate ways.

**P4 was a logical contradiction.** It was written as *"no size-1 intervention of
any kind suffices, but some $do(z=z')$ does"* — but $do(z=z')$ **is** an element
of the intervention lattice (`02-SCM.md` §5) and therefore **is** a size-1
intervention. The property was unsatisfiable by construction, and `route_check.py`
could never have passed. Corrected to the version `02` §5.1 always had: no
**single local Decision/Execution** intervention suffices, while one **process**
intervention does.

**P3's witness claim was false.** It asserted that $z_3$ is unreachable from $z_1$
by any size-1 local intervention. Counterexample, on the frozen schedule:

$$\kappa = 1:\ \text{hazard occupies } (2,2) \text{ at } t \in \{2,5,8,11\}$$

`rush` reaches $(2,2)$ at $t = 2$ and collides. Now apply the **single** local
intervention $do(d_2 = \texttt{WAIT})$: the agent holds at $(1,2)$ through $t=2$,
the hazard leaves, and it crosses at $t = 3, 4, 5$ — reaching $G$ at $t=5$ **inside
the horizon**. One size-1 local decision repair therefore rescues `rush`, which is
exactly what P3 said could not happen.

The accompanying claim that the upper bypass and the wait route are
*"vertex-disjoint from the short corridor except at the endpoints"* is also false
on the route table in §1: all three share $(1,2)$ and $(3,2)$.

Both are now assertions rather than grades, and the reason they were mis-graded is
the same in both cases: **a property of a route is not established by describing
the route.** It is established by enumerating the interventions and checking.

**Defined failure mode.** If `route_check.py` finds no P3 or P4 witness:

1. the map and the option semantics are redesigned and the check is re-run;
2. if after redesign no witness exists, then the corresponding representation arm
   has **no evaluable target** in this environment — $R_{\text{causal}}$'s process
   arm and $R_{\text{module}}$'s process level for P4 — and it is **blocked**,
   recorded as a gate outcome in `experiments/v02r/` rather than silently dropped.

Outcome 2 is legitimate. An environment that cannot express the distinction V0.2R
exists to test should say so, rather than manufacturing the distinction by
construction and then reporting that the representation captures it.

See `12-AMENDMENTS.md` **A12**.

---

## 5. The behaviour chain, instantiated

$$\kappa \;\longrightarrow\; z \;\longrightarrow\; a^{cmd}_t = \arg\max_a Q_D(s_t, z, a) \;\longrightarrow\; u_t = C_X(s_t, a^{cmd}_t) \;\longrightarrow\; a^{realized}_t = P(s_t, u_t, \epsilon_E)$$

$z$ selects the **slice of the decision table** that governs the episode; it does
not emit actions (`02-SCM.md` §2.1). Both process repair ($do(z=z')$) and decision
repair ($\Delta Q_D$) therefore change behaviour, which is the whole point.

The first draft of this document wrote $a^{cmd}_t = z(s_t, t, \kappa)$ — $z$
emitting actions directly — which would have left $Q_D$ out of the rollout
entirely. See `12-AMENDMENTS.md` **A1**.

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

The three channels are therefore physically distinct. The table below is a
statement about the **evaluator's structure**, not about what the learner sees —
$u_t$ is evaluator-only (`01-OBSERVATION-MODEL.md` §2.2), so the learner cannot
read this table off and must separate the columns by query.

| evaluator structural condition | fault kind | correct repair | learner-visible? |
|---|---|---|---|
| $a^{cmd}$ deviates from $\pi_D^{*}(\cdot, z_{\text{current}}, m)$ | decision fault | $\Delta Q_D$ | **yes** |
| $u \neq a^{cmd}$ | internal execution fault | $\Delta C_X$ | no — needs a controller probe |
| $u = a^{cmd}$, $a^{realized} \neq u$ | external fault | **none** | no — and this is the point |

The last two rows are exactly the pair the learner must resolve without seeing
$u_t$. If $u_t$ leaked into `obs`, $Z_X$ and $Z_E$ would become a one-line
comparison and the controller probe would be pointless (`01` §2.2).

---

## 6. Cause injection

Each cause is assigned exogenously (`02-SCM.md` §6), never reconstructed.

| cause | injection | well-formedness constraint |
|---|---|---|
| $Z_P$ | $z \leftarrow z'$, with $z'$ drawn **uniformly from $\mathcal Z \setminus \{z\}$** | none — see §6.4 |
| $Z_D$ | $d_{t^{*}} \leftarrow a' \neq d_{t^{*}}$ for one $t^{*}$ | $a' \in A_z(m_{t^{*}}, s_{t^{*}}) \setminus \{\pi_D^{*}(s_{t^{*}}, z, m_{t^{*}})\}$ — **inside** the option, not adjacent to it (`02-SCM.md` §5.0.2) |
| $Z_X$ | $C_X(s^{*}, a^{*}) \leftarrow a'$ | $a^{*}$ must be issued at $s^{*}$ on this tape |
| $Z_E$ | activate $\epsilon_E$ at one $t$ | $t$ within horizon |
| $Z_U$ | a rare cell-specific trap the agent's hypothesis space has no symbol for | within horizon |

### 6.1 Fault presence and but-for relevance are two different variables

The first draft of this document had a single $C$, filtered post hoc by
outcome-relevance: *"a cause is recorded as active only if the injection changes
the outcome on this tape."* **That filter is wrong**, and it fails on the most
standard case in multi-cause attribution.

Consider two faults that are each independently sufficient:

$$A \Rightarrow F, \qquad B \Rightarrow F$$

With both present, remove $A$: the episode still fails, via $B$. Remove $B$: it
still fails, via $A$. The filter therefore sets $c_A = 0$ **and** $c_B = 0$, and
records $C = (0,0,\dots)$ for an episode in which both mechanisms genuinely
broke. This is the classic redundancy / overdetermination problem, and with a
multi-label $C$ it is not an edge case — it is the expected behaviour of any
generator that permits co-occurring faults.

It also contradicted `02-SCM.md` §1. Causes are drawn independently and
exogenously; a filter that then *rejects* a drawn cause on the basis of the
outcome makes the observed label an outcome-conditioned quantity, which is not the
same distribution as the one that was generated.

**So the two concepts are separated:**

$$\boxed{Z = (Z_P, Z_D, Z_X, Z_E, Z_U)\quad\text{— fault presence: mechanism actually active}}$$

$$\boxed{B = (B_P, B_D, B_X, B_E, B_U)\quad\text{— but-for relevance: a difference-maker on this tape}}$$

> **Naming.** $B$ is called **but-for relevance**, not "but-for relevance", and not
> $A$. Two reasons, both load-bearing. $A$ is the action set (§3), so reusing it
> collided inside this very document. And in an overdetermined episode **both**
> genuinely broken mechanisms can have $B_i = 0$, so a name implying
> actual-causation would promise more than the definition delivers. See
> `12-AMENDMENTS.md` **A13**.

| | $Z_i$ | $B_i$ |
|---|---|---|
| source | forward generation, exogenously assigned | evaluator intervention, computed after generation |
| can be zeroed by the outcome? | **never** | by definition |
| what it answers | *what broke?* | *did it make a difference this time?* |
| cost to compute | free | one counterfactual rollout per cause |

$$Z_A = 1,\; B_A = 0 \quad\text{is a legal and meaningful state:}$$

> mechanism $A$ really did break, but on this episode another mechanism
> established the outcome first, so $A$ was not the difference-maker.

This is the same distinction the project already drew between **fault presence** and
**repair truth** (`02-SCM.md` §4), applied one level down: $Z$ is what is broken,
$B$ is what mattered, $R^{*}$ is what must change. Three different objects, all
evaluator truth.

### 6.2 Which one each version predicts

| version | target | rationale |
|---|---|---|
| **V0.1R** | **$Z$** — primary | the question is *what happened*, a diagnosis. Predicting $B$ would smuggle in causal responsibility and re-entangle diagnosis with prescription, which is the error the four-version split exists to undo |
| V0.1R | $B$ — **secondary endpoint** | reported, because a method that gets $Z$ right and $B$ wrong is informative — it means the method detects faults but cannot rank their contribution. **Requires its own identifiability audit** (`03-IDENTIFIABILITY.md` §1.3); if $B$ is not identifiable within $B_{CF}$ it is reported as **not evaluable**, not as a negative result |
| V0.2R | $R^{*}$ | still a third object, unchanged |

$B$ is computed for every episode regardless, and is what makes the redundant-cause
episodes visible in the results rather than silently mislabelled.

### 6.3 What survives of the old filter

The *motivation* was sound: an injection that changes nothing produces an episode
whose "fault" is inert, and labelling those as faults inflates every cause. That
concern is real and is still handled — but by **recording $A$ separately**, not by
erasing $Z$.

* inert-but-present faults remain in the data with $Z_i = 1, A_i = 0$;
* metrics that want fault *detection* use $Z$;
* metrics that want causal *ranking* use $A$;
* an injection whose $Z_i = 1, A_i = 0$ **and** which cannot be made relevant by
  any tape is excluded at generation time and listed in the exclusion table of
  the identifiability artifact (`03-IDENTIFIABILITY.md` §4) — that is a
  well-formedness constraint on the generator, not a post-hoc filter on labels.

This is also the structural replacement for `scene_from_trace`: causes are never
**added** by reconstruction (the legacy bug), and they are now no longer
**removed** by outcome either.

See `12-AMENDMENTS.md` **A2**.

### 6.4 $Z_P$ does not consult $z^{*}$

$$\boxed{Z_P:\ z \leftarrow z' \sim \text{Uniform}\bigl(\mathcal Z \setminus \{z\}\bigr)}$$

**No reference to $z^{*}$ appears in the generator.** An earlier revision wrote
$z' \neq z^{*}$, which reintroduces the circularity A19 removed: $z^{*}$ is a
DP-derived quantity (step 2 of the execution order, `00-INDEX.md` §7), and the
generator runs at step 1, so consulting it would make the kernel depend on a
solver that is supposed to read the kernel.

Whether the substitution *hurt* is not the generator's business. That is $B$,
computed by intervention (§6.1), and it is what makes redundant-cause episodes
visible rather than assumed away.

$$\text{the context-appropriate option } z^{*} = \arg\max_z V_z^{*} \text{ is a \textbf{derived reporting quantity}, computed after the DP}$$

It is never a generation input. See `12-AMENDMENTS.md` **A28**.

### 6.5 $do(z = z')$ is an episode-start intervention

$$\boxed{do(z = z') \text{ sets the option for the whole episode, with } m_0(z') = 0}$$

The automaton state is **not** inherited. Carrying the old $m$ across an option
switch would be undefined — $M_z$ differs between options, and one option's
progress carries no meaning for another's obligations. The kernel must therefore
reset $m$ to the initial state, and the specification must say so or the
implementer will decide it.

This also keeps the process intervention genuinely different in kind from a local
one: $do(z=z')$ acts **at the root** and changes which automaton runs for the
whole episode; $do(d_t=d')$ acts inside the running automaton (`02-SCM.md` §5.0).

### 6.6 $Z_U$ — the unmodelled trap, operationally

An earlier revision described $Z_U$ only as *"a rare cell-specific trap the
agent's hypothesis space has no symbol for"* — a description, not a mechanism.
The kernel is the single source of truth, so the trap's effect on the transition
is now frozen:

$$\boxed{Z_U:\ \text{entering cell } c^{*} \text{ at step } t^{*} \text{ is an immediate terminal failure}}$$

with $c^{*} \in \{\text{open, non-goal cells}\}$ and $t^{*} \in \{0,\dots,H-1\}$
drawn into $M$, and $c^{*} \notin \{\text{start}, G\}$.

Three properties make this the right operationalisation:

* **it is terminal and immediate**, so it cannot be repaired by a later action —
  no local decision at $t > t^{*}$ can undo it, which is what "unmodelled" means
  for repair purposes;
* **it is cell-and-time specific**, so it is not a general hazard rule the agent
  could learn; the agent has no symbol for "this cell is deadly on this step";
* **it is evaluation-only**: nothing in `obs` marks the trap, so the learner must
  represent "this failure is not explained by my hypothesis space" as $p_U > 0$,
  which is exactly what case **C5** (`04-SEMANTIC-INVARIANTS.md`) tests.

$Z_U$ is therefore the family's only cause whose *repair truth* is routinely
$\varnothing$: there is nothing to change. An arm that edits anyway is measurably
wrong, alongside the external-fault case C8.

See `12-AMENDMENTS.md` **A31**.

---

## 7. Feedback channel

At episode end the feedback channel emits a claimed cause vector

$$\hat Z^{fb} \in \{0,1\}^5$$

with error model, error rate $\eta$ frozen at $0.4$ for the primary claim:

* with probability $1-\eta$: $\hat Z^{fb}$ names a cause that **is** active —
  possibly not all of them, chosen uniformly among the active set;
* with probability $\eta$: $\hat Z^{fb}$ names a cause that is **not** active,
  chosen uniformly among the inactive set.

The channel aims at a non-empty claim whenever a fault exists, but **does not
guarantee one**: see §8.1.1 for the two reachable empty cases
($Z = (1,1,1,1,1)$ with `error_flag = 1`, and $Z = (0,0,0,0,0)$ with
`error_flag = 0`). An earlier revision said the channel "never emits the empty
vector when a fault exists", which contradicted the frozen decoder. The decoder
governs; the frequency of empty claims is counted and reported.

The channel frequently names a wrong cause. This is what makes `DirectFeedback`
(`06-V01R.md` §3) a genuine straw man rather than a parody.

**Substitution condition.** $\text{feedback}_t$ must be replaceable by pure noise
without changing anything else, and that substitution is itself a factor
(`01-OBSERVATION-MODEL.md`, **C3**).

---

## 8. Noise tape and the counterfactual validity rule

This is the most easily-broken part of the design and it is specified exactly.

$$\boxed{\text{The tape is addressed by a semantic key, never by draw order.}}$$

### 8.1 Keys carry subkeys

A `(t, role)` pair is **not** fine-grained enough. At the terminal step the
feedback channel needs at least two independent draws:

$$\omega(t, \texttt{feedback}, \texttt{error\_flag}),\qquad \omega(t, \texttt{feedback}, \texttt{cause\_choice})$$

With a single `(t, feedback)` slot there are only two options, and both are wrong:
reuse one value for both decisions — manufacturing a spurious correlation between
*"is this feedback wrong"* and *"which cause does it name"* — or draw a second
value positionally, which is the very thing the addressing rule exists to forbid.

So the frozen key form is

$$\boxed{\omega[\text{semantic key}]},\qquad \text{key} = (\texttt{kind},\ \texttt{where},\ \texttt{which})$$

### 8.1.1 The complete key set and its value domains

An earlier draft gave this list with `e.g.` and then declared it frozen — so the
list did not exist, while the kernel was required to implement it. Deciding which
keys exist and what they range over **is** defining the SCM's exogenous variables,
not an engineering detail, so it is fixed here in full.

$$\mathcal K = \{k_1, \dots, k_n\},\qquad D(k_i) = \text{the finite value domain of } k_i$$

| # | key $k$ | domain $D(k)$ | $\lvert D\rvert$ |
|---|---|---|---|
| 1 | `("hazard", "phase")` | $\{0,\dots,5\}$ — the phase $\phi$ of §2, part of $s_t$ | 6 |
| 2 | `("feedback", "error_flag")` | $\{0,1\}$ | 2 |
| 3 | `("feedback", "cause_rank")` | $\{0,\dots,59\}$ | 60 |

$$\lvert\mathcal T\rvert = \prod_i \lvert D(k_i)\rvert = 6 \times 2 \times 60 = 720$$

$$\mathcal T \subseteq \prod_{k \in \mathcal K} D(k) \quad\text{— finite, and enumerated in full}$$

#### The measure is not uniform, and the support alone does not define it

Writing the support was necessary but not sufficient: §7 promises
$P(\text{wrong}) = 0.4$ and *uniform over the eligible causes*, and **neither
follows from the domains**. Two gaps, both now closed.

**Gap 1 — $P(\text{wrong}) = 0.4$ needs an explicit measure.** A two-point support
$\{0,1\}$ does not imply $1/2$:

$$P(\texttt{error\_flag} = 1) = 0.4, \qquad P(\texttt{error\_flag} = 0) = 0.6$$

**Gap 2 — a 5-valued draw cannot be decoded uniformly onto an eligible set of
size 2, 3 or 4.** Taking a rank modulo $\lvert E\rvert$ from a uniform draw on
$\{0,\dots,4\}$ is uniform only when $\lvert E\rvert \in \{1,5\}$. That is why the
key is a **60-valued rank** rather than a 5-valued choice: $60$ is divisible by
$1,2,3,4,5$, so

$$i = \texttt{cause\_rank} \bmod \lvert E\rvert$$

is **exactly uniform on any non-empty eligible set**. The five-valued key silently
produced a *non-uniform* feedback distribution for $\lvert E\rvert \in \{2,3,4\}$ —
which is most episodes.

#### The three keys are jointly independent

Three marginals do **not** determine a joint distribution, and the kernel is
authorised to implement "the frozen measure", so the factorisation is stated:

$$\boxed{P(\phi,\; e,\; r) = P(\phi)\,P(e)\,P(r)},\qquad
P(\phi) = \tfrac{1}{6},\quad P(e{=}1) = 0.4,\quad P(r) = \tfrac{1}{60}$$

Independence is not a convenience. If the feedback's error flag correlated with
the hazard phase, feedback reliability would vary with the hazard schedule and the
channel would leak information about $\phi$ beyond what `obs` already carries —
an undeclared second information path, exactly what `01-OBSERVATION-MODEL.md` §2.2
forbids. See `12-AMENDMENTS.md` **A30**.

#### The decoder, frozen

$$E = \begin{cases}
\{\,i : Z_i = 1\,\} & \texttt{error\_flag} = 0 \quad\text{(name an active cause)}\\[2pt]
\{\,i : Z_i = 0\,\} & \texttt{error\_flag} = 1 \quad\text{(name an inactive cause)}
\end{cases}$$

$$\hat Z^{fb} = \begin{cases}
\text{one-hot at } E[\texttt{cause\_rank} \bmod |E|] & E \neq \varnothing\\[2pt]
\varnothing & E = \varnothing
\end{cases}$$

**The empty case is reachable and is frozen, not resampled.**
$Z = (1,1,1,1,1)$ with `error_flag = 1`, and $Z = (0,0,0,0,0)$ with
`error_flag = 0`, both leave $E = \varnothing$. Resampling in that case would
silently condition the feedback distribution on $Z$, reintroducing exactly the
outcome-conditioning A2 removed. Episodes with $E = \varnothing$ are counted and
reported so their frequency is visible.

See `12-AMENDMENTS.md` **A25**.

**Why the tape has only three keys.** This is the point that keeps
$\lvert\mathcal T\rvert$ finite and the gate tractable, and it is a consequence of
`03-IDENTIFIABILITY.md` §1's latent-case definition rather than a convenience.
Fault parameters — which faults fire, at which timestep, on which action or cell,
with which alternative — are **coordinates of the fault mask $M$**, which is a free
variable of $\ell$ *alongside* $\omega$. They are **not** tape keys.

Had they been tape keys, every fault's activation, location and parameter would
have been crossed into $\mathcal T$ and $\lvert\mathcal T\rvert$ would have
exploded past any hope of exhaustive enumeration — while the same information was
already being enumerated in $M$. The tape supplies only what is genuinely
*ambient*: the hazard's phase, and the feedback channel's two draws.

Concretely:

* **no `plant` key.** The plant is the identity unless $Z_E$ fires
  (§5.2), and $Z_E$'s timestep and deviation are $M$. There is no ambient plant
  noise to draw.
* **no `inject` keys.** Fault activation and parameters are $M$. Injection is
  deterministic given $M$ and the trajectory.
* **no $t$-indexed hazard key.** The schedule is a deterministic function of
  $(\kappa, \texttt{phase})$ (§2), so one phase draw per episode determines
  occupancy at every timestep.
* **feedback is drawn once per episode**, not per timestep — it is emitted at the
  terminal step — so `where` is the terminal step and appears once.

The list is frozen. Adding a kind or subkey later changes the exogenous structure
of every existing episode, and therefore voids the seeds, exactly like a code
change. See `12-AMENDMENTS.md` **A18**.

### 8.2 The invariant is *same assignment*, not *same access log*

The first draft required two rollouts under different $do()$ operations to read an
**identical tape access log**. That is stronger than the causal requirement and
would wrongly forbid a legitimate implementation.

What is actually needed is:

$$\boxed{
\begin{aligned}
&\text{(a) all rollouts of an episode share the same tape fingerprint, and}\\
&\text{(b) the same key yields the same value in every rollout, and}\\
&\text{(c) positional consumption is forbidden.}
\end{aligned}}$$

An intervention may legitimately make a variable irrelevant, in which case a
rollout may simply never look up that key — and that is fine, because the value it
*would* have received is unchanged. Requiring an identical log would either fail
such a rollout or force a redundant lookup purely to satisfy a test.

Materialising the entire $H \times \text{kinds} \times \text{subkeys}$ table up
front and having every rollout read every slot unconditionally would also satisfy
the log version — but that is an **implementation choice**, and it must not be
promoted into the definition of causal validity.

A mechanical test asserts (a), (b) and (c): the tape object is compared by
fingerprint; a read of the same key in two rollouts of one episode is asserted
equal; and the RNG interface exposes no positional/sequential accessor at all, so
(c) is enforced by construction rather than by discipline.

See `12-AMENDMENTS.md` **A3**.

---

## 9. Identifiability signature

For `03-IDENTIFIABILITY.md`, the signature of a case under query $q$ is the hash of
the learner's **total information set**, not of `obs_t` alone:

$$\boxed{\sigma(\ell, q) = \bigl(I_t\bigr)_{t=0}^{T}}, \qquad I_t = \bigl(obs_t,\ z_t,\ m_t\bigr)$$

expanded as

$$\bigl(s_t,\ a^{cmd}_t,\ a^{realized}_t,\ r_t,\ \text{feedback}_t,\ z_t,\ m_t\bigr)_{t=0}^{T}$$

**$z_t$ and $m_t$ are in the signature, and that is load-bearing.** `01` §2.1.1
makes them learner-visible, so a learner may legitimately index
$Q_D(s,z,m,\cdot)$ with them. A signature built from `obs_t` alone would *withhold
information the learner actually has*, and Gate L could then report an
information-theoretic failure that is an artefact of the bookkeeping (A27). An
earlier revision of this section did exactly that.

Truth fields ($Z$, $M$, and the fault parameters inside $M$) are **excluded**;
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
a proposed unit set $\hat R$ into an intervention set.

**Two representations had no rule at all in the first draft** — $R_{\text{module}}$
has an *action level* that merges decision and execution, and
$R_{\text{trajectory}}$ proposes the whole episode. Both are listed as official
competitors in `07` §3, and both were unconvertible, so V0.2R was not executable.
The rules are completed here. See `12-AMENDMENTS.md` **A5**.

#### 11.2.1 The rule, by unit kind

| unit kind | converts to |
|---|---|
| **process** | $do(z = z')$, where $z'$ is the option the representation names; if it names none, $z' = z^{*}$ |
| **decision** $(t)$ | $do(d_t = d')$, where $d'$ is the alternative named; if none, the reference action $\pi_D^{*}(s_t, z, m_t)$ |
| **execution** $(s^{*}, a^{*})$ | $do\bigl(C_X(s^{*}, a^{*}) = a^{*}\bigr)$ — one cell (`02-SCM.md` §5.0) |
| **action** $(t)$ | **both** of $\{do(d_t = \pi_D^{*}(s_t, z, m_t)),\ do(C_X(s_t, a^{cmd}_t) = a^{cmd}_t)\}$ |
| **trajectory** $(\text{whole episode})$ | the **process** candidate, **union** the union over all $t$ of the **action** conversion above |
| empty $\hat R$ | $\varnothing$ — change nothing |

#### 11.2.2 Why `action` expands to two candidates and not one

$R_{\text{module}} = \{\text{process}, \text{action}\}$ collapses decision and
execution into one unit. Keeping the timestep but dropping the kind gives

$$Action_t = \{Decision_t,\ Execution_t\}$$

If the conversion were allowed to pick whichever of the two the Oracle knows to be
correct, a **coarse** representation would silently receive the fine
representation's information, and the comparison in `07` §4 would measure nothing.

So the conversion is honest: a representation that cannot tell the two apart must
**propose both**. The consequences fall exactly where they should:

| endpoint | effect |
|---|---|
| InterventionSufficiency | can stay high — one of the two may suffice |
| CandidateSetSize | rises |
| FalseEditRate | **penalised** by the redundant candidate |

This is the price of coarseness, made visible instead of hidden. The Oracle is
never consulted to break the tie.

#### 11.2.3 Why `trajectory` expands to everything

$R_{\text{trajectory}}$ asserts only *"something in this run is wrong"*. Converted
honestly it proposes a candidate at every timestep, which is the correct
operationalisation of a representation that has no localisation. It is expected to
score high on coverage and poor on `CandidateSetSize` and `FalseEditRate`, and
that is the point of including it as a baseline.

#### 11.2.4 Admissibility

The rule is oracle-assisted — it may consult $z^{*}$ and
$\pi_D^{*}$, both evaluator truth. That is admissible in V0.2R because
V0.2R receives cause truth and is scored against repair truth (`07` §1). It is
**not** admissible in V0.4R, where $\hat V(c)$ must be learned, and it is not used
there (`09` §3).

The rule is frozen and identical across representations. Any per-representation
special case would reintroduce exactly the confound §11.2.2 exists to remove.

---

## 12. The reference checkpoint and the reference policy

V0.2R, V0.3R and V0.4R all refer to "the reference" without the source having been
fixed. It is fixed here, and it is a **single shared artifact** so that no version
can quietly use a different one.

### 12.1 $Q^{*}$ — computed exactly, not trained

$$\boxed{Q_D^{*}(s, z, m, a) \text{ is obtained by exact finite-horizon dynamic programming}}$$

over the **healthy** environment — no fault injected, $C_X$ = identity, no external
perturbation — with $z$ ranging over all four options and $a$ restricted to
$A_z(m,s)$ (`02-SCM.md` §2.3).

An earlier draft specified "the baseline learner trained to convergence under the
$T$-freezing rule". That was wrong for this environment, on three counts:

1. **It reintroduced seed dependence into the ruler.** $Q^{*}$ is the target that
   every arm is scored against; deriving it from a stochastic training run makes
   the measurement instrument depend on a seed, an $\epsilon$-schedule and a
   stopping rule. The state space is a few hundred states (`11` §1), so the exact
   solution is computable and there is no reason to approximate it.
2. **It could not answer how the four option slices get trained.** `02` §2.3
   requires four genuinely different policy classes; "train to convergence" never
   said what $z_2$ and $z_4$ were trained *on*. Exact DP answers it by
   construction: each slice is solved inside its own admissible set.
3. **It made P2/P3/P4 depend on a training run**, which is circular — the
   properties are supposed to validate the environment that the training would
   have needed.

The **learner still uses tabular Q-learning**. Only the evaluator's ruler is exact.

$Q^{*}$ is:

* **computed** by DP and committed to `experiments/_shared/reference/`, never
  regenerated per run;
* **fingerprinted** alongside the source tree (`10` §2);
* **frozen**: any change to it voids every experiment that used it.

### 12.2 The reference policy family

$$\boxed{\pi_D^{*}(s, z, m) = \arg\max_{a \in A_z(m,s)} Q_D^{*}(s, z, m, a)}$$

option-conditioned, with ties broken by a frozen declared order. The single global
$\pi_{\text{ref}}(s) = \arg\max_a Q^{*}(s,a)$ of the first draft is **retired** — it
is inconsistent with behaviour being generated by $Q_D(s, z, m, \cdot)$ (`02-SCM.md`
§2.1) and, worse, using it to define decision faults would re-create the
process/decision overlap: after a wrong $z$, the *locally correct* actions of that
option would be flagged as decision faults.

$\pi_D^{*}(\cdot, z, m)$ is used for:

* defining a decision fault **relative to the option in force** (`02-SCM.md` §2.3);
* the canonical conversion rule's fallback alternative (`11` §11.2);
* the `is_deviation` flag in any step trace.

### 12.3 $V_{\text{pre}}$

The recovery endpoints of `05` §8 compare against pre-corruption performance.
$V_{\text{pre}}$ is measured on $Q^{*}$ itself, at the same $N_{\text{eval}}$ and
over the same evaluation scenes as the post-corruption checkpoints, and is stored
with the reference artifact. It is **not** re-measured per run.

---

## 13. Frozen

1. the grid, start, goal, hazard schedule and phase, horizon $H = 12$, step cost;
2. the context lane and its two regimes;
3. the action set and the ill-formed-action rule;
4. the four options, and properties **P1–P4 as assertions discharged by
   `scripts/route_check.py`** (§4.1), with P4 carrying a defined failure mode (§4.2);
5. the behaviour chain $\kappa \to z \to Q_D(s, z, m, \cdot) \to a^{cmd}$ (§5); $z$ is an
   option id and does **not** emit actions;
6. the controller/plant split and the three-channel table (§5.2), with $u_t$
   evaluator-only;
7. the separation of fault presence $Z$ from but-for relevance $B$ (§6.1), and the
   rule that $Z$ is never zeroed by the outcome;
8. the feedback error model and $\eta = 0.4$;
9. the tape's semantic-key form $(\texttt{kind}, \texttt{where}, \texttt{which})$
   with the frozen three keys and their measures (§8.1), and the *same assignment* invariant
   (§8.2), including the prohibition on positional consumption;
10. the identifiability signature (§9), excluding truth fields;
11. the deferred-value table (§10) and its defaults;
12. the $R_{\text{module}}$ referent (§11.1) and the **complete** canonical
    conversion rule (§11.2), including the `action` and `trajectory` rows;
13. $Q^{*}$, $\pi_D^{*}$ and $V_{\text{pre}}$ as one shared, frozen,
    fingerprinted reference artifact (§12);
14. the execution primitive $do(C_X(s^{*},a^{cmd}) = a^{cmd})$ acting on one cell
    (`02-SCM.md` §5.0).
