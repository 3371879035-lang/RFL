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

$$\boxed{\ell = \bigl(Z,\; M,\; \kappa,\; z,\; \theta_{C_X},\; \epsilon_E,\; \omega\bigr)}$$

| symbol | role | why it is a generation variable |
|---|---|---|
| $Z$ | fault presence, $Z \in \{0,1\}^5$ | drawn exogenously |
| $M$ | fault mask: which timestep and which alternative each fault took | drawn — $Z_D$'s $(t^{*}, a')$, $Z_U$'s trap location |
| $\kappa$ | context lane | drawn |
| $z$ | option | drawn (or overwritten when $Z_P$) |
| $\theta_{C_X}$ | controller parameters | drawn (perturbed when $Z_X$) |
| $\epsilon_E$ | plant perturbation | drawn (when $Z_E$) |
| $\omega$ | noise tape | drawn |

Two derived quantities are **functions of $\ell$**, not coordinates of it:

$$B = f_B(\ell) \quad\text{(but-for relevance)},\qquad R^{*} = f_R(\ell) \quad\text{(repair truth)}$$

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

It is therefore listed **separately**, counted against a separate budget
$B_{\text{resample}}$, and it is **not** a member of $\mathcal Q_{\text{learner}}$
for the purposes of §1.4. Its legitimate use is to establish whether a failure is
stochastic or structural, which is a property of the environment and not of the
label, and it is used by the evaluator when computing $B$ (`11` §6.1).

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

* **rows** — every $\ell \in \mathcal L$, the full enumerated product of §1.2:
  $Z$, $z$, $\theta_{C_X}$, $\epsilon_E$, $\kappa$ and the canonical tape. **Not**
  one row per cause label. Rows the generator cannot produce (e.g. $Z_X = 1$ with
  a perfect controller and no plant perturbation) are excluded **and listed in an
  exclusion table with the reason**.
* **columns** — every $q \in \mathcal Q_{\text{learner}}$, up to $B_{CF}$.
* **cells** — a hash of $O(\ell, q)$.
* **derived column** — $B$, computed from the row.
* **final column** — the equivalence class of the row under the full query set.

The matrix is generated over $\mathcal L$ and then **collapsed by label for
reading**, not generated per label. The distinction is the whole point of §1.2:
the gate is decided on the uncollapsed rows.

### 4.0 Size

$$|\mathcal L| = |\mathcal Z_{\text{causes}}| \times 2^5 \times 4 \times |\Theta_{C_X}| \times |\mathcal E| \times |\mathcal T|$$

Every factor is finite and frozen (`11-ENVIRONMENT.md` §8.1 makes $\mathcal T$
finite). The realized $|\mathcal L|$ is reported. If it is large enough that
enumeration is impractical, the correct response is to shrink a factor and say
so — not to sample and call it exhaustive (§1.1).

The read-out required by the gate:

| quantity | requirement |
|---|---|
| number of feasible latent cases $\lvert\mathcal L\rvert$ | reported |
| number of distinct signature classes | reported |
| classes containing more than one distinct $Z$ | **must be empty** |
| $B_{\min}^{\text{adaptive}}$ (§1.4), or the non-adaptive fallback and which was used | **must be $\le B_{CF}$** |
| the separating query set $S$ actually used | reported — which queries are actually needed |
| queries that separate nothing | reported — candidates for removal |

If any class contains two distinct cause labels, the gate **FAILS**, and the
resolution is one of:

1. **merge** the labels into one, and record the merge in the spec so that every
   downstream metric uses the merged label set; or
2. **add a legal query** that separates them, and re-run the gate.

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
