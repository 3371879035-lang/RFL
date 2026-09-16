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

## 44. Summary and what remains open

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
