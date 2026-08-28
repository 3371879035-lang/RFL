"""S06 验收：learner CounterfactualRunner 语义与防泄漏。"""

import copy

import pytest

from rflcc.counterfactual import CounterfactualRunner
from rflcc.env import CausalChaseEnv
from rflcc.noise import NoiseTape
from rflcc.oracle import OracleEvaluator
from rflcc.policies import ScriptedRouteFollower, rollout_to_trace
from rflcc.types import (
    OPTION_LOWER,
    OPTION_UPPER,
    TERM_COLLISION,
)


def _runner(env=None):
    return CounterfactualRunner(
        policy_for=lambda o: ScriptedRouteFollower(o),
        env=env if env is not None else CausalChaseEnv(),
        top_k=2,
        low_level_window=3,
    )


def _h_trace(seed: int = 5):
    env = CausalChaseEnv()
    tape = NoiseTape.from_seed(seed)
    opt = tape.monster_start_lane
    tr = rollout_to_trace(
        env, tape=tape, option=opt, policy=ScriptedRouteFollower(opt),
        seed=seed, scenario_id="CF_H",
    )
    assert tr.terminal_type == TERM_COLLISION
    return env, tape, tr


def test_cf_does_not_mutate_env_or_tape():
    env, tape, trace = _h_trace()
    tape_before = NoiseTape(
        seed=tape.seed, monster_start_lane=tape.monster_start_lane,
        tie_break_u=tape.tie_break_u, dash_u=tape.dash_u, horizon=tape.horizon,
    )
    snap = env.snapshot()
    _runner(env).verify(trace, candidates=["H", "L", "E"])
    assert tape == tape_before
    assert env.snapshot() == snap


def test_high_level_cf_regenerates_actions():
    _, tape, trace = _h_trace()
    res = _runner().verify(trace, candidates=["H"])
    # alternative option 且动作被重新生成（rollout 从头用 alt policy）
    assert "H" in res.delta
    assert res.delta["H"] > 0.0


def test_low_level_window_limited():
    _, tape, trace = _h_trace()
    n = len(trace.transitions)
    runner = CounterfactualRunner(
        policy_for=lambda o: ScriptedRouteFollower(o), low_level_window=3
    )
    res = runner.verify(trace, candidates=["L"])
    # 每个候选 (t, a') 一次 rollout；t 只取最后 3 个 decision
    expected_rollouts = 3 * (5 - 1)
    assert res.cf_rollouts == expected_rollouts
    assert res.critical_low_t is not None
    assert res.critical_low_t >= n - 3


def test_top_k_candidates_checked():
    _, tape, trace = _h_trace()
    res = _runner().verify(trace, candidates=["H", "E"])
    assert res.checked_causes == ["H", "E"]
    assert "L" not in res.delta or res.delta["L"] == 0.0


def test_verified_causes_positive_delta():
    _, tape, trace = _h_trace()
    res = _runner().verify(trace, candidates=["H", "L", "E"])
    assert res.verified == {c for c in res.delta if res.delta[c] > 0.0}


def test_cf_counts_transitions():
    _, tape, trace = _h_trace()
    res = _runner().verify(trace, candidates=["H"])
    assert res.cf_rollouts >= 1
    assert res.cf_transitions >= res.cf_rollouts


def test_no_oracle_leakage_in_counterfactual_module():
    import inspect

    import rflcc.counterfactual as mod

    src = inspect.getsource(mod)
    for forbidden in ("OracleEvaluator", "oracle_delta", "oracle_R", "oracle_responsibility"):
        assert forbidden not in src, forbidden


def test_counterfactual_runner_signature_no_oracle():
    import inspect

    sig = inspect.signature(CounterfactualRunner.verify)
    params = " ".join(sig.parameters)
    assert "oracle" not in params
