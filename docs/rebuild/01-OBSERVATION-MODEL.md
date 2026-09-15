# 01 — Observation model

**Status:** FROZEN. This document is a prerequisite for every other document in
`docs/rebuild/`. No algorithm may be specified before the observation model is
fixed, because the observation model *is* the difficulty of the problem: a cause
that is visible in `obs` is not inferred, it is read off.

---

## 1. The three-layer action

The legacy environments conflated two different things under one symbol: "the
action the agent chose" and "the action that happened". Everything downstream —
`intent` vs `realized` in `env.py`, the `DECISION`/`EXECUTION` collision in
`rflv04`, the `scene_from_trace` reconstruction bug — traces back to that
conflation. The rebuild separates three layers:

$$a^{policy}_t \;\longrightarrow\; a^{cmd}_t \;\longrightarrow\; a^{realized}_t$$

| layer | symbol | produced by | meaning |
|---|---|---|---|
| policy | $a^{policy}_t$ | $\pi_D$ | what the decision system selected |
| command | $a^{cmd}_t$ | $\pi_D$ (issued) | what the decision system *told the body to do* |
| realized | $a^{realized}_t$ | plant $P$ | what actually happened in the world |

In this design $a^{policy}_t = a^{cmd}_t$ — the decision system issues what it
chose. They are kept as distinct symbols anyway, because a future interface
(where a planner's abstract action must be compiled into a motor command) would
separate them, and because the SCM must not need rewriting if it does.

The pair $(a^{cmd}_t, a^{realized}_t)$ is what makes execution faults *physical*
rather than notational.

### 1.1 The two failure modes, defined structurally

$$\text{Decision fault:}\quad a^{cmd}_t \text{ is a poor choice}$$

$$\text{Execution fault:}\quad a^{cmd}_t \text{ was fine, but } a^{realized}_t \neq a^{cmd}_t$$

These are now different objects in the data structure, not two labels on one
event. A `DECISION` unit and an `EXECUTION` unit therefore cannot address the
same parameter — see `04-SEMANTIC-INVARIANTS.md`, invariant **I1**.

---

## 2. What the learner observes

### 2.1 Main design

$$\boxed{\;obs_t \;=\; \bigl(s_t,\; a^{cmd}_t,\; a^{realized}_t,\; r_t,\; \text{feedback}_t,\; t\bigr)\;}$$

| field | visible? | note |
|---|---|---|
| $s_t$ | yes | full environment state within the observation function |
| $a^{cmd}_t$ | **yes** | the learner's own issued command |
| $a^{realized}_t$ | yes | what the world did |
| $r_t$ | yes | task reward |
| $\text{feedback}_t$ | yes | unreliable diagnostic feedback channel |
| $t$ | yes | timestep |

### 2.1.1 The learner's total information includes its control state

`obs_t` above is what the environment *reports*. The learner additionally holds
its own control commitments, which it must have in order to act at all:

$$\boxed{I_t = \bigl(obs_t,\; z_t,\; m_t\bigr)} \quad\text{— the learner's total information set}$$

$z_t$ is the option in force and $m_t$ the option automaton state
(`02-SCM.md` §2.3.2). The learner cannot evaluate $A_z(m_t, s_t)$ or index
$Q_D(s_t, z_t, m_t, \cdot)$ without them, so they are not optional.

**They are neither observations nor hidden, and the spec previously left them in
exactly that gap.** A22 made them visible to the policy while §2.2 below continued
to say every field is either in `obs` or in the hidden set — so the control state
was the "third category" this document explicitly forbids. The rule is restated
to cover it:

$$\boxed{\text{Every field is in } I \text{ (usable) or in the hidden set (§2.2). There is no third category.}}$$

Practically: **$z_t$ and $m_t$ enter the identifiability signature's usable
information set** (`03-IDENTIFIABILITY.md` §3.1). An analysis restricted to
`obs_t` alone would understate what a method can legitimately use, and would
manufacture an identifiability failure that is an artefact of the bookkeeping.

See `12-AMENDMENTS.md` **A27**.

### 2.2 What is hidden — evaluator truth only

$$Z_P,\ Z_D,\ Z_X,\ Z_E,\ Z_U,\qquad M \text{ (the fault mask)},\qquad u_t \text{ (the motor command)}$$

are **never** in `obs`. They exist only in the evaluator's ground truth. No
method may read them during a run; the Oracle may read them only where the spec
says so explicitly.

$u_t$ is named here rather than left implicit because it is the one field whose
visibility decides whether execution faults are inferable or merely *readable*.
The controller output $u_t$ sits between the command and the realised action:

$$a^{cmd}_t \;\to\; C_X \;\to\; u_t \;\to\; P \;\to\; a^{realized}_t$$

If $u_t$ were observed, the distinction between the two non-decision fault kinds
would collapse to a comparison:

$$u_t \neq a^{cmd}_t \;\Rightarrow\; \text{internal execution fault},\qquad
a^{realized}_t \neq u_t \;\Rightarrow\; \text{external fault}$$

Both would be read off rather than inferred, and $Z_X$ versus $Z_E$ — which the
learner must be able to separate, because one is repairable and the other is
not — would stop being a question.

So $u_t$ is **hidden**, and the learner must separate $Z_X$ from $Z_E$ through
legal queries — principally the controller probe of
`03-IDENTIFIABILITY.md` §3. This is stated as an explicit exclusion rather than
left to "it happens not to be in the list", because the legacy project's defects
were repeatedly of the form *a field was visible and nobody had decided it should
be*. See `12-AMENDMENTS.md` **A8**.

$$\boxed{\text{Every field is either in } obs \text{ (§2.1) or in the hidden set (§2.2). There is no third category.}}$$

### 2.3 Why $a^{cmd}$ is visible — and why that is not a giveaway

The tempting design is to hide $a^{cmd}$, on the theory that it makes the problem
harder. That is rejected, for two reasons.

**It is artificial.** If the learner is the system that issues commands, it knows
what it issued. Hiding a system's own command from itself is manufacturing partial
observability rather than modelling it. A difficulty produced that way does not
transfer to any real setting.

**It does not actually make attribution trivial.** Observing $a^{cmd}$ identifies

$$\boxed{\text{execution deviation}}\qquad a^{realized}_t \neq a^{cmd}_t$$

and nothing more. It does **not** identify decision correctness. Consider:

| observation | what it establishes | what it does **not** establish |
|---|---|---|
| $a^{cmd} = \text{LEFT}$, $a^{realized} = \text{LEFT}$ | execution was faithful | whether LEFT was a good decision |
| $a^{cmd} = \text{LEFT}$, $a^{realized} = \text{RIGHT}$ | execution deviated | whether LEFT was already bad; whether RIGHT accidentally rescued the episode; whether the environment would have defeated LEFT anyway; whether a decision fault *co-occurs* |

So the inference problem that remains is the whole of it:

* was $a^{cmd}_t$ correct **in the context it was issued**?
* is the observed failure attributable to the decision, the execution, the
  process, the environment, or something unmodelled?
* which of those co-occur?

Answering those requires sequence evidence and counterfactual queries. The
visible-command design makes execution deviation *detectable* while leaving causal
attribution *hard* — which is the intended problem.

### 2.4 Log-limited stress condition (secondary)

A single secondary condition hides $a^{cmd}$:

$$obs^{stress}_t = \bigl(s_t,\; a^{realized}_t,\; r_t,\; \text{feedback}_t,\; t\bigr)$$

This tests whether the method still recovers execution faults when the internal
log is missing — a realistic failure mode (logging disabled, sensor-only access).

**It is a condition, not the main design, and it is tier-2.** Results from it may
not be used to select the credit representation (V0.2R) or the repair primitive
(V0.3R).

---

## 3. Consequences that bind the rest of the spec

**C1 — Identifiability is a property of this observation model.** With $a^{cmd}$
visible, execution deviation is directly observable but every *causal* claim still
requires queries. The identifiability analysis in `03-IDENTIFIABILITY.md` must be
run against §2.1 exactly, and re-run if §2.1 changes.

**C2 — Decision faults cannot be labelled from `obs` alone.** Therefore any
"oracle" that claims to know $Z_D$ must obtain it from the exogenous assignment,
not from the trace. `scene_from_trace`-style reconstruction is prohibited by
construction: the SCM is generated forward, and the truth is carried alongside the
trace, never re-derived from it. See `02-SCM.md` §6.

**C3 — Feedback is separate from evidence.** $\text{feedback}_t$ is an unreliable
*channel*, not an observation of the cause. It may be wrong. It must be possible
to run any experiment with the feedback channel replaced by noise without changing
anything else, and that substitution is itself a factor.

**C4 — No method may condition on $t$ beyond what $obs_t$ contains.** Episode
length is fixed, so $t$ leaks no future information; this is asserted explicitly
so that a later move to variable horizons does not silently change the problem.

---

## 4. Frozen

The following are frozen and may not be altered after this point without a new
pre-registered study:

1. the three-layer action $a^{policy} \to a^{cmd} \to a^{realized}$;
2. the contents of $obs_t$ in §2.1;
3. the hidden set $\{Z_P, Z_D, Z_X, Z_E, Z_U, M\}$;
4. the rule that the learner never reads the hidden set;
5. the existence and tier of the log-limited stress condition.
