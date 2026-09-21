# 12 — Amendments

**Status:** append-only. `10-REPRODUCIBILITY-AND-OPS.md` §8: a frozen document may
be changed only by an amendment recorded **before** any seed of the affected
version is collected, and amendments are appended, never substituted. The
amendment history is the record of what the design had to learn, and it is the
part a reader should trust most, because it is the only part that could not have
been written in advance.

This round contains eight amendments, all raised in review of `01`, `02` and `11`,
before any implementation and before any seed. **No experiment was invalidated:**
there are no runs yet, which is precisely the point of freezing the design first.

$$\boxed{\text{Four of these would have changed the meaning of an experiment had they been found later.}}$$

---

## 1. How to read this log

Each amendment is a `##` section addressed by a stable id `A1` … `A8`, and each
records four things:

| field | meaning |
|---|---|
| **Was** | the frozen text, quoted |
| **Wrong because** | the argument, with the concrete case that breaks it |
| **Now** | the corrected text, and where it lives |
| **Trigger** | how it was found — because *how* a defect is found determines whether a test could have caught it |

The **Trigger** field is the one worth reading. Several of these were not
detectable by any test, because the code would have been internally consistent:
the design was wrong, not the implementation. `A1` and `A2` are both of that kind,
and both were P0.

Amendments `A1`–`A8` are §2–§9 below; §10 is the summary and the list of what
remains open after this round.

---

## 2. A1 — $z$ emitted actions directly, disconnecting $Q_D$ from behaviour

**Severity: P0.** Would have reproduced the legacy headline failure.

**Was** (`11` §5, first draft):

$$d_t = z(s_t, t, \kappa) \;\longrightarrow\; a^{cmd}_t = d_t$$

**Wrong because.** With $z$ emitting actions, the policy never reads $Q_D$. A
decision repair $\Delta Q_D$ would then change no rollout — and the rebuild would
have re-derived, from scratch, the legacy result *"we repaired the decision
precisely and the task utility did not move"*, for the trivial reason that
nothing read the table being repaired. Meanwhile `02` §3 defined
$\pi_D : s \to a^{cmd}$ and every decision-repair arm updated $Q_D$, and `11` §12
defined $Q^{*}$ and $\pi_{\text{ref}} = \arg\max Q^{*}$ — three objects with no
connection to the actual rollout.

**Now** (`02-SCM.md` §2.1, `11` §5):

$$\kappa \;\longrightarrow\; z \;\longrightarrow\; a^{cmd}_t = \arg\max_a Q_D(s_t, z, a) \;\longrightarrow\; u_t \;\longrightarrow\; a^{realized}_t$$

$z$ is an **option identifier** selecting a slice of the decision table. Both
$do(z=z')$ and $\Delta Q_D$ change behaviour, and neither is expressible as the
other.

**Trigger.** Reading `02` and `11` together. Not detectable by any test, because
the code would have been internally consistent — the design was wrong, not the
implementation.

---

## 3. A2 — the outcome-relevance filter erased genuinely co-occurring faults

**Severity: P0.** Would have produced systematically mislabelled data.

**Was** (`11` §6.1, first draft):

> A cause is recorded as active only if the injection is outcome-relevant on this
> tape.

**Wrong because.** With two independently sufficient faults $A$ and $B$, removing
either leaves the other establishing the failure, so the filter sets $c_A = 0$
**and** $c_B = 0$ — recording "nothing was wrong" for an episode in which two
mechanisms broke. This is the classic redundancy/overdetermination case, and with
a multi-label $Z$ it is the expected behaviour, not an edge case. It also
contradicted `02` §1: causes are drawn independently and exogenously, and a filter
that rejects a drawn cause on the basis of the outcome makes the observed label an
outcome-conditioned quantity.

**Now** (`11` §6.1): two separate variables.

$$Z = \text{fault presence: mechanism actually active (never zeroed by outcome)}$$

$$B = \text{but-for relevance: a difference-maker on this tape (evaluator intervention)}$$

$Z_A = 1, B_A = 0$ is legal and meaningful. V0.1R predicts $Z$ primarily and $B$
as a secondary endpoint (`11` §6.2). The symbol is $B$, not $A$ — see **A13**.

**Trigger.** Review, by reasoning about the redundant-cause case. The filter
looked correct on every single-cause example.

---

## 4. A3 — the tape key was too coarse, and the invariant was too strong

**Severity: medium.** Would have forced a bad implementation choice or a spurious
correlation.

**Was** (`11` §8, first draft): address by $(t, \text{role})$, and two rollouts
must read an **identical access log**.

**Wrong, part 1.** At the terminal step the feedback channel needs two independent
draws — *is this feedback wrong* and *which cause does it name*. A single
$(t, \texttt{feedback})$ slot forces either reuse of one value (manufacturing a
spurious correlation between the two) or a positional second draw (the thing the
addressing rule exists to forbid).

**Wrong, part 2.** "Identical access log" is stronger than the causal
requirement. An intervention may legitimately render a variable irrelevant, so a
rollout may never look that key up; the value it *would* have received is
unchanged. Demanding an identical log fails such a rollout, or forces a redundant
lookup purely to satisfy a test.

**Now** (`11` §8):

* keys are $(\texttt{kind}, \texttt{where}, \texttt{which})$ with the full list frozen;
* the invariant is **(a) same tape fingerprint, (b) same key $\Rightarrow$ same
  value, (c) no positional consumption** — with (c) enforced by exposing no
  sequential accessor at all.

Materialising the whole table and always reading every slot still satisfies the
old formulation, but that is now explicitly an **implementation choice**, not the
definition of causal validity.

---

## 5. A4 — the map made $z_2$'s sidestep impossible, and $z_4$ was self-contradictory

**Severity: high.** Two properties were asserted in prose and were false.

**Was** (`11` §1 map): side walls at $(1,1)$ and $(1,3)$.

**Wrong because.** From $(1,2)$ both $(1,1)$ and $(1,3)$ were walls, and the only
cell from which the contested cell can be avoided is $(2,2)$ — the cell the hazard
occupies. The "local sidestep" did not physically exist. No route had been walked;
the property was stated and believed.

**Also was** (`11` §4): $z_4$ described as *"delayed failure: times out at $H$"*
two lines above *"$z_3$ and $z_4$ succeed under both contexts"*. Both cannot hold,
and with an 8-move route under $H = 12$ the timeout claim was simply false.

**Now:** the map is corrected (walls at $(2,1)$, $(2,3)$), all three routes are
listed with hand-verified move counts, the hazard phase is concrete, and **the
four properties are promoted from prose to assertions** discharged by
`scripts/route_check.py` over the full product.

$z_4$'s "delayed failure" is **withdrawn and not replaced by a claim**: P4
(process granularity — an episode where no size-1 intervention suffices but some
$do(z=z')$ does) is marked **not established**, with a defined failure mode in
`11` §4.2.

**Trigger.** The reviewer walked the map. This is the amendment that most
justifies the assertion-over-prose rule.

---

## 6. A5 — two competing representations had no conversion rule

**Severity: high.** V0.2R was not executable as frozen.

**Was** (`11` §11.2, first draft): conversion rules for process, decision,
execution and empty — and nothing else.

**Wrong because.** `07` §3 lists $R_{\text{module}}$ and $R_{\text{trajectory}}$
as official competitors. $R_{\text{module}}$'s *action level* merges decision and
execution, so it matched none of the four rules; $R_{\text{trajectory}}$ was not
covered either. With `InterventionSufficiency` as the primary endpoint and
$\hat R \to \text{interventions}$ as the required path, two of four
representations could not be scored at all.

Worse, the natural "fix" — let the Oracle say which of decision/execution it
really was — would hand a **coarse** representation the fine representation's
information, and the comparison in `07` §4 would measure nothing.

**Now** (`11` §11.2):

$$Action_t = \{Decision_t, Execution_t\} \;\longrightarrow\; \{do(d_t = d'),\ do(C_X(s_t,a^{cmd}_t) = a^{cmd}_t)\}$$

A representation that cannot tell the two apart must **propose both**, paying in
`CandidateSetSize` and `FalseEditRate`. $R_{\text{trajectory}}$ converts to the
union over all timesteps. The Oracle is never consulted to break the tie.

---

## 7. A6 — the identifiability matrix was one row per label, not per case

**Severity: high.** The gate could report PASS while a label pair was
inseparable.

**Was** (`03` §4, first draft): *"rows — every feasible cause assignment
$C \in \{0,1\}^5$"*, while §1 correctly defined a latent case as the full
assignment and required $\forall \ell_i, \ell_j:\; C_i \neq C_j \Rightarrow
\ell_i \not\equiv \ell_j$.

**Wrong because.** One representative per label is strictly weaker. Two labels may
be separable under one nuisance setting $(z, t^{*}, \theta_{C_X}, \kappa, \omega)$
and inseparable under another; a per-label matrix reports PASS and V0.1R is then
asked to solve a problem that is not identifiable in part of the space.

Separately, $\omega$ as a stream of real draws cannot be enumerated, so
"exhaustive" quantified over a continuum and was not a gate.

**Now** (`03` §1.1, §1.2, §4): a **frozen finite canonical tape set** $\mathcal T$
(tapes are finite by construction because every tape role is a finite choice), and
rows over the full product $\mathcal L$, **collapsed by label for reading only —
decided on the uncollapsed rows**. Sampling $\mathcal T$ is a smoke test and must
be labelled as such. The predicted label is now stated as $Z$, not $C$ (A2).

---

## 8. A7 — the execution primitive replaced the whole controller

**Severity: medium.** Made $|R^{*}|$ non-comparable across fault kinds.

**Was** (`02-SCM.md` §5, first draft): $do(C_X = C')$ in the intervention lattice.

**Wrong because.** That reads as *replace the entire controller table*. A size-1
execution repair would then fix an arbitrarily large controller while a size-1
decision repair fixes one timestep, so the cardinality of $R^{*}$ would no longer
mean the same thing across fault kinds — an execution repair would look "cheaper"
only because it silently did more work. The comparison is central to
`02-SCM.md` §5.1 and to case C7.

**Now** (`02-SCM.md` §5.0):

$$do\bigl(C_X(s^{*}, a^{cmd}) = a^{cmd}\bigr) \text{ — one cell}$$

---

## 9. A8 — $u_t$ visibility was implicit, and `01` and `11` disagreed

**Severity: medium.** Would have leaked a field and collapsed an intended
inference into a lookup.

**Was.** `01` §2.1 froze $obs_t$ without $u_t$ — correct. But `11` §5.2 presented
the three fault channels in a table whose column header read **"observed"**. The
learner cannot observe $u_t$; the table was describing the evaluator's structure.

**Wrong because.** Had an implementer followed `11` §5.2 literally, $u_t$ would
have entered the observation, and then

$$u_t \neq a^{cmd}_t \;\Rightarrow\; \text{internal execution fault},\qquad a^{realized}_t \neq u_t \;\Rightarrow\; \text{external fault}$$

becomes a one-line comparison. $Z_X$ and $Z_E$ — one repairable, one not — would
stop being a question, and the controller probe in `03` §3 would be pointless.

**Now.** $u_t$ is named explicitly in `01` §2.2 as **evaluator-only**, alongside
$Z$ and $M$, with the reason recorded; and `11` §5.2's header reads *"evaluator
structural condition"* with a `learner-visible?` column.

The general lesson, which is why this is an amendment rather than a typo fix: the
legacy defects were repeatedly of the form *a field was visible and nobody had
decided it should be*. Fields are now either in `obs` §2.1 explicitly or in the
hidden set §2.2 explicitly. There is no third category.

---

## 10. A9 — the four options were four names for one policy

**Severity: P0.** Would have reopened A1 in a new costume.

**Was.** A1 fixed the chain to $\kappa \to z \to Q_D(s,z,\cdot) \to a^{cmd}$, but
nothing made the four options *different policies*. They were four numbered slices
of one table with the same action set and the same reward — under tabular
Q-learning each slice converges to the same fixed point, so $do(z=z')$ would again
change the name of the behaviour without changing the behaviour. Compounding it,
`11` §12 trained $Q^{*}$ under $z = z^{*}(\kappa)$ while `02` §2.1 claimed $Q^{*}$
covers all four options, so it was never specified what $z_2$ and $z_4$ are
trained on.

**Now** (`02-SCM.md` §2.3): an option carries a **waypoint automaton** and
constrains the policy class,

$$A_z(s) \subseteq A, \qquad \pi_D^{*}(s,z) = \arg\max_{a \in A_z(s)} Q_D^{*}(s,z,a)$$

with $z_1$ unconstrained, $z_2$ obliged to visit $(2,1)$, $z_3$ obliged to hold at
$(1,2)$ until the hazard clears, $z_4$ obliged to visit $(2,4)$. The admissible
sets differ, so the optimal policies differ on shared states.

**And decision faults are now defined relative to the option in force**,
$do(d_t) \neq \pi_D^{*}(s_t, z_{\text{current}})$. Against a single global
$\pi_{\text{ref}}$ a wrong $z$ would cause the option's *locally correct* actions
to be re-labelled as decision faults, re-creating exactly the process/decision
overlap the rebuild exists to remove. `11` §12.2's global
$\pi_{\text{ref}}(s) = \arg\max_a Q^{*}(s,a)$ is retired in favour of the family
$\{\pi_D^{*}(\cdot,z)\}$.

**Trigger.** Review. Note the shape: A1 was a *connection* bug, A9 is a
*degeneracy* bug. Fixing the first did not reveal the second, because the
degeneracy only appears once the connection exists.

---

## 11. A10 — the identifiability gate was not budget-aware

**Severity: P0.** Gate L could pass while the learner could never pass.

**Was** (`03` §1): $\ell_i \equiv \ell_j \iff \forall q \in \mathcal Q_{\text{legal}}:
O(\ell_i,q) = O(\ell_j,q)$ — "if every legal query were performed, could these be
told apart?"

**Wrong because.** That is not the question. A pair needing eight probes makes the
full-signature map injective, so Gate L reports **PASS**, while a learner holding
$B_{CF} = 4$ queries can never separate it. The gate would license an experiment
whose failure is guaranteed by the budget, and the failure would be written up as
an algorithmic result.

**Now** (`03` §1.4):

$$B_{\min}^{\text{adaptive}} = \min_{\Pi} \max_{\ell} \mathrm{depth}_{\Pi}(\ell) \le B_{CF}$$

over decision trees whose nodes issue legal queries and branch on outcomes; with a
tractable non-adaptive fallback $\exists S,\ |S| \le B_{CF}$ that separates.

**Two more defects in the same section:**

* the controller probe was still written $do(C_X = C')$ — the whole-table form A7
  had already replaced in `02` but not in `03`, so the identifiability analysis
  would have run against a **different intervention lattice** than the learner
  uses. Now the single-cell primitive.
* **noise resample is not a causal intervention.** It holds the mechanism fixed
  and varies the exogenous draw, whereas $do(\cdot)$ does the opposite. Mixing it
  into $\mathcal Q_{\text{learner}}$ would make signatures incomparable (the two
  rollouts do not share $\omega$) and would inflate $B_{CF}$ with a query that
  separates no two cases differing only in $Z$. It now has its own budget
  $B_{\text{resample}}$ and is excluded from $\mathcal Q_{\text{learner}}$.

---

## 12. A11 — the latent case was not closed

**Severity: P0.** The gate enumerated states the generator cannot produce, and
omitted ones it can.

**Was** (`03` §1): $\ell = (Z, A, z, \theta_{C_X}, \epsilon_E, \omega)$, with a size
formula multiplying in **two** five-dimensional factors.

**Wrong because.**

1. **$A$ is derived, not drawn.** It is computed by intervention *after*
   generation (`11` §6.1). Enumerating it as a free coordinate inflates
   $\lvert\mathcal L\rvert$ with unreachable states and dilutes the gate.
2. **$\kappa$ was missing** from $\ell$ and from the product, though it appears in
   the matrix description and changes the hazard schedule — and therefore changes
   signatures.
3. **$M$ was missing entirely**, though it is exactly what separates two episodes
   with the same $Z$: a decision fault at $t=2$ and one at $t=7$ are different
   episodes.

**Now** (`03` §1):

$$\ell = (Z,\; M,\; \kappa,\; z,\; \theta_{C_X},\; \epsilon_E,\; \omega), \qquad B = f_B(\ell), \quad R^{*} = f_R(\ell)$$

with $\mathcal L$ the feasible set of those free variables.

**Also withdrawn:** the claim that $B$ "cannot be less identifiable than $Z$".
Coarser as a *function of $\ell$* is not coarser as an *inference target* — the
same $Z$ yields different $B$ under different masks and tapes. $B$ now gets its
own audit, and if it is not identifiable within budget it is reported as **not
evaluable** rather than as a learner failure.

---

## 13. A12 — P3 and P4 were both mis-graded

**Severity: high.** One was unsatisfiable; the other was false.

**P4 was a logical contradiction.** Written as *"no size-1 intervention of any
kind suffices, but some $do(z=z')$ does"* — but $do(z=z')$ **is** an element of
the intervention lattice and **is** size-1. `route_check.py` could never have
passed. Corrected to `02` §5.1's form: no single **local Decision/Execution**
intervention suffices, while one **process** intervention does.

**P3's witness claim was false.** It asserted $z_3$ is unreachable from $z_1$ by
any size-1 local intervention. Counterexample on the frozen schedule: under
$\kappa=1$ the hazard occupies $(2,2)$ at $t \in \{2,5,8,11\}$ and `rush` arrives
at $t=2$. The **single** intervention $do(d_2 = \texttt{WAIT})$ holds the agent at
$(1,2)$, the hazard leaves, and it crosses at $t = 3,4,5$ — reaching $G$ inside
the horizon. One size-1 local repair rescues `rush`.

The same section claimed the bypass and wait routes are "vertex-disjoint from the
short corridor except at the endpoints"; the route table in `11` §1 shows all
three share $(1,2)$ and $(3,2)$.

**Now** (`11` §4.2): **all four properties are enumeration-pending; none is
claimed.** Both defects had the same cause — *a property of a route was asserted
by describing the route*. This is the second time (after A4) that prose
description substituted for enumeration, which is why the grading language
"available / not established" is gone entirely.

---

## 14. A13 — the $C$ symbol was not cleaned up, and $A$ collided

**Severity: medium.** Not cosmetic: implementers read these symbols as the data
schema.

**Was.** A2 introduced $Z$ and $A$ but $C$ survived in `02` §1, `02` §4, `02` §6,
`06` §2, `11` §7 (as $\hat C^{fb}$), `11` §9 ("excluding truth fields $C, M, z,
\epsilon_E$") and the `03` readout ("classes containing more than one distinct
$C$") — while `03` §1 declared the symbol retired. Separately, $A$ was the action
set in `11` §3 **and** the relevance vector in `11` §6.1: a collision inside one
document.

**Now.** The symbol table is frozen:

$$Z = \text{fault presence},\quad B = \text{but-for relevance},\quad R^{*} = \text{repair truth},\quad \hat Z^{fb} = \text{feedback claim}$$

$A$ is the action set, exclusively. And $B$ is named **but-for relevance**, not
"causal relevance", because in overdetermination two genuinely broken mechanisms
can both have $B_i = 0$; a name implying actual-causation would promise more than
the definition delivers.

---

## 15. A14 — the reward equivalence claim ignored the step cost

**Severity: high.** A mathematical error that propagated to three documents.

**Was** (`02` §7): $\mathbb{E}[R^{(A)}] = 2P(S)-1$, $\mathbb{E}[R^{(B)}] = P(S)$,
"so they induce the **same optimal policy**".

**Wrong because.** It ignored the per-step cost, which `11` §1 fixes at $-0.02$,
while the route lengths differ (4 / 6 / 8). With $L$ the policy-dependent step
count,

$$G_A = 2\cdot\mathbf{1}_{\text{success}} - 1 - 0.02L, \qquad G_B = \mathbf{1}_{\text{success}} - 0.02L$$

so $2\mathbb{E}[G_B] - 1 = 2P(S) - 1 - 0.04\,\mathbb{E}[L] \neq \mathbb{E}[G_A]$
whenever $\mathbb{E}[L] \neq 0$. **The objectives are not affine transforms and do
not in general share an optimal policy.**

**Now** (`02` §7): the claim is retracted; the step cost stays, because it is what
makes the short corridor better than the bypass when both are safe and therefore
what gives §2.3's option semantics any content. Reward × Update becomes a
**genuine secondary factorial between two different objectives**, and can no
longer be read as a "does reward matter" null.

The legacy Alpha pilot's finding of practical equivalence is explained by the
legacy environment having no policy-dependent step cost — it does not carry over.

---

## 16. A15 — $R_{\text{trajectory}}$ could never propose a process repair

**Severity: medium.** Would have biased the V0.2R primary endpoint.

**Was** (`11` §11.2): trajectory converts to "the union over all $t$ of the action
conversion".

**Wrong because.** $R_{\text{trajectory}}$ asserts *"something in this run is
wrong"* — the coarsest representation. Converted without a process candidate, it
is **structurally unable** to repair a pure process fault, not because it is too
coarse but because the conversion forbade it. `InterventionSufficiency` for that
arm would then be depressed by a rule of the conversion rather than by the
representation's coarseness.

**Now:**

$$R_{\text{trajectory}} \longrightarrow \{\text{process candidate}\} \cup \bigcup_t Action_t$$

---

## 17. A16 — the proposed execution order was circular

**Severity: P0 (process).** Would have produced a second simulator.

**Was.** The next step was "write `route_check.py` and the identifiability
generator, without touching `env/`, then let their results decide how `env/` is
written".

**Wrong because.**

1. `route_check` needs `rollout`, the hazard transition, the `do`-operators and
   the option policy; the identifiability generator needs the same. Re-implemented
   inside `scripts/`, that is a **second simulator**, and the day the real `env/`
   drifts from it we are back to *the specification's Oracle and the training
   world are not the same world* — the legacy failure, exactly.
2. P2/P3/P4 depend on option-conditioned $Q_D$, which needs the environment to
   produce it. "Run route_check first, let it decide how to write env" is
   therefore **circular**, a point `11` §4.2 itself conceded by noting P2 depends
   on trained $Q_D$.

**Now.** The first artifact is not V0.1R and not `route_check` — it is a minimal,
single-source **SCM kernel**:

$$\text{state transition} + \text{semantic tape} + \text{option constraints} + \text{do-operators}$$

at `src/rfl_rebuild/env/kernel.py`, with **no training, no RFL, no seeds**.
`route_check.py` and the identifiability generator both **import it** and add
nothing of their own about the world. The order becomes

$$\boxed{\text{kernel} \to \text{route\_check} \to \text{Gate E/L} \to \text{semantic suite} \to \text{reference DP} \to \text{V0.1R}}$$

which is the first ordering in this project with no circular dependency.

**And $Q^{*}$ by exact DP, not by training** (`11` §12.1). A few hundred states;
finite-horizon DP gives $Q_D^{*}(s,z,a)$ deterministically. This removes seed,
$\epsilon$-schedule and stopping-rule dependence from the *ruler* every arm is
scored against, answers "what were $z_2$ and $z_4$ trained on" by construction,
and dissolves the circularity in 2 above. The learner still uses tabular
Q-learning; only the evaluator is exact.

---

## 18. A17 — the option automata were obligation prose, and $do(d_t)$ was unconstrained

**Severity: P0.** `kernel.py` owns *option constraints*; an implementer would have
had to invent them.

**Was** (`02` §2.3): four options described by obligation — "must visit $(2,1)$",
"must hold at $(1,2)$ until the hazard clears" — with no automaton state, no
initial state, no discharge condition, no statement of how $A_z$ varies with
state, and no answer to the question that decides the whole design:

$$do(d_t = d') \text{ — may } d' \notin A_z?$$

**Wrong because.** Those are not engineering details; they are design decisions
that change the experiment. And the unanswered question decides whether
"process" and "local" granularity are distinct at all: if a local $do(d_t)$ may
ignore the option's obligation, then a nominal *decision* repair can deliver a
*process* repair — escaping the obligation is exactly what changing $z$ does —
and P3/P4 stop distinguishing anything.

Prose obligation is also the same hazard that produced A4 and A12: a property
asserted by describing it.

**Now** (`02` §2.4): all four automata are given as explicit transition tables
($M_z$, $m_0$, $\delta_z$, and $A_z(m,s)$ per state), all four are monotone so
that every obligation is recoverable, and the do-question is answered:

$$\boxed{do(d_t = d') \text{ is well-formed} \iff d' \in A_{z}(m_t, s_t)}$$

A local decision intervention changes **one decision inside the current option**;
it does not lift the option's constraint. Ill-formed interventions are rejected at
generation and recorded in the identifiability exclusion table, not silently
clamped.

**Two intended consequences.** When the option itself is wrong, **no** local
decision intervention can rescue the episode — which is what a process fault
*means*, and it makes P4 satisfiable without contrivance. And $do(z=z')$ stays
unrestricted over $\mathcal Z$.

---

## 19. A18 — the frozen tape key list did not exist

**Severity: P0.** The kernel implements the tape; the list was a placeholder.

**Was** (`11` §8.1): "the kinds and subkeys declared in full before
implementation, **e.g.**" followed by a partial list — and, three lines later,
"the list is frozen".

**Wrong because.** Deciding which keys exist, what they range over, how many
subkeys each needs, which slots are $t$-indexed, and how $\mathcal T$ is
constructed **is** defining the SCM's exogenous variables. The document declared
it frozen while not containing it, so an implementer would have decided it
silently. `03` §1.1 correctly required a finite $\mathcal T$; nothing said what
that finite set is.

**Now** (`11` §8.1.1): the complete key set with domains —

| key | domain | $\lvert D\rvert$ |
|---|---|---|
| `("hazard", "phase")` | $\{0,\dots,5\}$ | 6 |
| `("feedback", "error_flag")` | $\{0,1\}$ | 2 |
| `("feedback", "cause_choice")` | $\{P,D,X,E,U\}$ | 5 |

$$\lvert\mathcal T\rvert = 6 \times 2 \times 5 = 60$$

**The three-key result is a consequence of the latent-case definition, not a
convenience.** Fault parameters — which faults fire, at which timestep, on which
action or cell — are coordinates of the **fault mask $M$**, a free variable of
$\ell$ *alongside* $\omega$. Had they been tape keys, every fault's activation,
location and parameter would have been crossed into $\mathcal T$ and it would have
exploded beyond enumeration — while the same information was already being
enumerated in $M$. The tape carries only what is genuinely ambient: the hazard
phase and the feedback channel's two draws.

---

## 20. A19 — the execution order was still circular by one position

**Severity: P0 (process).**

**Was** (A16's order): kernel → `route_check` → Gate E/L → semantic suite →
reference DP → V0.1R.

**Wrong because.** P2/P3/P4 depend on $\pi_D^{*}(s,z)$ and option-conditioned
$Q_D^{*}$. `route_check` asks *"does a local repair rescue the episode?"* — but it
must first know what the option does when healthy, which requires the exact
solution. Placing the DP after `route_check` therefore left the circularity A16
had set out to remove, one position to the right.

**Now:**

$$\boxed{\text{kernel} \to \text{exact DP} \to route\_check \to \text{Gate E/L} \to \text{semantic suite} \to \text{V0.1R}}$$

The DP does **not** define the world — it reads the kernel and solves it — so
moving it before `route_check` does not create a second simulator. This is the
first ordering with no circular dependency at any position, and it matches the
authorisation boundary: kernel first, DP separately after.

---

## 21. A20 — admissible sets were not bounded by physical legality

**Severity: medium.** Would have polluted the DP's state-action space.

**Was** (`02` §2.3): $A_{z_1}(s) = A$.

**Wrong because.** `11` §3 makes wall and off-grid moves illegal and resolves them
to `WAIT`. If $A_{z_1}$ were the full action set, exact DP would treat that
resolution rule as part of the environment and generate candidates for moves the
agent cannot make — spurious ties and Q-entries, even where the optimal action is
unaffected.

**Now** (`02` §2.4.1):

$$A_z(m, s) \subseteq A_{\text{legal}}(s),\qquad A_{z_1}(m,s) = A_{\text{legal}}(s)$$

with $A_{\text{legal}}(s)$ fixed as the in-grid, non-wall moves.

---

## 22. A21 — retired symbols were still live, and the audit could not see them

**Severity: medium.** Not cosmetic: implementers read these as the data schema.

**Was.** A13 retired $C$ and A9 retired the global reference policy, but both
survived in live prose: `06` §2 still said "the cause truth $C = (c_P,\dots)$";
`11` §7 still wrote $\hat C^{fb}$ in three places; `11` §9 still listed $C$ among
the excluded truth fields; `03` §1 and §4 still used $A$ for but-for relevance
after the rename to $B$; and `11` §5.2 still defined a decision fault against
$\pi_{\text{ref}}$, which A9 had abolished.

**Wrong because — and this is the part worth recording.** `spec_audit.py` was good
at **reference closure** (does `NN §X` resolve?) and blind to **superseded
semantics surviving in prose**. A document set can be a perfectly closed graph and
still tell an implementer to build the wrong thing.

**Now.** The residuals are fixed, and the audit has a third check:

```python
RETIRED = ((r"\\hat C\^\{fb\}", ...), (r"predicts\s*\}?\s*C\b", ...), ...)
```

restricted to *live* lines — a line carrying a retirement marker ("retired",
"withdrawn", "first draft", "**Was**") is a notice quoting the old form, not a
usage, and is skipped. Without that exemption every withdrawal notice would trip
the check and the check would be switched off, which is worse than not having it.

Deliberately **not** a bare regex on `C`: that would flag `C_X`, the controller,
which is alive and load-bearing.

**The check immediately earned its place**, finding three residuals this review
had not listed: `06` §2's live $C$, and two further uses of the retired reference
policy.

---

## 24. A22 — $m$ was part of the decision state but missing from $Q_D$ and $\pi_D^{*}$

**Severity: P0.** Determines what the kernel's `State` object is.

**Was.** `02` §2.3/§2.4 made the admissible set depend on the automaton state —
$A_z(m,s)$ — while the policy objects stayed $Q_D(s,z,a)$ and $\pi_D^{*}(s,z)$.

**Wrong because.** The same $(s,z)$ admits different actions in different $m$. For
$z_2$ at $s=(3,2)$:

$$m=0:\ \texttt{RIGHT} \notin A_{z_2}(m,s) \qquad m=1:\ \texttt{RIGHT} \in A_{z_2}(m,s)$$

No single $Q_D(s,z,\cdot)$ is correct for both, so $(s,z)$ is **not a sufficient
statistic** and the representation is not Markov.

**Now:** $Q_D(s, z, m, a)$ and $\pi_D^{*}(s, z, m)$, with the admissible set
$A_z(m,s)$.

**And the visibility question is closed.** The learner must evaluate $A_z(m,s)$
and index the table, so

$$x^{D}_t = (s_t,\; z_t,\; m_t) \quad\text{— learner-visible internal control state}$$

$z_t$ and $m_t$ are the agent's own control commitments, with exactly the status
of $a^{cmd}_t$ (`01` §2.3). Hiding one's own control state from oneself is
manufactured partial observability. They therefore **enter the identifiability
signature's usable information set** (`03` §3.1): a field the policy may read but
the identifiability analysis may not would be an undeclared third category, which
`01` §2.2 forbids.

$Z_P$ does not become trivial: knowing *which* option is in force says nothing
about whether it *matched* the context, which is the fault.

---

## 25. A23 — the hazard phase made $s_t$ non-Markov

**Severity: P0.** Would have made DP and Q-learning solve the wrong object, and
agree with each other while doing it.

**Was.** $\phi \in \{0,\dots,5\}$ was introduced as a tape key while $s_t$ carried
only the *current* hazard occupancy.

**Wrong because.** Two episodes can share
$(x, y, t, \kappa, \text{occupancy now})$ and still have different **future**
schedules, so $P(s_{t+1} \mid s_t, a_t)$ is not determined by $s_t, a_t$. Both the
tabular Q-table and the finite-horizon DP would be ill-posed — and would agree
with each other, which is the hardest kind of error to notice.

**Now**, option A of the three the review listed:

$$\boxed{s_t = (x_t, y_t, t, \kappa, \phi)} \qquad 5 \times 5 \times 13 \times 2 \times 6 = 3900 \text{ states}$$

$$\text{hazard\_at}(t,\kappa,\phi) = \mathbf{1}\bigl[t \equiv \phi \pmod{p(\kappa)}\bigr]$$

$\phi$ is drawn uniformly, is a tape key, is **visible**, and lives in the state.
The earlier fixed phase offsets are gone: a fixed phase is not a distribution over
schedules, and the document had simultaneously described the schedule as frozen
and the tape as supplying uncertainty about it.

**Consequential:** $z^{*}(\kappa)$ is retired. If the best option can depend on the
hazard phase, "context-appropriate" cannot be a function of $\kappa$ alone. Rather
than replace it with $z^{*}(s)$ — which would need the DP, and re-circularise the
generator against step 2 — **the fault generator no longer consults $z^{*}$ at
all**: $Z_P$ draws $z' \in \mathcal Z \setminus \{z\}$ uniformly, and whether that
hurt is $B$, computed by intervention. $z^{*}(s) = \arg\max_z V_z^{*}(s)$ survives
as a **derived reporting quantity**, computed after the DP, never as a generation
input.

---

## 26. A24 — joint interventions had no semantics, and the fault generator could escape the option

**Severity: P0.**

**Was, part 1.** The well-formedness rule was stated for a single $do(d_t)$. But
$R^{*}$ is a **set**. Checking each member against the **factual** prefix is wrong
as soon as the set has two members: $do(d_2=a')$ changes the trajectory, so at
$t=5$ the counterfactual $(s_5^{cf}, m_5^{cf})$ differs, and a second intervention
validated against the factual prefix may repair a decision that does not exist, or
write an action no longer admissible.

**Now:** the intervention set is **fixed once, before the rollout**; validity is
checked against the **current counterfactual** at each intervened $t$; any failure
marks the **entire candidate `MALFORMED`** — not clamped, not skipped, not
partially applied. Two interventions on the same structural node are `MALFORMED`
too, their composition being undefined.

**Was, part 2.** `11` §6 required only that a decision fault's $a'$ be *physically
legal*. A17 fixed the counterfactual side and left the generator free to violate
its own option — so a nominal "decision fault" could step outside the obligation,
i.e. perform a process-level change while labelled local.

**Now:**

$$a' \in A_z(m_t, s_t) \setminus \{\pi_D^{*}(s_t, z, m_t)\}$$

inside the option, not adjacent to it.

---

## 27. A25 — the tape support was complete but had no measure or decoder

**Severity: P0.** The kernel could not have generated the promised feedback distribution.

**Was.** The support was written out — `error_flag` $\in \{0,1\}$ and
`cause_choice` $\in \{P,D,X,E,U\}$ — while §7 promised $P(\text{wrong}) = 0.4$ and
*uniform over the eligible causes*.

**Wrong because**, in two distinct ways:

1. **A two-point support does not imply $1/2$.** $P(\texttt{error\_flag}=1) = 0.4$
   is an extra fact that nothing stated.
2. **A five-valued draw cannot be decoded uniformly onto an eligible set of size
   2, 3 or 4.** Taking a rank modulo $\lvert E\rvert$ from a uniform draw on
   $\{0,\dots,4\}$ is uniform only for $\lvert E\rvert \in \{1,5\}$. For the common
   cases the feedback distribution was silently **non-uniform**, and nothing in the
   document said so.

**Now** — support, measure and decoder all frozen:

| key | domain | measure |
|---|---|---|
| `("hazard","phase")` | $\{0,\dots,5\}$ | uniform |
| `("feedback","error_flag")` | $\{0,1\}$ | $P(1) = 0.4$ |
| `("feedback","cause_rank")` | $\{0,\dots,59\}$ | uniform |

$$\lvert\mathcal T\rvert = 6 \times 2 \times 60 = 720$$

$60$ is divisible by $1,2,3,4,5$, so $i = \texttt{cause\_rank} \bmod \lvert E\rvert$
is **exactly uniform on any non-empty eligible set** $E$.

**And the empty case is frozen, not resampled.** $Z=(1,1,1,1,1)$ with
`error_flag=1`, and $Z=(0,0,0,0,0)$ with `error_flag=0`, leave $E=\varnothing$;
the claim is then $\varnothing$. Resampling would condition the feedback
distribution on $Z$, reintroducing the outcome-conditioning A2 removed. The
frequency of $E=\varnothing$ is counted and reported.

---

## 28. A26 — the A21 cleanup was incomplete, and the audit had false negatives

**Severity: medium**, but it is the amendment that says the most about method.

**Was.** A21 claimed the retired symbols were cleared. They were not: `11` §6.3
still used $A_i$; the canonical conversion rule and §11.2.4 still consulted the
retired reference policy; the frozen list still read "causal relevance $A$"; `03`
still said *mutually redundant … $A=(0,\dots)$*; and `route_check.py`'s comment
still said it "must pass before `src/rfl_rebuild/env/` is written", contradicting
the order A16/A19 had just fixed.

**Also wrong:** `03` said resampling is "used by the evaluator when computing $B$".
**But-for relevance holds $\omega$ fixed** and removes one fault to compare
outcomes; resampling $\omega$ is a different operation and is not a but-for test.

**Now.** All cleared. But the substantive finding is the one about the check
itself:

> **`spec_audit.py` had false negatives, and A21 was written as if it did not.**

A21's claim "the residuals are fixed" rested on a check that only matched a few
literal spellings. It missed LaTeX variants and semantically equivalent phrasing.
So the fix was not only to clear the text but to **widen the pattern table** —
`Q_D(s,z,·)` without $m$, `\pi_{\text{ref}}` in any form, `A_i`, `causal
relevance`, `z^{*}(\kappa)` — and to re-run it until clean.

**Widening it immediately found 26 hits**, including four the review had not
listed. The lesson, recorded because the same shape has now appeared four times in
this project: **a check that passes is not evidence that the thing is right; it is
evidence only that the check did not look.** The retired-semantics check is now
part of the standing audit (`scripts/spec_audit.py`), so the next residual is
caught by machine rather than by a reviewer reading closely.

---

## 30. A27 — the control state had no home in the observation model

**Was.** A22 made $z,m$ learner-visible and put them in $Q_D(s,z,m,a)$, but
`01` §2.1 still listed only `obs_t`, §2.2 listed only the hidden set, and `01`
insisted *"every field is either observable or hidden, no third category"*. So
$z,m$ **were** the forbidden third category. `11` §5 still wrote
$a^{cmd} = \arg\max_a Q_D(s,z,a)$; §12.1 still wrote $Q_D^{*}(s,z,a)$ and
$A_z(s)$; §12.2's left-hand side had $m$ while its right-hand side dropped it.

**Now** (`01` §2.1.1, `11` §5/§12):

$$I_t = (obs_t,\; z_t,\; m_t),\qquad Q_D(x^{D}_t, a),\qquad A_z(m_t, s_t)$$

with the rule restated to cover the control state. **$z_t$ and $m_t$ enter the
identifiability signature's usable information set** — an analysis restricted to
`obs_t` would understate what a method may legitimately use and manufacture a
false identifiability failure.

## 31. A28 — $Z_P$ still consulted $z^{*}$, restoring the circularity

**Was.** A23 removed $z^{*}$ from the generator; `11` §6 still wrote
$z' \neq z^{*}$. Not a wording issue: an implementer following it would put a
**DP-derived** quantity back into a **step-1** generator, restoring exactly the
dependency A19 removed.

**Now** (`11` §6.4):

$$z' \sim \text{Uniform}\bigl(\mathcal Z \setminus \{z\}\bigr)$$

with no reference to $z^{*}$ anywhere in the generator. Whether the substitution
hurt is $B$, computed by intervention. $z^{*}(s)$ survives only as a derived
reporting quantity.

**And $do(z=z')$ is now frozen as an episode-start intervention** (`11` §6.5):
it sets the option for the whole episode with $m_0(z') = 0$. The automaton state
is **not inherited** — $M_z$ differs between options and one option's progress
carries no meaning for another's obligations. Left unsaid, the kernel would have
decided it.

## 32. A29 — the order of events within a step was undefined

**Was.** The state was Markov (A23) but the within-step order was not stated. Two
readings were consistent with the text and differ observably: hazard-check-then-move
versus move-then-hazard-check. They change when `rush` collides, what
$\text{clear}(s)$ means, how $z_3$ behaves, which of P1–P4 have witnesses, and
later the Bellman target.

**Now** (`11` §1.1), frozen:

$$(s_t,z,m) \to a^{cmd}_t \to u_t \to a^{realized}_t \to (x_{t+1},y_{t+1}) \to t{+}1 \to \text{hazard check} \to \text{terminal/reward} \to m_{t+1}$$

with three consequences spelled out rather than left to be derived: the hazard is
checked against the **newly occupied** cell; $\text{clear}(s)$ tests the hazard at
the current step; and the automaton updates **last**, so an obligation discharged
by the move just made is available to the next decision.

## 33. A30 — three marginals do not determine the joint, and §7 contradicted the decoder

**Was, part 1.** Only marginals were given. If `error_flag` correlated with
$\phi$, feedback reliability would vary with the hazard schedule and the channel
would leak information about $\phi$ beyond what `obs` carries — an undeclared
second information path.

**Now** (`11` §8.1.1):

$$P(\phi, e, r) = P(\phi)P(e)P(r),\qquad P(\phi)=\tfrac16,\ P(e{=}1)=0.4,\ P(r)=\tfrac1{60}$$

**Was, part 2.** §7 said the channel "never emits the empty vector when a fault
exists", while A25's decoder correctly yields $\varnothing$ for $Z=(1,1,1,1,1)$
with `error_flag=1` and for $Z=(0,0,0,0,0)$ with `error_flag=0`. Two rules in one
document, contradicting each other.

**Now:** §7 says the channel *aims* at non-empty but does not guarantee it, and
defers to the decoder.

## 34. A31 — $Z_U$ was a description, not a mechanism

**Was.** *"a rare cell-specific trap the agent's hypothesis space has no symbol
for"* — and nothing about what the trap does to the transition. The kernel is the
single source of truth, so an implementer would have invented the SCM.

**Now** (`11` §6.6):

$$\boxed{Z_U:\ \text{entering cell } c^{*} \text{ at step } t^{*} \text{ is an immediate terminal failure}}$$

with $c^{*} \notin \{\text{start}, G\}$ drawn into $M$. Terminal and immediate, so
no later action can undo it — which is what "unmodelled" means for repair; cell-
and-time specific, so it is not a rule the agent could learn; evaluation-only, so
the learner must express it as $p_U > 0$ (case **C5**). $Z_U$ is the family's only
cause whose repair truth is routinely $\varnothing$, making it a second
"update nothing" case alongside C8.

**Residual cleanup in the same pass:** `02` §6 still said *assign $C$* / *carry
$C$*; `11` §6.3 and the frozen list still used $A$ for but-for relevance. Cleared,
and the retired-pattern table widened again — it found **14 more hits**, which is
the third time the widened check has found residuals a review had not listed.

Also noted for the Gate generator, not blocking the kernel: `03` §4's
$\lvert\mathcal L\rvert$ formula still does not match
$\ell = (Z, M, \kappa, z, \theta_{C_X}, \epsilon_E, \omega)$ and its row
description omits $M$; and `03` still says resampling is used to compute $B$,
which contradicts but-for relevance holding $\omega$ **fixed**. Both must be fixed
before the identifiability generator is written.

---

## 36. A39 — `rush` was an unconstrained superset, so it dominated every specialised option

**Severity: P0 (design).** Found by the exact DP on its first run, not by review.

**Was** (`02` §2.4.2): $A_{z_1}(m,s) = A_{\text{legal}}(s)$ — `rush` carried **no
obligation at all**.

**Wrong because.** The optimal policy *inside* an unconstrained option is simply
the unconstrained optimum. Three consequences, all measured:

$$z^{*}(s) = z_1 \;\;\text{for every } (\kappa,\phi)$$

the optimal `rush` trajectory under $\kappa=1,\phi=2$ is

$$\texttt{RIGHT, WAIT, RIGHT, RIGHT, RIGHT}$$

— it waits out the hazard and succeeds, so `rush` is not a rush; and property
**P1** ("`rush` succeeds iff $\kappa=0$") is therefore **false**, because inside
`rush` the DP can imitate every specialised option. `wait_then_cross` merely
*tied* it (0.90 vs 0.90) rather than beating it.

This is A9 in mirror image. A9 removed "four names for one policy" by giving the
options obligations; the resulting constraint set was degenerate in the opposite
direction, because exactly one option was unconstrained and therefore dominated.

**Now** (`02` §2.4.2), with $d_G$ the static shortest-path distance to $G$ over
the open-cell graph:

$$\boxed{A_{z_1}(0,s) = \bigl\{a \in A_{\text{legal}}(s) : d_G(\text{enter}(a,s)) = d_G(\text{cell}(s)) - 1\bigr\}}$$

Strict descent implies $\texttt{WAIT} \notin A_{z_1}$ and forbids any detour. From
$S$ it is exactly `RIGHT, RIGHT, RIGHT, RIGHT`; displaced by an execution fault it
resumes descending rather than deadlocking.

**Why this is not "tuning the environment until P1 passes".** The constraint reads
**no result**: not $Q^{*}$, not $z^{*}$, not `hazard_at`, not the reward. $d_G$ is a
property of the static grid alone, computed once by BFS at import. It states a
pre-declarable behavioural commitment — *rush always advances along the static
shortest path* — and the environment then decides where that commitment is good and
where it is bad. That is categorically different from *"if a hazard is detected,
forbid action $a$"*, which would write the correct answer into the option.

**P1 is restated over the full context.** With $\phi$ in the state (A23), the old
predicate keyed on $\kappa$ alone is the wrong predicate; what decides whether the
short corridor is safe at $t=2$ is $(\kappa,\phi)$:

$$\text{P1a}:\ \neg\text{hazard\_at}(2,\kappa,\phi) \Rightarrow \text{4-step success}$$

$$\text{P1b}:\ \text{hazard\_at}(2,\kappa,\phi) \Rightarrow \text{collision at the contested cell on step 2}$$

$$\text{P1c}:\ \bigl|\{z^{*}(s_0(\kappa,\phi))\}_{\kappa,\phi}\bigr| \ge 2$$

P1c is the assertion that closes this degeneracy. It deliberately does **not**
require a particular winner in the hazardous contexts: whether `wait_then_cross`,
`detour_upper` or a tie wins is for the DP to report, not for the environment to
arrange.

**Measured after the fix** (exact DP, 12 contexts): $z^{*}$ is `rush` in 9 and
`wait_then_cross` in 3 ($\kappa{=}0,\phi{=}2$; $\kappa{=}1,\phi{=}2$;
$\kappa{=}1,\phi{=}5$) — so $|\{z^{*}\}| = 2$, P1c passes. `rush` scores $+0.92$
(4 steps) where the corridor is clear and $-1.04$ (collision) where it is not.

**Consequence for fault injection:** $A_{z_1}$ is a **singleton** at most cells
(strict descent usually admits exactly one move), so there is frequently no
alternative action to substitute. A $Z_D$ fault must be injected under an option
with room. The kernel regression test that injected $Z_D$ under `rush` was moved
to `z_2` for this reason — and its failure after A39 was correct behaviour, not a
regression.

**Test replaced, not deleted.**
`test_z1_is_unconstrained_and_therefore_dominates` became
`test_z1_is_static_shortest_path_descent`, and
`test_the_context_appropriate_option_is_meant_to_depend_on_context` became
`test_best_option_depends_on_full_context`, which asserts P1c directly.

---

## 37. A40 — P2 required repair *uniqueness*, contradicting the ontology and deleting V0.2R's hard cases

**Severity: P0 (property definition).** Found by `route_check`, not by review.

**Was** (`11` §4): P2 read *"an episode with $|R^{*}| = 1$ whose **unique member**
is a decision intervention"*. `route_check` implemented that as
`len(rescuing) == 1` and it **FAILED**.

**The full enumeration, reported before anything was patched.** 26 candidate
episodes, each with its entire size-1 family evaluated:

| n rescuers | 5 | 9 | 11 | 12 | 15 |
|---|---:|---:|---:|---:|---:|
| episodes | 6 | 3 | 4 | 5 | 8 |

No episode had exactly one rescuer. But **the failure was in the operationalisation,
not the environment**:

1. **Uniqueness directly contradicts `02-SCM.md` §5.2**, which freezes size and
   candidate count as separate quantities, makes tied size-1 repairs first-class,
   and **prohibits** any metric that assumes a unique repair. Requiring
   $\#R^{*} = 1$ here is not extra strictness; it is working against the
   repair-truth ontology the spec just built.
2. **It would have required editing the map until repairs became unique** — which
   is precisely deleting the tie cases V0.2R's tie-handling **structural
   pass/fail endpoint** exists to face. A gate that can only be satisfied by
   removing the phenomenon under study is the wrong gate.
3. **The enumerator was also incomplete.** It tried only
   $\mathcal F_{\text{decision}} \cup \mathcal F_{\text{execution}}$, so even a
   correct uniqueness claim about $R^{*}$ would have been unsupported:
   $do(z=z')$ can rescue too and was never tried.

**Now:**

$$\boxed{\exists e:\ \min_{r\,\text{sufficient}} |r| = 1 \ \wedge\ \exists r \in R^{*}(e),\ r = \{do(d_t = d')\}}$$

$$\boxed{\#R^{*} = 1 \text{ is \textbf{not} required.}}$$

And `route_check` enumerates the full
$\mathcal F_1 = \mathcal F_{\text{process}} \cup \mathcal F_{\text{decision}} \cup \mathcal F_{\text{execution}}$,
reporting candidate count, unique-site count and per-kind counts as **diagnostics**.
Ties are described, never penalised.

**Measured after A40:** P2 **PASS**. Witness: `kappa=0, phi=0`, option
`detour_upper`, decision fault at $t=5$ to `LEFT`, factual outcome `COLLISION`.
Family 32, malformed 0, **18 rescuing candidates over 9 unique sites** —
15 decision, **3 process**, 0 execution. `do(z=rush)` is itself a rescuer.

That last row is the point: the same episode has both a Decision singleton and a
Process singleton that suffice. *"Minimal size is 1"* and *"the minimal repair is
unique"* are different questions, and only the first is P2's.

**Why a weak P2 is correct.** P2 is an **environment coverage gate** — it asks
whether the benchmark contains the object *"a local Decision-level repair"* at
all. It does not ask whether a Decision is the only correct explanation; that is
V0.2R's question. **P1–P4 establish that the environment can express a mechanism,
not that RFL works.** Making P2 look like a main hypothesis would be the error.

**Also fixed in the same pass:** `check_p2`'s PASS branch referenced an undefined
`t` for `fault_t` (it should be `st.t`). It never executed while P2 was failing,
so the defect was invisible — a reminder that a FAIL can hide a bug in the success
path.

**P3/P4 caveat, accepted and not acted on.** Their local family is only 4 members,
because after A39 $A_{z_1}$ is a singleton at most cells, so few local repairs
exist along a failed `rush` and the negative half is easy to satisfy. This is
correct behaviour, not a defect: `route_check` is an existence/coverage gate, not
an effect-size test. Guarding against "too few process cases, all representations
look alike" is V0.2R's **development gate**, which already requires the four
representations to differ on a non-trivial fraction of episodes. The environment
is **not** to be pre-tuned for that gate.

---

## 38. A50 — query availability is itself partially observable

**Severity: P0 (semantics).** Found by Stage 3's independent-replay assertion, on
its first run, after the earlier `query_family_conflicts == 0` check had reported
clean for two rounds.

**Was.** `03-IDENTIFIABILITY.md` §1.6 asserted

$$\forall \ell_i, \ell_j \in C:\quad \mathcal Q_{\text{legal}}(\ell_i) = \mathcal Q_{\text{legal}}(\ell_j)$$

on the grounds that members of a factual class share the same factual $I_t$.

**The counterexample.** A factual class of size 430 containing
$Z = (0,1,0,0,0)$ with `base_option = 1` and
$D = \texttt{DecisionOverride}(t{=}0, \texttt{WAIT})$. The query $do(z = \texttt{rush})$
is **well formed** for that case's siblings but **MALFORMED** for it: under `rush`,
$A_{z_1}$ admits only strict static descent (A39), so at `START` it is exactly
$\{\texttt{RIGHT}\}$, and `WAIT` is outside. Per `02` §5.0.1 the whole candidate is
then MALFORMED.

Two cases therefore share an identical factual observation while admitting
different query families, because **query legality depends on the latent $M$**:

$$\boxed{\mathcal Q_{\text{legal}} \text{ depends on } (I^{factual}_t \textbf{ and } M^{latent})}$$

**The three rejected repairs, and why.**

* **(d) partition by $\mathcal Q_{\text{legal}}$** — this was rejected outright, and
  the reason is the sharpest part of the ruling. If the class key became
  $(I_t, \mathcal Q_{\text{legal}})$, then two worlds the learner **cannot tell
  apart observationally** would be split apart by a hidden-$M$-derived quantity.
  That is a new information channel dressed up as a partition refinement: it tells
  the learner *"although you cannot see $M$, I will tell you in advance which
  questions are legal here."* It reintroduces the very leakage §1.6 forbids, only
  as a legal-query menu instead of a MALFORMED sentinel.
* **(b) legality against the factual option** — rewrites counterfactual
  well-formedness.
* **(c) MALFORMED as a sentinel response** — leaks hidden $M$ through illegality,
  and contradicts §1.6.

**Now — (a\*), information-state safe legality:**

$$\boxed{\mathcal Q_{\text{learner}}(H) = \bigcap_{\ell \in H} \mathcal Q_{\text{semantic}}(\ell)}$$

where $H$ is the current information set, determined by the factual observation and
the query-response history so far.

* **factual classes still partition by $I_t$ alone** — Stage 2's 2,921 classes stand
  unchanged, and the partition is **not** re-derived from hidden legality;
* $\mathcal Q_{\text{legal}}(\ell)$ is evaluator-side hidden structure, used only to
  decide whether an intervention is well formed *in that world*;
* the learner **never observes it**, and may only select queries that are legal in
  **every** still-possible world;
* after a response, $H$ shrinks and $\mathcal Q_{\text{learner}}(H)$ can **grow**;
* **MALFORMED is never an observation.**

**Why the intersection is not conservatism.** Under partial observability, an agent
may not choose an action that is well defined in only some of the worlds it still
considers possible. If it did, and the true world were one of the others, the only
options would be to return MALFORMED (leak), refuse the query (leak), or let it
execute (rewrite the SCM). Intersection is the only epistemically clean choice
given the frozen constraints.

**The consequence for the gate's proof structure.** Under the old assumption, a
root-level unlimited signature that failed to separate implied
`FAIL_UNIDENTIFIABLE_EVEN_UNBOUNDED`. It no longer does:

$$\boxed{\text{unsafe at the root} \;\not\Rightarrow\; \text{unsafe forever}}$$

A query unsafe at the root may become safe one level down, after an earlier
response has eliminated the world that made it malformed. So Stage 3 is the
**non-adaptive fallback only**: it searches $S \subseteq \mathcal Q_0(C)$ with
$|S| \le B_{CF}$, where $\mathcal Q_0(C) = \bigcap_{\ell \in C}\mathcal Q_{\text{legal}}(\ell)$;
a hit is a sound `PASS_NONADAPTIVE`, a miss is `INCONCLUSIVE_NEEDS_ADAPTIVE` and
nothing more. Stage 4 is the history-dependent adaptive tree,

$$D(H) = 1 + \min_{q \in \mathcal Q_{\text{learner}}(H)} \max_o D(H_o), \qquad D(H) = 0 \text{ if all } \ell \in H \text{ share one } Z$$

with $D(H) = \infty$ only when $\mathcal Q_{\text{learner}}(H) = \varnothing$ while
$H$ still spans multiple $Z$ — which is now the **only** route to
`FAIL_UNIDENTIFIABLE`. Gate L remains $B_{\min}^{\text{adaptive}} = \max_C D(C) \le B_{CF}$.

**The deeper point, recorded because it generalises.**

$$\boxed{\text{Observation} \to \text{belief} \to \text{safe intervention set}}$$

The project had assumed *same factual observation $\Rightarrow$ same executable
intervention set*. That is false. It is the same shape as the project's oldest
principle, $Evidence \neq Truth$: the evaluator knowing that a query is legal in the
true latent world does not make it legal for the learner.

**No environment change, no A39 change, no fault-mask change.** Only the
identifiability semantics changed.

---

## 39. A51 — Gate L splits in two, and both gates fail

**Found by**: running Gate L to completion under A50. Stage 3 had left 2,695
classes ``INCONCLUSIVE_NEEDS_ADAPTIVE``, which reads like "the non-adaptive
fallback was too weak". Stage 4 shows the adaptive machinery does not rescue
them either: $H$ shrinks legally and $\mathcal Q_{\text{safe}}(H)$ grows, and
still no finite depth reaches a single target. That is a theorem about the
observation–intervention interface, not a missing feature.

**Withdrawn, and recorded because it was nearly a real error.** The first
reaction was to *replace* the gate's target $Z$ with $B$ and call it a criterion
fix. That is not a bug fix:

$$\boxed{\text{changing the gate target from } Z \text{ to } B \;\neq\; \text{fixing a criterion bug}}$$

$Z \neq B$ is load-bearing in this project, and in an overdetermined world a
genuinely present fault can have $B_i = 0$ — two real faults can each be
non-difference-makers because they are redundant with one another. So the swap
**changes V0.1R's scientific question**. `06-V01R.md` has V0.1R claiming to
recover *which faults occurred*; licensing that with a $B$-gate would let a
learner fail to recover $Z$ and still pass. The target is therefore **not**
overwritten.

**The result instead — two gates:**

$$\boxed{\text{Gate}_Z:\ \text{fault-presence identifiability}} \qquad
  \boxed{\text{Gate}_B:\ \text{but-for-relevance identifiability}}$$

| gate | target | verdict |
|---|---|---|
| **Gate_Z** | $Z$ | **FAIL** — 2,695 / 2,749 multi-$Z$ classes provably unidentifiable at any finite depth |
| **Gate_B** | $B$ | **FAIL** — 432 classes provably unidentifiable at any finite depth |

This is the *stronger* statement: Gate_Z does not fail merely because $Z$ is too
demanding. Even after retreating to but-for relevance — the weakest target that
is still action-relevant — the learner's query set remains insufficient.

**Root cause of Gate_Z.** `identifiability_gate.canonicalise` takes
`[domain[0], domain[-1]]` under the frozen order and is **deliberately
outcome-blind**, while `_domains` populates `U` with `Trap(cell, t)` for every
open cell at every step of the healthy trace. Most of those traps cannot fire, so
the canonical first/last element is generally a trap with no effect on the
trajectory, the feedback, or the outcome. A fault that cannot fire is
observationally identical to its absence at every budget, by construction.
Attribution of the unbounded classes' witness pairs: `U` alone 2,435,
`X` alone 218, `X+E` 42.

**Root cause of Gate_B, and why it is not patchable.** $B_i$ is defined by
*removing* fault $i$ and comparing outcomes, but the learner's intervention
lattice

$$\mathcal I = \{do(z{=}z')\} \cup \{do(d_t{=}d')\} \cup \{do(C_X(s^\ast,a^{cmd}){=}a^{cmd})\} \cup \{\emptyset\}$$

contains **no operation that removes a fault**. A process query changes
`base_option`; it does not switch $Z_P$ off. Attribution of the 432: `E` 294,
`P` 108, and no `X`, `D` or `U` term.

Adding $do(Z_i = \text{off})$ is **rejected and the rejection is frozen**: that
operation *is* the but-for test, so using it to certify that $B$ is identifiable
installs the ground-truth construction itself as a diagnostic query, and the gate
would pass by construction while measuring nothing. Same class of error as
A50(d) — silently promoting a structure the evaluator has into a structure the
learner may access.

**Consequences frozen here.** $B_{CF}$ is **not** raised (it buys exactly zero
classes; $\max_C D(C) = 1$ over every decidable class, so the budget was never
the binding constraint). The environment is **not** tuned. The unbounded classes
are **not** dropped. **V0.1R seed collection is paused**, because `06-V01R.md`'s
go/no-go requires Gate L to PASS and it does not pass under either reading.

Full record: `13-GATE-L-FAILURE.md`. Quotient analysis: A52.

---

## 41. A53 — a budgeted plant-input audit query, and why it cannot be enough

**Decision taken**: add an independent plant-side diagnostic **before** any
process audit. Not $u_t \in obs_t$ permanently, but an on-demand, budgeted query

$$\boxed{q^{plant}_t = \mathrm{audit\_plant\_input}(t), \qquad \text{response} = u_t, \qquad \operatorname{cost} = 1}$$

where $u_t$ is the low-level command the plant actually received — the middle
link of $a^{cmd}_t \to C_X \to u_t \to P \to a^{realized}_t$. Since $a^{cmd}_t$
and $a^{realized}_t$ stay visible, one paid audit exposes the whole chain and
lets the learner separate $u_t \neq a^{cmd}_t$ (controller/internal) from
$a^{realized}_t \neq u_t$ (external plant).

**Why $E$ first.** The boundary already exists in the SCM and needs no new
ontology; reading an actuator bus, a command echo or a low-level control log is
ordinary practice in real robot, AV, industrial-control and software-execution
systems. It is not a but-for oracle: it does not execute $do(Z_E{=}0)$ and does
not report $B_E$ — it returns a mechanism signal and leaves the conclusion to the
learner. A process audit would have required deciding first what $Z_P$ *means*
(planner chose badly / proposal swapped in the commit layer / strategy unsuited
to context — three different things), and the SCM does not yet carry enough
structure to do that without quietly rewriting the ontology. So Process is left
untouched.

**What is rejected, and frozen.** Publishing $u_t$ every step for free:
`01` already fixes $u_t \neq a^{cmd}_t \Rightarrow$ internal and
$a^{realized}_t \neq u_t \Rightarrow$ external, so free $u_t$ turns the $X/E$
structural distinction into a read-off instead of an inference. A diagnostic
capability must be a **resource**, not an oracle field. Also rejected: ever
returning `plant_fault`, $B_E$, or success/failure.

Because queries are no longer all counterfactual rollouts the total budget is
written $B_Q$. The **value is unchanged** at $B_Q = 4$: this is a renaming, not a
loosened threshold.

**Result of the full re-run** (Gate_Z and Gate_B both recomputed):

| | before A53 | after A53 |
|---|---|---|
| Gate_Z residual | 2,695 | **2,665** — still FAIL |
| Gate_B residual | 432 | **261** — still FAIL |
| Gate_B witnesses attributed to `E` | 294 | 109 |
| Gate_B witnesses attributed to `P` | 108 | 122 |
| $\mathcal B/{\sim}$ components | 7 | 6 |

$B_Q$ is still not the binding constraint in either gate: the largest finite
adaptive depth is **2** under Gate_Z and **3** under Gate_B, both below 4. So the
audit bought real classes (171 of Gate_B's 432 became decidable) but no budget
increase would buy the rest.

The `P` figure rising from 108 to 122 is not a regression. It is the per-class
*first* unseparable witness, and when the query family changes, a different pair
becomes the first one found. The attribution locates an obstruction; it is not an
additive count over axes. Recorded so the number is not misread later.

**The structural finding, which is the real result.** The 109 surviving `E`
witnesses were extracted and saved (`a53_e_witnesses.json`). In **all 109**:

* the plant fault **does** fire on the factual rollout, in **both** worlds;
* the controller fault fires in **neither**;
* the two worlds are **identical through the audit — every $u_t$ agrees**.

They nevertheless differ in $B_E$. The two worlds differ only in latent
parameters (`base_option`, `trap`) that have **no factual effect at all**, yet
change the outcome of the *fault-removed* rollout — and $B_E$ is exactly whether
that rollout's outcome changes.

$$\boxed{\text{the current factual execution interface} + \text{plant telemetry cannot identify these } B_E}$$

**Deliberately narrower than it was first written.** An earlier wording claimed
"no factual telemetry, however rich, can identify $B$", and that is too strong.
The witness worlds differ in `base_option` and in the trap configuration — those
are *factual* latent variables. A real system with legitimate
provenance/configuration telemetry could distinguish the two worlds without ever
calling $do(Z_E{=}\text{off})$. So what the witnesses prove is the weaker and
still-strong claim in the box, not an impossibility over all possible factual
information. The impossibility is specific to telemetry on the *action path*.

Escalating the plant audit is therefore still not the answer — it reads the same
action path — but the honest reason is that it does not touch the differing
variables, not that no diagnostic could ever help. This distinction is what A54
turns on: `base_option` and `trap` are configuration, and configuration is a
*factual* thing a provenance channel may legitimately report.

**Consequences.** Gate_Z and Gate_B are both **FAILED**. Merge is still
unavailable — $\widetilde{\mathcal B}$ still discards exactly $(P, E)$ (A52), and
those are Process and Environment. **V0.1R seed collection remains paused**, and
A53 does not change that even if Gate_B had passed, because V0.1R's primary
target is $Z$ and Gate_Z is dominated by dormant $U$ faults: faults with **no
behavioural consequence whatsoever** whose *presence* is nonetheless demanded.
Inferring that a consequence-free hidden fault "occurred" is a separate problem
and is not addressed by any diagnostic on the action path.

---

## 42. A54 — configured, fired, difference-making: three objects, not one

**Found by**: A53's residual, and by the absurdity it exposed. `11` §6.1 defined
$Z$ as *fault presence: mechanism actually active*, yet the same environment
enumerates `Trap(cell, t)` for every open cell at every step of the healthy
trace. A trap at a cell the episode never enters is therefore $Z_U = 1$ while the
mechanism never runs. Those dormant traps were the dominant Gate_Z failure mode.
Worse, driving the feedback channel by presence meant a *truthful* feedback claim
could point at a fault that never happened.

Three distinct objects were being carried by one symbol:

$$\boxed{\text{fault configured} \neq \text{fault fired} \neq \text{fault but-for relevant}}$$

**The split.** $Z^{\text{pres}}$ (injected into the latent world) was already
there; $B$ (A2) was already there; the missing middle is

$$\boxed{Z^{\text{fire}}_i = 1 \iff \text{the mechanism actually executed on the factual trajectory}}$$

with $Z^{\text{pres}}_i \ge Z^{\text{fire}}_i$ always. `kernel.fired_mechanisms`
computes it from a single factual rollout with no counterfactual: $Z^{\text{fire}}_P$
iff the option in force differs from `base_option`; $Z^{\text{fire}}_D$ iff the
episode was still alive at the override's timestep; $Z^{\text{fire}}_X$ iff some
step has $u_t \neq a^{cmd}_t$; $Z^{\text{fire}}_E$ iff some step has
$a^{realized}_t \neq u_t$; $Z^{\text{fire}}_U$ iff the episode terminated in the
trap. This is the middle row of a three-row table that a single $Z$ could not
express:

| $Z^{\text{pres}}$ | $Z^{\text{fire}}$ | $B$ | meaning |
|---|---|---|---|
| 1 | 0 | 0 | **dormant** — configured, never executed |
| 1 | 1 | 0 | **fired but redundant** — it happened, removing it changes nothing |
| 1 | 1 | 1 | **fired and difference-making** |

The middle row is the overdetermination A2 existed to protect. The top row is a
fault event that never occurred, which the single-$Z$ account invented.

**V0.1R's primary target becomes $Z^{\text{fire}}$.** Stated plainly as a
**scientific-question revision**, because that is what it is:

* $Z^{\text{pres}} \to B$ (the withdrawn A51 proposal) *swaps* diagnosis for
  causal contribution — a different question;
* $Z^{\text{pres}} \to Z^{\text{fire}}$ **stays a diagnosis question**. It only
  corrects *what was secretly configured* to *what actually executed*. V0.1R's
  title is "can the system work out **what happened**?", and a trap placed where
  the episode never went did not happen.

It is not a gate fix, and it is not a relaxation: $Z^{\text{fire}}$ is still a
five-bit diagnosis target, and the learner must still recover it from evidence.

**Feedback channel synced.** `SemanticTape.decode_feedback` is now driven by
$Z^{\text{fire}}$, so the truthful eligible set is $\{i : Z^{\text{fire}}_i = 1\}$
and not $\{i : Z^{\text{pres}}_i = 1\}$. Reporting on a cause that never executed
would be a claim about the generator's private configuration masquerading as a
report about the episode.

**Gate_B demoted to a non-blocking secondary endpoint**, which `11` §6.2 already
required: if $B$ is not identifiable it is reported **not evaluable**, never as an
algorithm negative result. A53 proved it is not identifiable under the current
interface, so it is exactly that case. Chasing Gate_B to green would be fitting
the task to the gate.

**Result — the new gate, and it is the one that matters:**

| gate | target | verdict |
|---|---|---|
| **Gate_fire** | $Z^{\text{fire}}$ | **FAIL** — 600 of 2,783 classes provably unidentifiable at any depth |
| Gate_Z | $Z^{\text{pres}}$ — diagnostic | FAIL — 2,713 |
| Gate_B | $B$ — secondary, non-blocking | FAIL — 245, attribution `E` 95 / `P` 120 |

Gate_fire's depth histogram: $D = 0$ 1,553, $D = 1$ 630, unbounded 600.

$$\boxed{\text{Gate\_fire residual} = 100\%\ P}$$

$E$, $X$, $D$ and $U$ are **fully resolved** by the $Z^{\text{fire}}$ target: the
plant audit and the ontology split together close everything except process
observability. $\max_C D(C) = 1$ and $B_Q = 4$, so — for the third time and
independently — the budget is not the binding constraint.

Census over every feasible case (cause-world pairs, $1{,}541{,}400$ of which have
$Z^{\text{pres}} \neq Z^{\text{fire}}$): $U$ is dormant in $658{,}320$ pairs and
fired in $34{,}320$, and **whenever $U$ fires it is difference-making**; $D$
dormant $141{,}120$, $X$ dormant $377{,}280$, $E$ dormant $364{,}680$; $P$ has
**no dormant cases at all**, because `_domains` draws `option_fault` from
$\mathcal Z \setminus \{\text{base\_option}\}$ so the substitution always takes
effect.

**What follows.** The Gate_fire residual is a *process-observability* problem and
nothing else, which is precisely the branch that makes a process provenance layer
worth building. But building it requires first settling what $Z_P$ **denotes** —
whether the planner chose a bad strategy, or a correct proposal was swapped in a
process/commit layer, or the strategy program was unsuited to the context. Those
are three different mechanisms, and the current SCM does not yet carry enough
structure to instrument one of them without quietly rewriting the ontology.
So the process audit is **not** taken here; it is the next decision, and it needs
the explicit SCM form

$$z^{proposal} \rightarrow \text{process/commit layer} \rightarrow z^{\text{in force}}$$

before anything is instrumented. No new query is added in A54.

---

## 43. A55 — $Z_P$ is commit/routing integrity, and Gate_fire PASSES

**Denotation fixed.** A54 left one question open — what $Z_P$ actually *denotes* —
because three readings were live and they are different mechanisms. It is now
fixed and frozen:

$$\boxed{Z_P = \text{process commit / routing integrity fault}}$$

$$\boxed{\kappa \rightarrow z^{\text{proposal}} \rightarrow C_P \rightarrow z^{\text{in-force}} \rightarrow Q_D(s,z,m,\cdot) \rightarrow a^{cmd}}$$

Healthy: $C_P(z^{\text{proposal}}) = z^{\text{proposal}}$. Faulty:
$z^{\text{in-force}} \leftarrow z' \sim \text{Uniform}(\mathcal Z \setminus \{z^{\text{proposal}}\})$.
Hence $Z_P^{\text{fire}} = \mathbf 1[z^{\text{in-force}} \neq z^{\text{proposal}}]$.

$z^{\text{proposal}}$ is **not** required to be optimal or even correct. The fault is an unfaithful *commit*, not a bad plan. This is the only one of the three candidate readings that matches what the generator actually does, and it needs no dynamics change at all: `base_option` **is** $z^{\text{proposal}}$ and `RolloutTrace.option_in_force` **is** $z^{\text{in-force}}$.

**The other two readings are rejected.** *"The planner chose a bad strategy"* needs a reference for "bad"; using $z^{*}$ restores the solver → generator circularity A19 removed, and without such a reference "wrong" has no structural definition. *"The strategy is unsuited to the context"* is a normative relation $\text{option-suitability}(z,\kappa,\phi)$, not an exogenous injection, and relabelling a uniform substitution as "the strategy itself is wrong" would be exactly the ontology drift A54 was called to stop.

**The process audit, parallel to A53.** $q^{proc} = \mathrm{audit\_process\_proposal}()$, response $z^{\text{proposal}}$, cost 1. Since $z^{\text{in-force}}$ is already in $I_t$, one paid audit exposes the commit edge and the learner infers the fault. It returns a **provenance artifact** — never `process_fault`, never `proposal_corrupted`, never $Z_P$. The parallel with A53's $a^{cmd} \to u_t \to a^{realized}_t$ is exact.

**Three operations, kept apart** (`11` §6.4): `audit_process_proposal()` is the learner's and read-only; $do(z=z')$ is the learner's strategy replay and **not** a process repair; $do(C_P = \text{identity})$, which restores $z^{\text{in-force}} = z^{\text{proposal}}$, is the **evaluator's** but-for construction and stays out of the learner's query set — admitting it would be $do(Z_P{=}\text{off})$ (A51).

**Result:**

| gate | target | before A55 | after A55 |
|---|---|---|---|
| **Gate_fire** | $Z^{\text{fire}}$ | FAIL, 600 | **PASS** — 0 unidentifiable |
| Gate_Z | $Z^{\text{pres}}$, diagnostic | FAIL 2,713 | FAIL 2,713 |
| Gate_B | $B$, secondary/non-blocking | FAIL 245 | FAIL 135 |

Gate_fire depth histogram: $D = 0$ 1,553, $D = 1$ 990, $D = 2$ 230, $D = 3$ 10, unbounded **0**. So $B_{\min}^{\text{adaptive}} = 3 \le B_Q = 4$.

$$\boxed{\text{Gate\_fire PASS at } B_Q = 4}$$

The 600-class residual A54 measured was **100% $P$**, and the process proposal audit closes all of it. $E$ had already been closed by A53's plant audit, and $X$, $D$, $U$ by the A54 split.

**Recorded honestly: the margin is one unit.** $B_{\min}^{\text{adaptive}} = 3$ against a budget of 4. Every previous gate had slack of 3 or more, so this is the first time the budget is anywhere near binding — a single added identifiability requirement would break it. $B_Q$ is **not** raised here, and this is the reason to keep it at 4 rather than the reason to relax it.

Also recorded: Gate_B now needs depth **4** for 20 classes, so for the secondary endpoint the budget *is* binding. That is reported as-is; Gate_B is not blocking (`11` §6.2).

**V0.1R's identifiability precondition is met for the first time.** Seed collection may resume, subject to the remaining go/no-go rows (semantic suite, oracle ceiling, calibration). It is not started here.

---

## 44. A56 — semantic propagation of A54/A55, and the Gate E pre-check

**Scope, deliberately narrow: no environment change, no new query, no new
mechanism.** A54 and A55 changed the ontology, so every document that still
described the old world had to be brought forward *before* the semantic suite ran.
Running `04` first would have tested the old world.

**`02-SCM.md`**

* §1's $Z_P$ row now reads *process commit/routing integrity*, not "the policy the
  episode is being run under is wrong for this context".
* §3's consequence is rewritten. It used to argue that knowing $z^{\text{in-force}}$
  leaves open whether it was right for the context, so $Z_P$ is non-trivial "in
  the match between $z$ and the state". **A55 removed that reading.** $Z_P$ stays
  non-trivial for a structural reason instead: $I_t$ exposes $z^{\text{in-force}}$
  but not $z^{\text{proposal}}$, so the commit edge must be audited.
* §4's target line: V0.1R predicts $Z^{\text{fire}}$.
* §5's lattice gains the missing member:

$$\mathcal I = \{do(z{=}z')\}_{\text{strategy replay}} \cup \boxed{\{do(C_P{=}\text{identity})\}}_{\text{process repair}} \cup \{do(d_t{=}d')\} \cup \{do(C_X{=}a^{cmd})\} \cup \{\varnothing\}$$

  with a new §5.0 laying out the three operations and whose they are. Without it,
  Gate E, $R^{*}_{\text{suff}}$ and V0.2R would keep treating "switch strategy" and
  "repair the commit layer" as the same thing, i.e. A55 would have fixed diagnosis
  while the repair ontology silently slid back.
* §5.1 splits what one formula used to conflate: **what $Z_P$ is** (a commit fault;
  repair $do(C_P{=}\text{identity})$) versus **what "the process is the right
  granularity" is** (a lattice statement, *not* the definition of $Z_P$).

**`04-SEMANTIC-INVARIANTS.md`**

* **I4** restated, because it was in danger of prohibiting what A54 requires:
  $Z^{\text{pres}}$ comes from generation truth, $Z^{\text{fire}}$ from a **forward
  mechanism-fire receipt** emitted by the run, $B$ from the evaluator's
  counterfactual. The prohibition stands unchanged — *no code path may infer a
  cause label from ordinary learner-visible behaviour after the fact* — and the
  line is **forward receipt versus retrospective inference**, not "from the
  machinery" versus "from a rollout".
* **C3** is now a commit-integrity case with a falsifiable signature: a method
  shown $z^{\text{proposal}}$ and $z^{\text{in-force}}$ that still blames a local
  decision fails.
* **C4** keeps the strategy-level statement and is now explicitly **not** the
  definition of $Z_P$. The two come apart in both directions, so the old sentence
  ("distinguishes a genuine process fault from a co-occurrence of locals") is
  removed.

**`06-V01R.md`**

* §2's target is $Z^{\text{fire}}$; §3.1's Oracle ceiling is taken on
  $Z^{\text{fire}}$.
* The budget-bearing arms are renamed **`QueryOnly` / `SeqThenQuery`**. This is
  semantic, not cosmetic: Gate_fire's PASS *depends on* the A53 plant audit and
  the A55 process audit, so an arm restricted to counterfactual rollouts would
  have a strictly narrower information set than the gate credited. The gate would
  have been certifying a method that cannot exist. Interventions and audits now
  share one $B_Q$, each costing 1.
* $B_{CF} \to B_Q$ throughout.

**Terminology correction.** $\boxed{\text{Semantic suite }(04) \neq \text{Gate E}}$.
`04` is the **implementation semantics hard gate** — it asserts on the code's
outputs, and any failure blocks every version's seed collection. Gate E asks a
different question: whether the **evaluator truth and repair ontology are
well-defined** at all. Both must be clean, and they are not the same check.

**Gate E pre-check (`scripts/gate_e_precheck.py`, ~28{,}080 feasible cases
sampled 1-in-37).** Two questions, both about whether A55 broke the lattice:

*well-definedness* — $do(C_P{=}\text{identity})$ must be a no-op exactly when
there is no commit fault, or it would be "repairing" nothing and contaminating
$R^{*}$. Measured: **0 cases** where the commit repair is active without a fault.

*constituent totality* — every failing case must have something in the lattice
that repairs it, and an empty candidate set must be counted rather than silently
becoming an empty $R^{*}$. Measured: `no_repair_needed` 25,043,
`size1_repairable` 3,037, **`not_size1_repairable` 0**. The lattice is total for
size-1 repairs.

*the A55-specific separation*, which is the interesting number: among failing
cases the commit repair suffices for **2,374** while a strategy replay is needed
for **663**. So the two operations are empirically distinct, not merely
semantically — there are 663 cases where switching the strategy repairs the
episode and restoring a faithful commit does not. Those are precisely the C4
episodes, where the proposal itself is a poor option and the fault is *not* a
commit fault. Conflating the two would have mislabelled all 663.

Of 17,573 P-fired sampled cases, the commit repair changed the outcome in 3,202
and left it unchanged in the rest — consistent with A54's "fired but redundant"
regime: the trajectory changes, the outcome does not.

**Regression canary.** The **10 Gate_fire classes at $D = 3$** are the entire
margin between PASS and FAIL ($B_Q = 4$). They are recorded as a canary: any
future query-semantics change must first confirm none of them slides from $D = 3$
to $> 4$. With one unit of slack, a silent regression here would flip the gate.

**Execution order from here** (all four must pass before seed collection resumes):

$$\text{A56} \rightarrow \text{Gate E} \rightarrow \text{Semantic suite }(04) \rightarrow \text{Oracle ceiling} \rightarrow N_{\text{scenes}}{=}32 \text{ calibration}$$

A56 is complete. Gate E's lattice question is answered above; the semantic suite
is **not** run here.

---

## 45. A57 — commit repair becomes first-class, and formal Gate E

**The gap.** A56 wrote $do(C_P{=}\text{identity})$ into the repair lattice in
`02` §5, but the code still had only three `Intervention` kinds — `process`,
`decision`, `execution` — and `gate_e_precheck.py` simulated the commit repair
with a boolean bypass (`commit_repair=True`, blanking `option_fault`). That is
acceptable for a smoke check and **not** acceptable for a formal gate, because it
distorts four separate things: the repair does not count toward $|r|$; it cannot
appear in a jointly enumerated candidate such as
$\{do(C_P{=}\text{identity}), do(d_t{=}d')\}$; the `InterventionSet`
node-collision and composition rules cannot see it; and $R^{*}_{\text{suff}}$
cannot express a process repair in a unified type.

**A57 closes it. No world semantics change.** `Intervention(kind="process_commit")`,
built by `Intervention.commit_identity()`, with its **own structural node**
`("process_commit",)` distinct from `("process",)`, plus
`InterventionSet.commit_repair()`. Parameters are rejected, since restoring a
faithful commit takes none. The rollout priority is frozen at

$$\boxed{do(z{=}z') \;>\; do(C_P{=}\text{identity}) \;>\; Z_P\ \text{fault} \;>\; z^{\text{proposal}}}$$

so strategy replay is the downstream root intervention and the commit repair
**shadows** the fault. When both are present strategy replay wins and the commit
repair is merely shadowed — a legal composition, not MALFORMED, which is precisely
why the two carry distinct nodes.

**Canary held.** Gate_fire re-run after A57: depth histogram **unchanged** at
$D{=}0$ 1,553, $D{=}1$ 990, $D{=}2$ 230, $D{=}3$ 10, unidentifiable 0, PASS. The
10 $D{=}3$ classes are recorded in the artifact, and $D_{\text{old}}{=}3
\Rightarrow D_{\text{new}}{=}3$ holds **10/10**. This was the right regression
assertion precisely because the commit repair is evaluator-only and must not touch
the learner's query family.

**Formal Gate E (`scripts/gate_e.py`) — FULL primary feasible support,
$N = 1{,}038{,}960$, every case, no sampling.**

|$\lvert R^{*}\rvert$| cases |
|---|---|
| 0 (factual already succeeds) | 925,800 |
| 1 | 113,160 |
| 2 | 0 |
| 3 | 0 |
| $\bot$ NO-SUFFICIENT-REPAIR | **0** |

Every failing case is repaired by a **size-1** member, so the size-2/3 expansion
never fired and the finite lattice is total on this environment. No case was
`MALFORMED_FACTUAL`.

**All ties kept**, which is the whole point: $\#R^{*}$ ranges from 1 to 17, and the
mass is not at 1 —

| $\#R^{*}$ | 1 | 2 | 3 | 4 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cases | 925,800 | 13,680 | 41,040 | 11,160 | 360 | 2,160 | 11,160 | 9,000 | 16,680 | 3,480 | 4,200 | 240 |

A search that stopped at the first sufficient repair would have reported
$\#R^{*} = 1$ for 113,160 failing cases, destroying the tie structure every
downstream metric depends on ($|R^{*}| \neq \#R^{*}$).

**Kinds entering a minimal family:** strategy replay 113,160; process commit
88,320; decision 47,280; execution 23,160.

**The cross cells — A56's claim, validated at full scale:**

| cell | cases |
|---|---|
| commit sufficient **and** strategy sufficient | 88,320 |
| **strategy sufficient, commit not** | **24,840** |
| commit sufficient, strategy not | **0** |

So the two operations are empirically distinct, and the separation runs one way:
whenever the commit repair suffices, some strategy replay also suffices, but there
are **24,840** cases repaired by switching strategy and **not** by restoring a
faithful commit. Those are exactly the C4 episodes, where the proposal itself is a
poor option and the fault is not a commit fault. Conflating the two would have
mislabelled all 24,840.

(The precheck's sampled 663 scales to $663 \times 37 \approx 24{,}531$ against the
true 24,840 — an independent consistency check on the sampling.)

**A55's invariant, upgraded to trace level.** The precheck only compared final
outcomes. Gate E compares the full trajectory: for the **388,800** cases with
$Z_P^{\text{fire}} = 0$, `do(C_P = identity)` reproduces the factual trace
**step for step** — `trace_noop_ok` 388,800, `trace_changed_without_fault` **0**.
Outcome equality alone would have passed even if the repair perturbed the run.

**Verdict: Gate E PASS.** Proceeding to the semantic suite `04`, then the Oracle
ceiling, then the $N_{\text{scenes}}=32$ calibration. Any failure stops the chain.

---

## 46. A58 — the semantic gate is layered, and `04` is not weakened

**The scope problem.** `04-SEMANTIC-INVARIANTS.md` became unreachable, not
because it was wrong but because it mixes two obligations of different maturity.
`src/rfl_rebuild/` today contains only `env` and `solve`: there is **no
responsibility / update / write-space layer**. So I1, I2, I6, C6 and the write
halves of C0/C1/C2/C3/C5/C8 have nothing to assert against, and "implementing
`04` fully" would mean either a fake PASS or implementing V0.2R/V0.3R early.

**`04` remains the total hard gate.** What changes is that the artifact must
distinguish three statuses and must never use `N/A`:

$$ \boxed{\texttt{PASS} \;/\; \texttt{BLOCKED\_NOT\_IMPLEMENTED} \;/\; \texttt{FAIL}} $$

`BLOCKED_NOT_IMPLEMENTED` is deliberately loud — `N/A` is the status that gets
forgotten. A version gate consuming the artifact must state, per blocked item,
whether that version depends on it. When the write layer lands, each blocked item
becomes a real PASS/FAIL; it may not be quietly dropped.

**Two layers.**

* **S0 — Semantic Kernel Gate**, implementable today: I3, I4, I5 and the
  kernel/evaluator-truth halves of C0–C5, C7, C8.
* **S1 — Semantic Learning Gate**, implemented with the corresponding version:
  I1, I2, I6, C6, and the `p` / responsibility-output / write-receipt / update
  pieces of C0/C1/C2/C3/C5/C8.

**Correction recorded:** the case suite is **C0–C8**, not C0–C5.

**S0 result** (`scripts/semantic_gate_s0.py` → `experiments/v01r/semantic_gate.json`):

| | count |
|---|---|
| PASS | 12 |
| BLOCKED_NOT_IMPLEMENTED | 4 (I1, I2, I6, C6) |
| FAIL | 0 |

Every witness was **found by scanning 173,161 real feasible cases**, then checked.
Nothing is compared against an expectation transcribed from the prose — no
"expected value" was written down first, which is what would have made this a
self-confirming test.

What each S0 item actually asserts:

* **I3** reuses Gate E's full-support result mechanically and fixes a real
  $\#R^* > 1$ witness; it asserts that minimal cardinality and tie count are
  separable quantities, i.e. that a first-hit search would have collapsed them.
* **I4** runs three mis-reconstruction probes. Each takes a case whose fire
  vector is known ($X$-only, $D$-only, $E$-fired) and asks whether a naive
  behaviour-derived reading would attribute the fault to the *other* kind — the
  legacy `scene_from_trace` error, which read `realized != reference` as a
  decision fault. All three probes must come out False.
* **I5** compares **every** `StepResult` field plus the trace-level
  `outcome`/`control`/`base_option`/`option_in_force`, and additionally perturbs
  the truth and requires the trace to move. Without the perturbation the
  comparison would be vacuous — outcome equality alone passes even when the
  replay perturbs the run, which is exactly the weakness A57's trace-level
  invariant was introduced to remove.
* **C3** asserts $z^{\text{proposal}} \neq z^{\text{in-force}}$, that the proposal
  audit exposes the mismatch, and that `commit_identity()` has its own node.
* **C4** asserts on a witness with $Z_P^{\text{fire}} = 0$ that no singleton
  decision repair suffices while some $do(z{=}z')$ does — making explicit that
  this is a statement about repair **granularity** and not the definition of
  $Z_P$ (A56).
* **C7** asserts $|R^*| = 1$ with $\#R^* \ge 2$ on a constructed failing episode
  and **replays every tied candidate** to success.

**What S0 explicitly does not claim.** V0.1R has no update path, so the write
invariants are *vacuous* for it. That is recorded as `V0.1R_DEPENDENCY` and is
**not** evidence that I1/I2/I6 hold. V0.1R depends only on I3/I4/I5 and the
kernel halves, and the four blocked items stay blocked.

**Build order from here**, so that "finishing `04`" cannot smuggle in V0.2R:

$$\boxed{\text{S0 kernel/evaluator suite} \rightarrow \text{semantic\_gate.json harness} \rightarrow \text{V0.1R method-facing assertions}}$$

S0 and the harness are done. The method-facing assertions are next, and they are
what the Oracle ceiling and the $N_{\text{scenes}}=32$ calibration will run
against.

---

## 47. A59 — the V0.1R method contract

**Two boundary failures were visible before any code was written**, and this
amendment freezes the contract that prevents both. Full text:
`14-V01R-METHOD-CONTRACT.md`.

**V0.1R must not grow a responsibility output.** V0.1R is diagnosis only — its
output is a five-dimensional $p$ and nothing else. Credit assignment, repair and
update belong to V0.2R/V0.3R (`06-V01R.md` §6). Adding a $U$ output now would
implement V0.2R inside V0.1R and destroy the version split that exists precisely
to keep diagnosis and prescription apart.

**Arm isolation must hold by construction, not by promise.** If every arm gets
the same complete scene and is trusted not to read a field, the comparison
measures discipline instead of information. Arms therefore receive **different
types**.

Four consequences that are easy to get wrong:

* **`Prediction` splits into two typed fields.** $p_i \in [0,1]$ with
  $\sum_i p_i$ **unconstrained** is the object Brier/ECE are computed on;
  $s^{\text{raw}} \in \mathbb{R}^5$ is a *separate* diagnostic field. `06` §2
  already required normalising methods to report unnormalised scores, but the
  interface had not made them different types — and merging them makes "the
  probability" ambiguous at exactly the point calibration is measured.
* **The sequence arms receive $I^{\text{factual}}_{0:T}$, not bare
  $\text{obs}_{0:T}$.** Gate_fire counts the learner's own $z^{\text{in-force}}$
  and $m$ as legal information and A55's process diagnosis *requires*
  $z^{\text{in-force}}$; an `obs`-only arm would be strictly narrower than the
  gate credited — the same defect A56 fixed on the arm names.
* **`QueryOnly`'s blind selection is executed by the runner.** Query *addresses*
  are partly derived from the factual trajectory (an execution probe needs a
  site, a decision replay and a plant audit need a timestep), so handing the
  addresses over leaks sequence evidence through the query menu. The runner
  selects from the arm's safe family with a frozen blind policy and the method
  sees only responses. Only `SeqThenQuery` selects its own next query.
* **A50 lives in the API, not only in the gate scripts.** A method must never
  receive `MALFORMED`, `ILLEGAL_IN_THIS_WORLD` or
  `QUERY_REJECTED_BECAUSE_HIDDEN_FAULT`: unsafe queries simply **do not exist in
  the candidate set**, so a refusal is not a representable response and there is
  nothing to encode. Exposing the rejection would leak a function of hidden $M$ —
  the error A50(d) already rejected. And every query is an **independent probe**
  replayed from the same factual latent world; only the information history and
  the remaining budget persist across queries.

**What S1 asserts, and what it refuses to assert.** `04` says the semantic suite
does not test attribution accuracy, so the V0.1R method-facing assertions test
**interface and information-flow semantics only**: zero world/model mutation and
no write output (C0); the input view carries no evaluator truth and $p_X$/$p_D$
are separable coordinates (C1/C2); the process audit returns $z^{\text{proposal}}$
with no $Z_P$ verdict and $z^{\text{in-force}}$ arriving via the learner's control
state (C3); $p_E$ and $p_U$ exist as independent coordinates so "external /
unknown" is *expressible* (C5); the call is side-effect free (C8). It must **not**
demand $p_X > p_D$ or $p_E > 0$ — that is a scientific hypothesis, and a working
method mislabelled as a semantic bug. Acceptance is deliberately weak in the right
way: a trivially dumb method must be able to walk the whole interface and pass.

`Oracle` is the sole exception and must be exact: $p^{\text{Oracle}} =
Z^{\text{fire}}$.

**Implementation order, frozen:**

$$\text{Method API} \rightarrow \text{arm isolation runner} \rightarrow \text{query-session budget/legality} \rightarrow \text{V0.1R semantic S1}$$

The failure mode to avoid is writing a clever `SeqThenQuery` at this step: it
would make S1 pass for the wrong reason and pre-empt the experiment.

---

## 48. A62 — the support constructor bypassed typed isolation

**Found by development calibration, which is exactly what development is for.**
`calibration_dev.json` recorded AUPRC 0.9824 for `SequenceEvidence` **and**
`QueryOnly` — identical to four decimal places, from two arms with deliberately
different information interfaces. That coincidence was the tell.

**The defect is outside the type boundary.** `build_partition()` keys classes on
the complete $\sigma_0 = (\text{rows}, \text{feedback})$, and `calibration.py` then
passed `PublicSupport(worlds=reps)` to every arm and initialised the query session
with `members=reps`. So `SequenceEvidence` was silently conditioned on the
feedback claim and `QueryOnly` on the factual sequence, despite neither typed
input containing them. A59's types were correct; a constructor handed over the
answer anyway.

**A second, independent defect:** scenes were drawn from factual classes rather
than independently generated episodes, so the metrics were an estimate of the
wrong population — not the protocol's unit.

**Fixed:** the frozen scene DGP is written down (κ and $z^{\text{proposal}}$
uniform, tape measure unchanged with $P(\texttt{error\_flag}{=}1)=0.4$,
$Z_i^{\text{pres}} \sim \mathrm{Bernoulli}(0.2)$ on non-empty canonical domains,
fault parameters uniform within them); the arms' populations are redefined with
$H_{\text{seq}}(I) = \{\ell : \mathrm{rows}(\ell) = I\}$, **rows-only**, and
`QueryOnly` starts from the **global prior support** rather than the true class;
marginals use $P_{\text{DGP}}$ instead of the placeholder $w_\ell = 1$; and
`_freeze` no longer uses Python `hash()` as a semantic key, which would have
reintroduced the `PYTHONHASHSEED` nondeterminism this rebuild already removed
once. A comment claiming coverage-greedy scene selection that the code did not
implement is gone.

**$0.2$ is not tuning.** It is the value the existing "causes are sparse"
specification implies: $\mathbb{E}[|Z|] = 1$ and $P(|Z| \le 1) \approx 0.737$.

**dev_v1 is kept unchanged** and marked *development design diagnostic — invalid
for discriminative-range inference because the support was conditioned on the
full `(rows, feedback)` factual class*. It is **not** evidence that the benchmark
is too easy; that question is still open.

**Pre-registered before dev_v2**, so no third round of benchmark editing is
available: if dev_v2 still shows $\mathrm{SequenceEvidence} \approx 0.98$ and
$\mathrm{SeqThenQuery} \approx 1$, that is **accepted** and we go to the
confirmatory run. The frozen primary hypothesis is
$\text{SeqThenQuery} > \text{DirectFeedback} + \Delta_{\min}$, *not*
$\text{SeqThenQuery} > \text{SequenceEvidence} + \Delta_{\min}$; the correct
reading is that the factual sequence already carries most of the diagnosis
information and queries resolve residual ambiguity, with a ceiling-limited
incremental contrast. Natural separation is nicer but is **not** a PASS
condition. Only **one** fresh dev_v2 is allowed.

Full text: `15-SCENE-DGP.md`.

---

## 50. A63 — NOT_EVALUABLE per-cause metrics, and what dev_v2 measured

**The problem.** dev_v2 FAILED its coverage check because cause `U` had **zero
positive scenes** in the 32-scene batch, which made every macro value `nan`. A54's
census predicted exactly this: of 692,640 cause-world pairs in which $U$ is
present, $U$ *fires* in only 34,320 (~5%), so with $\mathrm{Bernoulli}(0.2)$
presence $P(U \text{ present} \wedge \text{fired}) \approx 1\%$ and the expected
U-positive count at $N = 32$ is ~0.3. Observing zero is the predicted outcome,
not a defect.

**The convention, frozen here.** A per-cause metric is **NOT_EVALUABLE** when the
batch contains no scene of that class. It is never `nan` and never silently
averaged as zero. The macro is taken over the **evaluable** causes and the
artifact names both sets. `Metrics.__post_init__` refuses a macro whose
`macro_over` says "all causes" while `not_evaluable_causes` is non-empty, so the
convention cannot be bypassed by constructing the object differently.

$$\boxed{\text{a per-cause metric undefined on the batch is NOT\_EVALUABLE, and the macro names its set}}$$

**This does not turn a coverage gap into a pass.** dev_v2's original FAIL stays on
record in `calibration_dev_v2.json`; the re-report is a separate artifact that
drew **no new scenes**, because only the arithmetic convention changed and
spending development scenes to re-derive reporting would have been waste.

**What dev_v2 then measured** — the point of the whole A62 exercise:

| arm | dev_v1 (leaky) | dev_v2 (corrected) |
|---|---|---|
| `DirectFeedback` | 0.3999 | 0.5322 |
| `SequenceEvidence` | 0.9824 | **0.6369** |
| `QueryOnly` | 0.9824 | **0.6390** |
| `SeqThenQuery` | 1.0000 | 1.0000 |

Evaluable causes $P, D, X, E$; $U$ NOT_EVALUABLE.

$$\boxed{\text{the dev\_v1 leak was worth about } 0.35 \text{ AUPRC to } \texttt{SequenceEvidence}}$$

Two arms with deliberately different information interfaces had scored
*identically* to four decimal places because the support constructor handed both
the full $(\text{rows}, \text{feedback})$ class. After A62 they separate, and the
gap is the measured cost of that leak. `DirectFeedback` also moved because the
scenes differ, so only the `SequenceEvidence`/`QueryOnly` collapse is attributable
to the leak itself.

**One concern remains, pre-registered and deliberately not acted on.**
`SeqThenQuery` is still exactly 1.0000. `15-SCENE-DGP.md` §4 already fixes what to
do: if dev_v2 still shows saturation, **accept it and proceed to the confirmatory
run without making the benchmark harder.** The frozen primary hypothesis is
$\text{SeqThenQuery} > \text{DirectFeedback} + \Delta_{\min}$, not a comparison
against `SequenceEvidence`, so a ceiling-limited incremental query contrast is a
property of the result rather than a defect to tune away.

**Warning recorded before the confirmatory run:** at $N = 400$ the expected
U-positive count is ~4. `AUPRC_U` will be defined but thin, and its contribution
to the macro will be unstable. That is a property of the frozen DGP.

---

## 51. A64 — the confirmatory run: PASS, and U is unevaluable at every feasible N

**Run.** Namespace `v01r_conf_v1`, $N = 400$ drawn as one deterministic sequence
from the frozen DGP, four non-overlapping blocks of 100, 165 distinct rows
blocks, 15,903,240 memoised rollouts. All 400 scenes were generated and all four
arms ran on every one.

**Primary contrast, pre-registered as `SeqThenQuery` vs `DirectFeedback` on macro
AUPRC against $\Delta_{\min} = 0.05$:**

| | alt | base | delta | position |
|---|---|---|---|---|
| cumulative | 1.0000 | 0.3899 | **0.6101** | **ABOVE** |
| block 1 (n=100) | | | 0.6313 | ABOVE |
| block 2 | | | 0.5159 | ABOVE |
| block 3 | | | 0.5918 | ABOVE |
| block 4 | | | 0.6230 | ABOVE |

**The delta is not block-driven, and separately, the per-scene diagnostic is
broad.** These are two different statements on two different quantities, and an
earlier draft merged them into one overclaim:

* **Primary, batch-level macro AUPRC:** the contrast clears $\Delta_{\min}$ in
  **each of the four 100-scene blocks independently** (0.6313, 0.5159, 0.5918,
  0.6230), not merely in aggregate. So it is not carried by one block.
* **Per-scene diagnostic, Brier:** $178$ scenes improve, $0$ worsen, tie fraction
  $0.555$, two-sided sign test $p \approx 5.2\times10^{-54}$, and the top-5 scenes
  supply only $5.2\%$ of the total Brier improvement.

The sign test is **not** a significance test of the AUPRC difference. AUPRC is
undefined at $n=1$, so the per-scene distribution can only be computed on a
per-scene-defined score; Brier is that score and is labelled a shape diagnostic
in `_contrast`. Writing it as an AUPRC sign test would have been a false claim
about what was tested.

Verdict: **PASS**.

**U is unevaluable at every PRE-REGISTERED $N$, and the exact reason is now
known.** Coverage at $N=400$ is $+[75, 63, 59, 62, \mathbf{0}]$. Across all three
planned sizes the sampled scene count is $5 + 32 + 400 = 437$, with **zero**
U-positives in every one.

Two things must not be said about that, and an earlier draft said both:

* **Zero observations do not bound the rate by $1/N$.** The correct one-sided 95%
  bound from $0/400$ is $1 - 0.05^{1/400} \approx 0.75\%$, and from $0/437$
  about $0.68\%$ — not $0.25\%$.
* **The zeros do not prove A63's estimate wrong by statistics.** They are simply
  the likely outcome, as the exact computation below shows.

$$\boxed{U \text{ produced no positives at any pre-registered } N \in \{5, 32, 400\}}$$

That is the defensible statement. "Unevaluable at any feasible $N$" is not: as
long as $P(Z_U^{\text{fire}} = 1) > 0$, a large enough $N$ would eventually draw
one.

**Exact DGP marginals, from the cache, costing no rollouts and no scenes.**
The dense support already stores every feasible world's DGP weight and
`fire_code`, so no sample-based inference is needed at all:

$$P(Z_i^{\text{fire}} = 1) = \sum_{\ell \in \mathcal F} w_\ell \, \mathbf 1[\text{bit } i]$$

| cause | $P(Z_i^{\text{fire}} = 1)$ |
|---|---|
| P | 0.193762 |
| D | 0.133613 |
| X | 0.156763 |
| E | 0.160047 |
| **U** | **0.002041** |

So U fires at roughly **1/79 of the average of the other four causes**, i.e. about
**65–95 times rarer** depending on which cause it is compared with
($P/U = 94.9$, $D/U = 65.5$, $X/U = 76.8$, $E/U = 78.4$ over the exact values
above). An earlier draft said "about ten times rarer", which contradicted its own
table by an order of magnitude — the two "orders of magnitude" must be kept
separate:

* **occurrence rate:** U is **65–95×** rarer than the other four causes;
* **sample size for ~10 U-positives:** $N \approx 10 / 0.002041 \approx 4900$,
  about **12× larger** than $N = 400$.

At $N = 400$ the expected U-positive count is $0.8165$ with

$$P(\text{observe zero at } N{=}400) = 0.4416, \qquad
  P(\text{observe zero at all three sizes}) = 0.4095.$$

The observed zeros are therefore **unremarkable**: they were the single most
likely outcome. A63's "~1%" estimate was indeed wrong, but in a way the exact
computation settles outright rather than a way the samples could convict — and
the sample-derived bound ($0.75\%$) still contains the true value ($0.204\%$), so
nothing about the observations was inconsistent. The practical consequence is
structural, not statistical: U fires about twice per thousand scenes, so a
benchmark that wants roughly ten U-positives needs $N \approx 4900$ — about an
order of magnitude beyond the largest $N$ planned here.

**V0.1R frozen claim.**

**What this establishes, and what it does not.** The frozen primary hypothesis is
met, on fresh confirmatory data:

$$\boxed{\text{under the frozen DGP, information boundary and } B_Q = 4,
  \text{ sequence evidence + targeted queries diagnose } Z^{\text{fire}}
  \text{ far better than believing feedback directly}}$$

with $\Delta\text{AUPRC} = 0.6101 \gg \Delta_{\min} = 0.05$, reproduced in
direction and threshold by all four blocks. This is the first genuine
confirmatory empirical result in the rebuild.

It supports **evidence and feedback interpretation $\rightarrow$ fired-mechanism
attribution**, i.e. V0.1R, and nothing further. It does **not** show that better
attribution yields better responsibility assignment, better selective update, or
a better learned policy, so it cannot be written up as "reinforcement feedback
learning works". The correct claim is that **the first link of the framework —
feedback interpretation and fault attribution — passed a pre-registered
confirmatory experiment.**

**The benchmark has largely finished its job.** With
$\text{AUPRC}(\texttt{SeqThenQuery}) = 1.0000$ exactly, this benchmark **cannot**
compare a better attribution algorithm against the current `SeqThenQuery`: there
is no headroom. Its future role is a **V0.1R regression and semantic benchmark**,
not an attribution leaderboard. The residual discriminative range is

$$0.3899 \;\rightarrow\; 0.6892 \;\rightarrow\; 0.7169,$$

the three non-trivial arms, not the saturated one.

**A gate defect found and fixed here.** The confirmatory artifact reported FAIL
while `failed_gating_checks` was empty, because
`coverage_every_cause_has_both_classes_INFORMATIONAL` — explicitly marked
INFORMATIONAL by A63 — was still being ANDed into the verdict. The rule was
wrong, not the data, so the verdict was **recomputed from the stored artifact**
without redrawing a single scene or repeating the 15.9M rollouts. The script
(`scripts/recompute_verdict.py`) records the original FAIL, the reason, and that
nothing was redrawn.

**Limitation, stated plainly.**
$\text{macro AUPRC}(\texttt{SeqThenQuery}) = 1.0000$ exactly, i.e. that arm sits
at the ceiling of the endpoint, and its AUROC, exact-set, Hamming, Brier and ECE
are saturated too. The contrast against `DirectFeedback` is correspondingly
large, but a saturated arm means **no further improvement by
`SeqThenQuery`-class methods is measurable on this benchmark**. Per
`15-SCENE-DGP.md` §4 this is accepted rather than tuned away, and the
consequence is drawn above: the benchmark becomes a regression artefact rather
than a leaderboard.

**Accounting note.** One verdict was recomputed rather than re-run, and the
distinction matters for how this result may be cited. The confirmatory artifact
originally reported FAIL while `failed_gating_checks` was empty, because
`coverage_every_cause_has_both_classes_INFORMATIONAL` — explicitly made
informational by A63 — was still being ANDed into the verdict. The rule was
wrong, not the data. The verdict was recomputed **from the stored artifact**,
without redrawing a scene or repeating the 15.9M rollouts, and
`scripts/recompute_verdict.py` records the original FAIL, the reason, and that
nothing was redrawn. No prediction, no scene and no metric was altered.

**Also corrected in this amendment after review**, because the first draft's
wording outran its data: the $0/400$ figure is $0/437$ counting all three planned
sizes; the claim that the true U rate is below $0.25\%$ is withdrawn (the correct
zero-observation bound is $\approx 0.75\%$ from $0/400$); the Brier sign test is
not an AUPRC significance test; "unevaluable at any feasible $N$" is narrowed to
the three pre-registered sizes; and "about ten times rarer" is **withdrawn as an
arithmetic error** and replaced by the exact ratios ($P/U = 94.9$, $D/U = 65.5$,
$X/U = 76.8$, $E/U = 78.4$, i.e. 65–95×, about $1/79$ of the other four's
average).

**Frozen claim (V0.1R closed).**

> Under the frozen DGP, information boundary and $B_Q = 4$, sequence evidence plus
> targeted queries diagnose $Z^{\text{fire}}$ far better than believing feedback
> directly: $\Delta\text{AUPRC} = 0.6101$ in the pre-registered $N = 400$
> confirmatory experiment, exceeding $\Delta_{\min} = 0.05$, with all four
> independent 100-scene blocks clearing the threshold on their own.

$$\boxed{\text{V0.1R establishes feedback interpretation} \rightarrow \text{attribution, and nothing further}}$$

It does **not** establish attribution $\rightarrow$ responsibility $\rightarrow$
selective update $\rightarrow$ better policy. Those are V0.2R onward, and no
result here may be cited for them.

---

## 52. A65 — V0.2R object and type semantics

**V0.1R is CLOSED at `8f35766`.** After that, no further change to benchmark, DGP,
method, endpoint or experiment design; errata only.

**Why V0.2R cannot start from `07` as written.** `07` presents V0.2R as "causal
truth $\to$ credit representation" and takes

$$R^\ast = \text{minimal sufficient intervention set}$$

as *the* repair truth, then compares module / trajectory / causal / repair
representations against it. A55–A64 make that too coarse. The specific
counterexample is A57's:

$$do(C_P = \text{identity}) \quad\text{vs}\quad do(z = z')$$

The first repairs the process-commit **mechanism**; the second may merely route
around it by running a different strategy. A rescue that succeeds therefore does
not imply that `Strategy` should carry the learning responsibility, and the
implicit identity

$$\text{minimal sufficient rescue} \Rightarrow \text{credit truth}$$

is **withdrawn**.

**Five objects, not two:**

$$\boxed{C^{\text{fire}} \neq R^{\text{mech}} \neq R^{\text{rescue}} \neq \Gamma^{\text{credit}} \neq W^{\text{update}}}$$

with $C^{\text{fire}}$ the closed V0.1R object, $R^{\text{mech}}$ the intervention
that restores a faulty mechanism, $R^{\text{rescue}}$ any intervention that makes
the episode succeed, $\Gamma^{\text{credit}}$ V0.2R's actual subject, and
$W^{\text{update}}$ V0.3R's. Where $R^{\text{mech}}$ and $R^{\text{rescue}}$ differ,
that difference *is* the structure V0.2R exists to study.

**Input contract**, stated precisely rather than as "receives cause truth":

$$X_{0.2} = (I^{\text{factual}}_{0:T}, Z^{\text{fire}}_{\text{truth}})$$

No latent fault parameters, no repair truth of either kind, no responsibility
truth, no write target. The asymmetry with V0.1R is deliberate: V0.1R was handed
no truth and had to infer it; V0.2R is handed the answer to V0.1R's question and
tested on the next one.

**Credit-unit ontology, re-frozen.** `07`'s `Plan / Decision_t / Execution_t /
Process` no longer matches the SCM: `Strategy` and `ProcessCommit` were one label
over two mechanisms, and one `Execution` swallowed the controller/plant boundary
A53 exists to expose.

$$\Gamma = \{\text{Strategy}, \text{ProcessCommit}, \text{Decision}_t, \text{ControllerSite}, \text{ExternalPlant}, \text{Unknown/NoWrite}\}$$

`Unknown/NoWrite` must remain **expressible**: a method forced to name a
responsible unit is pushed toward false credit by construction.

**Two repair truths, and a frozen projection.** Both $\mathcal R^{\text{mech},\ast}$
and $\mathcal R^{\text{rescue},\ast}$ are minimised and **ties retained**
($|R^\ast| \neq \#R^\ast$). Responsibility truth is then

$$\Gamma^\ast(\ell) = \{\pi_{\text{credit}}(r) : r \in \mathcal R^{\text{mech},\ast}(\ell)\}$$

projected **from $R^{\text{mech}}$, never from $R^{\text{rescue}}$** — otherwise
rescuing an outcome by switching strategy mints `Strategy` credit for a process
fault. $\pi_{\text{credit}}$ is total and declared, including on the empty repair,
which maps to `Unknown/NoWrite`.

**Endpoints revised.** `InterventionSufficiency` is **not** adopted as primary: it
needs a `credit unit → canonical intervention` conversion that is already most of
V0.3R's repair primitive, so a representation comparison would be measured partly
through a repair rule. Primary is instead set-valued —
$\text{CreditCoverage}$ and $\text{FalseCreditRate}$ — asking whether the
representation expresses *the right place to change at all*.
`OutcomeRepairSufficiency` demotes to secondary/evaluator diagnostic.

**Old Gate E does not carry over.** Its PASS ($|R^\ast| = 0$: 925,800;
$|R^\ast| = 1$: 113,160; none needing 2+) was under the old ontology and never
separated the two repair truths, so it is a **regression reference**, not a
prerequisite theorem. A **new exhaustive census** runs on the existing
1,038,960-world `DenseSupport` reporting **DGP-weighted mass alongside world
counts** — V0.1R already showed those can differ by an order of magnitude.

Full text: `16-V02R-SEMANTICS.md`. Order:
A65 → A66 enumerator → A67 projection + set-valued truth → new Gate E census →
rewrite `07` endpoints → method contract → smoke/dev/confirmatory.

**The next step is not a method.** It is answering, in the ontology, whether
"where to change" means repairing the fault or compensating for the outcome.

---

## 53. A66 — the mechanism-repair and rescue enumerators

**Two truths, two enumerators.** $R^{\text{mech}}$ is structural — it needs no
counterfactual simulation. $R^{\text{rescue}}$ needs it and is enumerated the way
Gate E enumerated $R^\ast_{\text{suff}}$.

**P0 fixed before any full run: the $Z_D$ repair address was wrong.** The
mechanism repair is $do(d_t = \pi^\ast(s_t, z_t, m_t))$, and all three arguments
are lookup keys of $\pi_D^\ast$. The first version substituted START, the proposal
option and $m = 0$, which gives the wrong nominal action for every override not at
START. The address now comes from the factual pre-action state at the override's
timestep, walked exactly as `walk_transition` does. $R^{\text{mech}}$ remains
structural; only its address was wrong.

**P0 fixed: a singleton miss is not bottom.** The first version recorded
`rescue_BOT` whenever no single intervention sufficed — quietly leaning on Gate E's
old singleton result, which A65 had just demoted to a regression reference. The
search now enumerates pairs then triples before concluding, reporting
`rescue_UNRESOLVED_GT3` only then. On the full support that count is **0**, so the
singleton claim is now *measured* rather than inherited.

**P0 fixed: the basis is FIRE, not presence.** A67's rules are stated on fired
mechanisms, A65's input contract is $(I^{\text{factual}}, Z^{\text{fire}}_{\text{truth}})$,
and V0.1R's closed object is $Z^{\text{fire}}$ — but the census gated
$\Gamma^\ast$ on fault *presence* for P/D/X/E. Writing the A67 structural test
measured the size of that inconsistency at **1,541,400 $(world, cause)$ pairs**
where presence differs from fire. Gating on presence lets a dormant mechanism mint
credit, which is the same class of error as crediting a rescue.

**Definition ambiguity reported, not resolved.** "Restore the mechanism" can mean
undo *every* firing of that cause or undo at least one; both readings are computed.
`a67_structural.json` settles it on a **structural** basis rather than as slice
luck: at most one mechanism primitive per cause per world holds over the whole
support, because each cause carries at most one fault object, so the two readings
coincide. The counter stays in the census so the ambiguity reopens if a future
schema admits multi-site same-cause faults.

## 54. A67 — the credit projection, frozen

**$\Gamma^\ast$ locates responsibility for the faulty MECHANISM, never for the
outcome**, so $R^{\text{rescue}}$ can never change the primary credit truth:

$$\boxed{Z_E^{\text{fire}} = 1 \Rightarrow \texttt{ExternalPlant} \in \Gamma^\ast \quad\text{independent of } R^{\text{rescue}}}$$

$$\boxed{Z_U^{\text{fire}} = 1 \Rightarrow \texttt{Unknown/NoWrite} \in \Gamma^\ast \quad\text{independent of } R^{\text{rescue}}}$$

`ExternalPlant` is **not** `Unknown/NoWrite`: it is a definite credit *location*
with agent-writability zero. $\boxed{\text{credit location} \neq \text{agent writeability}}$
and `ExternalPlant` stays in the metric denominator, because it is still the
correct answer to a *location* task; acting on `agent_writeable = false` is
V0.3R's business. `U` is not erased when an agent fault co-fires: the truth is
set-valued, e.g. $\{\texttt{ProcessCommit}, \texttt{Unknown/NoWrite}\}$. No fired
mechanism gives $\{\texttt{Unknown/NoWrite}\}$, read as **NoWrite**.

**$R^{\text{mech}}$ is descriptors, not only executable interventions:**

$$R^{\text{mech}} = R^{\text{mech}}_{\text{agent}} \cup R^{\text{mech}}_{\text{nonagent}}$$

with the frozen mapping $do(C_P{=}\text{identity}) \mapsto \texttt{ProcessCommit}$,
$do(d_t = \pi^\ast(s_t,z_t,m_t)) \mapsto \texttt{Decision}_t$,
$do(C_X(\text{site}){=}a^{cmd}) \mapsto \texttt{ControllerSite}$,
$\rho_E \mapsto \texttt{ExternalPlant}$, $\rho_U \mapsto \texttt{Unknown/NoWrite}$.
Without the non-agent branch, `ExternalPlant` could never enter $\Gamma^\ast$ and
A65's ontology would fail on its own terms; it also avoids fabricating an agent-side
$do(E = \text{identity})$ that nobody can execute.

**Endpoints.** `InterventionSufficiency` is **not** primary: it requires a
`credit unit → canonical intervention` conversion that is already most of V0.3R's
repair primitive. Primary is

$$\text{Coverage} = \frac{|\hat\Gamma \cap \Gamma^\ast|}{|\Gamma^\ast|},
\qquad
\text{FCR} = \frac{|\hat\Gamma \setminus \Gamma^\ast|}{\max(1, |\hat\Gamma|)}$$

so predicting $\{\texttt{Strategy}\}$ when the truth is $\{\texttt{ExternalPlant}\}$
scores FCR = 1 **even though the strategy rescue succeeded**, and
$\{\texttt{ExternalPlant}, \texttt{Strategy}\}$ scores coverage 1 with FCR = 1/2.
That is what resists "report every possible rescue".
`OutcomeRepairSufficiency` demotes to secondary.

**Structural tests, all 1,038,960 worlds, no rollouts:** `pi_credit_total`,
`agent_writeable_complete`, `strategy_never_credit_truth` (**`Strategy` in
$\Gamma^\ast$ zero times**), `gamma_star_never_empty`, `external_plant_rule_holds`,
`unknown_nowrite_rule_holds`, `one_primitive_per_cause_per_world` — **7/7 PASS**,
21 distinct $\Gamma^\ast$ sets.

## 55. A68 — the full mechanism-repair / rescue census

**Setup.** All $1{,}038{,}960$ worlds, DGP mass $1.0$, fire basis (A66 P0),
$\pi_{\text{credit}}$ frozen (A67), singleton→pairs→triples rescue search (A66
P0-2). No smoke/dev/confirmatory scene touched.

$$|R^{\text{mech}}|:\quad
\begin{array}{c|rrrrr}
 & 0 & 1 & 2 & 3 & 4\\\hline
\text{worlds} & 17{,}280 & 419{,}400 & 472{,}200 & 127{,}920 & 2{,}160\\
\text{DGP mass} & \mathbf{0.438594} & 0.480699 & 0.076610 & 0.004081 & 0.000016
\end{array}$$

$$\mathcal R^{\text{rescue},\ast}:\quad |R^\ast| = 0:\ 925{,}800\ (0.93614),
\qquad |R^\ast| = 1:\ 113{,}160\ (0.06386), \qquad \texttt{UNRESOLVED\_GT3}:\ \mathbf{0}$$

**The count and the mass invert, and that is the headline.** $|R^{\text{mech}}| = 0$
is the *rarest* count (17,280 worlds) yet carries the **largest** mass (43.9%):
"no mechanism repair needed" means every cause stayed dormant, which under
$\mathrm{Bernoulli}(0.2)$ is the high-probability regime. Conversely
$|R^{\text{mech}}| = 2$ is the most *common* count (472,200 worlds) at only 7.7%
mass. A census reporting only world counts would have described the benchmark
backwards. This is the concrete payoff of A65's requirement to report
DGP-weighted mass alongside counts.

**Singleton sufficiency is now measured, not inherited.** `UNRESOLVED_GT3 = 0`
over the full support. A66's P0-2 refused to conclude this from Gate E's old
result because A65 demoted Gate E to a regression reference; the claim is now
earned by the full enumeration, and the `rescue_size` histogram is
$0:925{,}800$, $1:113{,}160$, with no larger size needed.

**The $\pi_{\text{credit}}$ rules hold at full scale:**

| check | result |
|---|---|
| `mech_multi_primitive_per_cause` | **0** — the A66 (a)/(b) ambiguity is schema-guaranteed vacuous, not slice luck |
| `ambiguity_live` | False |
| `#R^{\text{mech}}` ties | $\{0: 17{,}280,\ 1: 1{,}021{,}680\}$ — no ties anywhere |

**The discrimination witness scales.** `PLANT_FAULT_and_strategy_rescues_truth_still_ExternalPlant`
is **33,960** worlds (99 on the 3,000-world slice, so it scaled as expected), and
`NO_mech_but_strategy_rescues` is 1,080. These are the worlds where a strategy
replay rescues the outcome while the frozen truth remains `ExternalPlant` (or
where no mechanism was repaired at all but a strategy replay still rescued):
exactly the cases where crediting `Strategy` must cost FalseCreditRate.

`mech_present_and_already_succeeded` = 909,600 and
`mech_present_and_strategy_also_rescues` = 112,080.

**Reporting gap, recorded rather than papered over.** The per-kind masses
(`mech_kind_*`) were never accumulated — the counter was incremented and the mass
was not — so the artifact shows `mass=0.00000` beside `count=326,520` for
`external_plant`. The quantity is not lost: the exact firing marginals already
exist in `exact_fire_marginals.json` ($P = 0.193762$, $D = 0.133613$,
$X = 0.156763$, $E = 0.160047$, $U = 0.002041$), so nothing needs re-running. It
is recorded because a reader comparing the two artifacts would otherwise see a
contradiction.

**What this does not do.** It does not license a V0.2R method. `07`'s endpoints are
not yet rewritten (see A67, section 7 of `16-V02R-SEMANTICS.md`); the method
contract does not exist and no arm has been run. The census is truth-side only.

---

## 56. A70 — V0.2R is an exact granularity census, not an ontology competition

**The degeneracy, restated so it cannot be read as a bug.** Under

$$X_{0.2} = (I^{\text{factual}}, Z^{\text{fire}}_{\text{truth}})$$

A67's projection is a deterministic function of the input, so "for each fired cause
emit $\pi_{\text{credit}}(\text{descriptor}_i)$" computes $\Gamma^\ast$ exactly and
a $R_{\text{causal}}$ defined that way is **identical to the ceiling**. That is a
logical consequence of the input contract, not an implementation defect.

**Route (b) rejected**: removing $Z^{\text{fire}}$ from $X_{0.2}$ re-imports
V0.1R's attribution error into V0.2R and destroys the version layering that
V0.2R's "isolate the error" design exists to create.

**Route (c) rejected, and `17` §9.3's reasoning for it was WRONG.** It claimed a
fallible causal rule would make "is the six-unit ontology correct?" testable. It
would not: the scoring truth is $\Gamma^\ast =
\pi_{\text{credit}}(\mathcal R^{\text{mech},\ast})$, so the *correct answer is
already defined by the current ontology*. A purpose-built wrong-but-fine rule
judged against $\Gamma^\ast$ can only show *this rule does not match the current
ontology*, never that the current ontology is closer to true learning
responsibility than another. It would replace

$$R_{\text{causal}} = \text{ceiling} \quad\text{with}\quad
\text{fallible causal inference} < \text{ceiling},$$

buying spread in the numbers while quietly changing the question from *is this
representation right* to *can this decoder rebuild the representation we
predefined*.

$$\boxed{\text{V0.2R cannot validate the }\Gamma\text{ ontology; it measures how much information each granularity loses under a FIXED }\Gamma}$$

**Redesign.** $R_{\text{causal}}$ stops being a competitor and becomes the **Fine /
Identity Reference** $E_\Gamma(\ell) = \Gamma^\ast(\ell)$, with
$\text{Coverage} = 1$ and $\text{FCR} = 0$ **by construction** — its win is not an
empirical finding and must never be reported as one. $R_{\text{module}}$ and
$R_{\text{trajectory}}$ are the two genuine coarse encodings, and what is studied
is the **over-credit introduced by compression**. `07`'s "if H/L wins it is
adopted, if it loses it is removed" is **withdrawn**: against an identity reference
there is nothing for H/L to win.

**Primary is an EXACT census, not a staged experiment:**

$$\mathbb{E}_{\text{DGP}}[\text{Coverage}],\quad
\mathbb{E}_{\text{DGP}}[\text{FCR}],\quad
\mathbb{E}_{\text{DGP}}[\#\hat\Gamma]$$

over all $1{,}038{,}960$ DGP-feasible worlds, with **DGP-weighted mass and
world-count averages side by side**. All three rules are deterministic and the
population is enumerable, so

$$\boxed{\text{smoke } 5 \to \text{dev } 32 \to \text{confirmatory } 400 \text{ is removed from V0.2R primary}}$$

Drawing 400 scenes to approximate an exactly computable quantity has no
statistical content. `OutcomeRepairSufficiency` and the blunt probe may remain as
sampled **secondary** experiments, but they cannot decide between representations
nor establish ontology correctness.

**May claim** (if the census shows the Fine reference lossless and the coarse ones
degrading): under the A65/A67 frozen ontology, coarse representations produce a
precisely quantifiable **over-credit on responsibility** while the fine $\Gamma$
representation is lossless. **May not claim** experimental validation of the
six-unit ontology: that needs an **external criterion not defined by
$\Gamma^\ast$**, which can only come from downstream consequences
$\text{representation} \to \text{repair/update} \to \text{collateral / utility / transfer}$.

**Consequence for V0.3R:** it must no longer say "fix the V0.2R winner" but

$$\boxed{\text{V0.3R conditions on the A65/A67 working ontology } \Gamma}$$

---

## 57. A71 — indexed responsibility truth, and cause identification ≠ site identification

**The P0.** A67/A70 built the truth as generic **type names** — `"Decision_t"`,
`"ControllerSite"` — while `credit.py` expands predictions into concrete
episode-local addresses (`Decision_3`, `ControllerSite_x_y_t_cmd`), and
`eta_causal` even rejects units outside `shape.gamma()`. Intersecting a generic
truth against concrete predictions yields the **empty set**, so the A70 census
produced systematic false negatives on every D/X component. The Fine reference hid
it by comparing the truth against itself, and `distinct_gamma_star = 21` was the
tell: a genuinely indexed truth cannot have only five-label-combination
granularity.

$$\boxed{\text{A70's census numbers are INVALID and are not inherited}}$$

**The consequence is larger than the bug.** Five fire bits say *which kind* fired,
not *which timestep or site*, so

$$Z^{\text{fire}}_{\text{truth}} \;\not\Rightarrow\; \Gamma^\ast$$

unless latent $M$ is handed over, which A65/A69 forbid. That **falsifies A70's
premise** that "for each fired cause emit $\pi_{\text{credit}}(\text{descriptor})$"
is the ceiling. A70's other conclusion stands (V0.2R cannot validate the ontology,
the scoring ontology being self-defined), but "V0.2R is only a granularity study"
does **not** stand.

**Built:** truth from $R^{\text{mech}}$ **descriptors**, so D/X carry addresses;
$\Gamma^\ast(\ell) \subseteq \Gamma(I_\ell)$ checked for all $\ell$; no generic
unit remains in any truth; and $\Gamma^-/\Gamma^+$ per information class.

$$\Gamma^-(x) = \bigcap_{\ell \in H(x)} \Gamma^\ast(\ell), \qquad
\Gamma^+(x) = \bigcup_{\ell \in H(x)} \Gamma^\ast(\ell)$$

**Measured**, full support, $1{,}038{,}960$ worlds:

| quantity | value |
|---|---|
| locator information classes $X^{\text{loc}} = (\text{rows}, Z^{\text{fire}}_{\text{truth}})$, keyed $(block, fire\_code)$ | 893 |
| classes with mixed $\Gamma^\ast$ | **14** = 1.57% of **classes** |
| **DGP mass in mixed classes** | **0.1881% of mass** |
| ambiguity-set size histogram | $\{2: 14\}$ |
| $\lvert\Gamma^+\rvert - \lvert\Gamma^-\rvert$ | mean 0.031, max 2 |
| domain-closure violations / generic leaks | 0 / 0 |

$\boxed{\text{These are 14 of 893 \textbf{locator} information classes } X^{\text{loc}}\text{, per A73 (12 §60).}}$
The full learner-visible *observational* partition, $X^{\text{obs}} = (\text{rows},
\text{feedback}, Z^{\text{fire}})$, is **4,513** classes — the feedback channel
splits all 893. Neither 14/893 nor 893 itself is a statement about
$X^{\text{obs}}$. The **class** figure must also not be read as a scene
probability.

$$\boxed{\text{Cause identification does not imply site identification}}$$

The ambiguity is thin on **both** counts — 1.57% of classes but 0.19% of DGP mass,
each mixed class with exactly two alternatives differing by one unit. The class
figure must not be read as a scene probability.

**Verified mechanism, not an artefact.** Worlds 4702 and 4704 share block 38 and
fire `01101` with identical rows, but world 4702 has the controller fault at
$(0,2,t{=}0)$ and the plant fault at $t{=}4$, while 4704 has them **swapped**. A
controller fault at one timestep combined with a plant fault at another produces
the same observation as the exchange, while the `ControllerSite` address differs.

This is an **identifiability negative result that holds against a perfect
$Z^{\text{fire}}_{\text{truth}}$**, not a method's poor performance — markedly
stronger than a purpose-built fallible decoder. Claim condition: credit
localisation **under a known SCM**, not a general learner.

**Two vacuous tests found and withdrawn here.** The first check was
`((zc >> i) & 1) > 1`, unsatisfiable because a bit is 0 or 1; its replacement
assigned `cnt = 1` and tested `cnt > 1`, unsatisfiable for a constant. **Both
reported PASS and neither could fail.** The proposition is now a *schema theorem*:
`LatentCase` stores P/D/X/E/U as single-valued fields, so one descriptor per cause
is *by construction*. If the schema ever admits multi-fault lists, A66's
(a)-vs-(b) ambiguity reopens and a real check must replace it.

## 58. A72 — set identification, and the one capability the locator is granted

**A new grant, recorded rather than assumed.** A69 allowed only the
environment/action grammar and a read-only $\pi_D^\ast$, and forbade DenseSupport,
world ids, DGP weights, $M$, both repair truths, $\Gamma^\ast$ and any
`outcome_after` oracle. The locator additionally needs forward simulation, so:

> `CausalSetLocator` may use the frozen public SCM and its structural
> fault-support grammar to forward-simulate **hypothetical** latent worlds and
> retain those whose learner-visible factual evidence and fired-cause vector equal
> $X_{0.2}$. This is **factual-consistency inversion**, not an intervention query.
> It may not access the factual world's latent assignment, DenseSupport identities
> or weights, repair/rescue truth, $\Gamma^\ast$, or any evaluator counterfactual
> oracle.

$$\boxed{\text{simulate a hypothetical factual world} \;\neq\; \text{intervene on the true world}}$$

The left side is model inversion; the right side is the counterfactual query
already forbidden. $B_Q = 0$ is unchanged.

$$\mathcal C_{\text{SCM}}(X) = \{\tilde\ell \in \mathcal L_{\text{public}} :
\operatorname{Obs}_{\text{learner}}(\operatorname{Rollout}(\tilde\ell)) = I^{\text{factual}},\;
Z^{\text{fire}}(\tilde\ell) = Z^{\text{fire}}_{\text{truth}}\}$$

with $\mathcal L_{\text{public}}$ generated **on the spot** from the public SCM
schema and finite fault grammar — **not** DenseSupport.

$$\boxed{\hat\Gamma_{\text{CSL}}(X) = \Gamma^+(X)}$$

with $\Gamma^-$ reported alongside as the *certain* responsibility diagnostic. A
mixed class therefore does not guess a site; it reports both addresses as
compatible. That is exactly why the locator is **not** the oracle: `OracleCredit`
receives the true $\Gamma^\ast$, `CausalSetLocator` reaches only the envelope $X$
supports.

**The whitelist is an interface, not a promise.** `PublicSCMView` exposes the
public fault grammar, forward factual rollout, read-only $\pi_D^\ast$ and the
descriptor→credit mapping; it does **not** expose `Intervention` / repair / rescue,
`DenseSupport`, DGP probability, or a truth-world handle. Allowed additionally:
public kernel transition and event order, public admissible-parameter domains and
structural feasibility rules, and enumerating *hypothetical* $Z^{\text{pres}}, M$
with their own internal $u$, $a^{realized}$, $Z^{\text{fire}}$. Forbidden:
comparing a candidate against anything beyond the learner-visible fields inside
$X_{0.2}$ and the given $Z^{\text{fire}}$ — in particular not the real world's
hidden $u$, plant input or proposal provenance.

$$\boxed{\hat\Gamma_{\text{CSL}}(X) = \Gamma^+_{\text{eval}}(X) \quad \forall X \in \{1,\dots,893\}}$$

The two sides must be **independently sourced**: $\Gamma^+_{\text{eval}}$ may be
enumerated from DenseSupport plus the indexed truth (it is the evaluator
reference); $\hat\Gamma_{\text{CSL}}$ may only be re-derived from $X$ through
`PublicSCMView`. Only then is it **exact SCM set inversion** rather than a support
lookup. A mutation merging the controller/plant mechanism boundary must be killed
by the X/E swap classes A71 found.

## 59. A69 — the V0.2R typed information boundary

*Logged late rather than out of order by intent: the A-number is the identifier,
and the section number only reflects when the entry was written. It appears after
A72 because the gap was found by the registration audit that A72's round added.*

**Why this entry exists.** `17-V02R-METHOD-CONTRACT.md` opens with

```text
Status: frozen — logged as **A69**.
```

and A69 never received an entry here. The reference-graph audit could not see it:
only a bold `**Axx**` in a non-amendment document counted as a reference, so a
`Status: … logged as Axx` line formed no edge, and the audit reported a closed
graph. This entry is **mechanical provenance registration**: it records what `17`
§1–§7 already froze and introduces no claim, no threshold, no experiment and no
new semantics. It is not A73.

**The type problem, frozen.** The three candidate representations do not live in
one space,

$$\hat U_{\text{module}} \subseteq \{H, L\}, \qquad
\hat U_{\text{trajectory}} \subseteq \{\text{Episode}\}, \qquad
\hat U_{\text{causal}} \subseteq \Gamma(I)$$

while the primary endpoints are set operations **on $\Gamma$**. So a frozen,
evaluator-side semantic expansion is required:

$$\eta_R : \mathcal U_R \times I^{\text{factual}} \longrightarrow 2^{\Gamma(I)},
\qquad \boxed{\eta_R \text{ must not read } Z^{\text{fire}}_{\text{truth}}}$$

$\eta_R$ is **not** the conversion rule A67 demoted: it names which credit units a
native proposal means and executes no repair. The `credit unit → canonical
intervention` conversion is a V0.3R primitive and stays out of the primary
comparison, or a representation comparison would quietly become a repair-algorithm
comparison. The **method** may read $Z^{\text{fire}}_{\text{truth}}$ — V0.2R hands
it over on purpose — but the **expansion** may not, or a coarse schema's expander
could use cause truth to pick out exactly the right fine units, which is the
evaluator upgrading a coarse schema into a causal one for free.

**Episode-local credit domain.**

$$\Gamma(I) = \{\texttt{Strategy}, \texttt{ProcessCommit}, \texttt{ExternalPlant},
\texttt{Unknown/NoWrite}\} \cup \{\texttt{Decision}_t : t \in I\}
\cup \{\texttt{ControllerSite}_t : t \in I\}$$

Episode-local, so a method **cannot name a timestep or site that never occurred**.

**Native alphabets and expansions, frozen.**

$$\eta_{\text{module}}(H) = \{\texttt{Strategy}, \texttt{ProcessCommit},
\texttt{ExternalPlant}, \texttt{Unknown/NoWrite}\}$$

$$\eta_{\text{module}}(L) = \{\texttt{Decision}_t : t \in I\}
\cup \{\texttt{ControllerSite}_t : t \in I\}$$

$$\eta_{\text{trajectory}}(\{\text{Episode}\}) = \Gamma(I), \qquad
\eta_{\text{causal}} = \mathrm{id}$$

The two module halves are disjoint and their union is $\Gamma(I)$, so a coarse
representation can express any truth at coarse granularity and pays FCR for the
units it over-covers. **A rejected alternative is recorded:** mapping
`ExternalPlant` and `Unknown/NoWrite` to *neither* half would make
$R_{\text{module}}$ structurally unable to express an external fault, scoring
Coverage $= 0$ on every plant-fault episode for a reason unrelated to the
representation's quality. Because $R_{\text{module}}$'s alphabet is only $\{H,L\}$,
the evaluator expands — never the method, or $R_{\text{module}}$ would degenerate
into $R_{\text{causal}}$.

**Oracle separation.** $R_{\text{repair}}$ is **not** a fourth method; it is a
reference ceiling and the interface must separate it:

$$\texttt{OracleCreditAdapter}(\Gamma^\ast) \longrightarrow \Gamma^\ast$$

evaluator-only, taking truth directly and **not** $X_{0.2}$, and sharing no entry
point with the ordinary method path — otherwise A59's risk repeats, a type that
claims to be an oracle while sharing the inference route.

**Abstention is not a verdict.**

$$\varnothing \neq \{\texttt{Unknown/NoWrite}\}, \qquad
\boxed{\text{Coverage} = 0, \quad \text{FCR} = 0 \text{ for } \hat\Gamma = \varnothing}$$

$\varnothing$ is abstention — nothing proposed; `{Unknown/NoWrite}` is a
substantive verdict that the ontology contains no writable mechanism to blame.
They must not be scored alike, and there is **no automatic relabelling** of
abstention into `Unknown/NoWrite`. Set-valued output is retained, no API may
demand a single-label argmax: $|\hat\Gamma| \ge 0$ and $|\Gamma^\ast| \ge 1$.

**`agent_writeable`, assigned here.** A67 left `Strategy` unassigned, so the
definition is stated rather than inferred:

> `agent_writeable(u) = true` iff V0.3R's frozen update primitive is permitted to
> write persistently to unit $u$.

`ProcessCommit`, `Decision_t`, `ControllerSite` are `true` (A67);
`ExternalPlant`, `Unknown/NoWrite` are `false` (A67); **`Strategy` is `false`,
assigned here** — a rescue atom, not a credit target, and it never appears in
$\Gamma^\ast$. Inferring `true` from $do(z = z')$ is exactly the mistake avoided:
being able to perform a runtime intervention is not the same as V0.3R being
permitted a persistent write.

**S2 — interface, typing and information-flow semantics only.** S2 does **not**
test which representation is more accurate; that is the experiment. Nine
assertions: input invariance under hidden changes; no support identity; alphabet
closure; expansion truth-independence; `ExternalPlant` survives scoring; rescue
cannot move truth; abstention $\neq$ NoWrite; oracle exactness; side-effect
freedom. Acceptance bar as in S1 — a trivially dumb method must be able to walk
the whole interface and pass. **S2 proves the pipe, never the method.**

**Forbidden inputs, with the boundary drawn here:** latent $M$, $Z^{\text{pres}}$,
$\mathcal R^{\text{mech}}$, $\mathcal R^{\text{rescue}}$, $\Gamma^\ast$, world id,
rows-block id, the `DenseSupport` hypothesis set, DGP weights, any
`outcome_after(intervention)` oracle, any write target. Allowed, because it is
public mechanism knowledge rather than evaluator truth: the public $\Gamma$
ontology and its `agent_writeable` flags, the environment/action grammar, and a
**read-only** $\pi_D^\ast(s,z,m)$ view. $B_Q = 0$ — no query session, no
counterfactual evaluator calls. V0.2R is not V0.1R with a different head: there is
nothing to query.

$$\boxed{\text{frozen — interface/type contract; later scientific interpretation amended by A70–A72}}$$

**Scope fence.** `17` §1–§7 are A69. `17` §8 is A72's locator grant, and `17`
§9–§10 are later: the order in force and the three-methods degeneracy exposed
*after* A69 was frozen. That degeneracy is deliberately **not** recorded here as
A69's content — it was not known at the freeze, and it is not backfilled. What
A70–A72 supersede is A69's **reading** of what V0.2R can claim, not its interface,
its typing or its information-flow boundary; `17` §9 states that the typed
contract and S2 are correct regardless.

## 60. A73 — the locator evidence quotient, and the public feasible support

**Why A72's wording was not tight enough.** A72 wrote the locator's input as
$X_{0.2} = (I^{\text{factual}}, Z^{\text{fire}}_{\text{truth}})$ and left
"learner-visible factual evidence" unqualified. But `sigma0` returns it as **two
parts**:

$$\texttt{sigma0} = \bigl(\text{rows},\ \text{feedback}\bigr), \qquad
\text{rows} = (x, y, t, \kappa, \phi, z, m, a^{cmd}, a^{realized}, r)$$

and `feedback` $=$ `decode_feedback`($Z^{\text{fire}}$) is driven by
`(error_flag, cause_rank)`, which **never appear in rows**. So one symbol $X_{0.2}$
was naming two different objects, and the phrase "893 information classes" was
silently describing the partition obtained **after discarding feedback**. Measured
on the full support:

$$\bigl|X^{\text{obs}}\text{-classes}\bigr| = 4513, \qquad
\bigl|X^{\text{loc}}\text{-classes}\bigr| = 893$$

and **100%** of the 893 locator classes are split by the feedback channel (845
into 5, 48 into 6), covering 100% of the DGP mass. $4513/893 = 5.0538$.

$$\boxed{\text{one symbol may not again denote both objects}}$$

**Historical occurrences are left as written.** The bare $X_{0.2}$ still appears
inside A65's, A70's and A72's own frozen text — their definitions, their rejected
routes, and the verbatim locator grant. Those are the **record**, and rewriting them
would falsify the log rather than clarify it. This section is their interpretation:
wherever a frozen passage says $X_{0.2}$, read it as the object that passage was
about, and the two live specifications (`16` §3, `17` §2) now state the split
directly rather than relying on this note.

**The quotient, frozen.**

$$X^{\text{obs}}_{0.2} = (\text{rows}, \text{feedback}, Z^{\text{fire}}_{\text{truth}}),
\qquad
X^{\text{loc}}_{0.2} = (\text{rows}, Z^{\text{fire}}_{\text{truth}})$$

$$q : X^{\text{obs}}_{0.2} \longrightarrow X^{\text{loc}}_{0.2}, \qquad
q(\text{rows}, \text{feedback}, Z^{\text{fire}}) = (\text{rows}, Z^{\text{fire}})$$

$$\boxed{\bigl|X^{\text{loc}}\text{-classes}\bigr| = 893 \text{ is the }
\texttt{CausalSetLocator} \text{ main gate}}$$

$4513$ is the full observational refinement. It is a fact about the environment,
**not** the gate.

**This is not "pretending feedback does not exist."** V0.2R hands over
$Z^{\text{fire}}_{\text{truth}}$ on purpose, so the feedback channel is a report
about a quantity already given, and the only thing it adds is the nuisance pair.
Declaring it out of the locator's input is therefore a **stronger** localisation
claim: the locator must invert from strictly less evidence.

**But redundancy may not be assumed — it must be proven.** Four exact invariances
must be discharged first:

$$\text{rows},\quad Z^{\text{fire}},\quad \Gamma_{\text{desc}},\quad
\text{feasibility} \quad\text{all invariant under } (error\_flag, cause\_rank)$$

and then the envelope equality over **all 4,513** observational classes:

$$\boxed{\Gamma^-_{\text{obs}}(x) = \Gamma^-_{\text{loc}}\bigl(q(x)\bigr),
\qquad
\Gamma^+_{\text{obs}}(x) = \Gamma^+_{\text{loc}}\bigl(q(x)\bigr)}$$

$$\boxed{\text{one violation} \;\Rightarrow\; \text{rows-only is void and the main
gate reverts to } 4513}$$

So the rule is **prove feedback is target-preserving, then quotient** — never fix
a representative and hope. Only *after* the gate passes may `PublicSCMView` choose
a canonical nuisance representative, e.g. $(\texttt{error\_flag},
\texttt{cause\_rank}) = (0,0)$, precisely because rows, fire, descriptor and
feasibility are constant on that nuisance equivalence class.

**A71's 14/893 must be re-read.** Henceforth

$$\boxed{\text{14 of 893 } \textbf{locator} \text{ information classes } X^{\text{loc}}}$$

It must not be read as a fraction of the full learner-visible observational
partition, which is $4513$.

**Second half: $\mathcal L_{\text{public}}$ is the feasible canonical grammar set,
not the grammar product.** A72 defined it as "canonical structural support as a
set, with probabilities erased", which still under-specified feasibility:

$$\boxed{\mathcal L_{\text{public}} = \{\text{canonical grammar candidates
that pass public forward-feasibility}\}}$$

$$\text{canonical grammar} \to \text{public factual rollout} \to
\text{reject MALFORMED / OptionViolation} \to \mathcal L_{\text{public}}$$

No DGP probability, no DGP weight, no world id — but the **same feasibility
semantics as `DenseSupport`**. Without this the locator is judged against a world
set it was never allowed to stand on: enumerating a grammatical but infeasible
hypothetical world would contribute a $\Gamma_{\text{desc}}$ outside
$\Gamma^+_{\text{eval}}$ and fail the gate for a reason that is not the locator's.
The support difference has **two** independent sources — enlarging the domain, and
feasibility filtering — and A72 closed only the first.

**Route C's semantic source, frozen.** The migration source is

$$\texttt{gate\_stage2}.\_domains \;+\;
\texttt{identifiability\_gate}.\texttt{canonicalise}$$

because `support_build.py` builds `DenseSupport` from exactly that path. The second
enumeration — `identifiability_gate.legal_fault_domains`, which returns **tuples**
and lacks the `Trap` `ValueError` guard that `_domains` carries — may later be
re-pointed at the same public grammar but **is not the truth source**. The
extraction regression compares **normalised canonical structural tuples**, not
bytes, in the frozen order:

```text
P: option_id
D: (t, action)
X: (x, y, t, kappa, phi, cmd, realized)
E: (t, realized)
U: (t, x, y)
```

$$\boxed{\texttt{canonical(new\_grammar(ctx))} =
\texttt{canonical(old\_\_domains(ctx))} \quad \text{for every public base context}}$$

Old code may switch to the new public implementation only after that holds
everywhere.

**Measured at extraction** (`scripts/a73_grammar_equivalence.py`), over all
**5,760** public base contexts — $2$ kappas $\times$ $720$ tapes $\times$
**$4$** options: raw legal domains, canonical domains, and canonical sizes/order
all **0 mismatches**. The regression compares A73's normalised structural form and
**not** bytes, because one historical implementation returns objects and the other
returns tuples.

Two corrections this measurement forced:

* `option_ids()` has **4** entries, not 6. An earlier review figure of $8{,}640$
  contexts (and the arithmetic "$6$ options $\times$ $32$ presence patterns") was
  wrong; the base-context count is $5{,}760$ and the canonical candidate space
  measures **1,166,400** assignments (~202.5 per context). The "thousands, not
  millions" performance argument survives, but the earlier constant does not.
* The `Trap` `ValueError` guard fires on **0** contexts. The guarded and unguarded
  enumerations are therefore **behaviourally identical** on the frozen map and
  horizon. `_domains` is the truth source because `support_build.py` builds
  `DenseSupport` through it — **not** because `legal_fault_domains` is observably
  broken. The earlier statement in review that the tuple variant "would raise" is
  an overstatement and is **corrected**: the divergence is latent, not observed,
  and would only appear if the map or horizon changed.

**`support_build.domains()` is re-pointed** to the public grammar, and gated on an
end-to-end check that the rebuild reproduces the committed support manifest
(`scripts/a73_support_digest_regression.py`) — the grammar determines the candidate
parameter set, so a matching `content_digest` over $1{,}038{,}960$ worlds is the
strongest available statement that the public grammar and the frozen evaluator
support are the same object.

**Measured at the re-pointing**: the rebuild takes **11.8 min** and reproduces
$n_{\text{worlds}} = 1{,}038{,}960$, $n_{\text{rows\_blocks}} = 547$,
$\text{weight\_sum} = 1.0$ and
$\texttt{content\_digest} = \texttt{8ecaf60d0b9af30f}$ — **all five identical** to
the committed manifest. The regression calls `build()` directly and never reaches
`sup.save()`, so the 115 MB regenerable payload is not overwritten by the
verification.

**Deliberately left on the historical path.** `a71_indexed_truth.py` and
`a73_quotient_gate.py` keep calling `gate_stage2._domains + canonicalise`. That is
a feature, not an oversight: it keeps those gates an **independent
implementation** cross-check of the public grammar instead of letting both sides
share one bug.

**`PublicSCMView`, and the extraction it forced.** The view must forward-simulate a
hypothetical world and report what a learner would have seen, so it needs the *same*
timeline and the *same* rows as `sigma0`. Those lived in `scripts/gate_stage2.py`,
and copying them would have created a second implementation of the observation
model — the very defect route C removed for the grammar. So `walk_transition` and
the row tuple moved to `src/rfl_rebuild/env/observation.py`, with `ROW_SCHEMA` now
naming the frozen fields; `gate_stage2` **re-exports the same function objects**, so
there is still one implementation, and `sigma0` calls `learner_rows`. That is also
where the observation model belongs: **the row tuple is the definition of
$X^{\text{loc}}$**.

**Measured at that re-pointing**: the full rebuild again takes ~11.4 min and again
reproduces $\texttt{content\_digest} = \texttt{8ecaf60d0b9af30f}$, so relocating the
observation model changed nothing. (The digest is the sensitive detector here: the
rows feed `block_id`, which is part of the digest's payload.)

The view exposes exactly the four capabilities and nothing else:

| capability | method |
|---|---|
| canonical public fault hypotheses | `hypotheses(kappa, phi)`, `proposals()` |
| forward factual rollout | `forward(hyp)` |
| fired-mechanism vector | `fire_vector(hyp)` |
| hypothetical descriptor → $\Gamma$ unit | `credit_unit(descriptor)`, `credit_units(hyp)` |

$\kappa$ and $\phi$ are inputs, not secrets — they appear verbatim in the
learner-visible rows. `proposal` is **not**: the evidence carries
$z^{\text{in-force}}$ only (A55), so it is enumerated. The canonical nuisance
representative $(\texttt{error\_flag}, \texttt{cause\_rank}) = (0,0)$ is fixed here,
and the gate **requires A73's quotient artifact to read PASS** before it is
allowed — the licence is tied to its evidence instead of asserted.

**Measured** (`scripts/a73_public_scm_gate.py`), 12/12 PASS:

| check | result |
|---|---|
| import allowlist, AST and prefix-based | clean: kernel / fault_grammar / observation / credit only |
| public attribute surface | exactly the four capabilities + 2 constants |
| no forbidden name on the surface | clean |
| canonical nuisance representative licensed | quotient gate PASS |
| truth inside `hypotheses(kappa, phi)` | **893 / 893** classes |
| `forward` reproduces the evaluator's rows | **893 / 893** |
| `fire_vector` reproduces the evaluator's $Z^{\text{fire}}$ | **893 / 893** |
| `credit_units` never returns $\varnothing$ | 0 collapses |
| clean worlds give `{Unknown/NoWrite}` | consistent |
| `EmptyCompatibleSet` is a `ProtocolError` | yes |

The round-trip is an **independent** confirmation of I1: the view fixes
$(\texttt{error\_flag}, \texttt{cause\_rank}) = (0,0)$ while the evaluator uses each
world's own values, and the rows still agree on every class. It also establishes
$\mathcal L_{\text{public}} \supseteq \text{support}$ — the candidate space never
misses the truth.

**Measured — the main gate** (`scripts/a73_locator_gate.py`), **12/12 PASS**:

| layer | result |
|---|---|
| 1 evaluator reference | 893 classes |
| 2 $\Gamma^+$ / $\Gamma^-$ / exact $\Gamma^\ast$ set | **0 / 0 / 0** mismatches over 893 |
| 2 empty compatible sets | 0 |
| 3 locator import allowlist | clean — `public_scm` only |
| 4 mutation: controller/plant boundary erased | **321 classes killed** |
| 4 kill set vs X-firing classes | **exactly equal** (321 = 321) |
| 4 kill set ∩ plant-only classes | **empty** (0 of 330) |
| 4 A71 ambiguous classes killed | **14 / 14** |
| 4 second control: A71's generic-unit P0 | **579 killed**, exactly the D-or-X classes |

$$\boxed{\hat\Gamma_{\text{CSL}}(X) = \Gamma^+_{\text{eval}}(X) \ \wedge\
\Gamma^-_{\text{CSL}}(X) = \Gamma^-_{\text{eval}}(X) \quad \forall X \in \{1,\dots,893\}}$$

The two sides use separately written projections (the evaluator's via
`DenseSupport` + A71's `gamma_star_indexed`, the locator's via `PublicSCMView`), so
the agreement is evidence rather than a tautology.

**Two notes on the mutation, because a kill count alone can mislead.** The kill set
is **exactly** the 321 classes where the controller mechanism fires — not merely a
subset of the 651 X-or-E classes, and disjoint from the 330 plant-only classes — so
the failure is attributable to the erased boundary rather than to collateral damage.
And the mutation had to be **repaired before it bit at all**: `credit_units`
originally called `PublicSCMView.credit_unit` instead of `self.credit_unit`, so the
subclass override never ran and the kill set came back **empty**. A no-op mutation
would have read as "the gate is robust". That is precisely why the kill set is
recorded instead of a boolean.

**The corrected census, and a degenerate endpoint.**

$$\boxed{\text{VOIDED BY A74 (12 §61)}}$$

The `Module` row below, the $\text{Coverage} \equiv 1$ box and the "degenerates to
FCR alone" conclusion are **invalid**: this census chose H/L from $\Gamma^\ast$
instead of $Z^{\text{fire}}$, so the object it scored was not the frozen
$R_{\text{module}}$. Kept as written because the log is append-only; A74 records the
correction and the rule that
$\text{Coverage}(\varnothing, \Gamma^\ast) = \text{FCR}(\varnothing, \Gamma^\ast)
= 0$. The rest of this section stands: the 57 distinct indexed $\Gamma^\ast$ sets, the
0.1881% mass, and the claim boundary.

`scripts/a73_census.py`, all $1{,}038{,}960$ worlds, co-primary `Coverage` / `FCR`:

| representation | Cov(count) | Cov(mass) | FCR(count) | FCR(mass) | $\lvert\hat\Gamma\rvert$(count) |
|---|---|---|---|---|---|
| `OracleCredit` | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 1.71 |
| `CausalSetLocator` | 1.0000 | 1.0000 | 0.0028 | 0.0006 | 1.72 |
| `Module` | 1.0000 | 1.0000 | 0.8083 | 0.7911 | 12.88 |
| `Trajectory` | 1.0000 | 1.0000 | 0.9017 | 0.9309 | 17.90 |

Distinct **indexed** $\Gamma^\ast$ sets: **57** — A70 reported 21 on the generic
truth, which is the tell A71 identified. Mass where $\Gamma^+ \neq \Gamma^\ast$:
**0.188122%**, reproducing A71's mixed-class mass (0.1881%) by an independent route.

$$\boxed{\text{Coverage} \equiv 1 \text{ for all four arms}}$$

and this is **structural, not empirical**:
$\text{Coverage}(\hat\Gamma,\Gamma^\ast) = 1 \iff \Gamma^\ast \subseteq \hat\Gamma$,
and every arm is a superset — `OracleCredit` *is* $\Gamma^\ast$;
$\Gamma^+ \supseteq \Gamma^\ast$; $\eta_{\text{module}}(H) \cup \eta_{\text{module}}(L)
= \Gamma(I) \supseteq \Gamma^\ast$ with at least one of $H, L$ always emitted
because $\Gamma^\ast \neq \varnothing$; and
$\eta_{\text{trajectory}}(\{\text{Episode}\}) = \Gamma(I)$.

**So the co-primary pair degenerates to FCR alone**, and A69's own design is why: its
expansions were chosen so that "a coarse representation can express any truth — at
coarse granularity, and paying FCR for the units it over-covers". That *guarantees*
maximal Coverage. A69 froze the intent without recording this consequence, and A70's
voided census could not have shown it either.

This changes no input field, no $\mathcal L_{\text{public}}$ and no locator target,
so it does **not** meet A73's own trigger for a new amendment. It is recorded here as
a **measured consequence**; freezing it as a standalone claim is a separate decision.

The headline contrast — the exact inversion over-credits **0.06%** of DGP mass while
`Module` over-credits **79%** and `Trajectory` **93%** — is subject to the unchanged
claim boundary: $\Gamma^+$ is built from the same $\pi_{\text{credit}}$ as the truth,
so this measures over-credit under a **fixed** ontology and does **not** validate
that ontology.

**Support closure, as an exact set not a subset.** The subset condition is the
minimum; because the endpoint is *exact* inversion, the requirement is

$$\boxed{\{\Gamma^\ast(\tilde\ell) : \tilde\ell \in \mathcal C_{\text{SCM}}(X)\}
= \{\Gamma^\ast(\ell) : \ell \in H_{\text{eval}}(X)\} \quad \forall X \in
\{1,\dots,893\}}$$

from which $\Gamma^+_{\text{CSL}} = \Gamma^+_{\text{eval}}$ and
$\Gamma^-_{\text{CSL}} = \Gamma^-_{\text{eval}}$ follow. This way 893/893 validates
the **candidate-world set semantics itself**, not merely the final output.

**Order in force.**

$$\boxed{\text{A73} \to 4513{\to}893 \text{ envelope gate} \to \text{grammar
extraction} \to \text{public-support exact-set regression} \to
\texttt{PublicSCMView} \to \texttt{CausalSetLocator} \to 893/893\ \Gamma^+/\Gamma^-
\to \text{X/E mutation} \to \text{corrected census}}$$

## 61. A74 — the A73 census built the Module proposal from evaluator truth

**The defect.** A73's census constructed `Module` by reading $\Gamma^\ast$ to choose
its native H/L proposal:

```python
h = {u for u in truth if not is_indexed(u)}
l = {u for u in truth if is_indexed(u)}
```

But `17` §9.1's frozen $R_{\text{module}}$ rule derives the proposal from the
**fired causes**. It is a function of $X^{\text{obs}}$ and must not read
$\Gamma^\ast$:

$$H \iff Z_P^{\text{fire}} \lor Z_E^{\text{fire}} \lor Z_U^{\text{fire}},
\qquad
L \iff Z_D^{\text{fire}} \lor Z_X^{\text{fire}}$$

Most worlds agree by accident, because $P/E/U \to H$ and $D/X \to L$. The footprint
is exactly one case:

$$\boxed{Z^{\text{fire}} = 00000}$$

The frozen rule has no fired cause, so it emits
$\hat U_{\text{module}} = \varnothing$ — **abstention**. A67's truth there is
$\Gamma^\ast = \{\texttt{Unknown/NoWrite}\}$, and A69 §5 froze
$\varnothing \neq \{\texttt{Unknown/NoWrite}\}$ with
$\text{Coverage}(\varnothing, \Gamma^\ast) = \text{FCR}(\varnothing, \Gamma^\ast)
= 0$. Reading the truth classified `Unknown/NoWrite` as non-indexed and emitted $H$,
converting an abstention into a coarse **substantive verdict** — precisely the
collapse A69 §5 exists to prevent, and the reason "say nothing is not a verdict" was
kept so carefully.

$$\boxed{\text{A73's Module row and its endpoint-degeneracy claim are INVALID}}$$

**Measured footprint**: $Z^{\text{fire}} = 00000$ is **17,280 worlds = 43.86% of DGP
mass** — the modal region, not a corner case.

**Voided, not inherited** (exactly as A71 voided A70's census rather than rewriting
it):

* A73's `Module` row — Cov 1.0000/1.0000, FCR 0.8083/0.7911, $\lvert\hat\Gamma\rvert$
  12.88;
* A73's "$\text{Coverage} \equiv 1$ for all four arms";
* A73's "the co-primary pair degenerates to FCR alone".

**Corrected**, frozen rule restored, **no design change**:

| representation | Cov(count) | Cov(mass) | FCR(count) | FCR(mass) |
|---|---|---|---|---|
| `OracleCredit` | 1.0000 | 1.0000 | 0.0000 | 0.0000 |
| `CausalSetLocator` | 1.0000 | 1.0000 | 0.0028 | 0.0006 |
| `Module` | **0.9834** | **0.5614** | **0.7958** | **0.4622** |
| `Trajectory` | 1.0000 | 1.0000 | 0.9017 | 0.9309 |

`Module` is the **only** arm outside the structural-identity family, and Coverage is
no longer degenerate — the opposite of A73's claim:

$$\boxed{\text{Coverage punishes abstention; FCR punishes over-credit}}$$

The co-primary pair was never degenerate; A73's leak is what made it look so. The
$Z^{\text{fire}} = 0$ region is exactly where both endpoints are needed, which is why
the pair is co-primary at all.

**Two guards, frozen here.**

1. **Semantic canary.** $Z^{\text{fire}} = 00000$ with
   $\Gamma^\ast = \{\texttt{Unknown/NoWrite}\}$ must give
   $R_{\text{module}} = \varnothing$,
   $\hat\Gamma_{\text{module}} = \varnothing$, Coverage $= 0$, FCR $= 0$. Observed on
   all 17,280 such worlds, **0 failures**. No special case is added:
   $Z^{\text{fire}} = 0 \Rightarrow H$ is *not* introduced, because that would
   redefine `Module` after seeing its result.
2. **Information-flow assertion.** $R_{\text{module}}(X^{\text{obs}})$ must not change
   when $\Gamma^\ast$ changes while $X^{\text{obs}}$ is held fixed. Tested against six
   counterfactual truths per fire code: **0 violations** for the frozen rule, and the
   assertion **rejects A73's defect variant on 21 fire codes** — so it has power
   rather than being satisfied by construction.

**Claim boundary, unchanged.** This is still over-credit under a **fixed** ontology;
it does not validate that ontology. And the lesson is the recurring one: every check
passed and the table looked clean, but the object being scored **was no longer the
frozen `Module`**.

## 62. A75 — V0.3R semantic rebase: persistent learning update

**Status: frozen — specification only.** The V0.3R semantic rebase. It authorises
**no** implementation: no `kernel.py` change, no B1 update formula, no run. The review
closed over three rounds — the first draft's shared $S_+/S_0$ (§62.5), its interpretive
provenance rule (§62.7), its `manifested addresses` placeholder and two
$Z$-provenance errors were corrected in the second, and §62.10's derived-feature
laundering hole in the third. **Any further change to this section requires a new
amendment; it is not to be rewritten in place.**

Its purpose is to stop three defects from being inherited by V0.3R and to stop four
distinctions from being re-invented at implementation time.

**Why it exists.** `08-V03R.md` identifies the process fault with $do(z = z')$,
which the frozen reading contradicts:

$$\text{mechanism repair} = do(C_P = \mathrm{identity}), \qquad
do(z = z') = \text{strategy replay / rescue}$$

But the deeper problem is the *subject*: `08` treats a **runtime mechanism repair**
as the thing V0.3R studies, which glues $R^{\text{mech}}$ to $W^{\text{update}}$ — the
one merge A65's five-way split exists to prevent. `08` is therefore **not
resynchronized** and V0.3R must not be implemented from it (recorded in `07`'s
status block).

### 62.1 The subject, frozen

$$\boxed{\text{V0.3R studies the persistent learning update, not runtime repair}}$$

$$\Gamma_r^\ast \;\longrightarrow\; \mathcal W(\Gamma_r^\ast) \;\longrightarrow\;
W^{\text{update}} \;\longrightarrow\; \Delta W \;\longrightarrow\; Y^{\text{future}},
\qquad r \in \{T, P\}$$

$$\boxed{R^{\text{mech}} \neq W^{\text{update}}}$$

$R^{\text{mech}}$ is retained as an **evaluator semantic reference** — it says which
faulty mechanism a credit location corresponds to — and may **never** be converted
automatically into a persistent write. The two differ in *who performs them*
(evaluator intervention vs learner state write) and, as §62.12 shows, sometimes also
in *content*; the invariant is that no rule may infer the second from the first.

### 62.2 Read channel / persistent store / addressable target

$$\boxed{\text{read channel} \;\neq\; \text{persistent backing state} \;\neq\;
\text{addressable write target}}$$

A kernel read channel existing does **not** establish that a persistent, writable
object exists behind it. A legal persistent target must satisfy all seven:

$$\boxed{\begin{aligned}
&1.\ learner\text{-owned}\\
&2.\ persistent\\
&3.\ future\text{-read}\\
&4.\ non\text{-environment}\\
&5.\ non\text{-evaluator-}do\\
&6.\ addressable\\
&7.\ contract\text{-preserving}
\end{aligned}}$$

### 62.3 Contract preservation, and the privilege split

**Learner baseline has no fault privilege.** For the current option system the
command must satisfy $a^{cmd} \in A_z(m,s)$, and a learner-owned controller baseline
may not bypass $A_z$ through its output $u$. Transient faults keep the **fault
privilege** — $Z_X$/$Z_E$ exist precisely because a fault *may* violate the contract:

$$\boxed{\text{fault privilege is fault semantics, not a learner privilege}}$$

**Measured, and the reason this is criterion 7 rather than a style rule**
(`scripts/_diag_controller_channel.py`, artifact `controller_channel_check.json`,
commit `0038a39`). `rollout` checks `a_cmd` against `option_actions` but never checks
the controller channel's output $u$, which becomes $a^{realized}$; and no caller in
the repository passes a non-`None` controller mapping, so the channel is a **latent**
extension point that V0.3R would open. Over the 13,824 $(s,z,m)$ entries with a
non-empty admissible set: 9,504 have $A_z(m,s)$ equal to all legal actions; 4,320
admit a legal action outside $A_z$; and **576** of those admit one that reaches a
strictly closer cell than every admissible action. Independently,
`ReferenceSolution.q[(s,z,m)]` is keyed only over `option_actions`, so the exact
reference DP **does not define a value** for leaving the option at all — the
evaluator could not score the deviation even in principle. A learner write with the
fault privilege would therefore let the future return reward a route the experiment
never defined.

### 62.4 B0 outputs a candidate family, not an answer

$$\boxed{B_0 : \Gamma_r^\ast \longrightarrow \mathcal W(\Gamma_r^\ast)}$$

**not** $\Gamma^\ast \to W^\ast$. $\mathcal W$ is the set of **legal persistent-write
hypotheses**. Current boundary, frozen here:

| credit location | baseline read channel | persistent store | address | V0.3R must |
|---|---|---|---|---|
| `ControllerSite` | `controller` mapping | caller-owned mapping | `ControllerSite(s,a^{cmd})` | add the contract check; B1 may write |
| `Decision_t` | `command_provider` | **not fixed by the kernel** | **not fixed** | provide the architecture explicitly |
| `ProcessCommit` | **none** | none | none | create a $C_P^L$ baseline path first (§62.11) |
| `ExternalPlant`, `Unknown/NoWrite` | — | — | — | $\mathcal W = \{\varnothing\}$ |
| `Strategy` | — | — | — | rescue atom; not in mechanism-credit write |

### 62.5 Stratification is regime-specific: $S_{T,\pm}$ and $S_{P,\pm}$

The writable projection is defined **per regime**, because the two regimes have
different truth sources (§62.8):

$$\Gamma_{r,W}^\ast = \{u \in \Gamma_r^\ast : agent\_writeable(u)\}, \qquad
r \in \{T, P\}$$

$$\boxed{\text{a single } S_+ / S_0 \text{ pair spanning both regimes is forbidden}}$$

A shared symbol would let a mass measured on one regime's population be read as a
property of the other's. The first draft did exactly that; it is corrected here rather
than annotated.

#### 62.5.1 Regime T

$$S_{T,+} = \{\Gamma_{T,W}^\ast \neq \varnothing\}, \qquad
S_{T,0} = \{\Gamma_{T,W}^\ast = \varnothing\}$$

**Measured on the frozen V0.2R support, and these numbers belong to $T$ alone**
(`_diag_v03r_scope.py`, `v03r_scope_diag.json`, commits `5fea68f`/`e13c62c`):

$$P_T(S_{T,+}) = 0.445711, \quad
\text{pure } 0.399814, \quad \text{mixed } 0.045898, \qquad
P_T(S_{T,0}) = 0.554289$$

#### 62.5.2 Regime P

Regime P's population does not exist yet. It therefore has **no measured mass**, and
none may be quoted for it. What can be frozen now is a construction property.

A P **learning event** requires at least one persistent learner manifestation:

$$\boxed{\mathcal M_P^L \neq \varnothing \text{ is required for a P trigger}}$$

Every manifestation target — `ProcessCommit`, `Decision_t`, `ControllerSite` — is
writable in the working ontology (A69 §6). Therefore, **on the P trigger population**,

$$\boxed{S_{P,+} = 1, \qquad S_{P,0} = 0}$$

is a **construction result, not a finding**. A persistent defect that does not
manifest in the current episode is an ordinary future-evaluation episode: it mints no
$\Gamma_P^\ast$ and triggers no update.

$$\boxed{\text{NoWrite chosen in } S_{P,+} \;\neq\; \text{positive-write-ineligible }
S_{P,0}}$$

The first says *a writable responsibility location existed and this primitive chose not
to write*; the second says *the ontology forbids writing*. Collapsing them would let a
method's own abstention be scored as a boundary.

#### 62.5.3 Rules that hold in both regimes

$$\boxed{\text{the stratum is fixed by the truth boundary, never by whether the
method actually wrote}}$$

Conditioning on $W^{\text{update}} \neq \varnothing$ would let B0/B1 abstain on hard
worlds and be scored on easy ones — a selection bias of A74's shape.

$$\boxed{\text{no whole-support primary mean, in either regime}}$$

$S_{r,+}$ answers *how to change correctly*; $S_{r,0}$ answers *how to avoid changing
wrongly*. Within each regime the two masses are reported together and always.

### 62.6 Regimes T, P, I

**T — transient incident.** Trigger uses the existing transient fault semantics;
future episodes are the clean baseline. Its role is **not** positive-primitive
ranking:

$$\boxed{T\text{'s primary role is harm / erroneous internalisation}}$$

NoWrite is the reference arm. Because the healthy baseline *is* the exact reference
($\pi_D^\ast$ from the frozen DP, identity controller, faithful commit), NoWrite
**weakly dominates** any write that changes healthy behaviour — so a strong positive
result in T is a signal to check contract preservation, not to celebrate.

**P — persistent learner defect.** The defect lives in the learner's persistent
state, and post-write episodes must read **the same state that was written**:

$$\boxed{\text{future rollout is endogenous to } \Delta W}$$

Pre-computing future $Z^{\text{fire}}/\Gamma^\ast$ and attaching it to the updated
learner is **forbidden**. Note endogeneity is *not* P-specific: in T a non-identity
contract-preserving write also changes the future episode's cause structure. What is
P-specific is that the defect itself lives in the store.

**I — intermittent.** Retained as a **secondary regime**. A75 freezes that it exists
and freezes nothing numeric about it: the recurrence probability and schedule are
preregistered after T/P semantics are settled, rather than guessed now.

### 62.7 Persistent manifestation: $J^L$, and why $Z^{\text{fire}}$ is not replaced

The frozen $Z^{\text{fire}}$ answers a **closed** V0.1R/V0.2R question and is left
untouched:

$$Z_D^{\text{fire}} = 1[\text{the injected DecisionOverride mechanism executed}]$$

Replacing it with a behavioural predicate would reopen V0.1R's target. V0.3R adds a
separate object instead:

$$J^L = (J_P^L, J_D^L, J_X^L)$$

$$\boxed{Z^{\text{fire}} = \text{the frozen closed-version factual
mechanism-execution object}}$$

$$\boxed{J^L = \text{the V0.3R learner-origin persistent manifestation object}}$$

They have **different source semantics**, they **may share a predicate**, they may be
numerically 1 at the same time, and they are **not required to be mutually
exclusive**. What keeps Regime P off the old truth chain is not a claim about the
function $Z^{\text{fire}}$ — which does *not* check provenance — but the source rule of
§62.8: $\Gamma_T^\ast$ uses the frozen T truth source, $\Gamma_P^\ast$ uses $J^L$ plus
learner-origin addresses.

**Provenance must be structural, not interpretive.** The first draft wrote the
predicates against the *final* command, but the frozen priority is
$do(d_t) > Z_D > \text{provider}$, so a deviation in $a^{cmd}_t$ cannot be attributed
to the learner baseline; the same holds for $X$ and $P$. A75 therefore names the
baseline intermediates first:

$$\boxed{a_t^L = \text{the learner decision baseline output, before } Z_D / do(d_t)}$$

$$\boxed{u_t^L = C_X^L(s_t, a_t^{cmd}), \text{ before } Z_X / do(C_X)}$$

$$\boxed{z_L^{commit} = C_P^L(z^{\text{proposal}}), \text{ before } Z_P / do(C_P)
/ do(z{=}z')}$$

and only then defines, over the whole argmax **set**
$A_D^\ast = \arg\max_{a \in A_z(m,s)} Q_D^\ast$ and never the tie-broken
`best_action`:

$$\boxed{J_D^L = 1[\exists t : a_t^L \notin A_D^\ast(s_t, z_t, m_t)]}$$

$$\boxed{J_X^L = 1[\exists t : u_t^L \neq a_t^{cmd}]}$$

$$\boxed{J_P^L = 1[z_L^{commit} \neq z^{\text{proposal}}]}$$

Provenance is thereby part of the object rather than an implementer's later reading of
a number, and the address sets of §62.8 are built from the same intermediates.

**The provenance table, corrected.** Note that `fired_mechanisms()` takes no
`InterventionSet` — it calls `rollout` with the default empty one — so **no evaluator
`do` participates in the frozen factual $Z^{\text{fire}}$ at all**:

| object | predicate | source |
|---|---|---|
| $Z_D^{\text{fire}}$ | the override was reached | injected `mask.decision` |
| $Z_X^{\text{fire}}$ | $\exists t: u_t \neq a^{cmd}_t$ | **value predicate only — no provenance check** |
| $Z_E^{\text{fire}}$ | $\exists t: a^{realized}_t \neq u_t$ | **value predicate only — no provenance check** |
| $Z_P^{\text{fire}}$ | factual commit mismatch $z^{\text{in-force}} \neq z^{\text{proposal}}$ in the closed transient world | injected `option_fault` on the frozen support |
| $J_D^L$ | $\exists t: a^L_t \notin A_D^\ast$ | learner baseline $a^L$ only |
| $J_X^L$ | $\exists t: u^L_t \neq a^{cmd}_t$ | learner baseline $u^L$ only |
| $J_P^L$ | $z^{commit}_L \neq z^{\text{proposal}}$ | learner baseline $z^{commit}_L$ only |

$$\boxed{J^L \text{ is } (\text{predicate}, \text{source}); \text{ neither half alone
is the object}}$$

$Z_X^{\text{fire}}$ and $J_X^L$ share a predicate **verbatim**. Separating them by a
later claim about provenance would make $J_X^L$ a synonym for $Z_X^{\text{fire}}$; the
intermediates $u^L$ versus $u$ are what actually separate them. Because
`fired_mechanisms()` accepts `controller=`, a learner-origin deviation passed through
that channel would make $Z_X^{\text{fire}}$ true as well — which is why the two objects
are *allowed* to co-fire and are never used interchangeably.

**Measured** (`scripts/_diag_jd_manifestation.py`,
`a75_jd_manifestation_precheck.json`, commit `5c0ae15`), all six checks PASS:

* with **no** `mask.decision` but a provider emitting a strictly suboptimal action at
  a reachable context: `fired_mechanisms()["Z_D"] == 0` while $J_D^L = 1$ — the
  frozen truth is blind to learner-origin defects, by design;
* a reachable `DecisionOverride` sets $Z_D^{\text{fire}} = 1$ whether or not it costs
  value: a **tied-optimal** override gives $Z_D = 1$ with $J_D^L = 0$;
* **tie audit**: 5,191 of 13,824 $(s,z,m)$ entries have $|A_D^\ast| > 1$; of the
  24,912 candidates the D domain admits, **8,548 (34.3%)** are tied-optimal; on the
  canonical support itself **720 of 8,640 D slots (8.3%)** carry **no value loss**.

$$\boxed{\text{"a decision fault happened"} \text{ is strictly weaker than }
\text{"a bad decision happened"}}$$

That is a recorded property of the frozen support, not a change to it. It is also
why $J_D^L$ uses $A_D^\ast$: the tie-broken definition would manufacture 720 defects
that do not exist.

### 62.8 Regime-specific credit truth, and the manifestation address sets

A bare $\Gamma^\ast$ must not be used, for the same reason A73 forbade a bare
$X_{0.2}$:

$$\boxed{\Gamma_T^\ast \neq \Gamma_P^\ast}$$

$\Gamma_T^\ast$ is the **already-frozen** V0.2R working-ontology truth (A67/A71: built
from $R^{\text{mech}}$ descriptors, D/X carrying addresses).

**Regime source rule, frozen.**

* **T trigger**: transient injected fault semantics only; the learner baseline is
  healthy before the update.
* **P trigger**: persistent learner defect semantics only. A P trigger may **not**
  manufacture its truth from `mask.decision`, `mask.controller` or `option_fault`, nor
  from an evaluator $do(\cdot)$.

$$\boxed{\Gamma_P^\ast \text{ may come only from learner-owned persistent baseline
manifestations}}$$

A study that wants a persistent defect **plus** a transient disturbance belongs to
regime I or to a composition extension: the two sources do not enter a P trigger
together. This is what makes provenance structural rather than a later judgement.

**Manifestation address sets, formalised.** $J_i^L$ is a bit and cannot carry
addresses, while the defect family of §62.9 admits $k > 1$ manifestations in one
episode. The address sets are therefore defined first and the bits are derived from
them:

$$\mathcal A_P^L(\tau) = \begin{cases}
\{\texttt{ProcessCommit}\}, & z_L^{commit} \neq z^{\text{proposal}}\\
\varnothing, & \text{otherwise}
\end{cases}$$

$$\mathcal A_D^L(\tau) = \{t : a_t^L \notin A_D^\ast(s_t, z_t, m_t)\}$$

$$\mathcal A_X^L(\tau) = \{\operatorname{ControllerSite}(s_t, a_t^{cmd}) :
u_t^L \neq a_t^{cmd}\}$$

$$J_i^L = 1[\mathcal A_i^L \neq \varnothing], \qquad
\mathcal M_P^L = \mathcal A_P^L \cup \mathcal A_D^L \cup \mathcal A_X^L$$

$$\boxed{\Gamma_P^\ast = \mathcal A_P^L \;\cup\; \{\texttt{Decision}_t : t \in
\mathcal A_D^L\} \;\cup\; \{\texttt{ControllerSite}_{site} : site \in
\mathcal A_X^L\}}$$

Equivalently $\Gamma_P^\ast = \pi_\Gamma(\mathcal M_P^L)$: the same public ontology
map applied to learner-origin manifestations rather than to $R^{\text{mech}}$. Neither
direction of inference between the regimes is permitted —
$\Gamma_P^\ast$ may not be computed from $R^{\text{mech}}$, and $\Gamma_T^\ast$ may not
be computed from $J^L$. A reader must be able to tell from the symbol alone which
benchmark they are in, so transient repair truth cannot be smuggled into the
persistent benchmark.

Writing the address sets out is what removes the last implementation-time invention:
with only the bits frozen, an implementer would still have to decide whether multiple
manifestations are all kept, only the first, or canonicalised to one.
$\Gamma_P^\ast$ keeps **all** of them — consistent with A71, which established that a
single address is not recoverable from coarse evidence.

### 62.9 Decision defect family: fairness

The defect is defined at the level both architectures must reproduce — the
**induced policy** — not in Q-space and not in patch-space:

$$\mathcal D_D(k, \text{shape}) = \{(x_j, a_j^-)\}_{j=1}^{k}, \qquad
x_j = (s_j, z_j, m_j)$$

$$a_j^- \in A_z(m_j, s_j), \qquad a_j^- \notin A_D^\ast(s_j, z_j, m_j)$$

Requirements, frozen:

* Q-backed and patch-backed stores **install the same extensional defect
  independently**; generating one from the other is forbidden (the discipline A72
  §8.3 already imposes on the locator reference);
* **budget aligns on $N_{\text{addressed decision contexts}}$**, not on scalar
  count — a Q row and a patch entry are not the same number of parameters, so
  freezing scalar equality would tilt the comparison;
* the ledger additionally reports $N_{\text{scalar changed}}$,
  $\sum \lvert\Delta\theta\rvert$, $\max \lvert\Delta\theta\rvert$, so a write with
  more internal parameters cannot quietly buy more edit power;
* the family has at least the two axes $k$ and shape;
* primary reports the whole preregistered family, and
  $\text{effect} \times k$ and $\text{effect} \times \text{shape}$ are mandatory;
* on a sign reversal: $\boxed{\text{report the interaction; declare no universal
  winner}}$. A split result may be a genuine architecture × defect-structure
  interaction, which is a finding, not a failure.

Claiming global superiority from a single defect stratum is forbidden.

**Prototype**: commit `5c0ae15` §4 installs one $(s,z,m,a^-)$ in a Q-backed store
(one corrupted value flips the row's argmax) and, independently, in a patch-backed
store (one override entry). Identical command sequences and identical $J_D^L$.

### 62.10 B2 externality: dependency closure, two views, and a constructor gate

B2's input **types** are frozen now; its formulas are not.

**The hole this closes.** The first draft forbade the metric from *reaching*
$\Gamma^\ast, R^{\text{mech}}, R^{\text{rescue}}, \pi_{\text{credit}}$. But

$$\boxed{\text{the metric not seeing the truth} \;\not\Rightarrow\; \text{the
metric's input was not built from it}}$$

An evaluator can compute $c = \text{Collateral}(\Delta W, \Gamma_P^\ast)$ and place
the already-computed scalar into the view. The metric imports nothing forbidden, and
neither a type boundary nor an AST scan can see it:

$$\boxed{\text{forbidden truth} \to \text{derived feature} \to
\texttt{FutureConsequenceView} \to \text{metric}}$$

This is A59's shape again: the method API leaked nothing, but the support constructor
had already conditioned on feedback.

**Dependency closure, frozen.** It is the *dependencies of the features*, not the
metric's imports, that must be clean:

$$F \in \texttt{FutureConsequenceView} \;\Longrightarrow\;
\mathrm{Deps}(F) \cap \mathcal H_{\text{forbidden}} = \varnothing$$

$$\mathcal H_{\text{forbidden}} = \{Z^{\text{fire}},\ J^L,\ \Gamma_T^\ast,\
\Gamma_P^\ast,\ R^{\text{mech}},\ R^{\text{rescue}},\ \pi_{\text{credit}}\}$$

These may additionally not enter a **per-scene** metric:

$$S_{T,\pm},\quad S_{P,\pm},\quad world\_id,\quad block\_id$$

$$\boxed{\text{the selector may use truth to choose the report table; the metric may
not learn which table it is in}}$$

A scene may be routed into a stratum outside the metric. Once it enters, the metric
must not be able to tell whether it is P, mixed, or Decision-truth — otherwise the
stratification of §62.5 leaks back in as a feature.

**Two views, not one.** "What was written" and "what happened next" must not travel
in the same object, or the first cannot be checked against the second.

1. $\texttt{FutureConsequenceView}$ — only genuinely external future rollout
   information:

   $$\boxed{\texttt{FutureConsequenceView} = \{\text{future rewards},\
   \text{outcomes},\ \text{trajectories},\ \text{actions/observations}\}}$$

   plus the ordinary time indices needed to compute them. **Its constructor must
   itself be truth-blind** — that is the fourth gate layer below.

2. $\texttt{UpdateLedger}$ — cost accounting, **not** an external criterion:

   $$N_{\text{addresses}},\quad N_{\text{scalar}},\quad
   \textstyle\sum\lvert\Delta\theta\rvert,\quad \max\lvert\Delta\theta\rvert,\quad
   \text{pre/post learner-state fingerprints}$$

**`CrossUnitCollateral` is not automatically a B2 primary.** If its definition needs
$\Gamma^\ast$, it cannot be used to adjudicate $\Gamma$ externally: that is
self-justification, the same error A70 and A74 were voided for. It may be a B2 primary
only if it rests on future **behavioural spillover**, or on pure parameter-diffusion /
write-quality measures; otherwise it is a secondary diagnostic, and its dependency must
be stated where it is used rather than inherited from the name.

**Gate layers, now four.**

$$\text{type boundary} \;+\; \text{AST/import allowlist} \;+\;
\text{constructor-flow} \;+\; \text{mutation power}$$

$$\boxed{\texttt{FutureConsequenceViewBuilder} \text{ itself cannot access forbidden
truth}}$$

and the mutation that proves it: fabricate

$$fake\_feature = 1[\texttt{Decision}_t \in \Gamma_P^\ast]$$

and attempt to place it in the view. **The gate must kill it.** Without that mutation
the check would demonstrate only that the *metric* does not import truth, not that the
whole $\text{truth} \to \text{metric input}$ path is closed.

### 62.11 Two authorised kernel semantic extensions (specified, not implemented)

A75 authorises these **in the rebase**, and implements neither:

1. a new ordinary learner baseline **$C_P^L$ read path**, so that a non-evaluator
   commit mapping can exist at all. Priority becomes
   $$do(z{=}z') > do(C_P{=}\text{identity}) > Z_P > C_P^L(z^{\text{proposal}})$$
   with healthy initialisation $C_P^L = \mathrm{id}$. Note `option_fault` ($Z_P$) and
   both `do` nodes are *evaluator* channels today; none of them is a baseline.
2. a **contract check on learner-owned $C_X^L$ output** ($u \in A_z$), while transient
   $Z_X$/$Z_E$ keep the unchecked fault privilege (§62.3).

**Backward-compatibility obligation**, frozen:

$$\boxed{\text{new learner state absent or healthy} \;\Rightarrow\; \text{V0.1R/V0.2R
observable semantics identical}}$$

A75 may not change the world of a closed version. The mechanism that enforces this is
a regression: with the new channels absent, the old rollouts and the frozen support
digest must be reproduced exactly.

### 62.12 Deliberately left open — B1 is not decided here

A75 selects **no** update primitive and **no** architecture. The sets below are
**candidate ranges, not frozen V0.3R arms**: a later document must not describe them
as "the V0.3R arms are frozen", because nothing here ranks or prunes them.
Specifically open:

* **$D$**: $\{D_0 = \text{NoWrite},\ D_{patch}: P_D^L(s,z,m) \mapsto a,\
  D_Q: Q_D^L(s,z,m,a)\}$;
* **$P$**: $\{P_0 = \text{NoWrite},\ P_{id}: C_P^L(z^{\text{proposal}}) \leftarrow
  z^{\text{proposal}}\}$. Mapping $z^{\text{proposal}} \mapsto z'$ is **not** an
  admissible ProcessCommit learning update: that is strategy selection, and it
  re-imports rescue into credit;
* **$X$**: $\{X_0 = \text{NoWrite},\ X_{id}: C_X^L(\text{site}) \leftarrow a^{cmd}\}$.
  $X_{id}$ is **stricter than** criterion 7 requires, deliberately: because
  $Z_X^{\text{fire}}$ is a behavioural predicate, a contract-preserving write with
  $u \neq a^{cmd}$ would make the future episode register a cause the learner itself
  created. Under criterion 7 that is permitted, so choosing identity is a B1 decision
  and is recorded as one;
* the update laws themselves (`NegativeFactual`, `PositiveAlternative`, `Contrastive`,
  `CFTarget`), and which of them are learner-feasible versus evaluator-assisted
  ceilings;
* every B2 formula (`HarmRate`, $\Delta G$, `RecoveryFraction`, and the
  $NOT\_EVALUABLE$ rule when $G_{\texttt{OracleRestore}} = G_{\text{NoWrite}}$,
  which must be reported as `NOT_EVALUABLE` rather than hard-set to 0 or 1);
* the $OracleRestore$ definition, recorded as: restore **the architecture's own
  persistent referent** to its known healthy reference state — *not* "make
  $R^{\text{mech}}$ permanent", which would re-merge the two objects.

Note the X-node asymmetry, recorded so it is not mistaken for a failure later: under
regime P a correct $C_X^L$ write **coincides in content** with the mechanism repair,
so the first invariant does less work there. **X is not V0.3R's most discriminating
node**; it is a semantic sanity case, and P's discriminating power concentrates in
$D$ (and $P$).

### 62.13 Verification tiers

$$\texttt{pytest} = \text{fast semantic regression}, \qquad
\texttt{gate scripts} = \text{exhaustive scientific verification}$$

The exhaustive scans (576 / 893 / 1,038,960) stay in gate scripts. `pytest` gains, at
minimum: $C_P^L$ priority and read path; the $C_X^L$ contract check; the $J_D^L$ tie
case; a Q/patch same-defect fixture; and **absence/healthy learner state reproduces
the old rollout**.

### 62.14 What this amendment does not do

* it is a **frozen specification** (§62 status line), closed over three review rounds:
  the shared $S_+/S_0$, the interpretive provenance rule, the `manifested addresses`
  placeholder and the two $Z$-provenance errors were corrected in the second, and
  §62.10's derived-feature laundering hole — a metric whose input was built from
  forbidden truth while importing none of it — in the third. Further change requires a
  new amendment, not an in-place rewrite;
* it does not change $Z^{\text{fire}}$, $R^{\text{mech}}$, $R^{\text{rescue}}$,
  $\Gamma_T^\ast$, or any V0.1R/V0.2R observable;
* it does not implement the two kernel extensions of §62.11;
* it does not select a B1 primitive, an architecture, or a B2 formula;
* it does not resynchronize `08-V03R.md`, which remains the next artifact to rebase;
* it aims to leave no follow-up amendment owed: §62.7's source-separated
  intermediates, §62.8's address sets and regime source rule, §62.5's regime-specific
  strata, and §62.10's dependency closure plus constructor-flow gate are the places
  where an implementation would otherwise have invented source, address, truth,
  stratum or metric-input semantics at the point of coding, and all are fixed here
  rather than deferred.

## 63. A76 — V0.3R B1 update-law contract

**Status: frozen — specification only.** B1 is specified here and implemented nowhere:
no `kernel.py` change, no store, no run. A75 (§62) owns *where a write is legal*; this
section owns only

$$\boxed{\text{given a legal persistent write address, what update operation is applied?}}$$

$$W^{\text{update}} \longrightarrow \Delta W$$

Attribution, target selection and B2 are **out of scope** and must not reappear here.
The review closed over three rounds: the first draft's unreachability proof for the
$a^+$ guard was **withdrawn and replaced by measurement** (§63.3), the counterfactual
was rewritten as a full-episode replay with a prefix invariant (§63.4), A75's global
`OracleRestore` was moved out of the matrix in favour of a locality-matched
`LocalOracleRestore` (§63.8), and the credit-unit→store-key map became the explicit
$\rho_A$ resolver (§63.10); the second renamed the address-level status so as not to
collide with A63's `NOT_EVALUABLE` (§63.3); and the third made `APPLIED`
architecture-neutral — a **store** change rather than a scalar write — pinned the four
status definitions, made `PROTOCOL_ERROR` a fail-stop excluded from B2 scoring, and
fixed statuses as per-addressed-context.

**The freeze dates from this revision.** It was briefly marked frozen one commit
earlier, while the `APPLIED` definition was still open; that was premature, and rather
than paper over it the freeze is dated here. **Any further change to this section
requires a new amendment; it is not to be rewritten in place.**

### 63.1 Information tiers, frozen

| tier | permitted information | status |
|---|---|---|
| $L_0$ | **factual-only**: the credited address, the learner's own store, the factual action/command, the factual **suffix** return | **learner-feasible** |
| $L_1$ | $L_0$ + verified local corrective content ($a^+$, or $z^{\text{proposal}}$) | **target-assisted**; not claimable as learner-feasible |
| $L_2$ | $L_1$ + the local counterfactual return $G_t^{CF}$ | **evaluator-assisted counterfactual tier** |
| $L_3$ | the architecture's own complete healthy persistent reference state | **constructional Oracle ceiling** |

$$\boxed{P_{id} \notin L_0}$$

$z^{\text{proposal}}$ is **not** in the factual rows
($\text{rows} = (x,y,t,\kappa,\phi,z,m,a^{cmd},a^{realized},reward)$ carries
$z^{\text{in-force}}$ only; A55's proposal audit exists precisely because of that), so
$P_{id}$ is an $L_1$ assisted target. A76 does not smuggle the capability in. Likewise
$a^+$ comes from an evaluator-side adapter; how an ordinary learner would *find* it is
V0.4R's selection problem.

### 63.2 Decision targets are local return-to-go, not episode return

For a credited decision context $x_t = (s_t, z_t, m_t)$ with factual command
$a_t^F = a_t^{cmd}$:

$$\boxed{G_t^F = \sum_{j=t}^{T_F - 1} r_j^F}$$

the sum of `StepResult.reward` from **action-step $t$ to the end of that factual
episode** — not the return from $t = 0$.

$$\boxed{\text{primary B1 is reward mode A, undiscounted, frozen step cost included}}$$

Mode B is excluded from this version; using it requires re-establishing the reference
scale. **Why the suffix and not the episode return**: the exact reference stores an
undiscounted return-to-go ($\texttt{row}[a] = \texttt{res.reward} + v[\text{next}]$,
`dp.py`), so $G_t^F$ is on the same scale as the values it is written into. A
whole-episode return would not be, which is the same defect the `+1` audit found.

### 63.3 The $a^+$ adapter, and a guard that is LIVE

B1 does not select its own alternative. One **architecture-blind** adapter supplies it:

$$\boxed{a_t^+ = \min\left(A_D^\ast(s_t, z_t, m_t) \setminus \{a_t^F\}\right)},
\qquad A_D^\ast = \arg\max_{a \in A_z(m,s)} Q_D^\ast(s, z, m, a)$$

The tie-break is the frozen one ("lowest action index"). Every compatible arm uses
**the same** $a_t^+$: never one for patch and another for $Q$.

**Reachability, measured — and the first draft's proof is withdrawn.** A76 originally
argued this guard unreachable from the canonical D domain, on the grounds that the
domain excludes the tie-broken `best_action`. **That argument does not hold.** The
domain is generated on the **healthy** trace (`fault_grammar.legal_fault_domains` walks
an unmasked rollout), so

$$a_D \neq \pi_D^\ast(x_{\text{generation}}) \quad\not\Rightarrow\quad
a_D \neq \text{unique optimum at } x_{\text{factual}}$$

because in a co-fault world a P fault changes $z^{\text{in-force}}$, earlier X/E faults
change the path, and $m$ follows the path. The generation context and the realized
context are *different contexts*, and the draft conflated them.

**Measured** (`_diag_a76_aplus_guard.py`, `a76_aplus_guard_reachability.json`) by
reading the **realized** pre-action context at every decision-credited address on the
frozen support:

| quantity | value |
|---|---|
| decision-credited addresses ($\Gamma_T^\ast \ni \texttt{Decision}_t$) | 431,280 |
| $a^F \notin A_D^\ast$ at the realized context | 388,800 |
| $a^F$ tied-optimal there | 38,880 |
| **$a^F$ the unique optimum — EMPTY alternative set** | **3,600** |

$$\boxed{N_{\text{empty-alt}} = 3{,}600 \neq 0}$$

The decomposition is the finding: the empty cases occur **only under a co-fault** —
`D+E` 1,440 of 60,480 (2.38%) and `X+D` 2,160 of 45,360 (4.76%) — and **never** under
`D` alone (0 of 127,440). That is exactly the mechanism above: the co-fault moves the
realized context until the injected decision parameter becomes uniquely optimal there.
Since it is established by enumeration and not by a structural proof, this is an
**exhaustive support invariant**, and it must be re-measured if the D domain or the
support changes.

**The guard is live, so the address carries a status — but not `NOT_EVALUABLE`.**

$$\boxed{a^+ \text{ absent} \;\Rightarrow\;
\begin{cases}\texttt{status} = \texttt{NO\_VALID\_ALTERNATIVE}\\
\Delta W = 0\\
\text{the scene remains in the population}\end{cases}}$$

$\texttt{NOT\_EVALUABLE}$ already means something else and must not be reused here. A63
(§50) freezes it for a **metric or cause with no evaluable class**, which is *dropped
from the macro denominator* — the opposite of what is needed at a
`NO_VALID_ALTERNATIVE` address, where the future consequence stays perfectly evaluable
and the scene must **not** be dropped. A75 §62.12 already uses `NOT_EVALUABLE` in that
A63 sense, for the `RecoveryFraction` denominator, so reusing it at the address level
would collide **inside the same document**.

**Ledger status taxonomy, frozen.** Three different ways of "no write happened" must
not be conflated:

$$\boxed{\{\texttt{APPLIED},\ \texttt{EVALUABLE\_NOOP},\
\texttt{NO\_VALID\_ALTERNATIVE},\ \texttt{PROTOCOL\_ERROR}\}}$$

| status | meaning |
|---|---|
| `APPLIED` | a well-typed operation committed and persistent learner state **changed** at at least one credited store address |
| `EVALUABLE_NOOP` | the operation was valid and defined, but the pre/post store is **identical** |
| `NO_VALID_ALTERNATIVE` | $a^+$ is required but absent, so no write was planned |
| `PROTOCOL_ERROR` | an invariant failed and the transaction was aborted |

$$\boxed{\texttt{APPLIED} \text{ is architecture-neutral: store CHANGED, not scalars
written}}$$

An earlier draft defined `APPLIED` as "wrote at least one scalar". That is wrong for
three of the four architectures, and §63.6 says so: a patch store is value-free, so
`SetAlternative` writes a categorical action mapping, $X_{id}$ writes a controller
action mapping, $P_{id}$ writes an option mapping, and `DeleteFactualPatch` **removes**
an entry. Under the scalar wording none of them could ever be `APPLIED` while all of
them genuinely change learner state.

$$N_{\text{scalar}} \text{ is } \texttt{UpdateLedger} \text{ accounting only and may
not determine a status}$$

$$\boxed{\texttt{PROTOCOL\_ERROR} \text{ is NOT a scientific no-write outcome and must
not enter B2 scoring}}$$

It is a **fail-stop**: it invalidates that run rather than being recorded as
$\Delta W = 0$ for an arm. Otherwise a genuine prefix-equality (§63.4) or atomicity
(§63.10) failure could later be tabulated as "this method chose not to write".

**Statuses are per addressed store context.** If a P scene credits several decision
contexts and one address is `NO_VALID_ALTERNATIVE`, the other legitimate addresses keep
their own statuses; an unavailable address does **not** cancel them. "No partial
application" means a law may not **degenerate at the same address** — above all
`DualReturnWrite` must not commit only its factual half — not that one unavailable
address voids the whole scene. Every write that *can* be formed is still computed from
the same pre-update snapshot and committed atomically.

**Address-level rules.**

* affected: the $a^+$-dependent laws only — `SetAlternative`,
  `CounterfactualReturnWrite`, `DualReturnWrite`. `FactualReturnWrite` and
  `DeleteFactualPatch` do not read $a^+$ and are unaffected;
* at such an address the law performs **no write at all**. Partial application is
  prohibited: a half-committed `DualReturnWrite` would violate §63.10's atomicity, and
  writing only the factual entry would silently turn the arm into `FactualReturnWrite`
  at exactly those addresses;
* it still counts as an **addressed context** whose store is unchanged, so the budget of
  §63.10 is unaffected;
* the **scene stays in the population**. Excluding it would be selection bias, and a
  systematic one: the empty-alt addresses *are* co-fault addresses, so dropping them
  would silently delete the composition cases A75 §62.9 exists to validate;
* the `NO_VALID_ALTERNATIVE` count and fraction are reported **per arm and per fire
  pattern**, because the rate is pattern-dependent (0% for `D` alone, 2.38% and 4.76%
  for the two co-fault patterns) and an aggregate would hide a co-fault-specific effect.

### 63.4 The counterfactual target

$$\boxed{G_t^{CF}(a_t^+) = \sum_{j=t}^{T_{CF}-1} r_j^{CF}}$$

**The counterfactual is produced by a FULL episode replay, not by a suffix rollout.**
The first draft said "a rollout that starts from the same pre-action
$(s_t,z_t,m_t)$", which is mathematically the same quantity but is an implementation
hazard: the canonical `rollout()` starts at the episode origin, so a literal reading
invites a `rollout_from(s_t,z_t,m_t)` — a second, suffix-only simulator, which is
exactly the A16/A19 failure mode.

$$\boxed{\text{replay the whole episode from the same initial conditions, adding only }
do(d_t = a_t^+) }$$

holding fixed the same latent world, the same exogenous tape, the same **pre-update**
learner state, and every other fault assignment. $do(d_t)$ is an existing kernel
primitive with the highest priority, so it overrides any $Z_D$.

The suffix is then **extracted** from that complete trace:

$$G_t^{CF} = \sum_{j=t}^{T_{CF}-1} r_j^{CF}$$

and the extraction carries a mechanical invariant:

$$\boxed{\text{trace}^{CF}_{0:t-1} = \text{trace}^{F}_{0:t-1}
\quad\text{else } \texttt{PROTOCOL\_ERROR} \text{ (§63.3)}}$$

The two traces must agree on everything before the intervention — if they differ, the
counterfactual is not counterfactual to *this* episode and the number is meaningless.
This is what makes $G_t^F$ and $G_t^{CF}$ comparable: both are suffix returns of
traces produced by the **one** kernel simulator, differing only in the single $do$ at
step $t$, so they are on the same reward / step-cost scale **by construction** rather
than by rescaling a constant.

### 63.5 Q-backed laws

**$L_0$ — `FactualReturnWrite`** (replaces `NegativeFactual` / `NegativeOnly`):

$$\boxed{Q_D^L(x_t, a_t^F) \leftarrow G_t^F}$$

Primary uses a **full backup** ($\alpha = 1$), because B1 studies target/write
semantics; adding an arbitrary $\alpha$ would introduce a second, unstudied question.

$$\boxed{\alpha \text{ may be used for a secondary sensitivity study, never to pick a
winner or to rescue a primary result}}$$

$$\boxed{\texttt{the } -1 \texttt{ constant is retired}}$$

The update is not necessarily "negative": it moves the factual entry toward the return
that was actually observed.

**$L_1$ — no scalar law exists.**

$$\boxed{D_Q \times L_1 : \text{no value-preserving update law}}$$

Knowing $a_t^+$ **without its value** gives no return-calibrated scalar target for
$Q_D^L(x_t, a_t^+)$. `PositiveAlternative` is **retired**, and specifically **not**
rescaled to $\approx 0.98$: a global extremum is not the value at a credited address,
so that substitution would merely replace one constant for another.

$$\boxed{\text{the law is information-deficient under the current } Q\text{-return
semantics}}$$

A pairwise-preference learner would be a different store semantics, not this
$Q_D^L$.

**$L_2$ — `CounterfactualReturnWrite`** (replaces `CFTarget`):

$$\boxed{Q_D^L(x_t, a_t^+) \leftarrow G_t^{CF}(a_t^+)}$$

**$L_2$ — `DualReturnWrite`** (replaces `Contrastive`'s $(-1, +1)$):

$$\boxed{Q_D^L(x_t, a_t^F) \leftarrow G_t^F, \qquad
Q_D^L(x_t, a_t^+) \leftarrow G_t^{CF}(a_t^+)}$$

Both targets are computed from the **same pre-update snapshot** and committed
atomically. Writing the factual entry first and letting the second target read the
modified store is **prohibited**. This is

$$\boxed{\text{two scalar writes, one addressed decision context}}$$

### 63.6 Patch-backed laws

$L_0$ — **`DeleteFactualPatch`**, a **total** operation:

$$\boxed{P_D^L \leftarrow P_D^L \setminus \{x_t\}}$$

If no patch exists at that address, $\Delta W = 0$ and the ledger records
`EVALUABLE_NOOP` (§63.3). It must **not** be recorded as an evaluability failure, or the
patchless cases — which in T are all of them — would be selectively excluded.

$L_1$ — **`SetAlternative`**:

$$\boxed{P_D^L[x_t] \leftarrow a_t^+}$$

overwriting an existing patch or creating one are both legal.

**No independent patch `Contrastive`.** $\text{Delete}(x_t)$ followed by
$\text{Set}(x_t, a^+)$ leaves the same final state as $\text{Set}(x_t, a^+)$ alone, so

$$\boxed{\text{patch Contrastive is algebraically redundant}}$$

and is not a separate treatment.

$L_2$ — **all value targets are ill-typed** on a value-free store:

$$\boxed{CFTarget,\ FactualReturnWrite,\ DualReturnWrite \text{ do not act on a patch
store}}$$

The general rule, of which the $D_{patch}$ row is one instance: **any law that targets
a *value* is ill-typed on a store with no scalar.**

### 63.7 $X$ and $P$: no invented complexity

$$X_0 = \text{NoWrite}, \qquad
\boxed{X_{id} : C_X^L(\text{site}) \leftarrow a^{cmd}}$$

$X_{id}$ is $L_0$: $a^{cmd}$ is factual information, already in the rows. It remains
**stricter than A75's criterion 7**, which only requires the output to stay inside
$A_z$; $X_{id}$ restores identity outright.

$$P_0 = \text{NoWrite}, \qquad
\boxed{P_{id} : C_P^L(z^{\text{proposal}}) \leftarrow z^{\text{proposal}}}$$

$P_{id}$ is $L_1$, **not** $L_0$ (§63.1). And

$$z^{\text{proposal}} \mapsto z' \quad\text{stays prohibited: strategy selection and
rescue, not a ProcessCommit learning update}$$

Neither node gets Negative/Positive/Contrastive variants: the persistent state is a
discrete map with a known healthy reference, so identity restoration is already the
natural typed operation. For $X$ in regime P, coinciding in content with the mechanism
repair is **expected** (A75 §62.12) and is not a reason to complicate it.

### 63.8 Two oracles: the global ceiling is outside the matrix

The first draft put A75's whole-referent `OracleRestore` into the B1 matrix. That
**contradicts address locality** (§63.10): if a P store holds other persistent defects
that this trigger did not manifest and did not credit, a whole-store restore repairs
them too, so

$$\boxed{\texttt{OracleRestore} \not\subseteq \text{credited addresses} \quad
\text{can hold}}$$

The B1 ceiling would then enjoy a write scope no ordinary primitive has, and any
recovery fraction computed against it would credit the arm for repairs it was never
allowed to make.

A75 is frozen, so its whole-referent `OracleRestore` is kept as what it is:

| object | scope | role |
|---|---|---|
| `OracleRestore` (A75 §62.12) | the architecture's **complete** persistent referent | **global constructional diagnostic ceiling**; **outside** the B1 matrix |
| $\texttt{LocalOracleRestore}$ (here) | **only** the credited B1 addresses | $L_3$, **inside** the B1 matrix |

$$\boxed{\texttt{LocalOracleRestore} \in L_3 \text{ in the B1 matrix}}$$

per architecture:

$$D_Q:\quad Q_D^L(x_t, \cdot) \leftarrow Q_D^\ast(x_t, \cdot) \quad
\text{(the credited context's row only)}$$

$$D_{patch}:\quad P_D^L \leftarrow P_D^L \setminus \rho_D(\texttt{Decision}_t)$$

$$X:\quad C_X^L(\rho_X(\texttt{ControllerSite})) \leftarrow a^{cmd}$$

$$P:\quad C_P^L(\rho_P(\texttt{ProcessCommit}, z^{\text{proposal}})) \leftarrow
z^{\text{proposal}}$$

Both are $L_3$ in information terms — each needs the architecture's healthy reference —
but they differ in **scope**, and scope is what locality constrains. Which one B2 uses
as its denominator is a **B2** decision and is deliberately not settled here.

**Aliases, not new treatments.** Only $D_Q$'s local oracle is a genuinely new
operation. On the other three architectures it coincides with a lower-tier law applied
at the credited address:

$$\texttt{LocalOracleRestore} = \texttt{DeleteFactualPatch} \ \text{on}\ D_{patch},
\qquad = X_{id}\ \text{on}\ X, \qquad = P_{id}\ \text{on}\ P$$

$$\boxed{\text{these aliases are NOT counted as new independent treatments}}$$

A tier is an **information envelope**, not a requirement that each level introduce a new
algorithm — `NoWrite` likewise repeats at every tier. Writing the aliases out is what
stops the same operation being counted twice when the arm list is assembled.

As in A75, the ledger counts only addresses and scalars that actually changed, so a
restore that touches nothing already-healthy is not billed as an edit.

### 63.9 The compatibility matrix, frozen

| tier | $D_{patch}$ | $D_Q$ | $X$ | $P$ |
|---|---|---|---|---|
| reference | `NoWrite` | `NoWrite` | `NoWrite` | `NoWrite` |
| $L_0$ factual-only | `DeleteFactualPatch` | `FactualReturnWrite` | $X_{id}$ | — |
| $L_1$ corrective content | `SetAlternative` | **— no scalar law** | — | $P_{id}$ |
| $L_2$ counterfactual return | **ill-typed** | `CounterfactualReturnWrite`, `DualReturnWrite` | — | — |
| $L_3$ healthy reference | `LocalOracleRestore` | `LocalOracleRestore` | $\texttt{LocalOracleRestore}$ | $\texttt{LocalOracleRestore}$ |

`NoWrite` is available at every tier as the same-tier reference, simply ignoring the
extra information. The matrix is **typed compatibility, not a Cartesian product**: a
full product would manufacture arms that are ill-typed or information-deficient, and
their scores would be artefacts of the pairing rather than of the law.

The $L_3$ row is the **locality-matched** oracle. A75's whole-referent `OracleRestore`
is deliberately **outside** this table (§63.8): it has a write scope no ordinary
primitive has, so it is a global diagnostic ceiling rather than a matrix cell.

### 63.10 Three execution invariants

$$\boxed{\text{1. regime-blind: a B1 primitive may not receive } T/P,\ S_{r,\pm},\
\Gamma^\ast}$$

T/P decide scene generation, truth provenance, and which B2 table reports the result —
never the primitive's behaviour. The same primitive must use the same implementation in
both regimes; it may read its **own store**, but may not be told which regime it is in.
This is the same discipline as A75's "the metric may not know which table it is in".

$$\boxed{\text{2. address locality: } \text{WriteSet}(p) \subseteq
\rho_A\bigl(\Gamma_{r,W}^\ast, \tau, \text{allowed assisted inputs}\bigr)}$$

B1 may not write an address that was not credited, or credit assignment would be redone
inside an update-law experiment.

**The two sides of that inclusion are not the same type.** A credit unit is not a store
key, so the map between them is frozen explicitly rather than left to implementation:

$$\boxed{\rho_A : \text{credit unit} \times \text{run} \times \text{allowed assisted
inputs} \to \text{store address}}$$

$$\rho_D(\texttt{Decision}_t) = (s_t, z_t, m_t)$$

$$\rho_X(\texttt{ControllerSite}) = \text{the site handle } (s_t, a^{cmd}_t)$$

$$\rho_P(\texttt{ProcessCommit},\ z^{\text{proposal}}) = z^{\text{proposal}}$$

$\rho_P$ is the one that needs an **assisted input**, which is precisely why
$P_{id} \in L_1$ (§63.1) and not $L_0$: the key cannot be computed from the factual rows
alone. Without $\rho_A$ written out, an implementer would have to decide for themselves
how a credit unit becomes a store key — and would get a different answer per
architecture.

$$\boxed{\text{3. snapshot + atomic commit}}$$

All targets are computed from the pre-update trigger state and all writes are committed
**simultaneously**; no target may observe another's write, and no result may depend on
iteration or hash order.

For Decision, the budget is

$$\boxed{B_{\text{addr}} = N_{\text{credited manifested decision contexts}}}$$

at most one site-level update per credited $(s,z,m)$; `DualReturnWrite` touching two
entries still counts as **one** addressed context, with the ledger reporting
$N_{\text{scalar}}$, $\sum\lvert\Delta\theta\rvert$ and $\max\lvert\Delta\theta\rvert$
separately (A75 §62.9).

### 63.11 Retirements

* the $-1$ "failure value" constant — replaced by $G_t^F$;
* the $+1$ target — retired outright, **not** rescaled to a global extremum;
* `PositiveAlternative` — information-deficient at $L_1$ on a scalar store;
* `Contrastive` as $(-1, +1)$ — replaced by `DualReturnWrite` on a common scale;
* `NegativeOnly` / `NegativeFactual` — renamed `FactualReturnWrite`, because the
  update is a return correction, not necessarily a negative one.

### 63.12 What this amendment does not do

* it implements nothing. The two nodes are **not** in the same state, and A75 §62.4
  already records the difference: $P_{id}$ has **no** ordinary baseline $C_P^L$ channel
  and **no** store, so it has no referent at all; whereas $X_{id}$ **already** has the
  baseline read channel (`controller`), a persistent caller-owned mapping, and the
  address `ControllerSite(s, a^{cmd})` — what it lacks is A75's **contract check** on
  the learner-owned baseline output. The earlier phrasing that both "have no referent
  yet" was wrong for $X$: its referent exists, but the write path is not yet a legal
  V0.3R learner path. **B1 cannot be run before those two extensions land**;
* it does not define any B2 endpoint or formula ($HarmRate$, $\Delta G$,
  `RecoveryFraction` remain open). **Which** $L_3$ object serves as their denominator —
  the locality-matched `LocalOracleRestore` of §63.9 or A75's global `OracleRestore` —
  is a B2 decision and is deliberately not settled here;
* it does not fix $\alpha$ beyond the primary full-backup choice, and forbids using
  $\alpha$ to select a winner;
* it does not select a winner among the matrix's cells, and does not reduce the
  candidate range to a declared set of V0.3R arms;
* it is a **draft**: the B1 review has not closed, and this section must not be cited
  as frozen until it has.

## 65. A77 — the $D_Q$ row: information contract, $Q$ store, and the scalar ledger

**Status:** **P0 (spec).** **Frozen — specification only. This amendment authorises no
implementation**; the $D_{patch}$ slice stays as built, and each later step is a separate
commit under §65.12's order. Further change requires a new amendment.

This specifies the $D_Q$ row of A76 §63.9, and the one thing that must change before it can
exist: `requires_alternative`, a boolean, is not an information contract.

### 65.1 The tier is a closed opaque enum, declared exactly once

$$\boxed{\texttt{Tier} = \{L_0^{\text{factual}},\ L_1^{\text{corrective}},\
L_2^{\text{counterfactual}},\ L_3^{\text{oracle}}\}}$$

Every law declares **exactly one** tier. The undeclared value is the sentinel `None`, never a
default tier, and the accepted type is tested as `type(tier) is Tier`. An opaque `Enum`, not
an `IntEnum` and not a `bool`: no ordering, no arithmetic, no truthiness inference. `0`,
`True`, `1`, `"L0_factual"` and `Tier` itself are all rejected.

The two failures the boolean caused, and which this replaces: $D_Q$'s $L_0$ arm **needs** an
envelope, and the absent $L_1$ cell of $D_Q$ had the **same encoding** as "$L_0$ needs
nothing".

### 65.2 Delivery is a property of the cell, and the field set is exact

$$\boxed{\text{fields}(\textbf{architecture},\ \ell) = \text{the complete field set handed
to every law in that cell}}$$

$$\boxed{\text{a law receives exactly } \text{fields}(\alpha,\ell)\text{ — no more, no less}}$$

This is keyed by **architecture**, not by a store kind: a value-free store does not imply an
empty $L_0$ field set ($X_{id}$ is $L_0$ and carries the factual $a^{cmd}$), and two
value-free architectures do not share $L_1$ content ($P$'s is $z^{\text{proposal}}$, which is
$\rho_P$'s *key*, and is why $P_{id}$ is $L_1$). Two rows are frozen here:

| architecture | $L_0$ | $L_1$ | $L_2$ | $L_3$ |
|---|---|---|---|---|
| $D_{patch}$ | $\varnothing$ | $\{a^+\}$ | ill-typed | $\varnothing$ |
| $D_Q$ | $\{a_t^F,\ G_t^F\}$ | **no substantive treatment** (§65.3) | $\{a_t^F,\ G_t^F,\ a_t^+,\ G_t^{CF}(a_t^+)\}$ | $\varnothing$ |

$X$ and $P$ keep A76 §63.7 unchanged and get their own rows when implemented.

$$\boxed{F_t := (a_t^F,\ G_t^F)}$$

The action is in the field set because $Q_D^L$'s entry is indexed by it and neither the
credited address nor the envelope otherwise carries it.

**Exactness.** $\operatorname{keys}(\text{envelope}) = \text{fields}(\alpha,\ell)$: an extra
delivered field is a `PROTOCOL_ERROR`, exactly as a non-credited address key is. The
$D_{patch}$ rule is the special case $\text{fields}=\varnothing$.

**Same cell, same envelope.**

$$\boxed{\text{same cell} \Rightarrow \text{same information envelope}}$$

All arms in a cell receive the identical field set, whether or not they read every field, and
**the reference is constructed through the same field construction as the treatments**. The
only difference permitted between arms of one cell is the update law, i.e. the write set. If a
field constructor fails with `PROTOCOL_ERROR`, it fails for the cell — the reference may not
bypass it and emit a normal result, or the treatment and reference populations diverge.

**Where $Q_D^\ast$ may appear.**

$$\boxed{Q_D^\ast \in \text{read path} \cup \text{identity canonicalisation and scalar
accounting} \cup \text{evaluator-side target and reference validation}}$$

and it is delivered to no law. $L_3$ is a statement of **semantic authorisation** ("restore
the credited context to the architecture's healthy referent"), not of what is handed over.

**Typed compatibility, executable.**

$$\boxed{\text{a law that }\textbf{writes a scalar store}\ \wedge\ \ell = L_1
\Longrightarrow \texttt{PROTOCOL\_ERROR}}$$

$L_1$ supplies $a^+$ **without its value**, and on a scalar store every write is a value. The
rule constrains **writing** laws; it does not make `NoWrite` ill-typed.

### 65.3 The same-tier reference is an object

$$\boxed{D_Q\times L_1 \text{ has no substantive compatible treatment } \Rightarrow
\text{ no comparison cell } \Rightarrow \text{ no same-tier reference}}$$

$$\boxed{\texttt{NoWriteRef}(\ell): \text{ one instance per cell with a substantive treatment}}$$

All instances share **the same** no-op plan function object and differ only in the tier they
declare; they are not independent treatments. The $D_{patch}$ slice's registered `NoWrite`
**is** its $\ell = L_0$ instance, so its registry and arm table are unchanged.

The tier is recorded in the **arm/cell descriptor**, not in the per-address receipt and not in
`UpdateLedger.canonical()`.

### 65.4 The $Q$ store and the injected reference view

$$\boxed{\texttt{QAddress}(s,z,m,a)}, \qquad
owner_Q\bigl(\texttt{QAddress}(s,z,m,a)\bigr) = \texttt{DecisionAddress}(s,z,m)$$

| key | role | budgeted |
|---|---|---|
| `DecisionAddress` | credited context, ledger receipt, locality unit | **yes**, $B_{\text{addr}}$ |
| `QAddress` | one scalar entry in that context's row | no — reported as $N_{\text{scalar}}$ |

$$Q_D^L : \texttt{QAddress} \rightharpoonup \mathbb{R}_{\text{finite}}, \qquad
Q^{\text{eff}}(x,a) = \begin{cases} Q_D^L(x,a), & (x,a) \in Q_D^L\\
Q_D^\ast(x,a), & \text{otherwise}\end{cases}$$

$$\boxed{\text{an absent entry means ``no deviation'', not ``the value is } 0\text{''}}$$

$$Q_D^L(x,a) \leftarrow Q_D^\ast(x,a) \;\Longrightarrow\; Q_D^L.\text{pop}(x,a)$$

$$\boxed{\texttt{QReferenceView} \text{ is injected, frozen and read-only};
\quad \text{no store or runner code calls } \texttt{solve\_reference()}}$$

$$a_t^L = \arg\max_{a \in A_z(m,s)} Q^{\text{eff}}(x_t,a) \quad\text{(lowest action index)}$$

$$\boxed{P_D^L \neq \varnothing \ \wedge\ Q_D^L \neq \varnothing \Longrightarrow
\texttt{PROTOCOL\_ERROR}}$$

No priority is defined between the two stores: $D_{patch}$ and $D_Q$ are different
architecture treatments, no legal experiment populates both, and the check is a
**construction-time precondition** evaluated before any episode or read adapter exists.

`fingerprint()` gains a fourth component over `QAddress` rows in which the value is encoded
with `float.hex()`; NaN and infinities are rejected at the transaction boundary.

### 65.5 Domain closure

$$\boxed{\operatorname{dom}(Q_D^L) \subseteq \operatorname{dom}(\texttt{QReferenceView}),
\qquad \text{all values finite}}$$

$$\boxed{\operatorname{dom}(\texttt{QReferenceView}) = \{(x,a) : x \text{ a legal decision
context},\ a \in A_z(m,s)\}}$$

Violations fail stop at the transaction boundary. The reference domain is data-dependent
rather than a closed enum, so the slice passes the transaction an injected **domain oracle**.
An entry outside it would change the fingerprint and clear `healthy` while the read path never
reads it — a persistent defect invisible in behaviour.

**Exhaustive-support invariant.** On the frozen support the reference row set **is** the
admissible-entry set: 13,824 rows, **0** with `set(row) != set(A_z(m,s))` (0 partial, 0
inadmissible extras), row-size histogram $\{1{:}2592, 2{:}1728, 3{:}6480, 4{:}1872, 5{:}1152\}$
identical to the $\lvert A_z(m,s)\rvert$ histogram row for row. This is what makes the domain
contract a checkable predicate. Re-measure if the solver or the grid changes.

### 65.6 $F_t$, $G_t^F$, and the return-to-go fold

$$\boxed{F_t = f\bigl(I^{\text{factual}}_{0:T}\bigr)}$$

$$\boxed{a_t^F = \text{rows}[t].a^{cmd}, \qquad
G_t^F = \sum_{j=t}^{T_F-1} \text{rows}[j].reward}$$

$F_t$ is built from the **learner-visible rows only** — the row tuple of the observation model,
which already carries `a_cmd` and `reward`. It is not built from the evaluator's latent trace.
The two are numerically identical on any consistent run; the same value reached by a different
construction path is a different information contract, so the builder's input type is the rows
and it is handed no trace, mask, reference or world identity.

$$\boxed{G_T = 0, \qquad G_j = r_j + G_{j+1} \quad (j = T-1, \ldots, t)}$$

**The return-to-go uses the frozen reverse Bellman fold, for $G^F$ and $G^{CF}$ alike.**
Left-to-right `sum`, `math.fsum`, and any other reordering are **prohibited**. The reason is
not numerical taste: on a healthy trajectory $G_t^F$ must be **bit-identical** to
$Q_D^\ast(x_t,a_t^F)$, or the write lands next to the reference instead of on it, the
canonicalisation to deletion never fires, and a minimal override appears — clearing `healthy`
and corrupting $N_{\text{scalar}}$, $\Sigma$ and the fingerprint. No epsilon
canonicalisation may be introduced to paper over it; that would add a free parameter.

Measured on the healthy support (48 trajectories $= \kappa \times \varphi \times z_0$, 278
decision addresses): the frozen fold is bit-identical to the DP at **278/278**, while
left-to-right `sum` and `math.fsum` each mismatch **92/278**. `fsum` is the more accurate
summation and still fails: what must match is the DP's *construction path*, not the real
number.

Note, recorded because it is what makes the fold exact: `solve_reference` has two branches,
`row[a] = res.reward` when the step is terminal and `res.reward + v[next]` otherwise, so the
final step's value is $r$ rather than $r + 0$. The two agree bitwise for every finite float
except $-0.0$, and no reward on this support is $-0.0$ (measured: 0 occurrences). The clause
above is normative in the form written; the terminal-branch equivalence is the reason it holds.

$G_t^F$ is never replaced by $Q_D^\ast$: a faulted episode's observed suffix return is the
target, and substituting the reference would make the $L_0$ law an oracle in disguise.

### 65.7 $G_t^{CF}$ is a full-episode replay

$$\text{config}^{CF} = \bigl(\kappa, \tau, \text{mask}, z^{\text{fault}}, z_0,
\text{controller}, C_P^L, \texttt{DecisionReadView}_{pre}, \text{mode A}\bigr)
\equiv \text{config}^{F}$$

$$\boxed{\texttt{DecisionReadView}_{pre} = \text{the complete pre-update decision read path}
}$$

$$\boxed{\text{interventions}^{CF} = \bigl(\text{interventions}^{F} \setminus
\{do(d_t{=}\cdot)\}\bigr) \cup \{do(d_t = a_t^+)\}}$$

$$\boxed{G_t^{CF}(a_t^+) = \sum_{j=t}^{T_{CF}-1} r_j^{CF}}$$

One full-episode replay from $t = 0$ under the factual episode's own configuration, differing
in **exactly one** thing: the decision node at $t$. It is never a suffix simulator.

The decision read path is part of the configuration because the replay visits steps **after**
$t$ and the decision channel there consults the learner's persistent state. Omitting it would
silently revert to the reference provider whenever an existing learner decision defect is met,
violating A76's "all targets from the same pre-update learner state" and measuring $G_t^{CF}$
against a different learner than $G_t^F$. The factual trace is likewise produced under the
frozen pre-update learner state.

Replacement rather than addition is required: two decisions at one $t$ are `MALFORMED`, so
"add" is ill-defined exactly when a factual intervention already sits at $t$.

$$\boxed{\text{rows}\bigl(\text{trace}^{CF}\bigr)[0:t] = \text{rows}\bigl(\text{trace}^{F}\bigr)[0:t]
\quad \text{else } \texttt{PROTOCOL\_ERROR}}$$

over the observation model's row schema, whose rows already carry $z$ and $m$, so this single
comparison subsumes the option-in-force and context equalities. A violation is a fail-stop —
never a $0$ target, which would enter B2 indistinguishable from a legitimate zero
counterfactual return. The invariant is a second witness, not the closure of the
decision-view requirement: it fires only when the divergence lands in the prefix.

The frozen kernel already supports this — `do(d_t)` exists with priority
`do(d_t) > Z_D > command_provider` — so no kernel extension is required.

### 65.8 The $D_Q$ law matrix

| tier | arm | write | plan entries $k$ |
|---|---|---|---|
| reference | `NoWriteRef(ℓ)` | — | 0 |
| $L_0$ | `FactualReturnWrite` | $Q_D^L(x_t,a_t^F) \leftarrow G_t^F$ | 1 |
| $L_1$ | **— none —** | — | — |
| $L_2$ | `CounterfactualReturnWrite` | $Q_D^L(x_t,a_t^+) \leftarrow G_t^{CF}(a_t^+)$ | 1 |
| $L_2$ | `DualReturnWrite` | both, one transaction | 2 |
| $L_3$ | `LocalOracleRestore` | restore the credited row (§65.9) | $0 \le k \le \lvert A_z(m,s)\rvert$ |

$\alpha = 1$ for the $L_0$/$L_2$ arms; the $L_3$ restore is not a backup and has no $\alpha$.
$\alpha < 1$ is a secondary sensitivity study and may never pick a winner or rescue a primary
result.

$$\text{write set}\bigl(\texttt{CounterfactualReturnWrite}\bigr) = \{(x_t,a_t^+)\}, \qquad
\text{write set}\bigl(\texttt{DualReturnWrite}\bigr) = \{(x_t,a_t^F),(x_t,a_t^+)\}$$

$$\boxed{\text{the entry write-sets are in a subset relation; the treatments are not
equivalent and must not be collapsed}}$$

Both targets are computed from the pre-update state and committed atomically; the factual
entry may not be read as part of computing the counterfactual one. At most two entries change
at one addressed context, which carries exactly **one** receipt.

$\lvert\text{independent treatments}\rvert(D_Q) = 4$ — references excluded; the $L_3$ arm is a
genuinely new operation on this architecture (A76 §63.8).

The absence of an $L_1$ arm is enforced by §65.2's scalar-write rule and exact field delivery,
not by the registry's silence.

**Zero revisit.** $\text{update applied} \not\Rightarrow \text{the future trajectory revisits
the updated address}$. Such a run is **kept and scored**. Future exposure is a B2 variable: it
is not one of A75's $S_{r,\pm}$ or $S_{T,\pm}/S_{P,\pm}$ populations, it may not redefine
them, and nothing is removed from a denominator because of it.

### 65.9 owner-based locality, and the row operation

$$\boxed{\forall e \in \text{Plan}(x):\ owner_\alpha(e.\text{address}) = x}, \qquad
\boxed{\{\text{Plan}.\text{address}\} = \text{the credited addresses, each exactly once}}$$

Each credited context has exactly one address-plan, of $k$ entry edits, and exactly **one**
receipt whatever $k$ is; the whole scene's edits enter **one** transaction. On $D_{patch}$
$owner$ is the identity, so the equality "credited = plan = edit" is this rule's special case,
not the rule.

Two plan-shape rules, so that no semantics is invented for states that cannot arise: an
address-plan contains **either** entry edits **or** one row operation, never both; and two
entry edits to the same `QAddress` in one address-plan are a `PROTOCOL_ERROR` (last-write-wins
would make the result depend on edit order).

$$\boxed{L_3:\ \text{delete every override in the credited context's row, returning it to }
Q_D^\ast}$$

The law emits the row-scoped structural operation; the slice lowers it against the pre-state:

$$\texttt{RestoreRow}(x_t) \longrightarrow \{Q_D^L(x_t,a) \leftarrow \bot\}_{a \in A_z(m,s),\
(x_t,a) \in Q_D^L}$$

so $k$ is the number of overrides actually present in that row, every lowered delete changes
the store, and $owner_Q(\texttt{RestoreRow}(x_t)) = x_t$ keeps it under the same locality rule
as an entry edit. Lowering needs no reference: `RestoreRow` returns the row to $Q_D^\ast$ by
construction, never by writing $Q_D^\ast$ values. Reference-valued entries are never stored
explicitly — that is the whole content of the $L_3$ choice, and it is why the delivery is
empty.

### 65.10 The scalar ledger

$$\boxed{\text{scalar\_metrics\_applicable} = \text{the slice's store is scalar-valued}}$$

A property of the slice, not of the outcome: true for every $D_Q$ run including one that
changed nothing.

$$\boxed{\Delta(e)=\begin{cases}
\lvert q_{\text{post}} - q_{\text{pre}}\rvert, & \text{override} \to \text{override}\\
\lvert q_{\text{post}} - Q_D^\ast(e)\rvert, & \bot \to \text{override}\\
\lvert Q_D^\ast(e) - q_{\text{pre}}\rvert, & \text{override} \to \bot
\end{cases}}$$

$$N_{\text{scalar}} = \#\{e : \text{the entry changed}\}, \quad \Sigma = \sum_e \Delta(e),
\quad \text{Max} = \max_e \Delta(e)$$

The delta is measured against the **effective** $Q$, not against an arbitrary zero: in a
sparse store "absent" is $Q_D^\ast(e)$, not $0$.

$$\boxed{N_{\text{scalar}} = 0 \iff \Sigma = 0 \iff fp_{\text{pre}} = fp_{\text{post}}
\qquad\text{within the scalar slice}}$$

This holds because canonicalisation leaves every genuinely changed entry with
$q_{\text{post}} \neq Q_D^\ast(e)$, $q_{\text{pre}} \neq Q_D^\ast(e)$ or
$q_{\text{pre}} \neq q_{\text{post}}$, so $\Delta(e) > 0$; the ledger is thereby a canary for
the canonicalisation rule. Enforced alongside it: $N_{\text{scalar}} = 0 \iff$
`n_changed_addresses` $= 0$; $N_{\text{scalar}} \ge$ `n_changed_addresses`;
$0 \le \text{Max} \le \Sigma$ with $\text{Max} > 0 \iff \Sigma > 0$; and per addressed context
$N_{\text{scalar}} \le 2$ for `DualReturnWrite` and $\le \lvert A_z(m,s)\rvert$ for
`LocalOracleRestore`.

A75 §62.9 stands unrepealed: these numbers are accounting, they may not determine a status,
and `APPLIED` remains "the store changed".

### 65.11 Gate obligations

Each is an obligation on the implementation, with the failure it must be able to detect.

| # | obligation | failure it detects |
|---|---|---|
| G1 | tier is a `Tier` and nothing else | an integer or boolean tier silently accepted |
| G2 | delivery equals `fields(α,ℓ)` exactly | a law handed a field its cell excludes, or an $L_0$ law handed $a_t^+$ |
| G3 | scalar-write law at $L_1$ rejected | `PositiveAlternative` returning under a new name |
| G4 | the $L_0$ arm is unaffected by the $L_2$ constructor | the whole cell built unconditionally |
| G5 | CF prefix equality fails stop | a replay built from the wrong config |
| G6 | empty store reproduces the baseline policy row for row | an invented tie-break in the read path |
| G7 | $\Delta$ against $Q_D^\ast$ for created/deleted entries | a near-reference write reading as a huge edit |
| G8 | $L_3$ writes only the credited row | a widened restore |
| G9 | `DualReturnWrite` is one atomic transaction | a half-committed pair |
| G10 | no $L_1$ $D_Q$ arm is registered or scored | a stub $L_1$ scalar law |
| G11 | `FactualReturnWrite` targets $G_t^F$, not $Q_D^\ast$ | the $L_0$ law becoming an oracle |
| G12 | the $D_{patch}$ suite and its ledger bytes are unchanged by the slice refactor | the refactor moving a patch number |
| G13 | co-residence is a construction-time fail-stop | two stores silently resolved by a priority |
| G14 | the canonicalisation canary holds | an assumed rather than enforced equivalence |
| G15 | the CF config carries `DecisionReadView_pre` | a replay reverting to the reference provider |
| G16 | a non-total reference row fails stop | a `KeyError` escaping the read path |
| G17 | $F_t$'s builder accepts rows only | the $L_0$ builder reading the trace |
| G18 | $L_3$ delivery is empty | reference values delivered to a law |
| G19 | locality is checked through $owner$ | an edit owned by another credited context |
| G20 | the $Q$ domain oracle is enforced at commit | an entry the read path can never read |
| G21 | the reference instances share one plan and do not count as treatments | a reference inflating the arm count |

The return-to-go fold (§65.6) is a G5-class obligation: left-to-right `sum` or `fsum` must be
observably rejected on a healthy trajectory.

### 65.12 What this amendment does not do

* it implements nothing. Every step below is a separate commit, in this order, and no commit
  may mix the refactor with new semantics:

$$\boxed{\text{generic slice refactor only} \rightarrow \text{Q store / read substrate}
\rightarrow L_0\ \texttt{FactualReturnWrite} \rightarrow L_2\ \text{CF builder} + \text{laws}}$$

* the first step is a refactor of **one** implementation of totality, locality, atomicity and
  exact delivery, and its acceptance conditions are: $D_{patch}$ ledger `canonical()` bytes
  unchanged for every arm; the observable preimage digest reproduced exactly; the existing
  interface gates still killable; and no $Q$, $F_t$ or $G^{CF}$ semantics in the commit. The
  later addition of the $Q$ fingerprint component is an encoding change that this condition
  does not govern;
* no B2 endpoint is specified. `HarmRate`, `ΔG`, `RecoveryFraction`, the `NOT_EVALUABLE`
  denominator rule and the exposure variable's schema are B2's, as is the choice of which
  oracle is B2's denominator (A76 §63.8);
* no $X$ or $P$ field row is specified (§65.2);
* no regime I numbers, and no attempt to settle $T/P$ semantics;
* no ledger schema change: the tier lives in the arm descriptor, and moving it or the $Q$
  fingerprint component into the canonical ledger is a versioned schema change of its own;
* no claim about $\Gamma$: $\Gamma^+$ and the truth share one $\pi_{\text{credit}}$, so every
  census measures over-credit under a **fixed** ontology and does not validate it.

---

## 66. A78 — $L_3$ `LocalOracleRestore` on $D_Q$: the fifth implementation step

A77 §65.12 wrote its implementation sequence as

$$\text{generic slice refactor only} \rightarrow \text{Q store / read substrate} \rightarrow
L_0\ \texttt{FactualReturnWrite} \rightarrow L_2\ \text{CF builder} + \text{laws}$$

and A77 states that further change requires a new amendment. All four steps are closed, so the
sequence ends **before** $L_3$: §65.9 fixes $L_3$'s semantics but is not an implementation
authorisation, and reading $L_2$'s closure as one would be proceeding by tacit consent on a
frozen order. This amendment adds that one step, and fixes the boundaries it has to respect.

It is **append-only**: it changes no text of A77, and the earlier steps acquire no new scope
from it.

### 66.1 Authorisation, and its size

$$\boxed{\text{A77's sequence} \rightarrow L_3\ \texttt{LocalOracleRestore}}$$

One step, one commit, no mixing with a refactor or with $L_0$/$L_2$ semantics — the same rule
A77 §65.12 applies to the other four. $L_3$'s semantics are **not** restated here: §65.9's row
operation, its lowering $\texttt{RestoreRow}(x_t) \to \{Q_D^L(x_t,a) \leftarrow \bot\}_{a \in
A_z(m,s),\, (x_t,a) \in Q_D^L}$, $k$ = the overrides actually present, and the empty delivery
$\text{fields}(D_Q,L_3)=\varnothing$ are frozen and unchanged.

### 66.2 The cell has a reference too

$$\boxed{\text{one } \texttt{NoWriteRef}(\ell) \text{ per cell with a substantive treatment (A77 §65.3)}}$$

$L_3$ has one, so the $D_Q$ registry gains **both** its reference and its treatment:

$$D_Q:\quad \texttt{NoWriteRef}(L_0),\ \texttt{FactualReturnWrite},\
\texttt{NoWriteRef}(L_2),\ \texttt{CounterfactualReturnWrite},\ \texttt{DualReturnWrite},\
\boxed{\texttt{NoWriteRef}(L_3)},\ \boxed{\texttt{LocalOracleRestore}}$$

References are not treatments (§65.3), so this gives

$$\boxed{\lvert\text{independent treatments}\rvert(D_Q) = 4}$$

which is the number A76 §63.8 already froze. $D_{patch}$ keeps its 3, and its registry is
untouched.

### 66.3 The B1 law domain is every credited address — for $L_2$ *and* $L_3$

$$\boxed{\text{Population}_{L_2} = \text{Population}_{L_3} = \text{all credited addresses at B1}}$$

An address with no verified $a^+$ is **not** removed from the population: A76 §63.3 records it
as `NO_VALID_ALTERNATIVE` under A76 §63.10's per-addressed-context taxonomy, and it stays an
addressed context. The difference between the tiers is therefore a **status distribution**, not
a domain: on the healthy support $L_2$ has a usable target at 32 of 278 addresses and
`NO_VALID_ALTERNATIVE` at 246, while $L_3$'s row restore is defined at every credited row.

Consequently $L_3$ must **not** be restricted to the addresses that have an $a^+$. Doing that
would make the arm's domain depend on $a^+$ availability, which is exactly the evaluator-side
information its empty cell forbids it to read (§65.2), and it would break the
"empty cell $\Rightarrow$ nothing to read" property that makes $L_3$'s delivery the whole
content of the $L_3$ choice.

B2 may still decide whether the primary comparison is over all addresses, whether an
"$L_2$ target available" stratum is reported alongside it, and whether `RecoveryFraction`'s
denominator is the local or the global oracle (A76 §63.8). None of those may change $L_3$'s B1
law domain, or silently cancel the frozen rule that a `NO_VALID_ALTERNATIVE` address remains in
the population.

### 66.4 What "$L_3$ needs no reference" means, exactly

$$\boxed{\text{no NEW } L_3\text{-specific reference entry point}}$$

§65.9's statement is about the **lowering**: the row returns to $Q_D^\ast$ by deleting overrides,
never by writing $Q_D^\ast$ values, so lowering needs no reference. It does not mean the run has
no reference. §65.10's deleted leg

$$\Delta(e) = \lvert Q_D^\ast(e) - q_{\text{pre}}(e)\rvert$$

still needs the injected view, exactly as it does for $L_0$ and $L_2$. So the $L_3$ path:

* needs no `sol` and no `episode`;
* needs no evaluator-side envelope, and its law and lowering do not read the reference;
* continues to receive the **existing** generic `q_reference` for the transaction boundary and
  the scalar accounting, and must not grow a fourth, $L_3$-specific way of naming one.

### 66.5 The row operation is a B1 object, and the substrate does not learn it

$$\boxed{\text{the B1 } D_Q \text{ owner resolver is total over entry-ops and row-ops}}$$

`learner/store.py::owner_Q` keeps taking a `QAddress` and must **not** import or recognise a
`RestoreRow`; §65.9's equation $owner_Q(\texttt{RestoreRow}(x_t)) = x_t$ is satisfied in the B1
layer that resolves owners for a plan, not by teaching the substrate about an update law. Step
3's separation — the substrate knows the store, not the laws — is not traded away to make an
equation look literal.

### 66.6 Lowering is an explicit pre-commit phase, and the ledger reads its output

$$\boxed{\text{symbolic plans} \rightarrow \text{all row ops lowered against ONE frozen
pre-state} \rightarrow \text{concrete entry edits} \rightarrow \text{ONE transaction}}$$

No alternating lower-one-row/commit/lower-the-next: a scene's row operations all lower against
the same pre-state, and the scene still commits once.

$$\boxed{\text{receipt status, } n_{\text{changed\_addresses}} \text{ and the scalar accounting
are computed from the LOWERED concrete edits}}$$

This is not bookkeeping taste. An `AddressPlan` carrying a row operation and `edits=()` would,
under the entry-only rule, be read as "no edits and no declared status" and reported
`EVALUABLE_NOOP` even though the lowering deleted entries — a ledger that contradicts its own
store, which is the defect class A77 §65.10's equivalences exist to catch.

### 66.7 The $D_Q$ law is an independent implementation

The existing `LocalOracleRestore` on $D_{patch}$ is an **alias** of `DeleteFactualPatch` and
deliberately shares its `plan` function object (A76 §63.6, A77 §65.2); it emits `DECISION`
edits and cannot serve $D_Q$. The $D_Q$ law is therefore a separate implementation that may keep
the display name `LocalOracleRestore`, registered **only** in the $D_Q$ registry:

* the $D_{patch}$ alias class and its `plan` binding are untouched, and its ledger `canonical()`
  bytes and treatment count do not move;
* no law branches on architecture. A law is not handed a slice (A76 §63.1), so "which store am
  I writing" is not a question a law may ask.

### 66.8 Gate obligations

* **row scope**: the arm deletes exactly the overrides in the credited row — no other row, no
  other store, and the fingerprint change is confined to that row;
* **the lowering reads this run's pre-state**: $k$ = the overrides present at pre-state, and a
  row with none lowers to no edits, so the address-plan has no edits and no declared status →
  `EVALUABLE_NOOP` with an empty edit set, still one receipt;
* **idempotence**: $\texttt{RestoreRow}(S) \to \texttt{RestoreRow}(\texttt{RestoreRow}(S))$ has
  $k=0$ and `EVALUABLE_NOOP` on the second run. Its content is precise: the lowering uses the
  **pre-state of its own run** rather than reusing a stale or previously computed lowering;
* **ledger**: $N_{\text{scalar}} = k$, $\Sigma = \sum \lvert Q_D^\ast(e) - q_{\text{pre}}(e)\rvert$,
  $N_{\text{scalar}} \le \lvert A_z(m,s)\rvert$, and §65.10's equivalences hold;
* **the empty cell is asserted, not assumed**: the $L_3$ path runs successfully when handed
  **poison evidence** — placeholders for `rows`, `sol` and `episode` that raise on any access —
  which demonstrates $\boxed{\text{$L_3$ execution does not read evaluator-side envelope
  inputs}}$ while it still reads the generic `q_reference` for the ledger. The two are thereby
  separated by evidence rather than by reading the code;
* **plan shape**: an address-plan carrying both entry edits and a row operation, or two row
  operations, is a `PROTOCOL_ERROR` — the rule §65.9 states and which is unenforceable until the
  row operation exists;
* **$D_{patch}$ untouched**: its registry, its alias identity and its ledger bytes;
* a mutation self-check over all of the above, with the failure reason declared where a gate can
  only fail by not raising.

### 66.9 What this amendment does not do

* it writes no code: the authorisation is this text, and the commit is its record;
* it changes no cell, no $L_0$ and no $L_2$ semantics, and does not touch A77's table;
* it does not restate or widen §65.9;
* it specifies no B2 endpoint, denominator, stratification or regime I number;
* it does not claim $L_3$ closes D6, and authorises nothing after it.

---

## 67. A79 — V0.3R B2: pre-registration of the future-consequence stage

$$\boxed{\text{B2 asks: what did this write do to this learner's future?}}$$

A75 §62.1 froze the subject and the chain; A76 §63 and A77–A78 froze the update-law contract
and the $D_Q$ row. Those answer *what was written*. This amendment pre-registers the stage
that answers *what followed*, and it is a **pre-registration**: it writes no code, collects no
seed, and fixes the design of B2 before any B2 number exists.

**It supersedes `08-V03R.md` on B2.** `08` §3 is the old Block 2, whose arms
(`NegativeOnly`, `PositiveAlternative`, `Contrastive`, `CFTarget`, `ControllerUpdate`,
`NoUpdateWhenExternal`) A76 retired — the $\pm1$ targets as information-deficient, the rest by
the tier-matched matrix — and whose process reading ($do(z = z')$ as mechanism repair) the
frozen reading rejects: mechanism repair is $do(C_P = \mathrm{identity})$, and $do(z=z')$ is
strategy replay. Nothing in `08` §3 governs B2. `08` §2 (Block 1, the offline semantic gate) is
**not** addressed here: this amendment neither endorses nor supersedes it, and the semantic and
identifiability obligations that were already frozen in `03`/`04` are unaffected. Where `08` and
this amendment disagree about B2, this one governs.

### 67.1 The problem B2 states, and the one it refuses to collapse

$$\boxed{\text{Good Update} = \text{FutureBenefit} - \text{UnacceptableCollateral}}$$

— as **two independent dimensions, never a weighted scalar**:

$$\boxed{Y^{\text{future}} = \{\text{FutureUtility},\ \text{Collateral},\ \text{Retention}\}}$$

The arithmetic above is a name for the question, not a scoring rule. A single weighted score
would let a large utility buy any amount of collateral, which is exactly the trade the stage
exists to expose: an arm that improves future behaviour by damaging behaviour it was not
supposed to touch has not been shown to be good, and a linearisation would report it as a
number rather than as the disagreement it is. **No composite primary is permitted.** Transfer is
deferred: it is a secondary dimension at most, and B2 does not become four or five questions.

### 67.2 Regimes are separate populations with separate claims

B2 inherits A75 §62.5's stratification and §62.6's regimes unchanged, and adds only their B2
reading. $T$ and $P$ **may not be pooled into one whole-support primary mean**.

**Regime T — a transient incident, and the question is erroneous internalisation.** The learner
starts healthy and the future is the clean baseline, so

$$\boxed{T\text{'s primary is harm: was a transient failure written into the learner?}}$$

`NoWrite` is the reference, and A75 §62.6's observation stands: because the healthy baseline *is*
the reference ($\pi_D^\ast$, identity controller, faithful commit), NoWrite **weakly dominates**
any write that changes healthy behaviour. A large positive $T$ result is therefore a signal to
re-examine contract preservation, not a result to celebrate. The failure mode B2 must be able to
name is

$$\text{a failure occurred} \;\not\Rightarrow\; \text{the learner had to change}.$$

**Regime P — a persistent learner defect, and the question is recovery that holds.** Here the
defect lives in the persistent state, so

$$\boxed{\text{future rollout is endogenous to } \Delta W}$$

and future episodes must read **the same state that was written**. Pre-computing future
$Z^{\text{fire}}$ or $\Gamma^\ast$ and attaching it to an updated learner is forbidden, and so is
any evaluation that simulates the future separately and reports it back.

### 67.3 FutureUtility: RMST primary, DeficitAUC a mandatory companion

Frozen by reference to `05` §8 rather than restated: the recovery time
$\tau = \inf\{t : V_{t'} \ge 0.95\,V_{\text{pre}} \ \forall t' \in [t, t+K-1]\}$ with $K=3$,
**right-censoring at $T_{\max}$**, and

$$\boxed{\mathrm{RMST}(T_{\max}) \text{ primary} \qquad \mathrm{DeficitAUC} \text{ co-primary, mandatory}}$$

The reason is not preference: averaging a time-to-recover over the seeds that recovered discards
precisely the seeds an ineffective arm produces, which is selection bias in the direction of the
arm being tested. $K=3$ consecutive checkpoints rather than a single crossing keeps an incidental
threshold touch from counting as recovery. Both are integrated over the **real episode index**
using $\mathcal G_{\text{ckpt}}$ (`05` §6.2), whose density is early by design — the grid exists
so that "recovered by 100, first measured at 250" cannot happen.

### 67.4 Collateral: future behavioural spillover, and nothing borrowed from the truth

A75 §62.10's warning is the binding constraint, and it is why this dimension is defined by what
it may **not** depend on:

$$\boxed{\text{the metric not seeing the truth} \;\not\Rightarrow\; \text{the metric's input was not built from it}}$$

**Primary collateral is spillover on future behaviour**: performance loss on future contexts
that are unrelated to the credited site and were performing correctly beforehand,

$$\boxed{\text{BehavioralCollateral} = V_{\text{unaffected,pre}} - V_{\text{unaffected,post}}}$$

The construction of the "unaffected context set" must be **truth-blind**, which is exactly what
A75 §62.10's fourth gate layer enforces: $\texttt{FutureConsequenceViewBuilder}$ itself may not
reach $\mathcal H_{\text{forbidden}}$, and the mutation that proves the gate is live — fabricate
$1[\texttt{Decision}_t \in \Gamma_P^\ast]$ and try to place it in the view — **must be killed**.

**Truth-blind is necessary and not sufficient.** It closes $\Gamma^\ast \to$ input and leaves a
second selection channel open, one that needs no evaluator truth at all:

$$\boxed{\text{post-update outcome} \;\to\; \text{a set chosen because it flatters this arm}}$$

So the set is additionally constrained. For each scene,

$$\boxed{U_{\text{unaffected}} \text{ is built BEFORE any arm executes and before } \Delta W}$$

* the constructor may not read the **law or arm identity**, $\Delta W$, the
  $\texttt{UpdateLedger}$, **post-update outcomes**, or anything in
  $\mathcal H_{\text{forbidden}}$;
* paired arms of one scene use **the same set** — the same constructed object, not two
  constructions that happen to agree;

$$\boxed{\text{truth-blind} \;+\; \text{arm-blind} \;+\; \text{pre-update} \;+\;
\text{one set per scene across paired arms}}$$

The concrete algorithm is a **development-stage decision**, and the rule for making it is frozen
now, on the same pattern as Retention (§67.5): choose on measurement properties — coverage of the
future context space, baseline stability of the pre-update values, interpretability, and
sensitivity to a **synthetic** injected spillover — and

$$\boxed{\text{never on which construction makes the treatment effect largest}}$$

A construction that cannot detect a synthetic spillover it was built to detect is not measurable
evidence whatever the direction of its effect; that is a calibration question, and it is settled
on development seeds.

The quantities that count *how much was written* — $N_{\text{addresses}}$, $N_{\text{scalar}}$,
$\sum\lvert\Delta\theta\rvert$, $\max\lvert\Delta\theta\rvert$, pre/post fingerprints — stay in
$\texttt{UpdateLedger}$ as intervention cost. They are not external criteria:

$$\boxed{\text{writing less} \;\neq\; \text{causing less collateral}}$$

A75 §62.10's ruling on `CrossUnitCollateral` is inherited as written: it may be a B2 primary
**only** if it rests on future behavioural spillover or on pure write-quality measures;
otherwise it is a secondary diagnostic, and its dependency is stated where it is used rather
than inherited from its name.

### 67.5 Retention is a dimension now and a formula later, by a declared rule

Retention is frozen **as a dimension**: an effect that exists for one or two episodes and then
decays is a different finding from one that holds, and pooling them would hide it. Its
operationalisation is **not** frozen here, because unlike RMST there is no already-frozen
statistical argument that selects one form.

**One requirement is frozen, and it is the one that rules forms out:**

$$\boxed{\text{the confirmatory Retention primary must be defined for EVERY seed}}$$

A form conditioned on recovery having happened is not admissible as the confirmatory endpoint.
$\tau$ does not exist for a seed that never recovers, and the natural repair — analyse over the
recovered seeds — reintroduces exactly the bias RMST was chosen to avoid (`05` §8): the worse the
arm, the more of its seeds the condition removes, so the comparison silently narrows towards the
seeds the arm handled well. The candidate set is therefore the forms that are total on seeds:

* $\boxed{\text{Retention}@H}$ — where $H$ is a **fixed absolute horizon measured from the
  update/trigger**, *not* "$H$ episodes after recovery". A fixed horizon is defined for every
  seed, and it is also the form that answers the question Retention is for: does the effect
  persist over a horizon the design chose in advance;
* $\boxed{\text{LateWindowRetention}}$ — the maintained-performance level over a pre-registered
  late window $[H_1, H_2]$, likewise defined for every seed;
* and, **demoted to a conditional descriptive diagnostic**,

$$\text{RetentionFraction} = \frac{\#\{t \ge \tau : V(t) \ge 0.95\,V_{\text{pre}}\}}{\#\{t \ge \tau\}}
\qquad\text{reported only alongside the }\tau\text{-conditioned denominator}$$

The choice among the all-seed forms is made on **development seeds** under `05` §2, and the rule
for making it is frozen now:

$$\boxed{\text{choose on measurement properties — stability, interpretability, redundancy with RMST/DeficitAUC — not on which form makes the effect largest}}$$

The dev stage may add forms to the candidate set; it may not promote a $\tau$-conditioned one to
the confirmatory primary. The choice is frozen with $T$, $N_{\text{eval}}$ and
$\mathcal G_{\text{ckpt}}$, **before** confirmatory seeds, and may not be changed afterwards
(`05` §6.1, §9).

### 67.6 Oracle roles: a matched ceiling and a diagnostic ceiling

$$\boxed{\texttt{LocalOracleRestore} = \text{matrix-matched normalisation ceiling}}$$
$$\boxed{\texttt{GlobalOracleRestore} = \text{diagnostic constructional ceiling only}}$$

Both are reported. The global oracle may **not** be the denominator of a treatment's
`RecoveryFraction`, because it can repair learner state outside this scene's credited addresses
and the ordinary arms cannot: as a denominator it would grant the oracle write permission the
treatments do not have, and normalise every treatment against a scope it was never allowed. This
is a scope-fairness argument and needs no development data — it is decided here, not measured
later. (A76 §63.8's placement of the global oracle **outside** the matrix is unchanged; this
clause fixes only which oracle normalises what.)

### 67.7 Arms are compared within their information tier, and the tiers are not a ranking

Each tier is contrasted against **its own same-tier reference**, per A77 §65.3 and §65.8. The
table below is the **completed $D_Q$ Decision row** — not the whole B2 matrix, which has no $D_Q$
$L_1$ cell and no rows for the stores §67.8 still owes:

| tier | treatments | reference | what it establishes |
|---|---|---|---|
| $L_0$ | `FactualReturnWrite` | `NoWriteRef(L0)` | learner-feasible |
| $L_2$ | `CounterfactualReturnWrite`, `DualReturnWrite` | `NoWriteRef(L2)` | evaluator-assisted counterfactual ceiling |
| $L_3$ | `LocalOracleRestore` | `NoWriteRef(L3)` | constructional oracle ceiling |

Process and Controller inherit A76 §63.9's cell/tier matrix **unchanged** once §67.8's
prerequisites exist — including their own same-tier references and their $L_3$ aliases — and
**A79 defines no treatments for them**. Read as "each tier" over the whole matrix, the table
above would appear to be missing $L_1$ entirely; it is a statement about one completed row.

Curves may be compared across tiers, but the interpretation is fixed in advance:

$$\boxed{L_3 \text{ beating } L_0 \text{ may not be written as "} L_3 \text{ is a better algorithm"}}$$

The tiers hold different information, so a cross-tier difference measures **how much headroom
remains above what the learner can do**, not which method is preferable. $L_0$ is the only tier
that is a candidate method under the learner's own information; $L_2$ and $L_3$ are ceilings.

### 67.8 A prerequisite that must be stated before B2 runs

The persistent substrate exists and the kernel reads it: $P_D^L$, $C_P^L$ and $C_X^L$ are part of
the learner state and the rollout consults $C_P^L$ and $C_X^L$. What is **complete** in
`src/rfl_rebuild/b1/` is the **Decision** path — the $D_{patch}$ slice and the $D_Q$ row through
$L_0$, $L_2$, $L_3$. There are no $P_{id}$/$X_{id}$ update laws.

$$\boxed{\text{``D6 / B1 CLOSED'' means the Decision B1 path, and must not be read as all three stores}}$$

So the Process and Controller B1 alias/write paths are **B2 prerequisites**, needing their own
implementation authorisation in the pattern A78 established. This does not reopen $D_Q$, changes
no frozen B1 semantics, and is not authorised by this amendment.

### 67.9 Statistical protocol: inherited unchanged, with the four quantities kept apart

`05` §1–§10 governs and is not weakened. Specifically: development $N_{\text{dev}} = 32$;
primary confirmatory $N_{\text{confirm}} = 400 = 4 \times 100$; secondary $N = 200 = 2 \times 100$;
paired seeds with common random numbers; at every look both the cumulative $100/200/300/400$ and
the fresh block alone, with **only $N=400$ confirmatory** (`05` §4.1); and the four-way verdict
$L > \Delta_{\min}$ / equivalent / $U < -\Delta_{\min}$ / inconclusive, where a **reversal** is a
change of that verdict and is reportable only with the fresh block's own mean (`05` §4.2).

$$\boxed{N_{\text{seeds}},\ N_{\text{train}},\ N_{\text{eval}},\ \mathcal G_{\text{ckpt}} \text{ are four numbers and are never collapsed into one}}$$

The development stage informs exactly what `05` §2 allows — benchmark headroom, baseline
convergence, $T$, the checkpoint grid, $N_{\text{eval}}$ stability, the Retention form, runtime —
and nothing else. Code and configuration are then locked.

### 67.10 $T$ is frozen from the baseline only, and the prohibition is the point

`05` §6.1 governs:

$$\boxed{T = Q_{0.9}\bigl(T_{\text{conv}}\bigr) \times (1+h), \qquad h = 0.20 \text{ by default}}$$

with $T_{\text{conv}}^{(i)}$ from the baseline arm per development seed, and

$$\boxed{\text{until } T \text{ is frozen and committed, no treatment-arm curve may be plotted, printed, or summarised}}$$

$T$, $\mathcal G_{\text{ckpt}}$, $N_{\text{eval}}$ and the Retention form are frozen **together**.
The rule exists because the alternative is not a variant of this design but a different one:
choosing $T$ where the treatment looks best selects the design at the effect's maximum. In
particular, no $N_{\text{train}}$ may be named in this pre-registration — the number does not
exist yet, and writing a plausible one down now would be exactly the legacy error.

### 67.11 Sequence, and the B2 go/no-go

$$\boxed{\text{smoke} \rightarrow \text{development} \rightarrow \text{lock} \rightarrow \text{confirmatory}}$$

B2's gates, in order:

| gate | condition |
|---|---|
| B1 regression | the five B1 mutation self-checks and the $D_{patch}$ ledger baseline still hold |
| prerequisites | the Process/Controller B1 paths exist, under their own authorisation (§67.8) |
| view contract | A75 §62.10's four layers, including the fabricated-feature mutation, kill a truth-derived feature |
| design freeze | $T$, $\mathcal G_{\text{ckpt}}$, $N_{\text{eval}}$, Retention form, $\Delta_{\min}$ per endpoint, committed before any confirmatory seed |
| smoke | 5 seeds, nothing scientific |
| development | 32 seeds, `05` §2's permitted uses only |

$$\boxed{\text{any gate FAIL} \Longrightarrow \text{no confirmatory B2 seed is collected}}$$

**What V0.3R PASS means, as a conjunction and not a score.** A79 §67.1 forbids collapsing the
outcome space into one number, so the version's verdict may not be one either. The logic is
frozen here; the thresholds are not, because they are instantiated at the dev freeze:

$$\boxed{\text{V0.3R PASS} = \text{FutureUtility benefit} \;\land\; \text{no unacceptable
Collateral} \;\land\; \text{Retention criterion satisfied} \;\land\; \text{T-regime harm
constraint satisfied}}$$

each conjunct being a pre-registered four-way verdict or bound (`05` §4), instantiated after the
dev stage as, for the learner-feasible $L_0$ treatment in $P$: FutureUtility `SUPPORT_A`;
`BehavioralCollateral` within the pre-registered harm bound; the Retention form meeting its
pre-registered persistence / non-inferiority rule; and $T$ showing no erroneous internalisation
beyond its threshold. This is a **conjunction gate, not a weighted sum** — it does not
re-introduce the composite that §67.1 refuses, because it never trades one dimension against
another:

$$\boxed{\text{if the conjuncts cannot hold simultaneously, } V0.3R \neq PASS \text{ and } V0.4R \text{ does not run}}$$

If B2 reaches its confirmatory stage and the tier-matched contrasts are `EQUIVALENT` or
`SUPPORT_B` — that is, the strongest available $L_0$ write does not improve the future over
writing nothing — the conclusion is that **incremental correction of this kind does not improve
learning in this environment**, and the programme redirects to a different update family rather
than to more attribution work. That is the falsification branch A75 anticipated, and it is a
result rather than a failure.

**V0.4R entry condition.** V0.4R begins only when V0.1R, V0.2R and V0.3R have each **passed their
gates**, which is `09-V04R.md` §1 and §6 and is not this amendment's to relax:

$$\boxed{\text{V0.3R's FINAL confirmatory analysis PASSES} \;\Longrightarrow\; \text{V0.4R may begin}}$$

"Final" is the whole of it. `05` §4.1 freezes that only $N = 400$ is confirmatory, so a
diagnostic look at 100, 200 or 300 — however favourable — is not a PASS, cannot open V0.4R, and
cannot be reported as one. `09` §5 makes the reason concrete in the other direction: if
`OracleRFL ≈ NoDiagnosticCorrection` the primitive did not hold and V0.4R **should not have been
run**, which is only knowable from a completed V0.3R. No V0.4R claim may be made about a B2
contrast that is still `INCONCLUSIVE`.

### 67.12 What this amendment does not do

* it collects **no seed**, of any stage, and authorises none;
* it writes no code: §67.8's prerequisites need their own authorisation;
* it sets no $\Delta_{\min}$ value, no $h$ other than `05`'s default, no $T$, no $N_{\text{eval}}$,
  no Retention formula — each is a dev-stage decision frozen under §67.5/§67.10;
* it specifies no formula for `BehavioralCollateral`'s "unaffected" set beyond the four
  properties §67.4 freezes for it — truth-blind, arm-blind, pre-update, one set per scene
  across paired arms — and the rule by which dev chooses among constructions; it also fixes
  no retention formula, only that the confirmatory form must be defined for every seed;
* it does not re-open $L_0$, $L_2$, $L_3$, the $D_Q$ store, or $D_{patch}$, and it may not be used
  to justify modifying a frozen B1 artifact;
* it makes no claim about $\Gamma$: every census measures over-credit under a **fixed** ontology
  and does not validate it (A77 §65.12's clause stands).

---

## 68. A80 — the $X$ and $P$ B1 paths, and the substrate refactor they need

$$\boxed{\text{the only purpose: turn A76's frozen } X/P \text{ B1 cells into real, executable paths}}$$

A76 §63.9 froze the $X$ and $P$ cells and §63.10's $\rho_A$ froze their store keys. A79 §67.8
recorded that ``D6/B1 CLOSED'' is the **Decision** path, and that $P_{id}$/$X_{id}$ are B2
prerequisites. This amendment authorises that work — and it is authorisation text only: it writes
no code, and the three steps below are each a separate commit with its own gates, in the pattern
A77 §65.12 and A78 §66.1 established.

### 68.1 Three steps, not two — and why the first one exists

The plan this amendment replaces was "implement $X$, then $P$". That is not executable as written,
because the shared B1 infrastructure is **Decision-shaped**:

| shared object | today |
|---|---|
| `AddressPlan.address` | `DecisionAddress` |
| `DecisionWriteReceipt.address` | `DecisionAddress` |
| receipt canonicalisation | reads `.state`, `.z`, `.m` |
| `SliceDescriptor.owner` | returns `DecisionAddress` |

while the addresses the new paths need are not decision addresses at all:

$$\rho_X(\texttt{ControllerSite}) = \text{the site handle } (s_t, a^{cmd}_t), \qquad
\rho_P(\texttt{ProcessCommit}, z^{\text{proposal}}) = z^{\text{proposal}}$$

An implementer given only "do $X$ then $P$" would have to decide *at code time* how a
`ControllerSite` fits a decision-shaped receipt, how a process integer becomes a plan address, and
what `owner` returns and how the canonical form encodes it. That is implementation-time invention,
which the rebuild exists to prevent. So:

$$\boxed{\text{generic address/receipt substrate refactor} \rightarrow X \rightarrow P}$$

Three steps, three commits, each with its own gates. Step 1 produces **no new scientific
capability**: it is the A77 §65.12 first-step pattern applied again, and it must be able to say so
by moving no number.

### 68.2 Step 1 — the address/receipt substrate, generalised by type rather than by duck typing

The goal is one sentence:

$$\boxed{\text{the B1 plan/receipt/locality contract stops assuming every credited address is a }
\texttt{DecisionAddress}}$$

What it may **not** become is `address: Any` with a "generalisation complete" note. That would
discard the nominal and typed closure that A77 §65.5, A78 §66.5 and the Step 3 domain work
established. The requirement is that the shared layer can *carry* per-architecture domains without
absorbing them:

$$\boxed{\text{typed credited address} + \text{typed store address} + owner_\alpha +
\text{deterministic canonical receipt}}$$

Each architecture continues to own its address domain, its owner resolver **and its admission
policy**. The mechanism is generic — the runner always asks the architecture's domain, so the
boundary is never decided by the shared layer — but what the domain *answers* is the
architecture's:

$$\boxed{\text{same cell} \Rightarrow \text{same admissibility boundary, by the architecture's own policy}}$$

$D_Q$ keeps the strict rule A78 §66.5 closed it with, and $X$/$P$ will choose theirs when they are
implemented. **$D_{patch}$ keeps the frozen legacy policy**: its recorded state is that its two
same-tier arms differ in admissibility, and §68.5 forbids repairing that in passing. A universal
boundary would do exactly that, silently, for both arms — which is the drift Step 1 produced once
and a regression gate now holds in place. The concrete
mechanism is the implementer's: a type parameter, a per-slice address protocol with an explicit
membership check, or a discriminated union are all acceptable **provided** no architecture's
addresses become acceptable to another's slice, and provided the nominal closure that makes a
stand-in insufficient is preserved rather than relaxed.

**Step 1 adds no law, no cell, and no capability.** It may not contain $X_{id}$, $P_{id}$, or any
$X/P$-specific code, and it may not touch the frozen $D_Q$ or $D_{patch}$ semantics.

**Step 1's acceptance conditions**, which are what make it a refactor rather than a change:

| condition | evidence |
|---|---|
| $D_Q$ behaviour unchanged | all five self-checks still pass: $Q$ 14/14, B1 13/13, $L_0$ 8/8, $L_2$ 11/11, $L_3$ 11/11 |
| $D_{patch}$ ledger unchanged | the 396-entry baseline still reports `ENCODING_ONLY`, 0 mismatches outside the fingerprint fields, 0 structural |
| no new capability | no $X/P$ cell, law, address type or slice in the commit |
| the typed closure survives | a stand-in address is still refused by the architecture that did not admit it |

**A second exact domain, proved synthetically.** Requiring only that a stand-in is still refused
would show that the old Decision closure did not break — not that the generic layer can *carry* a
second strict domain, and Step 1 may not add $X/P$ code in order to show it. So Step 1 is accepted
only together with a **test-only** synthetic domain: two nominal address types, plus a test-only
slice and address codec, proving that `AddressPlan`, the receipt, owner locality and the
canonicalisation really run a second exact domain; that an $A$-slice **rejects** a $B$-address; and
that a duck-typed stand-in is refused. With the honest mutation — relax the exact-domain validator —
the hostile gate must go red. Test-only dummies are not $X/P$ capability, so this does not breach
the "no new capability" condition above.

**The canonical form is injective, not merely deterministic.**

$$\boxed{canon_\alpha(x) = canon_\alpha(y) \iff x = y \quad \text{on the legal credited-address domain}}$$

Deterministic and complete are not enough. An $X$ canonical form that omitted $a^{cmd}$ would map
$\texttt{ControllerSite}(s, a_1)$ and $\texttt{ControllerSite}(s, a_2)$ to one value, and two
distinct credited sites would share a receipt identity. This project has already paid for that
omission once — the legacy controller site left out a key address component — so it is written down
rather than rediscovered. The requirements: **deterministic**; **complete**; **injective on the
legal domain**; and **architecture/store-tagged**, so that two slices' legal addresses cannot
collide in one representation by accident. $X$'s gates carry the canary: two sites differing only in
$a^{cmd}$ must produce **different** canonical receipts.

### 68.3 The exact cell delivery rows, frozen here

A77 §65.2 says $X$ and $P$ "get their own rows when implemented". This is that point, so the rows
are written now rather than discovered by whoever implements them:

| cell | delivery | what it is |
|---|---|---|
| $X \times L_0$ | $\{a^{cmd}\}$ | the factual command at the visited site |
| $X \times L_3$ | $\varnothing$ | the locality-matched restore, which needs no content |
| $P \times L_1$ | $\{z^{\text{proposal}}\}$ | the assisted input, and the only assisted row here |
| $P \times L_3$ | $\varnothing$ | likewise empty |

$$\boxed{fields(X, L_0) = \{a^{cmd}\}, \quad fields(X, L_3) = \varnothing, \quad
fields(P, L_1) = \{z^{\text{proposal}}\}, \quad fields(P, L_3) = \varnothing}$$

A76 §63.9 already decides the content; what is added is that the two rows are *written*, so that
"same cell $\Rightarrow$ same envelope" (A77 §65.2) has something to check against from the first
commit rather than a blank.

**Empty cells are not arms.** $X$'s $L_1$ and $L_2$, and $P$'s $L_0$ and $L_2$, have no substantive
treatment and therefore **no same-tier reference entry either** — A77 §65.3 gives a
$\texttt{NoWriteRef}(\ell)$ per cell that *has* a substantive treatment, so an empty cell has
nothing to reference. Neither may acquire an arm merely because the shared infrastructure can now
express one: expressibility is not authorisation, and a manufactured arm's score would be an
artefact of the pairing rather than of the law (A76 §63.9).

### 68.4 Step 2 — $X$: the controller path

A76's cells are implemented **as frozen**, not redesigned:

$$\rho_X(\texttt{ControllerSite}) = (s_t, a^{cmd}_t), \qquad
\boxed{C_X^L(\rho_X(\texttt{ControllerSite})) \leftarrow a^{cmd}}$$

$$X:\quad L_0 = \{\texttt{NoWriteRef}(L_0),\ X_{id}\}, \qquad
L_3 = \{\texttt{NoWriteRef}(L_3),\ \texttt{LocalOracleRestore} \equiv X_{id}\}$$

$$\boxed{\lvert\text{independent treatments}\rvert(X) = 1}$$

The $L_3$ entry is an **alias on this architecture — an information tier, not a second treatment**
— and it must not be counted as one. Following the $D_{patch}$ precedent, the alias should
demonstrate that it **reuses the same operation implementation** (the same `plan` function object,
as `LocalOracleRestore` does for `DeleteFactualPatch`) rather than being a second implementation
that happens to behave identically.

**Where $z$ and $m$ come from.** $a^{cmd} \in A_z(m,s)$ is a statement about an *option in force*, and
`ControllerSite` carries only $(s, a^{cmd})$. Left open, the implementer decides the source — which
row to read, whether the kernel's control state may be consulted, whether some other object may
supply it — and a different answer per site is exactly what A76 §63.10's $\rho_A$ exists to prevent.
So:

$$\boxed{\text{$X$'s credited-address validation uses the unique learner-visible factual row for that visited site}}$$

together with that row's $z$ and $m$ at that step, used **only** for pre-plan address and contract
validation:

$$\text{resolve the factual row} \rightarrow \text{strict } \texttt{ControllerSite} \text{ validation}
\rightarrow a^{cmd} \in A_z(m,s) \rightarrow \text{arm planning}$$

The treatment and its same-tier reference pass through **the same validator**, so the two cannot
differ in admissibility (A78 §66.5's rule). This is not solved by widening the law's fields: $X$'s
$L_0$ delivery stays exactly $\{a^{cmd}\}$ (§68.3), and $z, m$ are **cell-construction** inputs
rather than law information.

**$X$'s gates:**

* `ControllerSite` is an **exact, strictly typed** legal address — nominal closure, not "an object
  with `.state` and `.a`";
* $a^{cmd}$ is a legal action **and satisfies the learner baseline contract** $a^{cmd} \in A_z(m,s)$.
  A learner-owned write does **not** inherit fault privilege: A75 §62.3 keeps $Z_X$/$Z_E$'s right
  to violate the contract as *fault semantics*, and a persistent write is not a fault;
* $owner_X(\text{edit.address}) = $ the credited `ControllerSite`, and the runner consults the
  resolver for the operation kinds alike (A78 §66.5's load-bearing rule);
* a cross-architecture edit is refused; an uncredited site is not writable; duplicate edits and
  duplicate address-plans are refused;
* snapshot + **one atomic commit** per scene, one receipt per credited address;
* a **healthy identity write canonicalises to a no-op**, so the $\rho_X$ mapping and the store's
  canonicalisation agree on what "no change" means;
* a repeated run is **idempotent** — the second run changes nothing;
* the cell-level credited-address boundary is enforced **before** any arm plans, so the treatment
  and its same-tier reference cannot differ in admissibility (A78 §66.5, and the reason that rule
  exists).

### 68.5 Step 3 — $P$: the process path, and the assisted input

$$\rho_P(\texttt{ProcessCommit}, z^{\text{proposal}}) = z^{\text{proposal}}, \qquad
\boxed{C_P^L(z^{\text{proposal}}) \leftarrow z^{\text{proposal}}}$$

$$P:\quad L_1 = \{\texttt{NoWriteRef}(L_1),\ P_{id}\}, \qquad
L_3 = \{\texttt{NoWriteRef}(L_3),\ \texttt{LocalOracleRestore} \equiv P_{id}\}$$

$$\boxed{\lvert\text{independent treatments}\rvert(P) = 1}$$

$$\boxed{P_{id} \in L_1, \qquad P_{id} \notin L_0}$$

This is not a placement choice: the factual rows carry $z^{\text{in-force}}$ only, **never**
$z^{\text{proposal}}$, so the key cannot be computed from $L_0$ information. That is exactly why
A76 §63.1 put $P_{id}$ at $L_1$, and why $\rho_P$ is the one $\rho_A$ that needs an assisted input.

**The order that makes $P$ coherent.** $\rho_P$ is the one $\rho_A$ whose *store address depends on
the assisted input*, and A80 asks three things at once, one of them from §68.3: the proposal is
delivered by the $L_1$ envelope, the plan and receipt need an address, and the $L_3$ alias must reuse
implementation while its own delivery is empty. Left unordered, those force the implementer to
choose an architecture. Frozen:

$$\boxed{\text{credit unit} + \text{allowed assisted input} \xrightarrow{\rho_P}
\text{resolved B1 address } z^{\text{proposal}}}$$

* the resolver belongs to **cell construction** and runs **before any arm planning**;
* the address-plan and receipt locality unit is that resolved **true-int option key**;
* the $L_1$ cell still delivers $\{z^{\text{proposal}}\}$ explicitly — the same envelope to the
  reference and to the treatment;
* $P_{id}$'s operation therefore depends only on the resolved address,
  $\texttt{Edit}(\texttt{PROCESS}, z, z)$, which is what lets the $L_3$ alias reuse **the same plan
  function**;
* the $L_3$ law's delivery is still $\varnothing$ while it uses the same upstream $\rho_P$
  resolution.

$$\boxed{\text{address resolution} \neq \text{information delivered to the law}}$$

The resolver may use $z^{\text{proposal}}$ to construct a legal store address and for nothing else:
extending it into additional law information would be assisted-input laundering by another route.
This is also why

$$P_{id} \text{ at } L_0 \Longrightarrow \texttt{PROTOCOL\_ERROR}$$

holds even for a caller that already "knows the integer address" — the $L_0$ cell is not authorised
to run this resolver or this treatment at all.

**$P$'s gates, beyond $X$'s analogous set:**

* **no assisted-input laundering.** The fact that some kernel or state object can *reach* a
  proposal does not license the cell. $z^{\text{proposal}}$ must be delivered **explicitly by the
  $L_1$ envelope**, and

$$\boxed{P_{id} \text{ declared or run at } L_0 \;\Longrightarrow\; \texttt{PROTOCOL\_ERROR}}$$

  A path that reads a proposal without the envelope having delivered it is the same defect class as
  a metric whose *input* was built from forbidden truth (A75 §62.10): the cell not seeing it is not
  evidence that the cell was not handed it;
* **the process key is integer-semantics, so the numeric-alias lesson applies.** `True == 1` and
  `1.0 == 1` with equal hashes (the Step 3 finding, A78 §66.5), so a process address must pass an
  **exact type** check *before* domain membership. A boolean or a float must never be a legal
  process address, and a value-equal alias must not reach the store;
* the $L_1$ envelope is delivered through the same field-set mechanism as every other cell
  (A77 §65.2), so "same cell $\Rightarrow$ same envelope" holds for $P$ too.

### 68.6 What A80 does not authorise

$$\boxed{\text{NO B2 runner}}\quad
\boxed{\text{NO } \texttt{FutureConsequenceView} \text{ implementation}}\quad
\boxed{\text{NO } \texttt{BehavioralCollateral} \text{ implementation}}$$

$$\boxed{\text{NO development seed}}\quad \boxed{\text{NO confirmatory seed}}$$

and it may not be used as the occasion to:

* modify $D_Q$ — its five steps are closed and its artifacts are bound;
* repair the frozen $D_{patch}$ malformed-address asymmetry (recorded in `00-INDEX.md` §7.2 as a
  known property; it needs its own authorisation, not this one's convenience). **This clause
  outranks §68.2's generic mechanism read as a universal rule**: the substrate carries the
  architecture's policy, so a strict $D_Q$ and a legacy $D_{patch}$ coexist, and
  `test_19_the_frozen_d_patch_alias_asymmetry_is_preserved` measures all three folding aliases
  against both arms at the real $D_{patch}$ entry point;
* change any A79 endpoint, threshold, or the V0.3R PASS conjunction;
* add Regime $T$/$P$ behaviour, a stratification, or the global-oracle denominator;
* begin V0.4R, or collect any seed of any stage.

### 68.7 Sequence and review boundary

$$\boxed{\text{Step 1} \rightarrow \text{Step 2} \rightarrow \text{Step 3}, \qquad
\text{one commit each, own gates each, no mixing}}$$

Each step's commit is reviewed before the next begins, and Step 1 is reviewed against §68.2's
acceptance table specifically to confirm that it moved no number. The three steps are authorised by
this text, and each is still its own commit: no step may be combined with another, and none may
carry B2 work.


---

## 69. A81 — domain identity is out of band from the canonical ledger

A80 §68.2 requires a canonical address form that is "architecture/store-tagged", and A77 §65.12
freezes that the architecture lives in the arm descriptor and **not** in the canonical ledger,
where moving anything into that schema is a versioned change of its own. Read together, the two can
suggest that a receipt should serialise `D_Q|…`, `X|…`, `P|…`. It must not, and the implementation
does not. This amendment states the division, and under it §68.2's phrase is to be read; A80's text
is frozen and is not edited.

$$\boxed{\text{the contract's address identity} = \bigl(\text{domain tag},\
canon_\alpha(\text{address})\bigr)}$$

$$\boxed{\text{what the frozen ledger serialises} = canon_\alpha(\text{address})}$$

The architecture is already carried by the arm and slice descriptor, so the serialised form is the
per-domain canonical **alone**. That is also why the 396-entry $D_{patch}$ baseline remains
`ENCODING_ONLY` rather than becoming `DRIFTED`: a tag in the receipt bytes would have been a
**ledger schema change**, not a detail of generalising the address contract. The pair above is
therefore the whole identity while only its right-hand half is written down — out of band, by
construction rather than by omission.

$$\boxed{\text{cross-domain admission comes from } \texttt{require\_credited},\ \text{not from
comparing tags}}$$

Two architectures may legitimately admit value-equal addresses — $D_Q$ and $D_{patch}$ both credit
decision addresses — so a tag comparison is neither necessary nor sufficient for admission:

* what stops an $A$-slice accepting a $B$-address is that the slice asks **its own domain**, whose
  `require_credited` closes its own type and range (A80 §68.2);
* the tag's jobs are domain identity (equality and hashing of domains) and diagnostics, and
  nothing else;
* consequently a gate that "proves" cross-domain isolation by asserting that two tags differ
  proves a property of two constants, not of admission. `tests/rebuild/test_address_domain.py`
  asserts admission itself: `test_2` that an $A$-slice rejects a $B$-address, `test_3c` that a slice
  whose domain is not an `AddressDomain` fails stop.

One sentence of §68.2 stands as written and is worth restating here because the two clauses are
easy to conflate: the runner asks the domain for **every** architecture, while the *policy* it
executes is that architecture's own. $D_Q$ is strict, $D_{patch}$ keeps its frozen legacy policy,
and the substrate does neither on its own behalf.

**What this amendment does not do.** It writes no code, moves no number, collects no seed, and
changes none of A80's three steps; it exists so that the next implementer does not read §68.2 as
requiring a tag in the ledger bytes.

---

## 70. A82 — the concrete $\Gamma$ encoding is the wire contract; A69's index notation is not a spelling

A80 §68.4 fixes what $X$'s cell delivers and that $\rho_X$ yields the site $(s_t, a^{cmd}_t)$, but it
speaks of $\rho_X(\texttt{ControllerSite})$ **without freezing the concrete spelling of a credited
controller unit**. A69 wrote $\{\texttt{ControllerSite}_t : t \in I\}$, and that is an *index*: it
says which sites lie in $\Gamma(I)$, not which string names one. A71 then corrected the truth to be
built from $R^{\text{mech}}$ descriptors — "so D/X carry addresses … no generic unit remains in any
truth" — with `credit.py` expanding predictions into concrete episode-local addresses
(`Decision_3`, `ControllerSite_x_y_t_cmd`). The two are therefore **notation and encoding**, not two
spellings of one unit:

$$\boxed{\text{A69's } \texttt{ControllerSite}_t \text{ is mathematical index notation}}$$

$$\boxed{\text{A71's concrete } \Gamma \text{ encoding is the implementation interface}}$$

and the interface is **one string**, emitted by V0.2R and consumed by V0.3R B1:

$$\boxed{\texttt{ControllerSite}_{x,y,t,a^{cmd}} =
\texttt{PublicSCMView.credit\_unit}(\texttt{ControllerFault})}$$

This is a **cross-layer interface** question and not a downstream detail, because A75's chain begins
$\Gamma^\ast \to \mathcal W(\Gamma^\ast)$: the units of $\Gamma^\ast$, $\Gamma^+$, $\Gamma^-$ and the
coverage/FCR counters are the input of B1's $\rho_X$. Emitting
$\texttt{ControllerSite}_{x,y,t,a^{cmd}}$ from V0.2R while B1 accepted
$\texttt{ControllerSite}_t$ would leave the two frozen layers unable to meet.

Consequences, all of which the implementation satisfies:

* B1's $\rho_X$ consumes that concrete unit and **only** it. $\texttt{ControllerSite}_t$ is **not** a
  compatibility alias — the same $\Gamma$ unit with two wire spellings reopens exactly the namespace
  ambiguity A71 closed — and $\texttt{Decision}_t$ is refused, because A69 kept the two families
  apart and A76 §63.10 gives them different images, $(s_t, z_t, m_t)$ versus $(s_t, a^{cmd}_t)$.
* The parsed fields are the unit's **identity**, not decoration: $(x, y, t, a^{cmd})$ must equal the
  factual row's, or "D/X carry addresses" has quietly degraded back to timestep-only. $\kappa$ and
  $\phi$ come from the row, because the concrete unit does not encode them; $z$ and $m$ remain
  cell-construction inputs and never enter a law's delivery (§68.4).
* The legal namespace is injective by **canonical rendering**: $\mathrm{render}(\mathrm{parse}(u)) = u$
  is required, so a zero-padded field cannot name the unit it parses to.
* A **test-only** cross-layer gate (`tests/rebuild/test_x_controller.py::test_20`) resolves a unit
  produced by `PublicSCMView.credit_unit`, and a hostile gate (`test_21`) tampers with each field in
  turn. Production code imports no method layer: the compatibility is asserted where it can be, and
  the gate fails if either side changes its spelling, if the descriptor loses a field, or if B1 falls
  back to consuming the timestep alone.

**What this amendment does not do.** It re-designs nothing in A80: §68.3's admissibility rule,
§68.4's delivery rows and the $L_0$/$L_3$ single-operation requirement stand as frozen. It moves no
number, changes no endpoint, treatment or threshold, and collects no seed. It fixes a **wire contract
between two frozen layers**, and it exists so that A69's notation cannot be used to overwrite A71's
encoding a second time.

---

## 71. A83 — B2 implementation authorisation, and the boundary it does not cross

A79 §67.12 wrote: *it writes no code; it authorises no seed; §67.8's prerequisites need their own
authorisation.* A80 supplied those prerequisites, and its three steps are now **CLOSED**, each with
its own commit and its own gates:

| step | what | closure revision | evidence binding |
|---|---|---|---|
| Step 1 | the generic address/receipt substrate, generalised by type | `6f78949` | `3eeec3a` |
| — | reproducibility maintenance of the mutation instruments (accepted) | `aab5727` | — |
| Step 2 | $X$: the controller path, and $\rho_X$ over the concrete $\Gamma$ unit (A82 §70) | `e1c7141` | `81cb162` |
| Step 3 | $P$: the process path, the assisted input, and the entry point that binds both cells to $\rho_P$ | `5fcb750` | `c311b42` |

$$\boxed{\text{A79 §67.8's prerequisites} = \text{SATISFIED}}$$

A83 is what turns that fact into an **implementation** authorisation. It re-designs nothing: A79
§§67.1–§67.11 stand as frozen and A79's text is not edited. This amendment fixes only what may be
built now, what must still be decided later, and what may not happen at all.

### 71.1 What is authorised

Implementation of the B2 measurement stage, as A79 froze it and not otherwise:

* `FutureConsequenceView` and its builder — A75 §62.10's four gate layers, with the
  fabricated-feature mutation live;
* the future rollout that produces $Y^{\text{future}}$ from a post-update state;
* the three dimensions' estimators: RMST as FutureUtility's primary with DeficitAUC mandatory,
  `BehavioralCollateral`'s candidate machinery, and Retention's candidate machinery;
* the paired B2 runner: paired arms on common random numbers, the treatment/reference pair per
  cell, and the per-scene record that keeps the three dimensions separate.

$$\boxed{\text{implementation authorisation} \neq \text{seed authorisation}}$$

Nothing above authorises a seed, and "the code exists now" softens nothing:

$$\boxed{\text{NO smoke seed},\quad \text{NO development seed},\quad
\text{NO confirmatory seed},\quad \text{NO V0.4R}}$$

In particular the 32 development seeds of §67.9 may **not** be run once the runner exists. The
reason is the order of evidence rather than caution: dev data produced by an unvalidated instrument
is not dev data. The instrument's own gates close first (§71.3).

### 71.2 The B1 regression gate, restated by measurement rather than by count

§67.11's gate table opens with "the **five** B1 mutation self-checks and the $D_{patch}$ ledger
baseline still hold". That count was written when five tables existed. The live set is **eight**,
and it grew the way it was supposed to: each architecture's table joins the gate when its step
closes. B2's gate is therefore the measured set, not the historical number:

| table | mutations that must all go red |
|---|---|
| Q substrate | 14/14 |
| B1 interface | 13/13 |
| $L_0$ factual | 8/8 |
| $L_2$ counterfactual | 11/11 |
| $L_3$ row restore | 11/11 |
| address domain (A80 Step 1's synthetic second domain) | 6/6 |
| $X$ controller | 10/10 |
| $P$ process | 11/11 |

plus the $D_{patch}$ 396-entry ledger baseline reported `ENCODING_ONLY` with 0 mismatches outside
the fingerprint fields and 0 structural, at a revision bound in its own evidence commit.

**The rule this restates:** a self-check's *count* is not the gate. A table whose mutations are not
all `GATE_IS_REAL`, or whose artifacts were not regenerated at the revision under test, is not
evidence. Reading "five" literally in B2 would silently drop the address-domain, $X$ and $P$ tables
— that is, exactly the three steps A80 added — which is why the interpretation is recorded here
rather than left to whoever runs the gate.

### 71.3 The instrument must be validated before the first dev seed exists

The leakages A79 §67.2–§67.4 name are implementation errors before they are statistical ones, and
each needs a gate that can go **red**:

* **truth leakage** — a feature derived from $\mathcal H_{\text{forbidden}}$ reaching the view. A75
  §62.10's four layers plus the fabricated-feature mutation are the gate, and it must be shown to
  kill a truth-derived feature rather than merely to be present;
* **arm leakage** — an arm seeing the other arm's outcome, or its own future, through the runner.
  The gate is the paired construction and the per-scene record: one pre-update state, one shared
  $U_{\text{unaffected}}$, and no post-update information in the treatment's input;
* **post-update selection leakage** — choosing $T$, the checkpoint grid, $N_{\text{eval}}$, the
  Retention form or a $\Delta_{\min}$ *after* seeing treatment curves. §67.10 forbids the first of
  these in the strongest terms; §71.4 keeps all of them open until the dev freeze.

$$\boxed{\text{no development seed until the instrument's own gates close}}$$

### 71.4 What stays open, and where it is decided

A83 decides none of these. Each is a development-stage decision, made under the rule
§67.5/§67.9/§67.10 already fixed and committed **before** any confirmatory seed:

* the concrete construction of `BehavioralCollateral`'s unaffected set — §67.4's four properties
  (truth-blind, arm-blind, pre-update, one set per scene across paired arms) are frozen; the
  construction is chosen on measurement properties;
* the all-seed Retention form — §67.5 froze that the confirmatory primary must be defined for
  **every** seed and named the candidate forms; which one is chosen is a dev decision;
* $T$, from the baseline only and by §67.10's rule, with no treatment-arm curve plotted, printed or
  summarised before it is frozen and committed;
* $N_{\text{eval}}$ and the checkpoint grid $\mathcal G_{\text{ckpt}}$;
* $\Delta_{\min}$ per endpoint;
* and $N_{\text{train}}$, which does not exist yet and may not be named here.

$$\boxed{T,\ \mathcal G_{\text{ckpt}},\ N_{\text{eval}},\ \text{the Retention form, and each }
\Delta_{\min} \text{ are frozen together, before the first confirmatory seed}}$$

The statistical protocol is unchanged and is not re-opened: $N_{\text{dev}} = 32$,
$N_{\text{confirm}} = 400 = 4\times100$, secondary $N = 200 = 2\times100$, paired seeds with common
random numbers, cumulative **and** fresh block at every look with only $N=400$ confirmatory, the
four-way verdict, and V0.3R PASS as §67.11's conjunction rather than a score.

### 71.5 What this amendment does not do

It writes no code, moves no number, collects no seed of any stage, sets no threshold, changes no A79
endpoint or open item, does not touch the frozen $D_Q$ or $D_{patch}$ semantics, and does not begin
V0.4R. It does not convert A79 from pre-registration into anything else: §67.11's gate order and its
"any gate FAIL $\Longrightarrow$ no confirmatory B2 seed is collected" stand exactly as written.

---

## 72. A84 — the DeficitAUC numerical-integration contract

`05` §8.3 froze a **continuous** integral, and B2-2's first implementation realised it as a
left-rectangle sum with **no normalisation**:

$$\text{implemented}: \sum_i d_i\,(t_{i+1} - t_i) \qquad\text{vs}\qquad
\text{frozen}: \frac{1}{T_{\max}}\int_0^{T_{\max}} \bigl[V_{\text{pre}} -
V(t)\bigr]_+ dt, \quad d_i = \bigl[V_{\text{pre}} - V_{t_i}\bigr]_+$$

Two things were wrong and only one of them was arithmetic. The missing $1/T_{\max}$ made the
quantity an *area* that grows with the horizon rather than a mean deficit over it; and the
quadrature rule itself — left-hold, right-hold, or interpolation — was **nowhere frozen**, so the
implementation was choosing an estimator, which A83 §71.4 keeps to the development stage for
exactly this reason. A gate that pins an unfrozen rule pins the implementation's opinion.

**Frozen: trapezoidal integration on the real episode grid.**

$$\boxed{\mathrm{DeficitAUC} = \frac{1}{T_{\max}} \sum_i \frac{d_i + d_{i+1}}{2}
\,(t_{i+1} - t_i)}$$

with $d_i = [V_{\text{pre}} - V_{t_i}]_+$ and $t_{i+1} > t_i$ the **real episode indices**.
The reason is assumption-minimality rather than preference: `05` defines a continuous integral
between the checkpoints, and on a grid the direct reading of that integral assumes linear
interpolation between adjacent observations. Left-hold instead assumes that the measurement at
$t_i$ persists across the whole of $[t_i, t_{i+1}]$, which the frozen definition never says, and it
is not neutral — on a curve that recovers *within* an interval, left-hold overstates the deficit.
An array-position reading is refused for the same reason one step further out: it silently rescales
every deficit by the grid spacing.

**Calibrated analytically, and seedlessly.** On a constant deficit the rule must return that
constant; on a linear deficit it must return the analytic integral. Both are exact for trapezoid
and neither is for left-hold, so the calibration distinguishes the rules rather than merely
exercising the code. `tests/rebuild/test_b2_environment.py::test_8` carries both cases; no seed of
any stage is involved.

**And the curve spans the horizon.** `05` §6.2's grid is $\mathcal G_{\text{ckpt}} = \{0, 1, 2,
5, \dots, T\}$: it contains both ends. So

$$\boxed{episodes[0] = 0, \qquad episodes[-1] = T_{\max}, \qquad 0 \le t_i \le T_{\max}}$$

are part of the contract, and a curve that stops short is **refused rather than padded** — a rule
for the unobserved tail would be a second estimator chosen silently inside the first, and RMST and
DeficitAUC must describe one and the same $[0, T_{\max}]$. A recovery window that would only
complete past the horizon does not qualify, so $T_{\max}$ bounds the *answer* and not only the
grid.

**Naming.** The per-seed $\min(\tau, T_{\max})$ is **not** RMST. RMST is
$\mathbb E[\min(\tau, T_{\max})]$ across seeds and belongs to B2-4's aggregation; the per-seed
quantity is `restricted_time`. Exposing one under the other's name is how a restricted time and a
population summary get conflated when the aggregator is written.

**What this amendment does not do.** It re-opens nothing in A79: the endpoint stays DeficitAUC as
`05` §8.3 defines it, RMST stays the primary, the three dimensions and the four-way verdict are
untouched. It sets no $T$, no $\Delta_{\min}$, no $N_{\text{eval}}$, no checkpoint grid value,
and collects no seed. It fixes the **numerical realisation** of an already-frozen endpoint, and it
exists so that the realisation is a decision on the record rather than one inside a loop.

---

## 73. A85 — the behavioural measurement contract for future performance

A79 §67.4 froze `BehavioralCollateral` as **future behavioural spillover**, and froze four properties
of its unaffected set (truth-blind, arm-blind, pre-update, one set per scene across paired arms). It
did **not** freeze an executable measurement interface $c \mapsto V_W(c)$, and B2-4's first closure
attempt filled that gap with an adapter:

$$V_W(c) \;=\; \text{rewards}\big[\,c.\text{state}.x \bmod \#\text{rewards}\,\big]$$

which maps a **context** coordinate onto an index of a **temporal** reward array. The type is
plausible and the science is not: nothing about where a decision context sits in $x$ says which
episode reward measures the behaviour at that context. This amendment replaces that with a contract,
and it deliberately **chooses no unaffected-set candidate**: which construction is primary stays a
development-stage decision under §67.4/A83 §71.4.

### 73.1 $V_{\text{pre}}$ is already frozen, and it is not $V_{\text{unaffected,pre}}$

`11-ENVIRONMENT.md` §12.3 and §13 item 13 settle the FutureUtility side: $V_{\text{pre}}$ is measured on
$Q^{*}$ itself, at the same $N_{\text{eval}}$ and over the same evaluation scenes as the
post-corruption checkpoints, and it ships **inside the shared, frozen, fingerprinted reference
artifact** — it is not re-measured per run. Three consequences, all of them binding on B2:

$$\boxed{V_{\text{pre}} \text{ is read from the reference artifact, and both arms read the same
frozen value}}$$

* it is **not** the pre-update learner state's value, **not** the reference arm's outcome, and
  **not** the treatment's own post-update curve summarised as $\max|v|$ — reading a recovery target
  off the arm's own result makes the target a function of the thing it is supposed to judge;
* the runner may read it **before** any arm runs: the prohibition on producing a future before the
  update governs futures that participate in *this* pairing's outcome, not a pre-corruption
  measurement that was frozen and fingerprinted before the episode existed;
* and **the frozen thing is the rule, not the number**. §12.3 fixes $V_{\text{pre}}$'s provenance
  and generation rule,

$$V_{\text{pre}} = \mathcal E\bigl(Q^{*};\ N_{\text{eval}},\ \mathcal S_{\text{eval}}\bigr)$$

  together with "compute once, fingerprint, share by both arms, never re-measure per run".
  **A83 §71.4 explicitly keeps $N_{\text{eval}}$ open**; and because `11` §12.3 requires
  $V_{\text{pre}}$ and the post-corruption checkpoints to use the **same evaluation scenes**, the
  concrete $\mathcal S_{\text{eval}}$ used to instantiate $V_{\text{pre}}$ must be fixed
  consistently with the eventual evaluation design. **That consistency requirement is recorded here
  by A85; it is not an already-enumerated A83 design quantity**, so the chain of attribution is

$$\boxed{\text{A83 supplies the open } N_{\text{eval}}, \quad \text{§12.3 supplies the
  same-scenes constraint}, \quad \text{A85 makes their consequence explicit}}$$

  The rule and the instance are not in conflict, and reading them as one another is how an
  instrument-validation step would instantiate a confirmatory design quantity early:

$$\boxed{\text{the provenance rule is frozen} \;\neq\; \text{the final numerical instance is frozen}}$$

  During instrument validation only a **nominal, fixed test artifact** may exercise the interface.
  The confirmatory instance of $V_{\text{pre}}$ is frozen together with the chosen
  $N_{\text{eval}}$ (A83 §71.4) and the evaluation scenes that satisfy §12.3's same-scenes
  requirement, and from then on it is shared by both arms and never re-measured per run;

* and the two "pre"s are different quantities:

$$\boxed{V_{\text{pre}}\ (\text{the health reference}) \;\neq\;
V_{\text{unaffected,pre}}\ (\text{pre-write behaviour on the unaffected set})}$$

They share a word and nothing else. $V_{\text{pre}}$ comes from $Q^{*}$ through the frozen artifact
and is architecture-independent; $V_{\text{unaffected,pre}}$ is measured on **this learner's**
pre-update state, over the evaluation units -- the unaffected region -- the update was not supposed to touch. Merging them because both
are called "pre" would silently replace one of the two definitions with the other.

### 73.2 The measurement contract

$V_W(u)$ must satisfy all of the following. **They are properties, not formulas**, and the
executable measurement form remains **unchosen**: it requires a subsequent specification decision
before the Collateral path in B2-4 may be closed.

$$\boxed{\text{A85 freezes properties} \;\neq\; \text{A85 authorises implementation to choose
the unit}}$$

1. **Measured, not assembled.** $V_W(u)$ is behaviour the **audited environment** actually produces
   from learner state $W$. No index, hash, modulo, resampling or other adapter may fabricate it from
   a temporal reward array. A number whose provenance is an indexing convention is not a measurement.
2. **Pre from the raw state, post from the arm's own state.** Every pre value is measured on the
   **original pre-update** learner state; every post value on the post-update state of the arm it
   describes. No post measurement may be reused as a pre, and the two arms' pre values are the same
   measurement rather than two equal ones.
3. **One exogenous schedule, one CRN draw.** Pre and post, reference and treatment, share the same
   evaluation scenes and the same exogenous schedule, so a difference between two values can only
   come from $\Delta W$. This is the same requirement the paired runner already carries, raised to
   the measurement interface itself.
4. **A closed nominal measurement.** The result is a closed nominal object carrying exactly
   $\mathrm{dom} = U_{\text{unaffected}}$: a mapping from the **evaluation unit**
   $u \in U_{\text{unaffected}}$ to a finite real, with **missing and extra units both refused**.

$$\boxed{V_W: U_{\text{unaffected}} \to \mathbb R_{\text{finite}}}$$

   The unit is written $u$ and **not** `context` on purpose: §73.3 has not yet decided whether the
   unit is a decision context, and naming it here would decide by vocabulary what the next
   specification question is supposed to settle. No arbitrary callable may stand in for the measurement, for
   the reason A75 §62.10 and B2-2a spent two rounds establishing: a callable is a hole with a
   signature.
5. **Behaviourally load-bearing for every architecture.** The *interface* must be able to register a
   behavioural effect of a write in $D_Q$, $X$ **and** $P$; it is not required that a single unit type
   carry all three, because §73.3 has not decided that it does:

$$\boxed{\text{the measurement interface must be behaviourally load-bearing for every architecture}}$$

   * if the **unified** form is chosen, that one domain must be shown to register detectable effects
     of all three architectures' writes;
   * if **architecture-specific** domains are chosen, each domain must be load-bearing for its own
     architecture's write, and the rule for comparing **across** architectures must be frozen
     separately rather than assumed.
6. **Calibrated on synthetic spillover, per architecture.** For each of $D_Q$, $X$ and $P$, a known
   injected behavioural change in the unaffected region must be **detected** by the interface. A
   metric whose types are all correct can still be structurally blind for one architecture, and
   only a per-architecture calibration shows which.

### 73.3 The question this amendment poses and does not answer

$$\boxed{\text{what is a behavioural evaluation unit that is fair to all three architectures?}}$$

The obvious candidate — "roll out from each decision context $(s, z, m)$ and take its value" — is
**not** obviously fair, and $P$ is the witness. A $P$ update changes the process commit,
$z^{\text{proposal}} \to z^{\text{in-force}}$, and a decision context already *fixes* $z$: an
evaluation unit that begins at a decision context can bypass the very process edge the write acts on,
so $P$'s real behavioural collateral could be measured as **zero** by a contract that is completely
silent about it. If that turns out to be the case, the honest outcomes are either

* a **unified evaluation scene domain** that all three architectures read through, with the property
  in §73.2.5 demonstrated rather than assumed; or
* **architecture-specific evaluation domains**, frozen as such, with the cross-architecture
  comparison then carried by the unaffected-set construction rather than by a shared context type.

Choosing either one now would repeat the error this amendment exists to correct: an interface
decision taken inside an implementation. A85 therefore settles the **properties**, and the choice
between these two forms is the next specification question — it should be attacked with the $P$
counterexample above, not with a default.

### 73.4 What this amendment does not do

It does not choose an unaffected-set construction, does not name a Retention form, sets no $T$, no
$\Delta_{\min}$, no $N_{\text{eval}}$ value and no checkpoint grid, and collects no seed. It
re-opens nothing in A79: three dimensions, no composite primary, and the four-way verdict stand as
frozen. It writes no code — **corrective** changes to `utility.py`, `runner.py` and the environment are made
only after A85 is reviewed and frozen (the first closure attempt at `9bb04bf` is recorded as REVIEW
FAIL, so "these files are untouched" is not the historical claim), and the $V_{\text{pre}}$ half of it is a **reading of `11` §12.3**, not a
new definition.

---

## 74. A86 — the evaluation-unit structural screening method

A85 froze the measurement contract's **properties** and left one question open:

$$\boxed{\text{unified evaluation scene domain} \quad\text{vs}\quad \text{architecture-specific
domains}}$$

A86 freezes **the method** by which that question is screened, and by design it freezes neither the
answer nor the canaries:

$$\boxed{\text{A86 freeze} \;\not\Rightarrow\; \text{calibration authorised}}$$

The concrete injection fixtures are A87's; §74.6 states the boundary.

### 74.1 The pre-registered candidate set, with deterministic projections

$$\boxed{\mathcal U^{\text{pre}}_{\text{unified}} = \{U_1, U_2\}}$$

Each member carries a **deterministic projection** $g_U$ from the semantic witness of §74.2 to a
unit, so that

$$\boxed{g_U(\xi) \text{ is single-valued: the same witness yields one unit of that candidate}}$$

| candidate | $g_U(\xi)$ | closed field surface of the unit |
|---|---|---|
| $U_1$ | the decision situation of the witness | $(s, z, m)$ — the enumerated decision-context triple |
| $U_2$ | the witness's **evaluation scene unit** | $(\kappa, \varphi, \text{base option}, \text{reference artifact})$: the episode's starting condition, entered **upstream of $C_P^L$** so that $z^{\text{in-force}}$ is produced during evaluation |

Three properties of these definitions are load-bearing, and the review produced each of them:

* **the unit is pre-constructed and arm-blind.** A85/A79 require the unaffected set — and therefore
  every evaluation unit — to be fixed before any arm runs and shared across the pair. What is
  post-update is the **measurement** $V_{W+\Delta W}(u)$; the unit's identity never is. $U_2$ is
  therefore not a "post-update unit";
* **the measurement schedule is not part of the unit.** The checkpoint grid $\mathcal
  G_{\text{ckpt}}$ is an A83-open design quantity and interrogates a unit rather than constituting
  it, so it is **excluded** from $U_2$'s field surface. Screening therefore uses a **nominal test
  schedule**, and any structural conclusion is claimed only for such schedules: when the final grid
  is frozen, the screening is re-run against it before its conclusion travels. What must not happen
  is a unit whose identity silently changes when the schedule changes;
* $g_U(\xi) = \varnothing$ — a candidate that cannot represent the witness — is a **coverage
  failure** (§74.3), not an absence of evidence.

$U_3$ (architecture-specific domains) is a **fallback family**, not a screened member, and §74.4
fixes when it may be entered.

### 74.2 The witness, and why the direction is not circular

A measurement position is not a persistent write target: the three architectures write in different
spaces ($D_Q$: a `QAddress`; $X$: a `ControllerSite`; $P$: the process store keyed by the assisted
proposal), and for $P$ the write and the observation site are different objects. So what is shared
across candidates is the **semantic witness**, not a representation of it:

$$\boxed{\mathcal C_A = \bigl(W_{\text{pre}},\ \Delta W_A^{\text{cal}},\ \xi_A^*,\
s_A^{\text{expected}}\bigr)}, \qquad A \in \{D_Q, X, P\}}$$

* $\xi_A^*$ — the semantic **evaluation situation** the synthetic edit is expected to affect. It is
  candidate-independent: each candidate projects it through its own $g_U$;
* $\Delta W_A^{\text{cal}}$ — the concrete synthetic persistent edit, declared with the witness;
* $s_A^{\text{expected}} \in \{-1, +1\}$ — the expected sign of the **behavioural loss**

$$s_A^{\text{expected}} = \operatorname{sign}\bigl[V_W(u) - V_{W+\Delta W_A^{\text{cal}}}(u)\bigr]
\quad\text{stated by construction, before any measurement}$$

  and it must be knowable **without** the measurement it will be checked against. An earlier draft
  defined $s_A$ *as* the sign of that difference and then compared the difference to it, which is
  $x = \operatorname{sign}(M)$ followed by $\operatorname{sign}(M) = x$ — a tautology, not a
  pre-registration. A canary whose direction cannot be stated without measuring has **no direction
  gate** for that cell; that is recorded as a limitation rather than repaired after the fact;
* a magnitude $m_A$ only where it is analytically known, and never a forced common ratio across
  architectures.

**One semantic canary per architecture.** Every candidate is screened against the same
$\mathcal C_A$ through its own projection $g_U(\xi_A^*)$: candidates are screened, not injections
chosen to suit one of them. $\mathcal C_P$ in particular is one situation whose effect genuinely
depends on the commit edge.

### 74.3 The detection protocol

For a candidate $U$ and architecture $A$, with $u^*_{A,U} := g_U(\xi_A^*)$:

1. **coverage.** $u^*_{A,U} \neq \varnothing$, i.e. the candidate can represent the witness at all.
   A candidate that cannot has failed for a structural reason, recorded with its failure mode — this
   is a different defect from a metric that did not move;
2. **detection.** $\exists u \in U: V_{W+\Delta W_A^{\text{cal}}}(u) \neq V_W(u)$;
3. **direction at the witness.** $\operatorname{sign}\bigl[V_W(u^*_{A,U}) -
   V_{W+\Delta W_A^{\text{cal}}}(u^*_{A,U})\bigr] = s_A^{\text{expected}}$, where that sign is
   independently stated as above — otherwise the cell reports detection only.

A cell satisfying 1–3 is `DETECT`; failing any is `BLIND`, with the failure mode recorded. Values are
measured by the **audited environment** (A85 §73.2.1); no index, hash, modulo or resampling adapter
may stand in for a measurement.

### 74.4 The $P$ canary, and the bounded conclusion

$$\boxed{\text{the } P \text{ injection must genuinely traverse }
z^{\text{proposal}} \to C_P^L \to z^{\text{in-force}}}$$

The kernel realises the edge exactly this way: the process commit maps the proposal to the option in
force, and the episode starts from that option. A unit that fixes $z$ at its entry therefore bypasses
the edge, and — with type, state and CRN correct and the value genuinely measured — is recorded

$$\boxed{\texttt{STRUCTURALLY\_BLIND\_FOR\_P}}$$

and rejected. The screening's conclusions are bounded by what was registered:

$$\boxed{\exists U \in \mathcal U^{\text{pre}}_{\text{unified}} \text{ passing } D_Q, X, P
\;\Longrightarrow\; \text{the unified family survives structural screening}}$$

$$\boxed{\forall U \in \mathcal U^{\text{pre}}_{\text{unified}},\ \exists A: \ blind(U, A)
\;\Longrightarrow\; \text{every preregistered unified candidate is rejected, which triggers
architecture-specific specification directly}}$$

The second is **not** the claim that no unified domain can exist: that would require

$$\boxed{\mathcal U^{\text{pre}}_{\text{unified}} \text{ complete for admissible unified designs}}$$

which is neither proved nor claimed.

$$U_3 \text{'s entry is not exclusive to that case.}$$

$$\boxed{\text{detectability is necessary, not automatically sufficient}}$$

A survivor is **admissible, not selected**: it may still fail A85's other properties — nominal
closure, a definable unaffected region, interpretability, calibration stability — and if every
survivor fails them, the architecture-specific branch must remain enterable. A86 therefore does not
make $U_3$ conditional on a structural rejection alone.

### 74.5 What this amendment does not do

It chooses no unit, runs nothing, authorises no seed and **authorises no calibration**. It sets no
$T$, no $N_{\text{eval}}$, no grid value, no $\Delta_{\min}$ and no Retention form, and changes
nothing in A79 or A85. Its output, when the calibration is eventually run, is a DETECT/BLIND matrix
plus a structural admissibility conclusion — not a final evaluation unit.

It records the dependency owed before B2-4b: if the chosen $u$ is not the decision-context type,
B2-3's compatibility closure comes first, because `UnaffectedSet.contexts` and the
`state_parity_*` / `visited_complement` candidates were closed against the old unit ontology and do
not inherit a new one by being called candidates.

### 74.6 The freeze boundary, and what A87 owes

$$\boxed{\text{A86 freezes the screening method; the canaries are A87's; calibration runs after
A87}}$$

A86 deliberately registers the fixture **schema** $\mathcal C_A$ and the projections $g_U$, and not
the fixtures themselves: which `QAddress`, which `ControllerSite`, which process-proposal mapping,
which $\kappa/\varphi$ scene and which witness each $s_A^{\text{expected}}$ describes are the
instances that make a screening mean anything. Leaving them to the calibration code would be exactly
the implementation-chooses-the-definition error this sequence exists to prevent, so

$$\boxed{\mathcal C_{D_Q},\ \mathcal C_X,\ \mathcal C_P \text{ are frozen by A87, before any
calibration run}}$$

A87 freezes those three fixtures concretely — the edit, the witness, the independently stated
expected sign, and for each candidate the projection's image — and only then may the seedless
structural screening be executed. **A86's freeze does not authorise the run.**

Finally, a promotion note: this draft's revision is **not** cherry-pickable into `rebuild`, because
its ancestry contains a commit made on an unresolved conflict. Promotion must rebuild this file from
`rebuild`'s frozen tree plus this section's clean content, and then record the status change.

---

## 75. A87 — the injection fixtures (reserved; not yet written)

A86 §74.6 fixes the boundary this section exists to fill:

$$\boxed{\text{A86 freezes the screening method} \;\to\; \text{A87 freezes the canaries}
\;\to\; \text{only then may the seedless screening run}}$$

**Nothing is frozen here yet.** This heading is reserved so that A86's references to A87 are
resolvable rather than dangling, and so that the obligation is visible in the amendment record
rather than only in a draft branch.

When it is written, A87 must contain, for each $A \in \{D_Q, X, P\}$, a concrete fixture

$$\mathcal C_A = \bigl(W_{\text{pre}},\ \Delta W_A^{\text{cal}},\ \xi_A^*,\
s_A^{\text{expected}}\bigr)$$

with the edit, the semantic witness and the independently stated expected sign all named, and with
each preregistered candidate's projection image $g_U(\xi_A^*)$ — before any calibration run. Until
then the structural screening of A86 §74.3 is **not authorised**, and neither is any change to
`runner.py` on its account.

| # | what | severity | status |
|---|---|---|---|
| A87 | the concrete injection fixtures $\mathcal C_{D_Q}, \mathcal C_X, \mathcal C_P$ that A86 §74.6 requires before the screening may run | **P0 (interface)** | **reserved -- not yet written** |

## 64. Summary and what remains open

| # | what | severity | status |
|---|---|---|---|
| A1 | $z$ emitted actions; $Q_D$ disconnected from behaviour | **P0** | fixed |
| A2 | outcome-relevance filter erased redundant co-faults; $Z$/$B$ conflated | **P0** | fixed |
| A3 | tape key too coarse; invariant too strong | medium | fixed |
| A4 | map made $z_2$ impossible; $z_4$ self-contradictory | high | fixed |
| A5 | $R_{\text{module}}$ action level and $R_{\text{trajectory}}$ unconvertible | high | fixed |
| A6 | identifiability rows per label, not per case; tape set unbounded | high | fixed |
| A7 | execution primitive replaced the whole controller | medium | fixed |
| A8 | $u_t$ visibility implicit; `01`/`11` disagreed | medium | fixed |
| **A9** | four options were four names for one policy | **P0** | fixed |
| **A10** | identifiability gate not budget-aware; wrong primitive; resample miscounted | **P0** | fixed |
| **A11** | latent case not closed; derived $B$ enumerated as free; $M$, $\kappa$ missing | **P0** | fixed |
| A12 | P3 false by counterexample; P4 unsatisfiable | high | fixed |
| A13 | $C$ not cleaned up; $A$ collided with the action set | medium | fixed |
| A14 | reward equivalence claim ignored the step cost | high | fixed |
| A15 | $R_{\text{trajectory}}$ could never propose a process repair | medium | fixed |
| **A16** | proposed execution order was circular; risked a second simulator | **P0 (process)** | fixed |
| **A17** | option automata were obligation prose; $do(d_t)$ vs obligation unanswered | **P0** | fixed |
| **A18** | the frozen tape key list did not exist (`e.g.`) | **P0** | fixed |
| **A19** | execution order still circular — DP must precede `route_check` | **P0 (process)** | fixed |
| A20 | admissible sets not bounded by physical legality | medium | fixed |
| A21 | retired symbols live; audit blind to superseded semantics | medium | fixed |

This table covers rounds 1–3 only. Later amendments (A22–A51) are indexed by
section above; the most recent is:

| # | what | severity | status |
|---|---|---|---|
| **A51** | Gate L splits into Gate_Z and Gate_B, and **both** fail; replacing $Z$ by $B$ is a change of V0.1R's scientific question, not a bug fix | **P0 (spec)** | frozen — superseded by A54 for the target, retained for the split |
| **A54** | configured / fired / difference-making were one symbol; V0.1R's target becomes $Z^{\text{fire}}$; Gate_fire FAILs on 600 classes, residual **100% $P$** | **P0 (spec)** | frozen — denotation resolved by A55 |
| **A55** | $Z_P$ is commit/routing integrity (not a bad plan, not unsuited strategy); process proposal audit added; **Gate_fire PASSES**, $B_{\min} = 3$ vs $B_Q = 4$ | **P0 (spec)** | frozen — **first PASS**; V0.1R precondition met |
| **A56** | semantic propagation of A54/A55 through `02`, `04`, `06`; lattice gains $do(C_P{=}\text{identity})$; arms renamed `QueryOnly`/`SeqThenQuery`; Gate E pre-check clean | high | complete |
| **A57** | commit repair first-class in the kernel (own node, composes, counts in $\lvert r\rvert$); canary 10/10 held; **Gate E PASS** on full support, all ties kept, trace-level no-op invariant clean | high | complete — semantic suite next |
| **A69** | V0.2R typed information boundary: three native alphabets with a frozen evaluator-side $\eta_R$ that must not read $Z^{\text{fire}}_{\text{truth}}$; episode-local $\Gamma(I)$; `OracleCreditAdapter` separated from the ordinary method path; $\varnothing \neq \{\texttt{Unknown/NoWrite}\}$; `agent_writeable` assigned including `Strategy = false`; S2 as interface/typing/information-flow only | **P0 (spec)** | frozen — interface and typing; later scientific *reading* amended by A70–A72 (`17` §9). **Logged late: mechanical provenance registration only** |
| **A71** | truth was built from **generic** type names while predictions are concrete addresses, so A70's census was systematically false-negative; truth is now indexed from $R^{\text{mech}}$ descriptors, **A70's numbers are voided**, and $Z^{\text{fire}} \not\Rightarrow \Gamma^\ast$ — cause identification does **not** imply site identification (14 of 893 **locator** classes $X^{\text{loc}}$, 0.1881% of DGP mass) | **P0** | frozen — identifiability negative against a perfect $Z^{\text{fire}}_{\text{truth}}$ |
| **A72** | `PublicSCMView` / `CausalSetLocator` grant recorded: factual-consistency inversion (simulate hypothetical worlds) is not an intervention query; $\hat\Gamma_{\text{CSL}} = \Gamma^+$ with $\Gamma^-$ as the certain diagnostic, $B_Q = 0$, equivalence to be gated at 893/893 against an **independently sourced** $\Gamma^+_{\text{eval}}$ | **P0 (spec)** | frozen — implementation and gate pending |
| **A73** | locator evidence quotient and public feasible support: $X^{\text{loc}}_{0.2}=(\text{rows},Z^{\text{fire}})$ with $q$ dropping the redundant feedback channel, so **893 is the locator main gate** and $X^{\text{obs}}=(rows,feedback,Z^{\text{fire}})$'s **4,513** is only the observational refinement; $\mathcal L_{\text{public}}$ = canonical grammar candidates **passing public forward-feasibility**; route C's semantic source is `gate_stage2._domains` + `canonicalise`; support closure as **exact set** | **P0 (spec)** | frozen — rows-only **licensed by the 4513→893 gate** (9/9 PASS); one violation voids it and reverts the gate to 4513. **Its census Module row and endpoint-degeneracy claim are VOIDED by A74** |
| **A74** | the A73 census chose Module's H/L from $\Gamma^\ast$ instead of $Z^{\text{fire}}$, so evaluator truth entered the proposal construction; footprint is exactly $Z^{\text{fire}}=00000$ (**17,280 worlds, 43.86% of DGP mass**), where the frozen rule abstains but reading the truth emitted $H$, turning abstention into a coarse substantive verdict (violating $\varnothing \neq \{\texttt{Unknown/NoWrite}\}$). Corrected: Module Cov(count/mass) **0.9834/0.5614**, FCR **0.7958/0.4622**; the co-primary pair is **not** degenerate — Coverage punishes abstention, FCR over-credit | **P0 (census/implementation)** | frozen — semantic canary + information-flow assertion added, both with demonstrated power; **no design change**, only the frozen rule restored |
| **A75** | V0.3R semantic rebase: the subject becomes the **persistent learning update**, not runtime repair, with $R^{\text{mech}} \neq W^{\text{update}}$; $B_0: \Gamma_r^\ast \to \mathcal W(\Gamma_r^\ast)$ outputs a candidate family; seven ownership criteria including **addressable** and **contract-preserving** (learner baseline has **no fault privilege**); **regime-specific** stratification $S_{T,\pm}$ / $S_{P,\pm}$ with **no whole-support primary mean**; regimes **T** (harm / non-internalisation), **P** (benefit / recovery, future endogenous to $\Delta W$), **I** (secondary, no numbers yet); a **new** persistent-manifestation family $J^L = (J_P^L, J_D^L, J_X^L)$ defined by **(predicate, source-separated intermediate)** while **$Z^{\text{fire}}$ is left untouched**; **$\Gamma_T^\ast \neq \Gamma_P^\ast$** with formal manifestation address sets; a fair decision defect family at the induced-policy layer with address-count budgets; a split `FutureConsequenceView` / `UpdateLedger` with **dependency closure**, a **constructor-flow gate** and a laundering mutation; and two authorised-but-unimplemented kernel extensions | **P0 (spec)** | **frozen — specification only, no implementation authorised**; further change requires a new amendment; `08` still to be rebased |
| **A76** | V0.3R B1 update-law contract: B1 owns only $W^{\text{update}} \to \Delta W$; four information tiers $L_0$–$L_3$; Decision targets as **local return-to-go** $G_t^F$ / $G_t^{CF}$; the counterfactual is a **full-episode replay** with only $do(d_t{=}a_t^+)$ added plus a prefix-equality invariant, never a suffix simulator; the $-1$ constant and $+1$ target **retired** (not rescaled); `PositiveAlternative` retired as information-deficient at $L_1$; the $a^+$ guard is **live** (3,600 empty-alt addresses, co-fault only: `D+E` 2.38%, `X+D` 4.76%, `D` alone 0%), with a **per-addressed-context** ledger taxonomy `{APPLIED, EVALUABLE_NOOP, NO_VALID_ALTERNATIVE, PROTOCOL_ERROR}` in which `APPLIED` means the **store changed** (architecture-neutral, not "a scalar was written"), `N_scalar` is accounting only, and `PROTOCOL_ERROR` is a **fail-stop excluded from B2 scoring**; a locality-matched `LocalOracleRestore` inside the matrix with A75's global `OracleRestore` outside it and the lower-tier aliases declared non-treatments; the $\rho_A$ credit-unit→store-key resolver; and three execution invariants (regime-blind, address locality, snapshot + atomic commit) | **P0 (spec)** | **frozen — specification only, no implementation authorised** (dated from the taxonomy correction); further change requires a new amendment |
| **A77** | the $D_Q$ row, and the information contract that replaces the boolean `requires_alternative`: a closed opaque `Tier` enum declared exactly once with a `None` sentinel; delivery as an **exact per-(architecture, tier) field set** — $D_Q$'s $L_0=\{a_t^F,G_t^F\}$, $L_2=\{a_t^F,G_t^F,a_t^+,G_t^{CF}\}$, $L_3=\varnothing$ — with **same cell ⇒ same envelope**, the reference constructed through the same field construction, and `scalar write law ∧ L_1 ⇒ PROTOCOL_ERROR`; `NoWriteRef(ℓ)` as one object per cell with a substantive treatment, sharing one no-op plan and excluded from the treatment count; the $Q$ store as a sparse override table on an **injected frozen** `QReferenceView` (`QAddress` entries inside a `DecisionAddress` budget, identity canonicalisation to deletion, co-residence of $P_D^L$ and $Q_D^L$ a **construction-time** `PROTOCOL_ERROR`); **domain closure** $\operatorname{dom}(Q_D^L)\subseteq\operatorname{dom}(\texttt{QReferenceView})$ with the 13,824-row census as its evidence; $F_t=(a_t^F,G_t^F)$ built from the **learner-visible rows only**; the **frozen reverse Bellman fold** for $G^F$ and $G^{CF}$ (`sum`/`fsum`/reordering prohibited — measured 278/278 exact vs 92/278 mismatch); $G_t^{CF}$ as a full replay carrying `DecisionReadView_pre` with the intervention at $t$ **replaced**; the $D_Q$ matrix (4 independent treatments, no $L_1$ cell, `LocalOracleRestore` a genuinely new row-scoped operation); **owner-based locality** with one address-plan and one receipt per credited context and the row operation lowered by the slice; and the scalar ledger with an **effective-$Q$** $\Delta$ and $N_{\text{scalar}}=0 \iff \Sigma=0 \iff fp_{\text{pre}}=fp_{\text{post}}$ | **P0 (spec)** | **frozen — specification only, no implementation authorised**; implementation in the frozen order: slice refactor → $Q$ store/read → $L_0$ → $L_2$ |

| **A78** | $L_3$ `LocalOracleRestore` on $D_Q$ as A77 §65.12's **fifth** implementation step — one step, one commit, no mixing, and no new scope for the four already-closed steps; the cell's `NoWriteRef(L3)` alongside its treatment, giving $\lvert\text{treatments}\rvert(D_Q)=4$ exactly as A76 §63.8 froze ($D_{patch}$ stays 3); the B1 law domain fixed as **every credited address for $L_2$ and $L_3$ alike**, with `NO_VALID_ALTERNATIVE` addresses remaining in the population and $L_3$ forbidden to key its domain on $a^+$ availability; "no reference" scoped to the **lowering** and to *no new* $L_3-specific reference entry point, since §65.10's deleted leg still needs the existing `q_reference`; the row operation kept a **B1** object so `owner_Q` stays a `QAddress` function and the substrate does not learn an update law; lowering as an explicit **pre-commit phase** against **one** frozen pre-state, with status, $n_{\text{changed\_addresses}}$ and the scalar accounting computed from the **lowered concrete edits**; a $D_Q$-only law implementation beside the untouched $D_{patch}$ alias, with no architecture branching inside a law; and the gate obligations, including **idempotence** ($k=0$, `EVALUABLE_NOOP` on a second run, i.e. the lowering reads its own run's pre-state) and a **poison-evidence** empty-cell gate proving $L_3$ reads no evaluator-side inputs | **P0 (spec)** | **frozen — implementation authorised in this step only**; further change requires a new amendment |
| **A79** | V0.3R **B2 pre-registration**: the stage that answers *what did this write do to this learner's future*, and a pre-registration in the strict sense -- no code, no seed. It **supersedes `08-V03R.md` on B2** (whose Block 2 arms A76 retired and whose process reading $do(z=z')$ the frozen reading rejects) while leaving `08` §2 unaddressed. It fixes $Y^{\text{future}}=\{\text{FutureUtility},\text{Collateral},\text{Retention}\}$ as **three independent dimensions with no composite primary** (a weighted score would let utility buy collateral); keeps $T$ and $P$ as **separate populations that may not be pooled**, with $T$'s primary being harm/erroneous internalisation against a weakly dominating `NoWrite` and $P$'s requiring future rollout **endogenous to $\Delta W$**; freezes $\mathrm{RMST}(T_{\max})$ primary with $\mathrm{DeficitAUC}$ mandatory by reference to `05` §8 ($K=3$, right-censored); defines primary collateral as future behavioural spillover on a set that is **truth-blind, arm-blind, pre-update, and identical across a scene's paired arms** with the unaffected set constructed truth-blind under A75 §62.10's four gate layers, and keeps $N_{\text{scalar}}$/$\sum|\Delta\theta|$ in $\texttt{UpdateLedger}$ as intervention cost because *writing less is not causing less collateral*; retains **Retention** as a dimension **whose confirmatory form must be defined for every seed** ($\tau$-conditioned forms demoted to conditional descriptive diagnostics), the choice among all-seed forms being a declared development-stage decision on measurement properties only; makes `LocalOracleRestore` the **matrix-matched normalisation ceiling** and the global oracle a **diagnostic ceiling only** that may not be a treatment's denominator; fixes **tier-matched contrasts** so $L_3$ beating $L_0$ measures headroom, not merit; and states that **the Process/Controller B1 alias-write paths are B2 prerequisites under their own authorisation**, because ``D6/B1 CLOSED'' is the Decision path and not all three stores. `05` governs unchanged, with $T$ frozen from the baseline only and no treatment curve inspectable beforehand; **V0.3R PASS is a conjunction** of FutureUtility benefit, no unacceptable Collateral, the Retention criterion and the $T$-regime harm constraint -- a gate rather than a weighted sum, so the outcome space is never collapsed -- and **V0.4R begins only on V0.3R's FINAL confirmatory PASS**, a diagnostic look at 100/200/300 being neither a PASS nor able to open it. | **P0 (spec)** | **frozen — pre-registration only; no seed collected, no code authorised**; further change requires a new amendment |
| **A80** | the $X$ and $P$ B1 paths and the substrate refactor they need, as A79 §67.8's prerequisites -- **authorisation text only, no code**. The replacing plan's two steps are **three**: a generic address/receipt substrate refactor first, because the shared B1 objects are Decision-shaped (`AddressPlan.address`, `DecisionWriteReceipt.address` and its canonicalisation, `SliceDescriptor.owner`) while $\rho_X$ yields a site handle and $\rho_P$ an integer, and an implementer given only "$X$ then $P$" would have to invent the address contract at code time. Step 1 generalises **by type, not by duck typing** -- `address: Any` would discard the nominal closure -- keeps per-architecture strict domains, typed store addresses, $owner_\alpha$ and deterministic canonical receipts, keeps same-cell same-admissibility, and must move no number (five self-checks still pass, $D_{patch}$ still `ENCODING_ONLY`). Step 2 implements $X$ as frozen ($C_X^L(\rho_X(\texttt{ControllerSite})) \leftarrow a^{cmd}$, $L_0$ with $\lvert$treatments$\rvert=1$, $L_3$ an alias that **reuses the same operation implementation**), with $a^{cmd} \in A_z(m,s)$ because a learner write does not inherit fault privilege (A75 §62.3). Step 3 implements $P$ as frozen with $P_{id}\colon L_1$ and **not** $L_0$ -- the factual rows never carry $z^{\text{proposal}}$ -- and forbids **assisted-input laundering** ($P_{id}$ at $L_0 \Rightarrow$ `PROTOCOL_ERROR`), requiring the $L_1$ envelope to deliver the proposal explicitly and the integer-semantics process key to pass an exact type check before domain membership. Authorises **no B2 runner, no $\texttt{FutureConsequenceView}$, no $\texttt{BehavioralCollateral}$, no seed of any stage**, and may not be used to touch $D_Q$, to repair the frozen $D_{patch}$ asymmetry, to change an A79 endpoint or threshold, or to begin V0.4R. The exact delivery rows are **written here rather than deferred** (A77 §65.2's "when implemented"): $fields(X,L_0)=\{a^{cmd}\}$, $fields(X,L_3)=\varnothing$, $fields(P,L_1)=\{z^{\text{proposal}}\}$, $fields(P,L_3)=\varnothing$, and an empty cell acquires **no arm and no same-tier reference** merely because the infrastructure could express one. $X$'s $z,m$ come from the **unique learner-visible factual row** for the visited site, used only by a pre-plan validator that **both arms share**, without widening the law's $\{a^{cmd}\}$ delivery. $P$'s order is frozen -- **cell-level $\rho_P$ resolution before any arm planning**, the resolved true-int key as the locality unit, the $L_1$ envelope delivering $\{z^{\text{proposal}}\}$ to reference and treatment alike, and $\texttt{Edit}(\texttt{PROCESS},z,z)$ so the $L_3$ alias reuses the same plan function -- under the distinction $\boxed{\text{address resolution} \neq \text{information delivered to the law}}$. Step 1 must also prove the generalisation with a **test-only synthetic second domain** (an $A$-slice rejects a $B$-address, a stand-in is refused, and relaxing the validator reddens the gate) and its canonical form must be **injective on the legal domain**, not merely deterministic, since an $X$ canonical omitting $a^{cmd}$ would give two credited sites one receipt identity. | **P0 (spec)** | **frozen -- three implementation steps authorised, one commit each, own gates each; further change requires a new amendment** |
| **A81** | **domain identity is out of band from the canonical ledger**: the contract's address identity is the pair $(\text{domain tag}, canon_\alpha(\text{address}))$ while the **frozen ledger serialises only** $canon_\alpha(\text{address})$, because A77 \u00a765.12 puts the architecture in the arm descriptor and a tag in the receipt bytes would be a ledger **schema change** -- which is why the $D_{patch}$ baseline stays `ENCODING_ONLY` instead of becoming `DRIFTED`. It rules that **cross-domain admission comes from `require_credited`, not from comparing tags** (two architectures may legitimately admit value-equal addresses, so a tag comparison is neither necessary nor sufficient, and a gate asserting two tags differ proves a property of two constants rather than of admission); restates that the runner asks the domain for every architecture while the *policy* executed is that architecture's own; and fixes the reading of \u00a768.2 without editing A80. Writes no code, moves no number, collects no seed. | **P0 (spec)** | **frozen -- clarification only**; further change requires a new amendment |
| **A82** | **the concrete $\Gamma$ encoding is the wire contract, and A69's index notation is not a spelling**: $\texttt{ControllerSite}_t$ is mathematical index notation while A71's concrete encoding ($\texttt{ControllerSite}_{x,y,t,a^{cmd}}$, the string `PublicSCMView.credit_unit` emits for a `ControllerFault`) is the implementation interface, so V0.3R B1's $\rho_X$ consumes **that same unit** -- with $\texttt{ControllerSite}_t$ **not** accepted as a compatibility alias (two wire spellings for one $\Gamma$ unit would reopen the ambiguity A71 closed) and $\texttt{Decision}_t$ refused (A69's two families, A76 §63.10's two images). The parsed fields are the unit's identity: $(x,y,t,a^{cmd})$ must equal the factual row's, $\kappa/\phi$ come from the row, and $\mathrm{render}(\mathrm{parse}(u)) = u$ keeps the namespace injective -- so a descriptor cannot decay into decoration. A test-only cross-layer gate resolves a method-produced unit and a hostile gate tampers with each field; production code imports no method layer. A75's chain begins at $\Gamma^\ast$, which is why this is a cross-layer interface rather than a downstream detail. Writes no science, moves no number, collects no seed. | **P0 (interface)** | **frozen -- clarification only**; further change requires a new amendment |
| **A83** | **B2 implementation authorisation, and the boundary it does not cross**: A80's three steps are CLOSED (Step 1 `6f78949`/`3eeec3a`, reproducibility maintenance `aab5727`, Step 2 `e1c7141`/`81cb162`, Step 3 `5fcb750`/`c311b42`), so A79 §67.8's Process/Controller prerequisites are **SATISFIED** -- which authorises implementing the B2 measurement stage (`FutureConsequenceView` and its builder, the future rollout, RMST with mandatory DeficitAUC, the Collateral and Retention candidate machinery, the paired runner) and **nothing else**. $\text{implementation authorisation} \neq \text{seed authorisation}$: NO smoke, development or confirmatory seed, and no V0.4R, until the instrument's own gates close, because dev data from an unvalidated instrument is not dev data (truth leakage, arm leakage, post-update selection leakage each need a gate that can go red). §67.11's "five B1 mutation self-checks" is restated as the **measured eight-table set** (Q 14, B1 13, L0 8, L2 11, L3 11, address-domain 6, X 10, P 11) plus the $D_{patch}$ `ENCODING_ONLY` binding, since reading the historical count literally would silently drop exactly the three tables A80 added. Every open item stays open and is decided at the development stage under §67.5/§67.9/§67.10 -- the unaffected-set construction, the all-seed Retention form, $T$, $N_{\text{eval}}$, $\mathcal G_{\text{ckpt}}$, each $\Delta_{\min}$, and $N_{\text{train}}$ (which may not be named yet). Writes no code, moves no number, collects no seed. | **P0 (process)** | **frozen -- authorisation only**; further change requires a new amendment |
| **A84** | **the DeficitAUC numerical-integration contract**: `05` §8.3 froze a continuous integral with a $1/T_{\max}$ normalisation, and B2-2's first implementation realised it as an unnormalised left-rectangle sum — wrong in the normalisation **and** in the quadrature rule, which was frozen nowhere and was therefore the implementation choosing an estimator. Frozen now: trapezoidal integration on the real episode grid, $\mathrm{DeficitAUC} = \frac{1}{T_{\max}}\sum_i \frac{d_i+d_{i+1}}{2}(t_{i+1}-t_i)$ with $d_i=[V_{\text{pre}}-V_{t_i}]_+$, on the grounds of assumption-minimality (linear interpolation between adjacent observations, rather than left-hold's extra assumption that a measurement persists across its whole interval); calibrated analytically on constant and linear deficits, seedlessly. Also frozen: the curve spans the horizon ($episodes[0]=0$, $episodes[-1]=T_{\max}$, $0\le t_i\le T_{\max}$), a short curve is refused rather than padded, and a recovery window completing past $T_{\max}$ does not qualify. Terminology: the per-seed $\min(\tau,T_{\max})$ is `restricted_time`, **not** RMST, which is the cross-seed expectation and belongs to B2-4. Re-opens no A79 endpoint, sets no design quantity, collects no seed. | **P0 (numerics)** | **frozen -- clarification only**; further change requires a new amendment |
| **A85** | **the behavioural measurement contract for future performance**: A79 §67.4 froze `BehavioralCollateral` and its unaffected set's four properties but no executable $c \mapsto V_W(c)$, and B2-4 filled the gap with an adapter mapping a context coordinate onto a temporal reward index. Frozen here as **properties**: measured by the audited environment rather than assembled by an adapter; pre from the raw pre-update state and post from each arm's own post-update state; one shared evaluation scene and CRN draw, so a difference can only come from $\Delta W$; a closed nominal measurement $V_W: U_{\text{unaffected}} \to \mathbb R_{\text{finite}}$ refusing missing **and** extra units, never an arbitrary callable; behaviourally load-bearing for every architecture without deciding that one unit type carries all three; and calibrated on synthetic injected spillover **per architecture**, because correct types can still be structurally blind. Also records that $V_{\text{pre}}$ is already frozen by `11` §12.3 and §13 item 13 (measured on $Q^{*}$, same $N_{\text{eval}}$ and evaluation scenes, shipped in the reference artifact, never re-measured) and that $V_{\text{pre}} \neq V_{\text{unaffected,pre}}$ despite the shared word. It **poses without answering** whether the evaluation unit is a unified scene domain or architecture-specific domains, naming the $P$ counterexample that decides it ($z^{\text{proposal}} \to z^{\text{in-force}}$ cannot be seen from a context that already fixes $z$). Chooses no candidate, sets no design quantity, collects no seed, writes no code, and **does not authorise implementation to choose the evaluation unit**: the unified-vs-architecture-specific decision is the next specification question, to be settled by a seedless structural/calibration study (inject known spillover per architecture, keep the $P$ counterexample as canary, discard a candidate that is structurally blind). | **P0 (interface)** | **frozen -- properties only; evaluation unit unresolved; further change requires a new amendment** |
| **A86** | **the evaluation-unit structural screening method**: A85 left one question open (a **unified** evaluation scene domain or **architecture-specific** domains) and A86 freezes the **method** of screening it, explicitly **not** authorising calibration --- the concrete canaries are A87's, and until they are frozen the screening may not be run. Pre-registers $\mathcal U^{\text{pre}}_{\text{unified}} = \{U_1, U_2\}$ with a **deterministic projection** $g_U$ from a semantic witness to a unit: $U_1$ = the decision triple $(s,z,m)$; $U_2$ = an **evaluation scene unit** whose closed field surface is $(\kappa, \varphi, \text{base option}, \text{reference artifact})$, entered upstream of $C_P^L$ so $z^{\text{in-force}}$ is produced during evaluation. Units are **pre-constructed and arm-blind** (what is post-update is the measurement, never the unit's identity), and the **measurement schedule is excluded from unit identity** --- the grid is A83-open and interrogates a unit, so screening uses a nominal test schedule and is re-run against the final grid before its conclusion travels. The shared thing across candidates is the **semantic witness** $\xi_A^*$, not a representation: each candidate projects it, and $g_U(\xi) = \varnothing$ is a coverage `BLIND`. $s_A^{\text{expected}}$ is an **independently stated** expected sign of the behavioural loss --- not the sign of the measurement it is checked against, which was a tautology --- and a canary whose direction needs the measurement has no direction gate for that cell. Conclusions are bounded: a passing preregistered candidate leaves the unified family admissible; rejecting all of them triggers architecture-specific specification directly but is **not** a proof that no unified domain exists (that needs a completeness proof A86 does not claim); and since detectability is necessary but not sufficient, $U_3$ is **not** conditional on structural rejection alone --- a survivor that later fails A85's other properties still leaves the architecture-specific branch enterable. Chooses no unit, runs nothing, authorises no seed. | **P0 (interface)** | **draft -- awaiting review; not yet frozen** |

---

## 40. A52 — the identifiable quotient is too coarse to merge

**Found by**: reading out what the current interface supports, without changing
anything — no environment edit, no new target, no added query.

Define $b \sim b'$ iff some latent world carrying $b$ and some world carrying
$b'$ cannot be told apart by any history-dependent safe query policy. The
relation is exactly "no single query separates the pair": a tree splits worlds
only along query responses, and if $r_1, r_3$ were split while neither
$r_1, r_2$ nor $r_2, r_3$ is, then $r_2$ is legal on that query and must return
one of the two responses, differing from the other — so one of those pairs was
split. Hence it is transitive, and components of the complement-of-separability
graph give the quotient **exactly**, not approximately.

**Result** (`scripts/a52_quotient.py`, `outputs/rebuild/a52_quotient.json`):
723 classes span more than one $B$; 432 carry an inseparable $B$ pair; every such
per-class component holds exactly **two** $B$-vectors; 17 inseparable pairs
collapse to **7** components of $\mathcal B/{\sim}$; collapsing the $P$ and $E$
coordinates makes **all 432 vanish**, and $\{P, E\}$ is the minimal such set —
size 2.

$$\boxed{\widetilde{\mathcal B} = \mathcal B / \sim \;\text{keeps}\; (D, X, U) \;\text{and discards}\; (P, E)}$$

**Why this blocks the merge.** The two coordinates the interface cannot separate
are **exactly Process and Environment** — the distinction this project exists to
study. Merging them is not a bookkeeping move; it deletes the independent
variable. So `03` §4's option 1 is **unavailable here**, not because merging is
illegitimate in general but because this particular quotient destroys the
question.

**What remains.** Neither merge (destroys the axis) nor $do(Z_i{=}\text{off})$
(circular, A51) is available. The only remaining direction is a genuinely new
diagnostic capability — a process-audit channel for $P$, an independent
plant/environment channel for $E$ — and it must first be argued that a *real*
learner could possess it, then the whole gate re-run. That argument is not made
here, and no query is added.

There is a deeper reason to state plainly, because it bounds what any repair can
achieve: $B_i$ is *defined* as the outcome difference caused by applying the
repair of fault $i$. So $B$ is identifiable exactly to the extent the learner can
already apply repairs — and repair is what the chain is trying to *learn*
(V0.3R). A gate that certifies $B$ by granting repair queries certifies nothing.
Gate_B's failure is therefore not an oversight but a load-bearing feature of the
task as currently posed.

### The pattern across the three rounds

Round 1 produced four P0s, round 2 four more, round 3 three more (A17–A19). They
are not random. Three recurring shapes now account for nearly all of them:

**A fix that connects two objects can expose a degeneracy between them.** A1
connected $z$ to $Q_D$; only then was it visible that four identical slices
converge to one policy (A9).

**A property described in prose is not a property.** A4, A12, and now A17 — three
separate amendments from asserting automaton, route or reachability properties
without enumerating them. Every property in the spec is now an assertion
discharged by enumeration.

**A deferred decision is a decision.** A18 is the sharpest case: the spec declared
a list frozen, and the list did not exist. "Declared in full before
implementation" is not a specification; it is a note to self. Anything the kernel
must implement is now written out, or explicitly marked as the implementer's free
choice in `00-INDEX.md` §8.

### What is still open after this round

* **P1–P4 are all enumeration-pending.** None is claimed. They are answered by
  `route_check.py` against the kernel, and — per the reviewer's own point — they
  **do not block the kernel**: they are questions the enumerator answers *after*
  the kernel exists.
* $B_{\min}^{\text{adaptive}}$, $\lvert\mathcal L\rvert$,
  $\lvert\Theta_{C_X}\rvert$ and $\mathcal E$ are uncomputed. `03` §1.1 forbids
  sampling and calling it exhaustive.
* The identifiability audit for $B$ is specified (`03` §1.3) but not yet run.

### Authorised next step

$$\boxed{\text{minimal SCM kernel only — } \texttt{src/rfl\_rebuild/env/kernel.py}}$$

state transition, semantic tape (the three frozen keys), the four option
automata, and the `do`-operators with the well-formedness rule of §2.4.7. No
training, no RFL, no seeds, no metrics, no DP. The exact DP solver is authorised
separately once the kernel is complete.
