# 18 — V0.3R B1: the $D_Q$ row — implementation draft (revision 3)

$$\boxed{\text{DRAFT — for review. Not frozen, not authorised, no code written.}}$$

This is the implementation draft A76 §63.13 and the $D_{patch}$ slice left owed. It pins
the interfaces and invariants of the **$D_Q$** row of the compatibility matrix (A76
§63.9), together with the one thing that has to change before $D_Q$ can exist at all: the
boolean `requires_alternative` is not an information contract, and $D_Q$ needs one.

**Revision history.**

* **revision 1 → 2** incorporated the **D1–D8** rulings and six corrections. Two rulings
  overturned the draft's own recommendation (**D2** co-residence fail-stop, **D5** no
  $S_{r,0}$ classification), and four blockers were fixed (architecture-keyed `fields`,
  `DecisionReadView_pre` in the CF config, $Q_D^\ast$-referenced $\Delta$, the withdrawn
  $S_{r,0}$ claim).
* **revision 2 → 3**, this revision, fixes the **five interface points IF1–IF5** that
  would have left the code phase without a unique implementation. Three of them changed
  what the contract *says*, not merely how it is phrased:

| # | interface point | revision 2 | revision 3 |
|---|---|---|---|
| **IF1** | $D_Q$ delivery | $L_0=\{G_t^F\}$ — **unimplementable**: `FactualReturnWrite` must write $Q_D^L(x_t,a_t^F)$ and neither the address nor the envelope carries $a_t^F$ | $L_0=\{a_t^F,G_t^F\}$, $L_2=\{a_t^F,G_t^F,a_t^+,G_t^{CF}\}$, with $F_t$ built **only from learner-visible rows** (§1.2, §3.1) |
| **IF2** | $L_3$ delivery | $\{Q_D^\ast(x_t,\cdot)\}$ — contradicted D1 and D3 in the same document | $\boxed{\varnothing}$; the reference never enters law delivery (§1.2, §5.3) |
| **IF3** | locality model | "credited = plan = edit" — a patch-era rule; $D_Q$'s edit key is finer than its receipt key | owner-based: $owner_\alpha(e.\text{address})=\text{plan.address}\in\text{credited}$ (§6.1) |
| **IF4** | Q store domain | typed + finite value only | $\operatorname{dom}(Q_D^L)\subseteq\operatorname{dom}(\texttt{QReferenceView})$, fail-stop at the transaction boundary (§2.5) |
| **IF5** | same-tier references | "instantiated" with no object expressing it; one fixed-$L_0$ `NoWrite` would have posed as the $L_2$/$L_3$ reference | `NoWriteRef(ℓ)` instances sharing one no-op plan (§1.4) |

**Scope of G12 narrowed** (as instructed): "the $D_{patch}$ ledger's `canonical()` bytes
are unchanged" is an acceptance condition of **step 2 alone**, the pure generic refactor.
Step 3 adds the Q component to the global learner fingerprint, and whether an empty
component changes the absolute encoding is a **schema-version** question with its own
treatment. G12 must not be read as "every later commit keeps the old hash bytes".

**B2's schema is not fixed here.** The zero-revisit boundary is frozen (§5.2); the field
name `future_revisited` is *illustrative only*.

**This draft carries no amendment number.** Revision 1 pre-emptively named one here, and
`spec_audit.py` reported it as an amendment reference with no amendment heading —
correctly. A number named before the amendment exists is a phantom in the reference graph:
the citation closes and the amendment is un-logged. The number is assigned at approval, in
`12-AMENDMENTS.md`, and not here.

*Auditor note.* That first catch came from the **bold** reference source. `spec_audit.py`
extracts references from bold mentions, heading-level declarations, `logged as`,
`retired/withdrawn/superseded by`, ranges and the summary table — a **plain or backticked**
`A<n>` in prose is not one of its sources and is invisible to it. A draft that must not
cite an unassigned amendment therefore has to not *contain* the number at all, which is why
this revision names none. Widening the auditor is a change to the evidence tool and is
raised for a ruling rather than made here.

---

## 0. What the boolean cannot express

The $D_{patch}$ slice routes information with one flag
(`_Law.requires_alternative`). It works because $D_{patch}$ has exactly two information
states:

$$\text{no envelope} \quad\text{or}\quad \{a^+\}$$

$D_Q$ breaks that in **two directions at once**:

$$\boxed{\text{1. } L_0 \text{ now NEEDS an envelope}}$$

`FactualReturnWrite` is $L_0$ and its target is factual. Under the old flag, "requires no
alternative" means "receives nothing", so the $L_0$ arm would be handed no target at all
and could not be implemented.

$$\boxed{\text{2. } L_1 \text{ must be expressible as ABSENT}}$$

There is no $D_Q\times L_1$ arm (A76 §63.5). Under the old flag, "does not require an
alternative" *is* the $L_1$-excluded case, so the absence and the $L_0$ case are the
**same value**. A registry built on the boolean cannot state "this cell is empty"; it can
only state "this arm needs nothing", and the two would be confused the first time someone
adds a law.

A third, quieter failure: the boolean is read by the runner to decide *what to build*.
Once the envelope has more than one field, "the law did not read the higher-tier field" is
again weaker than "the runner never built it" — the A59 shape, one level down.

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
(`type(tier) is Tier`), and `Tier.L0_FACTUAL` is **not** the default. `bool` subclassing is
how the old flag failed; an `int`-valued enum would reproduce the same failure one step
later (`0`, `True` and `1` would all be accepted for `L0_FACTUAL`), so the enum is
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

**Keyed by architecture, not by a kind of store.** Revision 1 grouped $D_{patch}$, $X$ and
$P$ as "value-free" and gave all three $L_1 = \{a^+\}$. That abstraction is wrong twice
over:

* $P$'s assisted content is $z^{\text{proposal}}$, not $a^+$ — a different object with a
  different provenance ($\rho_P$ needs it as the *key*, which is exactly why $P_{id}\in
  L_1$ and not $L_0$, A76 §63.1);
* $X_{id}$ is $L_0$ and its content is the **factual** $a^{cmd}$, so $X$'s $L_0$ field set
  is not empty either.

"Value-free" describes a store's *value domain*. It does not describe what an
architecture's tiers carry. This revision freezes **two rows**:

| architecture | $L_0$ | $L_1$ | $L_2$ | $L_3$ |
|---|---|---|---|---|
| $D_{patch}$ | $\varnothing$ | $\{a^+\}$ | ill-typed | $\varnothing$ (restore = delete) |
| $D_Q$ | $\{a_t^F,\ G_t^F\}$ | **no substantive treatment** (§1.4) | $\{a_t^F,\ G_t^F,\ a_t^+,\ G_t^{CF}(a_t^+)\}$ | $\varnothing$ |

$$\boxed{F_t := (a_t^F,\ G_t^F)}$$

**IF1 — why $a_t^F$ must be in the field set.** Revision 2 gave
$\text{fields}(D_Q,L_0)=\{G_t^F\}$, which cannot be implemented:
`FactualReturnWrite`'s write is $Q_D^L(x_t,a_t^F)\leftarrow G_t^F$, and $a_t^F$ is in
neither the credited `DecisionAddress` (which carries $(s,z,m)$ only) nor the field set.
The same omission broke `DualReturnWrite`, whose factual half needs $a_t^F$ too. $F_t$ is
therefore the $L_0$ delivery, and it is a **pair**, because a return without its action
does not identify a store entry.

**IF2 — $L_3$ delivery is empty.** Revision 2 froze both
$\text{fields}(D_Q,L_3)=\{Q_D^\ast(x_t,\cdot)\}$ and "an ordinary law never receives
$Q_D^\ast$". Those cannot both hold, and D3 already settles which one gives: with
$L_3$ defined as *row-wise deletion*, the law needs no reference **values** at all. Its
$L_3$ designation is a statement about **semantic authorisation** ("restore the credited
context to the architecture's healthy referent"), not about what it is handed — exactly as
$D_{patch}$'s $L_3$ is also empty-delivery while remaining $L_3$ rather than $L_0$ (§1.5).

$$\boxed{Q_D^\ast \text{ appears in exactly three places: the read path } \cup \text{
identity canonicalisation and scalar accounting } \cup \text{ evaluator-side target and
reference validation}}$$

and in **none** of them is it delivered to a law.

$X$ and $P$ keep their A76 §63.7 content, which this table does not restate, and get their
own rows when they are implemented. Note the cell that looks like a contradiction and is
not: $L_2$ delivers $a_t^+$ even though $D_Q\times L_1$ has no treatment. At $L_1$ the
action would have to be the target **value**, and a bare action is not a value on a scalar
store — that is why the cell is empty. At $L_2$ it is the **index** of the target:
$G_t^{CF}$ is meaningful only as $G_t^{CF}(a_t^+)$, and `DualReturnWrite` needs $a_t^+$ as
the entry's address. The pair is the content; the action alone is not a target.

Two things the exactness rule buys, both earlier lessons applied one level up:

* the envelope's **field set is exact**, exactly as the credited address set is exact.
  `keys(envelope) == fields(α, ℓ)`, so "an extra field was delivered" is a
  `PROTOCOL_ERROR` in the same sense that a non-credited address key now is; the
  $D_{patch}$ hardening is the special case $\text{fields}=\varnothing$;
* $L_0$ is again *never handed* $a_t^+$ — the property the old flag was protecting — while
  still receiving the factual field it legitimately needs.

### 1.3 Typed compatibility, made executable

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

### 1.4 `NoWriteRef(ℓ)` — the same-tier reference is an object (IF5)

A76: `NoWrite` "is available at every tier as the same-tier reference, simply ignoring the
extra information." Taken literally that would put a reference into the empty $L_1$ cell of
$D_Q$, i.e. a reference to nothing. Revision 1 justified omitting it with the phrase
*NoWrite does not read $a^+$* — **that was the A59 argument again**, and it would license
the same exemption for any arm that merely promises not to look. Revision 2 stated the
conclusion correctly but had no mechanism: a single law fixed at $L_0$ cannot *be* the
$L_2$ reference, and "the tier is recorded per arm" had no object to record it on.

$$\boxed{D_Q\times L_1 \text{ has no substantive compatible treatment } \Rightarrow
\text{ no comparison cell } \Rightarrow \text{ no same-tier reference}}$$

$$\boxed{\texttt{NoWriteRef}(\ell): \text{ one instance per cell that has a substantive
treatment}}$$

For $D_Q$ the three instances are:

| instance | delivered | plan |
|---|---|---|
| `NoWriteRef(Tier.L0_FACTUAL)` | $F_t$ | $\varnothing$ |
| `NoWriteRef(Tier.L2_COUNTERFACTUAL)` | $(F_t,\ a_t^+,\ G_t^{CF})$ | $\varnothing$ |
| `NoWriteRef(Tier.L3_ORACLE)` | $\varnothing$ | $\varnothing$ |

Delivery stays a property of the cell, not of the reference (§1.2), so `NoWriteRef` on
$D_{patch}$ is delivered $\varnothing$ at every tier it is instantiated for.

All instances share **the same no-op plan function object** — asserted, not merely
intended, like the `LocalOracleRestore` alias — and differ only in the tier they declare:

$$\boxed{\text{the tier is what makes them distinct; the behaviour is what makes them one}}$$

$$\boxed{N_{\text{independent treatments}}\text{ does not increase}}$$

The $D_{patch}$ slice's existing `NoWrite` **is** the $\ell=L_0$ instance on that
architecture, so the registry keeps four arms and three independent treatments and step 2
changes no $D_{patch}$ ledger byte. The `D_Q` slice instantiates its three references the
same way.

`NoWriteRef` is the **mechanism**, not a rename: the registered $D_{patch}$ arm keeps the
name `NoWrite`, because the arm table and `law_metadata()` are part of the surface G12
protects and `test_11` reads them by name.

**Where the tier is recorded.** The arm's tier is carried by the **arm/cell descriptor**
(which cell of the matrix this run is in), not by the per-address receipt and **not** by
`UpdateLedger.canonical()` — so step 2's byte-for-byte condition holds, and the
(arm, same-tier reference) pairing is auditable from the run record. Putting the tier
inside the canonical ledger is a schema change and would be its own commit with its own
scope, exactly like the fingerprint-component question (see the G12 scope note).

### 1.5 Migration of the $D_{patch}$ arms

| arm | was | becomes |
|---|---|---|
| `NoWrite` | `requires_alternative=False` | `NoWriteRef(Tier.L0_FACTUAL)` — the reference for the cell this architecture runs; registry unchanged |
| `DeleteFactualPatch` | `False` | `Tier.L0_FACTUAL` |
| `SetAlternative` | `True` | `Tier.L1_CORRECTIVE` |
| `LocalOracleRestore` | `False` (alias) | `Tier.L3_ORACLE` (alias of `DeleteFactualPatch` **on this architecture**) |

`LocalOracleRestore`'s declared tier changes from $L_0$ to $L_3$ and its **behaviour does
not**, because on a value-free store the healthy referent *is* "no override" and the $L_3$
restore therefore canonicalises to a deletion. That is not a coincidence to be papered
over: it is why §63.8 registers it as an alias on this architecture and as a new operation
on $D_Q$. The alias test keeps asserting `plan is DeleteFactualPatch.plan`; a new test
asserts the tier is $L_3$ while the plan is unchanged, so "the tier is metadata" cannot
silently become "the tier is ignored".

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
**one** addressed context", and it is why §6.1's locality rule is stated through an owner
map rather than an equality.

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

and it is **not** part of any envelope (§1.2, IF2). The read path, the accounting and the
evaluator-side validators consult the view; a law does not. The existing
`build_target_envelope(sol, …)` already takes the reference as a *parameter* rather than
reaching for it — that is the pattern, and D1 extends it from "the builder" to everything
that reads $Q_D^\ast$.

The store and the runner must also fail stop **before** any episode or read adapter is
constructed if both $P_D^L$ and $Q_D^L$ are non-empty (§2.3), not when some address
happens to be visited.

### 2.3 $P_D^L$ and $Q_D^L$ may not co-reside

**Ruled as D2, overturning revision 1's recommendation of a shadowing priority.**

$$\boxed{P_D^L \neq \varnothing \;\wedge\; Q_D^L \neq \varnothing
\;\Longrightarrow\; \texttt{PROTOCOL\_ERROR}}$$

$D_{patch}$ and $D_Q$ are different **architecture treatments**, and no legal experiment
populates both. Revision 1's "patch shadows Q" defined an arbitrary priority for a state
no legal run can reach, i.e. it would have *hidden* contamination instead of exposing it.
A priority rule is only justified when both channels are live; here "this cannot happen"
means fail-stop, and if a future experiment wants the combination, that is a new amendment
with the composition semantics written out.

The check is a **construction-time precondition** of the slice, evaluated before the
episode is rolled out or the decision adapter is built — an entry that can never be read is
worse when it is discovered late (§2.5).

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
infinities are rejected at the transaction boundary (§2.5).

The component is added in **step 3**, not step 2. Adding an *empty* fourth component to the
canon changes the digest string for patch runs and **no invariant** — the ledger only ever
compares $fp_{\text{pre}}$ with $fp_{\text{post}}$ inside one run, and no committed artifact
records an absolute learner fingerprint (checked: `experiments/**/*.json` has no
`fingerprint_pre`/`fingerprint_post`) — but it *is* an encoding change, so it belongs to the
step that needs it, with G12's scope note as the boundary.

### 2.5 Domain closure (IF4)

Typing the address and requiring a finite value is not enough. An entry that is well-typed
but outside the reference domain is the Q version of the `P_override[99] = 1` defect that
the PROCESS store already had to be closed against:

$$Q_D^L(x, a_{\text{inadmissible}}) = 0.7
\quad\Longrightarrow\quad fp \text{ changes},\ \texttt{healthy} = \text{False},
\ \text{and the decision read path never reads it}$$

a persistent defect that is invisible in behaviour and therefore invisible to every
downstream metric. So:

$$\boxed{\operatorname{dom}(Q_D^L) \;\subseteq\; \operatorname{dom}(\texttt{QReferenceView}),
\qquad \text{all values finite}}$$

$$\boxed{\operatorname{dom}(\texttt{QReferenceView}) = \{(x,a) : x \text{ a legal
decision context},\ a \in A_z(m,s)\}}$$

Violations fail stop **at the transaction boundary**, alongside the existing typed-address
and duplicate-key checks. Because the reference domain depends on data rather than on a
closed enum like `is_option_id`, the slice passes the transaction a **domain oracle** (the
frozen view) rather than the substrate reaching for one — which is D1 applied to the write
path.

**The 13,824-row census is this contract's evidence, not a `KeyError` gate.** Measured:

| quantity | value |
|---|---|
| reference rows | 13,824 |
| rows with `set(row) != set(A_z(m,s))` | **0** (0 partial, 0 inadmissible extras) |
| row-size histogram | $\{1{:}2592,\ 2{:}1728,\ 3{:}6480,\ 4{:}1872,\ 5{:}1152\}$ |
| $\lvert A_z(m,s)\rvert$ histogram | identical, row for row |

so that, on this support,

$$\boxed{\operatorname{dom}(\texttt{QReferenceView}) = \{(x,a) : a \in A_z(m,s)\}}$$

which is what makes the domain contract a *checkable predicate* rather than a second,
informal notion of "legal entry". It is an exhaustive-support invariant of
`solve_reference` and must be re-measured if the solver or the grid changes; the boundary
fails stop on a non-total row rather than letting a `KeyError` escape from inside the read
path (§7 G16).

---

## 3. The factual target $G_t^F$

$$\boxed{G_t^F = \sum_{j=t}^{T_F-1} r_j^F}$$

the sum of `StepResult.reward` from action-step $t$ to the end of **that factual episode**
— not from $t=0$, and not the episode return. Mode A, undiscounted, frozen step cost
included (A76 §63.2).

### 3.1 $F_t$ is built from the learner-visible rows, not from the trace

$$\boxed{F_t = (a_t^F,\ G_t^F), \qquad
a_t^F = \text{rows}[t].a^{cmd}, \qquad
G_t^F = \sum_{j=t}^{T_F-1} \text{rows}[j].reward}$$

$$\boxed{F_t = f\bigl(I^{\text{factual}}_{0:T}\bigr) \quad\text{— not}\quad
f(\text{the evaluator's latent trace})}$$

The two are numerically identical on any consistent run, and that is exactly why the
distinction has to be frozen rather than left to the implementer: **the same value reached
by a different construction path is a different information contract.** The builder's input
type is therefore the row tuple from `env/observation.py` — `ROW_SCHEMA` already carries
`a_cmd` and `reward`, so nothing else is needed — and the $L_0$ builder is *structurally
incapable* of reading the mask, the tape, the reference or the world identity, because it is
never handed them (§7 G17). This is the A59/A62 discipline applied to the one field set that
is supposed to be learner-feasible: "it happens to compute the same number" is not the
claim; "it computes it from learner-visible evidence" is.

Two consistency points that keep $F_t$ from drifting into a second notion of the factual
action:

* the credited address is **already** resolved through the same observation model
  (`resolve_decision_address` → `walk_transition`), so the whole $L_0$ path — address and
  $F_t$ — is built from learner-visible rows; the trace enters only as the input to the
  row-producing model, never directly;
* $a_t^F$ is the same quantity the envelope validator calls `factual_command`, and the
  $L_0$ builder must read it from the same place. Two derivations of "the factual action"
  is exactly how an $a^+\neq a^F$ check ends up comparing across two definitions.

Three further pins:

* **Not $Q_D^\ast$.** `FactualReturnWrite` targets the *observed* suffix return. In a
  faulted episode $G_t^F \neq Q_D^\ast(x_t,a_t^F)$ in general, and substituting the
  reference would make the $L_0$ law an oracle in disguise — the defect class of the
  retired `+1`;
* **$L_0$ because the learner already has the rows.** $a^{cmd}$ and $r_j$ are in
  `ROW_SCHEMA`; $F_t$ is a *function of* learner-visible evidence. That is a stronger
  statement than "it is legal at $L_0$", and §3.1's construction rule is what makes it
  true rather than merely declared;
* **the scale is the reference's scale by construction.** `dp.py` stores an undiscounted
  return-to-go (`row[a] = res.reward + v[next]`), so $G_t^F$ is on the same scale as the
  entries it is written into. The best reachable return is $0.9800$, and the retired `+1`
  overstated it by exactly one `STEP_COST` — the audit that produced §63.2.

---

## 4. The counterfactual target $G_t^{CF}(a_t^+)$, and the prefix invariant

### 4.1 The replay

**Not a suffix simulator.** One full-episode replay from $t=0$, with the factual episode's
own configuration and **only** the decision node at $t$ changed:

$$\text{config}^{CF} = \bigl(\kappa,\ \tau,\ \text{mask},\ z^{\text{fault}},\ z_0,\
\text{controller},\ C_P^L,\ \texttt{DecisionReadView}_{pre},\ \text{mode A}\bigr)
\equiv \text{config}^{F}$$

$$\boxed{\texttt{DecisionReadView}_{pre} = \text{the complete pre-update decision read
path } (P_D^L/Q_D^L \to a^L), \text{ frozen}}$$

$$\boxed{\text{interventions}^{CF} = \bigl(\text{interventions}^{F} \setminus
\{do(d_t=\cdot)\}\bigr) \cup \{do(d_t = a_t^+)\}}$$

then

$$\boxed{G_t^{CF}(a_t^+) = \sum_{j=t}^{T_{CF}-1} r_j^{CF}}$$

**Why the decision read path is in the config.** Revision 1 listed only the evaluator
channels $C_P^L$ and $C_X^L$ and omitted the *learner's* decision read path. But the replay
runs a **full episode**, so it visits steps after $t$ — and at any of those steps the
decision channel consults the learner's persistent state. A replay that omitted the
pre-update decision view would silently fall back to the reference provider whenever it hit
an existing learner decision defect, which violates A76's frozen

$$\text{all targets are computed from the same pre-update learner state},$$

and would produce a $G_t^{CF}$ measured against a *different* learner than the one whose
factual return $G_t^F$ was measured. The counterfactual must therefore differ from the
factual episode in **exactly one** thing: the value at the decision node $t$.

This presumes the **factual** trace was itself produced under the same pre-update learner
state. That is A76 §63.10's third invariant ("all targets from the pre-update snapshot") and
it makes the identity $\text{config}^{F} \equiv \text{config}^{CF}$ an invariant of the
*experiment* rather than of the replay: the trigger episode is rolled out with the learner
state frozen, not updated online.

The rest of the config:

* **the kernel already supports the $do$.** `Intervention.decision(t, action)` exists and
  `rollout`'s command priority is frozen as `do(d_t) > Z_D > command_provider`, so this
  needs **no kernel extension**. Checked before committing to the design, not after;
* **replacement, not addition, when the factual episode already intervened at $t$.**
  `InterventionSet` de-duplicates on `("decision", t)` and two decisions at one $t$ are
  `MALFORMED`, so "add" would be ill-defined precisely when it is needed. Replacing is
  well-defined and is what "the counterfactual to *this* episode" means;
* **$a_t^+$ needs no re-check for admissibility here** — it is already verified inside
  $A_z(m,s)$ by the envelope validator, which is what stops the replay raising
  `MalformedIntervention` halfway through;
* **the replay is evaluator-side and stays there.** It reads the mask, the tape and the
  reference; it is the definition of the $L_2$ field and never enters a law.

$G_t^{CF}$ is a function of a **different trace**, so unlike $F_t$ it is *not* reconstructible
from the factual rows — that is precisely what makes the cell $L_2$ rather than $L_0$, and
the reason the two $L_2$ arms must not be confused with an $L_0$ arm that "also happens" to
know the counterfactual.

### 4.2 The invariant

$$\boxed{\text{rows}\bigl(\text{trace}^{CF}\bigr)[0:t] = \text{rows}\bigl(\text{trace}^{F}\bigr)[0:t]
\quad\text{else } \texttt{PROTOCOL\_ERROR}}$$

compared over the **row schema** $(x,y,t,\kappa,\phi,z,m,a^{cmd},a^{realized},reward)$ —
the same `ROW_SCHEMA` the locator uses, so "the prefix is the same" means the same thing in
both places. Comparing rows rather than a summary is deliberate: the row already carries
$z$ and $m$, so this single comparison **subsumes** the option-in-force equality and the
context equality, and no second, weaker check is added beside it.

Three honest notes:

* **the invariant is not sufficient for the decision-view requirement, and is not offered
  as such.** A replay that dropped `DecisionReadView_pre` would diverge in the prefix *only
  if* the pre-update decision defect is actually visited before $t$. That is constructible
  (§7 G15 uses exactly such a scene), but it is a property of the scene, not of the rule.
  The rule that closes it is structural — the config carries the view — and the invariant
  is the second, independent witness that catches the cases it can;
* the equality is *expected by determinism* (fixed `SemanticTape`, no earlier intervention).
  A check that cannot fail is not evidence — its value here is that it converts a **silent**
  corruption (a replay built from the wrong config, a provider with hidden state) into a
  fail-stop. It is therefore tested **by mutation**, not by observing that it passes;
* a violation is `PROTOCOL_ERROR` (§63.3), never a $0$ target and never a
  `NO_VALID_ALTERNATIVE`. A zero would be indistinguishable from a legitimate
  counterfactual return of zero and would enter B2 as an arm that "learned nothing".

---

## 5. The $D_Q$ arms, and the absence that must stay absent

| tier | arm | write | plan entries $k$ |
|---|---|---|---|
| reference | `NoWriteRef(ℓ)` | — | 0 |
| $L_0$ | `FactualReturnWrite` | $Q_D^L(x_t,a_t^F) \leftarrow G_t^F$ | 1 |
| $L_1$ | **— none —** | — | — |
| $L_2$ | `CounterfactualReturnWrite` | $Q_D^L(x_t,a_t^+) \leftarrow G_t^{CF}(a_t^+)$ | 1 |
| $L_2$ | `DualReturnWrite` | both of the above, one transaction | 2 |
| $L_3$ | `LocalOracleRestore` | restore the credited row (§5.3) | $0 \le k \le \lvert A_z(m,s)\rvert$ |

$\alpha = 1$ (full backup) for both $L_0$/$L_2$ arms; the $L_3$ restore is not a backup at
all and has no $\alpha$. $\alpha < 1$ is a secondary sensitivity study and may never pick a
winner or rescue a primary result (§63.5).

`DualReturnWrite`, ruled as **D4**:

$$\boxed{\text{two scalar writes, one addressed decision context, one transaction}}$$

$$\text{write set}\bigl(\texttt{CounterfactualReturnWrite}\bigr) = \{(x_t, a_t^+)\}, \qquad
\text{write set}\bigl(\texttt{DualReturnWrite}\bigr) = \{(x_t, a_t^F),\ (x_t, a_t^+)\}$$

$$\boxed{\{(x_t,a_t^+)\} \subset \{(x_t,a_t^F),(x_t,a_t^+)\} \text{ as entry write-sets,
yet the treatments are not equivalent and must not be collapsed}}$$

The entry write-sets *are* in a subset relation; revision 1's "neither is a subset" was
simply wrong. What does not follow from the inclusion is treatment equivalence: the two arms
ask different questions ("teach it what the alternative returns" versus "correct the action
it took **and** teach it what the alternative returns"), they are not inter-convertible by
any store-level operation, and a reader of B2 must not have to infer which was run.

Further pins:

* both targets from the **pre-update** state — the factual entry may not be read as part of
  computing the counterfactual one. They come from two different traces, so the prohibition
  is not what makes it well-defined; it is what forbids "write $a_t^F$, then let the second
  target observe it";
* at most two entries in $Q_D^L$ and exactly **one** receipt;
* `n_scalar` ∈ {0, 1, 2} for this arm at one address — $0$ when both writes are no-ops,
  which is `EVALUABLE_NOOP`, not a failure.

$$\boxed{N_{\text{independent treatments}}(D_Q) = 4}$$ (references excluded; the $L_3$ arm is
a genuinely new operation on this architecture — §63.8)

### 5.1 The absence, enforced

"No $L_1$ arm on $D_Q$" is a fact about a registry, and a registry cannot prove a negative.
What *can* be enforced is the reason it is absent (§1.3), plus the two ways it would come
back:

* a `FactualReturnWrite` that consumes the $L_2$ field while declaring $L_0$ — caught by
  exact field delivery: `fields(D_Q, L0) = {a_t^F, G_t^F}` and $a_t^+$, $G_t^{CF}$ are not
  in it;
* a `CounterfactualReturnWrite` that degenerates to "write $a_t^+$ with a constant" when the
  counterfactual is missing — caught by §4.2: a missing counterfactual is a
  `PROTOCOL_ERROR`, and the `0.98`/`+1` constants are retired, not dormant.

### 5.2 The revisit variable — reported, never a population definition

Ruled as **D5**: a run whose updated context the future trajectory never revisits is **kept
and scored**, not dropped.

$$\boxed{\text{update eligible / applied} \;\not\Rightarrow\; \text{the future trajectory
revisits the updated address}}$$

The trigger is still positive-write-eligible; what is zero is its **future exposure**. This
document freezes only that boundary:

$$\boxed{\text{the population keeps the run; future exposure is B2's, and it belongs to no
A75 population definition}}$$

An exposure flag (for instance a `future_revisited`-style $\{0,1\}$ variable, or an exposure
count) is **recorded and reported, not defined here** — the name and schema are B2's, and
fixing them now would be this document doing B2's job.

Revision 1 called the zero-revisit case "A75's $S_{r,0}$ population". **That was a category
error and is withdrawn**: $S_{r,\pm}$ and $S_{T,\pm}/S_{P,\pm}$ are A75's *regime-specific
populations*, defined by $T/P$ and by the trigger predicate. An applied update with zero
revisit is a sub-case **inside** those populations, distinguished by an exposure variable
that A75 does not define. Reporting it as $S_{r,0}$ would have silently redefined a frozen
population and moved a B2 exposure question into a B1 classification.

### 5.3 `LocalOracleRestore` on $D_Q$: the structural operation and its lowering

$$\boxed{L_3:\ \text{delete every override in the credited context's row, returning it to }
Q_D^\ast}$$

and, per IF2, **no values and no reference are delivered** to do it. The law emits a
row-scoped **structural operation**, and the slice lowers it:

$$\text{law} \;\longrightarrow\; \texttt{RestoreRow}(x_t)
\;\xrightarrow[\text{slice lowering}]{\text{pre-state}}\;
\{Q_D^L(x_t,a) \leftarrow \bot\}_{a \in A_z(m,s),\ (x_t,a) \in Q_D^L}$$

Three things this fixes, none of which revision 2 had:

* **the law needs no store and no reference.** It cannot know which entries are overridden
  — that is store state — so it does not try. It names the row; the slice, which already
  holds the pre-state view for the receipts, resolves the row's actual overrides;
* **$k$ is well-defined.** After lowering, $k(x_t) = \#\{(x_t,a) : a \in A_z(m,s),\ (x_t,a)
  \in Q_D^L\}$, which is exactly $0 \le k \le \lvert A_z(m,s)\rvert$, and every lowered
  delete changes the store, so $\kappa = k$ for this arm. Since lowering enumerates only
  the *present* overrides, entries already at the healthy referent are never "deleted" —
  the canonical encoding makes that a no-op by construction rather than by a filter;
* **locality stays uniform.** `owner_Q(RestoreRow(x_t)) = x_t`, the same owner map the entry
  edits use (§6.1), so the row operation is checked by the same rule and needs no special
  case in the locality validator.

**Lowering does not consult $Q_D^\ast$**: deleting an override needs no reference value. The
reference is needed by the read path, by the $\Delta$ accounting, and by the evaluator-side
validators — the three places §1.2 froze — and by nothing else.

$$\boxed{\texttt{RestoreRow} \text{ returns the row to } Q_D^\ast \text{ by construction,
not by writing } Q_D^\ast}$$

which is the whole content of D3: explicit reference-valued entries would make the store
non-canonical, and §63.8's point is that this arm is new *in scope*, not in encoding.

---

## 6. Runner generalisation and the ledger

### 6.1 One store slice, two architectures (IF3: the locality model)

Revision 2 still said "credited = plan = edit", which is a patch-era identity: on $D_{patch}$
the credited address, the plan address and the edit address are all the same object, so the
equality held and looked like the rule. On $D_Q$ the edit key is the finer `QAddress` while
the receipt key stays `DecisionAddress`, and `DualReturnWrite` writes two of them. The
general rule is therefore stated through an **owner map**:

$$\boxed{owner_{\text{patch}}(\texttt{DecisionAddress}) = \texttt{DecisionAddress}}, \qquad
owner_Q\bigl(\texttt{QAddress}(s,z,m,a)\bigr) = \texttt{DecisionAddress}(s,z,m)$$

$$\boxed{\forall e \in \text{Plan}(x):\ owner_\alpha(e.\text{address}) = x}$$

$$\boxed{\{\text{Plan}.\text{address}\} = \text{the credited addresses, each exactly once}}$$

So each credited context has exactly **one address-plan**, of

$$\text{Plan}_Q(x) = (e_1, \dots, e_k), \qquad
k = \begin{cases} 0 & \texttt{NoWriteRef} \\ 1 & \texttt{FactualReturnWrite},\
\texttt{CounterfactualReturnWrite} \\ 2 & \texttt{DualReturnWrite} \\
0 \le k \le \lvert A_z(m,s)\rvert & \texttt{LocalOracleRestore (after lowering)} \end{cases}$$

$$\boxed{\text{one receipt per } \texttt{DecisionAddress}, \text{ whatever } k \text{ is}}$$

and the whole scene's entry edits,

$$\bigcup_{x}\text{Plan}_Q(x).\text{edits},$$

enter **exactly one** transaction, as before.

Two plan-shape rules that follow from not inventing semantics for states that cannot arise
(the D2 discipline at plan level):

* an address-plan contains **either** entry edits **or** one row operation, never both —
  every registered arm uses exactly one kind, and the combination's semantics are not
  defined here;
* two entry edits to the same `QAddress` inside one address-plan are a `PROTOCOL_ERROR`,
  for the same reason the transaction already forbids duplicate keys: last-write-wins would
  make the result depend on edit order.

Everything already frozen stays **identical and single-implementation**: address-plan
totality, owner locality, one transaction per scene, per-receipt
`APPLIED ⟺ store changed`, exact envelope, four-status taxonomy, `PROTOCOL_ERROR` fail-stop.

| field | $D_{patch}$ | $D_Q$ |
|---|---|---|
| credited address | `DecisionAddress` | `DecisionAddress` |
| store | `DECISION` | `Q` |
| entry address | `DecisionAddress` | `QAddress` |
| owner map | identity | $Q_{s,z,m,a} \mapsto (s,z,m)$ |
| value | `Action \| None` | `float` |
| domain oracle | closed enum (`is_option_id`-style) | injected `QReferenceView` (§2.5) |
| healthy referent | no override | $Q_D^\ast$, via the injected view |
| scalar-valued | no | **yes** |
| delta metric | none ($N_{\text{scalar}}=0$) | §6.3 |

> **Implementation note (non-normative, must not enter the amendment).** In the code as it
> stands today the runner hard-codes the decision patch store in four places
> (`_store_view`, the `Edit(DECISION, …)` check, `DecisionWriteReceipt`,
> `scalar_metrics_applicable`). That is a description of the current implementation, not
> part of the contract; §9's step 2 is the commit that removes it.

### 6.2 `scalar_metrics_applicable`

$$\boxed{\text{scalar\_metrics\_applicable} = \text{the slice's store is scalar-valued}}$$

A property of the **slice**, not of the outcome: it is `True` for every $D_Q$ run, including
a run where nothing changed, and `False` for every $D_{patch}$ run. The flag answers "are
these three numbers defined here?", and "did anything change?" is what the receipts and the
fingerprint answer. Tying the flag to the outcome would make `n_scalar = 0` mean two
different things depending on the arm — which is exactly how the old
`APPLIED = "wrote a scalar"` definition went wrong.

### 6.3 Scalar accounting

$$\boxed{\Delta(e)=\begin{cases}
\lvert q_{\text{post}} - q_{\text{pre}}\rvert, & \text{override} \to \text{override}\\
\lvert q_{\text{post}} - Q_D^\ast(e)\rvert, & \bot \to \text{override}\\
\lvert Q_D^\ast(e) - q_{\text{pre}}\rvert, & \text{override} \to \bot
\end{cases}}$$

$$\boxed{N_{\text{scalar}} = \#\{e : \text{the entry changed}\},\quad
\Sigma = \sum_e \Delta(e),\quad \text{Max} = \max_e \Delta(e)}$$

In a sparse store "absent" is not $0$, it is $Q_D^\ast(e)$; measuring a created entry as
$\lvert q_{\text{post}}\rvert$ or a deleted one as $\lvert q_{\text{pre}}\rvert$ would have
made a nearly-reference-valued write look like a huge edit, and would have made the numbers
depend on where the reward scale happens to place zero.

$$\boxed{N_{\text{scalar}} = 0 \iff \Sigma = 0 \iff fp_{\text{pre}} = fp_{\text{post}}
\qquad\text{within the scalar slice}}$$

This strengthened form **depends on canonicalisation**, and that is a feature rather than a
caveat: after canonicalisation every genuinely changed entry has
$q_{\text{post}} \neq Q_D^\ast(e)$ (created), $q_{\text{pre}} \neq Q_D^\ast(e)$ (deleted) or
$q_{\text{pre}} \neq q_{\text{post}}$ (updated), so $\Delta(e) > 0$ in all three cases. If
someone ever bypasses canonicalisation, a "changed" entry with $\Delta = 0$ appears, the
equivalence breaks, and §7 G14 fires. The ledger thereby becomes a canary for the
canonicalisation rule, which is the same role the fingerprint plays for the transaction.

Enforced in full — and every line assumes the arm writes **one** store, the slice, which is
the whole B1 design:

| invariant | why |
|---|---|
| `N_scalar == 0 ⟺ Σ == 0 ⟺ fp_pre == fp_post` | the accounting, the count and the digest are three independent witnesses of "changed" |
| `N_scalar == 0 ⟺ n_changed_addresses == 0` | no address changed if and only if no entry did |
| `N_scalar ≥ n_changed_addresses` | every changed address changed at least one entry |
| `Max ≤ Σ`, both `≥ 0`, `Max > 0 ⟺ Σ > 0` | arithmetic coherence of the reported triple |
| `N_scalar ≤ 2` for `DualReturnWrite` at one context | §5's "two scalar writes" |
| `N_scalar ≤ \lvert A_z(m,s)\rvert` for `LocalOracleRestore` at one context | the row has that many entries (§5.3, G8) |

$\Delta$ needs the reference view (§2.2) — a second reason the view is injected rather than
looked up: without it the deleted and created cases are not defined at all.

A75 §62.9's rule stands unchanged and unrepealed: these numbers are **accounting**, they may
not determine a status, and `APPLIED` remains "the store changed".

---

## 7. Gates

Every gate names the *plausible wrong implementation* it catches. Each is mutation-verified
in the style of `scripts/b1_interface_gate_selfcheck.py`: a textual revert of the fix must
turn the gate red, or the gate is reported as `NOT_A_GATE`.

| # | gate | the wrong implementation it catches | mutation that must turn it red |
|---|---|---|---|
| G1 | enum closure | a tier given as `0`/`True`/`"L0_factual"` silently accepted | accept `int` instead of `Tier` |
| G2 | exact field delivery | an $L_0$ law handed $a_t^+$; a law handed a field its cell excludes | build the union of all fields |
| G3 | scalar-write law at $L_1$ rejected | `PositiveAlternative` returns as a "scalar" law | drop the architecture/tier compatibility check |
| G4 | $L_0$ needs no $L_2$ field | the $L_0$ arm fails when the counterfactual builder breaks | build all fields unconditionally |
| G5 | prefix equality | a replay from the wrong config silently produces a CF number | perturb one replay field; require `PROTOCOL_ERROR` |
| G6 | healthy-state equivalence | the $D_Q$ read path *changes* the policy when the store is empty | break the argmax tie-break; require a row-level difference |
| G7 | created/deleted accounting | $\Delta$ measured against $0$ instead of $Q_D^\ast$, so a near-reference write reads as a huge edit | require $\Sigma = \epsilon$ for a created override $Q_D^\ast+\epsilon$, not $\lvert q_{\text{post}}\rvert$ |
| G8 | row locality for $L_3$ | the restore writes a *different* context's row | widen the lowered write set by one context |
| G9 | dual atomicity | the factual half commits, the counterfactual half throws | split the transaction in two |
| G10 | absence of the $L_1$ cell | an $L_1$ $D_Q$ law is registered and scored | register a stub $L_1$ scalar law |
| G11 | no oracle leakage into $L_0$ | `FactualReturnWrite` targets $Q_D^\ast$ instead of $G_t^F$ | substitute the reference value |
| G12 | $D_{patch}$ unchanged — **step 2 only** | the store-slice refactor changes a patch arm's plan, status or ledger bytes | re-run the $D_{patch}$ suite against the generalised runner |
| G13 | no co-residence | both stores populated, silently resolved by a priority rule | replace the construction-time fail-stop with "patch wins" |
| G14 | canonicalisation canary | the scalar-count/$\Sigma$/fingerprint equivalence assumed rather than enforced | disable Q identity-assignment canonicalisation; require the triple to disagree |
| G15 | the CF config carries the pre-update decision view | a replay that silently reverts to the reference provider after $t$ | replay with the reference decision provider on a scene whose pre-update override is visited before $t$ |
| G16 | reference-row totality | a partial reference row leaks a `KeyError` out of the read path | delete one key from one reference row; require `PROTOCOL_ERROR`, not `KeyError` |
| G17 | $F_t$'s construction path | the $L_0$ builder reads the trace, mask or reference — same numbers, wrong contract | give the $L_0$ builder a trace parameter; require the builder-signature gate to reject it |
| G18 | $L_3$ delivery is empty | $Q_D^\ast$ values delivered to `LocalOracleRestore` | set `fields(D_Q,L3) = {Q_D^*(x,·)}` |
| G19 | owner locality | an edit whose `owner_Q` is another credited context passes as "inside" | check `e.address == plan.address` instead of the owner map |
| G20 | Q domain closure | an inadmissible `QAddress` entry persists: fingerprint changes, behaviour never reads it | drop the domain oracle from the transaction; the `P_override[99]` case |
| G21 | reference instances are one law | `NoWriteRef(L2)` and `NoWriteRef(L3)` become separate treatments, or one fixed-$L_0$ `NoWrite` poses as both | give each instance its own plan function; require the count to move |

G12's scope, stated once and narrowly: it is an acceptance condition of **step 2**, the pure
generic refactor. The whole $D_{patch}$ slice suite — the alias identity, the per-receipt
invariants, the plan/locality gates, the envelope gates and the mutation self-check — plus
the observable-preimage digest
`6034b9c75056424a3dec42c6363c370dbb980d289e8c16a653558bd9eadb4cc6` must reproduce byte for
byte **after that commit**, and its ledger `canonical()` bytes for every $D_{patch}$ arm must
be unchanged. Step 3's addition of the Q fingerprint component is an encoding change that
G12 does **not** govern.

G15's honest limit is stated where it belongs (§4.2): it fires only on a scene whose
pre-update decision defect is visited before $t$. The structural rule — the config carries
`DecisionReadView_pre` — is verified by construction, and G15 is the independent witness,
not the proof.

Note for whoever wires the mutations: the anchors in
`scripts/b1_interface_gate_selfcheck.py` are textual, and one of them straddles `_run`'s
pre-state lines. A refactor of `_run` must update those anchors, and the self-check's
`matched == 1` rule makes a stale anchor a visible `MUTATION_NOT_APPLIED` rather than a
silent pass. **The refactor commit must leave all eight existing mutations still killable** —
an anchor that stops matching is a gate that stopped existing, not a gate that passed.

---

## 8. The rulings

### 8.1 D1–D8 (accepted)

| # | ruling | frozen semantics |
|---|---|---|
| **D1** | **accepted** | $Q_D^\ast$ is the $D_Q$ read path's runtime healthy referent, as an **injected frozen read-only reference view**. Neither `learner/store.py` nor the runner calls `solve_reference()`; the substrate receives a **domain oracle** at the transaction boundary (§2.5). No law reaches $Q_D^\ast$ through delivery (§1.2). |
| **D2** | **accepted, overturning revision 1** | **No patch-shadows-Q priority.** Simultaneous non-emptiness of $P_D^L$ and $Q_D^L$ is **`PROTOCOL_ERROR`**, checked at **construction time** before any episode or read adapter exists. |
| **D3** | **accepted** | $L_3$ on $D_Q$ is **row-wise deletion**, realised as a structural `RestoreRow` operation lowered by the slice (§5.3). Reference-valued entries are never stored explicitly. |
| **D4** | **accepted** | `DualReturnWrite` = $(x_t,a_t^F)$ and $(x_t,a_t^+)$, two scalar entries, **one** `DecisionAddress` receipt, **one** transaction. |
| **D5** | **accepted, overturning revision 1's classification** | Keep and score; zero revisit is **not** A75's $S_{r,0}$. The boundary is frozen; the exposure field is B2's and is not schematised here (§5.2). |
| **D6** | **accepted, split further** | Amendment freeze → generic slice refactor **alone** ($D_{patch}$ regression only) → Q store/read substrate → $L_0$ `FactualReturnWrite` → $L_2$ CF builder + laws. No commit mixes the refactor with new target semantics. |
| **D7** | **accepted** | Opaque `Enum`: no ordering, no arithmetic, no truthiness inference. |
| **D8** | **accepted, reason as corrected** | The empty $L_1$ cell is not instantiated and not scored — because $D_Q\times L_1$ has **no substantive compatible treatment**, so there is no comparison cell. The type rule targets scalar **write** laws at $L_1$; `NoWrite` is not declared type-illegal. |

### 8.2 IF1–IF5 (this revision)

| # | interface point | frozen semantics | section |
|---|---|---|---|
| **IF1** | $a_t^F$ delivery and $F_t$'s construction path | $L_0=\{a_t^F,G_t^F\}$, $L_2=\{a_t^F,G_t^F,a_t^+,G_t^{CF}\}$; $F_t=f(I^{\text{factual}}_{0:T})$ from the **learner-visible rows only** | §1.2, §3.1 |
| **IF2** | $L_3$ delivery | $\text{fields}(D_Q,L_3)=\varnothing$; $L_3$ is a semantic authorisation. $Q_D^\ast$ lives in the read path, canonicalisation/accounting and evaluator validation — nowhere in law delivery | §1.2, §5.3 |
| **IF3** | locality | owner-based: $owner_\alpha(e.\text{address})=\text{plan.address}$, one address-plan per credited context, $k$ entry edits, **one receipt** | §6.1 |
| **IF4** | Q domain closure | $\operatorname{dom}(Q_D^L)\subseteq\operatorname{dom}(\texttt{QReferenceView})$, finite values, fail-stop at the transaction boundary via an injected domain oracle; the 13,824-row census is the contract's evidence | §2.5 |
| **IF5** | same-tier references | `NoWriteRef(ℓ)` instances sharing one no-op plan; not independent treatments; the tier lives in the arm/cell descriptor, not in the canonical ledger | §1.4 |

---

## 9. Execution order (D6), and what the amendment may contain

$$\boxed{\text{amendment freeze} \rightarrow \text{generic slice refactor only} \rightarrow
\text{Q store / read substrate} \rightarrow L_0\ \texttt{FactualReturnWrite} \rightarrow
L_2\ \text{CF builder} + \text{laws}}$$

The amendment freezes the **normative** content of §1–§6:

$$\boxed{\text{Tier/field contract} + D_Q\ \text{store/read semantics} + G^F + G^{CF} +
D_Q\ \text{law matrix} + \text{scalar ledger}}$$

It does **not** include implementation descriptions — "the runner currently hard-codes the
patch store in four places" (§6.1) is a note about the current code and belongs in step 2's
commit message, not in a frozen contract.

Step 2's acceptance conditions are exact, and are the whole point of splitting it out:

1. `D_patch` ledger `canonical()` bytes unchanged for every arm;
2. the observable-preimage digest reproduced exactly;
3. the eight existing interface mutations still all killable after their anchors are updated;
4. no new semantics in the commit — no $Q_D^L$, no $F_t$, no $G^{CF}$, and if a $D_{patch}$
   number moves, the commit is wrong.

---

## 10. Not in this draft

Stated so the boundary is not read as an oversight:

* **no B2 endpoints.** `HarmRate`, `ΔG`, `RecoveryFraction`, the `NOT_EVALUABLE` denominator
  rule and the exposure variable's schema are B2's; §63.8 already defers "which oracle is
  B2's denominator";
* **no regime I numbers.** Intermittent-regime statistics stay deferred until $T/P$ semantics
  settle;
* **no selection problem.** How an ordinary learner *finds* $a_t^+$ is V0.4R's;
* **no claim about $\Gamma$.** The standing boundary is untouched: $\Gamma^+$ and the truth
  come from the same $\pi_{\text{credit}}$, so every census measures over-credit under a
  **fixed** ontology and does not validate it;
* **no $X$ or $P$ field rows.** They are A76 §63.7's, and this revision stops generalising
  over them (§1.2);
* **no ledger schema change.** The tier is recorded in the arm descriptor; putting it (or the
  Q fingerprint component) inside `canonical()` is a versioned schema change with its own
  commit and its own scope;
* **no $08$-V03R rebase.** That document still carries the $do(z{=}z')$ error and remains
  deliberately unsynchronised; this draft does not touch it;
* **no amendment is edited in place.** A76 §63 stays as written; everything here that changes
  it is proposed as a new amendment, to be numbered if and when you approve it.
