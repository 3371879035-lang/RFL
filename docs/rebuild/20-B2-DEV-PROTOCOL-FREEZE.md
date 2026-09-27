# 20 — F0: development protocol freeze (revision 5, C3 and failure-only amendment)

**Status: protocol revision implemented; F0 execution authorization remains NOT VALID
until a source-bound review and fresh complete runtime evidence are committed.**

The current profile is C3 at layer 1, cap 576, the typed quantitative RMST margin,
and failure-triggered diagnostic correction. `31-FAILURE-ONLY-AND-RMST-AMENDMENT.md`
is the normative change record. Unchanged selector rules below retain their original
numeric conventions. Historical revisions and failed reviews are preserved separately
in `experiments/v03r/amendment_20260927/before-20-B2-DEV-PROTOCOL-FREEZE.md`.
They are evidence of the design history, not competing current declarations.

A91's training transition and episode axis remain frozen. Scientific smoke, dev,
confirmatory and V0.4R stages require their existing separate authorizations.
Implementing this revision does not approve a manifest or select an F1 design.

## 1. Seed sets and pre-data constants

Scientific smoke seeds are the ordered tuple (0,1,2,3,4); development seeds are
(1000,1001,1002,1003,1004,1005,1006,1007,1008,1009,1010,1011,1012,1013,1014,1015,
1016,1017,1018,1019,1020,1021,1022,1023,1024,1025,1026,1027,1028,1029,1030,1031).
The exact files are `experiments/v03r/smoke_seeds.txt` and
`experiments/v03r/dev_seeds.txt`. A seed identifies a complete A91 training run;
it is the statistical unit, not an evaluation scene or an episode.

| Pre-data constant | Value | Basis |
|---|---|---|
| alpha | 1/2 | Existing tabular update convention |
| exploration epsilon | 1/10, exact rational | Existing integer keyed exploration convention |
| epsilon_s | 0.001 level per episode | Existing flat-window convention |
| epsilon_f | 0.1 | Existing reversal-free K=3 window convention |
| ACQUISITION_CAP | **576** | C3's 48×H engineering budget, H=12; not a power or convergence guarantee |
| initializer | **c3-temporal-layer-1-v1** | Exact rule in section 3 and document 31 |

These values are fixed before scientific seeds. No operational curve selects them.
The initializer is independent of seed and arm. Confirmatory seeds must be disjoint
from smoke, development, and every previously used operational population.

The completed prior benchmark used 950001–950037 at its original source commit.
The fresh rev-5 benchmark uses **970001–970005** for its five-run smoke shape and
**970006–970037** for its thirty-two-run development shape. It may measure time and
check construction validity; it may not enter scientific artifacts or f_T/f_N/f_G/
f_C/f_R, choose thresholds, rank treatments or estimate scientific effects. Earlier
900001–900032, C1/C2/C3, integration and test keys remain operational exclusions.
There is no permission to overwrite a spent acquisition or reuse its reservation.

## 2. Candidate universes, exhaustively named

$$\boxed{\mathcal C_C = \{\texttt{eligible\_all},\ \texttt{eligible\_phase\_even},\
\texttt{eligible\_phase\_odd},\ \texttt{eligible\_cause\_rank\_lower},\ \texttt{eligible\_error\_absent},\
\texttt{eligible\_base\_option\_nonzero}\}}$$

the six calibrated refinements of A89 (**APPROVED** as membership).

$$\boxed{\mathcal C_R = \{\texttt{RetentionAtH},\ \texttt{LateWindowRetention}\}}$$

the two registered forms (**APPROVED** as membership); `RetentionFraction` is excluded by role, being a
`CONDITIONAL_DIAGNOSTIC`. A form is not a configured endpoint: `RetentionAtH.value` requires `H` and
`LateWindowRetention.value` requires `H1 < H2`, and neither has a default, so §4.5 freezes how $f_R$
derives those parameters and §5 registers the *configured* endpoint.

$$\boxed{\mathcal C_{N_{\text{eval}}} = \{100,\ 256,\ 512,\ 1024\}}$$

$100$ is restored to candidate status because `11-ENVIRONMENT` declares it the frozen default; a
development selector may reject it on evidence, but it may not remove it from candidacy in advance.
$N_{\max} = 1024 = \max \mathcal C_{N_{\text{eval}}}$ is the sample size the master envelope acquires.

$$\boxed{\mathcal C_{\mathcal G} = \{G_1,\ G_2,\ G_3\}}$$

**three $T$-parameterised grid functions, not fixed tuples.** Revision 1 froze $(0,5,15,40)$, which is
only legal when $T^{*} = 40$; A84 §71.6 freezes $episodes[0] = 0$, $episodes[-1] = T_{\max}$, so a fixed
tuple would either contradict the frozen contract or silently define $T$ by the grid. What is frozen here
is the *functions*, each of which is well-defined for every admissible $T$:

$$s_0 \ldots s_{11} = 0, 1, 2, 5, 10, 20, 50, 100, 150, 200, 300, 500, \qquad
\boxed{s_j = 2\,s_{j-1} \ \text{ for } j \ge 12}$$

`05` §6.2 prints that list with a trailing "$\ldots$" and never says what follows $500$, so revision 3's
earlier draft verified $T = 1200$ against a continuation rule that existed only inside the checking script.
The rule is frozen here instead: **the tail doubles**, which continues the skeleton's own growth (steps of
$50, 50, 100, 200$) and keeps the late phase coarse. Write
$\mathcal G^{\text{skeleton}}(T) = \{s_j : s_j < T\} \cup \{T\}$ for the skeleton truncated and completed at
$T$, and $\texttt{interior}(T)$ for its elements strictly between $0$ and $T$. Then, exactly:

| template | rule (exact) |
|---|---|
| $G_{\text{coarse}}(T) = G_1(T)$ | $(0) \,\|\, \texttt{interior}(T)[0::2] \,\|\, (T)$ -- the **even-indexed** interior points (0-based), so the first interior point is kept |
| $G_{\text{medium}}(T) = G_2(T)$ | $(0) \,\|\, \texttt{interior}(T) \,\|\, (T)$ |
| $G_{\text{fine}}(T) = G_3(T)$ | $(0) \,\|\, \texttt{interior}(T) \,\|\, \bigl\{\lfloor (a+b)/2 \rfloor : a < b \text{ adjacent in } (0) \,\|\, \texttt{interior}(T) \,\|\, (T),\ b - a > 1\bigr\} \,\|\, (T)$, sorted and deduplicated |

so the three ambiguities the construction review named are decided here rather than by an implementer:
**which** interior points `coarse` keeps (even indices, the first kept), **how** `fine`'s midpoint rounds
(floor division, and only for a gap wider than one episode), and **what** lies beyond $500$ (doubling). The
aliases $G_1 = G_{\text{coarse}}$, $G_2 = G_{\text{medium}}$, $G_3 = G_{\text{fine}}$ are frozen with them.

The family is a set of **dense-early grid transformations** of `05` §6.2's frozen skeleton ---
"coarsening" would be the wrong word for $G_{\text{fine}}$, which adds midpoints and is therefore a
refinement of the skeleton while all three remain coarse relative to the full episode axis. Revision 2 froze
$(0,5,15,40)$, which is legal only when $T^{*} = 40$; the follow-up used $T/2, T/3, T/4$ spacing, which the
review rejected for the opposite reason: at $T = 500$ it puts checkpoints at $125, 250, 375$ --- sparse
exactly where `05` §6.2 requires density, because recovery is fast when it happens. Every candidate
truncates at $T$ and contains both ends.

Each candidate is admissible only for a $T$ that makes it well-defined, and the frozen contract each
template must satisfy is

$$\boxed{G_j(T)_0 = 0, \qquad G_j(T)_{-1} = T, \qquad \text{strictly increasing}, \qquad
\text{integer}, \qquad \left|G_j(T)\right| \ge K = 3}$$

The $K = 3$ floor is not a taste: $05$'s recovery contract is
$\tau = \inf\{t : V_{t'} \ge 0.95\,V_{\text{pre}}\ \forall t' \in [t, t+K-1]\}$ with $K = 3$, so a grid
with fewer than three checkpoints cannot represent the maintained-recovery time at all. $G_1$ is admitted
exactly because $K \ge 3$ allows three; $G_3$ is the finest. The templates' minima differ, and each is
declared rather than assumed:

$$\boxed{\text{all three templates are well-defined for } T \ge 2}$$

Revision 3's earlier draft carried a "$G_3$ needs $T \ge 4$" bound and a "$G_3(3) = (0,1,2,3,3)$" example
from the superseded $T/4$-spacing rule. Under the frozen fine rule neither holds: at $T = 3$ the skeleton is
$(0,1,2,3)$, every adjacent gap is already $1$, no midpoint is added, and
$G_{\text{fine}}(3) = (0,1,2,3)$ is strictly increasing and legal. Since
$T^{*} = \lceil 1.2\,x_{(29)} \rceil \ge 2$ for any non-empty convergence sample, all three are well-defined
whenever the lock exists at all --- and the fail-closed outcome stays declared anyway, because "it cannot
happen" is not a rule:

$$\boxed{\text{no template satisfies the contract at } T^{*} \;\Longrightarrow\;
f_G \to \texttt{NO\_ADMISSIBLE\_GRID}}$$

## 3. The master acquisition envelope

Revision 1 ordered the evaluation sample by `(seed, episode)` and was wrong twice over: it made a
development *seed* the unit of an evaluation sample, and it made a future *episode* the unit of a
measurement whose frozen definition is a scene ensemble. A85 §73.1 fixes

$$V_{\text{pre}} = \mathcal E\bigl(Q^{*};\ N_{\text{eval}},\ \mathcal S_{\text{eval}}\bigr)$$

with `11-ENVIRONMENT` §12.3 requiring the pre and post checkpoints to use the **same evaluation scenes**,
and A86 §74.5 fixes the surviving unified unit as

$$U_2 = \mathcal K \times \mathcal T_{\text{SemanticTape}} \times \mathcal Z, \qquad \left|U_2\right| = 5760$$

so the master envelope is an ordered **evaluation-scene** sample, and $N_{\text{eval}}$ is a prefix length
of it:

$$\boxed{\mathcal S^{\text{master}}_{\text{eval}} = \left(u_1, u_2, \ldots, u_{N_{\max}}\right),
\qquad u_i \in U_2, \qquad N_{\max} = 1024}$$

$$\boxed{\mathcal S_{\text{eval}}(N) = \left(u_1, \ldots, u_N\right), \qquad
N \in \mathcal C_{N_{\text{eval}}}}$$

**The order is balanced, not lexicographic.** Revision 2 took the first $N_{\max}$ elements of the frozen
$U_2$ enumeration under A88 §76.2's lexicographic order, and the review rejected it: with $\kappa$ as the
leading key, **all** of the first $1024$ scenes have $\kappa = 0$ (the first $240$ also have $\phi = 0$), so
a candidate about *sample size* would have been a candidate about *stratum composition*, and $f_N$'s
stability would have measured the ordering rather than the sampling. Canonical order is for canonical
selection; it is not an evaluation design. The frozen order is built to cover the strata at every prefix:

* the $96$ **cells** of $(\kappa, \phi, \texttt{error\_flag}, z_{\text{base}})$ are visited round-robin, so
  the first $96$ units already contain every cell;
* the cause rank advances by a stride coprime with $60$ on each pass, so consecutive cells rotate through
  the whole cause support;
* the order is a bijection $n \mapsto u_{n+1}$ on $n = 0, \ldots, 5759$, generated from
  $n = 96q + r$ with $0 \le r < 96$: $u_{n+1}$ is the $r$-th cell (0-based) in ascending
  $(\kappa, \phi, \texttt{error\_flag}, z_{\text{base}})$ order carrying
  $\texttt{cause\_rank} = (7q + 37r) \bmod 60$ --- written explicitly so that no reader has to decide
  whether $r$ or the prose's "first unit" is 0-based.

$$\boxed{\forall N \in \mathcal C_{N_{\text{eval}}}:\ \text{prefix}(N) \text{ covers every } \kappa, \
\phi, \texttt{error\_flag}, z_{\text{base}} \text{ and all } 60 \text{ cause ranks}}$$

That is **verified rather than asserted**: the construction is a permutation of all $5760$ units, and the
prefixes at $100$, $256$, $512$ and $1024$ each cover $2/2$ $\kappa$, $6/6$ $\phi$, $2/2$ error flags,
$4/4$ options and $60/60$ cause ranks. Two consequences are deliberate:

* the evaluation sample is **seed-free**. Every scene in it is a deterministic element of a frozen finite
  domain, so "the first $N$" has one meaning that no seed and no data can move;
* $\mathcal C_{N_{\text{eval}}}$'s members are prefixes of that one order, and $N_{\max} = 1024 \le 5760$,
  so every candidate is available without enlarging the domain. A candidate above $\left|U_2\right|$
  would be `NO_ADMISSIBLE_N_EVAL`, not a silently extrapolated scene.

**One acquisition, and it is grid-free.** The development stage acquires

$$\boxed{D^{\text{master}}_{\text{dev,baseline}}\ \text{is the only acquisition before } F_1}$$

* the envelope stores the **master scene matrix**, not a mean and not a checkpoint tuple:

$$\boxed{\texttt{BaselineAcquisitionPlan} \;\longrightarrow\; \texttt{acquire\_master\_baseline}
\;\longrightarrow\; \left\{V_{\sigma,e,u}\right\}_{\sigma \in \mathcal S_{\text{dev}},\
e \le \texttt{ACQUISITION\_CAP},\ u \in \mathcal S_{\text{eval}}(N_{\max})}}$$

  one level per (development seed, episode, evaluation scene) --- A87 §75.3's reward-mode-A return of the
  run's learner at that scene --- plus the derived mean curve $V_\sigma(e) =
  \mathrm{mean}_u V_{\sigma,e,u}$ as a **view** of the matrix rather than the stored object. The matrix is
  what $f_N$ needs (per-scene values) and what $f_T$, $f_G$ and $f_R$ summarise (per-seed curves), and a
  mean-only acquisition would have made $f_N$'s cross-scene scale uncomputable.

  **The matrix is necessary and not sufficient.** $f_C$'s metric of §4.4 needs
  $C_r^{A,\sigma,e}(c) = E_{W_{\sigma,e}}(c) \cap S_r$, and A89's eligibility ---
  $\neg Consult_{W_{\sigma,e}}(u,c) \wedge H_{\text{pre}}(u)$ --- is a function of the run's own learner
  state, so it cannot be reconstructed from the levels alone; neither can $X$'s credited domain, which A89
  derives from the same episodes. The acquisition artifact is therefore

$$\boxed{D^{\text{master}}_{\text{dev,baseline}} = \left\{V_{\sigma,e,u}\right\} \cup
\text{sufficient A89 pre-update eligibility material}}$$

  where "sufficient" is frozen to mean: enough to recover $SE_{A,c,\sigma,e}(r)$ **mechanically at $F_1$**,
  without re-running a scientific stream and without inventing a static eligibility. **Rev 4 (CF-1) fixes
  what the artifact stores, and demotes what rev 3 called the minimum.** The recoverable $SE$ is §4.0's, and
  §4.0 now makes the set's own values the authoritative object, so the material that has to be stored is the
  **values together with the incidence** that says which values fall in $C_r^{A,\sigma,e}(c)$:

$$\boxed{D^{\text{master}}_{\text{dev,baseline}} \;\supseteq\; \left\{V_{\sigma,e,u}\right\} \cup
\left\{\textit{Consult}_{W_{\sigma,e}}(u, c)\right\} \cup \left\{H_{\text{pre}}(u)\right\} \cup
\left\{\mathcal D^{\text{credit}}_A(W_{\sigma,e})\right\}_{A}}$$

  The per-$(A, \sigma, e, c, r)$ statistics --- $\lvert C_r^{A,\sigma,e}(c)\rvert$,
  $\sum_{u \in C} V_{\sigma,e,u}$ and $\sum_{u \in C} V_{\sigma,e,u}^2$ --- are **derived from that material
  and are admissible as a cache and as a cross-check**, not as the authoritative numerical object: computed
  from the triple they carry the `binary64` cancellation §4.0 now forbids relying on. Rev 3's sentence that
  they "are the minimum" is withdrawn, and the withdrawal is measured rather than asserted: on the historical cap-40
  envelope $c$ ranges over A89 §77.4's production credited domains, $13824 + 229 + 4$ units, so the finished
  statistics are $1.1 \times 10^8$ triples (historical cap-40 size estimate) while the incidence that generates them is $1.7 \times 10^7$ pairs
  --- the "minimum" is $6.5\times$ the "alternative", and the derivation is the smaller object. A levels-only
  artifact is **not** sufficient: it would leave `run_dev_lock.py` to choose between re-running the
  development stream, inventing an eligibility, or failing.
  `acquire_master_baseline` **reuses A91's frozen machinery** --- the keyed episode generator
  `ExogenousEpisode`, the training behaviour policy, and `sweep_edits`' chronological $Q$ sweep --- while
  doing its own evaluation gathering, because `train_curve` returns the evaluation-sample *mean* and takes a
  `FutureTrainingProtocol` that does not exist before $F_1$:

$$\boxed{\texttt{BaselineAcquisitionPlan} \;\not\to\; \texttt{train\_curve}}$$

  Revision 3's draft wrote that arrow, which is a type error: the pre-$F_1$ plan deliberately has no
  $T^{*}$, no final grid and no $V_{\text{pre}}^{*}$, so it cannot instantiate the production protocol;
* that matrix is what makes $\mathcal C_{\mathcal G}$'s $T$-parameterised templates usable at $F_1$:
  **grids are projections of curves**, and a grid chosen before $T$ existed could not be;
* the cap is the pre-data envelope budget of §3, and it is enforced fail-closed rather than extended:

* $S_2$ runs **baseline and static material only**; the treatment arms of that seed set are not run before
  $F_1$ (A90 §78.5), and "the grid looks thin, add checkpoints" is adaptive acquisition and is unavailable.
  The treatment arms are a later, separately authorised stage, so the envelope's acquisition cost is a
  baseline cost, which is what §8's bound must be measured against.

**The episode axis is frozen --- by A91, not by this document.** Revisions 1 and 2 read the future curve off
`view.fields["future_rewards"]` and indexed it by `range(len(levels))`, the *step* index of one kernel
rollout, and could not say what a training episode was. **A91 (FROZEN at `3f02724`; instrument and
integration CLOSED at `b35f649`) settles it**, and this document consumes the frozen instrument instead of
re-specifying it:

* a training episode is $W_e \to$ rollout under $\Xi_e \to$ the chronological update $\to W_{e+1}$, and the
  curve's index is the episode $e$ (`b2.training.train_curve`);
* the **pre-data** constants ($\alpha$, $\varepsilon_{\text{explore}}$) and the **$F_1$-locked** quantities
  ($T^{*}$, $\mathcal G^{*}$, $\mathcal S_{\text{eval}}^{*}$, $V_{\text{pre}}^{*}$) arrive through
  `FutureTrainingProtocol`, while the pre-$F_1$ envelope is `BaselineAcquisitionPlan` --- two objects,
  because an acquisition cap is not a locked horizon;
* checkpoint evaluation is greedy and read-only, and both arms consume one protocol object, so the future
  contrast is paired by construction rather than by convention.

$$\boxed{\texttt{ACQUISITION\_CAP} = 576 \quad \texttt{[FIXED rev 5, pre-data]}F_0\text{ constant}}$$

The cap is the envelope's episode budget, not $T^{*}$: $T^{*}=\lceil 1.2\,x_{(29)}\rceil$ is computed *from*
the acquisition at $F_1$. A horizon the envelope cannot reach fails closed rather than extending itself:

**Current initial learner (rev 5).** Every run starts from a fresh C3 learner:
for each reference row at time layer 1 with maximum b and minimum q<b, choose the
smallest action id among its minimum-valued actions and set that entry to b+(b-q).
Other Q entries retain reference values; all non-Q stores stay healthy. The exact
implementation is `src/rfl_rebuild/b2/temporal_initializer.py`. The chosen layer is
fixed; acquisition performs no layer search or reads of construction curves.

This replaces the old calibration-canary initializer. It is a synthetic development
baseline, not a treatment, natural defect distribution, or selected winning method.
Document 25 declares its structural construction and 576-episode budget; document 26
retains its engineering checks and the C1/C2 history. Those checks do not guarantee
that F1 has admissible T, grid or Retention. The same initial learner and cap are
used by the operational benchmark, formal smoke and development acquisition.

Ordinary A91 learning remains active on successful and unsuccessful episodes.
Success flags in this master material are read-only evaluation/knowledge-protection
measurements. No causal reflection is invoked by baseline acquisition. Diagnostic
correction in an online RFL arm has the failure-only boundary of document 31.

## 4. The design-rule family

Every rule is total on its input surface with a fail-closed codomain, and declares its metric, its
admissibility threshold, its ranking rule, its tie-break, its missing-value behaviour and its
exact-equality behaviour.

### 4.0 Numerical conventions binding every rule

* **exact equality meets the threshold**: `value ≤ θ` and `value ≥ θ` are inclusive `float64`
  comparisons; a candidate whose metric equals its threshold is admissible (**APPROVED**);
* **no rounding before a comparison**; rounding is display-only (**APPROVED**);
* **missing values are never imputed**: a rule whose required input is missing returns its fail-closed
  outcome, and computing the metric on a smaller sample is not an option (**APPROVED**);
* **every tie-break is an explicit total order**, so no sort's stability decides anything (**APPROVED**);
* **an undefined ratio is never replaced by a number**: where a metric divides by a spread that can be
  zero, the rule below declares the zero case explicitly and either defines it as a limit or makes the
  candidate **inadmissible**. Revision 1 left `(max − min)/median` and a rank correlation undefined on
  constant series, which the reviewer rejected, and this is the general fix;
* **declared scales and epsilons**: every denominator below is either a frozen constant, a frozen
  quantity, or a spread with an explicit floor; the floor constants are declarations of this document, not
  library defaults;
* **one definition of `sd`, and it is the population form.** Every `sd` in this document --- $f_N$'s
  cross-scene scale, $f_C$'s standard error, the collateral bound's spread family and the Retention
  threshold's per-run spread --- is

$$\boxed{\mathrm{sd}(x_1, \ldots, x_n) = \sqrt{\frac{1}{n}\sum_{j=1}^{n}\left(x_j - \bar x\right)^2},
\qquad \bar x = \frac{1}{n}\sum_j x_j}$$

  i.e. the divisor is $n$, not $n-1$. The choice is frozen here rather than inherited, because Python and
  NumPy disagree by default and the difference moves $m_N$, $m_C$ and both derived $\Delta_{\min}$.

**The authority is the sample, not an expansion of it (rev 4, CF-1).** Rev 3 wrote that "the frozen per-set
sufficient statistics of §3 --- count, sum, sum of squares --- recover this form exactly, which is why they
are the declared minimum", and the construction **falsified that sentence**:
$\sum V^2/n - (\sum V/n)^2$ is a difference of two nearly equal `binary64` numbers, so a set whose values are
equal but not exactly representable comes back with a positive residue instead of $0$ --- measured at
$\mathrm{se}(1,\, 0.7,\, 0.49) = 7.45 \times 10^{-9}$, a set of one value whose population spread is exactly
zero. §4.4's zero cases are **exact comparisons** on this quantity, so a residue decides the branch, and
"the error is small" is not an answer to a rule that reads $SE(\texttt{all}) = 0$. The frozen rule is
therefore

$$\boxed{\text{the authoritative object of } \mathrm{sd} \text{ is the set's own values } x_1, \ldots, x_n
\text{, never an algebraic rearrangement of their summary}}$$

  computed by one deterministic `binary64` algorithm, so that two implementations of the same rule agree bit
  for bit and no tolerance is needed anywhere:

$$\boxed{\bar x = \frac{\text{left-to-right sum}(x_j)}{n}}, \qquad
\boxed{x_1 = \cdots = x_n \;\Longrightarrow\; \mathrm{sd} = 0}$$

$$\boxed{\mathrm{sd} = \sqrt{\frac{1}{n}\,\text{left-to-right sum}\bigl((x_j - \bar x)^2\bigr)}
\quad \text{otherwise}}$$

  and the **iteration order is frozen with the algorithm**, because a `binary64` left-to-right sum is
  order-sensitive:

$$\boxed{x_1, \ldots, x_n \text{ enter the accumulation in ascending \emph{bank index} order of the
balanced master bank}}$$

  §3's incidence already stores bank indices, so this promotes the order the artifact already has into a
  rule; it adds no storage and no acquisition.

  The constancy test reads the values themselves (`x_j == x_1`, in the artifact's own type), it is evaluated
  **first**, and it is what closes the constant case exactly --- which is what makes the zero cases of §4.2,
  §4.4 and §4.5 reachable rather than round-off-dependent. "Left-to-right sum" is the plain accumulation
  `t = 0.0; for v in values: t += v`, named in the text because `sum()` is Neumaier-compensated in CPython
  and is therefore a *different* algorithm. §4.1's mean curve uses that same accumulation order, and the
  acquisition reproduces A91's `_mean_return`, which is why the two agree on the ulp rather than only to
  within one.

  Two consequences are part of the definition. $n = 1$ gives $\mathrm{sd} = 0$ rather than an undefined
  value; and the per-set statistics of §3 are demoted to **derived/cache** material:

$$\boxed{\bigl(\lvert C\rvert,\ \textstyle\sum V,\ \sum V^2\bigr) \text{ is a derived cache};
\qquad \text{no } SE \text{ may be computed from it as the authoritative path}}$$

  This costs the acquisition nothing: §3's material already stores the values $V_{\sigma,e,u}$ **and** the
  incidence that says which values are in the set, so $SE$ is computable from the material under the boxed
  rule, with no new acquisition and no new artifact content. The statistics stay admissible as a cache and as
  a cross-check, and the acquisition's triple-entry helper is a **construction probe**: the authoritative
  $SE$ path --- the one `run_dev_lock.py` must use --- computes $\mathrm{sd}$ from the set's values under the
  boxed rule;
* **one acquisition**: every ranking metric reads $D^{\text{master}}_{\text{dev,baseline}}$ or the frozen
  static artifacts, never an arm.

### 4.1 $f_T$ — the horizon

$$T = \left\lceil\, 1.2\, Q_{0.9}\!\left(T_{\text{conv}}\right) \right\rceil$$

with the finite-sample quantile convention frozen here rather than inherited from a library:

$$\boxed{Q_{0.9}(x) = x_{(\lceil 0.9\,n \rceil)} \quad \text{on the ascending order statistics of } x}$$

i.e. nearest rank; with $n = 32$ this is $x_{(29)}$ (**APPROVED**). **The integerisation is frozen here**
as the ceiling: $1.2\,x_{(29)}$ need not be an integer while $T_{\max}$ is an integer episode index, and
`11-ENVIRONMENT`'s episode indices are integers. **A91 censoring clarification:** an observed
run with no qualifying window is censored, not dropped. Keep the original $n$ and
$r=\lceil0.9n\rceil$; fewer than $r$ uncensored runs gives `NO_ADMISSIBLE_T`, otherwise
take the $r$-th uncensored order statistic, exactly as `12` §79.7 freezes. The earlier
sentence "a missing T_conv makes f_T return NO_ADMISSIBLE_T" was ambiguous about
censoring and must not be read as rejecting any one censored run or recomputing a
rank on a smaller sample. Missing acquisition records remain protocol errors.
Ties at the rank are resolved by taking the
lower order statistic only when the tie spans the rank, so no tie-break rests on a sort's stability.

**The acquisition cap fails here, not at the grid.** The envelope acquired episodes $0 \ldots
\texttt{ACQUISITION\_CAP}$; a horizon the acquisition cannot reach is a *horizon* failure, and reporting it
as a grid failure would disguise "the acquisition was too short" as "no grid suited":

$$\boxed{T^{*} > \texttt{ACQUISITION\_CAP} \;\Longrightarrow\; f_T \to \texttt{NO\_ADMISSIBLE\_T}
\;\Longrightarrow\; \text{new amendment, fresh seeds}}$$

Revision 3's earlier draft put this consequence on $f_G$, which the construction review corrected.

### 4.2 $f_N$ — the evaluation-sample size (Monte-Carlo stability)

Revision 1 measured $N_{\text{eval}}$ with the same across-checkpoint spread as the grid, which answers a
different question: $N_{\text{eval}}$ is about **how many scenes the estimate stands on**, the grid is
about **when it is read**. $f_N$ now measures sampling stability directly, against the largest sample as
the reference:

$$\hat V_{\sigma,N}(e) = \frac{1}{N}\sum_{u \in \mathcal S_{\text{eval}}(N)} V_{\sigma,e,u},
\qquad
\mathrm{sd}_{\sigma,\text{scenes}}(e) = \mathrm{sd}_{u \in \mathcal S_{\text{eval}}(N_{\max})}
V_{\sigma,e,u}$$

$$\boxed{m_N(N) = \max_{\sigma \in \mathcal S_{\text{dev}}}\
\max_{e = 0}^{\texttt{ACQUISITION\_CAP}}\
\frac{\left|\hat V_{\sigma,N}(e) - \hat V_{\sigma,N_{\max}}(e)\right|}
{\max\left(\mathrm{sd}_{\sigma,\text{scenes}}(e),\ \epsilon_N\right)}}$$

with $\epsilon_N = 10^{-9}$ declared and every quantity read from the master matrix of §3. **Two quantifier
domains are frozen here, and revision 4's draft named only one of them.** The episode domain is the
acquisition axis $e = 0, \ldots, \texttt{ACQUISITION\_CAP}$, not $0 \ldots T^{*}$: $f_N$ deliberately does
not depend on $f_T$ in §6's graph, so its domain cannot be a horizon that does not exist when it runs. The
**seed** domain is the same **worst case over $\mathcal S_{\text{dev}}$** that $f_G$ and $f_C$ use, so an
evaluation sample that is unstable for one development seed is not averaged away by the other thirty-one;
the alternatives --- a per-seed-then-mean reading, or pooling seed and scene into one sample --- are
different selectors, and freezing the maximum is what stops `run_dev_lock.py` from choosing among them. The
zero-spread rules of the next bullets apply per $(\sigma, e)$. The scale is the
Monte-Carlo scale of the quantity being estimated, so $m_N$ is measured in units of cross-scene variation
rather than in units of the curve's own drift -- which is what the reviewer's finding asked for, and what
stops a healthy baseline that genuinely changes over time from being read as sample instability.

* **admissibility**: $m_N(N) \le \theta_N$, with $\theta_N = 0.25$ `[FIXED rev 5]` -- a quarter of one
  cross-scene standard deviation is below the resolution at which two candidate prefixes could be
  distinguished by any downstream endpoint;
* **ranking**: the **smallest sufficient sample**, expressed as the total order
  $(N \text{ ascending}, m_N \text{ ascending})$ over the admissible candidates --- $N$ first, because the
  principle is "the smallest sample that is stable", and an $m_N$-first order would systematically prefer
  the larger candidate, which is the opposite. Revision 3's draft wrote the order the other way round while
  describing the same principle, and the construction review caught the contradiction;
* **zero and undefined cases, without an epsilon argument**: where $\mathrm{sd}_{\text{scenes}}(t) = 0$
  the ratio is undefined, and the two cases are decided directly ---

$$\boxed{\mathrm{sd} = 0 \ \land\ \text{numerator} = 0 \;\Rightarrow\; \text{term} = 0} \qquad
\boxed{\mathrm{sd} = 0 \ \land\ \text{numerator} > 0 \;\Rightarrow\; \text{candidate inadmissible}}$$

  so a zero spread never has to be compared against $\epsilon_N$ to decide anything. (Revision 3 derived
  inadmissibility from $\text{numerator}/\epsilon_N \ge 1$, which is false for small positive numerators ---
  a numerator of $10^{-12}$ would have been credited.) $\epsilon_N$ therefore only floors the *denominator*
  in the ordinary case;
* **missing**: a candidate whose curves cannot be computed on the envelope is inadmissible; if none is
  admissible, $f_N \to \texttt{NO\_ADMISSIBLE\_N\_EVAL}$, and then there is no design lock and no
  confirmatory stage.

### 4.3 $f_G$ — the checkpoint grid (temporal resolution)

$f_G$ now asks whether **the grid preserves the frozen endpoints** rather than whether the baseline curve
is flat. For $G \in \mathcal C_{\mathcal G}$, on the baseline curve bank:

**Every term is per seed, and the seeds are combined by a maximum.** $\tau$ and `restricted_time` are
per-seed quantities and DeficitAUC is a per-seed endpoint too (A84 §72: RMST is the *cross-seed*
expectation, so comparing an "RMST on the grid" with an "RMST on the full grid" would compare two
population summaries while pretending to measure one seed's distortion). "full" is the **complete episode
axis** $0, 1, \ldots, T^{*}$ that the acquisition stores, and $G$ is read as the curve restricted to $G$'s
checkpoints. For dev seed $i$:

$$\boxed{\delta_i(G) = \max\Biggl(
\frac{\left|\texttt{restricted\_time}_i(G) - \texttt{restricted\_time}_i(\text{full})\right|}{T^{*}},
\ \left|\mathrm{DeficitAUC}_i(G) - \mathrm{DeficitAUC}_i(\text{full})\right|\Biggr)}$$

**The raw $\tau$ term is withdrawn, and with it a dimensional error.** Revision 3 divided
$\lvert\tau_i(G) - \tau_i(\text{full})\rvert$ by $K = 3$ and called $K$ a scale of three *episodes*; the
review had already ruled, on the RMST threshold, that $K$ counts **checkpoints**, and on a non-uniform grid
three checkpoints have no fixed episode width --- the same mistake as $K/2 = 1.5$ episodes, one paragraph
over. The per-seed primary endpoint is `restricted_time` $= \min(\tau, T^{*})$, in episodes, so dividing by
$T^{*}$ is dimensionally correct and needs no $K$ at all.

**Censoring is closed on both sides.** `restricted_time` is defined for every seed because $\tau$ is
right-censored at $T^{*}$: both readings censored gives $T^{*} - T^{*} = 0$; one side censored gives a finite
non-zero distortion in the correct direction (the coarse grid *lost* a recovery the full curve shows), which
is exactly the failure $f_G$ exists to detect. Revision 3's draft defined only the both-censored case and
left the one-sided case to the implementer.

$$\boxed{m_G(G) = \max_{i \in \mathcal S_{\text{dev}}}\ \delta_i(G)}$$

The maximum over seeds is deliberate: averaging would let one seed's destroyed recovery time hide behind
thirty-one unchanged ones, and the grid's job is to represent *every* seed's curve. A seed that never
recovers on either reading is right-censored at $T^{*}$ in both, so its term is $0$ rather than undefined.

* **the projection rule is A84's, and it is not step-hold.** Revision 2 wrote step-hold (last
  observation carried forward), which A84 §72 rejects in as many words: left-hold "assumes that the
  measurement at $t_i$ persists across the whole of $[t_i, t_{i+1}]$, which the frozen definition never
  says, and it is not neutral --- on a curve that recovers *within* an interval, left-hold overstates the
  deficit". Reading a grid therefore means evaluating the frozen summaries **on the grid's own episode
  indices with A84's trapezoidal rule**
  $\mathrm{DeficitAUC} = \frac{1}{T_{\max}}\sum_i \frac{d_i + d_{i+1}}{2}(t_{i+1} - t_i)$ and
  `utility.recovery_time` for $\tau$; there is no interpolation rule to choose at lock time because the
  frozen one already exists;
* **the scales are frozen**, one per **surviving** term: $T^{*}$ for `restricted_time` (episodes) and $1$ for
  DeficitAUC, which `05` defines as $\frac{1}{T_{\max}}\int [V_{\text{pre}} - V(t)]_+ dt$ and is therefore
  already a fraction. *(Rev 4, CF-3: rev 3's bullet still listed "K episodes for $\tau$" after withdrawing
  that term two bullets earlier. $K$ counts **checkpoints**, so it is not a scale of episodes at all, and the
  surviving metric $\delta_i(G)$ above never used it. Erratum only: no rule changed.)*
* **the reference level of both $V_{\text{pre}}$-relative terms is the frozen $V_{\text{pre}}$ of the
  reference artifact** (A85 §73.1), not a per-scene quantity: it is a static constant available before any
  arm runs, so the two terms measure the grid's distortion of the *endpoint's own integrand* rather than a
  different quantity computed on baseline material. This is the same reason $f_G$ may read these curves at
  all -- they are baseline curves plus a frozen constant, and no arm is involved;
* **admissibility**: $m_G(G) \le \theta_G$, $\theta_G = 0.05$ `[FIXED rev 5]`;
* **ranking**: the **coarsest** admissible grid -- fewest checkpoints first, then the template order
  $G_1, G_2, G_3$ as written above. Parsimony is the declared preference because a coarser admissible grid
  costs less and the retention estimators need only satisfy their own structural floor;
* **fail-closed**: no admissible grid, or $T^{*} > \texttt{ACQUISITION\_CAP}$, gives
  `NO_ADMISSIBLE_GRID`; the grid never sets $T$.

### 4.4 $f_C$ — the refinement

**Ontology, corrected.** Revision 1 wrote the interpretability predicate over $(s, z, m)$, a decision
context. The surviving unified unit is not a decision context:

$$\boxed{\text{the predicate is over } \left(\kappa,\ \phi,\ \texttt{error\_flag},\
\texttt{cause\_rank},\ z_{\text{base}}\right) \text{, i.e. over } U_2}$$

which is the same object `EvaluationScene` carries and the same field set A86 §74.5 freezes.

| property | instrument | allowed input surface | role |
|---|---|---|---|
| synthetic spillover sensitivity | A89's eighteen-cell calibration: $\lvert B^{ref}\rvert$ and its measured counterpart | the frozen calibration artifact (static) | **gate**: 18/18 licenses measurability; magnitudes never rank |
| coverage | $\lvert C_i(c)\rvert$ and the per-site ratio $\lvert C_i(c)\rvert / \lvert E(c)\rvert$ | the envelope, baseline traces | **static descriptor** (reported, never thresholded) |
| interpretability | the candidate's rule as a declared predicate over $U_2$'s fields | static (source-level) | **gate**: no fitted quantity may appear |
| baseline stability | the refined collateral estimator's sampling spread, per site (formula below) | the envelope, baseline traces | dev-estimated ranking metric |

* **coverage is a descriptor, not a floor.** Revision 2's absolute floor of $32$ was rejected as relating
  to nothing, and its replacements --- a per-site fraction $\rho_C = 0.25$ of the candidate's own pool and
  an aggregate bound $\lvert C(c)\rvert \ge N^{*}_{\text{eval}}$ --- were refused in turn, correctly: the
  second binds the collateral set to a *FutureUtility* sample size, which is the very conflation A85
  separates. A79 lists coverage as a property, and A90 §78.6 requires each property's **role** to be
  declared: coverage is therefore a **static descriptor**, reported for every candidate and for every
  credited site, and it decides nothing. A89's totality already guarantees non-emptiness;
* **the stability metric, as a formula.** It is stated on the objects below --- the refinement $r$, the
  credited site $c$, the seed $\sigma$ and the episode $e$ --- and the standard error it compares is the one
  defined there; the superseded single-index notation of revision 3's draft ($\mathrm{se}_i(c)$ over a
  candidate $c$ and a site $i$, with no run index) is withdrawn.

  **$v_u$ is the pre-update value from the master matrix, and A79 §67.4 fixes which quantity that is.**
  Revision 3's earlier draft read $v_u = V_{Q^{*}}(u)$, the *health reference's* own level, and called $f_C$ a
  static selector. The construction review rejected that, correctly: A85 §73.1 freezes
  $V_{\text{pre}} \neq V_{\text{unaffected,pre}}$ --- the first is the reference's level on $Q^{*}$, the
  second is **this learner's pre-update behaviour** on the unaffected region --- and A79 §67.4 names this
  selector's input as the *baseline stability of the pre-update values*. Substituting the reference's own
  heterogeneity for the learner's would silently change a frozen selector input surface. The reading is
  therefore the development one, taken from the master matrix of §3, and its aggregation over the matrix's
  indices is frozen here rather than left to an implementer:

**Two objects, two letters.** $r \in \mathcal C_C$ is the **refinement**; $c \in
\mathcal D_A^{\text{credit}}(W_{\sigma,e})$ is a **credited site**. Revision 3's draft used $c$ for both,
and --- more importantly --- wrote the candidate set without a run index. A89 §77.3 freezes eligibility as a
function of the learner state,
$E(c) = \{u : \neg Consult_{W_{\text{pre}}}(u, c) \wedge H_{\text{pre}}(u)\}$ with
$H_{\text{pre}}(u) = [\text{outcome}(W_{\text{pre}}, u) = \texttt{SUCCESS}]$, and in the acquisition
$W_{\text{pre}} = W_{\sigma,e}$; the frozen selector's input therefore carries that index:

$$C_r^{A,\sigma,e}(c) = E_{W_{\sigma,e}}(c) \cap S_r$$

$$SE_{A,c,\sigma,e}(r) = \frac{\mathrm{sd}_{u \in C_r^{A,\sigma,e}(c)}\ V_{\sigma,e,u}}
{\sqrt{\lvert C_r^{A,\sigma,e}(c)\rvert}}, \qquad
R_{A,c,\sigma,e}(r) = \frac{SE_{A,c,\sigma,e}(r)}{SE_{A,c,\sigma,e}(\texttt{eligible\_all})}$$

$$\boxed{m_C(r) = \max_{A,\ \sigma,\ e,\ c}\ R_{A,c,\sigma,e}(r)}$$

  with $A \in \{D_Q, X, P\}$, $c$ over that architecture's credited domain for that run, $\sigma \in
\mathcal S_{\text{dev}}$ and $e = 0, \ldots, \texttt{ACQUISITION\_CAP}$. The **worst case over the whole
family** is deliberate and matches the $f_G$ ruling: a refinement that is stable on average but unstable for
one architecture, site, seed or episode has not been shown to be stable. This is A89's own object rather than
a static proxy for it, and it introduces no new acquisition. The metric is that standard error **relative to the unrefined
  pool**, so it is dimensionless and compares candidates rather than sites:

**The zero cases, on the same objects.** There is one $m_C$, defined above over
$(A, c, \sigma, e)$; the ratio it maximises decides its own zero cases directly, with no epsilon in the
argument:

$$\boxed{SE_{A,c,\sigma,e}(\texttt{all}) = 0 \ \land\ SE_{A,c,\sigma,e}(r) = 0
\;\Rightarrow\; R_{A,c,\sigma,e}(r) = 1}
\qquad
\boxed{SE_{A,c,\sigma,e}(\texttt{all}) = 0 \ \land\ SE_{A,c,\sigma,e}(r) > 0
\;\Rightarrow\; r\ \text{inadmissible}}$$

A $0/0$ means "this site's pool is exactly stable for that seed and episode, and so is the slice", which is
*equal* stability rather than an undefined comparison; a slice that moves where its pool does not is one the
pool's own stability cannot excuse, and it is refused rather than credited. Revision 3's earlier draft left
these rules written on the superseded single-index $\mathrm{se}_i$ objects --- a second, contradictory
definition of $m_C$ in the same section --- which the construction review caught. (The
$(A, i, \sigma, e)$ spelling survives only inside that quotation of the withdrawn draft; the frozen
vocabulary is $(A, c, \sigma, e)$.)

  A slice can be more or less stable than the full pool --- dropping atypical units lowers the numerator,
  dropping units lowers the denominator's own $n$ --- which is exactly the trade a refinement makes, and
  the definition needs nothing that $F_1$ does not already have;
* **admissibility and ranking**: $m_C(r) \le \theta_C$ with $\theta_C = 1.0$ `[FIXED rev 5]` --- a refinement
  may not be *less* stable than the pool it was cut from --- and **smaller $m_C$ first**, because a smaller
  standard error *is* more stable. Tie-break: `eligible_all` before any slice, then the order of
  $\mathcal C_C$ as written;
* **dependency**: none on $f_N$ --- the metric reads the baseline envelope only, which is the correction
  the review asked for after revision 2 made the floor read $N^{*}_{\text{eval}}$;
* **fail-closed**: `NO_ADMISSIBLE_REFINEMENT` -- and then no primary refinement, no design lock's
  refinement field, and no confirmatory stage.

### 4.5 $f_R$ — the Retention endpoint, form **and** parameters

$f_R$ no longer emits a bare form name. It emits a **configured endpoint**, because `RetentionAtH` needs
$H$ and `LateWindowRetention` needs $H_1 < H_2$, neither has a default, and a form without its parameters
leaves $S_3$'s runner unable to run:

$$\boxed{f_R:\ \mathcal C_R \times \left(T^{*}, G^{*}\right) \longrightarrow
\left\{\texttt{RetentionAtH}(H^{*}),\ \texttt{LateWindowRetention}(H_1^{*}, H_2^{*})\right\}
\cup \left\{\texttt{NO\_ADMISSIBLE\_RETENTION}\right\}}$$

with the parameters **derived by a frozen function of the locked design values**:

$$H^{*} = T^{*} \qquad \text{(the level at the frozen horizon)}$$

$$H_1^{*} = \texttt{grid}[-3], \qquad H_2^{*} = \texttt{grid}[-1] = T^{*} \qquad
\text{(the last three locked checkpoints, written as indices into the locked grid rather than as } n\text{-relative
notation, because } n \text{ could mean a length or a last index)}$$

The last-three choice is deliberate: the window then contains three checkpoints, matching the $K = 3$
maintained-recovery contract, and every admissible grid has at least three checkpoints by §2. Both
parameters are integer episode indices, which is what the estimators require.

Input surface: $\mathcal C_R$ and **baseline/static diagnostics only** (A90 §78.10's amendment to A79
§67.5).

* **stability, over the development runs.** A configured Retention form maps **one training curve to one
  scalar**, so there is no "spread over the grid's cells" to take: the estimator object is the per-run
  value. Revision 3's earlier draft carried that phrase over from the pre-A91 step-indexed reading, where a
  "cell" was a step; the construction review caught the type error. The frozen series is

$$R_i = \text{form}\bigl(\text{curve}_i\bigr), \qquad i \in \mathcal S_{\text{dev}}$$

  --- the same $32$ baseline runs the redundancy uses --- and the metric is the **closed relative range**
  over it, $s = \dfrac{\max_i R_i - \min_i R_i}{\max_i \lvert R_i\rvert + \epsilon_R}$ with
  $\epsilon_R = 10^{-9}$ declared. The maximum-magnitude denominator is closed (revision 1's median was
  undefined for a non-positive median and unbounded near a zero median), and $s = 0$ when every $R_i = 0$ by
  direct evaluation rather than by convention. Admissible iff $s \le 0.10$ `[FIXED rev 5]`, inclusive;
* **interpretability**: **gate** -- the estimator must be a declared functional of the episode record with
  no fitted quantity;
* **redundancy, on the per-seed values.** Revision 2 correlated the form's value against "the RMST
  series" over evaluation scenes, which is a **type error**: A84 §72 freezes that the per-seed quantity is
  `restricted_time` and that
  $\mathrm{RMST} = \mathbb{E}[\texttt{restricted\_time}]$ is the cross-seed population summary, so no
  per-scene RMST series exists to correlate against. The redundancy is therefore computed over the
  **development seeds**, where all three quantities exist per seed:

$$\boxed{\rho_R = \max\Bigl(\bigl\lvert\rho_S\bigl(\text{form}_i,\ \texttt{restricted\_time}_i\bigr)
\bigr\rvert,\ \bigl\lvert\rho_S\bigl(\text{form}_i,\ \mathrm{DeficitAUC}_i\bigr)\bigr\rvert\Bigr),
\qquad i \in \mathcal S_{\text{dev}}}$$

  with $\rho_S$ the Spearman correlation over the $32$ baseline runs of the master acquisition -- the same
  material $f_T$ reads, no treatment data, no new synthetic object -- and $\rho_R \le 0.9$ `[FIXED rev 5]`.
  The executable convention uses average ranks for ties, followed by Pearson
  correlation of those ranks, with the authoritative left-to-right population
  arithmetic of §4.0. It does not apply the no-ties shortcut formula to tied data.
  **Zero-variance rule, closed**: if either series is constant the correlation is *undefined* and the form
  is **inadmissible** --- no imputation, no $\rho = 0$ default, and therefore no silent promotion of a form
  whose redundancy could not be measured. With $n = 32$ per seed, this is also the first place the
  per-seed/per-population distinction becomes load-bearing rather than editorial. *(Rev 4: this is the rule
  that made CF-2 a P0 rather than a curiosity --- on constant baseline curves all three series are constant
  and **both** forms are inadmissible. The rule is unchanged; §3's baseline initializer is what changed.)*
* **ranking**: lower $\max\lvert\rho\rvert$ first; tie-break: the order of $\mathcal C_R$ as written;
* **fail-closed**: `NO_ADMISSIBLE_RETENTION`, with the same consequence as $f_C$'s failure.

### 4.6 $\{f_{\Delta,e}\}$ — the thresholds

One per registry key of §5, each either a constant declared here or a frozen function instantiated at
$F_1$. No new judgement may appear at the lock.

## 5. The endpoint registry $\mathcal E_\Delta$, keyed by regime and statistic

Revision 1 keyed the registry by statistic alone and proposed letting the T-regime harm constraint *reuse*
the P-regime `RMST` row. The reviewer rejected that, correctly: A79 §62.5 freezes Regime T and Regime P as
**separate populations with separate claims**, so two endpoints that both apply an RMST statistic are still
two identities. The registry is therefore keyed

$$\boxed{\text{key} = \left(\text{regime},\ \text{statistic}\right) \qquad \text{never a bare statistic name}}$$

$$\boxed{\text{a shared numeric bound is a declared alias, not a shared identity}}$$

| key (regime, statistic) | role | threshold provenance |
|---|---|---|
| `(P, RMST)` | primary quantitative endpoint of regime P | Fixed benchmark margin 1.5 training episodes; typed policy in document 31. Not an independently established practical-value threshold or equivalence bound. |
| `(P, DeficitAUC)` | mandatory co-primary of regime P (A79 §67.3) | $\Delta_{\min} = 0.01$ -- **inherited frozen default** from `11-ENVIRONMENT` §10's AUC-like row, which itself inherits the legacy `noninferiority_margin`; **not** a designer judgement |
| `(P, BehavioralCollateral)` | collateral bound of regime P, over the refinement $f_C$ selects | **derived, with its aggregation surface frozen**: with $r^{*}$ the refinement $f_C$ produced (and $c$ a credited site, as in §4.4), the spread family is $\bigl\{\mathrm{sd}_{u \in C_{r^{*}}^{A,\sigma,e}(c)} V_{\sigma,e,u}\bigr\}$ over the same $(A, \sigma, e, c)$ indices as $f_C$'s metric, with $r^{*}$ the refinement it selected, and the bound is the **nearest-rank $Q_{0.95}$ of that family** (§4.1's quantile convention, so no library interpolation enters). A family that is identically zero makes the endpoint inadmissible rather than assigning it a zero bound. Revision 3's draft named a per-site spread "across $\mathcal S_{\text{eval}}(N_{\max})$" with no seed or episode index, leaving `run_dev_lock.py` to choose the aggregation |
| `(P, Retention)` | the $f_R$-configured endpoint -- `RetentionAtH(H*)` or `LateWindowRetention(H1*,H2*)`, under that form's own name and parameters | **derived in the endpoint's own units from its own per-run spread**: $\Delta_{\min} = \kappa_R \cdot \mathrm{sd}_i\bigl(R_i\bigr)$ over the $32$ baseline runs of §4.5, $\kappa_R = 0.25$ `[FIXED rev 5]`; an identically zero spread makes the form inadmissible. (Revision 3's draft wrote $\rho_R$ for this and $\rho_R$ for $f_R$'s Spearman redundancy, and read a *scene-level* spread for an endpoint that is a per-run scalar; the construction review caught both.) |
| `(T, RMST)` | separate T-regime quantitative harm tolerance | Alias by value to P RMST, 1.5; its quantity constraint is L >= -1.5 for reference-minus-treatment CI. Distinct identity and provenance, no zero-harm or practical-safety interpretation. |
| `(T, DeficitAUC)` | regime T's mandatory companion, approved by review | $\Delta_{\min} := \Delta_{\min}\texttt{(P, DeficitAUC)} = 0.01$ -- the inherited frozen default, shared by value and **separate by identity**. A79 §67.3 makes DeficitAUC a mandatory companion of the primary endpoint, and A79 §62.5 keeps the two regimes' populations and claims apart, so this row exists rather than the statistic being reused across regimes |

$$\boxed{\{\mathrm{RMST},\ \mathrm{DeficitAUC}\} \subseteq \text{the registry's statistic set}}$$

$$\boxed{\forall e:\ e\ \text{uses } \Delta_{\min}\ \text{in a confirmatory verdict or bound}
\;\Rightarrow\; e\ \text{has a key in } \mathcal E_\Delta} \qquad
\boxed{\forall \text{key} \in \mathcal E_\Delta:\ \text{exactly one provenance}}$$

**Revision 1's Retention threshold is withdrawn.** It read
$\Delta_{\min} = 0.5 \times d_{\mathrm{RMST}} = 0.75$ episodes applied to a Retention value, which is a
dimensional error: RMST is measured in episodes and `RetentionAtH`/`LateWindowRetention` return a
performance level. The replacement above is in the endpoint's own units, derived from its own sampling
variability, and has no free dimension.

**BehaviouralCollateral is defined precisely** rather than by the word "spread": its baseline spread
family is $\bigl\{\mathrm{sd}_{u \in C_{r^{*}}^{A,\sigma,e}(c)} V_{\sigma,e,u}\bigr\}$ over the
$(A, \sigma, e, c)$ indices of §4.4's metric, with the refinement $r^{*}$ that $f_C$ selected, and the bound
is the nearest-rank $Q_{0.95}$ of that family --- the same quantile convention §4.1 freezes, so no library's
interpolation enters. Revision 4's draft described "the per-site standard deviation of
$V_{\text{unaffected,pre}}$ across the evaluation-scene sample" with no seed, episode or refinement index,
which is the same defect §4.4 has since had corrected.

**RMST interpretation is explicit.** Document 31 supplies MARGIN_A, MARGIN_B,
WITHIN_BENCHMARK_MARGIN and INCONCLUSIVE for reference-minus-treatment intervals.
Do not use the generic practical EQUIVALENT label for these RMST rows. All other
endpoint rules and joint claim gates stay unchanged. The typed policy is validated
at manifest, design-input and registry-construction boundaries; text in a rationale
field alone cannot authorize an unsupported practical claim.

## 6. The dependency graph $\mathcal D_{F_1}$

$$\boxed{\mathcal D_{F_1}\ \text{is acyclic}}$$

$$\boxed{F_1^{\text{design}} = \operatorname{Eval}\bigl(f_T,\ f_N,\ f_G,\ f_C,\ f_R;\
D^{\text{master}}_{\text{dev,baseline}}\bigr)}$$

$$\boxed{F_1^{\text{threshold}} = \operatorname{Eval}\bigl(\{f_{\Delta,e}\}_{e \in \mathcal E_\Delta};\
F_1^{\text{design}}\bigr)}$$

Edges. Revision 3's earlier draft still carried $f_N \to f_C$ from the aggregate coverage floor, which
$\S$4.4 has since withdrawn; the construction review caught the contradiction, and the graph is now:

$$\boxed{\text{envelope} \to \{f_T,\ f_N,\ f_G,\ f_C,\ f_R\}, \qquad f_T \to f_G, \qquad
\{f_T,\ f_G\} \to f_R, \qquad F_1^{\text{design}} \to F_1^{\text{threshold}}}$$

* **the envelope feeds all five selectors directly**: each reads the one acquisition, and none reads
  another selector's *output* except where listed below. In particular $f_C$ reads the baseline traces and
  the envelope only --- its coverage is a descriptor and its metric is the $m_C$ of $\S$4.4, so the old
  $f_N \to f_C$ edge is gone;
* $f_T \to f_G$: the templates are functions of $T^{*}$ ($G_j(T^{*})$), and "full" is the episode axis
  $0 \ldots T^{*}$, so $f_G$ cannot be evaluated before $T$ exists;
* $\{f_T,\ f_G\} \to f_R$: $f_R$'s parameters are $H^{*} = T^{*}$ and
  $(H_1^{*}, H_2^{*}) = (\texttt{grid}[-3], \texttt{grid}[-1])$;
* **there is deliberately no $f_N \to f_G$ or $f_N \to f_R$ edge.** Every design-stage quantity is computed
  on the **master bank** $\mathcal S_{\text{eval}}(N_{\max})$, because the acquisition happens once and the
  candidate sizes are *re-estimates from that same bank* --- which is exactly what $f_N$'s metric compares.
  $N^{*}$ tells the confirmatory run how many scenes it must use; it does not re-measure the design stage.
  Freezing this is the point: an implementer who instead made $f_G$/$f_R$ read $\mathcal S_{\text{eval}}(N^{*})$
  would produce different numbers from the same frozen text;
* every *derived* threshold reads the design stage's outputs; a designer-constant threshold has no upstream
  dependency.

The graph stays acyclic and both stages live in **one** $F_1$ commit: nothing between them may read an
arm, be revised by hand, or differ from the single commit that carries both.

## 7. Commands, paths, and immutable source binding

The executable interfaces are `scripts/f0_manifest.py`, `scripts/run_smoke.py`,
`scripts/run_dev_baseline.py`, `scripts/run_dev_lock.py`, and
`experiments/v03r/evaluate_smoke_gate.py`. Document 30 gives the command surface.
The old default manifest remains an immutable NOT_VALID draft. Rev 5 uses a new
explicit manifest path, passed to every stage; output publication never overwrites.

The manifest pins all instrument source/spec/test bytes, its Git commit, seed-file
bytes, constants, balanced ordering, artifact schema, gate commands and expected
artifact digests, typed RMST policy, source-bound review and measured runtime.
It contains no future development digest or selected F1 quantity. The baseline index
binds that manifest and the passing smoke receipt. F1 binds that index and rechecks
all evidence before publishing one indivisible design/threshold object.

The mandatory serial gates are pytest, spec_audit, b2_view_gate_selfcheck,
a91_training_gate_selfcheck, run_calibration and f0_manifest_selfcheck. Mutation
gates edit and restore source temporarily and must never run concurrently. The
manifest self-check uses synthetic fixtures; a passing fixture approves no study.

Every instrument byte must belong to its stated committed revision. LF checkout
bytes are required by `.gitattributes`. Historical archives retain their original
bytes and digests. Code or protocol changes invalidate the old current-source match;
this revision uses fresh timing rather than rewriting evidence identifiers.

## 8. Runtime bound and the fresh complete measurement

For each stage B = 2 × (T_suite + 10 × T_stage_workload), with both durations
measured under the frozen current source inventory. Smoke measures five complete
streams and development measures thirty-two complete serialized streams, each
with 576 training episodes and 577 checkpoints, master bank 1024 and full-U2
incidence. Total workload: 21,312 training episodes and 21,349 checkpoints.

The benchmark runs its six gates serially and refuses a nonzero exit, source drift,
incomplete record axis or reused output directory. The final runtime file is
published only after all work completes. A short-run extrapolation cannot replace
this evidence. The bound is an abort criterion, not an expected duration.

The completed prior measurement is retained under `experiments/v03r/f0_runtime` at
its original commit. Rev 5 uses `experiments/v03r/f0_runtime_rev5` and the new keys
in section 1. Neither an updated source digest nor a successful gate suite alone
can promote the prior measurement into a new-source measurement.

## 9. Smoke PASS criteria, and the smoke artifact surface

Operational and instrumental only; no criterion may depend on a treatment effect:

1. every gate green: each gate command of §7 exits $0$ at the frozen execution revision, and its exit
   code is recorded in the smoke report;
2. every artifact written at its declared path, with a valid JSON parse;
3. no exception, no fallback, no `NO_ADMISSIBLE_*` outcome taken anywhere;
4. runtime inside §8's bound;
5. the manifest's digests matching the ones recorded here, at the execution revision it pins, with the
   smoke report's `artifact_digests` reproducing them;
6. the smoke report's key set being exactly the operational field set below.

**PASS/FAIL is decided by a frozen evaluator, not by a reader.**
`experiments/v03r/evaluate_smoke_gate.py` (declared with the smoke command in §7) takes the smoke report and
the manifest and returns PASS or the first criterion that failed; the report itself carries no verdict, so
nobody has to interpret an empty field. Revision 2 wrote `gate_exit_codes = {}` and `artifact_digests = {}`
and left the decision to whoever happened to look --- the gap the construction review refused to leave
open.

```
{stage, seeds, tree, runtime_s, gate_exit_codes, artifact_paths, artifact_digests,
 errors, fallbacks}
```

**no** efficacy field of any kind -- no arm contrast, no interval, no effect size, not even optionally.
`not shown` is not `not reachable`, so the surface itself excludes what the boundary excludes.

**Invalidation.** Any change to code, configuration or instrument invalidates these digests: the gates
must be re-closed, this protocol re-frozen, and smoke re-run. A repaired instrument may not inherit the
old PASS.

## 10. What this document does not do

It authorises no seed. It does not declare $\mathcal S_{\text{confirm}}$, does not select a refinement, a
Retention form or its parameters ($F_1$ computes those), does not name $N_{\text{train}}$
(not selected until F1), and does not enter $U_3$. Valid F0 is required for smoke
and development; development additionally waits on smoke's operational PASS.

## 11. Ratification and execution checklist

| Item | Current rule |
|---|---|
| Scientific populations | Exact smoke/dev seed files and complete historical operational exclusions |
| Baseline | C3 layer 1, cap 576, same object across benchmark/smoke/dev; old canary retired |
| Candidates and selectors | Sections 2–6; no outcome-driven fallback or partial F1 lock |
| RMST | Typed fixed 1.5 quantitative benchmark policy; no practical-equivalence or cost-benefit claim |
| Other endpoints | Separate identities and inherited/derived thresholds; no mixed utility score |
| Failure-only scope | Observed terminal failure before diagnosis; SUCCESS skips diagnostic calls/edits; ordinary TD unchanged |
| Gates | All six serial native exits zero and deterministic artifact hashes |
| Source identity | Every code/spec/test byte matches the committed instrument inventory |
| Runtime | Fresh complete source-matched workload and structural integrity verification |
| Review | Explicit source-bound policy review; successful engineering tests alone do not approve science |
| Publication | New manifest committed, then passing smoke, then complete dev, then indivisible F1 |
| Failure outcome | NO_ADMISSIBLE and invalid evidence remain distinct stops; no threshold relaxation |

The detailed mapping of the old 27 checklist items is historical review evidence.
This revision replaces the old cap/initializer and unsupported practical-rationale
requirement explicitly; it does not mark stale pending text as new evidence.

## 12. Revision history

Revision 5 applies the researcher's failure-only correction, promotes the explicit
C3 initializer/cap into the main protocol, gives the 1.5 RMST margin a restricted
quantitative interpretation, and requires new measurement under the changed source
identity. It leaves archived observations and scientific seed assignments untouched.

The complete earlier text, including prior review failures, CF findings and the
withdrawn K/2 rationale, is preserved byte-for-byte in the amendment evidence folder.
Document 31 is the normative change record. Previous closed engineering stages are
not silently relabeled failure-conditional scientific findings.

## 13. Historical review boundary

Earlier reviews explain why the healthy fixed point, calibration-canary defect,
step-axis surrogate and K/2 practical-effect rationale were insufficient. Their
original evidence and failure records are retained. They do not authorize current
execution or override the current clauses above. F0 remains fail-closed until the
source-matched manifest requirements of sections 7–11 are actually satisfied.
