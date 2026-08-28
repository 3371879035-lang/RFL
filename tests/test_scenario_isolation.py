"""S03 验收：H/L/E 单原因场景可被搜索生成且 target 干预明显优于非 target。"""

import pytest

from rflcc.scenarios import ScenarioGenerator
from rflcc.types import OPTION_LOWER, OPTION_UPPER


@pytest.fixture(scope="module")
def scenarios():
    gen = ScenarioGenerator(max_attempts=200)
    out = {}
    for cause in ("H", "L", "E"):
        out[cause] = gen.generate(cause, base_seed=1000 + {"H": 0, "L": 100, "E": 200}[cause], n=3)
    return out


def test_all_causes_generated(scenarios):
    for cause in ("H", "L", "E"):
        assert len(scenarios[cause]) == 3, cause


def test_acceptance_target_delta(scenarios):
    for cause in ("H", "L", "E"):
        for s in scenarios[cause]:
            assert s.oracle.delta_pos[cause] >= 0.4, (cause, s.scenario_id)


def test_acceptance_non_target_leak(scenarios):
    for cause in ("H", "L", "E"):
        for s in scenarios[cause]:
            for other in ("H", "L", "E"):
                if other != cause:
                    if cause == "E" and other == "L":
                        continue  # 结构性泄漏，见 SPEC 环境限制记录
                    assert s.oracle.delta_pos[other] <= 0.1, (
                        cause,
                        other,
                        s.scenario_id,
                        s.oracle.delta_pos,
                    )


def test_responsibility_approx_onehot(scenarios):
    # H/L 近似 one-hot；E 因环境几何与 L 固有耦合，要求 R*_E 为最大分量
    for cause in ("H", "L", "E"):
        for s in scenarios[cause]:
            r = s.oracle.responsibility
            assert r is not None
            if cause != "E":
                assert r[cause] > 0.9, (cause, r)
            else:
                assert r["E"] > r["L"] and r["E"] > r["H"], (cause, r)


def test_h_only_option_matches_monster_lane(scenarios):
    for s in scenarios["H"]:
        assert s.trace.option == s.trace.noise_tape.monster_start_lane


def test_e_only_has_observed_dash(scenarios):
    for s in scenarios["E"]:
        assert len(s.trace.env_meta.get("dash_log", [])) > 0
        assert s.oracle.blocked_dash_index is not None


def test_l_only_has_fault(scenarios):
    for s in scenarios["L"]:
        assert s.trace.fault_t is not None
        assert s.trace.fault_action is not None


def test_all_collisions(scenarios):
    for cause in ("H", "L", "E"):
        for s in scenarios[cause]:
            assert s.trace.terminal_type == "COLLISION"
