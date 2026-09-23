# 20 --- $F_0$: the development protocol freeze (revision 3, construction in progress)

**Status: `CONSTRUCTION IN PROGRESS (rev 3)`, on branch `f0-rev3` based on the frozen `rebuild@b5c5762`. Not valid, so nothing downstream of it is authorised.**

$$\boxed{F_0@\texttt{698eca2}:\ \textbf{REVIEW FAIL}} \qquad
\boxed{F_0@\texttt{c643b73}:\ \textbf{REVIEW FAIL (science layer; execution layer PASS)}} \qquad
\boxed{F_0 = \text{NOT VALID}}$$

$$\boxed{A91:\ \textbf{FROZEN}@\texttt{3f02724}, \qquad \textbf{instrument and integration CLOSED}
@\texttt{b35f649}, \qquad \text{promoted as } \texttt{rebuild@b5c5762}}$$

$$\boxed{\texttt{smoke5} = \texttt{dev32} = \text{confirmatory} = \text{V0.4R} = \textbf{NOT AUTHORISED}}$$

$$\boxed{\text{A90 FROZEN} \;\Longrightarrow\; F_0\ \text{may be constructed and reviewed}}$$

$$\boxed{\text{A90 FROZEN} \;\land\; F_0\ \text{VALID} \;\Longrightarrow\; \texttt{smoke5}\ \text{authorised}}$$

This revision is written on top of a **closed instrument**. A91 froze the training-time and
episode-axis contract (`3f02724`) and its instrument and integration were closed (`b35f649`, promoted as
`rebuild@b5c5762`), so the axis, the ordinary-learning transition system and the runner integration are
consumed here rather than re-specified. Revisions 1 and 2 are historical: §12 records their review rounds
and dispositions, and §13 records the review of rev 2 in full.

**Values marked `[PROPOSED]` are proposals for ratification, not frozen numbers**, and §11 is the checklist
a reviewer works through. Everything not marked `[PROPOSED]` is either derived from a frozen constant (and
says which) or is the *form* of a declaration. Where this revision says a construction was **verified**, the
verification was run before the text was written, and the check is named.

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

**What a seed is, and what it is not.** A seed $\sigma$ identifies a **whole training run's** keyed
exogenous stream, exactly as A91 §79.5 froze it:

$$\boxed{\sigma \;\longrightarrow\; \{\Xi_e\}_{e \ge 0}, \qquad
\Xi_e = \bigl(\kappa_e,\ \zeta_e,\ \text{Tape}_e,\ \chi_e(\cdot)\bigr)}$$

Revision 2 said "the noise tape of one development episode", which is the pre-A91 reading and is wrong in
both directions: one seed supplies the *entire* run, and an episode's tape is one component of $\Xi_e$. The
seed remains the **statistical unit** and is **not** the unit of the evaluation sample -- those are $U_2$
scenes (§3) -- so it is sample-generation provenance rather than unit identity. The pre-data constants this
document must declare are therefore the seed sets here **and** the four constants A91 §79.4(f) fixes:

$$\boxed{\alpha,\quad \varepsilon_{\text{explore}},\quad \epsilon_s,\quad \epsilon_f
\ \text{ are pre-data } F_0 \text{ constants, declared before the first seed}}$$

with A91's domains $0 < \alpha \le 1$ (a finite real), $\varepsilon_{\text{explore}} = p/q$ an
**exact rational** in $(0,1]$, $\epsilon_s > 0$ and $0 < \epsilon_f \le 1$. Their **values** are declared in the block below; the convergence tolerances belong with them rather
than inside $f_T$'s mechanics, because they are constants of the experiment and not outputs of any rule.

| pre-data constant | value | type / domain | provenance |
|---|---|---|---|
| $\alpha$ | $1/2$ `[PROPOSED]` | finite real, $0 < \alpha \le 1$ (A91 §79.4(f)) | designer judgement: the tabular $Q$-learning step size, declared before the first seed |
| $\varepsilon_{\text{explore}}$ | $1/10$ `[PROPOSED]` | **exact rational** $p/q$ in $(0,1]$ (A91 §79.4(f)) | designer judgement: the training behaviour policy's exploration rate; rational because §79.5's coin compares integers |
| $\epsilon_s$ | $10^{-3}$ `[PROPOSED]` | $\epsilon_s > 0$, in units of the level per episode | designer judgement: $\lvert\mathrm{slope}_K\rvert$ below this counts as flat |
| $\epsilon_f$ | $1/10$ `[PROPOSED]` | $0 < \epsilon_f \le 1$, dimensionless | designer judgement: under $K = 3$ a window has $K - 2 = 1$ adjacent non-zero increment pair, so a defined FlipRate is $0$ or $1$ and **any** $\epsilon_f$ in the frozen domain implements the same rule --- a qualifying window must be reversal-free. The value is kept as a positive pre-data threshold; revision 3's rationale ("at most one reversal in ten pairs") described a window that cannot occur, and strictly it would even have failed on FlipRate $= 1/10$ |
| $\texttt{ACQUISITION\_CAP}$ | $40$ `[PROPOSED]` | positive integer, episodes | designer judgement: the envelope's episode budget, and the number $T^{*}$ must not exceed (§4.1) |

Every one of them is a constant of the **experiment**, so none may be set after the first seed: A91 §79.4(f)
fixes the domains and this block fixes the values, which is what makes "pre-data" checkable rather than
merely stated. The seed **sets** above are the sixth pre-data declaration; unlike the five constants they
are sets rather than numbers, and they are already written element by element.

**The benchmark keys, and what they are not.** A91's training stream needs a key even to be *measured*, so a
runtime benchmark of the acquisition cannot be keyless; revision 3 said both "the benchmark must represent
`acquire_master_baseline`" and "no benchmark may draw a stream", which cannot both hold. The resolution is to
separate the two kinds of key:

$$\boxed{\mathcal B_{\text{bench}} = \{900001,\ 900002,\ \ldots,\ 900032\} \quad \texttt{[PROPOSED]},
\qquad \mathcal B_{\text{bench}} \cap \left(\mathcal S_{\text{smoke}} \cup \mathcal S_{\text{dev}}\right)
= \varnothing}$$

$$\boxed{\mathcal B^{\text{op}}_{\text{smoke}} = \text{the first } 5 \text{ benchmark keys}, \qquad
\mathcal B^{\text{op}}_{\text{dev}} = \text{all } 32 \text{ benchmark keys}}$$

  so each stage's benchmark is the **shape of its own workload** --- five keyed runs for smoke, thirty-two
  for the master acquisition --- with no scaling factor, no repetition rule and no mapping decision left to
  the harness. Revision 3 declared four keys and then required the development benchmark to represent a
  thirty-two-run acquisition, which the construction review caught: how four keys become thirty-two runs
  (repeat, cycle, or scale by $8$) would have been four different benchmarks from one frozen text.

$$\boxed{\text{scientific seed} \;\neq\; \text{operational benchmark key}}$$

  $\mathcal B_{\text{bench}}$ is **non-scientific**: it may be used only to time the instrument, it may not
  enter any scientific artifact, it may not be read by $f_T, f_N, f_G, f_C, f_R$ or by any threshold, and a
  number produced with it may never be promoted into a development or confirmatory observation. It is
  reserved against $\mathcal S_{\text{confirm}}$ exactly as the other two sets are, so a future confirmatory
  authorisation cannot reuse it by accident.

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
  without re-running a scientific stream and without inventing a static eligibility. The per-$(A, \sigma, e,
  c, r)$ sufficient statistics --- $\lvert C_r^{A,\sigma,e}(c)\rvert$,
  $\sum_{u \in C} V_{\sigma,e,u}$ and $\sum_{u \in C} V_{\sigma,e,u}^2$ --- are the minimum, and the full
  incidence form ($Consult$ and $H_{\text{pre}}$ per unit) is equally acceptable. A levels-only artifact is
  **not**: it would leave `run_dev_lock.py` to choose between re-running the development stream, inventing an
  eligibility, or failing.
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

$$\boxed{\texttt{ACQUISITION\_CAP} = 40 \quad \texttt{[PROPOSED, pre-data ]}F_0\text{ constant}}$$

The cap is the envelope's episode budget, not $T^{*}$: $T^{*}=\lceil 1.2\,x_{(29)}\rceil$ is computed *from*
the acquisition at $F_1$. A horizon the envelope cannot reach fails closed rather than extending itself:

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
  NumPy disagree by default and the difference moves $m_N$, $m_C$ and both derived $\Delta_{\min}$. Two
  consequences follow and are part of the definition: $n = 1$ gives $\mathrm{sd} = 0$ rather than an
  undefined value, and the frozen per-set sufficient statistics of §3 --- count, sum, sum of squares ---
  recover this form exactly, which is why they are the declared minimum;
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

$$m_N(N) = \max_{e = 0}^{\texttt{ACQUISITION\_CAP}}\
\frac{\left|\hat V_N(e) - \hat V_{N_{\max}}(e)\right|}
{\text{scale}(e)}, \qquad \text{scale}(e) = \max\left(\mathrm{sd}_{\text{scenes}}(e),\ \epsilon_N\right)$$

where $\hat V_N(e)$ is the mean over $\mathcal S_{\text{eval}}(N)$ of the level at training episode $e$,
$\mathrm{sd}_{\text{scenes}}(e)$ is the cross-scene standard deviation (the population form of §4.0) of the
per-scene levels at $e$ over $\mathcal S_{\text{eval}}(N_{\max})$ --- both read from the master matrix of
§3 --- and $\epsilon_N = 10^{-9}$ is declared. **The quantifier's domain is the acquisition axis, $e = 0,
\ldots, \texttt{ACQUISITION\_CAP}$, and not $0 \ldots T^{*}$**: $f_N$ deliberately does not depend on $f_T$
in §6's graph, so its domain cannot be a horizon that does not exist when it runs. Revision 4's draft wrote
$\max_t$ without naming the domain, which would have let an implementer choose the full acquisition axis,
the locked horizon, the grid's checkpoints, or another subset --- four different selectors from one
formula. The scale is the
Monte-Carlo scale of the quantity being estimated, so $m_N$ is measured in units of cross-scene variation
rather than in units of the curve's own drift -- which is what the reviewer's finding asked for, and what
stops a healthy baseline that genuinely changes over time from being read as sample instability.

* **admissibility**: $m_N(N) \le \theta_N$, with $\theta_N = 0.25$ `[PROPOSED]` -- a quarter of one
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
definition of $m_C$ in the same section --- which the construction review caught; what remains here is the
zero rule in the $(A, i, \sigma, e)$ vocabulary and nothing else.

  A slice can be more or less stable than the full pool --- dropping atypical units lowers the numerator,
  dropping units lowers the denominator's own $n$ --- which is exactly the trade a refinement makes, and
  the definition needs nothing that $F_1$ does not already have;
* **admissibility and ranking**: $m_C(r) \le \theta_C$ with $\theta_C = 1.0$ `[PROPOSED]` --- a refinement
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
  direct evaluation rather than by convention. Admissible iff $s \le 0.10$ `[PROPOSED]`, inclusive;
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
  material $f_T$ reads, no treatment data, no new synthetic object -- and $\rho_R \le 0.9$ `[PROPOSED]`.
  **Zero-variance rule, closed**: if either series is constant the correlation is *undefined* and the form
  is **inadmissible** --- no imputation, no $\rho = 0$ default, and therefore no silent promotion of a form
  whose redundancy could not be measured. With $n = 32$ per seed, this is also the first place the
  per-seed/per-population distinction becomes load-bearing rather than editorial;
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
| `(P, RMST)` | primary endpoint of regime P | $\Delta_{\min} = 1.5$ episodes `[PROPOSED]`, **designer judgement** with its **$K/2$ rationale withdrawn**: $K = 3$ counts *checkpoints*, not episodes, and the grid is non-uniform, so $K/2 = 1.5$ has no automatic "1.5 episodes" meaning. The value stands as a proposal and **needs an independent practical-meaning rationale** before $F_0$ can be VALID |
| `(P, DeficitAUC)` | mandatory co-primary of regime P (A79 §67.3) | $\Delta_{\min} = 0.01$ -- **inherited frozen default** from `11-ENVIRONMENT` §10's AUC-like row, which itself inherits the legacy `noninferiority_margin`; **not** a designer judgement |
| `(P, BehavioralCollateral)` | collateral bound of regime P, over the refinement $f_C$ selects | **derived, with its aggregation surface frozen**: with $r^{*}$ the refinement $f_C$ produced (and $c$ a credited site, as in §4.4), the spread family is $\bigl\{\mathrm{sd}_{u \in C_{r^{*}}^{A,\sigma,e}(c)} V_{\sigma,e,u}\bigr\}$ over the same $(A, \sigma, e, c)$ indices as $f_C$'s metric, with $r^{*}$ the refinement it selected, and the bound is the **nearest-rank $Q_{0.95}$ of that family** (§4.1's quantile convention, so no library interpolation enters). A family that is identically zero makes the endpoint inadmissible rather than assigning it a zero bound. Revision 3's draft named a per-site spread "across $\mathcal S_{\text{eval}}(N_{\max})$" with no seed or episode index, leaving `run_dev_lock.py` to choose the aggregation |
| `(P, Retention)` | the $f_R$-configured endpoint -- `RetentionAtH(H*)` or `LateWindowRetention(H1*,H2*)`, under that form's own name and parameters | **derived in the endpoint's own units from its own per-run spread**: $\Delta_{\min} = \kappa_R \cdot \mathrm{sd}_i\bigl(R_i\bigr)$ over the $32$ baseline runs of §4.5, $\kappa_R = 0.25$ `[PROPOSED]`; an identically zero spread makes the form inadmissible. (Revision 3's draft wrote $\rho_R$ for this and $\rho_R$ for $f_R$'s Spearman redundancy, and read a *scene-level* spread for an endpoint that is a per-run scalar; the construction review caught both.) |
| `(T, RMST)` | regime T's harm bound | $\Delta_{\min} := \Delta_{\min}\texttt{(P, RMST)}$ as a **declared alias** -- the same number, a separate identity, because the populations and the claims are separate |
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

**The T-regime rows are settled, and their provenance is per row.** The review ruled that the T regime
carries DeficitAUC as a mandatory companion (so `(T, DeficitAUC)` exists with $\Delta_{\min} = 0.01$ and its
own identity) and that `(T, RMST)` shares the P-regime **number** as a declared alias while remaining a
separate identity. Nothing in this table is left for a reviewer to rule on; what remains open is
$d_{(P,\mathrm{RMST})}$'s *rationale* (§5's first row), which is a value question and not a registry one.

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

## 7. Commands, paths, and the instrument hashes

| what | command | artifact |
|---|---|---|
| smoke | `python scripts/run_smoke.py --seeds-file experiments/v03r/smoke_seeds.txt` | `experiments/v03r/smoke_report.json` |
| development baseline | `python scripts/run_dev_baseline.py --seeds-file experiments/v03r/dev_seeds.txt` | `experiments/v03r/dev_baseline.json` |
| the lock | `python scripts/run_dev_lock.py --design experiments/v03r/dev_baseline.json` | `experiments/v03r/dev_lock.json` |

The seed sets of §1 are written to `experiments/v03r/smoke_seeds.txt` and `experiments/v03r/dev_seeds.txt`,
and the commands consume those files rather than a re-typed range: `1000-1031` in a command line would be a
range again, and §1's point is that the sets are sets.

**The command surface is declared here and is not yet implemented on this branch.** Revision 2's
harness (`devstage.py`, the three CLIs, the manifest generator, the seed files) lives on the
`f0-dev-protocol-freeze` line and does **not** carry over: it was written against the step-indexed future A91
retired. Bringing it forward is $F_0$'s *construction* work, and this section specifies it.

**The smoke gate suite is frozen, in order, as complete argv.** Asking `run_smoke.py` to "execute the frozen
gate suite" while the document never said which commands those are would hand the choice of gate to the
implementer, which is the same failure mode as an unfrozen grid:

$$\boxed{\mathcal G_{\text{smoke}} = \left(g_1, \ldots, g_6\right)}$$

| # | argv (exact, in this order) | artifact whose digest is recorded |
|---|---|---|
| $g_1$ | `python -m pytest -q` | --- (exit code only) |
| $g_2$ | `python scripts/spec_audit.py` | --- (exit code only) |
| $g_3$ | `python scripts/b2_view_gate_selfcheck.py` | `experiments/v03r/b2_view_gate_selfcheck.json` |
| $g_4$ | `python scripts/a91_training_gate_selfcheck.py` | `experiments/v03r/a91_training_gate_selfcheck.json` |
| $g_5$ | `python scripts/run_calibration.py` | `experiments/v03r/calibration_report.json` |
| $g_6$ | `python scripts/f0_manifest_selfcheck.py` | `experiments/v03r/f0_manifest_selfcheck.json` |

`run_smoke.py` **iterates this list and chooses nothing**: it records every exit code in order, computes the
digest of each artifact that has one, and writes both into the smoke report. The manifest records the same
list, a digest of the list itself, and its own copy of the exit codes and digests, so the two artifacts are
checkable against each other. $g_6$'s self-check belongs in the suite because the manifest is evidence; the
manifest's *generation* does not, because the manifest must already exist and be committed before smoke runs.

Beyond the suite, this section specifies the three commands:

* `run_dev_baseline.py` must acquire through `BaselineAcquisitionPlan` and the matrix contract of §3 --- the
  envelope is `ACQUISITION_CAP` training episodes per development seed, evaluated on the master bank, with
  `{V_{\sigma,e,u}}` stored --- not through a one-episode-per-seed probe;
* `run_dev_lock.py` must evaluate §4's rules on that acquisition and refuse rather than invent: every
  fail-closed outcome of §4 is a legal result of the lock, and none of them is an error;
* `experiments/v03r/evaluate_smoke_gate.py`, frozen with the smoke command, reads the smoke report plus the
  manifest and decides PASS or the first failed criterion mechanically.

Neither the scripts nor the manifest exist on this branch; the manifest table below is **rev 2's evidence
from a different line**, kept as history and to be regenerated on this line's own clean execution
revision.

* `run_smoke.py` must **execute and record the frozen gate suite** --- one exit code per gate command ---
  and compute the artifact digests, because §9's PASS criteria include both, and an empty `gate_exit_codes`
  would leave the decision to whoever read the file;
* `experiments/v03r/evaluate_smoke_gate.py`, frozen with the smoke command, reads that report plus the
  manifest and decides PASS or the first failed criterion mechanically;
* `run_dev_baseline.py` must acquire through `BaselineAcquisitionPlan` --- the envelope is
  `ACQUISITION_CAP` training episodes per development seed, evaluated on the master bank --- not through a
  one-episode-per-seed probe;
* `run_dev_lock.py` must evaluate §4's rules on that acquisition and refuse rather than invent: every
  fail-closed outcome of §4 is a legal result of the lock, and none of them is an error.

Neither the scripts nor the manifest exist on this branch; the manifest table below is **rev 2's evidence
from a different line**, kept as history and to be regenerated on this line's own clean execution
revision.

* each stage refuses to execute unless the manifest's `currently_authorises` contains its own stage name,
  and the refusal is a `ProtocolError` that writes nothing;
* every stage has a `--plan` mode that validates its inputs, prints the plan, runs no episode and writes no
  artifact -- which is what the gates exercise, so the gates themselves draw no seed;
* the smoke report's key set is asserted to be exactly the operational field set of §9.

$$\boxed{\texttt{currently\_authorises} = [\,] \quad \text{until a reviewer marks } F_0\ \text{VALID}}$$

**The rev 3 manifest contract, which the generator must implement rather than inherit.** The manifest
of this revision must record, at minimum: the **balanced ordering algorithm and its digest** (the cell
order and the two strides, plus a digest of the resulting $5760$-unit permutation), the **prefix summaries**
for $\mathcal C_{N_{\text{eval}}}$ (each candidate's size and its stratum-coverage counts), the pre-data
constant block of §1 verbatim, the frozen grid templates' outputs at the locked $T^{*}$ once $F_1$ exists,
the master-matrix digest of the acquisition, the gate artifacts' digests and the runtime measurements of
§8. Revision 2's manifest recorded an **A88 lexicographic prefix** as the evaluation sample, which rev 3
replaced; a generator copied from that line would re-freeze the retired ordering, so the contract is written
here instead of being inferred from the old artifact.

**What the table below is.** It is **HISTORICAL REV 2 EVIDENCE**, produced on the `f0-dev-protocol-freeze`
line and *not* evidence about this revision: the scripts, the seed files and the manifest do not exist on
this branch, and the digests are rev 2's.

**HISTORICAL REV2 CONTRACT --- NOT A REV3 REQUIREMENT.** The bullets that follow described revision 2's
generator, and one of them required the evaluation sample to be "A88 §76.2's lexicographic order", which
rev 3 replaced with the balanced ordering. They are kept, verbatim, as history rather than as instructions:

* *(rev 2)* asserts that the code tree is clean --- only the manifest output file itself may be dirty --- so a
  manifest cannot be produced from an uncommitted instrument;
* *(rev 2)* records the execution revision: the commit whose tree the scripts of §7 run from;
* *(rev 2)* fingerprints the harness --- every `scripts/run_*.py` and the two declared seed files, by content
  digest;
* *(rev 2)* asserts and records the evaluation sample of §3 as **A88 §76.2's lexicographic order** ---
  **superseded**: rev 3's manifest records the balanced ordering algorithm, its digest and the candidate
  prefix summaries instead;
* *(rev 2)* separates authorisation by validity: `"currently_authorises": []` /
  `"authorises_on_validity": ["smoke5"]` --- **still current**, and restated in the rev 3 contract above.

**The manifest and smoke report store different halves of the gate evidence.** The manifest cannot know a
future smoke run's exit codes, so the split is frozen rather than left to the harness:

$$\boxed{\text{the manifest stores } \mathcal G_{\text{smoke}}, \text{ the command-list digest, and the
}\textbf{ expected}\text{ artifact digests}}$$

$$\boxed{\text{the smoke report stores the }\textbf{ actual}\text{ exit codes and the }\textbf{ actual}
\text{ artifact digests}}$$

and `evaluate_smoke_gate.py` checks exactly three things: the command lists are equal, every actual exit
code is $0$, and every gate with an artifact has `actual digest == manifest's expected digest`. That is why
$\S$7 excludes manifest *generation* from the suite: the manifest is the expectation, the smoke report is
the observation, and neither has to predict the other. If a future revision wants the manifest to carry
preflight exit codes as well, they must be labelled as construction-time results of a non-scientific
benchmark run, never as a smoke invocation's.

As generated on this revision's execution commit:

**HISTORICAL REV2 EVIDENCE --- NOT CURRENT $F_0$ EVIDENCE**

| recorded quantity | value |
|---|---|
| execution revision | `9820209`, code tree clean, closure `a4451cc` an asserted ancestor |
| generator | `scripts/f0_manifest.py`, digest `fa4c804d0a…` |
| instrument sources | 54 files, tree digest `196a06b206…` |
| run harness | 5 run scripts, tree digest `2c3bb7b9d2…`, with the two seed-set files in the same block |
| test inventory | 721 collected node ids, digest `ee6336a1a5…` |
| evaluation sample | $\lvert U_2 \rvert = 5760$, $N_{\max} = 1024$, first-$N_{\max}$ digest `43c4a6011c…` |
| reference artifact | digest `01bb5c97d2c9bbf6552dbe4d3017e17162bddd7ac5344583d169da2f573061ae` |
| calibration artifact | digest `c3a58df529…`, 18/18 CALIBRATED, worst absolute gap `4.44e-16` |
| screening artifact | digest `1d493488d9…`, six cells, five non-rejected, `UNIFIED_SURVIVES` |
| mutation artifact | digest `671fa421a1…`, 45/45 `GATE_IS_REAL` across 31 distinct gates |
| runtime benchmark | $1024$ scenes in `0.063529 s`, seedless, from which §8's bounds follow |

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

## 8. Runtime bound, derived from two measurements

$$\boxed{B_{\text{stage}} = 2\left(T_{\text{suite}} + 10\,T^{\text{op}}_{\text{bench}}\right)
\qquad \texttt{[PROPOSED, derived from two measurements]}}$$

$$\boxed{T^{\text{op}}_{\text{bench}} = \text{the deterministic non-scientific benchmark of §1, run with }
\mathcal B_{\text{bench}}}$$

| stage | bound |
|---|---|
| smoke (five seeds) | `[PROPOSED]` $\left(T_{\text{suite}} + 10\,T_{\text{bench}}\right) \times 2$ --- about $220$ s at the rev-2 measurements $T_{\text{suite}} \approx 110$ s, $T_{\text{bench}} \approx 0.064$ s |
| development baseline acquisition | `[PROPOSED]` the same rule with the acquisition's own measured benchmark |

Revision 2's $30$ s bound could not contain the **mandatory** full-suite criterion of §9 --- a passing smoke
would not have fitted inside its own budget --- which is why the construction review rejected it. The rule
is stated over *both* measurements rather than over the workload alone, and both are to be re-measured on
this line's execution revision before the bound is ratified.

| stage | old rule (`[HISTORICAL rev 2]`) |
|---|---|
| smoke (5 seeds) | $\max(30\ \text{s},\ 100 \times \text{benchmark})$ |
| development baseline acquisition | $\max(300\ \text{s},\ 100 \times \text{benchmark})$ |

The old rule and its floors are kept **only as history**: it was computed from a benchmark that measured a
single $1024$-scene rollout pass, and its $30$ s smoke bound could not contain the mandatory gate suite, so
it cannot be the rev 3 rule. It is recorded rather than silently deleted because §12's log refers to it.

**What $T^{\text{op}}_{\text{bench}}$ must measure, per stage.** For smoke it is the smoke workload's
own pass; for the development baseline it must represent **A91's master acquisition**
(`acquire_master_baseline`: one training run per development seed to `ACQUISITION_CAP`, evaluated on the
master bank), not the retired $1024$-scene single-rollout probe. Both are `[PROPOSED]` until measured on
this line's execution revision, neither may be inferred from rev 2's numbers, and both draw their keys from
$\mathcal B_{\text{bench}}$ --- so "must represent the real keyed acquisition" and "must not touch a
scientific seed" hold together instead of contradicting each other.

The benchmark is **deterministic and non-scientific**, not "seedless": it draws its keys from
$\mathcal B_{\text{bench}}$ of §1, so it exercises the real keyed acquisition while touching no scientific
seed, and it may never produce a scientific artifact. Revision 3 called it "seedless" while also requiring it
to represent `acquire_master_baseline`, which A91 makes key-dependent; the construction review caught the
contradiction, and the name and the rule are corrected together here.

A bound is a smoke *criterion*: exceeding it fails smoke, and no bound is a target to be met by shrinking
the work.

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
(NONEXISTENT/OPEN), and does not enter $U_3$. Its validity is a precondition for smoke, not for
development: development waits on smoke's operational PASS.

## 11. Ratification checklist

| # | item | state |
|---|---|---|
| 1 | $\mathcal S_{\text{smoke}}$, $\mathcal S_{\text{dev}}$ and disjointness | **APPROVED** |
| 2 | $\mathcal C_C$, $\mathcal C_R$ membership | **APPROVED** |
| 3 | $\mathcal C_{N_{\text{eval}}} = \{100,256,512,1024\}$ and the **balanced** ordering of §3 | membership **APPROVED**; ordering `[PROPOSED]`, with the prefix-coverage claim verified |
| 4 | $\mathcal C_{\mathcal G}$: the three **dense-early grid transformations** of `05` §6.2 with $0, T, K \ge 3$ | `[PROPOSED]`, contract verified for $T \in \{12,20,40,120,500,1200\}$ |
| 5 | $\texttt{ACQUISITION\_CAP} = 40$ (pre-data) and its fail-closed consequence | `[PROPOSED]` |
| 6 | $f_T$'s ceiling integerisation, nearest-rank quantile, mechanical censoring | **APPROVED** (censoring) / `[PROPOSED convention]` |
| 7 | $f_N$'s metric on the balanced sample, $\theta_N = 0.25$, smallest-first | `[PROPOSED]` |
| 8 | $f_G$'s metric with **A84's trapezoidal reading**, scales $T^{*}/1$, $\theta_G = 0.05$, coarsest-first | `[PROPOSED]` (step-hold withdrawn) |
| 9 | $f_C$'s $U_2$ ontology, **coverage as a descriptor**, the $m_C$ formula, $\theta_C = 1.0$, smaller-first | `[PROPOSED]` (both floors withdrawn) |
| 10 | $f_R$'s parameters $H^{*} = T^{*} = \texttt{grid}[-1]$, $(H_1^{*}, H_2^{*}) = (\texttt{grid}[-3], \texttt{grid}[-1])$ | `[PROPOSED]`, contingent on the grid |
| 11 | $f_R$'s metrics: closed relative range, **per-seed** redundancy over $\mathcal S_{\text{dev}}$, $\max\lvert\rho\rvert \le 0.9$, undefined $\Rightarrow$ inadmissible | `[PROPOSED]` |
| 12 | registry keys $(\text{regime}, \text{statistic})$; the `(T, RMST)` alias | **APPROVED** |
| 13 | the `(T, DeficitAUC)` role, sharing $0.01$ with its own identity | **APPROVED** |
| 14 | $d_{(P,\mathrm{RMST})} = 1.5$ | `[PROPOSED — needs an independent rationale]`; the $K/2$ argument is withdrawn |
| 15 | $d_{\text{DeficitAUC}} = 0.01$ as an inherited default | **APPROVED** |
| 16 | `(P, BehavioralCollateral)` and `(P, Retention)` derived bounds | `[PROPOSED, derived]` |
| 17 | the runtime bound of §8 and the smoke PASS **evidence path** of §9 | `[PROPOSED]`; the bound must contain the mandatory gate suite |
| 18 | §4.0 conventions, smoke PASS criteria and artifact surface | **APPROVED** (carried from rev 1) |
| 19 | the execution revision, the clean-tree assertion and the manifest's authorisation fields | computed at the execution revision; reviewer verifies |
| 20 | the ten pre-existing CRLF artifacts | **APPROVED** as ledger treatment |
| 21 | **the episode index of a baseline curve** (§3) | **RESOLVED by A91**, FROZEN at `3f02724`, instrument closed at `b35f649`; this document consumes `train_curve` / `FutureTrainingProtocol` |
| 22 | the pre-data constant block of §1 ($\alpha$, $\varepsilon_{\text{explore}}$, $\epsilon_s$, $\epsilon_f$, `ACQUISITION_CAP`) with each value, type and provenance | `[PROPOSED]` values; A91 §79.4(f) fixes four of the domains ($\alpha$, $\varepsilon_{\text{explore}}$, $\epsilon_s$, $\epsilon_f$), while the cap's positive-integer domain comes from this document |

## 12. Revision log

**rev 3 (this revision) — the design freeze on top of a closed instrument.** Written after A91 reached
`CLOSED@b35f649` and was promoted to `rebuild@b5c5762`, which is the base of this branch: the episode axis,
the ordinary-learning transition system and the runner integration are frozen elsewhere and are **consumed**
here rather than re-specified. This revision applies the review's remaining rulings:

* the **balanced** master evaluation ordering replaces A88's lexicographic prefix, and its prefix-coverage
  claim was verified before it was written down (a permutation of all $5760$ units; every candidate prefix
  covers all strata and all $60$ cause ranks);
* the grid universe is the three **dense-early grid transformations** of `05` §6.2, replacing the $T/2, T/3, T/4$
  split, with the contract verified for six horizons;
* $f_G$ reads grids with **A84's trapezoidal rule**; step-hold is withdrawn;
* $f_C$'s coverage becomes a descriptor and both floors are withdrawn; its stability metric becomes the
  per-site standard-error ratio $m_C$;
* $f_R$'s redundancy moves to the **per-seed** values over $\mathcal S_{\text{dev}}$, where
  `restricted_time` and `DeficitAUC` exist, because no per-scene RMST series does;
* the endpoint registry keeps $(\text{regime}, \text{statistic})$ keys, `(T, DeficitAUC)` is approved with
  its own identity, and $d_{(P,\mathrm{RMST})}$'s $K/2$ rationale is withdrawn pending an independent one;
* the envelope cap is renamed to one name (`ACQUISITION_CAP`) and tied to `BaselineAcquisitionPlan`, and
  checklist item 21 is closed by A91.

The remaining work before this document can be VALID is stated where it belongs rather than implied:
the design stage is executable only through the frozen instrument, and the construction path is
`BaselineAcquisitionPlan` $\to$ `acquire_master_baseline` --- **not** `train_curve`, which takes the
post-$F_1$ `FutureTrainingProtocol` that does not exist before the lock (§7). So §7's command surface must be
brought onto A91 (the smoke path must execute and record the gate suite, and `run_dev_baseline.py` must
acquire the master matrix plus the eligibility material), and the bound of §8 must be re-derived from that
harness's own measurements. That is implementation work of $F_0$'s
*construction*, not a further design choice.

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
