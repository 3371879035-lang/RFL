"""Standard-HQ：真实 task Q-learning，无 diagnostic auxiliary update（S08）。"""

from __future__ import annotations

import numpy as np

from ..qtables import QTables


class StandardHQ:
    """Q_H 每 episode 一次 MC 更新；Q_L 每步在线 TD；epsilon-greedy。"""

    name = "standard"

    def __init__(
        self,
        *,
        alpha_low: float = 0.20,
        alpha_high: float = 0.15,
        gamma: float = 0.97,
        n_actions: int = 5,
        options: tuple[int, ...] = (0, 1),
        rng: np.random.RandomState | None = None,
    ) -> None:
        self.alpha_low = alpha_low
        self.alpha_high = alpha_high
        self.gamma = gamma
        self.q = QTables(n_actions=n_actions, options=options)
        self.rng = rng if rng is not None else np.random.RandomState(0)

    # -- action selection ----------------------------------------------
    def select_option(self, s_h, eps: float) -> int:
        if self.rng.random() < eps:
            return int(self.rng.randint(0, 2))
        return self.q.greedy_high(s_h)

    def select_action(self, state, eps: float) -> int:
        if self.rng.random() < eps:
            return int(self.rng.randint(0, self.q.n_actions))
        return self.q.greedy_low(state)

    # -- updates ---------------------------------------------------------
    def update_low(self, s, a: int, r: float, s2, done: bool) -> float:
        """在线 Q-learning：done（terminated or truncated）不 bootstrap。"""
        if done:
            target = r
        else:
            target = r + self.gamma * self.q.low_get(s2, self.q.greedy_low(s2))
        return self.q.low_update(s, a, target, self.alpha_low)

    def update_high(self, s_h, option: int, g0: float) -> float:
        """episodic MC：Q_H(s_H,o) <- Q + alpha_H (G0 - Q)。"""
        return self.q.high_update(s_h, option, g0, self.alpha_high)
