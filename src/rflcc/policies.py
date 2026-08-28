"""策略接口与 scripted route follower；公共 rollout 工具（S03 基础）。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .env import CausalChaseEnv
from .noise import NoiseTape
from .trace import EpisodeTrace
from .types import (
    ACT_E,
    ACT_N,
    ACT_S,
    ACT_W,
    ACT_WAIT,
    ACTION_DELTA,
    GOAL,
    LOW_MODULE,
    Observation,
    OBSTACLES,
    OPTION_LOWER,
    OPTION_UPPER,
    TERM_COLLISION,
    TERM_EXIT,
    TERM_TIMEOUT,
    TraceEvent,
    Transition,
    WAYPOINTS_BY_OPTION,
    InterventionSet,
    discounted_return,
    GAMMA,
    bfs_distance,
)

_MOVES = (ACT_N, ACT_S, ACT_E, ACT_W)


class Policy(ABC):
    """低层策略接口：根据观测给出下一个 primitive action。"""

    @abstractmethod
    def act(self, obs: Observation) -> int:
        ...


class ScriptedRouteFollower(Policy):
    """贪心朝当前 waypoint 的最短路径方向走一步（避障）。"""

    def __init__(self, option: int) -> None:
        self.option = int(option)

    def act(self, obs: Observation) -> int:
        waypoints = WAYPOINTS_BY_OPTION[self.option]
        wp = waypoints[min(obs.waypoint_index, len(waypoints) - 1)]
        x, y = obs.agent_xy
        if (x, y) == wp:
            # 已到 waypoint：若还有下一个则朝下一个（waypoint_index 尚未推进）
            nxt = waypoints[min(obs.waypoint_index + 1, len(waypoints) - 1)]
            return self._step_toward(obs.agent_xy, nxt)
        return self._step_toward(obs.agent_xy, wp)

    def _step_toward(self, xy: tuple[int, int], target: tuple[int, int]) -> int:
        """选使得到 target 的 BFS 距离最小的合法移动（含原地不动比较）。"""
        best: list[int] = []
        best_d = bfs_distance(xy, target)
        x, y = xy
        for a in _MOVES:
            dx, dy = ACTION_DELTA[a]
            nx, ny = x + dx, y + dy
            if not (0 <= nx < 9 and 0 <= ny < 7):
                continue
            if (nx, ny) in OBSTACLES:
                continue
            d = bfs_distance((nx, ny), target)
            if d < best_d:
                best_d = d
                best = [a]
            elif d == best_d:
                best.append(a)
        if best:
            # 确定性：优先 EAST/NORTH/SOUTH/WEST（固定顺序取第一个）
            for a in (ACT_E, ACT_N, ACT_S, ACT_W):
                if a in best:
                    return a
        return ACT_WAIT


class FrozenQLowPolicy(Policy):
    """冻结的低层 Q 策略（epsilon=0），供 Experiment B counterfactual 使用。

    q_tables: dict[state, dict[action, float]] 或带 get_q(state)->dict 的对象。
    """

    def __init__(self, q_tables, options: tuple[int, ...] = (OPTION_UPPER, OPTION_LOWER)):
        self._q = q_tables
        self._options = options

    def act(self, obs: Observation) -> int:
        s = obs.low_state
        q = self._q_get(s)
        if not q:
            return ACT_WAIT
        return max(q, key=q.get)

    def _q_get(self, state) -> dict[int, float]:
        if hasattr(self._q, "get"):
            row = self._q.get(state)
            if row is None:
                return {}
            if isinstance(row, (list, tuple)):
                return {i: float(v) for i, v in enumerate(row)}
            if hasattr(row, "items"):
                return dict(row)
            return {}
        raise TypeError("FrozenQLowPolicy requires dict-like q_tables")


# ---------------------------------------------------------------------------
# rollout 工具
# ---------------------------------------------------------------------------

def rollout_to_trace(
    env: CausalChaseEnv,
    *,
    tape: NoiseTape,
    option: int,
    policy: Policy,
    seed: int,
    scenario_id: str,
    interventions: InterventionSet | None = None,
    true_primary: str | None = None,
    fault_t: int | None = None,
    fault_action: int | None = None,
    env_overrides: dict | None = None,
) -> EpisodeTrace:
    """从 episode 初态用 policy 滚动到结束，返回完整 EpisodeTrace。

    interventions.action_override 可指定 (t -> action) 覆盖；t 之后继续用
    policy（frozen continuation），从而支持反事实重放。
    """
    env.reset(noise_tape=tape, option=option)
    if interventions is not None:
        env.set_interventions(interventions)

    trace = EpisodeTrace(
        seed=seed,
        scenario_id=scenario_id,
        option=option,
        terminal_type=None,
        noise_tape=tape,
        true_primary=true_primary,
        fault_t=fault_t,
        fault_action=fault_action,
    )
    overrides = interventions.action_override if interventions else {}

    while not (env.terminated or env.truncated):
        t = env.step_index
        obs = env._observe()
        if t in overrides:
            action = overrides[t]
        else:
            action = policy.act(obs)

        state = obs.low_state
        obs2, reward, terminated, truncated, info = env.step(action)
        state2 = obs2.low_state
        trace.transitions.append(
            Transition(
                t=t,
                state=state,
                action=action,
                reward=reward,
                next_state=state2,
                terminated=terminated,
                truncated=truncated,
                option=option,
                agent_xy=obs.agent_xy,
                monster_xy=obs.monster_xy,
            )
        )
        trace.causal_events.extend(info["events"])

    trace.terminal_type = env.terminal_type
    trace.compute_return(GAMMA)
    trace.env_meta["dash_log"] = list(env.dash_log)
    return trace


def observed_dash_indices(trace: EpisodeTrace) -> list[int]:
    """factual 中实际发生的 dash 所对应的 monster move index 序列。"""
    return list(trace.env_meta.get("dash_log", []))
