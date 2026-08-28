"""EpisodeTrace：episode 的完整记录（causal / feedback 两个 namespace 分离）。"""

from __future__ import annotations

from dataclasses import dataclass, field

from .noise import NoiseTape
from .types import TraceEvent, Transition, discounted_return, GAMMA


@dataclass
class EpisodeTrace:
    seed: int
    scenario_id: str
    option: int
    terminal_type: str | None
    transitions: list[Transition] = field(default_factory=list)
    causal_events: list[TraceEvent] = field(default_factory=list)
    feedback_events: list[TraceEvent] = field(default_factory=list)
    noise_tape: NoiseTape | None = None
    total_return: float = 0.0
    true_primary: str | None = None  # evaluator-only；learner 不得读取
    fault_t: int | None = None  # scenario 构造信息（L-only）
    fault_action: int | None = None
    env_meta: dict = field(default_factory=dict)

    # ------------------------------------------------------------------
    @property
    def tokens(self) -> list[str]:
        return [e.token for e in self.causal_events]

    @property
    def n_transitions(self) -> int:
        return len(self.transitions)

    @property
    def rewards(self) -> list[float]:
        return [tr.reward for tr in self.transitions]

    def compute_return(self, gamma: float = GAMMA) -> float:
        self.total_return = discounted_return(self.rewards, gamma)
        return self.total_return

    def add_feedback(self, token: str) -> None:
        """feedback token 只能进 feedback_events，绝不进 causal_events。"""
        self.feedback_events.append(
            TraceEvent(t=-1, token=token, module=None, source="feedback")
        )

    def feedback_tokens(self) -> list[str]:
        return [e.token for e in self.feedback_events]

    # ------------------------------------------------------------------
    def __hash__(self) -> int:  # 用于缓存 key
        return hash((self.scenario_id, self.seed))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, EpisodeTrace):
            return False
        return (
            self.scenario_id == other.scenario_id
            and self.seed == other.seed
            and self.option == other.option
            and [e.token for e in self.causal_events]
            == [e.token for e in other.causal_events]
        )
