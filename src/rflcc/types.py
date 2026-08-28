"""核心类型定义：Cause、事件、snapshot、intervention、NoiseTape 结构。"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field, replace
from typing import Literal

# ---------------------------------------------------------------------------
# 原因与动作常量
# ---------------------------------------------------------------------------

CAUSES: tuple[str, ...] = ("H", "L", "E")
Cause = Literal["H", "L", "E"]

ACT_N, ACT_S, ACT_E, ACT_W, ACT_WAIT = 0, 1, 2, 3, 4
ACTIONS: tuple[str, ...] = (
    "ACT_N",
    "ACT_S",
    "ACT_E",
    "ACT_W",
    "ACT_WAIT",
)
ACTION_TO_IDX: dict[str, int] = {name: i for i, name in enumerate(ACTIONS)}
IDX_TO_ACTION: dict[int, str] = dict(enumerate(ACTIONS))

# 每个动作的 (dx, dy)；WAIT 不移动
ACTION_DELTA: dict[int, tuple[int, int]] = {
    ACT_N: (0, -1),
    ACT_S: (0, 1),
    ACT_E: (1, 0),
    ACT_W: (-1, 0),
    ACT_WAIT: (0, 0),
}

OPTION_UPPER = 0
OPTION_LOWER = 1
OPTION_NAMES: tuple[str, ...] = ("UPPER", "LOWER")

# 高层 option 名称
HIGH_LOW = "HIGH"
LOW_MODULE = "LOW"
ENV_MODULE = "ENV"

# ---------------------------------------------------------------------------
# 事件 token 词汇表（causal namespace）
# ---------------------------------------------------------------------------

TOKEN_OPT_UPPER = "OPT_UPPER"
TOKEN_OPT_LOWER = "OPT_LOWER"

TOKEN_ACT_N = "ACT_N"
TOKEN_ACT_S = "ACT_S"
TOKEN_ACT_E = "ACT_E"
TOKEN_ACT_W = "ACT_W"
TOKEN_ACT_WAIT = "ACT_WAIT"

TOKEN_ROUTE_PROGRESS = "ROUTE_PROGRESS"
TOKEN_ROUTE_DEVIATE = "ROUTE_DEVIATE"

TOKEN_MONSTER_NORMAL = "MONSTER_NORMAL"
TOKEN_MONSTER_DASH = "MONSTER_DASH"

TOKEN_DIST_FAR = "DIST_FAR"
TOKEN_DIST_MID = "DIST_MID"
TOKEN_DIST_NEAR = "DIST_NEAR"

TOKEN_EXIT = "EXIT"
TOKEN_COLLISION = "COLLISION"
TOKEN_TIMEOUT = "TIMEOUT"

# 诊断反馈 namespace（严禁进入 causal events）
TOKEN_FEEDBACK_H = "FEEDBACK_H"
TOKEN_FEEDBACK_L = "FEEDBACK_L"
TOKEN_FEEDBACK_E = "FEEDBACK_E"
TOKEN_FEEDBACK_UNKNOWN = "FEEDBACK_UNKNOWN"
FEEDBACK_TOKENS: dict[str, str] = {
    "H": TOKEN_FEEDBACK_H,
    "L": TOKEN_FEEDBACK_L,
    "E": TOKEN_FEEDBACK_E,
    "UNKNOWN": TOKEN_FEEDBACK_UNKNOWN,
}
FEEDBACK_CAUSES: tuple[str, ...] = ("H", "L", "E", "UNKNOWN")

# 终端类型
TERM_EXIT = "EXIT"
TERM_COLLISION = "COLLISION"
TERM_TIMEOUT = "TIMEOUT"

# ---------------------------------------------------------------------------
# 网格几何（与 env 共享，避免循环 import）
# ---------------------------------------------------------------------------

GRID_WIDTH = 9
GRID_HEIGHT = 7
AGENT_START = (1, 3)
GOAL = (7, 3)
OBSTACLES: frozenset[tuple[int, int]] = frozenset(
    (x, y) for x in (3, 4, 5) for y in (2, 3, 4)
)
MONSTER_START_BY_OPTION: dict[int, tuple[int, int]] = {
    OPTION_UPPER: (6, 1),
    OPTION_LOWER: (6, 5),
}
WAYPOINTS_BY_OPTION: dict[int, tuple[tuple[int, int], ...]] = {
    OPTION_UPPER: ((2, 1), (6, 1), (7, 3)),
    OPTION_LOWER: ((2, 5), (6, 5), (7, 3)),
}

HORIZON = 30
GAMMA = 0.97
REWARD_EXIT = 1.0
REWARD_COLLISION = -1.0
REWARD_TIMEOUT = -0.5
REWARD_STEP = -0.01

MONSTER_MOVE_PERIOD = 2
MONSTER_DASH_P = 0.10


# ---------------------------------------------------------------------------
# 数据类型
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Observation:
    """环境返回的观测。"""

    monster_start_lane: int  # OPTION_UPPER / OPTION_LOWER
    agent_xy: tuple[int, int]
    monster_xy: tuple[int, int]
    option: int
    step_index: int
    waypoint_index: int
    terminal_type: str | None = None

    @property
    def low_state(self) -> tuple[int, int, int, int, int, int]:
        """s_L = (x_A, y_A, x_M, y_M, o, t mod 2)。"""
        ax, ay = self.agent_xy
        mx, my = self.monster_xy
        return (ax, ay, mx, my, self.option, self.step_index % 2)


@dataclass(frozen=True)
class TraceEvent:
    """一条因果事件。token 属于 causal namespace。"""

    t: int
    token: str
    module: str | None  # HIGH / LOW / ENV / None
    source: str

    def __post_init__(self) -> None:
        if not isinstance(self.token, str) or not self.token:
            raise ValueError("event token must be a non-empty string")


@dataclass(frozen=True)
class EnvSnapshot:
    """完整环境状态，用于 counterfactual restore。"""

    agent_xy: tuple[int, int]
    monster_xy: tuple[int, int]
    option: int
    step_index: int
    monster_move_index: int
    waypoint_index: int
    terminal_type: str | None
    terminated: bool
    truncated: bool
    causal_events: tuple[TraceEvent, ...]
    # noise tape 本身不变（frozen），restore 不重建
    reward_acc: float = 0.0


@dataclass(frozen=True)
class InterventionSet:
    """counterfactual 干预：全部表达为 overlay，不修改 NoiseTape。"""

    blocked_dash_indices: frozenset[int] = frozenset()
    option_override: int | None = None  # do(option=o')
    action_override: dict[int, int] = field(default_factory=dict)  # do(a_t=a')

    def with_dash_blocked(self, idx: int) -> "InterventionSet":
        return replace(self, blocked_dash_indices=self.blocked_dash_indices | {idx})

    def with_option(self, option: int) -> "InterventionSet":
        return replace(self, option_override=option)

    def with_action(self, t: int, action: int) -> "InterventionSet":
        acts = dict(self.action_override)
        acts[t] = action
        return replace(self, action_override=acts)

    def is_empty(self) -> bool:
        return (
            not self.blocked_dash_indices
            and self.option_override is None
            and not self.action_override
        )


@dataclass(frozen=True)
class Transition:
    """一条 (s, a, r, s', d) 转移记录。"""

    t: int
    state: tuple[int, int, int, int, int, int]
    action: int
    reward: float
    next_state: tuple[int, int, int, int, int, int]
    terminated: bool
    truncated: bool
    option: int
    agent_xy: tuple[int, int]
    monster_xy: tuple[int, int]
    feedback_primary: str | None = None  # 仅 evaluator 可用


@dataclass(frozen=True)
class NoiseTape:
    """episode 的全部外生随机变量，预采样、不可变。

    结构：U = (lane, u^tie_1..n, u^dash_1..m)。

    - monster_start_lane: OPTION_UPPER / OPTION_LOWER
    - tie_break_u: 每次 monster 基础移动与 dash 移动的方向选择（长度 2*horizon）
    - dash_u: 每次 monster 基础移动后的 dash 检查（长度 horizon）
    """

    seed: int
    monster_start_lane: int
    tie_break_u: tuple[float, ...]
    dash_u: tuple[float, ...]
    horizon: int = HORIZON

    @classmethod
    def from_seed(cls, seed: int, horizon: int = HORIZON) -> "NoiseTape":
        import numpy as np

        rng = np.random.RandomState(seed)
        lane = int(rng.randint(0, 2))
        tie_break_u = tuple(float(x) for x in rng.uniform(size=2 * horizon))
        dash_u = tuple(float(x) for x in rng.uniform(size=horizon))
        return cls(
            seed=seed,
            monster_start_lane=lane,
            tie_break_u=tie_break_u,
            dash_u=dash_u,
            horizon=horizon,
        )

    def tie_break(self, move_index: int) -> float:
        return self.tie_break_u[move_index]

    def dash_roll(self, move_index: int) -> float:
        return self.dash_u[move_index]

    def sha256(self) -> str:
        payload = (
            f"{self.seed}|{self.monster_start_lane}|"
            f"{','.join(f'{u:.9f}' for u in self.tie_break_u)}|"
            f"{','.join(f'{u:.9f}' for u in self.dash_u)}"
        )
        return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def __post_init__(self) -> None:
        if len(self.tie_break_u) < 2 * self.horizon:
            raise ValueError("tie_break_u too short")
        if len(self.dash_u) < self.horizon:
            raise ValueError("dash_u too short")
        for v in self.tie_break_u + self.dash_u:
            if not (0.0 <= v <= 1.0):
                raise ValueError(f"noise draw out of range: {v}")


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

_EPS = 1e-12


def softmax(logits: dict[str, float], tau: float = 1.0) -> dict[str, float]:
    """数值稳定 softmax over dict values。"""
    keys = list(logits.keys())
    vals = [logits[k] / max(tau, 1e-12) for k in keys]
    m = max(vals)
    exps = [math.exp(v - m) for v in vals]
    s = sum(exps)
    return {k: e / s for k, e in zip(keys, exps)}


def discounted_return(rewards: list[float], gamma: float = GAMMA) -> float:
    """从 t=0 的折扣回报 G_0 = sum_t gamma^t r_t。"""
    g = 0.0
    for r in reversed(rewards):
        g = r + gamma * g
    return g


_DIST_MATRIX: dict[tuple[tuple[int, int], tuple[int, int]], int] = {}


def _build_dist_matrix() -> None:
    from collections import deque

    cells = [(x, y) for x in range(GRID_WIDTH) for y in range(GRID_HEIGHT)]
    for gx, gy in cells:
        goal = (gx, gy)
        if goal in OBSTACLES:
            continue
        dist = {goal: 0}
        q = deque([goal])
        while q:
            (x, y) = q.popleft()
            d = dist[(x, y)]
            for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                nx, ny = x + dx, y + dy
                if not (0 <= nx < GRID_WIDTH and 0 <= ny < GRID_HEIGHT):
                    continue
                if (nx, ny) in OBSTACLES or (nx, ny) in dist:
                    continue
                dist[(nx, ny)] = d + 1
                q.append((nx, ny))
        for cell in cells:
            _DIST_MATRIX[(cell, goal)] = dist.get(cell, 10**9)


def bfs_distance(
    start: tuple[int, int],
    goal: tuple[int, int],
    obstacles: frozenset[tuple[int, int]] = OBSTACLES,
    width: int = GRID_WIDTH,
    height: int = GRID_HEIGHT,
) -> int:
    """网格上两点间最短路长度（4 邻域，避障碍）。不可达返回大数。

    预计算全网格距离矩阵（9x7 固定几何）后为 O(1) 查表。
    """
    if not _DIST_MATRIX:
        _build_dist_matrix()
    key = (start, goal)
    d = _DIST_MATRIX.get(key)
    if d is None:  # 非标准几何回退到在线 BFS
        return _bfs_distance_online(start, goal, obstacles, width, height)
    return d


def _bfs_distance_online(
    start: tuple[int, int],
    goal: tuple[int, int],
    obstacles: frozenset[tuple[int, int]],
    width: int,
    height: int,
) -> int:
    from collections import deque

    if start == goal:
        return 0
    if start in obstacles or goal in obstacles:
        return 10**9
    seen = {start}
    q = deque([(start, 0)])
    while q:
        (x, y), d = q.popleft()
        for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            nx, ny = x + dx, y + dy
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            if (nx, ny) in obstacles:
                continue
            if (nx, ny) == goal:
                return d + 1
            if (nx, ny) not in seen:
                seen.add((nx, ny))
                q.append(((nx, ny), d + 1))
    return 10**9
