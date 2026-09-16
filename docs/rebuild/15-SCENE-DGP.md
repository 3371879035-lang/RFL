# 15 — The scene DGP, and why dev_v1 is void for discriminative-range inference

Status: frozen — **A62**.

---

## 1. What dev_v1 got wrong

`experiments/v01r/calibration_dev.json` is **kept as-is** and marked:

> **development design diagnostic — invalid for discriminative-range inference
> because the support was conditioned on the full `(rows, feedback)` factual
> class.**

Two independent defects, and the first is the serious one.

**Support-level conditioning bypassed typed isolation.** `build_partition()` keys
classes on the complete

$$\sigma_0 = (\text{rows}, \text{feedback})$$

and `calibration.py` then handed `PublicSupport(worlds=tuple(reps), …)` to
`SequenceEvidence`, `QueryOnly` **and** `SeqThenQuery`, and initialised the query
session with `members=reps`. So

$$\boxed{\text{SequenceEvidence was silently conditioned on the feedback claim}}$$

even though its typed input never contains a `FeedbackView`, and

$$\boxed{\text{QueryOnly was silently conditioned on the factual sequence and feedback}}$$

even though its typed input contains only response payloads. This is not an A59
type-boundary failure — the types were right. It is a **constructor outside the
type boundary** handing over the answer. It also explains the otherwise
suspicious coincidence

$$\mathrm{AUPRC}(\text{SequenceEvidence}) = \mathrm{AUPRC}(\text{QueryOnly}) = 0.9824.$$

Two arms with genuinely different information interfaces should not have agreed
to four decimal places.

**The population was not the protocol's unit.** Scenes were drawn from factual
classes (keeping $|reps| \ge 2$, hashing the class, taking `true = reps[0]`), but
the statistical protocol's unit for V0.1R is **independently generated
episodes**. Class-conditioning both biases the metrics and makes them an estimate
of the wrong population.

So the 0.98–1.00 figures are **not** evidence that the benchmark is too easy, and
that question is still open. dev_v1's value is exactly that it exposed this.

---

## 2. The frozen scene DGP

A61 recorded that the generator's measure over worlds was unspecified, which is
why `w_l = 1` was used. That gap is now closed.

$$\kappa \sim \mathrm{Uniform}(\mathcal K), \qquad z^{\text{proposal}} \sim \mathrm{Uniform}(\mathcal Z)$$

The `SemanticTape` keeps its already-frozen real measure, including

$$P(\texttt{error\_flag} = 1) = 0.4.$$

For each cause $i$ whose canonical domain is non-empty **in the current context**:

$$Z_i^{\text{pres}} \sim \mathrm{Bernoulli}(0.2),$$

with $Z_i = 0$ forced when the domain is empty, and the fault parameter drawn
uniformly from that cause's canonical domain once active.

**Why $0.2$, stated so it is not mistaken for tuning.** It is not chosen to move
any dev score. The specification already says causes are sparse, and $0.2$ is the
value that makes the arithmetic say so:

$$\mathbb{E}\bigl[|Z|\bigr] = 1 \quad\text{when all five causes are available},
\qquad
P\bigl(|Z| \le 1\bigr) = 0.8^5 + 5(0.2)(0.8)^4 \approx 0.737,$$

i.e. most episodes carry zero or one fault.

Scenes are now **generated directly from the DGP and the namespace**, not picked
from factual classes.

---

## 3. The four arms' hypothesis populations

$$\boxed{H_{\text{seq}}(I) = \{\ell : \mathrm{rows}(\ell) = I\}}$$

**rows-only. No feedback conditioning.** Then:

| arm | population |
|---|---|
| `DirectFeedback` | the claim alone |
| `SequenceEvidence` | $H_{\text{seq}}$ — from the **global public support**, rows-only |
| `SeqThenQuery` | the same $H_{\text{seq}}$, then queries |
| `QueryOnly` | the **global prior support**, never the true factual class |

`PublicSupport` may be precomputed and cached, but it must be a **public object
independent of the true world**.

**Marginals use the real measure:**

$$p_i(H) = \frac{\sum_{\ell \in H} P_{\text{DGP}}(\ell)\, Z_i^{\text{fire}}(\ell)}{\sum_{\ell \in H} P_{\text{DGP}}(\ell)}$$

This is not fitting the algorithm to development data; it supplies the generator
measure that was explicitly missing.

**`_freeze` no longer uses Python `hash()`.** It canonicalises to nested immutable
tuples. Hashing as a semantic key would reintroduce the `PYTHONHASHSEED`
nondeterminism this rebuild already removed once, and admits collisions.

**No "greedy only for coverage extension" language remains.** The earlier comment
described behaviour the code did not have — it simply appended the first 32 items
in hash order without skipping any for coverage.

---

## 4. Pre-registered resolution, written down before dev_v2

So that there is no third round of benchmark editing:

**If, after the leakage is removed, dev_v2 still shows**

$$\mathrm{SequenceEvidence} \approx 0.98, \qquad \mathrm{SeqThenQuery} \approx 1,$$

**that is accepted, and we proceed to the confirmatory run without making the
environment harder.** The frozen primary hypothesis is

$$\text{SeqThenQuery} > \text{DirectFeedback} + \Delta_{\min},$$

**not** $\text{SeqThenQuery} > \text{SequenceEvidence} + \Delta_{\min}$. The correct
reading in that case is:

> the factual sequence already carries most of the diagnosis information and the
> queries only resolve residual ambiguity; the incremental query contrast is
> ceiling-limited.

That is part of the structure of the result, not a defect to be tuned away, and
it must not be "fixed" by making the benchmark harder to flatter a method.

**If dev_v2 separates naturally** — $\text{DirectFeedback} <
\text{SequenceEvidence} < \text{SeqThenQuery}$ — that is nicer, but it is **not** a
PASS condition.

Either way the rule is:

$$\boxed{\text{dev\_v1 is a support/population design defect; after the fix, only ONE fresh dev\_v2}}$$

---

## 5. Run order

$$\boxed{\text{A62} \rightarrow \text{S1 regression} \rightarrow \text{A60 regression} \rightarrow v01r\_smoke\_v2\ (N{=}5) \rightarrow v01r\_dev\_v2\ (N{=}32)}$$

`dev_v1` stays on disk unchanged. Namespaces are not reused.

No change is made to the kernel, fault semantics, the observation model, the
query family, or the difficulty of the environment.
