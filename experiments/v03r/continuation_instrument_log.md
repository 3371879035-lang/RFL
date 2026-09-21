# Continuation instrument — implementation log (branch `a87-continuation`)

Not an amendment, and not scientific evidence: this file records **what the instrument work ran**, so
that a later reader does not have to infer it from a diff, and so that the authorisation boundary of
A87 §75.5 stays auditable.

## What ran

* deterministic gates only: `tests/rebuild/test_b2_continuation.py` — the entry contract, the
  $\lambda_{U_1}$ determinism gate, the AST gate that the instrument cannot reach `rollout` or
  `process_commit_provider`, G1–G5, and the mutation-power gate that kills four deliberately divergent
  instruments;
* the full suite, and the B2 mutation self-check (`scripts/b2_view_gate_selfcheck.py`) with its JSON
  artifact `experiments/v03r/b2_view_gate_selfcheck.json`. After the shared-core refactor the table is
  still **43/43 `GATE_IS_REAL`**, with the three relocated anchors re-targeted onto the moved wiring.

## One behavioural comparison did run, and is withdrawn

Revision `7f650b0`'s G1 asserted, on the frozen canary scenes,

$$\Sigma_{\text{suffix}}\bigl(\text{ordinary}(W^{cal}_A)\bigr) \neq
\Sigma_{\text{suffix}}\bigl(\text{ordinary}(W_{\text{pre}})\bigr)$$

as a non-vacuity check that the calibration write lands on the executed path. That is a **pre/post
behavioural movement diagnostic**, which A87's authorisation deliberately leaves to the screening, so
the closure patch removes it. Non-vacuity now rests on frozen structural facts instead: for $D_Q$ the
calibrated read path selects 4 at the frozen $x^{*}$ (and 3 before the write); for $X$ the frozen
`ControllerSite(START, 3)` maps to 4 and is the site the healthy path queries. No cross-arm behaviour
comparison remains in the gates.

## What did **not** run

* A86's structural screening: no $V_W^{meas} : U \to \mathbb{R}$ was formed, no domain-quantified
  $D_{A,U}$ was computed, no six-cell status matrix was produced, and no candidate was screened;
* no B2 scientific seed, no smoke-5, no development-32, and no V0.4R run.

## Closure patch (the P0 of the `7f650b0` review)

The instrument's public entry had kept two freedoms A87 had already frozen: an optional `reward_mode`
and any tape that merely matched the entry's phase. Both are now closed at the **measurement** entry
while the generic kernel core keeps them:

* `continuation(...)` takes no reward mode, and fixes `"A"` at the call (§75.3);
* `tape` must equal `exogenous_lift(state, z, m)` exactly; a phase-matching tape with a different
  `error_flag` or `cause_rank` is refused (§75.4);
* gates added: the refusal cases above, and an inspect-based gate that the signature carries no
  `reward_mode` and no `**kwargs`.
