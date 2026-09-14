"""Deterministic exogenous randomness for the two-level causal grid.

Written fresh for v0.3: the v0.2 ``NoiseTape`` carries ``monster_start_lane``
and ``dash_u``, which are CausalChase-specific and meaningless here.

Everything random in an episode comes from this container, so two runs with
the same ``(seed, config)`` are bit-identical, and every condition in a paired
comparison can share one tape.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class NoiseTape:
    seed: int
    episodes: int
    horizon: int
    p_hazard: float
    goal_lane: tuple[int, ...]
    hazard: tuple[int, ...]
    explore_u: tuple[tuple[float, ...], ...]
    tie_u: tuple[tuple[float, ...], ...]

    @classmethod
    def from_seed(
        cls, seed: int, *, episodes: int, horizon: int, p_hazard: float
    ) -> "NoiseTape":
        rng = np.random.default_rng(int(seed) % (2**32 - 1))
        # One draw for the high-level decision at t=0, plus one per low step.
        draws = int(horizon) + 1
        goal_lane = tuple(int(v) for v in rng.integers(0, 2, size=episodes))
        hazard = tuple(int(v) for v in (rng.random(size=episodes) < float(p_hazard)))
        explore_u = tuple(
            tuple(float(x) for x in rng.random(size=draws)) for _ in range(episodes)
        )
        # A separate stream, so that whether the agent explores and which way
        # it breaks an argmax tie are statistically independent draws.
        tie_u = tuple(
            tuple(float(x) for x in rng.random(size=draws)) for _ in range(episodes)
        )
        return cls(
            seed=int(seed),
            episodes=int(episodes),
            horizon=int(horizon),
            p_hazard=float(p_hazard),
            goal_lane=goal_lane,
            hazard=hazard,
            explore_u=explore_u,
            tie_u=tie_u,
        )

    def digest(self) -> str:
        payload = [
            f"{self.seed}|{self.episodes}|{self.horizon}|{self.p_hazard:.12g}",
            ",".join(str(v) for v in self.goal_lane),
            ",".join(str(v) for v in self.hazard),
            ";".join(",".join(f"{v:.12g}" for v in row) for row in self.explore_u),
            ";".join(",".join(f"{v:.12g}" for v in row) for row in self.tie_u),
        ]
        return hashlib.sha256("|".join(payload).encode("utf-8")).hexdigest()
