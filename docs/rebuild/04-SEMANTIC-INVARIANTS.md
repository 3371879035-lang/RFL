# 04 — Semantic invariants

> **A58: this document is the total hard gate, and it is now layered for
> execution.** The invariants and cases below mix two obligations of different
> maturity. `src/rfl_rebuild/` contains only `env` and `solve` — there is no
> responsibility / update / write-space layer — so I1, I2, I6, C6 and the write
> halves of C0/C1/C2/C3/C5/C8 have nothing to assert against yet.
>
> The gate is therefore reported in three statuses, **never `N/A`**:
>
> $$\texttt{PASS} \;/\; \texttt{BLOCKED\_NOT\_IMPLEMENTED} \;/\; \texttt{FAIL}$$
>
> * **S0 — Semantic Kernel Gate** (implementable now): I3, I4, I5, and the
>   kernel/evaluator-truth halves of C0–C5, C7, C8. Runner:
>   `scripts/semantic_gate_s0.py`; artifact: `experiments/v01r/semantic_gate.json`.
> * **S1 — Semantic Learning Gate** (with the corresponding version): I1, I2, I6,
>   C6, and the `p` / responsibility / write-receipt / update pieces.
>
> `BLOCKED_NOT_IMPLEMENTED` is deliberately loud because `N/A` is the status that
> gets forgotten. A version gate consuming the artifact must state, per blocked
> item, whether that version depends on it — V0.1R depends on I3/I4/I5 and the
> kernel halves only, and the blocked items are **not** thereby verified.
>
> The case suite is **C0–C8**.
 and the case suite

**Status:** FROZEN. Hard gate. Depends on `01`–`03`.

$$\boxed{\text{Any failure here blocks seed collection for every version.}}$$

The legacy project had 177 passing unit tests and still shipped a training loop
that wrote two nominally distinct units into one Q entry, an Oracle that
reconstructed decision faults from realized actions, and a "ceiling" arm that
reinforced the action it was meant to repair. **Passing unit tests is not
evidence of semantic correctness.** This suite tests the three things unit tests
did not:

$$\boxed{\text{deterministic correctness}} \quad \boxed{\text{semantic correctness}} \quad \boxed{\text{causal correctness}}$$

---

## 1. Global invariants

These are asserted on **every** run, not only in the test suite. A violation
aborts the run.

### I1 — Write-space disjointness

$$\boxed{unit_i \neq unit_j \;\Longrightarrow\; \mathrm{WriteSpace}(unit_i) \cap \mathrm{WriteSpace}(unit_j) = \varnothing}$$

Two distinct learning units may not address the same parameter. If they must share
parameters, that must be **declared in the spec**, and the units may then no
longer be described as independent — the metrics must say so.

*Legacy failure this prevents:* `DECISION` and `EXECUTION` were distinct `Site`
units that both routed to `q.low`, producing two relative writes with opposing
targets on one entry. The resulting `PYTHONHASHSEED`-dependent write order gave a
3.3x spread in `WMD` for identical inputs.

`WriteSpace(unit)` is computed mechanically from the parameter objects the unit
can reach, not from a hand-maintained list.

### I2 — No write without a named, responsible unit

Every update carries a receipt naming the unit, the site, and the target. An
update with no site is recorded as `no_site` and performs **no** write. A failure
that cannot be localised may not be converted into an edit.

### I3 — Minimal size and candidate count are separate

$$|R^{*}| = \text{size of the minimal sufficient set},\qquad \#R^{*} = \text{number of such sets}$$

Both are reported. Neither is inferred from the other. Metrics that assume a
unique repair are ill-defined.

### I4 — No label reconstruction from traces; fire receipts are not reconstruction

**A54 restates this invariant, and A56 propagates the restatement**, because it
was in danger of being read as prohibiting something the design now requires.

$$Z^{\text{pres}} \text{ comes from the generation truth}, \qquad Z^{\text{fire}} \text{ comes from a forward mechanism-fire receipt}$$

Concretely:

* $Z^{\text{pres}}$ is the generator's own injection record (`02-SCM.md` §6). It
  is never inferred from anything.
* $Z^{\text{fire}}$ is produced by `kernel.fired_mechanisms` during the **forward
  execution**: the run reports which mechanisms it actually executed
  ($z^{\text{in-force}} \neq z^{\text{proposal}}$, override reached,
  $u_t \neq a^{cmd}_t$, $a^{realized}_t \neq u_t$, terminated in trap). This is an
  execution receipt emitted *by* the run, not a label inferred *about* the run
  afterwards.
* $B$ is the evaluator's counterfactual construction and is likewise never
  inferred from behaviour.

The prohibition stands and is unchanged in force: **no code path may infer a cause
label from ordinary learner-visible behaviour after the fact.** The distinction is
forward receipt versus retrospective inference, not "labels from the machinery"
versus "labels from a rollout" — the fire vector *is* read off a rollout, and
that is legitimate precisely because the mechanism reads it as the execution
happens, from fields the learner cannot see, and asserts nothing about what a
learner could conclude.

*Legacy failure this prevents:* `scene_from_trace` derived a decision fault from
`realized != reference`, which duplicated every execution fault as a decision
fault and inflated `WholeProcess` to 68.4% of failures while true `Execution`
faults were 0.36%.

### I5 — The forward model must reproduce the trace exactly

The one legal use of reconstruction: re-run the generator from the truth fields
and assert the trace is reproduced bit-for-bit. This is a consistency check on the
generator and the logger, never a source of labels.

### I6 — No update may exceed the declared budget

Each write is clipped to a declared maximum, the clip is recorded, and the total
update mass per episode is bounded and logged. Silent accumulation across units is
a violation.

---

## 2. The case suite

Each case is a hand-constructed episode with a known truth assignment. The suite
asserts on the **implementation's** outputs, not on the design.

### C0 — No fault

$$\text{successful episode},\quad C = (0,0,0,0,0)$$

Must produce $U = (0,0,0,0,0)$ and **no write of any kind**. An arm that edits a
clean episode is wrong even if its downstream AUC looks fine.

### C1 — Decision correct, execution deviated

$$a^{cmd}_t \text{ good},\qquad a^{realized}_t \neq a^{cmd}_t$$

Required: $U_D = 0$, $U_X = 1$; and **only the execution representation may be
written** ($\Delta C_X$), never $Q_D$.

### C2 — Decision wrong, execution faithful

$$a^{cmd}_t \text{ poor},\qquad a^{realized}_t = a^{cmd}_t$$

Required: $U_D = 1$, $U_X = 0$; the actuator must **not** be written.

### C3 — Commit-integrity fault, every local decision defensible

**A55: this case is no longer "the process is wrong for the context".** The
planner proposed $z^{\text{proposal}}$; the process/commit layer ran something
else:

$$z^{\text{in-force}} \neq z^{\text{proposal}}, \qquad Z_P^{\text{fire}} = 1$$

Each $d_t$ is locally defensible *given the option actually in force*, so no local
decision is at fault. The proposal need **not** be optimal or even correct — that
is the point of the case, and it is what separates it from a "bad strategy".

Required: the process/commit level is blamed, no local decision is written, and
the repair is $do(C_P = \text{identity})$. Note the falsifiable signature: if a
method is shown $z^{\text{proposal}}$ and $z^{\text{in-force}}$ via
`audit_process_proposal()` and still blames a decision, it fails this case.

### C4 — No local repair suffices; a strategy change does

$$\forall t, d': \{do(d_t = d')\} \text{ insufficient},\qquad \exists z': \{do(z=z')\} \text{ suffices}$$

Required: a process-level candidate **must** be present in $R^{*}$.

**A55: this is a statement about the repair lattice, and it is explicitly NOT the
definition of $Z_P$.** The earlier text said this case "distinguishes a genuine
process fault from a co-occurrence of locals", which conflated *process-granularity
repair* (`02` §5.1) with the *commit-integrity fault* (A55). The two can come
apart in both directions: a C4-shaped episode can exist with
$z^{\text{in-force}} = z^{\text{proposal}}$ and no commit fault at all (the
proposal itself is simply a poor option, and $do(z=z')$ is the only route), and a
C3 commit fault can be repairable by a single local intervention. C4 asserts the
lattice statement only; the fault label is C3's business.

### C5 — Environment fault

An external perturbation causes the failure while the agent's own choices were
sound.

Required: $p_E > 0$ or $p_U > 0$ — the method **must not be forced** to place the
blame on decision or execution. An architecture that cannot emit "not my fault"
fails here by construction, and that failure must be visible.

### C6 — Write collision

A scalar instance of **I1**: construct two units whose naive parameterisation
would address one entry, and assert the implementation either refuses or declares
the sharing.

### C7 — Two independent sufficient size-1 repairs

$$r_1 \text{ suffices},\quad r_2 \text{ suffices},\quad r_1 \neq r_2$$

Required: $|R^{*}| = 1$ with $\#R^{*} = 2$. Reporting $\{r_1 + r_2\}$ as a size-2
"whole-process" repair is a failure.

*Legacy failure this prevents:* the old code merged co-occurring independent
faults and called the result `WholeProcess`, which is a different error from the
one in I4 and must be caught separately.

### C8 — External plant fault with a correct controller

$C_X$ is correct; $P$ misbehaved.

Required: **no update to anything** is the default and correct action. An arm that
updates $Q_D$ here is wrong. This is the control condition that makes "sometimes
the right answer is to change nothing" measurable.

---

## 3. Gate mechanics

| rule | |
|---|---|
| location | `tests/semantic/` in the rebuild namespace, run by the version runner before seeds |
| artifact | `experiments/<version>/semantic_gate.json` with per-case PASS/FAIL and the observed values |
| blocking | any FAIL blocks seed collection for **all** versions until fixed |
| determinism | the suite must give identical results across processes; it runs under the fingerprint check (`10-REPRODUCIBILITY-AND-OPS.md`) |
| scope | invariants I1–I6 run on every episode of every run, not only in the suite |

### 3.1 What a failure means

A failed case is a **bug**, never a result. It is fixed, and — per the
no-mid-collection rule — if it is found after seeds have been collected, the seed
set is void and collection restarts from $N=0$.

---

## 4. Deliberate omissions

* The suite does **not** test learning quality. Semantic correctness is about
  *what the code changes*, not whether changing it helps.
* The suite does **not** test attribution accuracy. Identifiability says the
  answer is recoverable; whether a method recovers it is V0.1R's question.
* The suite does **not** replace the identifiability gate. That gate is about the
  environment; this one is about the implementation. A correct implementation of
  an unidentifiable design passes here and fails there.
