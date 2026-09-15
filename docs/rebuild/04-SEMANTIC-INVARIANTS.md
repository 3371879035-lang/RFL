# 04 — Semantic invariants and the case suite

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

### I4 — No label reconstruction from traces

Cause labels and repair labels come only from the forward generation
(`02-SCM.md` §6). Any code path that derives a cause from a rollout is prohibited.

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

### C3 — Process wrong, every local decision defensible

Each $d_t$ is locally reasonable given its context, yet the episode fails because
$z$ is wrong for this context.

Required: the process level is blamed, and no local decision is written.

### C4 — No local repair suffices; a strategy change does

$$\forall t, d': \{do(d_t = d')\} \text{ insufficient},\qquad \exists z': \{do(z=z')\} \text{ suffices}$$

Required: a process-level candidate **must** be present in $R^{*}$. This is the
case that distinguishes a genuine process fault (§5.1 of `02-SCM.md`) from a
co-occurrence of locals.

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
