r"""B2: the measurement stage A79 §67 froze and A83 §71.1 authorised.

B2 is built in four arrows, each with its own gates. This package currently contains only the
**first**:

$$\boxed{\text{B2-1 View/Builder} \rightarrow \text{B2-2 future rollout + estimators} \rightarrow
\text{B2-3 Collateral/Retention} \rightarrow \text{B2-4 paired runner}}$$

B2-1 is the view and its constructor gate (A75 §62.10). Nothing here estimates an effect, runs a
seed, or chooses a development-stage quantity: $U_{\text{unaffected}}$'s construction, the
Retention form, $T$, $N_{\text{eval}}$, the checkpoint grid and every $\Delta_{\min}$ are decided
under A83 §71.4 and are deliberately absent.
"""

from __future__ import annotations

from rfl_rebuild.b2.view import (
    H_FORBIDDEN,
    IMPORT_ALLOWLIST,
    SCENE_FORBIDDEN,
    VIEW_FIELDS,
    EvidenceOrigin,
    FutureConsequenceView,
    FutureConsequenceViewBuilder,
    FutureField,
    FutureRollout,
    assert_module_is_closed,
    require_learner_rollout,
)

__all__ = [
    "H_FORBIDDEN",
    "IMPORT_ALLOWLIST",
    "SCENE_FORBIDDEN",
    "VIEW_FIELDS",
    "EvidenceOrigin",
    "FutureConsequenceView",
    "FutureConsequenceViewBuilder",
    "FutureField",
    "FutureRollout",
    "assert_module_is_closed",
    "require_learner_rollout",
]
