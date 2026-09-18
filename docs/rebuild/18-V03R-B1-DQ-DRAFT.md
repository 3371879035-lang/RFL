# 18 — V0.3R B1: the $D_Q$ row — implementation draft (revision 2)

$$\boxed{\text{DRAFT — for review. Not frozen, not authorised, no code written.}}$$

This is the implementation draft A76 §63.13 and the $D_{patch}$ slice left owed. It
pins the interfaces and invariants of the **$D_Q$** row of the compatibility matrix
(A76 §63.9), together with the one thing that has to change before $D_Q$ can exist at
all: the boolean `requires_alternative` is not an information contract, and $D_Q$ needs
one.

**Revision 2** incorporates the rulings on **D1–D8** and the six corrections raised
against revision 1. Two of the rulings **overturn my recommendation** and are marked as
such: **D2** (co-residence is a `PROTOCOL_ERROR`, not a shadowing priority) and **D5**
(no $S_{r,0}$ classification). Four blockers in revision 1 were substantive:

1. `fields` was keyed by *store kind*, which is wrong for $X$ and $P$ (§1.2);
2. the $G_t^{CF}$ replay config **omitted the decision read path** (§4.1);
3. the scalar $\Delta$ was measured against an arbitrary zero instead of $Q_D^\ast$ (§6.3);
4. the $S_{r,0}$ claim in D5 was a category error (§5.2).

**This draft carries no amendment number.** An earlier revision said "on approval this
becomes A77" and `spec_audit.py` immediately reported `A77` as an amendment reference
with no amendment heading — correctly. A number named before the amendment exists is a
phantom in the reference graph: the citation closes and the amendment is un-logged. The
number is assigned at approval, in `12-AMENDMENTS.md`, and not here.

---

## 0. What the boolean cannot express

The $D_{patch}$ slice routes information with one flag
(`_Law.requires_alternative`). It works because $D_{patch}$ has exactly two
information states:

$$\text{no envelope} \quad\text{or}\quad \{a^+\}$$

$D_Q$ breaks that in **two directions at once**:

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
class Tier(Enum):             # opaque: no ordering, no arithmetic, no truthiness
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

Ruled as **D7**: no tier comparison, no tier arithmetic, and no boolean inference from a
tier. `0`, `True`, `"L0_factual"` and `Tier` itself must all be rejected; `test_8i`'s
mutation anchor moves from the bool check to the enum check.

### 1.2 Delivery is a property of (architecture, tier)

$$\boxed{\text{fields}(\textbf{architecture},\ \ell) \;=\; \text{the complete field set
the runner builds and hands to any law in that cell}}$$

$$\boxed{\text{a law is handed exactly } \text{fields}(\alpha,\ell)\text{ — no more and
no less}}$$

**Keyed by architecture, not by a kind of store.** Revision 1 grouped $D_{patch}$, $X$
and $P$ as "value-free" and gave all three $L_1 = \{a^+\}$. That abstraction is wrong
twice over:

* $P$'s assisted content is $z^{\text{proposal}}$, not $a^+$ — a different object with a
  different provenance ($\rho_P$ needs it as the *key*, which is exactly why
  $P_{id}\in L_1$ and not $L_0$, A76 §63.1);
* $X_{id}$ is $L_0$ and its content is the **factual** $a^{cmd}$, so $X$'s $L_0$ field
  set is not empty either.

"Value-free" describes a store's *value domain*. It does not describe what an
architecture's tiers carry, and the two coincided only for the single row that had been
implemented. This revision freezes **two rows**:

| architecture | $L_0$ | $L_1$ | $L_2$ | $L_3$ |
|---|---|---|---|---|
| $D_{patch}$ | $\varnothing$ | $\{a^+\}$ | ill-typed | $\varnothing$ (restore = delete) |
| $D_Q$ | $\{G_t^F\}$ | **no substantive treatment** (§1.4) | $\{G_t^F,\ a^+,\ G_t^{CF}(a^+)\}$ | $\{Q_D^\ast(x_t,\cdot)\}$ |

$X$ and $P$ keep their A76 §63.7 content, which this table does not restate, and get
their own rows when they are implemented. Inventing their field sets now would be a
generalisation from one data point — the error this table just corrected.

One cell in the second row looks like it contradicts §1.3 and does not: $L_2$ delivers
$a^+$ even though $D_Q\times L_1$ has no treatment. The difference is what $a^+$ is *for*.
At $L_1$ it would have to be the target **value**, and a bare action is not a value on a
scalar store — that is the whole reason the cell is empty. At $L_2$ it is the **index** of
the target: $G_t^{CF}$ is meaningful only as $G_t^{CF}(a_t^+)$, and `DualReturnWrite` needs
$a_t^+$ as the entry's address. The pair is the content; the action alone is not a target.

Two things the exactness rule buys, both of them earlier lessons applied one level up:

* the envelope's **field set is exact**, exactly as the credited address set is exact.
  `keys(envelope) == fields(α, ℓ)`, so "an extra field was delivered" is a
  `PROTOCOL_ERROR` in the same sense that a non-credited address key now is; the
  $D_{patch}$ hardening is the special case $\text{fields}=\varnothing$;
* $L_0$ is again *never handed* $a^+$ — the property the old flag was protecting — while
  still receiving the factual field it legitimately needs. The two requirements no longer
  collide, because the field set rather than a boolean is the unit of delivery.

### 1.3 Typed compatibility, made executable

A76 §63.9 says the matrix is "typed compatibility, not a Cartesian product". That becomes
a check rather than a table:

$$\boxed{\text{a law that }\textbf{writes a scalar store}\ \wedge\ \ell = L_1
\;\Longrightarrow\; \texttt{PROTOCOL\_ERROR}}$$

The justification is A76's own: $L_1$ knows $a^+$ **without its value**, and on a scalar
store every write is a value. `PositiveAlternative` is retired for exactly this reason;
this rule stops it coming back under a new name. On a value-free store the same cell is
perfectly well-typed (`SetAlternative`), which is why the rule is conditional on the
architecture.

The rule constrains **writing** laws. It does **not** declare `NoWrite` type-illegal —
`NoWrite` writes nothing, and §1.4 gives the separate, non-A59 reason the empty cell
carries no reference.

The two rules are keyed differently on purpose, and conflating the keys is what revision 1
did. §1.2's field sets are keyed by **architecture** — what a tier *carries*. This rule is
keyed by the **store's value domain** — what a write *can be*. $X$ and $P$ have different
$L_1$ contents while both having value-free stores; they are not the same question.

### 1.4 The empty cell carries no reference

A76 says `NoWrite` "is available at every tier as the same-tier reference, simply
ignoring the extra information." Taken literally that would put a reference into the
empty $L_1$ cell of $D_Q$, i.e. a reference to nothing. Revision 1 justified omitting it
with the phrase *NoWrite does not read $a^+$* — **that was the A59 argument again**, and
it would license the same exemption for any arm that merely promises not to look.

$$\boxed{D_Q\times L_1 \text{ has no substantive compatible treatment } \Rightarrow
\text{ no comparison cell } \Rightarrow \text{ no same-tier reference}}$$

A reference exists to be compared against a treatment. With no treatment there is nothing
to compare against, and instantiating one would create an arm whose only role is to sit
in a table next to an empty cell. The consequence:

$$\boxed{\text{one } \texttt{NoWrite}(\ell) \text{ per cell that has a substantive
treatment}}$$

So the $D_Q$ slice instantiates **three** references ($L_0$, $L_2$, $L_3$; $L_1$ is
empty) and the $D_{patch}$ slice **three** as well ($L_0$, $L_1$, $L_3$; $L_2$ is
ill-typed). This is a statement about which references are instantiated, not about the
registry's contents: the $D_{patch}$ slice keeps **exactly the one reference it has
today** (at $L_0$), so `LAWS` still holds four arms and
`independent_treatment_count()` is still 3.

The tier is **recorded in the ledger**, so the pairing (arm, its same-tier reference) is
auditable rather than inferred. `NoWrite` is a reference in every cell it is instantiated
for, never a treatment.

### 1.5 Migration of the $D_{patch}$ arms

| arm | was | becomes |
|---|---|---|
| `NoWrite` | `requires_alternative=False` | `Tier.L0_FACTUAL` — the reference for the cell the slice actually runs; the registry is unchanged |
| `DeleteFactualPatch` | `False` | `Tier.L0_FACTUAL` |
| `SetAlternative` | `True` | `Tier.L1_CORRECTIVE` |
| `LocalOracleRestore` | `False` (alias) | `Tier.L3_ORACLE` (alias of `DeleteFactualPatch` **on this architecture**) |

`LocalOracleRestore`'s declared tier changes from $L_0$ to $L_3$ and its **behaviour does
not**, because on a value-free store the healthy referent *is* "no override" and the
$L_3$ restore therefore canonicalises to a deletion. That is not a coincidence to be
papered over: it is why §63.8 registers it as an alias on this architecture and as a new
operation on $D_Q$. The alias test keeps asserting `plan is DeleteFactualPatch.plan`; a
new test asserts the tier is $L_3$ while the plan is unchanged, so "the tier is metadata"
cannot silently become "the tier is ignored".

$$\boxed{\text{a law's tier is metadata for delivery; two arms may share a plan and differ
in tier (alias), never the reverse}}$$

---

## 2. The $D_Q$ store

`learner/store.py` states the position this draft has to move:

> There is **no** `Q_D^L` here: an empty stub would later be mistaken for frozen Q
> semantics.

That reason is sound, and it is why $D_Q$ needs a *specified* store rather than a fourth
empty dict.

### 2.1 Address

The credited address stays $\rho_D(\texttt{Decision}_t) = (s_t,z_t,m_t)$ — **one receipt
per credited context**, as §63.10 requires. The scalar entry needs an action too, so the
*store* key is strictly finer than the credited address:

$$\boxed{\texttt{QAddress}(s, z, m, a)}, \qquad
\rho_Q(\texttt{Decision}_t, a) = \bigl(\rho_D(\texttt{Decision}_t), a\bigr)$$

| key | role | budgeted? |
|---|---|---|
| `DecisionAddress` | the credited context, the ledger receipt, the locality unit | **yes**, $B_{\text{addr}}$ |
| `QAddress` | one scalar entry inside that context's row | no — reported as $N_{\text{scalar}}$ |

This is the concrete content of "`DualReturnWrite` touching two entries still counts as
**one** addressed context".

### 2.2 The store, and the injected reference view

$$\boxed{Q_D^L : \texttt{QAddress} \rightharpoonup \mathbb{R}_{\text{finite}}}$$

The store is a **sparse override table on the frozen reference**, so the healthy state is
the empty state — the same rule the other three stores follow:

$$Q^{\text{eff}}(x, a) = \begin{cases} Q_D^L(x,a), & (x,a) \in Q_D^L\\
Q_D^\ast(x,a), & \text{otherwise}\end{cases}$$

$$\boxed{\text{an absent entry means ``no deviation'', NOT ``the value is } 0\text{''}}$$

Assigning the reference value canonicalises to **deletion**, at the transaction boundary,
like $C_P^L$ and $C_X^L$:

$$Q_D^L(x,a) \leftarrow Q_D^\ast(x,a) \;\Longrightarrow\; Q_D^L.\text{pop}(x,a)$$

**The reference is injected, never fetched** (ruling D1):

$$\boxed{\texttt{QReferenceView} \text{ is a frozen read-only view passed in by the
caller}; \quad \texttt{learner/store.py} \text{ and the runner never call }
\texttt{solve\_reference()}}$$

and it is **not** part of any envelope: an ordinary law receives $a^+$, $G_t^F$,
$G_t^{CF}$ — never $Q_D^\ast$. The read path and the ledger's scalar accounting consult
the view; a law does not. That keeps D1's widening from becoming a second, unlogged
channel into the law layer. The existing `build_target_envelope(sol, …)` already takes
the reference as a *parameter* rather than reaching for it — that is the pattern, and
this ruling extends it from "the builder" to "everything that reads $Q_D^\ast$".

**Totality of the reference is measured, not assumed.** $\Delta$ (§6.3), the row restore
and the healthy-state policy equivalence all need $Q_D^\ast(e)$ for arbitrary
$e=(x,a)$ with $a \in A_z(m,s)$:

| quantity | value |
|---|---|
| reference rows | 13,824 |
| rows with `set(row) != set(A_z(m,s))` | **0** (0 partial, 0 inadmissible extras) |
| row-size histogram | $\{1{:}2592,\ 2{:}1728,\ 3{:}6480,\ 4{:}1872,\ 5{:}1152\}$ |
| $\lvert A_z(m,s)\rvert$ histogram | identical, row for row |

It is an exhaustive-support invariant of `solve_reference` and must be re-measured if the
solver or the grid changes. The boundary **fails stop** on a non-total row (§7 G16) rather
than letting a `KeyError` escape from inside the read path.

### 2.3 $P_D^L$ and $Q_D^L$ may not co-reside

**Ruled as D2, overturning my recommendation of a shadowing priority.**

$$\boxed{P_D^L \neq \varnothing \;\wedge\; Q_D^L \neq \varnothing
\;\Longrightarrow\; \texttt{PROTOCOL\_ERROR}}$$

$D_{patch}$ and $D_Q$ are different **architecture treatments**, and no legal experiment
populates both. My revision-1 proposal — patch shadows Q — defined an arbitrary priority
for a state that no legal run can reach, i.e. it would have *hidden* contamination
instead of exposing it. A priority rule is only justified when both channels are live;
here the correct reading of "this cannot happen" is a fail-stop, and if a future
experiment wants the combination, that is a new amendment with the composition semantics
written out.

The read path is therefore unambiguous:

$$a_t^L = \arg\max_{a \in A_z(m,s)} Q^{\text{eff}}(x_t, a)
\quad\text{(lowest action index on ties)}$$

**`argmax` needs no tie-break invention**: over $Q^{\text{eff}}$ the frozen tie-break
("lowest action index", A76 §63.3) is the same one $a^+$ uses.

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

* **Not $Q_D^\ast$.** `FactualReturnWrite` targets the *observed* suffix return. In a
  faulted episode $G_t^F \neq Q_D^\ast(x_t,a_t^F)$ in general, and substituting the
  reference would make the $L_0$ law an oracle in disguise — the same defect class as the
  retired `+1`;
* **$L_0$ because the learner already has the rows.** $r_j$ and $t$ are in `ROW_SCHEMA`;
  $G_t^F$ is a *function of* learner-visible evidence, not extra information. That is a
  stronger statement than "it is legal at $L_0$", and it is what `FactualReturnWrite` is
  reported as;
* **the scale is the reference's scale by construction.** `dp.py` stores an undiscounted
  return-to-go (`row[a] = res.reward + v[next]`), so $G_t^F$ is on the same scale as the
  entries it is written into. The best reachable return is $0.9800$, and the retired `+1`
  overstated it by exactly one `STEP_COST` — the audit that produced §63.2.

---

## 4. The counterfactual target $G_t^{CF}(a^+)$, and the prefix invariant

### 4.1 The replay

**Not a suffix simulator.** One full-episode replay from $t=0$, with the factual
episode's own configuration and **only** the decision node at $t$ changed:

$$\text{config}^{CF} = \bigl(\kappa,\ \tau,\ \text{mask},\ z^{\text{fault}},\ z_0,\
\text{controller},\ C_P^L,\ \texttt{DecisionReadView}_{pre},\ \text{mode A}\bigr)
\equiv \text{config}^{F}$$

$$\boxed{\texttt{DecisionReadView}_{pre} = \text{the complete pre-update decision read
path } (P_D^L/Q_D^L \to a^L), \text{ frozen}}$$

$$\boxed{\text{interventions}^{CF} = \bigl(\text{interventions}^{F} \setminus
\{do(d_t=\cdot)\}\bigr) \cup \{do(d_t = a_t^+)\}}$$

then

$$\boxed{G_t^{CF}(a_t^+) = \sum_{j=t}^{T_{CF}-1} r_j^{CF}}$$

**Why the decision read path is in the config (blocker 2).** Revision 1 listed only the
evaluator channels $C_P^L$ and $C_X^L$ and omitted the *learner's* decision read path. But
the replay runs a **full episode**, so it visits steps after $t$ — and at any of those
steps the decision channel consults the learner's persistent state. A replay that omitted
the pre-update decision view would silently fall back to the reference provider whenever
it hit an existing learner decision defect, which violates A76's frozen

$$\text{all targets are computed from the same pre-update learner state},$$

and would produce a $G_t^{CF}$ measured against a *different* learner than the one whose
factual return $G_t^F$ was measured. The counterfactual must therefore differ from the
factual episode in **exactly one** thing: the value at the decision node $t$.

This presumes the **factual** trace was itself produced under the same pre-update learner
state. That is A76 §63.10's third invariant ("all targets from the pre-update snapshot")
and it makes the identity $\text{config}^{F} \equiv \text{config}^{CF}$ an invariant of the
*experiment* rather than of the replay: the trigger episode is rolled out with the learner
state frozen, not updated online.

The rest of the config is unchanged from revision 1:

* **the kernel already supports the $do$.** `Intervention.decision(t, action)` exists and
  `rollout`'s command priority is frozen as `do(d_t) > Z_D > command_provider`, so this
  needs **no kernel extension**. Checked before committing to the design, not after;
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

Three honest notes:

* **the invariant is not sufficient for blocker 2, and is not offered as such.** A replay
  that dropped `DecisionReadView_pre` would diverge in the prefix *only if* the pre-update
  decision defect is actually visited before $t$. That is constructible (§7 G15 uses
  exactly such a scene), but it is a property of the scene, not of the rule. The rule that
  closes blocker 2 is structural — the config carries the view — and the invariant is the
  second, independent witness that catches the cases it can;
* the equality is *expected by determinism* (fixed `SemanticTape`, no earlier
  intervention). A check that cannot fail is not evidence — its value here is that it
  converts a **silent** corruption (a replay built from the wrong config, a provider with
  hidden state) into a fail-stop. It is therefore tested **by mutation**, not by observing
  that it passes;
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
| $L_3$ | `LocalOracleRestore` | $Q_D^L(x_t,\cdot) \leftarrow Q_D^\ast(x_t,\cdot)$, i.e. **row-wise deletion** (D3) |

$\alpha = 1$ (full backup) for both $L_0$/$L_2$ arms; the $L_3$ restore is not a backup at
all and has no $\alpha$. $\alpha < 1$ is a secondary sensitivity study and may never pick
a winner or rescue a primary result (§63.5).

`DualReturnWrite`, ruled as **D4**:

$$\boxed{\text{two scalar writes, one addressed decision context, one transaction}}$$

$$\text{write set}\bigl(\texttt{CounterfactualReturnWrite}\bigr) = \{(x_t, a_t^+)\}, \qquad
\text{write set}\bigl(\texttt{DualReturnWrite}\bigr) = \{(x_t, a_t^F),\ (x_t, a_t^+)\}$$

$$\boxed{\{(x_t,a_t^+)\} \subset \{(x_t,a_t^F),(x_t,a_t^+)\} \text{ as entry write-sets,
yet the treatments are not equivalent and must not be collapsed}}$$

The entry write-sets *are* in a subset relation; revision 1's "neither is a subset" was
simply wrong. What does not follow from the inclusion is treatment equivalence: the two
arms ask different questions ("teach it what the alternative returns" versus "correct the
action it took **and** teach it what the alternative returns"), they are not
inter-convertible by any store-level operation, and a reader of B2 must not have to infer
which was run.

Further pins:

* both targets from the **pre-update** state — the factual entry may not be read as part
  of computing the counterfactual one. They come from two different traces, so the
  prohibition is not what makes it well-defined; it is what forbids "write $a^F$, then let
  the second target observe it";
* at most two entries in $Q_D^L$ and exactly **one** receipt;
* `n_scalar` ∈ {0, 1, 2} for this arm at one address — $0$ when both writes are no-ops,
  which is `EVALUABLE_NOOP`, not a failure.

$$\boxed{N_{\text{independent treatments}}(D_Q) = 4}$$ (reference excluded; the $L_3$ arm is
a genuinely new operation on this architecture — §63.8)

### 5.1 The absence, enforced

"No $L_1$ arm on $D_Q$" is a fact about a registry, and a registry cannot prove a
negative. What *can* be enforced is the reason it is absent (§1.3), plus the two ways it
would come back:

* a `FactualReturnWrite` that consumes the $L_2$ field while declaring $L_0$ — caught by
  exact field delivery: `fields(D_Q, L0) = {G_t^F}` and $a^+$, $G_t^{CF}$ are not in it;
* a `CounterfactualReturnWrite` that degenerates to "write $a^+$ with a constant" when
  the counterfactual is missing — caught by §4.2: a missing counterfactual is a
  `PROTOCOL_ERROR`, and the `0.98`/`+1` constants are retired, not dormant.

### 5.2 The revisit variable — reported, never a population definition

Ruled as **D5**: a run whose updated context the future trajectory never revisits is
**kept and scored**, not dropped.

$$\boxed{\text{update eligible / applied} \;\not\Rightarrow\; \text{the future trajectory
revisits the updated address}}$$

The trigger is still positive-write-eligible; what is zero is its **future exposure**. The
two facts are recorded separately, and the exposure fact is an *exposed variable*, not a
denominator:

$$\boxed{\texttt{future\_revisited} \in \{0,1\}} \qquad\text{(or a future exposure count)}$$

Revision 1 called this "A75's $S_{r,0}$ population". **That was a category error** and is
withdrawn: $S_{r,\pm}$ and $S_{T,\pm}/S_{P,\pm}$ are A75's *regime-specific populations*,
defined by $T/P$ and by the trigger predicate. An applied update with zero revisit is a
sub-case **inside** those populations, distinguished by an exposure variable that A75 does
not define. Reporting it as $S_{r,0}$ would have silently redefined a frozen population
and moved a B2 exposure question into a B1 classification.

---

## 6. Runner generalisation and the ledger

### 6.1 One store slice, two architectures

The $D_Q$ row needs the same totality, locality and atomicity that $D_{patch}$ has, and
duplicating them is the defect route C removed for the fault grammar. So the runner is
parameterised by a **store-slice descriptor**, and both architectures go through the same
code:

| field | $D_{patch}$ | $D_Q$ |
|---|---|---|
| credited address | `DecisionAddress` | `DecisionAddress` |
| store | `DECISION` | `Q` |
| entry address | `DecisionAddress` | `QAddress` |
| value | `Action \| None` | `float` |
| healthy referent | no override | $Q_D^\ast$, via the injected view |
| scalar-valued | no | **yes** |
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

> **Implementation note (non-normative, must not enter the amendment).** In the code as
> it stands today the runner hard-codes the decision patch store in four places
> (`_store_view`, the `Edit(DECISION, …)` check, `DecisionWriteReceipt`,
> `scalar_metrics_applicable`). That is a description of the current implementation, not
> part of the contract; §9's step 2 is the commit that removes it.

### 6.2 `scalar_metrics_applicable`

$$\boxed{\text{scalar\_metrics\_applicable} = \text{the slice's store is scalar-valued}}$$

A property of the **slice**, not of the outcome: it is `True` for every $D_Q$ run,
including a run where nothing changed, and `False` for every $D_{patch}$ run. The flag
answers "are these three numbers defined here?", and "did anything change?" is what the
receipts and the fingerprint answer. Tying the flag to the outcome would make
`n_scalar = 0` mean two different things depending on the arm — which is exactly how the
old `APPLIED = "wrote a scalar"` definition went wrong.

### 6.3 Scalar accounting

**Ruled as blocker 3: the delta is measured against the effective $Q$, not against an
arbitrary zero.** For each entry that changed, with $q$ the stored override value,
$\bot$ meaning *absent from the override table*, and $Q_D^\ast(e)$ the reference value at
that same entry:

$$\boxed{\Delta(e)=\begin{cases}
\lvert q_{\text{post}} - q_{\text{pre}}\rvert, & \text{override} \to \text{override}\\
\lvert q_{\text{post}} - Q_D^\ast(e)\rvert, & \bot \to \text{override}\\
\lvert Q_D^\ast(e) - q_{\text{pre}}\rvert, & \text{override} \to \bot
\end{cases}}$$

$$\boxed{N_{\text{scalar}} = \#\{e : \text{the entry changed}\},\quad
\Sigma = \sum_e \Delta(e),\quad \text{Max} = \max_e \Delta(e)}$$

In a sparse store "absent" is not $0$, it is $Q_D^\ast(e)$; measuring a created entry as
$\lvert q_{\text{post}}\rvert$ (revision 1) or a deleted one as $\lvert q_{\text{pre}}\rvert$
would have made a nearly-reference-valued write look like a huge edit, and would have made
the numbers depend on where the reward scale happens to place zero. Revision 1 then had to
compensate with a disclaimer — "$\Sigma = 0 \not\Rightarrow$ nothing changed". **That
disclaimer is no longer needed and is withdrawn.**

$$\boxed{N_{\text{scalar}} = 0 \iff \Sigma = 0 \iff fp_{\text{pre}} = fp_{\text{post}}
\qquad\text{within the scalar slice}}$$

This strengthened form **depends on canonicalisation**, and that is a feature rather than a
caveat: after canonicalisation every genuinely changed entry has $q_{\text{post}} \neq
Q_D^\ast(e)$ (created), $q_{\text{pre}} \neq Q_D^\ast(e)$ (deleted) or
$q_{\text{pre}} \neq q_{\text{post}}$ (updated), so $\Delta(e) > 0$ in all three cases. If
someone ever bypasses canonicalisation, a "changed" entry with $\Delta = 0$ appears, the
equivalence breaks, and §7 G14 fires. The ledger thereby becomes a canary for the
canonicalisation rule, which is the same role the fingerprint plays for the transaction.

Enforced in full — and every line assumes the arm writes **one** store, the slice, which
is the whole B1 design; an arm writing two stores would need them restated per store:

| invariant | why |
|---|---|
| `N_scalar == 0 ⟺ Σ == 0 ⟺ fp_pre == fp_post` | the scalar accounting, the count and the digest are three independent witnesses of "changed" |
| `N_scalar == 0 ⟺ n_changed_addresses == 0` | no address changed if and only if no entry did |
| `N_scalar ≥ n_changed_addresses` | every changed address changed at least one entry |
| `Max ≤ Σ`, both `≥ 0`, `Max > 0 ⟺ Σ > 0` | arithmetic coherence of the reported triple |
| `N_scalar ≤ 2` for `DualReturnWrite` at one context | §5's "two scalar writes" |
| `N_scalar ≤ \lvert A_z(m,s)\rvert` for `LocalOracleRestore` at one context | the row has that many entries (G8) |

$\Delta$ needs the reference view (§2.2) — a second reason the view is injected rather
than looked up: without it the deleted and created cases are not defined at all.

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
| G3 | scalar-write law at $L_1$ rejected | `PositiveAlternative` returns as a "scalar" law | drop the architecture/tier compatibility check |
| G4 | $L_0$ needs no $L_2$ field | the $L_0$ arm fails when the counterfactual builder breaks | build all fields unconditionally |
| G5 | prefix equality | a replay from the wrong config silently produces a CF number | perturb one replay field; require `PROTOCOL_ERROR` |
| G6 | healthy-state equivalence | the $D_Q$ read path *changes* the policy when the store is empty | break the argmax tie-break; require a row-level difference |
| G7 | created/deleted accounting | $\Delta$ measured against $0$ instead of $Q_D^\ast$, so a near-reference write reads as a huge edit | restore the revision-1 $\lvert\cdot\rvert$-against-absent rule; require $\Sigma = \epsilon$ for a created override $Q_D^\ast+\epsilon$, not $\lvert q_{\text{post}}\rvert$ |
| G8 | row locality for $L_3$ | the restore writes a *different* context's row | widen the write set by one context |
| G9 | dual atomicity | the factual half commits, the counterfactual half throws | split the transaction in two |
| G10 | absence of the $L_1$ cell | an $L_1$ $D_Q$ law is registered and scored | register a stub $L_1$ scalar law |
| G11 | no oracle leakage into $L_0$ | `FactualReturnWrite` targets $Q_D^\ast$ instead of $G_t^F$ | substitute the reference value |
| G12 | $D_{patch}$ unchanged | the store-slice refactor changes a patch arm's plan, status or ledger bytes | re-run the $D_{patch}$ suite against the generalised runner |
| G13 | no co-residence | both stores populated, silently resolved by a priority rule | replace the fail-stop with "patch wins" |
| G14 | canonicalisation canary | the scalar-count/$\Sigma$/fingerprint equivalence assumed rather than enforced | disable Q identity-assignment canonicalisation; require the triple to disagree |
| G15 | the CF config carries the pre-update decision view | a replay that silently reverts to the reference provider after $t$ | replay with the reference decision provider on a scene whose pre-update override is visited before $t$ |
| G16 | reference-row totality | a partial reference row leaks a `KeyError` out of the read path | delete one key from one reference row; require `PROTOCOL_ERROR`, not `KeyError` |

G12 is the regression that matters most and is the reason §6.1 is a refactor of *one*
implementation rather than a second runner: the whole $D_{patch}$ slice suite — the alias
identity, the per-receipt invariants, the plan/locality gates, the envelope gates and the
mutation self-check — plus the observable-preimage digest
`6034b9c75056424a3dec42c6363c370dbb980d289e8c16a653558bd9eadb4cc6` must all reproduce
**byte for byte** after it, and the ledger's `canonical()` bytes for every $D_{patch}$ arm
must be unchanged.

G15's honest limit is stated where it belongs (§4.2): it fires only on a scene whose
pre-update decision defect is visited before $t$. The structural rule — the config carries
`DecisionReadView_pre` — is verified by construction, and G15 is the independent witness,
not the proof.

Note for whoever wires the mutations: the anchors in
`scripts/b1_interface_gate_selfcheck.py` are textual, and one of them straddles `_run`'s
pre-state lines. A refactor of `_run` must update those anchors, and the self-check's
`matched == 1` rule makes a stale anchor a visible `MUTATION_NOT_APPLIED` rather than a
silent pass. **The refactor commit must leave all eight existing mutations still killable**
— an anchor that stops matching is a gate that stopped existing, not a gate that passed.

---

## 8. The rulings (D1–D8)

Recorded with the two that **overturn the draft's own recommendation** marked.

| # | ruling | frozen semantics |
|---|---|---|
| **D1** | **accepted** | $Q_D^\ast$ is the $D_Q$ read path's runtime healthy referent, but as an **injected frozen read-only reference view**. `learner/store.py` and the runner must not call `solve_reference()`; ordinary laws must not be able to reach $Q_D^\ast$ through the delivery contract. |
| **D2** | **accepted, overturning my recommendation** | **No patch-shadows-Q priority.** $D_{patch}$ and $D_Q$ are different architecture treatments, and a legal experiment never populates both, so simultaneous non-emptiness is **`PROTOCOL_ERROR`** — contamination is surfaced, not hidden behind an arbitrary ordering. Composing them is a future amendment. |
| **D3** | **accepted** | $L_3$ on $D_Q$ is **row-wise deletion** of the credited context's Q overrides, returning that row to $Q_D^\ast$. Reference-valued entries are never stored explicitly. |
| **D4** | **accepted** | `DualReturnWrite` = $(x_t,a_t^F)$ and $(x_t,a_t^+)$, two scalar entries, **one** `DecisionAddress` receipt, **one** transaction. |
| **D5** | **accepted in part, overturning my classification** | Keep and score the run; zero revisit is **not** A75's $S_{r,0}$. The relation is $\text{applied} \not\Rightarrow \text{revisited}$; exposure is recorded as an exposed variable (`future_revisited` $\in\{0,1\}$ or a count) and must not alter A75's $S_{T,\pm}/S_{P,\pm}$ definitions or remove anything from the denominator. |
| **D6** | **accepted, split further** | Freeze the amendment → runner/store-slice refactor **alone** with only the $D_{patch}$ regression → Q store/read substrate → $L_0$ `FactualReturnWrite` → $L_2$ CF builder + laws. No commit mixes the refactor with new target semantics. |
| **D7** | **accepted** | Opaque `Enum`: no ordering, no arithmetic, no truthiness inference. |
| **D8** | **accepted in conclusion, reason corrected** | The empty $L_1$ cell is not instantiated and not scored — because $D_Q\times L_1$ has **no substantive compatible treatment**, so there is no comparison cell needing a reference. The type rule targets **scalar *write* laws at $L_1$**; `NoWrite` itself is not declared type-illegal. |

---

## 9. Execution order (D6), and what the amendment may contain

$$\boxed{\text{amendment freeze} \rightarrow \text{generic slice refactor only} \rightarrow
\text{Q store / read substrate} \rightarrow L_0\ \texttt{FactualReturnWrite} \rightarrow
L_2\ \text{CF builder} + \text{laws}}$$

The amendment freezes the **normative** content of §1–§6:

$$\boxed{\text{Tier/field contract} + D_Q\ \text{store/read semantics} + G^F + G^{CF} +
D_Q\ \text{law matrix} + \text{scalar ledger}}$$

It does **not** include implementation descriptions — "the runner currently hard-codes the
patch store in four places" (§6.1) is a note about the current code, and belongs in the
commit message of step 2, not in a frozen contract.

Step 2's acceptance conditions are exact and are the whole point of splitting it out:

1. `D_patch` ledger `canonical()` bytes unchanged for every arm;
2. the observable-preimage digest reproduced exactly;
3. the eight existing interface mutations still all killable after their anchors are
   updated;
4. no new semantics in the commit — if a $D_{patch}$ number moves, the commit is wrong.

---

## 10. Not in this draft

Stated so the boundary is not read as an oversight:

* **no B2 endpoints.** `HarmRate`, `ΔG`, `RecoveryFraction`, the `NOT_EVALUABLE`
  denominator rule and the `future_revisited` exposure variable's use are B2's; §63.8
  already defers "which oracle is B2's denominator";
* **no regime I numbers.** Intermittent-regime statistics stay deferred until $T/P$
  semantics settle;
* **no selection problem.** How an ordinary learner *finds* $a^+$ is V0.4R's;
* **no claim about $\Gamma$.** The standing boundary is untouched: $\Gamma^+$ and the
  truth come from the same $\pi_{\text{credit}}$, so every census measures over-credit
  under a **fixed** ontology and does not validate it;
* **no $X$ or $P$ field rows.** They are A76 §63.7's, and this revision stops
  generalising over them (§1.2);
* **no $08$-V03R rebase.** That document still carries the $do(z{=}z')$ error and remains
  deliberately unsynchronised; this draft does not touch it;
* **no amendment is edited in place.** A76 §63 stays as written; everything here that
  changes it is proposed as a new amendment, to be numbered if and when you approve it.
