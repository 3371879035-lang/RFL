"""Baseline 统一接口与 AttributionOutcome。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AttributionOutcome:
    responsibility: dict[str, float] | None
    proposed_update_mass: dict[str, float] = field(default_factory=dict)
    cf_transitions: int = 0
    info: dict = field(default_factory=dict)


class AttributionBaseline:
    """Experiment A 中所有算法的统一接口。

    attribute(trace, observed_feedback, seq_model, cf_runner) -> AttributionOutcome
    """

    name: str = "base"

    def attribute(
        self,
        trace,
        observed_feedback: str,
        seq_model,
        cf_runner,
    ) -> AttributionOutcome:
        raise NotImplementedError
