# 18 — V0.3R B1: the $D_Q$ row — implementation draft

$$\boxed{\text{DRAFT — for review. Not frozen, not authorised, no code written.}}$$

This is the implementation draft A76 §63.13 and the $D_{patch}$ slice left owed. It
pins the interfaces and invariants of the **$D_Q$** row of the compatibility matrix
(A76 §63.9), together with the one thing that has to change before $D_Q$ can exist at
all: the boolean `requires_alternative` is not an information contract, and $D_Q$ needs
one.

**Status of every claim below.** Sections 1–7 are *proposals*. Section 8 lists the
rulings I need from you, and I have marked each proposal that I consider genuinely
open rather than forced. Nothing here is implemented.

**This draft carries no amendment number.** An earlier revision of this line said "on
approval this becomes A77" and `spec_audit.py` immediately reported `A77` as an amendment
reference with no amendment heading — correctly. A number that is named before the
amendment exists is a phantom in the reference graph: the citation closes and the
amendment is un-logged. The number is assigned at approval, in `12-AMENDMENTS.md`, and
not here.

---

## 0. What the boolean cannot express

The $D_{patch}$ slice routes information with one flag
(`_Law.requires_alternative`). It works because $D_{patch}$ has exactly two
information states:

$$\text{no envelope} \quad\text{or}\quad \{a^+\}$$

$D_Q$ breaks that in **two directions at once**, and the second is the one that matters:

$$\boxed{\text{1. } L_0 \text{ now NEEDS an envelope}}$$

`FactualReturnWrite` is $L_0$ and its target $G_t^F$ is a *factual* quantity. Under the
old flag, "requires no alternative" means "receives nothing", so the $L_0$ arm would be
handed no target at all and could not be implemented.

$$\boxed{\text{2. } L_1 \text{ must be expressible as ABSENT}}$$

There is no $D_Q\times L_1$ arm (A76 §63.5). Under the old flag, "does not require an
alternative" *is* the $L_1$-excluded case, so the absence and the $L_0$ case are the
**same value**. A registry built on the boolean cannot state "this cell is empty"; it
can only state "this arm needs nothing", and the two would be confused the first time
someone adds a law.

A third, quieter failure: the boolean is read by the runner to decide *what to build*.
Once the envelope has more than one field, "the law did not read the higher-tier field"
is again weaker than "the runner never built it" — the A59 shape, one level down.

---

## 1. The information contract

### 1.1 The tier enum

```python
class Tier(Enum):             # opaque: no ordering, no arithmetic
    L0_FACTUAL = "L0_factual"
    L1_CORRECTIVE = "L1_corrective"
    L2_COUNTERFACTUAL = "L2_counterfactual"
    L3_ORACLE = "L3_oracle"
```

A law declares **exactly one** tier. The `_Law` sentinel rule is unchanged and stays
enforced: an undeclared tier is `None`, `_tier` accepts only a real `Tier`
(`type(tier) is Tier`), and `Tier.L0_FACTUAL` is **not** the default. `bool` subclassing
is how the old flag failed; an `int`-valued enum would reproduce the same failure one
step later (`0`, `True` and `1` would all be accepted for `L0_FACTUAL`), so the enum is
deliberately **not** an `IntEnum`:

$$\boxed{\text{the accepted type is a closed enum, not an integer and not a bool}}$$

`test_8i`'s mutation anchor moves from the bool check to the enum check; `0`, `True`,
`"L0_factual"` and `Tier` itself must all be rejected.

### 1.2 Delivery is a property of (architecture, tier), not of the law

$$\boxed{\text{fields}(\alpha, \ell) \;=\; \text{the complete field set the runner builds
and hands to any law in cell } (\alpha,\ell)}$$

$\alpha$ is the **store slice** (§6.1) — for the patch architectures it is a value-free
store, for $D_Q$ a scalar one. The contract is *complete*, not permissive:

$$\boxed{\text{a law is handed exactly } \text{fields}(\alpha,\ell)\text{ — no more and
no less}}$$

| $\alpha$ | $L_0$ | $L_1$ | $L_2$ | $L_3$ |
|---|---|---|---|---|
| value-free (`D_patch`, $X$, $P$) | $\varnothing$ | $\{a^+\}$ | **ill-typed** | $\varnothing$ (restore = delete) |
| scalar ($D_Q$) | $\{G_t^F\}$ | **no value-preserving law** | $\{G_t^F,\ a^+,\ G_t^{CF}(a^+)\}$ | $\{Q_D^\ast(x_t,\cdot)\}$ |

Two things this buys, both of them already-learned lessons applied one level up:

* the envelope's **field set is exact**, exactly as the credited address set is exact.
  `keys(envelope) == fields(α, ℓ)`, so "an extra field was delivered" is a
  `PROTOCOL_ERROR` in the same sense that a non-credited address key now is. The
  $D_{patch}$ fix is the special case $\text{fields}=\varnothing$;
* $L_0$ is again *never handed* $a^+$ — the property the old flag was protecting — while
  still receiving the factual field it legitimately needs. The two requirements no
  longer collide because the field set, not a boolean, is the unit of delivery.

### 1.3 Typed compatibility, made executable

A76 §63.9 says the matrix is "typed compatibility, not a Cartesian product". That is
now a check rather than a table:

$$\boxed{\text{scalar store} \wedge \text{tier} = L_1 \;\Longrightarrow\;
\texttt{PROTOCOL\_ERROR}}$$

The justification is A76's own: $L_1$ knows $a^+$ **without its value**, and on a scalar
store every write is a value. `PositiveAlternative` is retired for exactly this reason;
this rule stops it coming back under a new name. On a value-free store the same cell is
perfectly well-typed (`SetAlternative`), which is why the rule is conditional on the
slice and not global.

### 1.4 `NoWrite` is a per-cell reference

A76: `NoWrite` "is available at every tier as the same-tier reference, simply ignoring
the extra information." Read literally that would put a reference in the empty $L_1$ cell
of the scalar slice, i.e. a reference to nothing — and it would also collide with §1.3,
because `NoWrite` is a law and `NoWrite(L1)` on a scalar store declares an ill-typed
cell. The reading this draft proposes:

$$\boxed{\text{one } \texttt{NoWrite}(\ell) \text{ per NON-EMPTY cell } (\alpha,\ell)}$$

so the scalar slice needs **three** references ($L_0$, $L_2$, $L_3$) and the patch slice
needs **two** ($L_0$, $L_1$, $L_3$ — $L_2$ is ill-typed there too). This is a statement
about availability, not about the registry: the reference is instantiated for the cell
being compared, and the $D_{patch}$ slice keeps **exactly the one it has today** (at
$L_0$), so `LAWS` still holds four arms and `independent_treatment_count()` is still 3.
Flagged as **D8**; the alternative reading ("a reference is always available, whatever the
cell") needs §1.3 to exempt `NoWrite`, which then needs a reason, and I could not find one
that is not "`NoWrite` does not read it" — the A59 argument.

The tier is **recorded in the ledger**, so the pairing (arm, its same-tier reference) is
auditable rather than inferred. This does not shrink $N_{\text{independent treatments}}$:
`NoWrite` is a reference in every cell, not a treatment in any.

### 1.5 Migration of the $D_{patch}$ arms

The four registered arms keep their semantics and their tiers:

| arm | was | becomes |
|---|---|---|
| `NoWrite` | `requires_alternative=False` | `Tier.L0_FACTUAL` — the reference for the cell the slice actually runs; the registry is unchanged |
| `DeleteFactualPatch` | `False` | `Tier.L0_FACTUAL` |
| `SetAlternative` | `True` | `Tier.L1_CORRECTIVE` |
| `LocalOracleRestore` | `False` (alias) | `Tier.L3_ORACLE` (alias of `DeleteFactualPatch` **on this slice**) |

`LocalOracleRestore`'s declared tier changes from `L0` to `L3` and its **behaviour does
not**, because on a value-free store the healthy referent *is* "no override" and the
$L_3$ restore therefore canonicalises to a deletion. That is not a coincidence to be
papered over: it is the reason §63.8 registers it as an alias on this slice and as a new
operation on $D_Q$. The alias test keeps asserting `plan is DeleteFactualPatch.plan`; a
new test asserts the tier is `L3` while the plan is unchanged, so "the tier is metadata"
cannot silently become "the tier is ignored".

$$\boxed{\text{a law's tier is metadata for delivery; two arms may share a plan and differ
in tier (alias), never the reverse}}$$

---

## 2. The $D_Q$ store

`learner/store.py` states the position this draft has to move:

> There is **no** `Q_D^L` here: an empty stub would later be mistaken for frozen Q
> semantics.

That reason is sound, and it is why $D_Q$ needs a *specified* store rather than a fourth
empty dict. Four things must be pinned.

### 2.1 Address

The credited address stays $\rho_D(\texttt{Decision}_t) = (s_t,z_t,m_t)$ — **one receipt
per credited context**, as §63.10 requires. The scalar entry needs an action too, so the
*store* key is strictly finer than the credited address:

$$\boxed{\texttt{QAddress}(s, z, m, a)}, \qquad
\rho_Q(\texttt{Decision}_t, a) = \bigl(\rho_D(\texttt{Decision}_t), a\bigr)$$

Two keys, two roles, written out so that they cannot be confused:

| key | role | budgeted? |
|---|---|---|
| `DecisionAddress` | the credited context, the ledger receipt, the locality unit | **yes**, $B_{\text{addr}}$ |
| `QAddress` | one scalar entry inside that context's row | no — reported as $N_{\text{scalar}}$ |

This is the concrete content of "`DualReturnWrite` touching two entries still counts as
**one** addressed context".

### 2.2 Value domain, and what "healthy" means for a scalar store

$$\boxed{Q_D^L : \texttt{QAddress} \rightharpoonup \mathbb{R}_{\text{finite}}}$$

The store is a **sparse override table on the frozen reference**, so the healthy state is
the empty state — the same rule the other three stores follow:

$$Q^{\text{eff}}(x, a) = \begin{cases} Q_D^L(x,a), & (x,a) \in Q_D^L\\
Q_D^\ast(x,a), & \text{otherwise}\end{cases}$$

$$\boxed{\text{an absent entry means ``no deviation'', NOT ``the value is } 0\text{''}}$$

Assigning the reference value canonicalises to **deletion**, at the transaction boundary,
like $C_P^L$ and $C_X^L$:

$$Q_D^L(x,a) \leftarrow Q_D^\ast(x,a) \;\Longrightarrow\; Q_D^L.\text{pop}(x,a)$$

Three consequences worth stating because each is a place a plausible implementation goes
wrong:

* **`argmax` needs no tie-break invention.** Over $Q^{\text{eff}}$ the frozen tie-break
  ("lowest action index", A76 §63.3) already exists and is the same one $a^+$ uses;
* with an empty store, $Q^{\text{eff}} \equiv Q_D^\ast$ **row for row**, so the $D_Q$
  architecture at the healthy state must reproduce the ordinary baseline policy exactly.
  That is a gate, not a remark (§7 G6);
* $Q_D^\ast$ becomes a **run-time** dependency of the $D_Q$ read path. This is not a new
  truth exposure: $Q_D^\ast$ is already what the baseline `command_provider` is built
  from, and it carries no $T/P$, no $S_{r,\pm}$ and no world identity. Flagged as D1
  because it is a real widening of what the read path touches.

### 2.3 Read path and patch priority

The decision channel of the $D_Q$ architecture is

$$a_t^L = \arg\max_{a \in A_z(m,s)} Q^{\text{eff}}(x_t, a)
\quad\text{(lowest action index on ties)}$$

and the relationship to the patch channel must be pinned, because both stores address the
same context:

$$\boxed{P_D^L \text{ shadows } Q_D^L} \quad\text{i.e.}\quad
a_t^L = \begin{cases} P_D^L[x_t], & x_t \in P_D^L \text{ (patch architecture)}\\
\arg\max_a Q^{\text{eff}}(x_t,a), & \text{otherwise}\end{cases}$$

The two stores are never populated by the same arm in this version (the matrix has
$D_{patch}$ **xor** $D_Q$), so the priority is a **defensive ordering**, not a live
mechanism. It is written down anyway because "which store wins" is exactly the kind of
thing that otherwise gets decided by dict iteration order the first time both exist.
Flagged as D2: the alternative is to make co-residence a `PROTOCOL_ERROR`.

### 2.4 Fingerprint

`fingerprint()` gains a fourth component, canonically sorted like the others:

```python
def _canon_q(overrides):        # Q:key|value_hex, lexicographically sorted
    rows = [f"Q:{s.x},{s.y},{s.t},{s.kappa},{s.phi},{addr.z},{addr.m},{addr.a}"
            f"|{float(v).hex()}"
            for addr, v in overrides.items()]
    return "\n".join(sorted(rows))
```

Values are canonically encoded with `float.hex()`: exact, round-trippable, and independent
of repr settings and locale (`str` and `repr` happen to agree for floats in CPython 3, so
the choice is made on exactness rather than on a difference that does not exist). NaN and
infinities are rejected at the transaction boundary — a NaN entry would make
$fp_{\text{pre}} = fp_{\text{post}}$ depend on comparison semantics rather than on
content, and the per-receipt canary `APPLIED ⟺ store changed` would inherit the same
ambiguity. Adding an *empty* fourth component to the canon changes the digest string for
patch runs and **no invariant**: the ledger only ever compares $fp_{\text{pre}}$ with
$fp_{\text{post}}$ inside one run, and no committed artifact records an absolute learner
fingerprint (checked: `experiments/**/*.json` has no `fingerprint_pre`/`fingerprint_post`).

---

## 3. The factual target $G_t^F$

$$\boxed{G_t^F = \sum_{j=t}^{T_F-1} r_j^F}$$

the sum of `StepResult.reward` from action-step $t$ to the end of **that factual
episode** — not from $t=0$, and not the episode return. Mode A, undiscounted, frozen step
cost included (A76 §63.2).

Three pins:

* **Not `Q_D^\ast`.** `FactualReturnWrite` targets the *observed* suffix return. In a
  faulted episode $G_t^F \neq Q_D^\ast(x_t,a_t^F)$ in general, and substituting the
  reference would make the $L_0$ law an oracle in disguise — the same defect class as the
  retired `+1`;
* **$L_0$ because the learner already has the rows.** $r_j$ and $t$ are in
  `ROW_SCHEMA`; $G_t^F$ is a *function of* learner-visible evidence, not extra
  information. That is a stronger statement than "it is legal at $L_0$" and it is what
  `FactualReturnWrite` will be reported as;
* **the scale is the reference's scale by construction.** `dp.py` stores an undiscounted
  return-to-go (`row[a] = res.reward + v[next]`), so $G_t^F$ is on the same scale as the
  entries it is written into. The best reachable return is $0.9800$, and the retired
  `+1` overstated it by exactly one `STEP_COST` — the audit that produced §63.2.

---

## 4. The counterfactual target $G_t^{CF}(a^+)$, and the prefix invariant

### 4.1 The replay

**Not a suffix simulator.** One full-episode replay from $t=0$, with the factual
episode's own configuration and **only** the decision node at $t$ changed:

$$\text{config}^{CF} = \bigl(\kappa,\ \tau,\ \text{mask},\ z^{\text{fault}},\ z_0,\
\text{controller},\ C_P^L,\ \text{mode A}\bigr) \equiv \text{config}^{F}$$

$$\boxed{\text{interventions}^{CF} = \bigl(\text{interventions}^{F} \setminus
\{do(d_t=\cdot)\}\bigr) \cup \{do(d_t = a_t^+)\}}$$

then

$$\boxed{G_t^{CF}(a_t^+) = \sum_{j=t}^{T_{CF}-1} r_j^{CF}}$$

Four pins:

* **the kernel already supports this, frozen and unmodified.**
  `Intervention.decision(t, action)` exists and `rollout`'s command priority is frozen as
  `do(d_t) > Z_D > command_provider`, so this needs **no kernel extension**. That was
  worth checking before committing to the design rather than after;
* **replacement, not addition, when the factual episode already intervened at $t$.**
  `InterventionSet` de-duplicates on `("decision", t)` and two decisions at one $t$ are
  `MALFORMED`, so "add" would be ill-defined precisely when it is needed. Replacing is
  well-defined and is what "the counterfactual to *this* episode" means;
* **$a^+$ needs no re-check for admissibility here** — it is already verified inside
  $A_z(m,s)$ by the envelope validator, which is what stops the replay raising
  `MalformedIntervention` halfway through;
* **the replay is evaluator-side and stays there.** It reads the mask, the tape and the
  reference; it is the definition of the $L_2$ field and never enters a law.

### 4.2 The invariant

$$\boxed{\text{rows}\bigl(\text{trace}^{CF}\bigr)[0:t] = \text{rows}\bigl(\text{trace}^{F}\bigr)[0:t]
\quad\text{else } \texttt{PROTOCOL\_ERROR}}$$

compared over the **row schema** $(x,y,t,\kappa,\phi,z,m,a^{cmd},a^{realized},reward)$ —
the same `ROW_SCHEMA` the locator uses, so "the prefix is the same" means the same thing
in both places. Comparing rows rather than a summary is deliberate: the row already
carries $z$ and $m$, so this single comparison **subsumes** the option-in-force equality
and the context equality, and no second, weaker check is added beside it.

Two honest notes:

* the equality is *expected by determinism* (fixed `SemanticTape`, no earlier
  intervention). A check that cannot fail is not evidence — its value here is that it
  converts a **silent** corruption (a replay built from the wrong config, a provider with
  hidden state) into a fail-stop. It is therefore tested **by mutation**, not by
  observing that it passes: §7 G5 perturbs the replay config and requires red;
* a violation is `PROTOCOL_ERROR` (§63.3), never a $0$ target and never a
  `NO_VALID_ALTERNATIVE`. A zero would be indistinguishable from a legitimate
  counterfactual return of zero and would enter B2 as an arm that "learned nothing".

---

## 5. The $D_Q$ arms, and the absence that must stay absent

| tier | arm | write |
|---|---|---|
| reference | `NoWrite(ℓ)` | — |
| $L_0$ | `FactualReturnWrite` | $Q_D^L(x_t,a_t^F) \leftarrow G_t^F$ |
| $L_1$ | **— none —** | — |
| $L_2$ | `CounterfactualReturnWrite` | $Q_D^L(x_t,a_t^+) \leftarrow G_t^{CF}(a_t^+)$ |
| $L_2$ | `DualReturnWrite` | both of the above, one transaction |
| $L_3$ | `LocalOracleRestore` | $Q_D^L(x_t,\cdot) \leftarrow Q_D^\ast(x_t,\cdot)$, i.e. **row-wise deletion** |

$\alpha = 1$ (full backup) for both $L_0$/$L_2$ arms; the $L_3$ restore is not a backup at
all and has no $\alpha$. $\alpha < 1$ is a secondary sensitivity study and may never pick a
winner or rescue a primary result (§63.5).

The write sets are what separate the two $L_2$ arms, and they are stated positively so
that neither has to be inferred from the other:

$$\text{write set}\bigl(\texttt{CounterfactualReturnWrite}\bigr) = \{(x_t, a_t^+)\}, \qquad
\text{write set}\bigl(\texttt{DualReturnWrite}\bigr) = \{(x_t, a_t^F),\ (x_t, a_t^+)\}$$

so they answer different questions — "correct it and teach it what the alternative
returns" versus "teach it only what the alternative returns" — and neither is a subset to
be collapsed into the other.

$$\boxed{N_{\text{independent treatments}}(D_Q) = 4}$$ (reference excluded; the $L_3$ arm is
a genuinely new operation on this slice — §63.8)

`DualReturnWrite` in detail, because §63.5's prohibition is easy to violate silently:

$$\boxed{\text{two scalar writes, one addressed decision context, one transaction}}$$

* both targets from the **pre-update** state — the factual entry may not be read as part
  of computing the counterfactual one (they come from two different traces anyway, but
  the rule is what forbids "write $a^F$, then let the second target observe it");
* at most two entries in $Q_D^L$ and exactly **one** receipt;
* `n_scalar` ∈ {0, 1, 2} for this arm at one address — $0$ when both writes are no-ops,
  which is `EVALUABLE_NOOP`, not a failure.

### 5.1 The absence, enforced

"No $L_1$ arm on $D_Q$" is a fact about a registry, and a registry cannot prove a
negative. What *can* be enforced is the reason it is absent (§1.3), plus the two ways it
would come back:

* a `FactualReturnWrite` that consumes the $L_2$ field while declaring $L_0$ — caught by
  exact field delivery: `fields(D_Q, L0) = {G_t^F}` and $a^+$, $G_t^{CF}$ are not in it;
* a `CounterfactualReturnWrite` that degenerates to "write $a^+$ with a constant" when
  the counterfactual is missing — caught by §4.2: a missing counterfactual is a
  `PROTOCOL_ERROR`, and the `0.98`/`+1` constants are retired, not dormant.

---

## 6. Runner generalisation and the ledger

### 6.1 One store slice, two architectures

The current runner hard-codes the decision **patch** store in four places (`_store_view`,
the `Edit(DECISION, ...)` check, `DecisionWriteReceipt`, `scalar_metrics_applicable`). The
$D_Q$ row needs the same totality, locality and atomicity, and duplicating them is the
defect route C removed for the fault grammar. So the runner is parameterised by a
descriptor, and *both* architectures go through the same code:

| field | `D_patch` | `D_Q` |
|---|---|---|
| credited address | `DecisionAddress` | `DecisionAddress` |
| store | `DECISION` | `Q` |
| entry address | `DecisionAddress` | `QAddress` |
| value | `Action \| None` | `float` |
| healthy referent | no override | $Q_D^\ast$ |
| value-free | **yes** | no |
| delta metric | none ($N_{\text{scalar}}=0$) | §6.3 |

Everything already frozen stays **identical and single-implementation**: plan totality,
real edit locality (credited = plan = edit), one transaction per scene, per-receipt
`APPLIED ⟺ store changed`, exact envelope, four-status taxonomy, `PROTOCOL_ERROR`
fail-stop.

One locality clause is $D_Q$-specific and is stated as such:

$$\boxed{\text{WriteSet}(L_3) \subseteq \{x_t\} \times A_z(m,s)}$$

the $L_3$ row restore may touch **every action at the credited context** and no other
context. That is §63.8's "the credited context's row only" made checkable, and it is the
one place where a law writes more than one entry at an addressed context.

### 6.2 `scalar_metrics_applicable`

$$\boxed{\text{scalar\_metrics\_applicable} = \text{the slice's store is scalar-valued}}$$

A property of the **slice**, not of the outcome: it is `True` for every $D_Q$ run,
including a run where nothing changed, and `False` for every $D_{patch}$ run. The flag
answers "are these three numbers defined here?", and "did anything change?" is what the
receipts and the fingerprint answer. Tying the flag to the outcome would make
`n_scalar = 0` mean two different things depending on the arm — which is exactly how the
old `APPLIED = "wrote a scalar"` definition went wrong.

### 6.3 Scalar accounting

For each entry that changed, with $\theta$ the stored value and $\bot$ meaning *absent
from the override table*:

$$\Delta\theta(e) = \begin{cases}
\lvert \theta_{\text{post}} - \theta_{\text{pre}} \rvert, & \text{updated}\\
\lvert \theta_{\text{post}} \rvert, & \text{created}\\
\lvert \theta_{\text{pre}} \rvert, & \text{deleted}\end{cases}$$

$$\boxed{N_{\text{scalar}} = \#\{e : \text{the entry changed}\},\quad
\Sigma = \sum_e \Delta\theta(e),\quad \text{Max} = \max_e \Delta\theta(e)}$$

The $\lvert\cdot\rvert$-against-absent convention is **accounting only**, and saying so is
the point: an absent entry is *not* a value of $0$ (§2.2), so

$$\boxed{\Sigma = 0 \;\not\Rightarrow\; \text{nothing changed}}$$

and no invariant is built on $\Sigma$. What *is* enforced — and every line below assumes
the arm writes **one** store, the slice, which is the whole B1 design; an arm writing two
stores would need them restated per store:

| invariant | why |
|---|---|
| `N_scalar == 0 ⟺ fp_pre == fp_post` | the scalar count and the digest must agree; two independent witnesses of "changed" |
| `N_scalar == 0 ⟺ n_changed_addresses == 0` | no address changed if and only if no entry did |
| `N_scalar ≥ n_changed_addresses` | every changed address changed at least one entry |
| `Max ≤ Σ`, both `≥ 0`, `Max > 0 ⟺ Σ > 0` | arithmetic coherence of the reported triple |
| `N_scalar ≤ 2` for `DualReturnWrite` at one context | §5's "two scalar writes" |
| `N_scalar ≤ \lvert A_z(m,s)\rvert` for `LocalOracleRestore` at one context | the row has that many entries (G8) |

A75 §62.9's rule stands unchanged and unrepealed: these numbers are **accounting**, they
may not determine a status, and `APPLIED` remains "the store changed".

---

## 7. Gates

Every gate names the *plausible wrong implementation* it catches. Each is
mutation-verified in the style of `scripts/b1_interface_gate_selfcheck.py`: a textual
revert of the fix must turn the gate red, or the gate is reported as `NOT_A_GATE`.

| # | gate | the wrong implementation it catches | mutation that must turn it red |
|---|---|---|---|
| G1 | enum closure | a tier given as `0`/`True`/`"L0_factual"` silently accepted | accept `int` instead of `Tier` |
| G2 | exact field delivery | an $L_0$ law handed $a^+$; a law handed a field its cell excludes | build the union of all fields |
| G3 | `scalar ∧ L1` rejected | `PositiveAlternative` returns as a "scalar" law | drop the slice/tier compatibility check |
| G4 | $L_0$ needs no $L_2$ field | the $L_0$ arm fails when the counterfactual builder breaks | build all fields unconditionally |
| G5 | prefix equality | a replay from the wrong config, or a stateful provider, silently produces a CF number | perturb one replay field; require `PROTOCOL_ERROR` |
| G6 | healthy-state equivalence | the $D_Q$ read path *changes* the policy when the store is empty | break the argmax tie-break; require a row-level difference |
| G7 | created/deleted accounting | `N_scalar` misses a created entry, so `N_scalar = 0` with `fp_pre ≠ fp_post` | count only updated entries |
| G8 | row locality for $L_3$ | the restore writes a *different* context's row | widen the write set by one context |
| G9 | dual atomicity | the factual half commits, the counterfactual half throws | split the transaction in two |
| G10 | absence of the $L_1$ cell | an $L_1$ $D_Q$ law is registered and scored | register a stub $L_1$ scalar law |
| G11 | no oracle leakage into $L_0$ | `FactualReturnWrite` targets $Q_D^\ast$ instead of $G_t^F$ | substitute the reference value |
| G12 | `D_patch` unchanged | the store-slice refactor changes a patch arm's plan, status or ledger bytes | re-run the $D_{patch}$ suite against the generalised runner |

G12 is the regression that matters most and is the reason §6.1 is a refactor of *one*
implementation rather than a second runner: the whole $D_{patch}$ slice suite — the
alias identity, the per-receipt invariants, the plan/locality gates, the envelope gates
and the mutation self-check — plus the observable-preimage digest
`6034b9c75056424a3dec42c6363c370dbb980d289e8c16a653558bd9eadb4cc6` must all reproduce
**byte for byte** after it.

Note for whoever wires the mutations: the anchors in
`scripts/b1_interface_gate_selfcheck.py` are textual, and one of them straddles
`_run`'s pre-state lines. A refactor of `_run` must update those anchors, and the
self-check's `matched == 1` rule makes a stale anchor a visible
`MUTATION_NOT_APPLIED` rather than a silent pass.

---

## 8. Rulings I need

| # | question | my recommendation |
|---|---|---|
| **D1** | $Q_D^\ast$ becomes a run-time dependency of the $D_Q$ read path. Accept, or invert the store so the healthy-adjacent case is "no entry" for *all* actions and the policy falls back to `command_provider` wholesale? | **accept.** It is already the baseline provider's source, and there is no architecture-blind alternative for scoring absent actions. |
| **D2** | When both $P_D^L$ and $Q_D^L$ exist, patch shadows Q (§2.3) — or co-residence is a `PROTOCOL_ERROR`? | **patch shadows**, written down, since the matrix never populates both. |
| **D3** | $L_3$ on $D_Q$: row-wise deletion, or an explicit write of every $Q_D^\ast$ value with identity canonicalisation removed for this one arm? | **row-wise deletion.** The latter would make `LocalOracleRestore` create entries whose content equals the reference, i.e. a non-canonical store, and A76 §63.8's whole point is that this arm is new *in scope*, not in encoding. |
| **D4** | `DualReturnWrite`'s write set: $\{(x_t,a_t^F), (x_t,a_t^+)\}$ (two entries), or only the counterfactual entry with the factual one assumed? | **two entries, one transaction** (§5). `CounterfactualReturnWrite` writes one entry and `DualReturnWrite` two; they are different write sets and therefore different treatments, not a subset relation to be collapsed. |
| **D5** | Is a run where the updated context is never revisited a *scored* run for $D_Q$? $Q_D^L$ changes, $J_D^L$'s predicate never fires, $\Delta W \neq 0$ but the behaviour never manifests. | **scored, and flagged**, not dropped — this is A75's $S_{r,0}$ population and B2's problem, not B1's. B1 must not re-define the denominator. |
| **D6** | Which of §1–§6 becomes the amendment, and does the runner refactor (§6.1) land **before** the first $D_Q$ law, or alongside it? | **refactor first, alone**, with the $D_{patch}$ suite as the regression (G12). A refactor bundled with new semantics cannot be attributed if something moves. |
| **D7** | Is the tier enum frozen as an opaque `Enum` or as an `IntEnum`? | **opaque** (§1.1): nothing in the design compares tiers numerically, and `L2 > L1` invites "higher tier = better arm". |
| **D8** | Does the empty $L_1$ cell of the scalar slice carry a `NoWrite` reference? | **no** (§1.4): one `NoWrite` per non-empty cell. The alternative needs §1.3 to exempt `NoWrite`, and the only available reason is "it does not read it" — the A59 argument. |

---

## 9. Not in this draft

Stated so the boundary is not read as an oversight:

* **no B2 endpoints.** `HarmRate`, `ΔG`, `RecoveryFraction` and the `NOT_EVALUABLE`
  denominator rule are unchanged and still open; §63.8 already defers "which oracle is
  B2's denominator" to B2;
* **no regime I numbers.** Intermittent-regime statistics stay deferred until $T/P$
  semantics settle;
* **no selection problem.** How an ordinary learner *finds* $a^+$ is V0.4R's;
* **no claim about $\Gamma$.** The standing boundary is untouched: $\Gamma^+$ and the
  truth come from the same $\pi_{\text{credit}}$, so every census measures over-credit
  under a **fixed** ontology and does not validate it;
* **no $08$-V03R rebase.** That document still carries the $do(z{=}z')$ error and remains
  deliberately unsynchronised; this draft does not touch it;
* **no amendment is edited in place.** A76 §63 stays as written; everything here that
  changes it is proposed as a new amendment, to be numbered if and when you approve it.
