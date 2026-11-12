# 19 — V0.3R B1: $L_3$ `LocalOracleRestore` on $D_Q$ — implementation-order request (draft)

$$\boxed{\text{ACCEPTED WITH CORRECTIONS — SUPERSEDED BY A78 (\S66). Not normative.}}$$

This draft did its job as the pre-decision request: it carried no amendment number and
authorised nothing. The reviewer accepted it with seven corrections, and the authorisation now
lives in **A78 (§66)**, which is the normative text. The corrections it must be read with:

1. the acceptance is recorded as a **new amendment** (A78), because A77 requires further change
   to go through one; A77 itself is not rewritten;
2. **`NoWriteRef(L3)` is named**, so the $D_Q$ registry gains a reference as well as a treatment
   and $\lvert\text{treatments}\rvert(D_Q)=4$ matches A76 §63.8;
3. the **population question is answered and the draft's framing corrected**: §2.3's "32 versus
   278" confused *population* with *addresses that have a substantive target*. A76 §63.3 keeps a
   `NO_VALID_ALTERNATIVE` address in the population, so $\text{Population}_{L_2} =
   \text{Population}_{L_3} = $ every credited address, and restricting $L_3$ to the addresses
   with an $a^+$ would let its empty cell read $a^+$ availability;
4. "no reference" is scoped to the **lowering** and to *no new* $L_3$-specific entry point — the
   deleted-leg ledger still needs the existing `q_reference`;
5. the row operation stays in **B1**: `owner_Q` keeps taking a `QAddress` and the substrate does
   not learn an update law;
6. lowering is an explicit **pre-commit phase** and the ledger reads the **lowered concrete
   edits**, or a row-op-only plan would be misreported `EVALUABLE_NOOP`;
7. the $D_Q$ law is an **independent implementation**; the $D_{patch}$ alias is untouched and no
   law branches on architecture.

The two gate obligations the reviewer tightened are in A78 §66.8: **idempotence** read as "the
lowering uses this run's pre-state", and the empty-cell gate made hard with **poison evidence**.

---

## 1. What §65.9 already freezes — not re-opened here

Nothing below re-decides these; they are quoted so the request is exactly the size of the gap.

$$\boxed{L_3:\ \text{delete every override in the credited context's row, returning it to }
Q_D^\ast}$$

$$\texttt{RestoreRow}(x_t) \longrightarrow \{Q_D^L(x_t,a) \leftarrow \bot\}_{a \in A_z(m,s),\
(x_t,a) \in Q_D^L}$$

* $k$ is the number of overrides **actually present** in that row, and every lowered delete
  changes the store;
* $owner_Q(\texttt{RestoreRow}(x_t)) = x_t$, under §65.9's one locality rule;
* lowering needs **no reference**: the row returns to $Q_D^\ast$ by construction, never by
  writing $Q_D^\ast$ values;
* the delivery is empty: $\text{fields}(D_Q, L_3) = \varnothing$ (§65.2), already in
  `DQ_SLICE.cells` today;
* two plan-shape rules: an address-plan carries **either** entry edits **or one row
  operation, never both**; two entry edits to the same `QAddress` in one address-plan are a
  `PROTOCOL_ERROR`.

Consequences that follow from what is already frozen, stated so they are not mistaken for new
rules: a credited row with no overrides lowers to **no edits**, so the address-plan has no
edits and no declared status → `EVALUABLE_NOOP` by §65.10's existing rule; and $L_3$ needs
**no evaluator-side envelope at all**, unlike $L_0$ and $L_2$.

## 2. The gap

### 2.1 The implementation order

§65.12's sequence is

$$\text{generic slice refactor} \rightarrow Q\ \text{store/read substrate} \rightarrow L_0\ \texttt{FactualReturnWrite} \rightarrow L_2\ \text{CF builder} + \text{laws}$$

and it says every step is a separate commit in that order. $L_3$'s semantics are frozen in
§65.9 but the sequence does not include it, so implementing it now would be proceeding by
tacit consent on a frozen order.

### 2.2 New machinery §65.9's text implies but does not name

1. **A row-operation type.** Today `AddressPlan` carries entry `Edit`s only, and
   `_validate_plan` checks exactly that. $L_3$ needs a second operation kind so the law can
   emit the row-scoped operation and the slice can lower it against the pre-state. §65.9
   fixes the *lowering*; it does not fix the object, and the object is what the plan-shape
   rule attaches to.
2. **The plan-shape rule is not enforced yet** because no row operation exists. "Either entry
   edits or one row operation, never both" becomes checkable only once (1) exists, so $L_3$'s
   implementation must add that check rather than inherit it.
3. **`owner_Q` must accept the row operation**, per §65.9's locality equation. Today it takes
   an entry address only.
4. **A `run_dq_law` branch for $L_3$ that builds and validates nothing.** Both existing
   branches build an envelope and re-derive it. $L_3$'s cell is empty, so its branch must
   assert *that* — an empty cell must not silently acquire a builder — and must not become a
   third place where a reference is named.

### 2.3 What the ledger will report, from frozen rules

$k$ deletions, each changing the store ⇒ $N_{\text{scalar}} = k$, each $\Delta(e)$ on the
deleted leg $|Q_D^\ast(e) - q_{\text{pre}}(e)|$ (§65.10), hence
$N_{\text{scalar}} \le |A_z(m,s)|$. Entries whose value already equals $Q_D^\ast$ cannot be
present: §65.4's canonicalisation deletes them at write time, so "overrides present" and
"entries with $q \neq Q_D^\ast$" are the same set.

## 3. Proposed amendment text (small, drop-in)

> **Implementation order, extended.** §65.12's sequence gains exactly one step:
>
> $$\rightarrow L_3\ \texttt{LocalOracleRestore}$$
>
> under the same rule that governs the others: a separate commit, no mixing with a refactor or
> with $L_0$/$L_2$ semantics. It is a *separate authorisation*: it is not implied by $L_2$
> being closed, and the sequence's earlier steps do not acquire new scope from it.
>
> **$L_3$'s plan object.** The address-plan carries either entry edits or one
> `RestoreRow(x_t)` operation, never both; the slice lowers `RestoreRow` against the pre-state
> into the deletions §65.9 specifies; `owner_Q` is total on both kinds; and the enforcement of
> the either/or rule is part of this step, because it is unenforceable before the row
> operation exists.

No other text changes. In particular §65.2's cell table already carries $L_3 = \varnothing$, so
enabling the cell is `implemented_tiers` plus the law — the separation A77 introduced, used for
the second time.

## 4. Gate and mutation obligations I would accept

* **row scope**: the arm deletes exactly the overrides in the credited row — no other row, no
  other store, and the fingerprint change is confined to that row;
* **lowering against the pre-state**: $k$ = overrides present at pre-state; a row with none
  yields `EVALUABLE_NOOP` with an empty edit set, and is still one receipt;
* **ledger**: $N_{\text{scalar}} = k$, $\Sigma = \sum |Q_D^\ast(e) - q_{\text{pre}}(e)|$,
  $N_{\text{scalar}} \le |A_z(m,s)|$, and the §65.10 equivalences hold;
* **idempotence**: a second run on the same store is $k = 0$ / `EVALUABLE_NOOP` — a property
  $L_0$ and $L_2$ do not have, and the clearest evidence that the lowering reads the pre-state
  rather than a plan-time snapshot;
* **plan shape**: an address-plan with both kinds, or with two row operations, is a
  `PROTOCOL_ERROR`;
* **empty cell**: `run_dq_law` for $L_3$ builds nothing, and a law in that cell that is handed
  a non-empty field set is refused;
* **no reference named**: the $L_3$ path must not add a fourth reference entry point; the
  referent binding stays where it is;
* **$D_{patch}$ untouched**: `LocalOracleRestore` there is an **alias** of
  `DeleteFactualPatch` (§65.2, A76 §63.6), a different implementation of the same tier on a
  value-free store. Its ledger `canonical()` bytes must not move, and the $D_{patch}$ arm
  count must stay 3.
* mutation self-check for each of the above, with the failure reason declared where a gate can
  only fail by not raising.

**One question I cannot answer from the frozen text**, and which decides part of the above:
$L_3$'s population. $L_2$ reaches only the 32 of 278 healthy addresses that have a verified
alternative, while $L_3$ needs no $a^+$ and so applies to **every** credited address. If that
is intended — $L_3$ is the within-row oracle **ceiling**, and a ceiling evaluated on a
different population than its treatments is not comparable to them — then the matrix's
comparison rule needs to say so. If instead the comparison is meant to be restricted to a
common address set, that is a B2 population decision, and it should be taken before $L_3$'s
numbers are produced rather than after.

## 5. What this draft does not authorise

* no code, no test, no ledger, no artifact — the tree stays at $L_2$ CLOSED;
* no change to `cells`, to $L_0$, to $L_2$, or to the $D_{patch}$ row;
* no B2 endpoint, denominator, regime I number, or oracle-ceiling choice (A76 §63.8);
* no claim that $L_3$ closes D6, and no automatic continuation to anything after it.
