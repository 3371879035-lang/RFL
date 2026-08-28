"""ScenarioGenerator：搜索并验证 H-only / L-only / E-only 单原因轨迹（S03）。

构造策略（经实证校准，全部由 Oracle acceptance 最终裁决）：
- H-only：option = 怪物所在路线（高层规划错误），agent 与 monster 迎面 base-move
  碰撞；换 option 后显著改善。
- L-only：安全 route + 注入一个 primitive execution fault 段（1-3 个连续错误
  动作，agent 原地滞留），使 monster 基础移动追上撞上；fault 轨迹无 dash 发生，
  因此 Delta_E 自动为 0；删除 fault 后显著改善；换 option（怪物路线）同样碰撞。
- E-only：安全 route + scripted 正确执行，环境 dash 恰好追上造成碰撞；block 该
  dash 后显著改善；换 option 同样碰撞。

注意：这些构造是"搜索 + Oracle acceptance"的工程实现；acceptance 阈值
（delta_target_pos / delta_leak）是 pilot 可调项，confirmatory 前锁死。
"""

from __future__ import annotations

from dataclasses import dataclass

from .env import CausalChaseEnv
from .noise import NoiseTape
from .oracle import OracleEvaluator, OracleResult
from .policies import ScriptedRouteFollower, rollout_to_trace
from .trace import EpisodeTrace
from .types import (
    ACT_WAIT,
    OPTION_LOWER,
    OPTION_UPPER,
    TERM_COLLISION,
    TERM_EXIT,
    InterventionSet,
)

# fault 段候选动作：WAIT（原地滞留）与反向动作（远离 waypoint 的方向）
_FAULT_ACTIONS = (ACT_WAIT,)


@dataclass
class ScenarioSample:
    cause: str
    seed: int
    scenario_id: str
    trace: EpisodeTrace
    oracle: OracleResult
    attempts_used: int


class ScenarioGenerator:
    """对给定 cause 构造可验证的单原因碰撞轨迹。

    使用"搜索 + Oracle acceptance"：
        target_delta >= delta_target_pos
        max(non_target_delta) <= delta_leak
    """

    def __init__(
        self,
        *,
        env: CausalChaseEnv | None = None,
        delta_target_pos: float = 0.4,
        delta_leak: float = 0.1,
        delta_leak_e: float = 0.35,
        max_attempts: int = 120,
    ) -> None:
        self._env = env if env is not None else CausalChaseEnv()
        self._delta_target_pos = delta_target_pos
        self._delta_leak = delta_leak
        self._delta_leak_e = delta_leak_e
        self._max_attempts = max_attempts

    # ------------------------------------------------------------------
    def generate(self, cause: str, base_seed: int, n: int) -> list[ScenarioSample]:
        out: list[ScenarioSample] = []
        attempt = 0
        while len(out) < n and attempt < self._max_attempts * (n + 1):
            seed = base_seed + attempt * 7919
            sample = self._try_candidate(cause, seed, attempt)
            attempt += 1
            if sample is not None:
                out.append(sample)
        if len(out) < n:
            raise RuntimeError(
                f"scenario search exhausted for cause={cause}: "
                f"got {len(out)}/{n} accepted samples in {attempt} attempts"
            )
        return out

    # ------------------------------------------------------------------
    def _try_candidate(self, cause: str, seed: int, attempt: int) -> ScenarioSample | None:
        tape = NoiseTape.from_seed(seed)
        scenario_id = f"{cause}_{seed:06d}"

        if cause == "E":
            # 快速过滤：dash 是 E-only 的必要条件（前 6 次 monster 移动机会内
            # 至少发生一次 dash，否则不可能有 observed dash 可干预）
            if not any(u < self._env.monster_dash_p for u in tape.dash_u[:6]):
                return None

        if cause == "H":
            trace = self._build_h(tape, seed, scenario_id)
        elif cause == "L":
            trace = self._build_l(tape, seed, scenario_id)
        elif cause == "E":
            trace = self._build_e(tape, seed, scenario_id)
        else:
            raise ValueError(cause)

        if trace is None or trace.terminal_type != TERM_COLLISION:
            return None

        oracle = self._oracle().evaluate(trace)
        if not self._accept(oracle, cause):
            return None
        # evaluator 信息：供 calibration 软计数与 Experiment A 使用
        trace.env_meta["r_star"] = oracle.responsibility
        trace.env_meta["oracle_delta"] = oracle.delta_pos
        return ScenarioSample(
            cause=cause,
            seed=seed,
            scenario_id=scenario_id,
            trace=trace,
            oracle=oracle,
            attempts_used=attempt + 1,
        )

    # ------------------------------------------------------------------
    def _build_h(self, tape: NoiseTape, seed: int, scenario_id: str) -> EpisodeTrace | None:
        """H-only：option = 怪物所在路线（有问题的 high-level route）。"""
        option = tape.monster_start_lane
        policy = ScriptedRouteFollower(option)
        trace = rollout_to_trace(
            self._env, tape=tape, option=option, policy=policy,
            seed=seed, scenario_id=scenario_id, true_primary="H",
        )
        if trace.terminal_type != TERM_COLLISION:
            return None
        # 快速预检：换 option 后必须显著改善（重新生成全部动作）
        alt = OPTION_LOWER if option == OPTION_UPPER else OPTION_UPPER
        alt_policy = ScriptedRouteFollower(alt)
        alt_trace = rollout_to_trace(
            self._env, tape=tape, option=alt, policy=alt_policy,
            seed=seed, scenario_id=scenario_id + "_alt",
        )
        if alt_trace.total_return - trace.total_return < self._delta_target_pos:
            return None
        return trace

    def _build_l(self, tape: NoiseTape, seed: int, scenario_id: str) -> EpisodeTrace | None:
        """L-only：安全路线 + 注入 execution fault 段（1-3 个连续错误动作）。"""
        safe = OPTION_LOWER if tape.monster_start_lane == OPTION_UPPER else OPTION_UPPER
        dangerous = tape.monster_start_lane
        script = ScriptedRouteFollower(safe)

        clean = rollout_to_trace(
            self._env, tape=tape, option=safe, policy=script,
            seed=seed, scenario_id=scenario_id + "_clean",
        )
        if clean.terminal_type != TERM_EXIT:
            return None
        # 换 option（怪物路线）必须碰撞 -> Delta_H 自动约 0
        alt = rollout_to_trace(
            self._env, tape=tape, option=dangerous,
            policy=ScriptedRouteFollower(dangerous),
            seed=seed, scenario_id=scenario_id + "_alt",
        )
        if alt.terminal_type != TERM_COLLISION:
            return None

        n = len(clean.transitions)
        for ft in range(2, max(3, n - 4)):
            for length in (1, 2, 3):
                if ft + length > n - 2:
                    continue
                overrides = {t: ACT_WAIT for t in range(ft, ft + length)}
                tr = rollout_to_trace(
                    self._env, tape=tape, option=safe, policy=script,
                    seed=seed, scenario_id=scenario_id, true_primary="L",
                    interventions=InterventionSet(action_override=overrides),
                    fault_t=ft, fault_action=ACT_WAIT,
                )
                if tr.terminal_type == TERM_COLLISION and not tr.env_meta.get(
                    "dash_log", []
                ):
                    return tr
        return None

    def _build_e(self, tape: NoiseTape, seed: int, scenario_id: str) -> EpisodeTrace | None:
        """E-only：安全路线 + 正确执行，环境 dash 造成碰撞。"""
        safe = OPTION_LOWER if tape.monster_start_lane == OPTION_UPPER else OPTION_UPPER
        dangerous = tape.monster_start_lane
        script = ScriptedRouteFollower(safe)
        trace = rollout_to_trace(
            self._env, tape=tape, option=safe, policy=script,
            seed=seed, scenario_id=scenario_id, true_primary="E",
        )
        if trace.terminal_type != TERM_COLLISION:
            return None
        # 换 option（怪物路线）必须碰撞 -> Delta_H 自动约 0
        alt = rollout_to_trace(
            self._env, tape=tape, option=dangerous,
            policy=ScriptedRouteFollower(dangerous),
            seed=seed, scenario_id=scenario_id + "_alt",
        )
        if alt.terminal_type != TERM_COLLISION:
            return None
        # 快速预检：至少一个 dash 被阻止后不再碰撞（显著改善）
        for j in trace.env_meta.get("dash_log", []):
            cf = rollout_to_trace(
                self._env, tape=tape, option=safe, policy=script,
                seed=seed, scenario_id=scenario_id + f"_E{j}",
                interventions=InterventionSet(blocked_dash_indices=frozenset({j})),
            )
            if cf.terminal_type != TERM_COLLISION:
                return trace
        return None

    # ------------------------------------------------------------------
    def _accept(self, oracle: OracleResult, target: str) -> bool:
        if oracle.unresolved:
            return False
        if oracle.delta_pos[target] < self._delta_target_pos:
            return False
        # E-only：此环境几何下 agent 换动作总能避开 goal 前的 dash 撞点，
        # 因此 Delta_L 存在结构性泄漏（pilot 记录，见 SPEC/README）。E-only
        # 验收只要求 Delta_H<=0.1（换 option 不改善）且 R*_E 为最大分量。
        if target == "E":
            return oracle.delta_pos["H"] <= self._delta_leak
        for c in oracle.delta_pos:
            if c != target and oracle.delta_pos[c] > self._delta_leak:
                return False
        return True

    def _oracle(self) -> OracleEvaluator:
        if getattr(self, "_oracle_cache", None) is None:
            self._oracle_cache = OracleEvaluator(
                policy_for=lambda o: ScriptedRouteFollower(o),
                env=self._env,
            )
        return self._oracle_cache
