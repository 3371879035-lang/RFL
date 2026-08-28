"""S08 验收：evaluation 是只读的（Q 与模型状态前后 bitwise 不变）。"""

import numpy as np

from rflcc.baselines.standard import StandardHQ
from rflcc.env import CausalChaseEnv
from rflcc.qtables import QTables
from rflcc.types import TERM_EXIT


def test_evaluation_is_read_only():
    agent = StandardHQ(
        alpha_low=0.2, alpha_high=0.15, gamma=0.97,
        rng=np.random.RandomState(0),
    )
    # 预训练一点状态（monster off，800 episodes 足够学到基本导航）
    env = CausalChaseEnv(monster_enabled=False)
    for ep in range(800):
        obs, _ = env.reset(seed=ep)
        s_h = obs.monster_start_lane
        option = agent.select_option(s_h, 0.3)
        env.set_option(option)
        done = False
        rewards = []
        while not done:
            a = agent.select_action(obs.low_state, 0.3)
            obs2, r, term, trunc, _ = env.step(a)
            agent.update_low(obs.low_state, a, r, obs2.low_state, term or trunc)
            rewards.append(r)
            obs = obs2
            done = term or trunc
        G = 0.0
        for r in reversed(rewards):
            G = r + 0.97 * G
        agent.update_high(s_h, option, G)

    q_before = agent.q.deep_hash()

    # 只读评估（不要求 success，重点：评估前后 Q bitwise 不变）
    for k in range(30):
        obs, _ = env.reset(seed=1000 + k)
        s_h = obs.monster_start_lane
        option = agent.select_option(s_h, 0.0)
        env.set_option(option)
        done = False
        while not done:
            a = agent.select_action(obs.low_state, 0.0)
            obs, r, term, trunc, _ = env.step(a)
            done = term or trunc

    q_after = agent.q.deep_hash()
    assert q_before == q_after
