# 14 — V0.1R method contract

Status: **frozen (A59).** This is the interface contract and the assertion map for
V0.1R's method-facing semantic gate. It specifies **what crosses the boundary**,
not what any algorithm does. No algorithm is specified here.

---

## 1. Why a contract, and why now

S0 asserted the kernel and evaluator-truth semantics. The remaining half of `04`
cannot be asserted until it is decided which interface it is asserting *on*.
Two failures were already visible before any implementation:

**V0.1R must not grow a responsibility output.** V0.1R is diagnosis only: its
output is a five-dimensional $p$ and nothing else. Credit assignment, repair and
update belong to later versions (`06-V01R.md` §6). Adding a $U$ output now would
implement V0.2R inside V0.1R and destroy the version split that exists precisely
to keep diagnosis and prescription apart.

**Arm isolation must be enforced by construction, not by promise.** If every arm
receives the same complete scene and is trusted not to read a field, the
comparison measures discipline rather than information. The arms must receive
*different types*.

---

## 2. The interfaces

| interface | must expose | must NOT expose |
|---|---|---|
| `FactualEvidence` | the learner-visible factual $I_{0:T}$: `obs` plus the learner's own `z_in_force`, `m` | $Z^{\text{pres}}, Z^{\text{fire}}, B, M, R^{*}, u_t, z^{\text{proposal}}$ |
| `FeedbackView` | the learner-facing content of the feedback channel | the truth decoder's internal state, `error_flag`, `cause_rank` |
| `QuerySession` | the currently safe query handles, remaining $B_Q$, query history | MALFORMED sentinels, the reason a query is hidden |
| `QueryRequest` | strategy replay, decision replay, controller probe, plant audit, process-proposal audit | $do(Z_i{=}\text{off})$, $do(C_P{=}\text{identity})$ |
| `QueryReceipt` | query kind, cost, learner-facing response, budget before/after | $Z, M, B, R^{*}$, `Outcome` |
| `Prediction` | five marginals $p=(p_P,\dots,p_U)$ | any requirement that $\sum_i p_i = 1$ |
| `MethodRunResult` | prediction, query receipts, arm, deterministic provenance | write receipts, responsibility $U$, update targets |
| `OracleAdapter` | feeds $Z^{\text{fire}}$ directly, for the ceiling only | reusing a method's inference path to peek at truth |

### 2.1 `Prediction` splits into two typed fields

This must be settled now, or Brier/ECE will be computed on the wrong object:

$$\boxed{p_i \in [0,1], \qquad \sum_i p_i \ \text{unconstrained}}$$

$p$ is the five marginal probabilities used by AUPRC / AUROC / Brier / ECE.

If a method internally holds logits or unnormalised scores, they are stored in a
**separate** field:

$$s^{\text{raw}} \in \mathbb{R}^5$$

as a diagnostic. `06-V01R.md` §2 already requires a normalising method to report
its unnormalised scores; the interface had not yet made the two different types.
Merging them would make "the probability" ambiguous at exactly the point where
calibration is measured.

### 2.2 `FactualEvidence` is $I^{\text{factual}}_{0:T}$, not bare `obs`

The sequence arms receive

$$\boxed{I^{\text{factual}}_{0:T}}$$

not $\text{obs}_{0:T}$. Gate_fire counts the learner's own $z^{\text{in-force}}$
and $m$ as legal information, and A55's process diagnosis *requires* knowing
$z^{\text{in-force}}$ — it is the second half of the commit edge. An arm handed
only `obs` would have a strictly narrower information set than the gate
credited, which is the same defect A56 fixed on the arm names.

---

## 3. Runner-enforced isolation

The runner passes **different types** to each arm. No arm is asked to promise
anything.

| arm | receives |
|---|---|
| `DirectFeedback` | `FeedbackView` only |
| `SequenceEvidence` | `FactualEvidence` only, $B_Q = 0$ |
| `QueryOnly` | query responses only, via **runner-executed blind selection** |
| `SeqThenQuery` | `FactualEvidence`, then selects its own queries |
| `Oracle` | $Z^{\text{fire}}$ directly |

### 3.1 `QueryOnly`'s blind selection is executed by the runner

Several query *addresses* are themselves derived from the factual trajectory: an
execution probe needs a `(state, a_cmd)` site, a decision replay needs a
timestep, a plant audit needs a timestep. Handing those addresses to a "no
sequence evidence" arm leaks sequence evidence through the query menu.

So for `QueryOnly` the runner selects queries from the arm's safe family using a
**frozen blind policy**, and the method sees only the responses and then emits
$p$. That makes the arm test what it is supposed to test:

> intervention and audit evidence, **without** sequence-informed targeting —

rather than "sequence evidence smuggled in through query addresses". Only
`SeqThenQuery` selects its own next query, from $I^{\text{factual}}_{0:T}$.

---

## 4. A50 lives in the API, not only in the gate scripts

A method must **never** receive any of

```text
MALFORMED
ILLEGAL_IN_THIS_WORLD
QUERY_REJECTED_BECAUSE_HIDDEN_FAULT
```

The runtime contract is

$$Q_{\text{learner}}(H) = \bigcap_{\ell \in H} Q_{\text{semantic}}(\ell)$$

and only queries guaranteed safe at the current information state are offered to
the selector. An unsafe query **does not exist in the candidate set**. A refusal
is therefore not a possible response, and there is nothing to encode: exposing
"this query was rejected" would leak a function of hidden $M$, which is exactly
the error A50(d) rejected.

**Every query is an independent probe.** Each intervention query is replayed from
the *same* factual latent world:

$$q_1, q_2, \dots \ \text{are independent probes of one } \ell$$

not a mutated world carried forward from $q_1$ into $q_2$. The only things that
persist across queries are the learner's information history and the remaining
budget.

---

## 5. The S1 assertion map — and what it deliberately does not test

`04` states that the semantic suite **does not test attribution accuracy**. So
the V0.1R method-facing assertions test **interface and information-flow
semantics only**. They must not require a real `SeqThenQuery` to satisfy
$p_X > p_D$ or $p_E > 0$; failing that would be a scientific hypothesis tested
early and a working method mislabelled as a semantic bug.

| item | what S1 asserts | what it does **not** assert |
|---|---|---|
| C0 | the run performs **zero** world/model mutation and emits no write or update output; $p$ schema valid ($p_i \in [0,1]$, length 5) | that $p$ is accurate |
| C1 | the input view contains no evaluator truth; the output space has an **independent** $p_X$ coordinate separable from $p_D$ | that $p_X$ is the larger one on an execution witness |
| C2 | same, symmetrically, for $p_D$ vs $p_X$ | that $p_D$ wins on a decision witness |
| C3 | the process audit's response really is $z^{\text{proposal}}$; $z^{\text{in-force}}$ arrives via the learner's control state; **no `Z_P` verdict is ever returned** | that the method concludes a commit fault |
| C5 | the output space contains independent $p_E$ and $p_U$, so "external / unknown" is **expressible** | that any $p_E > 0$ on this witness |
| C8 | a V0.1R call is side-effect free | the learning-layer "no update" semantics, which is S1 of a later version |

**`Oracle` is the sole exception:**

$$p^{\text{Oracle}} = Z^{\text{fire}} \quad\text{exactly}$$

It must be exact, because it is the metric and label plumbing's sanity gate, not
a method under test.

**Acceptance is deliberately weak in the right way:** a trivially dumb method
must be able to walk the entire interface and pass every S1 assertion. S1 proves
the pipe does not cheat, does not overstep, and has no side effects. Whether an
algorithm is any good is settled by development calibration and the confirmatory
run, not here.

---

## 6. Frozen implementation order

$$\boxed{\text{Method API} \rightarrow \text{arm isolation runner} \rightarrow \text{query-session budget/legality} \rightarrow \text{V0.1R semantic S1}}$$

Only after S1 passes does the Oracle ceiling run, then the
$N_{\text{scenes}} = 32$ development calibration.

The failure mode to avoid is implementing a clever `SeqThenQuery` at this step.
It would make S1 pass for the wrong reason and pre-empt the experiment.
