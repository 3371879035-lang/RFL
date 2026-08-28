"""CausalChaseEnv：9x7 确定性追逃环境（S02）。

所有随机性只能来自 NoiseTape；支持 snapshot/restore；事件语义按规范。
"""

from __future__ import annotations

from dataclasses import dataclass

from .noise import NoiseTape
from .types import (
    ACTION_DELTA,
    ACTIONS,
    AGENT_START,
    CAUSES,
    ENV_MODULE,
    GAMMA,
    GOAL,
    GRID_HEIGHT,
    GRID_WIDTH,
    HIGH_LOW,
    HORIZON,
    LOW_MODULE,
    MONSTER_DASH_P,
    MONSTER_MOVE_PERIOD,
    MONSTER_START_BY_OPTION,
    OBSTACLES,
    OPTION_LOWER,
    OPTION_NAMES,
    OPTION_UPPER,
    REWARD_COLLISION,
    REWARD_EXIT,
    REWARD_STEP,
    REWARD_TIMEOUT,
    TERM_COLLISION,
    TERM_EXIT,
    TERM_TIMEOUT,
    TOKEN_ACT_E,
    TOKEN_ACT_N,
    TOKEN_ACT_S,
    TOKEN_ACT_W,
    TOKEN_ACT_WAIT,
    TOKEN_COLLISION,
    TOKEN_DIST_FAR,
    TOKEN_DIST_MID,
    TOKEN_DIST_NEAR,
    TOKEN_EXIT,
    TOKEN_MONSTER_DASH,
    TOKEN_MONSTER_NORMAL,
    TOKEN_OPT_LOWER,
    TOKEN_OPT_UPPER,
    TOKEN_ROUTE_DEVIATE,
    TOKEN_ROUTE_PROGRESS,
    TOKEN_TIMEOUT,
    TraceEvent,
    WAYPOINTS_BY_OPTION,
    EnvSnapshot,
    InterventionSet,
    Observation,
    bfs_distance,
)


@dataclass
class StepInfo:
    events: list[TraceEvent]
    route_event: str | None
    agent_xy: tuple[int, int]
    monster_xy: tuple[int, int]
    waypoint_index: int
    terminal_type: str | None
    dash_occurred: bool


def _action_token(action: int) -> str:
    return ACTIONS[action]


class CausalChaseEnv:
    """RFL-CausalChase-v0.1 环境。

    事件顺序（每 agent step）：
        agent 移动 -> collision check -> route event ->
        (若 t % period == 0) monster base move -> collision check
            -> dash check -> collision check ->
        distance event -> EXIT/TIMEOUT check
    """

    def __init__(
        self,
        *,
        horizon: int = HORIZON,
        monster_move_period: int = MONSTER_MOVE_PERIOD,
        monster_dash_p: float = MONSTER_DASH_P,
        monster_enabled: bool = True,
        rewards: dict[str, float] | None = None,
        width: int = GRID_WIDTH,
        height: int = GRID_HEIGHT,
        seed: int | None = None,
    ) -> None:
        self.horizon = horizon
        self.monster_move_period = max(1, monster_move_period)
        self.monster_dash_p = monster_dash_p
        self.monster_enabled = monster_enabled
        self.width = width
        self.height = height
        self.rewards = {
            "exit": REWARD_EXIT,
            "collision": REWARD_COLLISION,
            "timeout": REWARD_TIMEOUT,
            "step": REWARD_STEP,
        }
        if rewards:
            self.rewards.update(rewards)
        self._default_seed = seed
        self._interventions: InterventionSet = InterventionSet()

        self.tape: NoiseTape | None = None
        self.agent_xy: tuple[int, int] = AGENT_START
        self.monster_xy: tuple[int, int] = MONSTER_START_BY_OPTION[OPTION_UPPER]
        self.option: int = OPTION_UPPER
        self.step_index = 0
        self.monster_move_index = 0
        self.waypoint_index = 0
        self.terminal_type: str | None = None
        self.terminated = False
        self.truncated = False
        self._events: list[TraceEvent] = []
        self._reward_acc = 0.0
        self._dash_log: list[int] = []  # 实际发生 dash 的 monster move index

    # ------------------------------------------------------------------
    # reset / snapshot / restore
    # ------------------------------------------------------------------

    def reset(
        self,
        *,
        seed: int | None = None,
        noise_tape: NoiseTape | None = None,
        option: int | None = None,
    ) -> tuple[Observation, dict]:
        tape = noise_tape if noise_tape is not None else NoiseTape.from_seed(
            seed if seed is not None else self._default_seed or 0,
            horizon=self.horizon,
        )
        self.tape = tape
        self.agent_xy = AGENT_START
        self.monster_xy = MONSTER_START_BY_OPTION[tape.monster_start_lane]
        self.option = (
            option if option is not None else tape.monster_start_lane
        )
        self.step_index = 0
        self.monster_move_index = 0
        self.waypoint_index = 0
        self.terminal_type = None
        self.terminated = False
        self.truncated = False
        self._events = []
        self._reward_acc = 0.0
        self._interventions = InterventionSet()
        self._dash_log = []
        self._emit(
            0,
            TOKEN_OPT_UPPER if self.option == OPTION_UPPER else TOKEN_OPT_LOWER,
            HIGH_LOW,
            "agent",
        )
        return self._observe(), {"events": list(self._events)}

    def set_option(self, option: int) -> None:
        """Experiment B：reset 后高层选择 option。"""
        if self.terminated or self.truncated:
            raise RuntimeError("cannot set option after episode end")
        if self.step_index != 0:
            raise RuntimeError("option must be set before the first step")
        self.option = int(option)
        self.waypoint_index = 0
        self._events = []
        self._emit(
            0,
            TOKEN_OPT_UPPER if self.option == OPTION_UPPER else TOKEN_OPT_LOWER,
            HIGH_LOW,
            "agent",
        )

    def set_interventions(self, interventions: InterventionSet) -> None:
        """counterfactual 干预 overlay；不改 NoiseTape。"""
        self._interventions = interventions

    def snapshot(self) -> EnvSnapshot:
        return EnvSnapshot(
            agent_xy=self.agent_xy,
            monster_xy=self.monster_xy,
            option=self.option,
            step_index=self.step_index,
            monster_move_index=self.monster_move_index,
            waypoint_index=self.waypoint_index,
            terminal_type=self.terminal_type,
            terminated=self.terminated,
            truncated=self.truncated,
            causal_events=tuple(self._events),
            reward_acc=self._reward_acc,
        )

    def restore(self, snap: EnvSnapshot) -> None:
        self.agent_xy = snap.agent_xy
        self.monster_xy = snap.monster_xy
        self.option = snap.option
        self.step_index = snap.step_index
        self.monster_move_index = snap.monster_move_index
        self.waypoint_index = snap.waypoint_index
        self.terminal_type = snap.terminal_type
        self.terminated = snap.terminated
        self.truncated = snap.truncated
        self._events = list(snap.causal_events)
        self._reward_acc = snap.reward_acc

    # ------------------------------------------------------------------
    # step
    # ------------------------------------------------------------------

    def step(self, action: int) -> tuple[Observation, float, bool, bool, dict]:
        if self.terminated or self.truncated:
            raise RuntimeError("step called after episode end")
        if self.tape is None:
            raise RuntimeError("reset() must be called before step()")

        t = self.step_index
        info_events: list[TraceEvent] = []
        route_event: str | None = None
        dash_occurred = False

        # --- 1. agent 移动 + collision check（monster_enabled 时）---
        agent_before = self.agent_xy
        dx, dy = ACTION_DELTA[action]
        nx, ny = agent_before[0] + dx, agent_before[1] + dy
        if self._in_bounds(nx, ny) and (nx, ny) not in OBSTACLES:
            self.agent_xy = (nx, ny)
        self._emit(t, _action_token(action), LOW_MODULE, "agent", info_events)

        if self.monster_enabled and self.agent_xy == self.monster_xy:
            self._collide(t, info_events)
            self._finish_step(info_events)
            return self._observe(), self.rewards["collision"], True, False, {
                "events": info_events,
                "route_event": route_event,
                "dash_occurred": dash_occurred,
            }

        # --- 2. route event（按动作前后到当前 waypoint 的最短路距离）---
        waypoint = WAYPOINTS_BY_OPTION[self.option][self.waypoint_index]
        d_before = bfs_distance(agent_before, waypoint)
        d_after = bfs_distance(self.agent_xy, waypoint)
        if d_after < d_before:
            route_event = TOKEN_ROUTE_PROGRESS
            self._emit(t, TOKEN_ROUTE_PROGRESS, LOW_MODULE, "env", info_events)
        elif d_after > d_before:
            route_event = TOKEN_ROUTE_DEVIATE
            self._emit(t, TOKEN_ROUTE_DEVIATE, LOW_MODULE, "env", info_events)
        # 相等：不发 route token

        # waypoint 推进（到达当前 waypoint 且不是终点）
        if (
            self.agent_xy == waypoint
            and self.waypoint_index < len(WAYPOINTS_BY_OPTION[self.option]) - 1
        ):
            self.waypoint_index += 1

        # --- 3. monster phase ---
        if self.monster_enabled and t % self.monster_move_period == 0:
            dash_occurred = self._monster_phase(t, info_events)
            if self.terminated:  # monster 撞上 agent
                self._finish_step(info_events)
                return self._observe(), self.rewards["collision"], True, False, {
                    "events": info_events,
                    "route_event": route_event,
                    "dash_occurred": dash_occurred,
                }

        # --- 4. distance event（monster phase 后 BFS 距离）---
        d = bfs_distance(self.agent_xy, self.monster_xy)
        if d <= 2:
            self._emit(t, TOKEN_DIST_NEAR, ENV_MODULE, "env", info_events)
        elif d <= 4:
            self._emit(t, TOKEN_DIST_MID, ENV_MODULE, "env", info_events)
        else:
            self._emit(t, TOKEN_DIST_FAR, ENV_MODULE, "env", info_events)

        # --- 5. EXIT / TIMEOUT check ---
        reward = self.rewards["step"]
        terminated, truncated = False, False
        if self.agent_xy == GOAL:
            self.terminated = True
            self.terminal_type = TERM_EXIT
            terminated, truncated = True, False
            reward = self.rewards["exit"]
            self._emit(t, TOKEN_EXIT, ENV_MODULE, "env", info_events)
        elif self.step_index + 1 >= self.horizon:
            self.truncated = True
            self.terminal_type = TERM_TIMEOUT
            terminated, truncated = False, True
            reward = self.rewards["timeout"]
            self._emit(t, TOKEN_TIMEOUT, ENV_MODULE, "env", info_events)

        self._finish_step(info_events)
        return self._observe(), reward, terminated, truncated, {
            "events": info_events,
            "route_event": route_event,
            "dash_occurred": dash_occurred,
        }

    # ------------------------------------------------------------------
    # monster phase
    # ------------------------------------------------------------------

    def _monster_phase(self, t: int, info_events: list[TraceEvent]) -> bool:
        """基础移动 -> collision -> dash -> collision。返回是否发生 dash。"""
        mi = self.monster_move_index
        dash_occurred = False

        # 基础移动
        self._move_monster_once(t, mi, TOKEN_MONSTER_NORMAL, info_events)
        if self.agent_xy == self.monster_xy:
            self._collide(t, info_events)
            return dash_occurred

        # dash（除非被干预阻止）
        dash_blocked = (
            self._interventions is not None
            and mi in self._interventions.blocked_dash_indices
        )
        if (
            not dash_blocked
            and self.tape is not None
            and self.tape.dash_roll(mi) < self.monster_dash_p
        ):
            dash_occurred = True
            self._dash_log.append(mi)
            # dash 方向使用 tie_break_u[horizon + mi]
            self._move_monster_once(
                t, self.horizon + mi, TOKEN_MONSTER_DASH, info_events
            )
            if self.agent_xy == self.monster_xy:
                self._collide(t, info_events)

        self.monster_move_index += 1
        return dash_occurred

    def _move_monster_once(
        self,
        t: int,
        tie_index: int,
        token: str,
        info_events: list[TraceEvent],
    ) -> None:
        """Monster 用 BFS 朝 agent 走一步；同长最短路用 tape tie-break 决定。"""
        assert self.tape is not None
        candidates = self._bfs_one_step(self.monster_xy, self.agent_xy)
        if not candidates:
            return
        u = self.tape.tie_break(tie_index)
        chosen = candidates[int(u * len(candidates)) % len(candidates)]
        self.monster_xy = chosen
        self._emit(t, token, ENV_MODULE, "env", info_events)

    def _bfs_one_step(
        self, start: tuple[int, int], goal: tuple[int, int]
    ) -> list[tuple[int, int]]:
        """返回使得到 goal 的 BFS 距离减 1 的合法邻居（可能多个）。"""
        best: list[tuple[int, int]] = []
        best_d = 10**9
        x, y = start
        for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            nx, ny = x + dx, y + dy
            if not self._in_bounds(nx, ny) or (nx, ny) in OBSTACLES:
                continue
            if (nx, ny) == goal:
                return [(nx, ny)]
            d = bfs_distance((nx, ny), goal)
            if d < best_d:
                best_d = d
                best = [(nx, ny)]
            elif d == best_d:
                best.append((nx, ny))
        return best

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _collide(self, t: int, info_events: list[TraceEvent]) -> None:
        self.terminal_type = TERM_COLLISION
        self.terminated = True
        self._emit(t, TOKEN_COLLISION, ENV_MODULE, "env", info_events)

    def _finish_step(self, info_events: list[TraceEvent]) -> None:
        # 已 emit 的事件加入全局记录（rollout 需要完整事件序列）
        self.step_index += 1
        self._events.extend(info_events)

    def _emit(
        self,
        t: int,
        token: str,
        module: str,
        source: str,
        bucket: list[TraceEvent] | None = None,
    ) -> None:
        ev = TraceEvent(t=t, token=token, module=module, source=source)
        if bucket is None:
            self._events.append(ev)
        else:
            bucket.append(ev)

    def _in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def _observe(self) -> Observation:
        assert self.tape is not None
        return Observation(
            monster_start_lane=self.tape.monster_start_lane,
            agent_xy=self.agent_xy,
            monster_xy=self.monster_xy,
            option=self.option,
            step_index=self.step_index,
            waypoint_index=self.waypoint_index,
            terminal_type=self.terminal_type,
        )

    @property
    def events(self) -> tuple[TraceEvent, ...]:
        return tuple(self._events)

    @property
    def reward_acc(self) -> float:
        return self._reward_acc

    @property
    def dash_log(self) -> tuple[int, ...]:
        return tuple(self._dash_log)

    def __repr__(self) -> str:
        return (
            f"CausalChaseEnv(agent={self.agent_xy}, monster={self.monster_xy}, "
            f"t={self.step_index}, term={self.terminal_type})"
        )
