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

A77 §65.4 added the fourth store, $Q_D^L$, and with it the one thing the substrate
needs in order to read or write a sparse override on a reference: the **injected**
:class:`~rfl_rebuild.learner.reference.QReferenceView`. Injected is the operative word
— nothing in this package calls ``solve_reference()``, so the persistent state can
never depend on a global the experiment is supposed to control. The store answers "can
this be persisted and read"; what should be *written* into it is step 4's question and
is not answered here.
"""

from rfl_rebuild.learner.reference import (
    QReferenceView,
    reference_view_from,
)
from rfl_rebuild.learner.store import (
    CONTROLLER,
    DECISION,
    PROCESS,
    Q,
    DecisionAddress,
    Edit,
    LearnerPersistentState,
    LearnerSnapshot,
    LearnerStateError,
    QAddress,
    ReferenceContractError,
    StoreTransactionError,
    is_option_id,
    owner_Q,
    require_q_reference,
)

__all__ = [
    "CONTROLLER",
    "DECISION",
    "PROCESS",
    "Q",
    "DecisionAddress",
    "Edit",
    "LearnerPersistentState",
    "LearnerSnapshot",
    "LearnerStateError",
    "QAddress",
    "QReferenceView",
    "ReferenceContractError",
    "StoreTransactionError",
    "is_option_id",
    "owner_Q",
    "require_q_reference",
    "reference_view_from",
]
