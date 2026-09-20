# B2-4 draft handoff — the paired runner (development checkpoint, NOT evidence)

$$\boxed{\text{development checkpoint} \neq \text{scientific evidence}}$$

Nothing on this branch is a frozen revision, an implementation revision, or authorisation of any
seed. The frozen basis stays `rebuild @ 143e911`. This file exists so that a context-limited round
does not have to re-derive a design that was already verified end to end once: the runner below ran,
its ten gates passed, and the event order was measured. The mutation suite is the missing piece, and
one further gate is owed -- see "gate count" below.

## 1. What was measured (on the reverted draft)

Event order from the recorder, with one P-architecture pair:

```
['unaffected', 'update_applied', 'update_applied', 'exogenous', 'future', 'exogenous', 'future']
```

so $U_{\text{unaffected}}$ is built before any arm, and no future exists before both updates are
applied. Also measured: both pre-fingerprints equal; the unaffected set constructed exactly once and
the same object handed to the metric (id compared by spy); both `exogenous` events carry one id; the
record's field surface is exactly its ten public fields.

## 2. Interface constants that must not drift

* **CORRECTED after the `9bb04bf` review:** the architecture set is **not** `("P", "X")`. A79
  §67.7 freezes a complete $D_Q$ B2 row as well (L0 `FactualReturnWrite`, both L2 arms, the L3
  restore, each against its same-tier `NoWriteRef`), and A83 §71.1 authorises a treatment/reference
  pair **per cell** -- so `D_Q` belongs in the registry and in the dispatch. The original text below
  is kept only to show what the failed attempt assumed.
  Original (WRONG): `ARCHITECTURES = ("P", "X")`; `LAW_REGISTRIES = {"P": P_LAWS, "X": X_LAWS}`.
* `ArmSpec(name, architecture, tier, law)`. A law is frozen iff a registry entry matches: **class
  entries by identity, instance entries (A77 §65.3's per-cell `NoWriteRef`) by (type, tier)**. The
  instance rule is required, or a caller cannot build the reference arm at all. A lambda, a
  stand-in, a foreign architecture or a mismatched tier is refused.
* The runner dispatches itself to `run_process_law` / `run_controller_law`. No new update path, and
  no caller-supplied update callable (this is B2-1's provenance hole, on the update side).
* `EXOGENOUS_FIELDS = ("kappa", "phi", "tape", "base_option", "q_reference", "checkpoints")` —
  exactly. Shared exogenous randomness is not routing truth: no world/block/stratum/Γ* rides along.
* `PairedSceneRecord` fields: `arm_names, architecture, unaffected_construction, retention_form,
  future_utility, collateral, retention, ledgers, fingerprints_pre, observations` — three
  dimensions with the cost view beside them, and no composite name among them.
* **CORRECTED after the `9bb04bf` review:** `environment_factory` re-opens the provenance hole B2-2
  closed -- an outer closure can read $\Gamma^\ast$ and return a nominal `LearnerEnvironment` the
  AST audit never sees. The production path must accept only the audited environment.
  Original (WRONG): `PairedRunner.__init__(*, environment_factory, collateral_construction, retention_form,
  retention_params, recorder=None)`: the names and horizons are **required**, and the runner's own
  call sites pass the caller's `Name`, never a literal.
* `PairedRunner.run(state, *, arms, evidence, exogenous)` — deliberately **no** `domain`/`visited`
  parameters: the runner derives them itself from the pre-update state in `pre_update_source`.

## 3. The eleven mutations, by the property each proves

Temporal / pairing integrity:

| mutation | gate it must kill | declaration that should hold |
|---|---|---|
| `unaffected_constructed_after_treatment` | order gate | `assert names[0] == "unaffected"` |
| `per_arm_construction` | one-object identity gate | `assert len(seen) == 1` |
| `serial_arm_chain` | same-pre-state gate | `did not start from one pre-update state` |
| `paired_arms_use_different_future_noise` | CRN identity gate | `assert len(set(setup_ids)) == 1` |
| `future_before_update` | event-order gate | `assert first_future > last_update` |

Selection / dispatch integrity:

| mutation | gate it must kill | declaration that should hold |
|---|---|---|
| `runner_defaults_the_form` | signature-default gate | `inspect.signature(select_form).parameters` |
| `runner_defaults_the_construction` | signature-default gate | `inspect.signature(select_construction).parameters` |
| `arm_accepts_arbitrary_callable` | nominal registry gate | `DID NOT RAISE` |
| `arm_uses_wrong_architecture_registry` | the cross-architecture gate (owed, see below) | `not in the X registry` |

Information boundary / outcome space:

| mutation | gate it must kill | declaration that should hold |
|---|---|---|
| `runner_accepts_forbidden_exogenous_field` | closed-field gate | `DID NOT RAISE` |
| `runner_adds_composite_score` | three-dimension independence gate | `record.__dataclass_fields__` |

All declarations are to be **measured, then written** — a mismatch is corrected to what the run
prints, never accommodated by weakening the check.

## 4. Gate count: the closure target is eleven, not ten

The reverted draft had ten gates, and the ninth mutation above needs a case they do not yet cover:
a **P** law handed to an **X** arm (or the reverse), which the ten do not distinguish from an
ordinary stand-in. The closure target is therefore

$$\boxed{10\ \text{existing gates} + 1\ \text{cross-architecture registry gate} = 11}$$

*unless* the cross-architecture case is folded into the existing nominal-registry gate **and that
single gate is shown to kill both independent holes** -- arbitrary callable and wrong-architecture
registry -- with its own mutation each. Otherwise the count must read eleven, so that "the gates are
complete" and "every mutation has a gate" cannot disagree.

## 5. Working rule for this branch

Do **not** revert this branch when a round runs out of budget or time. Commit the unclosed state as
`draft: ...`, mark it `NOT evidence` exactly as `515c4e9` does, and continue from there. Only
`rebuild` has to stay frozen-clean: development progress and the scientific evidence chain must not
be traded against each other again.

## 6. Gate-writing discipline (three self-inflicted findings, same root cause)

Structure is checked by AST, signature, nominal type, dataclass field-set or object identity.
String search is for narrow static hygiene only, never for a semantic gate. Three times a textual
probe tripped on prose or on the implementation's own identifiers (`"b2 import testing"` inside a
comment, a comment mentioning the fixture module, `"apply("` matching the runner's own `_apply`).

## 7. Remaining work before `rebuild` may receive this

1. re-land the runner and the ten previously exercised gates, then add the owed cross-architecture registry gate -- eleven closure gates in total;
2. land the eleven mutations, each measured and declared;
3. full sweep: 637+ tests, nine self-check tables, `spec_audit`;
4. only then: one source closure commit on `rebuild` plus the D_patch evidence binding commit.

## 8. Review record: `9bb04bf` = source closure attempt, REVIEW FAIL

$$\boxed{9bb04bf = \text{B2-4 source closure attempt, REVIEW FAIL}}$$

$$\boxed{461fc25 = \text{binding mechanically valid, bound source not scientifically closed}}$$

`smoke 5`, `development 32`, confirmatory and V0.4R remain **not authorised**.

The distinction that matters, and that the attempt's own report got wrong: **43/43 GATE_IS_REAL
proves the gates are not decorative; it does not prove they cover the frozen contract.** The
mutation framework did its job -- it found two gate defects while the arrow was being written -- and
what this review found are questions the table never asked, not questions it asked and failed to
catch.

| severity | finding |
|---|---|
| P0 | the runner has **no $D_Q$ architecture** at all: `ARCHITECTURES` is `("P", "X")` and the dispatch has only the P and X entry points, while A79 §67.7 freezes the full $D_Q$ row |
| P0 | $\mathcal G_{\text{ckpt}}$ is **dead data**, and the axis is wrong: one `kernel.rollout()` is a single episode ("Run one episode"), yet its step sequence is relabelled `range(horizon)` and the runner relabels it again -- so $\tau$, DeficitAUC and Retention are not on the frozen future-episode axis. The regulation's own example ("recovered by 100, first measured at 250") is inexpressible |
| P0 | $V_{\text{pre}}$ is taken as `max(abs(v))` over the arm's **own post-update** curve, so the two arms can hold different recovery targets, each derived from its own result |
| P0 | `environment_factory` is an arbitrary callable, so the truth-provenance hole B2-2 closed is open again |
| P0 | Collateral's per-context $V$ is not measured: `levels[context.state.x % len(levels)]` is a time-to-context modulo adapter |
| P1 | pairing is not enforced: treatment/treatment passes (the attempt's own `writing_pair()` fixture is the counterexample) |

### The two findings that need a definition before code

Per the review, neither may be settled by implementation:

1. **the source of $V_{\text{pre}}$** -- the frozen text says "pre", the gates forbid producing a
   future before the update, and no frozen document names the observation object it is read from;
2. **the measurement interface for per-context future performance** -- Collateral's per-context $V$
   must come from the environment, not from an adapter.

### The `serial_arm_chain` repair that this review also implies

Observe the derivation directly: record the **parent object identity** of each clone and require
`calls == [id(state), id(state)]`. A content fingerprint of the parent was the wrong instrument --
it is what forced a `PId/PId` fixture into the gate, which violates the pairing contract the P1
finding is about. Fixing the gate this way removes the fixture as well.

### Closure conditions for the next attempt

Each needs a mutation that really goes red:

1. a real same-tier $D_Q$ reference/treatment pair runs through the B2 entry point, and wrong-$D_Q$
   dispatch is refused;
2. a **non-uniform** grid such as `(0, 5, 15, 40)` appears exactly in the production record's
   `t_index`, and substituting `(0, 1, 2, 3)` is refused;
3. both arms share **one real $V_{\text{pre}}$**, and deriving it from either arm's own future is
   refused;
4. an outer-audit malicious `LearnerEnvironment` subclass/factory is refused **before the mint**;
5. Collateral comes from measured per-context future performance, and the modulo adapter mutation is
   refused;
6. the pair is exactly `NoWriteRef(tier)` plus one substantive treatment; treatment/treatment and
   reference/reference are both refused.
