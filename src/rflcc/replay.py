"""ReplayBuffer：普通 task-transition replay（ER-5 使用，S09）。

ER-5 语义：replay task transitions（标准 QL TD update），attribution 冻结
（episode 时计算一次），禁止重新调用 sequence/counterfactual inference。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field


@dataclass
class ReplayRecord:
    state: tuple
    action: int
    reward: float
    next_state: tuple
    done: bool


class ReplayBuffer:
    def __init__(self, capacity: int = 10000, rng: random.Random | None = None):
        self.capacity = capacity
        self.rng = rng if rng is not None else random.Random(0)
        self.data: list[ReplayRecord] = []

    def add(self, record: ReplayRecord) -> None:
        self.data.append(record)
        if len(self.data) > self.capacity:
            self.data.pop(0)

    def sample(self, k: int) -> list[ReplayRecord]:
        if not self.data:
            return []
        k = min(k, len(self.data))
        return self.rng.sample(self.data, k)

    def __len__(self) -> int:
        return len(self.data)
