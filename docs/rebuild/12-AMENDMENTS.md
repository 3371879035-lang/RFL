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

## 18. Summary and what remains open

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

### The pattern across the two rounds

Round 1 produced four P0s; round 2 produced four more. They are not random. Two
recurring shapes account for nearly all of them:

**A fix that connects two objects can expose a degeneracy between them.** A1
connected $z$ to $Q_D$; only then was it visible that four identical slices
converge to one policy (A9). A2 separated $Z$ from $B$; only then was it visible
that $B$ needs its own identifiability audit (A11).

**A property described in prose is not a property.** Three separate amendments
(A4, A12, and the P2 reclassification) came from asserting route or reachability
properties without enumerating. This is why the spec now says *assertion,
discharged by enumeration* wherever a property is claimed, and why the grading
language "available / not established" has been removed.

### What is still open after this round

* **P1–P4 all enumeration-pending.** None is claimed; witnesses come from
  `route_check.py` against the kernel.
* $B_{\min}^{\text{adaptive}}$, $\lvert\mathcal L\rvert$, $\lvert\Theta_{C_X}\rvert$
  and $\mathcal E$ are all **uncomputed**. `03` §1.1 forbids sampling and calling
  it exhaustive; if a factor must shrink, the spec says so.
* The identifiability audit for $B$ is specified (`03` §1.3) but not yet run.
* The option waypoint automata in `02` §2.3 are specified by obligation, not yet
  by transition table.

### The authorised next step

$$\boxed{\text{minimal SCM kernel only}}$$

`src/rfl_rebuild/env/kernel.py` — state transition, semantic tape, option
constraints, `do`-operators. No training, no RFL, no seeds, no metrics. Every
later artifact imports it. Nothing else is authorised until Gate E and Gate L have
been run against it.
