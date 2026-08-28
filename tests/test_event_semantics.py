"""S02 验收：事件语义（route / distance / terminal token）。"""

from rflcc.env import CausalChaseEnv
from rflcc.types import (
    ACT_E,
    ACT_N,
    ACT_S,
    ACT_W,
    OPTION_LOWER,
    OPTION_UPPER,
    TOKEN_DIST_FAR,
    TOKEN_DIST_MID,
    TOKEN_DIST_NEAR,
    TOKEN_ROUTE_DEVIATE,
    TOKEN_ROUTE_PROGRESS,
)


def test_progress_token_only_when_closer():
    env = CausalChaseEnv()
    env.reset(seed=1, option=OPTION_UPPER)
    # 起点 (1,3)，waypoint (2,1)：先东到 (2,3) —— 更近？(1,3)->(2,3) dist=3, 初始 dist(1,3, (2,1))=3
    # 到 (2,3) 后 dist=2 < 3 -> PROGRESS
    obs, _, _, _, info = env.step(ACT_E)
    assert info["route_event"] == TOKEN_ROUTE_PROGRESS


def test_equal_distance_no_route_token():
    env = CausalChaseEnv()
    env.reset(seed=2, option=OPTION_LOWER)
    # 起点 (1,3)，waypoint (2,5)：dist((1,3),(2,5)) = 3
    # WAIT 不移动 -> d_after == d_before -> 无 route token
    obs, _, _, _, info = env.step(4)  # WAIT
    assert info["route_event"] is None


def test_dist_event_always_present():
    env = CausalChaseEnv()
    env.reset(seed=4, option=OPTION_UPPER)
    obs, _, _, _, info = env.step(ACT_N)
    tokens = [e.token for e in info["events"]]
    assert any(
        tok in tokens for tok in (TOKEN_DIST_NEAR, TOKEN_DIST_MID, TOKEN_DIST_FAR)
    )


def test_upper_lower_option_tokens():
    e1 = CausalChaseEnv()
    e1.reset(seed=6, option=OPTION_UPPER)
    assert "OPT_UPPER" in [e.token for e in e1.events]
    e2 = CausalChaseEnv()
    e2.reset(seed=6, option=OPTION_LOWER)
    assert "OPT_LOWER" in [e.token for e in e2.events]
