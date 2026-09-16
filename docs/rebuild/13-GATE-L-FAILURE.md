# 13 — Gate L fails, and it is a specification defect

Status: **Gate L FAILS at the frozen $B_{CF}=4$.** The failure is proved, not
measured, and it is not repairable by raising the budget. This document records
what failed, why, and which of `03` §4's two resolutions applies. Logged as
**A51** in `12-AMENDMENTS.md`.

Nothing here is a result about RFL. It is a finding about the gate.

---

## 1. The result

Enumeration: $1{,}166{,}400$ candidate latent cases, $1{,}038{,}960$ feasible,
$127{,}440$ malformed (tabled with reasons). Collapsing factual signatures gives
$2{,}921$ classes.

| verdict | classes |
|---|---|
| single $Z$ — nothing to identify | 172 |
| $D(C) = 1$ | 54 |
| **provably unidentifiable at ANY finite depth** | **2,695** |

$54 + 2{,}695 = 2{,}749$ multi-$Z$ classes. Gate L's condition is
$\max_C D(C) \le B_{CF}$; it is violated by $2{,}695$ classes at every budget,
so the failure is not an artefact of $B_{CF} = 4$.

"At ANY finite depth" is a proof, not a depth-8 search that ran out of patience.
The bottom-up closure of `stage4_unidentifiable.py` is the monotone closure of the
"separable within depth $d$" predicate over a finite lattice; when it reaches a
fixed point with the root still unseparated, no finite $d$ separates it. The
probe that merely raised the cap to 8 recovered **zero** classes, which is
consistent with the proof and would be a bizarre coincidence without it.

## 2. Why it is not verifiable by the code that produced it

Four checks, none sharing an implementation with the DP, all committed:

| check | scope | result |
|---|---|---|
| **V1** necessary condition $D(C) \le \lvert S\rvert$ for a non-adaptive separating set $S$ | **every class** | 0 violations |
| **V2** no-memoisation, no-prune, no-early-exit brute-force tree search | 113 sampled | 113/113 agree |
| **V3** witness replay of every finite-depth claim | **all 54** | 54/54 replay to single-$Z$ leaves |
| **V4** bottom-up fixed point — different algorithm, no recursion, no early exit | **all 2,749** | 2,749 agree, 0 disagree |

## 3. Root cause

Every one of the 2,695 unbounded classes admits an **airtight pairwise witness**:
two feasible cases with *different* $Z$ that produce the same factual observation
$\sigma_0$ **and** the same response to *every* legal query. A decision tree can
only ever split worlds along query responses, so no adaptive policy at any budget
can tell them apart. This needs no search and no depth theory.

Attributing each witness to the cause keys the two worlds disagree on:

| keys | classes |
|---|---|
| `U` (trap) alone | **2,435** |
| `X` (controller) alone | 218 |
| `X+E` | 42 |

The trap term dominates. The mechanism is visible in the generator.
`identifiability_gate.canonicalise` selects `[domain[0], domain[-1]]` under the
frozen order and is **deliberately blind to outcome** — that blindness is the
stated reason the domain is a pre-declared finite support rather than
outcome-conditioned sampling. But `_domains` populates `U` with
`Trap(cell, t)` for *every* open cell at *every* time step of the healthy trace.
Most such traps cannot fire: the agent never enters that cell at that time. The
canonical first/last elements are therefore, in general, traps with **no effect
whatsoever** on the trajectory, the feedback, or the outcome.

A fault that cannot fire is, by construction, observationally identical to its
own absence. So the gate is asked to separate $Z_U = 1$ from $Z_U = 0$ in worlds
where the distinction has no consequence — and it cannot, at any budget.

**This is a specification defect, not an environment defect.** Two definitions
that this project already keeps strictly apart are being conflated:

* $Z$ — *fault presence*, a mechanism-agnostic fact about the world;
* $B$ — *but-for relevance*, whether removing the fault changes the outcome
  (`03` §3.2).

Gate L as written demands that $Z$ be recoverable. What RFL needs — for credit,
for repair, for $R^\ast$ — is $B$ and $R^\ast$. A fault that never fires has
$B = 0$ and no repair, and demanding that a learner distinguish it is demanding
the impossible and the useless at once.

## 4. Resolution — decided

`03` §4 offers merge or add-a-query. Adding a query cannot work here: no query
can reveal a fault with no consequence. So the resolution is a label change.

**DECIDED: option (1). The gate's target becomes $B$; $Z$ is retained as the
world's mechanism flag.** The criterion is now: *every but-for-relevant cause
pattern is separable within $B_{CF}$*. `canonicalise`'s outcome-blindness is
preserved exactly — the canonical domains are untouched — and only the label the
gate demands separation of changes. This is also the smaller change to the chain,
because V0.2R's $R_{\text{causal}}$ is already defined on $B$.

Option (2), restricting the canonical domains to trace-realizable faults, was
**not** adopted. It is not sufficient on its own (the 218 `X`-only and 42 `X+E`
witnesses are not explained by the trap term), and adopting it would have put an
outcome-blindness exception into the generator to fix a defect that lives in the
criterion. The domains stay as they are.

Consequence to keep straight: a fault that is present but has $B_i = 0$ is
**not** required to be recovered, and a learner that fails to recover it is not
wrong. Downstream, $Z$ remains available to the evaluator as the mechanism flag,
so metrics that need ground-truth mechanism (e.g. the malformed-exclusion table)
are unaffected; metrics that need *what to repair* use $B$ and $R^\ast$, as they
always did.

Logged as **A51** in `12-AMENDMENTS.md`, frozen before any seed.

## 5. What is not happening

* $B_{CF}$ is **not** being raised. It buys literally nothing here.
* The environment is **not** being tuned to make the gate pass.
* The 2,695 unbounded classes are **not** being dropped. They are the finding.

## 6. Reproduce

```
python scripts/stage4_unidentifiable.py    # the proof and the attribution
python scripts/gate_stage4.py              # the depth table at B_CF = 4
python scripts/verify_stage4_full.py       # V4, two algorithms, all classes
python scripts/verify_stage4_witnesses.py  # V3, all 54 positive claims
python scripts/capacity_bound.py           # counting, no search
```

Artifacts: `outputs/rebuild/stage4_unidentifiable.json`, `gate_stage4.json`,
`verify_stage4_full.json`, `verify_stage4.json`, `capacity_bound.json`.
