"""Tabular Q：Q_L（在线 TD）与 Q_H（episodic MC）与 epsilon 调度（S08）。"""

from __future__ import annotations

import math
from typing import Any

import numpy as np


def linear_epsilon(
    episode: int,
    start: float = 0.20,
    end: float = 0.02,
    decay_episodes: int = 3000,
) -> float:
    """显式线性 decay：epsilon(e) = start + min(e/D, 1) * (end - start)。"""
    frac = min(max(episode / decay_episodes, 0.0), 1.0)
    return start + frac * (end - start)


class QTables:
    """低层与高层 Q 表。low: state -> [q0..q4]；high: state -> {option: q}。"""

    def __init__(self, n_actions: int = 5, options: tuple[int, ...] = (0, 1)) -> None:
        self.n_actions = n_actions
        self.options = options
        self.low: dict[Any, list[float]] = {}
        self.high: dict[Any, dict[int, float]] = {}

    # -- low ------------------------------------------------------------
    def low_get(self, state, action: int) -> float:
        row = self.low.get(state)
        if row is None:
            return 0.0
        return row[action]

    def low_update(self, state, action: int, target: float, alpha: float) -> float:
        row = self.low.setdefault(state, [0.0] * self.n_actions)
        old = row[action]
        row[action] = old + alpha * (target - old)
        return abs(row[action] - old)

    def greedy_low(self, state) -> int:
        row = self.low.get(state)
        if row is None:
            return 4  # WAIT 作为默认
        return int(np.argmax(row))

    # -- high -----------------------------------------------------------
    def high_get(self, state, option: int) -> float:
        return self.high.get(state, {}).get(option, 0.0)

    def high_update(self, state, option: int, target: float, alpha: float) -> float:
        d = self.high.setdefault(state, {})
        old = d.get(option, 0.0)
        d[option] = old + alpha * (target - old)
        return abs(d[option] - old)

    def greedy_high(self, state) -> int:
        d = self.high.get(state)
        if d is None:
            return 0
        return max(d, key=d.get)

    # -- utilities ------------------------------------------------------
    def copy(self) -> "QTables":
        q = QTables(n_actions=self.n_actions, options=self.options)
        q.low = {k: list(v) for k, v in self.low.items()}
        q.high = {k: dict(v) for k, v in self.high.items()}
        return q

    def deep_hash(self) -> str:
        import hashlib

        payload = []
        for k in sorted(self.low, key=str):
            payload.append(f"{k}:{self.low[k]}")
        for k in sorted(self.high, key=str):
            payload.append(f"H{k}:{sorted(self.high[k].items())}")
        return hashlib.sha256("|".join(payload).encode()).hexdigest()

    def n_visited_states(self) -> int:
        return len(self.low) + len(self.high)
