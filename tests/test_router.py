"""S09 验收：Router 的 rho 映射、last-action routing、E-only 环境责任不惩罚。"""

import pytest

from rflcc.qtables import QTables
from rflcc.router import UpdateRouter, responsibility_to_rho


def test_rho_mapping_high():
    rho_h, rho_l = responsibility_to_rho({"H": 1.0, "L": 0.0, "E": 0.0})
    assert rho_h == pytest.approx(-1.0)
    assert rho_l == pytest.approx(0.0)


def test_rho_mapping_low():
    rho_h, rho_l = responsibility_to_rho({"H": 0.0, "L": 1.0, "E": 0.0})
    assert rho_h == pytest.approx(0.0)
    assert rho_l == pytest.approx(-1.0)


def test_rho_mapping_simultaneous():
    rho_h, rho_l = responsibility_to_rho({"H": 0.3, "L": 0.5, "E": 0.2})
    assert rho_h == pytest.approx(-0.3)
    assert rho_l == pytest.approx(-0.5)


def test_e_only_no_internal_punishment():
    """E-only（R_E 主导）时 rho_H/rho_L 应为 0（环境责任不直接惩罚内部模块）。"""
    router = UpdateRouter(alpha_diag=0.1)
    routed = router.route(
        responsibility={"H": 0.0, "L": 0.0, "E": 1.0},
        s_h=0, option=1,
        last_low=((2, 3, 6, 1, 1, 1), 2),
    )
    assert routed.update_mass["H"] == pytest.approx(0.0)
    assert routed.update_mass["L"] == pytest.approx(0.0)
    assert routed.high is None or routed.high[2] == 0.0
    assert routed.low is None or routed.low[2] == 0.0


def test_last_action_routing_used():
    router = UpdateRouter(alpha_diag=0.1)
    routed = router.route(
        responsibility={"H": 0.0, "L": 1.0, "E": 0.0},
        s_h=1, option=0,
        last_low=((5, 5, 6, 1, 0, 1), 2),
    )
    assert routed.low == ((5, 5, 6, 1, 0, 1), 2, -0.1)
    assert routed.high == (1, 0, 0.0)
    assert routed.update_mass["L"] == pytest.approx(0.1)


def test_cf_critical_secondary_flag_default_off():
    router = UpdateRouter(alpha_diag=0.1, use_cf_critical=False)
    routed = router.route(
        responsibility={"H": 0.0, "L": 1.0, "E": 0.0},
        s_h=0, option=1,
        last_low=((1, 1, 6, 1, 1, 1), 3),
        critical_low=((9, 9, 0, 0, 0, 0), 0),  # 假设 CF 找到更早的 site
    )
    # 默认用 last-action
    assert routed.low[0] == (1, 1, 6, 1, 1, 1)
    router2 = UpdateRouter(alpha_diag=0.1, use_cf_critical=True)
    routed2 = router2.route(
        responsibility={"H": 0.0, "L": 1.0, "E": 0.0},
        s_h=0, option=1,
        last_low=((1, 1, 6, 1, 1, 1), 3),
        critical_low=((9, 9, 0, 0, 0, 0), 0),
    )
    assert routed2.low[0] == (9, 9, 0, 0, 0, 0)


def test_router_apply_updates_q():
    q = QTables()
    router = UpdateRouter(alpha_diag=0.1)
    routed = router.route(
        responsibility={"H": 1.0, "L": 0.0, "E": 0.0},
        s_h=0, option=0,
        last_low=((1, 3, 6, 1, 0, 0), 2),
    )
    router.apply(q, routed)
    assert q.high_get(0, 0) == pytest.approx(-0.1)
    assert q.low_get((1, 3, 6, 1, 0, 0), 2) == pytest.approx(0.0)


def test_abstention_no_update():
    router = UpdateRouter(alpha_diag=0.1)
    routed = router.route(responsibility=None, s_h=0, option=0, last_low=None)
    assert routed.update_mass == {"H": 0.0, "L": 0.0}
