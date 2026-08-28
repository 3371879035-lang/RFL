"""Oracle-upper：直接使用 evaluator ground truth responsibility（仅作上界）。"""

from __future__ import annotations

from .base import AttributionBaseline, AttributionOutcome


class OracleUpper(AttributionBaseline):
    name = "oracle_upper"

    def attribute(self, trace, observed_feedback, seq_model, cf_runner) -> AttributionOutcome:
        r_star = trace.env_meta.get("r_star")
        if r_star is None:
            return AttributionOutcome(responsibility=None)
        return AttributionOutcome(
            responsibility=dict(r_star),
            proposed_update_mass={"H": r_star["H"], "L": r_star["L"]},
        )
