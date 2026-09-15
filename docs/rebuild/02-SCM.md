# 02 — Structural causal model

**Status:** FROZEN. Depends on `01-OBSERVATION-MODEL.md`.

This document defines the environment as an explicit structural model with
intervention semantics. The point of writing it as an SCM rather than as a
simulator is that **every causal claim in the project must be expressible as a
`do()` operation on a named variable**, and every such operation must be
executable by the evaluator. If a claim cannot be written that way, it is not a
claim this project can test.

---

## 1. Latent variables

Five exogenous causes, each independently assignable:

| symbol | name | what it means when active |
|---|---|---|
| $Z_P$ | process / strategy | the *policy the episode is being run under* is wrong for this context |
| $Z_D$ | decision | a specific $a^{cmd}_t$ is a poor choice **in its context** |
| $Z_X$ | execution | the body failed to carry out a correct command |
| $Z_E$ | environment | an external perturbation changed the world, not the agent |
| $Z_U$ | unmodelled | a cause the agent's hypothesis space cannot represent |

Plus $M$, the evaluator's fault mask, which records *which timesteps and which
variables* were perturbed. $M$ is bookkeeping, not a cause.

$$C = (c_P,\, c_D,\, c_X,\, c_E,\, c_U) \in \{0,1\}^5,\qquad \text{entries independent}$$

**Multi-label is required.** $C = (1,1,0,0,0)$ — a bad process *and* a bad local
decision — is a legal episode. The learner's output

$$p = (p_P,\, p_D,\, p_X,\, p_E,\, p_U)$$

is likewise **not required to sum to 1**, and no softmax over the five is
imposed. Any method that internally normalises must report the unnormalised
scores it would have produced, because "sums to 1 over five causes" is a modelling
assumption the spec does not grant.

---

## 2. The strategy variable

The legacy design had no object at the process level, which is why "WholeProcess"
degenerated into "two local faults happened to co-occur" and inflated to 68.4% of
failures. The rebuild gives the process level a real, intervenable referent:

$$z \in \mathcal Z,\qquad \boxed{|\mathcal Z| = 4}$$

$z$ is a **strategy program**: it determines the decision sequence.

$$z \;\longrightarrow\; d_1, d_2, \ldots, d_T$$

Concretely, $z$ is a small function from (context, timestep) to a decision rule —
"always head for the short corridor", "wait for the hazard to move, then cross",
and so on. Four programs, fully enumerable, chosen so that the following are all
representable:

| program | property it exists to provide |
|---|---|
| $z_1$ | the default / context-appropriate strategy |
| $z_2$ | a strategy that is locally improvable — one decision is wrong but the rest is fine |
| $z_3$ | a genuinely different strategy that succeeds where $z_1$ fails |
| $z_4$ | a strategy whose failure is delayed — it looks fine early and fails late |

$|\mathcal Z| = 4$ is frozen. It is large enough to make process-level attribution
a real question and small enough that the whole intervention lattice is
enumerable, so V0.3R does not silently become a search-algorithm contest.
Continuous $\mathcal Z$ is out of scope for the rebuild.

**Consequence for the DAG.** Decisions are *not* independent draws:

$$z \to d_1, \ldots, d_T$$

so a local decision repair must be a genuine intervention that leaves $z$ intact:

$$do(d_t = d') \quad\text{changes } d_t \text{ only}$$

and a process repair is

$$do(z = z') \quad\text{which rewrites the whole sequence}$$

These are different operations on different nodes. That is what makes the process
level a *granularity*, not a sum of locals.

---

## 3. The execution system

Execution is not a label on a decision. It is a separate mechanism with its own
parameters:

$$\pi_D:\; s \to a^{cmd} \qquad\qquad C_X:\; (s, a^{cmd}) \to u \qquad\qquad P:\; (s, u, \epsilon_E) \to a^{realized}$$

* $C_X$ is a **learnable tabular controller**. Its parameters are distinct from
  $Q_D$, and updating it is $\Delta C_X$, never $\Delta Q_D$.
* $P$ is the plant. External faults enter through $\epsilon_E$.

This split yields two failure modes that the legacy code could not distinguish:

| mode | condition | correct response |
|---|---|---|
| **internal controller fault** | $C_X$ produced a wrong $u$ | update $C_X$; **do not touch $Q_D$** |
| **external plant fault** | $C_X$ was right, $P$ misbehaved | environment / unmodelled; **default: update nothing** |

The second row is a first-class **external-fault control condition**, not an
awkward special case. Under $Z_E$ or $Z_U$ the correct behaviour is frequently to
make no edit at all, and an arm that edits anyway is measurably wrong.

---

## 4. Cause truth and repair truth are different objects

This distinction is new and load-bearing.

$$C = (c_P, c_D, c_X, c_E, c_U) \qquad\text{— \textbf{cause truth}: what is broken}$$

$$R^{*} = \text{minimal sufficient intervention set} \qquad\text{— \textbf{repair truth}: what must change}$$

They are both evaluator truth and they are **not** the same set. A broken decision
may be repairable by a process change; an execution fault whose controller is
already optimal may be unrepairable.

This is exactly the split the four-version chain needs:

$$\text{V0.1R predicts } C \qquad\qquad \text{V0.2R predicts } R^{*}$$

and it removes a confusion that ran through the whole legacy project, where
"attribution" was asked to be simultaneously a diagnosis and a prescription.

---

## 5. The intervention lattice, and what `WholeProcess` actually means

The admissible intervention space is

$$\mathcal I = \underbrace{\{do(z = z')\}_{z' \in \mathcal Z}}_{\text{process}} \;\cup\; \underbrace{\{do(d_t = d')\}_{t, d'}}_{\text{decision}} \;\cup\; \underbrace{\{do(C_X = C')\}}_{\text{execution}} \;\cup\; \{\varnothing\}$$

with $\varnothing$ meaning *change nothing* — which is a legal repair and must be
a legal answer.

A **repair** is a finite subset $r \subseteq \mathcal I$. It is **sufficient** iff
the episode succeeds under $do(r)$. The **minimal sufficient set** is

$$R^{*} = \arg\min_{r \text{ sufficient}} |r|$$

### 5.1 The corrected definition of a process fault

$$\boxed{\text{Process fault} \iff \exists\, z' : \{do(z=z')\} \text{ suffices, and no single local intervention suffices}}$$

That is: **the process is the right granularity to intervene at** — not "two
things are broken". A process fault is *not* defined as $|R^{*}| > 1$.

This is the direct fix for the legacy failure, where the definition effectively
became "minimal size > 1", and where a reconstruction bug then manufactured
multi-fault episodes until they were 68.4% of the data. Under §5.1 a single
co-occurring pair of independent local faults is a *size-2 repair whose members
are each independently sufficient*, i.e. $|R^{*}| = 1$ with two candidates — see
invariant **I3** in `04-SEMANTIC-INVARIANTS.md`.

### 5.2 Ties are first-class

When several size-1 repairs each suffice, $R^{*}$ is a **set of candidates**, not
a chosen one:

$$|R^{*}| = 1 \text{ (size)},\qquad \#\text{candidates} = k \ge 1$$

The evaluator reports both numbers separately. Any metric that assumes a unique
repair is ill-defined and is prohibited.

---

## 6. Forward generation only

The evaluator must **never** re-derive a cause from a trace. Every episode is
generated forward:

1. assign $C$ and $M$ exogenously;
2. assign $z$ (or perturb it if $Z_P$ active);
3. assign controller state and any $Z_X$ perturbation;
4. roll out $z \to d_1..d_T \to a^{cmd} \to u \to a^{realized}$;
5. carry $C$, $M$, $z$, and the true $a^{cmd}$ alongside the trace as **truth
   fields**, never as reconstructed fields.

$$\boxed{\text{No cause is ever inferred from the trace, even by the evaluator.}}$$

The legacy `scene_from_trace` was exactly this prohibited step, and it produced
the `WholeProcess` inflation. It has no counterpart here: if the evaluator wants
to know $Z_D$ it reads the assignment it made, not the rollout.

### 6.1 Reconstruction is permitted only as a checked inverse

One operation is allowed: given a trace and the truth fields, verify that the
forward model reproduces the trace exactly. This is a **test**, not a source of
labels (`04-SEMANTIC-INVARIANTS.md`, invariant **I5**).

---

## 7. Reward

Task reward is terminal plus a small step cost, with two modes as a secondary
factor (see `06-V01R.md` §6 for why reward is demoted out of the main line):

$$R^{(A)}: \text{success } +1,\ \text{failure } -1 \qquad\qquad R^{(B)}: \text{success } +1,\ \text{failure } 0$$

With $\gamma = 1$ and a fixed horizon these are affine:

$$\mathbb{E}[R^{(A)}] = 2P(S) - 1, \qquad \mathbb{E}[R^{(B)}] = P(S)$$

so they induce the **same optimal policy**. They are therefore *not* capable of
producing a large policy difference by themselves, which is exactly why the legacy
Alpha pilot found them practically equivalent. Under a fixed learning rate they
are still not interchangeable, because the TD error differs by 1 and any update
clipping bites at different times — which is why reward is accompanied by the
update-dynamics ledger in `10-REPRODUCIBILITY-AND-OPS.md` §4.

---

## 8. Hierarchy: demoted, not deleted

The legacy H/L (high-level plan / low-level action) split is **not the ontology**
of the rebuild. It survives as one candidate credit representation:

$$R_{\text{module}}$$

competing in V0.2R against $R_{\text{trajectory}}$, $R_{\text{causal}}$ and
$R_{\text{repair}}$. If it loses on the V0.2R endpoints, it is removed. What is
prohibited is starting from it as an assumption.

---

## 9. Frozen

1. the five exogenous causes and their independence;
2. multi-label $C$, and $p$ not summing to 1;
3. $|\mathcal Z| = 4$, discrete and fully enumerated;
4. the DAG $z \to d_1..d_T$, and $do(d_t)$ being a local intervention;
5. the three-part execution system $\pi_D / C_X / P$, with $C_X$ learnable and
   parameter-disjoint from $Q_D$;
6. the separation of cause truth $C$ from repair truth $R^{*}$;
7. the intervention lattice $\mathcal I$ and the definition §5.1;
8. forward generation only (§6);
9. $R^{*}$ as a candidate set with ties (§5.2).
