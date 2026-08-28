"""CF-only：不做 sequence/feedback，直接对全部 cause 做 exhaustive 验证。"""

from __future__ import annotations

from .base import AttributionBaseline, AttributionOutcome
from ..attribution import cf_only_responsibility
from ..types import CAUSES


class CFOnly(AttributionBaseline):
    """纯 CF 强基线：验证 H（换 option）、L（全部 T 个 decision x 其余 4 动作）、
    E（全部 observed dash）。不使用 sequence 与外部反馈。"""

    name = "cf_only"

    def attribute(self, trace, observed_feedback, seq_model, cf_runner) -> AttributionOutcome:
        # 用完整窗口的 runner：cf_runner 是外部传入的；这里要求 window=全部。
        # 为隔离性，CF-only 使用自己的 exhaustive runner（由 experiment 装配）。
        result = cf_runner.verify(trace, candidates=list(CAUSES))
        delta_pos = {c: max(0.0, result.delta.get(c, 0.0)) for c in CAUSES}
        R = cf_only_responsibility(delta_pos)
        if R is None:
            return AttributionOutcome(
                responsibility=None, cf_transitions=result.cf_transitions
            )
        return AttributionOutcome(
            responsibility=R,
            proposed_update_mass={"H": R["H"], "L": R["L"]},
            cf_transitions=result.cf_transitions,
            info={"cf_delta": result.delta},
        )
