# 20 — $F_0$: the development protocol freeze (draft for review)

**Status: `DRAFT FOR REVIEW`. Not valid, so nothing downstream of it is authorised.**

$$\boxed{\text{A90 FROZEN} \;\Longrightarrow\; F_0\ \text{may be constructed and reviewed}}$$

$$\boxed{\text{A90 FROZEN} \;\land\; F_0\ \text{VALID} \;\Longrightarrow\; \texttt{smoke5}\ \text{authorised}}$$

This document *is* the $F_0$ A90 §78.3 requires, written as a single artifact: exact seed sets, four
candidate universes, the complete design-rule family with its numerical conventions, the dependency graph
of the lock, the endpoint registry with one threshold provenance per endpoint, the master acquisition
envelope and its ordering, the commands and artifact paths, the instrument hashes, the runtime bound, and
the smoke PASS criteria with its artifact surface.

**Values marked `[PROPOSED]` are proposals for ratification, not frozen numbers.** A90 forbids this
document from inventing a designer's judgement, so every such value is declared as a proposal with its
rationale and listed again in §11, which is the checklist a reviewer works through. Everything not marked
`[PROPOSED]` is either derived from a frozen constant or is the *form* of a declaration, and is
checkable as written.

---

## 1. Seed sets

| set | purpose | value |
|---|---|---|
| $\mathcal S_{\text{smoke}}$ | instrument smoke | five seeds: `{0, 1, 2, 3, 4}` `[PROPOSED]` |
| $\mathcal S_{\text{dev}}$ | development stage | thirty-two seeds, enumerated below `[PROPOSED]` |
| $\mathcal S_{\text{confirm}}$ | confirmatory stage | **not declared here**; declared in its own authorisation |

```
S_dev = {1000, 1001, 1002, 1003, 1004, 1005, 1006, 1007,
         1008, 1009, 1010, 1011, 1012, 1013, 1014, 1015,
         1016, 1017, 1018, 1019, 1020, 1021, 1022, 1023,
         1024, 1025, 1026, 1027, 1028, 1029, 1030, 1031}
```

Both are **sets**, written element by element: neither is a range and neither is a stopping rule. A
seed that smoke drew may not later serve as a development input. The two sets are also written to
`experiments/v03r/smoke_seeds.txt` and `experiments/v03r/dev_seeds.txt`, which the run commands of §7
consume, so the drawn set and the declared set are the same bytes.

$$\boxed{\mathcal S_{\text{smoke}} \cap \mathcal S_{\text{dev}} = \varnothing}$$

$$\boxed{\mathcal S_{\text{confirm}} \cap \left(\mathcal S_{\text{smoke}} \cup
\mathcal S_{\text{dev}}\right) = \varnothing}$$

*Rationale for the proposal*: the two sets are disjoint by construction, far apart so a mistyped seed is
visible, and neither is a prefix of the other's range. The sizes (5 and 32) are not proposed here: they
are A79's.

## 2. Candidate universes, exhaustively named

$$\boxed{\mathcal C_C = \{\texttt{eligible\_all},\ \texttt{eligible\_phase\_even},\
\texttt{eligible\_phase\_odd},\ \texttt{eligible\_cause\_rank\_lower},\ \texttt{eligible\_error\_absent},\
\texttt{eligible\_base\_option\_nonzero}\}}$$

the six calibrated refinements of A89, all admissible at the frozen calibration.

$$\boxed{\mathcal C_R = \{\texttt{RetentionAtH},\ \texttt{LateWindowRetention}\}}$$

the two registered Retention forms. `RetentionFraction` is **excluded by role**: it is registered as a
`CONDITIONAL_DIAGNOSTIC` and is not a candidate, which is a fact about the registry rather than about any
result.

$$\boxed{\mathcal C_{N_{\text{eval}}} = \{256,\ 512,\ 1024\}} \quad \text{[PROPOSED]}$$

$$\boxed{\mathfrak G^{\text{master}} = (0, 5, 15, 40)} \quad \text{[PROPOSED]} \qquad
\mathcal C_{\mathcal G} = \{\mathfrak G^{\text{master}},\ (0, 15, 40),\ (0, 40)\}$$

so every grid candidate is a declared projection of the master rather than something constructed after the
data was seen.

## 3. The master acquisition envelope

$$\boxed{\text{one acquisition} \quad D^{\text{master}}_{\text{dev,baseline}} \quad \text{on the envelope}}$$

* the **evaluation sample** is ordered by `(seed, episode)` ascending, so "the first $N$" has one meaning
  and each $N \in \mathcal C_{N_{\text{eval}}}$ is a prefix of that order;
* the **master grid** is $\mathfrak G^{\text{master}}$ above, and each $\mathcal G \in \mathcal C_{\mathcal G}$
  is the declared projection;
* the development stage acquires this envelope **once**, before $F_1$, and **runs no treatment arm**:
  $S_2$ produces baseline convergence, the static candidate properties and nothing else;
* "the grid looks thin, add checkpoints" is adaptive acquisition and is unavailable.

## 4. The design-rule family

Every rule is total on its input surface, with a fail-closed codomain, and declares its metric, its
admissibility threshold, its ranking rule, its tie-break, its missing-value behaviour and its
exact-equality behaviour. Thresholds marked `[PROPOSED]` are designer judgements; the rest inherit a
frozen constant or contract.

### 4.0 Numerical conventions binding every rule

Frozen here rather than inherited from a library, and applying to all six families:

* **exact equality meets the threshold**: `value ≤ θ` and `value ≥ θ` are inclusive comparisons in
  `float64`, so a candidate whose metric equals its threshold is admissible. Every rule below states its
  comparison in that inclusive direction, and none of them means "strictly";
* **no rounding before a comparison**: rounding is display-only, and a rounded number is never the number
  compared;
* **missing values are never imputed**: a rule whose required input is missing returns its fail-closed
  outcome, and computing the metric on a smaller sample is not an option;
* **every tie-break is an explicit total order** over the candidate's literal form, so no sort's stability
  and no dictionary iteration order decides anything;
* **one acquisition**: every ranking metric is computed from $D^{\text{master}}_{\text{dev,baseline}}$, and
  a gate that reads the frozen calibration artifact is reading static material rather than the envelope.

### 4.1 $f_T$ — the horizon

$$T = Q_{0.9}(T_{\text{conv}})(1 + h), \qquad h = 0.20$$

with $T_{\text{conv}}$ the baseline convergence times of $\mathcal S_{\text{dev}}$, and the finite-sample
quantile convention frozen here rather than inherited from a library:

$$\boxed{Q_{0.9}(x) = x_{(\lceil 0.9\,n \rceil)} \quad \text{on the ascending order statistics of } x}$$

i.e. the nearest-rank definition. With $n = 32$ this is $x_{(29)}$. Missing values are **not** imputed:
a missing $T_{\text{conv}}$ makes $f_T$ return `NO_ADMISSIBLE_T` rather than a value computed from a
smaller sample, and an exact tie is resolved by taking the lower order statistic only if the tie spans the
rank -- the rule is stated so that no tie-break is left to a sort's stability.

### 4.2 $f_N$ and $f_G$ — the design quantities

$$f_N:\ D^{\text{master}}_{\text{dev,baseline}} \to \mathcal C_{N_{\text{eval}}} \cup
\{\texttt{NO\_ADMISSIBLE\_N\_EVAL}\}$$

$$f_G:\ D^{\text{master}}_{\text{dev,baseline}} \to \mathcal C_{\mathcal G} \cup
\{\texttt{NO\_ADMISSIBLE\_GRID}\}$$

* **metric**: the *baseline stability* of the reported curve under each candidate -- the relative spread
  of the level curve across the candidate's checkpoint set, computed on baseline episodes only;
* **admissibility threshold**: a candidate is admissible when its spread is at most `0.05` `[PROPOSED]`
  of the baseline's own level;
* **ranking**: smallest spread first; **tie-break**: the largest candidate (more evaluation is preferred
  when stability does not separate them), then lexicographic by the candidate's literal form;
* **missing values**: a candidate whose curve cannot be computed on the envelope is inadmissible, and if
  none is admissible the rule returns its `NO_ADMISSIBLE_*` outcome rather than the least bad candidate.

### 4.3 $f_C$ — the refinement

Input surface: $\mathcal C_C$ and the static properties of §78.6. Each property's instrument, its allowed
input surface and its role, frozen -- A90 §78.3 requires the surfaces to be declared, because a property
that may read an arm is not available at $F_1$ whatever its name:

| property | instrument | allowed input surface | role |
|---|---|---|---|
| synthetic spillover sensitivity | A89's eighteen-cell calibration: $\lvert B^{ref}\rvert$ and its measured counterpart | the frozen calibration artifact (static) | **gate**: 18/18 licenses measurability; magnitudes never rank |
| coverage | `|C_i(c)|`, the calibrated refinement's credited-unit count per $c$ | the envelope, baseline traces | static descriptor + admissibility floor |
| interpretability | the candidate's rule as a declared field-semantic predicate over `(s, z, m)` | static (source-level) | **gate**: no fitted quantity may appear |
| baseline stability | relative spread of the level curve across the candidate grid, baseline episodes only | the envelope | dev-estimated ranking metric |

* **admissibility floor (coverage)**: `|C_i(c)| ≥ 32` for every credited unit `[PROPOSED]`;
* **ranking**: baseline stability, larger first; **tie-break**: `eligible_all` before any slice, then the
  order of $\mathcal C_C$ as written above (declared, so no judgement enters after the numbers);
* **fail-closed**: if no candidate clears the gate and the floor,
  `NO_ADMISSIBLE_REFINEMENT` -- and then no primary refinement, and therefore no confirmatory stage.

### 4.4 $f_R$ — the Retention form

Input surface: $\mathcal C_R$ and **baseline/static diagnostics only** (A90's amendment to A79 §67.5;
a treatment-arm input would need a further amendment).

* **stability**: instrument = the form's own `.value` on baseline episodes; metric = the relative range of
  those values across the candidate grid's cells, `(max − min) / median` `[PROPOSED]`; allowed input
  surface = the envelope, baseline episodes only; admissibility threshold `0.10` `[PROPOSED]`, inclusive;
* **interpretability**: **gate** -- the form's estimator must be expressible as a declared functional of
  the episode record, with no fitted quantity;
* **redundancy with RMST and with DeficitAUC**: computed on baseline episodes as the absolute Spearman
  correlation between the form's value and each of the two endpoint values; a form is admissible when
  `max(ρ) ≤ 0.9` `[PROPOSED]`, i.e. it must not be a re-parameterisation of an endpoint it would then
  duplicate in the verdict;
* **ranking**: lower `max(ρ)` first; **tie-break**: the order of $\mathcal C_R$ as written;
  **fail-closed**: `NO_ADMISSIBLE_RETENTION`, with the same consequence as `f_C`'s failure.

### 4.5 $\{f_{\Delta,e}\}$ — the thresholds

One per endpoint of §5, each either a constant declared here or a frozen function instantiated at $F_1$
(§6). No new judgement may appear at the lock.

## 5. The endpoint registry $\mathcal E_\Delta$

A79 §67.3 fixes the first two; the rest are the endpoints the instrument reports.

| endpoint | identity | threshold provenance |
|---|---|---|
| `RMST` | $\mathrm{RMST}(T_{\max})$, primary | $d_{\mathrm{RMST}} = 1.5$ episodes `[PROPOSED]` [designer judgement] |
| `DeficitAUC` | normalised deficit integral, mandatory co-primary | $d_{\text{DeficitAUC}} = 0.05$ `[PROPOSED]` [designer judgement] |
| `BehavioralCollateral` | the A89 metric over the selected refinement | $g$: the collateral threshold is the frozen quantile of its **baseline** sampling spread, `g = Q_{0.95}(\lvert\text{spread}\rvert)` on the envelope [derived] |
| `RetentionAtH` / `LateWindowRetention` | exactly one is a registry member: **the form $f_R$ selects is in $\mathcal E_\Delta$, under that form's own registered name** | $g$: one half of $d_{\mathrm{RMST}}$ expressed on the selected form's own units, `g = 0.5 × d_RMST` [derived] |
| `T_regime_harm` | the harm constraint of A79 §67.11 | **proposed: it reuses the frozen `RMST` entry and its bound, and introduces no second threshold identity** — so it adds no row to the registry [PROPOSED — reviewer] |

$$\boxed{\{\mathrm{RMST},\ \mathrm{DeficitAUC}\} \subseteq \mathcal E_\Delta}$$

$$\boxed{\forall e:\ e\ \text{uses } \Delta_{\min}\ \text{in a confirmatory verdict or bound}
\;\Rightarrow\; e \in \mathcal E_\Delta}$$

$$\boxed{\forall e \in \mathcal E_\Delta:\ \text{exactly one threshold provenance}}$$

No dimension label appears in the registry: `BehavioralCollateral` and the selected form's own name are
endpoint names, and `FutureUtility` is not an endpoint at all -- it is the dimension whose two endpoints
are `RMST` and `DeficitAUC`. The `T_regime_harm` proposal is the one place where a reviewer's judgement is
still needed: ratifying it leaves the registry at four distinct endpoint identities (the fifth row being
`RMST` again), and refusing it requires that constraint to be listed as its own endpoint with its own
$d_e$ and rationale, since an unnamed threshold identity would violate
$\forall e \in \mathcal E_\Delta$: exactly one provenance.

## 6. The dependency graph $\mathcal D_{F_1}$

$$\boxed{\mathcal D_{F_1}\ \text{is acyclic}}$$

$$\boxed{F_1^{\text{design}} = \operatorname{Eval}\bigl(f_T,\ f_N,\ f_G,\ f_C,\ f_R;\
D^{\text{master}}_{\text{dev,baseline}}\bigr)}$$

$$\boxed{F_1^{\text{threshold}} = \operatorname{Eval}\bigl(\{f_{\Delta,e}\}_{e \in \mathcal E_\Delta};\
F_1^{\text{design}}\bigr)}$$

Edges: the envelope feeds $f_T, f_N, f_G, f_C, f_R$; their outputs feed every *derived* $f_{\Delta,e}$;
a designer-constant threshold has no upstream dependency. The two stages live in **one** $F_1$ commit, so
"frozen together" holds; nothing between them may read an arm, be revised by hand, or move to a second
commit.

## 7. Commands, paths, and the instrument hashes

| what | command | artifact |
|---|---|---|
| smoke | `python scripts/run_smoke.py --seeds-file experiments/v03r/smoke_seeds.txt` | `experiments/v03r/smoke_report.json` `[PROPOSED path]` |
| development baseline | `python scripts/run_dev_baseline.py --seeds-file experiments/v03r/dev_seeds.txt` | `experiments/v03r/dev_baseline.json` `[PROPOSED path]` |
| the lock | `python scripts/run_dev_lock.py --design experiments/v03r/dev_baseline.json` | `experiments/v03r/dev_lock.json` `[PROPOSED path]` |

The seed sets of §1 are written to `experiments/v03r/smoke_seeds.txt` and `experiments/v03r/dev_seeds.txt`,
and the commands consume those files rather than a re-typed range: `1000-1031` in a command line would be a
range again, and §1's point is that the sets are sets.

Neither `run_smoke.py`, `run_dev_baseline.py` nor `run_dev_lock.py` exists yet: writing them is
implementation work that A90's freeze does not authorise by itself, and this document therefore records
the paths they will use rather than pretending they exist. The frozen instrument's fingerprints are in
`experiments/v03r/f0_manifest.json`, generated by `scripts/f0_manifest.py`, which asserts each invariant
it records -- closure ancestry, the calibration summary, the screening verdicts, the mutation counters --
so a wrong tree cannot produce a well-formed manifest. As of this draft:

| recorded quantity | value |
|---|---|
| tree | `head = 507bc90` — the draft commit `f0_manifest.py` was last run on — on branch `f0-dev-protocol-freeze`, with closure `a4451cc` an asserted ancestor |
| generator | `scripts/f0_manifest.py`, digest `81b3a81c04…`; Python 3.14.3, Windows 11 |
| instrument sources | 53 files, tree digest `7a81be3687…` |
| test inventory | 694 collected node ids, digest `ed66e1ea03…` |
| reference artifact | digest `01bb5c97d2c9bbf6552dbe4d3017e17162bddd7ac5344583d169da2f573061ae` |
| calibration artifact | digest `c3a58df529…`, 18/18 CALIBRATED, worst absolute gap `4.44e-16` |
| structural screening artifact | digest `1d493488d9…`, six cells, five non-rejected, `UNIFIED_SURVIVES` |
| mutation artifact | digest `671fa421a1…`, 45/45 `GATE_IS_REAL` across 31 distinct gates, tree restored byte-identical |
| measured runtime | eighteen-cell calibration `92.42 s`; full suite (`694` tests) `223.15 s`, both exit 0 |

Re-running the calibration reproduced its committed artifact **byte for byte**, which is the determinism
the noise tape is supposed to give; the digests above are therefore fingerprints of a reproducible run
rather than of one lucky execution.

The generator's own assertions are mutation-verified rather than asserted to be strong:
`scripts/f0_manifest_selfcheck.py` corrupts one input at a time -- the closure commit, the calibration
counter, the mutation-power counter, the screening verdict's key, the line endings of a hashed artifact,
the test listing, and the fail-closed write -- and requires the generator to exit non-zero **with the
expected message**, while a mutation-free run must stay green and the tree must come back byte-identical.
It reports `7/7` gates red, control run ok, tree restored, in
`experiments/v03r/f0_manifest_selfcheck.json`.

**Line endings are part of a fingerprint.** `.gitattributes` declares `* text=auto eol=lf`, so a committed
blob is LF whatever a working tree materialises; a digest taken from a CRLF working-tree file is therefore
a digest of one machine rather than of the revision. The manifest asserts that each artifact it hashes is
CRLF-free, and the self-check mutation `artifact_not_lf` proves that assertion goes red. Recording this
found a defect in this very draft: the first generation wrote its artifacts through Python's default
newline translation, so `f0_manifest.json` and `f0_manifest_selfcheck.json` were CRLF on disk while their
blobs were LF. Both are now written with `newline="\n"`, and the manifest reports the ten *pre-existing*
artifacts still carrying CRLF on disk in `repo.crlf_artifacts_on_disk`. Those ten belong to earlier arrows;
they are listed rather than rewritten, because rewriting them would change working-tree bytes that those
arrows produced, and because any digest previously quoted from one of them is a working-tree digest. No
frozen text cites one today -- the three artifacts this protocol hashes are all LF -- but the ledger should
carry the finding.

## 8. Runtime bound

| stage | bound |
|---|---|
| smoke (5 seeds) | `900 s` `[PROPOSED]` |
| development baseline acquisition | `7200 s` `[PROPOSED]` |

*Rationale*: the reference is the measured cost of the existing seedless runs recorded in §7 -- the
eighteen-cell calibration at `92.42 s` and the 694-test suite at `223.15 s` -- and each bound is proposed
as a generous multiple of the nearest one, so that a smoke failure means "the instrument is broken" rather
than "the machine was busy". A bound is a smoke *criterion*: exceeding it fails smoke, and no bound is a
target to be met by shrinking the work.

## 9. Smoke PASS criteria, and the smoke artifact surface

All of these are **operational or instrumental**; none may depend on a treatment effect:

1. every gate green: the full suite exits 0 at the frozen tree;
2. every artifact written at its declared path, with a valid JSON parse;
3. no exception, no fallback, no `NO_ADMISSIBLE_*` outcome taken anywhere;
4. runtime inside §8's bound;
5. the manifest's digests match the ones recorded here;
6. the smoke report's schema is exactly the operational field set below.

**Smoke's artifact surface** is the operational field set

```
{stage, seeds, tree, runtime_s, gate_exit_codes, artifact_paths, artifact_digests,
 errors, fallbacks}
```

with **no** efficacy field of any kind -- no arm contrast, no interval, no effect size, not even
optionally. `not shown` is not `not reachable`, so the surface itself excludes what the boundary excludes.

**Invalidation.** Any change to code, configuration or instrument invalidates these digests: the gates
must be re-closed, this protocol re-frozen, and smoke re-run. A repaired instrument may not inherit the
old PASS.

## 10. What this document does not do

It authorises no seed. It does not declare $\mathcal S_{\text{confirm}}$, does not select a refinement or
a Retention form ($F_1$ computes those), does not name $N_{\text{train}}$ (NONEXISTENT/OPEN), and does not
enter $U_3$. Its validity is a precondition for smoke, not for development: development waits on smoke's
operational PASS.

## 11. Ratification checklist

For $F_0$ to become VALID a reviewer confirms, and may correct:

| # | item | state |
|---|---|---|
| 1 | $\mathcal S_{\text{smoke}}$, $\mathcal S_{\text{dev}}$ values and disjointness | `[PROPOSED]` |
| 2 | $\mathcal C_{N_{\text{eval}}}$, $\mathfrak G^{\text{master}}$, $\mathcal C_{\mathcal G}$ | `[PROPOSED]` |
| 3 | $f_T$'s quantile convention (nearest rank, $x_{(29)}$ at $n{=}32$) | `[PROPOSED convention]` |
| 4 | $f_N$/$f_G$ thresholds (`0.05`), ranking and tie-break | `[PROPOSED]` |
| 5 | $f_C$'s property instruments, allowed input surfaces, coverage floor (`32`), ranking and tie-break | `[PROPOSED]` |
| 6 | $f_R$'s metrics ($(max{-}min)/median$, $\max\lvert\rho\rvert$), thresholds (`0.10`, `0.9`), ranking and tie-break | `[PROPOSED]` |
| 7 | $\mathcal E_\Delta$ membership and the `T_regime_harm` reuse proposal | `[PROPOSED — reviewer]` |
| 7b | the numerical conventions of §4.0 (inclusive equality, no pre-comparison rounding, no imputation, explicit tie-breaks) | form frozen; checkable |
| 8 | $d_{\mathrm{RMST}}$, $d_{\text{DeficitAUC}}$ values | `[PROPOSED]` |
| 9 | artifact paths and the smoke/development commands | `[PROPOSED]` |
| 10 | runtime bound | `[PROPOSED]` |
| 11 | smoke PASS criteria and artifact surface | form frozen; set checkable |
| 12 | the instrument hashes in `f0_manifest.json` | computed; reviewer verifies |
| 13 | the generator's mutation self-check (`7/7` red, control green, tree restored) | recorded; reviewer verifies |
| 14 | the ten pre-existing CRLF artifacts listed in `repo.crlf_artifacts_on_disk` | flagged, not rewritten |
