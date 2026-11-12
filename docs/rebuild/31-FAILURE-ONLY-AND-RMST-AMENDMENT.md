# 31 — Failure-triggered RFL and the bounded RMST claim

## 1. Scope and authority

This is the explicit rev-5 correction requested by the researcher on 2026-09-27:
diagnose **why a task failed**, not why it succeeded. It also settles the C3
baseline declaration and withdraws the unsupported practical interpretation of
the proposed 1.5-episode RMST margin. It changes no archived observation.

The historical user statement is message 61, lines 18633–18637 of the supplied
September-19 transcript: successful outcomes can be accepted; detailed analysis
starts after a later similar failure. Assistant suggestions of reflection on
successful-but-surprising outcomes were not user requirements. The current user
instruction is stricter and governs this revision. Source identity and excerpts
are recorded in the experiment review's failure-only history report.

This amendment takes precedence over older generic practical-effect wording for
the **RMST rows only**. It does not silently ratify an F0 manifest. Source-bound
review, passing engineering gates and current full-envelope timing remain
mandatory. The former draft and prior timing evidence remain immutable history.

## 2. Failure is the diagnostic trigger

The outer task orchestrator observes a terminal task result. Native kernel
constants are strings: `SUCCESS`, `COLLISION`, `TRAP`, `TIMEOUT`. Unknown or
nonterminal values are protocol errors, never implicit failure or success.

| Observed result | Ordinary task learning | RFL diagnostic path |
|---|---|---|
| SUCCESS | Reward/TD learning and experience logging remain allowed | Skip cause inference, counterfactual queries, credit resolution, candidate selection and diagnostic edits |
| COLLISION / TRAP / TIMEOUT | Ordinary task learning remains allowed | May diagnose this failure, subject to the frozen information and query budget; choosing no edit remains valid |

The trigger must use the task's observed terminal result, not a hidden fault
mask, evaluator cause truth, reward-sign heuristic or conjecture that a success
was lucky. A success with a hidden fault still takes the success branch. A
failure need not imply learner blame or justify an edit.

This control decision stays outside inference-method envelopes. It does not
grant a method the evaluator's full trace, intervention state or hidden truth.
In a learned pipeline it must run **before constructing diagnostic evidence**.
`PairedRunner.run` additionally enforces the terminal-result boundary before
credit resolution and the B1 update pipeline. It is not itself a complete
V0.4R learning loop. Its private measurement core and the low-level B1 laws remain
available to instrument/calibration tests; they are not online trigger policies.

Success rate, healthy reference evaluation, recovery, Retention and Collateral
remain legitimate measurements. Checking whether a correction damaged a
previously successful task is not asking why that task succeeded. Ordinary Q
updates on successful trajectories also remain unchanged. No cross-experience
success reinterpretation or surprise-triggered success diagnosis is added here.

All diagnostic arms share this trigger. Prior all-DGP V0.1R instrument findings
retain their population and cannot be relabeled failure-conditional validation.
A failure-population validation is required before those learned components can
support the failure-only end-to-end claim. V0.2R's ontology census likewise stays
an offline census, not proof of an online trigger or learning benefit.

## 3. What 1.5 means now, and what it does not mean

No task utility model, measured diagnostic cost or theory in the supplied
evidence establishes 1.5 as a smallest practically important effect. K counts
checkpoints and cannot supply that rationale. Engineering wall time cannot
convert an RMST difference into net resource savings.

The number is therefore retained solely as a **predeclared quantitative benchmark
margin**, not as a scientifically derived practical-importance or equivalence
boundary. Keeping the already proposed value avoids inventing a new cutoff after
engineering runs. It defines a limited research question:

> On the locked recovery grid and frozen population, is the reference-minus-
> treatment restricted mean recovery time greater than 1.5 training episodes?

This is an effect-size question about this benchmark. Crossing the margin may
justify that numerical statement, conditional on all the existing statistical
and claim gates. It does not justify "useful in practice", "worth the diagnostic
cost", general equivalence, or a claim about exact episode-by-episode recovery.
The margin's provenance is a transparent research convention, not a universal
natural constant or a literature recommendation. The former requirement to
invent an independent *practical* rationale for this number is retired together
with that practical claim, not marked satisfied.

The policy is typed `benchmark-quantitative-margin-v1`, fixed at 1.5, with explicit
false flags for practical meaning, equivalence and zero-harm claims. A generic
`ratified=true` plus a nonempty rationale is no longer sufficient. The existing
six-row endpoint registry retains distinct P and T RMST identities and the same
numeric alias, but carries the revised claim semantics in both rows.

Let d = RMST(reference) - RMST(treatment), so positive values favor treatment.
For a valid interval [L,U], report:

| Label | Condition | Permitted interpretation |
|---|---|---|
| MARGIN_A | L > 1.5 | Positive difference exceeds the declared benchmark margin |
| MARGIN_B | U < -1.5 | Negative difference exceeds the declared benchmark margin |
| WITHIN_BENCHMARK_MARGIN | [L,U] is contained in [-1.5,1.5] | Interval is contained in this numerical band; no practical equivalence claim |
| INCONCLUSIVE | Otherwise | Margin claim unresolved |

The endpoint orientation must identify which named arm is treatment; callers
cannot infer it from lexical arm order. Equality at an outer margin is not a
strict margin exceedance. In regime T the tolerance stays separately identified:
a loss below this number is not zero harm, and a nonsignificant loss is not proof
of safety. Its separate numeric constraint is satisfied exactly when **L >= -1.5**,
using the same reference-minus-treatment interval and an inclusive boundary.
For example [-1,3] satisfies this T bound while its margin label is INCONCLUSIVE;
the four labels must not be used to guess the one-sided T decision. Failure to
satisfy the bound is unresolved or contrary evidence, never an automatic safety
finding. No automatic V0.4R authorization follows from either result.

All other endpoint definitions, margins, paired-seed units, final-look schedule,
Holm family, mandatory companion statistics and tail/direction diagnostics stay
in force. This amendment creates neither a new p-value-only rule nor an
alternative cutoff scan. A future practical-value claim requires a separately
declared cost/utility criterion before its scientific data, not relabeling this
study's quantitative finding.

## 4. C3 is the explicit current baseline

The stage baseline is `c3-temporal-layer-1-v1`, not the old calibration canary.
In each strict-gap reference row at time layer 1, choose the lowest-action-id
minimum-Q action and set it to b+(b-q), where b and q are the row maximum and
minimum. Other entries remain at reference values, all non-Q stores stay healthy,
and every run receives a fresh learner. The 840-edit construction was selected
structurally under document 25's declared rule; acquisition does not search layers.

The cap is 576 = 48×H with H=12, inherited from C3's predeclared engineering budget,
not a convergence or power guarantee. Alpha=1/2, exploration=1/10, epsilon_s=0.001
and epsilon_f=0.1 stay unchanged. The balanced 1024-scene master bank, full-U2
domains/incidence, every-episode axis and original fail-closed selectors remain.
Neither the engineering curves nor their recovery outcomes choose F1 values.

The earlier C1/C2/C3 construction sequence is disclosed exploration. It is not
evidence that C3 is optimal or representative of all naturally occurring failures.
Changing the stage initializer does not change the pair-local A91 transition
contract or the initial learner of every later scientific treatment pair.

## 5. Evidence binding and execution

The completed 37-key benchmark at instrument `7da3830` remains valid evidence
about that exact instrument: 5 smoke-shaped runs plus 32 serialized runs, with
full integrity verification. Its original sources, durations, hashes and keys
are never rewritten to claim it ran this amendment.

Rev 5 requires a **fresh** full-envelope benchmark after code, tests and protocol
are committed byte-identically. New operational keys are smoke 970001–970005 and
development-shaped 970006–970037, saved under `f0_runtime_rev5`. They are excluded
from scientific sampling along with all prior operational populations. There is
no timing-evidence migration exception. The former output directory is preserved.

The same six serial gates and the bound formula 2×(suite + 10×stage workload)
remain. This conservative bound is an abort criterion, not an expected duration.
Only a completed, source-matched measurement can enter the new manifest. A new
manifest is a new file; the old NOT_VALID draft is not overwritten. Finalization
requires a source-bound review, the typed RMST policy, exact gate digests, and
current measured runtime. These checks authorize only their named stages.

No formal scientific seed is drawn merely because the amendment is implemented.
After valid F0, smoke must pass before development; all selectors and thresholds
must succeed before the indivisible F1 lock. NO_ADMISSIBLE remains a valid stop,
including the already documented short-flat-window and Retention failure cases.
