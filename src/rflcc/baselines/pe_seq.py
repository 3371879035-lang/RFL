"""PE-Seq：sequence surprise + weak feedback（无 counterfactual）。"""

from __future__ import annotations

from .base import AttributionBaseline, AttributionOutcome
from ..attribution import pe_seq_responsibility
from ..feedback import FEEDBACK_WEIGHT


class PESeq(AttributionBaseline):
    name = "pe_seq"

    def attribute(self, trace, observed_feedback, seq_model, cf_runner) -> AttributionOutcome:
        score = seq_model.score(trace)
        R = pe_seq_responsibility(score.q_seq, observed_feedback, weight=FEEDBACK_WEIGHT)
        return AttributionOutcome(
            responsibility=R,
            proposed_update_mass={"H": R["H"], "L": R["L"]},
            info={"q_seq": score.q_seq, "G": score.G},
        )
