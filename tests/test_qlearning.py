"""S08 验收：Tabular Q-learning 数值正确性、epsilon 调度、B0/B1 smoke。"""

import numpy as np
import pytest

from rflcc.baselines.standard import StandardHQ
from rflcc.env import CausalChaseEnv
from rflcc.qtables import QTables, linear_epsilon


def test_linear_epsilon_endpoints():
    assert linear_epsilon(0, 0.20, 0.02, 3000) == pytest.approx(0.20)
    assert linear_epsilon(3000, 0.20, 0.02, 3000) == pytest.approx(0.02)
    assert linear_epsilon(5000, 0.20, 0.02, 3000) == pytest.approx(0.02)
    assert linear_epsilon(1500, 0.20, 0.02, 3000) == pytest.approx(0.11)


def test_linear_epsilon_monotonic():
    eps = [linear_epsilon(e, 0.2, 0.02, 100) for e in range(120)]
    assert all(eps[i] >= eps[i + 1] for i in range(len(eps) - 1))


def test_qlow_td_update_correct():
    q = QTables()
    s = (1, 3, 6, 1, 0, 0)
    s2 = (2, 3, 6, 1, 0, 1)
    alpha, gamma, r = 0.2, 0.97, -0.01
    agent = StandardHQ(alpha_low=alpha, alpha_high=0.15, gamma=gamma)
    # 初始 0；一步 TD：target = r + gamma*0 = -0.01
    agent.update_low(s, 2, r, s2, done=False)
    assert q.low_get(s, 2) == pytest.approx(0.0)
    assert agent.q.low_get(s, 2) == pytest.approx(alpha * (-0.01))
    # 第二次：target = r + gamma*max(s2)；s2 的 max 仍是 0
    agent.update_low(s, 2, r, s2, done=False)
    # 第一次后 old=-0.002；第二次 target=-0.01 -> -0.002 + 0.2*(-0.008)
    assert agent.q.low_get(s, 2) == pytest.approx(-0.002 + 0.2 * (-0.008))


def test_no_bootstrap_on_done():
    agent = StandardHQ(alpha_low=0.5, alpha_high=0.15, gamma=0.97)
    s = (1, 3, 6, 1, 0, 0)
    # terminated/truncated 时 target = r（不 bootstrap）
    agent.update_low(s, 2, 1.0, s, done=True)
    assert agent.q.low_get(s, 2) == pytest.approx(0.5 * 1.0)


def test_ghigh_episodic_mc():
    agent = StandardHQ(alpha_low=0.2, alpha_high=0.15, gamma=0.97)
    agent.update_high(0, 1, -0.5)
    assert agent.q.high_get(0, 1) == pytest.approx(0.15 * (-0.5))
    agent.update_high(0, 1, 1.0)
    expected = 0.15 * (-0.5) + 0.15 * (1.0 - 0.15 * (-0.5))
    assert agent.q.high_get(0, 1) == pytest.approx(expected)


def test_greedy_selection():
    agent = StandardHQ(rng=np.random.RandomState(0))
    agent.q.low_update((0, 0, 1, 1, 0, 0), 2, 1.0, 1.0)
    assert agent.select_action((0, 0, 1, 1, 0, 0), 0.0) == 2
    agent.q.high_update(0, 1, 2.0, 1.0)
    assert agent.select_option(0, 0.0) == 1


def test_eval_epsilon_zero_greedy():
    agent = StandardHQ(rng=np.random.RandomState(1))
    agent.q.low_update((2, 3, 6, 1, 0, 1), 2, 5.0, 1.0)
    for _ in range(20):
        assert agent.select_action((2, 3, 6, 1, 0, 1), 0.0) == 2


def _run_smoke(stage: str, seed: int):
    from scripts.experiment_b import run_learning

    cfg = {"environment": {"horizon": 30, "monster_move_period": 2,
                           "monster_dash_p": 0.10, "gamma": 0.97, "rewards": None},
           "learning": {"alpha_low": 0.20, "alpha_high": 0.15, "alpha_diag": 0.10,
                        "epsilon_start": 0.20, "epsilon_end": 0.02,
                        "epsilon_decay_episodes": 3000},
           "replay": {"ordinary_replay_k": 5},
           "counterfactual": {"top_k_causes": 2, "low_level_window": 3},
           "sequence": {"beta_prior": 1.0, "probability_floor": 0.01,
                        "adjacent_weight_eta": 0.5, "temperature": 0.5},
           "scenarios": {"calibration_seed_offset": 1_000_000,
                         "acceptance": {"delta_target_pos": 0.4, "delta_leak": 0.1}},
           "experiment": {"training_episodes": 3000, "feedback": {"p_false_symmetric": 0.4}}}
    return run_learning(cfg, stage, "standard", seed=seed, episodes=3000,
                        eval_every=500, use_scripted_low=(stage in ("B1", "B2")),
                        outdir="outputs/_test", run_id="test")


def test_b0_no_monster_learns():
    # B0：无 monster，tabular Q 应学会到达 goal
    res = _run_smoke("B0", seed=0)
    assert res["final_success"] >= 0.95


def test_b1_high_level_learns_safe_option():
    res = _run_smoke("B1", seed=0)
    assert res["final_safe_option"] >= 0.90
