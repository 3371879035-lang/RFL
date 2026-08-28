"""learner CounterfactualRunner：Full-RFL 自己的受限反事实验证（S06）。

与 evaluator 侧 exhaustive 验证的关键区别：
- 只验证 Top-K 候选 cause（默认 2）
- 低层只搜索最后 W_CF=3 个 factual decision（每个试其余 4 个动作）
- learner 侧绝不读取 ground-truth responsibility 相关结果
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .env import CausalChaseEnv
from .policies import Policy, rollout_to_trace
from .trace import EpisodeTrace
from .types import (
    ACTIONS,
    OPTION_LOWER,
    OPTION_UPPER,
    InterventionSet,
)


@dataclass
class CounterfactualResult:
    checked_causes: list[str] = field(default_factory=list)
    delta: dict[str, float] = field(default_factory=dict)
    verified: set[str] = field(default_factory=set)
    cf_rollouts: int = 0
    cf_transitions: int = 0
    critical_low_t: int | None = None


class CounterfactualRunner:
    """受限 counterfactual verification（learner 专用，无 evaluator 依赖）。

    policy_for(option: int) -> Policy：factual 冻结策略工厂。
    """

    def __init__(
        self,
        *,
        policy_for,
        env: CausalChaseEnv | None = None,
        top_k: int = 2,
        low_level_window: int = 3,
    ) -> None:
        self._policy_for = policy_for
        self._top_k = top_k
        self._window = low_level_window
        if env is not None:
            self._env = CausalChaseEnv(
                horizon=env.horizon,
                monster_move_period=env.monster_move_period,
                monster_dash_p=env.monster_dash_p,
                monster_enabled=env.monster_enabled,
                rewards=dict(env.rewards),
                width=env.width,
                height=env.height,
            )
        else:
            self._env = CausalChaseEnv()

    def verify(
        self,
        trace: EpisodeTrace,
        candidates: list[str],
    ) -> CounterfactualResult:
        """对候选 cause 执行验证，返回 delta（未验证的 cause 保持 0）。"""
        tape = trace.noise_tape
        if tape is None:
            raise ValueError("trace has no noise tape")
        J0 = trace.total_return
        result = CounterfactualResult(checked_causes=list(candidates))

        if "H" in candidates:
            alt = OPTION_LOWER if trace.option == OPTION_UPPER else OPTION_UPPER
            alt_tr = rollout_to_trace(
                self._env,
                tape=tape,
                option=alt,
                policy=self._policy_for(alt),
                seed=trace.seed,
                scenario_id=trace.scenario_id + "_rfl_cfH",
            )
            result.cf_rollouts += 1
            result.cf_transitions += alt_tr.n_transitions
            result.delta["H"] = alt_tr.total_return - J0

        if "L" in candidates:
            result.delta["L"], t_star, n_roll, n_tr = self._verify_low(trace)
            result.critical_low_t = t_star
            result.cf_rollouts += n_roll
            result.cf_transitions += n_tr

        if "E" in candidates:
            best_e = 0.0
            for dash_idx in trace.env_meta.get("dash_log", []):
                inv = InterventionSet(blocked_dash_indices=frozenset({dash_idx}))
                cf_tr = rollout_to_trace(
                    self._env,
                    tape=tape,
                    option=trace.option,
                    policy=self._policy_for(trace.option),
                    seed=trace.seed,
                    scenario_id=trace.scenario_id + f"_rfl_cfE_{dash_idx}",
                    interventions=inv,
                )
                result.cf_rollouts += 1
                result.cf_transitions += cf_tr.n_transitions
                gain = cf_tr.total_return - J0
                if gain > best_e:
                    best_e = gain
            result.delta["E"] = best_e

        result.verified = {
            c for c in result.delta if result.delta[c] > 0.0
        }
        return result

    # ------------------------------------------------------------------
    def _verify_low(self, trace: EpisodeTrace):
        """低层：最后 W_CF 个 decision，每个试其余 4 个动作。"""
        tape = trace.noise_tape
        assert tape is not None
        J0 = trace.total_return
        n = len(trace.transitions)
        t0 = max(0, n - self._window)
        best = 0.0
        t_star = None
        rollouts = 0
        transitions = 0
        n_actions = len(ACTIONS)
        for t in range(t0, n):
            factual_a = trace.transitions[t].action
            for a in range(n_actions):
                if a == factual_a:
                    continue
                inv = InterventionSet(action_override={t: a})
                cf_tr = rollout_to_trace(
                    self._env,
                    tape=tape,
                    option=trace.option,
                    policy=self._policy_for(trace.option),
                    seed=trace.seed,
                    scenario_id=trace.scenario_id + f"_rfl_cfL_{t}_{a}",
                    interventions=inv,
                )
                rollouts += 1
                transitions += cf_tr.n_transitions
                gain = cf_tr.total_return - J0
                if gain > best:
                    best = gain
                    t_star = t
        return best, t_star, rollouts, transitions
