# 03 — Identifiability gate

**Status:** FROZEN. Hard gate. Depends on `01-OBSERVATION-MODEL.md` and
`02-SCM.md`.

$$\boxed{\text{No seed collection may begin for a version until its identifiability gate PASSES.}}$$

If a cause cannot be distinguished from another cause by any query the *learner*
is allowed to issue, then a method that fails to distinguish them has failed for
information-theoretic reasons. Reporting that as "RFL does not work" would be a
false negative manufactured by the experimental design. This gate exists to make
that impossible.

---

## 1. Definition

A **latent case** is a full assignment of the **generator's free variables** — and
of nothing else:

$$\boxed{\ell = \bigl(Z,\; M,\; \kappa,\; z,\; \omega\bigr)}$$

| symbol | role |
|---|---|
| $Z$ | fault presence, $\in \{0,1\}^5$, drawn exogenously |
| $M$ | fault parameters — **all five** blocks ($P, D, X, E, U$): which timestep, which action or cell, which alternative |
| $\kappa$ | context lane |
| $z$ | the episode's **base option** — a genuinely free variable, not a fault |
| $\omega$ | the ambient tape (the three frozen keys, `11-ENVIRONMENT.md` §8.1.1) |

**$\theta_{C_X}$ and $\epsilon_E$ are no longer independent coordinates.** The
healthy controller is the identity; a $Z_X$ perturbation lives *inside* $M$; a
$Z_E$ perturbation lives *inside* $M$ too. Listing them separately enumerated
states the generator cannot produce — the same defect A11 removed for $B$, one
level down.

$$\boxed{\lvert\mathcal L\rvert \text{ is \textbf{counted by enumeration}, never asserted as a closed-form product}}$$

$M$'s feasible region depends on the option, on the trajectory, and on co-fault
interaction, so it is **not** a free Cartesian product. The product formula that
used to sit in §4 was already behind the SCM; it is replaced by an actual count.

Two quantities are **derived**, not coordinates:

$$B = f_B(\ell) \quad\text{(but-for relevance)}, \qquad R^{*}_{\text{suff}} = f_R(\ell) \quad\text{(task-rescuing repair)}$$

$$\boxed{\mathcal L = \{\, \ell \text{ satisfying the generator's well-formedness constraints} \,\}}$$

### 1.0 What the first draft got wrong here

The earlier definition was $\ell = (Z, A, z, \theta_{C_X}, \epsilon_E, \omega)$ and
the size formula then multiplied in **two** five-dimensional factors — $Z$ and $A$
— enumerating a *derived* label as though it were free. Three separate defects:

1. **$A$ was treated as independent.** It is not; it is computed by intervention
   after the episode is generated (`11-ENVIRONMENT.md` §6.1). Enumerating it
   inflates $|\mathcal L|$ with states the generator cannot produce and dilutes
   the gate.
2. **$\kappa$ was missing** from $\ell$ and from the product, although it appears
   in the matrix description and changes the hazard schedule — so it changes
   signatures.
3. **$M$ was missing entirely**, although it is what distinguishes two episodes
   with the *same* $Z$: $Z_D = 1$ with a fault at $t=2$ versus $t=7$ are different
   episodes, and the gate must quantify over both.

See `12-AMENDMENTS.md` **A11**.

$$\boxed{\text{The predicted label is } Z \text{. The symbol } C \text{ is retired.}}$$

`11-ENVIRONMENT.md` §6.1 removed the symbol $C$: an episode whose faults are
mutually redundant has $Z = (1,1,0,0,0)$ but $A = (0,0,0,0,0)$, and a single
symbol cannot carry both. The gate is stated on $Z$ because that is what V0.1R
predicts; $B$ is a secondary endpoint and gets its own audit (§1.3).
(below).

### 1.1 The tape set must be finite, or nothing is exhaustive

$\omega$ as a stream of real-valued draws cannot be enumerated, and a gate that
says "exhaustive" while quantifying over a continuum is not a gate.

$$\boxed{\mathcal T = \{\omega_1, \ldots, \omega_K\} \text{ is a frozen, finite set of canonical tapes}}$$

$\mathcal T$ contains every tape the generator can actually produce — the hazard's
occupancy schedule is deterministic given $(\kappa, \omega)$, and $\omega$'s only
roles are the finite choices listed in `11-ENVIRONMENT.md` §8.1. So $\mathcal T$ is
finite **by construction**, and its size is reported with the matrix.

If a future change makes any tape role continuous, $\mathcal T$ must be replaced
by a symbolic enumeration over the discrete choices, and the gate re-run. A gate
over a sampled subset of $\mathcal T$ is a **smoke test**, not a gate, and must be
labelled as such.

A **query** $q$ is an element of the legal intervention set applied to a case and
then rolled out, producing an observation sequence

$$O(\ell, q) \in \mathcal O^{*}$$

Because the SCM is deterministic given $\omega$, signatures are compared by
**exact equality**, not by a probabilistic divergence.

$$\boxed{\ell_i \equiv \ell_j \iff \forall q \in \mathcal Q_{\text{legal}}:\; O(\ell_i, q) = O(\ell_j, q)}$$

### 1.2 The gate quantifies over all cases, not one per label

$$\boxed{\text{Gate PASSES} \iff \forall \ell_i, \ell_j \in \mathcal L:\; Z_i \neq Z_j \Rightarrow \ell_i \not\equiv \ell_j}$$

with $\mathcal L$ the **feasible set of the generator's free variables** (§1) —
not a product that includes a derived label.

The first draft stated the symbol-correct version and then described the matrix as
having "one row per feasible cause assignment $C \in \{0,1\}^5$" — a strictly
weaker object. One representative per label misses exactly the failure that
matters:

$$\exists\, \ell_i, \ell_j \text{ with } Z_i \neq Z_j \text{ that collide under some }
(M, z, \theta_{C_X}, \kappa, \omega)$$

A single row per $Z$ would report PASS while the two labels are inseparable in
part of the nuisance space. See `12-AMENDMENTS.md` **A6**.

Cases that share a label but differ in nuisance variables *may* be equivalent —
that is what makes them nuisance variables. What is forbidden is two **different
labels** colliding.

### 1.3 But-for relevance needs its **own** audit

The first draft argued that $B$ is coarser than $Z$ and therefore cannot be harder
to identify:

> "$A$ is a coarser object than $Z$, so it cannot be *less* identifiable."

**Withdrawn.** Coarser as a *function of $\ell$* does not mean coarser as an
*inference target*. The same $Z$ yields different $B$ under different masks and
tapes — $Z_D = 1$ at $t=2$ may be a difference-maker on one tape and redundant on
another — so a learner that recovers $Z$ exactly can still be wrong about $B$:

$$\boxed{Z \text{ identifiable} \;\not\Rightarrow\; B \text{ identifiable}}$$

$B$ is a secondary prediction endpoint of V0.1R (`11-ENVIRONMENT.md` §6.2), so it
gets **its own identifiability audit** at the same budget. If $B$ is not
identifiable within $B_{CF}$, a learner's failure on $B$ may not be reported as an
algorithmic failure — the matrix records the verdict and V0.1R reports $B$ as
**not evaluable** rather than as a negative result.

See `12-AMENDMENTS.md` **A11**.

### 1.4 The gate must be budget-aware — this is Gate L's actual condition

The first draft defined equivalence as

$$\ell_i \equiv \ell_j \iff \forall q \in \mathcal Q_{\text{legal}}:\; O(\ell_i,q) = O(\ell_j,q)$$

which answers *"if every legal query were performed, could these be told apart?"*
It does **not** answer the question that governs whether V0.1R is testable:

> can they be told apart using at most $B_{CF}$ queries?

Those differ, and the gap is the whole gate. A pair needing eight distinct probes
to separate makes the full-signature map injective, so Gate L would **PASS** —
while a learner holding four queries can never separate them. The gate would then
license an experiment whose failure is guaranteed by the budget.

**The condition is therefore stated in terms of the budget.**

Primary form — adaptive, which is what a method actually does since it chooses its
next query from what it has seen:

$$\boxed{B_{\min}^{\text{adaptive}} = \min_{\Pi}\; \max_{\ell \in \mathcal L}\; \mathrm{depth}_{\Pi}(\ell) \;\le\; B_{CF}}$$

where $\Pi$ ranges over decision trees whose internal node at depth $d$ issues a
query from $\mathcal Q_{\text{learner}}$ and branches on the observed outcome.

Tractable fallback, if the adaptive minimisation is too large: a **non-adaptive
separating subset**

$$\boxed{\exists\, S \subseteq \mathcal Q_{\text{learner}},\; |S| \le B_{CF}:\; \text{the } S\text{-signature separates all } Z}$$

The fallback is conservative in the right direction — if a non-adaptive set of
size $\le B_{CF}$ separates, then so does an adaptive tree of depth $\le B_{CF}$,
but not conversely. So a fallback PASS is sound and a fallback FAIL is
inconclusive rather than fatal; the matrix reports which form was used.

### 1.5 Consequence

$$B_{\min}^{\text{adaptive}} > B_{CF} \;\Longrightarrow\; \textbf{Gate L FAILS}$$

and the resolution is the same as for any failed gate (`03` §5 of the first draft
— now §5): either raise $B_{CF}$ — which is a *design* change, declared before
seeds, and reported with every result — or **merge the labels that cannot be
separated within budget**, and say which ones. What is prohibited is proceeding
with a gate that passed on unbounded queries and calling a budget-limited failure
a scientific result.

---

### 1.6 Two repair-truth objects, and a sentinel — required before Gate E runs

"Sufficient" and "the learner should change this" are **different relations**, and
conflating them makes the matrix mathematically incoherent.

An external plant fault can be *dodged*: if $do(d_{t-1} = \texttt{WAIT})$ happens to
avoid the perturbed step, the task succeeds. That intervention is therefore
**sufficient** — but it emphatically does **not** mean the learner should modify its
decision policy for an environment fault. `11` §6.6 and case **C8** say the correct
response there is to update **nothing**.

So the two objects are separated:

$$\boxed{R^{*}_{\text{suff}} = \text{minimal \emph{task-rescuing} interventions}}$$

$$\boxed{U^{*} = \text{learning / update-responsibility truth}}$$

For external and unmodelled faults, $U^{*} = \varnothing$ is entirely reasonable
while $R^{*}_{\text{suff}} \neq \varnothing$.

**And an empty rescuing set is not "update nothing".** If no agent-side
intervention rescues the episode, $\varnothing$ did not turn failure into success —
it is the *absence* of a repair, not a repair. A sentinel is required:

$$\boxed{R^{*}_{\text{suff}} = \bot_{\texttt{NO-SUFFICIENT-REPAIR}}}$$

Only this closes Gate E. Which of the two objects V0.2R should compare
representations against is a further decision, but the Gate generator **must not**
fuse them into a single $R^{*}$ before that decision is made.

### 1.7 Query legality is per factual class, and MALFORMED is never an observation

> **Corrected by A50.** This section previously asserted that members of a factual
> class share one legal query family. **They do not.** Query legality depends on
> the latent fault parameters $M$, not only on the factual observation, so two
> cases with identical $I_t$ can admit different query families. The counterexample
> and the full analysis are in `12-AMENDMENTS.md` **A50**; what follows is the
> corrected rule.

**(a) The legal query family depends on the latent world, not just the trace.**
Whether $do(d_t = d')$ is legal depends on $A_z(m_t, s_t)$ *and* on whether the
case's own fault parameters survive the intervention. So

$$\mathcal Q_{\text{legal}} \text{ depends on } (I^{factual}_t,\ M^{latent})$$

**(b) A rejected query would leak information.** If "this query is illegal" were
observable, a learner could learn from *not* being allowed to ask. So a MALFORMED
query **does not enter the learner's family at all** and is never an observation.
That much of the original section stands.

**(c) What the learner may select is the intersection over its information set.**

$$\boxed{\mathcal Q_{\text{learner}}(H) = \bigcap_{\ell \in H} \mathcal Q_{\text{semantic}}(\ell)}$$

$H$ is the current information set, determined by the factual observation and the
query-response history. An agent may not choose a query that is well formed in only
some of the worlds it still considers possible: if the true world were one of the
others, the only options would be to return MALFORMED (leak), refuse (leak), or let
it execute (rewrite the SCM).

**The factual partition is unchanged.** Classes are still keyed on
$\sigma_0(\ell) = I^{factual}_{0:T}$ alone. Keying them on
$\mathcal Q_{\text{legal}}$ would split worlds the learner **cannot tell apart
observationally**, using a hidden-$M$-derived quantity — a new information channel
disguised as a partition refinement (A50 rejects this explicitly).

**$\mathcal Q_{\text{learner}}(H)$ grows as $H$ shrinks.** A query unsafe at the
root may become safe after an earlier response eliminates the world that made it
malformed. Therefore

$$\boxed{\text{unsafe at the root} \;\not\Rightarrow\; \text{unsafe forever}}$$

and a root-level failure to separate says nothing about adaptive depth.

**The gate is therefore computed per factual class**, by
$\mathcal L \overset{\sigma_0}{\longrightarrow}$ classes, and

$$\boxed{B_{\min}^{\text{adaptive}} = \max_{C} D(C)}$$

where $D(C)$ is the depth-limited adaptive value defined in §1.8. **Stage 3 is the
non-adaptive fallback only**: it searches $S \subseteq \mathcal Q_0(C)$,
$\lvert S\rvert \le B_{CF}$, where $\mathcal Q_0(C) = \bigcap_{\ell\in C}\mathcal Q_{\text{legal}}(\ell)$;
a hit is a sound `PASS_NONADAPTIVE`, a miss is `INCONCLUSIVE_NEEDS_ADAPTIVE` and
nothing more.

This also handles the cost of the factual episode correctly: *seeing your own
episode* is free and is **not** charged against $B_{CF}$.

### 1.8 The adaptive recursion, and the only route to FAIL

At a node with hypothesis set $H$:

$$D(H) = \begin{cases}
0, & \lvert\{Z(\ell) : \ell \in H\}\rvert = 1\\[2mm]
1 + \min_{q \in \mathcal Q_{\text{learner}}(H)} \max_{o} D(H_o), & \text{otherwise}
\end{cases}$$

$$\text{where } H_o = \{\ell \in H : O(\ell, q) = o\} \text{ is the branch set}$$

$$D(H) = \infty \quad\text{only when } \mathcal Q_{\text{learner}}(H) = \varnothing
\text{ while } H \text{ still spans more than one } Z$$

That is the **only** route to `FAIL_UNIDENTIFIABLE`. A class whose root has a safe
query may still have every adaptive path end in such a dead end, so a Stage 3
result of "no root-level dead end" is weaker than identifiability and is reported
as `ROOT_DEAD_END = 0`, not as an unbounded pass.

$$\boxed{D(C) \le B_{CF} \Rightarrow \text{PASS}},\qquad
\boxed{D(C) > B_{CF} \Rightarrow \text{Gate L FAIL at the frozen } B_{CF}}$$

Raising $B_{CF}$ on failure is a **new design amendment**, not a rerun.

### 1.9 Counterfactual rollouts use the exact reference policy

$O(\ell, q)$ needs one more object, and the kernel deliberately refuses to supply
it: **after an intervention, who chooses the subsequent actions?**

$$\boxed{\text{Gate E/L and V0.1R scene generation roll out under } \pi_D^{*}(s, z, m)}$$

that is, the exact reference policy, except where a $do(d_t)$ explicitly overrides
the current decision. After $q = do(z=z')$, the next action comes from
$\pi_D^{*}(s, z', m)$.

The justification is that **V0.1R has no policy learning at all**: the scene's
decision mechanism should be one fixed, deterministic, already-validated policy,
not something the generator improvises. The learner receives the resulting
observations and never reads $Q^{*}$, so this is not oracle-label leakage.

Without this freeze the identifiability generator would become a **third place that
silently defines world semantics**, after the kernel and the DP.

---

## 2. Two query sets — and why the distinction is load-bearing

| set | contents | used for |
|---|---|---|
| $\mathcal Q_{\text{eval}}$ | every intervention in $\mathcal I$ (`02-SCM.md` §5), unbounded | defining $R^{*}$, and the evaluator's ground truth |
| $\mathcal Q_{\text{learner}}$ | only what a method may legally issue, under a stated budget | **the V0.1R gate** |

The gate is run **twice**:

* **Gate E (evaluator).** With $\mathcal Q_{\text{eval}}$, the cause label and
  $R^{*}$ must be well defined for every generated episode. If this fails the
  *environment* is ill-posed and must be redesigned. This is non-negotiable.
* **Gate L (learner).** With $\mathcal Q_{\text{learner}}$, the cause label must be
  recoverable in principle. If this fails, the version's claim is untestable at
  the stated query budget, and the correct responses are exactly two:
  increase the legal query budget, **or** merge the indistinguishable labels and
  say so.

A pass on Gate E with a failure on Gate L is the dangerous case: the evaluator
knows the answer, no method could, and the experiment would measure the query
budget rather than the method. **Gate L is the one that gates V0.1R.**

---

## 3. The legal query set for the learner

### 3.1 Intervention queries — deterministic, hold $\omega$ fixed

| query | notation | cost | reveals |
|---|---|---|---|
| factual rollout | $q_\varnothing$ | 0 | the observed episode |
| decision replay | $do(d_t = d')$, $\omega$ fixed | 1 rollout | whether that decision was the operative one |
| strategy replay | $do(z = z')$, $\omega$ fixed | 1 rollout | whether the process is the right granularity |
| controller probe | $do\bigl(C_X(s^{*},a^{cmd}) = a^{cmd}\bigr)$, $\omega$ fixed | 1 rollout | whether execution is the operative fault |

The controller probe is the **single-cell** primitive of `02-SCM.md` §5.0. The
first draft of this table still carried $do(C_X = C')$, the whole-table form that
A7 replaced in `02` but not here — so the two documents disagreed about what a
size-1 execution intervention *is*, and the identifiability analysis would have
been run against a different intervention lattice than the one the learner uses.

### 3.2 The resample query is a different kind of object

$$\text{resample: same } \ell \text{ except } \omega' \neq \omega$$

This **changes the exogenous assignment**, so it is not a causal intervention at
all: $do(\cdot)$ holds the exogenous variables fixed and varies the mechanism,
whereas resampling holds the mechanism fixed and varies the exogenous draw.

Mixing it into the same table would have two bad consequences:

1. signatures under it are not comparable to signatures under the intervention
   queries — the two rollouts do not share a noise realisation, so a difference
   between them is not attributable to the intervention;
2. it would silently enter $B_{CF}$, inflating the apparent budget with a query
   that cannot separate any two cases differing only in $Z$.

It is therefore excluded from $\mathcal Q_{\text{learner}}$ outright. An earlier
revision said it was "listed separately and counted against a separate budget
$B_{\text{resample}}$", which was worse than wrong — it named a budget that no
artifact computes and no method is charged against, so it read as a licence. There
is **no $B_{\text{resample}}$**. The resample probe is not a query, not part of
any budget, and not a Gate input; if a robustness probe is ever run it is reported
as a diagnostic of the environment, with its own rollout count stated inline.

**It must not participate in $B$.** But-for relevance is

$$B_i = \mathbf{1}\bigl[\mathrm{Outcome}(\ell \setminus Z_i,\ \omega) \neq \mathrm{Outcome}(\ell,\ \omega)\bigr]$$

with $\omega$ **held fixed**. Resampling $\omega$ is a different operation and is
not a but-for test (A26). An earlier revision said the evaluator used resampling
when computing $B$; that was wrong and is removed.

See `12-AMENDMENTS.md` **A10**.

The **counterfactual budget** $B_{CF}$ is the number of rollouts of the four
intervention types a method may spend per episode. It is a frozen design
parameter, declared per version before seeds, and **reported alongside every
result** — a method that wins at $B_{CF}=20$ and loses at $B_{CF}=2$ has not been
shown to win.

$do(z = z')$ is in the learner's set because $|\mathcal Z| = 4$ makes it
enumerable and cheap. This is deliberate: without it, process faults would be
identifiable only to the evaluator, and V0.2R's $R_{\text{causal}}$ representation
could not be fairly compared against $R_{\text{module}}$.

---

## 4. The Identifiability Matrix

The gate's artifact is a matrix, generated exhaustively and committed to
`experiments/<version>/identifiability.json` **before** any seed is run:

* **rows** — every $\ell \in \mathcal L$, counted **by enumeration**, not from a
  closed-form product: $\ell = (Z, M, \kappa, z, \omega)$ where $Z \in 2^5$ is the
  cause pattern, $M = (z, \text{blocks})$ carries the base option and one
  canonical block per active cause, $\kappa$ is the active-controller index and
  $\omega$ the canonical tape. **Not** one row per cause label. Rows the
  generator cannot produce (e.g. $Z_X = 1$ with a perfect controller and no
  plant perturbation) are excluded **and listed in an exclusion table with the
  reason**.
* **columns** — every $q \in \mathcal Q_{\text{learner}}$, up to $B_{CF}$.
* **cells** — a hash of $O(\ell, q)$.
* **derived column** — $B$, computed from the row.
* **final column** — the equivalence class of the row under the full query set.

The matrix is generated over $\mathcal L$ and then **collapsed by label for
reading**, not generated per label. The distinction is the whole point of §1.2:
the gate is decided on the uncollapsed rows.

### 4.0 Size

There is **no product formula**, and writing one down was an error in the first
draft. A closed form requires every factor to have a size independent of the
others, and here it does not: the admissible block for a cause depends on
$\kappa$, $\omega$, $z$ and on which other causes are active, so the count is the
nested sum

$$|\mathcal L_{\text{cand}}| \;=\; \sum_{\kappa}\sum_{\omega}\sum_{z}\sum_{Z\in 2^5}
   \prod_{k \in Z}\bigl|\mathrm{dom}_k(\kappa,\omega,z,Z)\bigr|$$

over the finite frozen domains, with $\mathrm{dom}_k$ **recomputed per world**
(`gate_stage2.py`, `_domains` + `canonicalise`). The realized value is reported
from the enumeration; the current one is $\lvert\mathcal L_{\text{cand}}\rvert =
1{,}166{,}400$, of which $1{,}038{,}960$ are feasible and $127{,}440$ are
excluded as malformed and tabled with their reason. That $5{,}760$ clean
($Z \equiv 0$) worlds survive at all is itself a check: an `or [[]]` guard in the
product once deleted exactly those $5{,}760$ rows silently (A45).

Every factor is finite and frozen (`11-ENVIRONMENT.md` §8.1 makes $\mathcal T$
finite). If $|\mathcal L|$ is large enough to make enumeration impractical, the
correct response is to shrink a factor and say so — not to sample and call it
exhaustive (§1.1).

The read-out required by the gate:

| quantity | requirement |
|---|---|
| number of candidate latent cases $\lvert\mathcal L_{\text{cand}}\rvert$ | reported |
| feasible cases, and the malformed exclusion table | reported |
| number of distinct signature classes | reported |
| $B_{\min}^{\text{adaptive}} = \max_C D(C)$ (§1.8) | **must be $\le B_{CF}$** |
| classes with $D(C) = 0$ (single $Z$, no query needed) | reported |
| classes that are root dead ends ($\mathcal Q_{\text{safe}}(C) = \emptyset$) | reported |
| the separating query set $S$ actually used | reported — which queries are actually needed |
| queries that separate nothing | reported — candidates for removal |

Note what is **not** in that table: "no class may contain two distinct $Z$". That
was the pre-A50 criterion and it is wrong. A class with several $Z$ is the normal
case; a class is unidentifiable only if its adaptive depth exceeds $B_{CF}$ (or it
is a root dead end). Reading "$|\{Z \in C\}| > 1$" as failure would fail the gate
on $2{,}749$ of $2{,}921$ classes that are in fact decidable.

If some class has $D(C) > B_{CF}$, the gate **FAILS at the frozen budget**, and
the resolution is one of:

1. **merge** the labels into one, and record the merge in the spec so that every
   downstream metric uses the merged label set; or
2. **add a legal query** that separates them, and re-run the gate.

Raising $B_{CF}$ is **not** on that list. It is a new amendment, and it must be
argued for and frozen before the gate is re-run — not discovered as the reason
the gate passed.

There is no third option. Proceeding with a failed gate is prohibited.

---

## 5. Gate results are design inputs, not results

A failed gate is not a finding about RFL. It is a finding about the environment,
and it is reported in `docs/rebuild/` as a design change, never in a results
document.

Conversely, a passed gate is not evidence for anything either. It is a
precondition that lets the rest of the study mean something.

---

## 6. Re-running the gate is mandatory after any of these change

* the observation model (`01-OBSERVATION-MODEL.md` §2.1);
* the cause set or its independence structure;
* $|\mathcal Z|$ or the strategy semantics;
* the execution system's decomposition;
* the legal query set or $B_{CF}$;
* the noise model.

The gate is cheap (exhaustive enumeration, no learning) and there is no excuse
for running seeds against a stale matrix.

---

## 7. What this gate does not cover

* **Power.** Identifiability says the answer is recoverable in principle. It says
  nothing about whether a method recovers it at $N$ seeds. That is the statistical
  protocol's job (`05-STATISTICAL-PROTOCOL.md`).
* **Semantic correctness of the code.** A passed gate on paper does not mean the
  implementation distinguishes the causes. That is what the semantic invariant
  suite is for (`04-SEMANTIC-INVARIANTS.md`), and it runs against the *code*, not
  the design.

Identifiability, semantic invariants, and statistical power are three independent
gates. Passing one licenses nothing about the others.
