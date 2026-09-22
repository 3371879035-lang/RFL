# 20 — $F_0$: the development protocol freeze (revision 2, draft for review)

**Status: `DRAFT FOR REVIEW (rev 2)`. Not valid, so nothing downstream of it is authorised.**

$$\boxed{F_0@\texttt{698eca2}:\ \textbf{REVIEW FAIL}} \qquad \boxed{F_0 = \text{NOT VALID}} \qquad
\boxed{\texttt{smoke5} = \texttt{dev32} = \text{confirmatory} = \text{V0.4R} = \textbf{NOT AUTHORISED}}$$

$$\boxed{\text{A90 FROZEN} \;\Longrightarrow\; F_0\ \text{may be constructed and reviewed}}$$

$$\boxed{\text{A90 FROZEN} \;\land\; F_0\ \text{VALID} \;\Longrightarrow\; \texttt{smoke5}\ \text{authorised}}$$

Revision 2 answers the review of `698eca2`, which failed $F_0$ on twelve findings while accepting the
skeleton: the seed sets, the four universes' *form*, the complete rule family, the dependency graph, the
mutation self-check and the LF fingerprint principle all stand. §12 records every finding and its
disposition. The findings were not cosmetic: the first revision filled in designer choices and the
failures were scientific and unit errors in those values -- a fixed checkpoint grid that contradicts
$episodes[-1] = T_{\max}$, an evaluation sample ordered by the wrong unit, two different design questions
sharing one metric, two inverted rankings, a dimensional error in a threshold, and a final manifest that
pinned a dirty working tree rather than a runnable revision.

**Values marked `[PROPOSED]` are proposals for ratification, not frozen numbers**, and §11 is the checklist
a reviewer works through. Everything not marked `[PROPOSED]` is either derived from a frozen constant
(and says which) or is the *form* of a declaration.

---

## 1. Seed sets

| set | purpose | value |
|---|---|---|
| $\mathcal S_{\text{smoke}}$ | instrument smoke | five seeds: `{0, 1, 2, 3, 4}` (**APPROVED**) |
| $\mathcal S_{\text{dev}}$ | development stage | thirty-two seeds, enumerated below (**APPROVED**) |
| $\mathcal S_{\text{confirm}}$ | confirmatory stage | **not declared here**; declared in its own authorisation |

```
S_dev = {1000, 1001, 1002, 1003, 1004, 1005, 1006, 1007,
         1008, 1009, 1010, 1011, 1012, 1013, 1014, 1015,
         1016, 1017, 1018, 1019, 1020, 1021, 1022, 1023,
         1024, 1025, 1026, 1027, 1028, 1029, 1030, 1031}
```

$$\boxed{\mathcal S_{\text{smoke}} \cap \mathcal S_{\text{dev}} = \varnothing}$$

$$\boxed{\mathcal S_{\text{confirm}} \cap \left(\mathcal S_{\text{smoke}} \cup
\mathcal S_{\text{dev}}\right) = \varnothing}$$

Both are **sets**, written element by element: neither is a range and neither is a stopping rule. The two
sets are also written to `experiments/v03r/smoke_seeds.txt` and `experiments/v03r/dev_seeds.txt`, which
the run commands of §7 consume, so the drawn set and the declared set are the same bytes.

**What a seed is, and what it is not.** A seed identifies a stochastic *stream* -- the noise tape of one
development episode -- and is the statistical unit. It is **not** the unit of the evaluation sample: the
evaluation sample's units are $U_2$ scenes (§3). Seeds are, in the reviewer's phrase, sample-generation
provenance rather than unit identity, and this revision separates the two because revision 1 conflated
them.

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

$$G_1(T) = \left(0,\ \left\lceil \tfrac{T}{2} \right\rceil,\ T\right)$$

$$G_2(T) = \left(0,\ \left\lceil \tfrac{T}{3} \right\rceil,\
\left\lceil \tfrac{2T}{3} \right\rceil,\ T\right)$$

$$G_3(T) = \left(0,\ \left\lceil \tfrac{T}{4} \right\rceil,\ \left\lceil \tfrac{T}{2} \right\rceil,\
\left\lceil \tfrac{3T}{4} \right\rceil,\ T\right)$$

Each candidate is admissible only for a $T$ that makes it well-defined, and the frozen contract each
template must satisfy is

$$\boxed{G_j(T)_0 = 0, \qquad G_j(T)_{-1} = T, \qquad \text{strictly increasing}, \qquad
\text{integer}, \qquad \left|G_j(T)\right| \ge K = 3}$$

The $K = 3$ floor is not a taste: $05$'s recovery contract is
$\tau = \inf\{t : V_{t'} \ge 0.95\,V_{\text{pre}}\ \forall t' \in [t, t+K-1]\}$ with $K = 3$, so a grid
with fewer than three checkpoints cannot represent the maintained-recovery time at all. $G_1$ is admitted
exactly because $K \ge 3$ allows three; $G_3$ is the finest. The templates' minima differ, and each is
declared rather than assumed:

$$\boxed{G_1, G_2\ \text{well-defined for } T \ge 2; \qquad G_3\ \text{well-defined for } T \ge 4}$$

$G_3(T)$ at $T = 3$ would be $(0, 1, 2, 3, 3)$, which is not strictly increasing, so it is inadmissible
there by the contract rather than silently deduplicated. Since
$T^{*} = \lceil 1.2\,x_{(29)} \rceil \ge 2$ for any non-empty convergence sample, $G_1$ and $G_2$ are
well-defined whenever the lock exists at all; and the fail-closed outcome stays declared anyway, because
"it cannot happen" is not a rule:

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

**The order is frozen, not invented.** $u_1 \ldots u_{N_{\max}}$ is the first $N_{\max}$ elements of the frozen $U_2$ enumeration under A88
§76.2's lexicographic order on $(\kappa, \phi, \texttt{error\_flag}, \texttt{cause\_rank},
z_{\text{base}})$ -- which is not a new ordering this document invents: `scene_domain()` already returns
$U_2$ sorted by `EvaluationScene.key`, and that tuple *is* the order. Two consequences are deliberate:

* the evaluation sample is **seed-free**. Every scene in it is a deterministic element of a frozen finite
  domain, so "the first $N$" has one meaning that no seed and no data can move;
* $\mathcal C_{N_{\text{eval}}}$'s members are prefixes of that one order, and $N_{\max} = 1024 \le 5760$,
  so every candidate is available without enlarging the domain. A candidate above $\left|U_2\right|$
  would be `NO_ADMISSIBLE_N_EVAL`, not a silently extrapolated scene.

**One acquisition, and it is grid-free.** The development stage acquires

$$\boxed{D^{\text{master}}_{\text{dev,baseline}}\ \text{is the only acquisition before } F_1}$$

* the envelope stores **complete episode-indexed baseline curves**, $V(t)$ for
  $t = 0 \ldots \texttt{ENVELOPE\_CAP}$, for each of the first $N_{\max}$ scenes -- not a fixed checkpoint
  tuple. That is what makes $\mathcal C_{\mathcal G}$'s $T$-parameterised templates usable at $F_1$:
  **grids are projections of curves**, and a grid that was chosen before $T$ existed could not be;
* $\texttt{ENVELOPE\_CAP} = 40$ `[PROPOSED]`, with a fail-closed consequence rather than a silent
  extension:

$$\boxed{T^{*} > \texttt{ENVELOPE\_CAP} \;\Longrightarrow\; \texttt{NO\_ADMISSIBLE\_GRID}
\;\Longrightarrow\; \text{new amendment, fresh seeds}}$$

* $S_2$ runs **baseline and static material only**; the treatment arms of that seed set are not run before
  $F_1$ (A90 §78.5), and "the grid looks thin, add checkpoints" is adaptive acquisition and is unavailable.
  The treatment arms are a later, separately authorised stage, so the envelope's acquisition cost is a
  baseline cost, which is what §8's bound must be measured against.

**An open definition this revision does not settle, and its consequence.** $f_T$, $f_N$ and $f_G$ are
stated below over an **episode-indexed** baseline curve $V(t)$, $t = 0 \ldots \texttt{ENVELOPE\_CAP}$ -- the
axis $T_{\max}$, the checkpoint grid and the recovery contract all live on. Which mechanism indexes those
episodes in this rebuild line is *not* frozen, and it is a design choice: an episode index is a training
step, and nothing in A79/A84/A90 fixes what a baseline training step is here. $F_0$ therefore declares the
axis it needs and marks its construction

$$\boxed{\text{the episode index of a baseline curve is } \texttt{[PROPOSED]}\text{, and the lock refuses
until it is ratified}}$$

The harness reflects that literally: `run_dev_baseline.py` acquires the seedless evaluation-scene bank and
one baseline episode per seed, records `convergence_sample: null` with the reason, and `run_dev_lock.py`
raises rather than inventing an axis. A lock that produced numbers from an unfrozen curve semantics would
be choosing a design quantity inside an implementation, which is exactly what $F_1$ is for.

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
* **one acquisition**: every ranking metric reads $D^{\text{master}}_{\text{dev,baseline}}$ or the frozen
  static artifacts, never an arm.

### 4.1 $f_T$ — the horizon

$$T = \left\lceil\, 1.2\, Q_{0.9}\!\left(T_{\text{conv}}\right) \right\rceil$$

with the finite-sample quantile convention frozen here rather than inherited from a library:

$$\boxed{Q_{0.9}(x) = x_{(\lceil 0.9\,n \rceil)} \quad \text{on the ascending order statistics of } x}$$

i.e. nearest rank; with $n = 32$ this is $x_{(29)}$ (**APPROVED**). **The integerisation is frozen here**
as the ceiling: $1.2\,x_{(29)}$ need not be an integer while $T_{\max}$ is an integer episode index, and
`11-ENVIRONMENT`'s episode indices are integers. A missing $T_{\text{conv}}$ makes $f_T$ return
`NO_ADMISSIBLE_T` rather than a value from a smaller sample; ties at the rank are resolved by taking the
lower order statistic only when the tie spans the rank, so no tie-break rests on a sort's stability.

### 4.2 $f_N$ — the evaluation-sample size (Monte-Carlo stability)

Revision 1 measured $N_{\text{eval}}$ with the same across-checkpoint spread as the grid, which answers a
different question: $N_{\text{eval}}$ is about **how many scenes the estimate stands on**, the grid is
about **when it is read**. $f_N$ now measures sampling stability directly, against the largest sample as
the reference:

$$m_N(N) = \max_{t}\ \frac{\left|\hat V_N(t) - \hat V_{N_{\max}}(t)\right|}
{\text{scale}(t)}, \qquad \text{scale}(t) = \max\left(\mathrm{sd}_{\text{scenes}}(t),\ \epsilon_N\right)$$

where $\hat V_N(t)$ is the baseline level at episode $t$ computed over $\mathcal S_{\text{eval}}(N)$,
$\mathrm{sd}_{\text{scenes}}(t)$ is the cross-scene standard deviation of the per-scene level at $t$ over
$\mathcal S_{\text{eval}}(N_{\max})$, and $\epsilon_N = 10^{-9}$ is declared. The scale is the
Monte-Carlo scale of the quantity being estimated, so $m_N$ is measured in units of cross-scene variation
rather than in units of the curve's own drift -- which is what the reviewer's finding asked for, and what
stops a healthy baseline that genuinely changes over time from being read as sample instability.

* **admissibility**: $m_N(N) \le \theta_N$, with $\theta_N = 0.25$ `[PROPOSED]` -- a quarter of one
  cross-scene standard deviation is below the resolution at which two candidate prefixes could be
  distinguished by any downstream endpoint;
* **ranking**: the **smallest** admissible $N$, not the largest (**this reverses revision 1's tie-break**,
  which preferred more evaluation when stability did not separate candidates; the reviewer's ruling is
  that $N_{\text{eval}}$ is a cost as well as a precision, and the selector picks the smallest sample that
  is stable). The total order is $(m_N \text{ ascending}, N \text{ ascending})$;
* **zero and undefined cases**: if $\mathrm{sd}_{\text{scenes}}(t) = 0$ and the numerator is $0$ the term
  is defined as $0$ (an exactly stable sample); if the numerator is positive while the spread is zero the
  term is $\text{numerator}/\epsilon_N \ge 1 > \theta_N$, so the candidate is **inadmissible** rather than
  credited;
* **missing**: a candidate whose curves cannot be computed on the envelope is inadmissible; if none is
  admissible, $f_N \to \texttt{NO\_ADMISSIBLE\_N\_EVAL}$, and then there is no design lock and no
  confirmatory stage.

### 4.3 $f_G$ — the checkpoint grid (temporal resolution)

$f_G$ now asks whether **the grid preserves the frozen endpoints** rather than whether the baseline curve
is flat. For $G \in \mathcal C_{\mathcal G}$, on the baseline curve bank:

$$m_G(G) = \max\Biggl(
\underbrace{\frac{\left|\tau_G - \tau_{\text{full}}\right|}{K}}_{\text{recovery time, } K = 3},
\ \underbrace{\frac{\left|\mathrm{RMST}_G - \mathrm{RMST}_{\text{full}}\right|}{T^{*}}}_{\text{primary endpoint}},
\ \underbrace{\left|\mathrm{DeficitAUC}_G - \mathrm{DeficitAUC}_{\text{full}}\right|}_{
\text{co-primary, already normalised}}\Biggr)$$

* **the projection rule is frozen**: reading a curve at a grid means **step-hold** (last observation
  carried forward) between checkpoints, which is the interpolation under which the frozen summaries are
  defined on a checkpoint sequence; no spline and no re-fitting at lock time;
* **the scales are frozen**, one per term: $K$ episodes for $\tau$ (the width of the maintained-recovery
  window, so the term is "how many recovery windows of error the grid introduces"), $T^{*}$ for RMST
  (episodes), and $1$ for DeficitAUC, which `05` defines as $\frac{1}{T_{\max}}\int [V_{\text{pre}} -
  V(t)]_+ dt$ and is therefore already a fraction;
* **the reference level of both $V_{\text{pre}}$-relative terms is the frozen $V_{\text{pre}}$ of the
  reference artifact** (A85 §73.1), not a per-scene quantity: it is a static constant available before any
  arm runs, so the two terms measure the grid's distortion of the *endpoint's own integrand* rather than a
  different quantity computed on baseline material. This is the same reason $f_G$ may read these curves at
  all -- they are baseline curves plus a frozen constant, and no arm is involved;
* **admissibility**: $m_G(G) \le \theta_G$, $\theta_G = 0.05$ `[PROPOSED]`;
* **ranking**: the **coarsest** admissible grid -- fewest checkpoints first, then the template order
  $G_1, G_2, G_3$ as written above. Parsimony is the declared preference because a coarser admissible grid
  costs less and the retention estimators need only satisfy their own structural floor;
* **fail-closed**: no admissible grid, or $T^{*} > \texttt{ENVELOPE\_CAP}$, gives
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
| coverage | $\lvert C_i(c)\rvert$, the refined credited-unit count per credited site $i$ | the envelope, baseline traces | static descriptor + admissibility floor |
| interpretability | the candidate's rule as a declared predicate over $U_2$'s fields | static (source-level) | **gate**: no fitted quantity may appear |
| baseline stability | relative spread of the level curve under $c$, baseline scenes only | the envelope | dev-estimated ranking metric |

* **coverage floor, now scale-relative.** Revision 1's absolute floor of $32$ was rejected: it related to
  nothing. The floor is now stated against the candidate's own pool and against the evaluation sample:
  for every credited site $i$, $\lvert C_i(c)\rvert \ge \rho_C \cdot \lvert C_i(\texttt{eligible\_all})\rvert$
  with $\rho_C = 0.25$ `[PROPOSED]`, i.e. a refinement may thin a site's unaffected set but not below a
  quarter of what full eligibility gives it; and in aggregate, $\lvert C(c)\rvert \ge N^{*}_{\text{eval}}$
  `[PROPOSED]`, so the unaffected set can never be smaller than the evaluation sample it accompanies. The
  first is relative to $U_2$ through the candidate's own pool and survives any change of $U_2$'s size; the
  second is the $N_{\text{eval}}$ relation the reviewer asked for. A89's totality already guarantees
  non-emptiness, which is the floor's floor;
* **ranking, direction corrected**: **smaller** relative spread first -- a smaller spread *is* more stable,
  and revision 1's "larger first" was simply inverted. Tie-break: `eligible_all` before any slice, then the
  order of $\mathcal C_C$ as written;
* **dependency**: the aggregate floor reads $N^{*}_{\text{eval}}$, so $f_C$ is evaluated **after** $f_N$
  inside $F_1^{\text{design}}$ (§6);
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

$$H_1^{*} = G^{*}_{n-2}, \qquad H_2^{*} = G^{*}_{n} = T^{*} \qquad
\text{(the last three locked checkpoints)}$$

The last-three choice is deliberate: the window then contains three checkpoints, matching the $K = 3$
maintained-recovery contract, and every admissible grid has at least three checkpoints by §2. Both
parameters are integer episode indices, which is what the estimators require.

Input surface: $\mathcal C_R$ and **baseline/static diagnostics only** (A90 §78.10's amendment to A79
§67.5).

* **stability**: instrument = the form's own `.value` on baseline material; metric = the **closed**
  relative range over the frozen grid's cells,
  $s = \dfrac{\max_i v_i - \min_i v_i}{\max_i \lvert v_i\rvert + \epsilon_R}$ with $\epsilon_R = 10^{-9}$
  declared. Revision 1 divided by the median, which is undefined for a non-positive median and unbounded
  near a zero median; the maximum-magnitude denominator is closed, and $s = 0$ when every $v_i = 0$ by
  direct evaluation rather than by convention. Admissible iff $s \le 0.10$ `[PROPOSED]`, inclusive;
* **interpretability**: **gate** -- the estimator must be a declared functional of the episode record with
  no fitted quantity;
* **redundancy**: computed on the deterministic evaluation-scene sample $\mathcal S_{\text{eval}}(N_{\max})$
  -- a static bank of real $U_2$ scenes, no treatment data, no new synthetic object -- as the Spearman
  correlation between the form's value series and each endpoint's series (RMST, DeficitAUC), with
  $\max\lvert\rho\rvert \le 0.9$ `[PROPOSED]`. **Zero-variance rule, now closed**: if either series is
  constant the correlation is *undefined*, and an undefined redundancy makes the form **inadmissible** --
  no imputation, no $\rho = 0$ default, and therefore no silent promotion of a form whose redundancy could
  not be measured. The reviewer's alternative, a frozen synthetic curve bank, is explicitly **not** chosen:
  it would add an unfrozen object to the instrument when a deterministic sample of real scenes already
  supplies non-degenerate variation where it exists;
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
| `(P, RMST)` | primary endpoint of regime P | $\Delta_{\min} = 1.5$ episodes `[PROPOSED]`, **designer judgement**, rationale: $1.5 = K/2$ with $K = 3$ -- an average recovery-time improvement smaller than half the frozen maintained-recovery window is not practically meaningful |
| `(P, DeficitAUC)` | mandatory co-primary of regime P (A79 §67.3) | $\Delta_{\min} = 0.01$ -- **inherited frozen default** from `11-ENVIRONMENT` §10's AUC-like row, which itself inherits the legacy `noninferiority_margin`; **not** a designer judgement |
| `(P, BehavioralCollateral)` | collateral bound of regime P, over the refinement $f_C$ selects | **derived**: the nearest-rank $Q_{0.95}$ of that endpoint's own baseline sampling spread -- the per-credited-site standard deviation of $V_{\text{unaffected,pre}}$ across $\mathcal S_{\text{eval}}(N_{\max})$; if the spread is identically zero the endpoint is inadmissible rather than assigned a zero bound |
| `(P, Retention)` | the $f_R$-configured endpoint -- `RetentionAtH(H*)` or `LateWindowRetention(H1*,H2*)`, under that form's own name and parameters | **derived in the endpoint's own units**: $\Delta_{\min} = \rho_R \cdot \mathrm{sd}_{\text{scenes}}\!\left(\text{form}^{*}\right)$, $\rho_R = 0.25$ `[PROPOSED]`, computed on the deterministic scene sample; identically-zero spread makes the form inadmissible |
| `(T, RMST)` | regime T's harm bound | $\Delta_{\min} := \Delta_{\min}\texttt{(P, RMST)}$ as a **declared alias** -- the same number, a separate identity, because the populations and the claims are separate |

$$\boxed{\{\mathrm{RMST},\ \mathrm{DeficitAUC}\} \subseteq \text{the registry's statistic set}}$$

$$\boxed{\forall e:\ e\ \text{uses } \Delta_{\min}\ \text{in a confirmatory verdict or bound}
\;\Rightarrow\; e\ \text{has a key in } \mathcal E_\Delta} \qquad
\boxed{\forall \text{key} \in \mathcal E_\Delta:\ \text{exactly one provenance}}$$

**Revision 1's Retention threshold is withdrawn.** It read
$\Delta_{\min} = 0.5 \times d_{\mathrm{RMST}} = 0.75$ episodes applied to a Retention value, which is a
dimensional error: RMST is measured in episodes and `RetentionAtH`/`LateWindowRetention` return a
performance level. The replacement above is in the endpoint's own units, derived from its own sampling
variability, and has no free dimension.

**BehaviouralCollateral is defined precisely** rather than by the word "spread": the endpoint's baseline
sampling spread is the per-credited-site standard deviation of $V_{\text{unaffected,pre}}$ across the
evaluation-scene sample, taken site by site, and the bound is its nearest-rank $Q_{0.95}$ -- the same
quantile convention §4.1 freezes, so no library's interpolation enters.

**Two rows remain proposals a reviewer must rule on**, and both are consequential rather than cosmetic:

1. `(T, RMST)`'s shared numeric value. Sharing the number is proposed because the two regimes' harm claims
   are the same *kind* of claim about the same statistic; separating the identities is required because
   A79's populations are separate. A reviewer may instead require an independent number with its own
   rationale, which is a one-line change to this row;
2. `(T, DeficitAUC)`. A79 §67.3 makes DeficitAUC a **mandatory** co-primary; this revision reads that as a
   dimension-level requirement and therefore proposes that the T regime carries it too, with the same
   inherited default `0.01`, as `[PROPOSED — reviewer]`. The alternative -- DeficitAUC being mandatory only
   in the population that exists -- is equally readable from A79, and $F_0$ must not settle a frozen
   document's scope by silence.

## 6. The dependency graph $\mathcal D_{F_1}$

$$\boxed{\mathcal D_{F_1}\ \text{is acyclic}}$$

$$\boxed{F_1^{\text{design}} = \operatorname{Eval}\bigl(f_T,\ f_N,\ f_G,\ f_C,\ f_R;\
D^{\text{master}}_{\text{dev,baseline}}\bigr)}$$

$$\boxed{F_1^{\text{threshold}} = \operatorname{Eval}\bigl(\{f_{\Delta,e}\}_{e \in \mathcal E_\Delta};\
F_1^{\text{design}}\bigr)}$$

Edges, now including the two **intra-stage** dependencies this revision introduced:

$$\boxed{\text{envelope} \to \{f_T,\ f_N,\ f_G\}, \qquad f_N \to f_C, \qquad
\{f_T,\ f_G\} \to f_R, \qquad F_1^{\text{design}} \to F_1^{\text{threshold}}}$$

* $f_N \to f_C$: $f_C$'s aggregate coverage floor reads $N^{*}_{\text{eval}}$;
* $\{f_T, f_G\} \to f_R$: $f_R$'s parameters are derived from $T^{*}$ and $G^{*}$;
* every *derived* threshold reads the design stage's outputs; a designer-constant threshold has no
  upstream dependency.

The graph stays acyclic and both stages live in **one** $F_1$ commit: nothing between them may read an
arm, be revised by hand, or differ from the single commit that carries both.

## 7. Commands, paths, and the instrument hashes

| what | command | artifact |
|---|---|---|
| smoke | `python scripts/run_smoke.py --seeds-file experiments/v03r/smoke_seeds.txt` | `experiments/v03r/smoke_report.json` |
| development baseline | `python scripts/run_dev_baseline.py --seeds-file experiments/v03r/dev_seeds.txt` | `experiments/v03r/dev_baseline.json` |
| the lock | `python scripts/run_dev_lock.py --design experiments/v03r/dev_baseline.json` | `experiments/v03r/dev_lock.json` |

The seed sets of §1 are written to `experiments/v03r/smoke_seeds.txt` and `experiments/v03r/dev_seeds.txt`,
and the commands consume those files rather than a re-typed range: `1000-1031` in a command line would be a
range again, and §1's point is that the sets are sets.

**The three scripts are implemented and gated, and have not been executed.** A frozen command list that
cannot run is not a protocol, so the harness is part of $F_0$'s *construction* rather than follow-up work:
`src/rfl_rebuild/b2/devstage.py` plus the three thin CLIs, with tests and a mutation self-check. What they
may not do is draw a seed:

* each stage refuses to execute unless the manifest's `currently_authorises` contains its own stage name,
  and the refusal is a `ProtocolError` that writes nothing;
* every stage has a `--plan` mode that validates its inputs, prints the plan, runs no episode and writes no
  artifact -- which is what the gates exercise, so the gates themselves draw no seed;
* the smoke report's key set is asserted to be exactly the operational field set of §9.

$$\boxed{\texttt{currently\_authorises} = [\,] \quad \text{until a reviewer marks } F_0\ \text{VALID}}$$

**Manifest provenance.** Revision 1's manifest recorded `repo.head = 507bc90` with a dirty tree, so it
evidenced a working-tree generation rather than a runnable revision. The manifest now

* **asserts that the code tree is clean** -- only the manifest output file itself may be dirty -- so a
  manifest cannot be produced from an uncommitted instrument;
* records the **execution revision**: the commit whose tree the scripts of §7 will actually run from;
* fingerprints the **harness** itself -- every `scripts/run_*.py` (the three commands of §7 plus the two
  seedless gate drivers) and the two declared seed files, by content digest -- so the frozen command
  surface is pinned and not merely named;
* asserts and records the **evaluation sample** of §3: that `scene_domain()` and `u2_domain()` agree
  element-wise on all $5760$ units, that the order is A88 §76.2's lexicographic one, the prefix boundary
  of each $\mathcal C_{N_{\text{eval}}}$ candidate, and a digest of the first $N_{\max}$ scenes. Without
  that assertion a re-ordering of either enumerator would silently redefine every candidate;
* separates authorisation by validity:

```
"currently_authorises":    []
"authorises_on_validity":  ["smoke5"]
```

As generated on this revision's execution commit:

| recorded quantity | value |
|---|---|
| execution revision | `3156e17`, code tree clean, closure `a4451cc` an asserted ancestor |
| generator | `scripts/f0_manifest.py`, digest `b4f8055477…` |
| instrument sources | 54 files, tree digest `196a06b206…` |
| run harness | 5 run scripts, tree digest `2c3bb7b9d2…`, with the two seed-set files in the same block |
| test inventory | 716 collected node ids, digest `5cdb4346e5…` |
| evaluation sample | $\lvert U_2 \rvert = 5760$, $N_{\max} = 1024$, first-$N_{\max}$ digest `43c4a6011c…` |
| reference artifact | digest `01bb5c97d2c9bbf6552dbe4d3017e17162bddd7ac5344583d169da2f573061ae` |
| calibration artifact | digest `c3a58df529…`, 18/18 CALIBRATED, worst absolute gap `4.44e-16` |
| screening artifact | digest `1d493488d9…`, six cells, five non-rejected, `UNIFIED_SURVIVES` |
| mutation artifact | digest `671fa421a1…`, 45/45 `GATE_IS_REAL` across 31 distinct gates |
| runtime benchmark | $1024$ scenes in `0.062132 s`, seedless, from which §8's bounds follow |

The frozen instrument's own fingerprints -- closure commit, reference-artifact digest, calibration and
mutation artifacts, the source tree digest and the test inventory -- are recorded in
`experiments/v03r/f0_manifest.json`, generated by `scripts/f0_manifest.py`, which asserts each invariant
it reads back. The generator's assertions are themselves mutation-verified by
`scripts/f0_manifest_selfcheck.py`: ten mutations, each of which must go red with the expected message,
with a control run that must stay green -- including one that re-introduces the shipped status-parser
decapitation and one that dirties the code tree, which the manifest must refuse.

**Line endings are part of a fingerprint.** `.gitattributes` declares `* text=auto eol=lf`, so a digest
taken from a CRLF working-tree file is a digest of one machine rather than of the revision. The manifest
asserts that each artifact it hashes is CRLF-free, and a self-check mutation proves that assertion goes
red. Ten **pre-existing** artifacts still carry CRLF on disk relative to their LF blobs; they are listed
in `repo.crlf_artifacts_on_disk`, not rewritten, because rewriting them would change working-tree bytes
that earlier arrows produced (**ACCEPTED** as ledger treatment).

## 8. Runtime bound, derived from a seedless benchmark

$$\boxed{\text{bound} = \max\left(\text{floor},\ \text{multiple} \times
\text{seedless benchmark}\right)}, \qquad \text{multiple} = 100$$

| stage | floor | bound |
|---|---|---|
| smoke (5 seeds) | 30 s | 30 s `[PROPOSED, derived]` |
| development baseline acquisition (32 seeds, baseline/static only) | 300 s | 300 s `[PROPOSED, derived]` |

The measurement is the seedless pass of §3's evaluation sample: $1024$ scenes' rollouts on the frozen
instrument, recorded in `experiments/v03r/f0_manifest.json` as `runtime_benchmark` together with this
rule, the multiple and the floors -- so "the bound was measured" is checkable rather than asserted. The
measured value is of the order of $0.07$ s, which both floors dominate: they cover what the benchmark does
not, namely interpreter start, the reference solve and the gate re-checks a stage performs around its
workload.

Seedless is structural here rather than a matter of restraint: the evaluation sample is a prefix of the
frozen $U_2$ enumeration, so this workload is a property of the instrument and not of a sample, and it
draws no stream from $\mathcal S_{\text{smoke}}$ or $\mathcal S_{\text{dev}}$. Had the frozen instrument
required a noise stream even on that path, the honest outcome would have been to keep this section
provisional rather than to draw a seed and call it a benchmark.

A bound is a smoke *criterion*: exceeding it fails smoke, and no bound is a target to be met by shrinking
the work.

## 9. Smoke PASS criteria, and the smoke artifact surface

Operational and instrumental only; no criterion may depend on a treatment effect:

1. every gate green: the full suite exits 0 at the frozen execution revision;
2. every artifact written at its declared path, with a valid JSON parse;
3. no exception, no fallback, no `NO_ADMISSIBLE_*` outcome taken anywhere;
4. runtime inside §8's bound (which must be ratified before this criterion can be applied);
5. the manifest's digests matching the ones recorded here, at the execution revision it pins;
6. the smoke report's key set being exactly the operational field set below.

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
(NONEXISTENT/OPEN), and does not enter $U_3$. Its validity is a precondition for smoke, not for
development: development waits on smoke's operational PASS.

## 11. Ratification checklist

| # | item | state |
|---|---|---|
| 1 | $\mathcal S_{\text{smoke}}$, $\mathcal S_{\text{dev}}$ and disjointness | **APPROVED** |
| 2 | $\mathcal C_C$, $\mathcal C_R$ membership | **APPROVED** |
| 3 | $\mathcal C_{N_{\text{eval}}} = \{100,256,512,1024\}$ | `[PROPOSED]` (100 restored by review) |
| 4 | $\mathcal C_{\mathcal G}$ as three $T$-parameterised templates with $0, T, K \ge 3$ | `[PROPOSED]` |
| 5 | $\texttt{ENVELOPE\_CAP} = 40$ and its fail-closed consequence | `[PROPOSED]` |
| 6 | $f_T$'s ceiling integerisation and nearest-rank quantile | `[PROPOSED convention]` |
| 7 | $f_N$'s metric, $\theta_N = 0.25$, smallest-first ranking | `[PROPOSED]` |
| 8 | $f_G$'s metric, scales $K/T^{*}/1$, step-hold projection, $\theta_G = 0.05$, coarsest-first | `[PROPOSED]` |
| 9 | $f_C$'s $U_2$ ontology, $\rho_C = 0.25$, aggregate floor $\ge N^{*}_{\text{eval}}$, smaller-first | `[PROPOSED]` |
| 10 | $f_R$'s parameters $H^{*} = T^{*}$, $(H_1^{*}, H_2^{*}) = (G^{*}_{n-2}, G^{*}_n)$ | `[PROPOSED]` |
| 11 | $f_R$'s metrics: closed relative range, scene-sample redundancy, $\max\lvert\rho\rvert \le 0.9$, undefined $\Rightarrow$ inadmissible | `[PROPOSED]` |
| 12 | registry keys $(\text{regime}, \text{statistic})$; the `(T, RMST)` alias | `[PROPOSED — reviewer]` |
| 13 | the `(T, DeficitAUC)` role | `[PROPOSED — reviewer]` |
| 14 | $d_{(P,\mathrm{RMST})} = 1.5$ with the $K/2$ rationale | `[PROPOSED]` |
| 15 | $d_{\text{DeficitAUC}} = 0.01$ as an inherited default | `[PROPOSED as inherited]` |
| 16 | `(P, BehavioralCollateral)` and `(P, Retention)` derived bounds | `[PROPOSED]` |
| 17 | the runtime bound of §8, derived from the seedless benchmark | `[PROPOSED, derived]` |
| 18 | §4.0 conventions, smoke PASS criteria and artifact surface | **APPROVED** (carried from rev 1) |
| 19 | the execution revision, the clean-tree assertion and the manifest's authorisation fields | computed at the execution revision; reviewer verifies |
| 20 | the ten pre-existing CRLF artifacts | **APPROVED** as ledger treatment |
| 21 | **the episode index of a baseline curve** (§3) | `[PROPOSED — reviewer]`, and the lock refuses until ratified |

## 12. Revision log

**rev 1 (`698eca2`) — REVIEW FAIL.** The review accepted the skeleton (seed sets and their form, the four
universes' form, the complete rule family's form, the single-commit two-stage $\mathcal D_{F_1}$, the
numerical conventions, the registry's per-entry provenance requirement, the LF fingerprint principle, the
historical-CRLF ledger treatment, the manifest self-check mechanism, the operational-only smoke surface,
the no-adaptive-top-up rule, and that no scientific seed has been drawn) and failed the document on twelve
findings. Dispositions:

| # | finding | disposition |
|---|---|---|
| 1 | evaluation ordering by `(seed, episode)` used the wrong unit | **fixed**: §3 orders $U_2$ evaluation scenes under A88 §76.2's frozen order, seed-free, with $N_{\max} = 1024$ |
| 2 | fixed grid `(0,5,15,40)` contradicts A84's $episodes[-1] = T_{\max}$; `(0,40)` has two checkpoints while $K = 3$ | **fixed**: §2's three $T$-parameterised templates with $0$, $T$, strictly increasing, integer, $\ge 3$ checkpoints |
| 3 | $T$'s integerisation unfrozen | **fixed**: §4.1 freezes the ceiling |
| 4 | $f_N$ and $f_G$ measured one wrong quantity | **fixed**: §4.2 Monte-Carlo stability in cross-scene units; §4.3 endpoint-preservation with frozen scales |
| 5 | $f_C$'s predicate used decision-context fields; ranking direction inverted | **fixed**: §4.4's $U_2$ fields; smaller-first |
| 6 | absolute coverage floor `32` related to nothing | **fixed**: §4.4's per-site relative floor plus the $N^{*}_{\text{eval}}$ aggregate floor |
| 7 | $f_R$ emitted a bare form with no parameters; median-zero unclosed | **fixed**: §4.5's configured endpoint with derived $H^{*}, H_1^{*}, H_2^{*}$, closed relative range |
| 8 | Retention threshold `0.5 × d_RMST` was a dimensional error | **withdrawn and replaced** by §5's own-units derived bound |
| 9 | registry keyed by statistic; T-regime harm identity conflated with regime P's | **fixed**: §5's $(\text{regime}, \text{statistic})$ key and declared alias |
| 10 | `d_RMST` lacked rationale; `d_DeficitAUC = 0.05` silently loosened a frozen default | **fixed**: $1.5 = K/2$ rationale; `0.01` inherited |
| 11 | the three run commands did not exist, so the frozen command list was not runnable; the manifest evidenced a dirty working tree | **fixed**: the harness is implemented and gated, the manifest asserts a clean code tree and pins the execution revision, and authorisation is split into `currently_authorises` / `authorises_on_validity` |
| 12 | candidate status removed from the frozen default $N_{\text{eval}} = 100$ | **fixed**: §2 restores it to $\mathcal C_{N_{\text{eval}}}$ |

**A correction of this document's own correction.** Revision 1's reply dismissed the reviewer's reading of
`xperiments/v03r/f0_manifest.json` as a transcription slip, arguing that `git status --porcelain`'s
three-character prefix is stripped as designed. **That dismissal was wrong and is withdrawn.** The parser
called `git(...)`, whose final `.strip()` removes leading whitespace from the *whole* output; for the first
line -- where a modified-but-unstaged file reports ` M path` -- that eats the status space, and slicing
three characters then removes the path's first character. The mangled name was also classified as code
rather than evidence, so a dirty evidence artifact was reported as a dirty instrument. The review's finding
was therefore stronger than it stated, and its transcription was faithful. Parsing is now a pure function,
`parse_porcelain`, with its own tests (`tests/rebuild/test_f0_manifest.py`) and its own mutation in the
manifest self-check. Recording it here rather than quietly fixing it, because the failure mode was not the
bug: it was explaining away a reviewer's correct observation.

**The harness, and the one thing implementing it exposed.** Finding 11 was closed by writing the three
commands rather than by describing them: `src/rfl_rebuild/b2/devstage.py` plus the three thin CLIs, gated
by `tests/rebuild/test_b2_devstage.py` and mutation-checked by `scripts/b2_run_gate_selfcheck.py`, which
reverts ten guards -- the token comparison, the probe-manifest refusal, the validity-grant subset check,
the seed-set size, overlap and duplicate checks, the smoke surface guard, the benchmark's seedlessness, the
plan's "ran nothing" report, and the CLI's exit code -- and requires each to go red with the expected
message. Writing it also exposed an open definition that rev 1 had glossed: the rules of §4 read an
**episode-indexed** baseline curve, and what indexes those episodes in this rebuild line is not frozen.
That is now checklist item 21, the harness records `convergence_sample: null` with the reason, and the lock
refuses instead of inventing the axis. An implementation is allowed to find a hole in the design; it is not
allowed to fill it silently.
