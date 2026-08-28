"""S03 验收：Oracle exhaustive 语义、动作重新生成、UNRESOLVED、dash 干预保真。"""

import pytest

from rflcc.env import CausalChaseEnv
from rflcc.noise import NoiseTape
from rflcc.oracle import OracleEvaluator, normalize_responsibility
from rflcc.policies import ScriptedRouteFollower, rollout_to_trace
from rflcc.types import (
    ACT_E,
    ACT_N,
    ACT_S,
    ACT_W,
    ACTIONS,
    OPTION_LOWER,
    OPTION_UPPER,
    TERM_COLLISION,
    InterventionSet,
)

ACT_A, ACT_B, ACT_C, ACT_D, ACT_WAIT = 0, 1, 2, 3, 4


def _oracle(env=None):
    return OracleEvaluator(
        policy_for=lambda o: ScriptedRouteFollower(o),
        env=env if env is not None else CausalChaseEnv(),
    )


def _roll_collision(seed: int, option: int):
    """构造一个必然 COLLISION 的轨迹：agent 直接走向怪物（同路线）。"""
    env = CausalChaseEnv()
    tape = NoiseTape.from_seed(seed)
    # option = 怪物所在路线保证碰撞
    opt = tape.monster_start_lane
    trace = rollout_to_trace(
        env,
        tape=tape,
        option=opt,
        policy=ScriptedRouteFollower(opt),
        seed=seed,
        scenario_id=f"T_{seed}",
    )
    assert trace.terminal_type == TERM_COLLISION
    return env, tape, trace


def test_oracle_low_level_is_exhaustive():
    env, tape, trace = _roll_collision(3, OPTION_UPPER)
    result = _oracle(env).evaluate(trace)
    expected = len(trace.transitions) * (len(ACTIONS) - 1)
    assert result.low_candidates_checked == expected


def test_high_level_cf_regenerates_actions():
    env, tape, trace = _roll_collision(5, OPTION_UPPER)
    result = _oracle(env).evaluate(trace)
    assert result.alternative_option != trace.option
    assert result.actions_regenerated is True


def test_oracle_delta_directions():
    # 同路线碰撞：换 option 应显著改善
    env, tape, trace = _roll_collision(11, OPTION_UPPER)
    result = _oracle(env).evaluate(trace)
    # H 改善通常为正（换路线能逃生）
    assert result.delta["H"] > 0.0
    assert result.primary == "H"
    assert result.responsibility is not None
    assert abs(sum(result.responsibility.values()) - 1.0) < 1e-9


def test_normalize_responsibility_unresolved():
    assert normalize_responsibility({"H": 0.0, "L": 0.0, "E": 0.0}) is None
    r = normalize_responsibility({"H": 0.5, "L": 0.3, "E": 0.2})
    assert r is not None
    assert abs(sum(r.values()) - 1.0) < 1e-9
    assert r["H"] == pytest.approx(0.5)


def test_dash_intervention_preserves_other_noise():
    """blocked dash 干预不改变干预点之前的轨迹。"""
    env = CausalChaseEnv()
    tape = NoiseTape.from_seed(100)
    option = OPTION_LOWER if tape.monster_start_lane == OPTION_UPPER else OPTION_UPPER
    script = ScriptedRouteFollower(option)
    trace = rollout_to_trace(
        env, tape=tape, option=option, policy=script,
        seed=100, scenario_id="DASH",
    )
    dash_log = trace.env_meta.get("dash_log", [])
    if not dash_log:
        pytest.skip("no dash occurred for this seed")
    j = dash_log[0]
    inv = InterventionSet(blocked_dash_indices=frozenset({j}))
    cf = rollout_to_trace(
        env, tape=tape, option=option, policy=script,
        seed=100, scenario_id="DASH_CF", interventions=inv,
    )
    # 干预前的 token 序列一致：找到 dash 对应的事件位置
    fact_tokens = [e.token for e in trace.causal_events]
    cf_tokens = [e.token for e in cf.causal_events]
    # 前 3 个 monster phase 前的 token 应一致（dash 在 mi=... 时发生）
    dash_event_idx = next(
        (i for i, tok in enumerate(fact_tokens) if tok == "MONSTER_DASH"), None
    )
    if dash_event_idx is not None:
        prefix = fact_tokens[:dash_event_idx]
        assert cf_tokens[:dash_event_idx] == prefix


def test_oracle_does_not_mutate_env():
    env, tape, trace = _roll_collision(7, OPTION_UPPER)
    snap = env.snapshot()
    _oracle(env).evaluate(trace)
    after = env.snapshot()
    assert snap == after
