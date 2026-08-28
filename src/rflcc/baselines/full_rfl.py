"""Full-RFL：sequence + weak feedback -> Top-K -> 受限 CF 验证 -> finalize。"""

from __future__ import annotations

import math

from .base import AttributionBaseline, AttributionOutcome
from ..attribution import finalize_rfl
from ..feedback import FEEDBACK_WEIGHT, log_fusion
from ..types import CAUSES


class FullRFL(AttributionBaseline):
    name = "full_rfl"

    def __init__(
        self,
        *,
        top_k: int = 2,
        lambda_cf: float = 4.0,
        lambda_reject: float = 2.0,
        delta_reject: float = 0.05,
        tau_r: float = 1.0,
    ) -> None:
        self.top_k = top_k
        self.lambda_cf = lambda_cf
        self.lambda_reject = lambda_reject
        self.delta_reject = delta_reject
        self.tau_r = tau_r

    def attribute(self, trace, observed_feedback, seq_model, cf_runner) -> AttributionOutcome:
        score = seq_model.score(trace)
        q_pre = log_fusion(score.q_seq, observed_feedback, weight=FEEDBACK_WEIGHT)

        ranked = sorted(CAUSES, key=lambda c: q_pre[c], reverse=True)
        candidates = ranked[: self.top_k]

        cf_result = cf_runner.verify(trace, candidates=candidates)

        R = finalize_rfl(
            q_pre,
            cf_result.delta,
            verified=cf_result.verified,
            lambda_cf=self.lambda_cf,
            lambda_reject=self.lambda_reject,
            delta_reject=self.delta_reject,
            tau_r=self.tau_r,
        )
        return AttributionOutcome(
            responsibility=R,
            proposed_update_mass={"H": R["H"], "L": R["L"]},
            cf_transitions=cf_result.cf_transitions,
            info={
                "q_seq": score.q_seq,
                "G": score.G,
                "q_pre": q_pre,
                "cf_checked": candidates,
                "cf_delta": cf_result.delta,
                "verified": sorted(cf_result.verified),
            },
        )
