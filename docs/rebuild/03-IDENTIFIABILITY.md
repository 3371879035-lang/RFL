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

A **latent case** is a full assignment of everything the generator draws:

$$\ell = \bigl(Z,\; A,\; z,\; \theta_{C_X},\; \epsilon_E,\; \omega\bigr)$$

where $Z$ is fault presence and $A$ causal relevance (`11-ENVIRONMENT.md` §6.1),
$z$ the option, $\theta_{C_X}$ the controller parameters, $\epsilon_E$ the plant
perturbation, and $\omega$ the noise tape.

$$\boxed{\text{The predicted label is } Z \text{, never } C \text{.}}$$

`11-ENVIRONMENT.md` §6.1 removed the symbol $C$: an episode whose faults are
mutually redundant has $Z = (1,1,0,0,0)$ but $A = (0,0,0,0,0)$, and a single
symbol cannot carry both. The gate is stated on $Z$ because that is what V0.1R
predicts; $A$ is a secondary endpoint and gets its own, weaker, requirement
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

with $\mathcal L$ the **full enumerated product**

$$\mathcal L = \mathcal Z_{\text{causes}} \times \{0,1\}^5 \times \mathcal Z \times \Theta_{C_X} \times \mathcal E \times \mathcal T$$

The first draft of `03` stated this correctly in symbols and then described the
matrix as having "one row per feasible cause assignment $C \in \{0,1\}^5$" — which
is a strictly weaker object. One representative per label misses exactly the
failure that matters:

$$\exists\, \ell_i, \ell_j \text{ with } Z_i \neq Z_j \text{ that collide under some }
(z, t^{*}, \theta_{C_X}, \kappa, \omega)$$

A single row per $Z$ would report PASS while the two labels are inseparable in
part of the nuisance space, and V0.1R would then be asked to solve a problem that
is not identifiable there. See `12-AMENDMENTS.md` **A6**.

Cases that share a label but differ in nuisance variables *may* be equivalent —
that is what makes them nuisance variables. What is forbidden is two **different
labels** colliding.

### 1.3 The secondary requirement on $A$

$A$ is a coarser object than $Z$ ($A_i = 0$ wherever $Z_i = 0$), so it cannot be
*less* identifiable than $Z$. The gate therefore requires only that $A$ be
determined by $Z$ and the tape, which it is by construction, and does not run a
separate injectivity check. Reported as a derived column in the matrix.

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

| query | notation | cost | reveals |
|---|---|---|---|
| factual rollout | $q_\varnothing$ | 0 | the observed episode |
| decision replay | $do(d_t = d')$ under fixed $\omega$ | 1 rollout | whether that decision was the operative one |
| strategy replay | $do(z = z')$ under fixed $\omega$ | 1 rollout | whether the process is the right granularity |
| controller probe | $do(C_X = C')$ | 1 rollout | whether execution is the operative fault |
| noise resample | same case, $\omega' \neq \omega$ | 1 rollout | whether the failure is stochastic or structural |

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
* **derived column** — $A$, computed from the row.
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
| number of feasible cause assignments | reported |
| number of distinct signature classes | reported |
| classes containing more than one distinct $C$ | **must be empty** |
| smallest separating query set | reported — which queries are actually needed |
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
