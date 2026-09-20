r"""A76 §63 — the B1 update-law layer (the $D_{patch}$ vertical slice).

Sits above ``rfl_rebuild.learner`` (the substrate) and below B2:

* the substrate owns persistence, snapshots and atomicity and names no law;
* this layer owns **what update operation is applied at a legal address**, and nothing
  else — no attribution, no target selection, no endpoint.

The law receives already-resolved addresses and, **only if its cell declares fields**,
the envelope projected onto exactly those fields. That is the whole law API —
`(addresses, targets)`, enforced by the runner rather than assumed:

$$\boxed{\text{a law is handed no store view: not the state, not a snapshot}}$$

A76 §63.1 lets a primitive read *its own* store; it does not license handing a $D$ law an
independent handle on $P_D^L$, $C_P^L$ and $C_X^L$ at once. A $D_Q$ law that genuinely
needs the decision store gets a dedicated decision-only view, never the snapshot back.

The law also never receives $T/P$, $S_{r,\pm}$, $\Gamma^\ast$, a world id, a block id,
the trace, or $Q_D^\ast$.
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
    DQ_LAWS,
    DQLocalOracleRestore,
    CounterfactualReturnWrite,
    DualReturnWrite,
    LAWS,
    AddressPlan,
    DeleteFactualPatch,
    FactualReturnWrite,
    LawPlan,
    LocalOracleRestore,
    NoWrite,
    NoWriteRef,
    SetAlternative,
    independent_treatment_count,
    law_metadata,
)
from rfl_rebuild.b1.addressing import AddressDomain
from rfl_rebuild.b1.counterfactual import (
    CfEpisode,
    CounterfactualUndefined,
    CounterfactualTarget,
    build_counterfactual_envelope,
    replay_with_decision_replaced,
    validate_counterfactual_envelope,
)
from rfl_rebuild.b1.factual import (
    FactualTarget,
    build_factual_envelope,
    factual_return_to_go,
    validate_factual_envelope,
)
from rfl_rebuild.b1.runner import (
    B1Result,
    run_dq_law,
    run_factual_return_law,
    run_patch_law,
    run_row_restore_law,
    run_patch_law_with_envelope,
)
from rfl_rebuild.b1.targets import (
    TargetRecord,
    build_target_envelope,
    resolve_credited_units,
    resolve_decision_address,
)
from rfl_rebuild.b1.plan import RestoreRow, dq_owner
from rfl_rebuild.b1.tier import (
    DQ_DOMAIN,
    PATCH_DOMAIN,
    DQ_SLICE,
    ILL_TYPED,
    PATCH_SLICE,
    SliceDescriptor,
    Tier,
)

__all__ = [
    "APPLIED",
    "EVALUABLE_NOOP",
    "DQ_DOMAIN",
    "DQ_LAWS",
    "DQ_SLICE",
    "ILL_TYPED",
    "LAWS",
    "NO_VALID_ALTERNATIVE",
    "PATCH_DOMAIN",
    "PATCH_SLICE",
    "PROTOCOL_ERROR",
    "STATUSES",
    "AddressPlan",
    "B1Result",
    "DecisionWriteReceipt",
    "CounterfactualReturnWrite",
    "DQLocalOracleRestore",
    "DeleteFactualPatch",
    "DualReturnWrite",
    "FactualReturnWrite",
    "LawPlan",
    "LocalOracleRestore",
    "NoWrite",
    "NoWriteRef",
    "ProtocolError",
    "SetAlternative",
    "SliceDescriptor",
    "TargetRecord",
    "Tier",
    "UpdateLedger",
    "build_target_envelope",
    "AddressDomain",
    "CfEpisode",
    "RestoreRow",
    "dq_owner",
    "CounterfactualUndefined",
    "CounterfactualTarget",
    "FactualTarget",
    "build_counterfactual_envelope",
    "replay_with_decision_replaced",
    "build_factual_envelope",
    "factual_return_to_go",
    "fingerprint",
    "independent_treatment_count",
    "law_metadata",
    "resolve_credited_units",
    "resolve_decision_address",
    "run_dq_law",
    "run_factual_return_law",
    "run_row_restore_law",
    "run_patch_law",
    "run_patch_law_with_envelope",
    "validate_counterfactual_envelope",
    "validate_factual_envelope",
]
