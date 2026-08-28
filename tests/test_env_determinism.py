"""S02 验收：同 seed+actions 得到完全一致轨迹、事件语义、reward 精确。"""

from rflcc.env import CausalChaseEnv
from rflcc.noise import NoiseTape
from rflcc.types import (
    ACT_E,
    ACT_N,
    ACT_S,
    ACT_W,
    ACT_WAIT,
    OPTION_LOWER,
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
)

EAST, NORTH, SOUTH, WEST, WAIT = ACT_E, ACT_N, ACT_S, ACT_W, ACT_WAIT


def rollout(env: CausalChaseEnv, actions: list[int]):
    """从当前状态按 action list 滚动；环境终止后停止。"""
    events = []
    rewards = []
    for a in actions:
        if env.terminated or env.truncated:
            break
        obs, r, term, trunc, info = env.step(a)
        events.extend(info["events"])
        rewards.append(r)
        if term or trunc:
            break
    return [e.token for e in events], rewards


def test_same_seed_same_actions_identical_trajectory():
    tape1 = NoiseTape.from_seed(123, horizon=30)
    tape2 = NoiseTape.from_seed(123, horizon=30)
    actions = [EAST, EAST, NORTH, WAIT, EAST, SOUTH, WEST]

    env1 = CausalChaseEnv()
    env1.reset(noise_tape=tape1)
    t1, _ = rollout(env1, actions)

    env2 = CausalChaseEnv()
    env2.reset(noise_tape=tape2)
    t2, _ = rollout(env2, actions)

    assert t1 == t2


def test_same_seed_same_actions_identical_trajectory_from_seed():
    actions = [EAST, EAST, NORTH, WAIT, EAST]
    env1 = CausalChaseEnv()
    env1.reset(seed=321)
    t1, _ = rollout(env1, actions)
    env2 = CausalChaseEnv()
    env2.reset(seed=321)
    t2, _ = rollout(env2, actions)
    assert t1 == t2


def test_route_progress_not_deviation():
    # 从 (2,1) 向 waypoint (6,1) EAST 属于正常推进
    env = CausalChaseEnv()
    env.reset(seed=1, option=OPTION_UPPER)
    env.agent_xy = (2, 1)
    env.waypoint_index = 1  # 当前 waypoint 是 (6,1)
    obs, _, _, _, info = env.step(EAST)
    assert info["route_event"] == TOKEN_ROUTE_PROGRESS


def test_route_deviation_detected():
    env = CausalChaseEnv()
    env.reset(seed=1, option=OPTION_UPPER)
    # 从 (2,1) 向 waypoint (6,1) 走 WEST 是偏离
    env.agent_xy = (2, 1)
    env.waypoint_index = 1
    obs, _, _, _, info = env.step(WEST)
    assert info["route_event"] == TOKEN_ROUTE_DEVIATE


def test_reward_terminal_semantics_exit():
    env = CausalChaseEnv(monster_enabled=False)
    env.reset(seed=5, option=OPTION_UPPER)
    env.agent_xy = (6, 3)
    env.waypoint_index = 2
    obs, r, term, trunc, info = env.step(EAST)
    assert r == REWARD_EXIT
    assert term is True
    assert trunc is False
    assert info["events"][-1].token == TOKEN_EXIT


def test_reward_terminal_semantics_collision():
    env = CausalChaseEnv()
    env.reset(seed=5)
    env.agent_xy = (2, 2)
    env.monster_xy = (2, 3)
    obs, r, term, trunc, _ = env.step(SOUTH)
    assert r == REWARD_COLLISION
    assert term is True
    assert trunc is False


def test_reward_step_penalty():
    env = CausalChaseEnv()
    env.reset(seed=5, option=OPTION_UPPER)
    obs, r, term, trunc, _ = env.step(WAIT)
    assert r == REWARD_STEP
    assert term is False
    assert trunc is False


def test_timeout_semantics():
    env = CausalChaseEnv(monster_enabled=False, horizon=3)
    env.reset(seed=5, option=OPTION_UPPER)
    # 走到 timeout：agent 停在原地远离 goal
    for _ in range(3):
        obs, r, term, trunc, _ = env.step(WAIT)
    assert env.terminal_type == TERM_TIMEOUT
    assert env.truncated is True


def test_feedback_token_not_in_causal_events():
    env = CausalChaseEnv()
    env.reset(seed=5, option=OPTION_UPPER)
    obs, *_ = env.step(EAST)
    tokens = [e.token for e in env.events]
    assert all(not tok.startswith("FEEDBACK_") for tok in tokens)
    assert TOKEN_ACT_E in tokens
    assert TOKEN_OPT_UPPER in tokens


def test_monster_events_present():
    env = CausalChaseEnv()
    env.reset(seed=7, option=OPTION_UPPER)
    # 走几步触发 monster phase
    for _ in range(8):
        if env.terminated or env.truncated:
            break
        env.step(WAIT)
    tokens = [e.token for e in env.events]
    assert TOKEN_MONSTER_NORMAL in tokens or TOKEN_MONSTER_DASH in tokens
    # distance 事件必须在每步出现
    assert any(tok in tokens for tok in (TOKEN_DIST_NEAR, TOKEN_DIST_MID, TOKEN_DIST_FAR))


def test_distance_event_buckets():
    env = CausalChaseEnv()
    env.reset(seed=3, option=OPTION_UPPER)
    env.step(WAIT)
    # monster 与 agent 初始距离：(1,3) -> (6,1) BFS 距离 5+ -> FAR
    tokens = [e.token for e in env.events]
    assert TOKEN_DIST_FAR in tokens


def test_option_events():
    env = CausalChaseEnv()
    env.reset(seed=3, option=OPTION_LOWER)
    tokens = [e.token for e in env.events]
    assert TOKEN_OPT_LOWER in tokens


def test_blocked_action_no_move():
    env = CausalChaseEnv()
    env.reset(seed=3, option=OPTION_UPPER)
    env.agent_xy = (2, 2)  # 右侧 (3,2) 是障碍
    obs, *_ = env.step(EAST)
    assert obs.agent_xy == (2, 2)


def test_terminal_types_exhaustive():
    assert TERM_EXIT in ("EXIT",)
    assert TERM_COLLISION in ("COLLISION",)
    assert TERM_TIMEOUT in ("TIMEOUT",)
