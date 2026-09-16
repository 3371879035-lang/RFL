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

## 4. Resolution — two gates, not one, and both fail

`03` §4 offers merge or add-a-query. Adding a query cannot work for Gate_Z: no
query can reveal a fault with no consequence.

**A proposed resolution to replace $Z$ by $B$ as Gate L's target is WITHDRAWN.**
It was argued as a bug fix and it is not one. $Z \neq B$ is a load-bearing
distinction in this project, and in an overdetermined world a genuinely present
fault can have $B_i = 0$ — two real faults can each be non-difference-makers
because they are redundant with each other. So

$$\boxed{\text{changing the gate target from } Z \text{ to } B \;\neq\; \text{fixing a criterion bug}}$$

It is **changing V0.1R's scientific question**. V0.1R as specified in
`06-V01R.md` claims to recover *which faults occurred*; licensing that claim with
a $B$-gate would be illegitimate, because a learner can fail to recover $Z$ and
still pass.

The target is therefore **not** overwritten. Gate L splits in two, and both are
reported:

$$\boxed{\text{Gate}_Z:\ \text{fault-presence identifiability}} \qquad
  \boxed{\text{Gate}_B:\ \text{but-for-relevance identifiability}}$$

| gate | target | verdict |
|---|---|---|
| **Gate_Z** | $Z$, fault presence | **FAIL** — 2,695 / 2,749 multi-$Z$ classes provably unidentifiable at any depth; dominated by dormant faults, chiefly an untriggered $U$ |
| **Gate_B** | $B$, but-for relevance | **FAIL** — 432 classes provably unidentifiable at any depth; residual concentrated in $P$ / $E$ |

This is the *stronger* statement, and it is the one to freeze:

> Gate_Z does not fail merely because $Z$ is too demanding. Even after retreating
> to but-for relevance — the weakest target that is still action-relevant —
> the current learner query set remains insufficient.

**Consequence for the chain.** `06-V01R.md`'s go/no-go lists "Identifiability
Gate L: PASS — every cause separable within $B_{CF}$". That row is now
unsatisfied under **both** readings, so **V0.1R seed collection is paused**: a
**FAIL** under either gate, and certainly under both, prohibits proceeding.

Two legitimate directions remain, and neither is taken here:

* if the identifiable quotient $B/{\sim}$ (§7 and `a52_quotient.json`) preserves
  the distinction the project actually studies — Process vs Environment — then a
  formal amendment $B \to \widetilde B$ is available, justified *by the failed
  gate* rather than chosen to make a method pass;
* if the quotient is too coarse to preserve that distinction, no merge is
  available and a genuinely new diagnostic capability is required — one that must
  first be argued for as something a real learner could possess.

$do(Z_i = \text{off})$ is **rejected** as that capability, and the rejection is
frozen: $B_i = \mathbf{1}[Y(do(Z_i{=}0)) \neq Y]$, so handing the learner
$do(Z_i{=}0)$ in order to certify that $B_i$ is identifiable installs the
ground-truth construction itself as a diagnostic query. It is the same error as
A50(d): silently promoting a structure the evaluator knows into a structure the
learner may access. Gate_Z and Gate_B are therefore both reported as **FAILED**,
and closing either is a separate amendment.

## 7. Gate L re-run under the $B$ criterion

Re-running with $B$ as the target (`scripts/gate_stage4_B.py`; $B$ from
`kernel.but_for_relevance` with $\omega$ held fixed; representatives deduplicated
on $(\text{dynamical\_key}, B)$ so that worlds agreeing on all dynamics but
disagreeing on $B$ stay distinct):

| verdict | under $Z$ | under $B$ |
|---|---|---|
| $D = 0$ | 172 | 2,198 |
| $D = 1$ | 54 | 291 |
| provably unidentifiable at any depth | 2,695 | **432** |

So the relabel removes $84\%$ of the failures but **does not close the gate**.
Gate L still FAILS, on 432 classes.

The residual is *not* a budget problem, and this is the sharpest form of the
finding: $\max_C D(C) = 1$ over every decidable class. The budget $B_{CF} = 4$ is
generous and no increase helps; the obstruction is that 432 classes contain two
worlds that no legal query can tell apart.

Attribution of the disagreeing $B$ components across those 432:

| component | classes |
|---|---|
| `E` (plant relevance) | **294** |
| `P` (process relevance) | 108 |

No `X`, `D` or `U` term appears, and every one of the 432 has a pairwise witness.

**This is a different defect from §3, and it is about the query set, not the
label.** $B_i$ is defined by *removing* fault $i$ and comparing outcomes, but the
learner's intervention lattice is

$$\mathcal I = \{do(z = z')\} \cup \{do(d_t = d')\} \cup \{do(C_X(s^\ast, a^{cmd}) = a^{cmd})\} \cup \{\emptyset\},$$

which contains **no operation that removes a fault**. A process query changes
`base_option`; it does not switch $Z_P$ off. So two worlds can agree on every
query the learner may issue while differing on whether removing the plant or
process fault would have changed the outcome.

The obvious repair — add $do(Z_i = \text{off})$ to the learner's set — is
**rejected here**, and the reason matters: $do(Z_i=\text{off})$ *is* the but-for
test. Certifying that $B$ is identifiable by handing the learner the operation
that defines $B$ is circular, and it is the same class of mistake as A50(d)
(exposing a function of hidden $M$ to the learner for free). Gate L would pass by
construction and measure nothing.

So Gate L remains FAILED under the decided criterion, on 432 classes, for a
reason that is now precisely located. Resolving it is a separate amendment about
the task's query set, and it is not taken here.

## 7b. The identifiable quotient, and why the merge is unavailable

Read out with `scripts/a52_quotient.py` — **no environment edit, no new target,
no added query**; it only asks what ontology the current interface supports.
Logged as **A52**.

Two worlds are equivalent when no history-dependent safe policy separates them.
That relation is exactly "no single query separates the pair", and it is
transitive: a tree splits worlds only along query responses, so if $r_1, r_3$
were split while neither $r_1, r_2$ nor $r_2, r_3$ is, then $r_2$ is legal on
that query and must return one of the two responses and differ from the other —
one of those pairs was split. Hence components of the complement-of-separability
graph give $\mathcal B/{\sim}$ **exactly**.

* 723 classes span more than one $B$; 432 carry an inseparable $B$ pair.
* Every such per-class component holds exactly **two** $B$-vectors.
* 17 inseparable pairs $\to$ **7** components of $\mathcal B/{\sim}$.
* Collapsing the $P$ and $E$ coordinates makes **all 432 vanish**;
  $\{P, E\}$ is the minimal such set, size 2.

$$\boxed{\widetilde{\mathcal B} = \mathcal B/\sim \;\text{keeps}\; (D, X, U)
\;\text{and discards}\; (P, E)}$$

**This is why §4's option 1 is unavailable.** The two coordinates the interface
cannot separate are *exactly Process and Environment*. Merging them is not
bookkeeping; it deletes the independent variable this project exists to study.
The merge is illegitimate here not in general, but because this particular
quotient destroys the question.

**There is a deeper bound, and it closes the obvious escape.** $B_i$ is *defined*
as the outcome difference produced by applying the repair of fault $i$. So $B$ is
identifiable exactly to the extent the learner can already apply repairs — and
repair is what the chain is trying to *learn* in V0.3R. A gate that certifies $B$
by granting repair queries certifies nothing. Gate_B's failure is therefore not
an oversight to be patched but a load-bearing property of the task as posed.

The only direction left is a genuinely new diagnostic capability — a process
audit for $P$, an independent plant/environment channel for $E$ — and it must
first be argued that a *real* learner could possess it, after which the entire
gate is re-run. That argument is not made here.

## 8. What is not happening

* $B_{CF}$ is **not** being raised. It buys literally nothing here.
* The environment is **not** being tuned to make the gate pass.
* The 2,695 unbounded classes are **not** being dropped. They are the finding.

## 9. Reproduce

```bash
python scripts/stage4_unidentifiable.py    # the Gate_Z proof and the attribution
python scripts/gate_stage4.py              # depth table at B_CF = 4, target Z
python scripts/gate_stage4_B.py            # the same, target B
python scripts/a52_quotient.py             # B/~ and the minimal merge
python scripts/verify_stage4_full.py       # V4, two algorithms, all classes
python scripts/verify_stage4_witnesses.py  # V3, all 54 positive claims
python scripts/capacity_bound.py           # counting, no search
```

Artifacts: `outputs/rebuild/stage4_unidentifiable.json`, `gate_stage4.json`,
`gate_stage4_B.json`, `a52_quotient.json`, `verify_stage4_full.json`,
`verify_stage4.json`, `capacity_bound.json`.
