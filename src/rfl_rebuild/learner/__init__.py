"""A75 §62.11 / A76 §63 — the learner-owned persistent store substrate.

This package is deliberately **not** ``env/`` and **not** ``method/``:

* ``env/`` is the kernel, and the kernel does not own the learner — it accepts an
  external baseline, executes it under the SCM priority, and enforces the contract;
* ``method/`` carries the V0.1R/V0.2R method and interface semantics, which are
  closed.

What lives here is only the *substrate*: a state that can persist across episodes,
be read safely, be changed atomically, and be snapshotted exactly. It contains **no
update law** — no `DeleteFactualPatch`, no `SetAlternative`, no `LocalOracleRestore`,
no `FactualReturnWrite`, no ledger status. Those are law-execution receipts and belong
to the layer above; a store that named them would make the next bug
indistinguishable between substrate and law.
"""

from rfl_rebuild.learner.store import (
    CONTROLLER,
    DECISION,
    PROCESS,
    DecisionAddress,
    Edit,
    LearnerPersistentState,
    LearnerSnapshot,
    StoreTransactionError,
    is_option_id,
)

__all__ = [
    "CONTROLLER",
    "DECISION",
    "PROCESS",
    "DecisionAddress",
    "Edit",
    "LearnerPersistentState",
    "LearnerSnapshot",
    "StoreTransactionError",
    "is_option_id",
]
