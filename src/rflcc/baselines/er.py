"""ER-5：普通 task-transition replay + 冻结归因（S09）。

- 始终执行真实 task Q-learning
- COLLISION 时用 episode 时计算的 attribution（Immediate one-hot of feedback）
  冻结执行一次 aux update（不重新运行 sequence / counterfactual）
- 训练期间额外 replay 最近 task transitions 做标准 QL TD update（K=5）
"""

from __future__ import annotations

import numpy as np

from ..replay import ReplayBuffer, ReplayRecord


class ER5:
    name = "er5"

    def __init__(
        self,
        *,
        alpha_low: float = 0.20,
        alpha_high: float = 0.15,
        alpha_diag: float = 0.10,
        gamma: float = 0.97,
        replay_k: int = 5,
        rng: np.random.RandomState | None = None,
    ) -> None:
        self.alpha_low = alpha_low
        self.alpha_high = alpha_high
        self.alpha_diag = alpha_diag
        self.gamma = gamma
        self.replay_k = replay_k
        self.rng = rng if rng is not None else np.random.RandomState(0)
        self.buffer = ReplayBuffer(rng=random_wrap(rng))
        self.replay_updates_done = 0

    # -- 归因（冻结）：episode 时一次 Immediate ---------------------------
    def frozen_attribution(self, observed_feedback: str) -> dict[str, float] | None:
        from ..attribution import immediate_responsibility

        return immediate_responsibility(observed_feedback)

    # -- replay ----------------------------------------------------------
    def add_transition(self, s, a, r, s2, done) -> None:
        self.buffer.add(ReplayRecord(state=s, action=a, reward=r, next_state=s2, done=done))

    def replay(self, q_tables, n: int | None = None) -> int:
        """采样 K 条做标准 QL TD update（不调用任何归因/CF）。"""
        k = n if n is not None else self.replay_k
        count = 0
        for rec in self.buffer.sample(k):
            if rec.done:
                target = rec.reward
            else:
                target = rec.reward + self.gamma * q_tables.low_get(
                    rec.next_state, q_tables.greedy_low(rec.next_state)
                )
            q_tables.low_update(rec.state, rec.action, target, self.alpha_low)
            count += 1
        self.replay_updates_done += count
        return count


def random_wrap(rng: np.random.RandomState):
    import random

    return random.Random(rng.randint(0, 2**31 - 1))
