"""OracleEvaluator：exhaustive counterfactual ground truth（仅 evaluator 使用）。"""

from __future__ import annotations

from dataclasses import dataclass, field

from .env import CausalChaseEnv
from .policies import Policy, rollout_to_trace
from .trace import EpisodeTrace
from .types import (
    ACTIONS,
    CAUSES,
    OPTION_LOWER,
    OPTION_UPPER,
    InterventionSet,
)


@dataclass
class OracleResult:
    delta: dict[str, float] = field(default_factory=dict)  # raw delta（可负）
    delta_pos: dict[str, float] = field(default_factory=dict)  # max(delta, 0)
    responsibility: dict[str, float] | None = None  # None = UNRESOLVED
    primary: str | None = None
    unresolved: bool = False
    low_candidates_checked: int = 0
    cf_rollouts: int = 0
    cf_transitions: int = 0
    alternative_option: int | None = None
    actions_regenerated: bool = False
    blocked_dash_index: int | None = None
    critical_low_t: int | None = None

    @property
    def is_resolved(self) -> bool:
        return self.responsibility is not None


def normalize_responsibility(delta_pos: dict[str, float]) -> dict[str, float] | None:
    """R* = delta_pos / sum(delta_pos)；全零 -> UNRESOLVED（禁止 uniform）。"""
    total = sum(delta_pos.values())
    if total <= 0.0:
        return None
    return {k: v / total for k, v in delta_pos.items()}


class OracleEvaluator:
    """Exhaustive counterfactual evaluator。

    - H: 换 option 后从初态用 policy_for(alt_option) 重新生成动作（同一 NoiseTape）
    - L: 遍历 factual 每个 decision，尝试其余全部 (A-1) 个动作，之后 frozen policy 继续
    - E: 遍历 observed dash，阻止一个 dash，其他外生变量不变

    learner 绝不接收本对象或其输出。
    """

    def __init__(
        self,
        *,
        policy_for,
        env: CausalChaseEnv | None = None,
    ) -> None:
        """policy_for(option: int) -> Policy：factual 的冻结策略工厂。

        内部使用独立 env 副本（只复制配置，不共享状态），evaluate 绝不
        修改调用方传入的 env。
        """
        self._policy_for = policy_for
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

    # ------------------------------------------------------------------
    def evaluate(self, trace: EpisodeTrace) -> OracleResult:
        tape = trace.noise_tape
        if tape is None:
            raise ValueError("trace has no noise tape")
        J0 = trace.total_return

        deltas: dict[str, float] = {c: 0.0 for c in CAUSES}
        rollouts = 0
        transitions = 0
        alt_option: int | None = None
        actions_regenerated = False
        blocked_dash: int | None = None
        critical_low_t: int | None = None

        # --- H: 换 option ---
        alt_option = OPTION_LOWER if trace.option == OPTION_UPPER else OPTION_UPPER
        alt_tr = rollout_to_trace(
            self._env,
            tape=tape,
            option=alt_option,
            policy=self._policy_for(alt_option),
            seed=trace.seed,
            scenario_id=trace.scenario_id + "_cfH",
        )
        rollouts += 1
        transitions += alt_tr.n_transitions
        deltas["H"] = alt_tr.total_return - J0
        actions_regenerated = True

        # --- L: 每个 decision x 其余 (A-1) 动作 ---
        n_actions = len(ACTIONS)
        best_l = 0.0
        for t, tr in enumerate(trace.transitions):
            factual_a = tr.action
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
                    scenario_id=trace.scenario_id + f"_cfL_{t}_{a}",
                    interventions=inv,
                )
                rollouts += 1
                transitions += cf_tr.n_transitions
                gain = cf_tr.total_return - J0
                if gain > best_l:
                    best_l = gain
                    critical_low_t = t
        deltas["L"] = best_l

        # --- E: 阻止 observed dash ---
        best_e = 0.0
        for dash_idx in trace.env_meta.get("dash_log", []):
            inv = InterventionSet(blocked_dash_indices=frozenset({dash_idx}))
            cf_tr = rollout_to_trace(
                self._env,
                tape=tape,
                option=trace.option,
                policy=self._policy_for(trace.option),
                seed=trace.seed,
                scenario_id=trace.scenario_id + f"_cfE_{dash_idx}",
                interventions=inv,
            )
            rollouts += 1
            transitions += cf_tr.n_transitions
            gain = cf_tr.total_return - J0
            if gain > best_e:
                best_e = gain
                blocked_dash = dash_idx
        deltas["E"] = best_e

        delta_pos = {k: max(0.0, v) for k, v in deltas.items()}
        resp = normalize_responsibility(delta_pos)
        primary = None
        if resp is not None:
            primary = max(CAUSES, key=lambda c: resp[c])

        low_candidates = len(trace.transitions) * (n_actions - 1)
        return OracleResult(
            delta=deltas,
            delta_pos=delta_pos,
            responsibility=resp,
            primary=primary,
            unresolved=resp is None,
            low_candidates_checked=low_candidates,
            cf_rollouts=rollouts,
            cf_transitions=transitions,
            alternative_option=alt_option,
            actions_regenerated=actions_regenerated,
            blocked_dash_index=blocked_dash,
            critical_low_t=critical_low_t,
        )
