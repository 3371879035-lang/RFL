# RFL-Rebuild — frozen research specification

**Status:** specification complete, **no implementation and no runs yet**.
Nothing in this directory is a result. There is no evidence here, only design.

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
| **11** | [`11-ENVIRONMENT.md`](11-ENVIRONMENT.md) | the concrete task, the four strategy programs, the controller/plant split, the tape-addressing rule, and every deferred value with its default |

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

## 7. What happens next

Implementation, in this order, with nothing skipped:

1. `src/rfl_rebuild/env/` — the SCM, forward generation, truth fields;
2. identifiability matrix generator → **Gate E must pass**;
3. semantic suite → **I1–I6 and C0–C8 must pass**;
4. V0.1R arms and metrics → Gate L → development calibration → seeds;
5. and only then V0.2R.

No version may begin collection while a gate upstream of it is failing.

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
* $Q^{*}$, $\pi_{\text{ref}}$, $V_{\text{pre}}$ as one shared artifact (`11` §12);
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
