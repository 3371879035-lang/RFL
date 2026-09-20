# RFL-Rebuild — frozen research specification

$$\boxed{\text{V0.1R CLOSED};\quad \text{V0.2R CLOSED (A74)};\quad
\text{V0.3R rebased (A75), B1 specified (A76, A77)};\quad \text{V0.4R not started in rebuild}}$$

**Status:** the specification is complete, and this directory now holds **three
different kinds of artifact**: the **frozen specification**, the **implementation and
gates** that discharge it, and **frozen evidence** — support manifests, gate
artifacts, and one census record that is explicitly voided. Each version's document
states its own status, and no single sentence applies to all of them; a reader who
needs to know what is design and what is measured should follow the version state
above into that version's document.

**Branch:** `rebuild` (from `v0.4` / tag `legacy-v0.4.1`).
**Namespace:** `src/rfl_rebuild/`. The legacy trees `src/rflnext/` and
`src/rflv04/` are **frozen and must stay importable**.

---

## 1. Why the rebuild exists

The legacy programme (v0.1–v0.4) is preserved under tags and is not deleted. Its
value is that it made the design errors cheaply, and its failure mode was always
the same:

$$\boxed{\text{One experiment carried several questions at once.}}$$

Attribution accuracy, credit unit, update site, update target, training budget and
final policy quality were entangled in a single AUC. When a number came out badly
there was no way to tell which layer had failed — and when a number came out
well, no way to tell which layer deserved the credit. Three conclusions had to be
withdrawn, one of them a headline.

The rebuild makes **one arrow per version**:

$$\boxed{\text{V0.1R}:\ \text{Evidence} \to \text{Cause inference}}$$
$$\boxed{\text{V0.2R}:\ \text{Causal truth} \to \text{Credit representation}}$$
$$\boxed{\text{V0.3R}:\ \text{Credit truth} \to \text{Repair primitive}}$$
$$\boxed{\text{V0.4R}:\ \text{Learned RFL} \to \text{End-to-end learning}}$$

Each version is gated on the previous one, and each is designed so that its
failure has exactly one interpretation.

---

## 2. Reading order

The order is deliberate: the model of the problem comes before any algorithm, and
every algorithmic choice below is a consequence of a design decision above it.

| # | document | what it fixes |
|---|---|---|
| **01** | [`01-OBSERVATION-MODEL.md`](01-OBSERVATION-MODEL.md) | $a^{policy} \to a^{cmd} \to a^{realized}$; what the learner sees; what is hidden |
| **02** | [`02-SCM.md`](02-SCM.md) | five latent causes, $|\mathcal Z| = 4$, the intervention lattice, forward generation |
| **03** | [`03-IDENTIFIABILITY.md`](03-IDENTIFIABILITY.md) | the identifiability matrix and Gate E / Gate L |
| **04** | [`04-SEMANTIC-INVARIANTS.md`](04-SEMANTIC-INVARIANTS.md) | invariants I1–I6 and the case suite C0–C8 |
| **05** | [`05-STATISTICAL-PROTOCOL.md`](05-STATISTICAL-PROTOCOL.md) | tiers, blocks, the four-way rule, $T$ freezing, RMST |
| **06** | [`06-V01R.md`](06-V01R.md) | V0.1R — cause inference, no learning |
| **07** | [`07-V02R.md`](07-V02R.md) | V0.2R — credit representation, no learning |
| **08** | [`08-V03R.md`](08-V03R.md) | V0.3R — repair primitive, offline gate then online |
| **09** | [`09-V04R.md`](09-V04R.md) | V0.4R — end-to-end, candidate competition |
| **10** | [`10-REPRODUCIBILITY-AND-OPS.md`](10-REPRODUCIBILITY-AND-OPS.md) | determinism, fingerprints, runtime calibration, artifact layout |
| **11** | [`11-ENVIRONMENT.md`](11-ENVIRONMENT.md) | the concrete task, the four options, the controller/plant split, the tape-addressing rule, and every deferred value with its default |
| **12** | [`12-AMENDMENTS.md`](12-AMENDMENTS.md) | append-only amendment log: eight corrections raised before implementation, four of which would have changed the meaning of an experiment |
| **13** | [`13-GATE-L-FAILURE.md`](13-GATE-L-FAILURE.md) | Gate L fails: 2,695 of 2,749 multi-$Z$ classes are provably unidentifiable at any finite budget, and the defect is in the gate's label ($Z$ vs $B$), not in the world |
| **14** | [`14-V01R-METHOD-CONTRACT.md`](14-V01R-METHOD-CONTRACT.md) | the frozen V0.1R method boundary: interfaces, runner-enforced arm isolation, A50 in the API, and the S1 assertion map |
| **15** | [`15-SCENE-DGP.md`](15-SCENE-DGP.md) | the frozen scene DGP, the four arms' hypothesis populations, and why dev_v1 is void for discriminative-range inference |
| **16** | [`16-V02R-SEMANTICS.md`](16-V02R-SEMANTICS.md) | the V0.2R objects: $C^{\text{fire}} \neq R^{\text{mech}} \neq R^{\text{rescue}} \neq \Gamma^{\text{credit}} \neq W^{\text{update}}$, the re-frozen credit-unit ontology, and the set-valued responsibility truth |
| **17** | [`17-V02R-METHOD-CONTRACT.md`](17-V02R-METHOD-CONTRACT.md) | the V0.2R method boundary: native alphabets, the evaluator-side semantic expansion $\eta_R$, the forbidding of truth in the expansion, and the S2 assertion map |

---

## 3. The gate chain

Nothing downstream runs until everything upstream has passed.

```
identifiability gate (E and L)  ──►  semantic suite (I1–I6, C0–C8)  ──►  V0.1R
                                                                          │
                       ┌──────────────────────────────────────────────────┘
                       ▼
                     V0.2R  ──►  V0.3R Block 1 (offline)  ──►  V0.3R Block 2 (online)  ──►  V0.4R
```

| gate | blocks | document |
|---|---|---|
| Gate E — evaluator identifiability | everything | `03` §2 |
| Gate L — learner identifiability | V0.1R seeds | `03` §2 |
| Semantic suite | all seeds, all versions | `04` §3 |
| Oracle ceiling | V0.1R | `06` §3.1 |
| Representation distinctness | V0.2R | `07` §8 |
| Block 1 offline repair | V0.3R Block 2 | `08` §4 |
| Oracle-vs-baseline | V0.4R | `09` §6 |

A failed gate is a **bug or a design flaw**, never a result. Gate failures are
reported in this directory as amendments, not in a results document.

---

## 4. The four rules that matter most

These are the ones the legacy programme learned the hard way. Each is enforced
mechanically, not by discipline.

$$\boxed{\text{1. Never change the algorithm while collecting seeds.}}$$
Voiding is automatic via source fingerprint (`10` §2).

$$\boxed{\text{2. A bug found after collection voids the entire seed set.}}$$
Fix, then restart from $N = 0$. Never resume, extend, or pool across the change
(`05` §10).

$$\boxed{\text{3. A contrast's tier is frozen before collection.}}$$
"No, that looked good — let us add 400 seeds" is prohibited. An upgrade is a new
pre-registered study with a fresh seed base (`05` §2.1).

$$\boxed{\text{4. Look at the per-seed distribution before the mean.}}$$
Tabular RL readily produces 70% exact ties plus a few huge outliers, in which case
the mean describes a handful of runs. Tie fraction, median, trimmed mean, sign
test and top-5 share are mandatory companions to every mean (`05` §5).

---

## 5. Key design decisions, and the legacy failure each one answers

| decision | legacy failure it prevents |
|---|---|
| $a^{cmd}$ is **visible**; only $Z$ and $M$ are hidden | hiding a system's own command manufactures artificial partial observability |
| Identifiability is a hard gate | testing a method on a problem no method could solve |
| Cause truth $C$ and repair truth $R^{*}$ are **different objects** | "attribution" was asked to be a diagnosis and a prescription at once |
| A process fault means *the process is the right granularity*, not *size > 1* | `WholeProcess` inflated to 68.4% by a reconstruction bug |
| $|\mathcal Z| = 4$, enumerable | process-level repair had no intervenable referent |
| Execution has its own learnable controller $C_X$ | `DECISION` and `EXECUTION` were two names for one Q table |
| Forward generation only; no label reconstruction | `scene_from_trace` derived decision faults from realized actions |
| Write-space disjointness is a global invariant | two units wrote one entry; 3.3× spread in `WMD` from hash order |
| $T$ frozen from the **baseline only** | training budget was chosen after seeing the treatment curve |
| Four-way verdict against $\Delta_{\min}$, not $p < 0.05$ | seven CI flips that changed no conclusion, reported as reversals |
| RMST with right-censoring | averaging time-to-recover over only the seeds that recovered |
| V0.2R has **no learning loop** | selecting a representation with an unvalidated primitive |
| V0.3R has an **offline gate** before online | a mis-implemented "ceiling" arm produced a false negative |
| `c_keep` (change nothing) is a candidate | arms edited unconditionally on failure, so `NoCorrection` kept winning for the wrong reason |
| Update-dynamics ledger | reward modes are affine in expectation but not under fixed $\alpha$ and clipping |

---

## 6. Legacy record

The old work is preserved, unedited in substance, under annotated tags:

| tag | content |
|---|---|
| `legacy-v0.1` | attribution microbenchmark |
| `legacy-v0.2` | responsibility → learning chain |
| `legacy-v0.3` | credit / repair semantics, stage 1 |
| `legacy-v0.4.1` | credit-unit and repair semantics, frozen protocol |

Its three most useful documents are included in the legacy tree and remain
accurate:

* `docs/ROBUSTNESS_AUDIT.md` — why a mean over these per-seed deltas is not
  interpretable on its own;
* `docs/REVERSAL_LEDGER.md` — at which $N$ each verdict moved, and how many
  "reversals" were no-ops;
* `docs/V0_4_SEMANTIC_CORRECTIONS.md` — the withdrawn headline and the four
  semantic defects that motivated this rebuild.

$$\boxed{\text{The legacy programme's real output was the specification of how to test the rebuild.}}$$

---

## 7. Execution order — historical, and the current next step

**This section is a record, not a plan.** The chain below was executed in full:
steps 1–5 are complete, V0.1R is closed and V0.2R is closed. It is kept because it is
the dependency chain the rebuild actually walked, and because a future reader needs
to know *why* the kernel had to exist before the DP, and the DP before
`route_check`.

The order below is the first in this project with no circular dependency. Two
earlier proposals were rejected: writing `route_check.py` and the identifiability
generator standalone, then letting their results decide how `env/` is written,
was **circular** and risked a second simulator (`12-AMENDMENTS.md` **A16**); and
placing the DP after `route_check` was still circular, because P2/P3/P4 depend on
the option-conditioned $Q_D^{*}$ and `route_check` must know what the option does
when healthy before it can ask whether a local repair rescues the episode
(**A19**).

$$\boxed{\text{minimal SCM kernel} \to \text{exact reference DP} \to \text{route\_check} \to \text{Gate E/L} \to \text{semantic suite} \to \text{V0.1R}}$$

All six steps below are **done**; they are numbered as the order in which they were
authorised, not as outstanding work.

1. **`src/rfl_rebuild/env/kernel.py`** — state transition, semantic tape, option
   automata and constraints, `do`-operators. **No training, no RFL, no seeds, no
   metrics.** The single source of truth for what the world is; everything later
   imports it and adds nothing of its own about the world.
2. **Exact reference DP** — $Q_D^{*}(s, z, m, a)$ by finite-horizon backup over the
   kernel (`11` §12.1). It *reads* the kernel and *solves* it; it defines nothing
   about the world, so it is not a second simulator and may legally precede
   `route_check`.
3. `scripts/route_check.py` — enumerates the full product and discharges P1–P4 as
   assertions (`11` §4.1). Imports the kernel and the DP.
4. **Gate E, then Gate L** (`03`) — the identifiability matrix over the full
   feasible set, at the budget the learner actually has.
5. Semantic suite — invariants I1–I6 and cases C0–C8 (`04`).
6. V0.1R.

No version may begin collection while a gate upstream of it is failing. Steps 1–5
produce **no scientific result**; they exist to make step 6 interpretable.

### 7.1 Authorisation boundary — withdrawn as a live constraint

**"Only step 1 is authorised" was true when this section was written and is false
now.** Every step listed above has been executed and every gate has been run, so the
staged-authorisation statement is kept as a record of how work was released rather
than as a current restriction. The reasoning behind it is not withdrawn and is worth
preserving: `kernel.py` is the single source of truth for what the world is, so it is
precisely the artifact that must not be written while any semantics of the world
remain undecided. That principle is what produced the gate chain in §3, and it still
governs any future change to `kernel.py`.

### 7.2 The current next step

$$\boxed{\text{the V0.3R rebase has landed (A75); B1 runs in A77 §65.12's order as A78 §66.1 extended it — all five steps closed}}$$

The semantic rebase this section used to ask for **is A75** (§62): the subject is the
persistent learning update, not runtime repair, with the regime-specific populations and the
$J^L$ manifestation family that go with it. A76 (§63) then froze the B1 update-law contract
and A77 (§65) the $D_Q$ row, including the order in which the slice may be built:

$$\text{generic slice refactor only} \rightarrow \text{Q store / read substrate} \rightarrow
L_0\ \texttt{FactualReturnWrite} \rightarrow L_2\ \text{CF builder} + \text{laws}$$

Each step is a separate commit with its own acceptance conditions (A77 §65.12); the first is a
refactor of one implementation and must move no $D_{patch}$ number.

`08-V03R.md` is still **not** an implementation source. It still identifies the process fault
with $do(z = z')$, whereas the frozen reading is

$$\text{mechanism repair} = do(C_P = \mathrm{identity}), \qquad
do(z = z') = \text{strategy replay / rescue}$$

so `08` carries an error that must not be inherited, and rebasing it remains a semantic change
that has not been made. What changed with A75–A77 is that the B1 path no longer waits on `08`:
it is specified in the amendment log, and `08` is superseded on that path until it is rebased.

**Status of that sequence.** All four steps are closed: the generic slice refactor, the $Q$
store and read substrate, $L_0$ `FactualReturnWrite`, and $L_2$ (the CF builder with
`CounterfactualReturnWrite` and `DualReturnWrite`). The sequence as A77 §65.12 wrote it **ends
there**, so §65.9's frozen $L_3$ semantics were not an implementation authorisation, and reading
$L_2$'s closure as one would have been proceeding by tacit consent on a frozen order.

That gap was raised as a request and **closed by A78 (§66)**, which is now the normative text: it
extends the order by exactly one step — $L_3$ `LocalOracleRestore` on $D_Q$, one commit, no
mixing, no new scope for the four closed steps — names `NoWriteRef(L3)` so that
$\lvert\text{treatments}\rvert(D_Q)=4$ as A76 §63.8 froze, fixes the B1 law domain as **every
credited address for $L_2$ and $L_3$ alike** (`NO_VALID_ALTERNATIVE` addresses stay in the
population, and $L_3$ may not key its domain on $a^+$ availability), scopes "no reference" to the
lowering and to *no new* entry point, keeps the row operation inside B1 so the substrate does not
learn an update law, makes lowering an explicit pre-commit phase whose **lowered concrete edits**
the ledger reads, and keeps the $D_Q$ law an independent implementation beside the untouched
$D_{patch}$ alias. The pre-decision request survives as `19-V03R-B1-L3-DRAFT.md`, marked
superseded and non-normative.

**A78's step is now closed too.** $L_3$ `LocalOracleRestore` is implemented and audited closed
at `74213a7`, with its evidence binding at `9f29ce1`. The chain the review required is complete
end to end:

$$\text{strict credited context} \rightarrow \text{nominal } \texttt{RestoreRow} \rightarrow
\text{strict row context} \rightarrow \text{load-bearing owner} \rightarrow
\text{one-pre-state lowering} \rightarrow \text{one transaction} \rightarrow
\text{lowered-plan ledger}$$

with the cell's two arms sharing **one** admissibility boundary, checked before any arm plans.
All five steps of the extended order are therefore closed, and **no further step is
authorised**: B2's endpoints, denominators, strata and regime I numbers remain open and are not
implied by any of this.

**Recorded observation, deliberately not actioned.** The $D_{patch}$ entry points are *not*
guarded the same way. Measured at the real entry point for all three folding aliases, and
**identical before and after A80 Step 1**:

| alias | `NoWrite` | `SetAlternative` |
|---|---|---|
| `State(x{=}1.0)` | accepts | accepts and **writes**, onto the legal entry through folding |
| `z{=}\texttt{True}` | accepts | refused by the store's typed address boundary |
| `m{=}0.0` | accepts | refused by the store's typed address boundary |

So the asymmetry holds for the `z`/`m` forms, while the floated `x` is a stronger pre-existing
fact: the decision store types `z` and `m` and **not** the `State` fields, so that alias folds onto
the legal key and the write lands there. The reviewer's ruling is to **leave $D_{patch}$ frozen as
audited** -- the 396-entry ledger baseline is built on that architecture, and tightening its
accepted inputs is a change to a frozen artifact rather than a side effect of another step. A80
Step 1 briefly made the credited boundary universal and removed the asymmetry for *both* arms;
that drift was caught in review, undone, and is now held in place by
`test_19_the_frozen_d_patch_alias_asymmetry_is_preserved`. It is recorded here so that it is a known
property of the frozen architecture rather than a rediscovery, and reopening it would need its
own authorisation.

**The current next step is B2, and it is pre-registered before it is run.** `08-V03R.md` §3 — the
old "online recovery" block — is **superseded on B2 by A79 (§67)**: its arms were retired by A76
and its process reading ($do(z = z')$ as mechanism repair) is rejected by the frozen reading. A79
fixes B2's design and **collects no seed**: the question (*what did this write do to this
learner's future?*), the three independent outcome dimensions with **no composite primary**, $T$
and $P$ as separate populations that may not be pooled, RMST as FutureUtility's primary with
DeficitAUC mandatory, primary collateral as **truth-blind future behavioural spillover**,
Retention as a dimension whose formula is a declared development-stage decision, the local/global
oracle roles, tier-matched contrasts, and `05`'s protocol unchanged — including that $T$ is frozen
from the baseline only and that no $N_{\text{train}}$ may be named in advance. It also records one
prerequisite plainly: ``D6/B1 CLOSED'' is the **Decision** path, and the Process and Controller B1
alias-write paths need their own authorisation before B2 can run.

**A80 (§68) is that authorisation, and it is text only.** It replaces the obvious "do $X$, then $P$"
with **three** steps — a generic address/receipt substrate refactor first, because the shared B1
objects are Decision-shaped while $\rho_X$ yields a site handle and $\rho_P$ an integer, so a
two-step plan would force the address contract to be invented at code time. Step 1 may add no
capability and must move no number; $X$ and $P$ are then implemented as A76 froze them, each with its
own commit and gates. Step 1 is **CLOSED** (`6f78949`, its evidence rebound at `3eeec3a`); Step 2 is
implemented and its closure is under review; **Step 3 is not started and not authorised**, and A80
authorises **no B2 runner, no $\texttt{FutureConsequenceView}$, no $\texttt{BehavioralCollateral}$,
and no seed of any stage**.

**A82 (§70) fixes the wire contract Step 2's entry depends on.** A69's $\texttt{ControllerSite}_t$ is
index notation; A71's concrete encoding $\texttt{ControllerSite}_{x,y,t,a^{cmd}}$ — the string
`PublicSCMView.credit_unit` emits — is the interface, and B1's $\rho_X$ consumes that same unit, with
neither the index spelling nor $\texttt{Decision}_t$ accepted as an alias. Read §70 before touching
either side of that boundary: A75's chain starts at $\Gamma^\ast$, whose units are exactly these.

---

## 8. What the specification fixes, and what it leaves open

An implementer needs to know which choices are theirs. This is the boundary.

### Fixed — changing any of these voids the affected seeds

* the observation model (`01`), the SCM structure (`02`), the concrete environment
  (`11`);
* identifiability gates E and L, and the semantic invariants I1–I6 and cases
  C0–C8 (`03`, `04`);
* the statistical tiers, the four-way rule, the $T$-freezing rule, RMST with
  censoring (`05`);
* each version's **primary endpoint** and **go/no-go gates** (`06`–`09`);
* $Q^{*}$, $\pi_D^{*}$, $V_{\text{pre}}$ as one shared artifact (`11` §12);
* tape addressing by $(t, \text{role})$ (`11` §8).

### Open — the implementation's job, and where the research contribution lives

* **the internals of each method.** The spec fixes what is *compared* and how it
  is *scored*; it does not specify the algorithm inside `SequenceEvidence` or
  `SeqThenCF`. That is the work.
* any representation not listed in `07` §3 may be **added** as an extra arm, but
  the listed ones may not be removed;
* module layout, class design, log format, and the choice of tabular data
  structures;
* the mechanism of $U(c)$ in V0.4R, subject to the one constraint in `09` §3.2
  that it be a genuine uncertainty and not a softmax temperature.

### The rule that governs the boundary

$$\boxed{\text{A free choice may be made at any time \emph{before} it is frozen; after that it is fixed.}}$$

Every free choice that touches a reported number must be declared in
`experiments/<version>/config.yaml` before collection, so that "which choices were
made" is recoverable from the artifacts alone. A choice made after seeing a result
is not a free choice; it is a change to the experiment, and it voids the seeds.
