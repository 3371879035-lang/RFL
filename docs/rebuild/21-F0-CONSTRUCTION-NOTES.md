# 21 --- $F_0$ construction notes (live, not a freeze)

Latest implementation follow-up (2026-09-27):
[`30-F0-STAGE-RUNNERS.md`](30-F0-STAGE-RUNNERS.md) records the manifest generator,
seedless contract check, smoke/development runners, bound smoke receipt and
operational runtime benchmark harness. F0 remains NOT VALID; runtime measurement
and independent scientific review are still pending.

$$\boxed{F_0\ \text{design text} = \text{CLOSED}@\texttt{b923a0b} \qquad F_0\ \text{construction} =
\text{IN PROGRESS} \qquad F_0 = \texttt{NOT VALID}}$$

**What this document is.** The construction of §7's command surface, written down as it happens, on the line
that owns it (`f0-rev3`). It records what landed, what was measured, and --- the part that matters --- the
places where the frozen text and the frozen instrument do not fit together and an implementer must not
choose. It is **not** frozen design text, it changes nothing in
`20-B2-DEV-PROTOCOL-FREEZE.md`, and no statement here may be read as a ruling: every finding below is
addressed to the reviewer, with the measurement that produced it.

**What it does not do.** It draws no scientific seed, runs no smoke, mounts no design artifact, and selects
no $N_{\text{eval}}$, $\mathcal G_{\text{ckpt}}$, refinement, Retention form, $T$ or $\Delta_{\min}$. The
benchmark keys of $\mathcal B_{\text{bench}}$ are used for timing and for fixtures; a number produced with
them never enters a development observation (§1 of the freeze).

## 1. What landed

| commit | object | evidence |
|---|---|---|
| `4162b0d`, `5682daf` | `src/rfl_rebuild/b2/evalorder.py`, `src/rfl_rebuild/b2/acquisition.py`, their tests, the registration in `environment.PRODUCTION_MODULES` and `view.IMPORT_ALLOWLIST` | 753 passed / 1 skipped; `spec_audit.py` exit $0$; `b2_view_gate_selfcheck.py` 45/45; `a91_training_gate_selfcheck.py` 6/6 |

* **`evalorder.py` --- §3's balanced ordering, and the coverage claim recomputed rather than asserted.** The
  construction is §3's, verbatim: the $96$ cells round-robin with $\texttt{cause\_rank} = (7q + 37r) \bmod 60$
  for $n = 96q + r$. The module verifies its own bijectivity on $n = 0, \ldots, 5759$, that a prefix is nested
  and bounded, and that *every* candidate prefix covers $2/2$ $\kappa$, $6/6$ $\phi$, $2/2$ error flags, $4/4$
  options and $60/60$ cause ranks. The digest §3's pre-data verification recorded is pinned:
  $\texttt{prefix\_digest}(1024)_{[:16]} = \texttt{f9ac07213237dbdb}$. The replaced ordering is measured at the
  same prefix --- $\kappa$ $1/2$, $\phi$ $3/6$ --- which is §3's stated reason for replacing it, as a number
  rather than as prose. For §7's manifest contract, the whole-permutation digest is
  $\texttt{prefix\_digest}(5760)$, and each candidate's summary is `coverage(N)`; no second function was added
  for either.
* **`acquisition.py` --- §3's envelope to §3's artifact.**
  $\texttt{BaselineAcquisitionPlan} \to \texttt{acquire\_master\_baseline} \to \{V_{\sigma,e,u}\} \cup$
  eligibility material, with the run key being the seed: each run's own protocol is the envelope *carrying*
  that key, so the training machinery is never handed a protocol whose `seed` is not the key that generated
  its episodes. One rollout per scene supplies both the level and the eligibility material, which is what
  `PreUpdateTraces`' one-object-one-rollout contract is for. `slice_indices`, `sufficient` and `error` derive
  $C_r^{A,\sigma,e}(c)$ and §3's $(\lvert C\rvert, \sum V, \sum V^2)$ mechanically, and **sufficiency is
  verified rather than asserted**: the material's answer for every channel and all six refinements is compared
  against the frozen instrument's own `eligibility`/`refinement` for the same learner, and the shared value of
  an uncontacted site is checked the same way.
* **The mean reproduces A91's accumulation order.** `train_curve`'s `_mean_return` accumulates left to right
  with `total += value`; CPython's `sum()` is Neumaier-compensated, so the two differ by one ulp on the values
  this domain produces ($0.885$ against $0.8849999999999999$). The acquisition reproduces A91's order and
  `test_5`/`test_5b` make the agreement exact, because §4.1, §4.3 and §4.5 all read that quantity.

## 2. The artifact form is measured, not preferred

§3 freezes the sufficiency requirement and permits two forms --- "the per-$(A, \sigma, e, c, r)$ sufficient
statistics ... are the minimum, and the full incidence form ($\textit{Consult}$ and $H_{\text{pre}}$ per unit)
is equally acceptable". Which one an artifact can carry is a measurement:

```text
python scripts/f0_acquisition_size_probe.py      # operational, healthy learner, no seed, writes nothing
production credited domains (A89 §77.4): D_Q = 13824, X = 229, P = 4
bank incidence (N_max = 1024): D_Q 278 sites / 5934 pairs, X 229 / 5934, P 4 / 1024  -> 12892 pairs
finished sufficient statistics, c over the production domain, 32 seeds x 41 episodes: 110,656,704 triples
incidence form: 16,914,304 pairs
one (sigma, e) unit (full-U2 traces + incidence inversion): 0.486 s -> development envelope ~10.6 min
```

$$\boxed{\text{the "minimum" is } 6.5\times \text{ the "alternative" here} \;\Longrightarrow\; \text{the
artifact stores incidence}}$$

Two consequences are recorded rather than absorbed. The first is that the incidence form is the only one of
the two an artifact can carry at this envelope, and it is also the honest one: incidence is what the run's own
episodes produced, while the statistics are a derivation, so a derivation error stays recoverable instead of
becoming a corrupted record. The second is that $c$'s domain is A89 §77.4's **production** credited domain,
$13824 + 229 + 4$ units, of which the bank's episodes consult at most a few hundred: the artifact therefore
also records, per $(A, \sigma, e)$, whether that domain holds a site no bank episode consults, because
$C_r(c) = H_{\text{pre}} \cap S_r$ for such a site and whether that value is *attained* is a property of the
domain. $P$ is the case that makes it load-bearing: all four of its sites are consulted by any full bank, so
the shared value is **not** attained there, and a metric that added it would overstate the maximum.

## 3. Findings for the reviewer

**Dispositions, after the review of `63c5caf` (recorded here as the findings' outcome, not as new text).**
The reviewer ruled CF-1/CF-2/CF-5 **MUST AMEND**, CF-3 a **DOC ERRATUM** and CF-4 **APPROVED as implemented**,
reopened the rev-3 design text for a *targeted* amendment, and marked $d_{(P,\mathrm{RMST})}=1.5$
**NOT RATIFIED**. The amendment is `20-B2-DEV-PROTOCOL-FREEZE.md` rev 4, §1, §3, §4.0, §4.3, §4.5, §7, §11 and
§12. The findings below are left as written --- they are the record of what the construction found, and rev 4
is the record of what was done about it.

| finding | disposition | where it landed |
|---|---|---|
| CF-1 | **MUST AMEND**; reading (a) adopted, (b) and (c) rejected. Second round: **APPROVED** (PASS), implementation pending | §4.0's `sd` authority + §3's stored material; iteration order frozen to ascending bank index |
| CF-2 | **MUST AMEND (P0)**, then **APPROVED**: $I_{D_Q} = W^{\varnothing} + \Delta W^{\text{cal}}_{D_Q}$ as the $F_0$ choice, operational gate pending; A91 §79.3 ruled **pair-local**, no A91 addendum | §1, §3's baseline block, §4.5's cross-reference |
| CF-3 | **DOC ERRATUM**, **CLOSED** | §4.3, §7, header |
| CF-4 | **APPROVED, no action**, **CLOSED** | --- |
| CF-5 | **MUST AMEND**; second round **APPROVED in structure**, shard implementation pending, digest now over uncompressed canonical JSONL | §7 |
| $\mathcal B_{\text{bench}}$ role | **APPROVED** for pre-specified fail-closed construction gates as well as timing | §1's benchmark-keys block, §11 item 27 |
| $d_{(P,\mathrm{RMST})}=1.5$ | **NOT RATIFIED**, $F_0$ VALID blocker | §11 item 14 |

**What the second review round corrected in my own text.** Rev 4's first round attributed the fixed point to
the frozen corpus ("A87 fixes $W_{\text{pre}} = $ no overrides, A91 assigns it to the reference arm, so the
fixed point is mandated"). **That attribution was too strong and is withdrawn**: A87 §75.1's "common to all
three" is scoped to §75's three canary *fixtures*, and A91 §79.3 freezes **pair-relative** initialization
given a caller-supplied state --- the production runner takes `state` as an argument and builds its design
material from "the pair's own pre-update learner, not a minted healthy state". Neither freezes $S_2$'s
stage-level initializer, so rev 3 left the *instance* unspecified. What survives from the research is the
part that decided the initializer: only the $D_Q$ canary lives in the store ordinary learning writes.

### CF-1 --- the triple does not recover the population `sd` exactly, and §4.4's zero cases are exact comparisons

§4.0 says the frozen sufficient statistics "recover this form exactly, which is why they are the declared
minimum". In `float64` they do not, for a set whose values are equal but not exactly representable:
$\sum V^2/n - (\sum V/n)^2$ is a difference of two nearly equal numbers. Measured:
$\mathrm{se}\bigl(1, 0.7, 0.49\bigr) = 7.45 \times 10^{-9}$, not $0$ --- a set of one value, whose population
spread is exactly zero.

$$\boxed{\text{a constant set is the case } \S4.4 \text{ decides by exact comparison} \;\Longrightarrow\;
\text{the round-off decides the branch}}$$

$SE_{A,c,\sigma,e}(\texttt{eligible\_all}) = 0$ is the precondition of both frozen zero-case rules of §4.4,
and $7.45 \times 10^{-9}$ is not $0$, so the $0/0$ case --- "equal stability rather than an undefined
comparison" --- would be read as the *other* branch and become a ratio of two round-off quantities. §4.0 also
forbids replacing an undefined ratio by a number, and forbids rounding before a comparison, so clamping or
tolerance would both be new text.

Readings available: **(a)** recover `sd` by §4.0's own two-pass form over the set's values, which the artifact
also stores --- exactly $0$ for a constant set, and the triple stays the declared storage minimum; **(b)** keep
the triple recovery and accept that the zero cases are decided by round-off; **(c)** freeze an explicit
tolerance, which is a design change. This note recommends **(a)** on the ground that it needs no new text and
no new storage. Not decided here.

### CF-2 --- the baseline run is A91's fixed point, so every baseline curve is exactly flat

A91's own `test_15` asserts that a healthy learner neither moves nor gains overrides, and records why:
training a learner that is *not* at the reference's fixed point legitimately leaves overrides behind. Measured
at the acquisition's scale, on $\mathcal B_{\text{bench}}$ keys and an eleven-episode envelope: **zero**
persisting edits, $\lvert Q_D^L\rvert = 0$, for four keys, including episodes whose tape carries
$\texttt{error\_flag} = 1$. The mechanism is visible in the update rule: the learner starts at the healthy
state, whose effective table **is** $Q^{*}$, and $r_j + \max_{a'} Q^{*}(s', a') = Q^{*}(s_j, a^{\text{cmd}}_j)$
for every visited address --- the Bellman equation, at every action and not only at the greedy one --- so every
edit equals the reference value and `apply_transaction` canonicalises it away.

$$\boxed{W_0 = \text{healthy} \;\Longrightarrow\; W_e = W_0 \ \forall e \;\Longrightarrow\;
V_\sigma(e) \text{ is constant in } e}$$

The consequence is not a crash but a **degenerate input**: every window of every seed is exactly flat, so
$\lvert\mathrm{slope}_K\rvert = 0 < \epsilon_s$ and $\mathrm{FlipRate}_K = 0$ by `05` §6.1's declared
constant-window exception, the *first* window qualifies for every seed, $T_{\text{conv}}$ is a point mass
rather than a distribution, and the censoring machinery of A91 §79.7 --- $Q_{0.9}$ over uncensored runs, the
cap failure, `NO_ADMISSIBLE_T` --- is never reached. $T^{*}$ is then determined by the convergence window's
own convention and the grid templates, not by any learning dynamics. $f_N$ is unaffected in kind (its scale is
*cross-scene*, and scenes do differ), $f_G$'s distortion terms are $0$ on a flat curve, and $f_C$'s
eligibility material is what this increment stores.

Readings available: **(a)** intended --- the baseline *is* the reference, its convergence is trivial by
construction, and $T^{*}$ is a window convention, in which case §4.1's censoring and A91 §79.7's quantile
deserve a note saying so; **(b)** the development baseline acquisition is meant to start from a
**non-reference** $W_0$ (an intervention, a canary, or the pair's own $W_{\text{pre}}$), which F0 §3 does not
say and which would make the curve informative --- but A90 §78.5 forbids treatment arms before $F_1$, so if it
is this, the initial write has to be named in the frozen text. Not decided here; the construction implements
(a), because §3 says "the run's learner" and nothing else.

**Disposition (rev 4): reading (a) was rejected; (b) is the ruling.** The reviewer's chain is verified in the
amendment: on constant curves all three per-seed series of §4.5 are constant, so both Retention forms are
inadmissible and `NO_ADMISSIBLE_RETENTION` follows deterministically --- F0 would self-destruct after the
first development seed, not merely produce an uninteresting $T$. A read-only search of the corpus (frozen and
live) then established the part that matters for how the fix must be scoped: **A87 §75.1 defines
$W_{\text{pre}}$ as "the learner state with no overrides", and A91 §79.3 assigns it to a pair's reference arm
at episode $0$** --- so the fixed point is *mandated* by frozen text for a pair's arm, not merely omitted by
F0. The corpus contains no initializer, no address set, no magnitude, no mask and no statement about
$\sigma$-dependence; the only concrete non-reference $W_0$ objects are A87 §75.2's canaries. Rev 4 therefore
scopes the fix rather than editing a closed amendment --- A91 §79.3 governs a *pair's* arms, F0 §3 governs
what the $S_2$ *stage* acquires --- and proposes $I_{\text{baseline}} = W_{\text{pre}} +
\Delta W^{\text{cal}}_{D_Q}$, with the derivation that the $D_Q$ canary is the only family member ordinary
training can repair (A91 §79.4 makes the sweep write $Q_D^{L}$ only, while the $X$ and $P$ canaries write
`CONTROLLER` and `PROCESS` and would leave a curve flat *at the defective level*). That proposal is
`[PROPOSED]` in rev 4 §3 and needs the reviewer.

What is *not* affected, stated so the finding is not overread: the matrix is constant across seeds and
episodes, so every per-run curve statistic reduces to a property of the **scene set**. $f_N$'s quantity is
exactly that --- how far a prefix's scene-mean sits from the full bank's, in cross-scene spread units --- so it
keeps its meaning, with the seed and episode maxima collapsing onto one value each rather than varying.
No value of it is computed anywhere in this construction: §1 of the freeze forbids reading $f_N$ (or any
selector) from $\mathcal B_{\text{bench}}$ material, and the fixtures that exercise the harness are not an
exception to that.

### CF-3 --- a withdrawn term still lists its scale in §4.3

§4.3 withdraws the raw $\tau$ term ("**The raw $\tau$ term is withdrawn, and with it a dimensional error.**")
and three bullets later the scales bullet still reads "one per term: $K$ episodes for $\tau$ ..., $T^{*}$ for
RMST ..., and $1$ for DeficitAUC". The surviving metric $\delta_i(G)$ is explicit and unambiguous, so nothing
in the implementation turns on it; it is recorded as a **text** defect for the next revision of the frozen
document, not as a blocker.

### CF-4 --- the refinement predicate is imported from the instrument, not restated

Deriving $C_r^{A,\sigma,e}(c)$ needs A89 §77.4's $S_i$ predicate, which the instrument implements as
`unaffected._slice` and does not export. The acquisition imports that name rather than writing a second
table --- A89 §77.4 freezes "an intersection, never a rival definition", and this codebase already imports a
private collaborator's helper on the same ground (`retention.py` imports `utility._require_*`). The
alternative --- making the predicate public --- changes a **closed** instrument, which F0 §9's invalidation
rule prices at re-closing the gates; that was not done unilaterally. If the reviewer prefers a public export,
it is a one-line change plus a re-closure, and it should be decided before `run_dev_lock.py` is written.

### CF-5 --- the artifact surface of §7 has to carry $1.7 \times 10^7$ pairs

§7 declares `experiments/v03r/dev_baseline.json`. The material of §2 above is $1.69 \times 10^7$
(site, scene) pairs for the development envelope, plus $1.3 \times 10^6$ matrix levels; as JSON that is of
order $10^2$ MB, which is a **surface** question rather than a design one: either the artifact is allowed to
be that size, or the recorded material moves to a compact companion artifact with its own digest, or the
sufficiency requirement is narrowed. Since every one of those is a change to §7's declared surface, it is
raised here rather than settled by `run_dev_baseline.py`. One measured input to the ruling: a $(\sigma, e)$
unit costs $0.486$ s at the healthy state and the envelope holds $1312$ of them, so the development
acquisition is $\approx 11$ min of the *same* work the benchmark of §8 must time.

## 4. The approved initializer's gate, and its verdict

$I_{D_Q} = W^{\varnothing} + \Delta W^{\text{cal}}_{D_Q}$ was approved as the $F_0$ choice and implemented in
`src/rfl_rebuild/b2/initializer.py`; its pre-specified gate ran on the frozen workload (all $32$
$\mathcal B^{\text{op}}_{\text{dev}}$ keys, `ACQUISITION_CAP = 40`, the balanced master bank) and returned

$$\boxed{\texttt{experiments/v03r/f0\_initializer\_gate.json}:\ \textbf{INADMISSIBLE}}$$

| proposition | verdict | measurement |
|---|---|---|
| (a) canary present at $e = 0$ | **true** | exactly one override, at A87 §75.2's address, value $-0.14$ |
| (a$'$) left the fixed point | **false** | no episode changed $Q_D^{L}$ at all: 32 constant override traces |
| (b1) curve moves | **false** | every key's bank curve is constant in $e$ |
| (b2) curves separate | **false** | all $32$ curves are the *same* constant curve |
| (c) repaired within the cap | **false** | 0 repairs |
| diagnostic (non-deciding) | --- | the canary address was written by **0 of 1280** training episodes |

**Two mechanisms, both structural, neither about the run's luck.** `scripts/f0_initializer_diagnostic.py`
re-derives them:

* **the defect is off the training stream's support.** The stream writes $1330$ distinct $Q$ addresses over
  $1312$ episodes, and $99$ of those episodes do write the canary's *state* --- but the canary's **address**
  is the conjunction $(\kappa = 0 \land \phi = 0 \land \zeta = 1 \land a^{\text{cmd}} = 3)$ at the entry
  context, and that conjunction never occurs. The $27$ episodes in the canary's own cell
  $(\kappa, \phi, \zeta) = (0, 0, 1)$ would need the exploration coin to pick $a = 3$ at that step --- and
  the greedy action can never be $3$ there, because the canary is what lowered its value. An A87 canary is a
  **fixed-scene measurement fixture**: A88's screening guarantees reachability by choosing the witness scene,
  and the ordinary training stream makes no such promise;
* **repair needs 54 visits, not one.** The store canonicalises an override only on **bit-exact** equality with
  the reference, and the sweep is $v \leftarrow v + \alpha\,(Q^{*} - v)$. At the frozen $\alpha = 1/2$ that is
  a geometric contraction, so $-0.14$ reaches $0.8799999999999999$ only after **54** visits --- measured, and
  pinned as a test. Even the expected $0.9$ visits per key ($27/32$ of episodes in the cell, times a $\sim
  1/40$ exploration chance at that step) would leave the value at $0.37$, still an override.

$$\boxed{\text{the failure is a property of the \emph{form} (one frozen address, exploration-only
reachability, } \alpha = 1/2 \text{, bit-exact canonicalisation) --- not of the } D_Q \text{ choice}}$$

**What was not done, because the frozen text forbids it.** No cap was enlarged, no other corruption was
substituted, the acquisition path was **not** switched to the failed initializer (it still starts healthy and
is still marked provisional), and no selector was read from benchmark material. The gate artifact is
committed as the evidence, and the options belong to the reviewer: an initializer class whose defect lies on
the *training stream's* support (the `08-V03R.md` §2.1 corruption-*mask* form, which no frozen source
concretises), a stage-level redefinition of the training stream, or a repair criterion that is not bit-exact
canonicalisation --- each of which is a design change, not a construction fix.

## 5. What remains in construction

| object | state |
|---|---|
| `evalorder.py`, `acquisition.py` | **landed**, gated; the acquisition still starts healthy and is a **provisional implementation**: the approved $I_{D_Q}$ **failed its gate** (§4 above), so the path is not switched to it |
| `numerics.py` (CF-1's authoritative $\mathrm{sd}$), `initializer.py` + `scripts/f0_initializer_gate.py` + `scripts/f0_initializer_diagnostic.py`, their tests | **landed**; the gate's verdict is INADMISSIBLE and is with the reviewer |
| `experiments/v03r/smoke_seeds.txt`, `dev_seeds.txt` | **landed** (transcription of §1's declared sets; LF, element by element) |
| `scripts/run_smoke.py` (with `--plan`, the frozen $\mathcal G_{\text{smoke}}$ and the smoke-report field set of §9) | not written; `--plan` and the gate orchestration are unblocked, the real acquisition execution waits on CF-2 |
| `scripts/run_dev_baseline.py` | not written; blocked on CF-2 and CF-5 |
| `scripts/run_dev_lock.py` | not written; blocked on CF-1's authoritative $SE$ path (implemented in this line's next increment) and CF-2 |
| `experiments/v03r/evaluate_smoke_gate.py` | not written; unblocked |
| rev 3 `scripts/f0_manifest.py` + `f0_manifest_selfcheck.py` | not written; the rev-4 contract makes the manifest instrument/config/schema-only, which is unblocked, but its schema is declared final only after CF-2 |
| the deterministic non-scientific benchmark of §8 ($\mathcal B^{\text{op}}_{\text{smoke}}$, $\mathcal B^{\text{op}}_{\text{dev}}$) | not written; blocked on CF-2 (its workload is the initializer's workload) |
| $d_{(P, \mathrm{RMST})} = 1.5$'s independent rationale | **NOT RATIFIED** by the rev-4 review (checklist item 14); an $F_0$ VALID blocker, and a reviewer judgement rather than a harness blocker |

**Boundaries, restated because this document is close to them.** No smoke has been run; the official smoke on
$\mathcal S_{\text{smoke}}$ waits for $F_0 = \texttt{VALID}$. No seed of $\mathcal S_{\text{smoke}}$ or
$\mathcal S_{\text{dev}}$ has been drawn: the fixtures and the probe use $\mathcal B_{\text{bench}}$ keys and
the healthy state. $N_{\text{train}}$ remains `NONEXISTENT/OPEN`; no confirmatory seed exists; `V0.4R` is
untouched.

## 6. Handoff audit: initializer gate implementation corrections (2026-09-26)

Two predicates in `b2/initializer.py` did not implement the already-approved five-part
gate. These are implementation corrections, not changes to the initializer, workload,
thresholds or scientific protocol:

* (a') compared only whether the canary override existed. It could not see a Q-value
  change while the override remained present. The gate now records independent,
  immutable snapshots of the complete sparse Q store at each episode boundary and
  compares adjacent snapshots. `moved_at` uses those same snapshots.
* (c) required every post-entry presence flag to be false, effectively requiring repair
  in the first episode. It now accepts a repair at any episode through the cap, as the
  existential proposition specifies. `repaired_at` remains the first such episode.

Regression coverage includes partial Q-value recovery, writes elsewhere in the Q store,
snapshot independence, repair at episodes 1, 2 and 40, and repair followed by recurrence.
Restoring either old predicate in an isolated process makes its regression fail; no
source file is mutated by that additional check.

The frozen operational workload was rerun after the corrections. The new artifact is
`experiments/v03r/handoff_20260926_initializer_gate.json`; the original artifact is
preserved. Every report field except runtime is identical: **INADMISSIBLE**, (a) true,
(a'), (b1), (b2), (c) false, and **0/1280** episodes writing the canary address. Thus the
implementation defects were real but do not explain away this workload's failure.

The arithmetic diagnostic (`handoff_20260926_cap_diagnostic.json`) also separates
finite-sample non-visitation from the cap problem. The canary is at `t=0`, visited at
most once per episode because kernel time strictly increases. Under the fixed-target
recurrence, exact canonicalisation takes **54** hits at alpha=1/2. Even 40 consecutive
hits leave a residual of approximately 9.28e-13. This is a constraint on this canary,
update rule and exact-repair criterion, not proof that the address is unreachable or
that all possible Q defects have the same problem.

Validation: **774 passed, 1 skipped** (775 collected); A91 mutation self-check **6/6**;
B2 view mutation self-check **45/45**; both self-checks restored the source tree;
specification reference audit passed. The mutation self-checks must run serially:
their harness temporarily edits shared source files. The final suite and operational
rerun were started only after those self-checks finished. Windows runs used
`PYTHONUTF8=1`, and self-check output paths were kept inside the checkout because the
existing harness assumes that layout.

**Status remains F0 NOT VALID.** The failed initializer/cap/repair-criterion combination
needs a separately recorded design decision. The 1.5-episode Process RMST criterion
also remains NOT RATIFIED. No official smoke5, dev32 or confirmatory collection was
started, and no alternative initializer or enlarged budget was tried.

## 7. Follow-up: C1 construction passes, recovery observability fails (2026-09-26)

After the audit above, a separately declared alternative was implemented and tested;
the preceding paragraph describes the earlier handoff stage. See
`22-F0-INITIALIZER-CANDIDATE.md` for its predeclared design and
`23-F0-RECOVERY-OBSERVABILITY.md` for the results and disposition.

The unchanged-budget, fresh-key construction ran 32 by 40 episodes. All five
candidate construction predicates passed, with 14 runs recovering behaviour and
zero exact Q-override removals. It remains an isolated candidate, not the production
initializer. Full regression: 779 passed, 1 skipped.

The stronger seedless negative control rejects both the old and candidate initial
states as baselines for the current recovery endpoint: **even no learning yields
recovery time zero** on every registered bank size and on the full U2 support.
Neither construction pass nor more evaluation scenes resolves that scale mismatch.
F0 remains NOT VALID; no scientific seed was collected. The RMST threshold label
in the handoff paragraph should read **persistent regime P**, not the Process
architecture; those are different uses of the letter P.

## 8. C2/C3 construction and CF-1 integration (2026-09-26)

See `24-F0-ZERO-BASELINE-CANDIDATE.md`, `25-F0-TEMPORAL-BASELINE-CANDIDATE.md` and
`26-F0-BASELINE-CONSTRUCTION-RESULTS.md` for the frozen candidate rules and results.

The full-zero candidate C2 was observable but failed its fixed 6912-episode budget:
0 of 32 operational runs recovered, with all 221184 episodes retained. The time-layer
candidate C3 kept the existing endpoint, started below its threshold, and passed all
construction predicates: 32 of 32 operational runs recovered between episodes 27 and
372 and remained recovered through their 576-episode runs. No cap was enlarged after
inspection, no key was replaced, and these are not scientific effect estimates.

The acquisition artifact's authoritative standard-error API now consumes its actual
slice values through the rev-4 two-pass implementation. Its statistic triples are
derived caches only. This completes the CF-1 numerical wiring correction; broader
F0 acquisition/serialization/lock construction is still incomplete.

Full regression after all code changes: **790 passed, 1 skipped**. Source/data hash
checks and exact reconstruction of all 239680 C2/C3 curve points passed. C3 is an
evidenced amendment candidate; the production initializer is not silently changed.
F0 remains NOT VALID and no formal smoke/dev/confirmatory seed has been collected.

## 9. Master acquisition and shard integration (2026-09-26)

See `27-F0-ACQUISITION-INTEGRATION.md` for the predeclared engineering profile and
`28-F0-ACQUISITION-RESULTS.md` for its evidence. C3's fixed layer-1 initializer is
now explicitly injectable into the master acquisition, with a fresh full learner
per seed and all eligibility/domain information built from complete U2 traces.
The old initializer and healthy generic fixture default were not silently replaced.

CF-5 streaming serialization, complete-shard validation and read-only lock preflight
are implemented. The cap-2 integration rehearsal used operational keys 940001 and
940002: 6 records, 81032 incidence pairs, all saved means bit-equal to independent
A91 replay. The 71-file pre-run archive and all data digests passed verification.
This is not a full-cap runtime benchmark or a scientific baseline acquisition.

The complete A91 convergence definition was found in `12` §79.7 and implemented,
including zero/undefined windows and original-sample nearest-rank censoring.
The short main/F0 prose now points to and clarifies that existing rule. No C3
operational curve was used to select a horizon. The other selectors, combined
design/threshold lock, stage manifest/smoke commands and independent P-regime RMST
effect-threshold rationale remain open. F0 remains NOT VALID.

Final full regression: **837 passed, 1 existing skip**. The integration result and
the lack of formal-stage authorization are separate facts; no formal seed or
treatment arm was acquired. All changes and evidence are local and unpushed.

## 10. Selector implementation and GitHub publication preparation (2026-09-27)

`29-F0-DESIGN-SELECTORS.md` supersedes the preceding implementation checklist:
f_N/f_G/f_C/f_R and the combined design/threshold lock consumer are now implemented.
Synthetic tests cover worst-case aggregation, bank dependencies, exact grouped
incidence multiplicities, tied/undefined correlations, threshold identities,
provenance refusal and atomic publication. The main protocol now states average
ranks for Spearman ties explicitly. Full regression: **863 passed, 1 existing skip**.

The current branch is f0-rev3. The user explicitly requested publication, so the
previously local work and retained evidence are included in the publication set.
The README no longer claims implementation has not begun. Frozen candidate archives
remain the replay authority for their original runs. Stage manifest/smoke/baseline
commands and the independent RMST threshold rationale remain open; no F0 approval,
scientific design, formal seed collection or treatment arm is implied by publication.
