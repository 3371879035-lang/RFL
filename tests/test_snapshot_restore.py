"""S02 验收：snapshot -> rollout -> restore -> rollout 完全一致。"""

from rflcc.env import CausalChaseEnv
from rflcc.types import (
    ACT_E,
    ACT_N,
    ACT_S,
    ACT_W,
    ACT_WAIT,
    OPTION_UPPER,
)


def rollout_from_current(env: CausalChaseEnv, actions: list[int]):
    tokens = []
    rewards = []
    for a in actions:
        if env.terminated or env.truncated:
            break
        obs, r, term, trunc, info = env.step(a)
        tokens.extend([e.token for e in info["events"]])
        rewards.append((r, term, trunc))
        if term or trunc:
            break
    return tokens, rewards


def test_snapshot_restore_is_exact():
    env = CausalChaseEnv()
    env.reset(seed=7, option=OPTION_UPPER)
    env.step(ACT_E)
    snap = env.snapshot()

    traj_a = rollout_from_current(env, [ACT_N, ACT_E, ACT_WAIT])

    env.restore(snap)
    traj_b = rollout_from_current(env, [ACT_N, ACT_E, ACT_WAIT])

    assert traj_a == traj_b


def test_snapshot_restore_after_monster_phase():
    env = CausalChaseEnv()
    env.reset(seed=11, option=OPTION_UPPER)
    for a in (ACT_E, ACT_E, ACT_WAIT, ACT_WAIT):
        if env.terminated or env.truncated:
            break
        env.step(a)
    snap = env.snapshot()

    traj_a = rollout_from_current(env, [ACT_E, ACT_W, ACT_N, ACT_WAIT, ACT_E])
    env.restore(snap)
    traj_b = rollout_from_current(env, [ACT_E, ACT_W, ACT_N, ACT_WAIT, ACT_E])
    assert traj_a == traj_b


def test_restore_restores_all_fields():
    env = CausalChaseEnv()
    env.reset(seed=13, option=OPTION_UPPER)
    env.step(ACT_E)
    env.step(ACT_E)
    snap = env.snapshot()

    # 继续走直到改变状态
    for _ in range(4):
        if env.terminated or env.truncated:
            break
        env.step(ACT_W)

    env.restore(snap)
    assert env.agent_xy == snap.agent_xy
    assert env.monster_xy == snap.monster_xy
    assert env.option == snap.option
    assert env.step_index == snap.step_index
    assert env.monster_move_index == snap.monster_move_index
    assert env.waypoint_index == snap.waypoint_index
    assert env.terminal_type == snap.terminal_type
    assert [e.token for e in env.events] == [e.token for e in snap.causal_events]


def test_restore_after_terminal():
    env = CausalChaseEnv()
    env.reset(seed=5, option=OPTION_UPPER)
    env.agent_xy = (2, 2)
    env.monster_xy = (2, 3)
    obs, r, term, trunc, _ = env.step(ACT_S)
    assert term is True
    snap = env.snapshot()
    # 恢复后回到终止状态
    env.restore(snap)
    assert env.terminated is True
    assert env.terminal_type == "COLLISION"
