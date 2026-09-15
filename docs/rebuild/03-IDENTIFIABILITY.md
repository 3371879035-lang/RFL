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

A **latent case** is a full assignment of the exogenous variables together with
the strategy and the plant state:

$$\ell = \bigl(C,\; z,\; \theta_{C_X},\; \epsilon_E,\; \omega\bigr)$$

where $\omega$ is the noise tape (fixed by common random numbers).

A **query** $q$ is an element of the legal intervention set applied to a case and
then rolled out, producing an observation sequence

$$O(\ell, q) \in \mathcal O^{*}$$

Because the SCM is deterministic given $\omega$, signatures are compared by
**exact equality**, not by a probabilistic divergence.

$$\boxed{\ell_i \equiv \ell_j \iff \forall q \in \mathcal Q_{\text{legal}}:\; O(\ell_i, q) = O(\ell_j, q)}$$

$$\boxed{\text{Gate PASSES} \iff \text{no two cases with different cause labels are equivalent}}$$

Equivalently, the map $\ell \mapsto \bigl(O(\ell,q)\bigr)_{q \in \mathcal Q}$ must be
injective **on the cause label**:

$$\ell_i \not\equiv \ell_j \;\;\text{whenever}\;\; C_i \neq C_j$$

Cases that share a cause label but differ in $z$ or $\omega$ are *allowed* to be
equivalent — that is a nuisance variable, not a cause.

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

* **rows** — every *feasible* cause assignment $C \in \{0,1\}^5$ that the generator
  can produce. Infeasible combinations (e.g. $c_X = 1$ with a perfect controller
  and no plant perturbation) are excluded **and listed as excluded**, with the
  reason.
* **columns** — every $q \in \mathcal Q_{\text{learner}}$, up to $B_{CF}$.
* **cells** — a hash of $O(\ell, q)$.
* **final column** — the equivalence class of the row under the full query set.

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
