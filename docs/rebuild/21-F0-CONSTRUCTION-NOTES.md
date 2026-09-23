# 21 --- $F_0$ construction notes (live, not a freeze)

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

## 4. What remains in construction

| object | state |
|---|---|
| `evalorder.py`, `acquisition.py` | **landed**, gated |
| `scripts/run_smoke.py` (with `--plan`, the frozen $\mathcal G_{\text{smoke}}$ and the smoke-report field set of §9) | not written |
| `scripts/run_dev_baseline.py` | not written; blocked in part on CF-5 |
| `scripts/run_dev_lock.py` | not written; blocked in part on CF-1 and CF-4 |
| `experiments/v03r/evaluate_smoke_gate.py` | not written |
| rev 3 `scripts/f0_manifest.py` + `f0_manifest_selfcheck.py` | not written; the manifest contract is §7's, including the ordering digest and the prefix summaries this note records |
| the deterministic non-scientific benchmark of §8 ($\mathcal B^{\text{op}}_{\text{smoke}}$, $\mathcal B^{\text{op}}_{\text{dev}}$) | not written; it must represent `acquire_master_baseline`, and §8 requires the bound to be re-derived from this line's own measurements |
| `experiments/v03r/smoke_seeds.txt`, `dev_seeds.txt` | not written on this line (rev 2's live on the retired line) |
| $d_{(P, \mathrm{RMST})} = 1.5$'s independent rationale | open, as the freeze's checklist item 14 records; a reviewer judgement, not a harness blocker |

**Boundaries, restated because this document is close to them.** No smoke has been run; the official smoke on
$\mathcal S_{\text{smoke}}$ waits for $F_0 = \texttt{VALID}$. No seed of $\mathcal S_{\text{smoke}}$ or
$\mathcal S_{\text{dev}}$ has been drawn: the fixtures and the probe use $\mathcal B_{\text{bench}}$ keys and
the healthy state. $N_{\text{train}}$ remains `NONEXISTENT/OPEN`; no confirmatory seed exists; `V0.4R` is
untouched.
