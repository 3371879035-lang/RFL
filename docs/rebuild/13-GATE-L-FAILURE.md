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

## 10. A53 — the plant audit, and why no observability can close Gate_B

The decided diagnostic was added (`03` §3.1): an on-demand, budgeted
`audit_plant_input(t) → u_t`, cost 1, counted in the total query budget $B_Q$
(value unchanged at 4). Full re-run of **both** gates:

| | before A53 | after A53 |
|---|---|---|
| Gate_Z residual | 2,695 | **2,665** — still FAIL |
| Gate_B residual | 432 | **261** — still FAIL |
| $\mathcal B/{\sim}$ components | 7 | 6 |

$B_Q$ is still not binding in either gate (largest finite depth: 2 under Gate_Z,
3 under Gate_B). The audit bought 171 real classes and no budget increase would
buy the rest.

**The 109 surviving `E` witnesses settle the question.** Saved in
`a53_e_witnesses.json`; in all 109, the plant fault fires on the factual rollout
in *both* worlds, the controller fault in neither, and the two worlds are
**identical through the audit — every $u_t$ agrees**. They still differ in $B_E$,
because they differ in latent parameters (`base_option`, `trap`) that have no
factual effect yet change the outcome of the *fault-removed* rollout. Minimal
witness, class 11:

```
world_a  Z=[1,0,0,1,0]  base_option=0  plant=PlantFault(t=0, realized=4)  trap=None
world_b  Z=[1,0,0,1,1]  base_option=2  plant=PlantFault(t=0, realized=4)  trap=Trap((3,4),4)
B_a=[0,0,0,0,0]   B_b=[0,0,0,1,0]        (differ in E only)
chain (t,a_cmd,u,a_realized), identical in both:
  [(0,3,3,4), (1,3,3,3), (2,1,1,1), (3,1,1,1), (4,3,3,3),
   (5,3,3,3), (6,0,0,0), (7,0,0,0), (8,3,3,3)]
```

$$\boxed{\text{the current factual execution interface} + \text{plant telemetry cannot identify these } B_E}$$

**Narrower than first written, on purpose.** "No factual telemetry, however rich,
can identify $B$" is too strong. The two witness worlds differ in `base_option`
and in the trap configuration, and those are *factual* latent variables: a system
with legitimate provenance/configuration telemetry could separate the worlds
without ever calling $do(Z_E{=}\text{off})$. What the witnesses prove is the box,
not an impossibility over all factual information. The gap is specific to
telemetry on the *action path*, and this is exactly the distinction A54 turns on.

**V0.1R stays paused at the time of A53**, because V0.1R's primary target was
then $Z^{\text{pres}}$ and Gate_Z is dominated by dormant $U$ faults — faults
with no behavioural consequence whose *presence* is nonetheless demanded. Section
11 resolves that; A53 does not.

## 11. A54 — the split, and Gate_fire

`Z` was carrying three objects at once. Split into $Z^{\text{pres}}$ (configured),
$Z^{\text{fire}}$ (the mechanism actually executed) and $B$ (but-for), with
$Z^{\text{pres}} \ge Z^{\text{fire}}$. **V0.1R's primary target is now
$Z^{\text{fire}}$** — a scientific-question revision, not a gate fix, because it
stays a diagnosis question and only corrects *what was secretly configured* to
*what actually executed* (`12-AMENDMENTS.md` **A54**). The feedback channel is
driven by $Z^{\text{fire}}$ too, so a truthful claim can no longer point at a
dormant fault.

Re-running with the fire target (partition is now 2,783 classes, because the
feedback semantics changed):

| gate | target | verdict |
|---|---|---|
| **Gate_fire** | $Z^{\text{fire}}$ | **FAIL** — 600 classes provably unidentifiable at any depth |
| Gate_Z | $Z^{\text{pres}}$, diagnostic only | FAIL — 2,713 |
| Gate_B | $B$, secondary and **non-blocking** | FAIL — 245, attribution `E` 95 / `P` 120 |

$$\boxed{\text{Gate\_fire residual} = 100\%\ P}$$

$E$, $X$, $D$ and $U$ are **fully resolved**. The plant audit plus the ontology
split close everything except process observability, and again $\max_C D(C) = 1$
against $B_Q = 4$, so the budget is not the constraint.

Gate_B is **not** a blocker. `11` §6.2 already required that a non-identifiable
$B$ be reported **not evaluable** rather than treated as an algorithm negative
result, and A53 proved it is not identifiable here. Chasing it green would be
fitting the task to the gate.

**Next step, and it is a decision rather than a patch.** The residual is
exclusively $P$, which is exactly the branch that makes a process provenance layer
worth building. But it cannot be instrumented until $Z_P$'s **denotation** is
settled — planner chose a bad strategy? correct proposal swapped in a commit
layer? strategy program unsuited to context? — because those are three different
mechanisms. A non-cheating process audit needs the SCM to carry

$$z^{proposal} \rightarrow \text{process/commit layer} \rightarrow z^{\text{in force}}$$

first. No query is added here.

## 12. A55 — Gate_fire PASSES

$Z_P$'s denotation was the last open question: planner chose a bad strategy?
correct proposal swapped in a commit layer? strategy unsuited to context? Fixed
as the second, in its strict form — the commit layer failed to faithfully commit
what the planner proposed, and **the proposal need not be optimal or correct**:

$$\boxed{Z_P = \text{process commit / routing integrity fault}}, \qquad
\kappa \rightarrow z^{\text{proposal}} \rightarrow C_P \rightarrow z^{\text{in-force}} \rightarrow a^{cmd}$$

The other two readings are rejected: "bad plan" needs a reference for "bad" and
$z^{*}$ would restore the solver→generator circularity A19 removed; "unsuited
strategy" is a normative relation, not an exogenous injection. No world dynamics
changed — `base_option` **is** $z^{\text{proposal}}$, `option_in_force` **is**
$z^{\text{in-force}}$.

Added the parallel audit $q^{proc} = \mathrm{audit\_process\_proposal}() \to z^{\text{proposal}}$,
cost 1, and re-ran:

| gate | target | before A55 | after A55 |
|---|---|---|---|
| **Gate_fire** | $Z^{\text{fire}}$ | FAIL, 600 | **PASS** |
| Gate_Z | $Z^{\text{pres}}$, diagnostic | FAIL 2,713 | FAIL 2,713 |
| Gate_B | $B$, secondary/non-blocking | FAIL 245 | FAIL 135 |

Gate_fire: $D = 0$ 1,553, $D = 1$ 990, $D = 2$ 230, $D = 3$ 10, unidentifiable
**0**. So $B_{\min}^{\text{adaptive}} = 3 \le B_Q = 4$.

$$\boxed{\text{Gate\_fire PASS at } B_Q = 4}$$

The 600-class residual A54 measured was 100% $P$ and is closed entirely by the
process proposal audit.

**The margin is one unit.** $3$ against a budget of $4$, where every earlier gate
had three or more units of slack. This is the first time $B_Q$ is anywhere near
binding, and a single added identifiability requirement would break it. Recorded
so that the pass is read with its actual width. $B_Q$ is not raised.

**V0.1R's identifiability precondition is met for the first time.** Seed
collection may resume subject to the remaining go/no-go rows (`06-V01R.md` §7),
which have not been run.

## 8. What is not happening

* $B_Q$ is **not** being raised. It is not the binding constraint under either
  gate — the largest finite adaptive depth is 2 (Gate_Z) and 3 (Gate_B) against a
  budget of 4 — so raising it buys nothing.
* The environment is **not** being tuned to make the gates pass, and the fault
  support and label set are **not** changed.
* The residual classes are **not** being dropped. They are the finding.
* The plant audit is **not** being escalated toward "seeing $E$". Section 10
  shows that would be futile in principle, not merely unhelpful.

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
