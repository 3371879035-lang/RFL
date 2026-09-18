r"""A76 §63 — the B1 update-law layer (the $D_{patch}$ vertical slice).

Sits above ``rfl_rebuild.learner`` (the substrate) and below B2:

* the substrate owns persistence, snapshots and atomicity and names no law;
* this layer owns **what update operation is applied at a legal address**, and nothing
  else — no attribution, no target selection, no endpoint.

The law receives already-resolved addresses and already-resolved targets. It never
receives $T/P$, $S_{r,\pm}$, $\Gamma^\ast$, a world id, a block id, the trace, or
$Q_D^\ast$.
"""

from rfl_rebuild.b1.contract import (
    APPLIED,
    EVALUABLE_NOOP,
    NO_VALID_ALTERNATIVE,
    PROTOCOL_ERROR,
    STATUSES,
    DecisionWriteReceipt,
    ProtocolError,
    UpdateLedger,
    fingerprint,
)
from rfl_rebuild.b1.laws import (
    LAWS,
    DeleteFactualPatch,
    LawPlan,
    LocalOracleRestore,
    NoWrite,
    PlannedWrite,
    SetAlternative,
    independent_treatment_count,
    law_metadata,
)
from rfl_rebuild.b1.runner import (
    B1Result,
    run_patch_law,
    run_patch_law_with_envelope,
)
from rfl_rebuild.b1.targets import (
    TargetRecord,
    build_target_envelope,
    resolve_credited_units,
    resolve_decision_address,
)

__all__ = [
    "APPLIED",
    "EVALUABLE_NOOP",
    "LAWS",
    "NO_VALID_ALTERNATIVE",
    "PROTOCOL_ERROR",
    "STATUSES",
    "B1Result",
    "DecisionWriteReceipt",
    "DeleteFactualPatch",
    "LawPlan",
    "LocalOracleRestore",
    "NoWrite",
    "PlannedWrite",
    "ProtocolError",
    "SetAlternative",
    "TargetRecord",
    "UpdateLedger",
    "build_target_envelope",
    "fingerprint",
    "independent_treatment_count",
    "law_metadata",
    "resolve_credited_units",
    "resolve_decision_address",
    "run_patch_law",
    "run_patch_law_with_envelope",
]
