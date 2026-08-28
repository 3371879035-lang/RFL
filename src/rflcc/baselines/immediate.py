"""Immediate：直接相信诊断反馈为 one-hot responsibility。"""

from __future__ import annotations

from .base import AttributionBaseline, AttributionOutcome
from ..attribution import immediate_responsibility


class Immediate(AttributionBaseline):
    name = "immediate"

    def attribute(self, trace, observed_feedback, seq_model, cf_runner) -> AttributionOutcome:
        R = immediate_responsibility(observed_feedback)
        if R is None:
            return AttributionOutcome(responsibility=None)
        # proposed update mass = |rho| = R 的模块分量（H/L）
        return AttributionOutcome(
            responsibility=R,
            proposed_update_mass={"H": R["H"], "L": R["L"]},
            info={"feedback": observed_feedback},
        )
