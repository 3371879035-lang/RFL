# B2-4 draft handoff — the paired runner (development checkpoint, NOT evidence)

$$\boxed{\text{development checkpoint} \neq \text{scientific evidence}}$$

Nothing on this branch is a frozen revision, an implementation revision, or authorisation of any
seed. The frozen basis stays `rebuild @ 143e911`. This file exists so that a context-limited round
does not have to re-derive a design that was already verified end to end once: the runner below ran,
its ten gates passed, and the event order was measured. The mutation suite is the missing piece.

## What was measured (on the reverted draft)

Event order from the recorder, with one P-architecture pair:

```
['unaffected', 'update_applied', 'update_applied', 'exogenous', 'future', 'exogenous', 'future']
```

so $U_{\text{unaffected}}$ is built before any arm, and no future exists before both updates are
applied. Also measured: both pre-fingerprints equal; the unaffected set constructed exactly once and
the same object handed to the metric (id compared by spy); both `exogenous` events carry one id; the
record's field surface is exactly its ten public fields.

## Interface constants that must not drift

* `ARCHITECTURES = ("P", "X")`; `LAW_REGISTRIES = {"P": P_LAWS, "X": X_LAWS}`.
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
* `PairedRunner.__init__(*, environment_factory, collateral_construction, retention_form,
  retention_params, recorder=None)`: the names and horizons are **required**, and the runner's own
  call sites pass the caller's `Name`, never a literal.
* `PairedRunner.run(state, *, arms, evidence, exogenous)` — deliberately **no** `domain`/`visited`
  parameters: the runner derives them itself from the pre-update state in `pre_update_source`.

## The eleven mutations, by the property each proves

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
| `arm_uses_wrong_architecture_registry` | registry/dispatch gate | add a cross-architecture gate first |

Information boundary / outcome space:

| mutation | gate it must kill | declaration that should hold |
|---|---|---|
| `runner_accepts_forbidden_exogenous_field` | closed-field gate | `DID NOT RAISE` |
| `runner_adds_composite_score` | three-dimension independence gate | `record.__dataclass_fields__` |

All declarations are to be **measured, then written** — a mismatch is corrected to what the run
prints, never accommodated by weakening the check.

## Gate-writing discipline (three self-inflicted findings, same root cause)

Structure is checked by AST, signature, nominal type, dataclass field-set or object identity.
String search is for narrow static hygiene only, never for a semantic gate. Three times a textual
probe tripped on prose or on the implementation's own identifiers (`"b2 import testing"` inside a
comment, a comment mentioning the fixture module, `"apply("` matching the runner's own `_apply`).

## Remaining work before `rebuild` may receive this

1. re-land the runner and its ten gates on this branch;
2. land the eleven mutations, each measured and declared;
3. full sweep: 637+ tests, nine self-check tables, `spec_audit`;
4. only then: one source closure commit on `rebuild` plus the D_patch evidence binding commit.
